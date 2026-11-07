# Feature Recipe: FR-1008 - 6 Ultra-Modern Selectable Themes & Layout Density Engine Across Web UI & Widgets

## Overview
This feature recipe formalizes Ticket AIUM-1008. It establishes a zero-external-dependency canonical theme and layout density engine spanning the Python backend, REST API, system tray / native floating widget, and HTML5/CSS3 frontend presentation layers. The architecture guarantees WCAG AA accessibility compliance (contrast ratio >= 4.5:1 across all background/text combinations) and full backward compatibility with legacy theme keys.

---

## Technical Specifications & Scope of Changes

### 1. Canonical Theme Catalog & Accessibility Protocol (`backend/contracts/themes.py`)
Provides canonical constants, dataclass/dictionary contracts, and WCAG 2.1 relative luminance and contrast ratio algorithms:
- **Canonical Themes**:
  1. `linear-obsidian`: Modern Linear-inspired dark mode (`bg_main: #090A0F`, `bg_card: #12141C`, `accent_primary: #5E6AD2`, `text_main: #F3F4F6`, `text_muted: #9CA3AF`, `text_dim: #8B95A5`, `border_color: #1F2430`).
  2. `geist-monochrome`: Vercel Geist-inspired OLED dark mode (`bg_main: #000000`, `bg_card: #0A0A0A`, `accent_primary: #00E599`, `text_main: #FFFFFF`, `text_muted: #A1A1AA`, `text_dim: #8E8E98`, `border_color: #27272A`).
  3. `cyberpunk-hud`: Tactical cybernetic dark mode (`bg_main: #07090E`, `bg_card: #0D121F`, `accent_primary: #00F0FF`, `text_main: #E2F1FF`, `text_muted: #7C9CBF`, `text_dim: #6989AC`, `border_color: #1B2A4A`).
  4. `catppuccin-mocha`: Warm aesthetic dark mode (`bg_main: #1E1E2E`, `bg_card: #181825`, `accent_primary: #CBA6F7`, `text_main: #CDD6F4`, `text_muted: #A6ADC8`, `text_dim: #9399B2`, `border_color: #313244`).
  5. `tokyo-night`: Oceanic storm indigo dark mode (`bg_main: #1A1B26`, `bg_card: #24283B`, `accent_primary: #7AA2F7`, `text_main: #C0CAF5`, `text_muted: #9AA5CE`, `text_dim: #828BB8`, `border_color: #3B4261`).
  6. `executive-paper`: Daylight high-contrast light mode (`bg_main: #F8FAFC`, `bg_card: #FFFFFF`, `accent_primary: #2563EB`, `text_main: #0F172A`, `text_muted: #475569`, `text_dim: #64748B`, `border_color: #E2E8F0`).
- **Backward-Compatible Aliases**:
  - `cyberpunk_dark` -> `cyberpunk-hud`
  - `glass_slate` -> `linear-obsidian`
  - `high_contrast_light` -> `executive-paper`
  - `matrix_emerald` -> `geist-monochrome`
  - `obsidian_neon` -> `linear-obsidian`
  - `cyberpunk` -> `cyberpunk-hud`
  - `midnight_slate` -> `tokyo-night`
- **Layout Densities**:
  - `compact`: Tight padding and maximized information density.
  - `balanced`: Default comfortable layout.
  - `ultrawide`: Expanded spacing for large monitors.
- **Canonical Provider Palette**:
  - `claude`: `#F59E0B`
  - `ollama`: `#10B981`
  - `gemini`: `#3B82F6`
  - `copilot`: `#8B5CF6`
  - `chatgpt`: `#10B981`
- **Accessibility Helpers**:
  - `calculate_relative_luminance(hex_color)`: Computes sRGB linear relative luminance according to WCAG 2.1 specs.
  - `calculate_contrast_ratio(hex1, hex2)`: Evaluates contrast ratio in range [1.0, 21.0].
  - `meets_wcag_aa(hex_fg, hex_bg, is_large_text)`: Validates threshold >= 4.5:1 (normal text) or >= 3.0:1 (large text).

### 2. REST API Theme Discovery (`backend/server/http_server.py`)
- Exposes `GET /api/themes`.
- Returns HTTP 200 with JSON payload:
  ```json
  {
    "themes": [...],
    "densities": ["compact", "balanced", "ultrawide"],
    "providers": {
      "claude": "#F59E0B",
      "ollama": "#10B981",
      "gemini": "#3B82F6",
      "copilot": "#8B5CF6",
      "chatgpt": "#10B981"
    }
  }
  ```

### 3. Frontend Styling and Mini Widget Presentation (`frontend/css/`, `frontend/mini_widget.html`)
- **`frontend/css/themes.css`**: Defines CSS variables for all 6 canonical themes, 7 legacy alias mappings, and 3 layout densities (`compact`, `balanced`, `ultrawide`).
- **`frontend/css/styles.css`**: Imports `themes.css`, raises `--text-dim` to `#8B95A5` to guarantee WCAG AA contrast ratio (> 6.5:1 on `#080B11`), and unifies provider palette across dashboard surfaces.
- **`frontend/css/widget.css`**: Provides theme-aware, standalone stylesheet for floating mini widgets.
- **`frontend/mini_widget.html`**:
  - Links `css/themes.css` and `css/widget.css`.
  - Injects `#bucket-select` and `#scope-select` into the toolbar.
  - Loads canonical core scripts (`js/core/formatters.js`, `js/core/api_client.js`, `js/core/chart_renderer.js`, `js/core/telemetry_hierarchy.js`) before `js/widget.js`.

### 4. Native Taskbar Desktop Widget (`backend/tray/native_widget.py`)
- Integrates `THEMES_CATALOG`, `resolve_theme_id`, and `PROVIDER_PALETTE`.
- Supports all 6 themes + 4 legacy themes in `THEMES`.
- Dynamically queries Windows display DPI / scale factor and enforces a minimum font size of 9pt on HiDPI displays.

---

## Verification & Automated Test Suite
- Test file: `tests/test_ultra_modern_theme_engine.py`
- Test assertions: >=20 unit tests covering contracts, contrast calculations, API endpoints, CSS rules, HTML selectors, and native widget font scaling.
