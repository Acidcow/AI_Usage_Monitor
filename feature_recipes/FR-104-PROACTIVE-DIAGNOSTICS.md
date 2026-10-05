# Feature Recipe FR-104: Proactive Redacted Diagnostics & Logging Engine

## 1. Goal
Detect, categorize, and log system and provider errors safely.
Enable users to export sanitized diagnostic packages for rapid troubleshooting without leaking secrets.

## 2. Technical Requirements
1. **Automated Secret Redaction**:
   - Redact all Anthropic keys (`sk-ant-api03-...` -> `sk-ant-***`).
   - Redact OpenAI keys (`sk-...` -> `sk-***`).
   - Redact session cookies, bearer tokens, passwords, and private directory paths.
2. **Error Categorization**:
   - Classify errors into: `AUTH_FAILURE`, `RATE_LIMIT_EXCEEDED`, `NETWORK_TIMEOUT`, `PROXY_BLOCKED`, `SCHEMA_ERROR`, `INTERNAL_EXCEPTION`.
   - Track error counts, timestamps, and provider source.
3. **Diagnostic Bundle Export**:
   - Generate single-click sanitized JSON or ZIP bundle containing:
     - Platform metadata (OS version, Python version, monitor uptime).
     - Provider status matrix (connection status, last sync time).
     - Recent sanitized error events (last 50 events).
     - Anonymized token summary metrics.
   - User can copy JSON to clipboard directly from the Web UI or save to a file.

## 3. Verification Criteria
- Redaction regex catches all known secret formats in test strings.
- Exported bundle contains zero plaintext credentials.
- Error counts increment accurately on simulated network failures.
