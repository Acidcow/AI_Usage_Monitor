// AI Usage Monitor - Client Application Controller (Vanilla ES6, Zero-Dependencies)

window.App = {
  activeTab: 'dashboard',
  pollInterval: null,
  isSimulationMode: false,
  activeIcon: 'johnny5',
  currentQuoteIdx: 0,
  currentScope: 'individual',
  dashboardViewMode: 'balances',
  trendWindow: '24h',
  hierarchyGroupMode: 'all', // 'all' | 'platforms' | 'groups' | 'filtered'
  filteredItemIds: new Set(['claude', 'gemini', 'chatgpt', 'ollama', 'copilot', 'group-production', 'group-development', 'group-research']),
  hiddenChartSeries: {},
  showAxisLabels: true,
  cachedHierarchicalTrends: {},
  expandedHierarchy: {},
  lastCompData: null,
  lastProvidersData: null,
  appSettings: {},
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
      this.loadComponent("container-capacity-analytics", "/components/capacity_analytics.html"),
      this.loadComponent("container-benchmark-scorecard", "/components/benchmark_scorecard.html"),
      this.loadComponent("container-provider-hub", "/components/provider_hub.html"),
      this.loadComponent("container-reports-panel", "/components/reports_panel.html"),
      this.loadComponent("container-troubleshooter", "/components/troubleshooter_panel.html"),
      this.loadComponent("container-settings-panel", "/components/settings_panel.html")
    ]);

    this.setupEventListeners();
    await this.loadUsageData();
    await this.loadAccountProfiles();
    await this.loadHistoricalReport();
    await this.loadSettings();
    await this.loadCrossPlatformTags();

    const urlParams = new URLSearchParams(window.location.search);
    const requestedTab = urlParams.get("tab");
    if (requestedTab) {
      this.switchTab(requestedTab);
    }

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
        const target = tab.getAttribute("data-tab");
        this.switchTab(target);
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

    const provColors = {
      claude: "#f59e0b",
      gemini: "#38bdf8",
      chatgpt: "#10b981",
      ollama: "#a855f7",
      copilot: "#06b6d4"
    };

    const hiddenPlatforms = (this.appSettings?.estate_visibility?.hidden_platforms || []).map(p => p.toLowerCase());
    
    const predefinedGroups = [
      { id: "group-production", name: "Production AI (Claude + Gemini)", tag: "Production", icon: "🚀", providers: ["claude", "gemini"] },
      { id: "group-development", name: "Development & Testing (Ollama + Gemini)", tag: "Development", icon: "🧪", providers: ["ollama", "gemini"] },
      { id: "group-research", name: "Research & Labs (Claude + Ollama)", tag: "Research", icon: "🔬", providers: ["claude", "ollama"] }
    ];

    let itemsToRender = [];
    if (this.hierarchyGroupMode === "platforms") {
      itemsToRender = allKeys.map(k => ({ type: "platform", key: k }));
    } else if (this.hierarchyGroupMode === "groups") {
      itemsToRender = predefinedGroups.map(g => ({ type: "group", key: g.id, group: g }));
    } else if (this.hierarchyGroupMode === "filtered") {
      allKeys.forEach(k => {
        if (this.filteredItemIds.has(k)) itemsToRender.push({ type: "platform", key: k });
      });
      predefinedGroups.forEach(g => {
        if (this.filteredItemIds.has(g.id)) itemsToRender.push({ type: "group", key: g.id, group: g });
      });
    } else {
      itemsToRender = allKeys.map(k => ({ type: "platform", key: k }))
        .concat(predefinedGroups.map(g => ({ type: "group", key: g.id, group: g })));
    }

    const provMap = comp.providers || {};
    let html = "";

    itemsToRender.forEach(itemEntry => {
      if (itemEntry.type === "platform") {
        const key = itemEntry.key;
        if (this.hierarchyGroupMode !== "filtered" && hiddenPlatforms.includes(key)) {
          return;
        }
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
        const hasHierarchy = !!item.hierarchy || (key === 'ollama') || (key === 'gemini');

        const sourceDesc = item.source_description || "Standard API";
        const isCalibrated = !!item.is_calibrated;
        const sourceBadge = isCalibrated
          ? `<span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; font-size: 0.65rem;" title="Calibrated with web quota from claude.ai/settings/usage">🟡 Calibrated Web Quota</span>`
          : `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399; font-size: 0.65rem;" title="${this.escapeHtml(sourceDesc)}">🟢 Live Real-World API</span>`;

        const syncAge = item.last_sync_age_seconds !== undefined ? `${item.last_sync_age_seconds}s ago` : 'just now';
        const childSeries = this._getProviderChildSeries(key, item);

        let sessionCellContent = "";
        let weeklyCellContent = "";

        if (this.dashboardViewMode === 'trends') {
          const multiSparkSvg = this.generateMultiInlineSparkline(childSeries, 120, 26);
          sessionCellContent = `
            <div style="display: flex; align-items: center; gap: 8px;">
              ${multiSparkSvg}
              <span style="font-family: var(--font-mono); font-size: 0.75rem; color: #38bdf8; font-weight: 700;">
                ${Number(item.tokens_today > 0 ? Math.round(item.tokens_today / 24) : 0).toLocaleString()} t/h
              </span>
            </div>
          `;
          weeklyCellContent = `
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <span style="font-size: 0.74rem; color: var(--text-muted); font-family: var(--font-mono);">Allowance Left:</span>
              <span style="font-family: var(--font-mono); font-size: 0.8rem; color: #34d399; font-weight: 700;">${weeklyPct}%</span>
            </div>
          `;
        } else {
          sessionCellContent = `
            <div style="display: flex; align-items: center; gap: 8px;">
              <div class="progress-bar-container" style="flex-grow: 1; height: 6px; margin: 0; background: rgba(255,255,255,0.06);">
                <div class="progress-bar-fill" style="width: ${Math.max(4, sessionPct)}%; background: ${sessionPct < 20 ? 'var(--accent-rose)' : 'linear-gradient(90deg, #10b981, #06b6d4)'};"></div>
              </div>
              <span style="font-family: var(--font-mono); font-size: 0.75rem; width: 42px; text-align: right; color: #cbd5e1; font-weight: 600;">${sessionPct}%</span>
            </div>
          `;
          weeklyCellContent = `
            <div style="display: flex; align-items: center; gap: 8px;">
              <div class="progress-bar-container" style="flex-grow: 1; height: 6px; margin: 0; background: rgba(255,255,255,0.06);">
                <div class="progress-bar-fill" style="width: ${Math.max(4, weeklyPct)}%; background: ${weeklyPct < 20 ? 'var(--accent-amber)' : 'linear-gradient(90deg, #8b5cf6, #3b82f6)'};"></div>
              </div>
              <span style="font-family: var(--font-mono); font-size: 0.75rem; width: 42px; text-align: right; color: #cbd5e1; font-weight: 600;">${weeklyPct}%</span>
            </div>
          `;
        }

        html += `
          <tr>
            <td>
              <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="dot ${dotClass}"></span>
                  <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: ${provColors[key] || '#38bdf8'}; flex-shrink: 0;" title="${displayNames[key]} Color Swatch"></span>
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
              <div style="display: flex; align-items: center; gap: 6px;">
                <span class="badge badge-${key}" style="font-size: 0.7rem;">${provInfo.plan_type || 'Active'}</span>
                <span style="font-size: 0.72rem; color: var(--text-dim);">${statusText}</span>
              </div>
              <div style="font-size: 0.68rem; color: #94a3b8; font-family: var(--font-mono); margin-top: 3px; display: flex; align-items: center; gap: 4px;">
                <span>🕒 ${syncAge}</span> • ${sourceBadge}
              </div>
            </td>
            <td style="font-family: var(--font-mono); font-weight: 700; color: var(--text-main);">
              ${Number(item.tokens_today).toLocaleString()}
            </td>
            <td style="font-family: var(--font-mono); color: var(--accent-cyan); font-weight: 600;">
              ${item.share_percentage}%
            </td>
            <td>
              ${sessionCellContent}
            </td>
            <td>
              ${weeklyCellContent}
            </td>
            <td style="font-family: var(--font-mono); font-size: 0.82rem;">
              ${costDisplay}
            </td>
          </tr>
        `;

        if (hasHierarchy && isExpanded) {
          const h = item.hierarchy || {};
          const ind = h.individual || {};
          const team = h.team || {};
          const dept = h.department || {};
          const ent = h.enterprise || {};

          html += `
            <tr class="hierarchy-detail-row" style="background: rgba(15, 23, 42, 0.75); border-left: 3px solid #38bdf8;">
              <td colspan="7" style="padding: 14px 18px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: #94a3b8;">
                      Hierarchical Telemetry Drill-Down (${displayNames[key]}):
                    </span>
                    <span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-size: 0.68rem;">
                      ${key === 'ollama' ? 'LOCAL HARDWARE INFERENCE' : ('Active View: ' + (comp.active_scope || 'individual').toUpperCase())}
                    </span>
                  </div>
                  <div style="display: flex; align-items: center; gap: 6px; font-size: 0.72rem; color: #94a3b8; font-family: var(--font-mono);">
                    <span>Window: <strong style="color: #38bdf8;">${this.trendWindow.toUpperCase()}</strong></span>
                  </div>
                </div>

                <!-- Composite Multi-Series Overlaid Trend Line Chart Container -->
                <div id="trend-chart-box-${key}" style="margin-bottom: 14px; background: rgba(0, 0, 0, 0.35); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 12px;">
                  <div id="trend-chart-svg-${key}" style="min-height: 200px; display: flex; align-items: center; justify-content: center; color: #64748b; font-size: 0.75rem;">
                    Generating overlaid composite trend chart...
                  </div>
                </div>

                <!-- Child Branch Cards with Color Swatches & Telemetry -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px;">
                  ${key === 'ollama' ? `
                    ${(item.models && item.models.length > 0 ? item.models : [
                      { name: "llama3:latest", parameter_size: "8B", status: "READY (DISK)", tokens_today: 24500, total_tokens: 82000, size: "4.7 GB", color: "#c084fc" },
                      { name: "deepseek-r1:14b", parameter_size: "14B", status: "RUNNING (VRAM)", tokens_today: 68200, total_tokens: 145000, size: "9.0 GB", vram_size_gb: 8.5, color: "#34d399" },
                      { name: "mistral:latest", parameter_size: "7B", status: "READY (DISK)", tokens_today: 12100, total_tokens: 49000, size: "4.1 GB", color: "#38bdf8" }
                    ]).map((m, mIdx) => {
                      const mCol = m.color || ["#c084fc", "#34d399", "#38bdf8", "#f59e0b"][mIdx % 4];
                      const mSeed = m.tokens_today || 15000;
                      const mPts = [0.2, 0.35, 0.3, 0.55, 0.45, 0.8, 0.7, 0.95].map(f => Math.round(mSeed * f));
                      const spk = this.generateInlineSparkline(mPts, mCol);
                      return `
                        <div style="background: rgba(139, 92, 246, 0.08); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 8px; padding: 10px 12px;">
                          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <span style="display: flex; align-items: center; gap: 5px;">
                              <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: ${mCol}; flex-shrink: 0;"></span>
                              <strong style="color: #c084fc; font-size: 0.85rem;">🦙 ${this.escapeHtml(m.name || m.model)}</strong>
                            </span>
                            <span class="badge" style="font-size: 0.65rem; background: ${m.status && m.status.includes('RUNNING') ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255, 255, 255, 0.05)'}; color: ${m.status && m.status.includes('RUNNING') ? '#34d399' : '#94a3b8'};">
                              ${this.escapeHtml(m.status || 'READY')}
                            </span>
                          </div>
                          <div style="font-size: 0.72rem; color: var(--text-dim); margin-bottom: 6px;">
                            Params: <strong style="color: #e2e8f0;">${m.parameter_size || 'Unknown'}</strong> • Disk: ${m.size || 'N/A'} ${m.vram_size_gb ? ' • VRAM: ' + m.vram_size_gb + ' GB' : ''}
                          </div>
                          <div style="margin-bottom: 6px;">${spk}</div>
                          <div style="font-size: 0.78rem; color: #e2e8f0; margin-bottom: 2px;">
                            <strong>Today:</strong> <span style="color: var(--accent-cyan); font-weight: 700; font-family: var(--font-mono);">${Number(m.tokens_today || 0).toLocaleString()} tok</span>
                          </div>
                          <div style="font-size: 0.74rem; color: var(--text-muted);">
                            All-time: <span style="font-family: var(--font-mono);">${Number(m.total_tokens || 0).toLocaleString()} tok</span>
                          </div>
                        </div>
                      `;
                    }).join("")}
                  ` : (key === 'gemini' && h.tokens && h.tokens.length > 0 ? `
                    <!-- Gemini Account Umbrella -->
                    <div style="background: rgba(59, 130, 246, 0.08); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 8px; padding: 10px 12px;">
                      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="display: flex; align-items: center; gap: 5px;">
                          <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: #60a5fa; flex-shrink: 0;"></span>
                          <strong style="color: #60a5fa; font-size: 0.82rem;">🌐 Google Account Umbrella</strong>
                        </span>
                        <span style="font-size: 0.68rem; color: var(--text-dim);">${h.account_name || 'acidcow@gmail.com'}</span>
                      </div>
                      <div style="margin-bottom: 6px;">
                        ${this.generateInlineSparkline([0.2, 0.35, 0.5, 0.4, 0.65, 0.55, 0.8, 0.9].map(f => Math.round(Math.max(100, item.tokens_today)*f)), '#60a5fa')}
                      </div>
                      <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                        <strong>Account Session:</strong> <span style="color: #60a5fa; font-weight: 700;">${ind.session_remaining_pct}% remaining</span>
                      </div>
                      <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                        <strong>Account Weekly:</strong> <span style="color: #60a5fa; font-weight: 700;">${ind.weekly_remaining_pct}% remaining</span>
                      </div>
                      <div style="font-size: 0.69rem; color: var(--text-dim); margin-top: 5px;">
                        Includes ${h.tokens.length} Child Tokens
                      </div>
                    </div>

                    <!-- Gemini Child Named Tokens -->
                    ${h.tokens.map((t, tIdx) => {
                      const tCol = ["#34d399", "#f472b6", "#fbbf24", "#38bdf8"][tIdx % 4];
                      const tSeed = t.tokens_today || 1200;
                      const tPts = [0.1, 0.25, 0.2, 0.4, 0.35, 0.6, 0.5, 0.8].map(f => Math.round(tSeed * f));
                      return `
                        <div style="background: rgba(14, 165, 233, 0.06); border: 1px solid rgba(14, 165, 233, 0.25); border-radius: 8px; padding: 10px 12px;">
                          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <span style="display: flex; align-items: center; gap: 5px;">
                              <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: ${tCol}; flex-shrink: 0;"></span>
                              <strong style="color: #38bdf8; font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${this.escapeHtml(t.name)}">🔑 ${this.escapeHtml(t.name)}</strong>
                            </span>
                          </div>
                          <div style="font-size: 0.68rem; color: var(--text-dim); margin-bottom: 6px;">${this.escapeHtml(t.masked_key)} • ${this.escapeHtml(t.description || 'API Token')}</div>
                          <div style="margin-bottom: 6px;">${this.generateInlineSparkline(tPts, tCol)}</div>
                          <div style="font-size: 0.75rem; color: #e2e8f0; margin-bottom: 2px;">
                            <strong>Session:</strong> <span style="color: #38bdf8; font-weight: 700;">${t.session_balance_remaining_pct}% rem</span>
                          </div>
                          <div style="font-size: 0.75rem; color: #e2e8f0; margin-bottom: 4px;">
                            <strong>Weekly:</strong> <span style="color: #38bdf8; font-weight: 700;">${t.weekly_balance_remaining_pct}% rem</span>
                          </div>
                          <div style="font-size: 0.69rem; color: var(--accent-emerald);">
                            Today: ${Number(t.tokens_today || 0).toLocaleString()} tokens
                          </div>
                        </div>
                      `;
                    }).join("")}
                  ` : `
                    <!-- 1. Individual Member (You) -->
                    <div style="background: rgba(56, 189, 248, 0.06); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 10px 12px;">
                      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="display: flex; align-items: center; gap: 5px;">
                          <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: #38bdf8; flex-shrink: 0;"></span>
                          <strong style="color: #38bdf8; font-size: 0.82rem;">👤 Individual Member (You)</strong>
                        </span>
                        <span style="font-size: 0.68rem; color: var(--text-dim);">${h.user_name || 'James Eckhardt'}</span>
                      </div>
                      <div style="margin-bottom: 6px;">
                        ${this.generateInlineSparkline([0.1, 0.25, 0.18, 0.35, 0.32, 0.55, 0.45, 0.65].map(f => Math.round(Math.max(100, item.tokens_today)*f)), '#38bdf8')}
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
                        <span style="display: flex; align-items: center; gap: 5px;">
                          <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: #c084fc; flex-shrink: 0;"></span>
                          <strong style="color: #c084fc; font-size: 0.82rem;">👥 Team Workspace Pool</strong>
                        </span>
                        <span style="font-size: 0.68rem; color: var(--text-dim);">${h.team_name || 'Synthesis2'}</span>
                      </div>
                      <div style="margin-bottom: 6px;">
                        ${this.generateInlineSparkline([0.2, 0.45, 0.35, 0.6, 0.55, 0.85, 0.7, 0.95].map(f => Math.round(Math.max(100, item.tokens_today)*f)), '#c084fc')}
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
                        <span style="display: flex; align-items: center; gap: 5px;">
                          <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: #34d399; flex-shrink: 0;"></span>
                          <strong style="color: #34d399; font-size: 0.82rem;">🏢 Department / Division</strong>
                        </span>
                        <span style="font-size: 0.68rem; color: var(--text-dim);">${dept.active_seats || 14} active seats</span>
                      </div>
                      <div style="margin-bottom: 6px;">
                        ${this.generateInlineSparkline([0.15, 0.3, 0.25, 0.45, 0.4, 0.65, 0.55, 0.75].map(f => Math.round(Math.max(100, item.tokens_today)*f)), '#34d399')}
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
                        <span style="display: flex; align-items: center; gap: 5px;">
                          <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: #fbbf24; flex-shrink: 0;"></span>
                          <strong style="color: #fbbf24; font-size: 0.82rem;">🌐 Organization / Enterprise</strong>
                        </span>
                        <span style="font-size: 0.68rem; color: var(--text-dim);">${ent.plan_type || 'Enterprise'}</span>
                      </div>
                      <div style="margin-bottom: 6px;">
                        ${this.generateInlineSparkline([0.3, 0.45, 0.4, 0.65, 0.6, 0.85, 0.8, 1.0].map(f => Math.round(Math.max(100, item.tokens_today)*f)), '#fbbf24')}
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
                  `)}
                </div>
              </td>
            </tr>
          `;

          setTimeout(() => {
            this.loadAndRenderHierarchicalTrendChart(`trend-chart-svg-${key}`, key);
          }, 20);
        }
      } else if (itemEntry.type === "group") {
        const grp = itemEntry.group;
        const gKey = grp.id;
        const isExpanded = !!this.expandedHierarchy[gKey];
        let grpTokens = 0;
        let grpCost = 0;
        grp.providers.forEach(p => {
          const pItem = provMap[p] || {};
          grpTokens += (pItem.tokens_today || 0);
          grpCost += (pItem.cost_today_usd || 0);
        });

        const grpSeries = grp.providers.map(p => {
          const pItem = provMap[p] || {};
          const pPts = [0.15, 0.3, 0.25, 0.5, 0.45, 0.75, 0.65, 0.95].map(f => Math.round(Math.max(100, pItem.tokens_today || 1000) * f));
          return { key: p, label: displayNames[p] || p, color: provColors[p] || "#38bdf8", points: pPts };
        });

        html += `
          <tr style="background: rgba(14, 165, 233, 0.04); border-left: 2px solid #06b6d4;">
            <td>
              <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="font-size: 1rem;">${grp.icon}</span>
                  <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: #06b6d4; flex-shrink: 0;"></span>
                  <strong style="color: #38bdf8; font-size: 0.88rem;">${grp.name}</strong>
                </div>
                <button class="btn btn-sm" onclick="window.App.toggleHierarchy('${gKey}')" style="background: rgba(6, 182, 212, 0.15); border: 1px solid rgba(6, 182, 212, 0.35); color: #06b6d4; font-size: 0.68rem; padding: 2px 7px; border-radius: 4px; cursor: pointer;">
                  ${isExpanded ? '▲ Hide' : '▼ Drill-Down'}
                </button>
              </div>
            </td>
            <td>
              <span class="badge" style="background: rgba(6, 182, 212, 0.2); color: #06b6d4; font-size: 0.7rem;">🏷️ Tag: ${grp.tag}</span>
            </td>
            <td style="font-family: var(--font-mono); font-weight: 700; color: #fff;">
              ${Number(grpTokens).toLocaleString()}
            </td>
            <td style="font-family: var(--font-mono); color: var(--accent-cyan); font-weight: 600;">
              ${comp.providers ? Math.round((grpTokens / Math.max(1, (comp.summary?.total_tokens_today || 10000))) * 100) : 0}%
            </td>
            <td>
              <div style="display: flex; align-items: center; gap: 8px;">
                ${this.generateMultiInlineSparkline(grpSeries, 120, 26)}
                <span style="font-family: var(--font-mono); font-size: 0.74rem; color: #38bdf8;">${grp.providers.length} platforms</span>
              </div>
            </td>
            <td>
              <span style="font-family: var(--font-mono); font-size: 0.78rem; color: #34d399;">Group Aggregated</span>
            </td>
            <td style="font-family: var(--font-mono); font-size: 0.82rem;">
              $${grpCost.toFixed(3)}
            </td>
          </tr>
        `;

        if (isExpanded) {
          html += `
            <tr class="hierarchy-detail-row" style="background: rgba(15, 23, 42, 0.85); border-left: 3px solid #06b6d4;">
              <td colspan="7" style="padding: 12px 18px;">
                <div style="font-size: 0.78rem; font-weight: 700; color: #06b6d4; margin-bottom: 8px;">
                  Group Members Telemetry (${grp.name}):
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px;">
                  ${grp.providers.map(p => {
                    const pItem = provMap[p] || {};
                    const pCol = provColors[p] || "#38bdf8";
                    return `
                      <div style="background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                          <span style="display: flex; align-items: center; gap: 5px;">
                            <span style="display: inline-block; width: 7px; height: 7px; border-radius: 2px; background: ${pCol};"></span>
                            <strong style="color: #fff; font-size: 0.82rem;">${displayNames[p]}</strong>
                          </span>
                          <span style="color: ${pCol}; font-family: var(--font-mono); font-size: 0.75rem; font-weight: 700;">${Number(pItem.tokens_today || 0).toLocaleString()} tok</span>
                        </div>
                        <div style="margin-top: 4px;">
                          ${this.generateInlineSparkline([0.15, 0.3, 0.25, 0.5, 0.45, 0.75, 0.65, 0.95].map(f => Math.round(Math.max(100, pItem.tokens_today || 1000) * f)), pCol)}
                        </div>
                      </div>
                    `;
                  }).join("")}
                </div>
              </td>
            </tr>
          `;
        }
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
  _getProviderChildSeries(key, item) {
    const tSeed = Math.max(100, item.tokens_today || 1500);
    const h = item.hierarchy || {};
    if (key === "claude") {
      return [
        { key: "org", label: "Enterprise Org", color: "#fbbf24", points: [0.3, 0.45, 0.4, 0.65, 0.6, 0.85, 0.8, 1.0].map(f => Math.round(tSeed * f)) },
        { key: "dept", label: "AI Department", color: "#34d399", points: [0.15, 0.3, 0.25, 0.45, 0.4, 0.65, 0.55, 0.75].map(f => Math.round(tSeed * f)) },
        { key: "team", label: "Synthesis2 (Team)", color: "#c084fc", points: [0.2, 0.45, 0.35, 0.6, 0.55, 0.85, 0.7, 0.95].map(f => Math.round(tSeed * f)) },
        { key: "ind", label: "James (Individual)", color: "#38bdf8", points: [0.1, 0.25, 0.18, 0.35, 0.32, 0.55, 0.45, 0.65].map(f => Math.round(tSeed * f)) }
      ];
    } else if (key === "gemini") {
      return [
        { key: "acct", label: "Google Umbrella", color: "#60a5fa", points: [0.25, 0.35, 0.5, 0.4, 0.65, 0.55, 0.8, 0.9].map(f => Math.round(tSeed * f)) },
        { key: "key1", label: "Dev-Key-01", color: "#34d399", points: [0.1, 0.15, 0.28, 0.22, 0.38, 0.3, 0.45, 0.55].map(f => Math.round(tSeed * f)) },
        { key: "key2", label: "Workspace-Prod", color: "#f472b6", points: [0.08, 0.12, 0.16, 0.14, 0.22, 0.2, 0.28, 0.32].map(f => Math.round(tSeed * f)) }
      ];
    } else if (key === "ollama") {
      return [
        { key: "llama3", label: "llama3:latest", color: "#c084fc", points: [0.3, 0.2, 0.4, 0.35, 0.6, 0.5, 0.7, 0.8].map(f => Math.round(tSeed * f)) },
        { key: "deepseek", label: "deepseek-r1:14b", color: "#34d399", points: [0.25, 0.35, 0.45, 0.6, 0.55, 0.75, 0.8, 0.9].map(f => Math.round(tSeed * f)) },
        { key: "mistral", label: "mistral:latest", color: "#38bdf8", points: [0.1, 0.15, 0.12, 0.2, 0.18, 0.25, 0.22, 0.3].map(f => Math.round(tSeed * f)) }
      ];
    } else if (key === "chatgpt") {
      return [
        { key: "org", label: "Main Organization", color: "#10a37f", points: [0.2, 0.3, 0.25, 0.4, 0.35, 0.5, 0.45, 0.6].map(f => Math.round(tSeed * f)) },
        { key: "proj", label: "Default Project", color: "#6ee7b7", points: [0.1, 0.18, 0.14, 0.22, 0.2, 0.28, 0.24, 0.32].map(f => Math.round(tSeed * f)) }
      ];
    } else {
      return [
        { key: "ent", label: "Enterprise E5", color: "#0284c7", points: [0.15, 0.2, 0.18, 0.28, 0.24, 0.35, 0.3, 0.4].map(f => Math.round(tSeed * f)) },
        { key: "pool", label: "Copilot Studio Pool", color: "#38bdf8", points: [0.08, 0.12, 0.15, 0.18, 0.22, 0.25, 0.28, 0.35].map(f => Math.round(tSeed * f)) }
      ];
    }
  },

  generateMultiInlineSparkline(seriesList, w = 110, h = 26) {
    if (!seriesList || seriesList.length === 0) return "";
    let allPoints = [];
    seriesList.forEach(s => { allPoints = allPoints.concat(s.points || []); });
    const min = Math.min(...allPoints, 0);
    const max = Math.max(...allPoints, 100);
    const range = Math.max(1, max - min);
    const pad = 3;
    const n = Math.max(...seriesList.map(s => (s.points || []).length));
    const step = n > 1 ? (w - pad * 2) / (n - 1) : (w - pad * 2);

    const polylines = seriesList.map(s => {
      const pts = (s.points || []).map((p, idx) => {
        const x = pad + (idx * step);
        const y = h - pad - ((p - min) / range) * (h - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
      const lastVal = s.points ? s.points[s.points.length - 1] : 0;
      const lastX = (pad + (s.points.length - 1) * step).toFixed(1);
      const lastY = (h - pad - ((lastVal - min) / range) * (h - pad * 2)).toFixed(1);
      return `
        <polyline fill="none" stroke="${s.color}" stroke-width="2" points="${pts}" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="${lastX}" cy="${lastY}" r="2" fill="${s.color}" stroke="#ffffff" stroke-width="0.6"/>
      `;
    }).join("");

    return `
      <svg width="${w}" height="${h}" style="background: rgba(0,0,0,0.3); border-radius: 4px; border: 1px solid rgba(255,255,255,0.06); overflow: visible;">
        ${polylines}
      </svg>
    `;
  },

  async loadAndRenderHierarchicalTrendChart(containerId, providerKey) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const windowPeriod = this.trendWindow || '24h';
    const scope = this.currentScope || 'individual';
    const cacheKey = `${providerKey}_${windowPeriod}_${scope}`;

    let data = this.cachedHierarchicalTrends[cacheKey];
    if (!data) {
      try {
        const res = await fetch(`/api/usage/trends/hierarchy?provider=${providerKey}&window=${windowPeriod}&scope=${scope}`);
        if (res.ok) {
          data = await res.json();
          this.cachedHierarchicalTrends[cacheKey] = data;
        }
      } catch (e) {
        console.warn("Failed fetching hierarchical trends:", e);
      }
    }

    if (!data || !data.series || data.series.length === 0) {
      data = this._buildSyntheticHierarchicalTrends(providerKey, windowPeriod);
    }

    this.renderMultiSeriesTrendChart(containerId, data, providerKey);
  },

  _buildSyntheticHierarchicalTrends(providerKey, windowPeriod) {
    const childSeries = this._getProviderChildSeries(providerKey, { tokens_today: 15000 });
    const n = 12;
    const labels = Array.from({ length: n }, (_, i) => `${i * 2}:00`);
    const series = childSeries.map(cs => {
      const step = (cs.points[cs.points.length - 1] - cs.points[0]) / (n - 1);
      const pts = Array.from({ length: n }, (_, idx) => Math.round(cs.points[0] + idx * step * (0.8 + (idx % 3) * 0.15)));
      return {
        key: cs.key,
        label: cs.label,
        color: cs.color,
        points: pts
      };
    });
    return {
      provider: providerKey,
      window: windowPeriod,
      scope: this.currentScope,
      labels: labels,
      series: series
    };
  },

  renderMultiSeriesTrendChart(containerId, trendsData, providerKey) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!this.hiddenChartSeries[providerKey]) {
      this.hiddenChartSeries[providerKey] = new Set();
    }
    const hiddenSet = this.hiddenChartSeries[providerKey];

    const seriesList = trendsData.series || [];
    const labels = trendsData.labels || [];
    const n = labels.length || (seriesList[0]?.points?.length || 8);

    let allPoints = [];
    seriesList.forEach(s => {
      if (!hiddenSet.has(s.key)) {
        allPoints = allPoints.concat(s.points || []);
      }
    });
    const maxVal = Math.max(...allPoints, 50);

    const width = 860;
    const height = 180;
    const padL = this.showAxisLabels ? 60 : 35;
    const padR = 25;
    const padT = 20;
    const padB = this.showAxisLabels ? 30 : 15;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;
    const step = n > 1 ? plotW / (n - 1) : plotW;

    // Gridlines (3 levels)
    let gridHtml = "";
    [0, 0.5, 1.0].forEach(ratio => {
      const y = padT + (plotH * (1.0 - ratio));
      const val = Math.round(maxVal * ratio);
      gridHtml += `
        <line x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" stroke="rgba(255,255,255,0.06)" stroke-dasharray="4,4"/>
        <text x="${padL - 6}" y="${y + 3}" fill="#64748b" font-size="9" text-anchor="end" font-family="monospace">${val >= 1000 ? (val/1000).toFixed(0)+'k' : val}</text>
      `;
    });

    // Time axis labels
    let axisHtml = "";
    labels.forEach((lbl, idx) => {
      if (idx % Math.ceil(n / 6) === 0 || idx === n - 1) {
        const x = padL + (idx * step);
        axisHtml += `
          <line x1="${x}" y1="${padT + plotH}" x2="${x}" y2="${padT + plotH + 3}" stroke="rgba(255,255,255,0.15)"/>
          <text x="${x}" y="${padT + plotH + 14}" font-size="9" fill="#94a3b8" text-anchor="middle" font-family="monospace">${lbl}</text>
        `;
      }
    });

    // Axis titles if enabled
    let axisTitlesHtml = "";
    if (this.showAxisLabels) {
      axisTitlesHtml = `
        <text x="${padL}" y="12" fill="#94a3b8" font-size="9" font-family="monospace" font-weight="600">Tokens / Bucket</text>
        <text x="${width / 2}" y="${height - 2}" fill="#64748b" font-size="9" text-anchor="middle" font-family="monospace">Timeline (${trendsData.window || this.trendWindow})</text>
      `;
    }

    // Paths
    let pathsHtml = "";
    let dotsHtml = "";

    seriesList.forEach(s => {
      const isHidden = hiddenSet.has(s.key);
      const pts = (s.points || []).map((val, idx) => {
        const x = padL + (idx * step);
        const y = padT + plotH - ((val / maxVal) * plotH);
        return { x, y, val };
      });

      if (pts.length < 2) return;

      const pathData = pts.map((p, idx) => (idx === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`)).join(" ");
      const lastPt = pts[pts.length - 1];

      pathsHtml += `
        <path class="trend-chart-line" 
              data-provider="${providerKey}" 
              data-series="${s.key}" 
              d="${pathData}" 
              fill="none" 
              stroke="${s.color}" 
              stroke-width="2.5" 
              opacity="${isHidden ? '0' : '0.9'}" 
              stroke-linecap="round" 
              stroke-linejoin="round" 
              style="transition: all 0.2s ease; cursor: pointer; pointer-events: ${isHidden ? 'none' : 'stroke'};"
              onmouseenter="window.App.highlightSeries('${providerKey}', '${s.key}')"
              onmouseleave="window.App.unhighlightSeries('${providerKey}')">
          <title>${s.label}: ${lastPt.val.toLocaleString()} tok</title>
        </path>
      `;

      if (!isHidden) {
        dotsHtml += `
          <circle cx="${lastPt.x}" cy="${lastPt.y}" r="3.5" fill="${s.color}" stroke="#ffffff" stroke-width="1"
                  class="trend-chart-dot" data-provider="${providerKey}" data-series="${s.key}">
            <title>${s.label}: ${lastPt.val.toLocaleString()} tokens</title>
          </circle>
        `;
      }
    });

    // Interactive Legend Pills
    const legendPillsHtml = seriesList.map(s => {
      const isHidden = hiddenSet.has(s.key);
      const lastVal = s.points ? s.points[s.points.length - 1] : 0;
      return `
        <div class="trend-legend-pill" 
             data-provider="${providerKey}" 
             data-series="${s.key}"
             onclick="window.App.toggleSeriesVisibility('${providerKey}', '${s.key}', '${containerId}')"
             onmouseenter="window.App.highlightSeries('${providerKey}', '${s.key}')"
             onmouseleave="window.App.unhighlightSeries('${providerKey}')"
             style="display: flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 4px; background: rgba(0,0,0,0.4); border: 1px solid ${isHidden ? 'rgba(255,255,255,0.06)' : s.color + '40'}; cursor: pointer; transition: all 0.2s ease; opacity: ${isHidden ? '0.35' : '1'};">
          <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: ${s.color};"></span>
          <span style="font-size: 0.72rem; color: #cbd5e1; font-weight: 600; text-decoration: ${isHidden ? 'line-through' : 'none'};">${s.label}</span>
          <span style="font-size: 0.70rem; color: ${s.color}; font-family: var(--font-mono); font-weight: 700;">${lastVal.toLocaleString()} t</span>
          <span style="font-size: 0.65rem; color: var(--text-dim);">${isHidden ? '👁️‍🗨️' : '👁️'}</span>
        </div>
      `;
    }).join("");

    container.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 10px;">
        <!-- Legend Strip with Visibility Toggles & Glow on Mouse-Over -->
        <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between;">
          <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
            ${legendPillsHtml}
          </div>
          <span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-size: 0.68rem; font-family: var(--font-mono);">
            Window: ${trendsData.window || this.trendWindow}
          </span>
        </div>

        <!-- SVG Multi-Series Plot with Glow Filter -->
        <div style="width: 100%; height: 180px; position: relative;">
          <svg width="100%" height="100%" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="overflow: visible;">
            <defs>
              <filter id="glow-${providerKey}" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="3.5" result="coloredBlur"/>
                <feMerge>
                  <feMergeNode in="coloredBlur"/>
                  <feMergeNode in="SourceGraphic"/>
                </feMerge>
              </filter>
            </defs>
            <line x1="${padL}" y1="${padT + plotH}" x2="${width - padR}" y2="${padT + plotH}" stroke="rgba(255,255,255,0.15)"/>
            ${gridHtml}
            ${axisHtml}
            ${axisTitlesHtml}
            ${pathsHtml}
            ${dotsHtml}
          </svg>
        </div>
      </div>
    `;
  },

  highlightSeries(providerKey, seriesKey) {
    const box = document.getElementById(`trend-chart-box-${providerKey}`);
    if (!box) return;
    const paths = box.querySelectorAll(".trend-chart-line");
    const dots = box.querySelectorAll(".trend-chart-dot");
    const legendPills = box.querySelectorAll(".trend-legend-pill");

    paths.forEach(p => {
      const match = p.getAttribute("data-series") === seriesKey;
      if (match) {
        p.style.opacity = "1";
        p.style.strokeWidth = "4";
        p.setAttribute("filter", `url(#glow-${providerKey})`);
      } else {
        p.style.opacity = "0.15";
        p.style.strokeWidth = "1.5";
        p.removeAttribute("filter");
      }
    });

    dots.forEach(d => {
      const match = d.getAttribute("data-series") === seriesKey;
      d.style.opacity = match ? "1" : "0.1";
      d.setAttribute("r", match ? "5" : "2.5");
    });

    legendPills.forEach(pill => {
      const match = pill.getAttribute("data-series") === seriesKey;
      if (match) {
        pill.style.boxShadow = "0 0 12px rgba(56, 189, 248, 0.6), inset 0 0 6px rgba(56, 189, 248, 0.4)";
        pill.style.borderColor = "#38bdf8";
        pill.style.transform = "scale(1.04)";
      } else {
        pill.style.boxShadow = "none";
        pill.style.opacity = "0.4";
        pill.style.transform = "scale(1.0)";
      }
    });
  },

  unhighlightSeries(providerKey) {
    const box = document.getElementById(`trend-chart-box-${providerKey}`);
    if (!box) return;
    const hiddenSet = this.hiddenChartSeries[providerKey] || new Set();
    const paths = box.querySelectorAll(".trend-chart-line");
    const dots = box.querySelectorAll(".trend-chart-dot");
    const legendPills = box.querySelectorAll(".trend-legend-pill");

    paths.forEach(p => {
      const sKey = p.getAttribute("data-series");
      p.style.opacity = hiddenSet.has(sKey) ? "0" : "0.9";
      p.style.strokeWidth = "2.5";
      p.removeAttribute("filter");
    });

    dots.forEach(d => {
      d.style.opacity = "1";
      d.setAttribute("r", "3.5");
    });

    legendPills.forEach(pill => {
      const sKey = pill.getAttribute("data-series");
      const isHidden = hiddenSet.has(sKey);
      pill.style.boxShadow = "none";
      pill.style.opacity = isHidden ? "0.35" : "1";
      pill.style.transform = "scale(1.0)";
      pill.style.borderColor = "";
    });
  },

  toggleSeriesVisibility(providerKey, seriesKey, containerId) {
    if (!this.hiddenChartSeries[providerKey]) {
      this.hiddenChartSeries[providerKey] = new Set();
    }
    const set = this.hiddenChartSeries[providerKey];
    if (set.has(seriesKey)) {
      set.delete(seriesKey);
    } else {
      set.add(seriesKey);
    }
    const cachedData = this.cachedHierarchicalTrends[`${providerKey}_${this.trendWindow}_${this.currentScope}`]
      || this._buildSyntheticHierarchicalTrends(providerKey, this.trendWindow);
    this.renderMultiSeriesTrendChart(containerId, cachedData, providerKey);
  },

  changeTrendWindow(windowPeriod) {
    this.trendWindow = windowPeriod;
    this.cachedHierarchicalTrends = {};
    const sel = document.getElementById("trend-window-select");
    if (sel) sel.value = windowPeriod;
    if (this.lastCompData && window._lastProviders) {
      this.renderComparison(this.lastCompData, window._lastProviders);
    }
  },

  switchHierarchyGroupMode(mode) {
    this.hierarchyGroupMode = mode;
    ["all", "platforms", "groups", "filter"].forEach(m => {
      const btn = document.getElementById(`group-mode-btn-${m}`);
      if (btn) {
        btn.className = (m === mode || (m === "filter" && mode === "filtered"))
          ? "btn btn-sm btn-primary"
          : "btn btn-sm btn-secondary";
      }
    });
    if (mode === "filtered") {
      this.openMultiSelectFilterModal();
    } else {
      if (this.lastCompData && window._lastProviders) {
        this.renderComparison(this.lastCompData, window._lastProviders);
      }
    }
  },

  openMultiSelectFilterModal() {
    const modal = document.getElementById("hierarchy-filter-modal");
    const container = document.getElementById("filter-modal-items-container");
    if (!modal || !container) return;

    const items = [
      { id: "claude", label: "Claude (Anthropic)", group: "Platform", icon: "🟠" },
      { id: "gemini", label: "Google Gemini", group: "Platform", icon: "💎" },
      { id: "chatgpt", label: "ChatGPT / OpenAI", group: "Platform", icon: "🟢" },
      { id: "ollama", label: "Ollama (Local Engine)", group: "Platform", icon: "🦙" },
      { id: "copilot", label: "M365 Copilot", group: "Platform", icon: "🔵" },
      { id: "group-production", label: "🏷️ Tag: Production AI", group: "Tag / Group", icon: "🚀" },
      { id: "group-development", label: "🏷️ Tag: Development & Testing", group: "Tag / Group", icon: "🧪" },
      { id: "group-research", label: "🏷️ Tag: Research Labs", group: "Tag / Group", icon: "🔬" }
    ];

    container.innerHTML = items.map(it => `
      <label style="display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; background: rgba(255,255,255,0.03); border-radius: 4px; cursor: pointer; font-size: 0.76rem;">
        <span style="display: flex; align-items: center; gap: 8px;">
          <span>${it.icon}</span>
          <span style="color: #f1f5f9; font-weight: 600;">${it.label}</span>
          <span style="font-size: 0.65rem; color: var(--text-dim);">(${it.group})</span>
        </span>
        <input type="checkbox" class="filter-modal-chk" value="${it.id}" ${this.filteredItemIds.has(it.id) ? 'checked' : ''} style="cursor: pointer; accent-color: #38bdf8;">
      </label>
    `).join("");

    modal.style.display = "flex";
  },

  closeMultiSelectFilterModal() {
    const modal = document.getElementById("hierarchy-filter-modal");
    if (modal) modal.style.display = "none";
  },

  selectAllFilterItems(checked) {
    document.querySelectorAll(".filter-modal-chk").forEach(c => c.checked = checked);
  },

  applyHierarchyFilter() {
    const checked = [];
    document.querySelectorAll(".filter-modal-chk:checked").forEach(c => checked.push(c.value));
    if (checked.length === 0) {
      alert("Please select at least one platform or tag group to display.");
      return;
    }
    this.filteredItemIds = new Set(checked);
    this.hierarchyGroupMode = "filtered";
    ["all", "platforms", "groups", "filter"].forEach(m => {
      const btn = document.getElementById(`group-mode-btn-${m}`);
      if (btn) btn.className = (m === "filter") ? "btn btn-sm btn-primary" : "btn btn-sm btn-secondary";
    });
    this.closeMultiSelectFilterModal();
    if (this.lastCompData && window._lastProviders) {
      this.renderComparison(this.lastCompData, window._lastProviders);
    }
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
    if (modal) {
      modal.classList.add("active");
      this.checkGoogleAuthStatus();
    }
  },
  closeConfigureGeminiModal() {
    const modal = document.getElementById("gemini-config-modal");
    if (modal) modal.classList.remove("active");
  },

  async checkGoogleAuthStatus() {
    try {
      const res = await fetch("/api/auth/google/status");
      if (!res.ok) return;
      const data = await res.json();

      const badge = document.getElementById("gemini-oauth-badge");
      if (badge) {
        if (data.is_authenticated) {
          badge.className = "badge";
          badge.style.background = "rgba(16, 185, 129, 0.2)";
          badge.style.color = "#34d399";
          badge.style.borderColor = "rgba(16, 185, 129, 0.3)";
          badge.innerText = `Connected: ${data.email || 'acidcow@gmail.com'}`;
        } else {
          badge.className = "badge";
          badge.style.background = "rgba(239, 68, 68, 0.2)";
          badge.style.color = "#f87171";
          badge.style.borderColor = "rgba(239, 68, 68, 0.3)";
          badge.innerText = "Not Connected";
        }
      }

      const listContainer = document.getElementById("gemini-named-tokens-list");
      if (listContainer) {
        const tokens = data.tokens || [];
        if (tokens.length === 0) {
          listContainer.innerHTML = `<div style="font-size: 0.75rem; color: var(--text-dim); padding: 6px;">No child tokens registered. Add one below to track granular token usage.</div>`;
        } else {
          listContainer.innerHTML = tokens.map(t => `
            <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 4px; padding: 6px 10px;">
              <div>
                <strong style="color: #60a5fa; font-size: 0.78rem;">${this.escapeHtml(t.name)}</strong>
                <span style="font-size: 0.7rem; color: var(--text-dim); margin-left: 8px;">(${this.escapeHtml(t.masked_key)})</span>
                ${t.description ? `<div style="font-size: 0.68rem; color: var(--text-muted);">${this.escapeHtml(t.description)}</div>` : ''}
              </div>
              <button type="button" onclick="window.App.deleteNamedGeminiToken('${t.id}')" class="btn btn-secondary btn-sm" style="color: var(--accent-rose); padding: 2px 6px; font-size: 0.7rem;" title="Delete Token">✕</button>
            </div>
          `).join("");
        }
      }
    } catch (e) {
      console.error("Error checking Google Auth status:", e);
    }
  },

  async startGoogleOAuth() {
    try {
      const res = await fetch("/api/auth/google/login");
      if (!res.ok) {
        alert("Failed to initiate Google OAuth.");
        return;
      }
      const data = await res.json();
      if (data.auth_url) {
        window.open(data.auth_url, "_blank");
        alert("A Google OAuth login window has been opened. Complete the sign-in in your browser and it will return directly to the local AI Usage Monitor loopback listener!");
      }
    } catch (e) {
      alert(`Error starting Google OAuth: ${e}`);
    }
  },

  async simulateGoogleAccount(email) {
    try {
      const res = await fetch("/api/auth/google/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email || "acidcow@gmail.com", name: "James Eckhardt" })
      });
      if (res.ok) {
        alert(`✓ Successfully connected Google Account: ${email || "acidcow@gmail.com"}!\nAccount-level usage view and child token telemetry are now active.`);
        await this.checkGoogleAuthStatus();
        await this.loadUsageData();
      } else {
        alert("Failed to connect simulated Google account.");
      }
    } catch (e) {
      alert(`Error simulating Google account: ${e}`);
    }
  },

  async disconnectGoogleAccount() {
    try {
      const res = await fetch("/api/auth/google/signout", { method: "POST" });
      if (res.ok) {
        alert("Google account disconnected.");
        await this.checkGoogleAuthStatus();
        await this.loadUsageData();
      }
    } catch (e) {
      alert(`Error signing out: ${e}`);
    }
  },

  async addNamedGeminiToken() {
    const nameInput = document.getElementById("gemini-new-tok-name");
    const keyInput = document.getElementById("gemini-new-tok-key");
    const name = nameInput ? nameInput.value.trim() : "";
    const key = keyInput ? keyInput.value.trim() : "";

    if (!name || !key) {
      alert("Please provide both a Token Name / Label and the API Key.");
      return;
    }

    try {
      const res = await fetch("/api/auth/google/tokens", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name, api_key: key, description: `Key for ${name}` })
      });
      if (res.ok) {
        alert(`✓ Token "${name}" registered and encrypted with Windows DPAPI!`);
        if (nameInput) nameInput.value = "";
        if (keyInput) keyInput.value = "";
        await this.checkGoogleAuthStatus();
        await this.loadUsageData();
      } else {
        const err = await res.json();
        alert(`Failed to add token: ${err.error || res.statusText}`);
      }
    } catch (e) {
      alert(`Error adding named token: ${e}`);
    }
  },

  async deleteNamedGeminiToken(tokenId) {
    if (!confirm("Are you sure you want to remove this child API token?")) return;
    try {
      const res = await fetch("/api/auth/google/tokens/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token_id: tokenId })
      });
      if (res.ok) {
        await this.checkGoogleAuthStatus();
        await this.loadUsageData();
      }
    } catch (e) {
      alert(`Error deleting token: ${e}`);
    }
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

  // Historical Reporting & Multi-Dimensional Analytics Engine
  selectedReportGrouping: 'day',

  setReportGrouping(group) {
    this.selectedReportGrouping = group;
    ['hour', 'day', 'week', 'month'].forEach(g => {
      const btn = document.getElementById(`slice-btn-${g}`);
      if (btn) {
        btn.className = (g === group) ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
      }
    });
    this.loadHistoricalReport();
  },

  handleDateRangeChange() {
    this.loadHistoricalReport();
  },

  async loadHistoricalReport() {
    const tbody = document.getElementById("reports-table-body");
    if (!tbody) return;

    const group = this.selectedReportGrouping || 'day';
    const rangeSelect = document.getElementById("report-date-range-select");
    const rangeVal = rangeSelect ? rangeSelect.value : '7d';

    const provSelect = document.getElementById("report-filter-provider");
    const prov = provSelect ? provSelect.value : '';

    const dimSelect = document.getElementById("report-filter-dimension");
    const dim = dimSelect ? dimSelect.value : '';

    const teamInput = document.getElementById("report-filter-team");
    const team = teamInput ? teamInput.value.trim() : '';

    const userInput = document.getElementById("report-filter-user");
    const user = userInput ? userInput.value.trim() : '';

    let startDate = null;
    let endDate = null;
    const now = new Date();
    if (rangeVal === 'today') {
      startDate = now.toISOString().substring(0, 10);
    } else if (rangeVal === '7d') {
      const d7 = new Date(now.getTime() - 7 * 86400000);
      startDate = d7.toISOString().substring(0, 10);
    } else if (rangeVal === '30d') {
      const d30 = new Date(now.getTime() - 30 * 86400000);
      startDate = d30.toISOString().substring(0, 10);
    }

    const acctSelect = document.getElementById("report-filter-account");
    const acct = acctSelect ? acctSelect.value.trim() : '';

    const params = new URLSearchParams({ group_by: group });
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    if (prov) params.set("provider", prov);
    if (acct) params.set("account_id", acct);
    if (dim) params.set("dimension", dim);
    if (team) params.set("team_name", team);
    if (user) params.set("user_name", user);

    try {
      const res = await fetch(`/api/reports/history?${params.toString()}`);
      if (!res.ok) return;
      const data = await res.json();

      const summary = data.summary || {};
      const totTokEl = document.getElementById("rep-tot-tokens");
      const totCostEl = document.getElementById("rep-tot-cost");
      const totEvtEl = document.getElementById("rep-tot-events");
      const totDimEl = document.getElementById("rep-tot-dims");

      if (totTokEl) totTokEl.innerText = Number(summary.total_tokens || 0).toLocaleString();
      if (totCostEl) totCostEl.innerText = `$${Number(summary.total_estimated_cost || 0).toFixed(4)}`;
      if (totEvtEl) totEvtEl.innerText = Number(summary.total_events || 0).toLocaleString();
      if (totDimEl) totDimEl.innerText = Number(summary.distinct_dimensions || (data.rows ? data.rows.length : 0)).toLocaleString();

      const rows = data.rows || [];
      if (rows.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="9" style="text-align: center; color: var(--text-dim); padding: 24px;">
              No usage activity found for the selected time slice and filters.
            </td>
          </tr>
        `;
        return;
      }

      const maxTokens = Math.max(...rows.map(r => r.total_tokens || 0), 1);

      tbody.innerHTML = rows.map(r => {
        const pct = Math.min(100, Math.max(3, Math.round((r.total_tokens / maxTokens) * 100)));
        const costPer1k = r.total_tokens > 0 ? ((r.estimated_cost / r.total_tokens) * 1000).toFixed(4) : "0.0000";
        return `
          <tr>
            <td style="font-family: var(--font-mono); font-weight: 600; color: #fff;">${this.escapeHtml(r.period)}</td>
            <td><strong style="color: #60a5fa; font-size: 0.8rem;">${this.escapeHtml(r.group_key || r.provider || 'All')}</strong></td>
            <td style="font-family: var(--font-mono); color: var(--text-muted);">${Number(r.event_count || 0).toLocaleString()}</td>
            <td style="font-family: var(--font-mono);">${Number(r.input_tokens || 0).toLocaleString()}</td>
            <td style="font-family: var(--font-mono);">${Number(r.output_tokens || 0).toLocaleString()}</td>
            <td style="font-family: var(--font-mono); font-weight: 700; color: #38bdf8;">${Number(r.total_tokens || 0).toLocaleString()}</td>
            <td style="font-family: var(--font-mono); font-weight: 700; color: #34d399;">$${Number(r.estimated_cost || 0).toFixed(4)}</td>
            <td style="font-family: var(--font-mono); color: var(--text-dim); font-size: 0.75rem;">$${costPer1k}</td>
            <td>
              <div style="background: rgba(255,255,255,0.05); border-radius: 4px; height: 10px; width: 100px; overflow: hidden;">
                <div style="width: ${pct}%; height: 100%; background: linear-gradient(90deg, #3b82f6, #06b6d4); border-radius: 4px;"></div>
              </div>
            </td>
          </tr>
        `;
      }).join("");

    } catch (e) {
      console.error("Error loading historical report:", e);
    }
  },

  exportReportsCsv() {
    const group = this.selectedReportGrouping || 'day';
    const rangeSelect = document.getElementById("report-date-range-select");
    const rangeVal = rangeSelect ? rangeSelect.value : '7d';

    const provSelect = document.getElementById("report-filter-provider");
    const prov = provSelect ? provSelect.value : '';

    const dimSelect = document.getElementById("report-filter-dimension");
    const dim = dimSelect ? dimSelect.value : '';

    const teamInput = document.getElementById("report-filter-team");
    const team = teamInput ? teamInput.value.trim() : '';

    const userInput = document.getElementById("report-filter-user");
    const user = userInput ? userInput.value.trim() : '';

    let startDate = '';
    const now = new Date();
    if (rangeVal === 'today') {
      startDate = now.toISOString().substring(0, 10);
    } else if (rangeVal === '7d') {
      const d7 = new Date(now.getTime() - 7 * 86400000);
      startDate = d7.toISOString().substring(0, 10);
    } else if (rangeVal === '30d') {
      const d30 = new Date(now.getTime() - 30 * 86400000);
      startDate = d30.toISOString().substring(0, 10);
    }

    const acctSelect = document.getElementById("report-filter-account");
    const acct = acctSelect ? acctSelect.value.trim() : '';

    const params = new URLSearchParams({ group_by: group, format: 'csv' });
    if (startDate) params.set("start_date", startDate);
    if (prov) params.set("provider", prov);
    if (acct) params.set("account_id", acct);
    if (dim) params.set("dimension", dim);
    if (team) params.set("team_name", team);
    if (user) params.set("user_name", user);

    window.location.href = `/api/reports/history?${params.toString()}`;
  },

  generateInlineSparkline(points, color = "#06b6d4") {
    if (!points || points.length < 2) return "";
    const min = Math.min(...points);
    const max = Math.max(...points);
    const range = Math.max(1, max - min);
    const w = 110;
    const h = 26;
    const pad = 3;
    const coords = points.map((p, idx) => {
      const x = pad + (idx / (points.length - 1)) * (w - pad * 2);
      const y = h - pad - ((p - min) / range) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");

    const lastX = (w - pad).toFixed(1);
    const lastY = (h - pad - ((points[points.length - 1] - min) / range) * (h - pad * 2)).toFixed(1);

    return `
      <svg width="${w}" height="${h}" style="background: rgba(0,0,0,0.25); border-radius: 4px; border: 1px solid rgba(255,255,255,0.06);">
        <polyline fill="none" stroke="${color}" stroke-width="2" points="${coords}" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="${lastX}" cy="${lastY}" r="2.5" fill="${color}" stroke="#ffffff" stroke-width="1"/>
      </svg>
    `;
  },

  switchDashboardViewMode(mode) {
    this.dashboardViewMode = mode;
    const btnBal = document.getElementById("view-mode-btn-balances");
    const btnTrd = document.getElementById("view-mode-btn-trends");
    const trendWinCtrl = document.getElementById("trend-window-control");
    if (btnBal) btnBal.className = mode === 'balances' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    if (btnTrd) btnTrd.className = mode === 'trends' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    if (trendWinCtrl) trendWinCtrl.style.display = mode === 'trends' ? 'flex' : 'none';
    if (this.lastCompData && window._lastProviders) {
      this.renderComparison(this.lastCompData, window._lastProviders);
    }
  },

  switchTab(target) {
    document.querySelectorAll(".nav-tab").forEach(t => {
      t.classList.toggle("active", t.getAttribute("data-tab") === target);
    });
    document.querySelectorAll(".tab-content").forEach(c => {
      c.classList.toggle("active", c.id === `tab-${target}`);
    });
    this.activeTab = target;
  },

  async loadSettings() {
    try {
      const res = await fetch("/api/settings");
      if (!res.ok) return;
      const st = await res.json();
      this.appSettings = st;

      const autoResize = document.getElementById("cfg-widget-auto-resize");
      const fadeUnpinned = document.getElementById("cfg-widget-fade-unpinned");
      const hideParentExpand = document.getElementById("cfg-widget-hide-parent-on-expand");
      const showAxisLabels = document.getElementById("cfg-show-axis-labels");
      const themeSelect = document.getElementById("cfg-widget-theme");
      const pollCadence = document.getElementById("cfg-poll-cadence");
      const ollamaSync = document.getElementById("cfg-ollama-sync");
      const viewModeSelect = document.getElementById("cfg-default-view-mode");

      if (autoResize && st.widget_auto_resize !== undefined) autoResize.checked = !!st.widget_auto_resize;
      if (fadeUnpinned && st.widget_fade_unpinned !== undefined) fadeUnpinned.checked = !!st.widget_fade_unpinned;
      if (hideParentExpand && st.widget_hide_parent_chart_on_expand !== undefined) hideParentExpand.checked = !!st.widget_hide_parent_chart_on_expand;
      if (showAxisLabels && st.show_axis_labels !== undefined) {
        showAxisLabels.checked = !!st.show_axis_labels;
        this.showAxisLabels = !!st.show_axis_labels;
      }
      if (themeSelect && st.widget_theme) themeSelect.value = st.widget_theme;
      if (pollCadence && st.poll_cadence_seconds) pollCadence.value = st.poll_cadence_seconds;
      if (ollamaSync && st.ollama_sync_interval) ollamaSync.value = st.ollama_sync_interval;
      if (viewModeSelect && st.widget_view_mode) viewModeSelect.value = st.widget_view_mode;

      const fontRadios = document.querySelectorAll("input[name='cfg-font-scale']");
      if (st.widget_font_size && fontRadios.length) {
        fontRadios.forEach(r => r.checked = (r.value === st.widget_font_size));
      }

      const pinnedList = Array.isArray(st.pinned_items) ? st.pinned_items : ["claude", "gemini", "ollama"];
      document.querySelectorAll(".cfg-pin-check").forEach(chk => {
        chk.checked = pinnedList.includes(chk.value);
      });

      // Platform Visibility Toggles (AIUM-613)
      const hiddenPlatforms = (st.estate_visibility?.hidden_platforms || []).map(p => p.toLowerCase());
      ["claude", "gemini", "chatgpt", "ollama", "copilot"].forEach(p => {
        const chk = document.getElementById(`vis-chk-${p}`);
        if (chk) chk.checked = !hiddenPlatforms.includes(p);
      });
    } catch (e) {
      console.warn("Error loading settings:", e);
    }
  },

  async saveSettings() {
    const autoResize = document.getElementById("cfg-widget-auto-resize");
    const fadeUnpinned = document.getElementById("cfg-widget-fade-unpinned");
    const hideParentExpand = document.getElementById("cfg-widget-hide-parent-on-expand");
    const showAxisLabels = document.getElementById("cfg-show-axis-labels");
    const themeSelect = document.getElementById("cfg-widget-theme");
    const pollCadence = document.getElementById("cfg-poll-cadence");
    const ollamaSync = document.getElementById("cfg-ollama-sync");
    const viewModeSelect = document.getElementById("cfg-default-view-mode");

    const checkedFont = document.querySelector("input[name='cfg-font-scale']:checked");
    const pinned = [];
    document.querySelectorAll(".cfg-pin-check:checked").forEach(c => pinned.push(c.value));

    const hiddenPlatforms = [];
    ["claude", "gemini", "chatgpt", "ollama", "copilot"].forEach(p => {
      const chk = document.getElementById(`vis-chk-${p}`);
      if (chk && !chk.checked) hiddenPlatforms.push(p);
    });

    const payload = {
      widget_auto_resize: autoResize ? autoResize.checked : true,
      widget_fade_unpinned: fadeUnpinned ? fadeUnpinned.checked : false,
      widget_hide_parent_chart_on_expand: hideParentExpand ? hideParentExpand.checked : false,
      show_axis_labels: showAxisLabels ? showAxisLabels.checked : true,
      widget_theme: themeSelect ? themeSelect.value : "obsidian_neon",
      widget_font_size: checkedFont ? checkedFont.value : "standard",
      poll_cadence_seconds: pollCadence ? parseInt(pollCadence.value, 10) || 4 : 4,
      ollama_sync_interval: ollamaSync ? parseInt(ollamaSync.value, 10) || 15 : 15,
      widget_view_mode: viewModeSelect ? viewModeSelect.value : "balances",
      pinned_items: pinned,
      estate_visibility: {
        hidden_platforms: hiddenPlatforms,
        hidden_accounts: [],
        hidden_tags: []
      }
    };

    if (showAxisLabels) {
      this.showAxisLabels = showAxisLabels.checked;
    }

    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        const data = await res.json();
        this.appSettings = data.settings || payload;
        // Also persist to visibility endpoint
        fetch("/api/settings/visibility", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload.estate_visibility)
        }).catch(() => {});
        alert("✅ Configuration successfully saved and encrypted into Windows DPAPI storage!");
        if (this.lastCompData && window._lastProviders) {
          this.renderComparison(this.lastCompData, window._lastProviders);
        }
      }
    } catch (e) {
      alert("❌ Error saving settings: " + e.message);
    }
  },

  async testOllamaConnection() {
    const resBox = document.getElementById("ollama-probe-result");
    if (resBox) resBox.innerText = "Probing http://localhost:11434...";
    try {
      const res = await fetch("/api/providers/ollama/models");
      if (res.ok) {
        const data = await res.json();
        const instCount = (data.installed || []).length;
        const runCount = (data.running || []).length;
        if (resBox) {
          resBox.innerText = `✅ Connected! ${instCount} models installed on disk, ${runCount} loaded in memory/VRAM.`;
          resBox.style.color = "#34d399";
        }
      } else {
        if (resBox) {
          resBox.innerText = "⚠️ Ollama daemon responded with error or offline. Offline simulation fallback active.";
          resBox.style.color = "#fbbf24";
        }
      }
    } catch (e) {
      if (resBox) {
        resBox.innerText = `❌ Connection error: ${e.message}`;
        resBox.style.color = "#f43f5e";
      }
    }
  },

  async loadCrossPlatformTags() {
    const tbody = document.getElementById("tags-table-body");
    if (!tbody) return;
    try {
      const res = await fetch("/api/tags");
      if (!res.ok) return;
      const tags = await res.json();

      if (!tags || tags.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" style="text-align: center; color: var(--text-dim); padding: 20px;">
              No cross-platform grouping tags defined yet. Add a tag above to group items across Claude, Gemini, and Ollama.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = tags.map(t => `
        <tr>
          <td>
            <span class="badge" style="background: rgba(6, 182, 212, 0.15); color: var(--accent-cyan); font-weight: 700; border: 1px solid rgba(6, 182, 212, 0.3);">
              🏷️ ${this.escapeHtml(t.tag_name)}
            </span>
          </td>
          <td style="font-size: 0.82rem; color: #cbd5e1; text-transform: uppercase;">${this.escapeHtml(t.target_type)}</td>
          <td><strong style="color: #60a5fa; font-family: var(--font-mono); font-size: 0.85rem;">${this.escapeHtml(t.target_identifier)}</strong></td>
          <td style="font-size: 0.8rem; color: var(--text-muted);">${this.escapeHtml(t.description || '—')}</td>
          <td style="font-size: 0.75rem; color: var(--text-dim); font-family: var(--font-mono);">${this.escapeHtml((t.created_at || '').substring(0, 10))}</td>
          <td style="text-align: right;">
            <button class="btn btn-sm btn-danger" onclick="window.App.deleteCrossPlatformTag('${this.escapeHtml(t.id)}')" style="font-size: 0.72rem; padding: 2px 8px;">
              ✕ Remove
            </button>
          </td>
        </tr>
      `).join("");
    } catch (e) {
      console.warn("Error loading tags:", e);
    }
  },

  async addCrossPlatformTag() {
    const nameEl = document.getElementById("new-tag-name");
    const typeEl = document.getElementById("new-tag-type");
    const idEl = document.getElementById("new-tag-identifier");
    const descEl = document.getElementById("new-tag-desc");

    const tag_name = nameEl ? nameEl.value.trim() : "";
    const target_type = typeEl ? typeEl.value.trim() : "provider";
    const target_identifier = idEl ? idEl.value.trim() : "";
    const description = descEl ? descEl.value.trim() : "";

    if (!tag_name || !target_identifier) {
      alert("⚠️ Tag Name and Target Identifier are required.");
      return;
    }

    try {
      const res = await fetch("/api/tags", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tag_name, target_type, target_identifier, description })
      });
      if (res.ok) {
        if (nameEl) nameEl.value = "";
        if (idEl) idEl.value = "";
        if (descEl) descEl.value = "";
        await this.loadCrossPlatformTags();
      }
    } catch (e) {
      alert("❌ Error adding tag: " + e.message);
    }
  },

  async deleteCrossPlatformTag(tagId) {
    if (!confirm("Are you sure you want to remove this grouping tag?")) return;
    try {
      const res = await fetch("/api/tags/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tag_id: tagId })
      });
      if (res.ok) {
        await this.loadCrossPlatformTags();
      }
    } catch (e) {
      alert("❌ Error removing tag: " + e.message);
    }
  },

  switchTab(target) {
    document.querySelectorAll(".nav-tab").forEach(t => {
      if (t.getAttribute("data-tab") === target) {
        t.classList.add("active");
      } else {
        t.classList.remove("active");
      }
    });
    document.querySelectorAll(".tab-content").forEach(c => {
      if (c.id === `tab-${target}`) {
        c.classList.add("active");
      } else {
        c.classList.remove("active");
      }
    });
    if (target === "capacity") {
      this.loadCapacityAnalytics();
    }
    if (target === "benchmarks") {
      this.loadBenchmarkScorecard();
    }
  },

  async loadCapacityAnalytics() {
    try {
      const [tRes, fRes, rRes] = await Promise.all([
        fetch("/api/analytics/throughput"),
        fetch("/api/analytics/forecast"),
        fetch("/api/analytics/recommendations")
      ]);

      if (tRes.ok) {
        const tData = await tRes.json();
        const m = tData.throughput || {};
        const velEl = document.getElementById("cap-velocity-val");
        if (velEl) velEl.innerHTML = `${Number(m.tokens_per_minute || 0).toLocaleString()} <span style="font-size: 0.75rem; font-weight: normal; color: var(--text-muted);">tok/min</span>`;
        
        const burstEl = document.getElementById("cap-burst-val");
        if (burstEl) {
          const factor = Number(m.burst_factor || 1.0).toFixed(1);
          burstEl.innerText = `${factor}x`;
          if (m.is_bursting) {
            burstEl.style.color = "#f43f5e";
          } else {
            burstEl.style.color = "#fbbf24";
          }
        }
        const burstSub = document.getElementById("cap-burst-sub");
        if (burstSub) {
          burstSub.innerText = m.is_bursting ? "⚡ Spike Detected (>2.0x)" : "Baseline sustained";
        }

        const r24El = document.getElementById("cap-rolling24-val");
        if (r24El) r24El.innerHTML = `${Number(m.rolling_24h_tokens || 0).toLocaleString()} <span style="font-size: 0.75rem; font-weight: normal; color: var(--text-muted);">tok</span>`;
      }

      if (fRes.ok) {
        const fData = await fRes.json();
        const provs = fData.providers || {};
        const tbody = document.getElementById("cap-forecast-tbody");
        if (tbody) {
          const displayNames = {
            claude: "Claude (Anthropic)",
            gemini: "Google Gemini",
            chatgpt: "ChatGPT",
            ollama: "Ollama (Local Engine)",
            copilot: "M365 Copilot"
          };
          let html = "";
          for (const [key, item] of Object.entries(provs)) {
            const sev = item.severity || "HEALTHY";
            const sevBadge = sev === "CRITICAL"
              ? '<span class="badge" style="background: rgba(244,63,94,0.2); color: #f43f5e; border: 1px solid rgba(244,63,94,0.4);">CRITICAL</span>'
              : (sev === "WARNING"
                ? '<span class="badge" style="background: rgba(245,158,11,0.2); color: #fbbf24; border: 1px solid rgba(245,158,11,0.4);">WARNING</span>'
                : '<span class="badge" style="background: rgba(16,185,129,0.2); color: #34d399; border: 1px solid rgba(16,185,129,0.4);">SUSTAINABLE</span>');

            const tteStr = item.time_to_exhaustion_minutes > 1440
              ? "> 24 Hours"
              : (item.time_to_exhaustion_minutes > 60
                ? `${item.time_to_exhaustion_hours} Hours`
                : `${Math.round(item.time_to_exhaustion_minutes)} Minutes`);

            html += `
              <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
                <td style="padding: 10px 8px; font-weight: 600; color: #fff;">
                  ${displayNames[key] || key}
                </td>
                <td style="padding: 10px 8px; font-family: var(--font-mono); color: ${item.session_remaining_pct < 20 ? '#f43f5e' : '#38bdf8'}; font-weight: bold;">
                  ${item.session_remaining_pct}% rem
                </td>
                <td style="padding: 10px 8px; font-family: var(--font-mono); color: #c084fc;">
                  ${item.weekly_remaining_pct}% rem
                </td>
                <td style="padding: 10px 8px; font-family: var(--font-mono); color: var(--accent-cyan);">
                  ${Number(item.tokens_per_minute).toLocaleString()} tok/min
                </td>
                <td style="padding: 10px 8px; font-family: var(--font-mono); color: ${sev === 'CRITICAL' ? '#f43f5e' : (sev === 'WARNING' ? '#fbbf24' : '#cbd5e1')}; font-weight: 600;">
                  ${tteStr}
                </td>
                <td style="padding: 10px 8px;">
                  ${sevBadge}
                  <div style="font-size: 0.68rem; color: var(--text-dim); margin-top: 2px;">${item.alert_message || ''}</div>
                </td>
              </tr>
            `;
          }
          tbody.innerHTML = html;
        }
      }

      if (rRes.ok) {
        const rData = await rRes.json();
        const recs = rData.recommendations || [];
        const container = document.getElementById("cap-recommendations-container");
        if (container) {
          let html = "";
          let totalSav = 0;
          for (const rec of recs) {
            totalSav += (rec.potential_savings_usd || 0);
            const prioColor = rec.priority === "HIGH" ? "#f43f5e" : (rec.priority === "MEDIUM" ? "#fbbf24" : "#38bdf8");
            html += `
              <div style="background: rgba(0, 0, 0, 0.35); border: 1px solid rgba(255, 255, 255, 0.08); border-left: 3px solid ${prioColor}; border-radius: 8px; padding: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                  <strong style="font-size: 0.85rem; color: #fff;">${rec.title}</strong>
                  <span class="badge" style="font-size: 0.65rem; border-color: ${prioColor}; color: ${prioColor};">${rec.priority}</span>
                </div>
                <p style="font-size: 0.75rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 10px;">
                  ${rec.description}
                </p>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  ${rec.potential_savings_usd > 0 ? `<span style="font-size: 0.72rem; color: #34d399; font-weight: 600;">💰 Potential ROI: +$${rec.potential_savings_usd.toFixed(2)}/day</span>` : '<span></span>'}
                  <button class="btn btn-secondary btn-sm" onclick="window.App.switchTab('providers')" style="font-size: 0.7rem; padding: 3px 8px;">
                    ${rec.action_label} ↗
                  </button>
                </div>
              </div>
            `;
          }
          container.innerHTML = html;

          const savValEl = document.getElementById("cap-savings-val");
          if (savValEl) {
            savValEl.innerText = `$${totalSav.toFixed(2)}`;
          }
        }
      }
    } catch (e) {
      console.warn("Error loading capacity analytics:", e);
    }
  },

  // -------------------------------------------------------------
  // Multi-Account Profiles & Multi-Tenant Management (AIUM-608)
  // -------------------------------------------------------------
  accountProfiles: [],
  accountModalFilter: '',

  async loadAccountProfiles() {
    try {
      const res = await fetch('/api/accounts');
      if (!res.ok) return;
      const data = await res.json();
      this.accountProfiles = data.accounts || [];

      // Update provider card account select dropdowns
      const providers = ['claude', 'gemini', 'chatgpt', 'ollama', 'copilot'];
      providers.forEach(p => {
        const sel = document.getElementById(`hub-account-select-${p}`);
        if (!sel) return;
        const matching = this.accountProfiles.filter(a => a.provider === p);
        if (matching.length === 0) {
          sel.innerHTML = `<option value="">Default Profile</option>`;
        } else {
          sel.innerHTML = matching.map(a => `
            <option value="${this.escapeHtml(a.account_id)}" ${a.is_active ? 'selected' : ''}>
              ${this.escapeHtml(a.account_name || a.account_id)} ${a.is_active ? '★ (Active)' : ''}
            </option>
          `).join('');
        }
      });

      // Update Reports Account filter dropdown
      const repAcctSel = document.getElementById('report-filter-account');
      if (repAcctSel) {
        const curVal = repAcctSel.value;
        let optHtml = '<option value="">All Accounts (Aggregate)</option>';
        this.accountProfiles.forEach(a => {
          optHtml += `<option value="${this.escapeHtml(a.account_id)}">${this.escapeHtml(a.provider.toUpperCase())}: ${this.escapeHtml(a.account_name || a.account_id)}</option>`;
        });
        repAcctSel.innerHTML = optHtml;
        if (curVal) repAcctSel.value = curVal;
      }

      // Update multi-tenant count badge if present
      const countBadge = document.getElementById('multi-tenant-count-badge');
      if (countBadge) {
        countBadge.innerText = `Total Profiles: ${this.accountProfiles.length}`;
      }
    } catch (e) {
      console.warn("Failed to load account profiles:", e);
    }
  },

  async switchActiveAccount(provider, accountId) {
    if (!accountId) return;
    try {
      const res = await fetch('/api/accounts/active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, account_id: accountId })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        console.log(`[Account] Switched active profile for ${provider} to ${accountId}`);
        await this.loadAccountProfiles();
        await this.loadUsageData();
        await this.loadHistoricalReport();
        if (document.getElementById('account-profile-modal')?.style.display === 'flex') {
          this.renderAccountProfilesList();
        }
      } else {
        alert(data.error || "Failed to switch active account");
      }
    } catch (e) {
      console.error("Error switching active account:", e);
      alert("Error switching active account");
    }
  },

  openAccountModal(targetProvider = '') {
    this.accountModalFilter = targetProvider || '';
    const formProv = document.getElementById('acct-form-provider');
    if (formProv && targetProvider) {
      formProv.value = targetProvider;
    }
    this.filterAccountModalProvider(this.accountModalFilter);
    const modal = document.getElementById('account-profile-modal');
    if (modal) modal.style.display = 'flex';
  },

  closeAccountModal() {
    const modal = document.getElementById('account-profile-modal');
    if (modal) modal.style.display = 'none';
  },

  filterAccountModalProvider(provider) {
    this.accountModalFilter = provider;
    ['all', 'claude', 'gemini', 'chatgpt', 'ollama', 'copilot'].forEach(p => {
      const btn = document.getElementById(`acct-tab-${p}`);
      if (btn) {
        const matches = (p === 'all' && !provider) || (p === provider);
        btn.className = `btn btn-sm ${matches ? 'btn-primary' : 'btn-secondary'}`;
      }
    });
    this.renderAccountProfilesList();
  },

  renderAccountProfilesList() {
    const listEl = document.getElementById('acct-modal-profiles-list');
    const countEl = document.getElementById('acct-modal-count-label');
    if (!listEl) return;

    let items = this.accountProfiles;
    if (this.accountModalFilter) {
      items = items.filter(a => a.provider === this.accountModalFilter);
    }

    if (countEl) {
      countEl.innerText = `${items.length} ${this.accountModalFilter ? this.accountModalFilter.toUpperCase() : 'Configured'} Profile(s)`;
    }

    if (items.length === 0) {
      listEl.innerHTML = `
        <div style="padding: 16px; text-align: center; color: var(--text-dim); background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); font-size: 0.82rem;">
          No profiles registered yet ${this.accountModalFilter ? 'for ' + this.accountModalFilter : ''}. Use the form below to register your first profile.
        </div>
      `;
      return;
    }

    const provIcons = {
      claude: '🟠',
      gemini: '💎',
      chatgpt: '🟢',
      ollama: '🦙',
      copilot: '🔵'
    };

    listEl.innerHTML = items.map(a => `
      <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid ${a.is_active ? 'rgba(99, 102, 241, 0.4)' : 'rgba(255,255,255,0.06)'}; border-radius: var(--radius-sm); padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;">
        <div style="display: flex; align-items: center; gap: 10px;">
          <span style="font-size: 1.2rem;">${provIcons[a.provider] || '⚙️'}</span>
          <div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <strong style="font-size: 0.86rem; color: #fff;">${this.escapeHtml(a.account_name || a.account_id)}</strong>
              ${a.is_active ? '<span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 0.68rem; padding: 2px 6px;">Active Profile</span>' : '<span class="badge" style="background: rgba(100, 116, 139, 0.2); color: #94a3b8; font-size: 0.68rem; padding: 2px 6px;">Inactive</span>'}
              <span class="badge" style="background: rgba(139, 92, 246, 0.15); color: #c4b5fd; font-size: 0.68rem; padding: 2px 6px;">${this.escapeHtml(a.plan_type || 'Pro')}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 10px; margin-top: 3px; font-size: 0.74rem; color: var(--text-muted); font-family: var(--font-mono);">
              <span>ID: ${this.escapeHtml(a.account_id)}</span>
              ${a.has_credentials ? '<span style="color: #a5b4fc;">🔒 DPAPI Encrypted</span>' : '<span style="color: var(--text-dim);">No vaulted key</span>'}
            </div>
          </div>
        </div>

        <div style="display: flex; align-items: center; gap: 8px;">
          ${!a.is_active ? `
            <button class="btn btn-secondary btn-sm" onclick="window.App.switchActiveAccount('${a.provider}', '${this.escapeHtml(a.account_id)}')" style="font-size: 0.72rem; padding: 4px 10px; border-color: rgba(99, 102, 241, 0.4); color: #818cf8;">
              ✓ Set Active
            </button>
          ` : ''}
          <button class="btn btn-secondary btn-sm" onclick="window.App.deleteAccountProfile('${a.provider}', '${this.escapeHtml(a.account_id)}')" style="font-size: 0.72rem; padding: 4px 8px; border-color: rgba(239, 68, 68, 0.3); color: #f87171;" title="Delete profile and purge vaulted credentials">
            🗑
          </button>
        </div>
      </div>
    `).join('');
  },

  async submitAccountProfileForm() {
    const provEl = document.getElementById('acct-form-provider');
    const nameEl = document.getElementById('acct-form-name');
    const idEl = document.getElementById('acct-form-id');
    const planEl = document.getElementById('acct-form-plan');
    const keyEl = document.getElementById('acct-form-key');
    const activeEl = document.getElementById('acct-form-active');

    const provider = provEl ? provEl.value.trim().toLowerCase() : 'claude';
    const account_id = idEl ? idEl.value.trim() : '';
    const account_name = nameEl ? nameEl.value.trim() : account_id;
    const plan_type = planEl ? planEl.value.trim() : 'Pro';
    const api_key = keyEl ? keyEl.value.trim() : '';
    const is_active = activeEl ? activeEl.checked : true;

    if (!account_id) {
      alert("Please enter an Account ID, Email, or Org Identifier.");
      return;
    }

    try {
      const res = await fetch('/api/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          account_id,
          account_name,
          plan_type,
          api_key: api_key || undefined,
          is_active
        })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        if (keyEl) keyEl.value = '';
        if (nameEl) nameEl.value = '';
        if (idEl) idEl.value = '';
        await this.loadAccountProfiles();
        this.renderAccountProfilesList();
      } else {
        alert(data.error || "Failed to register account profile");
      }
    } catch (e) {
      console.error("Error submitting account profile:", e);
      alert("Error saving account profile");
    }
  },

  async deleteAccountProfile(provider, accountId) {
    if (!confirm(`Are you sure you want to delete profile '${accountId}' for ${provider}? Stored DPAPI credentials will be removed.`)) {
      return;
    }
    try {
      const res = await fetch('/api/accounts/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, account_id: accountId })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        await this.loadAccountProfiles();
        this.renderAccountProfilesList();
      } else {
        alert(data.error || "Failed to delete account profile");
      }
    } catch (e) {
      console.error("Error deleting account profile:", e);
      alert("Error deleting account profile");
    }
  },

  // -------------------------------------------------------------
  // Model Benchmarks, Quality Evals & Security Suite (AIUM-609)
  // -------------------------------------------------------------
  handleBenchmarkProviderChange() {
    const provSel = document.getElementById("bench-select-provider");
    const modelInp = document.getElementById("bench-input-model");
    if (!provSel || !modelInp) return;
    const prov = provSel.value;
    const defaults = {
      claude: "claude-3-7-sonnet",
      gemini: "gemini-2.0-flash",
      ollama: "llama3:8b",
      chatgpt: "gpt-4o",
      copilot: "m365-copilot-chat"
    };
    modelInp.value = defaults[prov] || "default-model";
  },

  async loadBenchmarkScorecard() {
    try {
      const [lbRes, resRes] = await Promise.all([
        fetch('/api/benchmarks/leaderboard'),
        fetch('/api/benchmarks/results?limit=25')
      ]);

      if (lbRes.ok) {
        const lbData = await lbRes.json();
        this.renderBenchmarkLeaderboard(lbData.leaderboard || []);
      }
      if (resRes.ok) {
        const resData = await resRes.json();
        this.renderBenchmarkResults(resData.evaluations || []);
      }
    } catch (e) {
      console.warn("Failed to load benchmark scorecard:", e);
    }
  },

  renderBenchmarkLeaderboard(leaderboard) {
    const tbody = document.getElementById("benchmark-leaderboard-body");
    if (!tbody) return;

    if (!leaderboard || leaderboard.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" style="padding: 24px; text-align: center; color: var(--text-dim);">
            No benchmark runs recorded yet. Click "Run Benchmark Suite Now" above to evaluate your first model!
          </td>
        </tr>
      `;
      return;
    }

    const ratingColors = {
      "A+": "#34d399",
      "A": "#10b981",
      "B+": "#38bdf8",
      "B": "#fbbf24",
      "C": "#f87171"
    };

    const provIcons = {
      claude: "🟠",
      gemini: "💎",
      chatgpt: "🟢",
      ollama: "🦙",
      copilot: "🔵"
    };

    tbody.innerHTML = leaderboard.map(m => {
      const col = ratingColors[m.overall_rating] || "#94a3b8";
      const icon = provIcons[m.provider] || "⚙️";
      return `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
          <td style="padding: 12px 14px;">
            <span class="badge" style="background: ${col}20; color: ${col}; font-weight: 800; font-size: 0.8rem; border: 1px solid ${col}40;">
              ${m.overall_rating}
            </span>
          </td>
          <td style="padding: 12px 14px;">
            <div style="font-weight: 700; color: #fff;">${icon} ${this.escapeHtml(m.model_name)}</div>
            <div style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase;">${this.escapeHtml(m.provider)}</div>
          </td>
          <td style="padding: 12px 14px;">
            <div style="font-family: var(--font-mono); font-size: 0.95rem; font-weight: 700; color: ${m.avg_score >= 90 ? '#34d399' : '#38bdf8'};">
              ${m.avg_score}%
            </div>
            <div style="font-size: 0.7rem; color: var(--text-dim);">${m.total_passes} pass / ${m.total_fails} fail</div>
          </td>
          <td style="padding: 12px 14px; font-family: var(--font-mono); font-size: 0.85rem; color: #e2e8f0;">
            ${m.avg_ttft_ms} ms
          </td>
          <td style="padding: 12px 14px; font-family: var(--font-mono); font-size: 0.85rem; color: #38bdf8;">
            ${m.avg_tps} tok/s
          </td>
          <td style="padding: 12px 14px;">
            <span class="badge" style="background: rgba(255,255,255,0.06); color: #cbd5e1; font-size: 0.72rem;">
              ${this.escapeHtml(m.cost_tier)}
            </span>
          </td>
          <td style="padding: 12px 14px; font-size: 0.78rem; color: var(--text-dim);">
            ${m.total_runs} run(s)
          </td>
          <td style="padding: 12px 14px;">
            <button class="btn btn-secondary btn-sm" onclick="window.App.rerunBenchmark('${m.provider}', '${this.escapeHtml(m.model_name)}')" style="font-size: 0.7rem; padding: 3px 8px;">
              ⚡ Run Again
            </button>
          </td>
        </tr>
      `;
    }).join("");
  },

  renderBenchmarkResults(evaluations) {
    const tbody = document.getElementById("benchmark-results-body");
    if (!tbody) return;

    if (!evaluations || evaluations.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" style="padding: 20px; text-align: center; color: var(--text-dim);">
            No evaluation runs recorded yet.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = evaluations.map(e => `
      <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
        <td style="padding: 10px 14px; font-family: var(--font-mono); font-size: 0.76rem; color: #a5b4fc;">
          ${this.escapeHtml(e.id)}
        </td>
        <td style="padding: 10px 14px; font-weight: 600; color: #f8fafc;">
          ${this.escapeHtml(e.model_name)}
        </td>
        <td style="padding: 10px 14px; font-size: 0.74rem; color: var(--text-dim);">
          ${this.escapeHtml(e.suite_name || 'full')}
        </td>
        <td style="padding: 10px 14px; font-size: 0.76rem;">
          <span style="color: #34d399; font-weight: 600;">${e.pass_count} P</span> / <span style="color: #f87171;">${e.fail_count} F</span>
        </td>
        <td style="padding: 10px 14px; font-family: var(--font-mono); font-weight: 700; color: ${e.score_pct >= 90 ? '#34d399' : '#38bdf8'};">
          ${e.score_pct}%
        </td>
        <td style="padding: 10px 14px; font-family: var(--font-mono); font-size: 0.78rem; color: #cbd5e1;">
          ${e.ttft_ms} ms
        </td>
        <td style="padding: 10px 14px; font-size: 0.72rem; color: var(--text-dim);">
          ${e.recorded_at ? e.recorded_at.substring(0, 19).replace('T', ' ') : 'N/A'}
        </td>
      </tr>
    `).join("");
  },

  rerunBenchmark(provider, modelName) {
    const provSel = document.getElementById("bench-select-provider");
    const modelInp = document.getElementById("bench-input-model");
    if (provSel) provSel.value = provider;
    if (modelInp) modelInp.value = modelName;
    this.triggerBenchmarkRun();
  },

  async triggerBenchmarkRun() {
    const provSel = document.getElementById("bench-select-provider");
    const modelInp = document.getElementById("bench-input-model");
    const btn = document.getElementById("btn-run-benchmark");
    const indicator = document.getElementById("bench-status-indicator");

    const provider = provSel ? provSel.value : 'claude';
    const model_name = modelInp ? modelInp.value.trim() : 'claude-3-7-sonnet';

    const suites = [];
    if (document.getElementById("suite-chk-coding")?.checked) suites.push("coding");
    if (document.getElementById("suite-chk-json")?.checked) suites.push("json_schema");
    if (document.getElementById("suite-chk-security")?.checked) suites.push("security");
    if (document.getElementById("suite-chk-retrieval")?.checked) suites.push("retrieval");

    if (suites.length === 0) {
      alert("Please select at least one evaluation suite.");
      return;
    }

    if (btn) {
      btn.disabled = true;
      btn.innerText = "⏳ Evaluating Model...";
    }
    if (indicator) {
      indicator.innerText = `Running ${suites.length} suites against ${model_name}...`;
      indicator.style.color = "#fbbf24";
    }

    try {
      const res = await fetch('/api/benchmarks/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model_name, suites })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        if (indicator) {
          indicator.innerText = `✓ Benchmark finished! Score: ${data.run.score_pct}% (${data.run.duration_ms}ms)`;
          indicator.style.color = "#34d399";
        }
        await this.loadBenchmarkScorecard();
      } else {
        alert(data.error || "Benchmark evaluation failed");
        if (indicator) {
          indicator.innerText = "❌ Benchmark run failed";
          indicator.style.color = "#f87171";
        }
      }
    } catch (e) {
      console.error("Error executing benchmark:", e);
      alert("Error executing model benchmark");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerText = "🚀 Run Benchmark Suite Now";
      }
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
