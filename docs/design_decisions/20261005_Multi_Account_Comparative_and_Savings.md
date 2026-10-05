# Architecture Decision Record: Multi-Account Dual-Bar Widget, Comparative Analytics & Local AI Savings

**Date**: 2026-10-05  
**Status**: Accepted  
**Authors**: Antigravity Engineering  
**Derived Standard**: KloGnist WoW v2.5.0 / ASD-STE100  

## Context & Problem Statement
Users require:
1. Fix for the system tray menu "Launch mini status widget" command failing silently.
2. A taskbar/docked status widget presenting dynamic metrics for all monitored accounts simultaneously, with two bar charts per account (Current session remaining % and weekly remaining %) and a Windows 11 Weather-style hover pop-up flyout.
3. Dashboard comparative overview charts providing side-by-side metrics across all accounts.
4. Approximate cost savings and ROI calculations for running local models (e.g. Ollama) compared to cloud frontier rates.
5. Clarification and architectural solution for whole-account vs single API key usage in Google Gemini.

## Decision & Design Rationale
1. **Tray Menu Message Loop**:
   - Win32 `WM_COMMAND` passes the command ID in the low-order word of `wParam`. Python's `ctypes.wintypes` does not define `LOWORD`. We apply the standard bitwise formula `cmd_id = int(wparam) & 0xFFFF`.
   - Each tray window class name is generated with a unique timestamp/pointer hash to avoid `ERROR_CLASS_ALREADY_EXISTS` upon reloads.
   - Removed `close_fds=True` on Windows subprocess creation in `desktop_widget.py`, adding seamless fallback to the system default browser.
2. **Taskbar Widget & Weather-Style Hover Flyout**:
   - Modern Windows 11 does not permit arbitrary third-party Win32 DeskBands into the taskbar strip without custom Shell COM hooks or an MSIX Widget Board provider.
   - The optimal zero-dependency solution is a standalone chromeless webview docked flush to the taskbar, featuring a floating flyout that triggers on mouse hover/click with detailed telemetry (tokens used, session quota, weekly quota, reset timer).
   - Each account card features dual progress bars: Green/Cyan for Session Balance Remaining % and Purple/Blue for Weekly Balance Remaining %.
3. **Comparative Dashboard Analytics & Local Model ROI**:
   - Database layer exposes `get_comparative_metrics()` computing tokens today, tokens this week, all-time volume, session remaining %, and weekly remaining % per provider.
   - Local AI cost savings benchmarks Ollama on-premise tokens against a blended frontier cloud model rate of **$6.00 / 1,000,000 tokens** (Claude 3.5 Sonnet / GPT-4o blended rate), displaying dollars saved today and all-time.
4. **Google Gemini Whole-Account vs Single Key**:
   - Google AI Studio API keys are scoped to specific Google Cloud Projects. A single key cannot query usage across other unrelated projects.
   - Solution: Multi-key aggregation in `configure_api_key` allowing users to register multiple keys separated by commas/newlines, aggregated and summed in the vault, plus direct links to the Google Cloud Quotas Console for project-wide quota analysis.

## Consequences & Trade-offs
- **Positives**: Complete visibility across all AI accounts simultaneously; clear financial ROI for running local hardware; zero third-party dependencies maintained.
- **Constraints**: Benchmarks for local savings are estimates based on standard cloud API price schedules.
