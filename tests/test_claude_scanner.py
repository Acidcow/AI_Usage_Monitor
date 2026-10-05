import unittest
import sys
import tempfile
import os
import json
import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.claude import ClaudeProvider

class TestClaudeScanner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_scanner_usage.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()
        self.diagnostics.clear_errors()
        self.claude = ClaudeProvider(self.db, self.vault, self.diagnostics)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scan_local_claude_project_directory(self):
        # Create a mock .claude directory structure
        mock_claude_dir = Path(self.temp_dir.name) / ".claude"
        proj_dir = mock_claude_dir / "projects" / "MockProject"
        proj_dir.mkdir(parents=True, exist_ok=True)

        today_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_file = proj_dir / "session-001.jsonl"
        lines = [
            {"type": "queue-operation", "sessionId": "sess-real-1", "timestamp": today_iso},
            {"type": "user", "sessionId": "sess-real-1", "timestamp": today_iso, "content": "Hello world"},
            {
                "type": "assistant",
                "sessionId": "sess-real-1",
                "timestamp": today_iso,
                "message": {
                    "model": "claude-sonnet-5-5",
                    "usage": {
                        "input_tokens": 120,
                        "output_tokens": 450,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0
                    }
                }
            },
            {
                "type": "assistant",
                "sessionId": "sess-real-1",
                "timestamp": today_iso,
                "message": {
                    "model": "claude-sonnet-5-5",
                    "usage": {
                        "input_tokens": 80,
                        "output_tokens": 300,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0
                    }
                }
            }
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for item in lines:
                f.write(json.dumps(item) + "\n")

        # Scan directory
        count = self.claude.scan_local_logs(search_dir=str(mock_claude_dir))
        self.assertEqual(count, 2)

        # Verify ingested in database
        summary = self.db.get_usage_summary(provider="claude")
        self.assertEqual(summary["input_tokens_today"], 200)
        self.assertEqual(summary["output_tokens_today"], 750)
        self.assertEqual(summary["total_tokens_today"], 950)

        # Idempotency check: running scan again should not duplicate rows
        count2 = self.claude.scan_local_logs(search_dir=str(mock_claude_dir))
        self.assertEqual(count2, 0)
        summary2 = self.db.get_usage_summary(provider="claude")
        self.assertEqual(summary2["total_tokens_today"], 950)

if __name__ == "__main__":
    unittest.main()
