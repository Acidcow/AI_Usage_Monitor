#!/usr/bin/env python3
"""
Unit Tests for AIUM-705:
Per-Client Token Limitations, Burst Windows, Temporary Elevated Bypass & Compact Node Pool Display.
"""

import os
import sys
import time
import json
import uuid
import datetime
import tempfile
import unittest
import urllib.request
import urllib.error

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from backend.storage.database import UsageDatabase
from backend.discovery.node_registry import NodeRegistry
from backend.discovery.traffic_governor import TrafficGovernor
from backend.server.http_server import AppHTTPServer


class TestClientTokenLimitsAndCompactPool(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_client_limits.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.registry = NodeRegistry(database=self.db)
        self.governor = TrafficGovernor(registry=self.registry, database=self.db)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except Exception:
            pass

    # 1. Database Schema & Quota Defaults
    def test_client_quota_upsert_and_retrieval(self):
        client = self.db.upsert_client_quota(
            client_ip="192.168.2.3",
            alias="Jamese-PC",
            session_window_minutes=15,
            session_token_limit=10000,
            daily_token_limit=100000,
            priority=8,
            notes="Development Workstation"
        )
        self.assertEqual(client["client_ip"], "192.168.2.3")
        self.assertEqual(client["alias"], "Jamese-PC")
        self.assertEqual(client["session_token_limit"], 10000)
        self.assertEqual(client["daily_token_limit"], 100000)
        self.assertEqual(client["priority"], 8)

        fetched = self.db.get_client_quota("192.168.2.3")
        self.assertEqual(fetched["alias"], "Jamese-PC")
        self.assertEqual(fetched["session_token_limit"], 10000)

    def test_default_quota_returned_for_new_client(self):
        """New unconfigured clients should return sensible default limits."""
        fetched = self.db.get_client_quota("10.0.0.99")
        self.assertEqual(fetched["client_ip"], "10.0.0.99")
        self.assertGreater(fetched["session_token_limit"], 0)
        self.assertGreater(fetched["daily_token_limit"], 0)
        self.assertEqual(fetched["is_unrestricted"], 0)

    def test_list_client_quotas(self):
        self.db.upsert_client_quota(client_ip="192.168.1.10", alias="Node-1")
        self.db.upsert_client_quota(client_ip="192.168.1.20", alias="Node-2")
        clients = self.db.list_client_quotas()
        ips = [c["client_ip"] for c in clients]
        self.assertIn("192.168.1.10", ips)
        self.assertIn("192.168.1.20", ips)

    # 2. Token Recording & Sliding Burst Window
    def test_record_client_tokens_and_usage_calc(self):
        client_ip = "192.168.2.5"
        self.db.upsert_client_quota(client_ip=client_ip, session_token_limit=5000, daily_token_limit=50000)

        # Record 1500 tokens
        self.db.record_client_tokens(client_ip, tokens=1500)
        usage = self.db.get_client_token_usage(client_ip)

        self.assertEqual(usage["session_tokens_used"], 1500)
        self.assertEqual(usage["daily_tokens_used"], 1500)
        self.assertEqual(usage["session_tokens_remaining"], 3500)
        self.assertEqual(usage["daily_tokens_remaining"], 48500)

    def test_burst_window_sliding_expiration(self):
        """Tokens older than the session window should expire from the burst counter."""
        client_ip = "192.168.2.6"
        self.db.upsert_client_quota(client_ip=client_ip, session_window_minutes=15, session_token_limit=5000)

        # Insert an old usage record from 20 minutes ago
        past_time = time.time() - (20 * 60)
        self.db.record_client_tokens(client_ip, tokens=3000, timestamp=past_time)

        # Insert a current usage record
        self.db.record_client_tokens(client_ip, tokens=1000)

        usage = self.db.get_client_token_usage(client_ip)
        # Session window (15m) should only count 1000, but daily (24h) counts 4000
        self.assertEqual(usage["session_tokens_used"], 1000)
        self.assertEqual(usage["daily_tokens_used"], 4000)

    def test_reset_client_tokens(self):
        client_ip = "192.168.2.7"
        self.db.record_client_tokens(client_ip, tokens=4000)
        self.db.reset_client_tokens(client_ip)
        usage = self.db.get_client_token_usage(client_ip)
        self.assertEqual(usage["session_tokens_used"], 0)
        self.assertEqual(usage["daily_tokens_used"], 0)

    # 3. Temporary & Scheduled Bypass
    def test_temporary_bypass_activation_and_expiry(self):
        client_ip = "192.168.2.8"
        self.db.upsert_client_quota(client_ip=client_ip, session_token_limit=1000)

        # Set 30 minute bypass
        self.db.set_client_temporary_bypass(client_ip, duration_minutes=30)
        client = self.db.get_client_quota(client_ip)
        self.assertTrue(self.db.is_client_bypass_active(client))

        # Set expired bypass (negative duration)
        self.db.set_client_temporary_bypass(client_ip, duration_minutes=-10)
        client = self.db.get_client_quota(client_ip)
        self.assertFalse(self.db.is_client_bypass_active(client))

    def test_scheduled_bypass_window(self):
        client_ip = "192.168.2.9"
        now = datetime.datetime.now(datetime.timezone.utc)
        start_iso = (now - datetime.timedelta(hours=1)).isoformat()
        end_iso = (now + datetime.timedelta(hours=2)).isoformat()

        self.db.set_client_scheduled_bypass(client_ip, start_iso=start_iso, end_iso=end_iso)
        client = self.db.get_client_quota(client_ip)
        self.assertTrue(self.db.is_client_bypass_active(client))

        # Future window (not yet started)
        future_start = (now + datetime.timedelta(hours=2)).isoformat()
        future_end = (now + datetime.timedelta(hours=5)).isoformat()
        self.db.set_client_scheduled_bypass(client_ip, start_iso=future_start, end_iso=future_end)
        client = self.db.get_client_quota(client_ip)
        self.assertFalse(self.db.is_client_bypass_active(client))

    def test_clear_client_bypass(self):
        client_ip = "192.168.2.10"
        self.db.set_client_temporary_bypass(client_ip, duration_minutes=60)
        self.db.clear_client_bypass(client_ip)
        client = self.db.get_client_quota(client_ip)
        self.assertFalse(self.db.is_client_bypass_active(client))

    # 4. Traffic Governor Enforcement
    def test_governor_allows_within_limits(self):
        client_ip = "192.168.2.11"
        self.db.upsert_client_quota(client_ip=client_ip, session_token_limit=5000, daily_token_limit=50000)
        allowed, err, details = self.governor.check_client_allowance(client_ip, requested_tokens=500)
        self.assertTrue(allowed)
        self.assertIsNone(err)

    def test_governor_blocks_session_burst_overload(self):
        client_ip = "192.168.2.12"
        self.db.upsert_client_quota(client_ip=client_ip, session_token_limit=2000, daily_token_limit=50000)
        self.db.record_client_tokens(client_ip, tokens=1800)

        # Requesting 500 when only 200 remain in burst window
        allowed, err, details = self.governor.check_client_allowance(client_ip, requested_tokens=500)
        self.assertFalse(allowed)
        self.assertIn("Burst Window Quota Exceeded", err)
        self.assertEqual(details["retry_after_reason"], "burst_window_limit")

    def test_governor_blocks_daily_limit_exceeded(self):
        client_ip = "192.168.2.13"
        self.db.upsert_client_quota(client_ip=client_ip, session_token_limit=50000, daily_token_limit=5000)
        self.db.record_client_tokens(client_ip, tokens=4800)

        allowed, err, details = self.governor.check_client_allowance(client_ip, requested_tokens=500)
        self.assertFalse(allowed)
        self.assertIn("Daily Token Quota Exceeded", err)
        self.assertEqual(details["retry_after_reason"], "daily_limit")

    def test_governor_permits_unrestricted_client(self):
        client_ip = "192.168.2.14"
        self.db.upsert_client_quota(client_ip=client_ip, session_token_limit=1000, daily_token_limit=1000, is_unrestricted=1)
        self.db.record_client_tokens(client_ip, tokens=50000)  # Way over limits

        allowed, err, details = self.governor.check_client_allowance(client_ip, requested_tokens=10000)
        self.assertTrue(allowed)
        self.assertIsNone(err)

    def test_governor_permits_temporary_bypass_client(self):
        client_ip = "192.168.2.15"
        self.db.upsert_client_quota(client_ip=client_ip, session_token_limit=1000, daily_token_limit=1000)
        self.db.record_client_tokens(client_ip, tokens=5000)
        self.db.set_client_temporary_bypass(client_ip, duration_minutes=30)

        allowed, err, details = self.governor.check_client_allowance(client_ip, requested_tokens=2000)
        self.assertTrue(allowed)
        self.assertIsNone(err)

    def test_governor_enforces_model_restrictions(self):
        client_ip = "192.168.2.16"
        self.db.upsert_client_quota(
            client_ip=client_ip,
            allowed_models=["llama3:8b", "codellama:7b"],
            blocked_models=["deepseek-r1:70b"]
        )

        # Allowed model
        allowed, err, _ = self.governor.check_client_allowance(client_ip, model_name="llama3:8b")
        self.assertTrue(allowed)

        # Blocked model
        allowed, err, _ = self.governor.check_client_allowance(client_ip, model_name="deepseek-r1:70b")
        self.assertFalse(allowed)
        self.assertIn("Model restricted", err)

        # Model not in allowed list
        allowed, err, _ = self.governor.check_client_allowance(client_ip, model_name="mistral:latest")
        self.assertFalse(allowed)
        self.assertIn("Model restricted", err)

    def test_governor_enforces_node_restrictions(self):
        client_ip = "192.168.2.17"
        self.db.upsert_client_quota(
            client_ip=client_ip,
            allowed_nodes=["node_asus_rog"],
            blocked_nodes=["node_quarantined_laptop"]
        )

        allowed, err, _ = self.governor.check_client_allowance(client_ip, node_id="node_asus_rog")
        self.assertTrue(allowed)

        allowed, err, _ = self.governor.check_client_allowance(client_ip, node_id="node_quarantined_laptop")
        self.assertFalse(allowed)
        self.assertIn("Node restricted", err)

    # 5. REST API Endpoints
    def test_rest_api_client_endpoints(self):
        from backend.security.dpapi_vault import DPAPIVault
        from backend.diagnostics.logging_engine import DiagnosticsEngine
        from backend.providers import ClaudeProvider

        vault = DPAPIVault()
        diagnostics = DiagnosticsEngine()
        claude = ClaudeProvider(database=self.db, vault=vault, diagnostics=diagnostics)
        server = AppHTTPServer(
            database=self.db,
            vault=vault,
            diagnostics=diagnostics,
            providers={"claude": claude},
            host="127.0.0.1",
            port=0,
            scanner=None,
            registry=self.registry,
            governor=self.governor
        )
        server.start()
        port = server.server_port

        try:
            # 1. GET /api/discovery/clients (empty initially)
            url = f"http://127.0.0.1:{port}/api/discovery/clients"
            req = urllib.request.urlopen(url)
            self.assertEqual(req.status, 200)
            data = json.loads(req.read().decode())
            self.assertIn("clients", data)

            # 2. POST /api/discovery/clients
            post_data = {
                "client_ip": "192.168.2.50",
                "alias": "Dev-Laptop",
                "session_token_limit": 15000,
                "daily_token_limit": 150000,
                "priority": 7
            }
            req_post = urllib.request.Request(
                url,
                data=json.dumps(post_data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            res_post = urllib.request.urlopen(req_post)
            self.assertEqual(res_post.status, 200)
            data_post = json.loads(res_post.read().decode())
            self.assertTrue(data_post["success"])
            self.assertEqual(data_post["client"]["alias"], "Dev-Laptop")

            # 3. POST /api/discovery/clients/bypass
            bypass_data = {
                "client_ip": "192.168.2.50",
                "duration_minutes": 120
            }
            req_bypass = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/discovery/clients/bypass",
                data=json.dumps(bypass_data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            res_bypass = urllib.request.urlopen(req_bypass)
            self.assertEqual(res_bypass.status, 200)
            data_bypass = json.loads(res_bypass.read().decode())
            self.assertTrue(data_bypass["success"])

            # 4. DELETE /api/discovery/clients
            req_del = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/discovery/clients?client_ip=192.168.2.50",
                method="DELETE"
            )
            res_del = urllib.request.urlopen(req_del)
            self.assertEqual(res_del.status, 200)
        finally:
            server.stop()

    def test_query_console_enforces_client_rate_limiting(self):
        """POST /api/discovery/query must extract client IP and reject if burst limit exceeded."""
        from backend.security.dpapi_vault import DPAPIVault
        from backend.diagnostics.logging_engine import DiagnosticsEngine
        from backend.providers import ClaudeProvider

        vault = DPAPIVault()
        diagnostics = DiagnosticsEngine()
        claude = ClaudeProvider(database=self.db, vault=vault, diagnostics=diagnostics)
        server = AppHTTPServer(
            database=self.db,
            vault=vault,
            diagnostics=diagnostics,
            providers={"claude": claude},
            host="127.0.0.1",
            port=0,
            registry=self.registry,
            governor=self.governor
        )
        server.start()
        port = server.server_port

        try:
            # Set tiny session limit for loopback 127.0.0.1
            self.db.upsert_client_quota(client_ip="127.0.0.1", session_token_limit=10, daily_token_limit=10)
            self.db.record_client_tokens("127.0.0.1", tokens=50)

            url = f"http://127.0.0.1:{port}/api/discovery/query"
            payload = {
                "target": "pool",
                "model": "llama3:latest",
                "prompt": "Hello test"
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 429)
            err_data = json.loads(ctx.exception.read().decode())
            self.assertIn("Burst Window Quota Exceeded", err_data.get("error", ""))
        finally:
            server.stop()

    def test_client_alias_resolution_from_device_inventory(self):
        """When a client connects from an IP present in device_inventory, its alias is resolved."""
        self.db.upsert_device_inventory(
            alias="ASUS-ROG-James",
            ip="192.168.2.99",
            state="KNOWN_SERVICES"
        )
        resolved_alias = self.db.resolve_client_alias("192.168.2.99")
        self.assertEqual(resolved_alias, "ASUS-ROG-James")

        # Unknown IP returns the IP itself
        self.assertEqual(self.db.resolve_client_alias("192.168.2.199"), "192.168.2.199")

    def test_compact_compute_node_card_formatting_helper(self):
        """Format node payload with prominent alias/IP header and model chips."""
        node = {
            "id": "node_test_1",
            "name": "Jamese-PC (10.1.7.74)",
            "endpoint": "http://10.1.7.74:11434",
            "engine": "ollama",
            "models": [{"name": "llama3:8b", "size": "4.7GB", "parameter_size": "8B"}, {"name": "qwen2.5-coder:7b", "size": "4.2GB"}],
            "status": "ONLINE",
            "is_trusted": 1,
            "compute_group": "Active Compute"
        }
        card_meta = self.registry.format_compact_node_card(node)
        self.assertEqual(card_meta["header_title"], "Jamese-PC (10.1.7.74)")
        self.assertEqual(card_meta["engine_label"], "🦙 Ollama")
        self.assertEqual(len(card_meta["models"]), 2)
        self.assertEqual(card_meta["models"][0]["name"], "llama3:8b")


if __name__ == "__main__":
    unittest.main()
