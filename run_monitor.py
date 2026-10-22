#!/usr/bin/env python3
"""
AI Usage Monitor - Unified Service Entrypoint
Runs zero-dependency HTTP server, transparent proxy, and native Windows tray icon.
"""

import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import json
import argparse
import webbrowser
import threading
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.config import DEFAULT_HOST, DEFAULT_PORT, PROXY_PORT, DEFAULT_OLLAMA_PORT
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.storage.database import UsageDatabase
from backend.system.windows_service import WindowsServiceManager, setup_daemon_logging
from backend.providers import (
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
    CopilotProvider,
    ChatGPTProvider
)
from backend.proxy.transparent_proxy import TransparentProxyServer
from backend.server.http_server import AppHTTPServer
from backend.tray.windows_tray import WindowsTrayManager
from backend.tray.desktop_widget import launch_desktop_widget

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="AI Usage Monitor Service")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind HTTP server to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port for web dashboard and API")
    parser.add_argument("--proxy-port", type=int, default=PROXY_PORT, help="Port for transparent Claude proxy")
    parser.add_argument("--ollama-port", type=int, default=DEFAULT_OLLAMA_PORT, help="Port for secondary Ollama emulator and worker node RPC bridge")
    parser.add_argument("--no-tray", action="store_true", help="Disable native Windows system tray icon")
    parser.add_argument("--open-browser", action="store_true", help="Open web dashboard in default browser on launch")
    parser.add_argument("--widget", action="store_true", help="Launch standalone floating desktop widget on launch")
    parser.add_argument("--demo", action="store_true", help="Pre-seed realistic initial Claude usage data")

    # Windows Auto-Start & Background Service Lifecycle Flags (AIUM-901)
    parser.add_argument("--daemon", action="store_true", help="Run as a supervised background daemon with rotating log output")
    parser.add_argument("--install-startup", action="store_true", help="Register AI Usage Monitor to start automatically with Windows")
    parser.add_argument("--uninstall-startup", action="store_true", help="Remove AI Usage Monitor from Windows automatic startup")
    parser.add_argument("--startup-method", default="registry", choices=["registry", "task_scheduler", "both"], help="Windows startup registration method")
    parser.add_argument("--service-status", action="store_true", help="Display current background service and Windows startup status")
    parser.add_argument("--service-start", action="store_true", help="Start AI Usage Monitor in the background (windowless daemon)")
    parser.add_argument("--service-stop", action="store_true", help="Stop the running AI Usage Monitor background service")
    parser.add_argument("--service-restart", action="store_true", help="Restart the AI Usage Monitor background service")
    return parser.parse_args(argv)

