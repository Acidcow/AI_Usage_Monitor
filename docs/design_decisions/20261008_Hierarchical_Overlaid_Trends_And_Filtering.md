# Architecture Decision Record (ADR): Hierarchical Overlaid Trends, Multi-Level Widget Charts & Dynamic Group Filtering

**Date**: 2026-10-08  
**Status**: Approved  
**Tickets**: AIUM-611, AIUM-612, AIUM-613  
**Authors**: Antigravity Pair Programming Engine  

---

## 1. Context & Problem Statement

Users monitoring complex multi-account AI estates need deeper visibility than single aggregated sparklines or static placeholders:
1. In the Dashboard "Trend Lines" mode, sparklines were hardcoded placeholders rather than multi-series time-bucketed curves reflecting actual child usage.
2. When expanding a platform or account hierarchy (e.g. Claude Org -> Dept -> Team -> Individual or Gemini Account -> API Keys), users need multi-series charts overlaid at the top level with interactive legend toggling and mouse-over glow effects.
3. In the Mini Widget (both Web and Native Win32), the trend view only displayed a single sparkline. Users require top-level overlaid child plots, nested child charts upon expansion with consistent color coding, color swatch blocks left of headers, and a toggle to keep or hide the parent chart on expand.
4. Users require flexible top-level grouping modes ("All", "Platforms/Services", "Groups/Tags", or "Filtered" via multi-select panel) and fine-grained visibility controls to hide unconfigured platforms by default.

---

## 2. Decision & Architecture Specification

### A. Hierarchical Time-Series Data Model (`UsageDatabase`)
- Add method `get_hierarchical_trends(provider, window="24h", scope="individual")`:
  - Buckets usage events by hour (for 24h/7d) or day (for 30d).
  - Groups series by parent provider and dimensional child attributes:
    - `team_name`, `user_name`, `token_id`, `model`.
  - Normalizes timestamps across series so points align on a shared X axis.
  - Returns structured JSON:
    ```json
    {
      "window": "24h",
      "labels": ["12:00", "13:00", ...],
      "series": [
        { "id": "parent", "name": "Google Gemini", "color": "#38bdf8", "points": [120, 340, ...] },
        { "id": "tok_1", "name": "Flash Key", "color": "#10b981", "points": [80, 200, ...] }
      ]
    }
    ```

### B. Interactive Multi-Series SVG Engine (`frontend/js/app.js`)
- Render multi-path SVG elements:
  - Base `<polyline>` or `<path>` per active series.
  - Subtle semi-transparent gradient area under the primary line.
  - Interactive legend badges above or beside the chart.
  - Click on legend: toggles line visibility by switching CSS opacity (`opacity: 0` vs `opacity: 1`).
  - Hover on legend: applies SVG `filter: drop-shadow(0 0 8px <color>)` to the matching path, dims other lines.
  - Hover on path: highlights the matching legend badge with a glowing border and reveals current value.
  - Axis labels: X-axis time markers and Y-axis token rate indicators configurable via user preferences.

### C. Mini Widget Nested Multi-Plot Rendering (`frontend/js/widget.js` & `backend/tray/native_widget.py`)
- In `trends` mode:
  - Top-level card plots multiple colored lines on the canvas for each child branch.
  - Header displays a colored swatch block `■` matching the primary series color.
  - Upon clicking expand, render individual nested trend charts for each child item in their respective assigned color.
  - Check `widget_hide_parent_chart_on_expand`: if true, collapse the parent chart when children are open; if false, display both.

### D. Grouping Switcher & Visibility Settings
- Add view modes:
  - `all`: Render both platform headers and cross-platform group tags.
  - `platforms`: Render only provider/platform roots.
  - `groups`: Render only tag/group roots.
  - `filtered`: Filter by user-selected IDs from multi-select dialog.
- Visibility settings:
  - Key `estate_visibility`: `{ "hidden_platforms": ["chatgpt"], "hidden_accounts": [], "hidden_tags": [] }`.
  - Filter out unconfigured or hidden providers from default rendering.

---

## 3. Security, Performance & Zero-Dependency Compliance
- Strictly Python 3 standard library (`sqlite3`, `json`, `datetime`, `urllib`).
- Zero external charting libraries (pure native SVG and Win32/Tkinter canvas).
- Visibility settings and credentials remain encrypted in Windows DPAPI vault.
