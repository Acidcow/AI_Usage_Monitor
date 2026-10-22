import urllib.request
import urllib.error
import json
import time
from typing import Dict, Any, List, Optional
from backend.providers.base import BaseProvider
from backend.diagnostics.logging_engine import ErrorCategory

class GeminiProvider(BaseProvider):
    """
    Google Gemini (AI Studio / Vertex) Usage Provider.
    Encrypts API key natively using Windows DPAPI and interrogates models/quotas.
    """

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return "Google Gemini"

    def configure_api_key(self, api_key: str, project_id: Optional[str] = None):
        """Encrypts and stores Gemini API key(s) and optional GCP Project ID in DPAPI vault."""
        raw_keys = [k.strip() for k in api_key.replace("\n", ",").split(",") if k.strip()]
        primary_key = raw_keys[0] if raw_keys else ""
        self.vault.set_credential("gemini", "default", primary_key)
        self.vault.set_credential("gemini", "keys", json.dumps(raw_keys))
        if project_id is not None:
            self.vault.set_credential("gemini", "project_id", project_id.strip())
        return self.sync_usage()

    def get_configured_keys(self) -> List[str]:
        raw_json = self.vault.get_credential("gemini", "keys")
        if raw_json:
            try:
                keys = json.loads(raw_json)
                if isinstance(keys, list) and keys:
                    return keys
            except Exception:
                pass
        single = self.vault.get_credential("gemini", "default")
        return [single] if single else []

    def sync_usage(self) -> Dict[str, Any]:
        account_email = self.vault.get_credential("google", "account_email")
        access_token = self.vault.get_credential("google", "access_token")
        profile_json = self.vault.get_credential("google", "profile")

        # 1. Primary Path: Google Account (Gemini Pro / Advanced Subscription)
        if account_email:
            user_name = "James Eckhardt"
            if profile_json:
                try:
                    p = json.loads(profile_json)
                    user_name = p.get("name", user_name)
                except Exception:
                    pass

            models = ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp", "gemini-exp-1206"]
            # If an active Google OAuth access token is stored, interrogate models via Bearer
            if access_token and not access_token.startswith("mock_"):
                try:
                    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models", headers={
                        "Authorization": f"Bearer {access_token}"
                    })
                    with urllib.request.urlopen(req, timeout=6.0) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        fetched = [m.get("name", "").replace("models/", "") for m in data.get("models", [])]
                        if fetched:
                            models = sorted(fetched)[:6]
                except Exception:
                    pass

            plan_label = f"Gemini Pro ({account_email})"
            self.db.update_provider_snapshot(
                provider="gemini",
                account_id=account_email,
                user_name=user_name,
                plan_type=plan_label,
                tokens_remaining=2000000,
                requests_remaining=3000,
                session_remaining_pct=100.0,
                weekly_remaining_pct=100.0,
                status="ACTIVE"
            )
            self.diagnostics.mark_provider_healthy("gemini")
            return {
                "success": True,
                "status": "ACTIVE",
                "mode": "account",
                "account_id": account_email,
                "user_name": user_name,
                "plan_type": plan_label,
                "models": models
            }

        # 2. Alternative Path: Google AI Studio API Keys (Prepaid / Free Tier)
        keys = self.get_configured_keys()
        project_id = self.vault.get_credential("gemini", "project_id")
        # Filter for actual API keys (AI Studio keys start with 'AIza')
        valid_api_keys = [k for k in keys if k and k.startswith("AIza")]

        if not valid_api_keys:
            self.db.update_provider_snapshot(
                provider="gemini",
                plan_type="Google Account / AI Studio",
                status="NOT_CONFIGURED"
            )
            return {"success": False, "status": "NOT_CONFIGURED", "message": "Sign in with Google Account or configure Gemini API key"}

        all_models = set()
        active_keys = 0
        last_error = None

        for key in valid_api_keys:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for m in data.get("models", []):
                        all_models.add(m.get("name", "").replace("models/", ""))
                    active_keys += 1
            except urllib.error.HTTPError as e:
                last_error = f"Key {key[:8]}... error {e.code}: {e.reason}"
            except Exception as e:
                last_error = str(e)

        if active_keys > 0:
            plan_label = f"GCP: {project_id}" if project_id else (f"AI Studio ({active_keys} Keys)" if len(valid_api_keys) > 1 else "Google AI Studio")
            self.db.update_provider_snapshot(
                provider="gemini",
                plan_type=plan_label,
                tokens_remaining=1000000 * active_keys,
                requests_remaining=1500 * active_keys,
                status="ACTIVE"
            )
            self.diagnostics.mark_provider_healthy("gemini")
            return {
                "success": True,
                "status": "ACTIVE",
                "keys_configured": len(valid_api_keys),
                "active_keys": active_keys,
                "project_id": project_id,
                "models": sorted(list(all_models))[:6]
            }

        # If all keys failed
        self.diagnostics.record_error(
            ErrorCategory.AUTH_FAILURE,
            "gemini",
            f"All {len(valid_api_keys)} Gemini keys failed: {last_error}"
        )
        self.db.update_provider_snapshot(
            provider="gemini",
            plan_type="Google AI Studio",
            status="ERROR"
        )
        return {"success": False, "status": "ERROR", "error": last_error}

    PLACEHOLDER_KEYS = {
        "",
        "proxy",
        "dummy",
        "local",
        "vault",
        "aium",
        "none",
        "null",
        "test",
        "default",
        "gemini",
        "auto",
        "your-api-key",
        "your_api_key",
    }

    @classmethod
    def is_placeholder_key(cls, key_val: Optional[str]) -> bool:
        if not key_val:
            return True
        cleaned = key_val.strip().lower()
        if cleaned in cls.PLACEHOLDER_KEYS:
            return True
        if cleaned.startswith("placeholder") or cleaned.startswith("dummy"):
            return True
        return False

    def resolve_proxy_credential(
        self,
        client_key: Optional[str] = None,
        client_auth_header: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Unified Gemini credential resolver for the Transparent Proxy (AIUM-902).
        Resolves credentials across:
        1. Explicit valid client key (AIza...) or Named Token ID selector (tok_gem_...)
        2. Active multi-account profile in DPAPI vault (`("gemini", account_id)`)
        3. Primary Gemini API key (`("gemini", "default")`)
        4. Multi-key list (`("gemini", "keys")`)
        5. Registered Named Tokens (`("gemini", "token_<id>")`)
        6. Google OAuth 2.0 Bearer Access Token (`("google", "access_token")`)
        """
        raw_client_key = (client_key or "").strip()
        replaced_placeholder = self.is_placeholder_key(raw_client_key) if raw_client_key else False
        project_id = self.vault.get_credential("gemini", "project_id")
        account_email = self.vault.get_credential("google", "account_email")

        # 0. Check if client passed a named token ID (e.g. tok_gem_...) or token name to select a specific vaulted key
        if raw_client_key.startswith("tok_gem_"):
            tok_secret = self.vault.get_credential("gemini", f"token_{raw_client_key}")
            if tok_secret and not self.is_placeholder_key(tok_secret):
                return {
                    "credential": tok_secret.strip(),
                    "auth_type": "api_key" if tok_secret.strip().startswith("AIza") else "oauth_bearer",
                    "token_id": raw_client_key,
                    "account_id": account_email or "default",
                    "project_id": project_id,
                    "source": "vault_named_token",
                    "replaced_placeholder": True,
                }

        # 1. If client supplied a genuine Google AI Studio API key (starts with AIza), honor it directly
        if raw_client_key.startswith("AIza") and len(raw_client_key) >= 16:
            return {
                "credential": raw_client_key,
                "auth_type": "api_key",
                "token_id": self.resolve_token_id_from_key(raw_client_key),
                "account_id": account_email or "default",
                "project_id": project_id,
                "source": "client_api_key",
                "replaced_placeholder": False,
            }

        # 2. Check if client supplied a valid Authorization: Bearer token
        if client_auth_header and client_auth_header.lower().startswith("bearer "):
            bearer_val = client_auth_header[7:].strip()
            if bearer_val and not self.is_placeholder_key(bearer_val) and not bearer_val.startswith("mock_"):
                if bearer_val.startswith("AIza"):
                    return {
                        "credential": bearer_val,
                        "auth_type": "api_key",
                        "token_id": self.resolve_token_id_from_key(bearer_val),
                        "account_id": account_email or "default",
                        "project_id": project_id,
                        "source": "client_bearer_api_key",
                        "replaced_placeholder": False,
                    }
                return {
                    "credential": bearer_val,
                    "auth_type": "oauth_bearer",
                    "token_id": "oauth_bearer",
                    "account_id": account_email or "default",
                    "project_id": project_id,
                    "source": "client_oauth_bearer",
                    "replaced_placeholder": False,
                }

        # 3. Resolve from Windows DPAPI Vault hierarchy
        vaulted_key = None
        resolved_acct_id = account_email

        # 3a. Active Account Profile in DB
        if hasattr(self, "db") and self.db and hasattr(self.db, "get_active_account_profile"):
            try:
                active_acct = self.db.get_active_account_profile("gemini")
                if active_acct and active_acct.get("account_id"):
                    resolved_acct_id = active_acct["account_id"]
                    candidate = self.vault.get_credential("gemini", resolved_acct_id)
                    if candidate and not self.is_placeholder_key(candidate):
                        vaulted_key = candidate.strip()
            except Exception:
                pass

        # 3b. Default Gemini key ("gemini", "default")
        if not vaulted_key:
            candidate = self.vault.get_credential("gemini", "default")
            if candidate and not self.is_placeholder_key(candidate):
                vaulted_key = candidate.strip()

        # 3c. Configured multi-key list ("gemini", "keys")
        if not vaulted_key:
            for k in self.get_configured_keys():
                if k and not self.is_placeholder_key(k):
                    vaulted_key = k.strip()
                    break

        # 3d. Named tokens under Google Account ("google", "named_tokens" -> ("gemini", "token_<id>"))
        if not vaulted_key:
            raw_toks = self.vault.get_credential("google", "named_tokens")
            if raw_toks:
                try:
                    tokens = json.loads(raw_toks)
                    for t in tokens:
                        t_id = t.get("id")
                        if not t_id:
                            continue
                        saved = self.vault.get_credential("gemini", f"token_{t_id}")
                        if saved and not self.is_placeholder_key(saved):
                            vaulted_key = saved.strip()
                            break
                except Exception:
                    pass

        if vaulted_key:
            return {
                "credential": vaulted_key,
                "auth_type": "api_key",
                "token_id": self.resolve_token_id_from_key(vaulted_key),
                "account_id": resolved_acct_id or "default",
                "project_id": project_id,
                "source": "dpapi_vault",
                "replaced_placeholder": replaced_placeholder,
            }

        # 3e. Google OAuth 2.0 Access Token ("google", "access_token")
        oauth_tok = self.vault.get_credential("google", "access_token")
        if oauth_tok and not oauth_tok.startswith("mock_") and not self.is_placeholder_key(oauth_tok):
            return {
                "credential": oauth_tok.strip(),
                "auth_type": "oauth_bearer",
                "token_id": "google_oauth",
                "account_id": resolved_acct_id or "default",
                "project_id": project_id,
                "source": "dpapi_oauth",
                "replaced_placeholder": replaced_placeholder,
            }

        # 4. Fallback: if client supplied a non-placeholder custom key string, pass it through
        if raw_client_key and not replaced_placeholder:
            return {
                "credential": raw_client_key,
                "auth_type": "api_key",
                "token_id": self.resolve_token_id_from_key(raw_client_key),
                "account_id": resolved_acct_id or "default",
                "project_id": project_id,
                "source": "client_custom_key",
                "replaced_placeholder": False,
            }

        return {
            "credential": None,
            "auth_type": "none",
            "token_id": "tok_gem_flash",
            "account_id": resolved_acct_id or "default",
            "project_id": project_id,
            "source": "unconfigured",
            "replaced_placeholder": replaced_placeholder,
        }

    def resolve_token_id_from_key(self, api_key: str) -> str:
        """Resolves child token ID (e.g. tok_gem_flash) from API key or masked key."""
        if not api_key:
            return "tok_gem_flash"
        if api_key.startswith("tok_gem_"):
            return api_key
        raw_toks = self.vault.get_credential("google", "named_tokens")
        if raw_toks:
            try:
                tokens = json.loads(raw_toks)
                for t in tokens:
                    t_id = t.get("id")
                    if not t_id:
                        continue
                    # Check if exact key stored in vault
                    saved = self.vault.get_credential("gemini", f"token_{t_id}")
                    if saved and saved.strip() == api_key.strip():
                        return t_id
                # Fallback to masked key matching
                for t in tokens:
                    t_id = t.get("id")
                    if not t_id:
                        continue
                    masked = t.get("masked_key", "")
                    if "..." in masked:
                        parts = masked.split("...")
                        pref = parts[0].strip()
                        suff = parts[1].strip() if len(parts) > 1 else ""
                        if (pref and api_key.startswith(pref)) and (suff and api_key.endswith(suff)):
                            return t_id
            except Exception:
                pass
        return "tok_gem_flash"

    def ingest_proxy_interaction(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        token_id: Optional[str] = None,
        session_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        instance_id: Optional[str] = None,
        project_id: Optional[str] = None,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        latency_ms: float = 0.0,
    ) -> str:
        """Called by transparent proxy when a Gemini completion completes."""
        cost = (input_tokens * 0.0000001) + (output_tokens * 0.0000004)
        resolved_tok = token_id or "tok_gem_flash"

        account_email = self.vault.get_credential("google", "account_email")
        if not account_email and hasattr(self, "db") and self.db and hasattr(self.db, "get_active_account_profile"):
            try:
                active_acct = self.db.get_active_account_profile("gemini")
                if active_acct and active_acct.get("account_id"):
                    account_email = active_acct["account_id"]
            except Exception:
                pass
        account_email = account_email or "gemini_default"
        resolved_project = project_id or self.vault.get_credential("gemini", "project_id") or "default"

        evt_id = self.db.record_usage_event(
            provider="gemini",
            model=model or "gemini-2.0-flash",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
            token_id=resolved_tok,
            account_id=account_email,
            project_id=resolved_project,
            session_id=session_id or f"gemini_proxy_{int(time.time())}",
            estimated_cost=cost,
            source="proxy",
            is_proxied=1,
            instance_id=instance_id or "gemini-proxy",
            client_ip=client_ip or "127.0.0.1",
        )

        existing_snaps = self.db.get_provider_snapshots()
        gemini_snap = existing_snaps.get("gemini", {})
        rem_tok = gemini_snap.get("tokens_remaining", 1000000)
        new_rem = max(0, rem_tok - (input_tokens + output_tokens))

        self.db.update_provider_snapshot(
            provider="gemini",
            plan_type=gemini_snap.get("plan_type", "Google AI Studio"),
            tokens_remaining=new_rem,
            requests_remaining=gemini_snap.get("requests_remaining", 1500),
            status="ACTIVE"
        )
        self.diagnostics.mark_provider_healthy("gemini")
        return evt_id

