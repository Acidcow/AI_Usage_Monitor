# Feature Recipe FR-205: Corporate Telemetry Importer & Manual Session Logger

## 1. Goal
Support locked-down enterprise environments like Microsoft 365 Copilot where direct network API calls are forbidden by corporate proxy.

## 2. Technical Requirements
1. **File Importer**:
   - Provide an endpoint `POST /api/usage/import` accepting JSON or JSONL exports.
   - Parse session timestamps, input tokens, output tokens, and models.
2. **Manual Session Logger**:
   - Provide `POST /api/usage/manual` allowing users to log token usage or estimate from prompt/response word counts.
3. Automatically mark provider as `ENTERPRISE_PASSIVE` with clear compliance notices.

## 3. Verification Criteria
- Correctly parses uploaded JSON and JSONL files.
- Manual sessions populate summary statistics accurately.
