# Release Notes - Version v0.2.0
**Date**: 2026-10-05

## Summary
Initial release of AI Usage Monitor featuring zero-dependency Python backend, Windows DPAPI encryption, native Windows Tray, modern web dashboard, and Claude multi-mode usage tracking.

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