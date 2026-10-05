import http.server
import json
import urllib.parse
import mimetypes
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional

from backend.config import FRONTEND_DIR, DEFAULT_HOST, DEFAULT_PORT
from backend.diagnostics.logging_engine import ErrorCategory

MIME_MAP = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

class AppHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """
    Zero-dependency HTTP Handler for Static Assets and REST API endpoints.
    """

    def log_message(self, format, *args):
        # Silence console log noise for regular polling
        pass

    def _send_json(self, status: int, data: Any):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API Endpoints
        if path.startswith("/api/"):
            return self._handle_api_get(path, query)

        # 2. Static File Serving
        self._serve_static(path)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            try:
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except Exception:
                body = {}

        if path.startswith("/api/"):
            return self._handle_api_post(path, body)

        self.send_error(404, "Endpoint not found")

    def _handle_api_get(self, path: str, query: Dict[str, Any]):
        srv = self.server

        if path == "/api/status":
            prov_snapshots = srv.database.get_provider_snapshots()
            resp = {
                "service": "AI_Usage_Monitor",
                "version": "0.1.0",
                "status": "HEALTHY",
                "proxy_port": srv.proxy_port,
                "server_port": srv.server_port,
                "providers": prov_snapshots
            }
            return self._send_json(200, resp)

        if path == "/api/usage/summary":
            provider = query.get("provider", [None])[0]
            summary = srv.database.get_usage_summary(provider=provider)
            return self._send_json(200, summary)

        if path == "/api/usage/sessions":
            limit = int(query.get("limit", [50])[0])
            provider = query.get("provider", [None])[0]
            sessions = srv.database.get_recent_sessions(limit=limit, provider=provider)
            return self._send_json(200, sessions)

        if path == "/api/usage/hourly":
            hours = int(query.get("hours", [24])[0])
            provider = query.get("provider", [None])[0]
            hourly = srv.database.get_hourly_breakdown(hours=hours, provider=provider)
            return self._send_json(200, hourly)

        if path == "/api/providers":
            result = {}
            for name, prov in srv.providers.items():
                result[name] = prov.get_snapshot()
            return self._send_json(200, result)

        if path == "/api/providers/ollama/models":
            ollama = srv.providers.get("ollama")
            if ollama:
                return self._send_json(200, {
                    "installed": ollama.get_installed_models(),
                    "running": ollama.get_running_models()
                })
            return self._send_json(404, {"error": "Ollama provider not registered"})

        if path == "/api/diagnostics/errors":
            limit = int(query.get("limit", [50])[0])
            errors = srv.diagnostics.get_recent_errors(limit=limit)
            return self._send_json(200, errors)

        if path == "/api/diagnostics/export":
            bundle = srv.diagnostics.export_diagnostic_bundle()
            bundle["usage_summary"] = srv.database.get_usage_summary()
            return self._send_json(200, bundle)

        self._send_json(404, {"error": "API route not found"})

    def _handle_api_post(self, path: str, body: Dict[str, Any]):
        srv = self.server

        if path == "/api/usage/import":
            from backend.storage.importer import TelemetryImporter
            importer = TelemetryImporter(srv.database)
            raw = body.get("raw_content", "")
            prov = body.get("provider", "copilot")
            imported = importer.import_raw_telemetry(raw, default_provider=prov)
            return self._send_json(200, {"success": True, "imported_count": imported})

        if path == "/api/usage/manual":
            from backend.storage.importer import TelemetryImporter
            importer = TelemetryImporter(srv.database)
            prov = body.get("provider", "copilot")
            model = body.get("model", "m365-chat")
            in_tok = int(body.get("input_tokens", 0))
            out_tok = int(body.get("output_tokens", 0))
            sess = body.get("session_id")
            evt_id = importer.log_manual_interaction(prov, model, in_tok, out_tok, sess)
            return self._send_json(200, {"success": True, "event_id": evt_id})

        if path == "/api/providers/sync":
            target = body.get("provider", "claude")
            prov = srv.providers.get(target)
            if prov:
                res = prov.sync_usage()
                return self._send_json(200, res)
            return self._send_json(404, {"error": f"Provider '{target}' not found"})

        if path == "/api/providers/claude/config":
            api_key = body.get("api_key")
            simulation = body.get("simulation_mode")

            claude_prov = srv.providers.get("claude")
            if simulation is not None and claude_prov:
                claude_prov.enable_simulation_mode(bool(simulation))

            if api_key:
                srv.vault.set_credential("claude", "default", api_key)
                if claude_prov:
                    claude_prov.enable_simulation_mode(False)

            return self._send_json(200, {"success": True, "message": "Claude configuration saved"})

        if path == "/api/providers/gemini/config":
            api_key = body.get("api_key")
            gemini_prov = srv.providers.get("gemini")
            if api_key and gemini_prov:
                gemini_prov.configure_api_key(api_key)
            elif api_key:
                srv.vault.set_credential("gemini", "default", api_key)
            return self._send_json(200, {"success": True, "message": "Google Gemini configuration saved"})

        if path == "/api/providers/chatgpt/config":
            api_key = body.get("api_key")
            chatgpt_prov = srv.providers.get("chatgpt")
            if api_key and chatgpt_prov:
                chatgpt_prov.configure_api_key(api_key)
            elif api_key:
                srv.vault.set_credential("chatgpt", "default", api_key)
            return self._send_json(200, {"success": True, "message": "ChatGPT / OpenAI configuration saved"})

        if path == "/api/system/open-url":
            import webbrowser
            target_url = body.get("url", "")
            if target_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
                webbrowser.open(target_url)
                return self._send_json(200, {"success": True, "url": target_url})
            return self._send_json(400, {"error": "Invalid or disallowed URL scheme"})

        if path == "/api/diagnostics/clear":
            srv.diagnostics.clear_errors()
            return self._send_json(200, {"success": True, "message": "Diagnostic errors cleared"})

        self._send_json(404, {"error": "API route not found"})

    def _serve_static(self, req_path: str):
        if req_path in ["", "/", "/index", "/dashboard"]:
            rel_file = "index.html"
        elif req_path in ["/widget", "/mini", "/mini_widget"]:
            rel_file = "mini_widget.html"
        else:
            rel_file = req_path.lstrip("/")

        file_path = (Path(FRONTEND_DIR) / rel_file).resolve()

        # Security check: prevent directory traversal outside FRONTEND_DIR
        try:
            file_path.relative_to(Path(FRONTEND_DIR).resolve())
        except ValueError:
            return self.send_error(403, "Access Denied")

        if not file_path.exists() or not file_path.is_file():
            # If not found, return 404
            return self.send_error(404, f"File not found: {rel_file}")

        suffix = file_path.suffix.lower()
        content_type = MIME_MAP.get(suffix, "application/octet-stream")

        try:
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")

class AppHTTPServer:
    """
    Main Application HTTP Server managing REST APIs and Web UI delivery.
    """

    def __init__(
        self,
        database,
        vault,
        diagnostics,
        providers: Dict[str, Any],
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        proxy_port: int = 8766
    ):
        self.database = database
        self.vault = vault
        self.diagnostics = diagnostics
        self.providers = providers
        self.host = host
        self.port = port
        self.proxy_port = proxy_port
        self._server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def server_port(self) -> int:
        if self._server:
            return self._server.server_port
        return self.port

    def start(self):
        server_address = (self.host, self.port)
        self._server = http.server.ThreadingHTTPServer(server_address, AppHTTPRequestHandler)
        self._server.database = self.database
        self._server.vault = self.vault
        self._server.diagnostics = self.diagnostics
        self._server.providers = self.providers
        self._server.proxy_port = self.proxy_port
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
