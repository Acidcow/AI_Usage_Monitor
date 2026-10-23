# AI Usage Monitor - Release Notes v0.9.7

**Release Identifier**: `v0.9.7`  
**Release Date**: 2026-10-23  
**Epic**: `EPIC-PLATFORM-OVERHAUL`  
**Ticket**: `AIUM-907`  
**Ways of Work Version**: v1.0.0  

---

## Executive Summary

AI Usage Monitor `v0.9.7` addresses the discrepancy between the "Multi-Account Telemetry & Quota Comparison" -> "Claude (Anthropic)" hierarchical trend chart and the "Token Velocity & Multi-Platform Telemetry Curves" chart / native Mini Widget. It eliminates hardcoded 60-minute hierarchical aggregation locks, introduces dynamic bucket intervals (1m, 5m, 10m, 15m, 30m, 60m), supports both interval delta bursts and cumulative run curves, and standardizes full ISO 8601 timestamps to ensure accurate workstation local time localization.

---

## Key Capabilities & Changes

### 1. Dynamic Granularity & Bucket Synchronization
- **Elimination of 60m Hardcoded Window Lock**: Removed hardcoded 60-minute aggregation steps from `DatabaseEngine.get_hierarchical_trends`.
- **Dynamic Bucket Sizing**: `get_hierarchical_trends` now accepts `bucket_minutes: Optional[int] = None` and computes dynamic bin counts (`num_bins = win_mins // step_min`, capped to `<= 288` bins for multi-day spans). For a 24-hour window at 5m bucket granularity, exactly 288 bins are generated, matching the Token Velocity curve and Mini Widget.
- **Query Parameter Forwarding**: Backend endpoint `GET /api/usage/trends/hierarchy` now parses and forwards `bucket_minutes` and `mode` directly to `get_hierarchical_trends`.
- **Frontend Granularity Propagation**: `loadAndRenderHierarchicalTrendChart` and synthetic trend builders in `frontend/js/app.js` now include `bucket_minutes` and `mode` in all requests and cache keys. Changing the Bucket dropdown automatically flushes the cache and re-renders the hierarchical chart in real time.

### 2. Delta Bursts vs. Cumulative Run Mode Alignment
- **Dynamic Mode Evaluation**: Added full support for `mode="cumulative"` to `get_hierarchical_trends`. When the user selects "Cumulative Run", hierarchical series (provider totals, account tiers, and individual child series) compute cumulative running totals over the window, producing monotonically non-decreasing curves.
- **Informative Status Badges**: Added contextual badges to the multi-series legend strip and drill-down row headers indicating the active `Window`, `Bucket`, and `Mode` (`Delta Bursts` vs. `Cumulative Run`).

### 3. Workstation Local Timezone Alignment
- **Canonical ISO 8601 Key Formatting**: In `database.py`, `keys` formatting was standardized to minute-precision ISO 8601 (`t.strftime("%Y-%m-%dT%H:%M")`), eliminating truncated `%Y-%m-%dT%H` strings.
- **Robust V8/Chromium ISO Parsing**: Updated `formatLocalTime` and `formatLocalDateTime` in `app.js` to automatically guard against truncated hourly timestamps. Valid ISO strings parse reliably across all browsers and correctly convert UTC database timestamps into workstation local time (e.g. SAST UTC+2), matching the Token Velocity X-axis labels.

---

## Verification & Test Results

- **Feature Test Suite**: `tests/test_hierarchical_trends_bucket_mode_localtime_alignment.py` (20/20 passed, 100%).
- **Full Platform Regression Suite**: `python dev_tools/manage_roadmap.py run-tests` (446/446 passed, 0 failures, 0 errors, 100% GREEN).
- **Live Endpoint Interrogation**: Verified live responses from `GET /api/usage/trends/hierarchy?provider=claude&window=24h&bucket_minutes=5&mode=interval_delta` (288 bins) and `mode=cumulative` (monotonically non-decreasing curve).
- **Zero External Dependencies**: Zero npm or pip dependencies added; strictly standard library Python and vanilla CSS/ES6.
