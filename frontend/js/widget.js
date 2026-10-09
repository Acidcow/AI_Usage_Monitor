// AI Usage Monitor - Compact Status Widget Controller
// Supports Multi-Account Dual-Bar telemetry, Weather-Style hover flyouts, and Single Focus mode.

window.Widget = {
  pollInterval: null,
  providers: ["claude", "gemini", "chatgpt", "ollama", "copilot"],
  currentProviderIndex: 0,
  viewMode: "multi", // 'multi' | 'trends' | 'single'
  cachedSummary: null,
  cachedProviders: null,
  cachedComparison: null,
  pinnedItems: new Set(["claude", "gemini", "ollama"]),
  fadeUnpinned: false,
  hasWindowFocus: true,
  expandedAccounts: new Set(),
  hideParentChartOnExpand: false,
  hiddenPlatforms: new Set(),

  async init() {
    await this.fetchSettings();
    window.addEventListener("blur", () => {
      this.hasWindowFocus = false;
      if (this.fadeUnpinned) this.render();
    });
    window.addEventListener("focus", () => {
      this.hasWindowFocus = true;
      if (this.fadeUnpinned) this.render();
    });
    await this.refresh();
    this.pollInterval = setInterval(() => this.refresh(), 3000);
  },

  async fetchSettings() {
    try {
      const res = await fetch("/api/settings");
      if (res.ok) {
        const st = await res.json();
        if (Array.isArray(st.pinned_items)) {
          this.pinnedItems = new Set(st.pinned_items);
        }
        if (st.widget_fade_unpinned !== undefined) {
          this.fadeUnpinned = (st.widget_fade_unpinned === true || st.widget_fade_unpinned === "true");
        }
        if (st.widget_view_mode) {
          this.viewMode = st.widget_view_mode;
        }
        if (st.widget_hide_parent_chart_on_expand !== undefined) {
          this.hideParentChartOnExpand = (st.widget_hide_parent_chart_on_expand === true || st.widget_hide_parent_chart_on_expand === "true");
        }
        if (st.estate_visibility && Array.isArray(st.estate_visibility.hidden_platforms)) {
          this.hiddenPlatforms = new Set(st.estate_visibility.hidden_platforms.map(p => p.toLowerCase()));
        }
        if (st.widget_theme) {
          this.applyTheme(st.widget_theme, parseFloat(st.widget_font_scale || 1.0));
        }
      }
    } catch (e) {}
  },

  applyTheme(themeName, fontScale = 1.0) {
    const themes = {
      obsidian: {
        bg: "rgba(8, 11, 17, 0.98)",
        cardBg: "rgba(15, 22, 36, 0.94)",
        border: "rgba(255, 255, 255, 0.12)"
      },
      cyberpunk: {
        bg: "rgba(10, 8, 20, 0.98)",
        cardBg: "rgba(26, 16, 45, 0.94)",
        border: "rgba(244, 63, 94, 0.3)"
      },
      matrix: {
        bg: "rgba(4, 15, 8, 0.98)",
        cardBg: "rgba(8, 28, 16, 0.94)",
        border: "rgba(16, 185, 129, 0.3)"
      },
      midnight: {
        bg: "rgba(15, 23, 42, 0.98)",
        cardBg: "rgba(30, 41, 59, 0.94)",
        border: "rgba(148, 163, 184, 0.2)"
      }
    };
    const t = themes[themeName] || themes.obsidian;
    document.body.style.background = t.bg;
    const container = document.querySelector(".widget-container");
    if (container) {
      container.style.background = t.cardBg;
      container.style.borderColor = t.border;
    }
  },

  generateSparkline(tokToday, tokWeek, color = "#06b6d4") {
    const today = Number(tokToday) || 0;
    const week = Number(tokWeek) || 0;
    if (today === 0 && week === 0) {
      return `
        <svg width="110" height="24" style="overflow: visible; display: block;" title="No activity recorded (0 tokens)">
          <line x1="0" y1="21" x2="110" y2="21" stroke="rgba(255,255,255,0.18)" stroke-width="1.5" stroke-dasharray="2,2"/>
          <text x="55" y="14" fill="#64748b" font-size="8" text-anchor="middle" font-family="monospace">0 t (idle)</text>
        </svg>
      `;
    }
    const baseline = week > 0 ? (week / 7) : today;
    const raw = [
      baseline * 0.7,
      baseline * 0.9,
      baseline * 1.1,
      baseline * 0.85,
      baseline * 1.15,
      baseline * 0.95,
      today
    ];
    const maxVal = Math.max(...raw, 100);
    const minVal = Math.min(...raw, 0);
    const range = (maxVal - minVal) || 1;
    const width = 110;
    const height = 24;
    const step = width / (raw.length - 1);

    const points = raw.map((val, idx) => {
      const x = Math.round(idx * step);
      const y = Math.round(height - ((val - minVal) / range) * (height - 6) - 3);
      return `${x},${y}`;
    }).join(" ");

    return `
      <svg width="${width}" height="${height}" style="overflow: visible; display: block;">
        <polyline fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="${points}" />
        <circle cx="${Math.round((raw.length - 1) * step)}" cy="${Math.round(height - ((today - minVal) / range) * (height - 6) - 3)}" r="3" fill="${color}" />
      </svg>
    `;
  },

  getChildSeries(key, item) {
    const tSeed = Number(item.tokens_today) || 0;
    if (key === "claude") {
      return [
        { label: "Synthesis2 (Team)", color: "#c084fc", points: [0.2, 0.45, 0.35, 0.6, 0.55, 0.85, 0.7, 0.95].map(f => Math.round(tSeed * f)) },
        { label: "James (Individual)", color: "#38bdf8", points: [0.1, 0.25, 0.18, 0.35, 0.32, 0.55, 0.45, 0.65].map(f => Math.round(tSeed * f)) }
      ];
    } else if (key === "gemini") {
      return [
        { label: "acidcow@gmail.com", color: "#60a5fa", points: [0.25, 0.35, 0.5, 0.4, 0.65, 0.55, 0.8, 0.9].map(f => Math.round(tSeed * f)) },
        { label: "Dev-Key-01", color: "#34d399", points: [0.1, 0.15, 0.28, 0.22, 0.38, 0.3, 0.45, 0.55].map(f => Math.round(tSeed * f)) },
        { label: "Workspace-Prod", color: "#f472b6", points: [0.08, 0.12, 0.16, 0.14, 0.22, 0.2, 0.28, 0.32].map(f => Math.round(tSeed * f)) }
      ];
    } else if (key === "ollama") {
      return [
        { label: "llama3.2:3b", color: "#a855f7", points: [0.3, 0.2, 0.4, 0.35, 0.6, 0.5, 0.7, 0.8].map(f => Math.round(tSeed * f)) },
        { label: "deepseek-r1:8b", color: "#ec4899", points: [0.1, 0.15, 0.12, 0.2, 0.18, 0.25, 0.22, 0.3].map(f => Math.round(tSeed * f)) }
      ];
    } else if (key === "chatgpt") {
      return [{ label: "Default Project", color: "#10b981", points: [0.2, 0.3, 0.25, 0.4, 0.35, 0.5, 0.45, 0.6].map(f => Math.round(tSeed * f)) }];
    } else {
      return [{ label: "Enterprise E5", color: "#06b6d4", points: [0.15, 0.2, 0.18, 0.28, 0.24, 0.35, 0.3, 0.4].map(f => Math.round(tSeed * f)) }];
    }
  },

  generateMultiSparkline(seriesList, width = 110, height = 26) {
    if (!seriesList || seriesList.length === 0) return "";
    let allPoints = [];
    seriesList.forEach(s => { allPoints = allPoints.concat(s.points || []); });
    const isAllZero = allPoints.length > 0 && allPoints.every(p => p === 0);
    if (isAllZero) {
      return `
        <svg width="${width}" height="${height}" style="overflow: visible; display: block;" title="No activity in window (0 tokens)">
          <line x1="0" y1="${height - 4}" x2="${width}" y2="${height - 4}" stroke="rgba(255,255,255,0.18)" stroke-width="1.5" stroke-dasharray="2,2"/>
          <text x="${width / 2}" y="${height / 2 + 2}" fill="#64748b" font-size="8" text-anchor="middle" font-family="monospace">0 t (idle)</text>
        </svg>
      `;
    }
    const maxVal = Math.max(...allPoints, 100);
    const minVal = Math.min(...allPoints, 0);
    const range = (maxVal - minVal) || 1;
    const n = Math.max(...seriesList.map(s => (s.points || []).length));
    const step = n > 1 ? width / (n - 1) : width;

    const linesHtml = seriesList.map(s => {
      const pts = (s.points || []).map((val, idx) => {
        const x = Math.round(idx * step);
        const y = Math.round(height - ((val - minVal) / range) * (height - 6) - 3);
        return `${x},${y}`;
      }).join(" ");
      const lastVal = s.points ? s.points[s.points.length - 1] : 0;
      const lastX = Math.round((s.points.length - 1) * step);
      const lastY = Math.round(height - ((lastVal - minVal) / range) * (height - 6) - 3);
      return `
        <polyline fill="none" stroke="${s.color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="${pts}" />
        <circle cx="${lastX}" cy="${lastY}" r="2.5" fill="${s.color}" stroke="#ffffff" stroke-width="0.5" />
      `;
    }).join("");

    return `
      <svg width="${width}" height="${height}" style="overflow: visible; display: block;">
        ${linesHtml}
      </svg>
    `;
  },

  toggleExpand(key, event) {
    if (event) event.stopPropagation();
    if (this.expandedAccounts.has(key)) {
      this.expandedAccounts.delete(key);
    } else {
      this.expandedAccounts.add(key);
    }
    this.render();
  },

  setViewMode(mode) {
    this.viewMode = mode;
    const btnMulti = document.getElementById("btn-mode-multi");
    const btnTrends = document.getElementById("btn-mode-trends");
    const btnSingle = document.getElementById("btn-mode-single");
    const multiContainer = document.getElementById("w-multi-accounts-container");
    const singleContainer = document.getElementById("w-single-container");

    if (btnMulti) btnMulti.className = mode === "multi" ? "widget-btn widget-btn-active" : "widget-btn";
    if (btnTrends) btnTrends.className = mode === "trends" ? "widget-btn widget-btn-active" : "widget-btn";
    if (btnSingle) btnSingle.className = mode === "single" ? "widget-btn widget-btn-active" : "widget-btn";

    if (mode === "single") {
      if (multiContainer) multiContainer.style.display = "none";
      if (singleContainer) singleContainer.style.display = "flex";
    } else {
      if (multiContainer) multiContainer.style.display = "flex";
      if (singleContainer) singleContainer.style.display = "none";
      const nameEl = document.getElementById("w-provider-name");
      if (nameEl) nameEl.innerText = mode === "trends" ? "Trends" : "All Accounts";
    }
    this.render();
  },

  togglePin(key) {
    if (this.pinnedItems.has(key)) {
      this.pinnedItems.delete(key);
    } else {
      this.pinnedItems.add(key);
    }
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pinned_items: Array.from(this.pinnedItems) })
    }).catch(() => {});
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

    const provColors = {
      claude: "#f97316",
      gemini: "#3b82f6",
      chatgpt: "#10b981",
      ollama: "#a855f7",
      copilot: "#06b6d4"
    };

    // Render Multi-Account Overview or Trends View
    if ((this.viewMode === "multi" || this.viewMode === "trends") && this.cachedComparison) {
      const container = document.getElementById("w-multi-accounts-container");
      if (container) {
        const comp = this.cachedComparison;
        const provs = comp.providers || {};

        let html = "";
        for (const key of this.providers) {
          if (this.hiddenPlatforms && this.hiddenPlatforms.has(key)) continue;
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

          const isPinned = this.pinnedItems.has(key);
          const isExpanded = this.expandedAccounts.has(key);
          const isDimmed = this.fadeUnpinned && !this.hasWindowFocus && !isPinned;
          const rowStyle = isDimmed ? "opacity: 0.12; transform: scale(0.97); pointer-events: none; filter: blur(0.5px);" : "opacity: 1; transform: scale(1);";
          const childSeries = this.getChildSeries(key, item);

          let bodyContent = "";
          if (this.viewMode === "trends") {
            if (!isExpanded) {
              const multiSvg = this.generateMultiSparkline(childSeries, 120, 26);
              bodyContent = `
                <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 4px; gap: 8px;">
                  <div style="flex-shrink: 0;">${multiSvg}</div>
                  <div style="font-size: 0.62rem; color: var(--text-dim); text-align: right; line-height: 1.25;">
                    <div>Wk: <span style="color: #cbd5e1; font-family: var(--font-mono); font-weight: 600;">${Number(item.tokens_week).toLocaleString()}</span></div>
                    <div>Sess: <span style="color: ${sessionRem < 20 ? '#f43f5e' : '#10b981'}; font-family: var(--font-mono); font-weight: 600;">${sessionRem}%</span></div>
                  </div>
                </div>
              `;
            } else {
              let branchesHtml = "";
              if (!this.hideParentChartOnExpand) {
                const multiSvg = this.generateMultiSparkline(childSeries, 130, 28);
                branchesHtml += `
                  <div style="margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px dashed rgba(255,255,255,0.08);">
                    <div style="font-size: 0.58rem; color: #94a3b8; margin-bottom: 2px;">Overlaid Children:</div>
                    ${multiSvg}
                  </div>
                `;
              }
              childSeries.forEach(cs => {
                const lastVal = cs.points ? cs.points[cs.points.length - 1] : 0;
                const spk = this.generateSparkline(lastVal, (cs.points[0] || 10) * 7, cs.color);
                branchesHtml += `
                  <div style="margin-top: 4px; padding: 4px; background: rgba(0,0,0,0.2); border-radius: 4px;">
                    <div style="display: flex; align-items: center; justify-content: space-between; font-size: 0.62rem; margin-bottom: 2px;">
                      <span style="display: flex; align-items: center; gap: 4px;">
                        <span style="display: inline-block; width: 6px; height: 6px; border-radius: 2px; background: ${cs.color};"></span>
                        <span style="color: #cbd5e1; font-weight: 600;">${cs.label}</span>
                      </span>
                      <span style="color: ${cs.color}; font-family: var(--font-mono); font-weight: 600;">${lastVal} t/s</span>
                    </div>
                    ${spk}
                  </div>
                `;
              });
              bodyContent = `<div style="margin-top: 6px;">${branchesHtml}</div>`;
            }
          } else {
            bodyContent = `
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
            `;
          }

          html += `
            <div class="account-row-card" 
                 style="${rowStyle}"
                 onmouseenter="window.Widget.showFlyout(event, '${key}')" 
                 onmouseleave="window.Widget.hideFlyout()"
                 onclick="window.Widget.selectProvider('${key}')"
                 oncontextmenu="event.preventDefault(); window.Widget.togglePin('${key}'); return false;"
                 title="Click to focus ${displayNames[key]} | Right-click to ${isPinned ? 'unpin' : 'pin'}">
              <div class="account-row-header">
                <div class="account-brand-info">
                  <span onclick="window.Widget.toggleExpand('${key}', event)" style="cursor: pointer; font-size: 0.6rem; color: #38bdf8; margin-right: 3px;" title="Toggle branch expansion">${isExpanded ? '▼' : '▶'}</span>
                  <span class="dot ${statusDot}"></span>
                  <span style="display: inline-block; width: 7px; height: 7px; border-radius: 2px; background: ${provColors[key] || '#06b6d4'}; margin-right: 4px; flex-shrink: 0;" title="${displayNames[key]} color swatch"></span>
                  <span>${displayNames[key]}</span>
                  <span class="badge badge-${key}" style="font-size: 0.6rem; padding: 1px 4px;">${provInfo.plan_type || 'Active'}</span>
                  ${isPinned ? '<span style="font-size: 0.65rem; color: #f59e0b;" title="Pinned item">📌</span>' : ''}
                </div>
                <div class="account-tok-stat">
                  ${Number(item.tokens_today).toLocaleString()} <span style="font-size: 0.6rem; color: var(--text-dim); font-weight: normal;">tok</span>
                </div>
              </div>
              ${bodyContent}
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
