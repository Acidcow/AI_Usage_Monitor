# Architecture & Design Decision: Comprehensive Architectural Audit & Platform Overhaul (`AIUM-902`)

**Date**: 2026-10-22  
**Ticket**: `AIUM-902`  
**Status**: Approved  

---

## 1. Executive Summary of Architectural Audit Findings

A full-stack architectural audit of `AI_Usage_Monitor` identified four primary technical debt clusters:

### Cluster 1: Monolithic Storage Engine (`backend/storage/database.py`)
- `backend/storage/database.py` grew to 3,422 lines combining schema initialization, raw telemetry ingestion, account management, LAN node inventory, client quota governance, and historical reporting/pivot analytics in a single class.
- **Remediation**: Extract the historical reporting, CSV export, and multi-dimensional pivot engine into a cohesive `ReportingEngineMixin` in `backend/storage/reporting_engine.py`. `DatabaseEngine` (and its alias `UsageDatabase`) inherits `ReportingEngineMixin` so all existing imports (`from backend.storage.database import UsageDatabase, DatabaseEngine`) remain 100% compatible while cleanly separating analytical OLAP queries from OLTP event ingestion.

### Cluster 2: Gemini Transparent Proxy Authentication & Routing Defects (`backend/proxy/transparent_proxy.py` & `backend/providers/gemini.py`)
- **Defect 1 (Vault Key Fragmentation)**: The Gemini config modal stores keys at `("gemini", "default")` and `("gemini", "keys")`, whereas `TransparentProxyHandler._proxy_gemini_request` only queried `("gemini", active_acct["account_id"])`.
- **Defect 2 (Placeholder Key Passthrough)**: Clients configured with placeholder keys (`GEMINI_API_KEY="proxy"` or `"dummy"`) caused `key_val` to evaluate truthy, skipping vault injection and forwarding the invalid string `"proxy"` to Google's servers.
- **Defect 3 (OAuth Bearer vs. API Key Injection)**: Google OAuth access tokens (`ya29...`) stored at `("google", "access_token")` require `Authorization: Bearer <token>`, whereas standard Gemini API keys (`AIza...`) require `x-goog-api-key`.
- **Defect 4 (Missing `GET` Proxy Forwarding)**: `do_GET` rejected all paths except `/health` with HTTP 404, breaking `GET /v1beta/models` authentication checks.
- **Defect 5 (Keyless `/models/...` Misrouting)**: Requests to `/models/gemini-2.5-pro:generateContent` without an inline key fell through `is_gemini` detection and were routed to `https://api.anthropic.com`.
- **Defect 6 (Missing Proxy Attribution in Gemini Telemetry)**: `GeminiProvider.ingest_proxy_interaction` omitted `source="proxy"`, `is_proxied=1`, `client_ip`, `instance_id`, `token_id`, and `project_id`.

### Cluster 3: Reports & Analytics Feature Completeness (`AIUM-607` / `AIUM-801`)
- `export_historical_csv` and `/api/reports/history?format=csv` ignored v2.0 filters (`dimension`, `source`, `model`, `instance_id`, `client_ip`, `token_id`, `project_id`) and omitted `Source`, `Instance`, `Client IP`, and `Client Alias` columns.
- `get_multi_dimensional_pivot` lacked support for the `"group"` (`cross_platform_tags`) dimension and was not wired into `frontend/components/reports_panel.html`.
- `reports_panel.html` lacked the `Yearly` slice button, custom `start_date`/`end_date` inputs, `model`/`instance_id`/`client_ip` filter inputs, and click-to-sort table headers.

### Cluster 4: Production Startup Purity (`run_monitor.py`)
- `run_monitor.py` unconditionally called `claude.calibrate_limits(...)` with hardcoded demo percentages (`60.0%` session used) on every fresh database startup even when `--demo` was not passed.
- **Remediation**: Gate initial hardcoded demo limit calibration behind `if args.demo:`.
