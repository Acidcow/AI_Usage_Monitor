import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.tray.desktop_widget import (
    find_edge_binary,
    calculate_widget_position,
    launch_desktop_widget
)

class TestDesktopWidget(unittest.TestCase):
    def test_find_edge_binary(self):
        """Assert that Edge binary locator returns a valid executable path or None on non-Windows."""
        binary = find_edge_binary()
        if sys.platform == "win32":
            self.assertIsNotNone(binary, "Microsoft Edge should be detected on Windows")
            self.assertTrue(Path(binary).exists(), f"Edge binary at {binary} must exist")
        else:
            self.assertIsNone(binary)

    def test_calculate_widget_position_math(self):
        """Assert taskbar snapping calculates coordinates within screen bounds."""
        pos = calculate_widget_position(widget_width=360, widget_height=210)
        self.assertIn("x", pos)
        self.assertIn("y", pos)
        self.assertIn("width", pos)
        self.assertIn("height", pos)
        self.assertEqual(pos["width"], 360)
        self.assertEqual(pos["height"], 210)
        self.assertGreaterEqual(pos["x"], 0)
        self.assertGreaterEqual(pos["y"], 0)

    def test_launch_command_generation(self):
        """Assert launch command includes app mode, window dimensions, and target widget URL."""
        pos = calculate_widget_position(widget_width=360, widget_height=210)
        edge_bin = find_edge_binary() or "msedge.exe"
        cmd = [
            str(edge_bin),
            "--app=http://127.0.0.1:8765/mini_widget.html",
            f"--window-size={pos['width']},{pos['height']}",
            f"--window-position={pos['x']},{pos['y']}"
        ]
        self.assertIn("--app=http://127.0.0.1:8765/mini_widget.html", cmd)
        self.assertTrue(any(arg.startswith("--window-size=") for arg in cmd))
        self.assertTrue(any(arg.startswith("--window-position=") for arg in cmd))

if __name__ == "__main__":
    unittest.main()
