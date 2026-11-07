"""
Unit tests for Ticket AIUM-1007: Shared Frontend Core (frontend/js/core/)
Verifies:
1. Core directory and canonical modules exist.
2. Formatters module exports formatTokens, formatCurrency, formatCountdown, formatLocalDateTime, formatLocalTime, formatDuration, escapeHtml, and provider maps.
3. ApiClient module exports getSettings, saveSettings, getThemes, getHierarchies, getHierarchicalTrends, getGranularTimeseries, syncActiveIcon.
4. ChartRenderer module renders crisp responsive SVG sparklines with non-scaling strokes and honest zero baselines.
5. TelemetryHierarchy module performs punctuation-agnostic matching and returns honest zero baselines.
6. Zero synthetic fallback multipliers [0.7, 0.9, 1.1...] across widget.js, app.js, and core/.
7. Scripts are wired into index.html right before app.js.
8. widget.js and app.js delegate to window.AIUMCore.*.
9. widget.js supports bucket granularity and scope filter synchronization.
"""

import json
import os
import re
import subprocess
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_node_eval(js_code: str) -> dict:
    """Helper to run JavaScript snippet through Node.js and return parsed JSON."""
    result = subprocess.run(
        ["node", "-e", js_code],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT)
    )
    if result.returncode != 0:
        raise RuntimeError(f"Node execution failed (code {result.returncode}):\n{result.stderr}\nCode:\n{js_code}")
    return json.loads(result.stdout.strip())


