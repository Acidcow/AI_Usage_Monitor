# Feature Recipe: FR-608 Multi-Account Profiles & Multi-Tenant Aggregation

**Epic**: `EPIC-COMPARATIVE-ANALYTICS`  
**Ticket ID**: `AIUM-608`  
**Author**: Antigravity  
**Status**: Complete  
**Standard**: ASD-STE100 Simplified Technical English  

---

## 1. Problem Statement & Motivation
Users often maintain multiple accounts for the same provider simultaneously:
- A personal account (e.g., `acidcow@gmail.com`) for side projects and personal experiments.
- A corporate or enterprise account (e.g., `user@company.com`, Synthesis Software Technologies workspace) for client deliverables.
- Multiple separate Claude organizations or workspace tokens.

Currently, provider snapshots track a single primary active account identity per provider. Users need the ability to register multiple account profiles per provider, switch between active profiles, or view an aggregated operational overview that consolidates all accounts across their environment.

---

## 2. Target Architecture
1. **Multi-Account Credential Vaulting**:
   - DPAPI Vault supports namespaced keys: `providers/{provider}/accounts/{account_id}/...`.
   - Store credentials, refresh tokens, and API keys per account identifier.
2. **Account Profile Selector in UI**:
   - Provider hubs and modals allow switching between registered accounts via dropdown or profile tabs.
   - 1-click active account switching updates proxy routing headers and sync loops.
3. **Multi-Tenant Reporting & Aggregation**:
   - `usage_events` table already tags `account_id`, `team_name`, and `user_name`.
   - Historical reports engine (`/api/reports/history`) slices and filters across multiple accounts per provider.
4. **Native Widget Multi-Account Tree**:
   - Canvas tree expands to display multiple account umbrellas per platform with child keys underneath each.

---

## 3. Acceptance Criteria
- [x] Users can register >= 2 distinct accounts per provider in the Web UI modal.
- [x] Active account toggle switches telemetry context and local proxy forwarding credentials.
- [x] Historical analytics dashboard provides filtering by specific account or "All Accounts" aggregate.
- [x] 100% test coverage with zero external dependencies.

