# Architecture Decision Record: Estate Throughput, Burst Performance & Capacity Analytics

**Date**: 2026-10-08  
**Status**: Accepted  
**Authors**: Antigravity Engineering  
**Derived Standard**: KloGnist WoW v2.5.0 / ASD-STE100  
**Epic**: `EPIC-ESTATE-BENCHMARKING`  
**Ticket ID**: `AIUM-610`  

## Context & Problem Statement
As developers and agentic workflows consume tokens across multiple platforms (Claude, Google Gemini, ChatGPT, Ollama Local Models, and Copilot), usage spikes often trigger sudden rate limits or deplete daily/weekly allowances prematurely.
Estate managers and power users lack proactive analytical visibility into:
1. Operational throughput metrics (rolling averages, peak burst velocity vs sustained throughput).
2. Predictive quota depletion: knowing when an active session or weekly allowance will run out based on current velocity.
3. Heuristic estate optimization: identifying when expensive cloud calls could be delegated to local zero-cost models (e.g. Ollama).

## Decision & Design Rationale
1. **Mathematical Analytics Engine (`backend/analytics/throughput_engine.py`)**:
   - Zero-dependency mathematical algorithms using Python standard library (`datetime`, `math`, `statistics`).
   - Computes:
     - Rolling token averages (1h, 24h, 7d).
     - Peak burst factor: maximum tokens consumed within any sliding 5-minute window compared to the 1-hour sustained baseline.
     - Velocity (tokens per minute, requests per minute).
2. **Predictive Exhaustion & Rate-Limit Alerting**:
   - Computes Time-To-Exhaustion (TTE):
     $$\text{TTE (minutes)} = \frac{\text{Tokens Remaining in Session Quota}}{\max(1, \text{Rolling 15-Minute Token Velocity (tokens/min)})}$$
   - Generates status severity (`HEALTHY`, `WARNING`, `CRITICAL_EXHAUSTION`) and clear human-readable alerts.
3. **Estate Optimization Heuristic Advisor**:
   - Analyzes model-level distributions:
     - Identifies low-complexity or high-frequency prompt patterns and recommends routing to Ollama local models (saving ~$6.00/M tokens).
     - Identifies unbalanced key utilization and recommends rotating or load-balancing keys.
4. **Data Storage & REST APIs (`backend/server/http_server.py`)**:
   - Endpoints:
     - `GET /api/analytics/throughput`: Model and platform burst vs sustained stats.
     - `GET /api/analytics/forecast`: Exhaustion predictions, TTE minutes, and active alert warnings.
     - `GET /api/analytics/recommendations`: Actionable advice for cost and capacity optimization.
5. **Interactive UI View (`frontend/components/capacity_analytics.html`, `frontend/js/app.js`)**:
   - A dedicated **Capacity & Throughput** view in the Web Dashboard.
   - Dual-axis throughput visualization (Velocity vs Concurrency).
   - TTE speedometer gauges and optimization advisory cards.

## Consequences & Verification
- Unit test suite in `tests/test_throughput_analytics.py` verifying rolling math, burst velocity calculation, TTE projections, and heuristic rules.
- 100% pass rate with zero external pip or npm dependencies.
