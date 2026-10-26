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
        try:
            self.wfile.write(payload)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path.startswith("/api/"):
            return self._handle_api_delete(path, query)

        self.send_error(404, "Endpoint not found")

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

    def _get_client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if hasattr(self, "client_address") and self.client_address:
            return self.client_address[0]
        return "127.0.0.1"

    def _handle_api_get(self, path: str, query: Dict[str, Any]):
        srv = self.server

        if path == "/api/status":
            prov_snapshots = srv.database.get_provider_snapshots()
            svc_mgr = getattr(srv, "service_manager", None)
            startup_enabled = svc_mgr.is_startup_enabled() if svc_mgr else False
            resp = {
                "service": "AI_Usage_Monitor",
                "version": "0.1.0",
                "status": "HEALTHY",
                "proxy_port": srv.proxy_port,
                "server_port": srv.server_port,
                "startup_enabled": startup_enabled,
                "providers": prov_snapshots
            }
            return self._send_json(200, resp)

        # AIUM-901: Windows Auto-Start & Background Service Lifecycle Status
        if path in ["/api/system/startup", "/api/system/service"]:
            svc_mgr = getattr(srv, "service_manager", None)
            if not svc_mgr:
                from backend.system.windows_service import WindowsServiceManager
                svc_mgr = WindowsServiceManager()
            include_logs = query.get("logs", ["true"])[0].lower() in ("1", "true", "yes")
            status = svc_mgr.get_service_status(include_logs=include_logs)
            # Since this HTTP request is actively being served by this process, ensure live port/PID visibility
            if not status.get("running"):
                import os
                status["running"] = True
                status["pid"] = os.getpid()
                status["mode"] = "interactive"
            status["port"] = srv.server_port
            status["proxy_port"] = srv.proxy_port
            return self._send_json(200, status)

        # AIUM-703, AIUM-704: LAN Discovery, Adapters, Inventory & Node Endpoints
        if path == "/api/discovery/adapters":
            scanner = getattr(srv, "scanner", None)
            if not scanner:
                from backend.discovery.lan_scanner import LANScanner
                scanner = LANScanner()
            adapters = scanner.get_local_adapters_and_subnets()
            return self._send_json(200, {"success": True, "adapters": adapters})

        if path == "/api/discovery/inventory":
            state_filter = query.get("state", [None])[0]
            group_filter = query.get("group", [None])[0] or query.get("compute_group", [None])[0]
            inv = srv.database.list_device_inventory(state=state_filter, compute_group=group_filter)
            return self._send_json(200, {"success": True, "inventory": inv})

        if path == "/api/discovery/platforms":
            from backend.discovery.lan_scanner import PLATFORM_CATALOG
            return self._send_json(200, {"success": True, "platforms": PLATFORM_CATALOG})

        if path == "/api/discovery/scan":
            targets_str = query.get("targets", [None])[0] or query.get("range", [None])[0]
            subnet = query.get("subnet", [None])[0]
            platforms_param = query.get("platforms", [None])[0]
            sec_ports_param = query.get("secondary_ports", [None])[0]
            timeout_val = float(query.get("timeout", [0.4])[0])

            scanner = getattr(srv, "scanner", None)
            if not scanner:
                from backend.discovery.lan_scanner import LANScanner
                scanner = LANScanner()

            platforms_list = [p.strip() for p in platforms_param.split(",") if p.strip()] if platforms_param else None
            sec_ports_list = [int(p.strip()) for p in sec_ports_param.split(",") if p.strip() and p.strip().isdigit()] if sec_ports_param else None

            spec = targets_str or subnet
            if spec:
                ips = scanner.parse_target_spec(spec)
            else:
                _, detected_sub = scanner.get_local_subnet_info()
                ips = scanner.parse_target_spec(detected_sub)

            if "127.0.0.1" not in ips:
                ips.append("127.0.0.1")

            target_pairs = scanner.build_scan_targets(
                ips=ips,
                platforms=platforms_list,
                secondary_ports=sec_ports_list
            )
            candidates = scanner.scan_targets(target_pairs, timeout=timeout_val)

            try:
                for c in candidates:
                    alias = c.get("alias") or c.get("ip")
                    srv.database.upsert_device_inventory(
                        alias=alias,
                        ip=c.get("ip"),
                        state="KNOWN_SERVICES",
                        discovered_services=[{"engine": c.get("engine"), "port": c.get("port"), "models": c.get("models", []), "endpoint": c.get("endpoint")}],
                        is_trusted=1,
                        compute_group="Active Compute"
                    )
            except Exception:
                pass

            return self._send_json(200, {"success": True, "candidates": candidates})

        if path == "/api/discovery/nodes":
            registry = getattr(srv, "registry", None)
            if not registry:
                from backend.discovery.node_registry import NodeRegistry
                registry = NodeRegistry(database=srv.database)
            status_filter = query.get("status", [None])[0]
            engine_filter = query.get("engine", [None])[0]
            nodes = registry.list_nodes(status=status_filter, engine=engine_filter)
            return self._send_json(200, {"success": True, "nodes": nodes})

        if path == "/api/discovery/telemetry":
            governor = getattr(srv, "governor", None)
            node_id = query.get("node_id", [None])[0]
            stats = governor.get_telemetry(node_id) if governor else {}
            return self._send_json(200, {"success": True, "telemetry": stats})

        # AIUM-705: Client Quotas, Burst Windows & Usage Metrics
        if path == "/api/discovery/clients":
            quotas = srv.database.list_client_quotas()
            enriched = []
            for q in quotas:
                usage = srv.database.get_client_token_usage(q["client_ip"])
                q_copy = dict(q)
                q_copy.update({
                    "session_tokens_used": usage["session_tokens_used"],
                    "session_tokens_remaining": usage["session_tokens_remaining"],
                    "daily_tokens_used": usage["daily_tokens_used"],
                    "daily_tokens_remaining": usage["daily_tokens_remaining"],
                    "is_bypass_active": usage["is_bypass_active"]
                })
                enriched.append(q_copy)
            return self._send_json(200, {"success": True, "clients": enriched})

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
            scope = query.get("scope", [None])[0]
            if not scope:
                scope = srv.database.get_quota_tracking_mode()
            filter_vis = query.get("filter_visibility", ["0"])[0] in ("1", "true")
            comp = srv.database.get_comparative_metrics(scope=scope, filter_visibility=filter_vis)
            return self._send_json(200, comp)

        if path == "/api/usage/trends/hierarchy":
            prov = query.get("provider", ["claude"])[0]
            window = query.get("window", ["24h"])[0]
            scope = query.get("scope", ["individual"])[0]
            try:
                bucket_minutes = int(query.get("bucket_minutes", [None])[0])
            except (ValueError, TypeError):
                bucket_minutes = None
            mode = query.get("mode", ["interval_delta"])[0]
            trends = srv.database.get_hierarchical_trends(
                provider=prov,
                window=window,
                scope=scope,
                bucket_minutes=bucket_minutes,
                mode=mode,
            )
            return self._send_json(200, trends)

        if path == "/api/usage/pivot":
            dims = query.get("dimensions", ["platform"])[0]
            window = query.get("window", ["24h"])[0]
            f_source = query.get("filter_source", [None])[0]
            f_client = query.get("filter_client", [None])[0]
            f_platform = query.get("filter_platform", [None])[0]
            f_instance = query.get("filter_instance", [None])[0]
            f_model = query.get("filter_model", [None])[0]
            f_project = query.get("filter_project", [None])[0]
            pivot_res = srv.database.get_pivot_metrics(
                dimensions=dims,
                window=window,
                filter_source=f_source,
                filter_client=f_client,
                filter_platform=f_platform,
                filter_instance=f_instance,
                filter_model=f_model,
                filter_project=f_project
            )
            return self._send_json(200, pivot_res)

        if path == "/api/usage/timeseries":
            provider = query.get("provider", [None])[0]
            window = query.get("window", ["24h"])[0]
            try:
                bucket_minutes = int(query.get("bucket_minutes", [5])[0])
            except (ValueError, TypeError):
                bucket_minutes = 5
            mode = query.get("mode", ["interval_delta"])[0]
            scope = query.get("scope", ["individual"])[0]
            breakdown = query.get("breakdown", ["consolidated"])[0]
            scope_filter = query.get("scope_filter", ["all"])[0]
            timeseries = srv.database.get_granular_timeseries(
                provider=provider,
                window=window,
                bucket_minutes=bucket_minutes,
                mode=mode,
                scope=scope,
                breakdown=breakdown,
                scope_filter=scope_filter
            )
            return self._send_json(200, timeseries)

        if path == "/api/taxonomy":
            from backend.storage.taxonomy import get_full_taxonomy_specification
            return self._send_json(200, get_full_taxonomy_specification())

        if path == "/api/settings/visibility":
            return self._send_json(200, srv.database.get_estate_visibility())

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

        if path == "/api/accounts":
            prov = query.get("provider", [None])[0]
            accounts = srv.database.get_account_profiles(provider=prov)
            for a in accounts:
                a["has_credentials"] = srv.vault.get_credential(a["provider"], a["account_id"]) is not None
            return self._send_json(200, {"success": True, "accounts": accounts})

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
            try:
                self.wfile.write(payload)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass
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
            source = query.get("source", [None])[0]
            instance_id = query.get("instance_id", [None])[0]
            client_ip = query.get("client_ip", [None])[0]
            sort_by = query.get("sort_by", [None])[0]
            sort_dir = query.get("sort_dir", ["desc"])[0]
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
                    model=model,
                    token_id=token,
                    project_id=proj,
                    dimension=dim,
                    source=source,
                    instance_id=instance_id,
                    client_ip=client_ip,
                )
                payload = csv_data.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="ai_usage_history.csv"')
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    pass
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
                dimension=dim,
                source=source,
                instance_id=instance_id,
                client_ip=client_ip,
                sort_by=sort_by,
                sort_dir=sort_dir,
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

        # Model Benchmarking & Evaluations Endpoints (AIUM-609)
        if path == "/api/benchmarks/results":
            prov = query.get("provider", [None])[0]
            model = query.get("model", [None])[0]
            limit = int(query.get("limit", [50])[0])
            evals = srv.database.get_model_evaluations(provider=prov, model_name=model, limit=limit)
            return self._send_json(200, {"success": True, "evaluations": evals})

        if path == "/api/benchmarks/leaderboard":
            lb = srv.database.get_model_leaderboard()
            return self._send_json(200, {"success": True, "leaderboard": lb})

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

        if path == "/api/providers/gemini/test-probe":
            gemini_prov = srv.providers.get("gemini")
            if not gemini_prov:
                return self._send_json(404, {"error": "Gemini provider not registered"})
            model = body.get("model", "gemini-2.0-flash")
            in_tok = int(body.get("input_tokens", 250))
            out_tok = int(body.get("output_tokens", 85))
            token_id = body.get("token_id", "tok_gem_flash")
            evt_id = gemini_prov.ingest_proxy_interaction(
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                token_id=token_id
            )
            return self._send_json(200, {
                "success": True,
                "event_id": evt_id,
                "token_id": token_id,
                "total_tokens": in_tok + out_tok
            })

        if path == "/api/providers/chatgpt/config":
            api_key = body.get("api_key")
            chatgpt_prov = srv.providers.get("chatgpt")
            if api_key and chatgpt_prov:
                chatgpt_prov.configure_api_key(api_key)
            elif api_key:
                srv.vault.set_credential("chatgpt", "default", api_key)
            return self._send_json(200, {"success": True, "message": "ChatGPT / OpenAI configuration saved"})

        # Multi-Account Profile Management (AIUM-608)
        if path == "/api/accounts":
            prov = body.get("provider", "").lower().strip()
            acct_id = body.get("account_id", "").strip()
            acct_name = body.get("account_name", "").strip() or acct_id
            email = body.get("email")
            plan_type = body.get("plan_type", "Pro")
            is_active = body.get("is_active")
            metadata = body.get("metadata")
            api_key = body.get("api_key")

            if not prov or not acct_id:
                return self._send_json(400, {"error": "Missing required fields: 'provider' and 'account_id'"})

            profile = srv.database.register_account_profile(
                provider=prov,
                account_name=acct_name,
                account_id=acct_id,
                email=email,
                plan_type=plan_type,
                is_active=is_active,
                metadata=metadata
            )

            if api_key:
                srv.vault.set_credential(prov, acct_id, api_key)
                profile["has_credentials"] = True
                if profile.get("is_active"):
                    prov_obj = srv.providers.get(prov)
                    if prov_obj and hasattr(prov_obj, "configure_api_key"):
                        try:
                            prov_obj.configure_api_key(api_key)
                        except Exception:
                            pass

            return self._send_json(200, {"success": True, "account": profile})

        if path == "/api/accounts/active":
            prov = body.get("provider", "").lower().strip()
            acct_id = body.get("account_id", "").strip()
            if not prov or not acct_id:
                return self._send_json(400, {"error": "Missing 'provider' or 'account_id'"})

            success = srv.database.set_active_account_profile(prov, acct_id)
            if success:
                cred = srv.vault.get_credential(prov, acct_id)
                prov_obj = srv.providers.get(prov)
                if cred and prov_obj and hasattr(prov_obj, "configure_api_key"):
                    try:
                        prov_obj.configure_api_key(cred)
                    except Exception:
                        pass
                return self._send_json(200, {"success": True, "message": f"Active profile set to {acct_id}"})
            return self._send_json(404, {"error": f"Account '{acct_id}' not found for provider '{prov}'"})

        if path == "/api/accounts/delete":
            prov = body.get("provider", "").lower().strip()
            acct_id = body.get("account_id", "").strip()
            if not prov or not acct_id:
                return self._send_json(400, {"error": "Missing 'provider' or 'account_id'"})

            deleted = srv.database.delete_account_profile(prov, acct_id)
            if deleted:
                try:
                    srv.vault.delete_credential(prov, acct_id)
                except Exception:
                    pass
                return self._send_json(200, {"success": True, "message": f"Account '{acct_id}' deleted"})
            return self._send_json(404, {"error": f"Account '{acct_id}' not found for provider '{prov}'"})

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
                if "quota_tracking_mode" in settings_dict:
                    val = settings_dict["quota_tracking_mode"]
                    if not isinstance(val, str) or val.strip().lower() not in ("individual", "team"):
                        return self._send_json(400, {"error": "quota_tracking_mode must be 'individual' or 'team'"})

                for k, v in settings_dict.items():
                    if k == "quota_tracking_mode":
                        srv.database.set_quota_tracking_mode(v)
                    elif k == "ui_refresh_interval_seconds":
                        try:
                            srv.database.set_ui_refresh_cadence(int(v))
                        except Exception:
                            srv.database.set_setting(k, v)
                    else:
                        srv.database.set_setting(k, v)
                return self._send_json(200, {"success": True, "settings": srv.database.get_all_settings()})
            return self._send_json(400, {"error": "Settings must be a key-value dictionary"})

        if path == "/api/settings/visibility":
            hidden_platforms = body.get("hidden_platforms")
            hidden_accounts = body.get("hidden_accounts")
            hidden_tags = body.get("hidden_tags")
            updated = srv.database.set_estate_visibility(
                hidden_platforms=hidden_platforms,
                hidden_accounts=hidden_accounts,
                hidden_tags=hidden_tags
            )
            return self._send_json(200, {"success": True, "visibility": updated})

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

        # Model Benchmarking Runner (AIUM-609)
        if path == "/api/benchmarks/run":
            from backend.analytics.benchmark_engine import BenchmarkEngine
            engine = BenchmarkEngine(database=srv.database)
            prov = body.get("provider", "claude")
            model = body.get("model_name", "claude-3-7-sonnet")
            suites = body.get("suites", ["coding", "json_schema", "security", "retrieval"])
            res = engine.run_benchmark_suite(provider=prov, model_name=model, suites=suites)
            return self._send_json(200, {"success": True, "run": res})

        # AIUM-703, AIUM-704: Node Registration, Inventory, Scan, and Query Console
        if path == "/api/discovery/nodes":
            registry = getattr(srv, "registry", None)
            if not registry:
                from backend.discovery.node_registry import NodeRegistry
                registry = NodeRegistry(database=srv.database)
            node = registry.register_node(
                name=body.get("name", "Remote Node"),
                endpoint=body.get("endpoint", ""),
                engine=body.get("engine", "ollama"),
                max_concurrency=body.get("max_concurrency", 1),
                queue_timeout_seconds=body.get("queue_timeout_seconds", 30.0),
                priority=body.get("priority", 5),
                models=body.get("models", []),
                metadata=body.get("metadata", {}),
                node_id=body.get("node_id") or body.get("id"),
                is_trusted=int(body.get("is_trusted", 1)),
                compute_group=body.get("compute_group", "Active Compute")
            )
            return self._send_json(200, {"success": True, "node": node})

        if path == "/api/discovery/inventory":
            alias = body.get("alias") or body.get("ip")
            ip = body.get("ip")
            state = body.get("state", "PENDING")
            services = body.get("discovered_services", [])
            is_trusted = int(body.get("is_trusted", 1))
            compute_group = body.get("compute_group", "Active Compute")
            notes = body.get("notes", "")
            dev = srv.database.upsert_device_inventory(
                alias=alias,
                ip=ip,
                state=state,
                discovered_services=services,
                is_trusted=is_trusted,
                compute_group=compute_group,
                notes=notes
            )
            return self._send_json(200, {"success": True, "device": dev})

        if path == "/api/discovery/scan":
            spec = body.get("range") or body.get("targets") or body.get("subnet")
            platforms_list = body.get("platforms")
            sec_ports_list = body.get("secondary_ports")
            timeout_val = float(body.get("timeout", 0.4))

            scanner = getattr(srv, "scanner", None)
            if not scanner:
                from backend.discovery.lan_scanner import LANScanner
                scanner = LANScanner()

            if spec:
                ips = scanner.parse_target_spec(spec)
            else:
                _, detected_sub = scanner.get_local_subnet_info()
                ips = scanner.parse_target_spec(detected_sub)

            if "127.0.0.1" not in ips:
                ips.append("127.0.0.1")

            target_pairs = scanner.build_scan_targets(
                ips=ips,
                platforms=platforms_list,
                secondary_ports=sec_ports_list
            )
            candidates = scanner.scan_targets(target_pairs, timeout=timeout_val)

            try:
                for c in candidates:
                    alias = c.get("alias") or c.get("ip")
                    srv.database.upsert_device_inventory(
                        alias=alias,
                        ip=c.get("ip"),
                        state="KNOWN_SERVICES",
                        discovered_services=[{"engine": c.get("engine"), "port": c.get("port"), "models": c.get("models", []), "endpoint": c.get("endpoint")}],
                        is_trusted=1,
                        compute_group="Active Compute"
                    )
            except Exception:
                pass

            return self._send_json(200, {"success": True, "candidates": candidates})

        # AIUM-705 & AIUM-707: Client Quota Configuration, Blocking & Elevated Bypass
        if path == "/api/discovery/clients":
            client_ip = body.get("client_ip") or self._get_client_ip()
            if not client_ip:
                return self._send_json(400, {"error": "Missing client_ip in payload"})

            action = body.get("action")
            is_blocked = int(body.get("is_blocked", 0))
            is_unrestricted = int(body.get("is_unrestricted", 0))
            if action == "block":
                is_blocked = 1
            elif action == "unblock":
                is_blocked = 0
            elif action == "unrestrict":
                is_unrestricted = 1
            elif action == "restrict":
                is_unrestricted = 0

            existing = srv.database.get_client_quota(client_ip)
            alias = body.get("alias") if "alias" in body else existing.get("alias")
            win_mins = int(body.get("session_window_minutes", existing.get("session_window_minutes", 15)))
            sess_limit = int(body.get("session_token_limit", existing.get("session_token_limit", 25000)))
            daily_limit = int(body.get("daily_token_limit", existing.get("daily_token_limit", 250000)))
            priority = int(body.get("priority", existing.get("priority", 5)))
            notes = body.get("notes") if "notes" in body else existing.get("notes", "")

            client = srv.database.upsert_client_quota(
                client_ip=client_ip,
                alias=alias,
                session_window_minutes=win_mins,
                session_token_limit=sess_limit,
                daily_token_limit=daily_limit,
                priority=priority,
                is_unrestricted=is_unrestricted,
                is_blocked=is_blocked,
                bypass_until=body.get("bypass_until", existing.get("bypass_until")),
                scheduled_start_at=body.get("scheduled_start_at", existing.get("scheduled_start_at")),
                scheduled_end_at=body.get("scheduled_end_at", existing.get("scheduled_end_at")),
                allowed_models=body.get("allowed_models", existing.get("allowed_models", [])),
                blocked_models=body.get("blocked_models", existing.get("blocked_models", [])),
                allowed_nodes=body.get("allowed_nodes", existing.get("allowed_nodes", [])),
                blocked_nodes=body.get("blocked_nodes", existing.get("blocked_nodes", [])),
                notes=notes
            )
            return self._send_json(200, {"success": True, "client": client})

        if path == "/api/discovery/clients/bypass":
            client_ip = body.get("client_ip") or self._get_client_ip()
            if not client_ip:
                return self._send_json(400, {"error": "Missing client_ip in payload"})
            duration_mins = float(body.get("duration_minutes", 60))
            if duration_mins <= 0:
                srv.database.clear_client_bypass(client_ip)
                client = srv.database.get_client_quota(client_ip)
            else:
                client = srv.database.set_client_temporary_bypass(client_ip, duration_mins)
            return self._send_json(200, {"success": True, "client": client})

        if path in ["/api/discovery/query", "/api/query/console"]:
            governor = getattr(srv, "governor", None)
            if not governor:
                return self._send_json(500, {"error": "Traffic governor not initialized"})
            target = body.get("target", "pool")
            prompt = body.get("prompt", "")
            files = body.get("files", [])
            model = body.get("model", "default")
            timeout_val = body.get("timeout")
            client_ip = body.get("client_ip") or self._get_client_ip()

            res = governor.forward_query_with_context(
                target=target,
                prompt=prompt,
                files=files,
                model=model,
                timeout=timeout_val,
                client_ip=client_ip
            )
            if res.get("status_code") == 429 or ("Quota Exceeded" in res.get("error", "")):
                status_code = 429
            else:
                status_code = 200 if res.get("success") else (res.get("status_code") or 400)
            return self._send_json(status_code, res)

        if path in ["/api/discovery/proxy/completion", "/api/proxy/remote/completion"]:
            governor = getattr(srv, "governor", None)
            if not governor:
                return self._send_json(500, {"error": "Traffic governor not initialized"})
            node_id = body.get("node_id")
            model = body.get("model", "default")
            prompt = body.get("prompt", "")
            stream = body.get("stream", False)
            extra = body.get("extra_payload")
            timeout_param = body.get("timeout")
            client_ip = body.get("client_ip") or self._get_client_ip()

            res = governor.forward_completion(
                node_id=node_id,
                model=model,
                prompt=prompt,
                stream=stream,
                extra_payload=extra,
                timeout=timeout_param,
                client_ip=client_ip
            )
            if res.get("status_code") == 429 or ("Quota Exceeded" in res.get("error", "")):
                status_code = 429
            else:
                status_code = 200 if res.get("success") else (res.get("status_code") or 400)
            return self._send_json(status_code, res)

        if path == "/api/mcp/rpc":
            mcp = getattr(srv, "mcp_server", None)
            if not mcp:
                return self._send_json(500, {"error": "MCP server not initialized"})
            resp = mcp.handle_json_rpc(body)
            if resp is None:
                self.send_response(204)
                self.end_headers()
                return
            return self._send_json(200, resp)

        # AIUM-901: Windows Auto-Start Registration & Background Service Control
        if path == "/api/system/startup":
            svc_mgr = getattr(srv, "service_manager", None)
            if not svc_mgr:
                from backend.system.windows_service import WindowsServiceManager
                svc_mgr = WindowsServiceManager()

            action = str(body.get("action", "")).strip().lower()
            if action == "toggle":
                res = svc_mgr.toggle_startup(launch_widget=body.get("launch_widget"))
                return self._send_json(200, res)

            enabled = bool(body.get("enabled", True))
            method = str(body.get("method", "registry")).strip().lower()
            launch_widget = bool(body.get("launch_widget", False))
            auto_restart = body.get("auto_restart_on_crash")
            if auto_restart is not None:
                svc_mgr.save_config({"auto_restart_on_crash": bool(auto_restart)})

            if enabled:
                res = svc_mgr.install_startup(method=method, launch_widget=launch_widget)
            else:
                res = svc_mgr.uninstall_startup(method=body.get("method", "all"))
            return self._send_json(200, res)

        if path == "/api/system/service":
            svc_mgr = getattr(srv, "service_manager", None)
            if not svc_mgr:
                from backend.system.windows_service import WindowsServiceManager
                svc_mgr = WindowsServiceManager()

            action = str(body.get("action", "status")).strip().lower()
            if action == "status":
                return self._send_json(200, svc_mgr.get_service_status(include_logs=True))
            elif action == "clear_logs":
                return self._send_json(200, svc_mgr.clear_service_logs())
            elif action == "restart":
                deferred = bool(body.get("deferred", True))
                res = svc_mgr.restart_background_service(
                    launch_widget=body.get("launch_widget"),
                    deferred=deferred
                )
                return self._send_json(200, res)
            elif action == "stop":
                res = svc_mgr.stop_background_service()
                return self._send_json(200, res)
            elif action == "start":
                res = svc_mgr.start_background_service(
                    launch_widget=bool(body.get("launch_widget", False)),
                    host=srv.host,
                    port=srv.server_port,
                    proxy_port=srv.proxy_port
                )
                return self._send_json(200, res)
            return self._send_json(400, {"error": f"Unsupported service action: {action}"})

        self._send_json(404, {"error": "API route not found"})

    def _handle_api_delete(self, path: str, query: Dict[str, Any]):
        srv = self.server
        if path == "/api/discovery/nodes":
            node_id = query.get("id", [None])[0] or query.get("node_id", [None])[0]
            if not node_id:
                return self._send_json(400, {"error": "Missing node id parameter"})
            registry = getattr(srv, "registry", None)
            if registry:
                deleted = registry.delete_node(node_id)
                return self._send_json(200, {"success": deleted})
            return self._send_json(500, {"error": "Registry not initialized"})

        if path == "/api/discovery/inventory":
            alias = query.get("alias", [None])[0] or query.get("id", [None])[0] or query.get("ip", [None])[0]
            if not alias:
                return self._send_json(400, {"error": "Missing alias or ip parameter"})
            deleted = srv.database.delete_device_inventory(alias)
            return self._send_json(200, {"success": deleted})

        # AIUM-705: Client Quota Deletion & Token Reset
        if path == "/api/discovery/clients":
            client_ip = query.get("client_ip", [None])[0] or query.get("ip", [None])[0]
            if not client_ip:
                return self._send_json(400, {"error": "Missing client_ip parameter"})
            action = query.get("action", ["delete"])[0]
            if action == "reset":
                reset_done = srv.database.reset_client_tokens(client_ip)
                return self._send_json(200, {"success": reset_done})
            else:
                deleted = srv.database.delete_client_quota(client_ip)
                return self._send_json(200, {"success": deleted})

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
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except Exception as e:
            try:
                self.send_error(500, f"Error reading file: {e}")
            except Exception:
                pass

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
        google_auth_mgr: Optional[Any] = None,
        scanner: Optional[Any] = None,
        registry: Optional[Any] = None,
        governor: Optional[Any] = None,
        mcp_server: Optional[Any] = None,
        service_manager: Optional[Any] = None
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

        from backend.discovery.lan_scanner import LANScanner
        from backend.discovery.node_registry import NodeRegistry
        from backend.discovery.traffic_governor import TrafficGovernor
        from backend.mcp.server import MCPServer
        from backend.system.windows_service import WindowsServiceManager

        self.scanner = scanner or LANScanner()
        self.registry = registry or NodeRegistry(database=self.database)
        self.governor = governor or TrafficGovernor(registry=self.registry, database=self.database)
        self.mcp_server = mcp_server or MCPServer(scanner=self.scanner, registry=self.registry, governor=self.governor, database=self.database)
        self.service_manager = service_manager or WindowsServiceManager()

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
        self._server.scanner = self.scanner
        self._server.registry = self.registry
        self._server.governor = self.governor
        self._server.mcp_server = self.mcp_server
        self._server.service_manager = self.service_manager
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
