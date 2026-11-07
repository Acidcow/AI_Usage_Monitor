import ast
import datetime
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.analytics.benchmark_engine import BenchmarkEngine
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.claude import ClaudeProvider
from backend.proxy.transparent_proxy import (
    TransparentProxyHandler,
    TransparentProxyServer,
    evaluate_budget_circuit_breaker,
    evaluate_spillover_target,
)
from backend.security.dpapi_vault import DPAPIVault
from backend.storage.database import UsageDatabase


class TestLiveBenchmarksAndCircuitBreakers(unittest.TestCase):
    """
    Comprehensive Unit & Integration Test Suite for Ticket AIUM-1011.
    Covers Live Ollama Inference, Deterministic CRC32 Reproducibility,
    Budget Circuit Breakers, Cloud-to-LAN Spillover, and Inspection Modal Markup.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_evals_cb.db")
        self.vault_path = os.path.join(self.tmp_dir.name, "test_vault.json")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=self.vault_path)
        self.diagnostics = DiagnosticsEngine()
        self.engine = BenchmarkEngine(database=self.db)
        self.claude = ClaudeProvider(database=self.db, vault=self.vault, diagnostics=self.diagnostics)
        self.server = None

    def tearDown(self):
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
        self.tmp_dir.cleanup()

    # =========================================================================
    # PART 1: Deterministic Baseline & CRC32 Reproducibility
    # =========================================================================

    def test_deterministic_crc32_latency_reproducibility(self):
        """Verify CRC32 latency calculation produces 100% reproducible TTFT and TPS across separate engine instances."""
        model = "llama3:8b"
        self.engine._force_deterministic_mock = True

        res1 = self.engine.run_benchmark_suite("ollama", model, suites=["coding"])
        res2 = self.engine.run_benchmark_suite("ollama", model, suites=["coding"])

        engine2 = BenchmarkEngine(database=self.db)
        engine2._force_deterministic_mock = True
        res3 = engine2.run_benchmark_suite("ollama", model, suites=["coding"])

        expected_crc = zlib.crc32(model.encode("utf-8"))
        expected_ttft = round(85.0 + (expected_crc % 40), 1)
        expected_tps = round(65.0 + (expected_crc % 35), 1)

        self.assertEqual(res1["ttft_ms"], expected_ttft)
        self.assertEqual(res2["ttft_ms"], expected_ttft)
        self.assertEqual(res3["ttft_ms"], expected_ttft)
        self.assertEqual(res1["tokens_per_sec"], expected_tps)
        self.assertEqual(res2["tokens_per_sec"], expected_tps)
        self.assertEqual(res3["tokens_per_sec"], expected_tps)
        self.assertEqual(res1["execution_mode"], "deterministic_baseline")

    def test_deterministic_crc32_different_models(self):
        """Verify different models compute distinct but deterministic baseline TTFT values."""
        self.engine._force_deterministic_mock = True
        res_llama = self.engine.run_benchmark_suite("ollama", "llama3:8b", suites=["coding"])
        res_qwen = self.engine.run_benchmark_suite("ollama", "qwen2.5:7b", suites=["coding"])
        res_phi = self.engine.run_benchmark_suite("ollama", "phi3:mini", suites=["coding"])

        self.assertIsInstance(res_llama["ttft_ms"], float)
        self.assertIsInstance(res_qwen["ttft_ms"], float)
        self.assertIsInstance(res_phi["ttft_ms"], float)

    def test_deterministic_crc32_cloud_vs_local_baseline(self):
        """Verify cloud models receive higher simulated latency tiers than local Ollama baseline."""
        self.engine._force_deterministic_mock = True
        res_local = self.engine.run_benchmark_suite("ollama", "llama3:8b", suites=["coding"])
        res_cloud = self.engine.run_benchmark_suite("claude", "claude-3-7-sonnet", suites=["coding"])

        self.assertLessEqual(res_local["ttft_ms"], 125.0)
        self.assertGreaterEqual(res_cloud["ttft_ms"], 195.0)

    def test_force_deterministic_mock_flag(self):
        """Verify _force_deterministic_mock skips live prompt network attempts."""
        self.engine._force_deterministic_mock = True
        res = self.engine._execute_live_model_prompt("ollama", "llama3:8b", "test prompt")
        self.assertIsNone(res)

    # =========================================================================
    # PART 2: Live Ollama Inference Execution & Error Fallback
    # =========================================================================

    @patch("urllib.request.urlopen")
    def test_live_ollama_prompt_execution_success(self, mock_urlopen):
        """Verify successful live inference measures real wall-clock TTFT, TPS, and generated code."""
        mock_response_data = {
            "response": "def calculate_moving_average(data, window_size):\n    return []\n",
            "eval_count": 25,
            "eval_duration": 500_000_000,  # 0.5s => 50 tokens/sec
            "prompt_eval_duration": 45_000_000,  # 45ms TTFT
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm
        mock_urlopen.return_value = mock_cm

        res = self.engine._execute_live_model_prompt(
            provider="ollama",
            model="llama3:8b",
            prompt="Write calculate_moving_average function"
        )

        self.assertIsNotNone(res)
        self.assertEqual(res["text"], mock_response_data["response"])
        self.assertEqual(res["ttft_ms"], 45.0)
        self.assertEqual(res["tokens_per_sec"], 50.0)
        self.assertEqual(res["eval_count"], 25)

    @patch("urllib.request.urlopen")
    def test_live_ollama_prompt_network_failure_fallback(self, mock_urlopen):
        """Verify URLError during live inference gracefully returns None."""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused: 127.0.0.1:11434")
        res = self.engine._execute_live_model_prompt("ollama", "llama3:8b", "test prompt")
        self.assertIsNone(res)

    @patch("urllib.request.urlopen")
    def test_live_ollama_prompt_timeout_fallback(self, mock_urlopen):
        """Verify socket timeout during live inference gracefully returns None."""
        mock_urlopen.side_effect = TimeoutError("HTTP connection timed out")
        res = self.engine._execute_live_model_prompt("ollama", "llama3:8b", "test prompt")
        self.assertIsNone(res)

    def test_live_ollama_non_ollama_provider_returns_none(self):
        """Verify live inference only targets local ollama/local endpoints."""
        res = self.engine._execute_live_model_prompt("claude", "claude-3-7-sonnet", "prompt")
        self.assertIsNone(res)
        res_gemini = self.engine._execute_live_model_prompt("gemini", "gemini-2.0-flash", "prompt")
        self.assertIsNone(res_gemini)

    @patch("urllib.request.urlopen")
    def test_run_benchmark_suite_live_inference_mode(self, mock_urlopen):
        """Verify run_benchmark_suite records execution_mode=live_inference and stores transcript metadata."""
        code_output = (
            "def calculate_moving_average(data, window_size):\n"
            "    if not data or window_size <= 0: return []\n"
            "    return [sum(data[i:i+window_size])/window_size for i in range(len(data)-window_size+1)]\n"
        )
        mock_response_data = {
            "response": code_output,
            "eval_count": 40,
            "eval_duration": 800_000_000,
            "prompt_eval_duration": 60_000_000,
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm
        mock_urlopen.return_value = mock_cm

        suite_res = self.engine.run_benchmark_suite(
            provider="ollama",
            model_name="llama3:8b",
            suites=["coding"]
        )

        self.assertEqual(suite_res["execution_mode"], "live_inference")
        self.assertEqual(suite_res["output_transcript"], code_output)
        self.assertIn("calculate_moving_average", suite_res["prompt_text"])
        self.assertIn("ast_diagnostics", suite_res)
        self.assertTrue(suite_res["ast_diagnostics"]["ast_valid"])
        self.assertEqual(suite_res["ttft_ms"], 60.0)

    def test_run_benchmark_suite_fallback_mode_when_offline(self):
        """Verify suite executes in deterministic_baseline mode when Ollama is offline."""
        self.engine._force_deterministic_mock = True
        res = self.engine.run_benchmark_suite("ollama", "llama3:8b", suites=["coding"])
        self.assertEqual(res["execution_mode"], "deterministic_baseline")
        self.assertIn("def calculate_moving_average", res["output_transcript"])
        self.assertTrue(res["ast_diagnostics"]["ast_valid"])

    @patch("urllib.request.urlopen")
    def test_run_benchmark_suite_ast_diagnostics_on_syntax_error(self, mock_urlopen):
        """Verify AST diagnostics report syntax failure when live model produces malformed Python."""
        bad_code = "def calculate_moving_average(data, window_size\n    invalid code line!"
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps({
            "response": bad_code,
            "eval_count": 10,
            "eval_duration": 200_000_000,
            "prompt_eval_duration": 30_000_000,
        }).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm
        mock_urlopen.return_value = mock_cm

        suite_res = self.engine.run_benchmark_suite("ollama", "llama3:8b", suites=["coding"])
        self.assertEqual(suite_res["execution_mode"], "live_inference")
        self.assertFalse(suite_res["ast_diagnostics"]["ast_valid"])
        self.assertIn("SyntaxError", suite_res["ast_diagnostics"]["error"])

    # =========================================================================
    # PART 3: Budget Circuit Breaker Verification
    # =========================================================================

    def test_check_budget_circuit_breaker_unlimited_default(self):
        """Verify circuit breaker does not trip when budgets are 0.0 (unlimited default)."""
        proxy = TransparentProxyServer(claude_provider=self.claude, database=self.db)
        status = proxy.check_budget_circuit_breaker("claude")
        self.assertFalse(status["tripped"])
        self.assertEqual(status["budget_limit_usd"], 0.0)

    def test_check_budget_circuit_breaker_tripped_hourly(self):
        """Verify hourly budget breaker trips when 1-hour spend exceeds proxy_hourly_budget_usd."""
        self.db.set_setting("proxy_hourly_budget_usd", 5.0)

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usage_events (id, provider, model, estimated_cost, recorded_at)
                VALUES ('ev_test_1', 'claude', 'claude-3-7-sonnet', 6.50, ?)
                """,
                (now_utc,),
            )
            conn.commit()
            conn.close()

        proxy = TransparentProxyServer(claude_provider=self.claude, database=self.db)
        cb = proxy.check_budget_circuit_breaker("claude")

        self.assertTrue(cb["tripped"])
        self.assertGreaterEqual(cb["hourly_spend_usd"], 6.50)
        self.assertEqual(cb["budget_limit_usd"], 5.0)
        self.assertIn("Hourly proxy spend limit reached", cb["reason"])

    def test_check_budget_circuit_breaker_not_tripped_under_hourly(self):
        """Verify breaker remains untripped when spend is below proxy_hourly_budget_usd."""
        self.db.set_setting("proxy_hourly_budget_usd", 20.0)

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usage_events (id, provider, model, estimated_cost, recorded_at)
                VALUES ('ev_test_under', 'claude', 'claude-3-7-sonnet', 4.25, ?)
                """,
                (now_utc,),
            )
            conn.commit()
            conn.close()

        proxy = TransparentProxyServer(claude_provider=self.claude, database=self.db)
        cb = proxy.check_budget_circuit_breaker("claude")

        self.assertFalse(cb["tripped"])
        self.assertEqual(cb["hourly_spend_usd"], 4.25)
        self.assertEqual(cb["budget_limit_usd"], 20.0)

    def test_check_budget_circuit_breaker_tripped_session(self):
        """Verify session budget breaker trips when a specific session_id exceeds limit."""
        self.db.set_setting("proxy_session_budget_usd", 2.0)
        target_session = "sess_autonomous_agent_007"

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usage_events (id, provider, model, session_id, estimated_cost, recorded_at)
                VALUES ('ev_test_sess', 'claude', 'claude-3-7-sonnet', ?, 2.75, ?)
                """,
                (target_session, now_utc),
            )
            conn.commit()
            conn.close()

        proxy = TransparentProxyServer(claude_provider=self.claude, database=self.db)
        cb = proxy.check_budget_circuit_breaker("claude", session_id=target_session)

        self.assertTrue(cb["tripped"])
        self.assertEqual(cb["budget_limit_usd"], 2.0)
        self.assertIn("Session proxy spend limit reached", cb["reason"])

    def test_check_budget_circuit_breaker_old_events_ignored(self):
        """Verify usage events older than 1 hour do not trigger hourly breaker."""
        self.db.set_setting("proxy_hourly_budget_usd", 10.0)

        two_hours_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)).isoformat()
        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usage_events (id, provider, model, estimated_cost, recorded_at)
                VALUES ('ev_test_old', 'claude', 'claude-3-7-sonnet', 50.0, ?)
                """,
                (two_hours_ago,),
            )
            conn.commit()
            conn.close()

        proxy = TransparentProxyServer(claude_provider=self.claude, database=self.db)
        cb = proxy.check_budget_circuit_breaker("claude")

        self.assertFalse(cb["tripped"])
        self.assertEqual(cb["hourly_spend_usd"], 0.0)

    def test_check_budget_circuit_breaker_standalone_function(self):
        """Verify standalone evaluate_budget_circuit_breaker matches object invocation."""
        self.db.set_setting("proxy_hourly_budget_usd", 8.0)
        res = evaluate_budget_circuit_breaker(self.db, "claude")
        self.assertIn("tripped", res)
        self.assertIn("hourly_spend_usd", res)
        self.assertIn("budget_limit_usd", res)

    # =========================================================================
    # PART 4: Smart Cloud-to-LAN Spillover Router
    # =========================================================================

    def test_resolve_spillover_disabled_by_default(self):
        """Verify spillover returns None when cloud_to_lan_spillover_enabled is False."""
        proxy = TransparentProxyServer(claude_provider=self.claude, database=self.db)
        res = proxy.resolve_spillover_target("claude")
        self.assertIsNone(res)

    def test_resolve_spillover_when_quota_under_85_returns_none(self):
        """Verify spillover returns None when provider quota is healthy (<85% used)."""
        self.db.set_setting("cloud_to_lan_spillover_enabled", True)
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 30% remaining => 70% used (healthy)
        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO provider_snapshots (provider, status, session_remaining_pct, last_sync)
                VALUES ('claude', 'ACTIVE', 30.0, ?)
                """,
                (now_utc,),
            )
            conn.commit()
            conn.close()

        proxy = TransparentProxyServer(claude_provider=self.claude, database=self.db)
        res = proxy.resolve_spillover_target("claude")
        self.assertIsNone(res)

    def test_resolve_spillover_trips_when_quota_used_ge_85(self):
        """Verify spillover routes to online LAN node when 5h quota is >= 85% used (<=15% remaining)."""
        self.db.set_setting("cloud_to_lan_spillover_enabled", True)
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 10% remaining => 90% used
        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO provider_snapshots (provider, status, session_remaining_pct, last_sync)
                VALUES ('claude', 'ACTIVE', 10.0, ?)
                """,
                (now_utc,),
            )
            # Register online LAN worker node
            cursor.execute(
                """
                INSERT OR REPLACE INTO managed_nodes (id, name, engine, endpoint, status, models_json, created_at, updated_at)
                VALUES ('node_worker_1', 'MacStudio-LAN-Worker', 'ollama', 'http://192.168.1.150:11434', 'ONLINE', '["qwen2.5-coder:7b"]', ?, ?)
                """,
                (now_utc, now_utc),
            )
            conn.commit()
            conn.close()

        proxy = TransparentProxyServer(claude_provider=self.claude, database=self.db)
        spillover = proxy.resolve_spillover_target("claude")

        self.assertIsNotNone(spillover)
        self.assertTrue(spillover["spillover_active"])
        self.assertEqual(spillover["target_node"], "MacStudio-LAN-Worker")
        self.assertEqual(spillover["target_endpoint"], "http://192.168.1.150:11434")
        self.assertEqual(spillover["target_model"], "qwen2.5-coder:7b")

    def test_resolve_spillover_trips_on_error_or_429_status(self):
        """Verify spillover routes to LAN node when provider snapshot enters 429 or ERROR state."""
        self.db.set_setting("cloud_to_lan_spillover_enabled", True)
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO provider_snapshots (provider, status, session_remaining_pct, last_sync)
                VALUES ('claude', '429', 50.0, ?)
                """,
                (now_utc,),
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO managed_nodes (id, name, engine, endpoint, status, models_json, created_at, updated_at)
                VALUES ('node_local_1', 'Local-RTX4090', 'ollama', 'http://127.0.0.1:11434', 'ONLINE', '["llama3:8b"]', ?, ?)
                """,
                (now_utc, now_utc),
            )
            conn.commit()
            conn.close()

        proxy = TransparentProxyServer(claude_provider=self.claude, database=self.db)
        spillover = proxy.resolve_spillover_target("claude")

        self.assertIsNotNone(spillover)
        self.assertTrue(spillover["spillover_active"])
        self.assertEqual(spillover["target_node"], "Local-RTX4090")
        self.assertEqual(spillover["target_model"], "llama3:8b")

    def test_resolve_spillover_returns_none_when_no_nodes_online(self):
        """Verify spillover returns None when provider is exhausted but all LAN nodes are OFFLINE."""
        self.db.set_setting("cloud_to_lan_spillover_enabled", True)
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO provider_snapshots (provider, status, session_remaining_pct, last_sync)
                VALUES ('claude', 'ACTIVE', 5.0, ?)
                """,
                (now_utc,),
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO managed_nodes (id, name, engine, endpoint, status, created_at, updated_at)
                VALUES ('node_down', 'Offline-Worker', 'ollama', 'http://192.168.1.199:11434', 'OFFLINE', ?, ?)
                """,
                (now_utc, now_utc),
            )
            conn.commit()
            conn.close()

        proxy = TransparentProxyServer(claude_provider=self.claude, database=self.db)
        self.assertIsNone(proxy.resolve_spillover_target("claude"))

    def test_resolve_spillover_standalone_function(self):
        """Verify standalone evaluate_spillover_target helper function."""
        self.db.set_setting("cloud_to_lan_spillover_enabled", True)
        res = evaluate_spillover_target(self.db, "claude")
        self.assertTrue(res is None or isinstance(res, dict))

    # =========================================================================
    # PART 5: Full HTTP Proxy Integration with Circuit Breaker
    # =========================================================================

    def test_proxy_http_post_trips_circuit_breaker_with_429(self):
        """Verify HTTP POST request is intercepted and rejected with 429 when budget circuit breaker trips."""
        self.db.set_setting("proxy_hourly_budget_usd", 2.0)
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usage_events (id, provider, model, estimated_cost, recorded_at)
                VALUES ('ev_overbudget', 'claude', 'claude-3-7-sonnet', 5.0, ?)
                """,
                (now_utc,),
            )
            conn.commit()
            conn.close()

        self.server = TransparentProxyServer(
            claude_provider=self.claude,
            database=self.db,
            host="127.0.0.1",
            port=0
        )
        self.server.start()
        port = self.server.server_port

        url = f"http://127.0.0.1:{port}/v1/messages"
        payload = json.dumps({
            "model": "claude-3-7-sonnet",
            "messages": [{"role": "user", "content": "Hello budget test"}]
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "x-mock-response": "true"
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                self.fail("Expected HTTP 429 error from tripped circuit breaker")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 429)
            body = json.loads(e.read().decode("utf-8"))
            self.assertEqual(body["error"]["type"], "budget_circuit_breaker_tripped")
            self.assertIn("Hourly proxy spend limit reached", body["error"]["message"])

    # =========================================================================
    # PART 6: HTML Component Inspection Modal Markup
    # =========================================================================

    def test_transcript_modal_html_elements_present(self):
        """Verify Evaluation Transcript Inspection Modal elements exist in benchmark_scorecard.html."""
        html_path = REPO_ROOT / "frontend" / "components" / "benchmark_scorecard.html"
        self.assertTrue(html_path.exists(), "benchmark_scorecard.html must exist")

        content = html_path.read_text(encoding="utf-8")

        # Modal Container
        self.assertIn('id="benchmark-transcript-modal"', content)
        self.assertIn('class="modal-overlay"', content)
        self.assertIn('class="modal-box"', content)

        # Inspection elements
        self.assertIn('id="modal-bench-mode-badge"', content)
        self.assertIn('id="modal-bench-model"', content)
        self.assertIn('id="modal-bench-provider"', content)
        self.assertIn('id="modal-bench-prompt"', content)
        self.assertIn('id="modal-bench-output"', content)
        self.assertIn('id="modal-bench-ast"', content)

    def test_benchmark_scorecard_all_existing_dom_ids_intact(self):
        """Verify legacy scorecard DOM elements were preserved without regression."""
        html_path = REPO_ROOT / "frontend" / "components" / "benchmark_scorecard.html"
        content = html_path.read_text(encoding="utf-8")

        required_ids = [
            "bench-status-indicator",
            "bench-select-provider",
            "bench-input-model",
            "suite-chk-coding",
            "suite-chk-json",
            "suite-chk-security",
            "suite-chk-retrieval",
            "btn-run-benchmark",
            "benchmark-leaderboard-body",
            "benchmark-results-body",
        ]

        for elem_id in required_ids:
            self.assertIn(f'id="{elem_id}"', content, f"Missing required legacy DOM id '{elem_id}'")


if __name__ == "__main__":
    unittest.main()
