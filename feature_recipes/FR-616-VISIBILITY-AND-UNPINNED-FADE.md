# Feature Recipe FR-616: Strict Platform Visibility Enforcement & Unpinned Widget Focus-Loss Fade

## 1. Goal
Enforce strict platform visibility toggling across both the Web Dashboard and Mini Widgets (Native Tkinter taskbar widget and Web mini widget). Guarantee that visibility toggles (`estate_visibility.hidden_platforms`) strictly override pinning (hidden platforms must never render under any condition). Ensure that when `fade_unpinned` is enabled, unpinned items reliably fade out of view / collapse when the widget loses focus.

## 2. Technical Requirements
1. **Backend Storage & Settings Propagation (`backend/storage/database.py`)**:
   - In `get_all_settings()`, guarantee that `"estate_visibility": self.get_estate_visibility()` is always included in the returned defaults dictionary so clients and widgets receive visibility configuration immediately upon polling.
   - Ensure `get_estate_visibility()` returns sanitized lowercased platform lists.

2. **Frontend Settings Panel Checkbox Binding (`frontend/components/settings_panel.html`)**:
   - Add explicit IDs (`vis-chk-claude`, `vis-chk-gemini`, `vis-chk-chatgpt`, `vis-chk-ollama`, `vis-chk-copilot`) to the visibility checkboxes in the Settings Panel so `loadSettings()` and `saveSettings()` can properly read and write visibility states.

3. **Dashboard Immediate Settings Ingestion & Filtering (`frontend/js/app.js`)**:
   - In `init()`, call `await this.loadSettings()` before initial polling and comparison rendering, ensuring `this.appSettings` is available immediately on page load rather than only after clicking the Settings tab.
   - In `renderComparison()`, filter out any platform listed in `this.appSettings.estate_visibility.hidden_platforms` from the estate tree and hierarchy cards.
   - In `renderPills()`, filter out hidden platforms from top status pills.
   - In `renderSvgChart()`, filter out hidden platforms from the 24-hour token velocity chart series and legend items.

4. **Native Mini Widget Visibility & Focus Loss Fade (`backend/tray/native_widget.py`)**:
   - Guarantee `p not in self.hidden_platforms` strictly overrides pinning: hidden platforms are unconditionally excluded from rendering.
   - When `self.fade_unpinned` is enabled and the widget is unfocused (`not self.has_focus`), filter provider list to ONLY pinned, non-hidden items: `[p for p in all_providers if p in self.pinned_items and p not in self.hidden_platforms]`.
   - Remove fallback that displays unpinned items when no pinned items exist during focus loss; display clean idle/pinned state instead.
   - Ensure `<FocusIn>` and `<FocusOut>` events reliably trigger canvas redraw and geometry readjustment.

5. **Web Mini Widget Visibility & Focus Loss Fade (`frontend/js/widget.js`)**:
   - In `render()`, strictly skip cards for platforms in `this.hiddenPlatforms`.
   - When `this.fadeUnpinned && !this.hasWindowFocus`, unpinned cards must be completely hidden (`display: none` / full fade out).
   - Ensure window blur and focus listeners trigger immediate re-render.

## 3. Verification Criteria
- [x] Toggling off visibility for a platform in Settings immediately hides it from the Web Dashboard comparison hierarchy, top pills, and 24h velocity chart.
- [x] Hidden platforms are never rendered in the Native Mini Widget or Web Mini Widget, even if the platform was previously pinned.
- [x] When `fade_unpinned` is true, unpinned items are hidden/faded out when the widget loses focus.
- [x] When widget regains focus, unpinned items reappear smoothly.
- [x] Unit tests in test suite verify strict visibility override and unpinned focus loss filtering.
- [x] All tests pass with 100% green rate.
