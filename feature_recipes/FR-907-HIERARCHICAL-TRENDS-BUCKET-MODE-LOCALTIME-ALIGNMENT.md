# Feature Recipe FR-907: Hierarchical Trends Bucket, Mode & Local Time Alignment

**Ticket**: AIUM-907  
**Epic**: EPIC-PLATFORM-OVERHAUL  
**Priority**: Critical  
**Status**: In Progress  
**Standard**: ASD-STE100 Simplified Technical English  

---

## 1. Problem Statement

In the AI Usage Monitor Web UI:
1. The top-most chart under "Multi-Account Telemetry & Quota Comparison" -> "Claude (Anthropic)" (and other hierarchical trend charts) does not align with the "Token Velocity & Multi-Platform Telemetry Curves" chart or Mini Widget.
2. The hierarchical trend endpoint `/api/usage/trends/hierarchy` and backend method `get_hierarchical_trends` permanently use hardcoded 60-minute time buckets for the 24-hour window, ignoring user selections in the "Bucket" selector (e.g., 1m, 5m, 10m, 15m, 30m, 60m).
3. The hierarchical trend curve permanently renders in delta mode, ignoring the "Mode" selector ("Cumulative" vs. "Delta Bursts").
4. The hierarchical time keys are formatted as `%Y-%m-%dT%H` without minute values. This non-standard format causes JavaScript `new Date()` to return `Invalid Date`. The frontend falls back to raw unformatted UTC strings (e.g. `2026-10-23 13:00`), displaying GMT time instead of workstation local time (e.g. `15:00` SAST / UTC+2).

---

## 2. Technical Requirements

### 2.1 Backend Database Engine (`backend/storage/database.py`)
1. Extend `get_hierarchical_trends(provider, window, scope, bucket_minutes=None, mode="interval_delta")`:
   - Accept optional `bucket_minutes: Optional[int]`. Valid buckets are `(1, 5, 10, 15, 30, 60)`.
   - If provided and valid, dynamically compute `step_min = bucket_minutes` and `num_bins = win_mins // step_min`.
   - Cap `num_bins` to `<= 288` for windows exceeding 24 hours.
   - Accept `mode: str` (`"interval_delta"` or `"cumulative"`). If `"cumulative"`, convert all output series points into monotonically non-decreasing running sums.
   - Ensure `keys` are formatted as valid ISO 8601 strings with minute precision: `t.strftime("%Y-%m-%dT%H:%M")`.
   - Include `"bucket_minutes": step_min` and `"mode": mode_val` in the returned payload.

### 2.2 HTTP Server API (`backend/server/http_server.py`)
1. In handler for `GET /api/usage/trends/hierarchy`:
   - Extract `bucket_minutes` (integer) and `mode` (string) query parameters.
   - Pass `bucket_minutes` and `mode` to `srv.database.get_hierarchical_trends(...)`.

### 2.3 Frontend Engine (`frontend/js/app.js`)
1. In `loadAndRenderHierarchicalTrendChart(containerId, providerKey)`:
   - Read active `this.chartGranularity` and `this.chartMode`.
   - Include `bucket_minutes` and `mode` in the cache key and HTTP query string:
     `/api/usage/trends/hierarchy?provider=${providerKey}&window=${windowPeriod}&bucket_minutes=${bucketMinutes}&mode=${mode}&scope=${scope}`.
2. In `formatLocalTime(isoStr)`:
   - Handle timestamps without minutes (e.g., `YYYY-MM-DDTHH`) by automatically appending `:00` prior to parsing.
   - Convert successfully parsed dates to workstation local time (`HH:MM`).
3. In `changeChartGranularity(val)` and `changeChartMode(mode)`:
   - Invalidate `this.cachedHierarchicalTrends = {}`.
   - Re-render active hierarchical charts immediately.
4. In `renderMultiSeriesTrendChart(containerId, trendsData, providerKey)`:
   - Display active Window, Bucket, and Mode badges in the legend header.

---

## 3. Verification Criteria

1. Setting Bucket to 5m updates both Token Velocity and Claude hierarchical curves to 5m granularity.
2. Setting Mode to Cumulative updates both Token Velocity and Claude hierarchical curves to cumulative totals.
3. Time axis labels on the Claude hierarchical chart display workstation local time (e.g., 14:00/15:00) instead of GMT.
4. Full regression test suite passes with 0 failures and 0 errors.
