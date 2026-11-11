import unittest
import sys
import tempfile
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.gemini import GeminiProvider

class TestGeminiProvider(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_gemini_usage.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()
        self.diagnostics.clear_errors()
        self.gemini = GeminiProvider(self.db, self.vault, self.diagnostics)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_gemini_not_configured_by_default(self):
        self.assertFalse(self.gemini.is_configured)
        res = self.gemini.sync_usage()
        self.assertEqual(res["status"], "NOT_CONFIGURED")

    def test_gemini_credential_encryption(self):
        fake_key = "AIzaSyFakeKeyForGeminiTesting12345678"
        self.gemini.configure_api_key(fake_key)
        self.assertTrue(self.gemini.is_configured)
        self.assertEqual(self.vault.get_credential("gemini", "default"), fake_key)

    def test_gemini_account_level_pro_subscription_sync(self):
        """Assert Gemini connects via Google Account SSO (Gemini Pro) without needing any API key."""
        self.vault.set_credential("google", "account_email", "acidcow@gmail.com")
        self.vault.set_credential("google", "profile", '{"email": "acidcow@gmail.com", "name": "James Eckhardt"}')

        res = self.gemini.sync_usage()
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "ACTIVE")
        self.assertEqual(res["mode"], "account")
        self.assertEqual(res["account_id"], "acidcow@gmail.com")
        self.assertIn("Gemini Pro", res["plan_type"])

        snap = self.db.get_latest_provider_snapshot("gemini")
        self.assertIsNotNone(snap)
        self.assertEqual(snap["status"], "ACTIVE")
        self.assertEqual(snap["account_id"], "acidcow@gmail.com")
        self.assertIn("Gemini Pro", snap["plan_type"])
        self.assertEqual(snap["tokens_remaining"], 2000000)

if __name__ == "__main__":
    unittest.main()
