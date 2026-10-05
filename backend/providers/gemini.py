from typing import Dict, Any
from backend.providers.base import BaseProvider

class GeminiProvider(BaseProvider):
    """
    Google Gemini (AI Studio / Vertex) Usage Provider.
    Ready for API key configuration or proxy capture.
    """

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return "Google Gemini"

    def sync_usage(self) -> Dict[str, Any]:
        if not self.is_configured:
            return {"success": False, "status": "NOT_CONFIGURED", "message": "Google Gemini API key required"}
        # Ready for Google AI Studio API polling
        return {"success": True, "status": "ACTIVE"}
