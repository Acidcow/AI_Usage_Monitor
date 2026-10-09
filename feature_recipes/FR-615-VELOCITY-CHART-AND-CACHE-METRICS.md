# Feature Recipe FR-615: Multi-Platform Velocity Chart Clarification, Idle Zero Baselines & Cache Token Metrics

## 1. Goal
Disambiguate overlapping curves in the 24-hour Token Velocity chart by adding per-platform token summary badges in the legend pills, rendering clean Option A zero baselines for idle platforms, providing comprehensive multi-platform hover inspection tooltips, and enhancing token accounting with distinct `cache_creation_tokens` and `cache_read_tokens` tracking for full parity with CCUSAGE.

## 2. Technical Requirements
1. **Multi-Platform Velocity Chart Clarification**:
   - In `frontend/js/app.js:renderSvgChart(hourly)`:
     - Compute total 24h tokens burned per platform (`claude`, `gemini`, `chatgpt`, `ollama`, `copilot`) and combined total.
     - Update legend pills to display real token volume badges (e.g., `Claude: 25.3k tok`, `Google Gemini: 0 t (idle)`).
     - Render clean zero baseline paths for idle platforms with subtle dashed styling and opacity so they are visible and interactable.
     - When only 1 platform has data (e.g. Claude represents 100% of the total), disambiguate the "Total Combined" line with distinct styling and explicit tooltips (`Total: 25,285 t (Claude: 100%)`).
     - Add interactive hover flyout / inspection line showing exact per-platform token counts for each hour.

2. **Cache Token Metrics (CCUSAGE Parity)**:
   - In `backend/storage/database.py`:
     - Add columns `cache_creation_tokens` and `cache_read_tokens` (both `INTEGER DEFAULT 0`) to `usage_events`.
     - Update `record_usage_event()` to accept and persist `cache_creation_tokens` and `cache_read_tokens`.
     - Update `query_historical_reports()` to aggregate `SUM(cache_creation_tokens)` and `SUM(cache_read_tokens)`.
   - In `backend/providers/claude.py`:
     - In `scan_local_logs()`, pass `cache_create` and `cache_read` into `record_usage_event()`.
     - Support rescanning or backfilling cache tokens.
   - In `frontend/components/historical_reports_card.html` and `frontend/js/app.js`:
     - Add table header and cell columns for `Cache Create` and `Cache Read` tokens.
     - Display cache tokens in the report view.

## 3. Verification Criteria
- [x] 24-hour velocity chart legend pills show accurate 24h token totals and idle badges.
- [x] Idle platforms (0 tokens) render clean zero baselines and can be isolated via legend clicks.
- [x] When 1 provider represents 100% of total tokens, tooltips and styling clearly state that the total equals that provider's burn without visual confusion.
- [x] `usage_events` records `cache_creation_tokens` and `cache_read_tokens`.
- [x] Historical reports display `Cache Create` and `Cache Read` token metrics alongside input/output.
- [x] All unit tests pass with 100% green rate.
