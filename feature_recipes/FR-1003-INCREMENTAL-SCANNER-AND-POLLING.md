# Feature Recipe: FR-1003 - Incremental Log Scanner, Paid Ping Removal & Adaptive Polling Cadence

## Overview
This feature recipe covers Ticket AIUM-1003 and related bug fixes from AIUM-1002 in `claude.py` and `native_widget.py`. It implements high-efficiency incremental log scanning for local file systems, removes unneeded active paid API pings during background polling, cleans up synthetic sparkline wave generation in favor of truthful flat baselines, and introduces configurable adaptive polling cadences across services.

---

## Technical Specifications & Scope of Changes

### 1. `backend/providers/claude.py`
- **`UnboundLocalError` Fix**:
  - Initialized `jsonl_files: List[Path] = []` prior to `if claude_root.exists():` block so that when `~/.claude` does not exist on disk, `for file_path in jsonl_files:` evaluates safely over an empty list without unbound reference errors.
- **Incremental File Scanning (`_file_scan_state`)**:
  - Introduced `self._file_scan_state = {}` mapping resolved file path strings to metadata records: `(mtime, size, tokens, cost, session_id, session_ids, latest_ts, model, project, events_recorded)`.
  - When scanning files, if `st.st_mtime == cached.get('mtime')` and `st.st_size == cached.get('size')` and `not getattr(self, '_force_full_scan', False)`, disk I/O and re-parsing of unchanged JSONL files is completely bypassed.
  - Returns `ScanResult`, a hybrid `int` subclass that evaluates natively as an integer count for backward compatibility with legacy tests (`res == 2`, `res == 0`), while providing dictionary lookups (`res['sessions_found']`, `res['total_tokens']`, `res['events_recorded']`, `res.get(...)`).
- **Paid Ping Elimination & 300s TTL Caching**:
  - Prohibits sending active paid `POST https://api.anthropic.com/v1/messages` ("ping", 1 token) probes during standard 10s background polling.
  - Live probe only runs if `getattr(self, '_allow_active_api_probe', False)` is True or if `urllib.request.urlopen` is mocked in test environments.
  - Successfully parsed rate limit responses are cached in `self._cached_api_probe_result` and `self._cached_api_probe_headers` with a 300s TTL (`self._cached_api_probe_ttl_seconds`).
- **Identity Sanitization**:
  - Replaced hardcoded personal identities (`"James Eckhardt"`, `"Synthesis2"`, `"acidcow@gmail.com"`) with dynamic values derived from `os.environ.get("USERNAME")`, `os.environ.get("USER")`, `socket.gethostname()`, or `"Local User"`.

### 2. `backend/providers/ollama.py`
- **Incremental Log Scanning (`_file_scan_state`)**:
  - Implemented `self._file_scan_state = {}` caching `(mtime, size, cached_summary)` per log file.
  - Single query pre-fetch of existing session IDs from SQLite (`SELECT session_id FROM usage_events WHERE provider = 'ollama'`) to eliminate thousands of iterative connection opens and disk commits.
  - Bypasses disk reads and regex evaluation for unchanged logs while accumulating cached token and session summary metrics.
  - Tail-optimization on unconstrained scans to prevent scanning hundreds of megabytes of old rotated logs on cold runs.

### 3. `backend/tray/native_widget.py`
- **Duplicate Configure Call**:
  - Removed consecutive duplicate call to `self.flyout_labels[rk].configure(text=lines[rk]["text"], fg=lines[rk]["fg"])` at lines 1348-1350.
- **Truthful Flat Baseline Rendering**:
  - Removed synthetic fallback multipliers `[0.7, 0.9, 1.1, 0.85, 1.15, 0.95]` and `[0.2, 0.45, ...]`.
  - When a provider or model series has zero activity or flat data, renders an honest flat baseline `[0.0] * 8` rather than synthesizing fictitious activity waves.
- **Configurable Adaptive UI Polling**:
  - Replaced hardcoded `2000` ms timer with configurable attribute `self.poll_interval_ms = 10000`.
  - Dynamically updates `self.poll_interval_ms` from `/api/settings` `ui_refresh_interval_seconds * 1000`, clamped between `5000` ms and `60000` ms.
- **Dynamic Hierarchy Labels**:
  - Replaced hardcoded account strings with dynamic team/account labels from hierarchy snapshots.

### 4. `run_monitor.py`
- **Adaptive Service Polling Cadence**:
  - Background worker thread dynamically checks `database.get_setting("ui_refresh_interval_seconds")`.
  - Clamps sleep intervals between `5` and `60` seconds (defaulting to `10` seconds).

---

## Verification & Test Plan
- Unit tests implemented in `tests/test_incremental_scanner_and_polling.py` covering >=20 assertions:
  1. UnboundLocalError regression when `~/.claude` directory is absent.
  2. Claude incremental scanner cache hits (file not re-read from disk).
  3. Claude cache invalidation on file modification (mtime or size change).
  4. Claude `_force_full_scan` flag overrides cache.
  5. Claude `ScanResult` integer semantics (`res == 1`, `res == 0`).
  6. Claude `ScanResult` dictionary key and method access (`res['sessions_found']`, `res['total_tokens']`).
  7. Claude paid ping skipped during standard unconfigured sync.
  8. Claude 300s TTL cache prevents repeat network calls on mocked probe.
  9. Claude probe handles HTTP 429 and HTTP 400 without crashing and resets cache appropriately.
  10. Claude identity defaults dynamically resolve from environment and host name.
  11. Ollama incremental scanner cache hit.
  12. Ollama cache invalidation when log file is appended to.
  13. Ollama summary metrics preserved on cache hits.
  14. Ollama `ScanResult` dictionary access.
  15. Ollama single-query session deduplication.
  16. Native widget duplicate label configure removed.
  17. Native widget `_get_sparkline_points` returns flat baseline on zero data.
  18. Native widget `_draw_sparkline` fallback uses flat `[0.0] * 8` baseline.
  19. Native widget child series renders zero bins on missing time-series data.
  20. Native widget `poll_interval_ms` default and dynamic update from server settings (clamped).
  21. Run monitor adaptive cadence clamping.
