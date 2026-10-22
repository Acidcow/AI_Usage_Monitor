import os
import tempfile
import unittest
from pathlib import Path

from backend.storage.database import UsageDatabase
from backend.tray.native_widget import NativeTaskbarWidget


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestWindowSyncAndDynamicReportsGrid(unittest.TestCase):
    """Unit test suite for AIUM-903:
    1. 15 Granular Time-Span Window Options & Bidirectional Web UI <-> Mini Widget Sync
    2. Historical Usage Reports & Cost Attribution Grid Overhaul:
       - All filterable attribution columns populated and displayed per row
       - Column visibility customization (show/hide)
       - Multi-column grouping with Group Subtotal line-items at end of each group
       - Drag-and-Drop column sequence reordering (left-to-right)
       - Local model negative 'Est. Cost' in parentheses with alternate color (estimated savings)
    """

    EXPECTED_WINDOWS = [
        "1h", "3h", "6h", "12h", "24h", "48h",
        "3d", "5d", "7d", "10d", "15d", "30d",
        "3m", "6m", "12m"
    ]

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_aium_903.db")
        self.db = UsageDatabase(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # ------------------------------------------------------------------
    # 1. Backend Time-Span Window Coverage (15 Windows)
    # ------------------------------------------------------------------

    def test_01_granular_timeseries_supports_all_15_windows(self):
        self.db.record_usage_event(
            provider="claude",
            input_tokens=1500,
            output_tokens=500,
            estimated_cost=0.015,
            model="claude-3-7-sonnet",
            source="proxy",
        )
        for win in self.EXPECTED_WINDOWS:
            res = self.db.get_granular_timeseries(window=win, bucket_minutes=5, mode="interval_delta")
            self.assertEqual(res["window"], win)
            self.assertGreater(len(res["labels"]), 0)
            self.assertIn("series", res)
            series_keys = [s["key"] for s in res["series"]]
            self.assertIn("claude", series_keys)

    def test_02_hierarchical_trends_supports_all_15_windows(self):
        self.db.record_usage_event(
            provider="gemini",
            input_tokens=2000,
            output_tokens=1000,
            estimated_cost=0.01,
            model="gemini-2.5-pro",
            source="api",
        )
        for win in self.EXPECTED_WINDOWS:
            res = self.db.get_hierarchical_trends(provider="gemini", window=win, scope="individual")
            self.assertEqual(res["window"], win)
            self.assertTrue(len(res["labels"]) >= 6)
            self.assertTrue(len(res["series"]) >= 1)

    def test_03_pivot_metrics_supports_all_15_windows(self):
        self.db.record_usage_event(
            provider="claude",
            input_tokens=800,
            output_tokens=400,
            estimated_cost=0.009,
            model="claude-3-7-sonnet",
            source="ide",
        )
        for win in self.EXPECTED_WINDOWS:
            res = self.db.get_pivot_metrics(dimensions=["platform", "model"], window=win)
            self.assertEqual(res["window"], win)
            self.assertGreaterEqual(len(res["rows"]), 1)

    def test_04_adaptive_bucket_scaling_prevents_excessive_buckets_on_long_windows(self):
        for win in ["30d", "3m", "6m", "12m"]:
            res = self.db.get_granular_timeseries(window=win, bucket_minutes=1)
            self.assertLessEqual(
                len(res["labels"]),
                200,
                f"Window {win} produced too many buckets ({len(res['labels'])})",
            )

    # ------------------------------------------------------------------
    # 2. Bidirectional Settings Sync (Web UI <-> Mini Widget)
    # ------------------------------------------------------------------

    def test_05_database_settings_default_and_roundtrip_for_window_sync(self):
        defaults = self.db.get_all_settings()
        self.assertIn("active_trend_window", defaults)
        self.assertIn("default_trend_window", defaults)
        self.assertIn("active_chart_granularity", defaults)
        self.assertIn("active_chart_mode", defaults)

        self.db.set_setting("active_trend_window", "15d")
        self.db.set_setting("default_trend_window", "15d")
        self.db.set_setting("active_chart_granularity", 15)
        self.db.set_setting("active_chart_mode", "cumulative")
        self.db.set_setting("widget_view_mode", "trends")

        updated = self.db.get_all_settings()
        self.assertEqual(updated["active_trend_window"], "15d")
        self.assertEqual(updated["default_trend_window"], "15d")
        self.assertEqual(updated["active_chart_granularity"], 15)
        self.assertEqual(updated["active_chart_mode"], "cumulative")
        self.assertEqual(updated["widget_view_mode"], "trends")

    def test_06_native_taskbar_widget_defines_all_15_window_options_and_sync_methods(self):
        codes = [item[0] if isinstance(item, tuple) else item for item in NativeTaskbarWidget.WINDOW_OPTIONS]
        for win in self.EXPECTED_WINDOWS:
            self.assertIn(win, codes, f"NativeTaskbarWidget missing window option {win}")
        self.assertTrue(hasattr(NativeTaskbarWidget, "set_trend_window"))
        self.assertTrue(hasattr(NativeTaskbarWidget, "cycle_trend_window"))
        self.assertTrue(hasattr(NativeTaskbarWidget, "_show_window_menu"))

    def test_07_html_mini_widget_and_js_have_all_15_windows_and_bidirectional_sync(self):
        widget_html = (PROJECT_ROOT / "frontend" / "mini_widget.html").read_text(encoding="utf-8")
        widget_js = (PROJECT_ROOT / "frontend" / "js" / "widget.js").read_text(encoding="utf-8")

        self.assertIn('id="w-window-select"', widget_html)
        for win in self.EXPECTED_WINDOWS:
            self.assertIn(f'value="{win}"', widget_html)

        self.assertIn("setTrendWindow(", widget_js)
        self.assertIn("active_trend_window", widget_js)
        self.assertIn("/api/usage/timeseries?window=", widget_js)

    def test_08_web_ui_usage_gauge_card_and_settings_panel_have_all_15_windows(self):
        gauge_html = (PROJECT_ROOT / "frontend" / "components" / "usage_gauge_card.html").read_text(encoding="utf-8")
        settings_html = (PROJECT_ROOT / "frontend" / "components" / "settings_panel.html").read_text(encoding="utf-8")

        for win in self.EXPECTED_WINDOWS:
            self.assertIn(f'value="{win}"', gauge_html, f"usage_gauge_card.html missing {win}")
            self.assertIn(f'value="{win}"', settings_html, f"settings_panel.html missing {win}")
        self.assertIn('id="cfg-default-trend-window"', settings_html)

    # ------------------------------------------------------------------
    # 3. Historical Report Full Attribution Columns & Local Model Negative Cost
    # ------------------------------------------------------------------

    def test_09_historical_report_populates_all_filter_attribution_columns(self):
        self.db.record_usage_event(
            provider="claude",
            input_tokens=4000,
            output_tokens=2000,
            cache_creation_tokens=500,
            cache_read_tokens=1500,
            estimated_cost=0.042,
            account_id="acct-enterprise-01",
            team_name="Platform-Eng",
            user_name="james@example.com",
            model="claude-3-7-sonnet",
            source="proxy-bridge",
            instance_id="node-workstation-1",
            client_ip="192.168.1.50",
            project_id="proj-alpha",
        )
        rep = self.db.query_historical_report(group_by="day")
        self.assertGreaterEqual(len(rep["rows"]), 1)
        row = rep["rows"][0]

        required_cols = [
            "period", "provider", "account_id", "group_key", "source",
            "model", "instance_id", "client_ip", "client_alias",
            "team_name", "user_name", "project_id",
            "event_count", "input_tokens", "output_tokens",
            "cache_creation_tokens", "cache_read_tokens", "total_tokens",
            "estimated_cost", "estimated_savings_usd", "net_cost_usd", "is_local_model",
        ]
        for col in required_cols:
            self.assertIn(col, row, f"Historical report row missing column '{col}'")

        self.assertEqual(row["provider"], "claude")
        self.assertEqual(row["account_id"], "acct-enterprise-01")
        self.assertEqual(row["team_name"], "Platform-Eng")
        self.assertEqual(row["user_name"], "james@example.com")
        self.assertEqual(row["model"], "claude-3-7-sonnet")
        self.assertEqual(row["source"], "proxy-bridge")
        self.assertEqual(row["instance_id"], "node-workstation-1")
        self.assertEqual(row["client_ip"], "192.168.1.50")
        self.assertEqual(row["project_id"], "proj-alpha")
        self.assertFalse(row["is_local_model"])
        self.assertGreater(row["net_cost_usd"], 0)

    def test_10_historical_report_local_model_computes_negative_net_cost_and_savings(self):
        # 500,000 total tokens on local Ollama -> $3.00 estimated savings at $6.00/1M frontier benchmark
        self.db.record_usage_event(
            provider="ollama",
            input_tokens=300000,
            output_tokens=200000,
            estimated_cost=0.0,
            account_id="local-gpu",
            team_name="Local-AI",
            user_name="james",
            model="qwen2.5-coder:32b",
            source="ollama-bridge",
            instance_id="rtx-4090-node",
            client_ip="127.0.0.1",
        )
        rep = self.db.query_historical_report(group_by="day", provider="ollama")
        self.assertEqual(len(rep["rows"]), 1)
        row = rep["rows"][0]

        self.assertTrue(row["is_local_model"])
        self.assertAlmostEqual(row["estimated_cost"], 0.0, places=4)
        self.assertAlmostEqual(row["estimated_savings_usd"], 3.0, places=4)
        self.assertAlmostEqual(row["net_cost_usd"], -3.0, places=4)

        summary = rep["summary"]
        self.assertAlmostEqual(summary["total_estimated_cost"], 0.0, places=4)
        self.assertAlmostEqual(summary["total_estimated_savings_usd"], 3.0, places=4)
        self.assertAlmostEqual(summary["net_cost_usd"], -3.0, places=4)

    def test_11_historical_report_mixed_cloud_and_local_rows_separate_properly(self):
        self.db.record_usage_event(
            provider="claude",
            input_tokens=100000,
            output_tokens=50000,
            estimated_cost=1.25,
            model="claude-3-7-sonnet",
            source="api",
        )
        self.db.record_usage_event(
            provider="ollama",
            input_tokens=100000,
            output_tokens=100000,
            estimated_cost=0.0,
            model="llama3.3:70b",
            source="ollama-local",
        )
        rep = self.db.query_historical_report(group_by="day")
        self.assertEqual(len(rep["rows"]), 2)
        by_prov = {r["provider"]: r for r in rep["rows"]}
        self.assertIn("claude", by_prov)
        self.assertIn("ollama", by_prov)
        self.assertGreater(by_prov["claude"]["net_cost_usd"], 0)
        self.assertLess(by_prov["ollama"]["net_cost_usd"], 0)
        self.assertGreater(rep["summary"]["total_estimated_savings_usd"], 0)

    def test_12_historical_report_sorting_by_net_cost_and_provider_columns(self):
        self.db.record_usage_event(
            provider="claude",
            input_tokens=50000,
            output_tokens=50000,
            estimated_cost=0.90,
            model="claude-3-7-sonnet",
        )
        self.db.record_usage_event(
            provider="ollama",
            input_tokens=200000,
            output_tokens=200000,
            estimated_cost=0.0,
            model="deepseek-r1:32b",
        )
        rep_asc = self.db.query_historical_report(group_by="day", sort_by="net_cost_usd", sort_dir="asc")
        self.assertEqual(rep_asc["rows"][0]["provider"], "ollama")
        rep_desc = self.db.query_historical_report(group_by="day", sort_by="net_cost_usd", sort_dir="desc")
        self.assertEqual(rep_desc["rows"][0]["provider"], "claude")

    def test_13_historical_report_sub_day_iso_timestamp_filter_works(self):
        self.db.record_usage_event(
            provider="gemini",
            input_tokens=1200,
            output_tokens=800,
            estimated_cost=0.005,
            model="gemini-2.5-flash",
        )
        from datetime import datetime, timedelta, timezone
        cutoff_3h = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        rep = self.db.query_historical_report(group_by="hour", start_date=cutoff_3h)
        self.assertGreaterEqual(len(rep["rows"]), 1)

    # ------------------------------------------------------------------
    # 4. Frontend Reports Panel & Dynamic Grid Capabilities
    # ------------------------------------------------------------------

    def test_14_reports_panel_html_contains_all_15_windows_and_grid_customizer(self):
        reports_html = (PROJECT_ROOT / "frontend" / "components" / "reports_panel.html").read_text(encoding="utf-8")
        for win in self.EXPECTED_WINDOWS:
            self.assertIn(f'value="{win}"', reports_html, f"reports_panel.html missing window {win}")
        self.assertIn('id="reports-grid-customizer"', reports_html)
        self.assertIn('id="reports-groupby-chips"', reports_html)
        self.assertIn('id="reports-group-totals-chk"', reports_html)
        self.assertIn('id="reports-column-sequence-chips"', reports_html)
        self.assertIn('id="reports-table-head-row"', reports_html)
        self.assertIn('id="rep-tot-savings"', reports_html)

    def test_15_app_js_defines_all_20_report_columns_matching_filters(self):
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        expected_col_keys = [
            "key: 'period'",
            "key: 'provider'",
            "key: 'account_id'",
            "key: 'group_key'",
            "key: 'source'",
            "key: 'model'",
            "key: 'instance_id'",
            "key: 'client_ip'",
            "key: 'team_name'",
            "key: 'user_name'",
            "key: 'project_id'",
            "key: 'event_count'",
            "key: 'input_tokens'",
            "key: 'output_tokens'",
            "key: 'cache_creation_tokens'",
            "key: 'cache_read_tokens'",
            "key: 'total_tokens'",
            "key: 'net_cost_usd'",
            "key: 'cost_per_1k'",
            "key: 'share'",
        ]
        for key_expr in expected_col_keys:
            self.assertIn(key_expr, app_js, f"app.js getDefaultReportColumns missing {key_expr}")

    def test_16_app_js_implements_column_visibility_and_reset_controls(self):
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("toggleReportColumnVisibility(", app_js)
        self.assertIn("setAllReportColumnsVisibility(", app_js)
        self.assertIn("resetReportColumnsDefault(", app_js)
        self.assertIn("toggleReportGridCustomizer(", app_js)

    def test_17_app_js_implements_drag_and_drop_column_reordering(self):
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("reorderReportColumn(", app_js)
        self.assertIn("onReportColDragStart(", app_js)
        self.assertIn("onReportColDragOver(", app_js)
        self.assertIn("onReportColDrop(", app_js)
        self.assertIn('draggable="true"', app_js)

    def test_18_app_js_implements_multi_column_grouping_and_group_subtotal_line_items(self):
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("toggleReportGroupByCol(", app_js)
        self.assertIn("clearReportGroupingCols(", app_js)
        self.assertIn("toggleReportGroupTotals(", app_js)
        self.assertIn("_aggregateReportGroup(", app_js)
        self.assertIn("report-group-subtotal-row", app_js)
        self.assertIn("report-grand-total-row", app_js)

    def test_19_app_js_formats_local_model_est_cost_as_negative_in_parentheses_with_alternate_color(self):
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("formatReportEstCostCell(", app_js)
        self.assertIn("(-$${absSavings.toFixed(4)})", app_js)
        self.assertIn("#c084fc", app_js)

    def test_20_app_js_synchronizes_window_and_chart_config_bidirectionally_with_settings_api(self):
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("active_trend_window", app_js)
        self.assertIn("default_trend_window", app_js)
        self.assertIn("active_chart_granularity", app_js)
        self.assertIn("active_chart_mode", app_js)


if __name__ == "__main__":
    unittest.main()
