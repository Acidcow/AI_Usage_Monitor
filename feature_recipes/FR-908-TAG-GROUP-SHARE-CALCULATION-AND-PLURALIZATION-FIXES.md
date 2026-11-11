# Feature Recipe FR-908: Tag Group Share Calculation & Pluralization Fixes

**Ticket**: AIUM-908  
**Epic**: EPIC-PLATFORM-OVERHAUL  
**Priority**: Critical  
**Status**: In Progress  
**Standard**: ASD-STE100 Simplified Technical English  

---

## 1. Problem Statement

In the AI Usage Monitor Web UI:
1. In the "Multi-Account Telemetry & Quota Comparison" table on the Dashboard, tag group rows (e.g. `Production AI (Claude + Gemini)`, `Development & Testing`, `Research & Labs`) display an incorrect `Share %` such as `99358%` and `99376%`.
   - **Root Cause**: In [`frontend/js/app.js`](file:///c:/AgenticDev/AI_Usage_Monitor/frontend/js/app.js#L1021), the calculation references `comp.summary?.total_tokens_today || 10000`. The endpoint `/api/usage/comparison` returns `total_tokens_today` at root object level (`comp.total_tokens_today`), not inside `summary`. Because `comp.summary` is undefined, the math divides by 10,000 instead of ~9.93M total tokens, producing an inflated percentage.
2. In the "Historical Usage Reports & Cost Attribution" view, the KPI summary card displays grammatical pluralization errors, for example: `ACTIVE SLICES: 1 slices`.

---

## 2. Technical Requirements

### 2.1 Frontend Engine (`frontend/js/app.js`)
1. In `_buildTagGroupRows(comp)`:
   - Accurately resolve total tokens today:
     `const totalToday = comp.total_tokens_today || Object.values(comp.providers || {}).reduce((acc, p) => acc + (p.tokens_today || 0), 0) || 1;`
   - Compute group share percentage:
     `const sharePct = Math.min(100, Math.round((grpTokens / totalToday) * 100));`
   - Ensure clean formatting with `%` suffix (e.g., `100%`, `18%`, `<1%`).
2. In `renderHistoricalReport(reportData)`:
   - Fix slice count display:
     `const sliceCount = reportData.rows ? reportData.rows.length : 0;`
     `const sliceLabel = sliceCount === 1 ? '1 slice' : `${sliceCount} slices`;`
     Ensure the KPI card reads `1 slice` when singular and `N slices` when plural.

---

## 3. Verification Criteria

1. Tag group share percentages in "Multi-Account Telemetry & Quota Comparison" are bounded between `0%` and `100%` and match actual provider consumption proportions.
2. Single-row historical reports display `1 slice` instead of `1 slices`.
3. 20 automated unit tests pass in `tests/test_tag_group_share_and_pluralization.py`.
4. Full regression suite passes with 100% GREEN status.
