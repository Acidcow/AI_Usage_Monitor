# Feature Recipe FR-801: Multi-Platform Telemetry Capture, Multi-Instance Rollups, Proxy Source Correlation, Zero Double-Accounting & Dynamic Pivoting

## 1. Goal
Provide enterprise-grade telemetry capture, correlation, and multidimensional visibility across all AI platforms (Claude, Gemini, Ollama, ChatGPT, Copilot):
1. **Accurate Multi-Platform & Model Telemetry Capture**: Ensure all enabled services and models capture input, output, cache, and cost metrics with verified tests across each platform.
2. **Multi-Account & Multi-Instance Aggregation**: Support distinct accounts and instances per platform, displaying individual activity and aggregating mathematically consistent sum totals at every level (Platform, Account, Instance/Node, Model).
3. **Proxy vs. Direct Source Discernment & Deduplication**: Tag every event with `source` (`'proxy'`, `'emulator'`, `'direct_api'`, `'log_scanner'`) and `is_proxied`, correlates events via `external_id` and temporal session fingerprinting to completely eliminate double-accounting between live proxy interception and periodic background syncs.
4. **Multi-Dimensional Pivoting**: Expose a flexible query/pivot API (`/api/usage/pivot`) and UI views allowing developers and teams to slice and pivot telemetry by `platform`, `account`, `instance`, `model`, `client`, `source`, or `group`.
5. **Platform-Wide UI & Widget Alignment**: Resolve the 6 identified alignment issues across the Web Dashboard, the Native Taskbar Widget, and the HTML Mini Widget.

## 2. Technical Architecture & Implementation Details

### 2.1 Database Schema Migrations (`backend/storage/database.py`)
- In `usage_events` table:
  - Add `source TEXT NOT NULL DEFAULT 'direct'`
  - Add `instance_id TEXT NOT NULL DEFAULT 'default'`
  - Add `external_id TEXT` (Upstream API request/message ID, e.g. `msg_01...` or `chatcmpl-...`)
  - Add `is_proxied INTEGER NOT NULL DEFAULT 0`
  - Create indices:
    - `idx_usage_source ON usage_events(source)`
    - `idx_usage_instance ON usage_events(instance_id)`
    - `idx_usage_external_id ON usage_events(external_id)`

### 2.2 Deduplication & Correlation Engine (`backend/storage/database.py`)
- Enhance `record_usage_event(...)`:
  - When recording:
    - If `external_id` is supplied: check if an event with that `external_id` already exists.
    - If `session_id` and timestamps match within a tight temporal window (+-60 seconds) with identical token count:
      - If existing event is from `proxy` and incoming is from `direct_api` or `log_scanner`: update/enrich existing record with account/metadata without duplicating tokens.
      - Return existing ID without adding duplicate tokens.
  - Expose `get_deduplicated_summary()` and ensure all aggregation queries avoid double-counting.

### 2.3 Multi-Instance & Account Aggregation (`backend/storage/database.py`)
- In `get_comparative_metrics(...)`:
  - Group events by `provider`, `account_id`, and `instance_id`.
  - For each provider:
    - Compute `accounts`: list of distinct accounts with tokens, costs, models, and instances.
    - Compute `instances`: list of distinct physical instances/nodes (e.g. `local`, `node_worker_1`).
    - Verify sum of child account tokens equals the platform total tokens.
  - Return `source_breakdown`: `{ "proxy": tokens, "direct": tokens, "scanner": tokens, "emulator": tokens }`.

### 2.4 Multi-Dimensional Pivot API (`backend/storage/database.py` & `backend/server/http_server.py`)
- New endpoint: `GET /api/usage/pivot`
  - Query parameters:
    - `dimensions`: comma-separated list of fields to pivot by (`platform`, `account`, `instance`, `model`, `client`, `source`, `group`)
    - `window`: `1h`, `24h`, `7d`, `30d`, `all`
    - `filter_source`: optional filter (`proxy`, `direct`, etc.)
    - `filter_client`: optional filter by client IP or alias
    - `filter_platform`: optional filter by platform
  - Response payload:
    - `rows`: list of pivoted rows with token sums, cost sums, session counts, and percentage share
    - `totals`: grand totals matching the sum of rows
    - `dimensions`: active grouping dimensions

### 2.5 Obvious Platform Alignment Fixes
1. **Ollama Sparklines in Widgets**:
   - In `backend/storage/database.py:get_granular_timeseries`: assign series IDs with both `ollama_model_{m}` and `{m}`.
   - In `backend/tray/native_widget.py` and `frontend/js/widget.js`: check both `s.id.startsWith("ollama_model_")` and model names from `item.models`.
2. **Live Theme Updates in Native Widget**:
   - In `backend/tray/native_widget.py:_apply_settings_from_server`: call `self.apply_theme(new_theme, self.font_scale)` whenever `st["widget_theme"]` differs.
3. **HTML Widget Theme & Font Scale**:
   - In `frontend/js/widget.js`: support canonical theme keys (`obsidian_neon`, `matrix_emerald`, `midnight_slate`), parse font scale properly, align view mode names (`balances` ↔ `multi`).
4. **Claude Expanded Card Height**:
   - In `backend/tray/native_widget.py:render_canvas`: set `card_h = 66` in `individual` tracking mode.
5. **Weather Flyout Mouse Events in HTML Widget**:
   - In `frontend/js/widget.js`: attach `onmouseenter` and `onmouseleave` to `.account-row-card`.
6. **Hierarchical Trends Endpoint**:
   - In `backend/server/http_server.py`: filter corporate division series when `quota_tracking_mode == "individual"`.

## 3. Verification Criteria
- >=20 unit tests in `tests/test_multi_dimensional_telemetry_and_deduplication.py` covering:
  - Multi-platform telemetry capture across Claude, Gemini, Ollama, ChatGPT, Copilot.
  - Multi-instance and multi-account distinct reporting and sum total validation.
  - Proxy vs direct traffic discrimination and tagging.
  - Deduplication and zero double-accounting verification.
  - Dimensional pivoting via `/api/usage/pivot`.
  - Sparkline series ID normalization for Ollama models.
  - Widget live theme update and height calibration.
- 100% green test execution across all tests.
