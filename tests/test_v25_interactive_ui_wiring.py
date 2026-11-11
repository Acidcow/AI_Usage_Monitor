"""
Unit Test Suite for AIUM-1013: Live v2.5 Interactive UI Wiring & Theme/Density Controls.
Verifies:
1. Settings Panel 6-Theme Swatch Grid (`#theme-swatch-grid`), `#cfg-widget-theme`, `#cfg-layout-density`, and unique DOM IDs.
2. Live Dashboard & Session Timeline Prompt Cache Efficiency Banner wiring (`renderCacheEfficiency`) and 14-column session table rendering (`renderSessions`).
3. Capacity Tab 5h/7d Rolling Quota Pacing Forecaster (`renderCapacityQuotaPacing`) & Context-Window Bloat Anomalies (`renderContextBloatAnomalies`).
4. Benchmark Scorecard click-to-inspect Transcript Modal (`openBenchmarkTranscriptModal`).
5. Troubleshooting Log deduplication & filter wiring (`renderErrors` -> `deduplicateDiagnosticErrors` / `filterDiagnosticLogs`).
"""

import os
import tempfile
import unittest
from pathlib import Path

from backend.storage.database import DatabaseManager
from backend.contracts.themes import CANONICAL_THEME_IDS, get_theme, get_all_themes


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_HTML_PATH = PROJECT_ROOT / "frontend" / "components" / "settings_panel.html"
TIMELINE_HTML_PATH = PROJECT_ROOT / "frontend" / "components" / "session_timeline.html"
GAUGE_HTML_PATH = PROJECT_ROOT / "frontend" / "components" / "usage_gauge_card.html"
CAPACITY_HTML_PATH = PROJECT_ROOT / "frontend" / "components" / "capacity_analytics.html"
BENCHMARK_HTML_PATH = PROJECT_ROOT / "frontend" / "components" / "benchmark_scorecard.html"
APP_JS_PATH = PROJECT_ROOT / "frontend" / "js" / "app.js"


