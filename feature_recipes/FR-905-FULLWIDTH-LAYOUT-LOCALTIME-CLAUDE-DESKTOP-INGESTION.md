# Feature Recipe: FR-905 Full-Width Web UI Layout, Local Timezone Alignment & Claude Desktop Live Telemetry Ingestion

## 1. Specification (ASD-STE100 Simplified Technical English)
- **Ticket ID**: AIUM-905
- **Category**: UI Responsiveness, Telemetry Accuracy, Ingestion Automation
- **Target Release**: v0.9.5

## 2. Problem Statement
1. **Constrained UI Layout**:
   - The Web UI layout (`.container`, `.dashboard-grid`, `.reports-container`, etc.) enforces an artificial `max-width` constraint (such as `1280px` or `1400px`) centered on the page. On standard 1440p and 4K displays, over 60% of horizontal screen space is wasted, forcing horizontal scrollbars in wide data grids like "Historical Usage Reports & Cost Attribution" and "Agentic Sessions".
2. **Chart Timestamp Offset**:
   - The token velocity chart and hierarchical drill-down generate time bucket labels using UTC (`strftime('%H:%M')` on UTC `datetime`) instead of the user's local operating system timezone (`astimezone()`). When the user's local time is 14:29 (UTC+2), the chart ends at 12:00, leading to confusion.
3. **Missing Background Claude Desktop Activity**:
   - The user executes tasks using Claude Desktop (Cowork / Claude Code / Chat in MSIX package `Claude_pzs8sxrjxfjjc`).
   - The previous log scanner only monitored `~/.claude/projects/**/*.jsonl` (CLI only). Activity conducted inside the Claude Desktop application was cached in `%LOCALAPPDATA%\Claude-Data\claude_pzs8sxrjxfjjc\IndexedDB` (Blink-Snappy V8-serialized turns) and was not ingested into SQLite `usage_events`.
4. **Redundant Manual Calibration UI**:
   - The "Calibrate Claude" button and modal required manual entry of percentages.
   - The live Anthropic OAuth API (`https://api.anthropic.com/api/oauth/usage` and `https://api.anthropic.com/api/oauth/profile`) is accessible using the decrypted OAuth token from Claude Desktop's `config.json` via native Windows DPAPI (`crypt32.dll`) and CNG (`bcrypt.dll`). It directly provides real-time 5-hour session utilization, 7-day weekly utilization, exact reset epochs, and account tier information with zero user intervention.

## 3. Technical Requirements
1. **Full-Width Layout**:
   - Update `frontend/css/styles.css` to remove rigid `max-width` restrictions on `.container`, `.app-header`, panels, and data tables.
   - Use `width: 100%`, `max-width: none`, with comfortable horizontal padding (`clamp(16px, 2vw, 32px)`).
   - Ensure tables in Reports & Analytics and Agentic Sessions fill the entire available width.
2. **Local Timezone Bucket Alignment**:
   - In `backend/storage/database.py`, ensure `get_granular_timeseries()` and `get_hierarchical_trends()` convert timestamps to the local system timezone (`astimezone()`) when building bucket labels (`labels`), ensuring the final bucket reflects the current local hour/minute.
3. **Claude Desktop Ingestion**:
   - In `backend/providers/claude.py`, implement automated discovery and decryption of Claude Desktop OAuth tokens using native Windows `crypt32.dll` and `bcrypt.dll` (`BCryptDecrypt` AES-256-GCM).
   - Implement `fetch_live_oauth_telemetry()` to query `https://api.anthropic.com/api/oauth/usage` and `https://api.anthropic.com/api/oauth/profile`.
   - Implement pure-Python Blink-Snappy decompression to extract turns (`msg_01...`) from `%LOCALAPPDATA%\Claude-Data\claude_*\IndexedDB` into `usage_events`.
4. **Remove Manual Calibration**:
   - Remove `#calibrate-claude-btn` and `#claude-quota-modal` from frontend components (`frontend/components/comparison_panel.html`, `frontend/index.html`) and remove corresponding manual modal triggers in `frontend/js/app.js`.

## 4. Verification Plan
- Create test suite `tests/test_fullwidth_layout_localtime_claude_desktop_ingestion.py` covering:
  - Full-width layout CSS assertions.
  - Local timezone label generation in `get_granular_timeseries` and `get_hierarchical_trends`.
  - Pure-Python Snappy decompressor and V8 integer extractor.
  - Claude Desktop IndexedDB turn scanner.
  - Live OAuth telemetry parsing and snapshot update.
  - Absence of manual calibration buttons in frontend markup.