def run_service_runtime(args, service_manager: WindowsServiceManager):
    print("\n" + "=" * 65)
    print("⚡ AI USAGE MONITOR - INITIALIZING")
    print("=" * 65)
    print(f"[INIT] Host: {args.host}")
    print(f"[INIT] Web Dashboard: http://{args.host}:{args.port}")
    print(f"[INIT] Transparent Proxy: http://{args.host}:{args.proxy_port}/v1")
    print(f"[INIT] Ollama API Emulator: http://{args.host}:{args.ollama_port}")
    print(f"[INIT] Platform: {sys.platform} (Native Windows DPAPI: Active)")

    # 1. Initialize Core Subsystems
    vault = DPAPIVault()
    diagnostics = DiagnosticsEngine()
    database = UsageDatabase()

    # Dynamic bridge ports from saved database settings
    saved_ollama_port = database.get_setting("ollama_emulator_port")
    if saved_ollama_port and args.ollama_port == DEFAULT_OLLAMA_PORT:
        try:
            args.ollama_port = int(saved_ollama_port)
        except Exception:
            pass

    saved_proxy_port = database.get_setting("transparent_proxy_port")
    if saved_proxy_port and args.proxy_port == PROXY_PORT:
        try:
            args.proxy_port = int(saved_proxy_port)
        except Exception:
            pass

    # Record active runtime PID lock
    service_manager.acquire_pid_lock(
        pid=os.getpid(),
        mode="daemon" if args.daemon else "interactive",
        host=args.host,
        port=args.port,
        proxy_port=args.proxy_port,
        ollama_port=args.ollama_port,
    )

    # 2. Initialize Providers
    claude = ClaudeProvider(database=database, vault=vault, diagnostics=diagnostics)
    gemini = GeminiProvider(database=database, vault=vault, diagnostics=diagnostics)
    ollama = OllamaProvider(database=database, vault=vault, diagnostics=diagnostics)
    copilot = CopilotProvider(database=database, vault=vault, diagnostics=diagnostics)
    chatgpt = ChatGPTProvider(database=database, vault=vault, diagnostics=diagnostics)

    providers = {
        "claude": claude,
        "gemini": gemini,
        "ollama": ollama,
        "copilot": copilot,
        "chatgpt": chatgpt
    }

    # Demo pre-seed (only populate synthetic quota percentages & simulated calls when --demo is passed)
    if args.demo:
        existing_snaps = database.get_provider_snapshots()
        if "claude" not in existing_snaps or existing_snaps["claude"].get("individual_session_rem_pct") is None:
            claude.calibrate_limits(
                scope="individual",
                individual_session_used_pct=60.0,
                individual_weekly_used_pct=27.0,
                team_session_used_pct=56.0,
                team_weekly_used_pct=26.0,
                session_reset_seconds=7560,
                weekly_reset_str="Mon 3:00 AM",
                plan_type="Team Enterprise",
                user_name=os.environ.get("USERNAME", "James Eckhardt"),
                team_name="Synthesis Engineering Core",
                org_name="Synthesis Software Technologies"
            )
        print("[DEMO] Generating initial realistic Claude usage telemetry...")
        claude.enable_simulation_mode(True)
        for _ in range(4):
            claude.sync_usage()
        claude.enable_simulation_mode(False)

    # 3. Start Transparent Proxy Server
    proxy = TransparentProxyServer(
        claude_provider=claude,
        gemini_provider=gemini,
        host=args.host,
        port=args.proxy_port
    )
    proxy.start()
    print(f"[OK] Transparent Proxy listening on port {proxy.server_port}")

    # 4. Start HTTP Application & API Server
    server = AppHTTPServer(
        database=database,
        vault=vault,
        diagnostics=diagnostics,
        providers=providers,
        host=args.host,
        port=args.port,
        proxy_port=proxy.server_port,
        service_manager=service_manager
    )
    server.start()
    print(f"[OK] Web Dashboard running on http://{args.host}:{server.server_port}")
    print(f"[OK] LAN Service Discovery & Node Governor: Ready")
    print(f"[OK] Model Context Protocol (MCP) Bridge: http://{args.host}:{server.server_port}/api/mcp/rpc")

    # 4b. Start Secondary Ollama API Emulator & Worker Node Bridge Server
    from backend.server.ollama_emulator import OllamaEmulatorServer
    ollama_emulator = OllamaEmulatorServer(
        host=args.host,
        port=args.ollama_port,
        governor=server.governor,
        registry=server.registry,
        database=database,
        mcp_server=server.mcp_server
    )
    ollama_emulator.start()
    print(f"[OK] Ollama API Emulator & Worker Node Bridge: http://{args.host}:{ollama_emulator.server_port}")

    # Update PID state with actual bound ports
    service_manager.update_heartbeat(
        port=server.server_port,
        proxy_port=proxy.server_port,
        ollama_port=ollama_emulator.server_port,
    )

    # 5. Initialize Windows Tray Manager
    tray = None
    if not args.no_tray and sys.platform == "win32":
        dashboard_url = f"http://{args.host}:{server.server_port}"

        def open_dash():
            webbrowser.open(dashboard_url)

        def open_wid():
            try:
                print(f"[WIDGET] Launching mini desktop widget for http://{args.host}:{server.server_port}...")
                res = launch_desktop_widget(host=args.host, port=server.server_port)
                print(f"[WIDGET] Launch result: {res}")
            except Exception as e:
                print(f"[WIDGET ERROR] Exception launching widget: {e}, opening browser...")
                webbrowser.open(f"http://{args.host}:{server.server_port}/mini_widget.html")

        def open_settings():
            print(f"[SETTINGS] Opening Settings panel...")
            webbrowser.open(f"http://{args.host}:{server.server_port}/?tab=settings")

        def sync_all():
            print("[SYNC] Triggering provider sync...")
            claude.sync_usage()
            ollama.sync_usage()

        def toggle_win_startup():
            res = service_manager.toggle_startup(launch_widget=args.widget)
            state_label = "ENABLED" if res.get("enabled") else "DISABLED"
            print(f"[STARTUP] Windows Auto-Start {state_label}")

        def exit_from_tray():
            service_manager.request_graceful_stop()
            service_manager.release_pid_lock(pid=os.getpid())
            os._exit(0)

        tray = WindowsTrayManager(
            app_name="AI Usage Monitor",
            on_open_dashboard=open_dash,
            on_open_widget=open_wid,
            on_sync_now=sync_all,
            on_open_settings=open_settings,
            on_toggle_startup=toggle_win_startup,
            is_startup_enabled=service_manager.is_startup_enabled,
            on_exit=exit_from_tray
        )
        tray.start()
        print("[OK] Native Windows System Tray icon active.")

    if args.open_browser:
        webbrowser.open(f"http://{args.host}:{server.server_port}")

    if args.widget:
        print("[INIT] Spawning standalone desktop floating widget...")
        launch_desktop_widget(host=args.host, port=server.server_port)

    # 6. Periodic Background Refresh & Tooltip Update Loop
    running = True
    def background_poller():
        while running:
            try:
                service_manager.update_heartbeat()
                # Continuously scan and ingest local model usage (Ollama & Claude)
                try:
                    ollama.sync_usage()
                except Exception:
                    pass
                try:
                    claude.sync_usage()
                except Exception:
                    pass

                summary = database.get_usage_summary(provider="claude")
                total_today = summary.get("total_tokens_today", 0)
                snapshots = database.get_provider_snapshots()
                claude_snap = snapshots.get("claude", {})
                rem_tok = claude_snap.get("tokens_remaining", "--")

                if tray:
                    tray.update_tooltip(
                        f"AI Usage Monitor\nClaude Today: {total_today:,} tok\nQuota Rem: {rem_tok}"
                    )
            except Exception:
                pass
            time.sleep(10)

    poller_thread = threading.Thread(target=background_poller, daemon=True)
    poller_thread.start()

    print("\n[READY] System operational. Press Ctrl+C to terminate.")
    print("=" * 65 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Stopping AI Usage Monitor...")
        running = False
        service_manager.request_graceful_stop()
        if tray:
            tray.stop()
        if ollama_emulator:
            ollama_emulator.stop()
        server.stop()
        proxy.stop()
        service_manager.release_pid_lock(pid=os.getpid())
        print("[SHUTDOWN] Finished cleanly.")

def main(argv=None):
    args = parse_args(argv)
    service_manager = WindowsServiceManager()

    # Handle CLI Service & Startup Management Commands
    if args.install_startup:
        res = service_manager.install_startup(
            method=args.startup_method,
            launch_widget=args.widget,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if args.uninstall_startup:
        res = service_manager.uninstall_startup()
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if args.service_status:
        res = service_manager.get_service_status(include_logs=True)
        print(json.dumps(res, indent=2))
        return 0

    if args.service_stop:
        res = service_manager.stop_background_service()
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if args.service_start:
        res = service_manager.start_background_service(
            launch_widget=args.widget,
            host=args.host,
            port=args.port,
            proxy_port=args.proxy_port,
            ollama_port=args.ollama_port,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if args.service_restart:
        res = service_manager.restart_background_service(
            launch_widget=args.widget if args.widget else None,
            deferred=False,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if args.daemon:
        return service_manager.run_supervised_daemon(
            worker_callable=lambda: run_service_runtime(args, service_manager),
            host=args.host,
            port=args.port,
            proxy_port=args.proxy_port,
            ollama_port=args.ollama_port,
        )

    # If launched directly via pythonw.exe without a console, ensure stdout/stderr are safe
    if sys.stdout is None or sys.stderr is None:
        setup_daemon_logging(service_manager.log_file)

    run_service_runtime(args, service_manager)
    return 0

if __name__ == "__main__":
    sys.exit(main())
