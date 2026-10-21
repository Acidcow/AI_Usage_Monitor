# Design Decision: LAN Service Discovery Scanner, Governed Proxy MCP Server & Multi-Node Traffic Manager

**Date**: 2026-10-16  
**Status**: Approved  
**Author**: Antigravity Core Team  
**Ticket**: AIUM-703  

---

## 1. Context & Problem Statement
As developers leverage multiple local and remote AI inference servers (e.g., shared team workstations, homelab GPU servers, or remote Ollama / vLLM clusters), two major challenges arise:
1. **Manual Endpoint Management & Lack of Discovery**: Developers must manually copy-paste IP addresses and ports. No automated discovery mechanism exists to find exposed AI runtimes on the local area network (LAN).
2. **Remote Machine Overwhelm & Lack of Governance**: Routing unthrottled concurrent requests from autonomous agents to a shared machine or peer's laptop causes VRAM thrashing, out-of-memory errors, and device unresponsiveness.
3. **Agent Integration Gap & Telemetry Blindspots**: Coding agents (Claude Code, Cursor, Windsurf, Antigravity) require standardized protocols (Model Context Protocol / MCP) to discover tools and query models. Requests dispatched directly bypass AI Usage Monitor's telemetry tracking, leaving gaps in dashboard cost, token, and quota graphs.

---

## 2. Decision & Architecture

### A. Zero-Dependency LAN Scanner (`backend/discovery/lan_scanner.py`)
- Utilize strictly Python standard library (`socket`, `urllib.request`, `concurrent.futures.ThreadPoolExecutor`).
- Auto-detect the host's active LAN subnet (e.g., `192.168.1.0/24`) and support custom CIDR or IP lists.
- Perform non-blocking socket sweeps (default 250ms timeout) across standard AI ports:
  - `11434` (Ollama)
  - `1234` (LM Studio)
  - `8000` / `8080` (vLLM, LocalAI, LiteLLM)
  - `5000` (Text Generation WebUI)
- Validate open ports via lightweight HTTP JSON fingerprinting (`/api/version`, `/api/tags`, `/v1/models`). Extract model manifests and verify the engine before classifying as a candidate node.

### B. Multi-Node Managed Registry (`backend/discovery/node_registry.py`)
- Persist discovered and user-approved remote nodes in SQLite (`managed_nodes` table).
- Support configurable parameters per node:
  - `max_concurrency`: Maximum concurrent active inference requests (default `1` or `2`).
  - `queue_timeout_seconds`: FIFO queue timeout before shedding traffic (default `30s`).
  - `priority`: Scheduling preference.
  - `status`: `ONLINE`, `BUSY`, `UNHEALTHY`, `OFFLINE`.

### C. Traffic Governor & Overwhelm Protection (`backend/discovery/traffic_governor.py`)
- Guard remote nodes using a `threading.Semaphore(max_concurrency)`.
- If a remote instance is operating at capacity, incoming requests enter a thread-safe FIFO queue rather than hitting the remote machine simultaneously.
- Circuit breaker automatically handles repeated network failures or HTTP 503s by transitioning the node to `UNHEALTHY` and shedding requests.
- All completions routed through the governor parse prompt/completion tokens, latency, and model names, recording them into `usage_events` with `provider="ollama"`.

### D. Model Context Protocol (MCP) Server (`backend/mcp/server.py`)
- Adhere to the JSON-RPC 2.0 Model Context Protocol (MCP) specification over standard I/O (`stdio`) and REST (`/api/mcp/rpc`).
- Expose standardized tools to agents:
  1. `scan_lan_ai_services`
  2. `list_managed_nodes`
  3. `register_managed_node`
  4. `generate_completion`
  5. `get_traffic_telemetry`
- Enables autonomous agents to dynamically discover available compute nodes and execute governed model prompts while guaranteeing full telemetry capture on the desktop dashboard and floating widget.
