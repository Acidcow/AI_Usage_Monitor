# Feature Recipe FR-610: Estate Throughput, Burst Performance & Capacity Analytics

## 1. Goal
Provide proactive analytical telemetry reporting and estate capacity management across all platforms and accounts. Compute granular operational metrics including usage averages, burst versus sustained throughput, peak velocity, and predictive quota depletion to optimize estate allocations and prevent rate limit interruptions.

## 2. Technical Requirements
1. **Mathematical Analytics & Time-Series Engine**:
   - Calculate rolling 1-hour, 24-hour, and 7-day token consumption averages.
   - Profile burst velocity (maximum tokens consumed in any 5-minute window) vs sustained baseline throughput.
   - Detect concurrency spikes and request queuing latency.
2. **Predictive Exhaustion Modeling**:
   - Linear and exponential projection of token consumption against remaining session and weekly allowances.
   - Estimate Time-To-Exhaustion (TTE) for active accounts (e.g., "Warning: At current velocity of 4.2k tokens/min, Claude 5-hour quota will exhaust in 47 minutes").
3. **Estate Optimization Advisor**:
   - Dynamic heuristic recommendations comparing local vs cloud models:
     - Suggest shifting routine batch summarization and classification to local Ollama (Llama 3.2 / Qwen 2.5) to preserve cloud frontier quotas.
     - Identify idle accounts or unbalanced usage distribution across registered API keys.
4. **Data Storage & REST APIs**:
   - SQLite tables `telemetry_analytics_snapshots` and `capacity_forecasts`.
   - REST endpoints:
     - `GET /api/analytics/throughput`: Provides burst vs sustained stats per model/platform.
     - `GET /api/analytics/forecast`: Provides estimated exhaustion times and rate limit alerts.
     - `GET /api/analytics/recommendations`: Provides automated estate optimization advice.
5. **Interactive UI Visualization**:
   - Dashboard Capacity Analytics tab with dual-axis throughput charts (Tokens/Min vs Concurrency).
   - Speedometer gauges displaying estate utilization % and peak burst factors.

## 3. Verification Criteria
- Mathematical unit tests verifying rolling averages, burst velocity calculation, and TTE projections.
- Mock telemetry streams validating alert generation when velocity exceeds sustainable limits.
- Zero external dependencies.
