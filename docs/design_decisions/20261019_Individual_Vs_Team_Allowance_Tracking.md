# Architectural Design Decision: Individual vs. Team Allowance Tracking Mode Toggle & Hierarchy Streamlining

**Date**: 2026-10-19  
**Status**: Approved  
**Context**: Ticket AIUM-618 / Feature Recipe FR-618  

---

## 1. Context & Problem Statement

Official Anthropic Claude documentation and web session endpoints (e.g. `claude.ai/settings/usage` and session rate limit headers) report quotas, remaining balances, and reset countdowns at the **individual member level**, rather than as an artificial fraction or calculated conversion of an entire enterprise workspace pool.

Previously, AI Usage Monitor had introduced theoretical multi-scope hierarchical models (`individual`, `team`, `department`, `enterprise`) with estimated division budgets and workspace seat allocations. However, presenting calculated company shares alongside or above real personal session usage introduced cognitive overload and confusing conversion discrepancies.

Developers require a clear setting to track directly against their **1:1 personal platform quotas** (as officially reported by Claude, Gemini, etc.), removing higher-level theoretical hierarchies and conversion rates from views, while retaining the capability to switch to shared team pools when desired.

---

## 2. Decision & Architecture

### 2.1 Dual-Mode Tracking Configuration
We introduce a first-class system setting stored in SQLite `app_settings`:
- `quota_tracking_mode`: `"individual"` (default) | `"team"`.
- When set to `"individual"`:
  - Metrics resolution in `get_comparative_metrics()` operates in 1:1 direct mode without applying fractional conversions or estimated division calculations.
  - The returned hierarchy payload sets `tracking_mode: "individual"` and `streamlined: True`.
  - Theoretical organizational rollups (`department` active seats/budget, `enterprise` shared pool) are disabled (`enabled: False`) to prevent UI clutter.
  - The Web Dashboard scope bar simplifies to highlight **👤 Individual Direct Tracking (Active)**.
  - The Comparative Breakdown table drill-down accordion suppresses the artificial `Team Workspace Pool`, `Department / Division`, and `Organization / Enterprise` cards, displaying only real personal metrics and real physical child resources (such as local Ollama models or named Gemini developer keys).
- When set to `"team"`:
  - Multi-scope pills (`Individual`, `Team`, `Enterprise`) and hierarchy cards remain visible for organizations actively managing collective pooled limits.

### 2.2 Native Taskbar Widget Alignment
The native floating widget inspects `quota_tracking_mode`:
- In `"individual"` mode, the hover flyout renders clean personal session and weekly quotas directly:
  `• 👤 Session Quota: {sess_rem}% rem ({sess_used}% used)`
  `• 👤 Weekly Quota:  {week_rem}% rem ({week_used}% used)`
- The redundant/confusing calculated team pool line is suppressed.

### 2.3 Zero-Dependency & Backward Compatibility
- Strictly adheres to Python Standard Library (`sqlite3`, `http.server`, `json`).
- Automated fallback ensures existing databases without `quota_tracking_mode` smoothly default to `"individual"`.

---

## 3. Alternatives Considered
1. **Hardcoded removal of all hierarchy logic**: Rejected because enterprise users with team accounts may still want team pool views.
2. **Client-side only filter**: Rejected because the backend API needs to return clean, authoritative payloads and drive consistent widget and headless reporting.
