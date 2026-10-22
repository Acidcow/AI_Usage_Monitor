# STE Feature Recipe: FR-903 - Granular Time-Span Windows, Bidirectional Web UI ↔ Mini Widget Sync & Dynamic Reports Grid with Local Model Savings

**Ticket ID**: `AIUM-903`  
**Title**: Granular Time-Span Windows, Bidirectional Web UI ↔ Mini Widget Sync & Dynamic Reports Grid with Local Model Savings  
**Priority**: Critical  
**Status**: Done  
**Standard**: ASD-STE100 (Simplified Technical English)  

---

## 1. Purpose
This recipe defines the technical implementation for two primary user requirements:
1. **Granular Time-Span Window Options & Bidirectional Web UI ↔ Mini Widget Synchronization**:
   - Expand time-span options across all Web UI chart/trend/report selectors and the Mini Widget (both Native Tkinter Taskbar Widget and Browser Mini Widget) to include:
     - **Last 1hr** (`1h`)
     - **Last 3hrs** (`3h`)
     - **Last 6hrs** (`6h`)
     - **Last 12hrs** (`12h`)
     - **Last 24hrs** (`24h`)
     - **Last 48hrs** (`48h`)
     - **Last 3 days** (`3d`)
     - **Last 5 days** (`5d`)
     - **Last 7 days** (`7d` — retained for continuity)
     - **Last 10 days** (`10d`)
     - **Last 15 days** (`15d`)
     - **Last 30 days** (`30d`)
     - **Last 3 months** (`3m`)
     - **Last 6 months** (`6m`)
     - **Last 12 months** (`12m`)
   - Synchronize time-span window (`active_trend_window` / `default_trend_window`), granularity (`active_chart_granularity`), and chart mode (`active_chart_mode` / `widget_view_mode`) bidirectionally via `/api/settings` so changes on the Web UI immediately align the Mini Widget, and changes on the Mini Widget immediately align the Web UI.
2. **Historical Usage Reports & Cost Attribution Grid Overhaul**:
   - Populate and expose **all** filterable operational dimensions as columns in the Historical Usage Reports grid (`Period / Date`, `Provider / Platform`, `Account / Tenant`, `Pivot Dimension`, `Traffic Route`, `Model`, `Instance / Node`, `Client IP`, `Client Alias`, `Team`, `User / Seat`, `Project`, `Events`, `Input`, `Output`, `Cache Create`, `Cache Read`, `Total Tokens`, `Est. Cost / Savings`, `Cost / 1k`, `Share`).
   - Provide an interactive **Column Visibility Manager** (Show/Hide checkboxes for every column, plus "Show All" / "Default View" presets).
   - Provide **Multi-Column Grouping & Group Aggregate Subtotals**: allow grouping rows by one or more selected columns (e.g., `Provider`, `Model`, `Traffic Route`, `Client Alias`) and toggling an **Aggregate Group Totals** option that inserts a highlighted subtotal line-item at the end of each group (plus a Grand Total footer row).
   - Provide **Drag-and-Drop Column Sequence Reordering** (`draggable="true"` on column headers and column manager chips) so users can reorder columns left-to-right dynamically.
   - Render **Local Model "Est. Cost" as Negative Estimated Savings**: for local inference rows (`provider === 'ollama'` or `is_local_model === true`), compute the cloud cost savings at the frontier benchmark rate (`$6.00 / 1M tokens`), expose `estimated_savings_usd` and negative `net_cost_usd` (`-savings`), and display the value in the `Est. Cost` column as a negative value wrapped in parentheses with a distinct alternate color badge (e.g., `(-$0.0450)` in vibrant emerald/violet).

---

## 2. Scope & Architectural Guardrails
1. **Zero External Dependencies**:
   - All backend changes use Python 3 Standard Library (`sqlite3`, `datetime`, `tkinter`, `json`).
   - All frontend changes use Vanilla ES6 JavaScript and HTML5 Drag-and-Drop (`dragstart`, `dragover`, `drop`, `dragend`).
2. **Backward Compatibility**:
   - Keep `total_cost_usd` and `estimated_cost` fields in `query_historical_report` summary and row payloads compatible with existing unit tests while adding `is_local_model`, `estimated_savings_usd`, `net_cost_usd`, and `display_cost_usd`.

---

## 3. Implementation Steps
1. **Step 1 — Backend Granular Window Engine (`backend/storage/database.py` & `backend/storage/reporting_engine.py`)**:
   - Update `get_granular_timeseries()` and `get_hierarchical_trends()` in `backend/storage/database.py` to support all 15 window codes (`1h`, `3h`, `6h`, `12h`, `24h`, `48h`, `3d`, `5d`, `7d`, `10d`, `15d`, `30d`, `3m`, `6m`, `12m`) with adaptive bucket sizing for multi-day/multi-month windows so bin counts stay fast and responsive (`<= 180` bins).
   - Update `get_all_settings()` in `backend/storage/database.py` to persist and return `active_trend_window` (default `"24h"`), `default_trend_window` (default `"24h"`), `active_chart_granularity` (default `5`), and `active_chart_mode` (default `"interval_delta"`).
   - Update `get_pivot_metrics()` in `backend/storage/reporting_engine.py` to support all 15 window codes in `window_deltas`.
