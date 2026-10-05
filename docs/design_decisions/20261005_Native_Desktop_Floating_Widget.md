# Architecture Decision Record: Native Desktop Floating Widget via Windows Edge App Mode

**Date**: 2026-10-05  
**Status**: Accepted  
**Deciders**: Engineering Team & Product Owner  

## Context
The user requested a small widget that can be placed on the Windows taskbar or status bar displaying up-to-date token usages, sessions, and quotas. Standard Python desktop GUI approaches (PySide6, PyQt, wxPython, Electron) violate our core requirement of zero external supply-chain dependencies (imposing 100MB+ pip downloads, C++ compiler toolchains, or node_modules).

## Decision
1. **Leverage Preinstalled Windows Edge in App Mode (`--app`)**:
   - Every modern Windows 10 and 11 installation includes Microsoft Edge.
   - Running `msedge.exe --app=http://127.0.0.1:8765/mini_widget.html --window-size=360,210` spawns a standalone, chromeless native OS window without browser tabs, address bars, or extensions.
2. **Win32 Work Area Geometry Detection (`ctypes.windll.user32`)**:
   - Use `SystemParametersInfoW(SPI_GETWORKAREA, ...)` via `ctypes` to retrieve exact desktop usable dimensions (excluding the taskbar).
   - Position the widget automatically in the bottom-right corner just above the system tray notification area.
3. **Draggable & Frameless Controls**:
   - Enable `-webkit-app-region: drag` for fluid dragging and repositioning anywhere on user displays.
   - Connect Win32 tray menu, Web Dashboard header button, and CLI flag `--widget` to a unified launcher module `backend/tray/desktop_widget.py`.

## Consequences
- **Positive**: 100% zero external dependencies; pure native Windows appearance; memory footprint under 30MB; instant startup; interactive draggable glassmorphic styling.
- **Negative**: Relies on Windows Edge being present (with automatic browser fallback if not found).
