import datetime
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from backend.server.http_server import AppHTTPRequestHandler
from backend.storage.database import UsageDatabase

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestHierarchicalTrendsBucketModeLocalTimeAlignment(unittest.TestCase):
    """
    Unit test suite for AIUM-907:
    Aligning Hierarchical Trend Curves with Token Velocity Granularity, Mode, and Workstation Local Time.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_aium_907.db")
        self.db = UsageDatabase(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # ------------------------------------------------------------------
    # 1. Dynamic Bucket Granularity in get_hierarchical_trends
    # ------------------------------------------------------------------

    def test_01_hierarchical_trends_supports_5m_buckets(self):
        """Verifies 24h window with 5m bucket returns 288 continuous bins."""
        res = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=5)
        self.assertEqual(res["window"], "24h")
        self.assertEqual(res["bucket_minutes"], 5)
        self.assertEqual(len(res["labels"]), 288)
        self.assertEqual(len(res["keys"]), 288)
        for s in res["series"]:
            self.assertEqual(len(s["points"]), 288)

    def test_02_hierarchical_trends_supports_1m_buckets(self):
        """Verifies 24h window with 1m bucket returns 1440 continuous bins."""
        res = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=1)
        self.assertEqual(res["bucket_minutes"], 1)
        self.assertEqual(len(res["labels"]), 1440)
        self.assertEqual(len(res["keys"]), 1440)

    def test_03_hierarchical_trends_supports_15m_buckets(self):
        """Verifies 24h window with 15m bucket returns 96 continuous bins."""
        res = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=15)
        self.assertEqual(res["bucket_minutes"], 15)
        self.assertEqual(len(res["labels"]), 96)

    def test_04_hierarchical_trends_supports_30m_buckets(self):
        """Verifies 24h window with 30m bucket returns 48 continuous bins."""
        res = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=30)
        self.assertEqual(res["bucket_minutes"], 30)
        self.assertEqual(len(res["labels"]), 48)

    def test_05_hierarchical_trends_supports_60m_buckets(self):
        """Verifies 24h window with 60m bucket returns 24 continuous bins."""
        res = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=60)
        self.assertEqual(res["bucket_minutes"], 60)
        self.assertEqual(len(res["labels"]), 24)

    def test_06_hierarchical_trends_rejects_invalid_bucket_falls_back_to_default(self):
        """Verifies invalid bucket_minutes (e.g. 7, 99) falls back safely to window default."""
        res = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=99)
        self.assertEqual(res["bucket_minutes"], 60)
        self.assertEqual(len(res["labels"]), 24)

    def test_07_hierarchical_trends_payload_includes_bucket_and_mode(self):
        """Verifies payload explicitly returns bucket_minutes and mode fields."""
        res = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=10, mode="interval_delta")
        self.assertIn("bucket_minutes", res)
        self.assertIn("mode", res)
        self.assertEqual(res["bucket_minutes"], 10)
        self.assertEqual(res["mode"], "interval_delta")

    # ------------------------------------------------------------------
    # 2. Cumulative Mode vs Delta Bursts
    # ------------------------------------------------------------------

    def test_08_hierarchical_trends_cumulative_mode_is_monotonically_non_decreasing(self):
        """Verifies cumulative mode sums running totals monotonically across all series."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            user_name="James",
            team_name="Claude Pro",
            input_tokens=1000,
            output_tokens=500,
            recorded_at=(now - datetime.timedelta(minutes=60)).isoformat()
        )
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            user_name="James",
            team_name="Claude Pro",
            input_tokens=2000,
            output_tokens=1000,
            recorded_at=(now - datetime.timedelta(minutes=10)).isoformat()
        )

        res_cum = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=5, mode="cumulative")
        self.assertEqual(res_cum["mode"], "cumulative")

        for s in res_cum["series"]:
            pts = s["points"]
            self.assertEqual(len(pts), 288)
            # Verify monotonically non-decreasing
            for i in range(1, len(pts)):
                self.assertGreaterEqual(pts[i], pts[i - 1], f"Cumulative point decreased at index {i} in series {s['id']}")

    def test_09_hierarchical_trends_delta_mode_has_idle_zeroes(self):
        """Verifies interval_delta mode preserves idle 0 baseline for intervals without activity."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            user_name="James",
            team_name="Claude Pro",
            input_tokens=1000,
            output_tokens=500,
            recorded_at=(now - datetime.timedelta(minutes=2)).isoformat()
        )

        res_delta = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=5, mode="interval_delta")
        total_series = next(s for s in res_delta["series"] if s["id"] == "claude_total")
        pts = total_series["points"]
        # The early bins must be 0
        self.assertEqual(pts[0], 0)
        # The last bin must have the burst
        self.assertGreater(pts[-1], 0)

    # ------------------------------------------------------------------
    # 3. Canonical ISO Keys & Workstation Local Time Labels
    # ------------------------------------------------------------------

    def test_10_hierarchical_trends_keys_are_canonical_iso_with_minutes(self):
        """Verifies keys always include minute precision (%Y-%m-%dT%H:%M) for valid JS Date parsing."""
        res = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=5)
        for k in res["keys"]:
            self.assertTrue(
                re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", k),
                f"Key '{k}' does not match canonical %Y-%m-%dT%H:%M format"
            )

    def test_11_hierarchical_trends_labels_are_workstation_local_time(self):
        """Verifies labels are generated in local timezone matching now.astimezone()."""
        now_local = datetime.datetime.now(datetime.timezone.utc).astimezone()
        res = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=5)
        last_label = res["labels"][-1]
        expected_hour = now_local.strftime("%H")
        self.assertTrue(
            last_label.startswith(expected_hour),
            f"Expected last label to start with local hour '{expected_hour}', got '{last_label}'"
        )

    # ------------------------------------------------------------------
    # 4. Multi-Series Disaggregation Under Granular Buckets
    # ------------------------------------------------------------------

    def test_12_claude_pro_disaggregation_preserved_under_5m_buckets(self):
        """Verifies personal Pro vs team pool disaggregation holds under granular 5m buckets."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            user_name="James",
            team_name="Claude Pro",
            input_tokens=5000,
            output_tokens=2000,
            recorded_at=now.isoformat()
        )

        res = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=5)
        ind_s = next(s for s in res["series"] if s["id"] == "claude_individual")
        team_s = next(s for s in res["series"] if s["id"] == "claude_team")

        self.assertEqual(ind_s["total_tokens"], 7000)
        self.assertNotEqual(team_s["total_tokens"], ind_s["total_tokens"])

    def test_13_ollama_model_disaggregation_under_5m_buckets(self):
        """Verifies Ollama models and locality disaggregate properly under 5m buckets."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.db.record_usage_event(
            provider="ollama",
            model="nomic-embed-text:latest",
            input_tokens=12000,
            output_tokens=0,
            recorded_at=now.isoformat()
        )

        res = self.db.get_hierarchical_trends(provider="ollama", window="24h", bucket_minutes=5)
        model_s = next(s for s in res["series"] if s["id"] == "ollama_model_nomic-embed-text_latest")
        self.assertEqual(model_s["total_tokens"], 12000)
        self.assertEqual(len(model_s["points"]), 288)

    # ------------------------------------------------------------------
    # 5. HTTP API Verification
    # ------------------------------------------------------------------

    def test_14_http_api_trends_hierarchy_forwards_bucket_minutes(self):
        """Verifies GET /api/usage/trends/hierarchy handles bucket_minutes=5 query param."""
        handler = AppHTTPRequestHandler.__new__(AppHTTPRequestHandler)
        handler.server = MagicMock()
        handler.server.database = self.db
        handler._send_json = MagicMock()
        handler._send_error = MagicMock()

        handler._handle_api_get("/api/usage/trends/hierarchy", {
            "provider": ["claude"],
            "window": ["24h"],
            "bucket_minutes": ["5"],
            "mode": ["interval_delta"]
        })

        handler._send_json.assert_called_once()
        status, payload = handler._send_json.call_args[0]
        self.assertEqual(status, 200)
        self.assertEqual(payload["bucket_minutes"], 5)
        self.assertEqual(len(payload["labels"]), 288)

    def test_15_http_api_trends_hierarchy_forwards_cumulative_mode(self):
        """Verifies GET /api/usage/trends/hierarchy handles mode=cumulative query param."""
        handler = AppHTTPRequestHandler.__new__(AppHTTPRequestHandler)
        handler.server = MagicMock()
        handler.server.database = self.db
        handler._send_json = MagicMock()
        handler._send_error = MagicMock()

        handler._handle_api_get("/api/usage/trends/hierarchy", {
            "provider": ["claude"],
            "window": ["24h"],
            "bucket_minutes": ["15"],
            "mode": ["cumulative"]
        })

        handler._send_json.assert_called_once()
        status, payload = handler._send_json.call_args[0]
        self.assertEqual(status, 200)
        self.assertEqual(payload["mode"], "cumulative")
        self.assertEqual(payload["bucket_minutes"], 15)
        self.assertEqual(len(payload["labels"]), 96)

    # ------------------------------------------------------------------
    # 6. Frontend Alignment Verification
    # ------------------------------------------------------------------

    def test_16_frontend_app_js_passes_bucket_minutes_and_mode_to_hierarchy_api(self):
        """Verifies app.js loadAndRenderHierarchicalTrendChart includes bucket_minutes and mode."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("bucket_minutes=${bucketMinutes}", app_js)
        self.assertIn("mode=${mode}", app_js)

    def test_17_frontend_app_js_includes_bucket_and_mode_in_cache_key(self):
        """Verifies hierarchical trend cacheKey incorporates bucket_minutes and mode."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("const cacheKey = `${providerKey}_${windowPeriod}_${bucketMinutes}_${mode}_${scope}`;", app_js)

    def test_18_frontend_format_local_time_handles_hours_without_minutes(self):
        """Verifies formatLocalTime normalizes YYYY-MM-DDTHH strings by appending :00."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/^\\d{4}-\\d{2}-\\d{2}T\\d{2}$/.test(s)", app_js)
        self.assertIn("s += \":00\";", app_js)

    def test_19_frontend_trend_chart_renders_window_bucket_and_mode_badges(self):
        """Verifies renderMultiSeriesTrendChart legend strip displays Window, Bucket, and Mode badges."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Window: ${(trendsData.window || this.trendWindow || \"24h\").toUpperCase()}", app_js)
        self.assertIn("Bucket: ${trendsData.bucket_minutes || this.chartGranularity || 5}m", app_js)
        self.assertIn("${(trendsData.mode || this.chartMode) === 'cumulative' ? 'Cumulative Run' : 'Delta Bursts'}", app_js)

    def test_20_frontend_granularity_and_mode_changes_invalidate_hierarchical_cache(self):
        """Verifies changeChartGranularity and changeChartMode clear cachedHierarchicalTrends."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        # In changeChartGranularity
        p_gran = r"changeChartGranularity\(val\)\s*\{[^}]+this\.cachedHierarchicalTrends\s*=\s*\{\};"
        self.assertTrue(re.search(p_gran, app_js, re.DOTALL), "changeChartGranularity must clear cachedHierarchicalTrends")
        # In changeChartMode
        p_mode = r"changeChartMode\(mode\)\s*\{[^}]+this\.cachedHierarchicalTrends\s*=\s*\{\};"
        self.assertTrue(re.search(p_mode, app_js, re.DOTALL), "changeChartMode must clear cachedHierarchicalTrends")


if __name__ == "__main__":
    unittest.main()
