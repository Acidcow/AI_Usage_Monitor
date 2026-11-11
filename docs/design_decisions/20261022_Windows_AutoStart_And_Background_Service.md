# Architecture & Design Decision: Windows Auto-Start & Background Service Lifecycle Management (`AIUM-901`)

**Date**: 2026-10-22  
**Ticket**: `AIUM-901`  
**Status**: Approved  

---

## 1. Context & Problem Statement

Users require AI Usage Monitor to start automatically when Windows boots/logs on and run silently in the background without a persistent terminal window, while providing full lifecycle control (status, start, stop, restart, auto-start registration) from the CLI, Web Dashboard Settings, and Windows System Tray.

## 2. Architectural Analysis: Session 0 Service vs. Interactive User-Session Daemon

A traditional Windows NT Service (`services.msc`) runs in **Session 0** under `NT AUTHORITY\SYSTEM` or `LocalService`. For AI Usage Monitor, Session 0 introduces two fatal incompatibilities:
1. **Windows DPAPI Scope**: `backend/security/dpapi_vault.py` calls `CryptProtectData` / `CryptUnprotectData` with user-scoped entropy. Credentials encrypted by the logged-in user cannot be decrypted by `SYSTEM` in Session 0 unless user-context impersonation is performed.
2. **Interactive GUI Isolation (Session 0 Isolation)**: Windows blocks Session 0 services from rendering taskbar notification icons (`Shell_NotifyIconW` in `backend/tray/windows_tray.py`) or floating desktop widgets (`Tkinter` in `backend/tray/native_widget.py`) on the user's desktop (`Session 1+`).

## 3. Selected Architecture

We implement `WindowsServiceManager` in `backend/system/windows_service.py` using a **Dual-Capable Interactive User Daemon + Supervisor Architecture**:

1. **Windowless Python Execution (`pythonw.exe` + `CREATE_NO_WINDOW`)**:
   - Resolves `pythonw.exe` alongside `sys.executable` (falling back to `sys.executable` with `CREATE_NO_WINDOW = 0x08000000` and `DETACHED_PROCESS = 0x00000008` creation flags).
2. **Registry (`winreg`) + Task Scheduler (`schtasks.exe`) Registration**:
   - Primary registration writes `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\AIUsageMonitor` via Python's built-in `winreg` module. Requires zero UAC elevation, runs immediately on user logon in Session 1, preserves DPAPI context, and renders the System Tray icon reliably.
   - Optional secondary support via `schtasks.exe /Create /TN "AIUsageMonitorService" /SC ONLOGON /IT /F` for Task Scheduler management.
3. **PID Lockfile & Win32 Process Liveness Verification**:
   - Stores runtime state in `data/service_state.json` and `data/service.pid`.
   - Uses `ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)` and `GetExitCodeProcess` (`STILL_ACTIVE == 259`) to verify real process liveness without `psutil`.
4. **Crash-Recovery Watchdog (`--daemon`) & Rotating Service Logs**:
   - When invoked with `--daemon`, `run_monitor.py` redirects `stdout`/`stderr` to `logs/service.log` (auto-rotating at 5 MB to `logs/service.log.1`) and supervises the runtime. Intentional stops write `"stop_requested": true` to `data/service_state.json` so the supervisor exits cleanly instead of respawning.
