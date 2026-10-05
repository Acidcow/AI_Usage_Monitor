# Feature Recipe FR-103: Windows System Tray & Status Bar Widget

## 1. Goal
Provide immediate, ambient visibility of AI token usage, rate limits, and plan status on Windows.

## 2. Technical Requirements
1. **Windows System Tray**:
   - Use `Shell_NotifyIconW` via Python `ctypes` and `shell32.dll`.
   - Display dynamic tooltip with live Claude token totals, remaining quota, and reset countdown.
   - Support right-click context menu: Open Dashboard, Launch Mini Widget, Refresh Now, Export Diagnostics, Exit.
   - Display Windows balloon / toast notification when token threshold (>80% quota) is reached.
2. **Mini Status Bar Widget**:
   - Provide a ultra-clean compact floating or dockable widget.
   - Dimensions suitable for status bar placement (e.g. 360px wide, sleek glassmorphism).
   - Display active provider pills (Claude active, Copilot, Gemini, Ollama), total tokens today, reset countdown timer, and plan badge.
   - Auto-refresh via lightweight background polling (every 5 seconds).

## 3. Verification Criteria
- Tray icon initializes without error on Windows systems.
- Mini widget renders correctly without external CSS/JS libraries.
- Tooltip displays live token and session count accurately.
