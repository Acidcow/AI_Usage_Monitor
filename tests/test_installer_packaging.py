import unittest
import os
import sys
import tempfile
import zipfile
import base64
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dev_tools.build_installer import (
    create_payload_zip,
    generate_self_extracting_cmd,
    PACKAGE_DIRS,
    PACKAGE_FILES,
    INSTALLER_PAYLOAD_MARKER
)

class TestInstallerPackaging(unittest.TestCase):
    """
    Verification test suite for IRIS single-file click-to-install distribution generator.
    Ensures zero external dependency compliance, proper exclusions, and round-trip payload integrity.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.out_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_create_payload_zip_contents(self):
        zip_path = self.out_path / "test_payload.zip"
        size = create_payload_zip(zip_path, include_tests=False)
        self.assertGreater(size, 100000, "Payload zip should be at least 100KB")
        self.assertTrue(zip_path.exists())

        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            # Assert core files present
            self.assertIn("run_monitor.py", namelist)
            self.assertIn("setup.ps1", namelist)
            self.assertIn("README.md", namelist)

            # Assert core backend modules present
            self.assertTrue(any(n.startswith("backend/config.py") for n in namelist))
            self.assertTrue(any(n.startswith("backend/server/http_server.py") for n in namelist))
            self.assertTrue(any(n.startswith("backend/storage/database.py") for n in namelist))
            self.assertTrue(any(n.startswith("frontend/index.html") for n in namelist))

            # Assert ephemeral and cache files are strictly excluded
            self.assertFalse(any("__pycache__" in n for n in namelist), "pycache must be excluded")
            self.assertFalse(any("widget_profile" in n for n in namelist), "Edge browser profile must be excluded")
            self.assertFalse(any(n.endswith(".db") for n in namelist), "Runtime SQLite databases must be excluded")
            self.assertFalse(any(n.endswith(".enc") for n in namelist), "Vault encryption files must be excluded")

    def test_02_generate_self_extracting_cmd(self):
        zip_path = self.out_path / "test_payload.zip"
        create_payload_zip(zip_path, include_tests=False)

        cmd_path = self.out_path / "IRIS-Setup.cmd"
        generate_self_extracting_cmd(zip_path, cmd_path)

        self.assertTrue(cmd_path.exists())
        content = cmd_path.read_text(encoding="utf-8")

        # Verify key script elements
        self.assertIn("IRIS (Inter-node Routing, Inference & Security)", content)
        self.assertIn("%LOCALAPPDATA%\\IRIS", content)
        self.assertIn(INSTALLER_PAYLOAD_MARKER, content)

        # Verify base64 extraction roundtrip
        marker_idx = content.rfind(INSTALLER_PAYLOAD_MARKER)
        self.assertGreater(marker_idx, 0)
        raw_tail = content[marker_idx + len(INSTALLER_PAYLOAD_MARKER):]
        # Filter strictly for valid base64 chars
        b64_chars = [c for c in raw_tail if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="]
        b64_str = "".join(b64_chars)
        decoded_bytes = base64.b64decode(b64_str)

        test_extracted_zip = self.out_path / "extracted.zip"
        test_extracted_zip.write_bytes(decoded_bytes)

        with zipfile.ZipFile(test_extracted_zip, "r") as zf:
            extracted_names = zf.namelist()
            self.assertIn("run_monitor.py", extracted_names)
            self.assertIn("backend/config.py", extracted_names)

    def test_03_payload_size_is_lean(self):
        zip_path = self.out_path / "test_payload.zip"
        size = create_payload_zip(zip_path, include_tests=False)
        # Should be less than 20 MB without bloated browser profiles
        self.assertLess(size, 20 * 1024 * 1024, "Payload should be under 20MB")

if __name__ == "__main__":
    unittest.main()
