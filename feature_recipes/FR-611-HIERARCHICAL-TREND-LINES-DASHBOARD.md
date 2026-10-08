# Feature Recipe FR-611: Interactive Multi-Series Overlaid Trend Lines & Hierarchy Drill-Down Charts in Dashboard

## 1. Goal
Replace the static/placeholder sparkline in the Dashboard "Trend Lines" view with dynamic, multi-series overlaid SVG line charts reflecting historical telemetry. Enable multi-level hierarchical drill-down (Accounts/Organization -> Department -> Team -> Individual, or Account -> API Keys) with interactive legend line toggling, bidirectional hover glow effects, configurable time windows, and optional X/Y axis labels.

## 2. Technical Requirements
1. **Historical Trend Telemetry Backend Service**:
   - Query time-bucketed token events across configured time windows: `1h`, `24h` (default), `7d`, `30d`.
   - Provide time-series data points not only for top-level platforms, but for each child entity in the hierarchy:
     - Claude: Organization, Department, Team, Individual.
     - Gemini: Google Account Umbrella, individual named API Keys (`tok_gem_flash`, `tok_gem_pro`, etc.).
     - Ollama: Individual models (`llama3:latest`, `deepseek-r1:14b`, `mistral:latest`).
   - Expose endpoint `GET /api/usage/trends/hierarchy?window=24h&provider=<key>&scope=<scope>`.

2. **Multi-Series Overlaid SVG Chart Engine**:
   - Pure zero-dependency SVG renderer with anti-aliased path smoothing, gradient fills, and distinct high-contrast palette per child series.
   - Plot child series lines overlaid together on the top-level chart.
   - Add interactive chart legend (reference key) with clickable pill badges:
     - Clicking a legend badge toggles visibility of the corresponding line plot.
   - Bidirectional mouse-over hover glow:
     - Hovering over a legend entry highlights the corresponding plotted line with a neon glow filter (`filter: drop-shadow(0 0 6px <color>)`) and thickens the stroke.
     - Hovering over a line path or data point highlights the corresponding legend entry badge and displays an inline tooltip with timestamp and token velocity.

3. **Chart Window and Axis Controls**:
   - Explicitly display active window period badge on the UI (e.g. `Window: Last 24 Hours`).
   - Support toggling X and Y axis labels (time stamps on X axis, token counts/rates on Y axis) via configuration.

## 3. Verification Criteria
- [ ] Backend endpoint `/api/usage/trends/hierarchy` returns multi-series time-bucketed points for all providers and their hierarchy children.
- [ ] SVG chart generates multiple overlaid `<polyline>` or `<path>` elements with distinct colors.
- [ ] Clicking a legend badge toggles line opacity/display without breaking SVG layout.
- [ ] Mouseover on legend triggers line glow, mouseover on line triggers legend badge glow.
- [ ] Window period is clearly indicated on the UI.
- [ ] Zero external JavaScript or CSS libraries (pure Vanilla JS and SVG).
