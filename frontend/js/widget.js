// AI Usage Monitor - Compact Status Widget Controller

window.Widget = {
  pollInterval: null,

  async init() {
    await this.refresh();
    this.pollInterval = setInterval(() => this.refresh(), 3000);
  },

  async refresh() {
    try {
      const [sumRes, provRes] = await Promise.all([
        fetch("/api/usage/summary"),
        fetch("/api/providers")
      ]);

      if (sumRes.ok && provRes.ok) {
        const sum = await sumRes.json();
        const provs = await provRes.json();

        // Update tokens today
        document.getElementById("w-tokens-today").innerText = Number(sum.total_tokens_today).toLocaleString();
        document.getElementById("w-session-count").innerText = sum.total_sessions;
        document.getElementById("w-cost-val").innerText = `$${Number(sum.estimated_cost_today_usd).toFixed(3)}`;

        // Claude specific
        const claude = provs["claude"] || {};
        if (claude.tokens_remaining !== null && claude.tokens_remaining !== undefined) {
          document.getElementById("w-tokens-remaining").innerText = Number(claude.tokens_remaining).toLocaleString();
          const pct = Math.min(100, (claude.tokens_remaining / 400000) * 100);
          const fill = document.getElementById("w-progress-fill");
          if (fill) {
            fill.style.width = `${pct}%`;
            if (pct < 20) {
              fill.classList.add("warning");
            } else {
              fill.classList.remove("warning");
            }
          }
        }

        if (claude.plan_type) {
          document.getElementById("w-plan-badge").innerText = claude.plan_type;
        }

        if (claude.reset_epoch) {
          const sec = Math.max(0, Math.floor(claude.reset_epoch - (Date.now() / 1000)));
          const m = Math.floor(sec / 60);
          const s = sec % 60;
          document.getElementById("w-reset-time").innerText = `${m}m ${s}s`;
        }
      }
    } catch (e) {
      console.warn("Widget polling failed:", e);
    }
  },

  async sync() {
    try {
      await fetch("/api/providers/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: "claude" })
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
