import http.server
import json
import urllib.parse
import threading
import time
from typing import Dict, Any, Optional, List

class OllamaEmulatorHandler(http.server.BaseHTTPRequestHandler):
    """
    Zero-dependency HTTP Handler emulating the Ollama REST API (/api/tags, /api/generate,
    /api/chat, /api/version, etc.), OpenAI-compatible routes (/v1/models, /v1/chat/completions),
    and direct Model Context Protocol JSON-RPC 2.0 pass-through (/api/mcp/rpc, /rpc).
    """

    def log_message(self, format, *args):
        # Silence console polling noise
        pass

    def _send_json(self, status: int, data: Any):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, Accept")
        self.end_headers()
        self.wfile.write(payload)

    def _get_client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "127.0.0.1"

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, Accept")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. Health Ping Root
        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"Ollama is running\n")
            return

        # 2. Ollama Version
        if path == "/api/version":
            return self._send_json(200, {"version": "0.5.4"})

        # 3. Model Inventory Aggregation
        if path in ["/api/tags", "/api/tags/"]:
            models = self._aggregate_models()
            return self._send_json(200, {"models": models})

        # 4. Running Compute Status
        if path == "/api/ps":
            models = self._aggregate_models()
            return self._send_json(200, {"models": models})

        # 5. OpenAI Compatible Models List
        if path == "/v1/models":
            models = self._aggregate_models()
            openai_models = [
                {
                    "id": m["name"],
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "ollama-emulator"
                }
                for m in models
            ]
            return self._send_json(200, {"object": "list", "data": openai_models})

        self._send_json(404, {"error": f"Endpoint '{path}' not found on Ollama emulator"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        client_ip = self._get_client_ip()

        content_len = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            data = {}

        # 1. MCP JSON-RPC 2.0 Bridging
        if path in ["/api/mcp/rpc", "/rpc"] or ("jsonrpc" in data and "method" in data):
            if hasattr(self.server, "mcp_server") and self.server.mcp_server:
                res = self.server.mcp_server.handle_json_rpc(data)
                if res is None:
                    self.send_response(204)
                    self.end_headers()
                    return
                return self._send_json(200, res)
            return self._send_json(503, {"error": "MCP server not available on emulator bridge."})

        # 2. Model Inspection (/api/show)
        if path == "/api/show":
            model_name = data.get("name") or data.get("model") or "llama3:8b"
            if hasattr(self.server, "governor") and self.server.governor:
                res = self.server.governor.forward_ollama_request("/api/show", data, client_ip=client_ip)
                if res.get("success") and res.get("data"):
                    return self._send_json(200, res["data"])

            family = model_name.split(":")[0] if ":" in model_name else "llama"
            fallback = {
                "modelfile": f"# Modelfile for {model_name}\nFROM {model_name}",
                "parameters": "stop \"<|end_of_text|>\"",
                "template": "{{ .Prompt }}",
                "details": {
                    "format": "gguf",
                    "family": family,
                    "parameter_size": "8B",
                    "quantization_level": "Q4_0"
                }
            }
            return self._send_json(200, fallback)

        # 3. Vector Embeddings (/api/embeddings, /api/embed)
        if path in ["/api/embeddings", "/api/embed"]:
            if hasattr(self.server, "governor") and self.server.governor:
                res = self.server.governor.forward_ollama_request(path, data, client_ip=client_ip)
                if res.get("success") and res.get("data"):
                    return self._send_json(200, res["data"])
                if not res.get("success") and res.get("status_code") in [403, 429]:
                    return self._send_json(res["status_code"], {"error": res.get("error")})

            return self._send_json(200, {"embedding": [0.012, -0.045, 0.089, 0.123]})

        # 4. Text Generation (/api/generate)
        if path == "/api/generate":
            stream = bool(data.get("stream", False))
            if not hasattr(self.server, "governor") or not self.server.governor:
                return self._send_json(503, {"error": "Traffic governor not initialized"})

            if stream:
                success, status, stream_res = self.server.governor.stream_ollama_request(
                    "/api/generate",
                    data,
                    client_ip=client_ip
                )
                if not success:
                    return self._send_json(status, stream_res)

                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

                try:
                    for chunk in stream_res:
                        if isinstance(chunk, bytes):
                            self.wfile.write(chunk)
                        else:
                            self.wfile.write((json.dumps(chunk) + "\n").encode("utf-8"))
                        self.wfile.flush()
                except Exception:
                    pass
                return
            else:
                res = self.server.governor.forward_ollama_request("/api/generate", data, client_ip=client_ip)
                if not res.get("success"):
                    return self._send_json(res.get("status_code", 500), {"error": res.get("error")})
                return self._send_json(200, res.get("data", {}))

        # 5. Structured Chat (/api/chat)
        if path == "/api/chat":
            stream = bool(data.get("stream", False))
            if not hasattr(self.server, "governor") or not self.server.governor:
                return self._send_json(503, {"error": "Traffic governor not initialized"})

            if stream:
                success, status, stream_res = self.server.governor.stream_ollama_request(
                    "/api/chat",
                    data,
                    client_ip=client_ip
                )
                if not success:
                    return self._send_json(status, stream_res)

                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

                try:
                    for chunk in stream_res:
                        if isinstance(chunk, bytes):
                            self.wfile.write(chunk)
                        else:
                            self.wfile.write((json.dumps(chunk) + "\n").encode("utf-8"))
                        self.wfile.flush()
                except Exception:
                    pass
                return
            else:
                res = self.server.governor.forward_ollama_request("/api/chat", data, client_ip=client_ip)
                if not res.get("success"):
                    return self._send_json(res.get("status_code", 500), {"error": res.get("error")})
                return self._send_json(200, res.get("data", {}))

        # 6. OpenAI Chat Completions Bridge (/v1/chat/completions)
        if path == "/v1/chat/completions":
            model = data.get("model", "llama3:8b")
            messages = data.get("messages", [])
            stream = bool(data.get("stream", False))

            if not hasattr(self.server, "governor") or not self.server.governor:
                return self._send_json(503, {"error": "Traffic governor not initialized"})

            chat_payload = {"model": model, "messages": messages, "stream": stream}

            if stream:
                success, status, stream_res = self.server.governor.stream_ollama_request(
                    "/api/chat",
                    chat_payload,
                    client_ip=client_ip
                )
                if not success:
                    return self._send_json(status, stream_res)

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

                try:
                    for line in stream_res:
                        if isinstance(line, bytes):
                            line_str = line.decode("utf-8").strip()
                        else:
                            line_str = json.dumps(line)
                        if line_str:
                            try:
                                chunk_json = json.loads(line_str)
                                content = chunk_json.get("message", {}).get("content", "")
                                sse_payload = {
                                    "id": f"chatcmpl-{int(time.time() * 1000)}",
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": model,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {"content": content},
                                            "finish_reason": "stop" if chunk_json.get("done") else None
                                        }
                                    ]
                                }
                                self.wfile.write(f"data: {json.dumps(sse_payload)}\n\n".encode("utf-8"))
                                self.wfile.flush()
                            except Exception:
                                pass
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except Exception:
                    pass
                return
            else:
                res = self.server.governor.forward_ollama_request("/api/chat", chat_payload, client_ip=client_ip)
                if not res.get("success"):
                    return self._send_json(res.get("status_code", 500), {"error": res.get("error")})

                resp_data = res.get("data", {})
                content = ""
                if "message" in resp_data:
                    content = resp_data["message"].get("content", "")
                elif "choices" in resp_data and resp_data["choices"]:
                    content = resp_data["choices"][0].get("message", {}).get("content", "")
                elif "response" in resp_data:
                    content = resp_data["response"]

                in_tok = int(resp_data.get("prompt_eval_count") or resp_data.get("usage", {}).get("prompt_tokens") or 10)
                out_tok = int(resp_data.get("eval_count") or resp_data.get("usage", {}).get("completion_tokens") or 25)

                openai_resp = {
                    "id": f"chatcmpl-{int(time.time() * 1000)}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": content
                            },
                            "finish_reason": "stop"
                        }
                    ],
                    "usage": {
                        "prompt_tokens": in_tok,
                        "completion_tokens": out_tok,
                        "total_tokens": in_tok + out_tok
                    }
                }
                return self._send_json(200, openai_resp)

        self._send_json(404, {"error": f"Endpoint '{path}' not found on Ollama emulator"})

    def _aggregate_models(self) -> List[Dict[str, Any]]:
        """Collects and deduplicates models installed across all registered nodes."""
        if not hasattr(self.server, "registry") or not self.server.registry:
            return []

        nodes = self.server.registry.list_nodes()
        models_list = []
        seen = set()

        for node in nodes:
            for m in (node.get("models") or []):
                if isinstance(m, dict):
                    name = m.get("name") or m.get("model") or "unknown"
                    param_size = m.get("parameter_size") or "8B"
                    family = m.get("family") or (name.split(":")[0] if ":" in name else name)
                    size = m.get("size") or 4661224676
                    digest = m.get("digest") or f"sha256:{abs(hash(name)):012x}"
                    modified_at = m.get("modified_at") or "2026-10-20T10:00:00Z"
                else:
                    name = str(m)
                    param_size = "8B"
                    family = name.split(":")[0] if ":" in name else name
                    size = 4661224676
                    digest = f"sha256:{abs(hash(name)):012x}"
                    modified_at = "2026-10-20T10:00:00Z"

                if name not in seen:
                    seen.add(name)
                    models_list.append({
                        "name": name,
                        "model": name,
                        "modified_at": modified_at,
                        "size": size,
                        "digest": digest,
                        "details": {
                            "format": "gguf",
                            "family": family,
                            "parameter_size": param_size,
                            "quantization_level": "Q4_0"
                        }
                    })

        return models_list


class OllamaEmulatorServer:
    """
    Dedicated secondary HTTP server that emulates the Ollama REST API and provides
    a pass-through bridge to managed worker nodes and MCP JSON-RPC.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8989,
        governor=None,
        registry=None,
        database=None,
        mcp_server=None
    ):
        self.host = host
        self.port = port
        self.governor = governor
        self.registry = registry
        self.database = database
        self.mcp_server = mcp_server
        self._server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def server_port(self) -> int:
        if self._server:
            return self._server.server_port
        return self.port

    def start(self):
        server_address = (self.host, self.port)
        self._server = http.server.ThreadingHTTPServer(server_address, OllamaEmulatorHandler)
        self._server.governor = self.governor
        self._server.registry = self.registry
        self._server.database = self.database
        self._server.mcp_server = self.mcp_server
        self._server.host = self.host
        self._server.port = self.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
