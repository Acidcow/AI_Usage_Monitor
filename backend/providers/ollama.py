import urllib.request
import json
import time
from typing import Dict, Any, List, Optional
from backend.providers.base import BaseProvider

class OllamaProvider(BaseProvider):
    """
    Ollama Local LLM Usage Provider.
    Monitors local Ollama runtime on http://localhost:11434, detects installed models,
    tracks running VRAM inference, and ingests local token usage.
    """

    def __init__(self, database, vault, diagnostics, base_url: str = "http://localhost:11434"):
        super().__init__(database, vault, diagnostics)
        self.base_url = base_url.rstrip("/")
        self._cached_models: List[Dict[str, Any]] = []
        self._last_models_fetch = 0

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama (Local)"

    def get_installed_models(self) -> List[Dict[str, Any]]:
        """Queries local Ollama for all installed models and parameters."""
        now = time.time()
        if self._cached_models and (now - self._last_models_fetch) < 15:
            return self._cached_models

        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models_raw = data.get("models", [])
                formatted = []
                for m in models_raw:
                    details = m.get("details", {})
                    size_bytes = m.get("size", 0)
                    size_gb = round(size_bytes / (1024**3), 2)
                    formatted.append({
                        "name": m.get("name"),
                        "size": f"{size_gb} GB",
                        "parameter_size": details.get("parameter_size", "Unknown"),
                        "quantization": details.get("quantization_level", "Unknown"),
                        "family": details.get("family", "Unknown"),
                        "modified_at": m.get("modified_at")
                    })
                self._cached_models = formatted
                self._last_models_fetch = now
                return formatted
        except Exception:
            return self._cached_models or []

    def get_running_models(self) -> List[Dict[str, Any]]:
        """Queries running models loaded in memory/VRAM."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/ps")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("models", [])
        except Exception:
            return []

    def ingest_inference_tokens(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        session_id: Optional[str] = None
    ) -> str:
        """Records a completed local inference run."""
        evt_id = self.db.record_usage_event(
            provider="ollama",
            model=model or "local_model",
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            session_id=session_id or f"ollama_{int(time.time())}",
            estimated_cost=0.0 # Local hardware inference is $0 API cost!
        )
        return evt_id

    def sync_usage(self) -> Dict[str, Any]:
        """Polls local Ollama health, models, and memory status."""
        try:
            models = self.get_installed_models()
            running = self.get_running_models()

            status_str = "ACTIVE" if models else "STANDBY"
            self.db.update_provider_snapshot(
                provider="ollama",
                plan_type="Local Hardware",
                tokens_remaining=999999999,
                requests_remaining=999999,
                reset_epoch=None,
                status="ACTIVE"
            )
            self.diagnostics.mark_provider_healthy("ollama")
            return {
                "success": True,
                "status": "ACTIVE",
                "installed_count": len(models),
                "running_count": len(running),
                "models": models[:5]
            }
        except Exception as e:
            self.db.update_provider_snapshot(
                provider="ollama",
                plan_type="Local Hardware",
                status="OFFLINE"
            )
            return {"success": False, "status": "OFFLINE", "error": str(e)}

    def get_snapshot(self) -> Dict[str, Any]:
        snap = super().get_snapshot()
        # Return cached models if available without blocking HTTP calls
        if self._cached_models:
            snap["installed_models"] = self._cached_models
        return snap
