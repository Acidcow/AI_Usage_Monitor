import unittest
import sys
import tempfile
import os
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.storage.importer import TelemetryImporter

class TestEnterpriseImporter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_import_usage.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.importer = TelemetryImporter(self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_json_array_records(self):
        raw_json = json.dumps([
            {"provider": "copilot", "model": "gpt-4o", "input_tokens": 500, "output_tokens": 120, "session_id": "m365-sess-1"},
            {"provider": "copilot", "model": "gpt-4o", "input_tokens": 800, "output_tokens": 250, "session_id": "m365-sess-2"}
        ])
        count = self.importer.import_raw_telemetry(raw_json, default_provider="copilot")
        self.assertEqual(count, 2)

        summary = self.db.get_usage_summary(provider="copilot")
        self.assertEqual(summary["total_tokens_today"], 1670)

    def test_import_csv_records(self):
        raw_csv = """provider,model,input_tokens,output_tokens,session_id
copilot,copilot-chat,300,100,csv-sess-1
claude,claude-3-5-sonnet,400,150,csv-sess-2
"""
        count = self.importer.import_raw_telemetry(raw_csv)
        self.assertEqual(count, 2)

        summary = self.db.get_usage_summary()
        self.assertEqual(summary["total_tokens_today"], 950)

    def test_manual_interaction_logging(self):
        evt_id = self.importer.log_manual_interaction(
            provider="copilot",
            model="m365-chat",
            input_tokens=150,
            output_tokens=75,
            session_id="manual-run-1"
        )
        self.assertTrue(evt_id.startswith("evt_"))

        sessions = self.db.get_recent_sessions(provider="copilot")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], "manual-run-1")

if __name__ == "__main__":
    unittest.main()
