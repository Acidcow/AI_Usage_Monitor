import unittest
import json
import urllib.request
import urllib.error
from pathlib import Path
import tempfile
import shutil

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.claude import ClaudeProvider
from backend.providers.gemini import GeminiProvider
from backend.providers.chatgpt import ChatGPTProvider
from backend.providers.ollama import OllamaProvider
from backend.providers.copilot import CopilotProvider
from backend.server.http_server import AppHTTPServer

class TestProviderProcurementAndConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = str(Path(self.temp_dir) / "test_usage.db")
        self.vault_path = str(Path(self.temp_dir) / "test_vault.enc")
        
        self.db = UsageDatabase(self.db_path)
        self.vault = DPAPIVault(self.vault_path)
        self.diagnostics = DiagnosticsEngine(self.temp_dir)
        
        self.providers = {
            "claude": ClaudeProvider(self.db, self.vault, self.diagnostics),
            "gemini": GeminiProvider(self.db, self.vault, self.diagnostics),
            "chatgpt": ChatGPTProvider(self.db, self.vault, self.diagnostics),
            "ollama": OllamaProvider(self.db, self.vault, self.diagnostics),
            "copilot": CopilotProvider(self.db, self.vault, self.diagnostics)
        }
        
        self.server = AppHTTPServer(
            self.db,
            self.vault,
            self.diagnostics,
            self.providers,
            host="127.0.0.1",
            port=0
        )
        self.server.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_gemini_config_endpoint_saves_dpapi_credential(self):
        """Assert POST /api/providers/gemini/config encrypts API key and saves to vault."""
        req_data = json.dumps({"api_key": "AIzaSyTestGeminiKey123456789"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/providers/gemini/config",
            data=req_data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))

        # Verify key was encrypted and stored in DPAPI vault
        stored_key = self.vault.get_credential("gemini", "default")
        self.assertEqual(stored_key, "AIzaSyTestGeminiKey123456789")

    def test_chatgpt_config_endpoint_saves_dpapi_credential(self):
        """Assert POST /api/providers/chatgpt/config encrypts API key and saves to vault."""
        req_data = json.dumps({"api_key": "sk-proj-TestOpenAIKey987654321"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/providers/chatgpt/config",
            data=req_data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))

        stored_key = self.vault.get_credential("chatgpt", "default")
        self.assertEqual(stored_key, "sk-proj-TestOpenAIKey987654321")

    def test_provider_procurement_urls_are_valid_and_present(self):
        """Assert all 5 AI providers have valid HTTPS procurement URLs."""
        procurement_registry = {
            "gemini": {
                "portal": "https://aistudio.google.com/app/apikey",
                "docs": "https://ai.google.dev/gemini-api/docs",
                "pricing": "https://ai.google.dev/pricing"
            },
            "claude": {
                "portal": "https://console.anthropic.com/settings/keys",
                "usage": "https://console.anthropic.com/settings/cost",
                "docs": "https://docs.anthropic.com/en/docs/initial-setup"
            },
            "chatgpt": {
                "portal": "https://platform.openai.com/api-keys",
                "usage": "https://platform.openai.com/usage",
                "docs": "https://platform.openai.com/docs/quickstart"
            },
            "copilot": {
                "admin": "https://admin.microsoft.com/#/reportsUsage/CopilotActivity",
                "studio": "https://copilotstudio.microsoft.com",
                "docs": "https://learn.microsoft.com/en-us/copilot/microsoft-365/microsoft-365-copilot-usage-reports"
            },
            "ollama": {
                "download": "https://ollama.com/download",
                "library": "https://ollama.com/library"
            }
        }
        
        for provider, links in procurement_registry.items():
            for key, url in links.items():
                self.assertTrue(url.startswith("https://"), f"{provider} {key} url must start with https://")
                self.assertIn(".", url)

if __name__ == "__main__":
    unittest.main()
