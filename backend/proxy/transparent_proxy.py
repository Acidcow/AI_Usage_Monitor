import http.server
import json
import threading
import urllib.request
import urllib.error
import time
from typing import Optional, Dict, Any

from backend.diagnostics.logging_engine import ErrorCategory

class TransparentProxyHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP Request Handler that transparently proxies LLM calls and extracts token telemetry.
    """

    def log_message(self, format, *args):
        # Suppress noisy standard HTTP access logs
        pass

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "status": "UP",
                "proxy_target": "claude",
                "listening_port": self.server.server_port
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        # 1. Test / Mock Mode Inspection
        if self.headers.get("x-mock-response") == "true":
            in_tok = int(self.headers.get("x-mock-input-tokens", 100))
            out_tok = int(self.headers.get("x-mock-output-tokens", 50))
            model_name = "claude-3-7-sonnet"
            try:
                data = json.loads(raw_body.decode("utf-8"))
                model_name = data.get("model", model_name)
            except Exception:
                pass

            # Ingest into provider
            self.server.claude_provider.ingest_proxy_interaction(
                model=model_name,
                input_tokens=in_tok,
                output_tokens=out_tok,
                session_id=f"cli_proxy_{int(time.time())}"
            )

            mock_response = {
                "id": "msg_mock_proxy_12345",
                "type": "message",
                "role": "assistant",
                "model": model_name,
                "content": [{"type": "text", "text": "This is a response proxied through AI Usage Monitor."}],
                "usage": {
                    "input_tokens": in_tok,
                    "output_tokens": out_tok
                }
            }
            body_bytes = json.dumps(mock_response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
            return

        # 2. Forward to Upstream Anthropic API
        upstream_url = "https://api.anthropic.com" + self.path
        upstream_headers = dict(self.headers)

        # Inject stored API key if not supplied by client
        if "x-api-key" not in upstream_headers or not upstream_headers["x-api-key"]:
            stored_key = self.server.claude_provider.vault.get_credential("claude", "default")
            if stored_key:
                upstream_headers["x-api-key"] = stored_key

        # Remove host header to avoid SSL hostname mismatch
        upstream_headers.pop("Host", None)
        upstream_headers.pop("host", None)

        try:
            req = urllib.request.Request(
                upstream_url,
                data=raw_body,
                headers=upstream_headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                resp_body = resp.read()
                resp_headers = dict(resp.headers)

                # Parse token metrics from response JSON
                try:
                    resp_json = json.loads(resp_body.decode("utf-8"))
                    usage = resp_json.get("usage", {})
                    in_tok = usage.get("input_tokens", 0)
                    out_tok = usage.get("output_tokens", 0)
                    model_val = resp_json.get("model", "claude")

                    self.server.claude_provider.ingest_proxy_interaction(
                        model=model_val,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        rate_limit_headers=resp_headers
                    )
                except Exception:
                    pass

                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ["content-encoding", "transfer-encoding"]:
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp_body)

        except urllib.error.HTTPError as e:
            err_body = e.read()
            self.server.claude_provider.diagnostics.record_error(
                ErrorCategory.PROXY_BLOCKED if e.code in [403, 407] else ErrorCategory.SYSTEM_ERROR,
                "claude",
                f"Proxy upstream HTTP error {e.code}: {e.reason}",
                {"status_code": e.code}
            )
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as e:
            self.server.claude_provider.diagnostics.record_error(
                ErrorCategory.NETWORK_TIMEOUT,
                "claude",
                f"Proxy network error forwarding request: {e}",
                {"exception": str(e)}
            )
            self.send_error(502, f"Bad Gateway: {e}")

class TransparentProxyServer:
    """
    Transparent Local Proxy Server running in background thread.
    """

    def __init__(self, claude_provider, host: str = "127.0.0.1", port: int = 8766):
        self.claude_provider = claude_provider
        self.host = host
        self.port = port
        self._server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def server_port(self) -> int:
        if self._server:
            return self._server.server_port
        return self.port

    def start(self):
        server_address = (self.host, self.port)
        self._server = http.server.ThreadingHTTPServer(server_address, TransparentProxyHandler)
        self._server.claude_provider = self.claude_provider
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
