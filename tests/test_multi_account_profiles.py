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
from backend.providers.claude import ClaudeProvider
from backend.providers.gemini import GeminiProvider

class TestMultiAccountProfiles(unittest.TestCase):
    """
    TDD Test Suite for AIUM-608: Multi-Account Profiles and Multi-Tenant Aggregation.
    Tests storage, vault isolation, REST API endpoints, and transparent proxy resolution.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_multi_acct.db")
        self.vault_path = os.path.join(self.tmp_dir.name, "test_vault.json")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=self.vault_path)
        self.diagnostics = DiagnosticsEngine()
        self.server = None

    def tearDown(self):
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
        self.tmp_dir.cleanup()

    def _start_server(self):
        claude = ClaudeProvider(self.db, self.vault, self.diagnostics)
        gemini = GeminiProvider(self.db, self.vault, self.diagnostics)
        providers = {"claude": claude, "gemini": gemini}
        self.server = AppHTTPServer(
            database=self.db,
            vault=self.vault,
            diagnostics=self.diagnostics,
            providers=providers,
            host="127.0.0.1",
            port=0
        )
        self.server.start()
        self.port = self.server.server_port

    def test_register_and_list_multiple_accounts(self):
        """Assert registering multiple account profiles per provider in the database."""
        # Claude accounts: Enterprise vs Personal
        acct1 = self.db.register_account_profile(
            provider="claude",
            account_name="Synthesis Software Technologies",
            account_id="org_synthesis_work",
            email="james@synthesis.co.za",
            plan_type="Team Enterprise",
            is_active=True
        )
        self.assertTrue(acct1["is_active"])
        self.assertEqual(acct1["account_id"], "org_synthesis_work")

        acct2 = self.db.register_account_profile(
            provider="claude",
            account_name="Personal Claude Pro",
            account_id="user_personal_claude",
            email="acidcow@gmail.com",
            plan_type="Pro",
            is_active=False
        )
        self.assertFalse(acct2["is_active"])

        # Gemini accounts
        acct3 = self.db.register_account_profile(
            provider="gemini",
            account_name="Google AI Studio Workspace",
            account_id="acidcow@gmail.com",
            email="acidcow@gmail.com",
            plan_type="Developer Pay-As-You-Go",
            is_active=True
        )

        all_accounts = self.db.get_account_profiles()
        self.assertGreaterEqual(len(all_accounts), 3)

        claude_accounts = self.db.get_account_profiles(provider="claude")
        self.assertEqual(len(claude_accounts), 2)
        claude_ids = [a["account_id"] for a in claude_accounts]
        self.assertIn("org_synthesis_work", claude_ids)
        self.assertIn("user_personal_claude", claude_ids)

    def test_active_account_switching_and_retrieval(self):
        """Assert setting active account profile updates active status atomically."""
        self.db.register_account_profile(
            provider="claude",
            account_name="Corp Account",
            account_id="acct_corp",
            is_active=True
        )
        self.db.register_account_profile(
            provider="claude",
            account_name="Personal Account",
            account_id="acct_pers",
            is_active=False
        )

        active = self.db.get_active_account_profile("claude")
        self.assertIsNotNone(active)
        self.assertEqual(active["account_id"], "acct_corp")

        # Switch to personal
        switched = self.db.set_active_account_profile("claude", "acct_pers")
        self.assertTrue(switched)

        active = self.db.get_active_account_profile("claude")
        self.assertEqual(active["account_id"], "acct_pers")

        # Ensure corp is no longer active
        accounts = self.db.get_account_profiles("claude")
        corp = [a for a in accounts if a["account_id"] == "acct_corp"][0]
        self.assertFalse(bool(corp["is_active"]))

    def test_delete_account_profile(self):
        """Assert account deletion removes profile and maintains valid active profile."""
        self.db.register_account_profile(
            provider="chatgpt",
            account_name="OpenAI Team",
            account_id="org_team_1",
            is_active=True
        )
        self.db.register_account_profile(
            provider="chatgpt",
            account_name="OpenAI Personal",
            account_id="user_pers_2",
            is_active=False
        )

        deleted = self.db.delete_account_profile("chatgpt", "org_team_1")
        self.assertTrue(deleted)

        remaining = self.db.get_account_profiles("chatgpt")
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["account_id"], "user_pers_2")
        # Fallback should activate remaining profile
        self.assertTrue(bool(remaining[0]["is_active"]))

    def test_dpapi_vault_credential_isolation_per_account(self):
        """Assert credentials for different accounts under same provider are isolated in vault."""
        self.vault.set_credential("claude", "org_work", "sk-ant-api03-work-secret-123456789")
        self.vault.set_credential("claude", "user_pers", "sk-ant-api03-pers-secret-987654321")

        work_key = self.vault.get_credential("claude", "org_work")
        pers_key = self.vault.get_credential("claude", "user_pers")

        self.assertEqual(work_key, "sk-ant-api03-work-secret-123456789")
        self.assertEqual(pers_key, "sk-ant-api03-pers-secret-987654321")
        self.assertNotEqual(work_key, pers_key)

    def test_event_recording_resolves_active_account(self):
        """Assert record_usage_event pulls active account when account_id not passed."""
        self.db.register_account_profile(
            provider="claude",
            account_name="Synthesis Software Technologies",
            account_id="org_synthesis_work",
            is_active=True
        )
        evt_id = self.db.record_usage_event(
            provider="claude",
            input_tokens=100,
            output_tokens=200,
            model="claude-3-7-sonnet"
        )
        events = self.db.get_recent_events(limit=5)
        self.assertTrue(any(e["id"] == evt_id and e["account_id"] == "org_synthesis_work" for e in events))

    def test_rest_api_account_endpoints(self):
        """Assert GET/POST /api/accounts, /api/accounts/active, /api/accounts/delete."""
        self._start_server()
        base_url = f"http://127.0.0.1:{self.port}"

        # 1. POST /api/accounts - register new account
        req_data = json.dumps({
            "provider": "claude",
            "account_name": "API Account 1",
            "account_id": "acct_api_01",
            "plan_type": "Pro",
            "api_key": "sk-ant-api03-testkey-111222333",
            "is_active": True
        }).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/api/accounts", data=req_data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res.get("success"))

        # Verify DPAPI credential was saved under account_id
        saved_key = self.vault.get_credential("claude", "acct_api_01")
        self.assertEqual(saved_key, "sk-ant-api03-testkey-111222333")

        # 2. Register second account
        req_data2 = json.dumps({
            "provider": "claude",
            "account_name": "API Account 2",
            "account_id": "acct_api_02",
            "plan_type": "Team Enterprise",
            "is_active": False
        }).encode("utf-8")
        req2 = urllib.request.Request(f"{base_url}/api/accounts", data=req_data2, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req2, timeout=5) as resp:
            self.assertEqual(resp.status, 200)

        # 3. GET /api/accounts - list accounts
        with urllib.request.urlopen(f"{base_url}/api/accounts?provider=claude", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            accounts = res.get("accounts", [])
            self.assertEqual(len(accounts), 2)
            self.assertTrue(any(a["account_id"] == "acct_api_01" and a["is_active"] for a in accounts))

        # 4. POST /api/accounts/active - switch active account
        switch_data = json.dumps({
            "provider": "claude",
            "account_id": "acct_api_02"
        }).encode("utf-8")
        req_switch = urllib.request.Request(f"{base_url}/api/accounts/active", data=switch_data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req_switch, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res.get("success"))

        # Check active status updated
        active_prof = self.db.get_active_account_profile("claude")
        self.assertEqual(active_prof["account_id"], "acct_api_02")

        # 5. POST /api/accounts/delete - delete account
        del_data = json.dumps({
            "provider": "claude",
            "account_id": "acct_api_01"
        }).encode("utf-8")
        req_del = urllib.request.Request(f"{base_url}/api/accounts/delete", data=del_data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req_del, timeout=5) as resp:
            self.assertEqual(resp.status, 200)

        # Verify key was cleaned up from vault
        self.assertIsNone(self.vault.get_credential("claude", "acct_api_01"))

    def test_multi_tenant_historical_report_filtering(self):
        """Assert historical reports filter accurately by specific account_id or all accounts."""
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=1000,
            output_tokens=500,
            account_id="acct_tenant_a"
        )
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=2000,
            output_tokens=1000,
            account_id="acct_tenant_b"
        )

        rep_all = self.db.query_historical_report(group_by="day", provider="claude")
        self.assertEqual(rep_all["summary"]["total_tokens"], 4500)

        rep_a = self.db.query_historical_report(group_by="day", provider="claude", account_id="acct_tenant_a")
        self.assertEqual(rep_a["summary"]["total_tokens"], 1500)

        rep_b = self.db.query_historical_report(group_by="day", provider="claude", account_id="acct_tenant_b")
        self.assertEqual(rep_b["summary"]["total_tokens"], 3000)

    def test_invalid_requests_handled_gracefully(self):
        """Assert HTTP API returns 400 for bad input and 404 for non-existent profiles."""
        self._start_server()
        base_url = f"http://127.0.0.1:{self.port}"

        # Missing provider
        req = urllib.request.Request(
            f"{base_url}/api/accounts",
            data=json.dumps({"account_id": "test_id"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

        # Activate non-existent profile
        req_act = urllib.request.Request(
            f"{base_url}/api/accounts/active",
            data=json.dumps({"provider": "claude", "account_id": "non_existent_123"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx2:
            urllib.request.urlopen(req_act, timeout=5)
        self.assertEqual(ctx2.exception.code, 404)

    def test_multiple_providers_account_isolation(self):
        """Assert accounts across different providers remain isolated."""
        self.db.register_account_profile(provider="claude", account_name="Claude Corp", account_id="corp_1", is_active=True)
        self.db.register_account_profile(provider="gemini", account_name="Gemini Personal", account_id="pers_1", is_active=True)
        self.db.register_account_profile(provider="chatgpt", account_name="ChatGPT Org", account_id="org_1", is_active=True)

        claude_profs = self.db.get_account_profiles("claude")
        self.assertEqual(len(claude_profs), 1)
        self.assertEqual(claude_profs[0]["account_id"], "corp_1")

        gemini_profs = self.db.get_account_profiles("gemini")
        self.assertEqual(len(gemini_profs), 1)
        self.assertEqual(gemini_profs[0]["account_id"], "pers_1")

        # Switching claude does not affect gemini
        self.db.register_account_profile(provider="claude", account_name="Claude Pers", account_id="pers_claude", is_active=True)
        gemini_active = self.db.get_active_account_profile("gemini")
        self.assertEqual(gemini_active["account_id"], "pers_1")

    def test_active_account_profile_metadata_and_json_handling(self):
        """Assert account metadata serialization and deserialization."""
        meta = {
            "organization_id": "org_987654",
            "rate_limit_rpm": 120,
            "region": "europe-west1"
        }
        res = self.db.register_account_profile(
            provider="claude",
            account_name="EU Cluster Profile",
            account_id="eu_cluster_01",
            metadata=meta,
            is_active=True
        )
        self.assertEqual(res["metadata"]["organization_id"], "org_987654")
        self.assertEqual(res["metadata"]["rate_limit_rpm"], 120)

        # Retrieve again to verify persistence
        active = self.db.get_active_account_profile("claude")
        self.assertEqual(active["metadata"]["region"], "europe-west1")

if __name__ == "__main__":
    unittest.main()
