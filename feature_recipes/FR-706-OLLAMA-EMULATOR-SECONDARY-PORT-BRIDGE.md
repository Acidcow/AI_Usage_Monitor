# Feature Recipe FR-706: Secondary Port Ollama API Emulator & Worker Node Bridge

## 1. Requirement Identification
- **Ticket ID**: AIUM-706
- **Epic**: EPIC-DISTRIBUTED-TELEMETRY
- **Component**: Ollama API Protocol Bridge, Secondary Port Server & Multi-Node Traffic Governor
- **Standard**: ASD-STE100 Compliant Technical Specification

---

## 2. Technical Scope & Functional Definitions

### 2.1 Secondary Dedicated Listener (Default Port 8989)
- The system must start a dedicated HTTP server on a configurable secondary port (default: `8989`).
- The port must be configurable via CLI argument `--ollama-port`, application settings, or environment variable `OLLAMA_EMULATOR_PORT`.
- Built strictly with Python 3 Standard Library (`http.server.ThreadingHTTPServer`).
- Operates concurrently with the Web Dashboard (`8765`) and Transparent Proxy (`8766`).

### 2.2 Ollama API Protocol Emulation
The secondary port must respond to all standard Ollama endpoints:
1. `GET /`: Returns plain text `"Ollama is running"` (HTTP 200).
2. `GET /api/version`: Returns JSON `{"version": "0.5.4"}`.
3. `GET /api/tags` and `GET /api/tags/`:
   - Inspects the managed compute node registry.
   - Aggregates all available models across registered active worker nodes.
   - Returns standard Ollama model list format (`models: [{"name": "...", "model": "...", "size": ..., "details": {...}}]`).
4. `POST /api/show`:
   - Returns model metadata (family, parameter size, format, modelfile template) for a queried model.
5. `POST /api/generate`:
   - Accepts Ollama text completion payload (`model`, `prompt`, `stream`, `options`, `system`).
   - Dispatches inference across configured worker nodes through the `TrafficGovernor`.
   - Supports non-streaming (`stream: false`) and streaming (`stream: true`) responses.
   - Returns standard Ollama fields: `response`, `done: true`, `prompt_eval_count`, `eval_count`, `total_duration`.
6. `POST /api/chat`:
   - Accepts Ollama chat payload (`model`, `messages`, `stream`, `options`).
   - Dispatches conversation turn to suitable worker node.
   - Returns standard Ollama chat structure (`message: {"role": "assistant", "content": "..."}, done: true`).
7. `POST /api/embeddings` & `POST /api/embed`:
   - Accepts embedding vectors request and dispatches to node.
8. `GET /api/ps`:
   - Returns active models in memory across the worker pool.
9. `GET /v1/models`, `POST /v1/chat/completions`:
   - Provides OpenAI-compatible endpoint compatibility.

### 2.3 JSON-RPC / MCP Bridge Dual-Protocol Support
- The secondary port must also process JSON-RPC 2.0 requests sent to `/api/mcp/rpc`, `/rpc`, or with `"jsonrpc": "2.0"` body.
- Re-uses `MCPServer.handle_json_rpc` to execute MCP discovery and governance tools.

### 2.4 Worker Node Dispatch, Concurrency & Token Metering
- When a model is requested:
  1. Identifies candidate worker nodes from `NodeRegistry` supporting the requested model.
  2. Respects node priority, active request count, and `max_concurrency` semaphore limits.
  3. Enforces client token allowances (session burst window & daily rolling limits) by client IP.
  4. Automatically fails over to secondary candidates if a worker node's circuit breaker trips.
  5. Ingests all generated tokens (`prompt_eval_count` + `eval_count`) into SQLite `usage_events` under provider `"ollama"`.

---

## 3. Verification Assertions (TDD Target)
1. Verify secondary HTTP server initializes and binds to port 8989 (or mock test port).
2. Verify `GET /` returns `"Ollama is running"` with HTTP 200.
3. Verify `GET /api/version` returns standard version JSON.
4. Verify `GET /api/tags` returns aggregated models from configured worker nodes.
5. Verify `POST /api/show` returns details for a model.
6. Verify `POST /api/generate` non-streaming returns standard Ollama completion response.
7. Verify `POST /api/generate` streaming returns valid NDJSON stream.
8. Verify `POST /api/chat` non-streaming returns standard assistant message.
9. Verify `POST /api/chat` streaming returns valid NDJSON message stream.
10. Verify `POST /api/embeddings` returns vector embeddings.
11. Verify `GET /v1/models` returns OpenAI-compatible model list.
12. Verify `POST /v1/chat/completions` routes to worker node and returns OpenAI format.
13. Verify `POST /api/mcp/rpc` on port 8989 processes MCP JSON-RPC requests.
14. Verify model-targeted routing routes to the worker node having that model.
15. Verify concurrency semaphore limits are respected during concurrent emulator requests.
16. Verify client quota burst window rejection (HTTP 429) is enforced through emulator port.
17. Verify token consumption is logged into `usage_events` in SQLite database.
18. Verify failover to secondary worker node if primary node fails.
19. Verify `run_monitor.py` starts emulator server and cleanly shuts down.
20. Verify zero external dependencies (Python 3 standard library only).
