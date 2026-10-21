# Architecture Decision Record (ADR): Proxy Bridges UI Integration Guidance & Dynamic Bridge Configuration

**Document Identifier**: ADR-20261020-PROXY-BRIDGES-UI-CONFIG  
**Date**: 2026-10-20  
**Status**: Accepted  
**Authors**: Core Architecture & Agentic Engineering Team  
**Ticket Ref**: AIUM-707  

---

## 1. Context
Following the implementation of the secondary port Ollama emulator (AIUM-706), external autonomous platforms and client libraries can consume AI models through `http://127.0.0.1:8989` and the transparent proxy on `http://127.0.0.1:8766`.
However:
1. Users need clear instructions, copyable endpoints, and concrete code snippets in the UI for various consuming implementations (Ollama SDK, OpenAI SDK, LangChain, Open WebUI, MCP).
2. Ports and default quota limits were hardcoded or CLI-only, requiring database-backed dynamic configuration.
3. Connected clients that have not been manually added to `client_quotas` should be discovered automatically from usage and token window records so operators can block, unrestrict, or adjust quotas with one click.

---

## 2. Decision

### 2.1 UI Guidance Architecture
We will implement an interactive **Proxy Bridges & Implementation Guides** component in `frontend/components/provider_hub.html` (and linked from Settings), containing:
- Live endpoint status badges showing configured host and port.
- Tabbed implementation guides:
  - **Ollama Client / Apps**: Env vars (`OLLAMA_BASE_URL`), Python snippet, curl test.
  - **OpenAI Compatible**: Base URL (`/v1`), OpenAI client snippet, LangChain / Cursor instructions.
  - **MCP JSON-RPC 2.0**: Endpoint (`/api/mcp/rpc`), sample JSON-RPC 2.0 payload, tools overview.
  - **Transparent Proxy**: Instructions for Claude CLI / Gemini transparent interception.
- Single-click copy functionality for all endpoints and snippets.

### 2.2 Dynamic Configuration Architecture
- Persist bridge ports (`ollama_emulator_port`, `transparent_proxy_port`) and default quota limits (`default_session_window_minutes`, `default_session_token_limit`, `default_daily_token_limit`) in SQLite `app_settings`.
- Update `UsageDatabase.get_all_settings()` and `UsageDatabase.get_client_quota()` to read defaults dynamically from `app_settings`.
- In `run_monitor.py`, resolve ports from database settings if not explicitly overridden by CLI arguments.
- Expose a dedicated **Proxy Bridges & Network Ports Configuration** card in `frontend/components/settings_panel.html` that saves via `POST /api/settings`.

### 2.3 Integrated Client Discovery & Governance Architecture
- Extend client listing in `UsageDatabase` (`list_all_integrated_clients()` or enhanced `list_client_quotas()`) to query:
  - Configured quotas in `client_quotas`
  - Active burst windows in `client_token_windows`
  - Historic sessions in `usage_events`
- Enhance `TrafficGovernor.check_client_allowance()` to recognize explicit client blocks (`is_blocked = 1` or `priority = 0` / limit = 0) returning HTTP 403 Forbidden.
- Provide quick-action UI buttons:
  - **Block / Unblock**
  - **Unrestrict / Restrict**
  - **Temporary Elevated Bypass (+1h, +4h, +24h)**
  - **Reset Window Tokens**
  - **Edit Quotas & Alias**

---

## 3. Consequences
- **Positive**:
  - Developers and operators have immediate on-screen access to accurate integration snippets.
  - Bridge ports and burst limits can be adjusted directly from the web dashboard.
  - Complete visibility over every client integrating with the cluster with instant moderation controls.
- **Negative / Mitigations**:
  - Changing server listening ports requires restarting the service. We provide clear UI badges informing the user when a port change requires restart.