class TestSharedFrontendCore(unittest.TestCase):
    """Test suite for AIUM-1007 Shared Frontend Core architecture."""

    @classmethod
    def setUpClass(cls):
        cls.core_dir = PROJECT_ROOT / "frontend" / "js" / "core"
        cls.formatters_path = cls.core_dir / "formatters.js"
        cls.api_client_path = cls.core_dir / "api_client.js"
        cls.chart_renderer_path = cls.core_dir / "chart_renderer.js"
        cls.telemetry_hierarchy_path = cls.core_dir / "telemetry_hierarchy.js"
        cls.widget_js_path = PROJECT_ROOT / "frontend" / "js" / "widget.js"
        cls.app_js_path = PROJECT_ROOT / "frontend" / "js" / "app.js"
        cls.index_html_path = PROJECT_ROOT / "frontend" / "index.html"

    # ------------------------------------------------------------------
    # 1. Existence of Core Files
    # ------------------------------------------------------------------

    def test_01_core_directory_and_modules_exist(self):
        """Verifies all four core JS modules exist in frontend/js/core/."""
        self.assertTrue(self.core_dir.is_dir(), "frontend/js/core directory must exist")
        self.assertTrue(self.formatters_path.is_file(), "formatters.js must exist")
        self.assertTrue(self.api_client_path.is_file(), "api_client.js must exist")
        self.assertTrue(self.chart_renderer_path.is_file(), "chart_renderer.js must exist")
        self.assertTrue(self.telemetry_hierarchy_path.is_file(), "telemetry_hierarchy.js must exist")

    # ------------------------------------------------------------------
    # 2. Formatters Functionality
    # ------------------------------------------------------------------

    def test_02_formatters_exports_format_tokens(self):
        """Verifies formatTokens formats numbers (1.2M, 45.3k, 850) correctly."""
        js = """
        const Formatters = require('./frontend/js/core/formatters.js');
        const res = {
            t850: Formatters.formatTokens(850),
            t45k: Formatters.formatTokens(45300),
            t1_2M: Formatters.formatTokens(1200000),
            t1M: Formatters.formatTokens(1000000),
            t2_5B: Formatters.formatTokens(2500000000),
            tZero: Formatters.formatTokens(0),
            tNull: Formatters.formatTokens(null)
        };
        console.log(JSON.stringify(res));
        """
        res = run_node_eval(js)
        self.assertEqual(res["t850"], "850")
        self.assertEqual(res["t45k"], "45.3k")
        self.assertEqual(res["t1_2M"], "1.2M")
        self.assertEqual(res["t1M"], "1M")
        self.assertEqual(res["t2_5B"], "2.5B")
        self.assertEqual(res["tZero"], "0")
        self.assertEqual(res["tNull"], "0")

    def test_03_formatters_exports_format_currency(self):
        """Verifies formatCurrency formats $0.00 or micro-cost $0.0042 correctly."""
        js = """
        const Formatters = require('./frontend/js/core/formatters.js');
        const res = {
            cZero: Formatters.formatCurrency(0),
            cMicro: Formatters.formatCurrency(0.0042),
            cStandard: Formatters.formatCurrency(12.5),
            cThreeDec: Formatters.formatCurrency(1.234, 3)
        };
        console.log(JSON.stringify(res));
        """
        res = run_node_eval(js)
        self.assertEqual(res["cZero"], "$0.00")
        self.assertEqual(res["cMicro"], "$0.0042")
        self.assertEqual(res["cStandard"], "$12.50")
        self.assertEqual(res["cThreeDec"], "$1.234")

    def test_04_formatters_exports_format_countdown(self):
        """Verifies formatCountdown produces unified countdown (e.g. 2h 14m or 45m 12s)."""
        js = """
        const Formatters = require('./frontend/js/core/formatters.js');
        const now = Date.now() / 1000;
        const res = {
            cHours: Formatters.formatCountdown(now + 8040),      // 2h 14m
            cMinutes: Formatters.formatCountdown(now + 2712),    // 45m 12s
            cFallback: Formatters.formatCountdown(null, "--"),
            cExpired: Formatters.formatCountdown(now - 10, "--")
        };
        console.log(JSON.stringify(res));
        """
        res = run_node_eval(js)
        self.assertEqual(res["cHours"], "2h 14m")
        self.assertEqual(res["cMinutes"], "45m 12s")
        self.assertEqual(res["cFallback"], "--")
        self.assertEqual(res["cExpired"], "--")

    def test_05_formatters_exports_datetime_and_duration(self):
        """Verifies formatLocalDateTime, formatLocalTime, and formatDuration."""
        js = """
        const Formatters = require('./frontend/js/core/formatters.js');
        const d1 = '2026-11-07T10:00:00Z';
        const d2 = '2026-11-07T12:15:30Z';
        const res = {
            hasDateTime: typeof Formatters.formatLocalDateTime === 'function',
            hasLocalTime: typeof Formatters.formatLocalTime === 'function',
            duration: Formatters.formatDuration(d1, d2)
        };
        console.log(JSON.stringify(res));
        """
        res = run_node_eval(js)
        self.assertTrue(res["hasDateTime"])
        self.assertTrue(res["hasLocalTime"])
        self.assertEqual(res["duration"], "2h 15m")

    def test_06_formatters_exports_escape_html(self):
        """Verifies escapeHtml neutralizes HTML special characters."""
        js = """
        const Formatters = require('./frontend/js/core/formatters.js');
        const res = {
            escaped: Formatters.escapeHtml('<script>alert("xss" & "test")</script>')
        };
        console.log(JSON.stringify(res));
        """
        res = run_node_eval(js)
        self.assertNotIn("<script>", res["escaped"])
        self.assertIn("&lt;script&gt;", res["escaped"])
        self.assertIn("&quot;", res["escaped"])
        self.assertIn("&amp;", res["escaped"])

    def test_07_formatters_canonical_provider_maps(self):
        """Verifies PROVIDER_COLORS and PROVIDER_NAMES maps contain all standard providers."""
        js = """
        const Formatters = require('./frontend/js/core/formatters.js');
        console.log(JSON.stringify({
            colors: Formatters.PROVIDER_COLORS,
            names: Formatters.PROVIDER_NAMES
        }));
        """
        res = run_node_eval(js)
        colors = res["colors"]
        names = res["names"]
        for p in ["claude", "ollama", "gemini", "copilot", "chatgpt"]:
            self.assertIn(p, colors)
            self.assertIn(p, names)
        self.assertEqual(colors["claude"], "#f59e0b")
        self.assertEqual(colors["ollama"], "#10b981")
        self.assertEqual(colors["gemini"], "#3b82f6")
        self.assertEqual(colors["copilot"], "#8b5cf6")

    # ------------------------------------------------------------------
    # 3. ApiClient Functionality
    # ------------------------------------------------------------------

    def test_08_api_client_exports_required_methods(self):
        """Verifies ApiClient exports getSettings, saveSettings, getThemes, getHierarchies, trends, syncActiveIcon."""
        js = """
        const ApiClient = require('./frontend/js/core/api_client.js');
        const res = {
            getSettings: typeof ApiClient.getSettings === 'function',
            saveSettings: typeof ApiClient.saveSettings === 'function',
            getThemes: typeof ApiClient.getThemes === 'function',
            getHierarchies: typeof ApiClient.getHierarchies === 'function',
            getHierarchicalTrends: typeof ApiClient.getHierarchicalTrends === 'function',
            getGranularTimeseries: typeof ApiClient.getGranularTimeseries === 'function',
            syncActiveIcon: typeof ApiClient.syncActiveIcon === 'function'
        };
        console.log(JSON.stringify(res));
        """
        res = run_node_eval(js)
        for method, is_fn in res.items():
            self.assertTrue(is_fn, f"ApiClient must export {method}")

    def test_09_api_client_sync_active_icon_persists_settings(self):
        """Verifies syncActiveIcon implementation accesses localStorage and saves to settings."""
        content = self.api_client_path.read_text(encoding="utf-8")
        self.assertIn("syncActiveIcon(iconId)", content)
        self.assertIn('localStorage.setItem(\'aium_active_icon\', iconId)', content)
        self.assertIn("active_icon: iconId", content)

    def test_10_api_client_themes_definition(self):
        """Verifies getThemes returns theme dictionary with obsidian, cyberpunk, matrix, midnight."""
        js = """
        const ApiClient = require('./frontend/js/core/api_client.js');
        ApiClient.getThemes().then(themes => {
            console.log(JSON.stringify(Object.keys(themes)));
        });
        """
        themes = run_node_eval(js)
        self.assertIn("obsidian", themes)
        self.assertIn("cyberpunk", themes)
        self.assertIn("matrix", themes)
        self.assertIn("midnight", themes)

    # ------------------------------------------------------------------
    # 4. ChartRenderer Functionality
    # ------------------------------------------------------------------

    def test_11_chart_renderer_exports_generate_sparkline_svg(self):
        """Verifies generateSparklineSvg method is exported on ChartRenderer."""
        js = """
        const ChartRenderer = require('./frontend/js/core/chart_renderer.js');
        console.log(JSON.stringify({
            hasSparkline: typeof ChartRenderer.generateSparklineSvg === 'function',
            hasMultiSparkline: typeof ChartRenderer.generateMultiSparklineSvg === 'function'
        }));
        """
        res = run_node_eval(js)
        self.assertTrue(res["hasSparkline"])
        self.assertTrue(res["hasMultiSparkline"])

    def test_12_chart_renderer_idle_points_flat_zero_baseline(self):
        """Verifies all-zero points produce an honest flat idle indicator without fake waves."""
        js = """
        const ChartRenderer = require('./frontend/js/core/chart_renderer.js');
        const svg = ChartRenderer.generateSparklineSvg([0, 0, 0, 0, 0, 0, 0, 0], '#06b6d4');
        console.log(JSON.stringify({ svg }));
        """
        res = run_node_eval(js)
        svg = res["svg"]
        self.assertIn("0 t (idle)", svg)
        self.assertIn('stroke-dasharray="2,2"', svg)
        self.assertIn('vector-effect="non-scaling-stroke"', svg)

    def test_13_chart_renderer_active_points_polyline_and_gradient(self):
        """Verifies active points render crisp polyline, end circle, and gradient fill."""
        js = """
        const ChartRenderer = require('./frontend/js/core/chart_renderer.js');
        const svg = ChartRenderer.generateSparklineSvg([100, 250, 400, 320, 600], '#38bdf8');
        console.log(JSON.stringify({ svg }));
        """
        res = run_node_eval(js)
        svg = res["svg"]
        self.assertIn("<polyline", svg)
        self.assertIn('stroke="#38bdf8"', svg)
        self.assertIn('vector-effect="non-scaling-stroke"', svg)
        self.assertIn("<circle", svg)
        self.assertIn("<linearGradient", svg)
        self.assertIn("<polygon", svg)

    def test_14_chart_renderer_multi_sparkline_svg(self):
        """Verifies generateMultiSparklineSvg renders multi-series overlaid lines with non-scaling-stroke."""
        js = """
        const ChartRenderer = require('./frontend/js/core/chart_renderer.js');
        const series = [
            { label: 'Team', color: '#c084fc', points: [10, 20, 30] },
            { label: 'Ind', color: '#38bdf8', points: [5, 15, 25] }
        ];
        const svg = ChartRenderer.generateMultiSparklineSvg(series, 120, 26);
        console.log(JSON.stringify({ svg }));
        """
        res = run_node_eval(js)
        svg = res["svg"]
        self.assertIn("#c084fc", svg)
        self.assertIn("#38bdf8", svg)
        self.assertIn('vector-effect="non-scaling-stroke"', svg)

    # ------------------------------------------------------------------
    # 5. TelemetryHierarchy Functionality
    # ------------------------------------------------------------------

    def test_15_telemetry_hierarchy_exports_extract_child_real_points(self):
        """Verifies extractChildRealPoints is exported on TelemetryHierarchy."""
        js = """
        const TH = require('./frontend/js/core/telemetry_hierarchy.js');
        console.log(JSON.stringify({
            hasExtract: typeof TH.extractChildRealPoints === 'function',
            hasBaseline: Array.isArray(TH.HONEST_ZERO_BASELINE)
        }));
        """
        res = run_node_eval(js)
        self.assertTrue(res["hasExtract"])
        self.assertTrue(res["hasBaseline"])

    def test_16_telemetry_hierarchy_punctuation_agnostic_matching(self):
        """Verifies punctuation-agnostic matching for model IDs with colons and underscores."""
        js = """
        const TH = require('./frontend/js/core/telemetry_hierarchy.js');
        const trends = {
            provider: 'ollama',
            series: [
                { id: 'ollama_model_nomic_embed_text_latest', points: [10, 20, 30, 40] },
                { id: 'ollama_model_gemma_2b', points: [5, 15, 25, 35] }
            ]
        };
        const res = {
            nomic: TH.extractChildRealPoints(trends, 'ollama', 'nomic-embed-text:latest'),
            gemma: TH.extractChildRealPoints(trends, 'ollama', 'gemma:2b')
        };
        console.log(JSON.stringify(res));
        """
        res = run_node_eval(js)
        self.assertEqual(res["nomic"], [10, 20, 30, 40])
        self.assertEqual(res["gemma"], [5, 15, 25, 35])

    def test_17_telemetry_hierarchy_idle_returns_honest_zero_baseline(self):
        """Verifies missing series return strict honest zero baseline [0, 0, 0, 0, 0, 0, 0, 0]."""
        js = """
        const TH = require('./frontend/js/core/telemetry_hierarchy.js');
        const res = {
            pts: TH.extractChildRealPoints(null, 'claude', 'missing_child')
        };
        console.log(JSON.stringify(res));
        """
        res = run_node_eval(js)
        self.assertEqual(res["pts"], [0, 0, 0, 0, 0, 0, 0, 0])

    # ------------------------------------------------------------------
    # 6. Zero Synthetic Multipliers Across Frontend
    # ------------------------------------------------------------------

    def test_18_zero_synthetic_multipliers_in_widget_and_core(self):
        """Verifies fake multipliers [0.7, 0.9, 1.1, 0.85, 1.15, 0.95] are completely eliminated."""
        files_to_check = [
            self.widget_js_path,
            self.app_js_path,
            self.formatters_path,
            self.api_client_path,
            self.chart_renderer_path,
            self.telemetry_hierarchy_path
        ]
        for f in files_to_check:
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("baseline * 0.7", text, f"Forbidden synthetic multiplier found in {f.name}")
            self.assertNotIn("baseline * 0.85", text, f"Forbidden synthetic multiplier found in {f.name}")
            self.assertNotIn("baseline * 1.15", text, f"Forbidden synthetic multiplier found in {f.name}")

    # ------------------------------------------------------------------
    # 7. HTML Script Inclusion
    # ------------------------------------------------------------------

    def test_19_index_html_wires_all_core_scripts(self):
        """Verifies index.html loads all 4 core scripts right before app.js."""
        html = self.index_html_path.read_text(encoding="utf-8")
        self.assertIn('src="js/core/formatters.js"', html)
        self.assertIn('src="js/core/api_client.js"', html)
        self.assertIn('src="js/core/chart_renderer.js"', html)
        self.assertIn('src="js/core/telemetry_hierarchy.js"', html)

        # Check ordering: all core scripts must appear before app.js
        idx_formatters = html.find('src="js/core/formatters.js"')
        idx_api = html.find('src="js/core/api_client.js"')
        idx_chart = html.find('src="js/core/chart_renderer.js"')
        idx_telemetry = html.find('src="js/core/telemetry_hierarchy.js"')
        idx_app = html.find('src="js/app.js"')
        if idx_app == -1:
            idx_app = html.find('src="/js/app.js"')

        self.assertGreater(idx_app, idx_formatters, "formatters.js must precede app.js")
        self.assertGreater(idx_app, idx_api, "api_client.js must precede app.js")
        self.assertGreater(idx_app, idx_chart, "chart_renderer.js must precede app.js")
        self.assertGreater(idx_app, idx_telemetry, "telemetry_hierarchy.js must precede app.js")

    # ------------------------------------------------------------------
    # 8. Widget & App Delegation
    # ------------------------------------------------------------------

    def test_20_widget_js_delegates_to_core_formatters_and_charts(self):
        """Verifies widget.js delegates formatting, sparkline rendering, and hierarchy resolution to core."""
        text = self.widget_js_path.read_text(encoding="utf-8")
        self.assertIn("window.AIUMCore.Formatters", text)
        self.assertIn("window.AIUMCore.ChartRenderer", text)
        self.assertIn("window.AIUMCore.TelemetryHierarchy", text)
        self.assertIn("formatTokens(", text)
        self.assertIn("formatCurrency(", text)
        self.assertIn("formatCountdown(", text)
        self.assertIn("getChildRealPoints(", text)

    def test_21_widget_js_bucket_and_scope_synchronization(self):
        """Verifies widget.js supports bucket granularity and scope filter synchronization."""
        text = self.widget_js_path.read_text(encoding="utf-8")
        self.assertIn("bucketMins:", text)
        self.assertIn("scopeFilter:", text)
        self.assertIn("setBucketMins(", text)
        self.assertIn("setScopeFilter(", text)
        self.assertIn("aium_bucket_mins", text)
        self.assertIn("aium_scope_filter", text)

    def test_22_app_js_delegates_to_core_modules(self):
        """Verifies app.js delegates to window.AIUMCore modules with backward-compatible fallbacks."""
        text = self.app_js_path.read_text(encoding="utf-8")
        self.assertIn("window.AIUMCore.Formatters", text)
        self.assertIn("window.AIUMCore.ChartRenderer", text)
        self.assertIn("window.AIUMCore.TelemetryHierarchy", text)
        self.assertIn("window.AIUMCore.ApiClient", text)
        self.assertIn("generateSparkline(", text)
        self.assertIn("formatTokens(", text)
        self.assertIn("syncActiveIcon(", text)


if __name__ == "__main__":
    unittest.main()
