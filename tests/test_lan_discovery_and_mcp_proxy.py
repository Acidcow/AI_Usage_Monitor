import unittest
import sys
import os
import json
import tempfile
import time
import http.server
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.discovery.lan_scanner import LANScanner
from backend.discovery.node_registry import NodeRegistry
from backend.discovery.traffic_governor import TrafficGovernor
from backend.mcp.server import MCPServer
from backend.server.http_server import AppHTTPServer

class MockAIHostHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        # Mock Ollama version & tags
        if self.path == "/api/version":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"version": "0.5.7"}).encode("utf-8"))
            return
        if self.path == "/api/tags":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "models": [
                    {"name": "deepseek-r1:8b", "size": 4900000000, "details": {"parameter_size": "8B", "quantization_level": "Q4_K_M"}},
                    {"name": "llama3.2:latest", "size": 2000000000, "details": {"parameter_size": "3B", "quantization_level": "Q4_K_M"}}
                ]
            }).encode("utf-8"))
            return
        # Mock OpenAI/vLLM models
        if self.path in ["/v1/models", "/models"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "object": "list",
                "data": [{"id": "mistral-7b-instruct", "owned_by": "vllm"}]
            }).encode("utf-8"))
            return
        self.send_error(404, "Not Found")

    def do_POST(self):
        # Mock Ollama generate
        if self.path == "/api/generate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            
            # Support artificial delay for concurrency testing
            delay = body.get("mock_delay", 0.0)
            if delay > 0:
                time.sleep(delay)

            # Support error simulation
            if body.get("mock_error_503"):
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b'{"error": "engine overloaded"}')
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "model": body.get("model", "deepseek-r1:8b"),
                "response": "Thought completed. Here is the local solution.",
                "done": True,
                "prompt_eval_count": 28,
                "eval_count": 84,
                "total_duration": 420000000
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return
        self.send_error(404, "Not Found")


