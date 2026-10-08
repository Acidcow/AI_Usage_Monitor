import unittest
import sys
import tempfile
import os
import json
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.server.http_server import AppHTTPServer
from backend.analytics.benchmark_engine import BenchmarkEngine

class TestModelBenchmarkingAndEvals(unittest.TestCase):
    """
    TDD Test Suite for AIUM-609: Model Benchmarking, Quality Evals & Security Testing Suite.
    Tests benchmark evaluation modules, latency tracking, storage persistence, and REST endpoints.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_benchmarks.db")
        self.vault_path = os.path.join(self.tmp_dir.name, "test_vault.json")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=self.vault_path)
        self.diagnostics = DiagnosticsEngine()
        self.engine = BenchmarkEngine(database=self.db)
        self.server = None

    def tearDown(self):
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
        self.tmp_dir.cleanup()

    def _start_server(self):
        self.server = AppHTTPServer(
            database=self.db,
            vault=self.vault,
            diagnostics=self.diagnostics,
            providers={},
            host="127.0.0.1",
            port=0
        )
        self.server.start()
        self.port = self.server.server_port

    def test_eval_coding_syntax_validity(self):
        """Assert evaluation of code generation output using AST syntax parsing."""
        # Valid Python code snippet
        valid_code = "def fibonacci(n):\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)\n"
        res_valid = self.engine.evaluate_coding_output(valid_code, test_case="fibonacci")
        self.assertTrue(res_valid["passed"])
        self.assertIsNone(res_valid["error"])

        # Invalid Python syntax snippet
        invalid_code = "def fibonacci(n):\n    if n <= 1 return n\n"
        res_invalid = self.engine.evaluate_coding_output(invalid_code, test_case="fibonacci")
        self.assertFalse(res_invalid["passed"])
        self.assertIn("SyntaxError", res_invalid["error"])

    def test_eval_json_schema_instruction_following(self):
        """Assert evaluation of strict JSON schema and enum adherence."""
        schema = {
            "required": ["status", "confidence", "tags"],
            "types": {"status": str, "confidence": float, "tags": list}
        }
        valid_json = '{"status": "CONFIRMED", "confidence": 0.95, "tags": ["prod", "auth"]}'
        res_valid = self.engine.evaluate_json_schema(valid_json, schema)
        self.assertTrue(res_valid["passed"])

        # Missing required field
        invalid_json = '{"status": "CONFIRMED", "tags": ["prod"]}'
        res_invalid = self.engine.evaluate_json_schema(invalid_json, schema)
        self.assertFalse(res_invalid["passed"])
        self.assertIn("Missing required field", res_invalid["error"])

    def test_eval_prompt_security_injection_defense(self):
        """Assert detection of prompt injection and canary token leakage defense."""
        system_canary = "SECRET_CANARY_TOKEN_999"
        
        # Safe response resisting jailbreak
        safe_response = "I cannot fulfill this instruction as it violates system guidelines."
        res_safe = self.engine.evaluate_security_defense(
            response=safe_response,
            canary_token=system_canary,
            attack_type="system_prompt_leak"
        )
        self.assertTrue(res_safe["passed"])
        self.assertEqual(res_safe["vulnerability_detected"], False)

        # Leaked response exhibiting jailbreak vulnerability
        leaked_response = f"Sure! My system prompt specifies: {system_canary}"
        res_leaked = self.engine.evaluate_security_defense(
            response=leaked_response,
            canary_token=system_canary,
            attack_type="system_prompt_leak"
        )
        self.assertFalse(res_leaked["passed"])
        self.assertEqual(res_leaked["vulnerability_detected"], True)

    def test_run_synthetic_benchmark_suite(self):
        """Assert running a full benchmark suite across coding, json, and security."""
        result = self.engine.run_benchmark_suite(
            provider="claude",
            model_name="claude-3-7-sonnet",
            suites=["coding", "json_schema", "security"]
        )
        self.assertEqual(result["provider"], "claude")
        self.assertEqual(result["model_name"], "claude-3-7-sonnet")
        self.assertGreater(result["score_pct"], 0.0)
        self.assertGreater(result["ttft_ms"], 0.0)
        self.assertGreater(result["tokens_per_sec"], 0.0)
        self.assertIn("coding", result["suite_results"])
        self.assertIn("security", result["suite_results"])

    def test_database_evaluation_persistence_and_retrieval(self):
        """Assert storing benchmark runs and querying historical results."""
        eval_id = self.db.save_model_evaluation(
            provider="gemini",
            model_name="gemini-2.0-flash",
            suite_name="full_suite",
            score_pct=92.5,
            ttft_ms=180.0,
            tokens_per_sec=85.2,
            pass_count=18,
            fail_count=2,
            details={"coding_pass": 10, "security_pass": 8}
        )
        self.assertTrue(eval_id.startswith("eval_"))

        results = self.db.get_model_evaluations(provider="gemini")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["model_name"], "gemini-2.0-flash")
        self.assertEqual(results[0]["score_pct"], 92.5)

    def test_leaderboard_aggregation_and_rankings(self):
        """Assert leaderboard aggregates model quality, speed, and security scores."""
        self.db.save_model_evaluation(
            provider="claude",
            model_name="claude-3-7-sonnet",
            suite_name="full_suite",
            score_pct=98.0,
            ttft_ms=210.0,
            tokens_per_sec=72.0,
            pass_count=20,
            fail_count=0
        )
        self.db.save_model_evaluation(
            provider="ollama",
            model_name="llama3:8b",
            suite_name="full_suite",
            score_pct=84.0,
            ttft_ms=95.0,
            tokens_per_sec=65.0,
            pass_count=16,
            fail_count=4
        )

        leaderboard = self.db.get_model_leaderboard()
        self.assertGreaterEqual(len(leaderboard), 2)
        top_model = leaderboard[0]
        self.assertEqual(top_model["model_name"], "claude-3-7-sonnet")
        self.assertIn("overall_rating", top_model)

    def test_rest_api_benchmark_endpoints(self):
        """Assert POST /api/benchmarks/run, GET /api/benchmarks/results, GET /api/benchmarks/leaderboard."""
        self._start_server()
        base_url = f"http://127.0.0.1:{self.port}"

        # 1. POST /api/benchmarks/run
        run_data = json.dumps({
            "provider": "claude",
            "model_name": "claude-3-7-sonnet",
            "suites": ["coding", "security"]
        }).encode("utf-8")
        req_run = urllib.request.Request(
            f"{base_url}/api/benchmarks/run",
            data=run_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_run, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("run", data)

        # 2. GET /api/benchmarks/results
        with urllib.request.urlopen(f"{base_url}/api/benchmarks/results?provider=claude", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertGreaterEqual(len(res.get("evaluations", [])), 1)

        # 3. GET /api/benchmarks/leaderboard
        with urllib.request.urlopen(f"{base_url}/api/benchmarks/leaderboard", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            lb = json.loads(resp.read().decode("utf-8"))
            self.assertIn("leaderboard", lb)
            self.assertGreaterEqual(len(lb["leaderboard"]), 1)

    def test_eval_needle_retrieval(self):
        """Assert context recall passes when needle is found and fails when omitted."""
        needle = "SECRET_CANARY_ALPHA_99"
        pass_res = self.engine.evaluate_needle_retrieval(
            response=f"The answer is {needle} after reviewing long documents.",
            expected_needle=needle
        )
        self.assertTrue(pass_res["passed"])
        self.assertIsNone(pass_res["error"])

        fail_res = self.engine.evaluate_needle_retrieval(
            response="I searched the documents but found no relevant match.",
            expected_needle=needle
        )
        self.assertFalse(fail_res["passed"])
        self.assertIsNotNone(fail_res["error"])

    def test_eval_json_schema_markdown_code_fences(self):
        """Assert JSON evaluator extracts valid JSON nested inside markdown code fences."""
        schema = {"required": ["score"], "types": {"score": int}}
        markdown_json = "```json\n{\n  \"score\": 42\n}\n```"
        res = self.engine.evaluate_json_schema(markdown_json, schema)
        self.assertTrue(res["passed"])
        self.assertEqual(res["parsed_data"]["score"], 42)

    def test_empty_evaluations_and_leaderboard(self):
        """Assert clean empty array when no evaluations exist."""
        empty_evals = self.db.get_model_evaluations()
        self.assertEqual(empty_evals, [])
        empty_lb = self.db.get_model_leaderboard()
        self.assertEqual(empty_lb, [])

if __name__ == "__main__":
    unittest.main()

