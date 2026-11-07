# Feature Recipe FR-1010: Rolling 5h/7d Burn-Rate Pacing Forecaster, Cross-Tab Quota Alignment & Context-Window Bloat Detector

## 1. Goal
Implement predictive quota pacing analytics, ensure 100% quota alignment between the Dashboard and Capacity Analytics tabs, and provide live heuristic detection of multi-turn conversation context-window bloat and runaway subagent loops across all connected AI providers without external dependencies.

## 2. Technical Requirements

### 2.1 Cross-Tab Quota Alignment
- Ensure `get_provider_hierarchies()` on `UsageDatabase` reads and exposes canonical provider quota metrics identical to the primary Dashboard:
  - `session_remaining_pct` and `session_balance_remaining_pct`
  - `weekly_remaining_pct` and `weekly_balance_remaining_pct`
  - `session_tokens_used` and `session_tokens_limit`
  - `session_reset_str` (e.g., `"Resets in 3h 15m"`, `"5h rolling window"`)
  - `reset_epoch` (UNIX timestamp float)

### 2.2 Rolling 5h/7d Burn-Rate Pacing Forecaster
- Implement `compute_quota_pacing_forecast(provider: str = "claude") -> Dict[str, Any]` on `ThroughputEngine` / `ThroughputAnalyticsEngine`:
  - Calculate rolling token velocity (`tokens_per_minute`) using sliding-window intervals (prioritizing 30-minute burst velocity, falling back to 5-hour rolling velocity).
  - Calculate `estimated_minutes_to_exhaustion` (`remaining_tokens / tokens_per_minute` when `tokens_per_minute > 0`, else `None`).
  - Parse `minutes_until_reset` from countdown strings (`"Resets in 3h 15m"`), ISO timestamps, or epoch seconds, defaulting to `300.0` minutes if unknown.
  - Determine operational pacing status:
    - `IDLE`: `tokens_per_minute == 0`
    - `IMPENDING_LOCKOUT`: `estimated_minutes_to_exhaustion < minutes_until_reset * 0.75`
    - `WARNING_HIGH_BURN`: `estimated_minutes_to_exhaustion < minutes_until_reset`
    - `SUSTAINABLE`: `estimated_minutes_to_exhaustion >= minutes_until_reset`
  - Output rich badge labels (e.g. `"🟢 Sustainable Pace"`, `"🟡 High Burn Warning"`, `"🔴 Lockout Before Reset"`, `"⚪ Idle (No Active Burn)"`) and actionable user recommendations.

### 2.3 Context-Window Bloat & Runaway Loop Detector
- Implement `detect_context_bloat_and_loops(hours: int = 24) -> List[Dict[str, Any]]` on `ThroughputEngine`:
  - Group multi-turn usage events by `session_id` ordered chronologically.
  - Flag **`CONTEXT_BLOAT`** when across $\ge 4$ consecutive turns, `input_tokens` grows by $> 40\%$ on average per turn while `output_tokens` remains $< 20\%$ of `input_tokens` (indicating uncompacted conversation history where `/compact` is needed).
  - Flag **`AGENT_RUNAWAY_LOOP`** when $\ge 8$ turns occur within a `120-second` window inside the same session.
  - Provide actionable suggestions (e.g., recommend `/compact` for bloat; abort or throttle subagent for loops).

### 2.4 Endpoints & Frontend Component Integration
- Include `quota_pacing` and `context_anomalies` payloads within `compute_throughput_metrics()` and `compute_capacity_forecast()`.
- Add `#capacity-pacing-bloat-panel` section to `frontend/components/capacity_analytics.html` while preserving all existing component element IDs (`cap-velocity-val`, `cap-burst-val`, `cap-burst-sub`, `cap-rolling24-val`, `cap-savings-val`, `cap-forecast-tbody`, `cap-recommendations-container`).

## 3. Verification Criteria
- Comprehensive test suite in `tests/test_quota_pacing_and_bloat_detector.py` with $\ge 20$ unit tests.
- 100% test pass rate across:
  - Cross-tab quota metric alignment.
  - Reset countdown string, epoch, and ISO parsing.
  - Pacing states (`IDLE`, `SUSTAINABLE`, `WARNING_HIGH_BURN`, `IMPENDING_LOCKOUT`).
  - Context bloat detection and false-positive immunity on healthy sessions.
  - Runaway loop detection and threshold boundaries.
- Zero external dependencies. Python standard library only.
