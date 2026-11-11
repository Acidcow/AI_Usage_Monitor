/**
 * IRIS (Intelligent Resource & Inference Sentinel) - Canonical Mascot & Asset Repository (v3.0)
 * Style: 1995 LucasArts "The Dig" High-Resolution Pixel Art
 * Provides structured access to:
 *  - 00_base_reference (Canonical digital skin-suit turnaround & concept sheet)
 *  - 01_poses (4 operational postures)
 *  - 02_outfits (4 modular outfit overlays)
 *  - 03_expressions (4 emotion/situation spectra x 3 severity degrees = 12 expression states)
 *  - 04_avatars (6 contextual 1:1 UI avatars for error messages, guidance, configurations, stats, and scanning)
 */
(function (global) {
  "use strict";

  const REPO_ROOT = "/assets/iris_mascot";

  const MASCOT_MANIFEST = {
    schema_version: "3.0.0",
    character_id: "iris_sentinel_v3",
    character_name: "IRIS",
    character_title: "Intelligent Resource & Inference Sentinel",
    art_style: "LucasArts 'The Dig' High-Res Pixel Art",
    base_references: [
      {
        id: "base_skinsuit_turnaround",
        label: "Master Canonical Turnaround (Digital Skin-Suit)",
        path: `${REPO_ROOT}/00_base_reference/iris_base_skinsuit_turnaround.png`,
        role: "Primary canonical anatomy, proportion, and pixel-palette anchor"
      },
      {
        id: "user_reference_concept",
        label: "Source Concept Turnaround Sheet",
        path: `${REPO_ROOT}/00_base_reference/user_reference_concept.jpg`,
        role: "Original line-art, front tactical, and rear turnaround reference"
      }
    ],
    poses: [
      {
        id: "pose_neutral_standing",
        label: "Neutral Sentinel Stance",
        path: `${REPO_ROOT}/01_poses/pose_neutral_standing.png`,
        context: "Nominal monitoring posture"
      },
      {
        id: "pose_analytical_console",
        label: "Analytical Console Inspection",
        path: `${REPO_ROOT}/01_poses/pose_analytical_console.png`,
        context: "Inspecting token velocity curves & prompt cache ROI"
      },
      {
        id: "pose_alert_defensive",
        label: "Tactical Rate-Limit Defense",
        path: `${REPO_ROOT}/01_poses/pose_alert_defensive.png`,
        context: "Quota exhaustion shielding & circuit-breaker intervention"
      },
      {
        id: "pose_diagnostic_repair",
        label: "Diagnostic Node Calibration",
        path: `${REPO_ROOT}/01_poses/pose_diagnostic_repair.png`,
        context: "Local daemon discovery, proxy bridge & DPAPI calibration"
      }
    ],
    outfits: [
      {
        id: "outfit_digital_skinsuit",
        label: "Digital Telemetry Skin-Suit (Base)",
        path: `${REPO_ROOT}/02_outfits/outfit_digital_skinsuit.png`,
        badge: "Base Layer"
      },
      {
        id: "outfit_field_tactical",
        label: "Field Tactical Utility Rig",
        path: `${REPO_ROOT}/02_outfits/outfit_field_tactical.png`,
        badge: "Tactical"
      },
      {
        id: "outfit_lab_chief_coat",
        label: "Chief Telemetry Scientist Coat",
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
    expression_matrix: {
      nominal: {
        category: "Nominal & Optimal Operations",
        sheet_path: `${REPO_ROOT}/03_expressions/expressions_nominal_3degrees.png`,
        avatar_path: `${REPO_ROOT}/04_avatars/avatar_nominal_healthy.png`,
        degrees: [
          { degree: 1, id: "nominal_deg1_serene", label: "Degree 1 — Serene Standby", description: "Calm baseline monitoring with zero active anomalies." },
          { degree: 2, id: "nominal_deg2_focused", label: "Degree 2 — Focused Tracking", description: "Active token stream ingestion within sustainable quota pacing." },
          { degree: 3, id: "nominal_deg3_optimal", label: "Degree 3 — Optimal Efficiency", description: "Prompt cache hit ratio >= 75% (Grade A+) and positive net savings." }
        ]
      },
      guidance: {
        category: "Analytical & Configuration Guidance",
        sheet_path: `${REPO_ROOT}/03_expressions/expressions_guidance_3degrees.png`,
        avatar_path: `${REPO_ROOT}/04_avatars/avatar_guidance_config.png`,
        degrees: [
          { degree: 1, id: "guidance_deg1_curious", label: "Degree 1 — Inquiring Scan", description: "Awaiting initial session traffic or scanning LAN endpoints." },
          { degree: 2, id: "guidance_deg2_advising", label: "Degree 2 — Configuration Advisor", description: "Guiding proxy port routing, OAuth calibration, or DPAPI key storage." },
          { degree: 3, id: "guidance_deg3_eureka", label: "Degree 3 — Optimization Insight", description: "Actionable cost-saving or model spillover opportunity identified." }
        ]
      },
      warning: {
        category: "Caution & Quota Pacing Drift",
        sheet_path: `${REPO_ROOT}/03_expressions/expressions_warning_3degrees.png`,
        avatar_path: `${REPO_ROOT}/04_avatars/avatar_warning_pacing.png`,
        degrees: [
          { degree: 1, id: "warning_deg1_concerned", label: "Degree 1 — Mild Pacing Drift", description: "Ephemeral 300s prompt cache cooling or quota below 50%." },
          { degree: 2, id: "warning_deg2_urgent", label: "Degree 2 — Elevated Burn Rate", description: "Burn velocity exceeds sustainable window reset trajectory." },
          { degree: 3, id: "warning_deg3_brace", label: "Degree 3 — Imminent Exhaustion / Bloat", description: "Projected exhaustion before reset or >35:1 quadratic context bloat." }
        ]
      },
      critical: {
        category: "Critical Faults & Rate-Limit Defense",
        sheet_path: `${REPO_ROOT}/03_expressions/expressions_critical_3degrees.png`,
        avatar_path: `${REPO_ROOT}/04_avatars/avatar_critical_error.png`,
        degrees: [
          { degree: 1, id: "critical_deg1_retry", label: "Degree 1 — Upstream Timeout", description: "Transient connection timeout or unreachable local inference node." },
          { degree: 2, id: "critical_deg2_ratelimit", label: "Degree 2 — HTTP 429 Rate Limit", description: "Upstream provider token quota exhausted; fallback recommended." },
          { degree: 3, id: "critical_deg3_overload", label: "Degree 3 — Circuit Breaker Tripped", description: "Daily budget guardrail engaged or automatic spillover active." }
        ]
      }
    },
    contextual_avatars: {
      nominal: {
        id: "avatar_nominal_healthy",
        label: "Nominal / All Systems Healthy",
        path: `${REPO_ROOT}/04_avatars/avatar_nominal_healthy.png`,
        badge_text: "NOMINAL",
        accent_var: "var(--color-success)"
      },
      scanning: {
        id: "avatar_scanning_idle",
        label: "Scanning Telemetry Channels",
        path: `${REPO_ROOT}/04_avatars/avatar_scanning_idle.png`,
        badge_text: "SCANNING",
        accent_var: "var(--accent-primary)"
      },
      guidance: {
        id: "avatar_guidance_config",
        label: "Configuration & Security Advisor",
        path: `${REPO_ROOT}/04_avatars/avatar_guidance_config.png`,
        badge_text: "GUIDANCE",
        accent_var: "var(--accent-primary)"
      },
      stats: {
        id: "avatar_stats_insights",
        label: "Telemetry & Efficiency Analyst",
        path: `${REPO_ROOT}/04_avatars/avatar_stats_insights.png`,
        badge_text: "ANALYTICS",
        accent_var: "var(--accent-primary)"
      },
      warning: {
        id: "avatar_warning_pacing",
        label: "Pacing & Context-Bloat Caution",
        path: `${REPO_ROOT}/04_avatars/avatar_warning_pacing.png`,
        badge_text: "CAUTION",
        accent_var: "var(--color-warning)"
      },
      critical: {
        id: "avatar_critical_error",
        label: "Rate-Limit & Circuit-Breaker Alert",
        path: `${REPO_ROOT}/04_avatars/avatar_critical_error.png`,
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
      label: degObj.label,
      description: degObj.description
    };
  }

  const MascotRepository = {
    manifest: MASCOT_MANIFEST,
    resolveContextualAvatar,
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
