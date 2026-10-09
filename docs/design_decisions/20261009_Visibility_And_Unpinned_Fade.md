# Architectural Decision Record: Strict Platform Visibility Enforcement & Unpinned Widget Focus-Loss Fade

- **Status**: Accepted
- **Date**: 2026-10-09
- **Deciders**: AI Usage Monitor Engineering Team
- **Context**: Ticket `AIUM-616` (FR-616)

## 1. Context & Problem Statement
Users configured platform visibility toggles in the Settings panel (e.g. hiding Gemini or Copilot), but observed that:
1. The Web Dashboard hierarchy and charts continued to render the hidden platforms because `this.appSettings` was only asynchronously populated when the user explicitly navigated to the Settings view, and the settings HTML lacked element IDs (`vis-chk-{provider}`) required by the checkbox save/load logic.
2. The Native Mini Widget (`native_widget.py`) and Web Mini Widget (`widget.js`) did not consistently remove hidden items, especially when items had been previously pinned or when no pinned items were configured.
3. Unpinned items did not reliably fade out or disappear when the widget lost focus, because unpinned items had a fallback showing the first two unpinned items, or used minimal opacity rather than hiding completely.

## 2. Decision
1. **Strict Precedence of Visibility Over Pinning**:
   - Platform visibility is a hard master filter: `is_visible(p) = (p not in hidden_platforms)`.
   - Pinned state is an orthogonal secondary flag: an item can be pinned, but if its platform is marked not visible, it is strictly excluded from all rendering in both Web Dashboard and Mini Widgets. Under no circumstance may a pinned hidden item be displayed.

2. **Immediate Settings Bootstrapping**:
   - In `backend/storage/database.py`, `get_all_settings()` will always include `"estate_visibility": self.get_estate_visibility()` in its initial returned dictionary.
   - In `frontend/js/app.js`, `await this.loadSettings()` is invoked during `init()` before data polling and DOM rendering, ensuring `this.appSettings` is populated immediately.
   - HTML elements in `frontend/components/settings_panel.html` will have explicit IDs `vis-chk-{provider}` for clean, two-way data-binding.

3. **Widget Focus-Loss Collapse**:
   - In `native_widget.py`, when `fade_unpinned` is active and `has_focus` is `False`, the rendered provider list is strictly `[p for p in all_providers if p in self.pinned_items and p not in self.hidden_platforms]`. If no pinned items exist, the widget displays an idle/compact bar rather than falling back to unpinned providers.
   - Window activation events (`<FocusIn>`, `<FocusOut>`) will toggle `has_focus` and trigger immediate canvas re-layout.
   - In `frontend/js/widget.js`, when `fade_unpinned` is enabled and the widget is blurred, unpinned cards are hidden (`display: none`), and re-shown upon focus.

## 3. Consequences
- **Positive**:
  - Consistent platform privacy and clutter reduction across all views.
  - Zero leakage of hidden platforms into status pills, hierarchy cards, or 24-hour velocity charts.
  - Native widget respects focus states reliably without confusing fallbacks.
- **Negative / Trade-offs**:
  - If a user hides a platform, any existing pinned items for that platform will disappear until visibility is re-enabled. This is the desired behavior requested by the user.
