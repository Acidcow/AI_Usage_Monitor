# Feature Recipe FR-703: LAN Service Discovery, Governed Proxy MCP Server & Multi-Node Traffic Manager

## 1. Goal
Provide zero-dependency automated local network (LAN) scanning to discover exposed AI engines (Ollama, LM Studio, vLLM, and OpenAI-compatible inference servers). Maintain a managed remote node registry with user-configured concurrency ceilings and queue policies to prevent overloading remote machines. Expose a standards-compliant Model Context Protocol (MCP) server (JSON-RPC 2.0) that agents (Claude Code, Cursor, Windsurf, Antigravity) can connect to for tool execution, managed completions, and node discovery. Ingest all proxied traffic telemetry into SQLite for real-time visualization on the web dashboard and floating widget.

## 2. Technical Requirements

### 1. LAN Service Discovery Engine (`backend/discovery/lan_scanner.py`)
- Zero external dependencies: rely strictly on Python standard library (`socket`, `urllib.request`, `concurrent.futures.ThreadPoolExecutor`).
- Auto-detect local host IPv4 address and default `/24` subnet (e.g. `192.168.1.0/24`) with support for user-specified CIDRs or IP ranges.
- Probe standard AI service ports with fast non-blocking socket connect timeouts (default 250ms):
  - Port `11434`: Ollama (`GET /api/version` and `GET /api/tags`)
  - Port `1234`: LM Studio (`GET /v1/models`)
  - Port `8000` / `8080`: vLLM / LocalAI / LiteLLM (`GET /v1/models` or `GET /health`)
  - Port `5000`: Text Generation WebUI (`GET /v1/models`)
- Safe HTTP Fingerprinting: Validate returned JSON manifests to confirm active model catalog, parameter sizes, and server engine identity. Ignore non-LLM services.
- Provide structured candidate node dictionaries: `{"ip": str, "port": int, "engine": str, "version": str, "models": list, "latency_ms": float}`.

### 2. Multi-Node Managed Registry (`backend/discovery/node_registry.py`)
- Manage active and candidate AI nodes stored in SQLite (`managed_nodes` table).
- Node schema:
  - `id`: Unique identifier (e.g. `node_ollama_192_168_1_45_11434`)
  - `name`: User-friendly display label (e.g. "Workstation GPU 4090")
  - `engine`: Engine type (`ollama`, `lmstudio`, `vllm`, `generic_openai`)
  - `endpoint`: Base URL (e.g. `http://192.168.1.45:11434`)
  - `max_concurrency`: Max simultaneous active requests (default `1`, configurable `1-10`)
  - `queue_timeout_seconds`: Max seconds a request will wait before timeout (default `30s`)
  - `priority`: Scheduling weight (integer `1-10`)
  - `status`: `ONLINE`, `BUSY`, `UNHEALTHY`, `OFFLINE`
  - `models`: Serialized list of available models on the node
  - `created_at`, `updated_at`, `last_seen_at`
- Provide CRUD operations: `register_node()`, `get_node()`, `list_nodes()`, `update_node()`, `delete_node()`, `update_node_health()`.

### 3. Traffic Manager & Resource Governor (`backend/discovery/traffic_governor.py`)
- Implement non-overwhelm protection per remote node using `threading.Semaphore(max_concurrency)` and thread-safe request queues.
- Prevent VRAM exhaustion and thread starvation on remote machines:
  - When active requests equal `max_concurrency`, enqueue subsequent requests up to `queue_timeout_seconds`.
  - If timeout expires before acquiring semaphore, reject cleanly with HTTP 429 / queue timeout error without sending traffic upstream.
- Circuit breaker: Record failure counters on consecutive 5xx errors or connection timeouts. Temporarily mark node `UNHEALTHY` and retry after a cooldown window.
- Telemetry Ingestion:
  - Intercept prompt tokens, completion tokens, time-to-first-token (TTFT), queue duration, and total latency.
  - Ingest directly into `usage_events` with `provider="ollama"`, `model=...`, `session_id=...`, `estimated_cost=0.0`.
  - Calculate throughput (tokens/sec) and aggregate into provider snapshots.

### 4. Model Context Protocol (MCP) Server (`backend/mcp/server.py`)
- Implement JSON-RPC 2.0 MCP protocol specifications over standard input/output (`stdio`) and callable programmatically.
- Support core MCP RPC methods:
  - `initialize`: Returns protocol version (`2024-11-05`), server capabilities (tools, resources), and server metadata.
  - `notifications/initialized`: Acknowledges initialization.
  - `tools/list`: Lists exposed tools with strict JSON Schema definitions:
    1. `scan_lan_ai_services`: Trigger network scan for available AI hosts.
    2. `list_managed_nodes`: Query all managed nodes, models, health, and queue status.
    3. `register_managed_node`: Add a discovered node to the managed pool.
    4. `generate_completion`: Run completion through the traffic governor with queue protection and token logging.
    5. `get_traffic_telemetry`: Retrieve real-time queue depth, active sessions, and token throughput.
  - `tools/call`: Executes specified tool with parameter validation and structured response output.
  - `ping`: Health verification.

### 5. HTTP REST API Extensions (`backend/server/http_server.py`)
- Expose REST API routes for dashboard and external tools:
  - `GET /api/discovery/scan`: Trigger LAN subnet sweep and return candidate services.
  - `GET /api/discovery/nodes`: List all managed nodes with active queue depth and latency.
  - `POST /api/discovery/nodes`: Register or update a managed node.
  - `DELETE /api/discovery/nodes/<node_id>`: Remove a node.
  - `POST /api/discovery/proxy/completion`: Run an inference request governed by node concurrency limits.
  - `POST /api/mcp/rpc`: Handle JSON-RPC 2.0 MCP message over HTTP.

### 6. Frontend Dashboard & Widget Integration (`frontend/`)
- In `frontend/components/provider_hub.html`:
  - Add "Remote AI Nodes & LAN Discovery" card and modal.
  - 1-click "Scan LAN for AI Services" button with animated progress indicator.
  - Discovered instances table displaying IP, Port, Engine badge, detected models, and "Add to Managed Pool" button.
  - Node card showing Max Concurrency, Active Requests, Queue Depth, and status pill.
- In `frontend/js/app.js`: Wire scan and node registration API calls.
- In `frontend/mini_widget.html` and `backend/tray/native_widget.py`: Include remote node token counts in aggregate totals.

## 3. Verification Criteria
- [ ] LAN Scanner reliably identifies mock Ollama (`11434`) and OpenAI-compatible (`1234`/`8000`) services without socket hangs.
- [ ] Traffic Governor strictly enforces `max_concurrency` ceiling; excess requests wait in queue or reject on timeout.
- [ ] Ingested inference calls through the governor record token metrics, models, and latency into `usage_events`.
- [ ] MCP Server handles `initialize`, `tools/list`, and `tools/call` complying with JSON-RPC 2.0.
- [ ] REST API endpoints for discovery, nodes, and MCP execute cleanly.
- [ ] Complete automated test suite (>=20 new tests) passes with 100% green execution.
