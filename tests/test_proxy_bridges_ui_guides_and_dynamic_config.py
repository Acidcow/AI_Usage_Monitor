import unittest
import json
import time
import os
import tempfile
import urllib.request
import urllib.error
import socket
import threading

from backend.storage.database import UsageDatabase
from backend.discovery.node_registry import NodeRegistry
from backend.discovery.traffic_governor import TrafficGovernor
from backend.mcp.server import MCPServer
from backend.server.http_server import AppHTTPServer

def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class TestProxyBridgesUIGuidesAndDynamicConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_config_guides.db")
        cls.db = UsageDatabase(cls.db_path)
        cls.registry = NodeRegistry(cls.db)
        cls.governor = TrafficGovernor(cls.registry, cls.db)
        cls.mcp_server = MCPServer(scanner=None, registry=cls.registry, governor=cls.governor)

        cls.http_port = get_free_port()
        cls.server = AppHTTPServer(
            database=cls.db,
            vault=None,
            diagnostics=None,
            providers={},
            host="127.0.0.1",
            port=cls.http_port,
            proxy_port=8766,
            registry=cls.registry,
            governor=cls.governor,
            mcp_server=cls.mcp_server
        )
        cls.server.start()
        time.sleep(0.15)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.temp_dir.cleanup()

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.http_port}{path}"

    def test_01_dynamic_port_settings_defaults(self):
        """Assert get_all_settings returns default ports for emulator and transparent proxy."""
        st = self.db.get_all_settings()
        self.assertEqual(st.get("ollama_emulator_port"), 8989)
        self.assertEqual(st.get("transparent_proxy_port"), 8766)

    def test_02_persisting_custom_bridge_ports(self):
        """Assert custom bridge ports can be persisted into app_settings."""
        self.db.set_setting("ollama_emulator_port", 9090)
        self.db.set_setting("transparent_proxy_port", 8888)
        st = self.db.get_all_settings()
        self.assertEqual(st.get("ollama_emulator_port"), 9090)
        self.assertEqual(st.get("transparent_proxy_port"), 8888)
        # Restore defaults
        self.db.set_setting("ollama_emulator_port", 8989)
        self.db.set_setting("transparent_proxy_port", 8766)

    def test_03_default_quota_settings_in_app_settings(self):
        """Assert default session burst window and daily limit are in get_all_settings."""
        st = self.db.get_all_settings()
        self.assertEqual(st.get("default_session_window_minutes"), 15)
        self.assertEqual(st.get("default_session_token_limit"), 25000)
        self.assertEqual(st.get("default_daily_token_limit"), 250000)

    def test_04_unconfigured_client_inherits_dynamic_defaults(self):
        """Assert get_client_quota for unconfigured client uses dynamic app_settings defaults."""
        quota = self.db.get_client_quota("192.168.10.55")
        self.assertEqual(quota.get("session_window_minutes"), 15)
        self.assertEqual(quota.get("session_token_limit"), 25000)
        self.assertEqual(quota.get("daily_token_limit"), 250000)

    def test_05_updating_default_quota_reflects_dynamically(self):
        """Assert changing default quota in app_settings immediately affects unconfigured clients."""
        self.db.set_setting("default_session_token_limit", 35000)
        self.db.set_setting("default_session_window_minutes", 20)
        quota = self.db.get_client_quota("192.168.10.99")
        self.assertEqual(quota.get("session_token_limit"), 35000)
        self.assertEqual(quota.get("session_window_minutes"), 20)
        # Reset defaults
        self.db.set_setting("default_session_token_limit", 25000)
        self.db.set_setting("default_session_window_minutes", 15)

    def test_06_client_discovery_from_client_quotas(self):
        """Assert client explicitly saved in client_quotas is returned in integrated clients."""
        self.db.upsert_client_quota(
            client_ip="192.168.1.101",
            alias="Dev Box Alpha",
            session_window_minutes=15,
            session_token_limit=30000,
            daily_token_limit=300000
        )
        clients = self.db.list_all_integrated_clients()
        ips = [c["client_ip"] for c in clients]
        self.assertIn("192.168.1.101", ips)
        entry = next(c for c in clients if c["client_ip"] == "192.168.1.101")
        self.assertEqual(entry["alias"], "Dev Box Alpha")

    def test_07_client_discovery_from_token_windows_without_prior_quota(self):
        """Assert client with recorded token activity is discovered even if never manually configured."""
        self.db.record_client_tokens("10.0.5.22", 150)
        clients = self.db.list_all_integrated_clients()
        ips = [c["client_ip"] for c in clients]
        self.assertIn("10.0.5.22", ips)

    def test_08_client_discovery_from_usage_events_without_prior_quota(self):
        """Assert client with usage events is discovered even if never manually configured."""
        self.db.record_usage_event(
            provider="ollama",
            model="llama3:8b",
            input_tokens=20,
            output_tokens=40,
            session_id="test_session_ext",
            client_ip="172.16.0.44",
            client_alias="Kubernetes Pod Worker"
        )
        clients = self.db.list_all_integrated_clients()
        ips = [c["client_ip"] for c in clients]
        self.assertIn("172.16.0.44", ips)
        entry = next(c for c in clients if c["client_ip"] == "172.16.0.44")
        self.assertEqual(entry["alias"], "Kubernetes Pod Worker")

    def test_09_client_alias_resolution(self):
        """Assert alias resolution falls back gracefully from device inventory or IP."""
        self.db.upsert_device_inventory(alias="Studio GPU Node", ip="192.168.1.200")
        alias = self.db.resolve_client_alias("192.168.1.200")
        self.assertEqual(alias, "Studio GPU Node")

    def test_10_traffic_governor_enforces_blocked_client(self):
        """Assert TrafficGovernor blocks client marked with is_blocked=1 or limit=0 returning HTTP 403."""
        self.db.upsert_client_quota(
            client_ip="192.168.1.66",
            alias="Abusive Client",
            session_token_limit=0,
            daily_token_limit=0,
            notes="Blocked due to abuse"
        )
        allowed, err, details = self.governor.check_client_allowance("192.168.1.66", 10)
        self.assertFalse(allowed)
        self.assertTrue("Blocked" in (err or "") or "restricted" in (err or "") or "Limit" in (err or ""))

    def test_11_traffic_governor_respects_unrestricted_client(self):
        """Assert TrafficGovernor allows unrestricted client past any burst usage."""
        self.db.upsert_client_quota(
            client_ip="192.168.1.77",
            alias="VIP Agent",
            session_token_limit=10,
            is_unrestricted=1
        )
        self.db.record_client_tokens("192.168.1.77", 500)
        allowed, err, details = self.governor.check_client_allowance("192.168.1.77", 100)
        self.assertTrue(allowed)

    def test_12_traffic_governor_respects_temporary_elevated_bypass(self):
        """Assert temporary elevated bypass allows client past normal limits."""
        self.db.upsert_client_quota(
            client_ip="192.168.1.88",
            session_token_limit=10,
            daily_token_limit=10
        )
        self.db.record_client_tokens("192.168.1.88", 50)
        # Activate 30 min temporary bypass
        self.db.set_client_temporary_bypass("192.168.1.88", 30.0)
        allowed, err, details = self.governor.check_client_allowance("192.168.1.88", 50)
        self.assertTrue(allowed)
        self.assertTrue(details.get("bypass_active"))

    def test_13_traffic_governor_clear_bypass_re_enforces_limits(self):
        """Assert clearing bypass immediately re-enforces quotas."""
        self.db.clear_client_bypass("192.168.1.88")
        allowed, err, details = self.governor.check_client_allowance("192.168.1.88", 50)
        self.assertFalse(allowed)

    def test_14_http_get_settings_returns_bridge_ports_and_quotas(self):
        """Assert GET /api/settings exposes bridge ports and default quota parameters."""
        req = urllib.request.Request(self._url("/api/settings"))
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("ollama_emulator_port", data)
            self.assertIn("transparent_proxy_port", data)
            self.assertIn("default_session_window_minutes", data)
            self.assertIn("default_session_token_limit", data)

    def test_15_http_post_settings_updates_bridge_configuration(self):
        """Assert POST /api/settings updates bridge ports and quota defaults."""
        payload = {
            "settings": {
                "ollama_emulator_port": 8990,
                "transparent_proxy_port": 8767,
                "default_session_window_minutes": 25,
                "default_session_token_limit": 50000
            }
        }
        req = urllib.request.Request(
            self._url("/api/settings"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            st = data.get("settings", {})
            self.assertEqual(st.get("ollama_emulator_port"), 8990)
            self.assertEqual(st.get("default_session_token_limit"), 50000)

        # Reset to defaults
        self.db.set_setting("ollama_emulator_port", 8989)
        self.db.set_setting("transparent_proxy_port", 8766)
        self.db.set_setting("default_session_window_minutes", 15)
        self.db.set_setting("default_session_token_limit", 25000)

    def test_16_http_get_discovery_clients_returns_all_integrated_clients(self):
        """Assert GET /api/discovery/clients returns list of all integrated clients."""
        req = urllib.request.Request(self._url("/api/discovery/clients"))
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("clients", data)
            ips = [c["client_ip"] for c in data["clients"]]
            self.assertIn("192.168.1.101", ips)

    def test_17_http_post_discovery_clients_saves_policy_and_blocks(self):
        """Assert POST /api/discovery/clients can save custom alias, window, and block client."""
        payload = {
            "client_ip": "10.10.10.5",
            "alias": "Restricted Workstation",
            "session_window_minutes": 10,
            "session_token_limit": 5000,
            "daily_token_limit": 50000,
            "is_blocked": 1
        }
        req = urllib.request.Request(
            self._url("/api/discovery/clients"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            client = data.get("client", {})
            self.assertEqual(client.get("alias"), "Restricted Workstation")
            self.assertEqual(client.get("is_blocked"), 1)

    def test_18_http_post_discovery_clients_unrestricts_client(self):
        """Assert POST /api/discovery/clients can set client to unrestricted."""
        payload = {
            "client_ip": "10.10.10.5",
            "is_unrestricted": 1
        }
        req = urllib.request.Request(
            self._url("/api/discovery/clients"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("client", {}).get("is_unrestricted"), 1)

    def test_19_http_post_discovery_clients_bypass_temporary(self):
        """Assert POST /api/discovery/clients/bypass activates temporary bypass."""
        payload = {"client_ip": "10.10.10.5", "duration_minutes": 60}
        req = urllib.request.Request(
            self._url("/api/discovery/clients/bypass"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIsNotNone(data.get("client", {}).get("bypass_until"))

    def test_20_http_delete_discovery_clients_reset_tokens(self):
        """Assert DELETE /api/discovery/clients?action=reset purges token window records."""
        self.db.record_client_tokens("10.10.10.5", 800)
        req = urllib.request.Request(
            self._url("/api/discovery/clients?client_ip=10.10.10.5&action=reset"),
            method="DELETE"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
        # Verify tokens were cleared
        usage = self.db.get_client_token_usage("10.10.10.5")
        self.assertEqual(usage.get("session_tokens_used"), 0)

    def test_21_html_component_contains_antigravity_mcp_config_guide(self):
        """Assert provider_hub.html contains Antigravity MCP JSON snippet and global path."""
        hub_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "components", "provider_hub.html")
        with open(hub_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Google Antigravity IDE &amp; Antigravity CLI Integration", html)
        self.assertIn("mcp_config.json", html)
        self.assertIn("get_usage_summary", html)
        self.assertIn("get_provider_quotas", html)
        self.assertIn("get_proxy_endpoints", html)
        self.assertIn("backend.mcp.server", html)

    def test_22_html_component_contains_vscode_and_funneling_guides(self):
        """Assert provider_hub.html contains VSCode Cline, Continue.dev, and proxy funneling."""
        hub_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "components", "provider_hub.html")
        with open(hub_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("cline_mcp_settings.json", html)
        self.assertIn("Continue.dev Model Provider", html)
        self.assertIn("$env:HTTP_PROXY='http://127.0.0.1:8766'", html)
        self.assertIn("ANTHROPIC_BASE_URL", html)

    def test_23_mcp_server_http_rpc_endpoint(self):
        """Assert POST /api/mcp/rpc executes JSON-RPC 2.0 requests over HTTP."""
        req_payload = {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/list",
            "params": {}
        }
        req = urllib.request.Request(
            self._url("/api/mcp/rpc"),
            data=json.dumps(req_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("jsonrpc"), "2.0")
            self.assertEqual(data.get("id"), 99)
            tools = data.get("result", {}).get("tools", [])
            tool_names = [t["name"] for t in tools]
            self.assertIn("get_usage_summary", tool_names)
            self.assertIn("get_provider_quotas", tool_names)
            self.assertIn("get_proxy_endpoints", tool_names)

if __name__ == "__main__":
    unittest.main()

