<#
.SYNOPSIS
    AI Usage Monitor - Environment Bootstrap & Launch Script
.DESCRIPTION
    Zero-dependency bootstrap script for Windows.
    Verifies Python, initializes database, runs test suite, and launches service.
#>

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AI Usage Monitor - Windows Environment Bootstrap       " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Verify Python
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    Write-Error "[FATAL] Python 3 was not found on PATH. Please install Python 3.10+."
    exit 1
}

$PyVer = python --version
Write-Host "[OK] Detected: $PyVer" -ForegroundColor Green

# 2. Initialize Roadmap Database
Write-Host "`n[STEP 1/3] Initializing Developer Database & Epics..." -ForegroundColor Yellow
python dev_tools/manage_roadmap.py init
if ($LASTEXITCODE -ne 0) {
    Write-Error "[FAIL] Failed to initialize roadmap database."
    exit 1
}

# 3. Pre-Flight Test Suite Verification
Write-Host "`n[STEP 2/3] Running Pre-Flight Unit & Security Test Suite..." -ForegroundColor Yellow
python dev_tools/manage_roadmap.py run-tests
if ($LASTEXITCODE -ne 0) {
    Write-Error "[FAIL] Pre-flight tests failed. Please investigate test log."
    exit 1
}

# 4. Launch Service
Write-Host "`n[STEP 3/3] Launching AI Usage Monitor Service..." -ForegroundColor Yellow
Write-Host "-> Dashboard: http://127.0.0.1:8765" -ForegroundColor Cyan
Write-Host "-> Mini Widget: http://127.0.0.1:8765/mini_widget.html" -ForegroundColor Cyan
Write-Host "-> Claude CLI Proxy: http://127.0.0.1:8766/v1" -ForegroundColor Cyan
Write-Host "-> Windows System Tray Icon: Active" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop.`n" -ForegroundColor Gray

# Ensure no duplicate background instances are holding ports 8765/8766
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*run_monitor.py*" -and $_.ProcessId -ne $PID } | ForEach-Object {
    Write-Host "[CLEANUP] Stopping previous monitor instance (PID $($_.ProcessId))..." -ForegroundColor DarkGray
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

python run_monitor.py --open-browser --demo