class TestLANDiscoveryAndMCPProxy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start mock AI server on dynamic ephemeral port
        cls.mock_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockAIHostHandler)
        cls.mock_port = cls.mock_server.server_port
        cls.mock_thread = threading.Thread(target=cls.mock_server.serve_forever, daemon=True)
        cls.mock_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_server.shutdown()
        cls.mock_server.server_close()
        cls.mock_thread.join(timeout=2.0)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_discovery.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()

        self.scanner = LANScanner()
        self.registry = NodeRegistry(database=self.db)
        self.governor = TrafficGovernor(registry=self.registry, database=self.db)
        self.mcp_server = MCPServer(scanner=self.scanner, registry=self.registry, governor=self.governor, database=self.db)

        # Wire AppHTTPServer with discovery components
        self.app_server = AppHTTPServer(
            database=self.db,
            vault=self.vault,
            diagnostics=self.diagnostics,
            providers={},
            host="127.0.0.1",
            port=0,
            scanner=self.scanner,
            registry=self.registry,
            governor=self.governor,
            mcp_server=self.mcp_server
        )
        self.app_server.start()

    def tearDown(self):
        self.app_server.stop()
        self.temp_dir.cleanup()

    # 1. LAN Scanner Tests
    def test_detect_local_subnet_format(self):
        """Assert local IP and subnet detection returns valid CIDR / IP format."""
        ip, subnet = self.scanner.get_local_subnet_info()
        self.assertIsInstance(ip, str)
        self.assertIsInstance(subnet, str)
        self.assertTrue(len(ip.split(".")) == 4)
        self.assertTrue("/" in subnet or len(subnet.split(".")) == 4)

    def test_fingerprint_ollama_service(self):
        """Assert scanner identifies Ollama service from mock host and extracts models."""
        node_info = self.scanner.probe_host("127.0.0.1", self.mock_port, timeout=1.0)
        self.assertIsNotNone(node_info)
        self.assertEqual(node_info["engine"], "ollama")
        self.assertEqual(node_info["version"], "0.5.7")
        self.assertEqual(len(node_info["models"]), 2)
        model_names = [m["name"] for m in node_info["models"]]
        self.assertIn("deepseek-r1:8b", model_names)

    def test_scanner_handles_closed_ports_gracefully(self):
        """Assert scanner handles unreachable ports without crashing or long blocking."""
        # Unused port
        node_info = self.scanner.probe_host("127.0.0.1", 65530, timeout=0.1)
        self.assertIsNone(node_info)

    def test_scan_subnet_targets(self):
        """Assert scan_hosts identifies candidate services across host list."""
        candidates = self.scanner.scan_targets(
            targets=[("127.0.0.1", self.mock_port), ("127.0.0.1", 65530)],
            timeout=0.5
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["port"], self.mock_port)

    # 2. Node Registry CRUD Tests
    def test_node_registry_crud_operations(self):
        """Assert registering, getting, listing, updating, and deleting nodes."""
        node = self.registry.register_node(
            name="Lab RTX 4090",
            endpoint=f"http://127.0.0.1:{self.mock_port}",
            engine="ollama",
            max_concurrency=2,
            queue_timeout_seconds=15,
            priority=5,
            models=["deepseek-r1:8b", "llama3.2:latest"]
        )
        self.assertIn("id", node)
        node_id = node["id"]

        # Fetch
        fetched = self.registry.get_node(node_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], "Lab RTX 4090")
        self.assertEqual(fetched["max_concurrency"], 2)
        self.assertEqual(len(fetched["models"]), 2)

        # List
        nodes = self.registry.list_nodes()
        self.assertEqual(len(nodes), 1)

        # Update health
        self.registry.update_node_status(node_id, "BUSY")
        updated = self.registry.get_node(node_id)
        self.assertEqual(updated["status"], "BUSY")

        # Delete
        self.registry.delete_node(node_id)
        self.assertIsNone(self.registry.get_node(node_id))
        self.assertEqual(len(self.registry.list_nodes()), 0)

    # 3. Traffic Governor & Non-Overwhelm Protection Tests
    def test_governor_executes_inference_and_logs_telemetry(self):
        """Assert single inference through governor executes, returns result, and records tokens."""
        node = self.registry.register_node(
            name="Fast Node",
            endpoint=f"http://127.0.0.1:{self.mock_port}",
            engine="ollama",
            max_concurrency=1
        )
        res = self.governor.forward_completion(
            node_id=node["id"],
            model="deepseek-r1:8b",
            prompt="Write a quick sorting algorithm"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["input_tokens"], 28)
        self.assertEqual(res["output_tokens"], 84)

        # Check telemetry recorded in SQLite
        events = self.db.get_recent_sessions(limit=5, provider="ollama")
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0]["input_tokens"], 28)
        self.assertEqual(events[0]["output_tokens"], 84)
        self.assertEqual(events[0]["model"], "deepseek-r1:8b")

    def test_governor_enforces_concurrency_ceiling_with_queuing(self):
        """Assert second concurrent request enters queue and executes sequentially."""
        node = self.registry.register_node(
            name="Strict 1-Concur Node",
            endpoint=f"http://127.0.0.1:{self.mock_port}",
            engine="ollama",
            max_concurrency=1,
            queue_timeout_seconds=5.0
        )

        results = []
        def _run_worker(delay):
            out = self.governor.forward_completion(
                node_id=node["id"],
                model="deepseek-r1:8b",
                prompt="Heavy query",
                extra_payload={"mock_delay": delay}
            )
            results.append(out)

        # Launch 2 concurrent requests
        t1 = threading.Thread(target=_run_worker, args=(0.3,))
        t2 = threading.Thread(target=_run_worker, args=(0.0,))
        t1.start()
        time.sleep(0.05) # ensure t1 acquires semaphore first
        t2.start()

        t1.join()
        t2.join()

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["success"])
        self.assertTrue(results[1]["success"])
        # Second request must have experienced queue wait time > 0.2s
        queue_waits = [r.get("queue_time_ms", 0) for r in results]
        self.assertTrue(any(qw >= 180 for qw in queue_waits))

    def test_governor_queue_timeout_rejection(self):
        """Assert excess requests reject cleanly when queue timeout expires."""
        node = self.registry.register_node(
            name="Low Timeout Node",
            endpoint=f"http://127.0.0.1:{self.mock_port}",
            engine="ollama",
            max_concurrency=1,
            queue_timeout_seconds=0.1
        )

        results = []
        def _slow_worker():
            out = self.governor.forward_completion(
                node_id=node["id"],
                model="deepseek-r1:8b",
                prompt="Hold semaphore",
                extra_payload={"mock_delay": 0.4}
            )
            results.append(out)

        def _timed_out_worker():
            out = self.governor.forward_completion(
                node_id=node["id"],
                model="deepseek-r1:8b",
                prompt="Immediate reject expected"
            )
            results.append(out)

        t1 = threading.Thread(target=_slow_worker)
        t2 = threading.Thread(target=_timed_out_worker)
        t1.start()
        time.sleep(0.05)
        t2.start()

        t1.join()
        t2.join()

        # Find timed out result
        timeout_res = next((r for r in results if not r["success"]), None)
        self.assertIsNotNone(timeout_res)
        self.assertIn("timeout", timeout_res["error"].lower())

    def test_governor_circuit_breaker_on_repeated_errors(self):
        """Assert node transitions to UNHEALTHY on consecutive 503 errors."""
        node = self.registry.register_node(
            name="Failing Node",
            endpoint=f"http://127.0.0.1:{self.mock_port}",
            engine="ollama",
            max_concurrency=1
        )

        # Trigger 3 consecutive 503s
        for _ in range(3):
            self.governor.forward_completion(
                node_id=node["id"],
                model="deepseek-r1:8b",
                prompt="Crash",
                extra_payload={"mock_error_503": True}
            )

        updated = self.registry.get_node(node["id"])
        self.assertEqual(updated["status"], "UNHEALTHY")

    # 4. Model Context Protocol (MCP) Server JSON-RPC Tests
    def test_mcp_initialize(self):
        """Assert JSON-RPC initialize returns MCP protocol capabilities and server info."""
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "claude-code", "version": "1.0.0"}
            }
        }
        res = self.mcp_server.handle_json_rpc(req)
        self.assertEqual(res["jsonrpc"], "2.0")
        self.assertEqual(res["id"], 1)
        self.assertIn("result", res)
        self.assertEqual(res["result"]["serverInfo"]["name"], "ai-usage-monitor-proxy")
        self.assertIn("tools", res["result"]["capabilities"])

    def test_mcp_notifications_suppressed(self):
        """Assert JSON-RPC notifications (without id) return None with zero response."""
        req1 = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self.assertIsNone(self.mcp_server.handle_json_rpc(req1))

        req2 = {"jsonrpc": "2.0", "method": "initialized"}
        self.assertIsNone(self.mcp_server.handle_json_rpc(req2))

        req3 = {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": "123"}}
        self.assertIsNone(self.mcp_server.handle_json_rpc(req3))

    def test_mcp_resources_and_prompts_empty_list(self):
        """Assert resources/list and prompts/list return valid empty lists instead of errors."""
        res_res = self.mcp_server.handle_json_rpc({"jsonrpc": "2.0", "id": 50, "method": "resources/list"})
        self.assertEqual(res_res["id"], 50)
        self.assertEqual(res_res["result"]["resources"], [])

        res_prompts = self.mcp_server.handle_json_rpc({"jsonrpc": "2.0", "id": 51, "method": "prompts/list"})
        self.assertEqual(res_prompts["id"], 51)
        self.assertEqual(res_prompts["result"]["prompts"], [])

    def test_mcp_tools_list(self):
        """Assert tools/list exposes all 8 managed tools with JSON schemas."""
        req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        res = self.mcp_server.handle_json_rpc(req)
        tools = res["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertEqual(len(tools), 8)
        self.assertIn("scan_lan_ai_services", tool_names)
        self.assertIn("list_managed_nodes", tool_names)
        self.assertIn("register_managed_node", tool_names)
        self.assertIn("generate_completion", tool_names)
        self.assertIn("get_traffic_telemetry", tool_names)
        self.assertIn("get_usage_summary", tool_names)
        self.assertIn("get_provider_quotas", tool_names)
        self.assertIn("get_proxy_endpoints", tool_names)

    def test_mcp_tool_call_scan_lan(self):
        """Assert calling scan_lan_ai_services via MCP tools/call."""
        req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "scan_lan_ai_services",
                "arguments": {
                    "targets": [f"127.0.0.1:{self.mock_port}"]
                }
            }
        }
        res = self.mcp_server.handle_json_rpc(req)
        self.assertIn("result", res)
        content = res["result"]["content"]
        self.assertEqual(content[0]["type"], "text")
        data = json.loads(content[0]["text"])
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["engine"], "ollama")

    def test_mcp_tool_call_register_and_list_nodes(self):
        """Assert registering node and listing nodes via MCP tool calls."""
        reg_req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "register_managed_node",
                "arguments": {
                    "name": "MCP Remote Node",
                    "endpoint": f"http://127.0.0.1:{self.mock_port}",
                    "engine": "ollama",
                    "max_concurrency": 2
                }
            }
        }
        reg_res = self.mcp_server.handle_json_rpc(reg_req)
        node_data = json.loads(reg_res["result"]["content"][0]["text"])
        self.assertIn("id", node_data)
        node_id = node_data["id"]

        list_req = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "list_managed_nodes", "arguments": {}}
        }
        list_res = self.mcp_server.handle_json_rpc(list_req)
        nodes = json.loads(list_res["result"]["content"][0]["text"])
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["id"], node_id)

    def test_mcp_tool_call_generate_completion(self):
        """Assert executing completion via MCP generate_completion tool."""
        node = self.registry.register_node(
            name="MCP Completion Node",
            endpoint=f"http://127.0.0.1:{self.mock_port}",
            engine="ollama"
        )
        req = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "generate_completion",
                "arguments": {
                    "node_id": node["id"],
                    "model": "deepseek-r1:8b",
                    "prompt": "Hello via MCP!"
                }
            }
        }
        res = self.mcp_server.handle_json_rpc(req)
        out = json.loads(res["result"]["content"][0]["text"])
        self.assertTrue(out["success"])
        self.assertEqual(out["output_tokens"], 84)

    def test_mcp_tool_call_traffic_telemetry(self):
        """Assert get_traffic_telemetry returns queue depth and token metrics."""
        node = self.registry.register_node(
            name="Telemetry Node",
            endpoint=f"http://127.0.0.1:{self.mock_port}",
            engine="ollama"
        )
        self.governor.forward_completion(node["id"], "deepseek-r1:8b", "ping")

        req = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "get_traffic_telemetry",
                "arguments": {"node_id": node["id"]}
            }
        }
        res = self.mcp_server.handle_json_rpc(req)
        stats = json.loads(res["result"]["content"][0]["text"])
        self.assertIn("active_requests", stats)
        self.assertIn("total_tokens_routed", stats)
        self.assertEqual(stats["total_tokens_routed"], 28 + 84)

    def test_mcp_tool_call_get_usage_summary(self):
        """Assert get_usage_summary tool executes through JSON-RPC and returns today's tokens."""
        self.db.record_usage_event(
            provider="claude",
            input_tokens=1500,
            output_tokens=500,
            model="claude-3-5-sonnet-20241022"
        )
        req = {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "get_usage_summary",
                "arguments": {"provider": "claude"}
            }
        }
        res = self.mcp_server.handle_json_rpc(req)
        self.assertFalse(res.get("result", {}).get("isError"))
        summary = json.loads(res["result"]["content"][0]["text"])
        self.assertGreaterEqual(summary["input_tokens_today"], 1500)
        self.assertGreaterEqual(summary["output_tokens_today"], 500)

    def test_mcp_tool_call_get_provider_quotas(self):
        """Assert get_provider_quotas tool returns active provider snapshots and reset times."""
        self.db.update_provider_snapshot(
            provider="claude",
            plan_type="Pro",
            session_remaining_pct=85.0,
            weekly_remaining_pct=92.5
        )
        req = {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "get_provider_quotas",
                "arguments": {"provider": "claude"}
            }
        }
        res = self.mcp_server.handle_json_rpc(req)
        self.assertFalse(res.get("result", {}).get("isError"))
        quotas = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(quotas["provider"], "claude")
        self.assertEqual(quotas["session_remaining_pct"], 85.0)

    def test_mcp_tool_call_get_proxy_endpoints(self):
        """Assert get_proxy_endpoints tool returns all proxy ports and environment variables."""
        req = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "get_proxy_endpoints",
                "arguments": {}
            }
        }
        res = self.mcp_server.handle_json_rpc(req)
        self.assertFalse(res.get("result", {}).get("isError"))
        endpoints = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(endpoints["transparent_reverse_proxy"], "http://127.0.0.1:8766")
        self.assertEqual(endpoints["ollama_and_openai_bridge"], "http://127.0.0.1:8989")
        self.assertIn("ANTHROPIC_BASE_URL", endpoints["env_variables"])
        self.assertIn("OLLAMA_BASE_URL", endpoints["env_variables"])

    # 5. REST API Endpoints Tests
    def test_rest_api_discovery_scan(self):
        """Assert GET /api/discovery/scan triggers scan and returns candidate list."""
        import urllib.request
        port = self.app_server.server_port
        url = f"http://127.0.0.1:{port}/api/discovery/scan?targets=127.0.0.1:{self.mock_port}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertGreaterEqual(len(data["candidates"]), 1)
            self.assertEqual(data["candidates"][0]["engine"], "ollama")

    def test_rest_api_discovery_nodes_crud(self):
        """Assert POST, GET, DELETE /api/discovery/nodes."""
        import urllib.request
        port = self.app_server.server_port

        # POST /api/discovery/nodes
        post_url = f"http://127.0.0.1:{port}/api/discovery/nodes"
        payload = json.dumps({
            "name": "REST Remote Host",
            "endpoint": f"http://127.0.0.1:{self.mock_port}",
            "engine": "ollama",
            "max_concurrency": 3
        }).encode("utf-8")
        req = urllib.request.Request(post_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            node = json.loads(resp.read().decode("utf-8"))["node"]
            node_id = node["id"]

        # GET /api/discovery/nodes
        get_url = f"http://127.0.0.1:{port}/api/discovery/nodes"
        with urllib.request.urlopen(get_url, timeout=3.0) as resp:
            nodes = json.loads(resp.read().decode("utf-8"))["nodes"]
            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0]["id"], node_id)

        # DELETE /api/discovery/nodes/<id>
        del_url = f"http://127.0.0.1:{port}/api/discovery/nodes?id={node_id}"
        del_req = urllib.request.Request(del_url, method="DELETE")
        with urllib.request.urlopen(del_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)

        with urllib.request.urlopen(get_url, timeout=3.0) as resp:
            nodes = json.loads(resp.read().decode("utf-8"))["nodes"]
            self.assertEqual(len(nodes), 0)

    def test_rest_api_mcp_rpc_bridge(self):
        """Assert POST /api/mcp/rpc executes JSON-RPC MCP commands over HTTP."""
        import urllib.request
        port = self.app_server.server_port
        url = f"http://127.0.0.1:{port}/api/mcp/rpc"
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 42,
            "method": "ping"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res["id"], 42)
            self.assertEqual(res["result"], {})


    def test_governor_circuit_breaker_immediate_rejection(self):
        """Assert circuit breaker immediately rejects subsequent calls during cooldown window."""
        node = self.registry.register_node(
            name="CB Rejection Node",
            endpoint=f"http://127.0.0.1:{self.mock_port}",
            engine="ollama"
        )
        # Trip breaker
        for _ in range(3):
            self.governor.forward_completion(node["id"], "deepseek-r1:8b", "err", extra_payload={"mock_error_503": True})

        # Next call must be rejected by circuit breaker immediately
        res = self.governor.forward_completion(node["id"], "deepseek-r1:8b", "test")
        self.assertFalse(res["success"])
        self.assertIn("circuit breaker tripped", res["error"].lower())

    def test_governor_unhealthy_node_recovers_on_success(self):
        """Assert UNHEALTHY node restores to ONLINE after cooldown and successful response."""
        node = self.registry.register_node(
            name="Recovery Node",
            endpoint=f"http://127.0.0.1:{self.mock_port}",
            engine="ollama"
        )
        self.registry.update_node_status(node["id"], "UNHEALTHY")
        stats = self.governor._get_node_stats(node["id"])
        stats["circuit_breaker_failures"] = 3
        stats["last_failure_time"] = time.time() - 35.0 # Cooldown expired

        res = self.governor.forward_completion(node["id"], "deepseek-r1:8b", "hello")
        self.assertTrue(res["success"])
        updated = self.registry.get_node(node["id"])
        self.assertEqual(updated["status"], "ONLINE")

    def test_mcp_invalid_json_rpc_method(self):
        """Assert unhandled JSON-RPC method returns standard -32601 method not found error."""
        req = {"jsonrpc": "2.0", "id": 99, "method": "unknown_action_xyz"}
        res = self.mcp_server.handle_json_rpc(req)
        self.assertIn("error", res)
        self.assertEqual(res["error"]["code"], -32601)

    def test_rest_api_proxy_completion(self):
        """Assert POST /api/discovery/proxy/completion routes governed inference through HTTP."""
        import urllib.request
        port = self.app_server.server_port
        node = self.registry.register_node(
            name="REST Governed Worker",
            endpoint=f"http://127.0.0.1:{self.mock_port}",
            engine="ollama"
        )
        url = f"http://127.0.0.1:{port}/api/discovery/proxy/completion"
        payload = json.dumps({
            "node_id": node["id"],
            "model": "deepseek-r1:8b",
            "prompt": "Solve math puzzle"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertEqual(data["input_tokens"], 28)
            self.assertEqual(data["output_tokens"], 84)


if __name__ == "__main__":
    unittest.main()

