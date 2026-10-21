# Design Decision: Granular Time-Series Aggregation, Cadence Control, Delta Widget Mode & Gemini Proxy Ingestion

**Date**: 2026-10-15  
**Status**: Approved  
**Author**: Antigravity Core Team  
**Ticket**: AIUM-617  

---

## 1. Context & Problem Statement
Users observed two key operational limitations:
1. **Google Gemini Idle State**: Gemini accounts and child keys (`tok_gem_flash`, `tok_gem_pro`, etc.) remained flatlined at `0 tokens` because Google AI Studio lacks a retrospective usage query API, browser chat and internal IDE agents bypass local developer keys, and direct API calls bypassed the monitor without proxy interception.
2. **Chart Resolution, Visual Jumpiness, and Lack of Delta View**:
   - The velocity chart only supported coarse 1-hour chunks (`substr(recorded_at, 1, 13)`).
   - Polling loops executed every 3-4 seconds, causing rapid visual DOM churn.
   - The widget and dashboard only rendered cumulative curves (monotonically increasing to the right), preventing users from observing discrete burst spikes and idle troughs within specific intervals (1m to 60m).

---

## 2. Decision & Architecture

### A. Dual-Provider Transparent Proxy Ingestion (Port 8766)
- Expand `TransparentProxyServer` to detect both Anthropic (`/v1/messages`) and Google Gemini (`/v1beta/models/...:generateContent` or requests with `key=` / `x-goog-api-key`).
- Forward Gemini requests to `https://generativelanguage.googleapis.com`.
- Intercept response JSON, extract `usageMetadata` (`promptTokenCount`, `candidatesTokenCount`, `totalTokenCount`), map the active API key to the user's named child token ID (`tok_gem_flash`, `tok_gem_pro`, etc.), and record directly to `usage_events`.
- Support mock header `x-mock-gemini-response` for deterministic automated verification.

### B. Contiguous Granular Time-Series Engine
- Implement `UsageDatabase.get_granular_timeseries(provider=None, window="24h", bucket_minutes=5, mode="cumulative", scope="individual")`.
- Valid bucket intervals: `1`, `5`, `10`, `15`, `30`, `60` minutes.
- Valid modes:
  - `"cumulative"`: Running sum total across the timeline.
  - `"interval_delta"`: Discrete token consumption within each individual bucket, resetting to zero for idle intervals.
- Generates a gap-free timeline continuum: buckets with no activity receive `0 tokens`, eliminating disjointed charts.

### C. Configurable Polling Cadence
- Introduce `ui_refresh_interval_seconds` in `app_settings` (minimum 30 seconds, maximum 300 seconds, default 30 seconds).
- Dashboard and widget timers respect this configuration to eliminate DOM flicker while allowing immediate on-demand manual refresh.

### D. Tri-Mode Desktop Widget
- Mode 1: `⊞ Accounts` (Dual-bar session/weekly progress).
- Mode 2: `📈 Trends` (Cumulative usage curve).
- Mode 3: `⚡ Interval` (Bucketed delta token usage from zero baseline).
