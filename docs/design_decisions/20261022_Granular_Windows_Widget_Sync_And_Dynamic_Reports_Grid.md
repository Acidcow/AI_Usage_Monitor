# Architecture & Design Decision: Granular Time-Span Windows, Bidirectional Web UI ↔ Mini Widget Sync & Dynamic Reports Grid

**Date**: 2026-10-22  
**Ticket**: `AIUM-903`  
**Feature Recipe**: `feature_recipes/FR-903-GRANULAR-WINDOWS-WIDGET-SYNC-AND-DYNAMIC-REPORTS-GRID.md`  
**Status**: Approved  

---

## 1. Context & Problem Statement
1. **Limited Time-Span Window Options & Desynchronized Mini Widget**:
   - Previously, the Web UI time-span selectors jumped abruptly from `Last 1hr` (`1h`) to `Last 24hrs` (`24h`), `Last 7 days` (`7d`), and `Last 30 days` (`30d`).
   - Furthermore, both `backend/tray/native_widget.py` and `frontend/js/widget.js` hardcoded `window=1h` when querying `/api/usage/timeseries`, meaning selecting a different time window on the Web UI did not align the Mini Widget, nor could the user change the time window on the Mini Widget and have the Web UI follow.
2. **Historical Usage Reports & Cost Attribution Grid Limitations**:
   - The Historical Usage Reports filter bar allows filtering by `Provider`, `Account / Tenant`, `Pivot Dimension`, `Traffic Route`, `Model`, `Instance / Node`, `Client IP / Alias`, `Team`, and `User`, but the table below only rendered `Period / Date` and a single collapsed `Dimension / Key` column alongside token/cost metrics.
   - Users could not choose which columns to show/hide, could not reorder columns left-to-right via drag-and-drop, and could not group items by one or more columns with an aggregated subtotal line-item at the end of each group.
   - Local models (such as `ollama`) displayed `$0.0000` in the `Est. Cost` column instead of displaying a negative value in parentheses with an alternate color representing the estimated savings for that line item.

---

## 2. Architectural Decisions

### Decision 1: Unified 15-Window Time-Span Catalog & Adaptive Binning
We standardize a canonical set of 15 time-span windows across `UsageDatabase.get_granular_timeseries`, `UsageDatabase.get_hierarchical_trends`, `ReportingEngineMixin.get_pivot_metrics`, the Web UI, and the Mini Widgets:
- `1h` (Last 1hr — 60 mins)
- `3h` (Last 3hrs — 180 mins)
- `6h` (Last 6hrs — 360 mins)
- `12h` (Last 12hrs — 720 mins)
- `24h` (Last 24hrs — 1,440 mins)
- `48h` (Last 48hrs — 2,880 mins)
- `3d` (Last 3 days — 4,320 mins)
- `5d` (Last 5 days — 7,200 mins)
- `7d` (Last 7 days — 10,080 mins)
- `10d` (Last 10 days — 14,400 mins)
- `15d` (Last 15 days — 21,600 mins)
- `30d` (Last 30 days — 43,200 mins)
- `3m` (Last 3 months / 90 days — 129,600 mins)
- `6m` (Last 6 months / 180 days — 259,200 mins)
- `12m` (Last 12 months / 365 days — 525,600 mins)

To prevent multi-month windows from generating hundreds of thousands of SVG points when `bucket_minutes=5`, `get_granular_timeseries` preserves exact `win_mins // bucket_min` for short windows (`<= 24h`) and caps `num_bins` to a clean, high-resolution ceiling (`<= 180` bins) for multi-day/multi-month windows by scaling the effective bucket interval proportionally when `win_mins // bucket_min > 288`.

### Decision 2: Bidirectional State Synchronization via `app_settings`
We store `active_trend_window` (and `default_trend_window`), `active_chart_granularity`, `active_chart_mode`, and `widget_view_mode` in SQLite `app_settings` exposed via `GET /api/settings` and `POST /api/settings`:
- When the user changes the window, granularity, or mode in the Web UI (`changeChartWindow`, `changeTrendWindow`, `changeChartMode`, `changeChartGranularity`), `window.App` persists `active_trend_window`, `active_chart_granularity`, and `active_chart_mode` to `POST /api/settings`.
- When the user changes the window or view mode in the Native Taskbar Widget (`backend/tray/native_widget.py`) or Browser Mini Widget (`frontend/js/widget.js`), the widget persists `active_trend_window` and `widget_view_mode` to `POST /api/settings`.
- During each poll cycle, both the Web UI and Mini Widgets inspect `/api/settings` and automatically align their active window and chart mode whenever an external update is detected.

### Decision 3: Full-Attribution Dynamic Reports Grid with Drag-and-Drop, Multi-Column Grouping & Local Savings
1. **Backend Attribution & Savings (`backend/storage/reporting_engine.py`)**:
   - `query_historical_report` returns all dimensional fields on every row: `period`, `provider`, `account_id`, `group_key`, `source`, `model`, `instance_id`, `client_ip`, `client_alias`, `team_name`, `user_name`, `project_id`, `token_id`.
   - For local model rows (`provider == 'ollama'`), `estimated_savings_usd = round((total_tokens / 1_000_000.0) * 6.00, 4)` and `net_cost_usd = -estimated_savings_usd`.
2. **Frontend Dynamic Column Engine (`frontend/js/app.js`, `frontend/components/reports_panel.html`)**:
   - `reportColumns` defines the ordered array of column descriptors (`key`, `label`, `visible`, `align`, `isNumeric`, `isDimension`).
   - Users can toggle column visibility via checkboxes, reorder columns left-to-right by dragging and dropping `<th>` headers or column manager chips (`HTML5 Drag and Drop API`), and group rows by any combination of dimension columns (`reportGroupByCols`) with optional **Aggregate Group Subtotals** (`reportIncludeGroupTotals`) rendered as a summary row at the end of each group.
   - Local model rows render their `Est. Cost` cell in an alternate emerald/violet savings style wrapped in parentheses: `(-$0.0450)`.
