# Feature Recipe: FR-1012-UX-POLISH-AND-LOG-DEDUP

**Ticket:** AIUM-1012  
**Title:** Troubleshooting Log Deduplication/Search, Report Date Presets & Provider Status Polish  
**Epic:** EPIC-V2.5-UNIFIED-OVERHAUL  

---

## Overview & Requirements

1. **Troubleshooting Log Viewer Polish & Deduplication**:
   - Add search input (`id="diag-log-search"`) and category/severity filter dropdown (`id="diag-log-category-filter"`) to the Troubleshooting log viewer header in `frontend/components/troubleshooter_panel.html`.
   - Implement helper `deduplicateDiagnosticErrors(errors)` in `frontend/js/app.js` (and use it in `loadDiagnostics` / `filterDiagnosticLogs`) that collapses consecutive or identical `(category, provider, message)` entries into a single row with a repeat count badge (e.g. `<span class="badge">×42</span>`) and latest timestamp, filtering by `#diag-log-search` and `#diag-log-category-filter`.

2. **Historical Reports Quick Date Presets**:
   - Add quick date preset pills (`Today`, `24h`, `7d`, `30d`, `MTD`, `All-Time`) calling `window.App.applyReportDatePreset('today' | '24h' | '7d' | '30d' | 'mtd' | 'all')` in `reports_panel.html`.
   - Implement `applyReportDatePreset(preset)` in `frontend/js/app.js` to populate `#report-filter-start-date` and `#report-filter-end-date` and trigger `loadHistoricalReport()`.

3. **Provider Hub, LAN Subnet & Theme Engine Polish**:
   - Ensure unconfigured optional providers (such as OpenAI / ChatGPT when no key is stored) display a neutral `"NOT CONFIGURED"` status badge instead of an alarming red `"ERROR"` badge.
   - Change default LAN discovery subnet placeholder/fallback from `/32` to `/24`.
   - Wire `applyTheme(themeId)` and `applyLayoutDensity(densityId)` in `frontend/js/app.js` so selecting any of the 6 themes (`linear-obsidian`, `geist-monochrome`, `cyberpunk-hud`, `catppuccin-mocha`, `tokyo-night`, `executive-paper`) sets `document.documentElement.setAttribute("data-theme", themeId)` on the main Web UI immediately.

4. **Testing**:
   - Create `tests/test_ux_polish_and_log_dedup.py` with `>=20` comprehensive unit tests verifying log deduplication badge logic, search/category filter elements, report date presets, neutral `NOT CONFIGURED` badge handling, `/24` CIDR subnet default, and `data-theme` application.
