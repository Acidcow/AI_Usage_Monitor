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
from backend.proxy.transparent_proxy import TransparentProxyServer

class TestProxyStreaming(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_stream_usage.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()
        self.diagnostics.clear_errors()
        self.claude = ClaudeProvider(self.db, self.vault, self.diagnostics)
        self.proxy = TransparentProxyServer(self.claude, host="127.0.0.1", port=0)
        self.proxy.start()

    def tearDown(self):
        self.proxy.stop()
        self.temp_dir.cleanup()

    def test_mock_sse_streaming_extraction(self):
        port = self.proxy.server_port
        url = f"http://127.0.0.1:{port}/v1/messages"
        payload = json.dumps({
            "model": "claude-3-7-sonnet",
            "messages": [{"role": "user", "content": "stream test"}],
            "stream": True
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "x-mock-stream": "true",
            "x-mock-input-tokens": "140",
            "x-mock-output-tokens": "60"
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        chunks = []
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))
            while True:
                line = resp.readline()
                if not line:
                    break
                chunks.append(line.decode("utf-8"))

        # Verify stream content was received
        full_text = "".join(chunks)
        self.assertIn("message_start", full_text)
        self.assertIn("message_delta", full_text)

        # Verify tokens were intercepted and saved to DB
        summary = self.db.get_usage_summary(provider="claude")
        self.assertEqual(summary["input_tokens_today"], 140)
        self.assertEqual(summary["output_tokens_today"], 60)
        self.assertEqual(summary["total_tokens_today"], 200)

if __name__ == "__main__":
    unittest.main()
