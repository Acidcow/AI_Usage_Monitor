# Feature Recipe: FR-904 — Claude Pro Plan Alignment, Local vs. Remote Node Disaggregation & Canonical Unified Telemetry Taxonomy

**Ticket ID**: `AIUM-904`  
**Epic**: `EPIC-PLATFORM-OVERHAUL`  
**Priority**: Critical  
**Status**: In Progress  
**Date**: 2026-10-22  

---

## 1. Objective (ASD-STE100)

Establish a canonical 8-tier unified telemetry taxonomy across all AI providers (Claude, Gemini, Ollama, ChatGPT, M365 Copilot), align Claude telemetry and quota tracking with the upgraded **Claude Pro** subscription (eliminating synthetic company-wide `Synthesis2` pollution and duplicate streaming JSONL chunk inflation), and disaggregate local vs. remote LAN compute nodes and multi-account telemetry across the Token Velocity chart, Hierarchical Drill-Down, and Historical Usage Reports.

---

## 2. Canonical 8-Tier Unified Telemetry Taxonomy

| Tier | Canonical Key | Unified UI Label | Claude | Gemini | Ollama / Local Compute | ChatGPT / OpenAI | M365 Copilot |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **L1** | `platform` | **Platform** | Claude (Anthropic) | Google Gemini | Ollama (Compute) | ChatGPT / OpenAI | M365 Copilot |
| **L2** | `tenant_account` | **Tenant / Account** | Personal Account (`Claude Pro`) / Org (`Synthesis 2`) | Google Account (`acidcow@gmail.com`) | Hardware Owner / Estate | OpenAI Org / Account | Entra ID Tenant |
| **L3** | `workspace_pool` | **Workspace / Pool** | Subscription Pool (`Pro Individual` vs `Team Pool`) | AI Studio / GCP Project | Compute Pool (`Local Host` vs `Active Compute LAN`) | Project / Tier Pool | Department / License Pool |
| **L4** | `principal_seat` | **Principal / Seat** | User Seat / API Key | Named API Key / OAuth Seat | Operator / Caller | API Key / User Seat | Licensed M365 Seat |
| **L5** | `compute_node` | **Compute Node & Locality** | Anthropic Cloud / Local CLI Host | Google Cloud Endpoint | **Local Node** (`127.0.0.1` / `DESKTOP-C9FNLB9`) vs **Remote LAN Node** (`JamesE-PC @ 10.1.7.74`) | OpenAI Cloud Endpoint | M365 Graph Cloud |
| **L6** | `client_host` | **Client Host** | Originating Machine Alias / IP | Originating Machine Alias / IP | Requesting Client Alias / IP | Requesting Client Alias / IP | Client Device |
| **L7** | `access_route` | **Access Route** | `direct`, `proxy` (:8766), `local_cli` | `direct`, `proxy` (:8766), `oauth` | `direct` (:11434), `proxy` (:8989), `log_scanner` | `direct`, `proxy` | `direct`, `graph_api` |
| **L8** | `model_session` | **Model & Session** | Model ID & Session / Message ID | Model ID & Session ID | Model Tag & Run ID | Model ID & Request ID | Copilot Model & Session |

---

## 3. Acceptance Criteria

1. **Canonical Taxonomy Module (`backend/storage/taxonomy.py`) & `/api/taxonomy` Endpoint**:
   - Provides deterministic normalization (`normalize_event_taxonomy`) and locality classification (`local`, `remote_lan`, `cloud`) for any usage event or compute node.
2. **Claude Pro Plan Upgrade & Accurate Telemetry Ingestion (`backend/providers/claude.py`, `backend/storage/database.py`)**:
   - Supports **Claude Pro** plan limits and individual direct tracking without defaulting unattributed events to `Synthesis2` company-wide team pools when in `individual` / `Claude Pro` mode.
   - Deduplicates Claude Code `.jsonl` session log entries by `message.id` (`msg_01...`) so multi-chunk assistant streaming lines are never double-counted.
   - Cleans synthetic `sess_agentic_*` demo rows from the live database (`usage_history.db`).
3. **Local vs. Remote Compute Node Separation & Multi-Account Disaggregation**:
   - `get_granular_timeseries` (`/api/usage/timeseries`) supports a `breakdown` parameter (`consolidated`, `locality`, `tenant_account`, `compute_node`, `access_route`, `model`) and `scope_filter` (`all`, `personal_only`, `local_only`, `remote_only`).
   - `get_hierarchical_trends` (`/api/usage/trends/hierarchy`) and `get_comparative_metrics` (`/api/usage/comparison`) separate **Local Compute Node (`DESKTOP-C9FNLB9 @ 127.0.0.1`)** vs **Remote LAN Compute Node (`JamesE-PC @ 10.1.7.74`)** for Ollama, and separate **Personal Pro Account** vs **Team/Org Account** for Claude and other providers.
4. **Historical Usage Reports & Unified Terminology UI**:
   - Adds `Node Locality` (`locality`) and unified canonical labels to the Historical Usage Reports grid and customizer.
5. **Automated Verification**:
   - `>= 20` unit tests in `tests/test_unified_taxonomy_claude_pro_and_node_locality.py` with 100% pass rate across the entire suite.
