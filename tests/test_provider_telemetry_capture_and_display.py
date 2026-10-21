"""
Authoritative Test Suite: Provider Telemetry Capture & Display Verification
Tests telemetry capture, parsing, model tracking, multi-account/multi-instance
reporting, and quota resilience across Gemini, Ollama, ChatGPT, Copilot, and Claude.
Ensures zero external dependency and zero external Claude network calls.
"""

import unittest
import tempfile
import os
import json
import time
from unittest.mock import patch, MagicMock
import urllib.error

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.gemini import GeminiProvider
from backend.providers.ollama import OllamaProvider
from backend.providers.chatgpt import ChatGPTProvider
from backend.providers.copilot import CopilotProvider
from backend.providers.claude import ClaudeProvider

class TestProviderTelemetryCaptureAndDisplay(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_telemetry.db")
        self.vault_path = os.path.join(self.temp_dir.name, "test_vault.json")
        self.db = UsageDatabase(self.db_path)
        self.vault = DPAPIVault(storage_path=self.vault_path)
        self.diagnostics = DiagnosticsEngine()

        self.gemini = GeminiProvider(self.db, self.vault, self.diagnostics)
        self.ollama = OllamaProvider(self.db, self.vault, self.diagnostics, base_url="http://localhost:11434")
        self.chatgpt = ChatGPTProvider(self.db, self.vault, self.diagnostics)
        self.copilot = CopilotProvider(self.db, self.vault, self.diagnostics)
        self.claude = ClaudeProvider(self.db, self.vault, self.diagnostics)

    def tearDown(self):
        self.temp_dir.cleanup()

    # =========================================================================
    # 1. Gemini Telemetry & Multi-Key Ingestion
    # =========================================================================
    def test_gemini_telemetry_capture_multi_key_and_models(self):
        """Verify Gemini captures models, scales quotas with active keys, and records events."""
        fake_models_response = json.dumps({
            "models": [
                {"name": "models/gemini-1.5-pro", "displayName": "Gemini 1.5 Pro"},
                {"name": "models/gemini-1.5-flash", "displayName": "Gemini 1.5 Flash"},
                {"name": "models/gemini-2.0-flash-exp", "displayName": "Gemini 2.0 Flash Exp"}
            ]
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_models_response
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with patch.object(self.vault, "get_credential") as mock_cred:
                def get_cred(service, key_name):
                    if service == "gemini" and key_name == "keys":
                        return json.dumps(["AIzaSyFakeKey1", "AIzaSyFakeKey2"])
                    if service == "gemini" and key_name == "project_id":
                        return "project-agentic-dev"
                    return None
                mock_cred.side_effect = get_cred

                result = self.gemini.sync_usage()
                self.assertTrue(result["success"])
                self.assertEqual(result["active_keys"], 2)
                self.assertIn("gemini-1.5-pro", result["models"])
                self.assertIn("gemini-1.5-flash", result["models"])

        # Check DB snapshot
        snap = self.db.get_latest_provider_snapshot("gemini")
        self.assertIsNotNone(snap)
        self.assertEqual(snap["tokens_remaining"], 2000000) # 1M * 2 keys
        self.assertEqual(snap["requests_remaining"], 3000)  # 1500 * 2 keys
        self.assertIn("GCP: project-agentic-dev", snap["plan_type"])

    def test_gemini_token_id_resolution(self):
        """Verify resolution of named child tokens for Gemini from vault credentials."""
        named_tokens = [
            {"id": "tok_gem_flash", "name": "Gemini Flash Token", "masked_key": "AIza...1234"},
            {"id": "tok_gem_pro", "name": "Gemini Pro Token", "masked_key": "AIza...5678"}
        ]
        with patch.object(self.vault, "get_credential") as mock_cred:
            def get_cred(service, key_name):
                if service == "google" and key_name == "named_tokens":
                    return json.dumps(named_tokens)
                if service == "gemini" and key_name == "token_tok_gem_pro":
                    return "AIzaSyFullProKey_secret"
                return None
            mock_cred.side_effect = get_cred

            resolved = self.gemini.resolve_token_id_from_key("AIzaSyFullProKey_secret")
            self.assertEqual(resolved, "tok_gem_pro")

    # =========================================================================
    # 2. Ollama Local Telemetry & Hardware Multi-Instance
    # =========================================================================
    def test_ollama_model_telemetry_and_vram_tracking(self):
        """Verify Ollama interrogates local tags, PS runtime, and VRAM footprint."""
        tags_data = json.dumps({
            "models": [
                {
                    "name": "llama3.2:3b",
                    "size": 2048 * 1024 * 1024,
                    "details": {"parameter_size": "3.2B", "quantization_level": "Q4_K_M", "family": "llama"}
                },
                {
                    "name": "qwen2.5-coder:7b",
                    "size": 4500 * 1024 * 1024,
                    "details": {"parameter_size": "7.6B", "quantization_level": "Q4_0", "family": "qwen2"}
                }
            ]
        }).encode("utf-8")

        ps_data = json.dumps({
            "models": [
                {
                    "name": "llama3.2:3b",
                    "size_vram": 2100 * 1024 * 1024
                }
            ]
        }).encode("utf-8")

        def fake_urlopen(req, timeout=0.5):
            url = req.full_url if hasattr(req, "full_url") else req
            m = MagicMock()
            if "/api/tags" in url:
                m.read.return_value = tags_data
            elif "/api/ps" in url:
                m.read.return_value = ps_data
            m.__enter__.return_value = m
            return m

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            models = self.ollama.get_installed_models(force_refresh=True)
            self.assertEqual(len(models), 2)
            self.assertEqual(models[0]["name"], "llama3.2:3b")
            self.assertEqual(models[0]["parameter_size"], "3.2B")

            running = self.ollama.get_running_models()
            self.assertEqual(len(running), 1)
            self.assertEqual(running[0]["name"], "llama3.2:3b")

            summary = self.ollama.get_model_telemetry_summary(allow_network=True)
            llama_sum = next(s for s in summary if s["name"] == "llama3.2:3b")
            self.assertTrue(llama_sum["is_running"])
            self.assertGreater(llama_sum["vram_size_gb"], 0.0)

    def test_ollama_multi_instance_and_log_scanner_telemetry(self):
        """Verify Ollama records telemetry across distinct instances and local logs with $0 cost."""
        # 1. Ingest direct local inference
        self.ollama.ingest_inference_tokens(
            model="llama3.2:3b",
            prompt_tokens=500,
            completion_tokens=250,
            session_id="ollama_local_1",
            source="direct",
            instance_id="local_rig"
        )

        # 2. Ingest remote cluster GPU worker inference
        self.ollama.ingest_inference_tokens(
            model="qwen2.5-coder:7b",
            prompt_tokens=1200,
            completion_tokens=800,
            session_id="ollama_worker_1",
            source="proxy",
            instance_id="worker_gpu_node_2",
            is_proxied=1
        )

        comp = self.db.get_comparative_metrics()
        ollama_metrics = comp["providers"]["ollama"]
        self.assertEqual(ollama_metrics["tokens_today"], 2750)
        self.assertEqual(ollama_metrics["cost_today_usd"], 0.0) # Always $0 for local hardware

        # Check multi-instance breakdown
        instances = {inst["instance_id"]: inst["tokens_today"] for inst in ollama_metrics["instances"]}
        self.assertEqual(instances["local_rig"], 750)
        self.assertEqual(instances["worker_gpu_node_2"], 2000)
        self.assertEqual(sum(instances.values()), ollama_metrics["tokens_today"])

    # =========================================================================
    # 3. ChatGPT Provider Telemetry & Pricing
    # =========================================================================
    def test_chatgpt_telemetry_models_and_cost_accounting(self):
        """Verify ChatGPT models discovery and exact input/output token pricing."""
        fake_openai_models = json.dumps({
            "data": [
                {"id": "gpt-4o"},
                {"id": "gpt-4o-mini"},
                {"id": "o1-preview"}
            ]
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_openai_models
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with patch.object(self.vault, "get_credential", return_value="sk-proj-FakeOpenAIKey"):
                res = self.chatgpt.sync_usage()
                self.assertTrue(res["success"])
                self.assertIn("gpt-4o", res["models"])

        # Ingest events for different models and accounts
        self.db.record_usage_event(
            provider="chatgpt",
            input_tokens=1000,
            output_tokens=500,
            model="gpt-4o",
            session_id="chatgpt_sess_1",
            account_id="proj-finance",
            source="direct"
        )
        self.db.record_usage_event(
            provider="chatgpt",
            input_tokens=4000,
            output_tokens=2000,
            model="gpt-4o-mini",
            session_id="chatgpt_sess_2",
            account_id="proj-research",
            source="proxy",
            is_proxied=1
        )

        comp = self.db.get_comparative_metrics()
        cg = comp["providers"]["chatgpt"]
        self.assertEqual(cg["tokens_today"], 7500)
        self.assertGreater(cg["cost_today_usd"], 0.0)

        # Verify account breakdown parity
        accts = {a["account_id"]: a["tokens_today"] for a in cg["accounts"]}
        self.assertEqual(accts["proj-finance"], 1500)
        self.assertEqual(accts["proj-research"], 6000)
        self.assertEqual(sum(accts.values()), cg["tokens_today"])

    # =========================================================================
    # 4. M365 Copilot Telemetry & Enterprise Policy
    # =========================================================================
    def test_copilot_restricted_sync_and_proxy_monitoring(self):
        """Verify Copilot sync operates in STANDBY_RESTRICTED and captures proxied enterprise traffic."""
        res = self.copilot.sync_usage()
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "STANDBY_RESTRICTED")

        snap = self.db.get_latest_provider_snapshot("copilot")
        self.assertEqual(snap["status"], "STANDBY_RESTRICTED")
        self.assertEqual(snap["plan_type"], "M365 Enterprise E5")

        # Ingest enterprise proxied Copilot traffic
        self.db.record_usage_event(
            provider="copilot",
            input_tokens=1500,
            output_tokens=800,
            model="copilot-m365-chat",
            session_id="copilot_ep_1",
            account_id="user@enterprise.com",
            source="proxy",
            instance_id="corp_proxy_gateway",
            is_proxied=1
        )

        comp = self.db.get_comparative_metrics()
        cp = comp["providers"]["copilot"]
        self.assertEqual(cp["tokens_today"], 2300)
        self.assertEqual(cp["source_breakdown"]["proxy"], 2300)

    # =========================================================================
    # 5. Claude Quota Exhaustion & Error Resilience
    # =========================================================================
    def test_claude_quota_exhaustion_resilience_without_crashing(self):
        """
        Verify that when Claude tokens are exhausted (HTTP 429 or 400),
        Claude snapshot gracefully updates to RATE_LIMITED or QUOTA_EXHAUSTED
        with tokens_remaining=0, without breaking poller or other providers.
        """
        # Simulate HTTP 429 Rate Limit from Anthropic API
        fake_429_headers = {
            "anthropic-ratelimit-tokens-remaining": "0",
            "anthropic-ratelimit-requests-remaining": "0",
            "anthropic-ratelimit-tokens-reset": "2026-10-21T16:00:00Z"
        }
        err_429 = urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=429,
            msg="Too Many Requests",
            hdrs=fake_429_headers,
            fp=None
        )

        with patch.object(self.claude, "scan_local_logs", return_value=0):
            with patch.object(self.vault, "get_credential", return_value="sk-ant-FakeKey"):
                with patch("urllib.request.urlopen", side_effect=err_429):
                    res = self.claude.sync_usage()
                    self.assertFalse(res["success"])
                    self.assertEqual(res["status"], "RATE_LIMITED")

        # Verify DB snapshot recorded zero tokens remaining and RATE_LIMITED status
        snap = self.db.get_latest_provider_snapshot("claude")
        self.assertIsNotNone(snap)
        self.assertEqual(snap["tokens_remaining"], 0)
        self.assertEqual(snap["status"], "RATE_LIMITED")
        err_429.close()

        # Simulate HTTP 400 Credit Low / Tokens Exhausted
        err_400 = urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=400,
            msg="Bad Request: Your credit balance is too low to access the Claude API",
            hdrs={},
            fp=None
        )
        with patch.object(self.claude, "scan_local_logs", return_value=0):
            with patch.object(self.vault, "get_credential", return_value="sk-ant-FakeKey"):
                with patch("urllib.request.urlopen", side_effect=err_400):
                    res_400 = self.claude.sync_usage()
                    self.assertFalse(res_400["success"])
                    self.assertEqual(res_400["status"], "QUOTA_EXHAUSTED")

        snap_400 = self.db.get_latest_provider_snapshot("claude")
        self.assertEqual(snap_400["tokens_remaining"], 0)
        self.assertEqual(snap_400["status"], "QUOTA_EXHAUSTED")
        err_400.close()

    # =========================================================================
    # 6. Cross-Platform Parity and Aggregation Under Zero Claude Tokens
    # =========================================================================
    def test_cross_platform_parity_under_claude_zero_tokens(self):
        """
        Verify that when Claude has 0 tokens, comparative metrics still compute
        perfect mathematical parity across Gemini, Ollama, ChatGPT, and Copilot.
        """
        # Claude is at 0 tokens
        self.db.update_provider_snapshot(
            provider="claude",
            plan_type="Claude Pro",
            tokens_remaining=0,
            requests_remaining=0,
            status="QUOTA_EXHAUSTED"
        )

        # Gemini events
        self.db.record_usage_event(provider="gemini", input_tokens=1000, output_tokens=500, model="gemini-1.5-pro", session_id="g1", account_id="acc_gem_1", source="direct")
        # Ollama events
        self.db.record_usage_event(provider="ollama", input_tokens=2000, output_tokens=1000, model="llama3.2:3b", session_id="o1", instance_id="gpu_rig_1", source="proxy", is_proxied=1)
        # ChatGPT events
        self.db.record_usage_event(provider="chatgpt", input_tokens=500, output_tokens=200, model="gpt-4o", session_id="c1", account_id="acc_cg_1", source="direct")
        # Copilot events
        self.db.record_usage_event(provider="copilot", input_tokens=800, output_tokens=400, model="copilot-m365", session_id="cp1", account_id="corp_user", source="emulator", is_proxied=1)

        comp = self.db.get_comparative_metrics()
        providers = comp["providers"]

        # Sum of tokens across providers must equal summary total
        total_tokens = sum(p["tokens_today"] for p in providers.values())
        self.assertEqual(total_tokens, comp["total_tokens_today"])
        self.assertEqual(comp["total_tokens_today"], 6400) # (1500 + 3000 + 700 + 1200)

        # Parity across source breakdowns
        for p_key, p_data in providers.items():
            if p_data["tokens_today"] > 0:
                src_sum = sum(src_tok if isinstance(src_tok, int) else src_tok.get("tokens", 0) for src_tok in p_data["source_breakdown"].values())
                self.assertEqual(src_sum, p_data["tokens_today"], f"Source breakdown sum mismatch for {p_key}")

                if p_data["accounts"]:
                    acc_sum = sum(a["tokens_today"] for a in p_data["accounts"])
                    self.assertEqual(acc_sum, p_data["tokens_today"], f"Accounts sum mismatch for {p_key}")

                if p_data["instances"]:
                    inst_sum = sum(i["tokens_today"] for i in p_data["instances"])
                    self.assertEqual(inst_sum, p_data["tokens_today"], f"Instances sum mismatch for {p_key}")

if __name__ == "__main__":
    unittest.main()
