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
import argparse
import webbrowser
import threading
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.config import DEFAULT_HOST, DEFAULT_PORT, PROXY_PORT
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.storage.database import UsageDatabase
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

def parse_args():
    parser = argparse.ArgumentParser(description="AI Usage Monitor Service")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind HTTP server to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port for web dashboard and API")
    parser.add_argument("--proxy-port", type=int, default=PROXY_PORT, help="Port for transparent Claude proxy")
    parser.add_argument("--no-tray", action="store_true", help="Disable native Windows system tray icon")
    parser.add_argument("--open-browser", action="store_true", help="Open web dashboard in default browser on launch")
    parser.add_argument("--widget", action="store_true", help="Launch standalone floating desktop widget on launch")
    parser.add_argument("--demo", action="store_true", help="Pre-seed realistic initial Claude usage data")
    return parser.parse_args()

def main():
    args = parse_args()

    print("\n" + "=" * 65)
    print("⚡ AI USAGE MONITOR - INITIALIZING")
    print("=" * 65)
    print(f"[INIT] Host: {args.host}")
    print(f"[INIT] Web Dashboard: http://{args.host}:{args.port}")
    print(f"[INIT] Transparent Proxy: http://{args.host}:{args.proxy_port}/v1")
    print(f"[INIT] Platform: {sys.platform} (Native Windows DPAPI: Active)")

    # 1. Initialize Core Subsystems
    vault = DPAPIVault()
    diagnostics = DiagnosticsEngine()
    database = UsageDatabase()

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

    # Demo pre-seed
    if args.demo:
        print("[DEMO] Generating initial realistic Claude usage telemetry...")
        claude.enable_simulation_mode(True)
        for _ in range(4):
            claude.sync_usage()

    # 3. Start Transparent Proxy Server
    proxy = TransparentProxyServer(
        claude_provider=claude,
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
        proxy_port=proxy.server_port
    )
    server.start()
    print(f"[OK] Web Dashboard running on http://{args.host}:{server.server_port}")

    # 5. Initialize Windows Tray Manager
    tray = None
    if not args.no_tray and sys.platform == "win32":
        dashboard_url = f"http://{args.host}:{server.server_port}"

        def open_dash():
            webbrowser.open(dashboard_url)

        def open_wid():
            launch_desktop_widget(host=args.host, port=server.server_port)

        def sync_all():
            print("[SYNC] Triggering provider sync...")
            claude.sync_usage()
            ollama.sync_usage()

        tray = WindowsTrayManager(
            app_name="AI Usage Monitor",
            on_open_dashboard=open_dash,
            on_open_widget=open_wid,
            on_sync_now=sync_all,
            on_exit=lambda: os._exit(0)
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
        if tray:
            tray.stop()
        server.stop()
        proxy.stop()
        print("[SHUTDOWN] Finished cleanly.")

if __name__ == "__main__":
    main()
