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
from backend.providers.claude import ClaudeProvider
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.proxy.transparent_proxy import TransparentProxyServer

class TestTransparentProxy(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_proxy_usage.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()
        self.diagnostics.clear_errors()
        self.claude = ClaudeProvider(database=self.db, vault=self.vault, diagnostics=self.diagnostics)
        self.proxy = TransparentProxyServer(
            claude_provider=self.claude,
            host="127.0.0.1",
            port=0 # dynamic ephemeral port for testing
        )
        self.proxy.start()

    def tearDown(self):
        self.proxy.stop()
        self.temp_dir.cleanup()

    def test_proxy_health_endpoint(self):
        port = self.proxy.server_port
        url = f"http://127.0.0.1:{port}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "UP")
            self.assertEqual(data["proxy_target"], "claude")

    def test_proxy_intercepts_mock_interaction(self):
        port = self.proxy.server_port
        url = f"http://127.0.0.1:{port}/v1/messages"
        payload = json.dumps({
            "model": "claude-3-7-sonnet",
            "messages": [{"role": "user", "content": "Hello via proxy"}],
            "max_tokens": 100
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "x-mock-response": "true", # Test flag to simulate upstream Anthropic response without external network
            "x-mock-input-tokens": "120",
            "x-mock-output-tokens": "45"
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("usage", data)

        # Verify DB intercepted the token metrics!
        summary = self.db.get_usage_summary(provider="claude")
        self.assertEqual(summary["total_tokens_today"], 165)
        self.assertEqual(summary["input_tokens_today"], 120)
        self.assertEqual(summary["output_tokens_today"], 45)

if __name__ == "__main__":
    unittest.main()
