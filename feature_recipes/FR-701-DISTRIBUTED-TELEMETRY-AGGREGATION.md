# Feature Recipe FR-701: Distributed Telemetry Aggregation & Multi-Node Central Hub

## 1. Goal
Provide a distributed architecture and protocol for reporting, consolidating, and aggregating AI token telemetry and cost metrics across a cluster of developer nodes, workstations, and accounts into a central repository.

## 2. Context & Problem Statement
In engineering teams and enterprise environments:
1. Multiple developers and automated agent nodes run independent instances of `AI_Usage_Monitor`.
2. Teams need aggregated visibility across the entire node cluster: total team token burn, organization-level quota headroom, per-node/per-developer attribution, and unified billing summaries.
3. Architecture must remain lightweight, security-first, and zero-external-dependency without requiring bloated third-party telemetry agents.

## 3. Architecture & Technical Design Specification
1. **Node Telemetry Exporter (Push / Pull Protocol)**:
   - **Push Mode**: Local `AI_Usage_Monitor` instance optionally pushes sanitized telemetry batches to a configured central hub URL (`POST /api/cluster/ingest`) on a scheduled interval (e.g. every 5 minutes or upon session termination).
   - **Pull Mode**: Central hub polls registered node endpoints (`GET /api/usage/summary`, `GET /api/usage/comparison`) via mutual authentication tokens.
2. **Cluster Central Repository Schema**:
   - `cluster_nodes`: `(node_id TEXT PRIMARY KEY, hostname TEXT, developer_id TEXT, tags TEXT, last_heartbeat DATETIME, status TEXT)`
   - `cluster_usage_events`: `(id INTEGER PRIMARY KEY, node_id TEXT, provider TEXT, model TEXT, input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER, estimated_cost REAL, recorded_at DATETIME, session_id TEXT)`
   - `cluster_quota_pools`: Group/account allowances shared across multiple nodes.
3. **Security & Privacy Safeguards**:
   - Zero-leak credential policy: Node API keys and DPAPI secrets are **never** transmitted to the central hub. Only aggregated token counts, model names, and session identifiers are reported.
   - Mutual Auth: HMAC-SHA256 request signatures or cluster-join tokens stored securely in Windows DPAPI on each node.
4. **Consolidated Dashboard Views**:
   - Organization / Team Overview: Combined 24h velocity curves across all nodes.
   - Per-Node Leaderboard & Breakdown: Token consumption and cost ranked by developer / workstation node.
   - Quota Pool Warnings: Alerts when cluster-wide team allowances are reaching thresholds (80%, 95%).

## 4. Verification & Implementation Criteria
- Node export endpoint and client sync daemon tested with unit mock tests.
- Central SQLite repository supports multi-node queries and aggregations.
- Zero external dependencies preserved across all node and hub services.
