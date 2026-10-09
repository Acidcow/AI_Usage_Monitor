# Feature Recipe FR-614: Real Telemetry Trend Curves, Normalized Legend Mapping & Zero-Data Sparklines

## 1. Goal
Eliminate all artificial / synthetic modulo saw-tooth fallbacks across backend trend calculations, resolve the object property mismatch causing "undefined" legend labels and broken hover/toggle bindings, and implement Option A for mini-sparklines (real time-series data when available, or a clean muted zero-state indicator when cumulative tokens are 0).

## 2. Technical Requirements
1. **Eliminate Synthetic Modulo Saw-Tooth Curves**:
   - In `backend/storage/database.py:get_hierarchical_trends()`:
     - Remove all fallback modulo formulas `(i % 5) * 200`, `(i % 6) * 150`, `(i % 4) * 350 + 200`, etc.
     - When an entity or platform has zero recorded events in a given bucket, its points must be strictly `0`.
     - Claude hierarchy: if no specific sub-tier events exist, distribute proportionally based on actual recorded tokens, or return `0` if total is `0`.
     - Gemini: plot real token burns per `token_id`. If `sum(pts) == 0`, return flat zeroes `[0] * num_bins`.
     - Ollama: plot real token burns per `model`. If `sum(pts) == 0`, return flat zeroes `[0] * num_bins`.
     - Both `id` and `key` as well as `name` and `label` must be provided in series dictionaries to ensure complete backwards and forward compatibility.

2. **Normalize Legend Mapping and Series Attributes**:
   - In `frontend/js/app.js`:
     - Access series key via `s.key || s.id`.
     - Access series label via `s.label || s.name`.
     - Ensure data attributes (`data-series`) use `s.key || s.id`.
     - Ensure tooltips and legend titles properly display the entity name and token burn.
     - Hover highlight and visibility toggles match cleanly on the resolved key.

3. **Option A: Real Mini-Sparklines with Clean Zero-State Indicator**:
   - For table row platform sparklines and expanded child cards:
     - If cumulative tokens for the entity in the window are greater than 0, render real time-bucketed SVG sparklines.
     - If cumulative tokens in the window are 0 (no activity), render a clean, muted zero-state baseline or indicator (e.g. `— No activity in window —` or a clean flat zero baseline SVG), eliminating all fake synthetic multiplier arrays.

## 3. Verification Criteria
- [x] Backend `get_hierarchical_trends` returns 100% real data with zeroes for inactive periods; zero modulo formulas.
- [x] Backend series objects include both `id`/`key` and `name`/`label`.
- [x] Chart legend displays genuine labels (e.g. "Individual Member (You)", "Claude (Total Burn)") instead of "undefined".
- [x] Clicking legend entries toggles the corresponding line correctly.
- [x] Hovering legend pills or lines triggers matching glow effects without console warnings.
- [x] Zero-data platforms (Gemini, Ollama when inactive) show a flat zero baseline or clean muted indicator, not synthetic waves.
- [x] All unit tests pass with 100% success rate.
