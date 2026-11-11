# AI Usage Monitor - Release Notes v0.9.5

**Release Identifier**: `v0.9.5`  
**Release Date**: 2026-10-22  
**Epic**: `EPIC-PLATFORM-OVERHAUL`  
**Ticket**: `AIUM-905`  
**Ways of Work Version**: v1.0.0  

---

## Executive Summary

AI Usage Monitor `v0.9.5` delivers a major frontend layout overhaul, system local timezone alignment across all timeseries curves, automatic ingestion of Claude Desktop application session telemetry from Windows IndexedDB storage, and direct zero-configuration live synchronization of Claude Pro personal quotas directly from Anthropic's OAuth API.

Manual Claude calibration buttons, dialogs, and manual percentage adjustments have been completely retired. Telemetry, session limits, weekly balances, and rolling resets are now discovered, decrypted, and tracked continuously with 100% autonomy.

---

## Key Capabilities & Changes

### 1. Fluid Full-Width Web UI Layout
- **Elimination of 1300px Max-Width Ceiling**: Replaced rigid `max-width: 1300px` on `main.container` and `header.app-header` with fluid `width: 100%; max-width: 100%; padding: 0 clamp(16px, 2.5vw, 40px);`.
- **Wide & Ultrawide Display Optimization**: "Historical Usage Reports & Cost Attribution" and "Recent Agentic Sessions & Tokens" now utilize 100% of usable horizontal screen space, eliminating horizontal scrollbars across dense multi-column grids.

### 2. Workstation Local Timezone Alignment
- **End-of-Chart Time Alignment**: Corrected granular timeseries bucket labeling in [`backend/storage/database.py`](file:///c:/AgenticDev/AI_Usage_Monitor/backend/storage/database.py) (`get_granular_timeseries` and `get_hierarchical_trends`) to format time bucket labels using `t_bin.astimezone()`.
- **Resolved UTC vs. Local Offset Mismatch**: Curves now terminate at the user's current workstation time (e.g. 16:04 SAST / UTC+2) rather than lagging behind at UTC 12:00.

### 3. Claude Desktop App Telemetry Ingestion (IndexedDB Engine)
- **Zero-Dependency Snappy Decompression**: Implemented a pure-Python Snappy frame decompressor supporting Chromium/Blink frame headers (`\xff\x11\x02`), literal tags, and 1/2/4-byte copy offsets without external C-libraries or pip dependencies.
- **V8 ZigZag Varint Extraction**: Decodes turn IDs (`msg_01...`), models (`claude-opus-5-5`, `claude-3-7-sonnet`, etc.), input tokens, output tokens, and cache tokens directly from `%LOCALAPPDATA%\Claude-Data\claude_pzs8sxrjxfjjc\IndexedDB`.
- **Message Deduplication & Real Usage**: Seamlessly ingests desktop turns with `source="desktop_app"`, surfacing them in the live dashboard, timeseries curves, and session timeline.

### 4. Direct Anthropic OAuth Telemetry & Pro Quota Sync
- **Native Windows DPAPI Decryption**: Decrypts user session credentials using Windows native `crypt32.dll` and `bcrypt.dll` via `ctypes`.
- **Authoritative OAuth Endpoints**: Automatically interrogates `https://api.anthropic.com/api/oauth/usage` and `/profile` using the bearer token, dynamically extracting 5-hour rolling session reset epochs, 7-day weekly balances, user full name, and plan tier (`Claude Pro`).
- **Resilient Fallback**: Falls back to `plan-usage-history.json` when disconnected or offline.

### 5. Retirement of Manual "Calibrate Claude" UI
- **Zero-Configuration Operation**: Completely removed `#claude-quota-modal`, calibration buttons, and client-side modal handlers from `usage_gauge_card.html`, `provider_hub.html`, `settings_panel.html`, `index.html`, and `app.js`.
- **Automated Integrity Notice**: Updated settings panel to reflect live continuous sync with zero manual calibration required.

---

## Verification & Test Results

- **Ticket Unit Test Suite**: `tests/test_fullwidth_layout_localtime_claude_desktop_ingestion.py` (20 tests passed, 100%).
- **Full Platform Regression Suite**: 42/42 tests passing across Claude Scanner, Unified Taxonomy, and Local Timezone/Full-Width suites; 403+ unit tests overall.
- **Live Daemon Status**: Running under Windows background daemon (`PID 16080`) serving on ports `8765` (Web UI/API), `8766` (Transparent Proxy), and `8989` (Ollama Bridge).
