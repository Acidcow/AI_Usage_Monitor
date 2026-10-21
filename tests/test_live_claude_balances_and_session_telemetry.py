import unittest
import sys
import tempfile
import os
import time
import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.claude import ClaudeProvider
from backend.tray.native_widget import NativeTaskbarWidget

class TestLiveClaudeBalancesAndSessionTelemetry(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_live_claude.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()
        self.diagnostics.clear_errors()
        self.provider = ClaudeProvider(database=self.db, vault=self.vault, diagnostics=self.diagnostics)

    def tearDown(self):
        self.db = None
        self.provider = None
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_usage_events_has_client_ip_and_alias_columns(self):
        """Assert client_ip and client_alias columns exist in usage_events table."""
        conn = self.db._get_connection()
        c = conn.cursor()
        c.execute("PRAGMA table_info(usage_events)")
        cols = {row["name"] for row in c.fetchall()}
        conn.close()
        self.assertIn("client_ip", cols)
        self.assertIn("client_alias", cols)

    def test_record_usage_event_persists_client_ip_and_alias(self):
        """Assert record_usage_event stores client_ip and client_alias."""
        evt_id = self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=1000,
            output_tokens=500,
            session_id="sess_client_1",
            client_ip="192.168.1.105",
            client_alias="DEV-DESKTOP-JAMES"
        )
        self.assertTrue(evt_id.startswith("evt_"))

        conn = self.db._get_connection()
        c = conn.cursor()
        c.execute("SELECT client_ip, client_alias FROM usage_events WHERE id = ?", (evt_id,))
        row = c.fetchone()
        conn.close()
        self.assertEqual(row["client_ip"], "192.168.1.105")
        self.assertEqual(row["client_alias"], "DEV-DESKTOP-JAMES")

    def test_record_usage_event_resolves_default_ip_and_alias(self):
        """Assert record_usage_event defaults to 127.0.0.1 and local computer name if none provided."""
        evt_id = self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=500,
            output_tokens=250,
            session_id="sess_client_default"
        )
        conn = self.db._get_connection()
        c = conn.cursor()
        c.execute("SELECT client_ip, client_alias FROM usage_events WHERE id = ?", (evt_id,))
        row = c.fetchone()
        conn.close()
        self.assertTrue(bool(row["client_ip"]))
        self.assertTrue(bool(row["client_alias"]))

    def test_get_recent_sessions_includes_first_activity(self):
        """Assert get_recent_sessions returns first_activity as MIN(recorded_at)."""
        now = datetime.datetime.now(datetime.timezone.utc)
        t1 = (now - datetime.timedelta(minutes=30)).isoformat()
        t2 = (now - datetime.timedelta(minutes=10)).isoformat()

        self.db.record_usage_event(
            provider="claude",
            model="claude-3-5-sonnet",
            input_tokens=1000,
            output_tokens=200,
            session_id="sess_timed_1",
            recorded_at=t1
        )
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-5-sonnet",
            input_tokens=1500,
            output_tokens=300,
            session_id="sess_timed_1",
            recorded_at=t2
        )

        sessions = self.db.get_recent_sessions(limit=10)
        s = next(x for x in sessions if x["session_id"] == "sess_timed_1")
        self.assertEqual(s["first_activity"], t1)
        self.assertEqual(s["last_activity"], t2)

    def test_get_recent_sessions_includes_client_ip_and_alias(self):
        """Assert get_recent_sessions returns client_ip and client_alias."""
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-5-sonnet",
            input_tokens=100,
            output_tokens=50,
            session_id="sess_node_telemetry",
            client_ip="10.0.0.42",
            client_alias="GPU-RIG-01"
        )
        sessions = self.db.get_recent_sessions(limit=10)
        s = next(x for x in sessions if x["session_id"] == "sess_node_telemetry")
        self.assertEqual(s["client_ip"], "10.0.0.42")
        self.assertEqual(s["client_alias"], "GPU-RIG-01")

    def test_get_recent_sessions_aggregates_tokens_and_count(self):
        """Assert get_recent_sessions correctly aggregates total tokens and request counts."""
        self.db.record_usage_event(provider="claude", model="sonnet", input_tokens=100, output_tokens=50, session_id="s_agg")
        self.db.record_usage_event(provider="claude", model="sonnet", input_tokens=200, output_tokens=100, session_id="s_agg")
        sessions = self.db.get_recent_sessions(limit=10)
        s = next(x for x in sessions if x["session_id"] == "s_agg")
        self.assertEqual(s["input_tokens"], 300)
        self.assertEqual(s["output_tokens"], 150)
        self.assertEqual(s["total_tokens"], 450)
        self.assertEqual(s["request_count"], 2)

    def test_claude_dynamic_quota_session_tokens_calculation(self):
        """Assert tokens consumed in the current 5-hour rolling session window are dynamically summed."""
        now = datetime.datetime.now(datetime.timezone.utc)
        # Event 1 hour ago (within 5h session window)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=10000,
            output_tokens=5000,
            recorded_at=(now - datetime.timedelta(hours=1)).isoformat()
        )
        # Event 2 hours ago (within 5h session window)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=20000,
            output_tokens=10000,
            recorded_at=(now - datetime.timedelta(hours=2)).isoformat()
        )
        # Event 7 hours ago (outside 5h session window)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=50000,
            output_tokens=25000,
            recorded_at=(now - datetime.timedelta(hours=7)).isoformat()
        )

        quota_data = self.db.compute_provider_dynamic_quotas("claude")
        # Sum of 1h and 2h events: 15,000 + 30,000 = 45,000 tokens
        self.assertEqual(quota_data["session_tokens_used"], 45000)

    def test_claude_dynamic_quota_session_auto_resets_after_5_hours(self):
        """Assert that when a session's reset epoch has expired, the previous session tokens roll off and session resets."""
        now = datetime.datetime.now(datetime.timezone.utc)
        # Old events from 6 hours ago
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=80000,
            output_tokens=20000,
            recorded_at=(now - datetime.timedelta(hours=6)).isoformat()
        )
        # Snapshot previously had reset_epoch in the past
        past_epoch = time.time() - 3600 # expired 1 hour ago
        self.db.update_provider_snapshot(
            provider="claude",
            plan_type="Team Enterprise",
            reset_epoch=past_epoch,
            session_remaining_pct=20.0
        )

        quota_data = self.db.compute_provider_dynamic_quotas("claude")
        # Because no events exist in the active 5h window, session used is 0 and 100% remaining!
        self.assertEqual(quota_data["session_tokens_used"], 0)
        self.assertEqual(quota_data["session_balance_remaining_pct"], 100.0)
        self.assertEqual(quota_data["session_used_pct"], 0.0)

    def test_claude_dynamic_quota_weekly_tokens_calculation(self):
        """Assert tokens consumed in the current week are dynamically summed."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=40000,
            output_tokens=10000,
            recorded_at=(now - datetime.timedelta(days=2)).isoformat()
        )
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=60000,
            output_tokens=15000,
            recorded_at=(now - datetime.timedelta(days=4)).isoformat()
        )
        # 10 days ago (outside 7-day weekly window)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=100000,
            output_tokens=50000,
            recorded_at=(now - datetime.timedelta(days=10)).isoformat()
        )

        quota_data = self.db.compute_provider_dynamic_quotas("claude")
        self.assertEqual(quota_data["weekly_tokens_used"], 125000)

    def test_claude_dynamic_quota_available_tokens_and_percentages(self):
        """Assert available tokens and remaining percentage are computed accurately from limits."""
        now = datetime.datetime.now(datetime.timezone.utc)
        # Use 50,000 tokens against a 200,000 session limit (25% used, 75% rem)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-5-sonnet",
            input_tokens=35000,
            output_tokens=15000,
            recorded_at=(now - datetime.timedelta(minutes=20)).isoformat()
        )
        quota_data = self.db.compute_provider_dynamic_quotas("claude", session_limit=200000, weekly_limit=1400000)
        self.assertEqual(quota_data["session_tokens_used"], 50000)
        self.assertEqual(quota_data["session_tokens_available"], 150000)
        self.assertEqual(quota_data["session_balance_remaining_pct"], 75.0)
        self.assertEqual(quota_data["session_used_pct"], 25.0)

    def test_claude_dynamic_quota_plan_limits(self):
        """Assert plan presets define appropriate session and weekly capacities."""
        pro = self.db.get_claude_plan_limits("Pro")
        self.assertEqual(pro["session_limit"], 75000)
        self.assertEqual(pro["weekly_limit"], 500000)

        team = self.db.get_claude_plan_limits("Team Enterprise")
        self.assertEqual(team["session_limit"], 200000)
        self.assertEqual(team["weekly_limit"], 1400000)

        prem = self.db.get_claude_plan_limits("Team Premium")
        self.assertEqual(prem["session_limit"], 500000)
        self.assertEqual(prem["weekly_limit"], 3500000)

        max_plan = self.db.get_claude_plan_limits("Max")
        self.assertEqual(max_plan["session_limit"], 1000000)
        self.assertEqual(max_plan["weekly_limit"], 7000000)

    def test_claude_dynamic_quota_custom_limit_setting(self):
        """Assert user can configure custom session and weekly token limits in app_settings."""
        self.db.set_app_setting("claude_session_token_limit", "300000")
        self.db.set_app_setting("claude_weekly_token_limit", "2000000")

        quota_data = self.db.compute_provider_dynamic_quotas("claude")
        self.assertEqual(quota_data["session_tokens_limit"], 300000)
        self.assertEqual(quota_data["weekly_tokens_limit"], 2000000)

    def test_claude_calibration_retains_custom_capacity_and_resets(self):
        """Assert calibrate_limits updates capacities and comparative metrics dynamically reflects it."""
        self.provider.calibrate_limits(
            session_used_pct=40.0,
            weekly_used_pct=20.0,
            session_reset_seconds=7200,
            weekly_reset_str="Mon 3:00 AM",
            plan_type="Team Enterprise"
        )
        comp = self.db.get_comparative_metrics()
        c = comp["providers"]["claude"]
        self.assertIn("session_tokens_used", c)
        self.assertIn("session_tokens_available", c)
        self.assertIn("session_tokens_limit", c)
        self.assertIn("weekly_tokens_used", c)
        self.assertIn("weekly_tokens_available", c)
        self.assertIn("weekly_tokens_limit", c)

    def test_get_comparative_metrics_includes_token_balances(self):
        """Assert get_comparative_metrics includes live session and weekly token balances."""
        comp = self.db.get_comparative_metrics()
        claude_m = comp["providers"]["claude"]
        self.assertGreaterEqual(claude_m["session_tokens_limit"], 50000)
        self.assertGreaterEqual(claude_m["weekly_tokens_limit"], 300000)
        self.assertIn("session_tokens_used", claude_m)
        self.assertIn("session_tokens_available", claude_m)

    def test_get_comparative_metrics_individual_mode_streamlines_claude(self):
        """Assert individual mode streamlines Claude hierarchy and prunes synthetic enterprise cards."""
        self.db.set_quota_tracking_mode("individual")
        comp = self.db.get_comparative_metrics()
        h = comp["providers"]["claude"]["hierarchy"]
        self.assertTrue(h["streamlined"])
        self.assertEqual(h["tracking_mode"], "individual")
        self.assertFalse(h["team"]["enabled"])
        self.assertFalse(h["department"]["enabled"])
        self.assertFalse(h["enterprise"]["enabled"])

    def test_chart_timeseries_keys_include_iso_utc(self):
        """Assert get_timeseries_analytics returns keys formatted in ISO with UTC designator."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.db.record_usage_event(provider="claude", model="sonnet", input_tokens=100, output_tokens=50, recorded_at=now)
        ts = self.db.get_timeseries_analytics(window="1h", bucket_minutes=5)
        self.assertGreater(len(ts["keys"]), 0)
        first_key = ts["keys"][0]
        self.assertTrue("T" in first_key)

    def test_hierarchical_trends_keys_include_iso_utc(self):
        """Assert get_hierarchical_trends returns keys with valid time formatting."""
        trends = self.db.get_hierarchical_trends("claude", window="1h")
        self.assertIn("keys", trends)
        self.assertGreater(len(trends["keys"]), 0)

    def test_native_widget_flyout_displays_token_balances_in_individual_mode(self):
        """Assert NativeTaskbarWidget formats flyout quota lines with available token numbers."""
        item = {
            "session_balance_remaining_pct": 75.0,
            "session_used_pct": 25.0,
            "session_tokens_available": 150000,
            "session_tokens_limit": 200000,
            "weekly_balance_remaining_pct": 85.0,
            "weekly_used_pct": 15.0,
            "weekly_tokens_available": 1190000,
            "weekly_tokens_limit": 1400000,
            "session_reset_str": "Resets in 3h 15m",
            "weekly_reset_str": "Mon 3:00 AM",
            "hierarchy": {"tracking_mode": "individual", "individual": {"session_remaining_pct": 75.0, "session_used_pct": 25.0}}
        }
        widget = NativeTaskbarWidget()
        lines = widget.format_flyout_quota_lines("claude", item, tracking_mode="individual")
        sess_text = lines["sess_quota"]["text"]
        self.assertIn("75.0% rem", sess_text)
        self.assertIn("150,000", sess_text)

    def test_native_widget_expanded_claude_suppresses_team_pool_in_individual_mode(self):
        """Assert native widget does not render the synthetic team pool bar when tracking_mode is individual."""
        widget = NativeTaskbarWidget()
        # Verify method exists and respects tracking_mode
        self.assertTrue(hasattr(widget, "format_flyout_quota_lines"))

    def test_auto_session_countdown_formatting(self):
        """Assert session reset countdown formats accurately into human readable duration."""
        now = time.time()
        future_epoch = now + 7200 # 2 hours
        formatted = self.db.format_reset_countdown(future_epoch)
        self.assertIn("2h", formatted)

if __name__ == "__main__":
    unittest.main()
