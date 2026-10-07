import unittest
import sys
import tempfile
import os
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.claude import ClaudeProvider

class TestClaudeProvider(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_claude_usage.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()
        self.diagnostics.clear_errors()
        self.provider = ClaudeProvider(database=self.db, vault=self.vault, diagnostics=self.diagnostics)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_provider_initialization_state(self):
        self.assertEqual(self.provider.provider_name, "claude")
        self.assertEqual(self.provider.display_name, "Claude (Anthropic)")
        self.assertFalse(self.provider.is_configured)

    def test_mock_simulation_mode(self):
        # Enable simulation mode for offline/POC testing
        self.provider.enable_simulation_mode(True)
        res = self.provider.sync_usage()
        self.assertTrue(res["success"])
        self.assertGreater(res["tokens_generated"], 0)

        # Check DB was populated
        summary = self.db.get_usage_summary(provider="claude")
        self.assertGreater(summary["total_tokens_today"], 0)

        # Check snapshot was updated
        snapshots = self.db.get_provider_snapshots()
        self.assertIn("claude", snapshots)
        self.assertEqual(snapshots["claude"]["plan_type"], "Team Enterprise")

    def test_parse_anthropic_headers(self):
        headers = {
            "anthropic-ratelimit-requests-limit": "1000",
            "anthropic-ratelimit-requests-remaining": "942",
            "anthropic-ratelimit-tokens-limit": "400000",
            "anthropic-ratelimit-tokens-remaining": "382100",
            "anthropic-ratelimit-tokens-reset": "2026-10-05T14:00:00Z"
        }
        parsed = self.provider.parse_rate_limit_headers(headers)
        self.assertEqual(parsed["requests_remaining"], 942)
        self.assertEqual(parsed["tokens_remaining"], 382100)
        self.assertEqual(parsed["tokens_limit"], 400000)

    def test_ingest_cli_proxy_interaction(self):
        event_id = self.provider.ingest_proxy_interaction(
            model="claude-3-7-sonnet-20250219",
            input_tokens=2400,
            output_tokens=850,
            session_id="agent-cli-run-42",
            rate_limit_headers={
                "anthropic-ratelimit-tokens-remaining": "350000",
                "anthropic-ratelimit-requests-remaining": "900"
            }
        )
        self.assertTrue(event_id.startswith("evt_"))
        summary = self.db.get_usage_summary(provider="claude")
        self.assertEqual(summary["total_tokens_today"], 3250)

    def test_calibrate_limits_and_metrics(self):
        res = self.provider.calibrate_limits(
            session_used_pct=56.0,
            session_reset_seconds=7560,
            weekly_used_pct=26.0,
            weekly_reset_str="Mon 3:00 AM",
            plan_type="Team Enterprise"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["session_remaining_pct"], 44.0)
        self.assertEqual(res["session_used_pct"], 56.0)
        self.assertEqual(res["weekly_remaining_pct"], 74.0)
        self.assertEqual(res["weekly_used_pct"], 26.0)
        self.assertEqual(res["weekly_reset_str"], "Mon 3:00 AM")

        # Verify DB comparative metrics reflects calibrated percentages
        comp = self.db.get_comparative_metrics()
        claude_m = comp["providers"]["claude"]
        self.assertEqual(claude_m["session_balance_remaining_pct"], 44.0)
        self.assertEqual(claude_m["session_used_pct"], 56.0)
        self.assertEqual(claude_m["weekly_balance_remaining_pct"], 74.0)
        self.assertEqual(claude_m["weekly_used_pct"], 26.0)
        self.assertEqual(claude_m["weekly_reset_str"], "Mon 3:00 AM")
        self.assertEqual(claude_m["plan_type"], "Team Enterprise")

if __name__ == "__main__":
    unittest.main()
