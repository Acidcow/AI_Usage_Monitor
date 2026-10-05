// AI Usage Monitor - Client Application Controller (Vanilla ES6, Zero-Dependencies)

window.App = {
  activeTab: 'dashboard',
  pollInterval: null,

  async init() {
    console.log("[AI Usage Monitor] Initializing SPA Shell...");
    // Load canonical components dynamically (KloGnist Universal Component Loader Pattern)
    await Promise.all([
      this.loadComponent("container-header-status", "/components/header_status.html"),
      this.loadComponent("container-usage-gauges", "/components/usage_gauge_card.html"),
      this.loadComponent("container-session-timeline", "/components/session_timeline.html"),
      this.loadComponent("container-provider-hub", "/components/provider_hub.html"),
      this.loadComponent("container-troubleshooter", "/components/troubleshooter_panel.html")
    ]);

    this.setupEventListeners();
    await this.loadUsageData();

    // Start background auto-refresh every 5 seconds
    this.pollInterval = setInterval(() => this.loadUsageData(), 5000);
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
    // Tab switching
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

    // Session filter change
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

      const [summaryRes, providersRes, sessionsRes, errorsRes] = await Promise.all([
        fetch("/api/usage/summary"),
        fetch("/api/providers"),
        fetch(`/api/usage/sessions${providerParam}`),
        fetch("/api/diagnostics/errors?limit=30")
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

    // Progress bar for today's tokens (capped visually at 100k for progress scaling)
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
        if (quotaPct < 25) {
          claudeFill.classList.add("warning");
        } else {
          claudeFill.classList.remove("warning");
        }
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
      claudePlanBadge.innerText = providers["claude"].plan_type || "Pro";
    }

    const ollamaDot = document.getElementById("dot-ollama");
    const ollamaStatusText = document.getElementById("ollama-status-text");
    if (ollamaDot && providers["ollama"]) {
      const isOnline = providers["ollama"].status === "ACTIVE";
      ollamaDot.className = `dot ${isOnline ? 'dot-green' : 'dot-gray'}`;
      if (ollamaStatusText) ollamaStatusText.innerText = isOnline ? "Active" : "Offline";
    }
  },

  renderSessions(sessions) {
    const tbody = document.getElementById("sessions-table-body");
    if (!tbody) return;

    if (!sessions || sessions.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align: center; color: var(--text-dim); padding: 30px;">
            No sessions recorded yet. Start interacting or click "Simulate Usage (Demo)".
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = sessions.map(s => {
      const timeStr = s.last_activity ? s.last_activity.replace("T", " ").substring(0, 19) : "-";
      const provBadgeClass = s.provider === "claude" ? "badge-claude" : (s.provider === "copilot" ? "badge-copilot" : "badge-pro");
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
          ✓ No unhandled errors or rate limit alerts recorded. System fully operational.
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

  // Modal & Configuration
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

  async triggerClaudeSimulation() {
    try {
      const res = await fetch("/api/providers/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: "claude" })
      });
      if (res.ok) {
        await this.loadUsageData();
      }
    } catch (e) {
      console.error("Simulation trigger failed:", e);
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

  // Diagnostics & Export
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

// Start application when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  window.App.init();
});
