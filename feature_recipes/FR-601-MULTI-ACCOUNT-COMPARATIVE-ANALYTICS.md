# Feature Recipe FR-601: Multi-Account Dual-Bar Widget & Comparative Dashboard Analytics

## 1. Goal
Provide a comprehensive comparative overview across all connected accounts (Claude, Google Gemini, ChatGPT, Ollama Local, M365 Copilot), featuring:
1. A multi-account status widget equipped with dual bar charts (current session remaining % and weekly remaining %) and a Windows 11 Weather-style hover flyout.
2. A dashboard comparative breakdown table and local AI cost savings calculation.
3. Multi-key and whole-account usage aggregation for Google Gemini.

## 2. Technical Requirements
1. **Tray Menu Message Loop Bug Fix**:
   - Fix `wintypes.LOWORD` AttributeError in `backend/tray/windows_tray.py` by replacing with bitwise `int(wparam) & 0xFFFF`.
   - Provide each tray instance with a unique Win32 window class name.
   - Remove `close_fds=True` on Windows in `backend/tray/desktop_widget.py` and supply automatic browser fallback.
2. **Dual-Bar Multi-Account Status Widget (`frontend/mini_widget.html`, `frontend/js/widget.js`)**:
   - List each active account with status dot, brand badge, and today's token volume.
   - Dual Progress Bars:
     - Bar 1: Current Session Balance Remaining % (Green/Cyan gradient).
     - Bar 2: Weekly Balance Remaining % (Purple/Blue gradient).
   - Weather-style detailed hover flyout (`#w-hover-flyout`) displaying exact tokens used, weekly volume, session quota remaining, and reset countdowns on hover or click.
   - Mode switcher between "⊞ Accounts" (all providers) and "⚲ Focus" (single provider).
3. **Comparative Dashboard Analytics & Local Model ROI (`frontend/components/usage_gauge_card.html`, `frontend/js/app.js`)**:
   - Local AI Cost Savings Card calculating dollars saved by running Ollama locally vs cloud frontier rate benchmark ($6.00/M tokens blended rate).
   - Side-by-side comparative table showing provider status, today's tokens, volume share %, dual session/weekly progress bars, and estimated costs.
4. **Google Gemini Multi-Key & Whole-Account Aggregation**:
   - Accept multiple comma- or newline-separated API keys in `POST /api/providers/gemini/config`.
   - Store credentials securely via Windows DPAPI (`backend/security/vault.py`).
   - Allow optional GCP Project ID and provide direct link to Google Cloud Quotas Console (`https://console.cloud.google.com/iam-admin/quotas`).

## 3. Verification Criteria
- Automated unit tests `test_tray_menu_commands`, `test_comparative_metrics_and_local_savings`, `test_api_usage_comparison`, and `test_api_gemini_config_with_project_id` pass.
- 100% test pass rate across 49+ tests.
- Zero external pip or npm dependencies.
