import urllib.request
import json
from typing import Dict, Any
from backend.providers.base import BaseProvider

class OllamaProvider(BaseProvider):
    """
    Ollama Local LLM Usage Provider.
    Monitors local Ollama runtime on http://localhost:11434.
    """

    def __init__(self, database, vault, diagnostics, base_url: str = "http://localhost:11434"):
        super().__init__(database, vault, diagnostics)
        self.base_url = base_url

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama (Local)"

    def sync_usage(self) -> Dict[str, Any]:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", [])]
                self.db.update_provider_snapshot(
                    provider="ollama",
                    plan_type="Local Hardware",
                    tokens_remaining=999999999,
                    requests_remaining=999999,
                    status="ACTIVE"
                )
                self.diagnostics.mark_provider_healthy("ollama")
                return {"success": True, "status": "ACTIVE", "models": models}
        except Exception:
            self.db.update_provider_snapshot(
                provider="ollama",
                plan_type="Local Hardware",
                status="OFFLINE"
            )
            return {"success": False, "status": "OFFLINE"}
