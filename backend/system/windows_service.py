"""
AI Usage Monitor - Windows Auto-Start & Background Service Manager (AIUM-901)
Zero-Dependency Windows Service/Daemon Lifecycle & Startup Registration.

Architectural Note:
AI Usage Monitor relies on Current-User Windows DPAPI (`CryptProtectData` via `crypt32.dll`)
and renders a native Win32 System Tray icon (`Shell_NotifyIconW`) + Tkinter Desktop Widget
in the active user desktop session (Session 1).
Therefore, background execution is architected around an interactive user-session daemon
(`pythonw.exe` + `CREATE_NO_WINDOW`) launched via `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`
and/or a user-scoped Windows Task Scheduler (`schtasks.exe`) `ONLOGON` task, backed by a
crash-recovery watchdog supervisor and Win32 PID lockfile tracking.
"""

import ctypes
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.config import (
    DATA_DIR,
    DEFAULT_HOST,
    DEFAULT_OLLAMA_PORT,
    DEFAULT_PORT,
    LOGS_DIR,
    PROXY_PORT,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_MONITOR_SCRIPT = REPO_ROOT / "run_monitor.py"

DEFAULT_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULT_REGISTRY_VALUE_NAME = "AIUsageMonitor"
DEFAULT_TASK_NAME = "AIUsageMonitorService"

# Win32 Process Creation & Query Constants
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
STILL_ACTIVE = 259


class RotatingFileStream:
    """
    Zero-dependency thread-safe file stream with automatic size-based rotation.
    Safely replaces sys.stdout / sys.stderr when running windowless under pythonw.exe.
    """

    def __init__(
        self,
        log_path: Path,
        max_bytes: int = 5 * 1024 * 1024,
        backup_count: int = 2,
        mirror_stream: Any = None,
    ):
        self.log_path = Path(log_path)
        self.max_bytes = max(1024, int(max_bytes))
        self.backup_count = max(1, int(backup_count))
        self.mirror_stream = mirror_stream
        self.encoding = "utf-8"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _rotate_if_needed(self) -> None:
        try:
            if not self.log_path.exists():
                return
            if self.log_path.stat().st_size < self.max_bytes:
                return

            # Shift backups: .1 -> .2, current -> .1
            for idx in range(self.backup_count, 0, -1):
                src = (
                    self.log_path
                    if idx == 1
                    else self.log_path.with_name(f"{self.log_path.name}.{idx - 1}")
                )
                dst = self.log_path.with_name(f"{self.log_path.name}.{idx}")
                if src.exists():
                    if dst.exists():
                        try:
                            dst.unlink()
                        except Exception:
                            pass
                    try:
                        src.replace(dst)
                    except Exception:
                        pass
        except Exception:
            pass

    def write(self, data: str) -> int:
        if not data:
            return 0
        text = str(data)
        try:
            self._rotate_if_needed()
            with open(self.log_path, "a", encoding="utf-8", errors="replace") as f:
                f.write(text)
        except Exception:
            pass

        if self.mirror_stream is not None:
            try:
                self.mirror_stream.write(text)
                self.mirror_stream.flush()
            except Exception:
                pass
        return len(text)

    def flush(self) -> None:
        if self.mirror_stream is not None:
            try:
                self.mirror_stream.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return False


def setup_daemon_logging(
    log_path: Optional[Path] = None,
    max_bytes: int = 5 * 1024 * 1024,
) -> RotatingFileStream:
    """
    Redirects sys.stdout and sys.stderr to the rotating service log file.
    Critical for pythonw.exe where stdout/stderr handles may be None or invalid.
    """
    target_path = Path(log_path) if log_path else (LOGS_DIR / "service.log")
    stream = RotatingFileStream(log_path=target_path, max_bytes=max_bytes)
    sys.stdout = stream  # type: ignore[assignment]
    sys.stderr = stream  # type: ignore[assignment]
    return stream


class WindowsServiceManager:
    """
    Manages Windows logon auto-start registration, single-instance PID locking,
    background daemon spawning, crash-recovery supervision, and service telemetry.
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        logs_dir: Optional[Path] = None,
        repo_root: Optional[Path] = None,
        run_key_path: str = DEFAULT_RUN_KEY_PATH,
        registry_value_name: str = DEFAULT_REGISTRY_VALUE_NAME,
        task_name: str = DEFAULT_TASK_NAME,
    ):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.logs_dir = Path(logs_dir) if logs_dir else LOGS_DIR
        self.repo_root = Path(repo_root) if repo_root else REPO_ROOT
        self.script_path = self.repo_root / "run_monitor.py"

        self.run_key_path = run_key_path
        self.registry_value_name = registry_value_name
        self.task_name = task_name

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.pid_file = self.data_dir / "service.pid"
        self.state_file = self.data_dir / "service_state.json"
        self.config_file = self.data_dir / "service_config.json"
        self.log_file = self.logs_dir / "service.log"

    # =========================================================================
    # 1. EXECUTABLE & COMMAND LINE RESOLUTION
    # =========================================================================

    @staticmethod
    def resolve_pythonw(python_exe: Optional[str] = None) -> str:
        """
        Resolves the windowless `pythonw.exe` executable adjacent to `sys.executable`
        on Windows so background services do not flash a console window.
        Falls back to `python_exe` / `sys.executable` if `pythonw.exe` is unavailable.
        """
        exe_path = Path(python_exe or sys.executable).resolve()
        if sys.platform == "win32":
            if exe_path.name.lower() == "pythonw.exe" and exe_path.exists():
                return str(exe_path)
            candidate = exe_path.with_name("pythonw.exe")
            if candidate.exists():
                return str(candidate)
        return str(exe_path)

    @staticmethod
    def resolve_python_console(python_exe: Optional[str] = None) -> str:
        """Resolves standard `python.exe` adjacent to `sys.executable`."""
        exe_path = Path(python_exe or sys.executable).resolve()
        if sys.platform == "win32" and exe_path.name.lower() == "pythonw.exe":
            candidate = exe_path.with_name("python.exe")
            if candidate.exists():
                return str(candidate)
        return str(exe_path)

    def build_startup_command(
        self,
        launch_widget: bool = False,
        extra_args: Optional[List[str]] = None,
        python_exe: Optional[str] = None,
    ) -> str:
        """
        Constructs the exact quoted command string stored in the Windows Run Registry key
        or Task Scheduler action.
        """
        pythonw = self.resolve_pythonw(python_exe)
        parts = [f'"{pythonw}"', f'"{self.script_path}"', "--daemon"]
        if launch_widget:
            parts.append("--widget")
        if extra_args:
            for arg in extra_args:
                arg_str = str(arg).strip()
                if arg_str and arg_str not in parts:
                    parts.append(arg_str)
        return " ".join(parts)

    # =========================================================================
    # 2. PERSISTENT SERVICE CONFIGURATION
    # =========================================================================

    def load_config(self) -> Dict[str, Any]:
        """Loads persistent startup preferences from `data/service_config.json`."""
        default_cfg = {
            "auto_start_enabled": False,
            "auto_start_method": "registry",
            "launch_widget_on_startup": False,
            "auto_restart_on_crash": True,
            "max_crash_restarts": 10,
            "updated_at": None,
        }
        if not self.config_file.exists():
            return default_cfg
        try:
            raw = json.loads(self.config_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                default_cfg.update(raw)
        except Exception:
            pass
        return default_cfg

    def save_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Updates and persists `data/service_config.json`."""
        cfg = self.load_config()
        cfg.update(updates)
        cfg["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self.config_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass
        return cfg

    # =========================================================================
    # 3. WINDOWS REGISTRY AUTO-START (HKCU\...\Run)
    # =========================================================================

    def install_registry_startup(
        self,
        launch_widget: bool = False,
        extra_args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Registers AI Usage Monitor under `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`.
        Requires zero administrator elevation and runs in the user's DPAPI & GUI session.
        """
        cmd = self.build_startup_command(launch_widget=launch_widget, extra_args=extra_args)
        reg_full_path = f"HKCU\\{self.run_key_path}\\{self.registry_value_name}"

        if sys.platform != "win32":
            self.save_config(
                {
                    "auto_start_enabled": True,
                    "auto_start_method": "registry",
                    "launch_widget_on_startup": bool(launch_widget),
                    " simulated_registry_command": cmd,
                }
            )
            return {
                "success": True,
                "method": "registry",
                "enabled": True,
                "command": cmd,
                "registry_key": reg_full_path,
                "launch_widget": bool(launch_widget),
            }

        try:
            import winreg

            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                self.run_key_path,
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_READ,
            ) as key:
                winreg.SetValueEx(key, self.registry_value_name, 0, winreg.REG_SZ, cmd)

            self.save_config(
                {
                    "auto_start_enabled": True,
                    "auto_start_method": "registry",
                    "launch_widget_on_startup": bool(launch_widget),
                }
            )
            return {
                "success": True,
                "method": "registry",
                "enabled": True,
                "command": cmd,
                "registry_key": reg_full_path,
                "launch_widget": bool(launch_widget),
            }
        except Exception as e:
            return {
                "success": False,
                "method": "registry",
                "enabled": False,
                "error": str(e),
                "registry_key": reg_full_path,
            }

    def uninstall_registry_startup(self) -> Dict[str, Any]:
        """Removes the `AIUsageMonitor` value from `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`."""
        reg_full_path = f"HKCU\\{self.run_key_path}\\{self.registry_value_name}"
        if sys.platform != "win32":
            self.save_config({"auto_start_enabled": False, " simulated_registry_command": None})
            return {
                "success": True,
                "method": "registry",
                "enabled": False,
                "removed": True,
                "registry_key": reg_full_path,
            }

        try:
            import winreg

            removed = False
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    self.run_key_path,
                    0,
                    winreg.KEY_SET_VALUE | winreg.KEY_READ,
                ) as key:
                    winreg.DeleteValue(key, self.registry_value_name)
                    removed = True
            except FileNotFoundError:
                removed = False

            self.save_config({"auto_start_enabled": False})
            return {
                "success": True,
                "method": "registry",
                "enabled": False,
                "removed": removed,
                "registry_key": reg_full_path,
            }
        except Exception as e:
            return {
                "success": False,
                "method": "registry",
                "error": str(e),
                "registry_key": reg_full_path,
            }

    def get_registry_startup_status(self) -> Dict[str, Any]:
        """Queries `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run` for `AIUsageMonitor`."""
        reg_full_path = f"HKCU\\{self.run_key_path}\\{self.registry_value_name}"
        if sys.platform != "win32":
            cfg = self.load_config()
            cmd = cfg.get(" simulated_registry_command")
            enabled = bool(cfg.get("auto_start_enabled") and cmd)
            return {
                "enabled": enabled,
                "command": cmd if enabled else None,
                "launch_widget": bool(cfg.get("launch_widget_on_startup", False)),
                "registry_key": reg_full_path,
            }

        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.run_key_path,
                0,
                winreg.KEY_READ,
            ) as key:
                val, _ = winreg.QueryValueEx(key, self.registry_value_name)
                cmd_str = str(val) if val else ""
                return {
                    "enabled": bool(cmd_str),
                    "command": cmd_str or None,
                    "launch_widget": "--widget" in cmd_str,
                    "registry_key": reg_full_path,
                }
        except FileNotFoundError:
            return {
                "enabled": False,
                "command": None,
                "launch_widget": False,
                "registry_key": reg_full_path,
            }
        except Exception as e:
            return {
                "enabled": False,
                "command": None,
                "launch_widget": False,
                "registry_key": reg_full_path,
                "error": str(e),
            }

    # =========================================================================
    # 4. WINDOWS TASK SCHEDULER (`schtasks.exe`) SUPPORT
    # =========================================================================

    def install_scheduled_task(self, launch_widget: bool = False) -> Dict[str, Any]:
        """
        Creates an interactive user logon task in Windows Task Scheduler (`schtasks.exe`).
        """
        cmd = self.build_startup_command(launch_widget=launch_widget)
        if sys.platform != "win32":
            return {"success": False, "error": "Task Scheduler requires Windows"}

        try:
            args = [
                "schtasks",
                "/Create",
                "/TN",
                self.task_name,
                "/TR",
                cmd,
                "/SC",
                "ONLOGON",
                "/F",
            ]
            res = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW,
            )
            success = res.returncode == 0
            if success:
                self.save_config(
                    {
                        "auto_start_enabled": True,
                        "auto_start_method": "task_scheduler",
                        "launch_widget_on_startup": bool(launch_widget),
                    }
                )
            return {
                "success": success,
                "method": "task_scheduler",
                "task_name": self.task_name,
                "command": cmd,
                "output": (res.stdout or res.stderr or "").strip(),
            }
        except Exception as e:
            return {
                "success": False,
                "method": "task_scheduler",
                "task_name": self.task_name,
                "error": str(e),
            }

    def uninstall_scheduled_task(self) -> Dict[str, Any]:
        """Deletes the `AIUsageMonitorService` task from Windows Task Scheduler."""
        if sys.platform != "win32":
            return {"success": True, "removed": False}

        try:
            args = ["schtasks", "/Delete", "/TN", self.task_name, "/F"]
            res = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW,
            )
            return {
                "success": True,
                "method": "task_scheduler",
                "removed": res.returncode == 0,
                "task_name": self.task_name,
            }
        except Exception as e:
            return {
                "success": False,
                "method": "task_scheduler",
                "task_name": self.task_name,
                "error": str(e),
            }

    def get_scheduled_task_status(self) -> Dict[str, Any]:
        """Checks whether the `AIUsageMonitorService` scheduled task exists."""
        if sys.platform != "win32":
            return {"enabled": False, "task_name": self.task_name}

        try:
            args = ["schtasks", "/Query", "/TN", self.task_name, "/FO", "CSV", "/NH"]
            res = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            enabled = res.returncode == 0 and self.task_name.lower() in (res.stdout or "").lower()
            return {
                "enabled": enabled,
                "task_name": self.task_name,
                "details": (res.stdout or "").strip() if enabled else None,
            }
        except Exception:
            return {"enabled": False, "task_name": self.task_name}

    # =========================================================================
    # 5. UNIFIED STARTUP REGISTRATION API
    # =========================================================================

    def install_startup(
        self,
        method: str = "registry",
        launch_widget: bool = False,
        extra_args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Installs Windows auto-start using the specified method:
        - 'registry' (default, zero-elevation HKCU Run key)
        - 'task_scheduler' (schtasks ONLOGON)
        - 'both'
        """
        method_norm = (method or "registry").strip().lower()
        results: Dict[str, Any] = {}

        if method_norm in ("registry", "both"):
            results["registry"] = self.install_registry_startup(
                launch_widget=launch_widget, extra_args=extra_args
            )
        if method_norm in ("task_scheduler", "both"):
            results["task_scheduler"] = self.install_scheduled_task(launch_widget=launch_widget)
            # If task scheduler requires elevation and fails, automatically fall back to HKCU registry
            if not results["task_scheduler"].get("success") and "registry" not in results:
                results["registry"] = self.install_registry_startup(
                    launch_widget=launch_widget, extra_args=extra_args
                )

        status = self.get_startup_status()
        status["install_results"] = results
        status["success"] = bool(status.get("enabled"))
        return status

    def uninstall_startup(self, method: str = "all") -> Dict[str, Any]:
        """Removes Windows auto-start registration."""
        method_norm = (method or "all").strip().lower()
        results: Dict[str, Any] = {}

        if method_norm in ("registry", "all", "both"):
            results["registry"] = self.uninstall_registry_startup()
        if method_norm in ("task_scheduler", "all", "both"):
            results["task_scheduler"] = self.uninstall_scheduled_task()

        self.save_config({"auto_start_enabled": False})
        status = self.get_startup_status()
        status["uninstall_results"] = results
        status["success"] = not bool(status.get("enabled"))
        return status

    def get_startup_status(self, check_scheduled_task: bool = False) -> Dict[str, Any]:
        """Returns consolidated startup registration status."""
        reg = self.get_registry_startup_status()
        cfg = self.load_config()
        sched = (
            self.get_scheduled_task_status()
            if check_scheduled_task
            else {"enabled": False, "task_name": self.task_name}
        )

        enabled = bool(reg.get("enabled") or sched.get("enabled"))
        active_method = (
            "both"
            if (reg.get("enabled") and sched.get("enabled"))
            else ("registry" if reg.get("enabled") else ("task_scheduler" if sched.get("enabled") else "none"))
        )
        launch_widget = bool(
            reg.get("launch_widget") or cfg.get("launch_widget_on_startup", False)
        )

        return {
            "enabled": enabled,
            "method": active_method,
            "preferred_method": cfg.get("auto_start_method", "registry"),
            "launch_widget": launch_widget,
            "auto_restart_on_crash": bool(cfg.get("auto_restart_on_crash", True)),
            "command": reg.get("command") or self.build_startup_command(launch_widget=launch_widget),
            "pythonw_path": self.resolve_pythonw(),
            "script_path": str(self.script_path),
            "registry": reg,
            "task_scheduler": sched,
        }

    def is_startup_enabled(self) -> bool:
        """Fast check suitable for System Tray context menu rendering."""
        return bool(self.get_registry_startup_status().get("enabled"))

    def toggle_startup(self, launch_widget: Optional[bool] = None) -> Dict[str, Any]:
        """Toggles Windows logon auto-start on or off."""
        current = self.get_startup_status()
        if current.get("enabled"):
            return self.uninstall_startup()
        use_widget = (
            bool(launch_widget)
            if launch_widget is not None
            else bool(current.get("launch_widget", False))
        )
        return self.install_startup(method="registry", launch_widget=use_widget)

    # =========================================================================
    # 6. WIN32 PROCESS LIVENESS & SINGLE-INSTANCE PID LOCKING
    # =========================================================================

    @staticmethod
    def is_pid_running(pid: Optional[int]) -> bool:
        """
        Checks if a process with the given PID is actively running.
        Uses Win32 `OpenProcess` + `GetExitCodeProcess` (`STILL_ACTIVE == 259`) via `ctypes`.
        """
        if not pid or int(pid) <= 0:
            return False
        pid_int = int(pid)
        if pid_int == os.getpid():
            return True

        if sys.platform == "win32":
            try:
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid_int)
                if not handle:
                    return False
                try:
                    exit_code = ctypes.c_ulong(0)
                    if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                        return int(exit_code.value) == STILL_ACTIVE
                    return False
                finally:
                    kernel32.CloseHandle(handle)
            except Exception:
                return False
        else:
            try:
                os.kill(pid_int, 0)
                return True
            except OSError:
                return False

    @staticmethod
    def terminate_pid(pid: Optional[int]) -> bool:
        """Terminates a target PID cleanly on Windows or POSIX."""
        if not pid or int(pid) <= 0:
            return False
        pid_int = int(pid)
        if pid_int == os.getpid():
            return False

        if sys.platform == "win32":
            try:
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid_int)
                if handle:
                    try:
                        res = kernel32.TerminateProcess(handle, 0)
                        if res:
                            return True
                    finally:
                        kernel32.CloseHandle(handle)
                # Fallback to taskkill /PID /T /F to ensure child threads/processes exit
                subprocess.run(
                    ["taskkill", "/PID", str(pid_int), "/T", "/F"],
                    capture_output=True,
                    timeout=5,
                    creationflags=CREATE_NO_WINDOW,
                )
                return not WindowsServiceManager.is_pid_running(pid_int)
            except Exception:
                return False
        else:
            try:
                import signal

                os.kill(pid_int, signal.SIGTERM)
                return True
            except Exception:
                return False

    def read_service_state(self) -> Dict[str, Any]:
        """Reads `data/service_state.json` and reconciles with `data/service.pid`."""
        state: Dict[str, Any] = {}
        if self.state_file.exists():
            try:
                raw = json.loads(self.state_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    state = raw
            except Exception:
                state = {}

        if not state.get("pid") and self.pid_file.exists():
            try:
                pid_txt = self.pid_file.read_text(encoding="utf-8").strip()
                if pid_txt.isdigit():
                    state["pid"] = int(pid_txt)
            except Exception:
                pass
        return state

    def acquire_pid_lock(
        self,
        pid: Optional[int] = None,
        mode: str = "interactive",
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        proxy_port: int = PROXY_PORT,
        ollama_port: int = DEFAULT_OLLAMA_PORT,
        supervisor_pid: Optional[int] = None,
        restart_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Records the active service PID and runtime metadata in `data/service.pid`
        and `data/service_state.json`.
        """
        active_pid = int(pid if pid is not None else os.getpid())
        now_iso = datetime.now(timezone.utc).isoformat()
        now_epoch = time.time()

        existing = self.read_service_state()
        started_at = existing.get("started_at") if existing.get("pid") == active_pid else now_iso
        started_epoch = (
            existing.get("started_epoch") if existing.get("pid") == active_pid else now_epoch
        )

        state = {
            "pid": active_pid,
            "supervisor_pid": int(supervisor_pid) if supervisor_pid else existing.get("supervisor_pid"),
            "running": True,
            "stop_requested": False,
            "mode": mode,
            "host": host,
            "port": int(port),
            "proxy_port": int(proxy_port),
            "ollama_port": int(ollama_port),
            "restart_count": int(restart_count),
            "started_at": started_at,
            "started_epoch": started_epoch,
            "last_heartbeat": now_iso,
            "last_heartbeat_epoch": now_epoch,
            "python_executable": sys.executable,
        }

        try:
            self.pid_file.write_text(str(active_pid), encoding="utf-8")
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass
        return state

    def update_heartbeat(self, **extra_fields: Any) -> Dict[str, Any]:
        """Updates `last_heartbeat` and any runtime fields in `data/service_state.json`."""
        state = self.read_service_state()
        now_iso = datetime.now(timezone.utc).isoformat()
        state["last_heartbeat"] = now_iso
        state["last_heartbeat_epoch"] = time.time()
        state["running"] = True
        for k, v in extra_fields.items():
            state[k] = v
        try:
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass
        return state

    def request_graceful_stop(self) -> None:
        """Marks `stop_requested = True` so the daemon watchdog knows not to respawn."""
        state = self.read_service_state()
        state["stop_requested"] = True
        state["running"] = False
        state["stopped_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass

    def release_pid_lock(self, pid: Optional[int] = None) -> bool:
        """Releases the PID lockfile if owned by `pid` (or unconditionally if `pid` is None)."""
        state = self.read_service_state()
        recorded_pid = state.get("pid")
        if pid is not None and recorded_pid and int(recorded_pid) != int(pid):
            return False

        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except Exception:
            pass

        state["running"] = False
        state["stopped_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass
        return True

    # =========================================================================
    # 7. SERVICE LIFECYCLE MANAGEMENT (STATUS / START / STOP / RESTART)
    # =========================================================================

    def get_recent_logs(self, max_lines: int = 40) -> List[str]:
        """Returns the last `max_lines` lines from `logs/service.log`."""
        if not self.log_file.exists():
            return []
        try:
            content = self.log_file.read_text(encoding="utf-8", errors="replace")
            lines = [line for line in content.splitlines() if line.strip()]
            return lines[-max(1, int(max_lines)) :]
        except Exception:
            return []

    def clear_service_logs(self) -> Dict[str, Any]:
        """Truncates `logs/service.log` cleanly."""
        try:
            if self.log_file.exists():
                self.log_file.write_text("", encoding="utf-8")
            return {"success": True, "log_file": str(self.log_file)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_service_status(self, include_logs: bool = False) -> Dict[str, Any]:
        """
        Computes comprehensive status of both the running background service/daemon
        and the Windows logon auto-start registration.
        """
        state = self.read_service_state()
        pid = state.get("pid")
        supervisor_pid = state.get("supervisor_pid")

        pid_alive = self.is_pid_running(pid) if pid else False
        sup_alive = self.is_pid_running(supervisor_pid) if supervisor_pid else False

        # Clean up stale PID file if neither worker nor supervisor is alive
        if pid and not pid_alive and not sup_alive:
            try:
                if self.pid_file.exists():
                    self.pid_file.unlink()
            except Exception:
                pass

        uptime_seconds = 0
        if pid_alive and state.get("started_epoch"):
            try:
                uptime_seconds = max(0, int(time.time() - float(state["started_epoch"])))
            except Exception:
                uptime_seconds = 0

        startup = self.get_startup_status()
        log_size_bytes = 0
        try:
            if self.log_file.exists():
                log_size_bytes = self.log_file.stat().st_size
        except Exception:
            pass

        result: Dict[str, Any] = {
            "running": bool(pid_alive or sup_alive),
            "pid": int(pid) if (pid and pid_alive) else None,
            "supervisor_pid": int(supervisor_pid) if (supervisor_pid and sup_alive) else None,
            "mode": state.get("mode", "stopped") if (pid_alive or sup_alive) else "stopped",
            "host": state.get("host", DEFAULT_HOST),
            "port": state.get("port", DEFAULT_PORT),
            "proxy_port": state.get("proxy_port", PROXY_PORT),
            "ollama_port": state.get("ollama_port", DEFAULT_OLLAMA_PORT),
            "started_at": state.get("started_at") if (pid_alive or sup_alive) else None,
            "last_heartbeat": state.get("last_heartbeat"),
            "uptime_seconds": uptime_seconds,
            "restart_count": int(state.get("restart_count", 0)),
            "log_file": str(self.log_file),
            "log_size_bytes": log_size_bytes,
            "startup": startup,
        }
        if include_logs:
            result["recent_logs"] = self.get_recent_logs(max_lines=40)
        return result

    def start_background_service(
        self,
        launch_widget: bool = False,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        proxy_port: int = PROXY_PORT,
        ollama_port: int = DEFAULT_OLLAMA_PORT,
        wait_seconds: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Spawns AI Usage Monitor as a detached windowless background daemon (`pythonw.exe run_monitor.py --daemon`).
        If an instance is already running, returns its status without spawning a duplicate.
        """
        current = self.get_service_status()
        if current.get("running"):
            current["already_running"] = True
            current["success"] = True
            return current

        pythonw = self.resolve_pythonw()
        cmd_args = [
            pythonw,
            str(self.script_path),
            "--daemon",
            "--host",
            str(host),
            "--port",
            str(port),
            "--proxy-port",
            str(proxy_port),
            "--ollama-port",
            str(ollama_port),
        ]
        if launch_widget:
            cmd_args.append("--widget")

        creationflags = 0
        if sys.platform == "win32":
            creationflags = CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

        try:
            proc = subprocess.Popen(
                cmd_args,
                cwd=str(self.repo_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                close_fds=True,
            )

            deadline = time.time() + max(0.2, float(wait_seconds))
            while time.time() < deadline:
                st = self.get_service_status()
                if st.get("running"):
                    st["success"] = True
                    st["spawned_pid"] = proc.pid
                    return st
                time.sleep(0.15)

            st = self.get_service_status()
            st["success"] = bool(st.get("running") or self.is_pid_running(proc.pid))
            st["spawned_pid"] = proc.pid
            return st
        except Exception as e:
            return {
                "success": False,
                "running": False,
                "error": str(e),
            }

    def stop_background_service(self, timeout_seconds: float = 5.0) -> Dict[str, Any]:
        """
        Gracefully stops any running background supervisor and worker processes,
        and cleans up PID lockfiles.
        """
        state = self.read_service_state()
        pid = state.get("pid")
        supervisor_pid = state.get("supervisor_pid")

        self.request_graceful_stop()

        stopped_pids: List[int] = []
        for target_pid in (supervisor_pid, pid):
            if target_pid and self.is_pid_running(target_pid):
                if self.terminate_pid(int(target_pid)):
                    stopped_pids.append(int(target_pid))

        deadline = time.time() + max(0.2, float(timeout_seconds))
        while time.time() < deadline:
            if not self.is_pid_running(pid) and not self.is_pid_running(supervisor_pid):
                break
            time.sleep(0.1)

        self.release_pid_lock()
        status = self.get_service_status()
        status["success"] = not bool(status.get("running"))
        status["stopped_pids"] = stopped_pids
        return status

    def restart_background_service(
        self,
        launch_widget: Optional[bool] = None,
        deferred: bool = False,
    ) -> Dict[str, Any]:
        """
        Restarts the background service.
        When `deferred=True` (invoked from an active HTTP API handler inside the process being restarted),
        spawns an asynchronous detached helper that waits 0.8s, stops the current process, and launches
        the fresh daemon so the HTTP response finishes cleanly first.
        """
        state = self.read_service_state()
        cfg = self.load_config()
        use_widget = (
            bool(launch_widget)
            if launch_widget is not None
            else bool(cfg.get("launch_widget_on_startup", False))
        )

        if deferred:
            pythonw = self.resolve_pythonw()
            cmd_args = [
                pythonw,
                str(self.script_path),
                "--service-restart",
            ]
            if use_widget:
                cmd_args.append("--widget")

            creationflags = (
                CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                if sys.platform == "win32"
                else 0
            )
            try:
                subprocess.Popen(
                    cmd_args,
                    cwd=str(self.repo_root),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                    close_fds=True,
                )
                return {
                    "success": True,
                    "deferred": True,
                    "message": "Background service restart initiated.",
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        self.stop_background_service()
        return self.start_background_service(
            launch_widget=use_widget,
            host=state.get("host", DEFAULT_HOST),
            port=int(state.get("port", DEFAULT_PORT)),
            proxy_port=int(state.get("proxy_port", PROXY_PORT)),
            ollama_port=int(state.get("ollama_port", DEFAULT_OLLAMA_PORT)),
        )

    # =========================================================================
    # 8. CRASH-RECOVERY WATCHDOG SUPERVISOR (`--daemon`)
    # =========================================================================

    def run_supervised_daemon(
        self,
        worker_callable: Callable[[], None],
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        proxy_port: int = PROXY_PORT,
        ollama_port: int = DEFAULT_OLLAMA_PORT,
    ) -> int:
        """
        Executes `worker_callable` inside a crash-recovery supervisor loop with
        rotating log redirection (`logs/service.log`) and PID lock management.
        """
        setup_daemon_logging(self.log_file)
        cfg = self.load_config()
        max_restarts = int(cfg.get("max_crash_restarts", 10))
        auto_restart = bool(cfg.get("auto_restart_on_crash", True))

        restart_count = 0
        print(
            f"\n[DAEMON] {datetime.now().isoformat()} - AI Usage Monitor Background Service starting (PID {os.getpid()})"
        )

        while True:
            self.acquire_pid_lock(
                pid=os.getpid(),
                supervisor_pid=os.getpid(),
                mode="daemon",
                host=host,
                port=port,
                proxy_port=proxy_port,
                ollama_port=ollama_port,
                restart_count=restart_count,
            )
            try:
                worker_callable()
                # Normal return means clean shutdown
                break
            except KeyboardInterrupt:
                print("[DAEMON] KeyboardInterrupt received; shutting down cleanly.")
                break
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 0
                if code == 0:
                    print("[DAEMON] Clean SystemExit(0); stopping daemon.")
                    break
                print(f"[DAEMON WARN] Worker exited with code {code}.")
            except Exception as exc:
                print(f"[DAEMON ERROR] Unhandled exception in service loop: {exc}")

            # Check if stop was intentionally requested via CLI/API/Tray
            state = self.read_service_state()
            if state.get("stop_requested") or not auto_restart:
                print("[DAEMON] Intentional stop requested; exiting supervisor.")
                break

            restart_count += 1
            if restart_count > max_restarts:
                print(f"[DAEMON FATAL] Exceeded max crash restarts ({max_restarts}). Stopping.")
                break

            backoff = min(30.0, 2.0 * restart_count)
            print(
                f"[DAEMON] Restarting service worker (attempt {restart_count}/{max_restarts}) in {backoff:.1f}s..."
            )
            time.sleep(backoff)

        self.release_pid_lock(pid=os.getpid())
        return 0
