# Architecture Decision Record: Windows Native Security (DPAPI) and System Tray

**Date**: 2026-10-05  
**Status**: Accepted  

## Context
Credentials such as Anthropic API keys or session tokens must never be written in plaintext in configuration files or SQLite tables. Windows provides built-in enterprise-grade cryptographic functions (Data Protection API - DPAPI) that encrypt data using the logged-in Windows user's profile credentials.

Similarly, user experience requires ambient taskbar / system tray visibility without installing heavy GUI toolkits.

## Decision
1. **Security**: We invoke `CryptProtectData` and `CryptUnprotectData` in `crypt32.dll` directly via Python's standard `ctypes` library.
2. **System Tray**: We interact directly with `shell32.dll` and `user32.dll` to register a Windows System Tray icon (`Shell_NotifyIconW`), display dynamic hover tooltips, and handle user clicks.
3. **Taskbar Status Widget**: We provide a dedicated, lightweight HTML5 floating/dockable micro-widget view (`frontend/mini_widget.html`) optimized for status bar display and second monitors.

## Consequences
- Eliminates dependencies like `cryptography` and `pystray`.
- Full native integration with Windows user security policies.
