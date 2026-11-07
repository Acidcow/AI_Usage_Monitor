#!/usr/bin/env python3
"""
IRIS Single-File Installer Generator
===================================
Packages the entire IRIS platform into a zero-external-dependency, single-file,
click-to-install distribution for Windows.

Generates:
1. dist/IRIS-Setup.cmd  - Single-file self-extracting executable batch installer.
                          Contains an embedded compressed payload. Double-click to install.
2. dist/IRIS-Setup.exe  - Native Windows PE executable installer generated via built-in IExpress.
3. dist/IRIS-Portable.zip - Clean portable archive.

Zero third-party tools required: Uses Python 3 Standard Library + native Windows utilities.
"""

import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import shutil
import zipfile
import base64
import subprocess
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files and directories to package into the distribution payload
PACKAGE_DIRS = [
    "backend",
    "frontend",
    "dev_tools",
    "docs"
]

PACKAGE_FILES = [
    "run_monitor.py",
    "setup.ps1",
    "LICENSE",
    "README.md"
]

IGNORE_DIRS = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    "widget_profile",
    "dist",
    "build",
    ".gemini"
}

IGNORE_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".dmp", ".db", ".enc", ".log", ".tmp", ".crx"
}

INSTALLER_PAYLOAD_MARKER = "___IRIS_PAYLOAD_START___"

def create_payload_zip(output_zip_path: Path, include_tests: bool = False) -> int:
    """Creates a clean, compressed zip archive of the IRIS platform."""
    print(f"[PACK] Assembling distribution payload at {output_zip_path}...")
    
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        # Add root files
        for f_name in PACKAGE_FILES:
            f_path = REPO_ROOT / f_name
            if f_path.exists():
                zf.write(f_path, arcname=f_name)
                print(f"  + Added file: {f_name}")

        # Add directories
        for d_name in PACKAGE_DIRS:
            d_path = REPO_ROOT / d_name
            if not d_path.exists():
                continue
            for root, dirs, files in os.walk(d_path):
                # Skip cache and ephemeral directories
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                for file in files:
                    ext = Path(file).suffix.lower()
                    if ext in IGNORE_EXTENSIONS:
                        continue
                    full_p = Path(root) / file
                    rel_p = full_p.relative_to(REPO_ROOT)
                    zf.write(full_p, arcname=str(rel_p))
            print(f"  + Added directory: {d_name}/")

        if include_tests:
            t_path = REPO_ROOT / "tests"
            if t_path.exists():
                for root, dirs, files in os.walk(t_path):
                    dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                    for file in files:
                        ext = Path(file).suffix.lower()
                        if ext in IGNORE_EXTENSIONS:
                            continue
                        full_p = Path(root) / file
                        rel_p = full_p.relative_to(REPO_ROOT)
                        zf.write(full_p, arcname=str(rel_p))
                print("  + Added directory: tests/")

    size_bytes = output_zip_path.stat().st_size
    print(f"[OK] Payload zip created: {size_bytes / (1024 * 1024):.2f} MB")
    return size_bytes

