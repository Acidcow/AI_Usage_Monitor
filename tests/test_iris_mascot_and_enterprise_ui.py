"""
Unit tests for the v3.1 Enterprise UI Overhaul and IRIS Pixel-Art Mascot Reference Repository.

Verifies:
1. Canonical IRIS Mascot Asset Manifest (docs/IRIS_MASCOT_ASSET_MANIFEST.json) schema v3.1.0 & copyright-clean 00_base_reference.
2. Physical file existence and non-zero integrity for all pixel-art assets across:
   - 00_base_reference/ (100% original turnaround: Royal-Blue hair, Sports Bra & Boy-Shorts, Deus-Ex Cyber Arm; no external concept file)
   - 01_poses/ (4 full-body operational poses)
   - 02_outfits/ (4 outfit overlays)
   - 03_expressions/ (4 3-degree sheets + 12 individual degree portraits)
   - 04_avatars/ (6 contextual 1:1 UI avatars)
   - 05_animations/ (4 multi-frame looping GIF89a animated pixel-art GIFs)
3. Selectable Windows Task Manager & System Tray Application Icons (iris_head, iris_eye, iris_cyber_arm, iris_holo) in backend.tray.icon_factory.
4. Full-Character Interactive Stage (#mascot-full-stage-img), hover/busy GIF triggers, and modal thumbnail icons in frontend/index.html & app.js.
"""

import json
import pathlib
import sys
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

MANIFEST_PATH = ROOT_DIR / "docs" / "IRIS_MASCOT_ASSET_MANIFEST.json"
FRONTEND_DIR = ROOT_DIR / "frontend"
MASCOT_DIR = FRONTEND_DIR / "assets" / "iris_mascot"


