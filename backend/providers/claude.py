import os
import sys
import json
import time
import random
import datetime
import base64
import ctypes
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, List

if sys.platform == "win32":
    import ctypes.wintypes

from backend.providers.base import BaseProvider
from backend.diagnostics.logging_engine import ErrorCategory


# ---------------------------------------------------------------------------
# Zero-Dependency Windows DPAPI & CNG AES-256-GCM Decryption
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    class BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.ULONG), ("dwInfoVersion", ctypes.wintypes.ULONG),
            ("pbNonce", ctypes.c_void_p), ("cbNonce", ctypes.wintypes.ULONG),
            ("pbAuthData", ctypes.c_void_p), ("cbAuthData", ctypes.wintypes.ULONG),
            ("pbTag", ctypes.c_void_p), ("cbTag", ctypes.wintypes.ULONG),
            ("pbMacContext", ctypes.c_void_p), ("cbMacContext", ctypes.wintypes.ULONG),
            ("cbAAD", ctypes.wintypes.ULONG), ("cbData", ctypes.c_ulonglong), ("dwFlags", ctypes.wintypes.ULONG),
        ]

def dpapi_decrypt_win32(encrypted_bytes: bytes) -> bytes:
    """Decrypts DPAPI encrypted bytes using native Windows crypt32.dll."""
    if sys.platform != "win32" or not encrypted_bytes:
        return b""
    try:
        blob_in = DATA_BLOB(len(encrypted_bytes), ctypes.create_string_buffer(encrypted_bytes, len(encrypted_bytes)))
        blob_out = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
            return b""
        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return data
    except Exception:
        return b""

def aes_gcm_decrypt_win32(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes) -> bytes:
    """Decrypts AES-256-GCM ciphertext using native Windows CNG (bcrypt.dll)."""
    if sys.platform != "win32" or not key or not nonce or not ciphertext:
        return b""
    try:
        bcrypt = ctypes.windll.bcrypt
        hAlg = ctypes.c_void_p()
        bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(hAlg), ctypes.c_wchar_p("AES"), None, 0)
        chain_mode = "ChainingModeGCM".encode("utf-16le") + b"\x00\x00"
        bcrypt.BCryptSetProperty(hAlg, ctypes.c_wchar_p("ChainingMode"), chain_mode, len(chain_mode), 0)
        hKey = ctypes.c_void_p()
        bcrypt.BCryptGenerateSymmetricKey(hAlg, ctypes.byref(hKey), None, 0, key, len(key), 0)
        nonce_buf = ctypes.create_string_buffer(nonce, len(nonce))
        tag_buf = ctypes.create_string_buffer(tag, len(tag))
        auth_info = BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO()
        auth_info.cbSize = ctypes.sizeof(BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO)
        auth_info.dwInfoVersion = 1
        auth_info.pbNonce = ctypes.cast(nonce_buf, ctypes.c_void_p)
        auth_info.cbNonce = len(nonce)
        auth_info.pbTag = ctypes.cast(tag_buf, ctypes.c_void_p)
        auth_info.cbTag = len(tag)
        out_buf = ctypes.create_string_buffer(len(ciphertext))
        pcbResult = ctypes.wintypes.ULONG()
        status = bcrypt.BCryptDecrypt(hKey, ciphertext, len(ciphertext), ctypes.byref(auth_info), None, 0, out_buf, len(ciphertext), ctypes.byref(pcbResult), 0)
        bcrypt.BCryptDestroyKey(hKey)
        bcrypt.BCryptCloseAlgorithmProvider(hAlg, 0)
        if status != 0:
            return b""
        return out_buf.raw[:pcbResult.value]
    except Exception:
        return b""


# ---------------------------------------------------------------------------
# Zero-Dependency Pure-Python Blink-Snappy & V8 Integer Extraction
# ---------------------------------------------------------------------------
def snappy_decompress(data: bytes) -> bytes:
    """Zero-dependency pure-Python Snappy frame decompressor for Chromium/Blink IndexedDB records."""
    if not data:
        return b""
    pos = 0
    n = len(data)
    uncompressed_len = 0
    shift = 0
    while pos < n:
        b = data[pos]
        pos += 1
        uncompressed_len |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    out = bytearray()
    while pos < n and len(out) < uncompressed_len:
        tag = data[pos]
        pos += 1
        tag_type = tag & 0x03
        if tag_type == 0:
            length = (tag >> 2) + 1
            if length > 60:
                extra_bytes = length - 60
                if pos + extra_bytes > n:
                    break
                length = int.from_bytes(data[pos:pos+extra_bytes], "little") + 1
                pos += extra_bytes
            out.extend(data[pos:pos+length])
            pos += length
        else:
            if tag_type == 1:
                if pos >= n:
                    break
                length = ((tag >> 2) & 0x07) + 4
                offset = ((tag & 0xe0) << 3) | data[pos]
                pos += 1
            elif tag_type == 2:
                if pos + 2 > n:
                    break
                length = (tag >> 2) + 1
                offset = int.from_bytes(data[pos:pos+2], "little")
                pos += 2
            else:
                if pos + 4 > n:
                    break
                length = (tag >> 2) + 1
                offset = int.from_bytes(data[pos:pos+4], "little")
                pos += 4
            if offset == 0 or offset > len(out):
                break
            start = len(out) - offset
            for i in range(length):
                out.append(out[start + i])
    return bytes(out)

def read_zigzag_varint(buf: bytes, idx: int) -> int:
    val = 0
    shift = 0
    while idx < len(buf):
        b = buf[idx]
        idx += 1
        val |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    return (val >> 1) ^ -(val & 1)

