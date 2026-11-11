# Release Notes - v0.9.4 (AIUM-904)

**Release Date**: 2026-10-22  
**Ticket ID**: `AIUM-904`  
**Title**: Claude Pro Plan Alignment, Local vs. Remote Node Disaggregation & Canonical Unified Telemetry Taxonomy  

---

## 1. Summary of Changes

1. **Canonical 8-Tier Cross-Platform Telemetry Taxonomy (`backend/storage/taxonomy.py`)**:
   - Defined `CANONICAL_TAXONOMY_TIERS` (`L1: Platform`, `L2: Tenant / Account Tier`, `L3: Workspace / Pool`, `L4: Principal / Seat`, `L5: Compute Node & Locality`, `L6: Client / Workstation`, `L7: Access / Traffic Route`, `L8: Model & Session`) and `PROVIDER_TERMINOLOGY_MATRIX` mapping Claude, Ollama, Gemini, ChatGPT, and M365 Copilot terminology to a single unified structure.
   - Implemented deterministic classifiers (`classify_node_locality()`, `classify_account_tier()`, `normalize_event_taxonomy()`) that classify Local vs. Remote LAN vs. Cloud compute nodes and Personal Pro vs. Team/Enterprise vs. On-Premise account tiers.
   - Exposed `GET /api/taxonomy` on `backend/server/http_server.py` and rendered an interactive **Unified Cross-Platform Terminology Mapping** reference drawer (`#unified-taxonomy-drawer`) directly inside the dashboard chart header.

2. **Claude Pro Plan Upgrade & Streaming Log Deduplication (`backend/providers/claude.py`, `backend/storage/database.py`, `run_monitor.py`)**:
   - Updated `ClaudeProvider.scan_local_logs()` to deduplicate multi-block streaming chunks within `.jsonl` files that share the same Anthropic `message.id` (`msg_01...`), preventing 3x-5x token inflation on multi-tool turns while preserving line-index fallback when `message.id` is absent.
   - Preserved calibrated `Claude Pro` plan metadata during local CLI `.jsonl` scanning so personal Pro accounts are never overwritten back to `Team Enterprise (CLI)`.
   - Disabled lingering background demo simulation mode (`claude.enable_simulation_mode(False)`) after initial `--demo` seed ticks in `run_monitor.py` and cleansed synthetic company-wide (`Synthesis2`) demo rows from `usage_history.db`.

3. **Local vs. Remote LAN Compute Node & Account Tier Disaggregation (`backend/storage/database.py`, `backend/storage/reporting_engine.py`, `frontend/js/app.js`)**:
   - Updated `UsageDatabase.record_usage_event()` to extract `instance_clean = "node_..."` from `remote_node_<id>_<epoch>` session IDs so remote LAN Ollama instances (`JamesE-PC @ 10.1.7.74:11434`) are never conflated with the local workstation (`DESKTOP-C9FNLB9 @ 127.0.0.1:11434`).
   - Enhanced `UsageDatabase.get_granular_timeseries()` and `GET /api/usage/timeseries` with `breakdown` (`consolidated`, `locality`, `tenant_account`, `workspace_pool`, `compute_node`, `client_host`, `access_route`, `model`) and `scope_filter` (`all`, `personal_only`, `team_only`, `local_only`, `remote_only`), emitting explicit disaggregated series (`claude_personal_pro`, `claude_team_org`, `ollama_local_node`, `ollama_remote_lan`, and `breakdown_series`).
   - Added **Series View** (`#chart-breakdown-select`) and **Scope Filter** (`#chart-scope-filter-select`) controls to the Token Velocity & Multi-Platform Telemetry Curves header, plus **Node Locality**, **Account Tier**, and **Compute Node** columns/pivots to the Historical Usage Reports grid.

---

## 2. Verification & Test Coverage
- **Unit Test Suite**: Added 20 unit tests in `tests/test_unified_taxonomy_claude_pro_and_node_locality.py` (`386/386` total tests passing).
