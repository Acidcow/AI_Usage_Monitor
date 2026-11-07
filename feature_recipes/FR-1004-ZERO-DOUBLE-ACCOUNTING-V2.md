# Feature Recipe: AIUM-1004 - Bulletproof Zero Double-Accounting Across Transparent Proxy, Traffic Governor & Local Log Scanners

## Overview
Implement deterministic, bulletproof deduplication and metadata enrichment across all AI usage ingestion sources in AI Usage Monitor.
Eliminates token double-accounting when LLM interactions are captured concurrently or sequentially by the Transparent Proxy, Distributed Traffic Governor, and local log scanners (`local_jsonl_scanner`, `claude_desktop_scanner`, `ollama_local_logs`).

## Key Capabilities & Requirements
1. **Upstream ID & Token SSE Extraction (`_extract_sse_tokens`)**:
   - Pure-Python zero-dependency extraction of upstream response identifiers (`message.id` `"msg_01..."` from Anthropic SSE `message_start`, OpenAI `"chatcmpl-..."`, or Gemini `"responseId"`).
   - Extracts accurate `input_tokens` and `output_tokens` across streaming deltas and buffered JSON responses.
   - Forwards extracted `external_id` from `TransparentProxyServer` through `ClaudeProvider.ingest_proxy_interaction(..., external_id=extracted_id)` into `UsageDatabase.record_usage_event(...)`.
2. **Exact `external_id` Deduplication & Metadata Enrichment**:
   - If an event arrives with an `external_id` matching an existing record `(provider, external_id)`, no duplicate row is inserted.
   - Automatically enriches the existing record: updates generic streaming sessions (`stream_...`, `proxy_...`, `remote_...`) to real client UUIDs (`sess_...` / Claude Code session UUIDs).
   - Enriches `project_id` and structured `metadata` without mutating token counts.
   - Returns the existing row ID to guarantee caller contract idempotency.
3. **Cross-Source Temporal + Token Fingerprint Deduplication (`±15s` Window)**:
   - When an event is recorded by a local scanner and matches an earlier proxied/governed event (or vice versa) for the same `provider` with identical `(input_tokens, output_tokens)` within `±15 seconds`, deduplicates automatically.
   - Handles `external_id` enrichment when one source supplies the upstream ID and the other was `NULL`.
   - Prevents double-accounting between proxy streaming and delayed local log file ingestion.
   - Preserves non-matching distinct user turns outside the 15-second window or with differing token fingerprints.
4. **Local Hardware Zero-Cost Invariance**:
   - Ollama governor routing and local Ollama server log scanning deduplicate seamlessly while maintaining $0.00 estimated API cost.

## Architecture & Data Flow

```mermaid
sequenceDiagram
    autonumber
    participant Client as LLM Client / Claude Code
    participant Proxy as Transparent Proxy
    participant DB as SQLite (UsageDatabase)
    participant Scanner as Local JSONL Scanner

    Client->>Proxy: POST /v1/messages (Prompt)
    Proxy->>Proxy: Intercepts & extracts tokens + message.id ("msg_01...")
    Proxy->>DB: record_usage_event(session="stream_1731", external_id="msg_01...", tokens)
    DB-->>Proxy: Event Saved (evt_001)

    Note over Client,Scanner: Real turn completes; CLI logs to ~/.claude/projects/.../session.jsonl
    Scanner->>Scanner: Discovers turn with real session UUID
    Scanner->>DB: record_usage_event(session="uuid-real", external_id="msg_01...", tokens)
    DB->>DB: Match on external_id -> Deduplicate & UPDATE session_id to "uuid-real"
    DB-->>Scanner: Returns evt_001 (Zero Double Count)
```

## Verification & Testing
- Unit test suite: `tests/test_zero_double_accounting_v2.py` (22 unit tests, 100% pass).
- Backwards compatibility: `tests/test_database.py`, `tests/test_multi_dimensional_telemetry_and_deduplication.py`, `tests/test_proxy_streaming.py`.