class TestV25InteractiveUIWiring(unittest.TestCase):
    """22 unit tests verifying v2.5 interactive UI wiring across HTML templates, app.js, and SQLite settings."""

    @classmethod
    def setUpClass(cls):
        cls.settings_html = SETTINGS_HTML_PATH.read_text(encoding="utf-8")
        cls.timeline_html = TIMELINE_HTML_PATH.read_text(encoding="utf-8")
        cls.gauge_html = GAUGE_HTML_PATH.read_text(encoding="utf-8")
        cls.capacity_html = CAPACITY_HTML_PATH.read_text(encoding="utf-8")
        cls.benchmark_html = BENCHMARK_HTML_PATH.read_text(encoding="utf-8")
        cls.app_js = APP_JS_PATH.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # 1. Settings Panel 6-Theme Selector, Swatches & Density Controls
    # ------------------------------------------------------------------
    def test_01_settings_panel_includes_all_six_ultra_modern_themes_in_select(self):
        for theme_id in (
            "linear-obsidian",
            "geist-monochrome",
            "cyberpunk-hud",
            "catppuccin-mocha",
            "tokyo-night",
            "executive-paper",
        ):
            self.assertIn(f'value="{theme_id}"', self.settings_html)

    def test_02_settings_panel_includes_interactive_swatch_grid(self):
        self.assertIn('id="theme-swatch-grid"', self.settings_html)
        for theme_id in (
            "linear-obsidian",
            "geist-monochrome",
            "cyberpunk-hud",
            "catppuccin-mocha",
            "tokyo-night",
            "executive-paper",
        ):
            self.assertIn(f'data-theme-id="{theme_id}"', self.settings_html)
            self.assertIn(f"window.App.selectThemeSwatch('{theme_id}')", self.settings_html)

    def test_03_settings_panel_includes_layout_density_selector(self):
        self.assertIn('id="cfg-layout-density"', self.settings_html)
        for mode in ("compact", "balanced", "ultrawide"):
            self.assertIn(f'value="{mode}"', self.settings_html)

    def test_04_settings_panel_has_no_duplicate_default_trend_window_id(self):
        count = self.settings_html.count('id="cfg-default-trend-window"')
        self.assertEqual(count, 1, "id='cfg-default-trend-window' must appear exactly once in settings_panel.html")
        self.assertIn('id="cfg-visibility-trend-window"', self.settings_html)

    def test_05_app_js_wires_select_and_highlight_theme_swatch(self):
        self.assertIn("selectThemeSwatch(themeId)", self.app_js)
        self.assertIn("highlightThemeSwatch(themeId)", self.app_js)
        self.assertIn("this.applyTheme(selectedTheme)", self.app_js)
        self.assertIn("this.applyLayoutDensity(selectedDensity)", self.app_js)

    def test_06_database_settings_default_includes_layout_density(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_settings.db")
            db = DatabaseManager(db_path=db_path)
            settings = db.get_all_settings()
            self.assertEqual(settings.get("layout_density"), "balanced")
            db.set_setting("widget_theme", "catppuccin-mocha")
            db.set_setting("layout_density", "ultrawide")
            updated = db.get_all_settings()
            self.assertEqual(updated.get("widget_theme"), "catppuccin-mocha")
            self.assertEqual(updated.get("layout_density"), "ultrawide")

    # ------------------------------------------------------------------
    # 2. Prompt Cache Efficiency Banner & 14-Column Session Table Wiring
    # ------------------------------------------------------------------
    def test_07_load_usage_data_fetches_cache_efficiency_endpoint(self):
        self.assertIn('fetch("/api/analytics/cache-efficiency?provider=claude&hours=24")', self.app_js)
        self.assertIn("this.renderCacheEfficiency(cacheData);", self.app_js)

    def test_08_render_cache_efficiency_populates_dashboard_and_timeline_elements(self):
        for dom_id in (
            "val-cache-hit-ratio",
            "val-cache-ttl-remaining",
            "val-cache-net-savings",
            "val-cache-ttl-badge",
            "val-cache-grade-badge",
            "timeline-cache-hit-ratio",
            "timeline-cache-ttl",
            "timeline-net-savings",
            "timeline-cache-grade-badge",
            "timeline-break-even-status",
        ):
            self.assertIn(dom_id, self.app_js)

    def test_09_dashboard_and_timeline_html_contain_matching_cache_banner_ids(self):
        for dom_id in ("val-cache-hit-ratio", "val-cache-ttl-remaining", "val-cache-net-savings", "val-cache-grade-badge"):
            self.assertIn(f'id="{dom_id}"', self.gauge_html)
        for dom_id in ("timeline-cache-hit-ratio", "timeline-cache-ttl", "timeline-net-savings", "timeline-cache-grade-badge"):
            self.assertIn(f'id="{dom_id}"', self.timeline_html)

    def test_10_session_timeline_14_columns_aligned_between_html_and_app_js(self):
        self.assertIn('colspan="14"', self.timeline_html)
        self.assertIn('colspan="14"', self.app_js)
        self.assertIn("cache_read_tokens", self.app_js)
        self.assertIn("cache_creation_tokens", self.app_js)
        self.assertIn("net_cache_savings_usd", self.app_js)

    def test_11_session_sorting_supports_cache_and_savings_columns(self):
        self.assertIn('"cache_read_tokens", "cache_creation_tokens"', self.app_js)
        self.assertIn('"net_cache_savings_usd"', self.app_js)

    # ------------------------------------------------------------------
    # 3. Capacity Tab 5h/7d Pacing Forecaster & Context-Bloat Table Wiring
    # ------------------------------------------------------------------
    def test_12_load_capacity_analytics_invokes_pacing_and_bloat_renderers(self):
        self.assertIn("this.renderCapacityQuotaPacing(", self.app_js)
        self.assertIn("this.renderContextBloatAnomalies(", self.app_js)

    def test_13_render_capacity_quota_pacing_populates_all_dom_ids(self):
        for dom_id in (
            "cap-pacing-badge",
            "cap-pacing-burn-rate",
            "cap-pacing-exhaustion",
            "cap-pacing-reset",
            "cap-pacing-session-rem",
            "cap-pacing-weekly-rem",
            "cap-pacing-recommendation",
        ):
            self.assertIn(f'id="{dom_id}"', self.capacity_html)
            self.assertIn(f'"{dom_id}"', self.app_js)

    def test_14_render_context_bloat_anomalies_populates_table_body(self):
        self.assertIn('id="cap-bloat-anomalies-tbody"', self.capacity_html)
        self.assertIn('"cap-bloat-anomalies-tbody"', self.app_js)
        self.assertIn("EXHAUSTION_BEFORE_RESET", self.app_js)

    # ------------------------------------------------------------------
    # 4. Benchmark Transcript Modal Click-to-Inspect Wiring
    # ------------------------------------------------------------------
    def test_15_benchmark_results_rows_trigger_open_transcript_modal(self):
        self.assertIn("window.App.openBenchmarkTranscriptModal(", self.app_js)
        self.assertIn("openBenchmarkTranscriptModal(evalId)", self.app_js)

    def test_16_open_benchmark_transcript_modal_populates_all_modal_elements(self):
        for dom_id in (
            "benchmark-transcript-modal",
            "modal-bench-mode-badge",
            "modal-bench-model",
            "modal-bench-provider",
            "modal-bench-ttft",
            "modal-bench-tps",
            "modal-bench-score",
            "modal-bench-prompt",
            "modal-bench-output",
            "modal-bench-ast",
        ):
            self.assertIn(f'id="{dom_id}"', self.benchmark_html)
            self.assertIn(f'"{dom_id}"', self.app_js)

    def test_17_benchmark_modal_distinguishes_live_inference_and_simulated_fallback(self):
        self.assertIn("LIVE_INFERENCE", self.app_js)
        self.assertIn("SIMULATED_FALLBACK", self.app_js)

    # ------------------------------------------------------------------
    # 5. Troubleshooter Log Deduplication & Filter Wiring
    # ------------------------------------------------------------------
    def test_18_render_errors_stores_raw_errors_and_deduplicates(self):
        self.assertIn("this._rawDiagnosticErrors = Array.isArray(errors) ? errors : [];", self.app_js)
        self.assertIn("const deduped = this.deduplicateDiagnosticErrors(errors);", self.app_js)
        self.assertIn("×${err.count}", self.app_js)

    def test_19_render_errors_respects_active_search_and_category_filters(self):
        self.assertIn('document.getElementById("diag-log-search")', self.app_js)
        self.assertIn('document.getElementById("diag-log-category-filter")', self.app_js)
        self.assertIn("this.filterDiagnosticLogs();", self.app_js)

    # ------------------------------------------------------------------
    # 6. Theme Registry & Backend Contract Alignment
    # ------------------------------------------------------------------
    def test_20_theme_registry_matches_all_six_settings_swatch_ids(self):
        themes = get_all_themes()
        self.assertEqual(len(themes), 6)
        for tid in CANONICAL_THEME_IDS:
            self.assertIn(f'data-theme-id="{tid}"', self.settings_html)

    def test_21_get_theme_resolves_legacy_and_modern_ids(self):
        for tid in CANONICAL_THEME_IDS:
            resolved = get_theme(tid)
            self.assertEqual(resolved["id"], tid)
        fallback = get_theme("nonexistent-theme")
        self.assertEqual(fallback["id"], "linear-obsidian")

    def test_22_sessions_summary_includes_cache_efficiency_fields_from_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_sessions.db")
            db = DatabaseManager(db_path=db_path)
            db.record_usage_event(
                provider="claude",
                input_tokens=1000,
                output_tokens=400,
                cache_creation_tokens=2000,
                cache_read_tokens=15000,
                model="claude-3-7-sonnet",
                session_id="sess_ui_test_01",
                estimated_cost=0.05,
            )
            sessions = db.get_recent_sessions(provider="claude")
            self.assertEqual(len(sessions), 1)
            s = sessions[0]
            self.assertEqual(s["cache_read_tokens"], 15000)
            self.assertEqual(s["cache_creation_tokens"], 2000)
            self.assertIn("net_cache_savings_usd", s)
            self.assertIn("cache_badge_label", s)


if __name__ == "__main__":
    unittest.main()
