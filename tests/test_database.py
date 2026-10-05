import unittest
import sys
import tempfile
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase

class TestUsageDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_usage.db")
        self.db = UsageDatabase(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_record_usage_and_get_summary(self):
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=1500,
            output_tokens=500,
            session_id="sess-001"
        )
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-5-sonnet",
            input_tokens=800,
            output_tokens=200,
            session_id="sess-002"
        )

        summary = self.db.get_usage_summary()
        self.assertEqual(summary["total_tokens_today"], 3000)
        self.assertEqual(summary["input_tokens_today"], 2300)
        self.assertEqual(summary["output_tokens_today"], 700)
        self.assertEqual(summary["total_sessions"], 2)

    def test_provider_snapshot_update_and_read(self):
        self.db.update_provider_snapshot(
            provider="claude",
            plan_type="Pro",
            tokens_remaining=95000,
            requests_remaining=98,
            reset_epoch=1760000000.0,
            status="ACTIVE"
        )

        snapshots = self.db.get_provider_snapshots()
        self.assertIn("claude", snapshots)
        claude_info = snapshots["claude"]
        self.assertEqual(claude_info["plan_type"], "Pro")
        self.assertEqual(claude_info["tokens_remaining"], 95000)
        self.assertEqual(claude_info["status"], "ACTIVE")

    def test_recent_sessions_retrieval(self):
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=100,
            output_tokens=50,
            session_id="session-alpha"
        )

        sessions = self.db.get_recent_sessions(limit=10)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], "session-alpha")
        self.assertEqual(sessions[0]["total_tokens"], 150)

if __name__ == "__main__":
    unittest.main()
