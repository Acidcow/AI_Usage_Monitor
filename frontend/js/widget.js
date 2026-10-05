// AI Usage Monitor - Compact Status Widget Controller
// Supports Multi-Account Dual-Bar telemetry, Weather-Style hover flyouts, and Single Focus mode.

window.Widget = {
  pollInterval: null,
  providers: ["claude", "gemini", "chatgpt", "ollama", "copilot"],
  currentProviderIndex: 0,
  viewMode: "multi", // 'multi' | 'single'
  cachedSummary: null,
  cachedProviders: null,
  cachedComparison: null,

  async init() {
    await this.refresh();
    this.pollInterval = setInterval(() => this.refresh(), 3000);
  },

  setViewMode(mode) {
    this.viewMode = mode;
    const btnMulti = document.getElementById("btn-mode-multi");
    const btnSingle = document.getElementById("btn-mode-single");
    const multiContainer = document.getElementById("w-multi-accounts-container");
    const singleContainer = document.getElementById("w-single-container");

    if (mode === "multi") {
      if (btnMulti) btnMulti.className = "widget-btn widget-btn-active";
      if (btnSingle) btnSingle.className = "widget-btn";
      if (multiContainer) multiContainer.style.display = "flex";
      if (singleContainer) singleContainer.style.display = "none";
      const nameEl = document.getElementById("w-provider-name");
      if (nameEl) nameEl.innerText = "All Accounts";
    } else {
      if (btnMulti) btnMulti.className = "widget-btn";
      if (btnSingle) btnSingle.className = "widget-btn widget-btn-active";
      if (multiContainer) multiContainer.style.display = "none";
      if (singleContainer) singleContainer.style.display = "flex";
    }
    this.render();
  },

  cycleProvider() {
    if (this.viewMode === "multi") {
      this.setViewMode("single");
    } else {
      this.currentProviderIndex = (this.currentProviderIndex + 1) % this.providers.length;
      this.render();
    }
  },

  async refresh() {
    try {
      const [sumRes, provRes, compRes] = await Promise.all([
        fetch("/api/usage/summary"),
        fetch("/api/providers"),
        fetch("/api/usage/comparison")
      ]);

      if (sumRes.ok && provRes.ok) {
        this.cachedSummary = await sumRes.json();
        this.cachedProviders = await provRes.json();
      }
      if (compRes.ok) {
        this.cachedComparison = await compRes.json();
      }
      this.render();
    } catch (e) {
      console.warn("Widget polling failed:", e);
    }
  },

  render() {
    if (!this.cachedSummary || !this.cachedProviders) return;

    const displayNames = {
      claude: "Claude",
      gemini: "Google Gemini",
      chatgpt: "ChatGPT",
      ollama: "Ollama (Local)",
      copilot: "M365 Copilot"
    };

    // Render Multi-Account Dual-Bar View
    if (this.viewMode === "multi" && this.cachedComparison) {
      const container = document.getElementById("w-multi-accounts-container");
      if (container) {
        const comp = this.cachedComparison;
        const provs = comp.providers || {};

        let html = "";
        for (const key of this.providers) {
          const item = provs[key] || {
            tokens_today: 0,
            tokens_week: 0,
            session_balance_remaining_pct: 100,
            weekly_balance_remaining_pct: 100,
            daily_allowance: 500000,
            weekly_allowance: 3500000
          };
          const provInfo = this.cachedProviders[key] || {};
          const isOnline = provInfo.status === "ACTIVE";
          const statusDot = isOnline ? "dot-green" : (provInfo.status === "ERROR" ? "dot-red" : "dot-gray");
          const sessionRem = item.session_balance_remaining_pct ?? 100;
          const weeklyRem = item.weekly_balance_remaining_pct ?? 100;

          html += `
            <div class="account-row-card" 
                 onmouseenter="window.Widget.showFlyout(event, '${key}')" 
                 onmouseleave="window.Widget.hideFlyout()"
                 onclick="window.Widget.selectProvider('${key}')"
                 title="Click to focus ${displayNames[key]}">
              <div class="account-row-header">
                <div class="account-brand-info">
                  <span class="dot ${statusDot}"></span>
                  <span>${displayNames[key]}</span>
                  <span class="badge badge-${key}" style="font-size: 0.6rem; padding: 1px 4px;">${provInfo.plan_type || 'Active'}</span>
                </div>
                <div class="account-tok-stat">
                  ${Number(item.tokens_today).toLocaleString()} <span style="font-size: 0.6rem; color: var(--text-dim); font-weight: normal;">tok</span>
                </div>
              </div>
              <div class="dual-bars-box">
                <div class="bar-item">
                  <span class="bar-tag">Session:</span>
                  <div class="bar-track">
                    <div class="bar-fill-session" style="width: ${Math.max(3, sessionRem)}%; ${sessionRem < 20 ? 'background: #f43f5e;' : ''}"></div>
                  </div>
                  <span class="bar-pct">${sessionRem}%</span>
                </div>
                <div class="bar-item">
                  <span class="bar-tag">Weekly:</span>
                  <div class="bar-track">
                    <div class="bar-fill-week" style="width: ${Math.max(3, weeklyRem)}%; ${weeklyRem < 20 ? 'background: #f59e0b;' : ''}"></div>
                  </div>
                  <span class="bar-pct">${weeklyRem}%</span>
                </div>
              </div>
            </div>
          `;
        }
        container.innerHTML = html;
      }

      // Update Local Savings Strip
      const savingsValEl = document.getElementById("w-savings-val");
      if (savingsValEl && this.cachedComparison.local_savings) {
        const saved = this.cachedComparison.local_savings.savings_today_usd || 0;
        savingsValEl.innerText = `$${saved.toFixed(2)}`;
      }
    }

    // Render Single Focus View
    const provKey = this.providers[this.currentProviderIndex];
    const provInfo = this.cachedProviders[provKey] || {};
    const sum = this.cachedSummary;

    const nameEl = document.getElementById("w-provider-name");
    const planEl = document.getElementById("w-plan-badge");
    const dotEl = document.getElementById("w-status-dot");
    const labelEl = document.getElementById("w-tokens-lbl");

    if (this.viewMode === "single") {
      if (nameEl) nameEl.innerText = displayNames[provKey] || provKey;
      if (labelEl) labelEl.innerText = `${(displayNames[provKey] || provKey).toUpperCase()} TOKENS TODAY`;
      const isOnline = provInfo.status === "ACTIVE";
      if (dotEl) {
        dotEl.className = `dot ${isOnline ? 'dot-green' : (provInfo.status === 'ERROR' ? 'dot-red' : 'dot-gray')}`;
      }
      if (planEl) {
        planEl.className = `badge badge-${provKey}`;
        planEl.innerText = provInfo.plan_type || "Ready";
      }
    }

    // Single view metrics
    const provComp = this.cachedComparison?.providers?.[provKey];
    const tokToday = provComp ? provComp.tokens_today : (provKey === "claude" ? sum.total_tokens_today : 0);
    const costToday = provComp ? provComp.cost_today_usd : sum.estimated_cost_today_usd;

    const tokTodayEl = document.getElementById("w-tokens-today");
    if (tokTodayEl) tokTodayEl.innerText = Number(tokToday).toLocaleString();

    const sessCountEl = document.getElementById("w-session-count");
    if (sessCountEl) sessCountEl.innerText = provComp?.sessions_count || sum.total_sessions;

    const costValEl = document.getElementById("w-cost-val");
    if (costValEl) costValEl.innerText = `$${Number(costToday).toFixed(3)}`;

    // Quota Remaining bar
    const remEl = document.getElementById("w-tokens-remaining");
    const fill = document.getElementById("w-progress-fill");

    if (provComp) {
      const pct = provComp.session_balance_remaining_pct;
      if (remEl) remEl.innerText = `${pct}% Bal`;
      if (fill) {
        fill.style.width = `${Math.max(5, pct)}%`;
        if (pct < 20) fill.style.background = "var(--accent-rose)";
        else fill.style.background = "var(--accent-cyan)";
      }
    } else if (provInfo.tokens_remaining !== null && provInfo.tokens_remaining !== undefined) {
      if (remEl) remEl.innerText = Number(provInfo.tokens_remaining).toLocaleString();
      const pct = Math.min(100, (provInfo.tokens_remaining / 400000) * 100);
      if (fill) {
        fill.style.width = `${Math.max(5, pct)}%`;
        if (pct < 20) fill.style.background = "var(--accent-rose)";
        else fill.style.background = "var(--accent-cyan)";
      }
    }

    // Reset countdown
    const resetEl = document.getElementById("w-reset-time");
    if (provInfo.reset_epoch) {
      const sec = Math.max(0, Math.floor(provInfo.reset_epoch - (Date.now() / 1000)));
      const m = Math.floor(sec / 60);
      const s = sec % 60;
      if (resetEl) resetEl.innerText = `${m}m ${s}s`;
    } else {
      if (resetEl) resetEl.innerText = "--";
    }
  },

  selectProvider(provKey) {
    const idx = this.providers.indexOf(provKey);
    if (idx !== -1) {
      this.currentProviderIndex = idx;
      this.setViewMode("single");
    }
  },

  showFlyout(e, provKey) {
    const flyout = document.getElementById("w-hover-flyout");
    if (!flyout || !this.cachedComparison) return;

    const comp = this.cachedComparison.providers?.[provKey] || {};
    const provInfo = this.cachedProviders?.[provKey] || {};

    const nameMap = {
      claude: "Claude (Anthropic)",
      gemini: "Google Gemini",
      chatgpt: "ChatGPT / OpenAI",
      ollama: "Ollama Local Engine",
      copilot: "M365 Copilot"
    };

    const titleEl = document.getElementById("flyout-provider-name");
    const badgeEl = document.getElementById("flyout-badge");
    const todayTokEl = document.getElementById("flyout-tokens-today");
    const weekTokEl = document.getElementById("flyout-tokens-week");
    const sessRemEl = document.getElementById("flyout-session-rem");
    const weekRemEl = document.getElementById("flyout-weekly-rem");

    if (titleEl) titleEl.innerText = nameMap[provKey] || provKey;
    if (badgeEl) {
      badgeEl.className = `badge badge-${provKey}`;
      badgeEl.innerText = provInfo.plan_type || "Active";
    }

    if (todayTokEl) todayTokEl.innerText = Number(comp.tokens_today || 0).toLocaleString();
    if (weekTokEl) weekTokEl.innerText = Number(comp.tokens_week || 0).toLocaleString();

    const sessRem = comp.session_balance_remaining_pct ?? 100;
    const weekRem = comp.weekly_balance_remaining_pct ?? 100;

    if (sessRemEl) sessRemEl.innerText = `${sessRem}% remaining`;
    if (weekRemEl) weekRemEl.innerText = `${weekRem}% remaining`;

    flyout.style.display = "block";
  },

  hideFlyout() {
    const flyout = document.getElementById("w-hover-flyout");
    if (flyout) flyout.style.display = "none";
  },

  async sync() {
    const provKey = this.providers[this.currentProviderIndex];
    try {
      await fetch("/api/providers/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: provKey })
      });
      await this.refresh();
    } catch (e) {
      console.error(e);
    }
  }
};

document.addEventListener("DOMContentLoaded", () => {
  window.Widget.init();
});
