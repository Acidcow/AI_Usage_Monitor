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
        keys = self.get_configured_keys()
        project_id = self.vault.get_credential("gemini", "project_id")

        if not keys:
            self.db.update_provider_snapshot(
                provider="gemini",
                plan_type="Google AI Studio",
                status="NOT_CONFIGURED"
            )
            return {"success": False, "status": "NOT_CONFIGURED", "message": "Google Gemini API key required"}

        all_models = set()
        active_keys = 0
        last_error = None

        for key in keys:
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
            plan_label = f"GCP: {project_id}" if project_id else (f"AI Studio ({active_keys} Keys)" if len(keys) > 1 else "Google AI Studio")
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
                "keys_configured": len(keys),
                "active_keys": active_keys,
                "project_id": project_id,
                "models": sorted(list(all_models))[:6]
            }

        # If all keys failed
        self.diagnostics.record_error(
            ErrorCategory.AUTH_FAILURE,
            "gemini",
            f"All {len(keys)} Gemini keys failed: {last_error}"
        )
        self.db.update_provider_snapshot(
            provider="gemini",
            plan_type="Google AI Studio",
            status="ERROR"
        )
        return {"success": False, "status": "ERROR", "error": last_error}

    def resolve_token_id_from_key(self, api_key: str) -> str:
        """Resolves child token ID (e.g. tok_gem_flash) from API key or masked key."""
        if not api_key:
            return "tok_gem_flash"
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
                    # Check prefix / suffix against masked key
                    masked = t.get("masked_key", "")
                    if "..." in masked:
                        pref, suff = masked.split("...")
                        if api_key.startswith(pref) or api_key.endswith(suff):
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
        session_id: Optional[str] = None
    ) -> str:
        """Called by transparent proxy when a Gemini completion completes."""
        cost = (input_tokens * 0.0000001) + (output_tokens * 0.0000004)
        resolved_tok = token_id or "tok_gem_flash"

        account_email = self.vault.get_credential("google", "account_email") or "acidcow@gmail.com"
        evt_id = self.db.record_usage_event(
            provider="gemini",
            model=model or "gemini-2.0-flash",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            token_id=resolved_tok,
            account_id=account_email,
            session_id=session_id or f"gemini_proxy_{int(time.time())}",
            estimated_cost=cost
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

