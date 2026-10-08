# Architecture Decision Record: Multi-Account Profiles & Multi-Tenant Aggregation

**Date**: 2026-10-08  
**Status**: Accepted  
**Authors**: Antigravity Engineering  
**Derived Standard**: KloGnist WoW v2.5.0 / ASD-STE100  
**Epic**: `EPIC-COMPARATIVE-ANALYTICS`  
**Ticket ID**: `AIUM-608`  

## Context & Problem Statement
Developers and teams frequently operate across multiple accounts and tenants for the same AI provider:
1. Personal developer accounts (e.g., `acidcow@gmail.com`) for testing, experimentation, and personal projects.
2. Enterprise or corporate client workspaces (e.g., `Synthesis Software Technologies`, `user@company.com`) for production and client deliverables.
3. Multiple distinct API keys or organizations with differing quota tiers and budgets.

Historically, provider snapshots and proxies assumed a single static active credential or default profile per provider. Users require the ability to:
- Register $\ge 2$ distinct account profiles per provider in the Web UI.
- Securely store credentials per account using Windows DPAPI without cross-account leakage.
- Switch active account profiles on demand, instantly updating proxy routing credentials, telemetry attribution, and widget badges.
- Filter historical reports and analytics by specific account profile or inspect aggregate multi-tenant rollups.

## Decision & Design Rationale
1. **Schema & Persistence (`account_profiles` Table)**:
   - Persist account profiles in SQLite with fields:
     - `id`: Unique UUID identifier.
     - `provider`: Provider key (`claude`, `gemini`, `chatgpt`, `ollama`, `copilot`).
     - `account_name`: Human-readable label (e.g., "Synthesis Work", "Personal Pro").
     - `account_id`: Unique identifier (e.g., email, organization ID, or token slug).
     - `email`: Optional user email address.
     - `plan_type`: Subscription tier (`Team Enterprise`, `Pro`, `Free Tier`, etc.).
     - `is_active`: Boolean flag (1 for active, 0 for inactive). Exactly one active profile per provider.
     - `metadata`: JSON payload for provider-specific attributes (e.g., org ID, project ID).
     - `created_at`, `updated_at`: ISO 8601 timestamps.
   - Unique constraint on `(provider, account_id)`.
2. **DPAPI Vault Namespaced Credentials (`backend/security/dpapi_vault.py`)**:
   - The vault natively supports `(provider, account_id)` indexing.
   - For every registered account profile with an API key, the secret is encrypted with `CryptProtectData` and stored under `vault.set_credential(provider, account_id, secret)`.
   - When an account profile is deleted, its vaulted credentials are wiped.
3. **Transparent Proxy & Telemetry Ingestion Binding**:
   - When `record_usage_event()` is invoked without explicit `account_id`, it resolves the currently active account profile from `account_profiles` instead of hardcoded fallbacks.
   - The transparent CLI proxy (`http://127.0.0.1:8766/v1`) resolves credentials for the active account profile for the requested provider, allowing transparent zero-config switching.
4. **REST API Surface (`backend/server/http_server.py`)**:
   - `GET /api/accounts`: Lists all account profiles, optionally filtered by `?provider=...`. Includes active status, plan type, and credential presence.
   - `POST /api/accounts`: Registers or updates an account profile. If `api_key` is provided, it is securely vaulted via DPAPI. If `is_active` is true, other profiles for the provider are deactivated.
   - `POST /api/accounts/active`: Sets the active profile for a given `(provider, account_id)` pair.
   - `POST /api/accounts/delete`: Deletes an account profile and deletes its DPAPI credential. If the deleted profile was active, auto-promotes the first remaining profile.
5. **Multi-Tenant Reporting & Aggregation**:
   - Historical reports (`GET /api/reports/history`) and CSV export (`GET /api/reports/export.csv`) support `?account_id=...` parameter filtering.
   - When omitted or set to `all`, results aggregate across all accounts.
6. **Frontend UI Integration (`frontend/components/provider_hub.html`, `frontend/js/app.js`)**:
   - Account Profile Manager modal accessible from each provider card and settings.
   - 1-click active account switcher dropdown on each provider card.
   - Multi-account badges indicating active tenant status.

## Consequences & Verification
- 100% green verification via `tests/test_multi_account_profiles.py` (unit tests covering storage, vault, REST endpoints, and attribution).
- Zero external dependencies (strictly Python 3 standard library: `sqlite3`, `ctypes`, `http.server`, `urllib`).
