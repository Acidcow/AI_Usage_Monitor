# Architecture Decision Record: Zero-Browser Native Taskbar Widget & Multi-Platform Analytics

**Date**: 2026-10-07  
**Status**: Accepted  
**Authors**: Antigravity Engineering  
**Derived Standard**: KloGnist WoW v2.5.0 / ASD-STE100  

## Context & Problem Statement
1. Users observed that the mini widget stopped displaying when invoked via Edge `--app` mode due to Chromium profile locks and browser process coupling. Users explicitly requested a taskbar widget that does not require keeping a web browser open.
2. The Windows system tray notification area icon was rendering as a generic application document/form icon because `user32.LoadIconW(None, IDI_APPLICATION)` was loaded instead of a recognizable brand icon.
3. The 24-hour token velocity chart on the dashboard displayed aggregated bars without distinguishing between AI platforms. A multi-series line chart with an interactive platform legend was requested.
4. An architectural backlog item was requested for distributed telemetry consolidation across developer workstations and nodes.

## Decision & Design Rationale
1. **Zero-Browser Native Taskbar Widget (`backend/tray/native_widget.py`)**:
   - Implemented using Python 3 standard library `tkinter` with zero external pip or npm dependencies.
   - Pinned on-top (`-topmost`), chromeless (`overrideredirect(True)`), and docked flush to the bottom-right of the Windows taskbar.
   - Canvas-rendered dual progress bars (Session Balance Remaining % and Weekly Balance Remaining %), live token counts, and interactive hover pop-up flyouts.
   - Runs independently as a lightweight desktop process (`python -m backend.tray.native_widget`), eliminating any browser requirement.
2. **Identifiable System Tray Icons (`backend/tray/icon_factory.py`)**:
   - Zero-dependency generator for standard Windows `.ico` files (32x32 / 16x16 with 32-bit BGRA pixels):
     - `app_icon_johnny5.ico`: Distinctive glowing cyan optic sensors, visor brow, and chassis.
     - `app_icon_shield.ico`: Transparent dark cyber shield with cyan outline and neon purple diagonal slash.
   - Win32 `LoadImageW` / `CreateIconIndirect` integration in `WindowsTrayManager`.
3. **Multi-Platform SVG Velocity Line Chart (`frontend/js/app.js`)**:
   - Multi-series line graph rendering distinct curves for Claude, Gemini, ChatGPT, Ollama, Copilot, and Total Combined.
   - Interactive platform legend pills with click-to-isolate and hover tooltips showing exact token counts per hour.
4. **Distributed Telemetry Consolidation (`feature_recipes/FR-701-DISTRIBUTED-TELEMETRY-AGGREGATION.md`)**:
   - Logged ticket `AIUM-701` under epic `EPIC-DISTRIBUTED-TELEMETRY` capturing push/pull architecture, cluster quota pools, and privacy-first DPAPI node authentication.

## Consequences & Verification
- All 51 unit tests pass (100% success rate).
- Native widget operates with zero browser dependency.
- System tray icon displays crisp, recognizable Johnny 5 / Cyber Shield graphics.
