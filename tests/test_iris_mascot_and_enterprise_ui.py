"""
Unit tests for the v3.0 Enterprise UI Overhaul and IRIS Pixel-Art Mascot Reference Repository.

Verifies:
1. Canonical IRIS Mascot Asset Manifest (docs/IRIS_MASCOT_ASSET_MANIFEST.json) schema & structure.
2. Physical file existence and non-zero integrity for all 32 pixel-art assets across:
   - 00_base_reference/ (master digital skin-suit turnaround + user concept reference)
   - 01_poses/ (4 full-body operational poses)
   - 02_outfits/ (4 outfit overlays)
   - 03_expressions/ (4 3-degree sheets + 12 individual degree portraits)
   - 04_avatars/ (6 contextual 1:1 UI avatars)
3. Frontend core module (frontend/js/core/mascot_repository.js) contract & severity resolver.
4. Enterprise UI styling (frontend/css/themes.css, frontend/css/styles.css) including
   pixel-art crisp rendering, Light Mode (executive-paper) normalization, and removal of
   conflicting legacy :root overrides.
5. Header quick theme switcher & IRIS Vault Reference Modal in frontend/index.html & app.js.
"""

import json
import pathlib
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT_DIR / "docs" / "IRIS_MASCOT_ASSET_MANIFEST.json"
FRONTEND_DIR = ROOT_DIR / "frontend"
MASCOT_DIR = FRONTEND_DIR / "assets" / "iris_mascot"


