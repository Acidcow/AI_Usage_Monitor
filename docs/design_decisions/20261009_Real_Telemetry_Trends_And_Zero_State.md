# Architectural Decision Record: Real Telemetry Trends, Normalized Legend Keys & Zero-Data State Handling

**Date**: 2026-10-09  
**Status**: Accepted  
**Ticket**: AIUM-614  
**Feature Recipe**: FR-614  

## Context
During initial development of hierarchical trend overlays in AIUM-611 and AIUM-612, fallback mock generators (`(i % 5) * 200`, `(i % 6) * 150`, etc.) were introduced so that UI charts would display visual curves during testing even when no database telemetry was logged. However, in live production environments, these fallback calculations manifested as artificial saw-tooth waves across platforms with zero usage (e.g., Gemini and Ollama) and formed a distracting artificial floor beneath genuine token spikes in Claude.

Additionally, a property name divergence existed between backend dictionary keys (`id`, `name`) and frontend JavaScript chart rendering expectations (`key`, `label`), causing legend items to render as "undefined" and breaking bidirectional hover and visibility toggle bindings.

Furthermore, inline sparklines in table rows and child hierarchy cards relied on hardcoded multiplier arrays scaled by today's token total (with a minimum of 100 tokens), drawing artificial curves even when zero tokens had been consumed.

## Decision
1. **Strictly Real Telemetry in Backend Aggregation**:
   - Strip all synthetic modulo formulas from `get_hierarchical_trends()` in `backend/storage/database.py`.
   - Buckets with zero usage must return `0`.
   - Ensure every series dictionary includes dual aliases: `id` and `key`, and `name` and `label`, ensuring zero ambiguity across backend callers and frontend components.

2. **Unified Legend Property Resolution**:
   - In `frontend/js/app.js`, normalize series identification to `s.key || s.id` and display labeling to `s.label || s.name`.
   - This ensures legend pills render their canonical names and binds hover glows and visibility filters directly to the series identifier.

3. **Option A for Mini-Sparklines**:
   - For platforms or child entities with zero activity in the active window, render a clean muted zero baseline or indicator rather than calculating artificial shapes.
   - For platforms with active usage, render real historical data points matching the selected window.

## Consequences
- Eliminates deceptive artificial data.
- Charts accurately represent real-world telemetry (flat zero when idle, true peaks when active).
- Legend pills display accurate names and toggle/glow their corresponding chart paths reliably.
- Preserves zero external dependencies.
