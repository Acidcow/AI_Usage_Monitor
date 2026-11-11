# AI Usage Monitor - Release Notes v0.9.8

**Release Identifier**: `v0.9.8`  
**Release Date**: 2026-10-26  
**Epic**: `EPIC-PLATFORM-OVERHAUL`  
**Tickets**: `AIUM-908`, `AIUM-909`  
**Ways of Work Version**: v1.0.0  

---

## Executive Summary

AI Usage Monitor `v0.9.8` resolves two critical P0 issues identified during the comprehensive platform audit:
1. Eliminates the `99358%` tag group share calculation overflow on the Dashboard and fixes pluralization glitches in Historical Reports.
2. Completely terminates continuous 15-second `[AUTH_FAILURE] CLAUDE Unauthorized` error floods and HTTP 429 rate limit rejections by introducing genuine key structural validation, purging test dummy keys from Windows DPAPI, and implementing a 5-minute in-memory TTL cache with exponential backoff on Anthropic OAuth endpoints.

---

## Key Capabilities & Changes

### 1. Tag Group Share Calculation & Pluralization (AIUM-908)
- **Root Denominator Fix**: In [`frontend/js/app.js`](file:///c:/AgenticDev/AI_Usage_Monitor/frontend/js/app.js), resolved total estate tokens from `comp.total_tokens_today` (with fallback summing of `comp.providers`) instead of querying the non-existent `comp.summary?.total_tokens_today || 10000`.
- **Proportional Formatting**: Group share percentages are strictly bounded between `0%` and `100%`. Micro-allocations (< 1%) now render clearly as `<1%` rather than rounding to zero.
- **Slice Count Pluralization**: Historical report summary cards now distinguish singular vs. plural records (`1 slice` vs. `N slices`).

### 2. Claude Auth Loop Elimination & OAuth Cache TTL (AIUM-909)
- **Key Validation Guard**: Added `ClaudeProvider.is_valid_anthropic_api_key(key)` to verify that API keys possess genuine structural characteristics (must start with `sk-ant-`, length >= 30, no placeholder substrings or ellipsis). Mock strings like `sk-ant-secret-999` are rejected before network probing.
- **DPAPI Vault Sanitization**: Cleaned up stale `sk-ant-secret-999` test credential left behind by unshielded test runs, and updated `tests/test_dpapi_vault.py` with reliable `try ... finally: delete_credential` cleanup.
- **OAuth Usage Cache TTL (5 Minutes)**: Implemented in-memory caching (`_oauth_telemetry_cache`, TTL 300s) for `/api/oauth/usage` to eliminate outbound request floods and stop Anthropic HTTP 429 rate limit errors.
- **HTTP 429 Exponential Backoff**: When Anthropic rate limits are encountered, engaged a 10-minute backoff window (`_oauth_rate_limited_until`) returning cached or local plan metrics.
- **Socket Disconnect Protection**: Wrapped HTTP server payload writes in `(ConnectionResetError, ConnectionAbortedError, BrokenPipeError)` guards to eliminate WinError 10053 tracebacks.

---

## Verification & Test Results

- **Feature Test Suites**:
  - `tests/test_tag_group_share_and_pluralization.py`: 20/20 passed (100%).
  - `tests/test_claude_auth_loop_elimination_and_oauth_cache.py`: 20/20 passed (100%).
- **Full Platform Regression Suite**: **486/486 passed (100% OK)** across the entire repository.
- **Zero External Supply-Chain Dependencies**: 100% Python Standard Library and vanilla ES6.
