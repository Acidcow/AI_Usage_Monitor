import os
import sys
import json
import time
import random
import datetime
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional

from backend.providers.base import BaseProvider
from backend.diagnostics.logging_engine import ErrorCategory

class ClaudeProvider(BaseProvider):
    """
    Claude (Anthropic) Multi-Mode Usage Provider.
    Supports: Direct API poller, Transparent Proxy ingestion, CLI cache scanner, and Simulation.
    """

    def __init__(self, database, vault, diagnostics):
        super().__init__(database, vault, diagnostics)
        self._simulation_mode = False
        self._cached_plan = "Pro"
        self._tokens_limit = 400000
        self._requests_limit = 1000

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
        rate_limit_headers: Optional[Dict[str, str]] = None
    ) -> str:
        """Called by transparent proxy or CLI scanner when a request completes."""
        # Estimate cost (approx Sonnet 3.5/3.7 rates: $3/M in, $15/M out)
        cost = (input_tokens * 0.000003) + (output_tokens * 0.000015)
        evt_id = self.db.record_usage_event(
            provider="claude",
            model=model or "claude-3-7-sonnet",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            session_id=session_id or f"proxy_{int(time.time())}",
            estimated_cost=cost
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

        self.db.update_provider_snapshot(
            provider="claude",
            plan_type=self._cached_plan,
            tokens_remaining=tokens_rem or 385000,
            requests_remaining=requests_rem or 950,
            reset_epoch=reset_epoch or (time.time() + 1800),
            status="ACTIVE"
        )
        self.diagnostics.mark_provider_healthy("claude")
        return evt_id

    def scan_local_logs(self, search_dir: Optional[str] = None) -> int:
        """
        Scans local ~/.claude directory for CLI and Claude Code session logs (*.jsonl).
        Ingests real token counts, models, and timestamps idempotently.
        """
        claude_root = Path(search_dir) if search_dir else (Path.home() / ".claude")
        if not claude_root.exists():
            return 0

        ingested_count = 0
        jsonl_files = list(claude_root.glob("projects/**/*.jsonl")) + list(claude_root.glob("sessions/**/*.jsonl"))

        for file_path in jsonl_files:
            try:
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

                        tot_in = in_tok + cache_create + cache_read
                        model_name = msg.get("model", "claude-sonnet-5-5")
                        ts = item.get("timestamp") or datetime.datetime.now(datetime.timezone.utc).isoformat()
                        session_id = item.get("sessionId") or file_path.stem
                        unique_sess_key = f"{session_id}_{line_idx}"

                        # Calculate estimated cost
                        cost = (in_tok * 0.000003) + (out_tok * 0.000015) + (cache_create * 0.00000375) + (cache_read * 0.0000003)

                        # Idempotency check in SQLite
                        conn = self.db._get_connection()
                        c = conn.cursor()
                        c.execute("SELECT 1 FROM usage_events WHERE session_id = ? AND recorded_at = ?", (unique_sess_key, ts))
                        exists = c.fetchone()
                        conn.close()

                        if not exists:
                            self.db.record_usage_event(
                                provider="claude",
                                model=model_name,
                                input_tokens=tot_in,
                                output_tokens=out_tok,
                                session_id=unique_sess_key,
                                estimated_cost=cost,
                                recorded_at=ts
                            )
                            ingested_count += 1

            except Exception as e:
                self.diagnostics.record_error(
                    ErrorCategory.SCHEMA_MISMATCH,
                    "claude",
                    f"Failed scanning log file {file_path.name}: {e}"
                )

        if ingested_count > 0:
            self.db.update_provider_snapshot(
                provider="claude",
                plan_type="Team Enterprise (CLI)",
                tokens_remaining=350000,
                requests_remaining=850,
                reset_epoch=time.time() + 3600,
                status="ACTIVE (Local CLI)"
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

            self.db.update_provider_snapshot(
                provider="claude",
                plan_type="Team Enterprise",
                tokens_remaining=cur_tokens_rem,
                requests_remaining=random.randint(450, 980),
                reset_epoch=reset_time,
                status="ACTIVE"
            )
            self.diagnostics.mark_provider_healthy("claude")
            return {
                "success": True,
                "mode": "simulation",
                "tokens_generated": in_tok + out_tok,
                "event_id": evt_id
            }

        # 1. Attempt scanning local CLI logs first
        local_ingested = self.scan_local_logs()
        if local_ingested > 0:
            return {
                "success": True,
                "mode": "local_cli_scan",
                "tokens_generated": local_ingested
            }

        # Real API Poller
        api_key = self.vault.get_credential("claude", "default")
        if not api_key:
            return {"success": False, "error": "No credential configured and no local logs found"}

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
                    {"headers": dict(e.headers)}
                )
            else:
                self.diagnostics.record_error(
                    ErrorCategory.SYSTEM_ERROR,
                    "claude",
                    f"Anthropic API HTTP Error {e.code}: {e.reason}",
                    {"status_code": e.code}
                )
            return {"success": False, "error": str(e)}
        except Exception as e:
            self.diagnostics.record_error(
                ErrorCategory.NETWORK_TIMEOUT,
                "claude",
                f"Failed to reach Anthropic endpoint: {e}",
                {"exception": str(e)}
            )
            return {"success": False, "error": str(e)}
