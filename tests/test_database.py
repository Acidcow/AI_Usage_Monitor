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

    def test_comparative_metrics_and_local_savings(self):
        # Record cloud usage (Claude)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-5-sonnet",
            input_tokens=1000,
            output_tokens=500,
            session_id="sess-claude"
        )
        # Record local usage (Ollama)
        self.db.record_usage_event(
            provider="ollama",
            model="llama3:8b",
            input_tokens=200000,
            output_tokens=100000,
            session_id="sess-ollama"
        )

        comp = self.db.get_comparative_metrics()
        self.assertIn("providers", comp)
        self.assertIn("local_savings", comp)

        providers = comp["providers"]
        self.assertIn("claude", providers)
        self.assertIn("ollama", providers)
        self.assertEqual(providers["claude"]["tokens_today"], 1500)
        self.assertEqual(providers["ollama"]["tokens_today"], 300000)

        # Check local savings calculations ($6.00/M tokens benchmark)
        # 300,000 / 1,000,000 * 6.00 = $1.80
        savings = comp["local_savings"]
        self.assertEqual(savings["local_tokens_today"], 300000)
        self.assertAlmostEqual(savings["savings_today_usd"], 1.80, places=2)
        self.assertEqual(savings["privacy_rating"], "100% On-Premise")

    def test_hierarchical_scopes_and_drilldown(self):
        """Assert multi-scope separation between Individual, Team, Dept, Enterprise."""
        self.db.update_provider_snapshot(
            provider="claude",
            plan_type="Team Enterprise",
            user_name="James Eckhardt",
            team_name="Synthesis Engineering Core",
            dept_name="Technology & AI Architecture",
            org_name="Synthesis Software Technologies",
            individual_session_rem_pct=40.0,
            individual_weekly_rem_pct=73.0,
            team_session_rem_pct=44.0,
            team_weekly_rem_pct=74.0,
            active_scope="individual",
            status="ACTIVE"
        )

        # 1. Query individual scope
        comp_ind = self.db.get_comparative_metrics(scope="individual")
        self.assertEqual(comp_ind["active_scope"], "individual")
        claude_ind = comp_ind["providers"]["claude"]
        self.assertEqual(claude_ind["session_balance_remaining_pct"], 40.0)
        self.assertEqual(claude_ind["weekly_balance_remaining_pct"], 73.0)

        # Hierarchy validation
        h = claude_ind["hierarchy"]
        self.assertEqual(h["user_name"], "James Eckhardt")
        self.assertEqual(h["individual"]["session_remaining_pct"], 40.0)
        self.assertEqual(h["individual"]["session_used_pct"], 60.0)
        self.assertEqual(h["individual"]["weekly_remaining_pct"], 73.0)
        self.assertEqual(h["individual"]["weekly_used_pct"], 27.0)

        self.assertEqual(h["team"]["session_remaining_pct"], 44.0)
        self.assertEqual(h["team"]["session_used_pct"], 56.0)
        self.assertEqual(h["team"]["weekly_remaining_pct"], 74.0)
        self.assertEqual(h["team"]["weekly_used_pct"], 26.0)

        self.assertIn("department", h)
        self.assertEqual(h["department"]["dept_name"], "Technology & AI Architecture")
        self.assertEqual(h["department"]["active_seats"], 14)

        self.assertIn("enterprise", h)
        self.assertEqual(h["enterprise"]["org_name"], "Synthesis Software Technologies")
        self.assertTrue(h["enterprise"]["shared_pool_active"])

        # 2. Query team scope
        comp_team = self.db.get_comparative_metrics(scope="team")
        self.assertEqual(comp_team["active_scope"], "team")
        claude_team = comp_team["providers"]["claude"]
        self.assertEqual(claude_team["session_balance_remaining_pct"], 44.0)
        self.assertEqual(claude_team["weekly_balance_remaining_pct"], 74.0)

if __name__ == "__main__":
    unittest.main()


