# Feature Recipe FR-604: Multi-Scope Usage Hierarchy (Individual, Team, Dept, Enterprise Drill-Down)

## 1. Goal
Provide clear architectural separation and drill-down between an individual user's personal quota limits (e.g. 60% session used / 27% weekly used on claude.ai settings), team workspace pools, departmental groups, and enterprise-wide rollups across all monitored AI platforms.

## 2. Technical Requirements
1. **Database Schema & Hierarchy Modeling (`backend/storage/database.py`)**:
   - Add hierarchical columns to `provider_snapshots`:
     - `scope TEXT NOT NULL DEFAULT 'individual'`
     - `user_name TEXT`
     - `team_name TEXT`
     - `dept_name TEXT`
     - `org_name TEXT`
     - `individual_session_rem_pct REAL`
     - `individual_weekly_rem_pct REAL`
     - `team_session_rem_pct REAL`
     - `team_weekly_rem_pct REAL`
   - Automated SQLite migration for existing databases.
   - Update `get_comparative_metrics(scope="individual")`:
     - Return active metrics based on the requested scope (`individual`, `team`, `enterprise`).
     - Return a complete `hierarchy` object per provider containing individual, team, department, and enterprise levels.

2. **Claude Provider Multi-Scope Calibration (`backend/providers/claude.py`)**:
   - Update `calibrate_limits(...)` to accept:
     - `scope`: `"individual"`, `"team"`, or `"all"`
     - `individual_session_used_pct`, `individual_weekly_used_pct`
     - `team_session_used_pct`, `team_weekly_used_pct`
     - `user_name`, `team_name`, `org_name`
   - Default pre-seeding:
     - Individual: 60.0% session used (40.0% remaining) | 27.0% weekly used (73.0% remaining)
     - Team: 56.0% session used (44.0% remaining) | 26.0% weekly used (74.0% remaining)

3. **HTTP Server API Updates (`backend/server/http_server.py`)**:
   - `GET /api/usage/comparison?scope=individual|team|enterprise`
   - `POST /api/providers/claude/quota` with scope parameters and multi-tier limits.

4. **Web UI Scope Switcher & Interactive Drill-Down (`frontend/`)**:
   - Add Scope Selector pill buttons at the top of the dashboard:
     - `[ 👤 Individual (My Quota) ]`
     - `[ 👥 Team Pool ]`
     - `[ 🏢 Enterprise / Org ]`
   - In Multi-Account Comparison table, add an interactive accordion drill-down toggle ("⤓ Drill-Down Hierarchy") on each account row, displaying side-by-side:
     - Individual User Scope
     - Team / Workspace Pool
     - Department & Enterprise Rollup
   - Update "⚖️ Calibrate Limits" modal to support both Individual and Team quotas.

5. **Native Widget Support (`backend/tray/native_widget.py`)**:
   - Default to `individual` scope so developers immediately see their personal quota limits.
   - In hover flyout, show both **👤 Personal Limits** and **👥 Team Pool Limits**.

## 3. Verification Criteria
- Unit tests pass with 100% success rate:
  - `test_database_hierarchical_scopes_and_metrics` in `tests/test_database.py`.
  - `test_claude_multi_scope_calibration` in `tests/test_claude_provider.py`.
  - `test_api_usage_comparison_with_scope_query` in `tests/test_http_api.py`.
- Zero external dependencies.
