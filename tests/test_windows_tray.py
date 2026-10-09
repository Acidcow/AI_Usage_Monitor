import unittest
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.tray.windows_tray import WindowsTrayManager

class TestWindowsTray(unittest.TestCase):
    def test_tray_initialization_and_tooltip(self):
        called = {"sync": False}
        def on_sync():
            called["sync"] = True

        tray = WindowsTrayManager(
            app_name="Test AI Monitor",
            on_sync_now=on_sync
        )
        # Should initialize without error
        tray.start()
        time.sleep(0.1)

        # Update tooltip
        tray.update_tooltip("Test AI Monitor\nTokens: 10,000")
        self.assertIn("Tokens: 10,000", tray._tooltip)

        tray.stop()

    def test_tray_menu_commands(self):
        called = {"dashboard": False, "widget": False, "sync": False, "settings": False}
        def on_dash():
            called["dashboard"] = True
        def on_widget():
            called["widget"] = True
        def on_sync():
            called["sync"] = True
        def on_settings():
            called["settings"] = True

        tray = WindowsTrayManager(
            app_name="Test AI Monitor Commands",
            on_open_dashboard=on_dash,
            on_open_widget=on_widget,
            on_sync_now=on_sync,
            on_open_settings=on_settings
        )
        tray.start()
        time.sleep(0.15)

        if sys.platform == "win32" and tray._hwnd:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            WM_COMMAND = 0x0111
            CMD_DASHBOARD = 1001
            CMD_WIDGET = 1002
            CMD_SYNC = 1003
            CMD_SETTINGS = 1004

            user32.SendMessageW(tray._hwnd, WM_COMMAND, CMD_DASHBOARD, 0)
            user32.SendMessageW(tray._hwnd, WM_COMMAND, CMD_WIDGET, 0)
            user32.SendMessageW(tray._hwnd, WM_COMMAND, CMD_SYNC, 0)
            user32.SendMessageW(tray._hwnd, WM_COMMAND, CMD_SETTINGS, 0)

            self.assertTrue(called["dashboard"], "Dashboard callback not invoked by WM_COMMAND")
            self.assertTrue(called["widget"], "Widget callback not invoked by WM_COMMAND")
            self.assertTrue(called["sync"], "Sync callback not invoked by WM_COMMAND")
            self.assertTrue(called["settings"], "Settings callback not invoked by WM_COMMAND")

        tray.stop()

    def test_tray_icon_factory_generates_valid_assets_and_handles(self):
        """Assert that icon_factory creates valid .ico files and Win32 HICON handles."""
        from backend.tray.icon_factory import ensure_ico_assets, get_tray_icon_handle
        ensure_ico_assets()

        icons_dir = REPO_ROOT / "frontend" / "assets" / "icons"
        j5_ico = icons_dir / "app_icon_johnny5.ico"
        sh_ico = icons_dir / "app_icon_shield.ico"

        self.assertTrue(j5_ico.exists(), "Johnny 5 .ico file was not generated")
        self.assertTrue(sh_ico.exists(), "Cyber Shield .ico file was not generated")
        self.assertGreater(j5_ico.stat().st_size, 500)
        self.assertGreater(sh_ico.stat().st_size, 500)

        if sys.platform == "win32":
            h_j5 = get_tray_icon_handle("johnny5")
            h_sh = get_tray_icon_handle("shield")
            self.assertIsNotNone(h_j5, "Failed to load Johnny 5 HICON handle")
            self.assertIsNotNone(h_sh, "Failed to load Cyber Shield HICON handle")

    def test_native_taskbar_widget_initialization_and_geometry(self):
        """Assert that the NativeTaskbarWidget initializes and renders without errors."""
        from backend.tray.native_widget import NativeTaskbarWidget
        widget = NativeTaskbarWidget(width=360, height=380)
        x, y = widget.calculate_position()
        self.assertGreater(x, 0)
        self.assertGreater(y, 0)

        widget.build_ui()
        widget.cached_comparison = {
            "providers": {
                "claude": {"tokens_today": 1200, "session_balance_remaining_pct": 85, "weekly_balance_remaining_pct": 92},
                "gemini": {"tokens_today": 3400, "session_balance_remaining_pct": 90, "weekly_balance_remaining_pct": 95},
                "chatgpt": {"tokens_today": 0, "session_balance_remaining_pct": 100, "weekly_balance_remaining_pct": 100},
                "ollama": {"tokens_today": 50000, "session_balance_remaining_pct": 98, "weekly_balance_remaining_pct": 99},
                "copilot": {"tokens_today": 0, "session_balance_remaining_pct": 100, "weekly_balance_remaining_pct": 100}
            },
            "local_savings": {"savings_today_usd": 0.30}
        }
        widget.render_canvas()
        self.assertIsNotNone(widget.canvas)
        self.assertEqual(widget.active_port, widget.port)

        # Test hover flyout creation and scaled geometry
        item = {
            "tokens_today": 6666,
            "tokens_week": 6666,
            "session_balance_remaining_pct": 44.0,
            "session_used_pct": 56.0,
            "weekly_balance_remaining_pct": 74.0,
            "weekly_used_pct": 26.0,
            "weekly_reset_str": "Mon 3:00 AM",
            "cost_today_usd": 0.042
        }
        stat = {"plan_type": "Team Enterprise", "status": "ACTIVE"}
        widget._show_flyout("claude", item, stat)
        self.assertIsNotNone(widget.flyout_window)
        self.assertIsNotNone(widget.flyout_canvas)
        self.assertIsNotNone(widget.flyout_scrollbar)
        widget._hide_flyout()

        widget.close()

    def test_native_widget_themes_pinning_and_view_mode(self):
        """Assert native widget theme customization, right-click pinning, and trends toggle."""
        from backend.tray.native_widget import NativeTaskbarWidget
        widget = NativeTaskbarWidget(width=360, height=380)
        widget.build_ui()

        # 1. Test pinning
        self.assertIn("claude", widget.pinned_items)
        widget.toggle_pin("claude")
        self.assertNotIn("claude", widget.pinned_items)
        widget.toggle_pin("claude")
        self.assertIn("claude", widget.pinned_items)

        # 2. Test themes and font scale
        widget.apply_theme("cyberpunk", 1.25)
        self.assertEqual(widget.theme_name, "cyberpunk")
        self.assertEqual(widget.font_scale, 1.25)
        self.assertEqual(widget.theme["cyan"], "#ec4899")

        # 3. Test view mode toggle
        self.assertEqual(widget.view_mode, "balances")
        widget.toggle_view_mode()
        self.assertEqual(widget.view_mode, "trends")
        widget.toggle_view_mode()
        self.assertEqual(widget.view_mode, "balances")

        # 4. Test sparkline generator
        spark_pts = widget._get_sparkline_points(1500, 10500, width=90, height=22)
        self.assertEqual(len(spark_pts), 7)
        self.assertTrue(all(isinstance(p, tuple) and len(p) == 2 for p in spark_pts))

        widget.close()

    def test_native_widget_strict_visibility_override_and_unpinned_fade(self):
        """Assert that visibility toggle strictly overrides pinning, and unpinned items fade on focus loss."""
        from backend.tray.native_widget import NativeTaskbarWidget
        widget = NativeTaskbarWidget(width=360, height=380)
        widget.build_ui()

        # 1. Strict Visibility Override: Pinned items must never render if hidden
        widget.pinned_items = set(["claude", "gemini", "ollama"])
        widget._apply_settings_from_server({
            "estate_visibility": {
                "hidden_platforms": ["claude", "copilot"]
            }
        })
        self.assertIn("claude", widget.hidden_platforms)
        self.assertIn("copilot", widget.hidden_platforms)

        order = widget.get_providers_order()
        self.assertNotIn("claude", order, "Hidden platform 'claude' must NOT be rendered even if pinned")
        self.assertNotIn("copilot", order, "Hidden platform 'copilot' must NOT be rendered")
        self.assertIn("gemini", order)
        self.assertIn("ollama", order)

        # 2. Focus Loss Unpinned Fade: When unfocused, unpinned items must fade out
        widget.fade_unpinned = True
        widget.has_focus = False
        widget.pinned_items = set(["gemini"])
        widget.hidden_platforms = set()

        unfocused_order = widget.get_providers_order()
        self.assertEqual(unfocused_order, ["gemini"], "Unfocused widget with fade_unpinned must only show pinned items")

        # When focused, all visible items should show
        widget.has_focus = True
        focused_order = widget.get_providers_order()
        self.assertEqual(len(focused_order), 5, "Focused widget should display all visible providers")

        # 3. Unfocused with 0 pinned items must be empty (not fall back to displaying unpinned items)
        widget.has_focus = False
        widget.pinned_items = set()
        empty_pinned_order = widget.get_providers_order()
        self.assertEqual(empty_pinned_order, [], "Unfocused widget with no pinned items must not fall back to displaying unpinned items")

        widget.close()

if __name__ == "__main__":
    unittest.main()

