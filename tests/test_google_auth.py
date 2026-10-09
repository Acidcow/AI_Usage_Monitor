import unittest
import os
import tempfile
from unittest.mock import patch, MagicMock

from backend.security.google_auth import GoogleAuthManager
from backend.security.dpapi_vault import DPAPIVault
from backend.storage.database import DatabaseEngine

class TestGoogleAuthManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_auth.db")
        self.db = DatabaseEngine(self.db_path)
        self.vault = DPAPIVault()
        self.auth_mgr = GoogleAuthManager(vault=self.vault, database=self.db)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_generate_pkce_pair(self):
        verifier, challenge = self.auth_mgr.generate_pkce_pair()
        self.assertIsInstance(verifier, str)
        self.assertIsInstance(challenge, str)
        self.assertGreaterEqual(len(verifier), 43)
        self.assertGreaterEqual(len(challenge), 43)

    def test_build_authorization_url(self):
        url, state = self.auth_mgr.build_authorization_url("challenge123", redirect_port=8765)
        self.assertTrue(url.startswith("https://accounts.google.com/o/oauth2/v2/auth"))
        self.assertIn("code_challenge=challenge123", url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("state=", url)
        self.assertEqual(len(state), 32)

    def test_simulate_sign_in_and_status(self):
        res = self.auth_mgr.simulate_sign_in(email="acidcow@gmail.com", name="James Eckhardt")
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("account_id"), "acidcow@gmail.com")

        status = self.auth_mgr.get_auth_status()
        self.assertTrue(status.get("is_authenticated"))
        self.assertEqual(status.get("email"), "acidcow@gmail.com")
        self.assertEqual(status.get("name"), "James Eckhardt")
        self.assertIsInstance(status.get("tokens"), list)

    def test_add_and_delete_named_tokens(self):
        self.auth_mgr.simulate_sign_in(email="acidcow@gmail.com", name="James Eckhardt")
        
        # Add child token
        res = self.auth_mgr.add_named_token(
            name="Gemini 2.0 Flash CLI",
            api_key="AIzaSyDummyKeyForTestingPurpose123456",
            description="CLI scripting and automation"
        )
        self.assertTrue(res.get("success"))
        tok = res.get("token")
        self.assertEqual(tok["name"], "Gemini 2.0 Flash CLI")
        self.assertTrue(tok["masked_key"].startswith("AIzaSy..."))
        self.assertEqual(tok["tokens_today"], 0)
        self.assertEqual(tok["session_balance_remaining_pct"], 100.0)
        self.assertEqual(tok["weekly_balance_remaining_pct"], 100.0)

        # Check in status
        status = self.auth_mgr.get_auth_status()
        tokens = status.get("tokens", [])
        self.assertTrue(any(t["name"] == "Gemini 2.0 Flash CLI" for t in tokens))

        # Delete token
        tok_id = tok["id"]
        del_res = self.auth_mgr.delete_named_token(tok_id)
        self.assertTrue(del_res.get("success"))

        status2 = self.auth_mgr.get_auth_status()
        self.assertFalse(any(t["id"] == tok_id for t in status2.get("tokens", [])))

    def test_sign_out(self):
        self.auth_mgr.simulate_sign_in(email="acidcow@gmail.com")
        self.assertTrue(self.auth_mgr.get_auth_status()["is_authenticated"])
        
        out_res = self.auth_mgr.sign_out()
        self.assertTrue(out_res.get("success"))
        self.assertFalse(self.auth_mgr.get_auth_status()["is_authenticated"])

if __name__ == "__main__":
    unittest.main()
