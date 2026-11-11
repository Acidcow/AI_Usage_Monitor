# Feature Recipe: FR-901 - Windows Auto-Start & Background Service Lifecycle Management

**Ticket ID**: `AIUM-901`  
**Epic**: `EPIC-PLATFORM-OVERHAUL`  
**Status**: Done  
**Standard**: ASD-STE100 Simplified Technical English  

---

## 1. Purpose

This feature recipe specifies the zero-dependency Windows auto-start registration, single-instance PID lock management, background watchdog daemon (`--daemon`), CLI lifecycle commands, REST API endpoints, System Tray toggle, and Settings UI controls for AI Usage Monitor.

## 2. Technical Constraints (DPAPI & Interactive Desktop Session)

1. The system uses Current-User Windows DPAPI (`CryptProtectData` via `crypt32.dll`) to encrypt and decrypt API keys in `data/vault.json`.
2. The system renders a native Win32 taskbar notification icon (`backend/tray/windows_tray.py`) and a native Tkinter floating widget (`backend/tray/native_widget.py`) in the active user desktop session (`Session 1`).
3. Therefore, the background service MUST execute under the interactive logged-on user security token (`pythonw.exe` windowless daemon) rather than an isolated `Session 0` `NT AUTHORITY\SYSTEM` context.

## 3. Functional Requirements (STE-100)

### 3.1 Windows Auto-Start Registration (`WindowsServiceManager`)
- **REQ-901-01**: Provide `backend/system/windows_service.py` using only the Python 3 Standard Library (`winreg`, `subprocess`, `ctypes`, `os`, `sys`, `pathlib`, `json`, `time`).
- **REQ-901-02**: Support Windows Registry startup registration under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (value name: `AIUsageMonitor`) pointing to `pythonw.exe` (resolved next to `sys.executable`) and `run_monitor.py --daemon` (plus `--widget` when configured).
- **REQ-901-03**: Support Windows Task Scheduler (`schtasks.exe`) `ONLOGON` task registration (`AIUsageMonitorService`) as an optional or redundant logon mechanism.
- **REQ-901-04**: Provide clean uninstallation (`uninstall_startup`) that removes the Registry key and/or Scheduled Task without leaving orphan entries.

### 3.2 Single-Instance Lock, PID Tracking & Background Supervisor (`--daemon`)
- **REQ-901-05**: Maintain a structured state & PID lock file at `data/service_state.json` (and `data/service.pid`) recording `pid`, `supervisor_pid`, `started_at`, `mode`, `host`, `port`, `proxy_port`, `ollama_port`, `restart_count`, and `last_heartbeat`.
- **REQ-901-06**: Verify whether a recorded PID is genuinely alive on Windows using `kernel32.OpenProcess` / `GetExitCodeProcess` (`STILL_ACTIVE == 259`) via `ctypes`.
- **REQ-901-07**: When launched with `--daemon`, run a background supervisor loop that redirects standard output/error to `logs/service.log` (with size-based rotation at 5 MB) and automatically restarts the monitor worker if it exits with a non-zero crash code, while exiting cleanly when stopped via `--service-stop`, `/api/system/service`, or the System Tray `Exit` action.

### 3.3 CLI, REST API, Tray, and Settings Dashboard Controls
- **REQ-901-08**: Add CLI flags to `run_monitor.py`:
  - `--install-startup`: Register Windows logon auto-start.
  - `--uninstall-startup`: Remove Windows logon auto-start.
  - `--service-status`: Print JSON/formatted service health, PID, uptime, ports, and startup status.
  - `--service-start`: Spawn the background windowless daemon (`pythonw.exe run_monitor.py --daemon`) and verify startup.
  - `--service-stop`: Gracefully stop the running background instance and clear stale PID locks.
  - `--service-restart`: Stop any existing instance and spawn a fresh background daemon.
  - `--daemon`: Run in supervised background daemon mode with log redirection.
- **REQ-901-09**: Expose REST API endpoints in `backend/server/http_server.py`:
  - `GET /api/system/startup`: Return comprehensive auto-start registration and live service daemon telemetry.
  - `POST /api/system/startup`: Enable/disable Windows logon auto-start (`enabled`, `method`, `launch_widget`).
  - `POST /api/system/service`: Trigger service actions (`restart`, `stop`, `status`, `clear_logs`).
- **REQ-901-10**: Add a toggleable `"🚀 Start Automatically with Windows"` item to the native System Tray context menu (`backend/tray/windows_tray.py`) with a native checkmark (`MF_CHECKED`) reflecting current startup state.
- **REQ-901-11**: Add a `"Windows Auto-Start & Background Service"` management card to `frontend/components/settings_panel.html` and wire it in `frontend/js/app.js`.
