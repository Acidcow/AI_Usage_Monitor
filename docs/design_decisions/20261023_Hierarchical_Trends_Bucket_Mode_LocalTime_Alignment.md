# Architecture Decision Document: Hierarchical Trends Bucket, Mode & Local Time Alignment

**Date**: 2026-10-23  
**Status**: Approved  
**Author**: Antigravity  
**Context**: Ticket AIUM-907 / FR-907  

---

## 1. Context and Problem Statement

Users observed a visual and temporal discrepancy between the "Token Velocity & Multi-Platform Telemetry Curves" chart (and native mini widget) and the "Multi-Account Telemetry & Quota Comparison" -> "Claude (Anthropic)" hierarchical trend curve.

Specifically:
1. When selecting different aggregation bucket sizes (e.g. 5 minutes), the Token Velocity chart rendered high-resolution burst curves, while the Claude hierarchical chart remained locked to 60-minute bins.
2. When switching from "Delta Bursts (Trend)" to "Cumulative Run", the Token Velocity chart switched to running totals, while the Claude hierarchical chart remained in delta mode.
3. The X-axis time labels on the Claude hierarchical chart displayed GMT/UTC hours (e.g. 13:00) instead of local workstation time (15:00 UTC+2), because the backend returned ISO date strings lacking minute tokens (`%Y-%m-%dT%H`), causing client-side `new Date()` parsing to fail and fall back to the un-localized UTC string.

---

## 2. Decision

1. **Parameterize `get_hierarchical_trends`**:
   - Add `bucket_minutes: Optional[int] = None` and `mode: str = "interval_delta"` to `get_hierarchical_trends` in `UsageDatabase`.
   - Compute `step_min` and `num_bins` using the exact same window mapping and bin constraints as `get_granular_timeseries`, ensuring mathematical parity across both charts.
   - If `mode == "cumulative"`, compute running cumulative sums for all hierarchical series (`total`, `individual`, `team`, `model`, `locality`).
2. **Canonical ISO 8601 Keys**:
   - Format all trend bin keys as `%Y-%m-%dT%H:%M`. This guarantees valid ISO 8601 formatting for client `Date` objects regardless of browser engine.
3. **HTTP Server Wiring**:
   - Update `/api/usage/trends/hierarchy` in `backend/server/http_server.py` to extract `bucket_minutes` and `mode` query arguments and forward them to the database engine.
4. **Client-Side Synchronization**:
   - In `app.js`, include `bucket_minutes` and `mode` in the hierarchical trend request and cache key.
   - Clear cache and re-render open hierarchical charts whenever granularity or mode changes.
   - Harden `formatLocalTime` to normalize any timestamp string before parsing.

---

## 3. Consequences

- **Positive**:
  - The Claude hierarchical chart, Token Velocity chart, and native mini widget now reflect identical burst timelines, bucket resolutions, and modes.
  - Time labels display the user's workstation local time accurately across all user interfaces.
  - Zero external dependencies are added.
