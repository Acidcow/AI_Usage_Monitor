# Feature Recipe FR-909: Claude Polling Auth Loop Elimination & OAuth Cache TTL

**Ticket**: AIUM-909  
**Epic**: EPIC-PLATFORM-OVERHAUL  
**Priority**: Critical  
**Status**: In Progress  
**Standard**: ASD-STE100 Simplified Technical English  

---

## 1. Problem Statement

1. In the AI Usage Monitor diagnostics log, a continuous stream of authentication failure errors occurs every 15–30 seconds:
   `[AUTH_FAILURE] CLAUDE Authentication failed: Unauthorized`
   - **Root Cause**: DPAPI vault contains a stale/placeholder credential for `claude:default` (`sk-ant-sec...`, length 17). In `ClaudeProvider.sync_usage()`, when `api_key` exists in the vault, it sends a probe request to `https://api.anthropic.com/v1/messages`. Anthropic rejects this 17-character dummy key with HTTP 401 Unauthorized, flooding the diagnostics error buffer.
2. In `ClaudeProvider.fetch_live_oauth_telemetry()`, `_request_oauth_json("https://api.anthropic.com/api/oauth/usage")` is called on every sync cycle (every 15 to 30 seconds). Anthropic's OAuth API enforces strict rate limits on `/api/oauth/usage`, immediately returning `HTTP Error 429: Too Many Requests`. This forces the provider into fallback mode and prevents live quota updates.
3. The Web UI continues displaying "CALIBRATED WEB QUOTA" and manual calibration prompts because live OAuth usage queries hit 429 rate limits, despite the user having an active Claude Pro subscription and valid decrypted OAuth token.

---

## 2. Technical Requirements

### 2.1 Backend Claude Provider (`backend/providers/claude.py`)
1. **API Key Validation Guard**:
   - Before probing `https://api.anthropic.com/v1/messages`, validate that `api_key` looks like a genuine Anthropic API key:
     Must start with `"sk-ant-api03-"` or `"sk-ant-"` and have length `>= 40` characters.
   - If key is a placeholder, dummy, or shorter than 40 chars, do not probe `messages` endpoint and do not trigger 401 `AUTH_FAILURE`.
2. **In-Memory TTL Cache for OAuth Usage**:
   - Add an in-memory cache for `fetch_live_oauth_telemetry()` with a 300-second (5-minute) TTL (`_oauth_usage_cache` and `_oauth_usage_cache_time`).
   - If cached and fresh (< 300s old), return the cached usage metrics immediately without issuing an HTTP request.
   - If HTTP 429 is encountered, back off gracefully for at least 600 seconds (10 minutes) and return cached or fallback metrics without spamming error logs.
3. **Vault Sanitization Utility**:
   - If the stored Claude key in DPAPI is detected as invalid/dummy (e.g. `sk-ant-sec...`), remove it or bypass it so it does not interfere with direct OAuth synchronization.
4. **Zero-Calibration Autonomous Operation**:
   - When OAuth token is valid and returns profile/usage, mark provider status as `ACTIVE` with `CLAUDE PRO (OAUTH LIVE)` instead of prompting for manual calibration.

### 2.2 Security DPAPI Vault (`backend/security/dpapi_vault.py`)
1. Add `is_valid_api_key_format(provider, key)` validation helper to prevent persisting truncated dummy keys.

---

## 3. Verification Criteria

1. No `[AUTH_FAILURE] CLAUDE Unauthorized` error entries appear in the diagnostics log during background polling.
2. Direct calls to `fetch_live_oauth_telemetry()` respect the 300-second TTL cache, preventing HTTP 429 rate limit errors.
3. 20 automated unit tests pass in `tests/test_claude_auth_loop_elimination_and_oauth_cache.py`.
4. Full regression suite passes with 100% GREEN status.