2. **Step 2 — Backend Historical Report Full-Dimension & Local Savings Attribution (`backend/storage/reporting_engine.py`)**:
   - Ensure `query_historical_report()` always returns every attribution column (`period`, `provider`, `account_id`, `group_key`, `dimension_value`, `source`, `model`, `instance_id`, `client_ip`, `client_alias`, `team_name`, `user_name`, `project_id`, `token_id`) in every row whether `dimension` is set or default.
   - Calculate local model savings (`FRONTIER_RATE_PER_M = 6.00`) for local inference rows (`provider.lower() in ("ollama", "lmstudio", "vllm", "local")` or `estimated_cost == 0 and provider == "ollama"`):
     - `is_local_model = (prov == "ollama")`
     - `estimated_savings_usd = round((total_tokens / 1_000_000.0) * 6.00, 4)` when `is_local_model` else `0.0`
     - `net_cost_usd = -estimated_savings_usd` when `is_local_model` else `total_cost_usd`
   - Expose `total_estimated_savings_usd` and `net_cost_usd` in report `summary` / `totals`.
3. **Step 3 — Mini Widget Window Selector & Bidirectional Sync (`backend/tray/native_widget.py`, `frontend/mini_widget.html`, `frontend/js/widget.js`)**:
   - In `NativeTaskbarWidget` (`backend/tray/native_widget.py`):
     - Add `self.trend_window = "24h"` and `WINDOW_OPTIONS = [("1h", "1h"), ("3h", "3h"), ("6h", "6h"), ("12h", "12h"), ("24h", "24h"), ("48h", "48h"), ("3d", "3d"), ("5d", "5d"), ("7d", "7d"), ("10d", "10d"), ("15d", "15d"), ("30d", "30d"), ("3m", "3m"), ("6m", "6m"), ("12m", "12m")]`.
     - Add a compact interactive window selector button/menu (`⏱ 24h ▾`) in the Native Widget mode bar that lets the user pick any of the 15 windows or cycle through them, persists `active_trend_window` to `POST /api/settings`, and fetches `/api/usage/timeseries?window={self.trend_window}...`.
     - Sync `self.trend_window` from `/api/settings` on every poll cycle so selecting a window on the Web UI immediately updates the Native Widget!
   - In `frontend/mini_widget.html` and `frontend/js/widget.js`:
     - Add `#w-window-select` dropdown with all 15 window options to the widget header/mode strip.
     - Sync `this.trendWindow` with `st.active_trend_window` on poll and `POST /api/settings` when changed in the mini widget.
4. **Step 4 — Web UI Window Selectors & Dynamic Reports Grid (`frontend/components/usage_gauge_card.html`, `frontend/components/reports_panel.html`, `frontend/js/app.js`)**:
   - Expand `#trend-window-select`, `#chart-window-select`, `#report-date-range-select`, and `#pivot-window-select` with all 15 window options.
   - Persist `active_trend_window`, `active_chart_granularity`, and `active_chart_mode` to `/api/settings` when changed in the Web UI, and align the Web UI selectors when `/api/settings` reports a change made from the Mini Widget.
   - Overhaul `frontend/components/reports_panel.html` and `frontend/js/app.js` with:
     - All 20 attribution & metric columns available in the grid.
     - Interactive Column Visibility Picker & Draggable Sequence Bar (`#reports-column-manager`).
     - HTML5 Drag-and-Drop on table `<th>` headers and column chips (`onReportColDragStart`, `onReportColDragOver`, `onReportColDrop`) to reorder columns left-to-right.
     - Multi-Column Group-By selector chips (`#reports-groupby-bar`) + `Aggregate Group Totals` checkbox (`#reports-group-totals-chk`) that groups rows by the selected column(s) and renders a styled Group Subtotal line-item at the end of each group.
     - Local model `Est. Cost` rendered as negative savings in parentheses with an alternate color badge, e.g. `($0.0450)` / `(-$0.0450)`.

---

## 4. Verification Criteria
- Unit test suite `tests/test_window_sync_and_dynamic_reports_grid.py` with `>= 20` unit tests covering all 15 time windows, bidirectional Web UI ↔ Mini Widget settings sync, full-dimension report rows, local model negative cost/savings calculation, multi-column grouping/aggregation, column visibility, and drag-and-drop sequence reordering.
- 100% pass rate across all unit tests via `python dev_tools/manage_roadmap.py run-tests`.
