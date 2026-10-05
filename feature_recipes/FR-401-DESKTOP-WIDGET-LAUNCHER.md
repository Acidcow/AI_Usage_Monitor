# Feature Recipe FR-401: Standalone Edge App Mode Desktop Widget Launcher

## 1. Goal
Provide a native, standalone, chromeless desktop mini-widget window on Windows without adding heavy dependencies like Electron, PySide, or PyQt.

## 2. Technical Requirements
1. **Edge App Mode Discovery**:
   - Detect system Microsoft Edge binary (`msedge.exe`) across standard 64-bit and 32-bit Program Files locations and Windows registry App Paths.
2. **Chromeless Window Launch**:
   - Spawn `msedge.exe` with `--app="http://127.0.0.1:8765/mini_widget.html"`, `--window-size=360,210`, and isolated temporary user data directory (`data/widget_profile`).
   - Eliminate address bar, tabs, extensions, and browser navigation chrome.
3. **Screen Geometry & Positioning**:
   - Query Windows Work Area using `ctypes.windll.user32.GetSystemMetrics` or `SystemParametersInfoW`.
   - Compute initial coordinate position snapped to the bottom-right corner just above the Windows taskbar and system tray notification area.
4. **Backend REST API Route**:
   - Expose `POST /api/widget/launch` to trigger the standalone desktop window from the Web Dashboard or Tray Menu.

## 3. Verification Criteria
- Unit tests verify Edge executable path resolution.
- Unit tests verify screen geometry calculation math.
- Endpoint `POST /api/widget/launch` returns success with process status.
