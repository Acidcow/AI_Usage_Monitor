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

    def test_scan_local_logs_extracts_tokens_and_model_transitions(self):
        # Create a mock Ollama server.log with two distinct models
        log_content = (
            "time=2026-10-14T12:43:46.036+02:00 level=INFO source=images.go:383 msg=\"template selection\" model=registry.ollama.ai/library/gemma4:e4b\n"
            "slot print_timing: id 0 | task 5911 | prompt eval time = 524.93 ms / 1527 tokens (0.34 ms per token)\n"
            "slot print_timing: id 0 | task 5911 | eval time = 14068.08 ms / 1113 tokens (12.65 ms per token)\n"
            "[GIN] 2026/10/14 - 12:45:18 | 200 | 22.6035845s | 127.0.0.1 | POST \"/api/chat\"\n"
            "time=2026-10-14T12:50:00.000+02:00 level=INFO source=images.go:383 msg=\"template selection\" model=registry.ollama.ai/library/qwen2.5:14b\n"
            "slot print_timing: id 0 | task 5912 | prompt eval time = 100.00 ms / 450 tokens (0.22 ms per token)\n"
            "slot print_timing: id 0 | task 5912 | eval time = 2000.00 ms / 320 tokens (6.25 ms per token)\n"
            "[GIN] 2026/10/14 - 12:50:15 | 200 | 2.1000000s | 127.0.0.1 | POST \"/api/chat\"\n"
        )
        log_file = os.path.join(self.temp_dir.name, "server.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(log_content)

        ingested = self.ollama.scan_local_logs(log_paths=[log_file])
        self.assertEqual(ingested, 2)

        # Check SQLite usage_events
        events = self.db.get_recent_sessions(limit=10, provider="ollama")
        self.assertEqual(len(events), 2)

        # Verify gemma4:e4b event
        gemma_ev = next(e for e in events if e["model"] == "gemma4:e4b")
        self.assertEqual(gemma_ev["input_tokens"], 1527)
        self.assertEqual(gemma_ev["output_tokens"], 1113)
        self.assertEqual(gemma_ev["total_tokens"], 2640)

        # Verify qwen2.5:14b event
        qwen_ev = next(e for e in events if e["model"] == "qwen2.5:14b")
        self.assertEqual(qwen_ev["input_tokens"], 450)
        self.assertEqual(qwen_ev["output_tokens"], 320)
        self.assertEqual(qwen_ev["total_tokens"], 770)

    def test_scan_local_logs_is_idempotent(self):
        log_content = (
            "time=2026-10-14T12:43:46.036+02:00 level=INFO source=images.go:383 msg=\"template selection\" model=gemma4:e4b\n"
            "slot print_timing: id 0 | task 5911 | prompt eval time = 50.0 ms / 100 tokens\n"
            "slot print_timing: id 0 | task 5911 | eval time = 200.0 ms / 50 tokens\n"
            "[GIN] 2026/10/14 - 12:45:18 | 200 | 1.0s | 127.0.0.1 | POST \"/api/chat\"\n"
        )
        log_file = os.path.join(self.temp_dir.name, "server.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(log_content)

        first_run = self.ollama.scan_local_logs(log_paths=[log_file])
        self.assertEqual(first_run, 1)

        second_run = self.ollama.scan_local_logs(log_paths=[log_file])
        self.assertEqual(second_run, 0)

        events = self.db.get_recent_sessions(limit=10, provider="ollama")
        self.assertEqual(len(events), 1)

    def test_dynamic_model_telemetry_and_hierarchical_trends(self):
        import datetime
        now = datetime.datetime.now()
        gin_time = now.strftime("%Y/%m/%d - %H:%M:%S")
        hdr_time = now.strftime("%Y-%m-%dT%H:%M:%S.000+02:00")
        log_content = (
            f"time={hdr_time} level=INFO source=images.go:383 msg=\"template selection\" model=gemma4:e4b\n"
            "slot print_timing: id 0 | task 5911 | prompt eval time = 50.0 ms / 1000 tokens\n"
            "slot print_timing: id 0 | task 5911 | eval time = 200.0 ms / 500 tokens\n"
            f"[GIN] {gin_time} | 200 | 1.0s | 127.0.0.1 | POST \"/api/chat\"\n"
        )
        log_file = os.path.join(self.temp_dir.name, "server.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(log_content)

        self.ollama.scan_local_logs(log_paths=[log_file])

        # Verify get_model_telemetry_summary reflects real usage
        summary = self.ollama.get_model_telemetry_summary()
        gemma_entry = next((m for m in summary if m["model"] == "gemma4:e4b"), None)
        self.assertIsNotNone(gemma_entry)
        self.assertEqual(gemma_entry["total_tokens"], 1500)

        # Verify hierarchical trends include dynamic gemma4:e4b series
        trends = self.db.get_hierarchical_trends(provider="ollama", window="24h")
        series_keys = [s["id"] for s in trends["series"]]
        self.assertTrue(any("gemma4_e4b" in k for k in series_keys))

if __name__ == "__main__":
    unittest.main()

