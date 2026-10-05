import unittest
import sys
import tempfile
import os
import json
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.claude import ClaudeProvider
from backend.providers.gemini import GeminiProvider
from backend.providers.ollama import OllamaProvider
from backend.providers.copilot import CopilotProvider
from backend.providers.chatgpt import ChatGPTProvider
from backend.server.http_server import AppHTTPServer

class TestHTTPAPI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_api_usage.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()
        self.diagnostics.clear_errors()

        self.claude = ClaudeProvider(self.db, self.vault, self.diagnostics)
        self.gemini = GeminiProvider(self.db, self.vault, self.diagnostics)
        self.ollama = OllamaProvider(self.db, self.vault, self.diagnostics)
        self.copilot = CopilotProvider(self.db, self.vault, self.diagnostics)
        self.chatgpt = ChatGPTProvider(self.db, self.vault, self.diagnostics)

        providers = {
            "claude": self.claude,
            "gemini": self.gemini,
            "ollama": self.ollama,
            "copilot": self.copilot,
            "chatgpt": self.chatgpt
        }

        self.server = AppHTTPServer(
            database=self.db,
            vault=self.vault,
            diagnostics=self.diagnostics,
            providers=providers,
            host="127.0.0.1",
            port=0 # dynamic ephemeral port
        )
        self.server.start()

    def tearDown(self):
        self.server.stop()
        self.temp_dir.cleanup()

    def _get(self, path):
        port = self.server.server_port
        url = f"http://127.0.0.1:{port}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _post(self, path, payload):
        port = self.server.server_port
        url = f"http://127.0.0.1:{port}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_api_status(self):
        status, data = self._get("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["service"], "AI_Usage_Monitor")
        self.assertIn("providers", data)

    def test_api_usage_summary(self):
        # Insert test data
        self.db.record_usage_event(
            provider="claude",
            input_tokens=1000,
            output_tokens=300,
            model="claude-3-7-sonnet"
        )
        status, data = self._get("/api/usage/summary")
        self.assertEqual(status, 200)
        self.assertEqual(data["total_tokens_today"], 1300)

    def test_api_providers_list(self):
        status, data = self._get("/api/providers")
        self.assertEqual(status, 200)
        self.assertIn("claude", data)
        self.assertIn("copilot", data)
        self.assertIn("gemini", data)
        self.assertIn("ollama", data)
        self.assertIn("chatgpt", data)

    def test_api_diagnostics_export(self):
        status, data = self._get("/api/diagnostics/export")
        self.assertEqual(status, 200)
        self.assertIn("system_info", data)
        self.assertIn("provider_health", data)

    def test_api_sync_trigger(self):
        self.claude.enable_simulation_mode(True)
        status, data = self._post("/api/providers/sync", {"provider": "claude"})
        self.assertEqual(status, 200)
        self.assertTrue(data["success"])

if __name__ == "__main__":
    unittest.main()
