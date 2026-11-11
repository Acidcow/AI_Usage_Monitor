# I.R.I.S. — Next Session Prioritized TODO Roadmap

**Last Updated**: 2026-11-11  
**Baseline Release**: `v3.1.0`  
**Target Release**: `v3.2.0`  

---

## Priority 1: Mascot v3.2 Revisit (Awaiting New Reference Images)

- **Action**: Wait for the user to provide new character reference images at the start of the next session.
- **Character Direction**:
  - Mature, demure, sassy, and confident demeanor with a mischievous dimpled smile.
  - Royal-blue / dark-blue hair, base pose in sports bra and boy-shorts, and a *Deus Ex*-style cybernetic arm.
  - High-resolution pixel art style inspired by *The Dig* (LucasArts).
- **Asset Pack Regeneration (`frontend/assets/iris_mascot/` & `frontend/assets/icons/`)**:
  - `00_base_reference/`: Canonical 3-view character turnaround sheet.
  - `01_poses/`: Full-character poses (`pose_base_athletic.png`, `pose_console_command.png`, `pose_cyber_shield.png`, `pose_diagnostic_repair.png`) featured prominently on main UI stages.
  - `02_outfits/`: Equippable overlays (`outfit_base_athletic.png`, `outfit_tactical_vest.png`, `outfit_command_coat.png`, `outfit_stealth_netrunner.png`).
  - `03_expressions/`: 4 emotion families (`nominal`, `guidance`, `warning`, `critical`) across 3 degrees of severity (`deg1`, `deg2`, `deg3`).
  - `04_avatars/`: 1:1 contextual avatars for dialogs, error messages, guidance, configurations, and stats.
  - `05_animations/`: Looping `GIF89a` animations (`anim_idle_wink_smile.gif`, `anim_loading_scan.gif`, `anim_busy_processing.gif`, `anim_alert_pulse.gif`) triggered on mouse-over, loading, and busy states.
  - `frontend/assets/icons/`: Selectable Windows Task Manager / System Tray / Native Widget icons (`iris_head`, `iris_eye`, `iris_cyber_arm`, `iris_holo`).

---

## Priority 2: Official `I.R.I.S.` Platform Identity in UI (Welcome, Help, About)

Integrate the full platform identity from [`docs/IRIS_PLATFORM_IDENTITY.md`](./IRIS_PLATFORM_IDENTITY.md) into the Web Dashboard (Welcome/Onboarding view, Help Pop-up, and About Modal):

```text
  ██╗██████╗ ██╗███████╗
  ██║██╔══██╗██║██╔════╝
  ██║██████╔╝██║███████╗
  ██║██╔══██╗██║╚════██║
  ██║██║  ██║██║███████║
  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝
I.R.I.S.
Inter-node Routing, Inference & Security
Zero-Dependency Sovereign P2P Agent Mesh & Multi-Model Observability Platform
```

### Acronym Breakdown to Display:
- **`[ I ]` INTER-NODE**: Zero-configuration LAN discovery (UDP beacon) detecting peer instances and pooling workstation capacity across the local network.
- **`[ R ]` ROUTING**: Intelligent delegation of agent tasks, quota bursting, and transparent proxy forwarding across idle local nodes.
- **`[ I ]` INFERENCE**: Real-time multi-provider model monitoring, streaming token extraction (SSE), and universal local emulation.
- **`[ S ]` SECURITY**: Native Windows DPAPI encryption, TLS 1.3 anti-snooping tunnels, mutual peer authentication, and proactive log sanitization.

### Mythology Pillars to Display:
1. **The Rainbow as the Multi-Model Spectrum**: Unifying Claude, Gemini, ChatGPT, Copilot, Ollama, and DeepSeek into one coherent pane of glass.
2. **The Golden Ewer of the River Styx**: Protecting credentials with Windows DPAPI (`crypt32.dll`) and encapsulating inter-instance traffic within TLS 1.3 encrypted tunnels (`AES-256-GCM`).
3. **The Golden Wings (*Chrysopteros*)**: Zero-external-dependency architecture (Python 3 Standard Library + Win32 native APIs) launching in milliseconds with zero npm/pip bloat.

---

## Priority 3: System-Wide `"AI Usage Monitor"` → `"IRIS"` Rebranding Sweep

Audit and replace remaining legacy `"AI Usage Monitor"` / `"AI-usage-monitor"` references across all UI surfaces, context menus, and system descriptors:
- `backend/tray/windows_tray.py`: System tray tooltip, default `app_name`, and right-click context menu labels (`"Open IRIS Dashboard"`, `"Launch IRIS Mini Widget"`, etc.).
- `backend/tray/native_widget.py`: Native taskbar widget header (`"⚡ IRIS SENTINEL"`) and right-click Win32/Tkinter context menu items.
- `frontend/mini_widget.html` & `frontend/js/widget.js`: Web mini-widget title, header badges, and tooltips.
- `run_monitor.py` & `backend/system/windows_service.py`: Process titles, startup registry labels, and service descriptions.
- `tests/`: Update corresponding test assertions that check legacy menu label strings.

---

## Priority 4: Retro CRT / Terminal "Prompt" Pop-Up UI

Build a dedicated pop-up **CRT / Phosphor Terminal Chat & Prompt Interface** accessible from the main header, keyboard shortcut, and system tray:
- **Visual Style**:
  - Classic CRT terminal aesthetic (phosphor green/amber/cyan selectable tint, subtle scanlines, monospace ASCII frame) featuring the **`I.R.I.S.` ASCII art header**.
  - **Live Mascot "Video-Chat Thumbnail" (`[REC] LIVE COMMS`)**: Corner HUD feed displaying IRIS with live animated GIF transitions (`idle` -> `scanning` -> `busy/transmitting` -> `nominal`/`alert`) reacting to prompt execution and responses.
- **Interactive Terminal Context Menus (Clickable Selectors)**:
  - **Target Interface / Instance Selector**:
    - `Load-Balanced Ollama Pool` (`target="pool"` across LAN mesh)
    - `Local Ollama Daemon` (`localhost:11434`)
    - Specific discovered LAN Peer Nodes (`node_id`)
    - Configured **Google Gemini** accounts
    - Configured **Claude (Anthropic)** accounts
    - Configured **ChatGPT / OpenAI** or **M365 Copilot** accounts
  - **Model Selector**: Dynamically populated based on selected interface/account.
  - **Reasoning / Thinking Depth Selector**: e.g., `Fast / Standard`, `Extended Thinking`, `Deep Audit`, plus temperature and max-token controls.
  - **Live Telemetry Readout**: Inline display of latency (`ms`), prompt/completion tokens, tok/s throughput, and routing path after each response.
