# Feature Recipe: FR-902 - Comprehensive Architectural Audit & Core Platform Overhaul

**Ticket ID**: `AIUM-902`  
**Epic**: `EPIC-PLATFORM-OVERHAUL`  
**Status**: Done  
**Standard**: ASD-STE100 Simplified Technical English  

---

## 1. Purpose

This recipe specifies the architectural audit and core platform overhaul of AI Usage Monitor to eliminate technical debt, resolve all Gemini Transparent Proxy authentication and routing defects, modularize the historical reporting and pivot analytics engine, remove unrequested demo data injection from production startup, and complete the end-to-end Reports & Analytics UI and CSV export pipeline.

## 2. Requirements (STE-100)

### 2.1 Gemini Transparent Proxy Authentication & Routing (`backend/proxy/transparent_proxy.py` & `backend/providers/gemini.py`)
- **REQ-902-01**: Implement unified Gemini credential resolution (`_resolve_gemini_credential`) in `GeminiProvider` and `TransparentProxyHandler` checking, in order:
  1. Named token lookup (`("gemini", f"token_{token_id}")`) or matched token hash.
  2. Active account credential (`("gemini", active_acct["account_id"])`).
  3. Default Gemini API key (`("gemini", "default")`).
  4. Multi-key JSON list (`("gemini", "keys")` -> first valid key).
  5. Google OAuth 2.0 access token (`("google", "access_token")`).
- **REQ-902-02**: Detect and replace client placeholder keys (`"proxy"`, `"dummy"`, `"local"`, `"vault"`, `"aium"`, `"none"`, `"null"`, `"test"`) with the resolved vaulted credential instead of forwarding invalid placeholder strings upstream to Google.
- **REQ-902-03**: Distinguish Google API keys (`AIza...` -> injected via `x-goog-api-key` header or `?key=` query parameter) from Google OAuth 2.0 Bearer tokens (injected via `Authorization: Bearer <token>` header).
- **REQ-902-04**: Support `GET` requests through `TransparentProxyHandler` (`do_GET`) for `/v1beta/models`, `/v1/models`, and `/models` so Gemini CLI and SDK discovery handshakes succeed.
- **REQ-902-05**: Route keyless `/models/gemini-...` requests to `https://generativelanguage.googleapis.com` (normalizing `/models/...` to `/v1beta/models/...` when needed) rather than misrouting them to `https://api.anthropic.com`.
- **REQ-902-06**: Record `source="proxy"`, `is_proxied=1`, `client_ip`, `instance_id`, `token_id`, and `project_id` in `GeminiProvider.ingest_proxy_interaction`.

### 2.2 Storage Modularization & Reporting Engine Overhaul (`backend/storage/reporting_engine.py` & `backend/storage/database.py`)
- **REQ-902-07**: Extract reporting, historical aggregation, CSV export, and multi-dimensional pivot logic into a dedicated `ReportingEngineMixin` in `backend/storage/reporting_engine.py`, inherited by `DatabaseEngine` in `backend/storage/database.py` to preserve 100% backward compatibility.
- **REQ-902-08**: Update `export_historical_csv` and `GET /api/reports/history?format=csv` to accept all v2.0 filters (`dimension`, `source`, `model`, `instance_id`, `client_ip`, `token_id`, `project_id`, `team_name`, `user_name`) and output v2.0 attribution columns (`Source`, `Instance`, `Client IP`, `Client Alias`).
- **REQ-902-09**: Support `"group"` (cross-platform tags from `cross_platform_tags`) in `get_multi_dimensional_pivot` alongside `provider`, `account_id`, `model`, `source`, `instance_id`, `client_ip`, `token_id`, `project_id`, `user_name`, `team_name`, and `department`.
- **REQ-902-10**: Resolve `client_alias` dynamically from `client_quotas` and `device_inventory` in `query_historical_report` when `usage_events.client_alias` is empty.

### 2.3 Reports & Analytics Frontend Overhaul (`frontend/components/reports_panel.html` & `frontend/js/app.js`)
- **REQ-902-11**: Add `Yearly` time-slice button, custom `Start Date` and `End Date` date pickers, `Model`, `Instance ID`, and `Client IP` filter controls, and `Project / Workspace` (`project_id`) pivot option to `frontend/components/reports_panel.html`.
- **REQ-902-12**: Implement interactive click-to-sort column headers (`window.App.sortReportsTable`) on the Historical Reports table.
- **REQ-902-13**: Wire the Multi-Dimensional Pivot Matrix (`/api/usage/pivot`) UI section into `frontend/components/reports_panel.html` and `frontend/js/app.js`.
- **REQ-902-14**: Gate initial demo quota pre-calibration in `run_monitor.py` behind `--demo` so production startups remain pure.
