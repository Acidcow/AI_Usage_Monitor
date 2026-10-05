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
from backend.providers.ollama import OllamaProvider

class TestOllamaProvider(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_ollama_usage.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()
        self.diagnostics.clear_errors()
        self.ollama = OllamaProvider(self.db, self.vault, self.diagnostics)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_provider_metadata(self):
        self.assertEqual(self.ollama.provider_name, "ollama")
        self.assertEqual(self.ollama.display_name, "Ollama (Local)")

    def test_sync_usage_live_or_offline(self):
        # Sync against local Ollama
        result = self.ollama.sync_usage()
        self.assertIn("status", result)
        self.assertIn(result["status"], ["ACTIVE", "OFFLINE"])

        snapshots = self.db.get_provider_snapshots()
        self.assertIn("ollama", snapshots)
        self.assertIn(snapshots["ollama"]["status"], ["ACTIVE", "OFFLINE"])

    def test_get_installed_models_structure(self):
        models = self.ollama.get_installed_models()
        self.assertIsInstance(models, list)
        if models:
            m = models[0]
            self.assertIn("name", m)
            self.assertIn("size", m)

if __name__ == "__main__":
    unittest.main()
