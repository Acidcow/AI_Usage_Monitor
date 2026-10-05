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

if __name__ == "__main__":
    unittest.main()
