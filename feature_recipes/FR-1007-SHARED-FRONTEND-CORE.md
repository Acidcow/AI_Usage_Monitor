# Feature Recipe FR-1007: Extract Shared Frontend Core (frontend/js/core/) for Full Web UI & Mini Widget

## 1. Specification (ASD-STE100 Simplified Technical English)
- **Problem**:
  1. Frontend formatting, chart generation, API communication, and telemetry hierarchy traversal were duplicated between `frontend/js/app.js` and `frontend/js/widget.js`.
  2. Floating Mini Widget (`widget.js`) contained synthetic fallback multipliers (`[0.7, 0.9, 1.1, 0.85, 1.15, 0.95]`) which fabricated artificial trend data when real points were missing, violating the zero-assumptions and empirical-verification engineering standard.
  3. Active app icon changes in the Full Web UI did not immediately synchronize with the Floating Mini Widget and Windows Tray due to fragmented persistence.
  4. Mini Widget lacked granular bucket and scope filter synchronization with backend settings and localStorage.
- **Solution**:
  1. Extract a shared, zero-external-dependency frontend core into four canonical ES modules under `frontend/js/core/`:
     - `formatters.js`: Unified number, currency, countdown, timestamp, and HTML escaping functions, plus canonical provider palette maps.
     - `api_client.js`: Canonical API fetching, settings storage, and cross-surface active icon synchronization (`syncActiveIcon`).
     - `chart_renderer.js`: Crisp, responsive SVG sparkline rendering using `vector-effect="non-scaling-stroke"`, linear gradient fill, and honest zero baselines (never fake wave multipliers).
     - `telemetry_hierarchy.js`: Canonical punctuation-agnostic hierarchy series extraction (`extractChildRealPoints`) returning real server points or strict zero baselines.
  2. Wire `frontend/index.html` to load all four core scripts before `app.js`.
  3. Refactor `app.js` and `widget.js` to delegate formatting, SVG sparkline rendering, hierarchy point resolution, and icon synchronization to `window.AIUMCore.*` while preserving safe fallbacks.
  4. Eliminate all synthetic multiplier arrays from `widget.js`.
  5. Add bucket granularity and scope filter synchronization to `widget.js`.

## 2. Architecture Decisions
- Global namespace: `window.AIUMCore = window.AIUMCore || {};` with `Formatters`, `ApiClient`, `ChartRenderer`, and `TelemetryHierarchy` sub-namespaces.
- Node / CommonJS fallback exports: `if (typeof module !== 'undefined' && module.exports) module.exports = ...` to enable automated unit verification.
- SVG rendering: pure standards-compliant SVG with `viewBox`, `vector-effect="non-scaling-stroke"`, and linearGradient fill. Flat honest line `[0, 0, ...]` for idle states.
- Multi-surface synchronization: `syncActiveIcon` updates both `localStorage` and `POST /api/settings` (`active_icon`), coordinating Web UI, Mini Widget, and Windows Tray.

## 3. Test Assertions (>=20 Unit Tests)
1. `test_01_core_directory_and_modules_exist`: Verifies all 4 core JS files exist on disk.
2. `test_02_formatters_exports_format_tokens`: Verifies `formatTokens` formats 850, 45.3k, 1.2M, 2.5B, and 0 correctly.
3. `test_03_formatters_exports_format_currency`: Verifies `formatCurrency` formats standard $0.00, micro-cost $0.0042, and custom decimal values.
4. `test_04_formatters_exports_format_countdown`: Verifies `formatCountdown` formats hour-minute (2h 14m) and minute-second (45m 12s) intervals.
5. `test_05_formatters_exports_datetime_and_duration`: Verifies `formatLocalDateTime`, `formatLocalTime`, and `formatDuration`.
6. `test_06_formatters_exports_escape_html`: Verifies `escapeHtml` neutralizes HTML special characters.
7. `test_07_formatters_canonical_provider_maps`: Verifies `PROVIDER_COLORS` and `PROVIDER_NAMES` cover Claude, Ollama, Gemini, Copilot, ChatGPT.
8. `test_08_api_client_exports_required_methods`: Verifies `getSettings`, `saveSettings`, `getThemes`, `getHierarchies`, `getHierarchicalTrends`, `getGranularTimeseries`, `syncActiveIcon`.
9. `test_09_api_client_sync_active_icon_persists_settings`: Verifies `syncActiveIcon` sets localStorage and posts to `/api/settings`.
10. `test_10_api_client_themes_definition`: Verifies `getThemes` provides obsidian, cyberpunk, matrix, and midnight variants.
11. `test_11_chart_renderer_exports_generate_sparkline_svg`: Verifies `generateSparklineSvg` produces SVG with `vector-effect="non-scaling-stroke"`.
12. `test_12_chart_renderer_idle_points_flat_zero_baseline`: Verifies all-zero points produce honest idle indicator and zero fake waves.
13. `test_13_chart_renderer_active_points_polyline_and_gradient`: Verifies non-zero points generate polyline, circle, and linearGradient fill.
14. `test_14_chart_renderer_multi_sparkline_svg`: Verifies `generateMultiSparklineSvg` renders multi-series overlaid lines with non-scaling-stroke.
15. `test_15_telemetry_hierarchy_exports_extract_child_real_points`: Verifies `extractChildRealPoints` function presence.
16. `test_16_telemetry_hierarchy_punctuation_agnostic_matching`: Verifies colon, dash, underscore matching for Ollama models and accounts.
17. `test_17_telemetry_hierarchy_idle_returns_honest_zero_baseline`: Verifies missing or empty series return strict zeroes `[0, 0, 0, 0, 0, 0, 0, 0]`.
18. `test_18_zero_synthetic_multipliers_in_widget_and_core`: Verifies `[0.7, 0.9, 1.1` fake multiplier waves are completely eliminated from `widget.js`, `app.js`, and `core/`.
19. `test_19_index_html_wires_all_core_scripts`: Verifies `index.html` includes all 4 core scripts immediately before `app.js`.
20. `test_20_widget_js_delegates_to_core_formatters_and_charts`: Verifies `widget.js` defines delegation methods to `window.AIUMCore.*`.
21. `test_21_widget_js_bucket_and_scope_synchronization`: Verifies `widget.js` supports `bucketMins`, `scopeFilter`, `setBucketMins`, and `setScopeFilter`.
22. `test_22_app_js_delegates_to_core_modules`: Verifies `app.js` delegates sparkline, hierarchy points, and formatters to `window.AIUMCore.*`.
