# Feature Recipe FR-102: Claude Multi-Mode Usage Provider

## 1. Goal
Track Claude token usage, sessions, rate limits, and plan status across multiple environments.

## 2. Modes of Operation
1. **Direct API Poller**:
   - Queries Anthropic API or Anthropic Admin/Usage endpoint with user API key.
   - Extracts input tokens, output tokens, remaining requests, and reset timestamps.
2. **Transparent Local Proxy**:
   - Runs a local HTTP proxy on `127.0.0.1:8765/v1/proxy/claude`.
   - Local CLI tools and IDE extensions send requests through this proxy.
   - Proxy forwards requests, intercepts token usage headers (`anthropic-ratelimit-*`), and logs metrics into SQLite.
3. **Local CLI Cache Scanner**:
   - Scans known local cache directories (for example `~/.claude/` or tool session files).
   - Ingests recent prompt tokens and completion tokens.
4. **Mock / Simulated Provider**:
   - Provides realistic live data for offline testing, demos, and rapid UI development.

## 3. Data Schema
Each record must contain:
- `provider`: "claude"
- `model`: e.g. "claude-3-7-sonnet", "claude-3-5-sonnet"
- `session_id`: Unique session or interaction ID
- `input_tokens`: Integer >= 0
- `output_tokens`: Integer >= 0
- `total_tokens`: Integer >= 0
- `estimated_cost_usd`: Float >= 0.0
- `rate_limit_tokens_remaining`: Integer or null
- `rate_limit_reset_epoch`: Timestamp or null
- `plan_type`: "Free", "Pro", "Team", "Enterprise"
- `recorded_at`: ISO8601 UTC timestamp

## 4. Verification Criteria
- Polling returns valid usage telemetry without unhandled network exceptions.
- Transparent proxy records request and response metrics accurately.
- Offline mock mode functions without internet connection.
