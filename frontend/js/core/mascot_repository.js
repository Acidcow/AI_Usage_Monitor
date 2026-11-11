/**
 * IRIS (Intelligent Resource & Inference Sentinel) - Canonical Mascot & Asset Repository (v3.1)
 * Style: 1995 LucasArts "The Dig" & "Deus Ex" High-Resolution Pixel Art
 * Features:
 *  - 00_base_reference (100% original canonical turnaround: Royal-Blue hair, Sports Bra & Boy-Shorts, Deus-Ex Cybernetic Left Arm, Dimpled Smile)
 *  - 01_poses (4 full-body/scene operational postures)
 *  - 02_outfits (4 modular outfit overlays)
 *  - 03_expressions (4 emotion/situation spectra x 3 severity degrees = 12 expression states)
 *  - 04_avatars (6 contextual 1:1 UI avatars for dialogs, guidance, configurations, stats, and alerts)
 *  - 05_animations (4 multi-frame animated GIFs for mouse-over hover, loading/syncing, busy/calibration, and alerts)
 *  - Selectable Windows System Tray & Task Manager Application Icons (iris_head, iris_eye, iris_cyber_arm, iris_holo)
 */
(function (global) {
  "use strict";

  const REPO_ROOT = "/assets/iris_mascot";

  const MASCOT_MANIFEST = {
    schema_version: "3.1.0",
    character_id: "iris_sentinel_v3",
    character_name: "IRIS",
    character_title: "Intelligent Resource & Inference Sentinel",
    art_style: "LucasArts 'The Dig' & 'Deus Ex' High-Res Pixel Art",
    base_references: [
      {
        id: "base_skinsuit_turnaround",
        label: "Master Canonical Turnaround (Sports Bra, Boy-Shorts & Deus-Ex Cyber Arm)",
        path: `${REPO_ROOT}/00_base_reference/iris_base_skinsuit_turnaround.png`,
        role: "100% original canonical anatomy, royal-blue hair, Deus-Ex cybernetic arm, and pixel-palette anchor"
      }
    ],
    poses: [
      {
        id: "pose_neutral_standing",
        label: "Sassy Sentinel Stance (Base)",
        path: `${REPO_ROOT}/01_poses/pose_neutral_standing.png`,
        hover_gif: `${REPO_ROOT}/05_animations/anim_idle_wink_smile.gif`,
        context: "Nominal monitoring posture in sports bra, boy-shorts & Deus-Ex cybernetic arm"
      },
      {
        id: "pose_analytical_console",
        label: "Analytical Console Inspection",
        path: `${REPO_ROOT}/01_poses/pose_analytical_console.png`,
        hover_gif: `${REPO_ROOT}/05_animations/anim_loading_scan.gif`,
        context: "Inspecting token velocity curves & prompt cache ROI"
      },
      {
        id: "pose_alert_defensive",
        label: "Tactical Rate-Limit Defense",
        path: `${REPO_ROOT}/01_poses/pose_alert_defensive.png`,
        hover_gif: `${REPO_ROOT}/05_animations/anim_alert_pulse.gif`,
        context: "Quota exhaustion shielding & circuit-breaker intervention"
      },
      {
        id: "pose_diagnostic_repair",
        label: "Diagnostic Node Calibration",
        path: `${REPO_ROOT}/01_poses/pose_diagnostic_repair.png`,
        hover_gif: `${REPO_ROOT}/05_animations/anim_busy_processing.gif`,
        context: "Local daemon discovery, proxy bridge & DPAPI calibration"
      }
    ],
    outfits: [
      {
        id: "outfit_digital_skinsuit",
        label: "Athletic Base (Sports Bra & Boy-Shorts)",
        path: `${REPO_ROOT}/02_outfits/outfit_digital_skinsuit.png`,
        badge: "Base Layer"
      },
      {
        id: "outfit_field_tactical",
        label: "Deus-Ex Field Tactical Rig",
        path: `${REPO_ROOT}/02_outfits/outfit_field_tactical.png`,
        badge: "Tactical"
      },
      {
        id: "outfit_lab_chief_coat",
        label: "Chief Telemetry Suit",
        path: `${REPO_ROOT}/02_outfits/outfit_lab_chief_coat.png`,
        badge: "Lab / R&D"
      },
      {
        id: "outfit_eva_astronaut_rig",
        label: "Deep-Space EVA Rig ('The Dig')",
        path: `${REPO_ROOT}/02_outfits/outfit_eva_astronaut_rig.png`,
        badge: "LucasArts EVA"
      }
    ],
    animations: {
      idle_wink: {
        id: "anim_idle_wink_smile",
        label: "Mischievous Dimpled Smile & Wink (Hover)",
        path: `${REPO_ROOT}/05_animations/anim_idle_wink_smile.gif`
      },
      loading_scan: {
        id: "anim_loading_scan",
        label: "Holographic Telemetry Scan (Loading / Sync)",
        path: `${REPO_ROOT}/05_animations/anim_loading_scan.gif`
      },
      busy_processing: {
        id: "anim_busy_processing",
        label: "Node Calibration Sparks (Busy / Benchmark)",
        path: `${REPO_ROOT}/05_animations/anim_busy_processing.gif`
      },
      alert_pulse: {
        id: "anim_alert_pulse",
        label: "Hexagonal Shield Pulse (Alert / 429)",
        path: `${REPO_ROOT}/05_animations/anim_alert_pulse.gif`
      }
    },
    app_icons: [
      {
        id: "iris_head",
        alias: "johnny5",
        label: "IRIS Portrait (Royal-Blue Hair & Dimpled Smile)",
        ico_path: "/assets/icons/app_icon_iris_head.ico",
        png_path: "/assets/icons/app_icon_iris_head.png"
      },
      {
        id: "iris_eye",
        alias: "scanning",
        label: "IRIS Cyber-Optic Eye (Sapphire & Gold Reticle)",
        ico_path: "/assets/icons/app_icon_iris_eye.ico",
        png_path: "/assets/icons/app_icon_iris_eye.png"
      },
      {
        id: "iris_cyber_arm",
        alias: "shield",
        label: "Deus-Ex Cybernetic Arm Crest",
        ico_path: "/assets/icons/app_icon_iris_cyber_arm.ico",
        png_path: "/assets/icons/app_icon_iris_cyber_arm.png"
      },
      {
        id: "iris_holo",
        alias: "holo",
        label: "IRIS Tactical Holo-Visor",
        ico_path: "/assets/icons/app_icon_iris_holo.ico",
        png_path: "/assets/icons/app_icon_iris_holo.png"
      }
    ],
    expression_matrix: {
      nominal: {
        category: "Nominal & Sassy Operations",
        sheet_path: `${REPO_ROOT}/03_expressions/expressions_nominal_3degrees.png`,
        avatar_path: `${REPO_ROOT}/04_avatars/avatar_nominal_healthy.png`,
        degrees: [
          { degree: 1, id: "nominal_deg1_serene", path: `${REPO_ROOT}/03_expressions/nominal_deg1_serene.png`, label: "Degree 1 — Demure Standby", description: "Calm baseline monitoring with zero active anomalies." },
          { degree: 2, id: "nominal_deg2_focused", path: `${REPO_ROOT}/03_expressions/nominal_deg2_focused.png`, label: "Degree 2 — Sassy Focused Tracking", description: "Active token stream ingestion within sustainable quota pacing." },
          { degree: 3, id: "nominal_deg3_optimal", path: `${REPO_ROOT}/03_expressions/nominal_deg3_optimal.png`, label: "Degree 3 — Mischievous Dimpled Grin", description: "Prompt cache hit ratio >= 75% (Grade A+) and positive net savings." }
        ]
      },
      guidance: {
        category: "Analytical & Configuration Guidance",
        sheet_path: `${REPO_ROOT}/03_expressions/expressions_guidance_3degrees.png`,
        avatar_path: `${REPO_ROOT}/04_avatars/avatar_guidance_config.png`,
        degrees: [
          { degree: 1, id: "guidance_deg1_curious", path: `${REPO_ROOT}/03_expressions/guidance_deg1_curious.png`, label: "Degree 1 — Telemetry Scan", description: "Awaiting initial session stream or discovering local inference nodes." },
          { degree: 2, id: "guidance_deg2_advising", path: `${REPO_ROOT}/03_expressions/guidance_deg2_advising.png`, label: "Degree 2 — Configuration Advisor", description: "Guiding DPAPI credential encryption, proxy routing, or quota calibration." },
          { degree: 3, id: "guidance_deg3_eureka", path: `${REPO_ROOT}/03_expressions/guidance_deg3_eureka.png`, label: "Degree 3 — Strategic Insight", description: "Surfacing high-impact cost/latency optimization or benchmark leaderboard result." }
        ]
      },
      warning: {
        category: "Caution & Quota Pacing Drift",
        sheet_path: `${REPO_ROOT}/03_expressions/expressions_warning_3degrees.png`,
        avatar_path: `${REPO_ROOT}/04_avatars/avatar_warning_pacing.png`,
        degrees: [
          { degree: 1, id: "warning_deg1_concerned", path: `${REPO_ROOT}/03_expressions/warning_deg1_concerned.png`, label: "Degree 1 — Mild Pacing Drift", description: "Session quota below 50% or ephemeral prompt cache approaching 5-minute TTL." },
          { degree: 2, id: "warning_deg2_urgent", path: `${REPO_ROOT}/03_expressions/warning_deg2_urgent.png`, label: "Degree 2 — Elevated Burn Rate", description: "Rolling token velocity exceeds sustainable window pace (burst > 1.5x)." },
          { degree: 3, id: "warning_deg3_brace", path: `${REPO_ROOT}/03_expressions/warning_deg3_brace.png`, label: "Degree 3 — Imminent Exhaustion", description: "Projected quota exhaustion before window reset or severe 35:1 context bloat." }
        ]
      },
      critical: {
        category: "Critical Fault & Rate-Limit Defense",
        sheet_path: `${REPO_ROOT}/03_expressions/expressions_critical_3degrees.png`,
        avatar_path: `${REPO_ROOT}/04_avatars/avatar_critical_error.png`,
        degrees: [
          { degree: 1, id: "critical_deg1_retry", path: `${REPO_ROOT}/03_expressions/critical_deg1_retry.png`, label: "Degree 1 — Transient Upstream Fault", description: "Single upstream timeout or unreachable LAN inference node; retrying." },
          { degree: 2, id: "critical_deg2_ratelimit", path: `${REPO_ROOT}/03_expressions/critical_deg2_ratelimit.png`, label: "Degree 2 — HTTP 429 Quota Exhausted", description: "Upstream provider rate-limited; spillover to local Ollama recommended." },
          { degree: 3, id: "critical_deg3_overload", path: `${REPO_ROOT}/03_expressions/critical_deg3_overload.png`, label: "Degree 3 — Circuit Breaker Tripped", description: "Hard daily budget ceiling tripped or critical security/runtime exception." }
        ]
      }
    },
    contextual_avatars: {
      nominal: {
        id: "avatar_nominal_healthy",
        label: "All Systems Nominal (Dimpled Smile)",
        path: `${REPO_ROOT}/04_avatars/avatar_nominal_healthy.png`,
        hover_gif: `${REPO_ROOT}/05_animations/anim_idle_wink_smile.gif`,
        badge_text: "SYSTEM NOMINAL",
        accent_var: "var(--color-success)"
      },
      scanning: {
        id: "avatar_scanning_idle",
        label: "Scanning Telemetry Channels",
        path: `${REPO_ROOT}/04_avatars/avatar_scanning_idle.png`,
        hover_gif: `${REPO_ROOT}/05_animations/anim_loading_scan.gif`,
        badge_text: "SCANNING",
        accent_var: "var(--accent-primary)"
      },
      guidance: {
        id: "avatar_guidance_config",
        label: "Configuration & Security Advisor",
        path: `${REPO_ROOT}/04_avatars/avatar_guidance_config.png`,
        hover_gif: `${REPO_ROOT}/05_animations/anim_idle_wink_smile.gif`,
        badge_text: "GUIDANCE",
        accent_var: "var(--accent-primary)"
      },
      stats: {
        id: "avatar_stats_insights",
        label: "Telemetry & Efficiency Analyst",
        path: `${REPO_ROOT}/04_avatars/avatar_stats_insights.png`,
        hover_gif: `${REPO_ROOT}/05_animations/anim_busy_processing.gif`,
        badge_text: "ANALYTICS",
        accent_var: "var(--accent-primary)"
      },
      warning: {
        id: "avatar_warning_pacing",
        label: "Pacing & Context-Bloat Caution",
        path: `${REPO_ROOT}/04_avatars/avatar_warning_pacing.png`,
        hover_gif: `${REPO_ROOT}/05_animations/anim_alert_pulse.gif`,
        badge_text: "CAUTION",
        accent_var: "var(--color-warning)"
      },
      critical: {
        id: "avatar_critical_error",
        label: "Rate-Limit & Circuit-Breaker Alert",
        path: `${REPO_ROOT}/04_avatars/avatar_critical_error.png`,
        hover_gif: `${REPO_ROOT}/05_animations/anim_alert_pulse.gif`,
        badge_text: "ALERT",
        accent_var: "var(--color-danger)"
      }
    },
    operational_briefs: [
      {
        context: "nominal",
        status: "SYSTEM NOMINAL",
        text: "SQLite WAL telemetry pipeline and Windows DPAPI vault are operating normally. Cross-source deduplication is active across proxy and CLI log streams."
      },
      {
        context: "stats",
        status: "CACHE ANALYTICS",
        text: "Anthropic ephemeral prompt caches expire after 300 seconds of inactivity. Keeping iterative turns within the 5-minute TTL reduces input token costs by up to 90%."
      },
      {
        context: "guidance",
        status: "ROUTING TIP",
        text: "Point local IDE agents and CLIs to 127.0.0.1:8766/v1 for zero-latency SSE token accounting, budget circuit-breakers, and automatic Ollama spillover."
      },
      {
        context: "warning",
        status: "CONTEXT HYGIENE",
        text: "Sessions exceeding a 35:1 input-to-output token ratio indicate uncompacted history bloat. Trigger /compact or rotate sessions to preserve 5-hour quota windows."
      }
    ]
  };

  function resolveContextualAvatar(contextKey) {
    const key = String(contextKey || "nominal").toLowerCase();
    return MASCOT_MANIFEST.contextual_avatars[key] || MASCOT_MANIFEST.contextual_avatars.nominal;
  }

  function resolveAnimatedGif(triggerKey) {
    const key = String(triggerKey || "idle_wink").toLowerCase();
    if (key.includes("load") || key.includes("sync") || key.includes("scan")) {
      return MASCOT_MANIFEST.animations.loading_scan.path;
    }
    if (key.includes("busy") || key.includes("bench") || key.includes("calibrat")) {
      return MASCOT_MANIFEST.animations.busy_processing.path;
    }
    if (key.includes("alert") || key.includes("warn") || key.includes("crit") || key.includes("429")) {
      return MASCOT_MANIFEST.animations.alert_pulse.path;
    }
    return MASCOT_MANIFEST.animations.idle_wink.path;
  }

  function resolveExpressionSeverity(category, severityDegree) {
    const cat = MASCOT_MANIFEST.expression_matrix[String(category || "nominal").toLowerCase()] || MASCOT_MANIFEST.expression_matrix.nominal;
    const degNum = Math.max(1, Math.min(3, parseInt(severityDegree, 10) || 1));
    const degObj = cat.degrees.find(d => d.degree === degNum) || cat.degrees[0];
    return {
      category: cat.category,
      sheet_path: cat.sheet_path,
      avatar_path: cat.avatar_path,
      degree: degObj.degree,
      id: degObj.id,
      path: degObj.path,
      label: degObj.label,
      description: degObj.description
    };
  }

  const MascotRepository = {
    manifest: MASCOT_MANIFEST,
    resolveContextualAvatar,
    resolveAnimatedGif,
    resolveExpressionSeverity,
    getManifest() {
      return MASCOT_MANIFEST;
    }
  };

  global.AIUMCore = global.AIUMCore || {};
  global.AIUMCore.MascotRepository = MascotRepository;
  global.IRISMascot = MascotRepository;

  if (typeof module !== "undefined" && module.exports) {
    module.exports = MascotRepository;
  }
})(typeof window !== "undefined" ? window : globalThis);
