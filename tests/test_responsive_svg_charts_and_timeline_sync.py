import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.storage.database import UsageDatabase

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestResponsiveSvgChartsAndTimelineSync(unittest.TestCase):
    """
    Authoritative verification test suite for AIUM-906:
    1. SVG Charts Scaling vs Stretching: uniform scaling, vector-effect non-scaling-stroke,
       crisp un-stretched rendering on ultrawide displays.
    2. Timeline & Plot Synchronization: fresh backend data ingestion on refresh/sync,
       cache invalidation, consistent time axis.
    3. Ollama Model Sparklines: punctuation-agnostic ID matching and async DOM hydration.
    4. Claude Personal Pro vs Team Workspace Disaggregation.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_aium_906.db")
        self.db = UsageDatabase(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # ------------------------------------------------------------------
    # 1. Frontend SVG Scaling & Non-Stretching Rules
    # ------------------------------------------------------------------

    def test_01_no_preserve_aspect_ratio_none_in_frontend(self):
        """Verifies that preserveAspectRatio='none' is eliminated across frontend HTML and JS."""
        frontend_dir = PROJECT_ROOT / "frontend"
        files_to_check = list(frontend_dir.glob("*.html")) + \
                         list(frontend_dir.glob("*.js")) + \
                         list((frontend_dir / "components").glob("*.html")) + \
                         list((frontend_dir / "js").glob("*.js"))

        for f in files_to_check:
            content = f.read_text(encoding="utf-8")
            self.assertNotIn(
                'preserveAspectRatio="none"',
                content,
                f"File {f.name} contains forbidden preserveAspectRatio='none' which causes chart stretching."
            )

    def test_02_vector_effect_non_scaling_stroke_in_svg_charts(self):
        """Verifies that vector-effect='non-scaling-stroke' is applied to prevent line thickening."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('vector-effect="non-scaling-stroke"', app_js)
        # Should be used in renderSvgChart, renderMultiSeriesTrendChart, and sparklines
        count = app_js.count('vector-effect="non-scaling-stroke"')
        self.assertGreaterEqual(count, 5, f"Expected at least 5 non-scaling-stroke references, got {count}")

    def test_03_responsive_viewbox_uses_dynamic_width(self):
        """Verifies that charts dynamically measure container width instead of using static 860/900."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        # In renderSvgChart:
        self.assertIn("chartContainer.clientWidth", app_js)
        # In renderMultiSeriesTrendChart:
        self.assertIn("container.clientWidth", app_js)
        # Check that viewBox uses dynamic width
        self.assertIn("viewBox=\"0 0 ${width} ${height}\"", app_js)

    def test_04_crosshair_scales_with_dynamic_width(self):
        """Verifies crosshair mouse position calculation uses dynamic width parameter."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("_setupChartHoverCrosshair", app_js)
        self.assertIn("const svgX = (mouseX / rect.width) * width;", app_js)

    def test_05_sparkline_has_unique_container_ids(self):
        """Verifies child branch cards render sparkline targets with unique IDs."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="sparkline-ollama-${safeModelId}"', app_js)
        self.assertIn('id="sparkline-claude-claude_individual"', app_js)
        self.assertIn('id="sparkline-claude-claude_team"', app_js)
        self.assertIn('id="sparkline-gemini-gemini_account"', app_js)

    def test_06_async_update_child_sparklines_method_exists(self):
        """Verifies updateChildSparklines method is present and invoked in loadAndRenderHierarchicalTrendChart."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("updateChildSparklines(providerKey, data)", app_js)
        self.assertIn("this.updateChildSparklines(providerKey, data);", app_js)

    def test_07_get_child_real_points_punctuation_agnostic_matching(self):
        """Verifies punctuation-agnostic regex matching in getChildRealPoints."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("normChild = String(childId || '').toLowerCase().replace(/[^a-z0-9]/g, '')", app_js)
        self.assertIn("normRaw = rawId.toLowerCase().replace(/[^a-z0-9]/g, '')", app_js)

    def test_08_cache_invalidation_on_load_usage_data(self):
        """Verifies that loadUsageData invalidates cachedHierarchicalTrends for fresh fetches."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        # In loadUsageData
        pattern = r"async\s+loadUsageData\(\)\s*\{[^}]+this\.cachedHierarchicalTrends\s*=\s*\{\};"
        self.assertTrue(re.search(pattern, app_js, re.DOTALL), "cachedHierarchicalTrends must be cleared in loadUsageData")

    def test_09_cache_invalidation_on_sync_provider(self):
        """Verifies that syncProvider invalidates cachedHierarchicalTrends."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        pattern = r"async\s+syncProvider\(provider\)\s*\{[^}]+this\.cachedHierarchicalTrends\s*=\s*\{\};"
        self.assertTrue(re.search(pattern, app_js, re.DOTALL), "cachedHierarchicalTrends must be cleared in syncProvider")

    def test_10_cache_invalidation_on_window_change(self):
        """Verifies that setChartWindow and setTrendWindow invalidate cached trends."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("this.chartWindow = win || \"24h\";\n    this.trendWindow = this.chartWindow;\n    this.cachedHierarchicalTrends = {};", app_js)
        self.assertIn("this.trendWindow = windowPeriod || \"24h\";\n    this.chartWindow = this.trendWindow;\n    this.cachedHierarchicalTrends = {};", app_js)

    # ------------------------------------------------------------------
    # 2. Backend Claude Disaggregation & Ollama Model Handling
    # ------------------------------------------------------------------

    def test_11_claude_pro_personal_events_routed_to_individual_only(self):
        """Verifies that personal Claude Pro events only increment individual bucket, not team."""
        # Record a personal Claude Pro event
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            user_name="James",
            team_name="Claude Pro",  # Personal subscription name
            input_tokens=2000,
            output_tokens=1000,
            estimated_cost=0.03,
            account_id="user-james-claude-pro",
            source="direct"
        )

        trends = self.db.get_hierarchical_trends(provider="claude", window="24h")
        self.assertEqual(trends["provider"], "claude")
        series_by_id = {s["id"]: s for s in trends["series"]}

        self.assertIn("claude_individual", series_by_id)
        self.assertIn("claude_team", series_by_id)

        ind_total = series_by_id["claude_individual"]["total_tokens"]
        self.assertEqual(ind_total, 3000)

        # Team pool must be disaggregated from individual (not a 1:1 duplicate)
        team_total = series_by_id["claude_team"]["total_tokens"]
        self.assertNotEqual(team_total, ind_total)

    def test_12_claude_team_events_routed_to_team_bucket(self):
        """Verifies that enterprise/team Claude events increment team_org series."""
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-5-sonnet",
            user_name="Colleague",
            team_name="Synthesis2 Enterprise",
            input_tokens=5000,
            output_tokens=2500,
            estimated_cost=0.08,
            account_id="acct_synthesis2",
            source="proxy"
        )

        trends = self.db.get_hierarchical_trends(provider="claude", window="24h")
        series_by_id = {s["id"]: s for s in trends["series"]}
        self.assertIn("claude_team", series_by_id)
        team_total = series_by_id["claude_team"]["total_tokens"]
        self.assertEqual(team_total, 7500)

    def test_13_claude_team_ratio_disaggregation_without_external_team_events(self):
        """Verifies that when only local personal Claude Pro usage exists, team pool computes ratio."""
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            user_name="James",
            team_name="Claude Pro",
            input_tokens=1000,
            output_tokens=500,
            estimated_cost=0.015,
            account_id="user-james-claude-pro"
        )

        trends = self.db.get_hierarchical_trends(provider="claude", window="24h")
        series_by_id = {s["id"]: s for s in trends["series"]}
        ind_pts = series_by_id["claude_individual"]["points"]
        team_pts = series_by_id["claude_team"]["points"]

        # Points must not be identical across all bins
        self.assertNotEqual(ind_pts, team_pts)
        self.assertGreater(sum(team_pts), sum(ind_pts))

    def test_14_ollama_model_hierarchy_series_generation(self):
        """Verifies that Ollama models are correctly surfaced with sanitized IDs in trends hierarchy."""
        self.db.record_usage_event(
            provider="ollama",
            model="nomic-embed-text:latest",
            input_tokens=10000,
            output_tokens=0,
            instance_id="local",
            source="direct"
        )
        self.db.record_usage_event(
            provider="ollama",
            model="gemma:2b",
            input_tokens=500,
            output_tokens=300,
            instance_id="local",
            source="direct"
        )

        trends = self.db.get_hierarchical_trends(provider="ollama", window="24h")
        self.assertEqual(trends["provider"], "ollama")
        series_ids = [s["id"] for s in trends["series"]]

        # Both models should be represented with sanitized IDs
        self.assertIn("ollama_model_nomic-embed-text_latest", series_ids)
        self.assertIn("ollama_model_gemma_2b", series_ids)

        model_s = next(s for s in trends["series"] if s["id"] == "ollama_model_nomic-embed-text_latest")
        self.assertEqual(model_s["total_tokens"], 10000)

    def test_15_ollama_node_locality_disaggregation(self):
        """Verifies that Ollama trends separate local hardware compute from remote LAN nodes."""
        self.db.register_managed_node(
            name="Remote Rig RTX 4090",
            endpoint="http://192.168.1.50:11434",
            engine="ollama",
            node_id="node_rtx4090"
        )
        self.db.record_usage_event(
            provider="ollama",
            model="llama3:latest",
            input_tokens=1200,
            output_tokens=400,
            instance_id="local"
        )
        self.db.record_usage_event(
            provider="ollama",
            model="llama3:latest",
            input_tokens=3000,
            output_tokens=1000,
            instance_id="node_rtx4090"
        )

        trends = self.db.get_hierarchical_trends(provider="ollama", window="24h")
        series_ids = [s["id"] for s in trends["series"]]

        self.assertIn("ollama_local_node", series_ids)
        self.assertIn("ollama_remote_lan", series_ids)
        self.assertIn("ollama_node_node_rtx4090", series_ids)

        local_s = next(s for s in trends["series"] if s["id"] == "ollama_local_node")
        remote_s = next(s for s in trends["series"] if s["id"] == "ollama_remote_lan")

        self.assertEqual(local_s["total_tokens"], 1600)
        self.assertEqual(remote_s["total_tokens"], 4000)

    # ------------------------------------------------------------------
    # 3. Timeline Alignment & Labels
    # ------------------------------------------------------------------

    def test_16_hierarchical_trends_timeline_labels_match_num_bins(self):
        """Verifies that hierarchical trends return matching labels and keys length for all windows."""
        windows = ["1h", "3h", "6h", "12h", "24h", "48h", "3d", "7d"]
        for win in windows:
            res = self.db.get_hierarchical_trends(provider="claude", window=win)
            self.assertIn("labels", res)
            self.assertIn("keys", res)
            self.assertEqual(len(res["labels"]), len(res["keys"]))
            for s in res["series"]:
                self.assertEqual(len(s["points"]), len(res["labels"]))

    def test_17_hierarchical_trends_keys_are_iso_prefixes(self):
        """Verifies that keys returned by hierarchical trends allow browser local-time conversion."""
        res = self.db.get_hierarchical_trends(provider="ollama", window="24h")
        self.assertTrue(len(res["keys"]) > 0)
        # 24h keys format is %Y-%m-%dT%H
        for k in res["keys"]:
            self.assertTrue(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}$", k), f"Key {k} is not in expected %Y-%m-%dT%H format")

    def test_18_inline_sparkline_responsive_viewbox(self):
        """Verifies generateInlineSparkline produces responsive viewBox with non-scaling-stroke."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("viewBox=\"0 0 ${w} ${h}\"", app_js)
        self.assertIn("stroke-width=\"2\" vector-effect=\"non-scaling-stroke\"", app_js)

    def test_19_multi_inline_sparkline_vector_effect(self):
        """Verifies generateMultiInlineSparkline uses vector-effect='non-scaling-stroke'."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        # In generateMultiInlineSparkline
        self.assertIn("generateMultiInlineSparkline", app_js)
        self.assertIn("<polyline fill=\"none\" stroke=\"${s.color}\" stroke-width=\"2\" vector-effect=\"non-scaling-stroke\"", app_js)

    def test_20_dynamic_label_interval_prevents_overlap(self):
        """Verifies that dynamic label intervals are computed in renderMultiSeriesTrendChart and renderSvgChart."""
        app_js = (PROJECT_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        # In renderSvgChart:
        self.assertIn("const maxLabels = Math.max(5, Math.floor(plotW / 85));", app_js)
        self.assertIn("const labelInterval = Math.max(1, Math.ceil(numPoints / maxLabels));", app_js)
        # In renderMultiSeriesTrendChart:
        self.assertIn("const maxLabels = Math.max(4, Math.floor(plotW / 85));", app_js)
        self.assertIn("const labelInterval = Math.max(1, Math.ceil(n / maxLabels));", app_js)


if __name__ == "__main__":
    unittest.main()
