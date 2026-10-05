# Architecture Decision Record: Johnny 5 Visual Identity & Contextual Mascot System

**Date**: 2026-10-05  
**Status**: Accepted  
**Driver**: User Request for cute, recognizable Short Circuit Johnny 5 mascot and dual-choice app icons  

---

## 1. Context & Problem Statement
AI Usage Monitor is a developer tool tracking LLM tokens, rate limits, and Windows DPAPI encrypted credentials. To elevate the application's user experience and personality without adding third-party asset libraries or frameworks, a cohesive visual identity is needed:
- A friendly, memorable mascot (Johnny 5 from *Short Circuit*) who embodies "alive" telemetry and "input".
- Two app icon options: a glowing Johnny 5 headshot and a transparent cyber shield with a purple slash.
- Contextual mascot variations across UI views (dashboard welcome, session inspection, and zero-error health reports).

## 2. Decision
1. **Zero-Dependency Static Asset Pipeline**:
   - Store generated high-resolution assets in `frontend/assets/icons/` and `frontend/assets/mascot/`.
   - Update `MIME_MAP` in `backend/server/http_server.py` to natively serve `.jpg`, `.jpeg`, and `.webp` with `image/jpeg` / `image/webp` headers.
   - Avoid Pillow, PIL, or node graphics pipelines; keep all image assets standard web formats.
2. **Switchable Application Icon Pattern**:
   - Provide two primary icons:
     - **Johnny 5 Headshot**: Glowing cyan stereoscopic sensors, electric purple/cyan circuit patterns.
     - **Cyber Shield**: Glass shield with bold black outline and vibrant neon purple slash, symbolizing DPAPI encryption.
   - Support instant client-side toggling via header avatar click or dedicated Modal with persistence in `localStorage`.
3. **Contextual Mascot UI Integration**:
   - **Dashboard Banner**: Johnny 5 Pointing (`johnny5_pointing.jpg`) with an interactive speech bubble and rotating quotes.
   - **Session Telemetry Empty State**: Johnny 5 Inspecting (`johnny5_inspecting.jpg`) scanning holograms.
   - **Diagnostics Zero Errors State**: Johnny 5 Thumbs-Up Success (`johnny5_success.jpg`) confirming zero malfunctions.
   - **Floating Mini-Widget Header**: Miniature Johnny 5 badge in the draggable title bar.

## 3. Consequences
- **Positive**:
  - Imbues the application with a delightful, unique personality.
  - Maintains strict zero-dependency core architecture.
  - Enhances user feedback across empty and healthy states.
- **Negative / Mitigations**:
  - Adds ~3.8MB of static image assets to the repository. Mitigated by optimized JPEG compression.
