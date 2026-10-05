from typing import Dict, Any
from backend.providers.base import BaseProvider

class ChatGPTProvider(BaseProvider):
    """
    ChatGPT / OpenAI Usage Adapter.
    Staged for future release.
    """

    @property
    def provider_name(self) -> str:
        return "chatgpt"

    @property
    def display_name(self) -> str:
        return "ChatGPT / OpenAI (Coming Soon)"

    def sync_usage(self) -> Dict[str, Any]:
        return {
            "success": False,
            "status": "COMING_SOON",
            "message": "OpenAI / ChatGPT integration scheduled for Phase 2."
        }
