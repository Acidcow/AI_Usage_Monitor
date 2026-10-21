# Architectural Design Decision: Multi-Dimensional Telemetry Capture, Multi-Instance Rollups, Proxy Source Correlation, Zero Double-Accounting & Dynamic Pivoting

**Date**: 2026-10-21  
**Status**: Approved  
**Context**: Ticket AIUM-801 / Feature Recipe FR-801 / v2.0 Architecture  

---

## 1. Problem Statement
In real-world agentic environments, developers and teams interact with AI platforms through multiple channels simultaneously:
1. **Direct API calls** (e.g. CLI tools or apps hitting Claude/OpenAI endpoints with API keys).
2. **Proxied calls** (traffic transparently routed through local port 8766 or Ollama port 8989).
3. **Local engines and background syncs** (Ollama log scanning, periodic polling).
4. **Multiple accounts and multiple instances** (e.g., several Google AI Studio developer keys, team vs personal Claude accounts, local GPU vs LAN worker nodes).

Without explicit source tagging and temporal correlation, systems suffer from **double-accounting** (e.g., an agentic session intercepted by the proxy in real-time, then scanned from logs or polled via API). Furthermore, users lack the ability to pivot between different operational perspectives: "Show me tokens by physical instance", "Show me proxy vs direct split", "Show me tokens per client IP across models".

Additionally, minor misalignments between the Web Dashboard and the Taskbar Mini Widget (Ollama sparklines, theme re-coloring, Claude card height) degrade UX cohesion.

---

## 2. Decision & Architecture

### 2.1 Event Source Discrimination & Correlation Keying
In `usage_events`, every event is explicitly tagged with:
- `source`: `'proxy'` | `'emulator'` | `'direct'` | `'log_scanner'`
- `instance_id`: physical hardware node or instance identifier (default `'local'`)
- `external_id`: upstream API request/response ID (`msg_...`, `chatcmpl-...`, or hash)
- `is_proxied`: boolean integer flag (`1` for proxied/emulated, `0` for direct)

### 2.2 Deduplication Protocol (Zero Double-Accounting)
When recording usage events:
1. If `external_id` matches an existing record:
   - The event is correlated. Metadata (such as client IP, user name, or account ID) is merged, and token counts are not duplicated.
2. If `session_id`, `provider`, `model`, and token metrics match an event recorded within a ±60-second window:
   - The event is identified as the same request seen across layers (e.g. proxy stream + log scanner).
   - The existing event is preserved as the canonical entry; duplicate token accumulation is prevented.

### 2.3 Multi-Instance & Multi-Account Hierarchical Rollups
For all platforms:
- **Platform Total** = $\sum \text{Accounts}$ = $\sum \text{Instances}$ = $\sum \text{Models}$
- Distinct accounts report individual token burn, session counts, and cost.
- Distinct instances (e.g. `local` vs remote worker node) report their dedicated throughput.
- Grouping levels maintain strict mathematical parity: parent totals always equal the exact sum of their children.

### 2.4 Multi-Dimensional Pivot REST API
`GET /api/usage/pivot` dynamically groups by any combination of:
- `platform`, `account`, `instance`, `model`, `client`, `source`, `group`
Filtering by `window` (`1h`, `24h`, `7d`, `30d`, `all`), `filter_source`, and `filter_client` allows slicing the entire estate without altering underlying stored events.

### 2.5 Taskbar Mini Widget & Web UI Unification
- **Ollama Model Series Normalization**: Series IDs in `/api/usage/timeseries` provide both `ollama_model_{name}` and `{name}` so both widget implementations immediately display real non-zero curves.
- **Live Theme Frame Application**: Native widget immediately invokes `self.apply_theme()` upon receiving settings updates.
- **Claude Individual Quota Card Height**: Set to `66px` when in individual tracking mode.
- **HTML Widget Hover Events**: Hook `onmouseenter` and `onmouseleave` to activate the weather hover flyout.

---

## 3. Backward Compatibility & Zero Supply-Chain Risk
- Database schema changes execute via idempotent `ALTER TABLE ADD COLUMN` with safe defaults.
- All implementations strictly use the Python 3 Standard Library (`sqlite3`, `http.server`, `urllib.request`, `json`, `time`, `threading`).
