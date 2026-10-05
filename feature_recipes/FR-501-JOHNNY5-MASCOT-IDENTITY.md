# Feature Recipe FR-501: Johnny 5 Mascot & Visual Identity System

## 1. Goal
Introduce an engaging, recognizable retro-futuristic brand identity and mascot inspired by Johnny 5 (*Short Circuit*), complete with punchy modern background aesthetics, switchable cybernetic app icons, and contextual mascot variations across all UI views.

## 2. Technical Requirements
1. **Asset Deployment & Zero Dependencies**:
   - Store high-resolution visual assets in `frontend/assets/icons/` and `frontend/assets/mascot/`.
   - Ensure the zero-dependency Python HTTP server (`http_server.py`) recognizes `.jpg`, `.jpeg`, and `.webp` MIME types with standard `image/jpeg` headers.
2. **Dual Switchable App Icons**:
   - **Johnny 5 Headshot (`app_icon_johnny5.jpg`)**: Glowing cyan optic sensors, electric violet/cyan circuit pattern, and numbered headcap.
   - **Cyber Shield (`app_icon_shield.jpg`)**: Transparent glass cybernetic shield with bold black outline and vibrant purple neon diagonal slash.
   - Interactive icon toggle on header brand logo and dedicated Icon Customizer Modal (`#icon-picker-modal`).
   - Store user preference in `localStorage` under `aium_active_icon`.
3. **Contextual Mascot UI Variations**:
   - **Main Dashboard Banner (`johnny5_pointing.jpg`)**: Johnny 5 with index finger raised to make a point, equipped with an interactive quote rotator and status badge.
   - **Recent Sessions Telemetry (`johnny5_inspecting.jpg`)**: Johnny 5 on tracks inspecting holographic token streams when scanning for agentic activity.
   - **Diagnostic Troubleshooter (`johnny5_success.jpg`)**: Johnny 5 giving a cheerful thumbs-up when zero errors or rate limits are present.
   - **Floating Mini-Widget (`mini_widget.html`)**: Miniature glowing Johnny 5 badge in the draggable taskbar header.
4. **Interactive Mascot Quotes Engine**:
   - Rotates iconic Short Circuit quotes ("Number 5 is alive!", "Input! Need more input!", "Hey laser lips, DPAPI protects your keys!").

## 3. Verification Criteria
- Automated unit test `test_static_asset_serving_icons_and_mascots` passes with HTTP 200 and `image/jpeg` headers.
- Total test suite maintains 100% pass rate across 45+ tests.
- UI elements in `index.html` and `mini_widget.html` render cleanly with zero external npm/pip dependencies.
