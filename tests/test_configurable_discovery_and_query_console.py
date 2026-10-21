import unittest
import os
import json
import time
import socket
import tempfile
import urllib.request
import urllib.error
from unittest.mock import MagicMock, patch

from backend.storage.database import UsageDatabase
from backend.discovery.lan_scanner import LANScanner, STANDARD_AI_PORTS, PLATFORM_CATALOG
from backend.discovery.node_registry import NodeRegistry
from backend.discovery.traffic_governor import TrafficGovernor
from backend.server.http_server import AppHTTPServer
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine

class TestConfigurableDiscoveryAndQueryConsole(unittest.TestCase):
    """
    Test suite for AIUM-704 / FR-704:
    - Multi-subnet and adapter detection
    - Flexible target parsing (CIDR, ranges, hostnames/aliases)
    - Platform catalog checkboxes & secondary ports
    - 3-color device state classification (Turquoise, Red, Orange)
    - Persistent device inventory in SQLite
    - Trusted vs untrusted compute groups with auto-exclusion rules
    - Pool routing with failover and trusted node prioritization
    - Interactive query console with file attachment context & security warnings
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_discovery_704.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.registry = NodeRegistry(database=self.db)
        self.governor = TrafficGovernor(registry=self.registry, database=self.db)
        self.scanner = LANScanner()

    def tearDown(self):
        self.tmp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Adapter & Multi-Subnet Detection
    # -------------------------------------------------------------------------
    def test_detect_local_network_adapters(self):
        """Assert scanner discovers local IPv4 addresses, hostnames, and derived subnets."""
        adapters = self.scanner.get_local_adapters_and_subnets()
        self.assertIsInstance(adapters, list)
        self.assertGreater(len(adapters), 0)
        first = adapters[0]
        self.assertIn("ip", first)
        self.assertIn("subnet", first)
        self.assertIn("hostname", first)

    # -------------------------------------------------------------------------
    # 2. Flexible Target Parsing (CIDRs, Ranges, Hostnames & Aliases)
    # -------------------------------------------------------------------------
    def test_parse_cidr_targets(self):
        """Assert CIDR notation (e.g. 10.1.7.0/29) expands to the exact discrete host IP addresses."""
        targets = self.scanner.parse_target_spec("10.1.7.0/29")
        # /29 gives 8 total IPs (10.1.7.0 to 10.1.7.7), host IPs are 10.1.7.1 to 10.1.7.6
        self.assertTrue(any(ip == "10.1.7.1" for ip in targets))
        self.assertTrue(any(ip == "10.1.7.6" for ip in targets))
        self.assertLessEqual(len(targets), 8)

    def test_parse_range_targets(self):
        """Assert range notation (e.g. 10.1.7.50-10.1.7.54) expands to contiguous IPs."""
        targets = self.scanner.parse_target_spec("10.1.7.50 - 10.1.7.54")
        expected = ["10.1.7.50", "10.1.7.51", "10.1.7.52", "10.1.7.53", "10.1.7.54"]
        self.assertEqual(targets, expected)

    def test_parse_hybrid_and_aliases(self):
        """Assert comma-separated list of hostnames, aliases, and IPs parses correctly."""
        targets = self.scanner.parse_target_spec("127.0.0.1, localhost, 10.1.7.74")
        self.assertIn("127.0.0.1", targets)
        self.assertIn("10.1.7.74", targets)

    def test_parse_safety_clamping(self):
        """Assert scanning wide subnet (like /16) is clamped by default to prevent network storm."""
        targets = self.scanner.parse_target_spec("10.1.0.0/16", max_hosts=256)
        self.assertLessEqual(len(targets), 256)

    # -------------------------------------------------------------------------
    # 3. Platform Catalog & Secondary Port Filtering
    # -------------------------------------------------------------------------
    def test_platform_catalog_definitions(self):
        """Assert PLATFORM_CATALOG exposes expected platforms and default ports."""
        self.assertIn("ollama", PLATFORM_CATALOG)
        self.assertIn("lmstudio", PLATFORM_CATALOG)
        self.assertIn("vllm", PLATFORM_CATALOG)
        self.assertEqual(PLATFORM_CATALOG["ollama"]["port"], 11434)
        self.assertEqual(PLATFORM_CATALOG["lmstudio"]["port"], 1234)

    def test_build_scan_targets_with_selected_platforms_and_secondary_ports(self):
        """Assert target tuples (ip, port) build properly from selected platform checkboxes and custom ports."""
        ips = ["10.1.7.74"]
        targets = self.scanner.build_scan_targets(
            ips=ips,
            platforms=["ollama", "lmstudio"],
            secondary_ports=[11435, 8001]
        )
        # Expected ports: 11434 (ollama), 1234 (lmstudio), 11435, 8001
        ports = [p for ip, p in targets]
        self.assertIn(11434, ports)
        self.assertIn(1234, ports)
        self.assertIn(11435, ports)
        self.assertIn(8001, ports)

    # -------------------------------------------------------------------------
    # 4. Device State Classification (Turquoise, Red, Orange)
    # -------------------------------------------------------------------------
    def test_classify_device_states(self):
        """Assert devices are classified into KNOWN_SERVICES, NO_SERVICES, or PENDING."""
        # 1. Device with confirmed AI engine
        cand_with_service = {
            "ip": "10.1.7.74",
            "port": 11434,
            "engine": "ollama",
            "models": [{"name": "llama3:latest"}]
        }
        state1 = self.scanner.classify_device(cand_with_service)
        self.assertEqual(state1, "KNOWN_SERVICES")

        # 2. Host responsive but no AI ports open
        cand_no_service = {
            "ip": "10.1.7.80",
            "host_responsive": True,
            "engine": None,
            "models": []
        }
        state2 = self.scanner.classify_device(cand_no_service)
        self.assertEqual(state2, "NO_SERVICES")

        # 3. Host unscanned / pending
        cand_pending = {
            "ip": "10.1.7.99",
            "host_responsive": False,
            "engine": None
        }
        state3 = self.scanner.classify_device(cand_pending)
        self.assertEqual(state3, "PENDING")

    # -------------------------------------------------------------------------
    # 5. Persistent Device Inventory Storage in SQLite
    # -------------------------------------------------------------------------
    def test_device_inventory_crud(self):
        """Assert upserting, retrieving, listing, and deleting devices in device_inventory."""
        dev = self.db.upsert_device_inventory(
            alias="Jamese-PC",
            ip="10.1.7.74",
            state="KNOWN_SERVICES",
            discovered_services=[{"engine": "ollama", "port": 11434}],
            is_trusted=1,
            compute_group="Active Compute",
            notes="ASUS ROG Gaming Rig"
        )
        self.assertIsNotNone(dev)
        self.assertEqual(dev["alias"], "Jamese-PC")
        self.assertEqual(dev["ip"], "10.1.7.74")
        self.assertEqual(dev["state"], "KNOWN_SERVICES")
        self.assertEqual(dev["is_trusted"], 1)

        # Retrieve
        fetched = self.db.get_device_inventory("Jamese-PC")
        self.assertEqual(fetched["ip"], "10.1.7.74")

        # Update
        updated = self.db.upsert_device_inventory(
            alias="Jamese-PC",
            ip="10.1.7.74",
            state="KNOWN_SERVICES",
            is_trusted=1,
            compute_group="Active Compute",
            notes="Updated note"
        )
        self.assertEqual(updated["notes"], "Updated note")

        # List
        devs = self.db.list_device_inventory()
        self.assertEqual(len(devs), 1)

        # Delete
        deleted = self.db.delete_device_inventory("Jamese-PC")
        self.assertTrue(deleted)
        self.assertIsNone(self.db.get_device_inventory("Jamese-PC"))

    # -------------------------------------------------------------------------
    # 6. Trust & Compute Group Guardrails
    # -------------------------------------------------------------------------
    def test_untrusted_node_auto_excluded_from_active_compute(self):
        """Assert registering or updating a node with is_trusted=0 automatically excludes it from 'Active Compute'."""
        # Attempt to register untrusted node into 'Active Compute'
        node = self.registry.register_node(
            name="Untrusted Lab Server",
            endpoint="http://10.1.7.99:11434",
            engine="ollama",
            is_trusted=0,
            compute_group="Active Compute"
        )
        # Invariant: Must NOT be in 'Active Compute'
        self.assertEqual(node["is_trusted"], 0)
        self.assertNotEqual(node["compute_group"], "Active Compute")
        self.assertIn(node["compute_group"], ["Quarantined", "Untrusted", "Other"])

    def test_marking_node_untrusted_evicts_from_active_compute(self):
        """Assert toggling an existing active node to untrusted evicts it from 'Active Compute'."""
        node = self.registry.register_node(
            name="Trusted Node",
            endpoint="http://10.1.7.74:11434",
            engine="ollama",
            is_trusted=1,
            compute_group="Active Compute"
        )
        self.assertEqual(node["compute_group"], "Active Compute")

        # User toggles trust to 0
        updated = self.registry.update_node(node["id"], is_trusted=0)
        self.assertEqual(updated["is_trusted"], 0)
        self.assertNotEqual(updated["compute_group"], "Active Compute")

    # -------------------------------------------------------------------------
    # 7. Pool Routing with Failover & Trusted Prioritization
    # -------------------------------------------------------------------------
    def test_pool_routing_dispatches_to_highest_priority_trusted_node(self):
        """Assert dispatching to 'pool' selects the highest priority trusted online node."""
        node1 = self.registry.register_node(
            name="Primary GPU",
            endpoint="http://10.1.7.74:11434",
            engine="ollama",
            priority=10,
            is_trusted=1,
            compute_group="Active Compute"
        )
        node2 = self.registry.register_node(
            name="Secondary GPU",
            endpoint="http://10.1.7.75:11434",
            engine="ollama",
            priority=5,
            is_trusted=1,
            compute_group="Active Compute"
        )
        # Untrusted node (should never be selected)
        node3 = self.registry.register_node(
            name="Untrusted Node",
            endpoint="http://10.1.7.99:11434",
            engine="ollama",
            priority=20, # Higher priority, but untrusted!
            is_trusted=0,
            compute_group="Quarantined"
        )

        mock_resp = {
            "response": "Hello from pool!",
            "prompt_eval_count": 15,
            "eval_count": 45
        }
        with patch("urllib.request.urlopen") as mock_url:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(mock_resp).encode("utf-8")
            mock_cm.__enter__.return_value = mock_cm
            mock_url.return_value = mock_cm

            res = self.governor.forward_completion(
                node_id="pool",
                model="llama3",
                prompt="Hello pool"
            )

        self.assertTrue(res["success"])
        # Selected node must be Primary GPU (highest priority among trusted active nodes)
        self.assertEqual(res["node_id"], node1["id"])

    def test_pool_routing_failover_when_primary_fails(self):
        """Assert pool routing automatically fails over to next trusted candidate if primary errors."""
        node1 = self.registry.register_node(
            name="Failing Primary",
            endpoint="http://10.1.7.74:11434",
            engine="ollama",
            priority=10,
            is_trusted=1,
            compute_group="Active Compute"
        )
        node2 = self.registry.register_node(
            name="Healthy Backup",
            endpoint="http://10.1.7.75:11434",
            engine="ollama",
            priority=5,
            is_trusted=1,
            compute_group="Active Compute"
        )

        call_count = 0
        def side_effect(req, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if "10.1.7.74" in req.full_url:
                raise urllib.error.URLError("Connection refused on primary")
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps({"response": "Failover success", "prompt_eval_count": 10, "eval_count": 20}).encode("utf-8")
            mock_cm.__enter__.return_value = mock_cm
            return mock_cm

        with patch("urllib.request.urlopen", side_effect=side_effect):
            res = self.governor.forward_completion(
                node_id="pool",
                model="llama3",
                prompt="Testing failover"
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["node_id"], node2["id"])
        self.assertEqual(res["response"], "Failover success")

    # -------------------------------------------------------------------------
    # 8. Interactive Query Console with File Attachments & Untrusted Warnings
    # -------------------------------------------------------------------------
    def test_query_console_with_file_context(self):
        """Assert prompt with context files concatenates content and records telemetry."""
        node = self.registry.register_node(
            name="Jamese-PC",
            endpoint="http://10.1.7.74:11434",
            engine="ollama",
            is_trusted=1,
            compute_group="Active Compute"
        )
        context_files = [
            {"filename": "main.py", "content": "print('hello world')"},
            {"filename": "notes.txt", "content": "Meeting agenda item"}
        ]
        mock_resp = {
            "response": "Analysis complete for provided code.",
            "prompt_eval_count": 40,
            "eval_count": 30
        }
        with patch("urllib.request.urlopen") as mock_url:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(mock_resp).encode("utf-8")
            mock_cm.__enter__.return_value = mock_cm
            mock_url.return_value = mock_cm

            res = self.governor.forward_query_with_context(
                target="node:" + node["id"],
                prompt="Review these files",
                files=context_files,
                model="llama3"
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["input_tokens"], 40)
        self.assertEqual(res["output_tokens"], 30)
        self.assertFalse(res.get("is_untrusted_warning", False))

    def test_query_console_untrusted_target_raises_warning_in_response(self):
        """Assert executing a prompt against an untrusted node flags an explicit security warning."""
        untrusted_node = self.registry.register_node(
            name="Rogue Workstation",
            endpoint="http://10.1.7.99:11434",
            engine="ollama",
            is_trusted=0,
            compute_group="Quarantined"
        )
        mock_resp = {"response": "Untrusted reply", "prompt_eval_count": 10, "eval_count": 10}
        with patch("urllib.request.urlopen") as mock_url:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(mock_resp).encode("utf-8")
            mock_cm.__enter__.return_value = mock_cm
            mock_url.return_value = mock_cm

            res = self.governor.forward_query_with_context(
                target="node:" + untrusted_node["id"],
                prompt="Run sensitive query",
                files=[{"filename": "secret.env", "content": "KEY=123"}],
                model="llama3"
            )

        self.assertTrue(res["success"])
        self.assertTrue(res.get("is_untrusted_warning", False))
        self.assertIn("UNTRUSTED", res.get("warning_message", ""))

    # -------------------------------------------------------------------------
    # 9. REST API Endpoints Integration
    # -------------------------------------------------------------------------
    def test_rest_api_adapters_and_inventory(self):
        """Assert GET /api/discovery/adapters, GET/POST/DELETE /api/discovery/inventory."""
        vault = DPAPIVault(storage_path=os.path.join(self.tmp_dir.name, "vault.json"))
        diag = DiagnosticsEngine()
        server = AppHTTPServer(
            database=self.db,
            vault=vault,
            diagnostics=diag,
            providers={},
            host="127.0.0.1",
            port=0,
            registry=self.registry,
            governor=self.governor,
            scanner=self.scanner
        )
        server.start()
        port = server.server_port

        try:
            # 1. GET /api/discovery/adapters
            req1 = urllib.request.Request(f"http://127.0.0.1:{port}/api/discovery/adapters")
            with urllib.request.urlopen(req1) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data["success"])
                self.assertIn("adapters", data)

            # 2. POST /api/discovery/inventory
            req2 = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/discovery/inventory",
                data=json.dumps({
                    "alias": "Jamese-PC",
                    "ip": "10.1.7.74",
                    "state": "KNOWN_SERVICES",
                    "is_trusted": 1,
                    "compute_group": "Active Compute"
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data["success"])
                self.assertEqual(data["device"]["alias"], "Jamese-PC")

            # 3. GET /api/discovery/inventory
            req3 = urllib.request.Request(f"http://127.0.0.1:{port}/api/discovery/inventory")
            with urllib.request.urlopen(req3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data["success"])
                self.assertEqual(len(data["inventory"]), 1)

            # 4. DELETE /api/discovery/inventory?alias=Jamese-PC
            req4 = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/discovery/inventory?alias=Jamese-PC",
                method="DELETE"
            )
            with urllib.request.urlopen(req4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data["success"])
        finally:
            server.stop()

    def test_rest_api_query_console_endpoint(self):
        """Assert POST /api/discovery/query executes query with file context."""
        node = self.registry.register_node(
            name="Jamese-PC",
            endpoint="http://10.1.7.74:11434",
            engine="ollama",
            is_trusted=1,
            compute_group="Active Compute"
        )
        vault = DPAPIVault(storage_path=os.path.join(self.tmp_dir.name, "vault2.json"))
        diag = DiagnosticsEngine()
        server = AppHTTPServer(
            database=self.db,
            vault=vault,
            diagnostics=diag,
            providers={},
            host="127.0.0.1",
            port=0,
            registry=self.registry,
            governor=self.governor,
            scanner=self.scanner
        )
        server.start()
        port = server.server_port

        mock_resp = {"response": "Query completed", "prompt_eval_count": 25, "eval_count": 35}
        orig_urlopen = urllib.request.urlopen
        def side_effect(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "10.1.7.74" in url or ":11434" in url:
                mock_cm = MagicMock()
                mock_cm.read.return_value = json.dumps(mock_resp).encode("utf-8")
                mock_cm.__enter__.return_value = mock_cm
                return mock_cm
            return orig_urlopen(req, *args, **kwargs)

        try:
            with patch("urllib.request.urlopen", side_effect=side_effect):

                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/discovery/query",
                    data=json.dumps({
                        "target": "pool",
                        "model": "llama3",
                        "prompt": "Evaluate code",
                        "files": [{"filename": "app.py", "content": "import sys"}]
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(data["success"])
                    self.assertEqual(data["response"], "Query completed")
        finally:
            server.stop()

    def test_parse_target_spec_with_custom_comma_and_spaces(self):
        """Assert target spec parser tolerates leading/trailing whitespace and empty tokens."""
        spec = "  10.1.7.74 ,  , 10.1.7.50-10.1.7.52 ,  "
        parsed = self.scanner.parse_target_spec(spec)
        self.assertEqual(parsed, ["10.1.7.74", "10.1.7.50", "10.1.7.51", "10.1.7.52"])

    def test_upsert_device_inventory_updates_existing_services(self):
        """Assert updating device inventory preserves fields while updating discovered services."""
        self.db.upsert_device_inventory(
            alias="Jamese-PC",
            ip="10.1.7.74",
            state="PENDING",
            notes="Initial note"
        )
        updated = self.db.upsert_device_inventory(
            alias="Jamese-PC",
            ip="10.1.7.74",
            state="KNOWN_SERVICES",
            discovered_services=[{"engine": "ollama", "port": 11434, "models": ["llama3"]}]
        )
        self.assertEqual(updated["notes"], "Initial note")
        self.assertEqual(updated["state"], "KNOWN_SERVICES")
        self.assertEqual(len(updated["discovered_services"]), 1)

    def test_pool_routing_exhaustion_when_all_nodes_offline(self):
        """Assert pool routing handles zero available nodes cleanly."""
        res = self.governor.forward_completion(node_id="pool", model="llama3", prompt="test")
        self.assertFalse(res["success"])
        self.assertIn("No active trusted nodes available", res["error"])

    def test_forward_query_with_context_empty_files(self):
        """Assert prompt with empty files list forwards clean query without context headers."""
        node = self.registry.register_node(
            name="Jamese-PC",
            endpoint="http://10.1.7.74:11434",
            engine="ollama",
            is_trusted=1,
            compute_group="Active Compute"
        )
        mock_resp = {"response": "Direct prompt reply", "prompt_eval_count": 5, "eval_count": 10}
        with patch("urllib.request.urlopen") as mock_url:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(mock_resp).encode("utf-8")
            mock_cm.__enter__.return_value = mock_cm
            mock_url.return_value = mock_cm

            res = self.governor.forward_query_with_context(
                target="node:" + node["id"],
                prompt="Simple prompt",
                files=[],
                model="llama3"
            )
        self.assertTrue(res["success"])
        self.assertEqual(res["response"], "Direct prompt reply")

    def test_governor_active_compute_excludes_untrusted_even_if_active_status(self):
        """Assert pool dispatch excludes untrusted nodes even if status is ONLINE."""
        self.registry.register_node(
            name="Untrusted Rogue",
            endpoint="http://10.1.7.99:11434",
            engine="ollama",
            is_trusted=0,
            compute_group="Quarantined"
        )
        res = self.governor.forward_completion(node_id="pool", model="llama3", prompt="test")
        self.assertFalse(res["success"])
        self.assertIn("No active trusted nodes available", res["error"])

    def test_get_local_subnet_info_fallback(self):
        """Assert fallback to loopback when no adapters available."""
        with patch.object(self.scanner, "get_local_adapters_and_subnets", return_value=[]):
            ip, sub = self.scanner.get_local_subnet_info()
            self.assertEqual(ip, "127.0.0.1")
            self.assertEqual(sub, "127.0.0.0/24")

if __name__ == "__main__":
    unittest.main()


