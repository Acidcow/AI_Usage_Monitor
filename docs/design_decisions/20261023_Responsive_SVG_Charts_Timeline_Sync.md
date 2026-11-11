# Architecture & Design Decision: Responsive Non-Stretching SVG Engine, Chart Timeline Synchronization & Model Sparkline Population

**Date**: 2026-10-23  
**Status**: Accepted  
**Author**: Antigravity  
**Ticket**: `AIUM-906`  
**Supercedes**: Static 900x200 SVG ViewBox Architecture  

---

## 1. Context & Problem Statement

Upon removing max-width constraints on the Web UI to take advantage of wide/ultrawide displays, the SVG charts (`#token-velocity-chart` and `.trend-chart-box`) were observed to stretch non-uniformly. This occurred because `<svg viewBox="0 0 900 200" preserveAspectRatio="none">` was mapped across 2400+ pixel containers. The browser scaled X by 2.6x+ while maintaining Y at 1.0x, deforming circular data points into horizontal ellipses, multiplying vertical stroke widths, and distorting monospace text labels.

Additionally, three telemetry integrity discrepancies were identified:
1. **Stale Hierarchical Trend Curves**: Clicking "Refresh" or "Sync Now" failed to update the Claude hierarchical curves beyond early morning timestamps because `cachedHierarchicalTrends` in JavaScript memory was never cleared upon polling.
2. **Empty Ollama Model Card Sparklines**: Active models (`nomic-embed-text:latest` with 427k tokens, `gemma:2b` with 25k tokens) displayed empty `0 t (idle)` sparklines due to string mismatch between `ollama_model_...` identifiers and model names, combined with lack of deferred sparkline rendering upon asynchronous trend arrival.
3. **Claude 1:1 Duplicate Individual & Team Curves**: Personal Claude Pro turns were assigned to both `child_buckets["individual"]` and `child_buckets["team"]` when `team_name == "Claude Pro"`, producing identical duplicate plots for individual user and team workspace pool.

---

## 2. Decision & Architecture

### A. Unified Responsive SVG Rendering Engine
- **Direct Container Measurement**: Charts measure `container.clientWidth` (or `getBoundingClientRect().width`) dynamically at render time.
- **1:1 Coordinate Mapping**: The SVG viewBox is configured as `0 0 ${width} ${height}`, setting 1 SVG coordinate unit equal to exactly 1 screen pixel.
- **Elimination of `preserveAspectRatio="none"`**: Uniform pixel mapping ensures circular points (`r="3.5"` / `r="4"`), razor-sharp lines (`stroke-width="2"`, `vector-effect="non-scaling-stroke"`), and crisp, un-stretched typography.
- **Debounced ResizeObserver**: Automatically triggers chart re-rendering when the browser window or container dimensions change without full page reloads.

### B. Client-Side Cache Lifecycle
- `this.cachedHierarchicalTrends` is purged on `loadUsageData()`, `syncProvider()`, and manual `↻ Refresh`.
- Every refresh cycle guarantees fresh data interrogation from `/api/usage/trends/hierarchy`.

### C. Child Sparkline Dynamic Dispatch
- Child sparklines are given unique DOM identifiers: `id="sparkline-${providerKey}-${safeId}"`.
- `getChildRealPoints()` uses case-insensitive, punctuation-agnostic string normalization (`replace(/[:_.-]/g, '')`).
- As soon as hierarchical trends resolve, `updateChildSparklines(providerKey, data)` updates all child cards immediately.

### D. Claude Individual vs. Team Disaggregation
- In `backend/storage/database.py`, `account_tier == "personal_pro"` is strictly isolated to `claude_individual`.
- `claude_team` (Team Workspace Pool) reflects actual team events or distinct team workspace allocation/burn derived from snapshot team utilization rather than mirroring personal turns 1:1.

---

## 3. Consequences

- **Visual Quality**: Crisp, legible, un-distorted SVG charts on 1080p, 1440p, 4K, 5K, and Ultrawide monitors.
- **Telemetry Accuracy**: Clear separation between individual seat consumption and team pool balances.
- **Responsive Feel**: Instant resizing without layout thrashing or font blurriness.
