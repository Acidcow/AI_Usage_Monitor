# Design Decision: Claude Polling Auth Loop Elimination & OAuth Cache TTL

**Date**: 2026-10-26  
**Status**: Approved & Implemented  
**Author**: Antigravity Agent  
**Context**: AIUM-909  

---

## Context and Problem Statement

Diagnostics logs were continually spammed with `[AUTH_FAILURE] CLAUDE Authentication failed: Unauthorized` every 15–30 seconds.
Empirical diagnostics established that:
1. `backend/security/dpapi_vault.py` stored a 17-character dummy string (`sk-ant-sec...`) under `claude:default`.
2. `ClaudeProvider.sync_usage()` checked `if not api_key: return ...` and then sent a POST to `https://api.anthropic.com/v1/messages` with `x-api-key: sk-ant-sec...`, which failed with HTTP 401.
3. `ClaudeProvider.fetch_live_oauth_telemetry()` requested `/api/oauth/usage` from Anthropic's OAuth servers on every sync cycle. Anthropic strictly rate limits this endpoint, triggering HTTP 429 Too Many Requests.
4. Because live quota queries hit 429 rate limits, the UI fell back to "CALIBRATED WEB QUOTA" and prompted users for manual calibrations, despite active Claude Pro desktop logins.

---

## Decision

1. **API Key Sanity Check**: Add a format validator to `ClaudeProvider`. If an API key is shorter than 40 characters or does not begin with standard Anthropic prefixes (`sk-ant-`), treat it as an invalid/mock placeholder, bypass the live messages probe, and do not record an `AUTH_FAILURE`.
2. **In-Memory TTL Caching**: Implement a 300-second (5-minute) TTL cache for `fetch_live_oauth_telemetry()`. Subsequent background syncs within 5 minutes return cached quota metrics immediately without outbound network calls.
3. **HTTP 429 Backoff Guard**: If Anthropic returns HTTP 429 on `/api/oauth/usage`, engage an exponential/10-minute backoff window (`_oauth_rate_limited_until`) to avoid hammering the endpoint and keep provider state healthy.
4. **Vault Sanitization**: Automatically purge dummy placeholder keys from DPAPI if encountered during initialization.
5. **Zero-Calibration Autonomous Status**: Present the user with `CLAUDE PRO (OAUTH LIVE)` whenever decrypted OAuth credentials provide authoritative profile and usage data.

---

## Consequences & Trade-offs

- Positive: Zero 401 `AUTH_FAILURE` errors in logs.
- Positive: Zero 429 Rate Limit rejections from Anthropic OAuth API.
- Positive: Seamless zero-calibration live synchronization for Claude Pro users.
- Maintained zero external dependencies.
