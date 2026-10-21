# Design Decision: Secondary Port Ollama API Emulator & Worker Node Bridge

**Date**: 2026-10-20  
**Status**: Accepted  
**Authors**: Antigravity / Synthesis Core  
**Context**: Ticket AIUM-706 (EPIC-DISTRIBUTED-TELEMETRY)  

---

## 1. Context & Motivation
An external, unrelated software platform requires connectivity to an Ollama-compatible endpoint (e.g. `http://127.0.0.1:8989/`). Rather than connecting to a single fixed machine, the user requires this secondary port to feed directly into the AI Usage Monitor distributed compute infrastructure, multiplexing queries across all registered, active worker nodes in the cluster (e.g. ASUS ROG, LAN workstations, Ollama/vLLM engines), while supporting JSON-RPC / MCP commands.

## 2. Architectural Decisions

### 2.1 Dual-Protocol Secondary Listener (`OllamaEmulatorServer`)
A dedicated Python standard library `ThreadingHTTPServer` binds to `DEFAULT_HOST` on a secondary port (default: `8989`, configurable via `--ollama-port`, settings, or `OLLAMA_EMULATOR_PORT` environment variable).

It exposes:
1. **Ollama Native REST API**:
   - `GET /`: Healthcheck banner (`"Ollama is running"`).
   - `GET /api/version`: Ollama semantic version (`{"version": "0.5.4"}`).
   - `GET /api/tags` & `GET /api/tags/`: Aggregated model catalog collected from all registered, trusted worker nodes in the managed compute pool.
   - `POST /api/show`: Model inspection details and template metadata.
   - `POST /api/generate`: Prompt completion dispatch with streaming and non-streaming responses.
   - `POST /api/chat`: Structured chat message turns with streaming and non-streaming responses.
   - `POST /api/embeddings` / `POST /api/embed`: Vector embedding computation.
   - `GET /api/ps`: Active running compute models.
2. **OpenAI Compatibility Layer**:
   - `GET /v1/models`: OpenAI model list mapping.
   - `POST /v1/chat/completions`: OpenAI chat completions format.
3. **Model Context Protocol (MCP) JSON-RPC 2.0**:
   - `POST /api/mcp/rpc`, `POST /rpc`, or JSON-RPC payloads: routed directly to `MCPServer.handle_json_rpc`.

### 2.2 Intelligent Node Selection & Concurrency Governance
1. **Model Matching**: When an inference request arrives, the bridge queries `NodeRegistry.list_nodes(is_trusted=1, compute_group="Active Compute")`. It prioritizes nodes explicitly advertising the requested model in their catalog.
2. **Load Balancing & Semaphores**: Selected nodes are acquired via `TrafficGovernor._get_semaphore(node_id, max_concurrency)` to prevent resource exhaustion and GPU thrashing.
3. **Circuit Breaker Failover**: If a node fails or exceeds its queue timeout, the bridge gracefully falls back to the next candidate in the pool.
4. **Client Quota Enforcement**: Connecting client IPs are metered against `client_quotas` (15m burst window and 24h daily token limits). Rejections return HTTP 429 in standard Ollama error format.
5. **Zero-Cost Hardware Accounting**: All completed tokens (`prompt_eval_count` + `eval_count`) are ingested into `usage_events` with provider `"ollama"` and $0 cost, updating real-time dashboard telemetry.

### 2.3 Streaming NDJSON Support
For streaming requests (`"stream": true`), the secondary server writes HTTP `Transfer-Encoding: chunked` or direct flushed newline-delimited JSON (NDJSON) tokens identical to official Ollama streaming behavior, capturing and tallying final token counts from the terminating `"done": true` chunk.

---

## 3. Zero External Dependencies Compliance
Strictly utilizes:
- `http.server.ThreadingHTTPServer` & `http.server.BaseHTTPRequestHandler`
- `urllib.request`, `urllib.error`
- `json`, `threading`, `time`, `socket`
- No pip packages or third-party web frameworks.