def generate_self_extracting_cmd(payload_zip: Path, output_cmd: Path) -> Path:
    """
    Builds a single-file, double-clickable Windows command/PowerShell hybrid installer.
    Contains embedded compressed base64 payload that self-extracts to %LOCALAPPDATA%\\IRIS,
    creates desktop/start menu shortcuts, registers Windows startup, and starts the service.
    """
    print(f"[BUILD] Generating single-file self-extracting click-installer: {output_cmd}...")

    with open(payload_zip, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode("ascii")

    # Split into 76-character chunks for clean readability and shell compatibility
    chunk_size = 76
    b64_chunks = [b64_data[i:i + chunk_size] for i in range(0, len(b64_data), chunk_size)]
    b64_block = "\n".join(b64_chunks)

    installer_script = f"""@echo off
rem ==============================================================================
rem IRIS (Inter-node Routing, Inference & Security) - Single-File Click Installer
rem ==============================================================================
setlocal EnableDelayedExpansion

title IRIS - Installing Sovereign P2P Agent Mesh & Telemetry Monitor...
color 0B

echo.
echo  ==================================================================
echo    IRIS: Inter-node Routing, Inference ^& Security
echo    Zero-Dependency Sovereign P2P Mesh ^& Agent Telemetry Monitor
echo  ==================================================================
echo.

rem 1. Check for Python 3
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python 3 was not detected on this system.
    echo Please install Python 3.10+ from https://python.org or the Microsoft Store.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python -c "import sys; print(f'{{sys.version_info.major}}.{{sys.version_info.minor}}')"') do set PYVER=%%i
echo [OK] Detected Python %PYVER% on system.

rem 2. Target Directory in User Local AppData (Zero Administrator UAC Prompt Needed)
set "INSTALL_DIR=%LOCALAPPDATA%\\IRIS"
echo [INFO] Target installation directory: %INSTALL_DIR%

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
set "TEMP_ZIP=%TEMP%\\iris_install_payload_%RANDOM%.zip"
set "B64_FILE=%TEMP%\\iris_payload_%RANDOM%.b64"

echo [STEP 1/5] Extracting embedded platform payload...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$raw = Get-Content -Path '%~f0' | Out-String; " ^
    "$marker = '___' + 'IRIS_PAYLOAD_START___'; " ^
    "$idx = $raw.LastIndexOf($marker); " ^
    "if ($idx -lt 0) {{ Write-Error 'Payload marker not found'; exit 1 }}; " ^
    "$b64 = $raw.Substring($idx + $marker.Length).Trim(); " ^
    "[IO.File]::WriteAllText('%B64_FILE%', $b64); " ^
    "$bytes = [Convert]::FromBase64String($b64); " ^
    "[IO.File]::WriteAllBytes('%TEMP_ZIP%', $bytes); " ^
    "Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%INSTALL_DIR%' -Force; " ^
    "Remove-Item '%TEMP_ZIP%' -Force -ErrorAction SilentlyContinue; " ^
    "Remove-Item '%B64_FILE%' -Force -ErrorAction SilentlyContinue;"

if %ERRORLEVEL% NEQ 0 (
    echo [FATAL] Extraction failed.
    pause
    exit /b 1
)
echo [OK] Platform files extracted successfully.

rem 3. Initialize Database and Subsystems
echo [STEP 2/5] Initializing local database and cryptographic DPAPI vault...
pushd "%INSTALL_DIR%"
python dev_tools/manage_roadmap.py init >nul 2>&1
popd

rem 4. Register Windows Auto-Start
echo [STEP 3/5] Registering Windows Auto-Start (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)...
pushd "%INSTALL_DIR%"
python run_monitor.py --install-startup --widget >nul 2>&1
popd
echo [OK] Windows Auto-Start configured.

rem 5. Create Desktop and Start Menu Shortcuts
echo [STEP 4/5] Creating Desktop and Start Menu shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
    "$shortcutPath = Join-Path $desktop 'IRIS Monitor.lnk'; " ^
    "$sc = $ws.CreateShortcut($shortcutPath); " ^
    "$pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source; " ^
    "if (-not $pyw) {{ $pyw = (Get-Command python).Source }}; " ^
    "$sc.TargetPath = $pyw; " ^
    "$sc.Arguments = '\"%INSTALL_DIR%\\run_monitor.py\" --open-browser --widget'; " ^
    "$sc.WorkingDirectory = '%INSTALL_DIR%'; " ^
    "$sc.Description = 'IRIS - Inter-node Routing, Inference & Security'; " ^
    "$iconPath = Join-Path '%INSTALL_DIR%' 'frontend\\assets\\icons\\app_icon_johnny5.ico'; " ^
    "if (Test-Path $iconPath) {{ $sc.IconLocation = $iconPath }}; " ^
    "$sc.Save(); " ^
    "$programs = [Environment]::GetFolderPath('Programs'); " ^
    "$smPath = Join-Path $programs 'IRIS.lnk'; " ^
    "$sc2 = $ws.CreateShortcut($smPath); " ^
    "$sc2.TargetPath = $pyw; " ^
    "$sc2.Arguments = '\"%INSTALL_DIR%\\run_monitor.py\" --open-browser --widget'; " ^
    "$sc2.WorkingDirectory = '%INSTALL_DIR%'; " ^
    "$sc2.Description = 'IRIS - Inter-node Routing, Inference & Security'; " ^
    "if (Test-Path $iconPath) {{ $sc2.IconLocation = $iconPath }}; " ^
    "$sc2.Save();"
echo [OK] Desktop and Start Menu shortcuts created.

rem 6. Launch Service & Dashboard
echo [STEP 5/5] Launching IRIS background service and dashboard...
pushd "%INSTALL_DIR%"
start "" pythonw run_monitor.py --open-browser --widget
popd

echo.
echo ==================================================================
echo   [SUCCESS] IRIS installed and active!
echo.
echo   - Web Dashboard:     http://127.0.0.1:8765
echo   - Mini Taskbar Bar:  http://127.0.0.1:8765/mini_widget.html
echo   - Transparent Proxy: http://127.0.0.1:8766/v1
echo   - P2P Tunnel:        https://127.0.0.1:8767
echo   - System Tray Icon:  Running in Taskbar Notification Area
echo ==================================================================
echo.
timeout /t 5 >nul
exit /b 0

{INSTALLER_PAYLOAD_MARKER}
{b64_block}
"""

    with open(output_cmd, "w", encoding="utf-8") as f:
        f.write(installer_script)

    print(f"[OK] Single-file click installer created: {output_cmd} ({output_cmd.stat().st_size / (1024 * 1024):.2f} MB)")
    return output_cmd

def generate_iexpress_exe(payload_zip: Path, setup_cmd: Path, output_exe: Path) -> bool:
    """
    Invokes Windows built-in IExpress (C:\\Windows\\System32\\iexpress.exe) to produce
    a native PE .exe installer with embedded extraction instructions and manifest.
    Zero third-party tools required.
    """
    iexpress_bin = Path(os.environ.get("WINDIR", "C:\\Windows")) / "System32" / "iexpress.exe"
    if not iexpress_bin.exists():
        print("[WARN] IExpress.exe not found on system. Skipping native PE .exe generation.")
        return False

    print(f"[BUILD] Generating native Windows executable installer via IExpress: {output_exe}...")
    temp_dir = payload_zip.parent / "iexpress_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    sed_file = temp_dir / "iris_setup.sed"

    # IExpress SED Directive Script
    sed_content = f"""[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName={output_exe.resolve()}
FriendlyName=IRIS Setup
AppLaunched=cmd.exe /c "{setup_cmd.name}"
PostInstallCmd=<None>
AdminQuietInstCmd=cmd.exe /c "{setup_cmd.name}"
UserQuietInstCmd=cmd.exe /c "{setup_cmd.name}"
SourceFiles=SourceFiles
[SourceFiles]
SourceFiles0={setup_cmd.parent.resolve()}\\
[SourceFiles0]
%FILE0%={setup_cmd.name}
[Strings]
FILE0="{setup_cmd.name}"
"""

    with open(sed_file, "w", encoding="utf-8") as f:
        f.write(sed_content)

    try:
        res = subprocess.run(
            [str(iexpress_bin), "/N", "/Q", str(sed_file)],
            capture_output=True,
            text=True,
            timeout=15.0
        )
        if res.returncode == 0 and output_exe.exists():
            print(f"[OK] Native PE .exe installer generated successfully: {output_exe} ({output_exe.stat().st_size / (1024*1024):.2f} MB)")
            return True
        else:
            print(f"[WARN] IExpress returned code {res.returncode}. Output: {res.stdout} {res.stderr}")
            return False
    except Exception as e:
        print(f"[WARN] Failed to run IExpress: {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser(description="IRIS Single-File Installer Generator")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "dist"), help="Directory to save generated installers")
    parser.add_argument("--include-tests", action="store_true", help="Include test suite in distribution bundle")
    parser.add_argument("--iexpress", action="store_true", help="Generate optional native PE .exe installer using Windows built-in IExpress")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 65)
    print("⚡ IRIS SINGLE-FILE INSTALLER BUILDER")
    print("=" * 65)

    payload_zip = out_dir / "iris_payload.zip"
    create_payload_zip(payload_zip, include_tests=args.include_tests)

    # 1. Generate Single-File Click Installer (.cmd)
    setup_cmd = out_dir / "IRIS-Setup.cmd"
    generate_self_extracting_cmd(payload_zip, setup_cmd)

    # 2. Generate Native Windows Executable (.exe) if explicitly requested
    if args.iexpress and sys.platform == "win32":
        output_exe = out_dir / "IRIS-Setup.exe"
        generate_iexpress_exe(payload_zip, setup_cmd, output_exe)

    # Clean up intermediate raw zip if desired, or keep as portable archive
    portable_zip = out_dir / "IRIS-Portable.zip"
    if portable_zip.exists():
        portable_zip.unlink()
    payload_zip.rename(portable_zip)
    print(f"[OK] Clean portable archive saved: {portable_zip}")

    print("\n" + "=" * 65)
    print("🎉 BUILD COMPLETE")
    print("=" * 65)
    print(f"1. Single-File Click Installer:  {setup_cmd}")
    if (out_dir / "IRIS-Setup.exe").exists():
        print(f"2. Native Windows Executable:     {out_dir / 'IRIS-Setup.exe'}")
    print(f"3. Portable Zip Archive:          {portable_zip}")
    print("\nUsers can simply copy IRIS-Setup.cmd or IRIS-Setup.exe to any Windows machine and double-click to install!")

if __name__ == "__main__":
    main()
