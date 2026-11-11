"""
Unit Test Suite for Ultra-Modern Selectable Themes & Layout Density Engine (AIUM-1008)
Verifies:
- Canonical theme catalog, legacy aliases, and contracts
- WCAG AA contrast ratio compliance (>= 4.5:1)
- REST API GET /api/themes response schema
- CSS stylesheets and mini widget HTML integration
- Native Taskbar Widget theme resolution and HiDPI font enforcement
"""

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.contracts.themes import (
    CANONICAL_THEME_IDS,
    THEMES_CATALOG,
    THEME_ALIASES,
    LAYOUT_DENSITIES,
    LAYOUT_DENSITY_CONFIGS,
    PROVIDER_PALETTE,
    resolve_theme_id,
    get_theme,
    get_all_themes,
    calculate_relative_luminance,
    calculate_contrast_ratio,
    meets_wcag_aa,
    ThemeDict,
)
from backend.server.http_server import AppHTTPRequestHandler
from backend.tray.native_widget import NativeTaskbarWidget, THEMES, PROVIDER_COLORS

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestUltraModernThemeEngine(unittest.TestCase):
    """Deterministic Unit Tests for Ticket AIUM-1008 Theme & Layout Density Engine."""

    # -------------------------------------------------------------------------
    # 1. Canonical Theme Catalog & Contracts Tests
    # -------------------------------------------------------------------------
    def test_01_six_canonical_themes_defined(self):
        """Verify that exactly 6 canonical themes are defined in CANONICAL_THEME_IDS."""
        expected = [
            "linear-obsidian",
            "geist-monochrome",
            "cyberpunk-hud",
            "catppuccin-mocha",
            "tokyo-night",
            "executive-paper",
        ]
        self.assertEqual(CANONICAL_THEME_IDS, expected)

    def test_02_get_all_themes_returns_list_of_six(self):
        """Verify get_all_themes returns the 6 canonical themes in presentation order."""
        themes = get_all_themes()
        self.assertEqual(len(themes), 6)
        ids = [t["id"] for t in themes]
        self.assertEqual(ids, CANONICAL_THEME_IDS)

    def test_03_canonical_theme_required_fields(self):
        """Verify each canonical theme provides all required design-token fields."""
        required_fields = [
            "id", "name", "mode", "bg_main", "bg_card",
            "accent_primary", "text_main", "text_muted", "text_dim", "border_color"
        ]
        for tid in CANONICAL_THEME_IDS:
            t = get_theme(tid)
            for f in required_fields:
                self.assertIn(f, t, f"Field '{f}' missing in theme '{tid}'")
                self.assertTrue(t[f], f"Field '{f}' is empty in theme '{tid}'")

    def test_04_native_widget_compatibility_fields(self):
        """Verify each canonical theme includes Tkinter / native widget compatibility keys."""
        native_keys = [
            "bg", "container_bg", "card_bg", "header_bg", "border",
            "text", "subtext", "accent", "cyan", "accent2", "success", "danger", "strip_bg"
        ]
        for tid in CANONICAL_THEME_IDS:
            t = get_theme(tid)
            for k in native_keys:
                self.assertIn(k, t, f"Native key '{k}' missing in theme '{tid}'")
                self.assertTrue(t[k], f"Native key '{k}' is empty in theme '{tid}'")

    def test_05_theme_dict_attribute_and_item_access(self):
        """Verify ThemeDict allows both item indexing and attribute access."""
        theme = get_theme("linear-obsidian")
        self.assertIsInstance(theme, ThemeDict)
        self.assertEqual(theme["id"], theme.id)
        self.assertEqual(theme["accent_primary"], theme.accent_primary)
        self.assertEqual(theme["bg_main"], theme.bg_main)
        self.assertEqual(theme.to_dict()["id"], "linear-obsidian")

    # -------------------------------------------------------------------------
    # 2. Backward-Compatible Aliases Tests
    # -------------------------------------------------------------------------
    def test_06_legacy_theme_alias_cyberpunk_dark(self):
        """Verify cyberpunk_dark resolves to cyberpunk-hud."""
        self.assertEqual(resolve_theme_id("cyberpunk_dark"), "cyberpunk-hud")
        t = get_theme("cyberpunk_dark")
        self.assertEqual(t["id"], "cyberpunk-hud")

    def test_07_legacy_theme_alias_glass_slate(self):
        """Verify glass_slate resolves to linear-obsidian."""
        self.assertEqual(resolve_theme_id("glass_slate"), "linear-obsidian")
        t = get_theme("glass_slate")
        self.assertEqual(t["id"], "linear-obsidian")

    def test_08_legacy_theme_alias_high_contrast_light(self):
        """Verify high_contrast_light resolves to executive-paper."""
        self.assertEqual(resolve_theme_id("high_contrast_light"), "executive-paper")
        t = get_theme("high_contrast_light")
        self.assertEqual(t["id"], "executive-paper")

    def test_09_legacy_theme_alias_matrix_emerald(self):
        """Verify matrix_emerald resolves to geist-monochrome."""
        self.assertEqual(resolve_theme_id("matrix_emerald"), "geist-monochrome")
        t = get_theme("matrix_emerald")
        self.assertEqual(t["id"], "geist-monochrome")

    def test_10_legacy_tray_aliases(self):
        """Verify legacy tray widget aliases resolve properly."""
        self.assertEqual(resolve_theme_id("obsidian_neon"), "linear-obsidian")
        self.assertEqual(resolve_theme_id("cyberpunk"), "cyberpunk-hud")
        self.assertEqual(resolve_theme_id("midnight_slate"), "tokyo-night")

    def test_11_unknown_and_none_theme_resolves_default(self):
        """Verify unknown or None theme resolves to linear-obsidian."""
        self.assertEqual(resolve_theme_id(None), "linear-obsidian")
        self.assertEqual(resolve_theme_id(""), "linear-obsidian")
        self.assertEqual(resolve_theme_id("non-existent-theme-xyz"), "linear-obsidian")

    # -------------------------------------------------------------------------
    # 3. WCAG AA Contrast Compliance Tests
    # -------------------------------------------------------------------------
    def test_12_wcag_aa_contrast_ratio_text_main(self):
        """Verify WCAG AA contrast ratio (>= 4.5:1) between bg_main and text_main for all 6 themes."""
        for t in get_all_themes():
            ratio = calculate_contrast_ratio(t.text_main, t.bg_main)
            self.assertGreaterEqual(
                ratio, 4.5,
                f"Theme '{t.id}' text_main contrast ratio {ratio:.2f}:1 is below 4.5:1"
            )

    def test_13_wcag_aa_contrast_ratio_text_muted(self):
        """Verify WCAG AA contrast ratio (>= 4.5:1) between bg_main and text_muted for all 6 themes."""
        for t in get_all_themes():
            ratio = calculate_contrast_ratio(t.text_muted, t.bg_main)
            self.assertGreaterEqual(
                ratio, 4.5,
                f"Theme '{t.id}' text_muted contrast ratio {ratio:.2f}:1 is below 4.5:1"
            )

    def test_14_wcag_aa_contrast_ratio_text_dim(self):
        """Verify WCAG AA contrast ratio (>= 4.5:1) between bg_main and text_dim for all 6 themes."""
        for t in get_all_themes():
            ratio = calculate_contrast_ratio(t.text_dim, t.bg_main)
            self.assertGreaterEqual(
                ratio, 4.5,
                f"Theme '{t.id}' text_dim contrast ratio {ratio:.2f}:1 is below 4.5:1"
            )

    def test_15_wcag_contrast_calculation_helpers(self):
        """Verify relative luminance and contrast ratio calculations on known benchmarks."""
        # Pure black and pure white has contrast ratio 21.0
        black_lum = calculate_relative_luminance("#000000")
        white_lum = calculate_relative_luminance("#FFFFFF")
        self.assertAlmostEqual(black_lum, 0.0, places=4)
        self.assertAlmostEqual(white_lum, 1.0, places=4)
        ratio = calculate_contrast_ratio("#FFFFFF", "#000000")
        self.assertAlmostEqual(ratio, 21.0, places=1)
        self.assertTrue(meets_wcag_aa("#FFFFFF", "#000000"))
        # Same color has 1.0 contrast ratio and fails WCAG AA
        self.assertAlmostEqual(calculate_contrast_ratio("#FFFFFF", "#FFFFFF"), 1.0, places=2)
        self.assertFalse(meets_wcag_aa("#888888", "#888888"))

    # -------------------------------------------------------------------------
    # 4. Layout Densities & Provider Palette Constants
    # -------------------------------------------------------------------------
    def test_16_layout_densities_constant(self):
        """Verify LAYOUT_DENSITIES contains compact, balanced, and ultrawide."""
        self.assertIn("compact", LAYOUT_DENSITIES)
        self.assertIn("balanced", LAYOUT_DENSITIES)
        self.assertIn("ultrawide", LAYOUT_DENSITIES)
        self.assertEqual(len(LAYOUT_DENSITIES), 3)

    def test_17_provider_palette_constant(self):
        """Verify canonical PROVIDER_PALETTE hex codes match specification."""
        self.assertEqual(PROVIDER_PALETTE["claude"], "#F59E0B")
        self.assertEqual(PROVIDER_PALETTE["ollama"], "#10B981")
        self.assertEqual(PROVIDER_PALETTE["gemini"], "#3B82F6")
        self.assertEqual(PROVIDER_PALETTE["copilot"], "#8B5CF6")
        self.assertEqual(PROVIDER_PALETTE["chatgpt"], "#10B981")

    # -------------------------------------------------------------------------
    # 5. REST API GET /api/themes Endpoint Test
    # -------------------------------------------------------------------------
    def test_18_http_themes_endpoint_response_structure(self):
        """Verify GET /api/themes returns expected JSON structure."""
        handler = AppHTTPRequestHandler.__new__(AppHTTPRequestHandler)
        handler.server = MagicMock()
        sent_status = None
        sent_data = None

        def mock_send_json(status, data):
            nonlocal sent_status, sent_data
            sent_status = status
            sent_data = data

        handler._send_json = mock_send_json
        handler._handle_api_get("/api/themes", {})

        self.assertEqual(sent_status, 200)
        self.assertIsNotNone(sent_data)
        self.assertIn("themes", sent_data)
        self.assertIn("densities", sent_data)
        self.assertIn("providers", sent_data)
        self.assertEqual(len(sent_data["themes"]), 6)
        self.assertEqual(sent_data["densities"], LAYOUT_DENSITIES)
        self.assertEqual(sent_data["providers"], PROVIDER_PALETTE)

    # -------------------------------------------------------------------------
    # 6. CSS Stylesheets & Mini Widget Integration Tests
    # -------------------------------------------------------------------------
    def test_19_themes_css_file_selectors(self):
        """Verify frontend/css/themes.css exists and defines theme and density selectors."""
        themes_css_path = REPO_ROOT / "frontend" / "css" / "themes.css"
        self.assertTrue(themes_css_path.exists(), "frontend/css/themes.css does not exist")
        content = themes_css_path.read_text(encoding="utf-8")

        for tid in CANONICAL_THEME_IDS:
            self.assertIn(f'[data-theme="{tid}"]', content)
        for alias in ["cyberpunk_dark", "glass_slate", "high_contrast_light", "matrix_emerald"]:
            self.assertIn(f'[data-theme="{alias}"]', content)
        for density in ["compact", "balanced", "ultrawide"]:
            self.assertIn(f'[data-density="{density}"]', content)

    def test_20_styles_css_imports_and_wcag_dim_contrast(self):
        """Verify frontend/css/styles.css imports themes.css and ensures --text-dim >= 4.5:1 on #080b11."""
        styles_css_path = REPO_ROOT / "frontend" / "css" / "styles.css"
        self.assertTrue(styles_css_path.exists())
        content = styles_css_path.read_text(encoding="utf-8")
        self.assertIn('themes.css', content)
        self.assertIn('--text-dim: #8b95a5', content.lower())
        self.assertIn('--provider-claude: #f59e0b', content.lower())

        # Validate WCAG AA contrast of #8B95A5 against #080B11
        contrast = calculate_contrast_ratio("#8B95A5", "#080B11")
        self.assertGreaterEqual(contrast, 4.5, f"Contrast {contrast:.2f} is below WCAG AA 4.5:1")

    def test_21_widget_css_file_structure(self):
        """Verify frontend/css/widget.css exists and contains widget styling rules."""
        widget_css_path = REPO_ROOT / "frontend" / "css" / "widget.css"
        self.assertTrue(widget_css_path.exists(), "frontend/css/widget.css does not exist")
        content = widget_css_path.read_text(encoding="utf-8")
        self.assertIn(".widget-container", content)
        self.assertIn(".widget-btn", content)
        self.assertIn("#bucket-select", content)
        self.assertIn("#scope-select", content)

    def test_22_mini_widget_html_links_and_scripts(self):
        """Verify frontend/mini_widget.html links themes.css, widget.css, and loads core scripts."""
        html_path = REPO_ROOT / "frontend" / "mini_widget.html"
        self.assertTrue(html_path.exists())
        content = html_path.read_text(encoding="utf-8")

        self.assertIn("css/themes.css", content)
        self.assertIn("css/widget.css", content)

        # Core scripts must be linked before widget.js
        idx_fmt = content.find("js/core/formatters.js")
        idx_api = content.find("js/core/api_client.js")
        idx_crt = content.find("js/core/chart_renderer.js")
        idx_tlm = content.find("js/core/telemetry_hierarchy.js")
        idx_wdg = content.find("js/widget.js")

        self.assertNotEqual(idx_fmt, -1, "js/core/formatters.js not found in mini_widget.html")
        self.assertNotEqual(idx_api, -1, "js/core/api_client.js not found in mini_widget.html")
        self.assertNotEqual(idx_crt, -1, "js/core/chart_renderer.js not found in mini_widget.html")
        self.assertNotEqual(idx_tlm, -1, "js/core/telemetry_hierarchy.js not found in mini_widget.html")
        self.assertNotEqual(idx_wdg, -1, "js/widget.js not found in mini_widget.html")

        self.assertLess(idx_fmt, idx_wdg)
        self.assertLess(idx_api, idx_wdg)
        self.assertLess(idx_crt, idx_wdg)
        self.assertLess(idx_tlm, idx_wdg)

    def test_23_mini_widget_html_bucket_and_scope_selectors(self):
        """Verify frontend/mini_widget.html contains #bucket-select and #scope-select elements."""
        html_path = REPO_ROOT / "frontend" / "mini_widget.html"
        content = html_path.read_text(encoding="utf-8")
        self.assertIn('id="bucket-select"', content)
        self.assertIn('id="scope-select"', content)

    # -------------------------------------------------------------------------
    # 7. Native Taskbar Floating Widget Integration Tests
    # -------------------------------------------------------------------------
    def test_24_native_widget_themes_catalog_integration(self):
        """Verify NativeTaskbarWidget THEMES dictionary contains all 6 themes and 4 legacy keys."""
        for tid in CANONICAL_THEME_IDS:
            self.assertIn(tid, THEMES, f"Canonical theme '{tid}' not present in native widget THEMES")
        for legacy_key in ["obsidian_neon", "cyberpunk", "matrix_emerald", "midnight_slate"]:
            self.assertIn(legacy_key, THEMES, f"Legacy key '{legacy_key}' not present in native widget THEMES")

    def test_25_native_widget_hidpi_minimum_font_size(self):
        """Verify NativeTaskbarWidget enforces a minimum font size of 9pt on HiDPI displays."""
        widget = NativeTaskbarWidget()
        widget.font_scale = "small"  # Normally subtracts 1 from base size

        # Non-HiDPI mode: size 7 - 1 = 6 (clamped at 6)
        widget._is_hidpi = lambda: False
        font_normal = widget._get_font(7)
        self.assertEqual(font_normal[1], 6)

        # HiDPI mode: size must be enforced to >= 9
        widget._is_hidpi = lambda: True
        font_hidpi = widget._get_font(7)
        self.assertGreaterEqual(font_hidpi[1], 9, "Font size was not clamped to >= 9pt on HiDPI")

    def test_26_native_widget_apply_theme_alias_resolution(self):
        """Verify apply_theme resolves aliases and sets theme_name cleanly."""
        widget = NativeTaskbarWidget()
        widget.apply_theme("cyberpunk_dark")
        self.assertEqual(widget.theme_name, "cyberpunk-hud")
        self.assertEqual(widget.theme["accent"], "#00F0FF")

        widget.apply_theme("glass_slate")
        self.assertEqual(widget.theme_name, "linear-obsidian")
        self.assertEqual(widget.theme["accent"], "#5E6AD2")


if __name__ == "__main__":
    unittest.main()
