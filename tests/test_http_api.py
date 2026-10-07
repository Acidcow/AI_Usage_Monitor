import unittest
import sys
import tempfile
import os
import json
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.claude import ClaudeProvider
from backend.providers.gemini import GeminiProvider
from backend.providers.ollama import OllamaProvider
from backend.providers.copilot import CopilotProvider
from backend.providers.chatgpt import ChatGPTProvider
from backend.server.http_server import AppHTTPServer

class TestHTTPAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_api_usage.db")
        cls.db = UsageDatabase(db_path=cls.db_path)
        cls.vault = DPAPIVault(storage_path=os.path.join(cls.temp_dir.name, "vault.json"))
        cls.diagnostics = DiagnosticsEngine()
        cls.diagnostics.clear_errors()

        cls.claude = ClaudeProvider(cls.db, cls.vault, cls.diagnostics)
        cls.gemini = GeminiProvider(cls.db, cls.vault, cls.diagnostics)
        cls.ollama = OllamaProvider(cls.db, cls.vault, cls.diagnostics)
        cls.copilot = CopilotProvider(cls.db, cls.vault, cls.diagnostics)
        cls.chatgpt = ChatGPTProvider(cls.db, cls.vault, cls.diagnostics)

        providers = {
            "claude": cls.claude,
            "gemini": cls.gemini,
            "ollama": cls.ollama,
            "copilot": cls.copilot,
            "chatgpt": cls.chatgpt
        }

        cls.server = AppHTTPServer(
            database=cls.db,
            vault=cls.vault,
            diagnostics=cls.diagnostics,
            providers=providers,
            host="127.0.0.1",
            port=0
        )
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.temp_dir.cleanup()

    def _get(self, path):
        port = self.server.server_port
        url = f"http://127.0.0.1:{port}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _post(self, path, payload):
        port = self.server.server_port
        url = f"http://127.0.0.1:{port}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_api_status(self):
        status, data = self._get("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["service"], "AI_Usage_Monitor")
        self.assertIn("providers", data)

    def test_api_usage_summary(self):
        # Insert test data
        self.db.record_usage_event(
            provider="claude",
            input_tokens=1000,
            output_tokens=300,
            model="claude-3-7-sonnet"
        )
        status, data = self._get("/api/usage/summary")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["total_tokens_today"], 1300)

    def test_api_providers_list(self):
        status, data = self._get("/api/providers")
        self.assertEqual(status, 200)
        self.assertIn("claude", data)
        self.assertIn("copilot", data)
        self.assertIn("gemini", data)
        self.assertIn("ollama", data)
        self.assertIn("chatgpt", data)

    def test_api_diagnostics_export(self):
        status, data = self._get("/api/diagnostics/export")
        self.assertEqual(status, 200)
        self.assertIn("system_info", data)
        self.assertIn("provider_health", data)

    def test_api_sync_trigger(self):
        self.claude.enable_simulation_mode(True)
        status, data = self._post("/api/providers/sync", {"provider": "claude"})
        self.assertEqual(status, 200)
        self.assertTrue(data["success"])

    def test_api_gemini_config(self):
        status, data = self._post("/api/providers/gemini/config", {"api_key": "AIzaSyFakeTestKey456"})
        self.assertEqual(status, 200)
        self.assertTrue(data["success"])
        stored = self.vault.get_credential("gemini", "default")
        self.assertEqual(stored, "AIzaSyFakeTestKey456")

    def test_api_chatgpt_config(self):
        status, data = self._post("/api/providers/chatgpt/config", {"api_key": "sk-proj-FakeOpenAIKey789"})
        self.assertEqual(status, 200)
        self.assertTrue(data["success"])
        stored = self.vault.get_credential("chatgpt", "default")
        self.assertEqual(stored, "sk-proj-FakeOpenAIKey789")

    def test_api_widget_launch(self):
        status, data = self._post("/api/widget/launch", {"dry_run": True})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("mode"), "dry_run")

    def test_api_claude_quota_calibration(self):
        status, data = self._post("/api/providers/claude/quota", {
            "session_used_pct": 56.0,
            "session_reset_minutes": 126,
            "weekly_used_pct": 26.0,
            "weekly_reset_str": "Mon 3:00 AM",
            "plan_type": "Team Enterprise"
        })
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("session_remaining_pct"), 44.0)
        self.assertEqual(data.get("weekly_remaining_pct"), 74.0)

        # Check that GET /api/usage/comparison reflects calibrated quota
        st, comp = self._get("/api/usage/comparison")
        self.assertEqual(st, 200)
        claude_comp = comp["providers"]["claude"]
        self.assertEqual(claude_comp["session_balance_remaining_pct"], 44.0)
        self.assertEqual(claude_comp["weekly_balance_remaining_pct"], 74.0)
        self.assertEqual(claude_comp["weekly_reset_str"], "Mon 3:00 AM")

    def test_api_claude_quota_multiscope_and_comparison_scope_param(self):
        """Assert multi-scope quota calibration via API and query param scope filtering."""
        status, data = self._post("/api/providers/claude/quota", {
            "scope": "individual",
            "individual_session_used_pct": 60.0,
            "individual_weekly_used_pct": 27.0,
            "team_session_used_pct": 56.0,
            "team_weekly_used_pct": 26.0,
            "session_reset_minutes": 126,
            "weekly_reset_str": "Mon 3:00 AM",
            "user_name": "James Eckhardt",
            "team_name": "Synthesis Engineering"
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["scope"], "individual")
        self.assertEqual(data["session_remaining_pct"], 40.0)
        self.assertEqual(data["weekly_remaining_pct"], 73.0)
        self.assertEqual(data["individual"]["session_remaining_pct"], 40.0)
        self.assertEqual(data["team"]["session_remaining_pct"], 44.0)

        # GET with ?scope=individual
        st, comp_ind = self._get("/api/usage/comparison?scope=individual")
        self.assertEqual(st, 200)
        self.assertEqual(comp_ind["active_scope"], "individual")
        self.assertEqual(comp_ind["providers"]["claude"]["session_balance_remaining_pct"], 40.0)
        self.assertEqual(comp_ind["providers"]["claude"]["weekly_balance_remaining_pct"], 73.0)

        # GET with ?scope=team
        st, comp_team = self._get("/api/usage/comparison?scope=team")
        self.assertEqual(st, 200)
        self.assertEqual(comp_team["active_scope"], "team")
        self.assertEqual(comp_team["providers"]["claude"]["session_balance_remaining_pct"], 44.0)
        self.assertEqual(comp_team["providers"]["claude"]["weekly_balance_remaining_pct"], 74.0)

    def test_static_asset_serving_icons_and_mascots(self):
        port = self.server.server_port
        asset_paths = [
            "/assets/icons/app_icon_johnny5.jpg",
            "/assets/icons/app_icon_shield.jpg",
            "/assets/mascot/johnny5_pointing.jpg",
            "/assets/mascot/johnny5_inspecting.jpg",
            "/assets/mascot/johnny5_success.jpg"
        ]
        for path in asset_paths:
            url = f"http://127.0.0.1:{port}{path}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                self.assertEqual(resp.status, 200, f"Failed to fetch {path}")
                content_type = resp.headers.get("Content-Type")
                self.assertEqual(content_type, "image/jpeg", f"Wrong mime type for {path}")
                data = resp.read()
                self.assertGreater(len(data), 1000, f"Asset file {path} was unexpectedly small or empty")

    def test_api_usage_comparison(self):
        status, data = self._get("/api/usage/comparison")
        self.assertEqual(status, 200)
        self.assertIn("providers", data)
        self.assertIn("local_savings", data)
        self.assertIn("claude", data["providers"])
        self.assertIn("ollama", data["providers"])

    def test_api_gemini_config_with_project_id(self):
        payload = {
            "api_key": "AIzaSyKeyOne, AIzaSyKeyTwo",
            "project_id": "my-gcp-project-123"
        }
        status, data = self._post("/api/providers/gemini/config", payload)
        self.assertEqual(status, 200)
        self.assertTrue(data["success"])
        stored_key = self.vault.get_credential("gemini", "default")
        stored_proj = self.vault.get_credential("gemini", "project_id")
        self.assertIn("AIzaSyKeyOne", stored_key)
        self.assertEqual(stored_proj, "my-gcp-project-123")

    def test_api_google_auth_status_and_simulate(self):
        status, data = self._get("/api/auth/google/status")
        self.assertEqual(status, 200)
        self.assertIn("is_authenticated", data)

        # Simulate sign-in for acidcow@gmail.com
        status, sim_data = self._post("/api/auth/google/simulate", {"email": "acidcow@gmail.com", "name": "James Eckhardt"})
        self.assertEqual(status, 200)
        self.assertTrue(sim_data["success"])

        # Check status again
        status, data2 = self._get("/api/auth/google/status")
        self.assertEqual(status, 200)
        self.assertTrue(data2["is_authenticated"])
        self.assertEqual(data2["email"], "acidcow@gmail.com")

    def test_api_reports_history_and_csv(self):
        # JSON endpoint
        status, data = self._get("/api/reports/history?group_by=day")
        self.assertEqual(status, 200)
        self.assertIn("rows", data)
        self.assertIn("summary", data)

        # CSV endpoint
        port = self.server.server_port
        url = f"http://127.0.0.1:{port}/api/reports/history?group_by=day&format=csv"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/csv", resp.headers.get("Content-Type", ""))
            csv_content = resp.read().decode("utf-8")
            self.assertIn("Period,Provider", csv_content)

if __name__ == "__main__":
    unittest.main()

