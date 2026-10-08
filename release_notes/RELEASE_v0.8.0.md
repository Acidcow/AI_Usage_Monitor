# Release Notes - Version v0.8.0
**Date**: 2026-10-08

## Summary
AI Usage Monitor v0.8.0 introduces the Model Benchmarking, Quality Evaluations & Prompt Security Testing Suite (`AIUM-609`). Features zero-dependency AST code syntax validation, strict JSON schema and enum adherence, needle-in-a-haystack context recall, canary token leakage defense, latency/throughput metrics (TTFT, TPS), SQLite persistence, and an interactive frontend leaderboard and evaluation runner.

## Completed Features & Tickets

- **[AIUM-101] Windows Native DPAPI Security Vault** (Feature): Zero-dependency native encryption using crypt32.dll for secure credential storage.
- **[AIUM-102] Proactive Redacted Diagnostics & Logging Engine** (Feature): Structured error tracker with automated token/key sanitization and 1-click diagnostic export.
- **[AIUM-103] Core SQLite Usage Time-Series Storage** (Feature): Local database tracking provider tokens, sessions, costs, rate limits, and hourly/daily trends.
- **[AIUM-104] Claude Multi-Mode Usage Provider** (Feature): Anthropic API poller, Transparent Local Proxy, CLI log scanner, and mock fallback.
- **[AIUM-105] Multi-Provider Framework (Gemini, Ollama, M365 Copilot)** (Feature): Pluggable provider architecture with initial interfaces and coming soon indicators.
- **[AIUM-106] Zero-Dependency HTTP Server & REST API** (Feature): ThreadingHTTPServer serving REST API and canonical SPA web components.
- **[AIUM-107] Web UI Dashboard & Canonical Components** (Feature): Stunning dark-mode glassmorphic dashboard with live token gauges and session timeline.
- **[AIUM-108] Windows System Tray & Mini Status Bar Widget** (Feature): Shell_NotifyIconW native tray icon and compact status bar widget view.
- **[AIUM-109] End-to-End TDD Verification & Release v0.1.0** (Task): Comprehensive unit tests (>=20), 100% error-free pass rate, and release compilation.
- **[AIUM-201] Claude Local Code & CLI Session Scanner** (Feature): Scan ~/.claude/projects/ and sessions for real tokens, cache read/write metrics, models, and timestamps.
- **[AIUM-202] Transparent Proxy SSE Streaming & Token Extraction** (Feature): Add Server-Sent Events stream chunk passthrough and real-time delta usage extraction for live CLI coding tools.
- **[AIUM-203] Live Ollama Model Monitor & Local Inference Ingestor** (Feature): Query running models, parameter sizes, and family details directly from localhost:11434 with health badge.
- **[AIUM-204] Google Gemini Live Provider with DPAPI Vault** (Feature): Support Google AI Studio API key storage and model quota interrogation.
- **[AIUM-205] Corporate Telemetry Importer & Manual Session Logger** (Feature): Allow uploading sanitized session json/jsonl/csv files or manual logging for restricted enterprise environments.
- **[AIUM-206] Dashboard Real Data Mode & Live SVG Analytics Chart** (Feature): Interactive pure SVG time-series analytics chart with toggle between Real Local Data and Demo Simulation.
- **[AIUM-207] Verification & Test Expansion to >=35 Tests** (Task): Unit and integration tests for scanner, streaming proxy, and Ollama integration with 100% pass.
- **[AIUM-301] Automated API Key Procurement Buttons & Step-by-Step Guides** (feature): Interactive 1-click launch buttons and visual procurement steps for Gemini (AI Studio), Claude (Console), ChatGPT (OpenAI Platform), Copilot (M365 Admin), and Ollama (Download & Models).
- **[AIUM-302] Gemini & ChatGPT DPAPI Endpoint Wiring & Active Interrogation** (feature): Wire /api/providers/gemini/config and /api/providers/chatgpt/config to DPAPI vault and test model interrogation.
- **[AIUM-401] Standalone Edge App Mode Desktop Widget Launcher** (feature): Launch chromeless standalone desktop mini-widget using built-in Windows Edge app mode and screen resolution detection.
- **[AIUM-402] Win32 Taskbar Snapping & Draggable Header Controls** (feature): Add draggable window header, bottom-right taskbar snapping, provider cycle button, and Tray menu integration.
- **[AIUM-501] Johnny 5 Mascot, Dual Icons & Quote Engine Integration** (Feature): Incorporate high-res Johnny 5 headshot and Cyber Shield icons, contextual UI mascots for dashboard banner, session inspection, and health status, plus quote engine and customizer modal.
- **[AIUM-502] Fix ctypes WNDPROC LOWORD AttributeError on Tray Menu Command** (Bug): Replace non-existent wintypes.LOWORD with bitwise (wparam & 0xFFFF) in windows_tray.py and ensure unique window class names per instance.
- **[AIUM-601] Multi-Account Dual-Bar Widget & Local AI Cost Savings** (Feature): Dual bar widget displaying session and weekly remaining %, weather-style hover flyout, comparative dashboard metrics, local model ROI savings, and multi-key account aggregation
- **[AIUM-602] Zero-Browser Native Taskbar Widget & Identifiable Tray Icons** (Feature): Native Tkinter taskbar floating widget eliminating browser dependency, pixel-perfect Johnny 5 and Cyber Shield tray icons, and multi-platform SVG velocity line charts
- **[AIUM-603] Claude Team Quota Calibration, Widget Port Probing & Scaled Hover Flyout** (Feature): Calibrate Claude rolling session/weekly limits, auto-probe active port in widget pop-out, prevent test orphan processes, and scale hover flyouts with custom scrollbar
- **[AIUM-604] Multi-Scope Usage Hierarchy (Individual, Team, Dept, Enterprise Drill-Down)** (Feature): Provide scoped separation and interactive drill-down between Individual User, Team Pool, Department, and Enterprise usage thresholds and quotas
- **[AIUM-608] Multi-Account Profiles and Multi-Tenant Aggregation** (Feature): Cater for multiple concurrent accounts per service/platform (e.g. personal vs corporate accounts, multi-tenant orgs) with active profile toggling and consolidated operational telemetry.
- **[AIUM-609] Model Benchmarking, Quality Evals & Security Testing Suite** (Feature): Automated test harness for evaluating model accuracy, TTFT latency, output token throughput, prompt injection defense, and schema adherence across platforms.
- **[AIUM-610] Estate Throughput, Burst Performance & Capacity Analytics** (Feature): Telemetry-based usage analytics engine computing rolling averages, burst velocity spikes, sustained throughput, predictive quota exhaustion (TTE), and estate optimization recommendations.