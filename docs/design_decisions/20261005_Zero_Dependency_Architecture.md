# Architecture Decision Record: Zero-Dependency Pure Python Core

**Date**: 2026-10-05  
**Status**: Accepted  
**Deciders**: Engineering Team & Product Owner  

## Context
AI Usage Monitor is designed to track sensitive API usage and credentials on Windows desktop environments. Incorporating third-party packages (e.g. FastAPI, cryptography, pystray, PySide) introduces:
1. High supply-chain vulnerability attack surface.
2. Complex wheel compilation issues on diverse developer machines.
3. Heavy disk footprint and runtime startup latency.

## Decision
We build the core backend and desktop service entirely using Python 3 Standard Library:
- **Web & API Server**: `http.server.ThreadingHTTPServer` with custom JSON dispatch.
- **Data Persistence**: Built-in `sqlite3` for ACID local time-series metrics.
- **Network Requests**: Built-in `urllib.request` with SSL verification.
- **Frontend**: Vanilla ES6 JavaScript, HTML5, and CSS3 without build tools or node_modules.

## Consequences
- **Positive**: Zero install friction (`python run_monitor.py` works immediately), zero supply-chain vulnerabilities, fast cold start (<0.2s), minimal memory usage (<35MB RAM).
- **Negative**: Requires writing clean, lightweight HTTP request routing and JSON serialization utilities manually instead of relying on heavyweight frameworks.
