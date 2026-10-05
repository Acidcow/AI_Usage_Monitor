# Feature Recipe FR-201: Claude Local Code & CLI Session Scanner

## 1. Goal
Scan local filesystem directories (`~/.claude/projects/`, `~/.claude/sessions/`) to ingest real agentic CLI token history.

## 2. Technical Requirements
1. Locate `~/.claude` directory automatically in user profile.
2. Traverse all project subfolders looking for `*.jsonl` files (e.g. `C--AgenticDev-AEGIS/*.jsonl`).
3. Parse lines with `type: "assistant"`:
   - Extract `model` (e.g. `claude-sonnet-5-5`, `claude-3-7-sonnet`).
   - Extract `usage.input_tokens`, `usage.output_tokens`, `usage.cache_creation_input_tokens`, and `usage.cache_read_input_tokens`.
   - Extract `timestamp` (ISO8601).
   - Calculate cost using model rates.
4. Record sessions into `usage_events` table in `usage_stats.db` idempotently.
5. Prevent duplicate ingestion using a state hash or tracking ingested line offsets.

## 3. Verification Criteria
- Correctly parses real JSONL logs without failing on queue-operation or user attachment lines.
- Ingested sessions appear immediately in `get_recent_sessions()` and `get_usage_summary()`.
