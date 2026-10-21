# Feature Recipe: FR-707 Proxy Bridges UI Integration Guidance & Dynamic Bridge Configuration

**Ticket ID**: AIUM-707  
**Epic**: EPIC-DISTRIBUTED-TELEMETRY  
**Status**: In Progress  
**Standard**: ASD-STE100 Compliant Specification  

---

## 1. Context and Problem Statement
AI Usage Monitor provides two primary proxy bridges:
1. Secondary Ollama API Emulator & Worker Node Bridge (port 8989) supporting Ollama REST, OpenAI compatibility, and MCP JSON-RPC 2.0.
2. Transparent Proxy (port 8766) supporting Claude CLI and Google Gemini streaming telemetry.

Users and developers currently lack direct, on-screen guidance in the web dashboard explaining how to configure external platforms (e.g. LangChain, Cursor, Python `ollama` SDK, Open WebUI, custom agent runtimes) to connect to these bridges. Furthermore, bridge ports (8989, 8766) and default burst window parameters (15m window, 25k session limit, 250k daily limit) are currently hard-coded or CLI-only, and clients that connect to the bridges without explicit database policies are not dynamically discovered and listed in the UI with instant restriction/unrestriction controls.

---

## 2. Technical Requirements

### 2.1 UI Proxy Bridge Implementation Guides
1. Provide a dedicated, tabbed **Proxy Bridges & Implementation Guides** component in the dashboard:
   - **Ollama Client Guide**: Copyable environment variables (`OLLAMA_BASE_URL`), Python `ollama.Client` code snippet, Open WebUI setup instructions, and curl test command.
   - **OpenAI Compatible SDK Guide**: Copyable Base URL (`http://<host>:<port>/v1`), Python `OpenAI` client snippet, Cursor / LangChain / LlamaIndex instructions.
   - **MCP JSON-RPC 2.0 Guide**: Copyable JSON-RPC endpoint (`http://<host>:<port>/api/mcp/rpc`), sample `tools/list` payload, and client config snippets.
   - **Transparent Proxy Guide**: Instructions for routing live Claude CLI and Gemini requests through port 8766.
2. Provide 1-click "Copy Endpoint" and "Copy Code Snippet" buttons with live visual feedback.
3. Automatically interpolate currently configured host and port numbers into all displayed endpoints and snippets.

### 2.2 Dynamic Bridge Port & Quota Configuration
1. Store proxy bridge network ports and default client quota limits in SQLite `app_settings`:
   - `ollama_emulator_port` (default: 8989)
   - `transparent_proxy_port` (default: 8766)
   - `default_session_window_minutes` (default: 15)
   - `default_session_token_limit` (default: 25000)
   - `default_daily_token_limit` (default: 250000)
2. Expose these settings in the Settings panel under **Proxy Bridges & Network Ports Configuration**.
3. Allow users to update and save these parameters through `POST /api/settings`.
4. In `run_monitor.py`, load the configured ports dynamically from database settings when CLI arguments use default values.
5. In `UsageDatabase.get_client_quota()`, dynamically load default quota parameters from `app_settings` instead of static constants.

### 2.3 Integrated Client Discovery & Governance Controls
1. Enhance client discovery so that any client IP recorded in `client_quotas`, `client_token_windows`, or `usage_events` is listed.
2. For each client entry, display:
   - Client IP and editable Computer Alias.
   - Current sliding burst window token usage and progress bar.
   - 24-hour rolling daily quota usage and progress bar.
   - Current status: Governed, Unrestricted, Temporary Bypass Active, or Blocked.
3. Provide one-click governance actions per client:
   - **Quick Block**: Immediately set client limit to 0 tokens / blocked flag, returning HTTP 403 Forbidden to that client IP.
   - **Quick Unrestrict**: Toggle `is_unrestricted = 1` for unlimited throughput.
   - **Temporary Bypass**: Grant +1h, +4h, or +24h elevated bypass with live countdown.
   - **Reset Usage**: Clear active token windows to reset burst usage immediately.
   - **Configure Quota**: Custom window minutes, token ceilings, and notes.

---

## 3. Verification Criteria
1. At least 20 unit and integration tests verifying:
   - Dynamic port storage and retrieval in `app_settings`.
   - Default quota retrieval from `app_settings`.
   - Client discovery aggregating `client_quotas`, `client_token_windows`, and `usage_events`.
   - Block / unrestrict / bypass enforcement in `TrafficGovernor`.
   - HTTP REST API endpoints for bridge guidance info and client governance.
2. 100% test pass rate across the full project test suite.
