import unittest
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.security.dpapi_vault import DPAPIVault, VaultError

class TestDPAPIVault(unittest.TestCase):
    def setUp(self):
        self.vault = DPAPIVault()

    def test_encrypt_and_decrypt_secret(self):
        secret = "sk-ant-api03-test-secret-key-12345"
        encrypted = self.vault.encrypt(secret)
        self.assertIsInstance(encrypted, str)
        self.assertNotEqual(encrypted, secret)
        self.assertNotIn("sk-ant-api03", encrypted)

        decrypted = self.vault.decrypt(encrypted)
        self.assertEqual(decrypted, secret)

    def test_encrypt_empty_string(self):
        encrypted = self.vault.encrypt("")
        self.assertEqual(self.vault.decrypt(encrypted), "")

    def test_encrypt_unicode_characters(self):
        secret = "p@ssw0rd_🔒_日本語_token"
        encrypted = self.vault.encrypt(secret)
        self.assertEqual(self.vault.decrypt(encrypted), secret)

    def test_corrupted_ciphertext_raises_vault_error(self):
        with self.assertRaises(VaultError):
            self.vault.decrypt("corrupted_invalid_hex_string!!!")

    def test_store_and_retrieve_credential(self):
        self.vault.set_credential("claude", "default", "sk-ant-secret-999")
        retrieved = self.vault.get_credential("claude", "default")
        self.assertEqual(retrieved, "sk-ant-secret-999")

        # Non-existent credential
        self.assertIsNone(self.vault.get_credential("non_existent", "account"))

if __name__ == "__main__":
    unittest.main()
