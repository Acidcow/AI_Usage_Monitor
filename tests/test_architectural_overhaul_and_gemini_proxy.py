import json
import os
import shutil
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.claude import ClaudeProvider
from backend.providers.gemini import GeminiProvider
from backend.proxy.transparent_proxy import TransparentProxyServer, TransparentProxyHandler
from backend.security.dpapi_vault import DPAPIVault
from backend.security.google_auth import GoogleAuthManager
from backend.server.http_server import AppHTTPServer
from backend.storage.database import DatabaseEngine, UsageDatabase
from backend.storage.reporting_engine import ReportingEngineMixin


class TestArchitecturalOverhaulAndGeminiProxy(unittest.TestCase):
    """
    Comprehensive Test Suite for Ticket AIUM-902 (Architectural Audit & Overhaul)
    and Ticket AIUM-607 (Historical Reporting & Multi-Dimensional Pivot Engine):
    - Unified Gemini Proxy DPAPI Credential Resolution & Placeholder Replacement
    - OAuth Bearer vs. AIza API Key Injection
    - GET /v1beta/models Proxy Support & Keyless /models/... Routing
    - Proxy Telemetry Attribution (source='proxy', is_proxied=1, client_ip, instance_id)
    - ReportingEngineMixin Modularization, Cross-Platform Tag ('group') Pivoting & CSV Parity
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="aium_overhaul_test_"))
        self.db_path = self.temp_dir / "test_overhaul.db"
        self.vault_path = self.temp_dir / "test_vault.json"

        self.db = UsageDatabase(db_path=str(self.db_path))
        self.vault = DPAPIVault(storage_path=str(self.vault_path))
        self.diag = DiagnosticsEngine()

        self.claude = ClaudeProvider(database=self.db, vault=self.vault, diagnostics=self.diag)
        self.gemini = GeminiProvider(database=self.db, vault=self.vault, diagnostics=self.diag)
        self.google_auth = GoogleAuthManager(vault=self.vault, database=self.db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================================
    # 1. GEMINI CREDENTIAL RESOLUTION & TRANSPARENT PROXY TESTS
    # =========================================================================

    def test_01_gemini_placeholder_key_detection(self):
        """Verify placeholder keys ('proxy', 'dummy', 'vault', 'local', '') are detected."""
        for placeholder in ["", "proxy", "PROXY", "dummy", "local", "vault", "aium", "none", "null", "placeholder_key"]:
            self.assertTrue(
                GeminiProvider.is_placeholder_key(placeholder),
                f"Expected '{placeholder}' to be detected as placeholder",
            )
        self.assertFalse(GeminiProvider.is_placeholder_key("AIzaSyD-RealGoogleStudioKey123456"))

    def test_02_resolve_proxy_credential_honors_valid_client_aiza_key(self):
        """Verify a genuine client-supplied AIza... key is used directly."""
        client_key = "AIzaSyClientDirectKey987654321"
        res = self.gemini.resolve_proxy_credential(client_key=client_key)
        self.assertEqual(res["credential"], client_key)
        self.assertEqual(res["auth_type"], "api_key")
        self.assertEqual(res["source"], "client_api_key")
        self.assertFalse(res["replaced_placeholder"])

    def test_03_resolve_proxy_credential_replaces_placeholder_with_vault_default(self):
        """Verify 'proxy' or 'dummy' client key is replaced with ('gemini', 'default') from DPAPI vault."""
        vault_key = "AIzaSyVaultDefaultKey111222333"
        self.vault.set_credential("gemini", "default", vault_key)

        res = self.gemini.resolve_proxy_credential(client_key="proxy")
        self.assertEqual(res["credential"], vault_key)
        self.assertEqual(res["auth_type"], "api_key")
        self.assertEqual(res["source"], "dpapi_vault")
        self.assertTrue(res["replaced_placeholder"])

    def test_04_resolve_proxy_credential_from_multi_key_json_list(self):
        """Verify resolution from ('gemini', 'keys') JSON array when 'default' is absent."""
        multi_key = "AIzaSyMultiListKey444555666"
        self.vault.set_credential("gemini", "keys", json.dumps([multi_key]))

        res = self.gemini.resolve_proxy_credential(client_key="dummy")
        self.assertEqual(res["credential"], multi_key)
        self.assertEqual(res["auth_type"], "api_key")
        self.assertEqual(res["source"], "dpapi_vault")

    def test_05_resolve_proxy_credential_from_active_account_profile(self):
        """Verify resolution prioritizes active account profile in DB + DPAPI vault."""
        acct_key = "AIzaSyActiveAccountKey777888999"
        self.db.register_account_profile(
            provider="gemini",
            account_id="team-gemini-prod",
            account_name="Team Gemini Prod",
            is_active=True,
        )
        self.vault.set_credential("gemini", "team-gemini-prod", acct_key)

        res = self.gemini.resolve_proxy_credential(client_key="")
        self.assertEqual(res["credential"], acct_key)
        self.assertEqual(res["account_id"], "team-gemini-prod")

    def test_06_resolve_proxy_credential_from_named_token_id_and_fallback(self):
        """Verify named token lookup both via explicit tok_gem_* selector and automatic fallback."""
        added = self.google_auth.add_named_token(
            name="Workstation CLI Key",
            api_key="AIzaSyNamedTokenKey000111222",
        )
        tok_id = added["token"]["id"]

        # 1. Explicit selector via client_key=tok_id
        res_explicit = self.gemini.resolve_proxy_credential(client_key=tok_id)
        self.assertEqual(res_explicit["credential"], "AIzaSyNamedTokenKey000111222")
        self.assertEqual(res_explicit["token_id"], tok_id)
        self.assertEqual(res_explicit["source"], "vault_named_token")

        # 2. Automatic fallback when client sends no key
        res_fallback = self.gemini.resolve_proxy_credential(client_key="proxy")
        self.assertEqual(res_fallback["credential"], "AIzaSyNamedTokenKey000111222")
        self.assertEqual(res_fallback["token_id"], tok_id)

    def test_07_resolve_proxy_credential_google_oauth_bearer(self):
        """Verify Google OAuth 2.0 access_token resolves as auth_type='oauth_bearer'."""
        self.vault.set_credential("google", "access_token", "ya29.a0AfH6SMB_RealGoogleOAuthToken")
        self.vault.set_credential("google", "account_email", "engineer@synthesis.co")

        res = self.gemini.resolve_proxy_credential(client_key="proxy")
        self.assertEqual(res["credential"], "ya29.a0AfH6SMB_RealGoogleOAuthToken")
        self.assertEqual(res["auth_type"], "oauth_bearer")
        self.assertEqual(res["source"], "dpapi_oauth")

    def test_08_transparent_proxy_get_models_and_keyless_routing(self):
        """Verify GET /v1beta/models and keyless POST /models/gemini-... work through TransparentProxyServer."""
        self.vault.set_credential("gemini", "default", "AIzaSyProxyTestKey123456789")
        proxy = TransparentProxyServer(
            claude_provider=self.claude,
            gemini_provider=self.gemini,
            host="127.0.0.1",
            port=0,
        )
        proxy.start()
        try:
            base_url = f"http://127.0.0.1:{proxy.server_port}"

            # 1. GET /v1beta/models with placeholder key ?key=proxy in mock mode
            req_get = urllib.request.Request(
                f"{base_url}/v1beta/models?key=proxy",
                headers={"x-mock-gemini-response": "true"},
                method="GET",
            )
            with urllib.request.urlopen(req_get) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("models", data)
                self.assertEqual(data["proxy_auth"]["auth_type"], "api_key")
                self.assertEqual(data["proxy_auth"]["source"], "dpapi_vault")
                self.assertTrue(data["proxy_auth"]["replaced_placeholder"])

            # 2. Keyless POST /models/gemini-2.5-pro:generateContent (previously misrouted to Claude!)
            req_post = urllib.request.Request(
                f"{base_url}/models/gemini-2.5-pro:generateContent",
                data=json.dumps({"contents": [{"parts": [{"text": "Hello"}]}]}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-mock-gemini-response": "true",
                    "x-mock-input-tokens": "320",
                    "x-mock-output-tokens": "180",
                    "X-AIUM-Instance": "workstation-alpha",
                },
                method="POST",
            )
            with urllib.request.urlopen(req_post) as resp:
                self.assertEqual(resp.status, 200)
                post_data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(post_data["usageMetadata"]["totalTokenCount"], 500)
                self.assertEqual(post_data["proxyAuth"]["source"], "dpapi_vault")

            # Verify telemetry recorded source='proxy', is_proxied=1, instance_id='workstation-alpha'
            report = self.db.query_historical_report(provider="gemini", source="proxy")
            self.assertEqual(report["summary"]["total_tokens"], 500)
            self.assertEqual(report["rows"][0]["instance_id"], "workstation-alpha")
        finally:
            proxy.stop()

    def test_09_transparent_proxy_upstream_header_injection_verification(self):
        """Verify real upstream urllib.request.Request receives vaulted key instead of placeholder."""
        self.vault.set_credential("gemini", "default", "AIzaSyRealUpstreamKey999888777")
        proxy = TransparentProxyServer(
            claude_provider=self.claude,
            gemini_provider=self.gemini,
            host="127.0.0.1",
            port=0,
        )
        proxy.start()
        captured_requests = []

        class DummyResp:
            status = 200
            headers = {"content-type": "application/json"}

            def read(self):
                return json.dumps(
                    {"usageMetadata": {"promptTokenCount": 40, "candidatesTokenCount": 60}}
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        def fake_urlopen(req, timeout=None):
            if isinstance(req, urllib.request.Request) and "generativelanguage.googleapis.com" in req.full_url:
                captured_requests.append(req)
                return DummyResp()
            return urllib.request.urlopen(req, timeout=timeout)

        try:
            base_url = f"http://127.0.0.1:{proxy.server_port}"
            with patch.object(
                TransparentProxyHandler,
                "_open_upstream",
                side_effect=lambda req, timeout=None: (captured_requests.append(req), DummyResp())[1],
            ):
                req = urllib.request.Request(
                    f"{base_url}/v1beta/models/gemini-2.0-flash:generateContent?key=proxy",
                    data=b"{}",
                    headers={"Content-Type": "application/json", "x-goog-api-key": "dummy"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as resp:
                    self.assertEqual(resp.status, 200)

            self.assertEqual(len(captured_requests), 1)
            up_req = captured_requests[0]
            # Ensure ?key=proxy was replaced with real key and header has real key
            self.assertNotIn("key=proxy", up_req.full_url)
            self.assertIn("AIzaSyRealUpstreamKey999888777", up_req.full_url)
            header_map = {k.lower(): v for k, v in up_req.header_items()}
            self.assertEqual(header_map.get("x-goog-api-key"), "AIzaSyRealUpstreamKey999888777")
        finally:
            proxy.stop()

    def test_10_transparent_proxy_oauth_bearer_upstream_injection(self):
        """Verify Google OAuth Bearer token is injected as Authorization: Bearer when no API key exists."""
        self.vault.set_credential("google", "access_token", "ya29.OAuthAccessTokenForProxy")
        proxy = TransparentProxyServer(
            claude_provider=self.claude,
            gemini_provider=self.gemini,
            host="127.0.0.1",
            port=0,
        )
        proxy.start()
        captured_requests = []

        class DummyResp:
            status = 200
            headers = {"content-type": "application/json"}

            def read(self):
                return json.dumps({"models": []}).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        try:
            base_url = f"http://127.0.0.1:{proxy.server_port}"
            with patch.object(
                TransparentProxyHandler,
                "_open_upstream",
                side_effect=lambda r, timeout=None: (captured_requests.append(r), DummyResp())[1],
            ):
                req = urllib.request.Request(
                    f"{base_url}/v1beta/models",
                    headers={"x-goog-api-key": "proxy"},
                    method="GET",
                )
                with urllib.request.urlopen(req) as resp:
                    self.assertEqual(resp.status, 200)

            self.assertEqual(len(captured_requests), 1)
            header_map = {k.lower(): v for k, v in captured_requests[0].header_items()}
            self.assertEqual(header_map.get("authorization"), "Bearer ya29.OAuthAccessTokenForProxy")
            self.assertNotIn("x-goog-api-key", header_map)
        finally:
            proxy.stop()

    def test_11_claude_proxy_replaces_placeholder_api_key(self):
        """Verify Claude proxy replaces 'x-api-key: proxy' with vaulted DPAPI Claude key."""
        self.vault.set_credential("claude", "default", "sk-ant-api03-real-vaulted-key")
        proxy = TransparentProxyServer(
            claude_provider=self.claude,
            gemini_provider=self.gemini,
            host="127.0.0.1",
            port=0,
        )
        proxy.start()
        captured = []

        class DummyClaudeResp:
            status = 200
            headers = {"content-type": "application/json"}

            def read(self):
                return json.dumps(
                    {"model": "claude-3-7-sonnet", "usage": {"input_tokens": 25, "output_tokens": 75}}
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        try:
            base_url = f"http://127.0.0.1:{proxy.server_port}"
            with patch.object(
                TransparentProxyHandler,
                "_open_upstream",
                side_effect=lambda r, timeout=None: (captured.append(r), DummyClaudeResp())[1],
            ):
                req = urllib.request.Request(
                    f"{base_url}/v1/messages",
                    data=b'{"model":"claude-3-7-sonnet"}',
                    headers={"Content-Type": "application/json", "x-api-key": "proxy"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as resp:
                    self.assertEqual(resp.status, 200)

            self.assertEqual(len(captured), 1)
            header_map = {k.lower(): v for k, v in captured[0].header_items()}
            self.assertEqual(header_map.get("x-api-key"), "sk-ant-api03-real-vaulted-key")
        finally:
            proxy.stop()

    # =========================================================================
    # 2. MODULAR REPORTING ENGINE, PIVOT & CSV EXPORT TESTS (AIUM-607 / AIUM-902)
    # =========================================================================

    def test_12_reporting_engine_mixin_architecture(self):
        """Verify UsageDatabase / DatabaseEngine inherits ReportingEngineMixin cleanly."""
        self.assertTrue(issubclass(UsageDatabase, ReportingEngineMixin))
        self.assertIs(DatabaseEngine, UsageDatabase)
        self.assertTrue(hasattr(self.db, "get_multi_dimensional_pivot"))

    def test_13_historical_report_yearly_and_all_time_slices(self):
        """Verify hourly, daily, weekly, monthly, and yearly time slices in query_historical_report."""
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=1000,
            output_tokens=500,
            source="proxy",
            instance_id="node-main",
            client_ip="192.168.1.50",
        )
        for slice_name in ["hour", "hourly", "day", "daily", "week", "weekly", "month", "monthly", "year", "yearly"]:
            rep = self.db.query_historical_report(group_by=slice_name)
            self.assertGreaterEqual(rep["record_count"], 1)
            self.assertEqual(rep["summary"]["total_tokens"], 1500)

    def test_14_historical_report_client_alias_fallback_resolution(self):
        """Verify query_historical_report resolves client_alias from client_quotas when event alias is empty."""
        self.db.upsert_client_quota(client_ip="10.0.0.77", alias="Design-Workstation-77")
        self.db.record_usage_event(
            provider="gemini",
            model="gemini-2.5-pro",
            input_tokens=400,
            output_tokens=600,
            source="proxy",
            client_ip="10.0.0.77",
        )
        rep = self.db.query_historical_report(
            group_by="day", dimension="client_alias", client_ip="10.0.0.77"
        )
        self.assertEqual(len(rep["rows"]), 1)
        self.assertEqual(rep["rows"][0]["client_alias"], "Design-Workstation-77")
        self.assertEqual(rep["rows"][0]["group_key"], "Design-Workstation-77")

    def test_15_historical_report_cross_platform_tag_group_dimension(self):
        """Verify query_historical_report supports dimension='group' using cross_platform_tags."""
        self.db.add_cross_platform_tag(
            tag_name="Project-Atlas",
            target_type="provider",
            target_identifier="claude",
            description="Atlas Claude workload",
        )
        self.db.add_cross_platform_tag(
            tag_name="Project-Atlas",
            target_type="model",
            target_identifier="gemini-2.0-flash",
            description="Atlas Gemini workload",
        )
        self.db.record_usage_event(provider="claude", model="claude-3-7-sonnet", input_tokens=500, output_tokens=500)
        self.db.record_usage_event(provider="gemini", model="gemini-2.0-flash", input_tokens=1000, output_tokens=1000)

        rep = self.db.query_historical_report(group_by="day", dimension="group")
        self.assertEqual(rep["dimension"], "group")
        atlas_rows = [r for r in rep["rows"] if r["group_key"] == "Project-Atlas"]
        self.assertEqual(sum(r["total_tokens"] for r in atlas_rows), 3000)

    def test_16_historical_report_sorting_asc_and_desc(self):
        """Verify sort_by and sort_dir parameters order report rows accurately."""
        self.db.record_usage_event(provider="claude", model="m1", input_tokens=100, output_tokens=100)
        self.db.record_usage_event(provider="gemini", model="m2", input_tokens=2000, output_tokens=1000)

        rep_desc = self.db.query_historical_report(group_by="day", sort_by="total_tokens", sort_dir="desc")
        self.assertEqual(rep_desc["rows"][0]["provider"], "gemini")

        rep_asc = self.db.query_historical_report(group_by="day", sort_by="total_tokens", sort_dir="asc")
        self.assertEqual(rep_asc["rows"][0]["provider"], "claude")

    def test_17_export_historical_csv_full_v2_filters_and_columns(self):
        """Verify export_historical_csv honors source/instance_id/client_ip filters and outputs v2.0 columns."""
        self.db.upsert_client_quota(client_ip="192.168.1.88", alias="Dev-Laptop-88")
        self.db.record_usage_event(
            provider="gemini",
            model="gemini-2.0-flash",
            input_tokens=700,
            output_tokens=300,
            source="proxy",
            instance_id="edge-proxy-1",
            client_ip="192.168.1.88",
        )
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=5000,
            output_tokens=5000,
            source="direct",
            instance_id="local-default",
            client_ip="127.0.0.1",
        )

        csv_out = self.db.export_historical_csv(
            group_by="day",
            source="proxy",
            instance_id="edge-proxy-1",
            client_ip="192.168.1.88",
        )
        self.assertIn("Period,Provider,Account,Team,User,Model,Source,Instance,Client IP,Client Alias", csv_out)
        self.assertIn("edge-proxy-1", csv_out)
        self.assertIn("Dev-Laptop-88", csv_out)
        self.assertNotIn("claude-3-7-sonnet", csv_out)

    def test_18_pivot_metrics_with_cross_platform_group_tag(self):
        """Verify get_pivot_metrics supports 'group' (cross_platform_tags) and 'project' dimensions."""
        self.db.add_cross_platform_tag(
            tag_name="Core-AI-Cluster",
            target_type="provider",
            target_identifier="ollama",
        )
        self.db.record_usage_event(
            provider="ollama",
            model="qwen2.5:14b",
            input_tokens=1200,
            output_tokens=800,
            project_id="Local-RAG",
        )
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=500,
            output_tokens=500,
            project_id="Cloud-Agent",
        )

        pivot = self.db.get_pivot_metrics(dimensions="group,platform,project", window="24h")
        self.assertTrue(pivot["success"])
        self.assertEqual(pivot["totals"]["total_tokens"], 3000)
        groups = {r["group"]: r["total_tokens"] for r in pivot["rows"]}
        self.assertEqual(groups.get("Core-AI-Cluster"), 2000)
        self.assertEqual(groups.get("Untagged"), 1000)

    def test_19_http_api_reports_csv_and_pivot_endpoints(self):
        """Verify HTTP GET /api/reports/history?format=csv and GET /api/usage/pivot?dimensions=group,platform."""
        self.db.add_cross_platform_tag("Prod-Tag", "provider", "gemini")
        self.db.record_usage_event(
            provider="gemini",
            model="gemini-2.0-flash",
            input_tokens=900,
            output_tokens=100,
            source="proxy",
            instance_id="inst-99",
            client_ip="10.10.10.5",
        )

        server = AppHTTPServer(
            database=self.db,
            vault=self.vault,
            diagnostics=self.diag,
            providers={"claude": self.claude, "gemini": self.gemini},
            host="127.0.0.1",
            port=0,
        )
        server.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"

            # 1. CSV export with source & instance_id filter
            with urllib.request.urlopen(
                f"{base_url}/api/reports/history?format=csv&source=proxy&instance_id=inst-99"
            ) as resp:
                self.assertEqual(resp.status, 200)
                csv_text = resp.read().decode("utf-8")
                self.assertIn("inst-99", csv_text)
                self.assertIn("10.10.10.5", csv_text)

            # 2. Pivot endpoint with 'group' dimension
            with urllib.request.urlopen(
                f"{base_url}/api/usage/pivot?dimensions=group,platform&window=24h"
            ) as resp:
                self.assertEqual(resp.status, 200)
                pivot_data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(pivot_data["success"])
                self.assertEqual(pivot_data["rows"][0]["group"], "Prod-Tag")
                self.assertEqual(pivot_data["rows"][0]["total_tokens"], 1000)
        finally:
            server.stop()

    def test_20_reports_panel_html_contains_overhauled_controls(self):
        """Verify frontend/components/reports_panel.html includes Yearly slice, custom dates, filters, and Pivot card."""
        html_path = Path(__file__).resolve().parent.parent / "frontend" / "components" / "reports_panel.html"
        content = html_path.read_text(encoding="utf-8")
        self.assertIn("slice-btn-year", content)
        self.assertIn("report-filter-start-date", content)
        self.assertIn("report-filter-end-date", content)
        self.assertIn("report-filter-model", content)
        self.assertIn("report-filter-instance", content)
        self.assertIn("report-filter-client-ip", content)
        self.assertIn("sortReportsTable", content)
        self.assertIn("pivot-matrix-table-body", content)


if __name__ == "__main__":
    unittest.main()
