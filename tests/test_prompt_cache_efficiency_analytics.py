"""
AI Usage Monitor - Prompt Cache Efficiency Analytics & TTL Keep-Alive Test Suite (AIUM-1009)
Zero external dependencies. Python 3 standard library only.
"""

import unittest
import os
import sys
import tempfile
import datetime
import json
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.analytics.cache_analyzer import (
    PromptCacheAnalyzer,
    parse_iso_utc_timestamp,
    ANTHROPIC_CACHE_TTL_SECONDS,
)
from backend.server.http_server import AppHTTPServer


class TestPromptCacheEfficiencyAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_cache_analytics.db")
        cls.db = UsageDatabase(db_path=cls.db_path)
        cls.vault = DPAPIVault(storage_path=os.path.join(cls.temp_dir.name, "vault.json"))
        cls.diagnostics = DiagnosticsEngine()
        cls.diagnostics.clear_errors()

        cls.analyzer = PromptCacheAnalyzer(cls.db)

        cls.server = AppHTTPServer(
            database=cls.db,
            vault=cls.vault,
            diagnostics=cls.diagnostics,
            providers={},
            host="127.0.0.1",
            port=0,
        )
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        # Clean usage_events table prior to each test
        with self.db._lock:
            conn = self.db._get_connection()
            conn.execute("DELETE FROM usage_events;")
            conn.commit()
            conn.close()

    def _record_event(
        self,
        provider: str = "claude",
        model: str = "claude-3-7-sonnet",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        recorded_at: str = None,
        session_id: str = "session-test",
    ):
        now_str = recorded_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.db.record_usage_event(
            provider=provider,
            model=model,
            session_id=session_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            recorded_at=now_str,
        )

    # -------------------------------------------------------------------------
    # 1. Cache Hit Ratio Math
    # -------------------------------------------------------------------------
    def test_01_cache_hit_ratio_zero_denominator(self):
        """Hit ratio is 0.0 when there are no prompt tokens."""
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["total_input_tokens"], 0)
        self.assertEqual(res["total_cache_creation_tokens"], 0)
        self.assertEqual(res["total_cache_read_tokens"], 0)
        self.assertEqual(res["cache_hit_ratio_pct"], 0.0)

    def test_02_cache_hit_ratio_standard_anthropic_distribution(self):
        """75k read, 15k input, 10k write -> 75 / (15 + 10 + 75) = 75.0%."""
        self._record_event(
            input_tokens=15000,
            cache_creation_tokens=10000,
            cache_read_tokens=75000,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["total_input_tokens"], 15000)
        self.assertEqual(res["total_cache_creation_tokens"], 10000)
        self.assertEqual(res["total_cache_read_tokens"], 75000)
        self.assertEqual(res["cache_hit_ratio_pct"], 75.0)

    def test_03_cache_hit_ratio_pure_reads(self):
        """Pure cache reads (no uncached input, no cache creation) yields 100.0%."""
        self._record_event(
            input_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=50000,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["cache_hit_ratio_pct"], 100.0)

    def test_04_cache_hit_ratio_pure_writes(self):
        """Pure cache creation without any cache reads yields 0.0%."""
        self._record_event(
            input_tokens=5000,
            cache_creation_tokens=25000,
            cache_read_tokens=0,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["cache_hit_ratio_pct"], 0.0)

    def test_05_cache_hit_ratio_fractional_rounding(self):
        """Verify 1 decimal place rounding (e.g. 1 read, 2 input = 33.3%)."""
        self._record_event(
            input_tokens=2000,
            cache_creation_tokens=0,
            cache_read_tokens=1000,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["cache_hit_ratio_pct"], 33.3)

    # -------------------------------------------------------------------------
    # 2. Write Surcharge vs Read Savings Math (Claude Sonnet, Opus, Haiku)
    # -------------------------------------------------------------------------
    def test_06_cache_write_surcharge_sonnet_pricing(self):
        """Sonnet ($3.00/M base input): 100k cache writes = 100k * 0.000003 * 0.25 = $0.0750."""
        self._record_event(
            model="claude-3-7-sonnet",
            cache_creation_tokens=100000,
            cache_read_tokens=0,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["cache_write_surcharge_usd"], 0.0750)
        self.assertEqual(res["gross_cache_read_savings_usd"], 0.0)
        self.assertEqual(res["net_cache_savings_usd"], -0.0750)

    def test_07_cache_write_surcharge_opus_pricing(self):
        """Opus ($15.00/M base input): 10k cache writes = 10k * 0.000015 * 0.25 = $0.0375."""
        self._record_event(
            model="claude-3-opus",
            cache_creation_tokens=10000,
            cache_read_tokens=0,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["cache_write_surcharge_usd"], 0.0375)

    def test_08_gross_cache_read_savings_sonnet_pricing(self):
        """Sonnet ($3.00/M base input): 200k cache reads = 200k * 0.000003 * 0.90 = $0.5400."""
        self._record_event(
            model="claude-3-5-sonnet",
            cache_creation_tokens=0,
            cache_read_tokens=200000,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["gross_cache_read_savings_usd"], 0.5400)
        self.assertEqual(res["cache_write_surcharge_usd"], 0.0)
        self.assertEqual(res["net_cache_savings_usd"], 0.5400)

    def test_09_gross_cache_read_savings_haiku_pricing(self):
        """Haiku ($0.80/M base input): 100k cache reads = 100k * 0.0000008 * 0.90 = $0.0720."""
        self._record_event(
            model="claude-3-5-haiku",
            cache_creation_tokens=0,
            cache_read_tokens=100000,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["gross_cache_read_savings_usd"], 0.0720)

    def test_10_net_cache_savings_calculation(self):
        """Sonnet: 100k writes ($0.0750) and 200k reads ($0.5400) -> Net = $0.4650."""
        self._record_event(
            model="claude-3-7-sonnet",
            cache_creation_tokens=100000,
            cache_read_tokens=200000,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["cache_write_surcharge_usd"], 0.0750)
        self.assertEqual(res["gross_cache_read_savings_usd"], 0.5400)
        self.assertEqual(res["net_cache_savings_usd"], 0.4650)

    def test_11_net_cache_savings_negative_when_writes_dominate(self):
        """Sonnet: 100k writes ($0.0750 surcharge) and 10k reads ($0.0270 savings) -> Net -$0.0480."""
        self._record_event(
            model="claude-3-7-sonnet",
            cache_creation_tokens=100000,
            cache_read_tokens=10000,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["net_cache_savings_usd"], -0.0480)

    # -------------------------------------------------------------------------
    # 3. Break-Even Detection
    # -------------------------------------------------------------------------
    def test_12_break_even_achieved_true_when_net_savings_positive(self):
        """Positive net savings and cache read tokens > 0 triggers break_even_achieved = True."""
        self._record_event(
            cache_creation_tokens=10000,
            cache_read_tokens=50000,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertTrue(res["break_even_achieved"])

    def test_13_break_even_achieved_false_when_zero_reads(self):
        """Zero cache reads (even with 0 writes and $0.0 net savings) yields break_even_achieved = False."""
        self._record_event(
            input_tokens=1000,
            cache_creation_tokens=0,
            cache_read_tokens=0,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertFalse(res["break_even_achieved"])

    def test_14_break_even_achieved_false_when_negative_net_savings(self):
        """When write surcharge exceeds read savings, break_even_achieved is False."""
        self._record_event(
            cache_creation_tokens=100000,
            cache_read_tokens=1000,
        )
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertFalse(res["break_even_achieved"])

    # -------------------------------------------------------------------------
    # 4. Efficiency Grading Scale
    # -------------------------------------------------------------------------
    def test_15_efficiency_grade_a_plus(self):
        """Hit ratio >= 75% receives grade 'A+'."""
        self._record_event(input_tokens=2500, cache_read_tokens=7500)
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["efficiency_grade"], "A+")

    def test_16_efficiency_grade_a(self):
        """Hit ratio in [50%, 75%) receives grade 'A'."""
        self._record_event(input_tokens=4000, cache_read_tokens=6000)
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["efficiency_grade"], "A")

    def test_17_efficiency_grade_b(self):
        """Hit ratio in [25%, 50%) receives grade 'B'."""
        self._record_event(input_tokens=7000, cache_read_tokens=3000)
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["efficiency_grade"], "B")

    def test_18_efficiency_grade_c(self):
        """Hit ratio in (0%, 25%) receives grade 'C'."""
        self._record_event(input_tokens=9000, cache_read_tokens=1000)
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["efficiency_grade"], "C")

    def test_19_efficiency_grade_na(self):
        """Hit ratio == 0% receives grade 'N/A'."""
        self._record_event(input_tokens=10000, cache_read_tokens=0)
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        self.assertEqual(res["efficiency_grade"], "N/A")

    # -------------------------------------------------------------------------
    # 5. Ephemeral 300s TTL Countdown & Keep-Alive Status
    # -------------------------------------------------------------------------
    def test_20_ttl_status_no_cache_activity(self):
        """No cache creation or read events yields is_warm=False, 0s TTL."""
        self._record_event(input_tokens=5000, cache_creation_tokens=0, cache_read_tokens=0)
        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24)
        ttl = res["ttl_status"]
        self.assertFalse(ttl["is_warm"])
        self.assertEqual(ttl["ttl_remaining_seconds"], 0)
        self.assertEqual(ttl["ttl_formatted"], "0m 0s")
        self.assertIsNone(ttl["last_touch_utc"])

    def test_21_ttl_status_active_warm_cache(self):
        """Event touched 60 seconds ago has 240s remaining (4m 0s) and is warm."""
        ref_now = datetime.datetime(2026, 11, 7, 16, 0, 0, tzinfo=datetime.timezone.utc)
        touch_ts = (ref_now - datetime.timedelta(seconds=60)).isoformat()
        self._record_event(cache_read_tokens=1000, recorded_at=touch_ts)

        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24, now=ref_now)
        ttl = res["ttl_status"]
        self.assertTrue(ttl["is_warm"])
        self.assertEqual(ttl["ttl_remaining_seconds"], 240)
        self.assertEqual(ttl["ttl_formatted"], "4m 0s")
        self.assertEqual(ttl["last_touch_utc"], touch_ts)

    def test_22_ttl_status_expired_cold_cache(self):
        """Event touched 350 seconds ago (>300s) is expired cold (0s TTL, is_warm=False)."""
        ref_now = datetime.datetime(2026, 11, 7, 16, 0, 0, tzinfo=datetime.timezone.utc)
        touch_ts = (ref_now - datetime.timedelta(seconds=350)).isoformat()
        self._record_event(cache_creation_tokens=5000, recorded_at=touch_ts)

        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24, now=ref_now)
        ttl = res["ttl_status"]
        self.assertFalse(ttl["is_warm"])
        self.assertEqual(ttl["ttl_remaining_seconds"], 0)
        self.assertEqual(ttl["ttl_formatted"], "0m 0s")

    def test_23_ttl_status_exact_300s_boundary(self):
        """Event touched exactly 300 seconds ago has 0s remaining and is no longer warm."""
        ref_now = datetime.datetime(2026, 11, 7, 16, 0, 0, tzinfo=datetime.timezone.utc)
        touch_ts = (ref_now - datetime.timedelta(seconds=ANTHROPIC_CACHE_TTL_SECONDS)).isoformat()
        self._record_event(cache_read_tokens=2000, recorded_at=touch_ts)

        res = self.analyzer.analyze_cache_efficiency(provider="claude", hours=24, now=ref_now)
        ttl = res["ttl_status"]
        self.assertEqual(ttl["ttl_remaining_seconds"], 0)
        self.assertFalse(ttl["is_warm"])

    # -------------------------------------------------------------------------
    # 6. Session Cache Enrichment
    # -------------------------------------------------------------------------
    def test_24_enrich_session_cache_metrics_adds_required_fields(self):
        """enrich_session_cache_metrics adds cache_hit_ratio_pct, net_cache_savings_usd, and cache_badge_label."""
        raw_session = {
            "session_id": "ses-abc",
            "provider": "claude",
            "model": "claude-3-7-sonnet",
            "input_tokens": 15000,
            "cache_creation_tokens": 10000,
            "cache_read_tokens": 75000,
        }
        enriched = self.analyzer.enrich_session_cache_metrics(raw_session)
        self.assertEqual(enriched["cache_hit_ratio_pct"], 75.0)
        self.assertEqual(enriched["cache_badge_label"], "Optimal (A+)")
        self.assertEqual(enriched["net_cache_savings_usd"], 0.1950)

    def test_25_enrich_session_cache_metrics_badge_labels(self):
        """Verifies badge label mappings across hit ratio tiers."""
        # No Cache
        s0 = {"input_tokens": 1000, "cache_creation_tokens": 0, "cache_read_tokens": 0}
        self.assertEqual(self.analyzer.enrich_session_cache_metrics(s0)["cache_badge_label"], "No Cache")

        # Warmup (Creation only, 0 reads)
        s_warm = {"input_tokens": 1000, "cache_creation_tokens": 5000, "cache_read_tokens": 0}
        self.assertEqual(self.analyzer.enrich_session_cache_metrics(s_warm)["cache_badge_label"], "Warmup")

        # High (A)
        s_a = {"input_tokens": 4000, "cache_creation_tokens": 0, "cache_read_tokens": 6000}
        self.assertEqual(self.analyzer.enrich_session_cache_metrics(s_a)["cache_badge_label"], "High (A)")

        # Moderate (B)
        s_b = {"input_tokens": 7000, "cache_creation_tokens": 0, "cache_read_tokens": 3000}
        self.assertEqual(self.analyzer.enrich_session_cache_metrics(s_b)["cache_badge_label"], "Moderate (B)")

        # Low (C)
        s_c = {"input_tokens": 9000, "cache_creation_tokens": 0, "cache_read_tokens": 1000}
        self.assertEqual(self.analyzer.enrich_session_cache_metrics(s_c)["cache_badge_label"], "Low (C)")

    # -------------------------------------------------------------------------
    # 7. Live REST API Verification: GET /api/analytics/cache-efficiency
    # -------------------------------------------------------------------------
    def test_26_api_analytics_cache_efficiency_http_endpoint(self):
        """GET /api/analytics/cache-efficiency returns 200 JSON with complete efficiency metrics schema."""
        self._record_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=15000,
            cache_creation_tokens=10000,
            cache_read_tokens=75000,
        )
        port = self.server.server_port
        url = f"http://127.0.0.1:{port}/api/analytics/cache-efficiency"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))

        self.assertEqual(data["provider"], "claude")
        self.assertEqual(data["total_input_tokens"], 15000)
        self.assertEqual(data["total_cache_creation_tokens"], 10000)
        self.assertEqual(data["total_cache_read_tokens"], 75000)
        self.assertEqual(data["cache_hit_ratio_pct"], 75.0)
        self.assertEqual(data["efficiency_grade"], "A+")
        self.assertTrue(data["break_even_achieved"])
        self.assertIn("ttl_status", data)
        self.assertIn("is_warm", data["ttl_status"])

    def test_27_api_analytics_cache_efficiency_query_params(self):
        """GET /api/analytics/cache-efficiency respects provider and hours query parameters."""
        now = datetime.datetime.now(datetime.timezone.utc)
        # Claude event 2 hours ago
        self._record_event(
            provider="claude",
            cache_read_tokens=20000,
            recorded_at=(now - datetime.timedelta(hours=2)).isoformat(),
        )
        # Claude event 40 hours ago (outside 24h window)
        self._record_event(
            provider="claude",
            cache_read_tokens=50000,
            recorded_at=(now - datetime.timedelta(hours=40)).isoformat(),
        )
        # Gemini event
        self._record_event(
            provider="gemini",
            cache_read_tokens=30000,
            recorded_at=(now - datetime.timedelta(hours=1)).isoformat(),
        )

        port = self.server.server_port
        url = f"http://127.0.0.1:{port}/api/analytics/cache-efficiency?provider=claude&hours=24"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total_cache_read_tokens"], 20000)
            self.assertEqual(data["event_count"], 1)

    # -------------------------------------------------------------------------
    # 8. Frontend HTML Components Markup & DOM ID Invariant Assertions
    # -------------------------------------------------------------------------
    def test_28_frontend_components_contain_cache_efficiency_banner_and_metrics(self):
        """Verifies session_timeline.html and usage_gauge_card.html contain #cache-efficiency-banner and required columns."""
        timeline_html = (REPO_ROOT / "frontend" / "components" / "session_timeline.html").read_text(encoding="utf-8")
        gauge_html = (REPO_ROOT / "frontend" / "components" / "usage_gauge_card.html").read_text(encoding="utf-8")

        # 1. cache-efficiency-banner presence in both components
        self.assertIn('id="cache-efficiency-banner"', timeline_html)
        self.assertIn('id="cache-efficiency-banner"', gauge_html)

        # 2. Session table columns and sorting icons
        self.assertIn("Cache Read", timeline_html)
        self.assertIn("Cache Write", timeline_html)
        self.assertIn("Net Savings", timeline_html)
        self.assertIn('id="sort-icon-cache_read_tokens"', timeline_html)
        self.assertIn('id="sort-icon-cache_creation_tokens"', timeline_html)
        self.assertIn('id="sort-icon-net_cache_savings_usd"', timeline_html)

        # 3. Cache metrics legend
        self.assertIn("session-cache-legend", timeline_html)
        self.assertIn("0.10x cost", timeline_html)
        self.assertIn("1.25x cost", timeline_html)

        # 4. Gauge card metrics
        self.assertIn('id="val-cache-hit-ratio"', gauge_html)
        self.assertIn('id="val-cache-ttl-remaining"', gauge_html)
        self.assertIn('id="val-cache-net-savings"', gauge_html)


if __name__ == "__main__":
    unittest.main()
