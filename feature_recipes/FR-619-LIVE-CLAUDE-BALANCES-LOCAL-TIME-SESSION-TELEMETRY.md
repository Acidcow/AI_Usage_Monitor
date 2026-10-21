# Feature Recipe FR-619: Live Claude Session & Weekly Token Balances, GMT+2 Timezone Localization, Simplified Personal View & Enhanced Session Activity Telemetry

## 1. Goal
Address Claude monitoring limitations by:
1. Providing live, automated token balance tracking for Claude's 5-hour rolling session and weekly quotas (used, available, limit, and countdowns) directly from real ingested events, eliminating reliance on static manual calibration pop-ups and automatically resetting expired sessions.
2. Clarifying telemetry scope: Claude limits operate strictly per-member (individual). Streamline the UI by removing synthetic Team, Department, and Enterprise pool estimates in individual mode.
3. Localizing all timestamps and chart axis entries to the user's local timezone (GMT+2) instead of raw UTC / GMT.
4. Enhancing the "Recent Agentic Sessions & Tokens" view with client IP addresses, computer hostnames/aliases, First Activity timestamps, session duration calculations, and interactive header sorting & search filtering.

## 2. Technical Architecture & Requirements

### 1. Database Schema & Dynamic Quota Calculations (`backend/storage/database.py`)
- **Schema Migrations**:
  - Add `client_ip TEXT` and `client_alias TEXT` to `usage_events` table with index on `client_ip`.
- **Dynamic 5-Hour Rolling Session & Weekly Token Balances**:
  - Implement `compute_provider_dynamic_quotas(provider="claude")`:
    - Reads configured token limits from `app_settings` (defaults based on plan: Pro = 75k session / 500k weekly; Team Standard = 200k session / 1.4M weekly; Team Premium = 500k session / 3.5M weekly; Max = 1M session / 7M weekly).
    - Checks `reset_epoch`:
      - If `now_epoch >= reset_epoch`: previous session has expired. Checks for new events after expired `reset_epoch`. If new events exist, new session begins at `MIN(recorded_at)` with `reset_epoch = start_epoch + 5 * 3600`. If no new events exist, session is 100% idle (`session_tokens_used = 0`), awaiting new activity.
      - If `now_epoch < reset_epoch`: session is active. Sums all `total_tokens` where `provider = 'claude' AND recorded_at >= session_start_iso`.
    - Computes:
      - `session_tokens_used`: Real sum of tokens in active 5h window.
      - `session_tokens_available`: `max(0, session_tokens_limit - session_tokens_used)`.
      - `session_balance_remaining_pct`: `round((session_tokens_available / session_tokens_limit) * 100, 1)`.
      - `session_used_pct`: `round(100.0 - session_balance_remaining_pct, 1)`.
      - `weekly_tokens_used`: Real sum of tokens since weekly reset cutoff.
      - `weekly_tokens_available`: `max(0, weekly_tokens_limit - weekly_tokens_used)`.
      - `weekly_balance_remaining_pct`: `round((weekly_tokens_available / weekly_tokens_limit) * 100, 1)`.
      - `weekly_used_pct`: `round(100.0 - weekly_balance_remaining_pct, 1)`.
  - Update `get_comparative_metrics()` to integrate these live balances into Claude's metrics and hierarchy.
  - In `get_recent_sessions()`:
    - Query `MIN(recorded_at) as first_activity`, `MAX(recorded_at) as last_activity`, `COALESCE(MAX(client_ip), '127.0.0.1') as client_ip`, and `COALESCE(MAX(client_alias), '') as client_alias`.
    - Resolve missing aliases via `resolve_client_alias(client_ip)` or local computer name fallback.

### 2. Timezone Localization & Chart Axis Bins (`backend/storage/database.py` & `frontend/js/app.js`)
- **Backend**:
  - Ensure ISO timestamp strings in `keys` include explicit UTC `Z` designator so client parses correctly into local time.
- **Frontend**:
  - Add `formatLocalDateTime(isoStr)` and `formatLocalTime(isoStr)` converting UTC ISO strings into user's local timezone (GMT+2) with 24h format.
  - In `renderVelocityChart` and `_setupChartHoverCrosshair`:
    - Generate bottom X-axis tick labels and hover tooltip time strings from the UTC ISO keys converted to local time (`HH:MM`).
  - In `renderSessions`:
    - Render `first_activity` and `last_activity` localized.
    - Compute and display `duration` (formatted e.g. "45m 12s").
  - In `renderErrors`:
    - Localize error timestamps.

### 3. Recent Sessions UI Table Sorting & Filtering (`frontend/components/session_timeline.html` & `frontend/js/app.js`)
- Add columns:
  - Session ID
  - Provider
  - Model
  - Client / Host (IP + Alias)
  - Input Tokens
  - Output Tokens
  - Total Tokens
  - Est. Cost
  - First Activity
  - Last Activity
  - Duration
- Add interactive column sorting on header click with `▲` and `▼` indicators.
- Add instant search input filtering by Session ID, Provider, Model, IP, or Alias.

### 4. Simplified Personal View in Native Widget & Dashboard
- In `backend/tray/native_widget.py`:
  - When in individual mode, display exact token counts in the flyout:
    `• 👤 Session Quota: {sess_rem}% rem ({sess_used}% used) [{tokens_available:,} / {tokens_limit:,} tok]`
  - In expanded view, suppress the theoretical Team Pool bar when tracking mode is individual.

## 3. Verification Criteria
- >=20 comprehensive unit tests covering:
  - Dynamic 5h rolling session token calculation and auto-reset.
  - Dynamic weekly token calculation.
  - Plan limit configuration & custom budget overrides.
  - `usage_events` migration for `client_ip` and `client_alias`.
  - `get_recent_sessions()` returning first_activity, last_activity, client_ip, and client_alias.
  - Native widget flyout formatting with live token balances.
- 100% green test execution across all tests.
- Zero external dependencies.
