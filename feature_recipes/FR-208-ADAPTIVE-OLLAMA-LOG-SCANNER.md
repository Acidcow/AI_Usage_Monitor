# Feature Recipe FR-208: Adaptive Ollama Log Scanner & Dynamic Model Ingestor

## 1. Goal
Continuously monitor and parse local Ollama runtime server logs (`server.log`), dynamically detect active model switches (`gemma4:e4b`, `llama3.2`, `qwen2.5`, etc.), extract real prompt and evaluation token counts, and ingest them idempotently into the SQLite telemetry store so dashboard statistics, model telemetry cards, and multi-model trend charts update automatically in real time.

## 2. Technical Requirements
1. **Multi-Platform Log File Location**:
   - Windows: `%LOCALAPPDATA%\Ollama\server.log` (and rotated archives `server-*.log`).
   - macOS / Linux: `~/.ollama/logs/server.log` or `/var/log/ollama/server.log`.
   - Accept custom search path overrides for isolated testing and enterprise deployments.
2. **Sequential Model State & Token Parser**:
   - Detect model switches from `template selection model=...` or `loading model via llama-server model=...` and strip prefixes like `registry.ollama.ai/library/`.
   - Extract prompt eval tokens: `prompt eval time = ... / <N> tokens`.
   - Extract generation eval tokens: `eval time = ... / <M> tokens`.
   - Extract completion timestamp: `[GIN] YYYY/MM/DD - HH:MM:SS` or log line ISO8601 time.
3. **Idempotent Database Persistence**:
   - Generate deterministic `session_id` using model name, timestamp, and token signature (e.g. `ollama_gemma4_e4b_20261014T124518_p1527_e1113`).
   - Check SQLite `usage_events` before insertion to prevent double counting on repeated scans.
   - Record with provider `"ollama"`, model `<model_tag>`, input tokens `<N>`, output tokens `<M>`, total tokens `<N + M>`, and `estimated_cost = 0.0`.
4. **Continuous Background Scanning & Synchronization**:
   - Invoke `scan_local_logs()` automatically inside `OllamaProvider.sync_usage()`.
   - Wire `ollama.sync_usage()` into `run_monitor.py` periodic background poller (executing every 10 seconds).
   - Ensure `get_model_telemetry_summary()` dynamically aggregates real SQLite usage data for all discovered models.
5. **Dynamic Model Trend Lines in Database Engine**:
   - In `UsageDatabase.get_hierarchical_trends(provider="ollama")`, dynamically build trend series for all models present in `child_buckets` using a vibrant color palette rather than restricting to a hardcoded list.

## 3. Verification Criteria
- Unit tests verify log parsing, model switching between multiple models, token extraction, and idempotent backfill.
- All existing 115 unit tests pass 100% green.
- Existing user runs for `gemma4:e4b` (18,932 tokens) are successfully ingested from real `server.log`.
- `/api/providers/ollama/models` and `/api/usage/trends/hierarchy?provider=ollama` return real token metrics and non-zero trend points for `gemma4:e4b`.
