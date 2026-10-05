# Feature Recipe FR-302: Gemini & ChatGPT DPAPI Endpoint Wiring & Active Interrogation

## 1. Goal
Wire backend REST API endpoints `/api/providers/gemini/config` and `/api/providers/chatgpt/config` to securely encrypt API keys using Windows DPAPI, trigger active model interrogation, and return updated provider status to the frontend.

## 2. Technical Requirements
1. **HTTP Server API Routes**:
   - `POST /api/providers/gemini/config`: Accepts `{ "api_key": "..." }`, stores in DPAPI vault, triggers `GeminiProvider.sync_usage()`.
   - `POST /api/providers/chatgpt/config`: Accepts `{ "api_key": "..." }`, stores in DPAPI vault, triggers `ChatGPTProvider.sync_usage()`.
2. **Provider Implementations**:
   - Implement `ChatGPTProvider.configure_api_key(api_key)` and `sync_usage()` to interrogate `https://api.openai.com/v1/models`.
   - Verify `GeminiProvider.configure_api_key(api_key)` saves and queries `https://generativelanguage.googleapis.com/v1beta/models`.
3. **Frontend Modal Hookup**:
   - Connect `saveGeminiConfig()` and `saveChatGPTConfig()` in `app.js` to post to their respective endpoints with user feedback.

## 3. Verification Criteria
- Unit tests assert `/api/providers/gemini/config` and `/api/providers/chatgpt/config` return HTTP 200 and persist credentials.
- Unit tests verify DPAPI encryption and error categorization for invalid keys.
- All tests pass with 100% pass rate.
