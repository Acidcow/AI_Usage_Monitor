# Design Decision: Tag Group Share Calculation & Pluralization Fixes

**Date**: 2026-10-26  
**Status**: Approved & Implemented  
**Author**: Antigravity Agent  
**Context**: AIUM-908  

---

## Context and Problem Statement

On wide-screen dashboards, under "Multi-Account Telemetry & Quota Comparison", grouping by tags caused tag rows to display `99358%` and `99376%`.
Investigation revealed that [`frontend/js/app.js`](file:///c:/AgenticDev/AI_Usage_Monitor/frontend/js/app.js) attempted to divide `grpTokens` by `comp.summary?.total_tokens_today || 10000`. The `/api/usage/comparison` payload structure does not contain a `summary` nested dictionary; rather, `total_tokens_today` exists at the top-level root. Consequently, the fallback `10000` was used as the denominator, inflating the percentage by ~1000x.
Additionally, the Historical Reports summary card displayed `1 slices` when a single active slice was returned.

---

## Decision

1. In `_buildTagGroupRows()`, compute `totalToday` using root `comp.total_tokens_today` with fallback to summing `tokens_today` across `comp.providers`.
2. Bound group share percentage between `0%` and `100%`:
   `const sharePct = Math.min(100, Math.round((grpTokens / totalToday) * 100));`
3. In `renderHistoricalReport()`, format slice labels with singular/plural awareness:
   `sliceCount === 1 ? '1 slice' : `${sliceCount} slices``.

---

## Consequences & Trade-offs

- Positive: Dashboard group share percentage reflects accurate estate share proportions with zero overflow.
- Positive: Text metrics and KPI cards exhibit professional typographic quality.
- Zero dependencies added.