def extract_v8_int(chunk: bytes, field_name: bytes) -> int:
    marker = b'"' + bytes([len(field_name)]) + field_name + b'I'
    pos = chunk.find(marker)
    if pos == -1:
        return 0
    return max(0, read_zigzag_varint(chunk, pos + len(marker)))


class ClaudeProvider(BaseProvider):
    """
    Claude (Anthropic) Multi-Mode Usage Provider.
    Supports: Direct API poller, Transparent Proxy ingestion, CLI cache scanner, and Simulation.
    """

    @staticmethod
    def is_valid_anthropic_api_key(key: Optional[str]) -> bool:
        """Validates that a string has the structural signature of an Anthropic API key."""
        if not key or not isinstance(key, str):
            return False
        k = key.strip()
        if k.lower() in ("proxy", "dummy", "vault", "local", "demo", "mock", "none", "sk-ant-secret123", "sk-ant-sec...", "sk-ant-secret-999", "sk-ant-dummy"):
            return False
        if "..." in k or k.endswith("."):
            return False
        if not k.startswith("sk-ant-"):
            return False
        if len(k) < 30:
            return False
        return True

    def __init__(self, database, vault, diagnostics):
        super().__init__(database, vault, diagnostics)
        self._simulation_mode = False
        self._cached_plan = "Team Enterprise"
        self._tokens_limit = 400000
        self._requests_limit = 1000

        # AIUM-909: In-memory TTL cache and 429 rate limit backoff guards
        self._oauth_telemetry_cache: Optional[Dict[str, Any]] = None
        self._oauth_telemetry_cache_time: float = 0.0
        self._oauth_rate_limited_until: float = 0.0
        self._oauth_cache_ttl_seconds: float = 300.0  # 5 minutes

        # AIUM-909: Automatic sanitization of invalid placeholder keys from vault
        if hasattr(self.vault, "get_credential") and hasattr(self.vault, "delete_credential"):
            try:
                cur_key = self.vault.get_credential("claude", "default")
                if cur_key and not self.is_valid_anthropic_api_key(cur_key):
                    self.vault.delete_credential("claude", "default")
            except Exception:
                pass

    def calibrate_limits(
        self,
        session_used_pct: Optional[float] = None,
        session_remaining_pct: Optional[float] = None,
        session_reset_seconds: Optional[int] = None,
        session_reset_str: Optional[str] = None,
        weekly_used_pct: Optional[float] = None,
        weekly_remaining_pct: Optional[float] = None,
        weekly_reset_str: Optional[str] = None,
        plan_type: Optional[str] = "Team Enterprise",
        scope: str = "individual",
        individual_session_used_pct: Optional[float] = None,
        individual_weekly_used_pct: Optional[float] = None,
        team_session_used_pct: Optional[float] = None,
        team_weekly_used_pct: Optional[float] = None,
        user_name: Optional[str] = None,
        team_name: Optional[str] = None,
        dept_name: Optional[str] = None,
        org_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calibrates official Anthropic rolling session and weekly quota limits with
        multi-scope separation between Individual User limits and Team/Org pools.
        """
        # Resolve Individual limits
        if individual_session_used_pct is None:
            if scope == "individual" and session_used_pct is not None:
                individual_session_used_pct = session_used_pct
            elif scope == "individual" and session_remaining_pct is not None:
                individual_session_used_pct = max(0.0, 100.0 - float(session_remaining_pct))
            else:
                individual_session_used_pct = 60.0

        if individual_weekly_used_pct is None:
            if scope == "individual" and weekly_used_pct is not None:
                individual_weekly_used_pct = weekly_used_pct
            elif scope == "individual" and weekly_remaining_pct is not None:
                individual_weekly_used_pct = max(0.0, 100.0 - float(weekly_remaining_pct))
            else:
                individual_weekly_used_pct = 27.0

        # Resolve Team pool limits
        if team_session_used_pct is None:
            if scope == "team" and session_used_pct is not None:
                team_session_used_pct = session_used_pct
            elif scope == "team" and session_remaining_pct is not None:
                team_session_used_pct = max(0.0, 100.0 - float(session_remaining_pct))
            else:
                team_session_used_pct = 56.0

        if team_weekly_used_pct is None:
            if scope == "team" and weekly_used_pct is not None:
                team_weekly_used_pct = weekly_used_pct
            elif scope == "team" and weekly_remaining_pct is not None:
                team_weekly_used_pct = max(0.0, 100.0 - float(weekly_remaining_pct))
            else:
                team_weekly_used_pct = 26.0

        ind_sess_rem = max(0.0, 100.0 - float(individual_session_used_pct))
        ind_week_rem = max(0.0, 100.0 - float(individual_weekly_used_pct))
        team_sess_rem = max(0.0, 100.0 - float(team_session_used_pct))
        team_week_rem = max(0.0, 100.0 - float(team_weekly_used_pct))

        final_sess_rem = ind_sess_rem if scope == "individual" else team_sess_rem
        final_week_rem = ind_week_rem if scope == "individual" else team_week_rem
        final_week_reset = str(weekly_reset_str) if weekly_reset_str else "Mon 3:00 AM"

        if session_reset_seconds is not None:
            reset_epoch = time.time() + int(session_reset_seconds)
        else:
            reset_epoch = time.time() + 7560  # Default ~2 hr 6 min

        if plan_type:
            self._cached_plan = plan_type

        default_user = os.environ.get("USERNAME") or os.environ.get("USER") or "James Eckhardt"
        self.db.update_provider_snapshot(
            provider="claude",
            plan_type=self._cached_plan,
            session_remaining_pct=final_sess_rem,
            weekly_remaining_pct=final_week_rem,
            weekly_reset_str=final_week_reset,
            reset_epoch=reset_epoch,
            status="ACTIVE",
            user_name=user_name or default_user,
            team_name=team_name or "Synthesis Engineering Core",
            dept_name=dept_name or "Technology & AI Architecture",
            org_name=org_name or "Synthesis Software Technologies",
            individual_session_rem_pct=ind_sess_rem,
            individual_weekly_rem_pct=ind_week_rem,
            team_session_rem_pct=team_sess_rem,
            team_weekly_rem_pct=team_week_rem,
            active_scope=scope
        )
        self.diagnostics.mark_provider_healthy("claude")
        return {
            "success": True,
            "scope": scope,
            "session_remaining_pct": final_sess_rem,
            "session_used_pct": round(100.0 - final_sess_rem, 1),
            "weekly_remaining_pct": final_week_rem,
            "weekly_used_pct": round(100.0 - final_week_rem, 1),
            "individual": {
                "session_remaining_pct": ind_sess_rem,
                "session_used_pct": round(float(individual_session_used_pct), 1),
                "weekly_remaining_pct": ind_week_rem,
                "weekly_used_pct": round(float(individual_weekly_used_pct), 1)
            },
            "team": {
                "session_remaining_pct": team_sess_rem,
                "session_used_pct": round(float(team_session_used_pct), 1),
                "weekly_remaining_pct": team_week_rem,
                "weekly_used_pct": round(float(team_weekly_used_pct), 1)
            },
            "reset_epoch": reset_epoch,
            "weekly_reset_str": final_week_reset,
            "plan_type": self._cached_plan
        }

    @property
    def provider_name(self) -> str:
        return "claude"

    @property
    def display_name(self) -> str:
        return "Claude (Anthropic)"

    def enable_simulation_mode(self, enabled: bool = True):
        self._simulation_mode = enabled

    def is_simulation_mode(self) -> bool:
        return self._simulation_mode

    def parse_rate_limit_headers(self, headers: Dict[str, str]) -> Dict[str, Any]:
        """Extracts and normalizes Anthropic rate limit headers."""
        norm_headers = {k.lower(): v for k, v in headers.items()}

        def _to_int(val):
            try:
                return int(val) if val is not None else None
            except (ValueError, TypeError):
                return None

        req_limit = _to_int(norm_headers.get("anthropic-ratelimit-requests-limit"))
        req_rem = _to_int(norm_headers.get("anthropic-ratelimit-requests-remaining"))
        tok_limit = _to_int(norm_headers.get("anthropic-ratelimit-tokens-limit"))
        tok_rem = _to_int(norm_headers.get("anthropic-ratelimit-tokens-remaining"))
        tok_reset_str = norm_headers.get("anthropic-ratelimit-tokens-reset")

        reset_epoch = None
        if tok_reset_str:
            try:
                # ISO timestamp like 2026-10-05T14:00:00Z or seconds
                if "T" in str(tok_reset_str):
                    dt = datetime.datetime.fromisoformat(tok_reset_str.replace("Z", "+00:00"))
                    reset_epoch = dt.timestamp()
                else:
                    reset_epoch = float(tok_reset_str)
            except Exception:
                reset_epoch = time.time() + 3600

        return {
            "requests_limit": req_limit,
            "requests_remaining": req_rem,
            "tokens_limit": tok_limit,
            "tokens_remaining": tok_rem,
            "reset_epoch": reset_epoch
        }

    def ingest_proxy_interaction(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        session_id: Optional[str] = None,
        rate_limit_headers: Optional[Dict[str, str]] = None,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        client_ip: Optional[str] = None,
        client_alias: Optional[str] = None
    ) -> str:
        """Called by transparent proxy or CLI scanner when a request completes."""
        # Estimate cost (approx Sonnet rates: $3/M in, $15/M out, $3.75/M cache write, $0.30/M cache read)
        cost = (
            (input_tokens * 0.000003) +
            (output_tokens * 0.000015) +
            (cache_creation_tokens * 0.00000375) +
            (cache_read_tokens * 0.0000003)
        )
        evt_id = self.db.record_usage_event(
            provider="claude",
            model=model or "claude-3-7-sonnet",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            session_id=session_id or f"proxy_{int(time.time())}",
            estimated_cost=cost,
            client_ip=client_ip,
            client_alias=client_alias
        )

        # Update rate limits if provided
        tokens_rem = None
        requests_rem = None
        reset_epoch = None
        if rate_limit_headers:
            parsed = self.parse_rate_limit_headers(rate_limit_headers)
            tokens_rem = parsed["tokens_remaining"]
            requests_rem = parsed["requests_remaining"]
            reset_epoch = parsed["reset_epoch"]

        existing_snaps = self.db.get_provider_snapshots()
        claude_snap = existing_snaps.get("claude", {})
        sess_rem = claude_snap.get("session_remaining_pct", 44.0)
        week_rem = claude_snap.get("weekly_remaining_pct", 74.0)
        week_reset = claude_snap.get("weekly_reset_str", "Mon 3:00 AM")

        self.db.update_provider_snapshot(
            provider="claude",
            plan_type=self._cached_plan,
            tokens_remaining=tokens_rem or 385000,
            requests_remaining=requests_rem or 950,
            reset_epoch=reset_epoch or claude_snap.get("reset_epoch") or (time.time() + 7560),
            status="ACTIVE",
            session_remaining_pct=sess_rem,
            weekly_remaining_pct=week_rem,
            weekly_reset_str=week_reset
        )
        self.diagnostics.mark_provider_healthy("claude")
        return evt_id

    def _get_claude_desktop_data_dirs(self) -> List[Path]:
        """Discovers Claude Desktop data directories on Windows."""
        dirs: List[Path] = []
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            claude_data_root = Path(local_appdata) / "Claude-Data"
            if claude_data_root.exists():
                for sub in claude_data_root.iterdir():
                    if sub.is_dir() and sub.name.startswith("claude_"):
                        dirs.append(sub)
                if not dirs:
                    dirs.append(claude_data_root)
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            appdata_claude = Path(appdata) / "Claude"
            if appdata_claude.exists() and appdata_claude not in dirs:
                dirs.append(appdata_claude)
        return dirs

    def _discover_oauth_token(self) -> Optional[str]:
        """Automatically discovers and decrypts Claude Desktop OAuth token from config.json using Windows DPAPI and CNG."""
        for d in self._get_claude_desktop_data_dirs():
            local_state_p = d / "Local State"
            config_p = d / "config.json"
            if not local_state_p.exists() or not config_p.exists():
                continue
            try:
                ls_data = json.loads(local_state_p.read_text(encoding="utf-8", errors="ignore"))
                enc_key_b64 = ls_data.get("os_crypt", {}).get("encrypted_key", "")
                if not enc_key_b64:
                    continue
                enc_key = base64.b64decode(enc_key_b64)
                if not enc_key.startswith(b"DPAPI"):
                    continue
                master_key = dpapi_decrypt_win32(enc_key[5:])
                if not master_key or len(master_key) != 32:
                    continue

                cfg_data = json.loads(config_p.read_text(encoding="utf-8", errors="ignore"))
                for token_key in ("oauth:tokenCacheV2", "oauth:tokenCache"):
                    raw_val = cfg_data.get(token_key, "")
                    if not raw_val:
                        continue
                    try:
                        raw_bytes = base64.b64decode(raw_val)
                        if raw_bytes.startswith(b"v10"):
                            nonce = raw_bytes[3:15]
                            ciphertext = raw_bytes[15:-16]
                            tag = raw_bytes[-16:]
                            plain = aes_gcm_decrypt_win32(master_key, nonce, ciphertext, tag)
                            if plain:
                                tokens_map = json.loads(plain.decode("utf-8", errors="ignore"))
                                for k, v in tokens_map.items():
                                    if "user:inference" in k and isinstance(v, dict) and v.get("token"):
                                        return v["token"]
                                for k, v in tokens_map.items():
                                    if isinstance(v, dict) and v.get("token"):
                                        return v["token"]
                    except Exception:
                        continue
            except Exception:
                continue

        # Check ~/.claude/.credentials.json fallback
        home_creds = Path.home() / ".claude" / ".credentials.json"
        if home_creds.exists():
            try:
                cdata = json.loads(home_creds.read_text(encoding="utf-8", errors="ignore"))
                for k, v in cdata.items():
                    if isinstance(v, dict) and v.get("accessToken"):
                        return v["accessToken"]
            except Exception:
                pass
        return None

    def _request_oauth_json(self, url: str) -> Optional[Dict[str, Any]]:
        """Makes an authenticated HTTP request using the decrypted OAuth token."""
        if time.time() < self._oauth_rate_limited_until:
            return None
        token = self._discover_oauth_token()
        if not token:
            return None
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-code/2.1.308",
            "Accept": "application/json"
        })
        try:
            with urllib.request.urlopen(req, timeout=7.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8", errors="ignore"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                self._oauth_rate_limited_until = time.time() + 600.0  # 10m backoff
            return None
        except Exception:
            return None
        return None

    def _parse_latest_plan_usage_sample(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts the latest 5-hour and 7-day utilization percentage from plan-usage-history.json."""
        samples = data.get("samples", [])
        if not samples:
            return {"fh": 0, "sd": 0}
        latest = samples[-1]
        u = latest.get("u", {})
        return {
            "fh": u.get("fh", 0),
            "sd": u.get("sd", 0),
            "timestamp": latest.get("t")
        }

    def _scan_offline_plan_history(self) -> Dict[str, Any]:
        """Offline fallback: scan plan-usage-history.json."""
        for d in self._get_claude_desktop_data_dirs():
            history_file = d / "plan-usage-history.json"
            if history_file.exists():
                try:
                    data = json.loads(history_file.read_text(encoding="utf-8", errors="ignore"))
                    sample = self._parse_latest_plan_usage_sample(data)
                    fh = sample.get("fh", 0)
                    sd = sample.get("sd", 0)
                    sess_rem = max(0.0, min(100.0, round(100.0 - float(fh), 1)))
                    week_rem = max(0.0, min(100.0, round(100.0 - float(sd), 1)))
                    self.db.update_provider_snapshot(
                        provider="claude",
                        plan_type="Claude Pro",
                        status="ACTIVE (Local Cache)",
                        session_remaining_pct=sess_rem,
                        weekly_remaining_pct=week_rem,
                        individual_session_rem_pct=sess_rem,
                        individual_weekly_rem_pct=week_rem,
                        active_scope="individual"
                    )
                    return {
                        "success": True,
                        "session_remaining_pct": sess_rem,
                        "weekly_remaining_pct": week_rem,
                        "fallback": True
                    }
                except Exception:
                    pass
        return {"success": False, "error": "Unable to fetch live OAuth telemetry or local plan history", "fallback": True}

    def fetch_live_oauth_telemetry(self, force: bool = False) -> Dict[str, Any]:
        """Fetches live personal session and weekly quotas directly from Anthropic OAuth API with fallback."""
        now = time.time()
        if not force and self._oauth_telemetry_cache and (now - self._oauth_telemetry_cache_time < self._oauth_cache_ttl_seconds):
            res = dict(self._oauth_telemetry_cache)
            res["cached"] = True
            return res

        if not force and now < self._oauth_rate_limited_until:
            if self._oauth_telemetry_cache:
                res = dict(self._oauth_telemetry_cache)
                res["cached"] = True
                return res
            return self._scan_offline_plan_history()

        usage_data = self._request_oauth_json("https://api.anthropic.com/api/oauth/usage")
        profile_data = self._request_oauth_json("https://api.anthropic.com/api/oauth/profile")

        if usage_data:
            fh = usage_data.get("five_hour", {}).get("utilization", 0.0)
            sd = usage_data.get("seven_day", {}).get("utilization", 0.0)
            sess_rem = max(0.0, min(100.0, round(100.0 - float(fh), 1)))
            week_rem = max(0.0, min(100.0, round(100.0 - float(sd), 1)))

            fh_resets = usage_data.get("five_hour", {}).get("resets_at")
            reset_epoch = None
            if fh_resets:
                try:
                    dt = datetime.datetime.fromisoformat(fh_resets.replace("Z", "+00:00"))
                    reset_epoch = dt.timestamp()
                except Exception:
                    pass

            sd_resets = usage_data.get("seven_day", {}).get("resets_at")
            weekly_reset_str = "Mon 3:00 AM"
            if sd_resets:
                try:
                    dt = datetime.datetime.fromisoformat(sd_resets.replace("Z", "+00:00"))
                    local_dt = dt.astimezone()
                    weekly_reset_str = local_dt.strftime("%a %I:%M %p")
                except Exception:
                    pass

            user_name = "James Christopher (Fourie) Eckhardt"
            team_name = "Synthesis 2"
            plan_type = "Claude Pro"
            if profile_data:
                user_name = profile_data.get("account", {}).get("full_name") or user_name
                org = profile_data.get("organization", {})
                team_name = org.get("name") or team_name
                rate_limit_tier = org.get("rate_limit_tier", "")
                seat_tier = org.get("seat_tier", "")
                if "max" in rate_limit_tier.lower() or "tier_1" in seat_tier.lower():
                    plan_type = "Claude Pro"

            self.db.update_provider_snapshot(
                provider="claude",
                plan_type=plan_type,
                tokens_remaining=350000,
                requests_remaining=850,
                reset_epoch=reset_epoch or (time.time() + 7200),
                status="ACTIVE (Live API)",
                session_remaining_pct=sess_rem,
                weekly_remaining_pct=week_rem,
                weekly_reset_str=weekly_reset_str,
                user_name=user_name,
                team_name=team_name,
                dept_name="Personal Pro",
                org_name=team_name,
                individual_session_rem_pct=sess_rem,
                individual_weekly_rem_pct=week_rem,
                active_scope="individual"
            )
            result = {
                "success": True,
                "session_remaining_pct": sess_rem,
                "weekly_remaining_pct": week_rem,
                "plan_type": plan_type,
                "user_name": user_name,
                "cached": False
            }
            self._oauth_telemetry_cache = result
            self._oauth_telemetry_cache_time = now
            return result

        return self._scan_offline_plan_history()

    def scan_desktop_indexeddb(self) -> int:
        """Scans Claude Desktop IndexedDB leveldb and blob storage for assistant turns and usage."""
        ingested_count = 0
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for d in self._get_claude_desktop_data_dirs():
            idb_root = d / "IndexedDB"
            if not idb_root.exists():
                continue
            idb_files: List[Path] = []
            for ext in ("*.blob", "*.log", "*.ldb"):
                idb_files.extend(idb_root.rglob(ext))

            for fp in idb_files:
                if fp.name in ("LOCK", "CURRENT", "LOG"):
                    continue
                try:
                    raw = fp.read_bytes()
                    if not raw:
                        continue
                    decompressed_chunks = [raw]
                    for m in re.finditer(rb'\xff\x11\x02', raw):
                        dec = snappy_decompress(raw[m.end():])
                        if len(dec) > 32:
                            decompressed_chunks.append(dec)

                    for chunk in decompressed_chunks:
                        for mm in re.finditer(rb'msg_01[a-zA-Z0-9]{15,30}', chunk):
                            mid = mm.group(0).decode("ascii", errors="ignore")
                            window = chunk[max(0, mm.start()-60):min(len(chunk), mm.end()+550)]
                            if b'output_tokens' not in window and b'input_tokens' not in window:
                                continue

                            model_m = re.search(rb'"\x05model"[\x05-\x25]([a-zA-Z0-9\-\._]+)', window)
                            model_name = model_m.group(1).decode("ascii", errors="ignore") if model_m else "claude-opus-5-5"

                            ts_m = re.search(rb'(202[0-9]-[0-9]{2}-[0-9]{2}T[0-9:\.]+Z)', window)
                            if ts_m:
                                ts = ts_m.group(1).decode("ascii")
                            else:
                                try:
                                    ts = datetime.datetime.fromtimestamp(fp.stat().st_mtime, datetime.timezone.utc).isoformat()
                                except Exception:
                                    ts = now_iso

                            sid_m = re.search(rb'session_id"[\x10-\x30]([a-zA-Z0-9\-_]+)', window)
                            session_id = sid_m.group(1).decode("ascii") if sid_m else f"desktop_{mid}"

                            in_tok = extract_v8_int(window, b"input_tokens")
                            out_tok = extract_v8_int(window, b"output_tokens")
                            cr_tok = extract_v8_int(window, b"cache_read_input_tokens")
                            cc_tok = extract_v8_int(window, b"cache_creation_input_tokens")
                            tot_toks = in_tok + out_tok + cr_tok + cc_tok

                            cost = (
                                (in_tok * 0.000003) +
                                (out_tok * 0.000015) +
                                (cc_tok * 0.00000375) +
                                (cr_tok * 0.0000003)
                            )

                            conn = self.db._get_connection()
                            c = conn.cursor()
                            c.execute(
                                "SELECT id, input_tokens, output_tokens, total_tokens FROM usage_events WHERE session_id = ? OR (provider = 'claude' AND external_id = ?)",
                                (f"desktop_{mid}", mid)
                            )
                            existing_row = c.fetchone()
                            conn.close()

                            if not existing_row:
                                self.db.record_usage_event(
                                    provider="claude",
                                    model=model_name,
                                    input_tokens=in_tok,
                                    output_tokens=out_tok,
                                    cache_creation_tokens=cc_tok,
                                    cache_read_tokens=cr_tok,
                                    session_id=f"desktop_{mid}",
                                    estimated_cost=cost,
                                    recorded_at=ts,
                                    client_ip="127.0.0.1",
                                    client_alias=os.environ.get("COMPUTERNAME") or "Local Workstation",
                                    source="desktop_app",
                                    instance_id="local",
                                    external_id=mid,
                                    user_name="James Eckhardt",
                                    team_name="Claude Pro",
                                    account_id="James Eckhardt"
                                )
                                ingested_count += 1
                            else:
                                evt_db_id = existing_row[0]
                                prev_out = existing_row[2] or 0
                                if out_tok > prev_out or tot_toks > (existing_row[3] or 0):
                                    conn = self.db._get_connection()
                                    c = conn.cursor()
                                    c.execute("""
                                        UPDATE usage_events
                                        SET input_tokens = ?,
                                            output_tokens = ?,
                                            cache_creation_tokens = ?,
                                            cache_read_tokens = ?,
                                            total_tokens = ?,
                                            estimated_cost = ?,
                                            external_id = COALESCE(external_id, ?)
                                        WHERE id = ?
                                    """, (in_tok, out_tok, cc_tok, cr_tok, tot_toks, cost, mid, evt_db_id))
                                    conn.commit()
                                    conn.close()
                                    ingested_count += 1
                except Exception:
                    continue
        return ingested_count

    def scan_local_logs(self, search_dir: Optional[str] = None) -> int:
        """
        Scans local ~/.claude directory for CLI and Claude Code session logs (*.jsonl)
        and scans Claude Desktop IndexedDB storage for Cowork and Desktop turns.
        Ingests real token counts, models, and timestamps idempotently, with cache token backfill.
        """
        ingested_count = 0

        # 1. Ingest Claude Desktop IndexedDB turns (when running default unconstrained scan)
        if search_dir is None:
            try:
                desktop_count = self.scan_desktop_indexeddb()
                ingested_count += desktop_count
            except Exception as e:
                self.diagnostics.record_error(
                    ErrorCategory.LOG_PARSER_ERROR,
                    "claude",
                    f"Failed scanning Claude Desktop IndexedDB: {e}"
                )

        # 2. Ingest CLI and Claude Code *.jsonl session logs
        claude_root = Path(search_dir) if search_dir else (Path.home() / ".claude")
        if claude_root.exists():
            jsonl_files = list(claude_root.glob("projects/**/*.jsonl")) + list(claude_root.glob("sessions/**/*.jsonl"))

        for file_path in jsonl_files:
            try:
                # Group streaming chunks within the same JSONL file by Anthropic message.id when present
                # so multi-block assistant turns (thinking + text + tool_use) are not double/triple-counted.
                deduped_entries: Dict[str, Dict[str, Any]] = {}
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_idx, line in enumerate(f):
                        line_str = line.strip()
                        if not line_str or '"assistant"' not in line_str:
                            continue

                        try:
                            item = json.loads(line_str)
                        except Exception:
                            continue

                        if item.get("type") != "assistant":
                            continue

                        msg = item.get("message", {})
                        usage = msg.get("usage", {})
                        if not usage:
                            continue

                        in_tok = int(usage.get("input_tokens", 0))
                        out_tok = int(usage.get("output_tokens", 0))
                        cache_create = int(usage.get("cache_creation_input_tokens", 0))
                        cache_read = int(usage.get("cache_read_input_tokens", 0))

                        model_name = msg.get("model", "claude-sonnet-5-5")
                        ts = item.get("timestamp") or datetime.datetime.now(datetime.timezone.utc).isoformat()
                        session_id = item.get("sessionId") or file_path.stem
                        msg_id = msg.get("id")
                        unique_sess_key = f"{session_id}_{msg_id}" if msg_id else f"{session_id}_{line_idx}"

                        if unique_sess_key in deduped_entries:
                            prev = deduped_entries[unique_sess_key]
                            prev["in_tok"] = max(prev["in_tok"], in_tok)
                            prev["out_tok"] = max(prev["out_tok"], out_tok)
                            prev["cache_create"] = max(prev["cache_create"], cache_create)
                            prev["cache_read"] = max(prev["cache_read"], cache_read)
                            prev["ts"] = ts
                            prev["model_name"] = model_name or prev["model_name"]
                        else:
                            deduped_entries[unique_sess_key] = {
                                "unique_sess_key": unique_sess_key,
                                "msg_id": msg_id,
                                "model_name": model_name,
                                "in_tok": in_tok,
                                "out_tok": out_tok,
                                "cache_create": cache_create,
                                "cache_read": cache_read,
                                "ts": ts,
                            }

                for unique_sess_key, entry in deduped_entries.items():
                    in_tok = entry["in_tok"]
                    out_tok = entry["out_tok"]
                    cache_create = entry["cache_create"]
                    cache_read = entry["cache_read"]
                    model_name = entry["model_name"]
                    ts = entry["ts"]
                    msg_id = entry["msg_id"]

                    # Calculate accurate estimated cost with prompt caching discounts
                    cost = (
                        (in_tok * 0.000003) +
                        (out_tok * 0.000015) +
                        (cache_create * 0.00000375) +
                        (cache_read * 0.0000003)
                    )

                    # Idempotency and backfill check in SQLite
                    conn = self.db._get_connection()
                    c = conn.cursor()
                    if msg_id:
                        c.execute(
                            "SELECT id, input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, total_tokens FROM usage_events WHERE session_id = ? OR (provider = 'claude' AND external_id = ?)",
                            (unique_sess_key, msg_id)
                        )
                    else:
                        c.execute(
                            "SELECT id, input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, total_tokens FROM usage_events WHERE session_id = ? AND recorded_at = ?",
                            (unique_sess_key, ts)
                        )
                    existing_row = c.fetchone()
                    conn.close()

                    tot_toks = in_tok + out_tok + cache_create + cache_read
                    if not existing_row:
                        self.db.record_usage_event(
                            provider="claude",
                            model=model_name,
                            input_tokens=in_tok,
                            output_tokens=out_tok,
                            cache_creation_tokens=cache_create,
                            cache_read_tokens=cache_read,
                            session_id=unique_sess_key,
                            estimated_cost=cost,
                            recorded_at=ts,
                            client_ip="127.0.0.1",
                            client_alias=os.environ.get("COMPUTERNAME") or "Local Workstation",
                            source="cli_scanner",
                            instance_id="local",
                            external_id=msg_id
                        )
                        ingested_count += 1
                    else:
                        # Backfill if cache tokens weren't recorded previously or if streaming turn completed with more output tokens
                        evt_db_id = existing_row[0]
                        prev_out = existing_row[2] or 0
                        prev_cc = existing_row[3] or 0
                        prev_cr = existing_row[4] or 0
                        if ((cache_create > 0 or cache_read > 0) and (prev_cc == 0 and prev_cr == 0)) or (out_tok > prev_out):
                            conn = self.db._get_connection()
                            c = conn.cursor()
                            c.execute("""
                                UPDATE usage_events
                                SET input_tokens = ?,
                                    output_tokens = ?,
                                    cache_creation_tokens = ?,
                                    cache_read_tokens = ?,
                                    total_tokens = ?,
                                    estimated_cost = ?,
                                    external_id = COALESCE(external_id, ?)
                                WHERE id = ?
                            """, (in_tok, out_tok, cache_create, cache_read, tot_toks, cost, msg_id, evt_db_id))
                            conn.commit()
                            conn.close()
                            ingested_count += 1

            except Exception as e:
                self.diagnostics.record_error(
                    ErrorCategory.SCHEMA_MISMATCH,
                    "claude",
                    f"Failed scanning log file {file_path.name}: {e}"
                )

        if ingested_count > 0:
            existing_snaps = self.db.get_provider_snapshots()
            claude_snap = existing_snaps.get("claude", {})
            preserved_plan = claude_snap.get("plan_type") or self._cached_plan or "Claude Pro"
            self.db.update_provider_snapshot(
                provider="claude",
                plan_type=preserved_plan,
                tokens_remaining=claude_snap.get("tokens_remaining") or 350000,
                requests_remaining=claude_snap.get("requests_remaining") or 850,
                reset_epoch=claude_snap.get("reset_epoch") or (time.time() + 3600),
                status="ACTIVE (Local CLI)",
                session_remaining_pct=claude_snap.get("session_remaining_pct"),
                weekly_remaining_pct=claude_snap.get("weekly_remaining_pct"),
                weekly_reset_str=claude_snap.get("weekly_reset_str"),
                user_name=claude_snap.get("user_name"),
                team_name=claude_snap.get("team_name"),
                dept_name=claude_snap.get("dept_name"),
                org_name=claude_snap.get("org_name"),
                individual_session_rem_pct=claude_snap.get("individual_session_rem_pct"),
                individual_weekly_rem_pct=claude_snap.get("individual_weekly_rem_pct"),
                team_session_rem_pct=claude_snap.get("team_session_rem_pct"),
                team_weekly_rem_pct=claude_snap.get("team_weekly_rem_pct"),
                active_scope=claude_snap.get("active_scope")
            )
            self.diagnostics.mark_provider_healthy("claude")

        return ingested_count

    def sync_usage(self) -> Dict[str, Any]:
        """Polls or ingests Claude usage."""
        if self._simulation_mode:
            # Generate realistic demo telemetry
            in_tok = random.randint(450, 2800)
            out_tok = random.randint(150, 950)
            cost = (in_tok * 0.000003) + (out_tok * 0.000015)
            models = ["claude-3-7-sonnet", "claude-3-5-sonnet", "claude-3-5-haiku"]
            model = random.choice(models)
            session_id = f"sess_agentic_{random.randint(101, 109)}"

            evt_id = self.db.record_usage_event(
                provider="claude",
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                session_id=session_id,
                estimated_cost=cost
            )

            # Realistic rate limit calculation
            cur_tokens_rem = max(10000, self._tokens_limit - (in_tok * 15))
            reset_time = time.time() + random.randint(900, 3600)

            existing_snaps = self.db.get_provider_snapshots()
            claude_snap = existing_snaps.get("claude", {})
            sess_rem = claude_snap.get("session_remaining_pct", 44.0)
            week_rem = claude_snap.get("weekly_remaining_pct", 74.0)
            week_reset = claude_snap.get("weekly_reset_str", "Mon 3:00 AM")
            target_reset = claude_snap.get("reset_epoch") or reset_time

            self.db.update_provider_snapshot(
                provider="claude",
                plan_type="Team Enterprise",
                tokens_remaining=cur_tokens_rem,
                requests_remaining=random.randint(450, 980),
                reset_epoch=target_reset,
                status="ACTIVE",
                session_remaining_pct=sess_rem,
                weekly_remaining_pct=week_rem,
                weekly_reset_str=week_reset
            )
            self.diagnostics.mark_provider_healthy("claude")
            return {
                "success": True,
                "mode": "simulation",
                "tokens_generated": in_tok + out_tok,
                "event_id": evt_id
            }

        # 1. Fetch live authoritative OAuth telemetry & quotas from Anthropic API
        oauth_res = self.fetch_live_oauth_telemetry()

        # 2. Ingest local CLI and Claude Desktop IndexedDB turns
        local_ingested = self.scan_local_logs()

        # 3. If direct API key exists in vault and is structurally valid, probe messages endpoint to refresh headers
        api_key = self.vault.get_credential("claude", "default")
        if not api_key or not self.is_valid_anthropic_api_key(api_key):
            return {
                "success": True,
                "mode": "live_sync",
                "oauth": oauth_res,
                "tokens_generated": local_ingested
            }

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        # Lightweight probe query to refresh rate-limit headers
        payload = json.dumps({
            "model": "claude-3-5-haiku-20241022",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}]
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                headers_dict = dict(resp.headers)
                rate_limits = self.parse_rate_limit_headers(headers_dict)
                self.db.update_provider_snapshot(
                    provider="claude",
                    plan_type=self._cached_plan,
                    tokens_remaining=rate_limits["tokens_remaining"],
                    requests_remaining=rate_limits["requests_remaining"],
                    reset_epoch=rate_limits["reset_epoch"],
                    status="ACTIVE"
                )
                self.diagnostics.mark_provider_healthy("claude")
                return {"success": True, "mode": "api", "rate_limits": rate_limits}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.diagnostics.record_error(
                    ErrorCategory.AUTH_FAILURE,
                    "claude",
                    f"Authentication failed: {e.reason}",
                    {"status_code": 401}
                )
            elif e.code == 429:
                self.diagnostics.record_error(
                    ErrorCategory.RATE_LIMIT_EXCEEDED,
                    "claude",
                    "Rate limit exceeded (HTTP 429)",
                    {"headers": dict(e.headers) if hasattr(e, "headers") else {}}
                )
                rate_limits = {}
                if hasattr(e, "headers") and e.headers:
                    try:
                        rate_limits = self.parse_rate_limit_headers(dict(e.headers))
                    except Exception:
                        pass
                self.db.update_provider_snapshot(
                    provider="claude",
                    plan_type=self._cached_plan,
                    tokens_remaining=rate_limits.get("tokens_remaining", 0),
                    requests_remaining=rate_limits.get("requests_remaining", 0),
                    reset_epoch=rate_limits.get("reset_epoch"),
                    status="RATE_LIMITED"
                )
                return {"success": False, "status": "RATE_LIMITED", "error": str(e), "rate_limits": rate_limits}
            elif e.code == 400:
                self.diagnostics.record_error(
                    ErrorCategory.RATE_LIMIT_EXCEEDED,
                    "claude",
                    f"Anthropic API request error (tokens exhausted or credit low): {e.reason}",
                    {"status_code": 400}
                )
                self.db.update_provider_snapshot(
                    provider="claude",
                    plan_type=self._cached_plan,
                    tokens_remaining=0,
                    requests_remaining=0,
                    status="QUOTA_EXHAUSTED"
                )
                return {"success": False, "status": "QUOTA_EXHAUSTED", "error": str(e)}
            else:
                self.diagnostics.record_error(
                    ErrorCategory.SYSTEM_ERROR,
                    "claude",
                    f"Anthropic API HTTP Error {e.code}: {e.reason}",
                    {"status_code": e.code}
                )
            if oauth_res.get("success"):
                return {"success": True, "mode": "oauth_live", "api_error": str(e), "oauth": oauth_res}
            return {"success": False, "error": str(e)}
        except Exception as e:
            self.diagnostics.record_error(
                ErrorCategory.NETWORK_TIMEOUT,
                "claude",
                f"Failed to reach Anthropic endpoint: {e}",
                {"exception": str(e)}
            )
            if oauth_res.get("success"):
                return {"success": True, "mode": "oauth_live", "api_error": str(e), "oauth": oauth_res}
            return {"success": False, "error": str(e)}
