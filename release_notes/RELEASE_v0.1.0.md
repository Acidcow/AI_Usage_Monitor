# Release Notes - Version v0.1.0
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