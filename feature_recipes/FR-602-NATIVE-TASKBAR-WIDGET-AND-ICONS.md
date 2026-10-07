# Feature Recipe FR-602: Zero-Browser Native Taskbar Widget & Identifiable Tray Icons

## 1. Goal
Provide a 100% native desktop taskbar widget that functions without requiring a web browser process, upgrade system tray icons to identifiable Johnny 5 and Cyber Shield visuals, and implement multi-platform SVG velocity line graphs with interactive legends.

## 2. Technical Requirements
1. **Zero-Browser Native Taskbar Widget (`backend/tray/native_widget.py`)**:
   - Built exclusively with Python 3 Standard Library (`tkinter` + `ctypes`).
   - Chromeless (`overrideredirect(True)`), pinned on-top (`-topmost`), translucent dark cyber styling (`-alpha 0.97`, `#080b11` / `#0d131f`).
   - Automatic bottom-right docking geometry right above the Windows taskbar with draggable header.
   - Live canvas rendering for all 5 accounts (Claude, Gemini, ChatGPT, Ollama, Copilot):
     - Session balance remaining % (emerald/cyan)
     - Weekly balance remaining % (purple/blue)
     - Tokens used today
     - Hover pop-up telemetry flyout with exact quota numbers and reset timers.
   - Ambient bottom strip displaying local AI dollars saved.
   - Periodic 3-second non-blocking poller querying local monitor server.
2. **Identifiable System Tray Icons (`backend/tray/icon_factory.py`)**:
   - Zero-dependency pixel generator producing standard 32x32 Windows `.ico` files:
     - `app_icon_johnny5.ico`: Glowing cyan optic lenses, metallic visor bar, antenna mount, and chin chassis.
     - `app_icon_shield.ico`: Transparent dark cyber shield with cyan outline and neon purple diagonal slash.
   - Native `HICON` loader via Win32 `LoadImageW` / `CreateIconIndirect`.
   - Update `WindowsTrayManager` in `backend/tray/windows_tray.py` to display the custom icon rather than generic `IDI_APPLICATION`.
3. **Multi-Platform SVG Velocity Line Graphs (`frontend/components/usage_gauge_card.html`, `frontend/js/app.js`)**:
   - Replace bar chart with multi-series line curves for Claude, Gemini, ChatGPT, Ollama, and Copilot.
   - Interactive legend bar with colored platform pills; clicking isolates or highlights specific platform curves.
   - 24-hour continuum with hourly timestamp ticks, dashed reference grid lines, and interactive hover tooltips.

## 3. Verification Criteria
- Unit tests verify `.ico` asset generation and `HICON` creation.
- Native taskbar widget initializes, renders canvas elements, and closes cleanly in automated headless tests.
- 100% test pass rate across all test suites.
