import unittest
import os
import tempfile
import datetime

from backend.storage.database import DatabaseEngine

class TestReportsAnalytics(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_rep.db")
        self.db = DatabaseEngine(self.db_path)

        # Seed dimensional usage events
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=1500,
            output_tokens=500,
            session_id="sess_c1",
            account_id="Synthesis2",
            team_name="Synthesis2",
            user_name="James Eckhardt",
            project_id="Proj-Alpha"
        )
        self.db.record_usage_event(
            provider="gemini",
            model="gemini-2.0-flash",
            input_tokens=8000,
            output_tokens=2000,
            session_id="sess_g1",
            account_id="acidcow@gmail.com",
            team_name="Personal",
            user_name="James Eckhardt",
            token_id="tok_gem_flash",
            project_id="CLI-Scripts"
        )
        self.db.record_usage_event(
            provider="chatgpt",
            model="gpt-4o",
            input_tokens=3000,
            output_tokens=1000,
            session_id="sess_o1",
            account_id="org-enterprise",
            team_name="Synthesis2",
            user_name="Alice Smith",
            project_id="Proj-Alpha"
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_query_historical_report_daily(self):
        res = self.db.query_historical_report(group_by="day")
        self.assertIn("rows", res)
        self.assertIn("summary", res)
        self.assertEqual(res["summary"]["total_events"], 3)
        self.assertEqual(res["summary"]["total_tokens"], 2000 + 10000 + 4000)
        self.assertGreater(res["summary"]["total_estimated_cost"], 0.0)

    def test_query_historical_report_dimension_grouping(self):
        # Group by team_name
        res_team = self.db.query_historical_report(group_by="day", dimension="team_name")
        self.assertGreaterEqual(len(res_team["rows"]), 2)
        group_keys = [r["group_key"] for r in res_team["rows"]]
        self.assertIn("Synthesis2", group_keys)

        # Group by user_name
        res_user = self.db.query_historical_report(group_by="day", dimension="user_name")
        user_keys = [r["group_key"] for r in res_user["rows"]]
        self.assertIn("James Eckhardt", user_keys)

        # Filter by provider
        res_gemini = self.db.query_historical_report(group_by="day", provider="gemini")
        self.assertEqual(len(res_gemini["rows"]), 1)
        self.assertEqual(res_gemini["rows"][0]["total_tokens"], 10000)

    def test_export_historical_csv(self):
        csv_str = self.db.export_historical_csv(group_by="day")
        self.assertIn("Period,Provider,Account,Team,User,Model", csv_str)
        lines = csv_str.strip().split("\r\n" if "\r\n" in csv_str else "\n")
        self.assertGreaterEqual(len(lines), 2)

if __name__ == "__main__":
    unittest.main()
