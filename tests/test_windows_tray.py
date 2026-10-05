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
        called = {"dashboard": False, "widget": False, "sync": False}
        def on_dash():
            called["dashboard"] = True
        def on_widget():
            called["widget"] = True
        def on_sync():
            called["sync"] = True

        tray = WindowsTrayManager(
            app_name="Test AI Monitor Commands",
            on_open_dashboard=on_dash,
            on_open_widget=on_widget,
            on_sync_now=on_sync
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

            user32.SendMessageW(tray._hwnd, WM_COMMAND, CMD_DASHBOARD, 0)
            user32.SendMessageW(tray._hwnd, WM_COMMAND, CMD_WIDGET, 0)
            user32.SendMessageW(tray._hwnd, WM_COMMAND, CMD_SYNC, 0)

            self.assertTrue(called["dashboard"], "Dashboard callback not invoked by WM_COMMAND")
            self.assertTrue(called["widget"], "Widget callback not invoked by WM_COMMAND")
            self.assertTrue(called["sync"], "Sync callback not invoked by WM_COMMAND")

        tray.stop()

if __name__ == "__main__":
    unittest.main()
