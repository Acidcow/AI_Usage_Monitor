"""
Zero-Dependency Standalone Desktop Floating Widget Launcher.
Uses Microsoft Edge App Mode (--app) and Win32 Work Area Geometry.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

def find_edge_binary() -> Optional[str]:
    """
    Locates the Microsoft Edge executable across common Windows installation paths.
    """
    if sys.platform != "win32":
        return None

    # Common Windows installation directories
    candidate_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate_paths.append(str(Path(local_app_data) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidate_paths.append(str(Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))

    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if program_files_x86:
        candidate_paths.append(str(Path(program_files_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))

    for p in candidate_paths:
        if Path(p).is_file():
            return str(Path(p).resolve())

    # Try registry lookup
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
        val, _ = winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)
        if Path(val).is_file():
            return str(Path(val).resolve())
    except Exception:
        pass

    # Fallback to PATH search
    which_edge = shutil.which("msedge.exe") or shutil.which("msedge")
    if which_edge:
        return str(Path(which_edge).resolve())

    return None

def calculate_widget_position(widget_width: int = 360, widget_height: int = 210, margin: int = 16) -> Dict[str, int]:
    """
    Computes screen coordinates to snap the widget to the bottom-right corner
    just above the Windows taskbar and system notification area.
    """
    width = widget_width
    height = widget_height
    x = 100
    y = 100

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", wintypes.LONG),
                    ("top", wintypes.LONG),
                    ("right", wintypes.LONG),
                    ("bottom", wintypes.LONG)
                ]

            SPI_GETWORKAREA = 0x0030
            rect = RECT()
            user32 = ctypes.windll.user32
            res = user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
            if res:
                work_width = rect.right - rect.left
                work_height = rect.bottom - rect.top
                x = max(0, rect.right - width - margin)
                y = max(0, rect.bottom - height - margin)
        except Exception:
            # Fallback to standard 1080p assumption
            x = max(0, 1920 - width - margin)
            y = max(0, 1040 - height - margin)

    return {"x": x, "y": y, "width": width, "height": height}

def launch_desktop_widget(
    host: str = "127.0.0.1",
    port: int = 8765,
    width: int = 360,
    height: int = 210
) -> Dict[str, Any]:
    """
    Launches the mini widget in standalone chromeless desktop app mode.
    """
    edge_bin = find_edge_binary()
    url = f"http://{host}:{port}/mini_widget.html"
    pos = calculate_widget_position(widget_width=width, widget_height=height)

    profile_dir = Path(REPO_ROOT) / "data" / "widget_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    if edge_bin and Path(edge_bin).exists():
        args = [
            edge_bin,
            f"--app={url}",
            f"--window-size={pos['width']},{pos['height']}",
            f"--window-position={pos['x']},{pos['y']}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return {
                "success": True,
                "mode": "standalone_edge_app",
                "pid": proc.pid,
                "position": pos
            }
        except Exception as e:
            import webbrowser
            webbrowser.open(url)
            return {
                "success": True,
                "mode": "browser_fallback_after_error",
                "error": str(e),
                "url": url
            }

    # Fallback to standard browser launch
    import webbrowser
    webbrowser.open(url)
    return {
        "success": True,
        "mode": "browser_fallback",
        "url": url
    }
