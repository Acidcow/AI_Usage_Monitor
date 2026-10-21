# Design Decision: Per-Client Token Limitations, Burst Windows, Temporary Bypass & Compact Compute Pool Layout

**Date**: 2026-10-19  
**Status**: Accepted  
**Authors**: Antigravity / Synthesis Core  
**Context**: Ticket AIUM-705 (EPIC-DISTRIBUTED-TELEMETRY)  

---

## 1. Context & Motivation
When multiple computers or developers on a local area network (LAN) connect to the AI Usage Monitor distributed proxy and query console, unconstrained clients can exhaust shared GPU/NPU resources, queue starvation occurs, and remote machines (like an ASUS ROG workstation) can crash from unbounded concurrent inference.

Furthermore, the existing Managed Compute Pool cards rendered bulky, unstructured blocks that lacked an immediate summary of the computer's alias, host IP, supported inference platforms, and installed models.

## 2. Architectural Decisions

### 2.1 Storage & Schema: `client_quotas` and `client_token_windows`
Two lightweight SQLite tables manage client tracking with zero external dependencies:
1. `client_quotas`:
   - `client_id` (PRIMARY KEY, e.g. `192.168.2.3` or `client_192_168_2_3`)
   - `client_ip` TEXT NOT NULL
   - `alias` TEXT
   - `session_window_minutes` INTEGER DEFAULT 15
   - `session_token_limit` INTEGER DEFAULT 25000
   - `daily_token_limit` INTEGER DEFAULT 250000
   - `priority` INTEGER DEFAULT 5
   - `is_unrestricted` INTEGER DEFAULT 0
   - `bypass_until` TEXT (ISO timestamp or NULL)
   - `scheduled_start_at` TEXT (ISO timestamp or NULL)
   - `scheduled_end_at` TEXT (ISO timestamp or NULL)
   - `allowed_models_json` TEXT DEFAULT '[]'
   - `blocked_models_json` TEXT DEFAULT '[]'
   - `allowed_nodes_json` TEXT DEFAULT '[]'
   - `blocked_nodes_json` TEXT DEFAULT '[]'
   - `notes` TEXT
   - `created_at` TEXT
   - `updated_at` TEXT

2. `client_token_windows`:
   - `id` TEXT PRIMARY KEY
   - `client_id` TEXT NOT NULL
   - `tokens` INTEGER NOT NULL
   - `timestamp` REAL NOT NULL (UNIX epoch for ultra-fast range indexing)

### 2.2 Rate Limiting & Window Algorithm
1. **Sliding Session Burst Window**: Sum of tokens where `timestamp >= current_time - (session_window_minutes * 60)`. If sum + estimated tokens > `session_token_limit`, request is rejected with HTTP 429 (`Burst Window Quota Exceeded`).
2. **Rolling 24-Hour Limit**: Sum of tokens where `timestamp >= current_time - 86400`. If sum + estimated tokens > `daily_token_limit`, request is rejected with HTTP 429 (`Daily Quota Exceeded`).
3. **Bypass Evaluation Order**:
   - `is_unrestricted == 1`: Always allowed.
   - `bypass_until >= now`: Temporary bypass active &rarr; Allowed.
   - `scheduled_start_at <= now <= scheduled_end_at`: Scheduled bypass active &rarr; Allowed.
   - Otherwise, standard burst and daily checks apply.

### 2.3 UI Layout: Compact High-Density Node Cards
- **Header**: `💻 [Alias] • [IP:Port]` with Engine Badge (`🦙 Ollama`, `🤖 LM Studio`, `⚡ vLLM`) and status dot (`● ONLINE`).
- **Sub-strip**: Trust level (`🛡️ Trusted` / `🚨 Untrusted`), Compute Group pill, priority badge, concurrency limit.
- **Models Section**: Compact chip cluster (`llama3:8b`, `qwen2.5:14b`, etc.) with quick search/copy and model count badge.
- **Client Governance Section**: Dedicated accordion panel in Provider Hub showing active connecting clients, token usage progress bars (Session Window + Daily), priority tier, and 1-click bypass controls.
