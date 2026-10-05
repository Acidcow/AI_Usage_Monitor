# Architecture Decision Record: Claude Multi-Mode Usage Ingestion & Fallbacks

**Date**: 2026-10-05  
**Status**: Accepted  

## Context
Claude environments vary widely across corporate setups. In some environments, engineers have direct Anthropic API keys. In others, enterprise environments lock down direct internet access and require developers to route through CLI proxies or use corporate web sessions.

## Decision
We implement a four-tier fallback ingestion architecture for Claude:
1. **Tier 1: Direct Anthropic API / Admin Poller**: Queries official endpoints using DPAPI-stored API key.
2. **Tier 2: Transparent Intercepting Local Proxy**: A local endpoint (`http://127.0.0.1:8765/v1/proxy/claude`) that CLI tools (e.g. `claude-code`, Continue, Aider) can use as their base URL. It records all request/response tokens and rate-limit headers automatically, then forwards the response to the target upstream.
3. **Tier 3: Local Log & Cache Scanner**: Scans local file directories for existing session cache files.
4. **Tier 4: Offline / Simulated Telemetry Generator**: Allows users and developers to test dashboard views, widget gauges, and rate-limit alerts with realistic mock token feeds when offline.

## Consequences
- Guarantees seamless functionality regardless of corporate network restrictions or proxy configurations.
- Transparent proxy allows 100% accurate token tracking for local CLI coding without needing special API access.
