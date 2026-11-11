"""
Unit tests for Ticket AIUM-1010:
Rolling 5h/7d Burn-Rate Pacing Forecaster, Cross-Tab Quota Alignment & Context-Window Bloat Detector.
Zero external dependencies. Python 3 standard library only.
"""

import datetime
import os
import tempfile
import time
import unittest
from pathlib import Path

from backend.analytics.throughput_engine import ThroughputAnalyticsEngine, ThroughputEngine
from backend.storage.database import UsageDatabase

class TestQuotaPacingAndBloatDetector(unittest.TestCase):
    """
    Test suite for Quota Pacing Forecaster, Cross-Tab Quota Alignment,
    and Context Bloat / Loop Detection.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_aium.db")
        self.db = UsageDatabase(self.db_path)
        self.engine = ThroughputAnalyticsEngine(self.db)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _insert_event(
        self,
        provider="claude",
        model="claude-3-5-sonnet",
        session_id="sess_1",
        input_tokens=1000,
        output_tokens=100,
        recorded_at=None,
    ):
        if recorded_at is None:
            recorded_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        total_tokens = input_tokens + output_tokens
        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usage_events (
                    id, provider, model, session_id, input_tokens, output_tokens,
                    total_tokens, estimated_cost, request_count, recorded_at,
                    source, instance_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    f"ev_{time.time_ns()}",
                    provider.lower(),
                    model,
                    session_id,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    0.005,
                    1,
                    recorded_at,
                    "direct",
                    "local",
                ),
            )
            conn.commit()
            conn.close()

    # --- 1. Cross-Tab Quota Alignment Tests ---

    def test_01_cross_tab_quota_alignment_claude_dynamic(self):
        """Verify get_provider_hierarchies aligns with comparative metrics and dynamic quota."""
        self._insert_event(provider="claude", input_tokens=4000, output_tokens=1000)
        hierarchies = self.db.get_provider_hierarchies()
        comp = self.db.get_comparative_metrics()

        self.assertIn("claude", hierarchies)
        claude_h = hierarchies["claude"]
        claude_c = comp["providers"]["claude"]

        self.assertEqual(claude_h["session_remaining_pct"], claude_c["session_remaining_pct"])
        self.assertEqual(claude_h["weekly_remaining_pct"], claude_c["weekly_remaining_pct"])
        self.assertEqual(claude_h["session_tokens_limit"], claude_c["session_tokens_limit"])
        self.assertEqual(claude_h["session_reset_str"], claude_c["session_reset_str"])

    def test_02_cross_tab_quota_alignment_snapshot_propagation(self):
        """Verify snapshot updates propagate identically across hierarchy and comparative views."""
        self.db.update_provider_snapshot(
            provider="claude",
            session_remaining_pct=62.5,
            weekly_remaining_pct=81.0,
            account_id="user_test",
        )
        hierarchies = self.db.get_provider_hierarchies()
        comp = self.db.get_comparative_metrics()

        self.assertEqual(hierarchies["claude"]["session_remaining_pct"], comp["providers"]["claude"]["session_remaining_pct"])
        self.assertEqual(hierarchies["claude"]["weekly_remaining_pct"], comp["providers"]["claude"]["weekly_remaining_pct"])

    def test_03_cross_tab_quota_alignment_non_claude_provider(self):
        """Verify Gemini metrics align between get_provider_hierarchies and get_comparative_metrics."""
        self.db.update_provider_snapshot(
            provider="gemini",
            session_remaining_pct=75.0,
            weekly_remaining_pct=90.0,
            account_id="gemini_user",
        )
        hierarchies = self.db.get_provider_hierarchies()
        comp = self.db.get_comparative_metrics()

        self.assertEqual(hierarchies["gemini"]["session_remaining_pct"], comp["providers"]["gemini"]["session_remaining_pct"])
        self.assertEqual(hierarchies["gemini"]["weekly_remaining_pct"], comp["providers"]["gemini"]["weekly_remaining_pct"])

    # --- 2. parse_minutes_until_reset Tests ---

    def test_04_parse_minutes_until_reset_hours_and_minutes(self):
        """Parses 'Resets in 3h 15m' into 195.0 minutes."""
        mins = self.engine.parse_minutes_until_reset("Resets in 3h 15m")
        self.assertEqual(mins, 195.0)

    def test_05_parse_minutes_until_reset_minutes_and_seconds(self):
        """Parses 'Resets in 45m 12s' into 45.2 minutes."""
        mins = self.engine.parse_minutes_until_reset("Resets in 45m 12s")
        self.assertAlmostEqual(mins, 45.2, places=1)

    def test_06_parse_minutes_until_reset_seconds_only(self):
        """Parses 'Resets in 30s' into 0.5 minutes."""
        mins = self.engine.parse_minutes_until_reset("Resets in 30s")
        self.assertAlmostEqual(mins, 0.5, places=1)

    def test_07_parse_minutes_until_reset_rolling_window_str(self):
        """Parses '5h rolling window' into 300.0 minutes."""
        mins = self.engine.parse_minutes_until_reset("5h rolling window")
        self.assertEqual(mins, 300.0)

    def test_08_parse_minutes_until_reset_session_ready(self):
        """Parses 'Session Reset Ready' into 0.0 minutes."""
        mins = self.engine.parse_minutes_until_reset("Session Reset Ready")
        self.assertEqual(mins, 0.0)

    def test_09_parse_minutes_until_reset_epoch(self):
        """Parses epoch timestamp into correct delta minutes."""
        future_epoch = time.time() + 3600  # 60 mins from now
        mins = self.engine.parse_minutes_until_reset(future_epoch)
        self.assertAlmostEqual(mins, 60.0, delta=1.0)

    def test_10_parse_minutes_until_reset_iso_string(self):
        """Parses future ISO timestamp string into correct delta minutes."""
        future_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=120)
        mins = self.engine.parse_minutes_until_reset(future_dt.isoformat())
        self.assertAlmostEqual(mins, 120.0, delta=1.0)

    def test_11_parse_minutes_until_reset_fallback(self):
        """Defaults to 300.0 for unknown or None reset specifications."""
        self.assertEqual(self.engine.parse_minutes_until_reset(None), 300.0)
        self.assertEqual(self.engine.parse_minutes_until_reset(""), 300.0)
        self.assertEqual(self.engine.parse_minutes_until_reset("unknown_format"), 300.0)

    # --- 3. compute_quota_pacing_forecast Scenarios ---

    def test_12_compute_quota_pacing_forecast_idle_state(self):
        """Asserts IDLE state when no events exist in rolling window."""
        res = self.engine.compute_quota_pacing_forecast("claude")
        self.assertEqual(res["pacing_status"], "IDLE")
        self.assertEqual(res["tokens_per_minute"], 0.0)
        self.assertIsNone(res["estimated_minutes_to_exhaustion"])
        self.assertIn("⚪ Idle", res["pacing_badge_text"])

    def test_13_compute_quota_pacing_forecast_sustainable_pace(self):
        """Asserts SUSTAINABLE state when exhaustion time >= minutes until reset."""
        self.db.update_provider_snapshot(
            provider="claude",
            session_remaining_pct=90.0,
            reset_epoch=time.time() + 3600,  # 60m to reset
        )
        # Remaining: ~180,000 tokens (out of 200,000 limit)
        # Insert 3,000 tokens in last 10m -> 100 tok/min -> 1800 mins runway >= 60 mins
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        self._insert_event(
            provider="claude",
            input_tokens=2500,
            output_tokens=500,
            recorded_at=(now_dt - datetime.timedelta(minutes=5)).isoformat(),
        )

        res = self.engine.compute_quota_pacing_forecast("claude")
        self.assertEqual(res["pacing_status"], "SUSTAINABLE")
        self.assertIn("🟢 Sustainable", res["pacing_badge_text"])
        self.assertIsNotNone(res["estimated_minutes_to_exhaustion"])
        self.assertGreaterEqual(res["estimated_minutes_to_exhaustion"], res["minutes_until_reset"])

    def test_14_compute_quota_pacing_forecast_warning_high_burn(self):
        """Asserts WARNING_HIGH_BURN when exhaustion < reset time but >= 0.75 * reset time."""
        # 100 minutes to reset
        reset_epoch = time.time() + (100 * 60)
        self.db.update_provider_snapshot(
            provider="claude",
            session_remaining_pct=11.5,  # 11.5% of limit gives ~86 mins exhaustion at 100 tok/min
            reset_epoch=reset_epoch,
        )
        # Burn rate: 3,000 tokens over 30 mins = 100 tok/min
        # Estimated exhaustion = ~86 mins
        # 86m is < 100m (reset), but >= 75m (0.75 * 100m) => WARNING_HIGH_BURN
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        self._insert_event(
            provider="claude",
            input_tokens=2500,
            output_tokens=500,
            recorded_at=(now_dt - datetime.timedelta(minutes=5)).isoformat(),
        )

        res = self.engine.compute_quota_pacing_forecast("claude")
        self.assertEqual(res["pacing_status"], "WARNING_HIGH_BURN")
        self.assertIn("🟡 High Burn", res["pacing_badge_text"])

    def test_15_compute_quota_pacing_forecast_impending_lockout(self):
        """Asserts IMPENDING_LOCKOUT when exhaustion < 0.75 * minutes until reset."""
        # 100 minutes to reset
        reset_epoch = time.time() + (100 * 60)
        self.db.update_provider_snapshot(
            provider="claude",
            session_remaining_pct=2.5,  # 2.5% of 200,000 = 5,000 tokens
            reset_epoch=reset_epoch,
        )
        # Burn rate: 3,000 tokens over 30 mins = 100 tok/min
        # Estimated exhaustion = 50 mins < 75 mins (0.75 * 100m) => IMPENDING_LOCKOUT
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        self._insert_event(
            provider="claude",
            input_tokens=2500,
            output_tokens=500,
            recorded_at=(now_dt - datetime.timedelta(minutes=5)).isoformat(),
        )

        res = self.engine.compute_quota_pacing_forecast("claude")
        self.assertEqual(res["pacing_status"], "IMPENDING_LOCKOUT")
        self.assertIn("🔴 Lockout Before Reset", res["pacing_badge_text"])

    def test_16_quota_pacing_burn_velocity_falls_back_to_5h(self):
        """When no events in 30m, falls back to 5h window velocity."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        # Event 90 minutes ago (within 5h, but outside 30m)
        self._insert_event(
            provider="claude",
            input_tokens=6000,
            output_tokens=0,
            recorded_at=(now_dt - datetime.timedelta(minutes=90)).isoformat(),
        )

        res = self.engine.compute_quota_pacing_forecast("claude")
        self.assertEqual(res["tokens_per_minute_30m"], 0.0)
        self.assertGreater(res["tokens_per_minute_5h"], 0.0)
        self.assertEqual(res["tokens_per_minute"], res["tokens_per_minute_5h"])

    # --- 4. detect_context_bloat_and_loops Tests ---

    def test_17_detect_context_bloat_positive_flagged(self):
        """Flags CONTEXT_BLOAT across 4 consecutive turns with >40% avg input growth and <20% output."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        sid = "bloated_sess_101"
        # Turn 1: 1000 in, 50 out (5% < 20%)
        self._insert_event("claude", "claude-3-5-sonnet", sid, 1000, 50, (now_dt - datetime.timedelta(minutes=40)).isoformat())
        # Turn 2: 1500 in, 60 out (+50% growth, 4% < 20%)
        self._insert_event("claude", "claude-3-5-sonnet", sid, 1500, 60, (now_dt - datetime.timedelta(minutes=30)).isoformat())
        # Turn 3: 2200 in, 70 out (+46.7% growth, 3.2% < 20%)
        self._insert_event("claude", "claude-3-5-sonnet", sid, 2200, 70, (now_dt - datetime.timedelta(minutes=20)).isoformat())
        # Turn 4: 3200 in, 80 out (+45.5% growth, 2.5% < 20%)
        self._insert_event("claude", "claude-3-5-sonnet", sid, 3200, 80, (now_dt - datetime.timedelta(minutes=10)).isoformat())

        anomalies = self.engine.detect_context_bloat_and_loops(hours=24)
        bloat_flags = [a for a in anomalies if a["session_id"] == sid and a["anomaly_type"] == "CONTEXT_BLOAT"]

        self.assertEqual(len(bloat_flags), 1)
        flag = bloat_flags[0]
        self.assertEqual(flag["session_id"], sid)
        self.assertEqual(flag["turn_count"], 4)
        self.assertEqual(flag["peak_input_tokens"], 3200)
        self.assertGreater(flag["avg_growth_rate_pct"], 40.0)
        self.assertIn("/compact", flag["recommended_action"])

    def test_18_detect_context_bloat_ignores_short_sessions(self):
        """Ignores high growth sessions that have fewer than 4 turns."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        sid = "short_sess_3turns"
        self._insert_event("claude", "claude-3-5-sonnet", sid, 1000, 50, (now_dt - datetime.timedelta(minutes=20)).isoformat())
        self._insert_event("claude", "claude-3-5-sonnet", sid, 2000, 50, (now_dt - datetime.timedelta(minutes=10)).isoformat())
        self._insert_event("claude", "claude-3-5-sonnet", sid, 4000, 50, (now_dt - datetime.timedelta(minutes=5)).isoformat())

        anomalies = self.engine.detect_context_bloat_and_loops(hours=24)
        bloat_flags = [a for a in anomalies if a["session_id"] == sid and a["anomaly_type"] == "CONTEXT_BLOAT"]
        self.assertEqual(len(bloat_flags), 0)

    def test_19_detect_context_bloat_ignores_high_output_sessions(self):
        """Ignores sessions where output tokens are >= 20% of input tokens."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        sid = "high_output_healthy_sess"
        # Output is ~30% of input (code generation)
        self._insert_event("claude", "claude-3-5-sonnet", sid, 1000, 300, (now_dt - datetime.timedelta(minutes=40)).isoformat())
        self._insert_event("claude", "claude-3-5-sonnet", sid, 1600, 480, (now_dt - datetime.timedelta(minutes=30)).isoformat())
        self._insert_event("claude", "claude-3-5-sonnet", sid, 2500, 750, (now_dt - datetime.timedelta(minutes=20)).isoformat())
        self._insert_event("claude", "claude-3-5-sonnet", sid, 3800, 1100, (now_dt - datetime.timedelta(minutes=10)).isoformat())

        anomalies = self.engine.detect_context_bloat_and_loops(hours=24)
        bloat_flags = [a for a in anomalies if a["session_id"] == sid and a["anomaly_type"] == "CONTEXT_BLOAT"]
        self.assertEqual(len(bloat_flags), 0)

    def test_20_detect_context_bloat_ignores_low_growth_sessions(self):
        """Ignores sessions with <= 40% turn-over-turn input token growth."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        sid = "steady_compacted_sess"
        # Input grows slowly by ~10%
        self._insert_event("claude", "claude-3-5-sonnet", sid, 2000, 50, (now_dt - datetime.timedelta(minutes=40)).isoformat())
        self._insert_event("claude", "claude-3-5-sonnet", sid, 2200, 50, (now_dt - datetime.timedelta(minutes=30)).isoformat())
        self._insert_event("claude", "claude-3-5-sonnet", sid, 2400, 50, (now_dt - datetime.timedelta(minutes=20)).isoformat())
        self._insert_event("claude", "claude-3-5-sonnet", sid, 2600, 50, (now_dt - datetime.timedelta(minutes=10)).isoformat())

        anomalies = self.engine.detect_context_bloat_and_loops(hours=24)
        bloat_flags = [a for a in anomalies if a["session_id"] == sid and a["anomaly_type"] == "CONTEXT_BLOAT"]
        self.assertEqual(len(bloat_flags), 0)

    def test_21_detect_agent_runaway_loop_positive_flagged(self):
        """Flags AGENT_RUNAWAY_LOOP when >= 8 turns occur in <= 120 seconds."""
        base_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
        sid = "runaway_loop_sess_99"

        # 9 turns spaced 10 seconds apart => 80 seconds total (< 120s)
        for i in range(9):
            rec = (base_dt + datetime.timedelta(seconds=i * 10)).isoformat()
            self._insert_event("claude", "claude-3-5-haiku", sid, 800, 40, rec)

        anomalies = self.engine.detect_context_bloat_and_loops(hours=24)
        loop_flags = [a for a in anomalies if a["session_id"] == sid and a["anomaly_type"] == "AGENT_RUNAWAY_LOOP"]

        self.assertEqual(len(loop_flags), 1)
        flag = loop_flags[0]
        self.assertEqual(flag["session_id"], sid)
        self.assertEqual(flag["anomaly_type"], "AGENT_RUNAWAY_LOOP")
        self.assertEqual(flag["turn_count"], 9)
        self.assertIn("runaway loop", flag["recommended_action"].lower())

    def test_22_detect_agent_runaway_loop_ignores_spaced_turns(self):
        """Ignores 10 turns spaced 30 seconds apart (270s window > 120s)."""
        base_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=20)
        sid = "healthy_spaced_sess"

        for i in range(10):
            rec = (base_dt + datetime.timedelta(seconds=i * 30)).isoformat()
            self._insert_event("claude", "claude-3-5-haiku", sid, 800, 40, rec)

        anomalies = self.engine.detect_context_bloat_and_loops(hours=24)
        loop_flags = [a for a in anomalies if a["session_id"] == sid and a["anomaly_type"] == "AGENT_RUNAWAY_LOOP"]
        self.assertEqual(len(loop_flags), 0)

    def test_23_detect_agent_runaway_loop_ignores_fewer_than_8_turns(self):
        """Ignores 7 rapid turns (threshold requires >= 8)."""
        base_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
        sid = "rapid_subagent_7turns"

        for i in range(7):
            rec = (base_dt + datetime.timedelta(seconds=i * 5)).isoformat()
            self._insert_event("claude", "claude-3-5-haiku", sid, 800, 40, rec)

        anomalies = self.engine.detect_context_bloat_and_loops(hours=24)
        loop_flags = [a for a in anomalies if a["session_id"] == sid and a["anomaly_type"] == "AGENT_RUNAWAY_LOOP"]
        self.assertEqual(len(loop_flags), 0)

    def test_24_multi_session_isolation_bloat_and_loop(self):
        """Correctly isolates bloat, runaway loop, and healthy sessions."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)

        # 1. Bloated session
        for i, tok in enumerate([1000, 1500, 2300, 3500]):
            self._insert_event("claude", "claude-3-5-sonnet", "bloat_sess", tok, 50, (now_dt - datetime.timedelta(minutes=40 - i * 5)).isoformat())

        # 2. Runaway loop session
        for i in range(8):
            self._insert_event("claude", "claude-3-5-haiku", "loop_sess", 500, 20, (now_dt - datetime.timedelta(seconds=60 - i * 5)).isoformat())

        # 3. Normal session (2 turns)
        self._insert_event("claude", "claude-3-5-sonnet", "normal_sess", 1000, 500, (now_dt - datetime.timedelta(minutes=15)).isoformat())
        self._insert_event("claude", "claude-3-5-sonnet", "normal_sess", 1100, 550, (now_dt - datetime.timedelta(minutes=5)).isoformat())

        anomalies = self.engine.detect_context_bloat_and_loops(hours=24)
        flagged_sids = {a["session_id"] for a in anomalies}

        self.assertIn("bloat_sess", flagged_sids)
        self.assertIn("loop_sess", flagged_sids)
        self.assertNotIn("normal_sess", flagged_sids)

    # --- 5. Throughput Engine Integration & Aliases ---

    def test_25_compute_throughput_metrics_includes_pacing_and_anomalies(self):
        """Assert compute_throughput_metrics includes quota_pacing and context_anomalies."""
        res = self.engine.compute_throughput_metrics()
        self.assertIn("quota_pacing", res)
        self.assertIn("context_anomalies", res)
        self.assertIn("tokens_per_minute", res["quota_pacing"])
        self.assertIn("pacing_status", res["quota_pacing"])
        self.assertIsInstance(res["context_anomalies"], list)

    def test_26_compute_capacity_forecast_includes_pacing_and_anomalies(self):
        """Assert compute_capacity_forecast includes quota_pacing and context_anomalies."""
        res = self.engine.compute_capacity_forecast()
        self.assertIn("quota_pacing", res)
        self.assertIn("context_anomalies", res)
        self.assertIn("forecast", res)

    def test_27_throughput_engine_aliases_and_methods(self):
        """Verify ThroughputEngine class alias and method aliases."""
        alias_engine = ThroughputEngine(self.db)
        metrics = alias_engine.get_throughput_metrics()
        forecast = alias_engine.get_exhaustion_forecasts()

        self.assertIn("throughput", {"throughput": metrics})
        self.assertIn("quota_pacing", metrics)
        self.assertIn("quota_pacing", forecast)

    def test_28_capacity_analytics_html_contains_panel_and_preserves_ids(self):
        """Verify capacity_analytics.html contains #capacity-pacing-bloat-panel and preserves all IDs."""
        html_path = Path("frontend/components/capacity_analytics.html")
        self.assertTrue(html_path.exists())
        content = html_path.read_text(encoding="utf-8")

        required_ids = [
            "cap-velocity-val",
            "cap-burst-val",
            "cap-burst-sub",
            "cap-rolling24-val",
            "cap-savings-val",
            "cap-forecast-tbody",
            "cap-recommendations-container",
            "capacity-pacing-bloat-panel",
            "cap-pacing-badge",
            "cap-pacing-burn-rate",
            "cap-pacing-exhaustion",
            "cap-pacing-reset",
            "cap-pacing-session-rem",
            "cap-pacing-weekly-rem",
            "cap-pacing-recommendation",
            "cap-bloat-anomalies-tbody",
        ]

        for elem_id in required_ids:
            self.assertIn(f'id="{elem_id}"', content, f"Missing element ID: {elem_id}")

if __name__ == "__main__":
    unittest.main()
