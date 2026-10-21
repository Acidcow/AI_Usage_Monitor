# Feature Recipe FR-705: Per-Client Token Limits, Burst Windows, Temporary Elevated Bypass & Compact Node Pool Display

## 1. Requirement Identification
- **Ticket ID**: AIUM-705
- **Epic**: EPIC-DISTRIBUTED-TELEMETRY
- **Component**: Distributed Node Governor, Client Rate Limiter & Managed Pool Dashboard
- **Standard**: ASD-STE100 Compliant Technical Specification

---

## 2. Technical Scope & Functional Definitions

### 2.1 Managed Compute Pool & Clusters Compact Visual Redesign
- The user interface must present compute cluster nodes in a clean, compact layout.
- The card header must show the **Device Alias and/or IP Address** prominently (e.g. `💻 ASUS ROG (Jamese-PC) • 10.1.7.74:11434`).
- The card body must show the available **platforms/services** on that host (Ollama, LM Studio, vLLM) with latency, health status, and trust badge.
- The card body must display the **available models** in compact tag chips (e.g. `llama3:8b`, `qwen2.5-coder:7b`) with parameter size and quantization when available.
- Telemetry stats (active requests, queued requests, total tokens routed) must display in a high-density status strip.

### 2.2 Per-Connecting-Client Token Limits & Burst Windows
- The traffic governor must track every connecting client by **Client IP** and **Computer Alias**.
- The system must maintain client budget rules:
  1. `session_window_minutes`: Short burst interval (default 15 minutes).
  2. `session_token_limit`: Maximum tokens allowed in the burst window (e.g., 20,000 tokens) to prevent endpoint overload.
  3. `daily_token_limit`: Maximum tokens allowed in a 24-hour period (e.g., 200,000 tokens).
  4. `priority`: Queue dispatch priority (1-10).
  5. `allowed_models` / `blocked_models`: Restrictions on specific models.
  6. `allowed_nodes` / `blocked_nodes`: Restrictions on specific compute nodes.
- When a client reaches its session limit or daily limit, requests must be rejected with HTTP 429 and a descriptive JSON error detailing tokens remaining and reset countdown.

### 2.3 Trusted Worker Elevation & Temporary Bypass
- Trusted worker nodes and developers can receive:
  1. High priority in the governor dispatch queue.
  2. Elevated token limits or unrestricted access (`is_unrestricted = 1`).
  3. **Temporary Elevated Bypass**:
     - Bypass for a specific duration in minutes, hours, or days (e.g., 30 minutes, 2 hours, 1 day).
     - **Scheduled Bypass**: Valid between a start date-time and end date-time.
- When an elevated bypass expires, the client returns automatically to default limits.

### 2.4 Client Governance REST API
- `GET /api/discovery/clients`: Lists connecting clients, token usage, burst window status, and bypass state.
- `POST /api/discovery/clients`: Creates or updates client limits, priority, and restrictions.
- `POST /api/discovery/clients/bypass`: Sets or clears a temporary/scheduled bypass.
- `DELETE /api/discovery/clients`: Resets token counters or removes custom client rules.

---

## 3. Verification Assertions (TDD Target)
1. Verify database schema creates `client_quotas` and `client_usage_records` tables.
2. Verify recording token usage increments sliding session window and daily rolling counters.
3. Verify client exceeding session token window is rejected with HTTP 429.
4. Verify client exceeding daily token limit is rejected with HTTP 429.
5. Verify client with active temporary bypass can query even when normal limits are exceeded.
6. Verify temporary bypass expires when countdown elapses.
7. Verify scheduled bypass activates only within defined start/end timestamps.
8. Verify REST API endpoints (`GET`, `POST`, `DELETE /api/discovery/clients`).
9. Verify compact compute pool card HTML rendering with Alias, IP, platform badges, and model chips.
