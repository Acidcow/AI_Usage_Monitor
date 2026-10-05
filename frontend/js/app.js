// AI Usage Monitor - Client Application Controller (Vanilla ES6, Zero-Dependencies)

window.App = {
  activeTab: 'dashboard',
  pollInterval: null,
  isSimulationMode: false,

  async init() {
    console.log("[AI Usage Monitor] Initializing SPA Shell...");
    await Promise.all([
      this.loadComponent("container-header-status", "/components/header_status.html"),
      this.loadComponent("container-usage-gauges", "/components/usage_gauge_card.html"),
      this.loadComponent("container-session-timeline", "/components/session_timeline.html"),
      this.loadComponent("container-provider-hub", "/components/provider_hub.html"),
      this.loadComponent("container-troubleshooter", "/components/troubleshooter_panel.html")
    ]);

    this.setupEventListeners();
    await this.loadUsageData();

    // Start background auto-refresh every 4 seconds
    this.pollInterval = setInterval(() => this.loadUsageData(), 4000);
  },

  async loadComponent(containerId, url) {
    const el = document.getElementById(containerId);
    if (!el) return;
    try {
      const res = await fetch(url);
      if (res.ok) {
        el.innerHTML = await res.text();
      } else {
        console.error(`Failed to load component ${url}: ${res.status}`);
      }
    } catch (err) {
      console.error(`Network error loading ${url}:`, err);
    }
  },

  setupEventListeners() {
    document.querySelectorAll(".nav-tab").forEach(tab => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
        tab.classList.add("active");
        const target = tab.getAttribute("data-tab");
        const content = document.getElementById(`tab-${target}`);
        if (content) content.classList.add("active");
      });
    });

    document.addEventListener("change", (e) => {
      if (e.target && e.target.id === "filter-session-provider") {
        this.loadUsageData();
      }
    });
  },

  async loadUsageData() {
    try {
      const provSelect = document.getElementById("filter-session-provider");
      const providerParam = provSelect && provSelect.value ? `?provider=${provSelect.value}` : '';

      const [summaryRes, providersRes, sessionsRes, errorsRes, hourlyRes] = await Promise.all([
        fetch("/api/usage/summary"),
        fetch("/api/providers"),
        fetch(`/api/usage/sessions${providerParam}`),
        fetch("/api/diagnostics/errors?limit=30"),
        fetch("/api/usage/hourly?hours=24")
      ]);

      if (summaryRes.ok && providersRes.ok) {
        const summary = await summaryRes.json();
        const providers = await providersRes.json();
        this.renderGauges(summary, providers);
        this.renderPills(providers, summary);
      }

      if (sessionsRes.ok) {
        const sessions = await sessionsRes.json();
        this.renderSessions(sessions);
      }

      if (errorsRes.ok) {
        const errors = await errorsRes.json();
        this.renderErrors(errors);
      }

      if (hourlyRes.ok) {
        const hourly = await hourlyRes.json();
        this.renderSvgChart(hourly);
      }
    } catch (err) {
      console.warn("[App] Polling error:", err);
    }
  },

  renderGauges(summary, providers) {
    const totalTokEl = document.getElementById("val-total-tokens");
    if (totalTokEl) totalTokEl.innerText = Number(summary.total_tokens_today).toLocaleString();

    const breakdownEl = document.getElementById("val-tokens-breakdown");
    if (breakdownEl) {
      breakdownEl.innerText = `In: ${Number(summary.input_tokens_today).toLocaleString()} | Out: ${Number(summary.output_tokens_today).toLocaleString()}`;
    }

    const costEl = document.getElementById("val-total-cost");
    if (costEl) costEl.innerText = `$${Number(summary.estimated_cost_today_usd).toFixed(3)}`;

    const sessEl = document.getElementById("val-total-sessions");
    if (sessEl) sessEl.innerText = summary.total_sessions;

    const monthEl = document.getElementById("val-sessions-month");
    if (monthEl) monthEl.innerText = `Month total: ${Number(summary.total_tokens_month).toLocaleString()} tokens`;

    const fillTok = document.getElementById("fill-tokens-today");
    if (fillTok) {
      const pct = Math.min(100, (summary.total_tokens_today / 100000) * 100);
      fillTok.style.width = `${Math.max(4, pct)}%`;
    }

    // Claude specific quota & reset
    const claudeInfo = providers["claude"] || {};
    const claudeRemainingEl = document.getElementById("val-claude-remaining");
    const claudeResetEl = document.getElementById("val-claude-reset");
    const claudeFill = document.getElementById("fill-claude-quota");

    if (claudeRemainingEl && claudeInfo.tokens_remaining !== null) {
      claudeRemainingEl.innerText = Number(claudeInfo.tokens_remaining).toLocaleString();
      if (claudeFill) {
        const quotaPct = Math.min(100, (claudeInfo.tokens_remaining / 400000) * 100);
        claudeFill.style.width = `${quotaPct}%`;
      }
    }

    if (claudeResetEl && claudeInfo.reset_epoch) {
      const secondsLeft = Math.max(0, Math.floor(claudeInfo.reset_epoch - (Date.now() / 1000)));
      const mins = Math.floor(secondsLeft / 60);
      const secs = secondsLeft % 60;
      claudeResetEl.innerText = `Reset In: ${mins}m ${secs}s`;
    }
  },

  renderPills(providers, summary) {
    const claudePillTok = document.getElementById("claude-pill-tokens");
    if (claudePillTok) {
      claudePillTok.innerText = `${Number(summary.total_tokens_today).toLocaleString()} tok`;
    }

    const claudePlanBadge = document.getElementById("badge-claude-plan");
    if (claudePlanBadge && providers["claude"]) {
      claudePlanBadge.innerText = providers["claude"].plan_type || "Team Pro";
    }

    // Ollama dot
    const ollamaDot = document.getElementById("dot-ollama");
    const ollamaStatusText = document.getElementById("ollama-status-text");
    if (ollamaDot && providers["ollama"]) {
      const isOnline = providers["ollama"].status === "ACTIVE";
      ollamaDot.className = `dot ${isOnline ? 'dot-green' : 'dot-gray'}`;
      if (ollamaStatusText) ollamaStatusText.innerText = isOnline ? "Active" : "Offline";
    }

    // Data Mode pill
    const modeText = document.getElementById("text-data-mode");
    const modeDot = document.getElementById("dot-data-mode");
    if (modeText && modeDot) {
      if (this.isSimulationMode) {
        modeText.innerText = "DEMO SIMULATION";
        modeText.style.color = "var(--accent-amber)";
        modeDot.className = "dot dot-amber";
      } else {
        modeText.innerText = "LIVE LOCAL DATA";
        modeText.style.color = "var(--accent-cyan)";
        modeDot.className = "dot dot-green";
      }
    }
  },

  renderSvgChart(hourly) {
    const svg = document.getElementById("token-velocity-chart");
    const peakInfo = document.getElementById("chart-peak-info");
    if (!svg) return;

    if (!hourly || hourly.length === 0) {
      svg.innerHTML = `
        <text x="400" y="65" text-anchor="middle" fill="#64748b" font-size="14" font-family="sans-serif">
          No hourly tokens recorded yet in past 24 hours.
        </text>
      `;
      if (peakInfo) peakInfo.innerText = "Peak: 0 tokens/hr";
      return;
    }

    // Group by hour
    const hourMap = {};
    let maxTokens = 100;
    hourly.forEach(item => {
      const k = item.hour_key;
      hourMap[k] = (hourMap[k] || 0) + item.tokens;
      if (hourMap[k] > maxTokens) maxTokens = hourMap[k];
    });

    const entries = Object.entries(hourMap);
    if (peakInfo) peakInfo.innerText = `Peak: ${maxTokens.toLocaleString()} tokens/hr`;

    const width = 800;
    const height = 120;
    const padding = 20;
    const plotWidth = width - (padding * 2);
    const plotHeight = height - (padding * 2);

    const step = plotWidth / Math.max(1, entries.length);
    let barsHtml = "";

    entries.forEach(([hour, tok], idx) => {
      const barHeight = Math.max(4, (tok / maxTokens) * plotHeight);
      const x = padding + (idx * step);
      const y = height - padding - barHeight;
      const hourLabel = hour.substring(11, 13) + ":00";

      barsHtml += `
        <g class="chart-bar-group" style="cursor: pointer;">
          <title>${hourLabel} UTC: ${tok.toLocaleString()} tokens</title>
          <rect x="${x + 2}" y="${y}" width="${Math.max(6, step - 6)}" height="${barHeight}" rx="3" fill="url(#chart-grad)" opacity="0.85">
            <animate attributeName="opacity" from="0.4" to="0.85" dur="0.3s"/>
          </rect>
          <text x="${x + (step/2)}" y="${height - 4}" font-size="9" fill="#64748b" text-anchor="middle" font-family="sans-serif">${hourLabel}</text>
        </g>
      `;
    });

    svg.innerHTML = `
      <defs>
        <linearGradient id="chart-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#06b6d4" stop-opacity="1"/>
          <stop offset="100%" stop-color="#3b82f6" stop-opacity="0.3"/>
        </linearGradient>
      </defs>
      <!-- Base Axis -->
      <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
      ${barsHtml}
    `;
  },

  renderSessions(sessions) {
    const tbody = document.getElementById("sessions-table-body");
    if (!tbody) return;

    if (!sessions || sessions.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align: center; color: var(--text-dim); padding: 30px;">
            No sessions recorded yet.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = sessions.map(s => {
      const timeStr = s.last_activity ? s.last_activity.replace("T", " ").substring(0, 19) : "-";
      let provBadgeClass = "badge-claude";
      if (s.provider === "copilot") provBadgeClass = "badge-copilot";
      else if (s.provider === "gemini") provBadgeClass = "badge-gemini";
      else if (s.provider === "ollama") provBadgeClass = "badge-ollama";

      return `
        <tr>
          <td><code style="font-family: var(--font-mono); color: var(--accent-cyan); font-size: 0.8rem;">${this.escapeHtml(s.session_id)}</code></td>
          <td><span class="badge ${provBadgeClass}">${this.escapeHtml(s.provider)}</span></td>
          <td style="color: var(--text-muted); font-size: 0.82rem;">${this.escapeHtml(s.model || 'default')}</td>
          <td style="font-family: var(--font-mono);">${Number(s.input_tokens).toLocaleString()}</td>
          <td style="font-family: var(--font-mono);">${Number(s.output_tokens).toLocaleString()}</td>
          <td style="font-family: var(--font-mono); font-weight: 700; color: #fff;">${Number(s.total_tokens).toLocaleString()}</td>
          <td style="font-family: var(--font-mono); color: var(--accent-emerald);">$${Number(s.estimated_cost).toFixed(4)}</td>
          <td style="font-size: 0.78rem; color: var(--text-dim);">${timeStr}</td>
        </tr>
      `;
    }).join("");
  },

  renderErrors(errors) {
    const container = document.getElementById("error-log-container");
    if (!container) return;

    if (!errors || errors.length === 0) {
      container.innerHTML = `
        <div style="color: var(--text-dim); text-align: center; padding: 20px;">
          ✓ No unhandled errors or rate limit alerts recorded. System operational.
        </div>
      `;
      return;
    }

    container.innerHTML = errors.map(err => `
      <div class="error-item">
        <div class="meta">
          <span style="color: var(--accent-rose); font-weight: 700;">[${this.escapeHtml(err.category)}]</span>
          <span>${this.escapeHtml(err.provider).toUpperCase()}</span>
          <span>${err.timestamp ? err.timestamp.substring(11, 19) : ''}</span>
        </div>
        <div class="msg">${this.escapeHtml(err.message)}</div>
      </div>
    `).join("");
  },

  // Toggle Mode
  async toggleDataMode() {
    this.isSimulationMode = !this.isSimulationMode;
    try {
      await fetch("/api/providers/claude/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ simulation_mode: this.isSimulationMode })
      });
      await this.loadUsageData();
    } catch (e) {
      console.error(e);
    }
  },

  // Ollama Models Drawer
  async toggleOllamaModelsList() {
    const drawer = document.getElementById("ollama-models-drawer");
    const grid = document.getElementById("ollama-models-grid");
    if (!drawer) return;

    if (drawer.style.display === "block") {
      drawer.style.display = "none";
      return;
    }

    drawer.style.display = "block";
    grid.innerHTML = '<div style="color: var(--text-dim);">Scanning local Ollama models on port 11434...</div>';

    try {
      const res = await fetch("/api/providers/ollama/models");
      if (res.ok) {
        const data = await res.json();
        const models = data.installed || [];
        if (models.length === 0) {
          grid.innerHTML = '<div style="color: var(--text-dim);">No models currently loaded in Ollama.</div>';
          return;
        }

        grid.innerHTML = models.map(m => `
          <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 10px;">
            <div style="font-weight: 700; font-size: 0.82rem; color: #fff;">${this.escapeHtml(m.name)}</div>
            <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 4px;">
              Size: <span style="color: var(--accent-cyan); font-family: var(--font-mono);">${m.size}</span> | Param: ${m.parameter_size}
            </div>
            <div style="font-size: 0.7rem; color: var(--text-dim);">Quant: ${m.quantization}</div>
          </div>
        `).join("");
      }
    } catch (e) {
      grid.innerHTML = `<div style="color: var(--accent-rose);">Failed to reach Ollama: ${e}</div>`;
    }
  },

  // Modals & Configuration
  openConfigureClaudeModal() {
    const modal = document.getElementById("claude-config-modal");
    if (modal) modal.classList.add("active");
  },
  closeConfigureClaudeModal() {
    const modal = document.getElementById("claude-config-modal");
    if (modal) modal.classList.remove("active");
  },

  async saveClaudeConfig() {
    const keyInput = document.getElementById("claude-api-key-input");
    const simCheckbox = document.getElementById("claude-sim-checkbox");
    const apiKey = keyInput ? keyInput.value.trim() : "";
    const sim = simCheckbox ? simCheckbox.checked : false;

    try {
      const res = await fetch("/api/providers/claude/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey, simulation_mode: sim })
      });
      if (res.ok) {
        alert("Claude settings encrypted with Windows DPAPI and saved!");
        this.closeConfigureClaudeModal();
        if (keyInput) keyInput.value = "";
        await this.loadUsageData();
      }
    } catch (e) {
      alert(`Error saving configuration: ${e}`);
    }
  },

  openConfigureGeminiModal() {
    const modal = document.getElementById("gemini-config-modal");
    if (modal) modal.classList.add("active");
  },
  closeConfigureGeminiModal() {
    const modal = document.getElementById("gemini-config-modal");
    if (modal) modal.classList.remove("active");
  },

  async saveGeminiConfig() {
    const keyInput = document.getElementById("gemini-api-key-input");
    const apiKey = keyInput ? keyInput.value.trim() : "";
    if (!apiKey) return;

    try {
      const res = await fetch("/api/providers/claude/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey })
      });
      alert("Gemini key encrypted with DPAPI!");
      this.closeConfigureGeminiModal();
      await this.loadUsageData();
    } catch (e) {
      alert(`Error saving Gemini configuration: ${e}`);
    }
  },

  openImportModal(provider) {
    const modal = document.getElementById("telemetry-import-modal");
    const sel = document.getElementById("import-provider-select");
    if (sel && provider) sel.value = provider;
    if (modal) modal.classList.add("active");
  },
  closeImportModal() {
    const modal = document.getElementById("telemetry-import-modal");
    if (modal) modal.classList.remove("active");
  },

  async submitImport() {
    const sel = document.getElementById("import-provider-select");
    const txt = document.getElementById("import-raw-text");
    const raw = txt ? txt.value.trim() : "";
    const prov = sel ? sel.value : "copilot";

    if (!raw) {
      alert("Please paste telemetry content (JSON, JSONL, or CSV).");
      return;
    }

    try {
      const res = await fetch("/api/usage/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_content: raw, provider: prov })
      });
      if (res.ok) {
        const data = await res.json();
        alert(`Successfully imported ${data.imported_count} session records!`);
        this.closeImportModal();
        if (txt) txt.value = "";
        await this.loadUsageData();
      }
    } catch (e) {
      alert(`Import failed: ${e}`);
    }
  },

  openManualModal(provider) {
    const modal = document.getElementById("manual-session-modal");
    const provInput = document.getElementById("manual-provider");
    if (provInput && provider) provInput.value = provider;
    if (modal) modal.classList.add("active");
  },
  closeManualModal() {
    const modal = document.getElementById("manual-session-modal");
    if (modal) modal.classList.remove("active");
  },

  async submitManualSession() {
    const prov = document.getElementById("manual-provider").value;
    const model = document.getElementById("manual-model").value;
    const inTok = parseInt(document.getElementById("manual-input-tokens").value, 10) || 0;
    const outTok = parseInt(document.getElementById("manual-output-tokens").value, 10) || 0;

    try {
      const res = await fetch("/api/usage/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: prov, model, input_tokens: inTok, output_tokens: outTok })
      });
      if (res.ok) {
        this.closeManualModal();
        await this.loadUsageData();
      }
    } catch (e) {
      alert(`Manual recording failed: ${e}`);
    }
  },

  async syncProvider(provider) {
    try {
      await fetch("/api/providers/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider })
      });
      await this.loadUsageData();
    } catch (e) {
      console.error("Sync failed:", e);
    }
  },

  async copyDiagnosticBundle() {
    try {
      const res = await fetch("/api/diagnostics/export");
      if (res.ok) {
        const bundle = await res.json();
        const jsonText = JSON.stringify(bundle, null, 2);
        await navigator.clipboard.writeText(jsonText);
        alert("Sanitized diagnostic bundle copied to clipboard! Ready to paste into GitHub issues or chat.");
      }
    } catch (e) {
      alert(`Failed to copy diagnostics: ${e}`);
    }
  },

  async downloadDiagnosticBundle() {
    try {
      const res = await fetch("/api/diagnostics/export");
      if (res.ok) {
        const bundle = await res.json();
        const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `ai_usage_diagnostics_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e) {
      alert(`Download failed: ${e}`);
    }
  },

  async clearDiagnostics() {
    if (confirm("Clear in-memory diagnostic error history?")) {
      await fetch("/api/diagnostics/clear", { method: "POST" });
      await this.loadUsageData();
    }
  },

  escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
};

document.addEventListener("DOMContentLoaded", () => {
  window.App.init();
});
