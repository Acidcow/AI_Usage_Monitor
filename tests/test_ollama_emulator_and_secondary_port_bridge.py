import unittest
import json
import time
import socket
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, List

from backend.storage.database import UsageDatabase
from backend.discovery.node_registry import NodeRegistry
from backend.discovery.traffic_governor import TrafficGovernor
from backend.mcp.server import MCPServer
from backend.server.ollama_emulator import OllamaEmulatorServer

def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class MockWorkerNodeHandler:
    """Simulates an upstream worker node running Ollama or an OpenAI-compatible engine."""
    def __init__(self, port: int, engine: str = "ollama", models: List[str] = None):
        self.port = port
        self.engine = engine
        self.models = models or ["llama3:8b", "qwen2.5:7b"]
        self.server = None
        self.thread = None
        self.request_count = 0
        self.fail_mode = False

    def start(self):
        from http.server import HTTPServer, BaseHTTPRequestHandler
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                outer.request_count += 1
                if outer.fail_mode:
                    self.send_response(503)
                    self.end_headers()
                    self.wfile.write(b'{"error": "node unavailable"}')
                    return

                if self.path == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"Ollama is running")
                    return

                if self.path in ["/api/tags", "/api/tags/"]:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    resp = {
                        "models": [
                            {
                                "name": m,
                                "model": m,
                                "modified_at": "2026-10-20T10:00:00Z",
                                "size": 4661224676,
                                "digest": "sha256:abc12345",
                                "details": {
                                    "format": "gguf",
                                    "family": "llama",
                                    "parameter_size": "8B",
                                    "quantization_level": "Q4_0"
                                }
                            }
                            for m in outer.models
                        ]
                    }
                    self.wfile.write(json.dumps(resp).encode("utf-8"))
                    return

                if self.path == "/api/version":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"version": "0.5.4"}')
                    return

                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                outer.request_count += 1
                if outer.fail_mode:
                    self.send_response(503)
                    self.end_headers()
                    self.wfile.write(b'{"error": "node crashed"}')
                    return

                content_len = int(self.headers.get("Content-Length", 0))
                body_bytes = self.rfile.read(content_len) if content_len > 0 else b"{}"
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}

                # 1. /api/generate
                if self.path == "/api/generate":
                    model = data.get("model", "llama3:8b")
                    prompt = data.get("prompt", "")
                    stream = data.get("stream", False)

                    if stream:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/x-ndjson")
                        self.end_headers()
                        chunk1 = {"model": model, "response": "Hello ", "done": False}
                        chunk2 = {
                            "model": model,
                            "response": "world!",
                            "done": True,
                            "prompt_eval_count": 8,
                            "eval_count": 12,
                            "total_duration": 150000000
                        }
                        self.wfile.write((json.dumps(chunk1) + "\n").encode("utf-8"))
                        self.wfile.flush()
                        time.sleep(0.01)
                        self.wfile.write((json.dumps(chunk2) + "\n").encode("utf-8"))
                        self.wfile.flush()
                        return

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    resp = {
                        "model": model,
                        "created_at": "2026-10-20T12:00:00Z",
                        "response": f"Generated reply to '{prompt}' from mock node.",
                        "done": True,
                        "done_reason": "stop",
                        "total_duration": 150000000,
                        "load_duration": 10000000,
                        "prompt_eval_count": 12,
                        "eval_count": 25
                    }
                    self.wfile.write(json.dumps(resp).encode("utf-8"))
                    return

                # 2. /api/chat
                if self.path == "/api/chat":
                    model = data.get("model", "llama3:8b")
                    stream = data.get("stream", False)
                    if stream:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/x-ndjson")
                        self.end_headers()
                        chunk1 = {"model": model, "message": {"role": "assistant", "content": "Chat "}, "done": False}
                        chunk2 = {
                            "model": model,
                            "message": {"role": "assistant", "content": "stream."},
                            "done": True,
                            "prompt_eval_count": 10,
                            "eval_count": 20
                        }
                        self.wfile.write((json.dumps(chunk1) + "\n").encode("utf-8"))
                        self.wfile.flush()
                        time.sleep(0.01)
                        self.wfile.write((json.dumps(chunk2) + "\n").encode("utf-8"))
                        self.wfile.flush()
                        return

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    resp = {
                        "model": model,
                        "created_at": "2026-10-20T12:00:00Z",
                        "message": {"role": "assistant", "content": "Chat assistant response from mock worker node."},
                        "done": True,
                        "prompt_eval_count": 14,
                        "eval_count": 30
                    }
                    self.wfile.write(json.dumps(resp).encode("utf-8"))
                    return

                # 3. /api/show
                if self.path == "/api/show":
                    model = data.get("name") or data.get("model") or "llama3:8b"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    resp = {
                        "modelfile": f"# Modelfile for {model}\nFROM {model}",
                        "parameters": "stop \"<|end_of_text|>\"",
                        "template": "{{ .Prompt }}",
                        "details": {
                            "format": "gguf",
                            "family": "llama",
                            "parameter_size": "8B",
                            "quantization_level": "Q4_0"
                        }
                    }
                    self.wfile.write(json.dumps(resp).encode("utf-8"))
                    return

                # 4. /api/embeddings or /api/embed
                if self.path in ["/api/embeddings", "/api/embed"]:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"embedding": [0.012, -0.045, 0.089, 0.123]}')
                    return

                self.send_response(404)
                self.end_headers()

        self.server = HTTPServer(('127.0.0.1', self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()


class TestOllamaEmulatorAndSecondaryPortBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile, os
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_emulator.db")

        # Start 2 Mock Worker Nodes on random ports
        cls.worker1_port = get_free_port()
        cls.worker2_port = get_free_port()

        cls.worker1 = MockWorkerNodeHandler(cls.worker1_port, models=["llama3:8b", "mistral:7b"])
        cls.worker1.start()

        cls.worker2 = MockWorkerNodeHandler(cls.worker2_port, models=["qwen2.5-coder:7b", "deepseek-coder:6.7b"])
        cls.worker2.start()

        # Database, Registry, Governor, MCP
        cls.db = UsageDatabase(cls.db_path)
        cls.registry = NodeRegistry(cls.db)
        cls.governor = TrafficGovernor(cls.registry, cls.db)
        cls.mcp_server = MCPServer(scanner=None, registry=cls.registry, governor=cls.governor)

        # Register worker nodes in database
        cls.node1 = cls.registry.register_node(
            name="ASUS ROG Workstation",
            endpoint=f"http://127.0.0.1:{cls.worker1_port}",
            engine="ollama",
            models=[{"name": "llama3:8b", "parameter_size": "8B"}, {"name": "mistral:7b", "parameter_size": "7B"}],
            is_trusted=1,
            compute_group="Active Compute",
            priority=8
        )
        cls.node2 = cls.registry.register_node(
            name="Dev Workstation Secondary",
            endpoint=f"http://127.0.0.1:{cls.worker2_port}",
            engine="ollama",
            models=[{"name": "qwen2.5-coder:7b", "parameter_size": "7B"}, {"name": "deepseek-coder:6.7b", "parameter_size": "6.7B"}],
            is_trusted=1,
            compute_group="Active Compute",
            priority=5
        )

        # Start OllamaEmulatorServer on free port
        cls.emulator_port = get_free_port()
        cls.emulator = OllamaEmulatorServer(
            host="127.0.0.1",
            port=cls.emulator_port,
            governor=cls.governor,
            registry=cls.registry,
            database=cls.db,
            mcp_server=cls.mcp_server
        )
        cls.emulator.start()
        time.sleep(0.15)

    @classmethod
    def tearDownClass(cls):
        cls.emulator.stop()
        cls.worker1.stop()
        cls.worker2.stop()
        cls.temp_dir.cleanup()

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.emulator_port}{path}"

    def test_01_root_returns_ollama_is_running(self):
        """Assert GET / returns 'Ollama is running' with HTTP 200."""
        req = urllib.request.Request(self._url("/"))
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            text = resp.read().decode("utf-8").strip()
            self.assertEqual(text, "Ollama is running")

    def test_02_api_version(self):
        """Assert GET /api/version returns version JSON."""
        req = urllib.request.Request(self._url("/api/version"))
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("version", data)

    def test_03_api_tags_aggregates_models_across_all_worker_nodes(self):
        """Assert GET /api/tags aggregates models across all configured worker nodes."""
        req = urllib.request.Request(self._url("/api/tags"))
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("models", data)
            model_names = [m["name"] for m in data["models"]]
            # Models from Node 1
            self.assertIn("llama3:8b", model_names)
            self.assertIn("mistral:7b", model_names)
            # Models from Node 2
            self.assertIn("qwen2.5-coder:7b", model_names)
            self.assertIn("deepseek-coder:6.7b", model_names)

    def test_04_api_tags_trailing_slash_handling(self):
        """Assert GET /api/tags/ with trailing slash returns model list."""
        req = urllib.request.Request(self._url("/api/tags/"))
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(len(data.get("models", [])) >= 4)

    def test_05_api_show_model_details(self):
        """Assert POST /api/show returns model parameters, template, and details."""
        req = urllib.request.Request(
            self._url("/api/show"),
            data=json.dumps({"name": "llama3:8b"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("details", data)
            self.assertEqual(data["details"].get("family"), "llama")

    def test_06_api_generate_non_streaming(self):
        """Assert POST /api/generate non-streaming returns standard Ollama completion response."""
        payload = {
            "model": "llama3:8b",
            "prompt": "Hello from autonomous agent platform",
            "stream": False
        }
        req = urllib.request.Request(
            self._url("/api/generate"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("response", data)
            self.assertTrue(data.get("done"))
            self.assertIn("prompt_eval_count", data)
            self.assertIn("eval_count", data)

    def test_07_api_generate_streaming(self):
        """Assert POST /api/generate streaming returns NDJSON chunks terminated by done=True."""
        payload = {
            "model": "llama3:8b",
            "prompt": "Stream this test token sequence",
            "stream": True
        }
        req = urllib.request.Request(
            self._url("/api/generate"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            raw = resp.read().decode("utf-8")
            lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
            self.assertTrue(len(lines) >= 2)
            last_chunk = json.loads(lines[-1])
            self.assertTrue(last_chunk.get("done"))
            self.assertIn("eval_count", last_chunk)

    def test_08_api_chat_non_streaming(self):
        """Assert POST /api/chat non-streaming returns Ollama structured chat message."""
        payload = {
            "model": "llama3:8b",
            "messages": [
                {"role": "user", "content": "How many worker nodes are active?"}
            ],
            "stream": False
        }
        req = urllib.request.Request(
            self._url("/api/chat"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("message", data)
            self.assertEqual(data["message"].get("role"), "assistant")
            self.assertTrue(data.get("done"))

    def test_09_api_chat_streaming(self):
        """Assert POST /api/chat streaming returns NDJSON message chunks."""
        payload = {
            "model": "llama3:8b",
            "messages": [{"role": "user", "content": "Stream chat"}],
            "stream": True
        }
        req = urllib.request.Request(
            self._url("/api/chat"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            raw = resp.read().decode("utf-8")
            lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
            self.assertTrue(len(lines) >= 2)
            last_chunk = json.loads(lines[-1])
            self.assertTrue(last_chunk.get("done"))

    def test_10_api_embeddings(self):
        """Assert POST /api/embeddings returns embedding vector list."""
        payload = {"model": "llama3:8b", "prompt": "Embed this string"}
        req = urllib.request.Request(
            self._url("/api/embeddings"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("embedding", data)
            self.assertTrue(len(data["embedding"]) > 0)

    def test_11_api_ps_running_models(self):
        """Assert GET /api/ps returns active compute pool status."""
        req = urllib.request.Request(self._url("/api/ps"))
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("models", data)

    def test_12_v1_models_openai_compatible(self):
        """Assert GET /v1/models returns OpenAI formatted model list."""
        req = urllib.request.Request(self._url("/v1/models"))
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("object"), "list")
            ids = [m["id"] for m in data.get("data", [])]
            self.assertIn("llama3:8b", ids)
            self.assertIn("qwen2.5-coder:7b", ids)

    def test_13_v1_chat_completions_openai_compatible(self):
        """Assert POST /v1/chat/completions returns OpenAI chat completion format."""
        payload = {
            "model": "llama3:8b",
            "messages": [{"role": "user", "content": "OpenAI format ping"}],
            "stream": False
        }
        req = urllib.request.Request(
            self._url("/v1/chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("choices", data)
            self.assertIn("usage", data)

    def test_14_mcp_rpc_bridge_on_secondary_port(self):
        """Assert POST /api/mcp/rpc executes JSON-RPC 2.0 tools/list directly on the secondary port."""
        rpc_req = {
            "jsonrpc": "2.0",
            "id": "test-rpc-1",
            "method": "tools/list"
        }
        req = urllib.request.Request(
            self._url("/api/mcp/rpc"),
            data=json.dumps(rpc_req).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("id"), "test-rpc-1")
            tools = data.get("result", {}).get("tools", [])
            tool_names = [t["name"] for t in tools]
            self.assertIn("generate_completion", tool_names)
            self.assertIn("list_managed_nodes", tool_names)

    def test_15_mcp_rpc_custom_path_rpc(self):
        """Assert POST /rpc also routes to MCP handler."""
        rpc_req = {"jsonrpc": "2.0", "id": "test-rpc-2", "method": "ping"}
        req = urllib.request.Request(
            self._url("/rpc"),
            data=json.dumps(rpc_req).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("id"), "test-rpc-2")

    def test_16_model_targeted_routing(self):
        """Assert requesting qwen2.5-coder:7b routes specifically to worker node 2."""
        initial_w2_reqs = self.worker2.request_count
        payload = {
            "model": "qwen2.5-coder:7b",
            "prompt": "Write a python function",
            "stream": False
        }
        req = urllib.request.Request(
            self._url("/api/generate"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
        self.assertTrue(self.worker2.request_count > initial_w2_reqs)

    def test_17_token_telemetry_persisted_in_database(self):
        """Assert inference requests through emulator log token usage into SQLite usage_events."""
        payload = {"model": "llama3:8b", "prompt": "Count tokens test", "stream": False}
        req = urllib.request.Request(
            self._url("/api/generate"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)

        # Check SQLite usage_events table
        summary = self.db.get_usage_summary(provider="ollama")
        self.assertTrue(summary.get("total_tokens_today", 0) > 0)

    def test_18_client_burst_limit_enforcement(self):
        """Assert client exceeding burst quota receives HTTP 429 error."""
        # Set tight quota for 127.0.0.1 (limit: 5 tokens)
        self.db.set_client_quota(
            client_ip="127.0.0.1",
            alias="localhost",
            session_window_minutes=15,
            session_token_limit=5,
            daily_token_limit=50000
        )
        # Record 10 tokens to immediately exceed the 5 token limit
        self.db.record_client_tokens("127.0.0.1", 10)

        payload = {"model": "llama3:8b", "prompt": "Should be rate limited", "stream": False}
        req = urllib.request.Request(
            self._url("/api/generate"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3.0)
        self.assertEqual(ctx.exception.code, 429)

        # Clean up / reset quota
        self.db.reset_client_tokens("127.0.0.1")
        self.db.set_client_quota(
            client_ip="127.0.0.1",
            session_token_limit=25000,
            daily_token_limit=250000
        )

    def test_19_failover_when_primary_node_tripped(self):
        """Assert circuit breaker failover routes to secondary candidate when primary node returns 503."""
        # Mark worker1 into fail mode
        self.worker1.fail_mode = True
        try:
            payload = {"model": "default", "prompt": "Failover prompt", "stream": False}
            req = urllib.request.Request(
                self._url("/api/generate"),
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            # Should failover to worker2 without failing the request
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data.get("done"))
        finally:
            self.worker1.fail_mode = False

    def test_20_cors_headers_supported(self):
        """Assert OPTIONS requests receive appropriate CORS headers for web clients."""
        req = urllib.request.Request(
            self._url("/api/generate"),
            method="OPTIONS"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods", ""))

if __name__ == "__main__":
    unittest.main()
