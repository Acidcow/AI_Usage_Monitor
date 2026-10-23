# AI Usage Monitor - Release Notes v0.9.6

**Release Identifier**: `v0.9.6`  
**Release Date**: 2026-10-23  
**Epic**: `EPIC-PLATFORM-OVERHAUL`  
**Ticket**: `AIUM-906`  
**Ways of Work Version**: v1.0.0  

---

## Executive Summary

AI Usage Monitor `v0.9.6` resolves SVG chart distortion on wide and ultrawide displays, unifies responsive rendering across all telemetry curves, synchronizes chart timelines between the Web UI and native Mini Widget, populates model sparklines in child hardware cards, and strictly disaggregates personal Claude Pro usage from team workspace pool burns.

---

## Key Capabilities & Changes

### 1. Responsive Non-Stretching SVG Engine
- **Elimination of `preserveAspectRatio="none"`**: Completely removed `preserveAspectRatio="none"` from `usage_gauge_card.html`, `renderSvgChart()`, `renderMultiSeriesTrendChart()`, and inline sparkline templates.
- **Dynamic Container Width Measurement**: Charts now measure `clientWidth` dynamically and set `viewBox="0 0 ${width} ${height}"`, maintaining a strict 1:1 ratio between SVG coordinate units and physical display pixels.
- **Crisp, Uniform Stroke & Geometry**: Applied `vector-effect="non-scaling-stroke"` across all trend lines, idle baselines, and gridlines. Circular data points remain perfectly circular, line thicknesses remain constant, and monospace typography remains legible across any screen width or aspect ratio.
- **Dynamic Time Axis Spacing**: Implemented dynamic interval calculations (`maxLabels = Math.floor(plotW / 85)`) to cleanly space time labels and prevent text overlap on wide or narrow screens.
- **Fluid Resize Observer**: Added debounced `ResizeObserver` on `#svg-chart-container` and `#container-usage-gauges` to re-render charts cleanly whenever the browser window or viewport size changes.

### 2. Chart Timeline & Refresh Synchronization
- **Live Cache Invalidation**: `loadUsageData()` and `syncProvider()` now invalidate `cachedHierarchicalTrends = {}` on every poll and sync action, eliminating stale cached curves.
- **Timeline Alignment**: Unified granular timeseries and hierarchical trend buckets using client-side timezone localization (`this.formatLocalTime`), ensuring that Token Velocity, Claude, Gemini, and Ollama plots terminate at the exact current workstation time.

### 3. Ollama Child Model Sparklines & Async DOM Hydration
- **Punctuation-Agnostic Matching**: Updated `getChildRealPoints()` and model sparkline selectors with normalized matching (`replace(/[^a-z0-9]/g, '')`), resolving the colon vs. underscore mismatch between model names (`nomic-embed-text:latest`) and sanitized series identifiers (`ollama_model_nomic-embed-text_latest`).
- **Asynchronous Sparkline Hydration**: Added `updateChildSparklines()` to asynchronously update `#sparkline-ollama-*`, `#sparkline-claude-*`, and `#sparkline-gemini-*` elements in the DOM immediately upon hierarchical trend resolution.
- **Responsive Inline Sparklines**: Replaced fixed-width sparkline SVGs with `viewBox="0 0 ${w} ${h}"`, `max-width: 140px`, and `vector-effect="non-scaling-stroke"`.

### 4. Claude Pro Personal vs. Team Workspace Disaggregation
- **Strict Personal Pro Routing**: Claude turns tagged with `account_tier == "personal_pro"` or personal subscriptions are strictly assigned to `claude_tier_buckets["personal_pro"]` and `child_buckets["individual"]`. They are no longer added to `child_buckets["team"]`.
- **Intelligent Team Workspace Pool Estimation**: When no external team events exist on the local workstation, `claude_team` computes the shared team workspace pool burn using the provider snapshot utilization ratio (e.g. 44% session rem / 56% used vs. 92% session rem / 8% used = ~7x ratio), completely eliminating 1:1 duplicate curves.

---

## Verification & Test Results

- **Feature Test Suite**: `tests/test_responsive_svg_charts_and_timeline_sync.py` (20/20 passed, 100%).
- **Full Platform Regression Suite**: `python dev_tools/manage_roadmap.py run-tests` (426/426 passed, 0 failures, 0 errors, 100% GREEN).
- **Zero External Dependencies**: Verified zero pip/npm packages introduced; 100% Python Standard Library and vanilla CSS/ES6.
