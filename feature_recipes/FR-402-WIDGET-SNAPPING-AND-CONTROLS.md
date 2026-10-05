# Feature Recipe FR-402: Win32 Taskbar Snapping & Draggable Header Controls

## 1. Goal
Provide rich interactive widget controls including a draggable glassmorphic header, provider cycle button, close button, and Tray menu integration.

## 2. Technical Requirements
1. **Draggable CSS App Region**:
   - Apply `-webkit-app-region: drag` to the widget header to permit fluid click-and-drag movement anywhere on the desktop.
   - Apply `-webkit-app-region: no-drag` to action buttons so clicks register instantly.
2. **Provider Cycle / Selector**:
   - In the widget header, allow clicking the provider badge to cycle through active providers (Claude -> Gemini -> ChatGPT -> Ollama -> Copilot).
   - Display active model, tokens today, and quota remaining for the selected provider.
3. **Tray Menu & Dashboard Integration**:
   - Add "🪟 Launch Floating Widget" button on the Web Dashboard header status bar.
   - Wire Win32 Tray context menu "🪟 Launch Mini Status Widget" to invoke the native desktop widget launcher directly.
4. **CLI Integration**:
   - Support `python run_monitor.py --widget` to automatically pop the desktop floating widget on startup.

## 3. Verification Criteria
- Widget renders fluidly with glassmorphic styling and draggable handle.
- Clicking provider cycles through active provider telemetry.
- Dashboard button and tray menu invoke the launcher without errors.
