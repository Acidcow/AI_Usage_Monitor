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
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
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

        if path == "/api/usage/comparison":
            scope = query.get("scope", ["individual"])[0]
            comp = srv.database.get_comparative_metrics(scope=scope)
            return self._send_json(200, comp)

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
                    "running": ollama.get_running_models(),
                    "models": ollama.get_model_telemetry_summary()
                })
            return self._send_json(404, {"error": "Ollama provider not registered"})

        if path == "/api/settings":
            return self._send_json(200, srv.database.get_all_settings())

        if path == "/api/tags":
            return self._send_json(200, srv.database.get_cross_platform_tags())

        if path == "/api/diagnostics/errors":
            limit = int(query.get("limit", [50])[0])
            errors = srv.diagnostics.get_recent_errors(limit=limit)
            return self._send_json(200, errors)

        if path == "/api/diagnostics/export":
            bundle = srv.diagnostics.export_diagnostic_bundle()
            bundle["usage_summary"] = srv.database.get_usage_summary()
            return self._send_json(200, bundle)

        # Google OAuth Endpoints
        if path == "/api/auth/google/login":
            redirect_uri = f"http://{srv.host}:{srv.server_port}/api/auth/google/callback"
            info = srv.google_auth_mgr.get_authorization_url(redirect_uri)
            if query.get("browser", ["0"])[0] == "1":
                self.send_response(302)
                self.send_header("Location", info["auth_url"])
                self.end_headers()
                return
            return self._send_json(200, info)

        if path == "/api/auth/google/callback":
            code = query.get("code", [""])[0]
            state = query.get("state", [""])[0]
            redirect_uri = f"http://{srv.host}:{srv.server_port}/api/auth/google/callback"
            res = srv.google_auth_mgr.exchange_code_for_tokens(code, state, redirect_uri)
            email = res.get("email", "acidcow@gmail.com")
            html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Google Account Connected</title></head>
            <body style="background:#0b101b;color:#f8fafc;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
              <div style="background:#151e2e;padding:32px;border-radius:12px;border:1px solid #10b981;text-align:center;max-width:420px;box-shadow:0 0 24px rgba(16,185,129,0.2);">
                <div style="font-size:2.5rem;margin-bottom:12px;">✅</div>
                <h2 style="color:#34d399;margin-top:0;">Google Account Connected!</h2>
                <p style="color:#cbd5e1;font-size:0.95rem;">Authenticated as: <strong style="color:#38bdf8;">{email}</strong></p>
                <p style="font-size:0.8rem;color:#94a3b8;margin-top:16px;">Credentials encrypted via Windows DPAPI. Returning to monitor...</p>
                <script>setTimeout(() => {{ window.opener ? window.close() : (window.location.href = '/'); }}, 1800);</script>
              </div>
            </body></html>"""
            payload = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/api/auth/google/status":
            return self._send_json(200, srv.google_auth_mgr.get_auth_status())

        # Historical Reporting & Analytics Endpoint
        if path == "/api/reports/history":
            group_by = query.get("group_by", ["day"])[0]
            start_date = query.get("start_date", [None])[0]
            end_date = query.get("end_date", [None])[0]
            prov = query.get("provider", [None])[0]
            acct = query.get("account_id", [None])[0]
            team = query.get("team_name", [None])[0]
            user = query.get("user_name", [None])[0]
            token = query.get("token_id", [None])[0]
            model = query.get("model", [None])[0]
            proj = query.get("project_id", [None])[0]
            dim = query.get("dimension", [None])[0]
            fmt = query.get("format", ["json"])[0]

            if fmt == "csv":
                csv_data = srv.database.export_historical_csv(
                    group_by=group_by,
                    start_date=start_date,
                    end_date=end_date,
                    provider=prov,
                    account_id=acct,
                    team_name=team,
                    user_name=user,
                    model=model
                )
                payload = csv_data.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="ai_usage_history.csv"')
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            res = srv.database.query_historical_report(
                group_by=group_by,
                start_date=start_date,
                end_date=end_date,
                provider=prov,
                account_id=acct,
                team_name=team,
                user_name=user,
                token_id=token,
                model=model,
                project_id=proj,
                dimension=dim
            )
            return self._send_json(200, res)

        # Capacity & Throughput Analytics Endpoints
        if path == "/api/analytics/throughput":
            from backend.analytics.throughput_engine import ThroughputAnalyticsEngine
            engine = ThroughputAnalyticsEngine(srv.database)
            prov = query.get("provider", [None])[0]
            metrics = engine.compute_throughput_metrics(provider=prov)
            return self._send_json(200, {"throughput": metrics})

        if path == "/api/analytics/forecast":
            from backend.analytics.throughput_engine import ThroughputAnalyticsEngine
            engine = ThroughputAnalyticsEngine(srv.database)
            fc = engine.compute_capacity_forecast()
            return self._send_json(200, fc)

        if path == "/api/analytics/recommendations":
            from backend.analytics.throughput_engine import ThroughputAnalyticsEngine
            engine = ThroughputAnalyticsEngine(srv.database)
            recs = engine.generate_estate_recommendations()
            return self._send_json(200, {"recommendations": recs})

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
            project_id = body.get("project_id")
            gemini_prov = srv.providers.get("gemini")
            if api_key and gemini_prov:
                gemini_prov.configure_api_key(api_key, project_id=project_id)
            elif api_key:
                srv.vault.set_credential("gemini", "default", api_key)
                if project_id:
                    srv.vault.set_credential("gemini", "project_id", project_id)
            return self._send_json(200, {"success": True, "message": "Google Gemini configuration saved"})

        if path == "/api/providers/chatgpt/config":
            api_key = body.get("api_key")
            chatgpt_prov = srv.providers.get("chatgpt")
            if api_key and chatgpt_prov:
                chatgpt_prov.configure_api_key(api_key)
            elif api_key:
                srv.vault.set_credential("chatgpt", "default", api_key)
            return self._send_json(200, {"success": True, "message": "ChatGPT / OpenAI configuration saved"})

        if path == "/api/providers/claude/quota":
            claude_prov = srv.providers.get("claude")
            scope = body.get("scope", "individual")
            session_used = body.get("session_used_pct")
            session_rem = body.get("session_remaining_pct")
            session_reset_secs = body.get("session_reset_seconds")
            session_reset_mins = body.get("session_reset_minutes")
            weekly_used = body.get("weekly_used_pct")
            weekly_rem = body.get("weekly_remaining_pct")
            weekly_reset_str = body.get("weekly_reset_str")
            plan_type = body.get("plan_type", "Team Enterprise")
            ind_sess_used = body.get("individual_session_used_pct")
            ind_week_used = body.get("individual_weekly_used_pct")
            team_sess_used = body.get("team_session_used_pct")
            team_week_used = body.get("team_weekly_used_pct")
            user_name = body.get("user_name")
            team_name = body.get("team_name")

            if session_reset_mins is not None and session_reset_secs is None:
                try:
                    session_reset_secs = int(float(session_reset_mins) * 60)
                except Exception:
                    session_reset_secs = 7560

            if claude_prov and hasattr(claude_prov, "calibrate_limits"):
                res = claude_prov.calibrate_limits(
                    session_used_pct=session_used,
                    session_remaining_pct=session_rem,
                    session_reset_seconds=session_reset_secs,
                    weekly_used_pct=weekly_used,
                    weekly_remaining_pct=weekly_rem,
                    weekly_reset_str=weekly_reset_str,
                    plan_type=plan_type,
                    scope=scope,
                    individual_session_used_pct=ind_sess_used,
                    individual_weekly_used_pct=ind_week_used,
                    team_session_used_pct=team_sess_used,
                    team_weekly_used_pct=team_week_used,
                    user_name=user_name,
                    team_name=team_name
                )
                return self._send_json(200, res)
            else:
                if session_rem is None and session_used is not None:
                    session_rem = max(0.0, 100.0 - float(session_used))
                if weekly_rem is None and weekly_used is not None:
                    weekly_rem = max(0.0, 100.0 - float(weekly_used))
                reset_epoch = (time.time() + session_reset_secs) if session_reset_secs else (time.time() + 7560)
                srv.database.update_provider_snapshot(
                    provider="claude",
                    plan_type=plan_type,
                    session_remaining_pct=session_rem or 40.0,
                    weekly_remaining_pct=weekly_rem or 73.0,
                    weekly_reset_str=weekly_reset_str or "Mon 3:00 AM",
                    reset_epoch=reset_epoch,
                    status="ACTIVE",
                    user_name=user_name,
                    team_name=team_name,
                    active_scope=scope
                )
                return self._send_json(200, {"success": True, "message": "Claude quota calibrated in database"})

        if path == "/api/widget/launch":
            dry_run = bool(body.get("dry_run", False))
            from backend.tray.desktop_widget import launch_desktop_widget
            host = getattr(srv, "host", srv.server_address[0] if hasattr(srv, "server_address") else "127.0.0.1")
            raw_port = getattr(srv, "port", srv.server_address[1] if hasattr(srv, "server_address") else 8765)
            # Route to canonical port 8765 if on ephemeral port (>30000 or 0)
            target_port = 8765 if (raw_port == 0 or raw_port > 30000) and not dry_run else raw_port
            res = launch_desktop_widget(host=host, port=target_port, dry_run=dry_run)
            return self._send_json(200, res)

        # Google OAuth POST Endpoints
        if path == "/api/auth/google/simulate":
            email = body.get("email", "acidcow@gmail.com")
            name = body.get("name", "James Eckhardt")
            res = srv.google_auth_mgr.simulate_sign_in(email=email, name=name)
            return self._send_json(200, res)

        if path == "/api/auth/google/signout":
            res = srv.google_auth_mgr.sign_out()
            return self._send_json(200, res)

        if path == "/api/auth/google/tokens":
            name = body.get("name", "Gemini Dev Token")
            api_key = body.get("api_key", "")
            desc = body.get("description")
            res = srv.google_auth_mgr.add_named_token(name=name, api_key=api_key, description=desc)
            return self._send_json(200, res)

        if path == "/api/auth/google/tokens/delete":
            token_id = body.get("token_id", "")
            res = srv.google_auth_mgr.delete_named_token(token_id=token_id)
            return self._send_json(200, res)

        if path == "/api/system/open-url":
            import webbrowser
            target_url = body.get("url", "")
            if target_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
                webbrowser.open(target_url)
                return self._send_json(200, {"success": True, "url": target_url})
            return self._send_json(400, {"error": "Invalid or disallowed URL scheme"})

        if path == "/api/settings":
            settings_dict = body.get("settings", body)
            if isinstance(settings_dict, dict):
                for k, v in settings_dict.items():
                    srv.database.set_setting(k, v)
                return self._send_json(200, {"success": True, "settings": srv.database.get_all_settings()})
            return self._send_json(400, {"error": "Settings must be a key-value dictionary"})

        if path == "/api/tags":
            tag_name = body.get("tag_name", "").strip()
            target_type = (body.get("target_type") or body.get("entity_type") or "account").strip()
            target_identifier = (body.get("target_identifier") or body.get("entity_identifier") or "").strip()
            provider = body.get("provider", "").strip()
            desc = body.get("description", "")
            if not tag_name or not target_identifier:
                return self._send_json(400, {"error": "tag_name and target_identifier are required"})
            tag_id = srv.database.add_cross_platform_tag(
                tag_name=tag_name,
                target_type=target_type,
                target_identifier=target_identifier,
                description=desc,
                provider=provider
            )
            return self._send_json(200, {"success": True, "tag_id": tag_id, "tag_name": tag_name})

        if path == "/api/tags/delete":
            tag_id = body.get("tag_id") or body.get("id") or body.get("tag_name")
            if not tag_id:
                return self._send_json(400, {"error": "tag_id or tag_name is required"})
            deleted = srv.database.remove_cross_platform_tag(tag_id)
            return self._send_json(200, {"success": True, "deleted": deleted})

        if path == "/api/providers/ollama/telemetry":
            ollama = srv.providers.get("ollama")
            if not ollama:
                return self._send_json(404, {"error": "Ollama provider not registered"})
            model = body.get("model", "llama3:latest")
            prompt_tokens = int(body.get("prompt_tokens") or body.get("input_tokens") or 0)
            completion_tokens = int(body.get("completion_tokens") or body.get("output_tokens") or 0)
            session_id = body.get("session_id")
            evt_id = ollama.ingest_inference_tokens(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                session_id=session_id
            )
            return self._send_json(200, {"success": True, "event_id": evt_id, "model": model})

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
        proxy_port: int = 8766,
        google_auth_mgr: Optional[Any] = None
    ):
        self.database = database
        self.vault = vault
        self.diagnostics = diagnostics
        self.providers = providers
        self.host = host
        self.port = port
        self.proxy_port = proxy_port

        from backend.security.google_auth import GoogleAuthManager
        self.google_auth_mgr = google_auth_mgr or GoogleAuthManager(vault=self.vault, database=self.database)

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
        self._server.host = self.host
        self._server.port = self.server_port
        self._server.google_auth_mgr = self.google_auth_mgr
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
