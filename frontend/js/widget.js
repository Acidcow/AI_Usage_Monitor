// AI Usage Monitor - Compact Status Widget Controller
// Supports live polling, provider cycling, and standalone desktop window mode.

window.Widget = {
  pollInterval: null,
  providers: ["claude", "gemini", "chatgpt", "ollama", "copilot"],
  currentProviderIndex: 0,
  cachedSummary: null,
  cachedProviders: null,

  async init() {
    await this.refresh();
    this.pollInterval = setInterval(() => this.refresh(), 3000);
  },

  cycleProvider() {
    this.currentProviderIndex = (this.currentProviderIndex + 1) % this.providers.length;
    this.render();
  },

  async refresh() {
    try {
      const [sumRes, provRes] = await Promise.all([
        fetch("/api/usage/summary"),
        fetch("/api/providers")
      ]);

      if (sumRes.ok && provRes.ok) {
        this.cachedSummary = await sumRes.json();
        this.cachedProviders = await provRes.json();
        this.render();
      }
    } catch (e) {
      console.warn("Widget polling failed:", e);
    }
  },

  render() {
    if (!this.cachedSummary || !this.cachedProviders) return;

    const provKey = this.providers[this.currentProviderIndex];
    const provInfo = this.cachedProviders[provKey] || {};
    const sum = this.cachedSummary;

    // Display Name & Badge
    const nameEl = document.getElementById("w-provider-name");
    const planEl = document.getElementById("w-plan-badge");
    const dotEl = document.getElementById("w-status-dot");
    const labelEl = document.getElementById("w-tokens-lbl");

    const displayNames = {
      claude: "Claude",
      gemini: "Gemini",
      chatgpt: "ChatGPT",
      ollama: "Ollama",
      copilot: "Copilot"
    };

    if (nameEl) nameEl.innerText = displayNames[provKey] || provKey;
    if (labelEl) labelEl.innerText = `${(displayNames[provKey] || provKey).toUpperCase()} TOKENS TODAY`;

    // Status Dot Color
    const isOnline = provInfo.status === "ACTIVE";
    if (dotEl) {
      dotEl.className = `dot ${isOnline ? 'dot-green' : (provInfo.status === 'ERROR' ? 'dot-red' : 'dot-gray')}`;
    }

    // Plan Badge
    if (planEl) {
      planEl.className = `badge badge-${provKey}`;
      planEl.innerText = provInfo.plan_type || "Ready";
    }

    // Tokens Today & Sessions
    const todayTokens = provKey === "claude" ? sum.total_tokens_today : (provInfo.tokens_remaining ? 0 : 0);
    document.getElementById("w-tokens-today").innerText = Number(sum.total_tokens_today).toLocaleString();
    document.getElementById("w-session-count").innerText = sum.total_sessions;
    document.getElementById("w-cost-val").innerText = `$${Number(sum.estimated_cost_today_usd).toFixed(3)}`;

    // Quota Remaining
    const remEl = document.getElementById("w-tokens-remaining");
    const fill = document.getElementById("w-progress-fill");

    if (provInfo.tokens_remaining !== null && provInfo.tokens_remaining !== undefined) {
      if (remEl) remEl.innerText = Number(provInfo.tokens_remaining).toLocaleString();
      const pct = Math.min(100, (provInfo.tokens_remaining / 400000) * 100);
      if (fill) {
        fill.style.width = `${Math.max(5, pct)}%`;
        if (pct < 20) fill.classList.add("warning");
        else fill.classList.remove("warning");
      }
    } else {
      if (remEl) remEl.innerText = provInfo.status || "--";
      if (fill) fill.style.width = "50%";
    }

    // Reset countdown (Claude specific or provider reset)
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