class TestIrisMascotAndEnterpriseUI(unittest.TestCase):
    """Comprehensive verification of the IRIS pixel-art repository and enterprise UI."""

    @classmethod
    def setUpClass(cls) -> None:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            cls.manifest = json.load(f)
        cls.index_html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        cls.app_js = (FRONTEND_DIR / "js" / "app.js").read_text(encoding="utf-8")
        cls.mascot_js = (FRONTEND_DIR / "js" / "core" / "mascot_repository.js").read_text(encoding="utf-8")
        cls.themes_css = (FRONTEND_DIR / "css" / "themes.css").read_text(encoding="utf-8")
        cls.styles_css = (FRONTEND_DIR / "css" / "styles.css").read_text(encoding="utf-8")

    def _resolve_web_path(self, web_path: str) -> pathlib.Path:
        rel = web_path.lstrip("/")
        return FRONTEND_DIR / rel

    def test_01_manifest_schema_and_metadata(self) -> None:
        """Verify manifest top-level schema version, character ID, and LucasArts style descriptor."""
        self.assertEqual(self.manifest.get("schema_version"), "3.0.0")
        self.assertEqual(self.manifest.get("character_id"), "iris_sentinel_v3")
        self.assertIn("The Dig", self.manifest.get("art_style", ""))
        self.assertIn("pixelated", self.manifest.get("visual_signature", {}).get("rendering_css", ""))

    def test_02_base_reference_assets_exist_and_non_empty(self) -> None:
        """Verify 00_base_reference contains both the master digital skin-suit turnaround and user reference."""
        base_refs = self.manifest.get("base_references", [])
        self.assertEqual(len(base_refs), 2)
        ids = {item["id"] for item in base_refs}
        self.assertIn("base_skinsuit_turnaround", ids)
        self.assertIn("user_reference_concept", ids)
        for item in base_refs:
            disk_path = self._resolve_web_path(item["path"])
            self.assertTrue(disk_path.is_file(), f"Missing base reference file: {disk_path}")
            self.assertGreater(disk_path.stat().st_size, 1024, f"Base reference file too small: {disk_path}")

    def test_03_four_operational_poses_exist_and_non_empty(self) -> None:
        """Verify all 4 operational poses in 01_poses exist on disk and are valid images."""
        poses = self.manifest.get("poses", [])
        self.assertEqual(len(poses), 4)
        expected_ids = {
            "pose_neutral_standing",
            "pose_analytical_console",
            "pose_alert_defensive",
            "pose_diagnostic_repair",
        }
        self.assertEqual({p["id"] for p in poses}, expected_ids)
        for pose in poses:
            disk_path = self._resolve_web_path(pose["path"])
            self.assertTrue(disk_path.is_file(), f"Missing pose file: {disk_path}")
            self.assertGreater(disk_path.stat().st_size, 1024)

    def test_04_four_outfit_overlays_exist_and_non_empty(self) -> None:
        """Verify all 4 outfit overlays in 02_outfits exist on disk and are valid images."""
        outfits = self.manifest.get("outfits", [])
        self.assertEqual(len(outfits), 4)
        expected_ids = {
            "outfit_digital_skinsuit",
            "outfit_field_tactical",
            "outfit_lab_chief_coat",
            "outfit_eva_astronaut_rig",
        }
        self.assertEqual({o["id"] for o in outfits}, expected_ids)
        for outfit in outfits:
            disk_path = self._resolve_web_path(outfit["path"])
            self.assertTrue(disk_path.is_file(), f"Missing outfit file: {disk_path}")
            self.assertGreater(disk_path.stat().st_size, 1024)

    def test_05_expression_matrix_covers_four_categories_and_three_degrees(self) -> None:
        """Verify expression_matrix defines 4 emotion categories x 3 severity degrees (12 states)."""
        matrix = self.manifest.get("expression_matrix", {})
        self.assertEqual(set(matrix.keys()), {"nominal", "guidance", "warning", "critical"})
        for category, spec in matrix.items():
            sheet_path = self._resolve_web_path(spec["sheet_path"])
            self.assertTrue(sheet_path.is_file(), f"Missing 3-degree sheet for {category}: {sheet_path}")
            self.assertGreater(sheet_path.stat().st_size, 1024)
            degrees = spec.get("degrees", [])
            self.assertEqual(len(degrees), 3, f"Category {category} must have exactly 3 degrees")
            self.assertEqual([d["degree"] for d in degrees], [1, 2, 3])

    def test_06_twelve_individual_degree_portraits_exist_on_disk(self) -> None:
        """Verify all 12 sliced individual degree portraits exist in 03_expressions/."""
        matrix = self.manifest.get("expression_matrix", {})
        count = 0
        for spec in matrix.values():
            for deg in spec["degrees"]:
                portrait_path = MASCOT_DIR / "03_expressions" / f"{deg['id']}.png"
                self.assertTrue(portrait_path.is_file(), f"Missing individual degree portrait: {portrait_path}")
                self.assertGreater(portrait_path.stat().st_size, 1024)
                count += 1
        self.assertEqual(count, 12)

    def test_07_six_contextual_ui_avatars_exist_on_disk(self) -> None:
        """Verify all 6 contextual UI avatars in 04_avatars exist on disk."""
        avatars = self.manifest.get("contextual_avatars", {})
        expected_keys = {"nominal", "scanning", "guidance", "stats", "warning", "critical"}
        self.assertEqual(set(avatars.keys()), expected_keys)
        for key, spec in avatars.items():
            disk_path = self._resolve_web_path(spec["path"])
            self.assertTrue(disk_path.is_file(), f"Missing contextual avatar for {key}: {disk_path}")
            self.assertGreater(disk_path.stat().st_size, 1024)

    def test_08_png_headers_valid_for_generated_repository_assets(self) -> None:
        """Verify PNG files in the repository have valid PNG or JPEG magic bytes."""
        png_files = list(MASCOT_DIR.rglob("*.png"))
        self.assertGreaterEqual(len(png_files), 30)
        for png in png_files:
            header = png.read_bytes()[:8]
            is_png = header == b"\x89PNG\r\n\x1a\n"
            is_jpg = header[:3] == b"\xff\xd8\xff"
            self.assertTrue(is_png or is_jpg, f"Invalid image header in {png}")

    def test_09_mascot_repository_js_exposes_canonical_api(self) -> None:
        """Verify frontend/js/core/mascot_repository.js defines MascotRepository and helpers."""
        self.assertIn("MascotRepository", self.mascot_js)
        self.assertIn("resolveContextualAvatar", self.mascot_js)
        self.assertIn("resolveExpressionSeverity", self.mascot_js)
        self.assertIn("global.IRISMascot = MascotRepository", self.mascot_js)

    def test_10_mascot_repository_js_includes_all_12_degree_paths(self) -> None:
        """Verify mascot_repository.js maps all 12 individual degree portrait paths."""
        expected_degree_ids = [
            "nominal_deg1_serene", "nominal_deg2_focused", "nominal_deg3_optimal",
            "guidance_deg1_curious", "guidance_deg2_advising", "guidance_deg3_eureka",
            "warning_deg1_concerned", "warning_deg2_urgent", "warning_deg3_brace",
            "critical_deg1_retry", "critical_deg2_ratelimit", "critical_deg3_overload",
        ]
        for deg_id in expected_degree_ids:
            self.assertIn(deg_id, self.mascot_js, f"Missing degree ID in mascot_repository.js: {deg_id}")

    def test_11_themes_css_defines_pixel_art_rendering_classes(self) -> None:
        """Verify themes.css defines .pixel-art-asset and .iris-pixel-img with crisp pixel rendering."""
        self.assertIn(".pixel-art-asset", self.themes_css)
        self.assertIn(".iris-pixel-img", self.themes_css)
        self.assertIn("image-rendering: pixelated", self.themes_css)

    def test_12_themes_css_defines_light_mode_executive_paper_normalization(self) -> None:
        """Verify themes.css normalizes form controls, headings, and modals in executive-paper light theme."""
        self.assertIn('[data-theme="executive-paper"]', self.themes_css)
        self.assertIn('[data-theme="executive-paper"] input', self.themes_css)
        self.assertIn('[data-theme="executive-paper"] .modal-box', self.themes_css)
        self.assertIn("color-scheme: light", self.themes_css)

    def test_13_styles_css_does_not_override_theme_root_variables(self) -> None:
        """Verify styles.css no longer re-declares conflicting hardcoded :root dark colors after themes.css."""
        self.assertIn('@import "themes.css";', self.styles_css)
        self.assertNotIn("--bg-dark: #080b11;", self.styles_css)
        self.assertNotIn("radial-gradient(circle at 12% 0%", self.styles_css)

    def test_14_index_html_loads_mascot_repository_core_script(self) -> None:
        """Verify frontend/index.html loads js/core/mascot_repository.js before js/app.js."""
        pos_mascot = self.index_html.find('js/core/mascot_repository.js')
        pos_app = self.index_html.find('js/app.js')
        self.assertNotEqual(pos_mascot, -1, "mascot_repository.js not loaded in index.html")
        self.assertLess(pos_mascot, pos_app, "mascot_repository.js must load before app.js")

    def test_15_index_html_includes_header_quick_theme_selector(self) -> None:
        """Verify frontend/index.html includes #header-quick-theme-select with both Dark and Light themes."""
        self.assertIn('id="header-quick-theme-select"', self.index_html)
        self.assertIn('value="linear-obsidian"', self.index_html)
        self.assertIn('value="geist-monochrome"', self.index_html)
        self.assertIn('value="executive-paper"', self.index_html)

    def test_16_index_html_navigation_tabs_are_clean_enterprise_typography(self) -> None:
        """Verify main navigation buttons use clean enterprise labels without noisy decorative emojis."""
        self.assertIn('data-tab="dashboard">Dashboard</button>', self.index_html)
        self.assertIn('data-tab="capacity">Capacity &amp; Velocity</button>', self.index_html)
        self.assertIn('data-tab="settings">Settings</button>', self.index_html)

    def test_17_index_html_includes_iris_vault_and_expression_matrix_modal(self) -> None:
        """Verify #icon-picker-modal showcases the turnaround sheet, poses, outfits, and 3-degree expression matrix."""
        self.assertIn('id="icon-picker-modal"', self.index_html)
        self.assertIn("iris_base_skinsuit_turnaround.png", self.index_html)
        self.assertIn("expressions_nominal_3degrees.png", self.index_html)
        self.assertIn("expressions_guidance_3degrees.png", self.index_html)
        self.assertIn("expressions_warning_3degrees.png", self.index_html)
        self.assertIn("expressions_critical_3degrees.png", self.index_html)

    def test_18_index_html_mascot_banner_uses_contextual_iris_sentinel_elements(self) -> None:
        """Verify the dashboard banner includes #mascot-main-img, #mascot-status-tag, and #mascot-quote-text."""
        self.assertIn('id="mascot-main-img"', self.index_html)
        self.assertIn('id="mascot-status-tag"', self.index_html)
        self.assertIn('id="mascot-quote-text"', self.index_html)

    def test_19_app_js_wires_update_contextual_iris_avatar(self) -> None:
        """Verify app.js defines updateContextualIrisAvatar and calls it on dashboard/error/tab updates."""
        self.assertIn("updateContextualIrisAvatar(contextKey", self.app_js)
        self.assertIn("MascotRepository", self.app_js)
        self.assertIn("resolveContextualAvatar", self.app_js)

    def test_20_app_js_wires_quick_theme_switch_and_syncs_header_select(self) -> None:
        """Verify app.js defines selectThemeSwatch and keeps #header-quick-theme-select synchronized."""
        self.assertIn("selectThemeSwatch(themeId)", self.app_js)
        self.assertIn("header-quick-theme-select", self.app_js)

    def test_21_app_js_uses_contextual_iris_avatars_for_empty_and_healthy_states(self) -> None:
        """Verify renderSessions and renderErrors use IRIS pixel-art avatars from /assets/iris_mascot/04_avatars/."""
        self.assertIn("/assets/iris_mascot/04_avatars/avatar_scanning_idle.png", self.app_js)
        self.assertIn("/assets/iris_mascot/04_avatars/avatar_nominal_healthy.png", self.app_js)

    def test_22_legacy_icon_paths_Remain_populated_for_backward_compatibility(self) -> None:
        """Verify legacy /assets/icons/ and /assets/mascot/ files exist on disk."""
        self.assertTrue((FRONTEND_DIR / "assets" / "icons" / "app_icon_iris.png").is_file())
        self.assertTrue((FRONTEND_DIR / "assets" / "icons" / "app_icon_johnny5.jpg").is_file())
        self.assertTrue((FRONTEND_DIR / "assets" / "mascot" / "johnny5_success.jpg").is_file())
        self.assertTrue((FRONTEND_DIR / "assets" / "mascot" / "johnny5_pointing.jpg").is_file())
        self.assertTrue((FRONTEND_DIR / "assets" / "mascot" / "johnny5_inspecting.jpg").is_file())


if __name__ == "__main__":
    unittest.main()
