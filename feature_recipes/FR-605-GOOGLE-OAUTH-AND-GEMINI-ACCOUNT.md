# Feature Recipe: FR-605 - Google OAuth 2.0 Loopback Sign-In & Gemini Account Integration

## 1. Specification & Objectives
- **Ticket**: `AIUM-605`
- **Module**: `backend/security/google_auth.py`, `backend/providers/gemini.py`, `backend/server/http_server.py`, `frontend/`
- **Goal**: Enable direct Google Account sign-in (e.g. `acidcow@gmail.com`) for Google Gemini with zero external dependencies, providing account-level identity, quota tracking, and multi-token child registry.

## 2. Technical Requirements
1. **Zero External Dependencies**:
   - Use Python standard library: `urllib.request`, `urllib.parse`, `http.server`, `json`, `hashlib`, `secrets`, `base64`, `webbrowser`.
2. **Native Windows Security**:
   - Store Google OAuth access tokens, refresh tokens, and client secrets in Windows DPAPI (`backend/security/dpapi_vault.py`).
   - Plaintext credentials strictly forbidden.
3. **PKCE Loopback Flow**:
   - Generate cryptographically secure `code_verifier` and `code_challenge` (S256).
   - Listen on loopback callback `/api/auth/google/callback` on the server port.
   - Exchange authorization code for token securely.
   - Query Google UserInfo endpoint (`https://www.googleapis.com/oauth2/v3/userinfo`) to obtain email (`acidcow@gmail.com`), name, and profile.
4. **Gemini Provider Multi-Token & Account Hierarchy**:
   - Store account info in `provider_snapshots` for Gemini (`account_id: acidcow@gmail.com`, `user_name`, `status: ACTIVE`).
   - Manage registered tokens under the account with friendly descriptions/names (e.g., `Flash Dev Token`, `CLI Workstation Token`).
5. **REST API Endpoints**:
   - `GET /api/auth/google/login`: Initiates OAuth URL with PKCE state.
   - `GET /api/auth/google/callback`: Receives auth code, exchanges token, saves to DPAPI vault, updates snapshot.
   - `GET /api/auth/google/status`: Returns current Google account sign-in status (email, name, picture, tokens registered).
   - `POST /api/auth/google/tokens`: Add/remove named API tokens under the Google account.
   - `POST /api/auth/google/disconnect`: Revoke and clear stored credentials.

## 3. TDD Baseline & Assertions
- `TestGoogleOAuth`:
  - `test_generate_auth_url_and_pkce`: Verifies SHA256 code challenge generation and valid OAuth URL.
  - `test_exchange_code_and_store_dpapi`: Verifies token exchange mock and encryption in DPAPI vault.
  - `test_gemini_account_identity_and_multi_tokens`: Verifies Gemini provider returns `account_id="acidcow@gmail.com"` with child token metadata.
  - `test_google_auth_api_endpoints`: Verifies HTTP endpoints.
