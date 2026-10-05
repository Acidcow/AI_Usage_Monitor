# Feature Recipe FR-204: Google Gemini Live Provider with DPAPI Vault

## 1. Goal
Support Google Gemini (AI Studio / Vertex) credentials and model usage tracking.

## 2. Technical Requirements
1. Encrypt and store Gemini API Key (`AIza...`) using Windows DPAPI.
2. Interrogate Google AI Studio model quota via `https://generativelanguage.googleapis.com/v1beta/models?key=...`.
3. Support proxy forwarding for Gemini endpoints (`/v1beta/models/...`).

## 3. Verification Criteria
- Key stored securely via DPAPI.
- Models query returns active Google Gemini models without errors.
