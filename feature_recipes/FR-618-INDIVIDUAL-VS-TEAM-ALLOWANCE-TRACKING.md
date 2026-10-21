# Feature Recipe FR-618: Individual vs. Team Allowance Tracking Mode Toggle & Hierarchy Streamlining

## 1. Goal
Provide a user-configurable System Setting toggle between **Individual Direct Tracking** (1:1 personal platform quotas) and **Team / Group Allowance Pool Tracking**. When set to Individual Tracking Mode, align with official Claude documentation (which reports quotas at the individual member level) by removing high-level hierarchical views, estimated department/enterprise rollups, and artificial conversion rates, focusing strictly on direct personal platform session and weekly limits.

## 2. Technical Requirements

### 1. Database Schema & Settings Persistence (`backend/storage/database.py`)
- Add setting `quota_tracking_mode` to `app_settings` (default: `"individual"`).
- Implement `get_quota_tracking_mode() -> str`:
  - Returns `"individual"` or `"team"`.
- Implement `set_quota_tracking_mode(mode: str) -> str`:
  - Validates `mode in ("individual", "team")`.
  - Persists to `app_settings` and returns the sanitized mode.
- Update `get_all_settings()` to include `quota_tracking_mode: "individual"`.
- Update `get_comparative_metrics(scope=None, ...)`:
  - When `scope` is `None` or not provided, default `scope` to `get_quota_tracking_mode()`.
  - When `quota_tracking_mode == "individual"`:
    - Use direct 1:1 individual member session and weekly percentages without artificial conversion rates or estimated company fractions.
    - Set `tracking_mode: "individual"` in the root response.
    - In `hierarchy`, mark `hierarchy["streamlined"] = True`, set `hierarchy["tracking_mode"] = "individual"`, and prune or disable higher-level theoretical rollups (`department` and `enterprise`).
  - When `quota_tracking_mode == "team"`:
    - Retain multi-scope hierarchy objects (`individual`, `team`, `department`, `enterprise`).

### 2. REST API & HTTP Endpoints (`backend/server/http_server.py`)
- `GET /api/settings`: Returns `quota_tracking_mode` along with existing settings.
- `POST /api/settings`: Accepts `{"quota_tracking_mode": "individual" | "team"}` and persists via `set_quota_tracking_mode`.
- `GET /api/usage/comparison`: Uses configured `quota_tracking_mode` as default scope when no query param is passed.

### 3. Web UI Settings Component (`frontend/components/settings_panel.html` & `frontend/js/app.js`)
- Add a dedicated **Allowance & Quota Tracking Mode** card in System Settings:
  - Radio/toggle selector:
    - **👤 Individual Member Direct Quotas (Official claude.ai 1:1)**:
      Direct session and weekly balances reported for the active user account. Disables theoretical multi-level organizational estimates.
    - **👥 Team / Shared Allowance Pool**:
      Tracks shared organization and workspace team pools with department and division rollups.
  - Automatically loads and saves via `App.loadSettings()` and `App.saveSettings()`.

### 4. Dashboard View & Hierarchy Streamlining (`frontend/components/usage_gauge_card.html` & `frontend/js/app.js`)
- When `quota_tracking_mode == "individual"`:
  - Scope Switcher bar in Dashboard simplifies:
    - Hides `Team Workspace Pool` and `Enterprise / Division` buttons.
    - Shows `👤 Individual Direct Tracking (Active)` with an informational badge and quick link to Settings.
  - In Comparative Breakdown Table:
    - Status badge renders `👤 Individual Quota (claude.ai)`.
    - Drill-down accordion removes the theoretical `👥 Team Workspace Pool`, `🏢 Department / Division`, and `🌐 Organization / Enterprise` cards.
    - Keeps real child telemetry (e.g. local Ollama models, named Gemini keys).
- When `quota_tracking_mode == "team"`:
  - Restores full multi-scope selector and all hierarchy cards.

### 5. Claude Calibration Modal Alignment (`frontend/index.html` & `frontend/js/app.js`)
- Streamlines `openClaudeQuotaModal()` so in Individual Mode, it presents direct personal session and weekly quotas from `claude.ai/settings/usage` without requiring or expecting artificial company-level conversion inputs.

### 6. Native Taskbar Widget Alignment (`backend/tray/native_widget.py`)
- In hover flyout, reads `quota_tracking_mode` from `/api/settings`:
  - When `quota_tracking_mode == "individual"`, shows direct personal lines:
    - `• 👤 Session Quota: {sess_rem}% rem ({sess_used}% used)`
    - `• 👤 Weekly Quota:  {week_rem}% rem ({week_used}% used)`
  - Suppresses confusing/redundant calculated `• 👥 Team Pool: ...` line.

## 3. Verification Criteria
- Comprehensive TDD unit test suite with >=20 tests:
  - Setting read/write and validation in SQLite.
  - Comparative metrics behavior under `individual` vs `team` tracking modes.
  - Streamlined hierarchy payload assertions (omission of theoretical department/enterprise when individual).
  - HTTP Server `/api/settings` and `/api/usage/comparison` integration.
  - Native widget flyout formatting under both modes.
- 100% green test execution across all 168+ tests in the repository.
- Zero external dependencies.