class TestIrisMascotAndEnterpriseUI(unittest.TestCase):
    """Comprehensive verification of the IRIS v3.1 pixel-art repository, animated GIFs, tray icons, and enterprise UI."""

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

    def test_01_manifest_schema_and_royal_blue_deus_ex_signature(self) -> None:
        """Verify manifest top-level schema version 3.1.0, royal-blue hair, sports bra/boy-shorts, and Deus-Ex cyber arm."""
        self.assertEqual(self.manifest.get("schema_version"), "3.1.0")
        self.assertEqual(self.manifest.get("character_id"), "iris_sentinel_v3")
        sig = self.manifest.get("visual_signature", {})
        self.assertIn("royal-blue", sig.get("hair", "").lower())
        self.assertIn("deus-ex", sig.get("cybernetic_arm", "").lower())
        self.assertIn("sports bra", sig.get("base_attire", "").lower())
        self.assertIn("boy-shorts", sig.get("base_attire", "").lower())
        self.assertIn("dimpled smile", sig.get("demeanor", "").lower())

    def test_02_base_reference_is_clean_and_original_only(self) -> None:
        """Verify 00_base_reference contains only the 100% original turnaround and no external user_reference_concept.jpg."""
        base_refs = self.manifest.get("base_references", [])
        self.assertEqual(len(base_refs), 1)
        self.assertEqual(base_refs[0]["id"], "base_skinsuit_turnaround")
        disk_path = self._resolve_web_path(base_refs[0]["path"])
        self.assertTrue(disk_path.is_file(), f"Missing base reference file: {disk_path}")
        self.assertGreater(disk_path.stat().st_size, 1024)
        external_ref = MASCOT_DIR / "00_base_reference" / "user_reference_concept.jpg"
        self.assertFalse(external_ref.exists(), "External concept image must not exist in repository")

    def test_03_four_operational_poses_exist_and_define_hover_gifs(self) -> None:
        """Verify all 4 operational poses in 01_poses exist on disk and map to hover GIFs."""
        poses = self.manifest.get("poses", [])
        self.assertEqual(len(poses), 4)
        for pose in poses:
            disk_path = self._resolve_web_path(pose["path"])
            self.assertTrue(disk_path.is_file(), f"Missing pose file: {disk_path}")
            self.assertGreater(disk_path.stat().st_size, 1024)
            gif_path = self._resolve_web_path(pose["hover_gif"])
            self.assertTrue(gif_path.is_file(), f"Missing hover GIF for pose: {gif_path}")

    def test_04_four_outfit_overlays_exist_and_non_empty(self) -> None:
        """Verify all 4 outfit overlays in 02_outfits exist on disk and are valid images."""
        outfits = self.manifest.get("outfits", [])
        self.assertEqual(len(outfits), 4)
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
            self.assertEqual([d["degree"] for d in spec.get("degrees", [])], [1, 2, 3])

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
        self.assertEqual(set(avatars.keys()), {"nominal", "scanning", "guidance", "stats", "warning", "critical"})
        for key, spec in avatars.items():
            disk_path = self._resolve_web_path(spec["path"])
            self.assertTrue(disk_path.is_file(), f"Missing contextual avatar for {key}: {disk_path}")
            self.assertGreater(disk_path.stat().st_size, 1024)

    def test_08_four_looping_animated_gifs_exist_and_have_gif89a_netscape_headers(self) -> None:
        """Verify all 4 animated GIFs in 05_animations/ are valid multi-frame looping GIF89a files."""
        anims = self.manifest.get("animations", {})
        self.assertEqual(set(anims.keys()), {"idle_wink", "loading_scan", "busy_processing", "alert_pulse"})
        for key, spec in anims.items():
            gif_path = self._resolve_web_path(spec["path"])
            self.assertTrue(gif_path.is_file(), f"Missing animated GIF for {key}: {gif_path}")
            raw = gif_path.read_bytes()
            self.assertGreater(len(raw), 4096)
            self.assertTrue(raw.startswith(b"GIF89a"), f"Invalid GIF89a header in {gif_path}")
            self.assertIn(b"NETSCAPE2.0", raw, f"Missing NETSCAPE2.0 infinite loop extension in {gif_path}")

    def test_09_four_selectable_windows_tray_and_task_manager_icons(self) -> None:
        """Verify icon_factory generates all 4 selectable .ico + .png files and loads Win32 HICON handles."""
        from backend.tray.icon_factory import (
            ensure_ico_assets,
            get_tray_icon_handle,
            resolve_icon_ico_path,
            apply_process_and_window_icon,
            CANONICAL_ICON_CHOICES,
        )
        ensure_ico_assets()
        self.assertEqual(len(CANONICAL_ICON_CHOICES), 4)
        for choice in CANONICAL_ICON_CHOICES:
            ico_path = resolve_icon_ico_path(choice["id"])
            self.assertTrue(ico_path.is_file(), f"Missing .ico for {choice['id']}: {ico_path}")
            self.assertGreater(ico_path.stat().st_size, 500)
            png_path = self._resolve_web_path(choice["preview"])
            self.assertTrue(png_path.is_file(), f"Missing .png preview for {choice['id']}: {png_path}")
            if sys.platform == "win32":
                hicon = get_tray_icon_handle(choice["id"])
                self.assertIsNotNone(hicon)

        # Also verify apply_process_and_window_icon executes cleanly
        apply_process_and_window_icon("iris_head")

    def test_10_mascot_repository_js_exposes_canonical_api_and_gif_resolver(self) -> None:
        """Verify frontend/js/core/mascot_repository.js defines MascotRepository, resolveAnimatedGif, and helpers."""
        self.assertIn("MascotRepository", self.mascot_js)
        self.assertIn("resolveContextualAvatar", self.mascot_js)
        self.assertIn("resolveAnimatedGif", self.mascot_js)
        self.assertIn("resolveExpressionSeverity", self.mascot_js)
        self.assertIn("global.IRISMascot = MascotRepository", self.mascot_js)

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

    def test_13_styles_css_defines_full_character_stage_classes(self) -> None:
        """Verify styles.css defines .iris-full-stage-banner, .iris-character-stage, and .iris-full-stage-img."""
        self.assertIn(".iris-full-stage-banner", self.styles_css)
        self.assertIn(".iris-character-stage", self.styles_css)
        self.assertIn(".iris-full-stage-img", self.styles_css)

    def test_14_index_html_loads_mascot_repository_core_script(self) -> None:
        """Verify frontend/index.html loads js/core/mascot_repository.js before js/app.js."""
        pos_mascot = self.index_html.find('js/core/mascot_repository.js')
        pos_app = self.index_html.find('js/app.js')
        self.assertNotEqual(pos_mascot, -1)
        self.assertLess(pos_mascot, pos_app)

    def test_15_index_html_features_full_character_stage_and_pose_switcher(self) -> None:
        """Verify frontend/index.html features #mascot-full-stage-img, .iris-pose-selector-bar, and hover handlers."""
        self.assertIn('id="mascot-full-stage-img"', self.index_html)
        self.assertIn('class="iris-pose-selector-bar"', self.index_html)
        self.assertIn("window.App.onMascotHover(true)", self.index_html)
        self.assertIn("window.App.setMascotStagePose(", self.index_html)

    def test_16_index_html_includes_four_selectable_app_icon_cards_and_gif_gallery(self) -> None:
        """Verify #icon-picker-modal includes all 4 selectable app icon cards and the 05_animations GIF gallery."""
        self.assertIn("selectAppIcon('iris_head')", self.index_html)
        self.assertIn("selectAppIcon('iris_eye')", self.index_html)
        self.assertIn("selectAppIcon('iris_cyber_arm')", self.index_html)
        self.assertIn("selectAppIcon('iris_holo')", self.index_html)
        self.assertIn("anim_idle_wink_smile.gif", self.index_html)
        self.assertIn("anim_loading_scan.gif", self.index_html)
        self.assertIn("anim_busy_processing.gif", self.index_html)
        self.assertIn("anim_alert_pulse.gif", self.index_html)
        self.assertNotIn("user_reference_concept.jpg", self.index_html)

    def test_17_app_js_wires_hover_busy_and_stage_pose_methods(self) -> None:
        """Verify app.js defines onMascotHover, setIrisBusyState, setMascotStagePose, and previewBusyAnimation."""
        self.assertIn("onMascotHover(isHovering)", self.app_js)
        self.assertIn("setIrisBusyState(isBusy", self.app_js)
        self.assertIn("setMascotStagePose(poseSrc", self.app_js)
        self.assertIn("previewBusyAnimation()", self.app_js)

    def test_18_http_server_and_native_widget_sync_active_icon(self) -> None:
        """Verify http_server.py and native_widget.py call apply_process_and_window_icon when active_icon updates."""
        http_srv = (ROOT_DIR / "backend" / "server" / "http_server.py").read_text(encoding="utf-8")
        native_wdg = (ROOT_DIR / "backend" / "tray" / "native_widget.py").read_text(encoding="utf-8")
        self.assertIn("apply_process_and_window_icon", http_srv)
        self.assertIn("apply_process_and_window_icon", native_wdg)


if __name__ == "__main__":
    unittest.main()
