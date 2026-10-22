# Architecture Decision Document: Full-Width Layout, Local Timezone Alignment & Claude Desktop Live Telemetry Ingestion

**Document Version**: 1.0.0  
**Date**: 2026-10-22  
**Status**: Approved  
**Related Ticket**: AIUM-905  

---

## 1. Context & Motivation
During operational testing on high-resolution widescreen monitors (1440p / 4K), users experienced significant whitespace on either side of the interface while experiencing horizontal overflow inside complex tabular views (Reports & Analytics, Agentic Sessions).

Concurrently, the telemetry curve ended at UTC 12:00 when the workstation's local time was 14:29 (UTC+2), and active background work on Claude was not appearing in the velocity chart or Today's Tokens count.

Investigating the workstation revealed that:
1. The user was interacting via **Claude Desktop** (Windows Store MSIX application `Claude_pzs8sxrjxfjjc`).
2. Claude Desktop caches session turns in `%LOCALAPPDATA%\Claude-Data\claude_pzs8sxrjxfjjc\IndexedDB` in Blink-Snappy compressed format containing V8-serialized assistant messages (`msg_01...`).
3. Claude Desktop stores OAuth access tokens (`sk-ant-oat01-...`) in `config.json` encrypted with Chromium `os_crypt` / Electron `safeStorage`.
4. Using Windows native DPAPI (`crypt32.dll`) and CNG (`bcrypt.dll`), these OAuth credentials can be decrypted in memory without any external libraries, enabling direct API calls to Anthropic's authoritative quota and profile endpoints (`https://api.anthropic.com/api/oauth/usage` and `https://api.anthropic.com/api/oauth/profile`).

---

## 2. Design Decisions

### 2.1 Full-Width Fluid Layout
- Remove `.container { max-width: 1400px; }` from `frontend/css/styles.css`.
- Replace with:
  ```css
  .container {
    width: 100%;
    max-width: none;
    padding: 1.25rem clamp(1rem, 2vw, 2.5rem);
    margin: 0;
  }
  ```
- Adjust header, grid rows, and table containers to expand to 100% of the viewport width.

### 2.2 Local System Timezone Bucket Generation
- In `backend/storage/database.py`, `get_granular_timeseries()` and `get_hierarchical_trends()` must format bin timestamps using `t_bin.astimezone()`:
  ```python
  t_local = t_bin.astimezone()
  labels.append(t_local.strftime(lbl_fmt))
  ```
- This ensures that when the user views the chart at 15:39 local time, the rightmost bucket label accurately reflects the current local hour/minute.

### 2.3 Live Direct Anthropic OAuth API Ingestion
- `ClaudeProvider` will maintain an automated OAuth interrogation routine:
  1. Inspect `Local State` in `%LOCALAPPDATA%\Claude-Data\claude_*\Local State` to obtain `os_crypt.encrypted_key`.
  2. Unprotect master key via `CryptUnprotectData` (`crypt32.dll`).
  3. Decrypt `oauth:tokenCacheV2` in `config.json` using `BCryptDecrypt` (`bcrypt.dll`) with `ChainingModeGCM`.
  4. Invoke `GET https://api.anthropic.com/api/oauth/usage` and `GET https://api.anthropic.com/api/oauth/profile`.
  5. Populate `session_remaining_pct`, `weekly_remaining_pct`, exact `reset_epoch`, and account metadata in `provider_snapshots` automatically.
  6. If network connectivity fails, fallback to parsing `%LOCALAPPDATA%\Claude-Data\claude_*\plan-usage-history.json`.

### 2.4 Pure-Python Blink-Snappy IndexedDB Turn Extraction
- Implement a zero-dependency 45-line Snappy decompressor (`snappy_decompress`) and ZigZag V8 varint integer decoder.
- Scan `%LOCALAPPDATA%\Claude-Data\claude_*\IndexedDB` (`.blob`, `.ldb`, `.log`) for `\xff\x11\x02` Blink-Snappy records.
- Deduplicate turns by Anthropic `message.id` (`msg_01...`) and ingest into SQLite `usage_events` with `source = 'desktop_app'` and `account_id = 'James Eckhardt'`.

### 2.5 Elimination of Manual Calibration UI
- Remove `#calibrate-claude-btn` from `frontend/components/comparison_panel.html`.
- Remove `#claude-quota-modal` markup and references in `frontend/index.html` and `frontend/js/app.js`.
- The system self-calibrates deterministically from live API data.
