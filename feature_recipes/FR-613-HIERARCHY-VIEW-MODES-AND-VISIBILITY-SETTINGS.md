# Feature Recipe FR-613: Dynamic Hierarchy View Modes, Group Tagging & Platform Visibility Settings

## 1. Goal
Provide the ability in both the Dashboard and the Mini Widget to switch top-level hierarchy structure between "All", "Platforms/Services", "Groups" (labels/tags), or filtered views using an interactive multi-select panel. Allow fine-grained configuration to toggle visibility of any platform, account, API key, or tag (e.g. hide unconfigured ChatGPT or hide Gemini by default).

## 2. Technical Requirements
1. **Hierarchy Grouping Switcher Modes**:
   - **All**: Displays all platforms and all defined tag groups in the root hierarchy tree.
   - **Platforms**: Groups items strictly under provider/platform parents (`claude`, `gemini`, `chatgpt`, `ollama`, `copilot`).
   - **Groups**: Groups items strictly by custom tag/label umbrellas (`Engineering`, `Production`, `R&D`, `Personal`).
   - **Filtered**: Filters the view to a user-selected subset of platforms and/or groups.

2. **Interactive Multi-Select Filter Panel**:
   - Accessible via a button/icon in both the Dashboard and Mini Widget headers.
   - Displays a clean checklist of all available platforms and groups with select all / deselect all controls.
   - Updates the table and widget layout immediately upon selection change or confirmation.

3. **Item Visibility & Default Display Configurations**:
   - In Settings / Configuration view: allow users to configure global visibility flags for each platform and account:
     - `visible_platforms`: Array of platform keys to display (`["claude", "gemini", "ollama"]`).
     - If a platform is marked invisible (e.g. unconfigured `chatgpt`), it is excluded from the default view in both the Dashboard and Mini Widget.
     - Unconfigured platforms default to hidden or greyed out unless explicitly enabled.
   - Stored securely in `app_settings` via SQLite and Windows DPAPI.
   - REST API endpoints:
     - `GET /api/settings/visibility`
     - `POST /api/settings/visibility` (payload with `platforms`, `accounts`, `tags`)

## 3. Verification Criteria
- [x] Switching between All, Platforms, and Groups restructures the hierarchy tree correctly.
- [x] Multi-select filter panel renders correctly and filters top-level nodes in real-time.
- [x] Visibility configuration persists in database and filters out hidden platforms in both Dashboard and Mini Widget.
- [x] Zero external dependencies.

