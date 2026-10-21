# Feature Recipe FR-617: Granular Time-Series Aggregation, Interval Delta Widget Mode, Cadence Control & Gemini Proxy Ingestion

## 1. Goal
Provide fine-grained 1-minute to 60-minute time-series telemetry aggregation with selectable plotting buckets. Eliminate UI visual jumpiness through user-configurable refresh cadences (30s to 300s). Introduce a 3rd widget view mode for interval/delta token usage plotted from a zero baseline. Expand the local transparent proxy to intercept Google Gemini completions (`generativelanguage.googleapis.com`), parse `usageMetadata`, and attribute tokens to registered named Gemini API keys.

## 2. Technical Requirements

1. **Google Gemini Proxy Ingestion (`backend/proxy/transparent_proxy.py`)**:
   - Inspect incoming requests on port 8766. If path starts with `/v1beta/` or contains `models` / `generativelanguage.googleapis.com`, forward to `https://generativelanguage.googleapis.com`.
   - Support mock testing headers (`x-mock-gemini-response`) for deterministic test execution.
   - On completion response, parse `usageMetadata` (`promptTokenCount`, `candidatesTokenCount`, `totalTokenCount`).
   - Extract the active API key from `key=` query parameter or `x-goog-api-key` header.
   - Map key to the corresponding child token ID (`tok_gem_flash`, `tok_gem_pro`, `tok_gem_...`).
   - Ingest into SQLite `usage_events` with `provider='gemini'`, `token_id=...`, `account_id='acidcow@gmail.com'`.
   - Update `provider_snapshots` for Gemini with real tokens consumed and health status.

2. **Multi-Granularity Time-Series Aggregator (`backend/storage/database.py`)**:
   - Add method `get_granular_timeseries(provider=None, window="24h", bucket_minutes=5, mode="cumulative", scope="individual")`.
   - Support bucket sizes: `1`, `5`, `10`, `15`, `30`, `60` minutes.
   - Support modes:
     - `"cumulative"`: Monotonically running cumulative sum total across the window.
     - `"interval_delta"`: Discrete tokens consumed strictly inside each bucket interval, resetting to 0 for idle periods.
   - Generate contiguous timestamps from `cutoff` to `now`, ensuring every bucket is represented (idle buckets have 0 tokens).
   - Ensure `get_hierarchical_trends()` supports `bucket_minutes` and `mode`.

3. **HTTP Server API Endpoints (`backend/server/http_server.py`)**:
   - `GET /api/usage/timeseries`: Expose granular time-series data with parameters `provider`, `window`, `bucket_minutes`, `mode`, and `scope`.
   - `POST /api/providers/gemini/test-probe`: Allow lightweight simulated or real test inference through the proxy to immediately populate telemetry for Gemini tokens.

4. **Configurable Refresh Cadence (`backend/storage/database.py`, `frontend/js/app.js`, `frontend/js/widget.js`)**:
   - In `app_settings`, add `ui_refresh_interval_seconds` with a minimum of 30 seconds (default 30s; options: 30s, 60s, 90s, 120s, 180s, 300s).
   - Update `frontend/js/app.js` and `frontend/js/widget.js` to replace hardcoded 3-4s polling with the configured cadence.
   - Add a Cadence selector dropdown in the dashboard header or analytics controls.
   - Guarantee manual refresh buttons bypass the timer and trigger immediate polling.

5. **Frontend Dashboard Velocity Chart Granularity & Mode Toggles (`frontend/js/app.js`, `frontend/components/usage_gauge_card.html`)**:
   - Add bucket granularity control buttons: `[1m | 5m | 15m | 30m | 60m]`.
   - Add chart mode switch: `[📈 Cumulative Total] vs [⚡ Interval Delta]`.
   - Update SVG chart rendering to display discrete spikes in delta mode and running totals in cumulative mode.

6. **Mini Widget 3rd Mode (Interval Delta) (`frontend/mini_widget.html`, `frontend/js/widget.js`, `backend/tray/native_widget.py`)**:
   - Add 3rd mode button in `mini_widget.html`: `[⊞ Accounts] [📈 Trends] [⚡ Delta]`.
   - In Mode 3 (`interval`): plot discrete bucketed delta token usage from a zero baseline using real API data.
   - Update `native_widget.py` to support `view_mode="interval"` alongside `balances` and `trends`.

## 3. Verification Criteria
- [ ] Transparent proxy successfully intercepts Gemini completions, parses `usageMetadata`, and attributes tokens to the matching child token ID.
- [ ] `/api/usage/timeseries` accurately computes contiguous buckets for 1m, 5m, 15m, 30m, and 60m in both cumulative and interval_delta modes.
- [ ] UI polling interval adheres to configured cadence (>= 30 seconds), eliminating rapid DOM re-rendering.
- [ ] Widget 3-way toggle switches between Accounts, Cumulative Trends, and Interval Delta.
- [ ] All unit tests pass with 100% green execution.
