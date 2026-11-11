# Architecture & Design Decision: Unified Telemetry Taxonomy, Claude Pro Alignment & Local vs. Remote Node Disaggregation

**Date**: 2026-10-22  
**Ticket**: `AIUM-904`  
**Author**: Antigravity Architecture Team  
**Status**: Approved  

---

## 1. Context & Empirical Findings

Following the user's upgrade to **Claude Pro**, we performed an empirical audit of `usage_history.db`, `~/.claude`, `managed_nodes`, and the ingestion/aggregation pipelines:

1. **Company-Wide (`Synthesis2`) vs. Personal (`Claude Pro`) Conflation**:
   - `usage_history.db` contained 13,809 synthetic demo rows (`sess_agentic_101..109`) stamped with `account_id='Synthesis2'` and `team_name='Synthesis2'` from an earlier `--demo` run.
   - `UsageDatabase.record_usage_event()` defaulted every Claude event without an explicit `team_name` or `account_id` to `"Synthesis2"`, conflating personal Claude Pro usage with company team pool telemetry.
   - `ClaudeProvider.scan_local_logs()` used `f"{session_id}_{line_idx}"` as the deduplication key when scanning `~/.claude/projects/**/*.jsonl`. Because Claude Code writes multiple streaming JSONL lines sharing the same Anthropic `message.id` (`msg_01...`) and cumulative `usage` object, a single message turn was being ingested multiple times.
2. **Ollama Local vs. Remote LAN Node Conflation**:
   - `managed_nodes` contains both a local node (`node_ollama_1387210`: `DESKTOP-C9FNLB9` at `http://127.0.0.1:11434`) and a remote LAN node (`node_ollama_3958379`: `JamesE-PC` at `http://10.1.7.74:11434`).
   - However, `get_granular_timeseries()` and `get_hierarchical_trends()` aggregated all Ollama events into a single `"Ollama (Local)"` curve and per-model curves without distinguishing **Local Node (`127.0.0.1` / `DESKTOP-C9FNLB9`)** from **Remote LAN Node (`JamesE-PC @ 10.1.7.74`)**.
3. **Disparate Provider Terminology**:
   - Each AI platform uses different hierarchical concepts (e.g., Anthropic uses Organization / Team / Seat / Session; Google uses Account / GCP Project / AI Studio Key; Ollama uses Cluster / Compute Group / Host Node / Client IP). Without a canonical taxonomy mapping, cross-platform charts and reports could not compare or slice telemetry on a unified basis.

---

## 2. Architectural Decision

### 2.1 Canonical 8-Tier Unified Telemetry Taxonomy (`backend/storage/taxonomy.py`)
We introduce a zero-dependency canonical taxonomy module (`backend/storage/taxonomy.py`) that maps all provider-specific fields into 8 standardized dimensions:
1. **L1 `platform`**: Provider / Engine (`claude`, `gemini`, `ollama`, `chatgpt`, `copilot`)
2. **L2 `tenant_account`**: Account / Tenant Umbrella (e.g., `james@synthesis.co.za (Claude Pro)`, `Synthesis2`, `acidcow@gmail.com`, `Local Hardware Estate`)
3. **L3 `workspace_pool`**: Quota Pool / Workspace / Compute Group (e.g., `Claude Pro (Personal)`, `Team Workspace (Synthesis2)`, `Active Compute`)
4. **L4 `principal_seat`**: User Seat / Named Token / Credential (`James Eckhardt`, `tok_gem_flash`, etc.)
5. **L5 `compute_node` & `locality`**: Execution Instance & Locality (`local` for `127.0.0.1`/`localhost`/`DESKTOP-C9FNLB9`, `remote_lan` for LAN worker nodes like `JamesE-PC @ 10.1.7.74`, `cloud` for hosted frontier APIs)
6. **L6 `client_host`**: Originating Workstation Alias & IP (`DESKTOP-C9FNLB9 (127.0.0.1)`)
7. **L7 `access_route`**: Ingestion Path (`direct`, `proxy`, `emulator`, `local_cli`, `log_scanner`)
8. **L8 `model` & `session_id`**: Model Identifier & Conversation/Execution Session

### 2.2 Disaggregated Time-Series & Hierarchy Curves
- `UsageDatabase.get_granular_timeseries()` now accepts:
  - `breakdown`: `consolidated` (default platform curves + sub-series), `locality` (splits Local vs. Remote LAN vs. Cloud Accounts), `tenant_account` (splits by Account/Tenant), `compute_node` (splits by Compute Instance/Node), `access_route` (splits by Traffic Route), or `model` (splits by Model).
  - `scope_filter`: `all`, `personal_only` (excludes legacy/company team pool rows), `local_only` (local machine/node only), `remote_only` (remote LAN nodes only).
- `UsageDatabase.get_hierarchical_trends()` now emits distinct **Local Node** vs **Remote LAN Node** series for Ollama (alongside per-node and per-model series) and distinct **Personal Pro Account** vs **Team/Org Workspace** series for Claude.
