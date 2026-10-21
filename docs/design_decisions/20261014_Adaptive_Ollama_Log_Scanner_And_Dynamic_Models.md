# Architecture Decision Record: Adaptive Ollama Log Scanner & Dynamic Model Telemetry

**Date**: 2026-10-14  
**Status**: Accepted  
**Linked Feature Recipe**: `feature_recipes/FR-208-ADAPTIVE-OLLAMA-LOG-SCANNER.md`  
**Ticket**: `AIUM-208`

## Context
Local Ollama instances (`ollama serve` / `http://localhost:11434`) do not maintain a persistent database or historical query API for token usage. When local inference runs (e.g. CLI `ollama run`, Open WebUI, Continue, Roo Code, LangChain), Ollama returns token metrics in the stream and discards them from memory upon connection termination.
Direct API polling against `/api/tags` and `/api/ps` only provides model names and memory states, leaving token metrics at zero.

## Decision
We implement a zero-dependency, continuous, adaptive Ollama log scanner and dynamic model state tracker:
1. **Multi-Platform Log Ingestion**:
   - Automatically locate Ollama runtime logs (`%LOCALAPPDATA%\Ollama\server.log` and `server-*.log` on Windows; `~/.ollama/logs/server.log` on macOS/Linux).
2. **Stateful Model Switch & Inference Tracking**:
   - Parse sequential log streams to track active model switches via `template selection model=...` or `loading model via llama-server model=...` (stripping registry prefixes).
   - Extract prompt evaluation and generation tokens from `slot print_timing` entries:
     - `prompt eval time = ... / <N> tokens` -> `input_tokens`
     - `eval time = ... / <M> tokens` -> `output_tokens`
   - Pair with HTTP timestamp from `[GIN] YYYY/MM/DD - HH:MM:SS` or log line timestamp.
3. **Idempotency & Zero Double-Counting**:
   - Construct deterministic `session_id` using model name, timestamp, and token counts.
   - Guard against duplicate inserts via SQLite index/query lookup.
4. **Dynamic Model Discovery in Database Engine**:
   - Extend `UsageDatabase.get_hierarchical_trends(provider="ollama")` to dynamically enumerate and plot all models discovered in `child_buckets` using a vibrant color palette rather than restricting to a hardcoded list.
5. **Continuous Background Sync**:
   - Hook `scan_local_logs()` into `OllamaProvider.sync_usage()`, executed during regular 10-second polling loops in `run_monitor.py` and on dashboard auto-refresh.

## Consequences
- Every local inference across any model (`gemma4:e4b`, `llama3.2`, `qwen2.5`, `mistral`, etc.) is captured within seconds of completion.
- Users can switch models freely at any time; the monitor automatically adapts to new models, generating discrete model cards, token totals, and trend plots dynamically.
- Zero external runtime dependencies preserved (strictly Python standard library).
