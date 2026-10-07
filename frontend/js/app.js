// AI Usage Monitor - Client Application Controller (Vanilla ES6, Zero-Dependencies)

window.App = {
  activeTab: 'dashboard',
  pollInterval: null,
  isSimulationMode: false,
  activeIcon: 'johnny5',
  currentQuoteIdx: 0,
  currentScope: 'individual',
  expandedHierarchy: {},
  lastCompData: null,
  mascotQuotes: [
    "\"Number 5 is alive! No disassemble! Tracking your token telemetry and locking your API keys inside Windows DPAPI with 256-bit encryption. Input! Need more input!\"",
    "\"Hey, laser lips, your API keys are protected by hardware DPAPI! Plaintext credential storage is strictly prohibited!\"",
    "\"Stephanie! Look at this token velocity graph! Beautiful telemetry! Millions of tokens counted!\"",
    "\"Zero malfunctions detected! CLI Transparent Proxy listening on port 8766. All neural pathways nominal!\"",
    "\"Programmed to protect! Route your terminal and IDE tools through http://127.0.0.1:8766/v1 to capture tokens with zero latency!\"",
    "\"Input! More input! Local Ollama models detected and ready for offline inference!\""
  ],

  async init() {
    console.log("[AI Usage Monitor] Initializing SPA Shell...");
    const savedIcon = localStorage.getItem("aium_active_icon") || 'johnny5';
    this.applyActiveIcon(savedIcon);

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

  switchScope(newScope) {
    this.currentScope = newScope;
    const btnInd = document.getElementById("scope-btn-individual");
    const btnTeam = document.getElementById("scope-btn-team");
    const btnEnt = document.getElementById("scope-btn-enterprise");
    const indText = document.getElementById("active-scope-indicator");

    if (btnInd) {
      btnInd.className = newScope === "individual" ? "btn btn-sm btn-primary" : "btn btn-sm btn-secondary";
    }
    if (btnTeam) {
      btnTeam.className = newScope === "team" ? "btn btn-sm btn-primary" : "btn btn-sm btn-secondary";
    }
    if (btnEnt) {
      btnEnt.className = newScope === "enterprise" ? "btn btn-sm btn-primary" : "btn btn-sm btn-secondary";
    }

    if (indText) {
      if (newScope === "individual") {
        indText.innerText = "Focused on Personal / Individual Limits (claude.ai/settings/usage)";
      } else if (newScope === "team") {
        indText.innerText = "Focused on Shared Team Workspace Pool";
      } else {
        indText.innerText = "Focused on Organization / Enterprise Rollup";
      }
    }

    this.loadUsageData();
  },

  toggleHierarchy(providerKey) {
    this.expandedHierarchy[providerKey] = !this.expandedHierarchy[providerKey];
    if (this.lastCompData) {
      this.renderComparison(this.lastCompData, window._lastProviders || {});
    } else {
      this.loadUsageData();
    }
  },

  async loadUsageData() {
    try {
      const provSelect = document.getElementById("filter-session-provider");
      const providerParam = provSelect && provSelect.value ? `?provider=${provSelect.value}` : '';

      const [summaryRes, providersRes, sessionsRes, errorsRes, hourlyRes, compRes] = await Promise.all([
        fetch("/api/usage/summary"),
        fetch("/api/providers"),
        fetch(`/api/usage/sessions${providerParam}`),
        fetch("/api/diagnostics/errors?limit=30"),
        fetch("/api/usage/hourly?hours=24"),
        fetch(`/api/usage/comparison?scope=${this.currentScope || 'individual'}`)
      ]);

      let compData = null;
      if (compRes.ok) {
        compData = await compRes.json();
        this.lastCompData = compData;
      }

      if (summaryRes.ok && providersRes.ok) {
        const summary = await summaryRes.json();
        const providers = await providersRes.json();
        window._lastProviders = providers;
        this.renderGauges(summary, providers);
        this.renderPills(providers, summary);
        if (compData) {
          this.renderComparison(compData, providers);
        }
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
    const claudeBadge = document.getElementById("claude-quota-badge");

    if (claudeBadge) {
      claudeBadge.innerText = this.currentScope === 'team' ? 'Team Pool' : 'Personal Quota';
    }

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
      const scopeLabel = this.currentScope === 'team' ? 'Team Pool' : 'Session';
      claudeResetEl.innerText = `${scopeLabel} Reset In: ${mins}m ${secs}s`;
    }
  },

  renderComparison(comp, providers) {
    if (!comp) return;

    // 1. Local AI ROI Savings
    if (comp.local_savings) {
      const ls = comp.local_savings;
      const savTodayEl = document.getElementById("val-savings-today");
      const savTotalEl = document.getElementById("val-savings-total");
      const savTokEl = document.getElementById("val-savings-tokens");

      if (savTodayEl) savTodayEl.innerText = `$${Number(ls.savings_today_usd || 0).toFixed(2)}`;
      if (savTotalEl) savTotalEl.innerText = `$${Number(ls.savings_total_usd || 0).toFixed(2)}`;
      if (savTokEl) savTokEl.innerText = `${Number(ls.local_tokens_today || 0).toLocaleString()} tok`;
    }

    // 2. Comparative Accounts Breakdown Table
    const tbody = document.getElementById("comparison-table-body");
    if (!tbody) return;

    const allKeys = ["claude", "gemini", "chatgpt", "ollama", "copilot"];
    const displayNames = {
      claude: "Claude (Anthropic)",
      gemini: "Google Gemini",
      chatgpt: "ChatGPT / OpenAI",
      ollama: "Ollama (Local Engine)",
      copilot: "M365 Copilot"
    };

    const provMap = comp.providers || {};
    let html = "";

    allKeys.forEach(key => {
      const item = provMap[key] || {
        tokens_today: 0,
        share_percentage: 0,
        session_balance_remaining_pct: 100,
        weekly_balance_remaining_pct: 100,
        cost_today_usd: 0,
        daily_allowance: 500000,
        weekly_allowance: 3500000
      };
      const provInfo = providers[key] || {};
      const isOnline = provInfo.status === "ACTIVE";
      const dotClass = isOnline ? "dot-green" : (provInfo.status === "ERROR" ? "dot-red" : "dot-gray");
      const statusText = isOnline ? "Active" : (provInfo.status || "Ready");

      const sessionPct = item.session_balance_remaining_pct ?? 100;
      const weeklyPct = item.weekly_balance_remaining_pct ?? 100;
      const costDisplay = key === "ollama" ? `<span style="color: #34d399; font-weight: 700;">$0.000 (Free)</span>` : `$${Number(item.cost_today_usd || 0).toFixed(3)}`;

      const isExpanded = !!this.expandedHierarchy[key];
      const hasHierarchy = !!item.hierarchy;

      html += `
        <tr>
          <td>
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="dot ${dotClass}"></span>
                <strong style="color: #fff; font-size: 0.9rem;">${displayNames[key]}</strong>
              </div>
              ${hasHierarchy ? `
                <button class="btn btn-sm" onclick="window.App.toggleHierarchy('${key}')" style="background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); color: #38bdf8; font-size: 0.68rem; padding: 2px 7px; border-radius: 4px; cursor: pointer;" title="Toggle multi-level hierarchy drill-down">
                  ${isExpanded ? '▲ Hide' : '▼ Drill-Down'}
                </button>
              ` : ''}
            </div>
          </td>
          <td>
            <span class="badge badge-${key}" style="font-size: 0.7rem;">${provInfo.plan_type || 'Active'}</span>
            <span style="font-size: 0.72rem; color: var(--text-dim); margin-left: 4px;">${statusText}</span>
          </td>
          <td style="font-family: var(--font-mono); font-weight: 700; color: var(--text-main);">
            ${Number(item.tokens_today).toLocaleString()}
          </td>
          <td style="font-family: var(--font-mono); color: var(--accent-cyan); font-weight: 600;">
            ${item.share_percentage}%
          </td>
          <td>
            <div style="display: flex; align-items: center; gap: 8px;">
              <div class="progress-bar-container" style="flex-grow: 1; height: 6px; margin: 0; background: rgba(255,255,255,0.06);">
                <div class="progress-bar-fill" style="width: ${Math.max(4, sessionPct)}%; background: ${sessionPct < 20 ? 'var(--accent-rose)' : 'linear-gradient(90deg, #10b981, #06b6d4)'};"></div>
              </div>
              <span style="font-family: var(--font-mono); font-size: 0.75rem; width: 42px; text-align: right; color: #cbd5e1; font-weight: 600;">${sessionPct}%</span>
            </div>
          </td>
          <td>
            <div style="display: flex; align-items: center; gap: 8px;">
              <div class="progress-bar-container" style="flex-grow: 1; height: 6px; margin: 0; background: rgba(255,255,255,0.06);">
                <div class="progress-bar-fill" style="width: ${Math.max(4, weeklyPct)}%; background: ${weeklyPct < 20 ? 'var(--accent-amber)' : 'linear-gradient(90deg, #8b5cf6, #3b82f6)'};"></div>
              </div>
              <span style="font-family: var(--font-mono); font-size: 0.75rem; width: 42px; text-align: right; color: #cbd5e1; font-weight: 600;">${weeklyPct}%</span>
            </div>
          </td>
          <td style="font-family: var(--font-mono); font-size: 0.82rem;">
            ${costDisplay}
          </td>
        </tr>
      `;

      if (hasHierarchy && isExpanded) {
        const h = item.hierarchy;
        const ind = h.individual || {};
        const team = h.team || {};
        const dept = h.department || {};
        const ent = h.enterprise || {};

        html += `
          <tr class="hierarchy-detail-row" style="background: rgba(15, 23, 42, 0.75); border-left: 3px solid #38bdf8;">
            <td colspan="7" style="padding: 14px 18px;">
              <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
                <span style="font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: #94a3b8;">
                  Hierarchical Quota Drill-Down (${displayNames[key]}):
                </span>
                <span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-size: 0.68rem;">Active View: ${(comp.active_scope || 'individual').toUpperCase()}</span>
              </div>
              <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px;">
                <!-- 1. Individual Member (You) -->
                <div style="background: rgba(56, 189, 248, 0.06); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 10px 12px;">
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <strong style="color: #38bdf8; font-size: 0.82rem;">👤 Individual Member (You)</strong>
                    <span style="font-size: 0.68rem; color: var(--text-dim);">${h.user_name || 'Personal Seat'}</span>
                  </div>
                  <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                    <strong>Session:</strong> <span style="color: #38bdf8; font-weight: 700;">${ind.session_remaining_pct}% remaining</span> (${ind.session_used_pct}% used)
                  </div>
                  <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                    <strong>Weekly:</strong> <span style="color: #38bdf8; font-weight: 700;">${ind.weekly_remaining_pct}% remaining</span> (${ind.weekly_used_pct}% used)
                  </div>
                  <div style="font-size: 0.69rem; color: var(--text-dim); margin-top: 5px;">
                    Resets: ${ind.weekly_reset_str || 'Mon 3:00 AM'}
                  </div>
                </div>

                <!-- 2. Team Workspace Pool -->
                <div style="background: rgba(168, 85, 247, 0.06); border: 1px solid rgba(168, 85, 247, 0.25); border-radius: 8px; padding: 10px 12px;">
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <strong style="color: #c084fc; font-size: 0.82rem;">👥 Team Workspace Pool</strong>
                    <span style="font-size: 0.68rem; color: var(--text-dim);">${h.team_name || 'Core Engineering'}</span>
                  </div>
                  <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                    <strong>Team Session:</strong> <span style="color: #c084fc; font-weight: 700;">${team.session_remaining_pct}% remaining</span> (${team.session_used_pct}% used)
                  </div>
                  <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                    <strong>Team Weekly:</strong> <span style="color: #c084fc; font-weight: 700;">${team.weekly_remaining_pct}% remaining</span> (${team.weekly_used_pct}% used)
                  </div>
                  <div style="font-size: 0.69rem; color: var(--text-dim); margin-top: 5px;">
                    Resets: ${team.weekly_reset_str || 'Mon 3:00 AM'}
                  </div>
                </div>

                <!-- 3. Department Division -->
                <div style="background: rgba(16, 185, 129, 0.06); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 8px; padding: 10px 12px;">
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <strong style="color: #34d399; font-size: 0.82rem;">🏢 Department / Division</strong>
                    <span style="font-size: 0.68rem; color: var(--text-dim);">${dept.active_seats || 14} active seats</span>
                  </div>
                  <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                    <strong>Division:</strong> ${dept.dept_name || 'Technology & AI'}
                  </div>
                  <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                    <strong>Monthly Volume:</strong> ${Number(dept.monthly_tokens || 0).toLocaleString()} tok
                  </div>
                  <div style="font-size: 0.69rem; color: var(--text-dim); margin-top: 5px;">
                    Dept Budget: $${Number(dept.budget_limit_usd || 1500).toFixed(2)}
                  </div>
                </div>

                <!-- 4. Enterprise Organization -->
                <div style="background: rgba(245, 158, 11, 0.06); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 8px; padding: 10px 12px;">
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <strong style="color: #fbbf24; font-size: 0.82rem;">🌐 Organization / Enterprise</strong>
                    <span style="font-size: 0.68rem; color: var(--text-dim);">${ent.plan_type || 'Enterprise'}</span>
                  </div>
                  <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                    <strong>Org Name:</strong> ${ent.org_name || 'Enterprise Workspace'}
                  </div>
                  <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                    <strong>Pool Sync:</strong> <span style="color: #34d399; font-weight: 600;">Active & Synced</span>
                  </div>
                  <div style="font-size: 0.69rem; color: var(--text-dim); margin-top: 5px;">
                    Centralized Token Telemetry
                  </div>
                </div>
              </div>
            </td>
          </tr>
        `;
      }
    });

    tbody.innerHTML = html;
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
    const hubClaudeStatus = document.getElementById("hub-claude-status");
    if (hubClaudeStatus && providers["claude"]) {
      hubClaudeStatus.innerText = providers["claude"].status || "Active";
    }

    // Gemini dot & Hub status
    const geminiDot = document.getElementById("dot-gemini");
    const geminiStatusText = document.getElementById("gemini-status-text");
    const hubGeminiStatus = document.getElementById("hub-gemini-status");
    if (providers["gemini"]) {
      const gActive = providers["gemini"].status === "ACTIVE";
      if (geminiDot) geminiDot.className = `dot ${gActive ? 'dot-green' : 'dot-gray'}`;
      if (geminiStatusText) geminiStatusText.innerText = gActive ? "Active" : "Ready";
      if (hubGeminiStatus) {
        hubGeminiStatus.innerText = providers["gemini"].status || "Ready";
        hubGeminiStatus.style.color = gActive ? "#34d399" : "#60a5fa";
      }
    }

    // ChatGPT Hub status
    const hubChatgptStatus = document.getElementById("hub-chatgpt-status");
    if (hubChatgptStatus && providers["chatgpt"]) {
      const cActive = providers["chatgpt"].status === "ACTIVE";
      hubChatgptStatus.innerText = providers["chatgpt"].status || "Ready";
      hubChatgptStatus.style.color = cActive ? "#34d399" : "#60a5fa";
    }

    // Ollama dot & Hub status
    const ollamaDot = document.getElementById("dot-ollama");
    const ollamaStatusText = document.getElementById("ollama-status-text");
    const hubOllamaBadge = document.getElementById("hub-ollama-badge");
    if (providers["ollama"]) {
      const isOnline = providers["ollama"].status === "ACTIVE";
      if (ollamaDot) ollamaDot.className = `dot ${isOnline ? 'dot-green' : 'dot-gray'}`;
      if (ollamaStatusText) ollamaStatusText.innerText = isOnline ? "Active" : "Offline";
      if (hubOllamaBadge) {
        hubOllamaBadge.innerText = isOnline ? "Active" : "Offline";
        hubOllamaBadge.style.color = isOnline ? "#34d399" : "var(--text-dim)";
      }
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

    const platforms = ["claude", "gemini", "chatgpt", "ollama", "copilot"];
    const platformColors = {
      claude: "#f59e0b",
      gemini: "#3b82f6",
      chatgpt: "#10a37f",
      ollama: "#8b5cf6",
      copilot: "#0284c7",
      total: "#06b6d4"
    };
    const platformNames = {
      claude: "Claude",
      gemini: "Google Gemini",
      chatgpt: "ChatGPT",
      ollama: "Ollama (Local)",
      copilot: "M365 Copilot",
      total: "Total Combined"
    };

    if (!hourly || hourly.length === 0) {
      svg.innerHTML = `
        <text x="450" y="95" text-anchor="middle" fill="#64748b" font-size="13" font-family="sans-serif">
          No hourly tokens recorded yet in past 24 hours. Interacting with AI models will plot real-time multi-platform velocity curves here.
        </text>
      `;
      if (peakInfo) peakInfo.innerText = "Peak: 0 tokens/hr";
      return;
    }

    // Build timeline of distinct hour keys
    const hourMap = {};
    const allHoursSet = new Set();
    let maxTokens = 50;

    hourly.forEach(item => {
      const h = item.hour_key;
      const prov = (item.provider || "claude").toLowerCase();
      allHoursSet.add(h);

      if (!hourMap[h]) {
        hourMap[h] = { total: 0 };
        platforms.forEach(p => hourMap[h][p] = 0);
      }
      const tok = Number(item.tokens || 0);
      hourMap[h][prov] = (hourMap[h][prov] || 0) + tok;
      hourMap[h].total += tok;

      if (hourMap[h].total > maxTokens) maxTokens = hourMap[h].total;
    });

    const sortedHours = Array.from(allHoursSet).sort();
    if (peakInfo) peakInfo.innerText = `Peak: ${maxTokens.toLocaleString()} tokens/hr`;

    // SVG ViewBox dimensions: 900 x 200
    const width = 900;
    const height = 200;
    const padL = 60;
    const padR = 25;
    const padT = 20;
    const padB = 30;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;

    const numPoints = sortedHours.length;
    const step = numPoints > 1 ? plotW / (numPoints - 1) : plotW;

    // Grid lines (3 levels: 0%, 50%, 100%)
    let gridHtml = "";
    [0, 0.5, 1.0].forEach(ratio => {
      const y = padT + (plotH * (1.0 - ratio));
      const val = Math.round(maxTokens * ratio);
      gridHtml += `
        <line x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" stroke="rgba(255,255,255,0.07)" stroke-width="1" stroke-dasharray="4,4"/>
        <text x="${padL - 8}" y="${y + 4}" fill="#64748b" font-size="9" text-anchor="end" font-family="monospace">${val >= 1000 ? (val/1000).toFixed(0)+'k' : val}</text>
      `;
    });

    // Time axis labels along the bottom
    let axisHtml = "";
    sortedHours.forEach((hourStr, idx) => {
      const x = padL + (idx * step);
      const label = hourStr.substring(11, 13) + ":00";
      // Show every label if <= 12 hours, otherwise every 2nd or 3rd
      const showLabel = numPoints <= 12 || idx % Math.ceil(numPoints / 8) === 0 || idx === numPoints - 1;
      if (showLabel) {
        axisHtml += `
          <line x1="${x}" y1="${padT + plotH}" x2="${x}" y2="${padT + plotH + 4}" stroke="rgba(255,255,255,0.2)" stroke-width="1"/>
          <text x="${x}" y="${height - 8}" font-size="9" fill="#94a3b8" text-anchor="middle" font-family="monospace">${label}</text>
        `;
      }
    });

    // Generate Path Data for each platform & total
    const seriesToRender = [...platforms, "total"];
    let linesHtml = "";
    let dotsHtml = "";

    seriesToRender.forEach(seriesKey => {
      const color = platformColors[seriesKey];
      const isTotal = seriesKey === "total";
      const points = [];

      sortedHours.forEach((hourStr, idx) => {
        const tok = hourMap[hourStr][seriesKey] || 0;
        const x = numPoints > 1 ? (padL + (idx * step)) : (padL + plotW / 2);
        const y = padT + plotH - ((tok / maxTokens) * plotH);
        points.push({ x, y, tok, hour: hourStr.substring(11, 13) + ":00" });
      });

      // Only draw if there's non-zero data or if it's total
      const hasData = points.some(p => p.tok > 0);
      if (!hasData && !isTotal) return;

      let d = "";
      points.forEach((pt, idx) => {
        d += (idx === 0 ? `M ${pt.x} ${pt.y}` : ` L ${pt.x} ${pt.y}`);
      });

      const strokeDash = isTotal ? 'stroke-dasharray="6,4"' : '';
      const strokeWidth = isTotal ? '2' : '2.5';
      const opacity = isTotal ? '0.6' : '0.9';

      linesHtml += `
        <path class="chart-line-path" data-series="${seriesKey}" d="${d}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" ${strokeDash} opacity="${opacity}" stroke-linecap="round" stroke-linejoin="round" style="transition: all 0.2s ease;">
          <title>${platformNames[seriesKey]} Trend</title>
        </path>
      `;

      // Dots on active points
      points.forEach(pt => {
        if (pt.tok > 0) {
          dotsHtml += `
            <circle class="chart-dot" data-series="${seriesKey}" cx="${pt.x}" cy="${pt.y}" r="${isTotal ? 3 : 4}" fill="${color}" stroke="#0b0f19" stroke-width="1.5" style="cursor: pointer;">
              <title>${platformNames[seriesKey]}: ${pt.tok.toLocaleString()} tokens at ${pt.hour} UTC</title>
            </circle>
          `;
        }
      });
    });

    svg.innerHTML = `
      <!-- Base Axes -->
      <line x1="${padL}" y1="${padT + plotH}" x2="${width - padR}" y2="${padT + plotH}" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
      ${gridHtml}
      ${axisHtml}
      ${linesHtml}
      ${dotsHtml}
    `;

    // Setup interactive legend click filtering
    this._setupChartLegendInteractivity();
  },

  _setupChartLegendInteractivity() {
    const legendPills = document.querySelectorAll(".chart-legend-pill");
    legendPills.forEach(pill => {
      pill.onclick = () => {
        const plat = pill.getAttribute("data-platform");
        const allPaths = document.querySelectorAll(".chart-line-path");
        const allDots = document.querySelectorAll(".chart-dot");
        const isAlreadyIsolated = pill.classList.contains("isolated");

        legendPills.forEach(p => p.classList.remove("isolated"));

        if (isAlreadyIsolated) {
          // Restore all
          allPaths.forEach(p => { p.style.opacity = p.getAttribute("data-series") === "total" ? "0.6" : "0.9"; p.style.strokeWidth = "2.5"; });
          allDots.forEach(d => d.style.opacity = "1");
        } else {
          // Isolate clicked platform
          pill.classList.add("isolated");
          allPaths.forEach(p => {
            const match = p.getAttribute("data-series") === plat;
            p.style.opacity = match ? "1" : "0.15";
            p.style.strokeWidth = match ? "4" : "1.5";
          });
          allDots.forEach(d => {
            const match = d.getAttribute("data-series") === plat;
            d.style.opacity = match ? "1" : "0.1";
          });
        }
      };
    });
  },

  renderSessions(sessions) {
    const tbody = document.getElementById("sessions-table-body");
    if (!tbody) return;

    if (!sessions || sessions.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align: center; color: var(--text-dim); padding: 32px 20px;">
            <div style="display: flex; flex-direction: column; align-items: center; gap: 10px;">
              <img src="/assets/mascot/johnny5_inspecting.jpg" alt="Johnny 5 Inspecting" style="width: 76px; height: 76px; border-radius: 14px; border: 2px solid rgba(6, 182, 212, 0.4); box-shadow: 0 0 18px rgba(6, 182, 212, 0.3); object-fit: cover;">
              <div style="color: var(--text-main); font-weight: 700; font-size: 0.95rem;">Johnny 5 is scanning for token traffic...</div>
              <div style="color: var(--text-dim); font-size: 0.8rem; max-width: 440px;">
                Route your agentic IDE, CLI, or API calls through <code style="color: var(--accent-cyan); font-family: var(--font-mono);">http://127.0.0.1:8766/v1</code> or import telemetry logs to populate sessions.
              </div>
            </div>
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
        <div class="mascot-success-card">
          <img src="/assets/mascot/johnny5_success.jpg" alt="Johnny 5 Success" class="mascot-thumb-img">
          <div>
            <h4 style="color: var(--accent-emerald); font-weight: 700; margin-bottom: 6px; font-size: 1.05rem;">
              ✓ Zero Malfunctions Detected!
            </h4>
            <p style="color: var(--text-muted); font-size: 0.85rem; line-height: 1.45;">
              Johnny 5 reports all API routes, token proxy connections, and DPAPI encrypted vaults are operating at 100% capacity with zero rate limits.
            </p>
            <div style="display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap;">
              <span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.3);">Proxy Port: 8766 OK</span>
              <span class="badge" style="background: rgba(6, 182, 212, 0.2); color: #67e8f9; border: 1px solid rgba(6, 182, 212, 0.3);">DPAPI Vault: Active</span>
              <span class="badge" style="background: rgba(139, 92, 246, 0.2); color: #c4b5fd; border: 1px solid rgba(139, 92, 246, 0.3);">Telemetry: Flowing</span>
            </div>
          </div>
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

  // Claude Quota & Limit Calibration
  openClaudeQuotaModal() {
    const modal = document.getElementById("claude-quota-modal");
    if (modal) {
      if (this.lastCompData && this.lastCompData.providers && this.lastCompData.providers.claude) {
        const c = this.lastCompData.providers.claude;
        const h = c.hierarchy || {};
        const ind = h.individual || {};
        const team = h.team || {};

        const scopeSelect = document.getElementById("claude-quota-scope-select");
        if (scopeSelect && h.scope) scopeSelect.value = h.scope;

        const indSess = document.getElementById("claude-quota-ind-session-used");
        if (indSess && ind.session_used_pct !== undefined) indSess.value = ind.session_used_pct;

        const indWeek = document.getElementById("claude-quota-ind-weekly-used");
        if (indWeek && ind.weekly_used_pct !== undefined) indWeek.value = ind.weekly_used_pct;

        const teamSess = document.getElementById("claude-quota-team-session-used");
        if (teamSess && team.session_used_pct !== undefined) teamSess.value = team.session_used_pct;

        const teamWeek = document.getElementById("claude-quota-team-weekly-used");
        if (teamWeek && team.weekly_used_pct !== undefined) teamWeek.value = team.weekly_used_pct;

        const weekReset = document.getElementById("claude-quota-weekly-reset-str");
        if (weekReset && ind.weekly_reset_str) weekReset.value = ind.weekly_reset_str;
      }
      modal.classList.add("active");
    }
  },
  closeClaudeQuotaModal() {
    const modal = document.getElementById("claude-quota-modal");
    if (modal) modal.classList.remove("active");
  },
  async saveClaudeQuotaCalibration() {
    const scopeSelect = document.getElementById("claude-quota-scope-select");
    const planSelect = document.getElementById("claude-quota-plan");
    const indSessUsedInput = document.getElementById("claude-quota-ind-session-used");
    const indWeekUsedInput = document.getElementById("claude-quota-ind-weekly-used");
    const teamSessUsedInput = document.getElementById("claude-quota-team-session-used");
    const teamWeekUsedInput = document.getElementById("claude-quota-team-weekly-used");
    const sessMinsInput = document.getElementById("claude-quota-session-reset-mins");
    const weekResetInput = document.getElementById("claude-quota-weekly-reset-str");

    const scope = scopeSelect ? scopeSelect.value : "individual";
    const planType = planSelect ? planSelect.value : "Team Enterprise";
    const indSessUsed = indSessUsedInput ? parseFloat(indSessUsedInput.value) : 60.0;
    const indWeekUsed = indWeekUsedInput ? parseFloat(indWeekUsedInput.value) : 27.0;
    const teamSessUsed = teamSessUsedInput ? parseFloat(teamSessUsedInput.value) : 56.0;
    const teamWeekUsed = teamWeekUsedInput ? parseFloat(teamWeekUsedInput.value) : 26.0;
    const sessMins = sessMinsInput ? parseFloat(sessMinsInput.value) : 126.0;
    const weekReset = weekResetInput ? weekResetInput.value.trim() : "Mon 3:00 AM";

    try {
      const res = await fetch("/api/providers/claude/quota", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope: scope,
          plan_type: planType,
          individual_session_used_pct: indSessUsed,
          individual_weekly_used_pct: indWeekUsed,
          team_session_used_pct: teamSessUsed,
          team_weekly_used_pct: teamWeekUsed,
          session_reset_minutes: sessMins,
          weekly_reset_str: weekReset
        })
      });
      if (res.ok) {
        this.currentScope = scope;
        this.switchScope(scope);
        alert(`✓ Claude limits successfully calibrated!\n• Active View: ${scope.toUpperCase()}\n• 👤 Individual Member: ${100 - indSessUsed}% remaining (${indSessUsed}% used) / Weekly: ${100 - indWeekUsed}% rem (${indWeekUsed}% used)\n• 👥 Team Pool: ${100 - teamSessUsed}% remaining (${teamSessUsed}% used) / Weekly: ${100 - teamWeekUsed}% rem (${teamWeekUsed}% used)\n• Resets: ${weekReset}`);
        this.closeClaudeQuotaModal();
        await this.loadUsageData();
      } else {
        const err = await res.json();
        alert(`Failed to calibrate Claude limits: ${err.error || res.statusText}`);
      }
    } catch (e) {
      alert(`Error calibrating Claude quota: ${e}`);
    }
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

  // Clipboard paste helper
  async pasteFromClipboard(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    try {
      if (navigator.clipboard && navigator.clipboard.readText) {
        const text = await navigator.clipboard.readText();
        if (text) {
          input.value = text.trim();
          input.focus();
        }
      } else {
        alert("Clipboard access not available. Please press Ctrl+V directly to paste your key.");
      }
    } catch (e) {
      alert("Could not access clipboard directly. Please press Ctrl+V to paste your key.");
    }
  },

  // Open external URL helper
  openExternalUrl(url) {
    if (!url) return;
    window.open(url, "_blank", "noopener,noreferrer");
    try {
      fetch("/api/system/open-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      }).catch(() => {});
    } catch (e) {}
  },

  // Launch Desktop Floating Widget
  async launchDesktopWidget() {
    try {
      const res = await fetch("/api/widget/launch", { method: "POST" });
      if (!res.ok) {
        window.open("/mini_widget.html", "_blank", "width=380,height=220,menubar=no,toolbar=no,location=no,status=no");
      }
    } catch (e) {
      window.open("/mini_widget.html", "_blank", "width=380,height=220,menubar=no,toolbar=no,location=no,status=no");
    }
  },

  // Gemini Configuration
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
    const projInput = document.getElementById("gemini-project-id-input");
    const apiKey = keyInput ? keyInput.value.trim() : "";
    const projectId = projInput ? projInput.value.trim() : "";
    if (!apiKey) {
      alert("Please enter a Google Gemini API key (or multiple keys separated by commas for aggregated tracking).");
      return;
    }

    try {
      const res = await fetch("/api/providers/gemini/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey, project_id: projectId })
      });
      if (res.ok) {
        alert("✓ Google Gemini configuration securely encrypted with Windows DPAPI!");
        this.closeConfigureGeminiModal();
        if (keyInput) keyInput.value = "";
        await this.loadUsageData();
      } else {
        const err = await res.json();
        alert(`Failed to save Gemini key: ${err.error || res.statusText}`);
      }
    } catch (e) {
      alert(`Error saving Gemini configuration: ${e}`);
    }
  },

  // ChatGPT / OpenAI Configuration
  openConfigureChatGPTModal() {
    const modal = document.getElementById("chatgpt-config-modal");
    if (modal) modal.classList.add("active");
  },
  closeConfigureChatGPTModal() {
    const modal = document.getElementById("chatgpt-config-modal");
    if (modal) modal.classList.remove("active");
  },

  async saveChatGPTConfig() {
    const keyInput = document.getElementById("chatgpt-api-key-input");
    const apiKey = keyInput ? keyInput.value.trim() : "";
    if (!apiKey) {
      alert("Please enter an OpenAI API key (or click 'Get OpenAI Key' to procure one on OpenAI Platform).");
      return;
    }

    try {
      const res = await fetch("/api/providers/chatgpt/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey })
      });
      if (res.ok) {
        alert("✓ OpenAI / ChatGPT API key securely encrypted with Windows DPAPI!");
        this.closeConfigureChatGPTModal();
        if (keyInput) keyInput.value = "";
        await this.loadUsageData();
      } else {
        const err = await res.json();
        alert(`Failed to save OpenAI key: ${err.error || res.statusText}`);
      }
    } catch (e) {
      alert(`Error saving ChatGPT configuration: ${e}`);
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

  // =========================================================================
  // Icon and Mascot Management
  // =========================================================================
  applyActiveIcon(iconName) {
    this.activeIcon = iconName;
    try {
      localStorage.setItem("aium_active_icon", iconName);
    } catch (_) {}

    const logoImg = document.getElementById("brand-logo-img");
    const favicon = document.getElementById("app-favicon");
    const iconSrc = iconName === 'shield' 
      ? '/assets/icons/app_icon_shield.jpg' 
      : '/assets/icons/app_icon_johnny5.jpg';

    if (logoImg) logoImg.src = iconSrc;
    if (favicon) favicon.href = iconSrc;

    // Update modal cards
    const cardJohnny5 = document.getElementById("card-choice-johnny5");
    const cardShield = document.getElementById("card-choice-shield");
    const badgeJohnny5 = document.getElementById("badge-choice-johnny5");
    const badgeShield = document.getElementById("badge-choice-shield");

    if (cardJohnny5 && cardShield) {
      if (iconName === 'shield') {
        cardShield.classList.add("selected");
        cardJohnny5.classList.remove("selected");
        if (badgeShield) badgeShield.style.display = "block";
        if (badgeJohnny5) badgeJohnny5.style.display = "none";
      } else {
        cardJohnny5.classList.add("selected");
        cardShield.classList.remove("selected");
        if (badgeJohnny5) badgeJohnny5.style.display = "block";
        if (badgeShield) badgeShield.style.display = "none";
      }
    }
  },

  toggleAppIcon() {
    const nextIcon = this.activeIcon === 'johnny5' ? 'shield' : 'johnny5';
    this.applyActiveIcon(nextIcon);
  },

  selectAppIcon(iconName) {
    this.applyActiveIcon(iconName);
  },

  openIconPickerModal() {
    const modal = document.getElementById("icon-picker-modal");
    if (modal) {
      this.applyActiveIcon(this.activeIcon);
      modal.classList.add("active");
    }
  },

  closeIconPickerModal() {
    const modal = document.getElementById("icon-picker-modal");
    if (modal) modal.classList.remove("active");
  },

  cycleMascotQuote() {
    this.currentQuoteIdx = (this.currentQuoteIdx + 1) % this.mascotQuotes.length;
    const quoteEl = document.getElementById("mascot-quote-text");
    const mascotImg = document.getElementById("mascot-main-img");

    if (quoteEl) {
      quoteEl.style.opacity = "0.2";
      setTimeout(() => {
        quoteEl.innerText = this.mascotQuotes[this.currentQuoteIdx];
        quoteEl.style.opacity = "1";
      }, 150);
    }
    if (mascotImg) {
      mascotImg.style.transform = "scale(1.1) rotate(2deg)";
      setTimeout(() => {
        mascotImg.style.transform = "scale(1.0) rotate(0deg)";
      }, 300);
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
