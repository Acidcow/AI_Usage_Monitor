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
  chartGranularity: 5,
  chartMode: 'interval_delta',
  chartWindow: '24h',
  chartBreakdown: 'locality',
  chartScopeFilter: 'all',
  refreshCadenceSeconds: 30,
  hierarchyGroupMode: 'all', // 'all' | 'platforms' | 'groups' | 'filtered'
  filteredItemIds: new Set(['claude', 'gemini', 'chatgpt', 'ollama', 'copilot', 'group-production', 'group-development', 'group-research']),
  hiddenChartSeries: {},
  showAxisLabels: true,
  cachedHierarchicalTrends: {},
  expandedHierarchy: {},
  lastCompData: null,
  lastProvidersData: null,
  appSettings: {},
  rawSessions: [],
  sessionSortCol: 'last_activity',
  sessionSortAsc: false,
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
    await this.loadSettings();
    await this.loadUsageData();
    await this.loadAccountProfiles();
    await this.loadHistoricalReport();
    await this.loadCrossPlatformTags();
    await this.loadManagedNodes();
    await this.loadClientQuotas();
    await this.loadDeviceInventory();
    await this.fetchDetectedAdapters();

    const urlParams = new URLSearchParams(window.location.search);
    const requestedTab = urlParams.get("tab");
    if (requestedTab) {
      this.switchTab(requestedTab);
    }

    // Start background auto-refresh respecting user-configured cadence (minimum 30s)
    this.resetPollingInterval(this.refreshCadenceSeconds || 30);
  },

  resetPollingInterval(seconds) {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    const sec = Math.max(30, Math.min(300, parseInt(seconds, 10) || 30));
    this.refreshCadenceSeconds = sec;
    this.pollInterval = setInterval(() => this.loadUsageData(), sec * 1000);
  },

  async changeRefreshCadence(seconds) {
    const sec = Math.max(30, Math.min(300, parseInt(seconds, 10) || 30));
    this.resetPollingInterval(sec);
    const topSelect = document.getElementById("ui-refresh-cadence-select");
    const cfgSelect = document.getElementById("cfg-ui-refresh-cadence");
    if (topSelect) topSelect.value = sec;
    if (cfgSelect) cfgSelect.value = sec;
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: { ui_refresh_interval_seconds: sec } })
      });
    } catch (e) {
      console.warn("Failed saving refresh cadence:", e);
    }
  },

  changeChartGranularity(val) {
    this.chartGranularity = parseInt(val, 10) || 5;
    this._lastLocalWindowUpdateTs = Date.now();
    const gSelect = document.getElementById("chart-granularity-select");
    const tSelect = document.getElementById("trend-granularity-select");
    if (gSelect) gSelect.value = this.chartGranularity;
    if (tSelect) tSelect.value = this.chartGranularity;
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: { active_chart_granularity: this.chartGranularity } })
    }).catch(() => {});
    this.loadUsageData();
  },

  changeChartMode(mode) {
    this.chartMode = mode === "cumulative" ? "cumulative" : "interval_delta";
    this._lastLocalWindowUpdateTs = Date.now();
    const mSelect = document.getElementById("chart-mode-select");
    const tSelect = document.getElementById("trend-mode-select");
    if (mSelect) mSelect.value = this.chartMode;
    if (tSelect) tSelect.value = this.chartMode;
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: { active_chart_mode: this.chartMode } })
    }).catch(() => {});
    this.loadUsageData();
  },

  changeChartWindow(win) {
    this.chartWindow = win || "24h";
    this.trendWindow = this.chartWindow;
    this.cachedHierarchicalTrends = {};
    this._lastLocalWindowUpdateTs = Date.now();
    const wSelect = document.getElementById("chart-window-select");
    const tSelect = document.getElementById("trend-window-select");
    const cfgWinSelect = document.getElementById("cfg-default-trend-window");
    if (wSelect) wSelect.value = this.chartWindow;
    if (tSelect) tSelect.value = this.chartWindow;
    if (cfgWinSelect) cfgWinSelect.value = this.chartWindow;
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        settings: {
          active_trend_window: this.chartWindow,
          default_trend_window: this.chartWindow
        }
      })
    }).catch(() => {});
    this.loadUsageData();
  },

  changeTrendGranularity(val) {
    this.changeChartGranularity(val);
  },

  changeChartBreakdown(val) {
    this.chartBreakdown = val || 'locality';
    const bSel = document.getElementById("chart-breakdown-select");
    if (bSel) bSel.value = this.chartBreakdown;
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: { active_chart_breakdown: this.chartBreakdown } })
    }).catch(() => {});
    this.loadUsageData();
  },

  changeChartScopeFilter(val) {
    this.chartScopeFilter = val || 'all';
    const sSel = document.getElementById("chart-scope-filter-select");
    if (sSel) sSel.value = this.chartScopeFilter;
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: { active_chart_scope_filter: this.chartScopeFilter } })
    }).catch(() => {});
    this.loadUsageData();
  },

  toggleTaxonomyDrawer() {
    const drawer = document.getElementById("unified-taxonomy-drawer");
    if (!drawer) return;
    drawer.style.display = drawer.style.display === "none" ? "block" : "none";
  },

  changeTrendMode(mode) {
    this.changeChartMode(mode);
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
      // Bidirectional alignment with Mini Widget settings (AIUM-903)
      if (!this._lastLocalWindowUpdateTs || (Date.now() - this._lastLocalWindowUpdateTs > 2500)) {
        try {
          const stRes = await fetch("/api/settings");
          if (stRes && stRes.ok) {
            const st = await stRes.json();
            this.appSettings = st;
            const remoteWin = st.active_trend_window || st.default_trend_window;
            if (remoteWin && remoteWin !== this.chartWindow) {
              this.chartWindow = remoteWin;
              this.trendWindow = remoteWin;
              this.cachedHierarchicalTrends = {};
              const wSel = document.getElementById("chart-window-select");
              const tSel = document.getElementById("trend-window-select");
              const cfgWinSel = document.getElementById("cfg-default-trend-window");
              if (wSel) wSel.value = remoteWin;
              if (tSel) tSel.value = remoteWin;
              if (cfgWinSel) cfgWinSel.value = remoteWin;
            }
            if (st.active_chart_granularity && Number(st.active_chart_granularity) !== Number(this.chartGranularity)) {
              this.chartGranularity = parseInt(st.active_chart_granularity, 10) || 5;
              const gSel = document.getElementById("chart-granularity-select");
              const tgSel = document.getElementById("trend-granularity-select");
              if (gSel) gSel.value = this.chartGranularity;
              if (tgSel) tgSel.value = this.chartGranularity;
            }
            if (st.active_chart_mode && st.active_chart_mode !== this.chartMode) {
              this.chartMode = st.active_chart_mode;
              const mSel = document.getElementById("chart-mode-select");
              const tmSel = document.getElementById("trend-mode-select");
              if (mSel) mSel.value = this.chartMode;
              if (tmSel) tmSel.value = this.chartMode;
            }
            if (st.widget_view_mode && (st.widget_view_mode === "balances" || st.widget_view_mode === "trends") && st.widget_view_mode !== this.dashboardViewMode) {
              this.dashboardViewMode = st.widget_view_mode;
              const btnBal = document.getElementById("view-mode-btn-balances");
              const btnTrd = document.getElementById("view-mode-btn-trends");
              const trendWinCtrl = document.getElementById("trend-window-control");
              if (btnBal) btnBal.className = this.dashboardViewMode === "balances" ? "btn btn-sm btn-primary" : "btn btn-sm btn-secondary";
              if (btnTrd) btnTrd.className = this.dashboardViewMode === "trends" ? "btn btn-sm btn-primary" : "btn btn-sm btn-secondary";
              if (trendWinCtrl) trendWinCtrl.style.display = this.dashboardViewMode === "trends" ? "flex" : "none";
            }
          }
        } catch (_syncErr) {}
      }

      const provSelect = document.getElementById("filter-session-provider");
      const providerParam = provSelect && provSelect.value ? `?provider=${provSelect.value}` : '';

      const bucketMinutes = this.chartGranularity || 5;
      const chartMode = this.chartMode || "interval_delta";
      const chartWindow = this.chartWindow || "24h";
      const chartBreakdown = this.chartBreakdown || "locality";
      const chartScopeFilter = this.chartScopeFilter || "all";

      const [summaryRes, providersRes, sessionsRes, errorsRes, timeseriesRes, compRes] = await Promise.all([
        fetch("/api/usage/summary"),
        fetch("/api/providers"),
        fetch(`/api/usage/sessions${providerParam}`),
        fetch("/api/diagnostics/errors?limit=30"),
        fetch(`/api/usage/timeseries?window=${chartWindow}&bucket_minutes=${bucketMinutes}&mode=${chartMode}&scope=${this.currentScope || 'individual'}&breakdown=${encodeURIComponent(chartBreakdown)}&scope_filter=${encodeURIComponent(chartScopeFilter)}`),
        fetch(`/api/usage/comparison?scope=${this.currentScope || 'individual'}&filter_visibility=true`)
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
        this.rawSessions = sessions || [];
        this.applySessionFilterAndSort();
      }

      if (errorsRes.ok) {
        const errors = await errorsRes.json();
        this.renderErrors(errors);
      }

      if (timeseriesRes.ok) {
        const timeseries = await timeseriesRes.json();
        this.renderSvgChart(timeseries);
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
      const inT = Number(summary.input_tokens_today || 0);
      const outT = Number(summary.output_tokens_today || 0);
      const ccT = Number(summary.cache_creation_tokens_today || 0);
      const crT = Number(summary.cache_read_tokens_today || 0);
      if (ccT > 0 || crT > 0) {
        breakdownEl.innerText = `In: ${inT.toLocaleString()} | Out: ${outT.toLocaleString()} | Cache R/W: ${(crT + ccT).toLocaleString()}`;
        breakdownEl.title = `Prompt In: ${inT.toLocaleString()} | Out: ${outT.toLocaleString()} | Cache Write: ${ccT.toLocaleString()} | Cache Read: ${crT.toLocaleString()}`;
      } else {
        breakdownEl.innerText = `In: ${inT.toLocaleString()} | Out: ${outT.toLocaleString()}`;
      }
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
    const trackingMode = this.appSettings?.quota_tracking_mode || comp.tracking_mode || 'individual';
    const isIndividualMode = (trackingMode === 'individual');

    // Update Usage Scope indicator and buttons to align with Tracking Mode
    const btnTeam = document.getElementById("scope-btn-team");
    const btnEnt = document.getElementById("scope-btn-enterprise");
    const indText = document.getElementById("active-scope-indicator");
    if (isIndividualMode) {
      if (btnTeam) btnTeam.style.display = "none";
      if (btnEnt) btnEnt.style.display = "none";
      if (indText) {
        indText.innerHTML = `👤 <strong>Individual Direct Tracking (1:1 Active)</strong> <span style="color: var(--text-dim); margin-left: 6px;">claude.ai/settings/usage</span>`;
      }
    } else {
      if (btnTeam) btnTeam.style.display = "";
      if (btnEnt) btnEnt.style.display = "";
      if (indText) {
        indText.innerText = this.currentScope === 'team' ? "Focused on Shared Team Workspace Pool" : (this.currentScope === 'enterprise' ? "Focused on Organization / Enterprise Rollup" : "Focused on Personal / Individual Limits");
      }
    }
    
    const predefinedGroups = [
      { id: "group-production", name: "Production AI (Claude + Gemini)", tag: "Production", icon: "🚀", providers: ["claude", "gemini"] },
      { id: "group-development", name: "Development & Testing (Ollama + Gemini)", tag: "Development", icon: "🧪", providers: ["ollama", "gemini"] },
      { id: "group-research", name: "Research & Labs (Claude + Ollama)", tag: "Research", icon: "🔬", providers: ["claude", "ollama"] }
    ];

    let itemsToRender = [];
    if (this.hierarchyGroupMode === "platforms") {
      itemsToRender = allKeys
        .filter(k => !hiddenPlatforms.includes(k))
        .map(k => ({ type: "platform", key: k }));
    } else if (this.hierarchyGroupMode === "groups") {
      itemsToRender = predefinedGroups
        .filter(g => g.providers.some(p => !hiddenPlatforms.includes(p)))
        .map(g => ({ type: "group", key: g.id, group: g }));
    } else if (this.hierarchyGroupMode === "filtered") {
      allKeys.forEach(k => {
        if (!hiddenPlatforms.includes(k) && this.filteredItemIds.has(k)) {
          itemsToRender.push({ type: "platform", key: k });
        }
      });
      predefinedGroups.forEach(g => {
        if (this.filteredItemIds.has(g.id) && g.providers.some(p => !hiddenPlatforms.includes(p))) {
          itemsToRender.push({ type: "group", key: g.id, group: g });
        }
      });
    } else {
      itemsToRender = allKeys
        .filter(k => !hiddenPlatforms.includes(k))
        .map(k => ({ type: "platform", key: k }))
        .concat(predefinedGroups
          .filter(g => g.providers.some(p => !hiddenPlatforms.includes(p)))
          .map(g => ({ type: "group", key: g.id, group: g })));
    }

    const provMap = comp.providers || {};
    let html = "";

    itemsToRender.forEach(itemEntry => {
      if (itemEntry.type === "platform") {
        const key = itemEntry.key;
        if (hiddenPlatforms.includes(key)) {
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
          ? `<span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; font-size: 0.65rem;" title="Calibrated with web quota from claude.ai/settings/usage">🟡 ${isIndividualMode ? '👤 Individual Direct Quota' : '🟡 Calibrated Web Quota'}</span>`
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
          const sessBalToks = item.session_tokens_available !== undefined ? item.session_tokens_available : null;
          const sessLimToks = item.session_tokens_limit || null;
          const weekBalToks = item.weekly_tokens_available !== undefined ? item.weekly_tokens_available : null;
          const weekLimToks = item.weekly_tokens_limit || item.weekly_allowance || null;

          sessionCellContent = `
            <div style="display: flex; flex-direction: column; gap: 4px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <div class="progress-bar-container" style="flex-grow: 1; height: 6px; margin: 0; background: rgba(255,255,255,0.06);">
                  <div class="progress-bar-fill" style="width: ${Math.max(4, sessionPct)}%; background: ${sessionPct < 20 ? 'var(--accent-rose)' : 'linear-gradient(90deg, #10b981, #06b6d4)'};"></div>
                </div>
                <span style="font-family: var(--font-mono); font-size: 0.75rem; width: 42px; text-align: right; color: #cbd5e1; font-weight: 600;">${sessionPct}%</span>
              </div>
              ${sessLimToks ? `
                <div style="display: flex; justify-content: space-between; font-size: 0.68rem; color: #94a3b8; font-family: var(--font-mono);">
                  <span>${Number(sessBalToks !== null ? sessBalToks : 0).toLocaleString()} / ${Number(sessLimToks).toLocaleString()} tok left</span>
                  ${item.session_reset_str ? `<span style="color: #38bdf8;">🕒 ${item.session_reset_str}</span>` : ''}
                </div>
              ` : ''}
            </div>
          `;
          weeklyCellContent = `
            <div style="display: flex; flex-direction: column; gap: 4px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <div class="progress-bar-container" style="flex-grow: 1; height: 6px; margin: 0; background: rgba(255,255,255,0.06);">
                  <div class="progress-bar-fill" style="width: ${Math.max(4, weeklyPct)}%; background: ${weeklyPct < 20 ? 'var(--accent-amber)' : 'linear-gradient(90deg, #8b5cf6, #3b82f6)'};"></div>
                </div>
                <span style="font-family: var(--font-mono); font-size: 0.75rem; width: 42px; text-align: right; color: #cbd5e1; font-weight: 600;">${weeklyPct}%</span>
              </div>
              ${weekLimToks ? `
                <div style="display: flex; justify-content: space-between; font-size: 0.68rem; color: #94a3b8; font-family: var(--font-mono);">
                  <span>${Number(weekBalToks !== null ? weekBalToks : 0).toLocaleString()} / ${Number(weekLimToks).toLocaleString()} tok left</span>
                </div>
              ` : ''}
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
                  <button class="btn btn-sm" onclick="window.App.toggleHierarchy('${key}')" style="background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); color: #38bdf8; font-size: 0.68rem; padding: 2px 7px; border-radius: 4px; cursor: pointer;" title="Toggle hierarchy details">
                    ${isExpanded ? '▲ Hide' : (isIndividualMode ? '▼ Details' : '▼ Drill-Down')}
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
                      ${key === 'ollama' ? 'LOCAL HARDWARE INFERENCE' : (isIndividualMode ? '1:1 INDIVIDUAL DIRECT TELEMETRY' : ('Active View: ' + (comp.active_scope || 'individual').toUpperCase()))}
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
                    ${(item.models && item.models.length > 0 ? item.models : []).map((m, mIdx) => {
                      const mCol = m.color || ["#c084fc", "#34d399", "#38bdf8", "#f59e0b"][mIdx % 4];
                      const mPts = this.getChildRealPoints('ollama', m.name || m.model);
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
                        ${this.generateInlineSparkline(this.getChildRealPoints('gemini', 'gemini_account'), '#60a5fa')}
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
                      const tPts = this.getChildRealPoints('gemini', t.id);
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
                        ${this.generateInlineSparkline(this.getChildRealPoints('claude', 'claude_individual'), '#38bdf8')}
                      </div>
                      <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                        <strong>5h Session:</strong> <span style="color: ${(ind.session_remaining_pct === 0 || item.session_tokens_available === 0) ? '#f87171' : '#38bdf8'}; font-weight: 700;">${(item.session_tokens_available !== undefined ? item.session_tokens_available : Math.round(((ind.session_remaining_pct ?? 100) / 100) * (item.session_tokens_limit || 200000))).toLocaleString()} tok</span> left (${ind.session_remaining_pct ?? 100}% rem, ${(item.session_tokens_used || 0).toLocaleString()} used)
                        ${(ind.session_remaining_pct === 0 || item.session_tokens_available === 0) ? '<span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171; font-size: 0.65rem; margin-left: 6px;">⚠️ Exhausted</span>' : ''}
                      </div>
                      <div style="font-size: 0.72rem; color: #38bdf8; margin-bottom: 4px; font-family: var(--font-mono);">
                        🕒 Resets in: <strong>${item.session_reset_str || ind.session_reset_str || '5h 0m'}</strong> (auto-refills upon expiry)
                      </div>
                      <div style="font-size: 0.76rem; color: #e2e8f0; margin-bottom: 3px;">
                        <strong>Weekly Quota:</strong> <span style="color: #38bdf8; font-weight: 700;">${(item.weekly_tokens_available !== undefined ? item.weekly_tokens_available : Math.round(((ind.weekly_remaining_pct ?? 100) / 100) * (item.weekly_tokens_limit || 1400000))).toLocaleString()} tok</span> left (${ind.weekly_remaining_pct ?? 100}% rem, ${(item.weekly_tokens_used || 0).toLocaleString()} used)
                      </div>
                      <div style="font-size: 0.69rem; color: var(--text-dim); margin-top: 5px;">
                        Weekly Reset: ${ind.weekly_reset_str || 'Mon 3:00 AM'}
                      </div>
                    </div>

                    ${(isIndividualMode || h.streamlined) ? '' : `
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
                        ${this.generateInlineSparkline(this.getChildRealPoints('claude', 'claude_team'), '#c084fc')}
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
                    <div style="background: rgba(160, 185, 129, 0.06); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 8px; padding: 10px 12px;">
                      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="display: flex; align-items: center; gap: 5px;">
                          <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: #34d399; flex-shrink: 0;"></span>
                          <strong style="color: #34d399; font-size: 0.82rem;">🏢 Department / Division</strong>
                        </span>
                        <span style="font-size: 0.68rem; color: var(--text-dim);">${dept.active_seats || 14} active seats</span>
                      </div>
                      <div style="margin-bottom: 6px;">
                        ${this.generateInlineSparkline(this.getChildRealPoints('claude', 'claude_department'), '#34d399')}
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
                        ${this.generateInlineSparkline(this.getChildRealPoints('claude', 'claude_enterprise'), '#fbbf24')}
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
                    `}
                  `)}
                </div>

                ${((item.accounts && item.accounts.length > 0) || (item.instances && item.instances.length > 0) || item.source_breakdown) ? `
                  <div style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed rgba(255, 255, 255, 0.1); display: flex; flex-direction: column; gap: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                      <span style="font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: #94a3b8;">
                        Distinct Accounts & Hardware Instances (${(item.accounts || []).length} Accounts • ${(item.instances || []).length} Instances)
                      </span>
                      ${item.source_breakdown ? `
                        <div style="display: flex; gap: 6px; align-items: center; font-size: 0.7rem; font-family: var(--font-mono);">
                          <span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399;" title="Direct upstream API calls">🌐 Direct: ${Number(item.source_breakdown.direct?.tokens || 0).toLocaleString()}</span>
                          <span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24;" title="Transparent Proxy (Port 8766)">⚡ Proxy: ${Number(item.source_breakdown.proxy?.tokens || 0).toLocaleString()}</span>
                          <span class="badge" style="background: rgba(168, 85, 247, 0.15); color: #c084fc;" title="Bridge Emulator (Port 11435)">🌉 Bridge: ${Number(item.source_breakdown.emulator?.tokens || 0).toLocaleString()}</span>
                          <span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8;" title="Local Log Scanner">📑 Log: ${Number(item.source_breakdown.log_scanner?.tokens || 0).toLocaleString()}</span>
                        </div>
                      ` : ''}
                    </div>

                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px;">
                      ${(item.accounts || []).map(acc => `
                        <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 6px 10px; display: flex; justify-content: space-between; align-items: center;">
                          <div style="display: flex; align-items: center; gap: 6px; overflow: hidden;">
                            <span style="font-size: 0.8rem;">👤</span>
                            <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                              <div style="font-size: 0.75rem; color: #e2e8f0; font-weight: 600;" title="${this.escapeHtml(acc.account_id)}">${this.escapeHtml(acc.account_id)}</div>
                              <div style="font-size: 0.65rem; color: var(--text-dim);">${acc.event_count || 0} calls</div>
                            </div>
                          </div>
                          <div style="text-align: right; font-family: var(--font-mono); font-size: 0.74rem;">
                            <div style="color: #38bdf8; font-weight: 700;">${Number(acc.tokens_today || 0).toLocaleString()} tok</div>
                            <div style="color: var(--text-dim); font-size: 0.66rem;">$${Number(acc.cost_today_usd || 0).toFixed(3)}</div>
                          </div>
                        </div>
                      `).join('')}

                      ${(item.instances || []).map(inst => `
                        <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 6px 10px; display: flex; justify-content: space-between; align-items: center;">
                          <div style="display: flex; align-items: center; gap: 6px; overflow: hidden;">
                            <span style="font-size: 0.8rem;">🖥️</span>
                            <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                              <div style="font-size: 0.75rem; color: #a78bfa; font-weight: 600;" title="${this.escapeHtml(inst.instance_id)}">${this.escapeHtml(inst.instance_id)}</div>
                              <div style="font-size: 0.65rem; color: var(--text-dim);">${inst.event_count || 0} runs</div>
                            </div>
                          </div>
                          <div style="text-align: right; font-family: var(--font-mono); font-size: 0.74rem;">
                            <div style="color: #34d399; font-weight: 700;">${Number(inst.tokens_today || 0).toLocaleString()} tok</div>
                            <div style="color: var(--text-dim); font-size: 0.66rem;">$${Number(inst.cost_today_usd || 0).toFixed(3)}</div>
                          </div>
                        </div>
                      `).join('')}
                    </div>
                  </div>
                ` : ''}
              </td>
            </tr>
          `;

          setTimeout(() => {
            this.loadAndRenderHierarchicalTrendChart(`trend-chart-svg-${key}`, key);
          }, 20);
        }
      } else if (itemEntry.type === "group") {
        const grp = itemEntry.group;
        const visibleGroupProviders = grp.providers.filter(p => !hiddenPlatforms.includes(p));
        if (visibleGroupProviders.length === 0) {
          return;
        }
        const gKey = grp.id;
        const isExpanded = !!this.expandedHierarchy[gKey];
        let grpTokens = 0;
        let grpCost = 0;
        visibleGroupProviders.forEach(p => {
          const pItem = provMap[p] || {};
          grpTokens += (pItem.tokens_today || 0);
          grpCost += (pItem.cost_today_usd || 0);
        });

        const grpSeries = visibleGroupProviders.map(p => {
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
                <span style="font-family: var(--font-mono); font-size: 0.74rem; color: #38bdf8;">${visibleGroupProviders.length} platforms</span>
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
                  ${visibleGroupProviders.map(p => {
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
                          ${this.generateInlineSparkline(this.getChildRealPoints(p, p + '_total'), pCol)}
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
    const hiddenPlatforms = (this.appSettings?.estate_visibility?.hidden_platforms || []).map(p => p.toLowerCase());
    ["claude", "copilot", "gemini", "ollama", "chatgpt"].forEach(p => {
      const pill = document.getElementById(`pill-${p}`);
      if (pill) {
        pill.style.display = hiddenPlatforms.includes(p) ? "none" : "inline-flex";
      }
    });

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
      const isGeminiPro = (providers["gemini"].plan_type || '').includes("Gemini Pro") || (providers["gemini"].account_id === "acidcow@gmail.com");
      if (geminiDot) geminiDot.className = `dot ${gActive ? 'dot-green' : (providers["gemini"].status === 'ERROR' ? 'dot-red' : 'dot-gray')}`;
      if (geminiStatusText) geminiStatusText.innerText = isGeminiPro ? "Gemini Pro (Active)" : (gActive ? "Active" : (providers["gemini"].status || "Ready"));
      if (hubGeminiStatus) {
        hubGeminiStatus.innerText = isGeminiPro ? "Active (Gemini Pro)" : (providers["gemini"].status || "Ready");
        hubGeminiStatus.style.color = gActive ? "#34d399" : (providers["gemini"].status === "ERROR" ? "#f87171" : "#60a5fa");
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

  renderSvgChart(timeseriesData) {
    const svg = document.getElementById("token-velocity-chart");
    const peakInfo = document.getElementById("chart-peak-info");
    const singleProvNotice = document.getElementById("chart-single-provider-notice");
    const legendContainer = document.getElementById("chart-legend-container");
    if (!svg) return;

    const hiddenPlatforms = (this.appSettings?.estate_visibility?.hidden_platforms || []).map(p => p.toLowerCase());
    const allKnownPlatforms = ["claude", "gemini", "chatgpt", "ollama", "copilot"];
    const activeBreakdown = timeseriesData?.breakdown || this.chartBreakdown || "locality";
    const breakdownSeries = Array.isArray(timeseriesData?.breakdown_series) ? timeseriesData.breakdown_series : [];

    let platforms = allKnownPlatforms.filter(p => !hiddenPlatforms.includes(p));
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

    const seriesList = timeseriesData?.series || [];
    const seriesMap = {};
    seriesList.forEach(s => {
      seriesMap[s.id] = s;
    });
    breakdownSeries.forEach(s => {
      seriesMap[s.id] = s;
    });

    if (activeBreakdown !== "consolidated" && breakdownSeries.length > 0) {
      platforms = [];
      breakdownSeries.forEach(bs => {
        const prov = String(bs.provider || "").toLowerCase();
        if (prov && hiddenPlatforms.includes(prov)) return;
        platforms.push(bs.id);
        platformColors[bs.id] = bs.color || "#38bdf8";
        platformNames[bs.id] = bs.label || bs.name || bs.id;
      });
    }

    if (legendContainer) {
      const renderPillsList = [...platforms, "total"];
      legendContainer.innerHTML = renderPillsList.map(pKey => {
        const col = platformColors[pKey] || "#38bdf8";
        const name = platformNames[pKey] || pKey;
        const s = seriesMap[pKey];
        const pTok = s ? (s.total_tokens || 0) : 0;
        const tokText = pTok > 0 ? (pTok >= 1000 ? `${(pTok / 1000).toFixed(1)}k` : `${pTok} t`) : "0 t (idle)";
        const isTot = pKey === "total";
        const badgeStyle = isTot
          ? "font-family: var(--font-mono); font-size: 0.68rem; padding: 1px 5px; border-radius: 4px; margin-left: 6px; font-weight: 700; background: rgba(6, 182, 212, 0.25); color: #06b6d4;"
          : (pTok > 0
            ? "font-family: var(--font-mono); font-size: 0.68rem; padding: 1px 5px; border-radius: 4px; margin-left: 6px; font-weight: 700; background: rgba(255, 255, 255, 0.15); color: #f8fafc;"
            : "font-family: var(--font-mono); font-size: 0.68rem; padding: 1px 5px; border-radius: 4px; margin-left: 6px; font-weight: 600; background: rgba(255, 255, 255, 0.05); color: #64748b;");
        const borderStyle = isTot ? `1px dashed ${col}` : `1px solid ${col}55`;
        return `
          <div class="chart-legend-pill" data-platform="${this.escapeHtml(pKey)}" style="display: inline-flex; align-items: center; gap: 6px; font-size: 0.75rem; color: #f8fafc; cursor: pointer; padding: 2px 8px; border-radius: 4px; background: rgba(15, 23, 42, 0.7); border: ${borderStyle};">
            <span style="display: inline-block; width: 14px; height: 3px; background: ${col}; border-radius: 2px;"></span>
            <strong>${this.escapeHtml(name)}</strong>
            <span class="legend-token-badge" style="${badgeStyle}">${tokText}</span>
          </div>
        `;
      }).join("");
    }

    const labels = timeseriesData?.labels || [];
    const keys = timeseriesData?.keys || [];
    const bucketMin = timeseriesData?.bucket_minutes || this.chartGranularity || 5;
    const chartMode = timeseriesData?.mode || this.chartMode || "interval_delta";
    const totalTokens = timeseriesData?.total_tokens || 0;
    const numPoints = labels.length;

    if (!timeseriesData || numPoints === 0) {
      svg.innerHTML = `
        <text x="450" y="95" text-anchor="middle" fill="#64748b" font-size="13" font-family="sans-serif">
          No usage telemetry recorded yet. Real-time multi-platform velocity curves will appear here when tokens are consumed.
        </text>
      `;
      if (peakInfo) peakInfo.innerText = "Peak: 0 tokens";
      if (singleProvNotice) singleProvNotice.style.display = "none";
      return;
    }

    let maxTokens = 50;
    seriesList.forEach(s => {
      const pts = s.points || [];
      pts.forEach(p => {
        if (p > maxTokens) maxTokens = p;
      });
    });

    if (peakInfo) {
      const modeSuffix = chartMode === "cumulative" ? "total run" : `/${bucketMin}m`;
      peakInfo.innerText = `Peak: ${maxTokens.toLocaleString()} tokens ${modeSuffix}`;
    }

    // Check single active platform dominance
    const activePlatforms = platforms.filter(p => (seriesMap[p]?.total_tokens || 0) > 0);
    if (singleProvNotice) {
      if (activePlatforms.length === 1 && totalTokens > 0) {
        const soleProv = activePlatforms[0];
        const soleName = platformNames[soleProv];
        const soleToks = seriesMap[soleProv]?.total_tokens || 0;
        singleProvNotice.style.display = "inline-flex";
        singleProvNotice.innerHTML = `ℹ️ <strong>${soleName}</strong> accounts for 100% of activity (${soleToks.toLocaleString()} tokens). Total Combined curve mirrors ${soleName}. Other platforms idle at 0 baseline.`;
      } else {
        singleProvNotice.style.display = "none";
      }
    }

    // SVG ViewBox dimensions: 900 x 200
    const width = 900;
    const height = 200;
    const padL = 60;
    const padR = 25;
    const padT = 20;
    const padB = 30;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;
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

    // Time axis labels along the bottom (localized to user's timezone)
    let axisHtml = "";
    const localLabels = (keys && keys.length === numPoints)
      ? keys.map(k => this.formatLocalTime(k))
      : labels;

    const labelInterval = Math.max(1, Math.ceil(numPoints / 10));
    localLabels.forEach((labelStr, idx) => {
      const showLabel = (idx % labelInterval === 0) || (idx === numPoints - 1);
      if (showLabel) {
        const x = padL + (idx * step);
        axisHtml += `
          <line x1="${x}" y1="${padT + plotH}" x2="${x}" y2="${padT + plotH + 4}" stroke="rgba(255,255,255,0.2)" stroke-width="1"/>
          <text x="${x}" y="${height - 8}" font-size="9" fill="#94a3b8" text-anchor="middle" font-family="monospace">${labelStr}</text>
        `;
      }
    });

    // Generate Path Data for each platform & total
    const seriesToRender = [...platforms, "total"];
    let defsHtml = `
      <defs>
        <linearGradient id="velocity-total-area-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#06b6d4" stop-opacity="0.22"/>
          <stop offset="100%" stop-color="#06b6d4" stop-opacity="0.02"/>
        </linearGradient>
      </defs>
    `;
    let areaHtml = "";
    let linesHtml = "";
    let dotsHtml = "";

    seriesToRender.forEach(seriesKey => {
      const color = platformColors[seriesKey];
      const isTotal = seriesKey === "total";
      const sObj = seriesMap[seriesKey];
      const rawPoints = sObj?.points || new Array(numPoints).fill(0);
      const points = [];

      rawPoints.forEach((tokVal, idx) => {
        const tok = Number(tokVal) || 0;
        const x = numPoints > 1 ? (padL + (idx * step)) : (padL + plotW / 2);
        const y = padT + plotH - ((tok / maxTokens) * plotH);
        points.push({ x, y, tok, label: localLabels[idx] || labels[idx] });
      });

      const hasData = points.some(p => p.tok > 0);

      if (!hasData && !isTotal) {
        const yZero = padT + plotH;
        linesHtml += `
          <path class="chart-line-path chart-idle-baseline" data-series="${seriesKey}" d="M ${padL} ${yZero} L ${width - padR} ${yZero}" fill="none" stroke="${color}" stroke-width="1.5" stroke-dasharray="3,3" opacity="0.25" style="transition: all 0.2s ease;">
            <title>${platformNames[seriesKey]}: Idle (0 tokens)</title>
          </path>
        `;
        return;
      }

      let d = "";
      points.forEach((pt, idx) => {
        d += (idx === 0 ? `M ${pt.x} ${pt.y}` : ` L ${pt.x} ${pt.y}`);
      });

      if (isTotal && hasData) {
        const areaD = `${d} L ${points[points.length - 1].x} ${padT + plotH} L ${points[0].x} ${padT + plotH} Z`;
        areaHtml += `
          <path class="chart-total-area" data-series="total" d="${areaD}" fill="url(#velocity-total-area-grad)" opacity="0.9" pointer-events="none"></path>
        `;
      }

      const strokeDash = isTotal ? 'stroke-dasharray="6,4"' : '';
      const strokeWidth = isTotal ? '2' : '2.5';
      const opacity = isTotal ? '0.75' : '0.9';

      linesHtml += `
        <path class="chart-line-path" data-series="${seriesKey}" d="${d}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" ${strokeDash} opacity="${opacity}" stroke-linecap="round" stroke-linejoin="round" style="transition: all 0.2s ease;">
          <title>${platformNames[seriesKey]}</title>
        </path>
      `;

      points.forEach(pt => {
        if (pt.tok > 0) {
          dotsHtml += `
            <circle class="chart-dot" data-series="${seriesKey}" cx="${pt.x}" cy="${pt.y}" r="${isTotal ? 3 : 4}" fill="${color}" stroke="#0b0f19" stroke-width="1.5" style="cursor: pointer;">
              <title>${platformNames[seriesKey]}: ${pt.tok.toLocaleString()} tokens at ${pt.label}</title>
            </circle>
          `;
        }
      });
    });

    // Crosshair line for hover inspection
    const crosshairHtml = `
      <line id="chart-crosshair-line" x1="0" y1="${padT}" x2="0" y2="${padT + plotH}" stroke="rgba(56, 189, 248, 0.6)" stroke-width="1.5" stroke-dasharray="3,3" opacity="0" pointer-events="none"></line>
    `;

    svg.innerHTML = `
      ${defsHtml}
      <!-- Base Axes -->
      <line x1="${padL}" y1="${padT + plotH}" x2="${width - padR}" y2="${padT + plotH}" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
      ${gridHtml}
      ${axisHtml}
      ${areaHtml}
      ${linesHtml}
      ${dotsHtml}
      ${crosshairHtml}
    `;

    this._setupChartLegendInteractivity();
    this._setupChartHoverCrosshair(localLabels, keys, seriesMap, padL, plotW, step, platforms, platformNames, platformColors, chartMode, bucketMin);
  },

  _setupChartHoverCrosshair(labels, keys, seriesMap, padL, plotW, step, platforms, platformNames, platformColors, chartMode, bucketMin) {
    const container = document.getElementById("svg-chart-container");
    const svg = document.getElementById("token-velocity-chart");
    const crosshair = document.getElementById("chart-crosshair-line");
    const tooltip = document.getElementById("chart-flyout-tooltip");
    if (!container || !svg || !crosshair || !tooltip || !labels || labels.length === 0) return;

    container.onmousemove = (e) => {
      const rect = svg.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const svgX = (mouseX / rect.width) * 900;

      if (svgX < padL - 10 || svgX > padL + plotW + 10) {
        crosshair.setAttribute("opacity", "0");
        tooltip.style.display = "none";
        return;
      }

      const numPoints = labels.length;
      const idx = Math.max(0, Math.min(numPoints - 1, Math.round((svgX - padL) / (numPoints > 1 ? step : 1))));
      const ptX = padL + (idx * (numPoints > 1 ? step : 0));
      crosshair.setAttribute("x1", ptX);
      crosshair.setAttribute("x2", ptX);
      crosshair.setAttribute("opacity", "1");

      const timeLabel = labels[idx];
      const timeKey = keys[idx] || "";
      const totalTok = seriesMap["total"]?.points?.[idx] || 0;
      const modeDesc = chartMode === "cumulative" ? "Cumulative Run" : `${bucketMin}m Interval Burst`;

      let rowsHtml = "";
      platforms.forEach(p => {
        const tok = seriesMap[p]?.points?.[idx] || 0;
        const color = platformColors[p];
        const name = platformNames[p];
        const pct = totalTok > 0 && tok > 0 ? ` (${Math.round((tok / totalTok) * 100)}%)` : (tok === 0 ? " (idle)" : "");
        rowsHtml += `
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 3px;">
            <span style="color: ${color}; display: flex; align-items: center; gap: 4px;">
              <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${color};"></span>
              ${name}:
            </span>
            <span style="font-family: var(--font-mono); font-weight: 600; color: ${tok > 0 ? '#fff' : '#64748b'};">
              ${tok.toLocaleString()} tok${pct}
            </span>
          </div>
        `;
      });

      tooltip.innerHTML = `
        <div style="font-size: 0.76rem; font-weight: 700; color: #fff; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center;">
          <span>⏱️ ${timeKey ? this.formatLocalDateTime(timeKey) : timeLabel} <span style="font-size: 0.65rem; color: #94a3b8; font-weight: 400;">(${modeDesc})</span></span>
          <span style="font-family: var(--font-mono); font-size: 0.74rem; color: #06b6d4; font-weight: 800;">${totalTok.toLocaleString()} total</span>
        </div>
        <div style="height: 1px; background: rgba(255,255,255,0.1); margin-bottom: 6px;"></div>
        <div style="font-size: 0.72rem;">
          ${rowsHtml}
        </div>
      `;
      tooltip.style.display = "block";

      const contRect = container.getBoundingClientRect();
      let leftPx = e.clientX - contRect.left + 15;
      let topPx = e.clientY - contRect.top - 20;
      if (leftPx + 230 > contRect.width) {
        leftPx = e.clientX - contRect.left - 240;
      }
      if (topPx < 10) topPx = 10;
      tooltip.style.left = `${leftPx}px`;
      tooltip.style.top = `${topPx}px`;
    };

    container.onmouseleave = () => {
      crosshair.setAttribute("opacity", "0");
      tooltip.style.display = "none";
    };
  },

  _setupChartLegendInteractivity() {
    const legendPills = document.querySelectorAll(".chart-legend-pill");
    legendPills.forEach(pill => {
      pill.onclick = () => {
        const plat = pill.getAttribute("data-platform");
        const allPaths = document.querySelectorAll(".chart-line-path");
        const allDots = document.querySelectorAll(".chart-dot");
        const totalArea = document.querySelector(".chart-total-area");
        const isAlreadyIsolated = pill.classList.contains("isolated");

        legendPills.forEach(p => p.classList.remove("isolated"));

        if (isAlreadyIsolated) {
          // Restore all
          allPaths.forEach(p => {
            if (p.classList.contains("chart-idle-baseline")) {
              p.style.opacity = "0.25";
              p.style.strokeWidth = "1.5";
            } else {
              p.style.opacity = p.getAttribute("data-series") === "total" ? "0.75" : "0.9";
              p.style.strokeWidth = p.getAttribute("data-series") === "total" ? "2" : "2.5";
            }
          });
          allDots.forEach(d => d.style.opacity = "1");
          if (totalArea) totalArea.style.opacity = "0.9";
        } else {
          // Isolate clicked platform
          pill.classList.add("isolated");
          allPaths.forEach(p => {
            const match = p.getAttribute("data-series") === plat;
            if (match) {
              p.style.opacity = "1";
              p.style.strokeWidth = "3.5";
            } else {
              p.style.opacity = "0.08";
              p.style.strokeWidth = "1";
            }
          });
          allDots.forEach(d => {
            const match = d.getAttribute("data-series") === plat;
            d.style.opacity = match ? "1" : "0.05";
          });
          if (totalArea) {
            totalArea.style.opacity = plat === "total" ? "0.9" : "0.05";
          }
        }
      };
    });
  },

  getChildRealPoints(provKey, childId) {
    const zeroes = [0, 0, 0, 0, 0, 0, 0, 0];
    const cacheKey = `${provKey}_${this.trendWindow || '24h'}_${this.currentScope || 'individual'}`;
    const cached = (this.cachedHierarchicalTrends && this.cachedHierarchicalTrends[cacheKey]) ||
                   (this.trendsCache && this.trendsCache[provKey]);
    if (cached && cached.series && cached.series.length > 0) {
      const match = cached.series.find(s => {
        const sid = s.id || s.key || '';
        return sid === childId || sid.includes(childId) || (childId && childId.includes(sid));
      });
      if (match && match.points && match.points.length > 0) {
        return match.points;
      }
    }
    return zeroes;
  },

  _getProviderChildSeries(key, item) {
    const zeroes = [0, 0, 0, 0, 0, 0, 0, 0];

    // Check if we have real cached hierarchical trend series from backend
    const cacheKey = `${key}_${this.trendWindow || '24h'}_${this.currentScope || 'individual'}`;
    const cached = (this.cachedHierarchicalTrends && this.cachedHierarchicalTrends[cacheKey]) ||
                   (this.trendsCache && this.trendsCache[key]);
    if (cached && cached.series && cached.series.length > 0) {
      return cached.series.map(s => ({
        key: s.key || s.id,
        id: s.id || s.key,
        label: s.label || s.name,
        name: s.name || s.label,
        color: s.color,
        points: s.points || zeroes
      }));
    }

    if (key === "claude") {
      return [
        { key: "claude_total", id: "claude_total", label: "Claude Total", name: "Claude Total", color: "#38bdf8", points: zeroes },
        { key: "claude_individual", id: "claude_individual", label: "Individual Member", name: "Individual Member", color: "#60a5fa", points: zeroes },
        { key: "claude_team", id: "claude_team", label: "Team Workspace", name: "Team Workspace", color: "#c084fc", points: zeroes }
      ];
    } else if (key === "gemini") {
      return [
        { key: "gemini_account", id: "gemini_account", label: "Google Umbrella", name: "Google Umbrella", color: "#60a5fa", points: zeroes },
        { key: "tok_gem_flash", id: "tok_gem_flash", label: "Dev Key", name: "Dev Key", color: "#34d399", points: zeroes }
      ];
    } else if (key === "ollama") {
      return [
        { key: "ollama_total", id: "ollama_total", label: "Local Hardware", name: "Local Hardware", color: "#a855f7", points: zeroes }
      ];
    }
    return [
      { key: `${key}_total`, id: `${key}_total`, label: `${key} Active`, name: `${key} Active`, color: "#38bdf8", points: zeroes }
    ];
  },

  generateMultiInlineSparkline(seriesList, w = 110, h = 26) {
    if (!seriesList || seriesList.length === 0) return "";
    let allPoints = [];
    seriesList.forEach(s => { allPoints = allPoints.concat(s.points || []); });
    const isAllZero = allPoints.length > 0 && allPoints.every(p => p === 0);
    const pad = 3;

    if (isAllZero) {
      const yZero = (h - pad).toFixed(1);
      return `
        <svg width="${w}" height="${h}" style="background: rgba(0,0,0,0.25); border-radius: 4px; border: 1px solid rgba(255,255,255,0.06);" title="No activity in window (0 tokens)">
          <line x1="${pad}" y1="${yZero}" x2="${w - pad}" y2="${yZero}" stroke="rgba(255,255,255,0.18)" stroke-width="1.5" stroke-dasharray="2,2"/>
          <text x="${w / 2}" y="${h / 2 + 3}" fill="#64748b" font-size="8" text-anchor="middle" font-family="monospace">0 t (idle)</text>
        </svg>
      `;
    }

    const min = Math.min(...allPoints, 0);
    const max = Math.max(...allPoints, 100);
    const range = Math.max(1, max - min);
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
    const childSeries = this._getProviderChildSeries(providerKey, { tokens_today: 0 });
    const n = 12;
    const labels = Array.from({ length: n }, (_, i) => `${i * 2}:00`);
    const series = childSeries.map(cs => {
      const sKey = cs.key || cs.id;
      const sLabel = cs.label || cs.name || sKey;
      return {
        key: sKey,
        id: sKey,
        label: sLabel,
        name: sLabel,
        color: cs.color,
        points: Array(n).fill(0)
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
      const sKey = s.key || s.id;
      if (!hiddenSet.has(sKey)) {
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
      const sKey = s.key || s.id;
      const sLabel = s.label || s.name || sKey;
      const isHidden = hiddenSet.has(sKey);
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
              data-series="${sKey}" 
              d="${pathData}" 
              fill="none" 
              stroke="${s.color}" 
              stroke-width="2.5" 
              opacity="${isHidden ? '0' : '0.9'}" 
              stroke-linecap="round" 
              stroke-linejoin="round" 
              style="transition: all 0.2s ease; cursor: pointer; pointer-events: ${isHidden ? 'none' : 'stroke'};"
              onmouseenter="window.App.highlightSeries('${providerKey}', '${sKey}')"
              onmouseleave="window.App.unhighlightSeries('${providerKey}')">
          <title>${sLabel}: ${lastPt.val.toLocaleString()} tok</title>
        </path>
      `;

      if (!isHidden) {
        dotsHtml += `
          <circle cx="${lastPt.x}" cy="${lastPt.y}" r="3.5" fill="${s.color}" stroke="#ffffff" stroke-width="1"
                  class="trend-chart-dot" data-provider="${providerKey}" data-series="${sKey}">
            <title>${sLabel}: ${lastPt.val.toLocaleString()} tokens</title>
          </circle>
        `;
      }
    });

    // Interactive Legend Pills
    const legendPillsHtml = seriesList.map(s => {
      const sKey = s.key || s.id;
      const sLabel = s.label || s.name || sKey;
      const isHidden = hiddenSet.has(sKey);
      const lastVal = s.points ? s.points[s.points.length - 1] : 0;
      return `
        <div class="trend-legend-pill" 
             data-provider="${providerKey}" 
             data-series="${sKey}"
             onclick="window.App.toggleSeriesVisibility('${providerKey}', '${sKey}', '${containerId}')"
             onmouseenter="window.App.highlightSeries('${providerKey}', '${sKey}')"
             onmouseleave="window.App.unhighlightSeries('${providerKey}')"
             style="display: flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 4px; background: rgba(0,0,0,0.4); border: 1px solid ${isHidden ? 'rgba(255,255,255,0.06)' : s.color + '40'}; cursor: pointer; transition: all 0.2s ease; opacity: ${isHidden ? '0.35' : '1'};">
          <span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: ${s.color};"></span>
          <span style="font-size: 0.72rem; color: #cbd5e1; font-weight: 600; text-decoration: ${isHidden ? 'line-through' : 'none'};">${sLabel}</span>
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
    this.trendWindow = windowPeriod || "24h";
    this.chartWindow = this.trendWindow;
    this.cachedHierarchicalTrends = {};
    this._lastLocalWindowUpdateTs = Date.now();
    const sel = document.getElementById("trend-window-select");
    const cSel = document.getElementById("chart-window-select");
    const cfgWinSel = document.getElementById("cfg-default-trend-window");
    if (sel) sel.value = this.trendWindow;
    if (cSel) cSel.value = this.trendWindow;
    if (cfgWinSel) cfgWinSel.value = this.trendWindow;
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        settings: {
          active_trend_window: this.trendWindow,
          default_trend_window: this.trendWindow
        }
      })
    }).catch(() => {});
    if (this.lastCompData && window._lastProviders) {
      this.renderComparison(this.lastCompData, window._lastProviders);
    }
    this.loadUsageData();
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

  sortSessionsBy(column) {
    if (this.sessionSortCol === column) {
      this.sessionSortAsc = !this.sessionSortAsc;
    } else {
      this.sessionSortCol = column;
      if (["session_id", "provider", "model", "client_ip"].includes(column)) {
        this.sessionSortAsc = true;
      } else {
        this.sessionSortAsc = false;
      }
    }

    const cols = [
      "session_id", "provider", "model", "client_ip",
      "input_tokens", "output_tokens", "total_tokens", "estimated_cost",
      "first_activity", "last_activity", "duration"
    ];
    cols.forEach(c => {
      const el = document.getElementById("sort-icon-" + c);
      if (el) {
        el.innerText = (c === this.sessionSortCol ? (this.sessionSortAsc ? " ▲" : " ▼") : "");
      }
    });

    this.applySessionFilterAndSort();
  },

  applySessionFilterAndSort() {
    if (!this.rawSessions || !Array.isArray(this.rawSessions)) {
      this.renderSessions([]);
      return;
    }

    const searchInput = document.getElementById("filter-session-search");
    const searchVal = searchInput ? searchInput.value.trim().toLowerCase() : "";

    const provSelect = document.getElementById("filter-session-provider");
    const provVal = provSelect ? provSelect.value.trim().toLowerCase() : "";

    let list = this.rawSessions.slice();

    if (provVal) {
      list = list.filter(s => (s.provider || "").toLowerCase() === provVal);
    }

    if (searchVal) {
      list = list.filter(s => {
        const sid = (s.session_id || "").toLowerCase();
        const p = (s.provider || "").toLowerCase();
        const m = (s.model || "").toLowerCase();
        const ip = (s.client_ip || "").toLowerCase();
        const alias = (s.client_alias || "").toLowerCase();
        return sid.includes(searchVal) || p.includes(searchVal) || m.includes(searchVal) || ip.includes(searchVal) || alias.includes(searchVal);
      });
    }

    const col = this.sessionSortCol || "last_activity";
    const asc = !!this.sessionSortAsc;

    list.sort((a, b) => {
      let vA, vB;
      if (["input_tokens", "output_tokens", "total_tokens", "estimated_cost"].includes(col)) {
        vA = Number(a[col] || 0);
        vB = Number(b[col] || 0);
        return asc ? vA - vB : vB - vA;
      } else if (col === "duration") {
        const getDurSec = (s) => {
          if (!s.first_activity || !s.last_activity) return 0;
          let s1 = s.first_activity.endsWith("Z") ? s.first_activity : s.first_activity + "Z";
          let s2 = s.last_activity.endsWith("Z") ? s.last_activity : s.last_activity + "Z";
          return Math.max(0, (new Date(s2).getTime() - new Date(s1).getTime()) / 1000);
        };
        vA = getDurSec(a);
        vB = getDurSec(b);
        return asc ? vA - vB : vB - vA;
      } else if (["first_activity", "last_activity"].includes(col)) {
        const getTs = (s, f) => {
          if (!s[f]) return 0;
          let str = s[f].endsWith("Z") ? s[f] : s[f] + "Z";
          const t = new Date(str).getTime();
          return isNaN(t) ? 0 : t;
        };
        vA = getTs(a, col);
        vB = getTs(b, col);
        return asc ? vA - vB : vB - vA;
      } else {
        vA = String(a[col] || "").toLowerCase();
        vB = String(b[col] || "").toLowerCase();
        return asc ? vA.localeCompare(vB) : vB.localeCompare(vA);
      }
    });

    this.renderSessions(list);
  },

  renderSessions(sessions) {
    const tbody = document.getElementById("sessions-table-body");
    if (!tbody) return;

    if (!sessions || sessions.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="11" style="text-align: center; color: var(--text-dim); padding: 32px 20px;">
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
      let provBadgeClass = "badge-claude";
      if (s.provider === "copilot") provBadgeClass = "badge-copilot";
      else if (s.provider === "gemini") provBadgeClass = "badge-gemini";
      else if (s.provider === "ollama") provBadgeClass = "badge-ollama";
      else if (s.provider === "chatgpt") provBadgeClass = "badge-chatgpt";

      const firstTime = this.formatLocalDateTime(s.first_activity);
      const lastTime = this.formatLocalDateTime(s.last_activity);
      const durationStr = this.formatDuration(s.first_activity, s.last_activity);
      const clientIp = s.client_ip || "127.0.0.1";
      const clientAlias = s.client_alias || "localhost";

      const isProxied = s.is_proxied === 1 || s.source === "proxy" || s.source === "emulator";
      const sourceTag = s.source || (isProxied ? "proxy" : "direct");
      let routeBadge = `<span class="badge" style="font-size: 0.65rem; background: rgba(52, 211, 153, 0.12); color: #34d399;" title="Direct client connection">🌐 Direct</span>`;
      if (sourceTag === "proxy") {
        routeBadge = `<span class="badge" style="font-size: 0.65rem; background: rgba(6, 182, 212, 0.2); color: #38bdf8; border: 1px solid rgba(6, 182, 212, 0.4);" title="Routed via Port 8766 Transparent Proxy">⚡ Proxy</span>`;
      } else if (sourceTag === "emulator") {
        routeBadge = `<span class="badge" style="font-size: 0.65rem; background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4);" title="Routed via Port 11435 Secondary Bridge">🌉 Bridge</span>`;
      } else if (sourceTag === "log_scanner") {
        routeBadge = `<span class="badge" style="font-size: 0.65rem; background: rgba(245, 158, 11, 0.15); color: #fbbf24;" title="Discovered via background CLI scanner">📑 Scanner</span>`;
      }

      return `
        <tr>
          <td><code style="font-family: var(--font-mono); color: var(--accent-cyan); font-size: 0.8rem;">${this.escapeHtml(s.session_id)}</code></td>
          <td><span class="badge ${provBadgeClass}">${this.escapeHtml(s.provider)}</span></td>
          <td style="color: var(--text-muted); font-size: 0.82rem;">${this.escapeHtml(s.model || 'default')}</td>
          <td>
            <div style="display: flex; flex-direction: column; gap: 3px;">
              <div style="display: flex; align-items: center; gap: 4px;">
                <span style="font-family: var(--font-mono); font-size: 0.8rem; color: #e2e8f0;">${this.escapeHtml(clientIp)}</span>
                ${routeBadge}
              </div>
              <div style="display: flex; align-items: center; gap: 4px;">
                <span class="badge" style="font-size: 0.65rem; background: rgba(56, 189, 248, 0.12); color: #38bdf8; width: fit-content;">💻 ${this.escapeHtml(clientAlias)}</span>
                ${s.instance_id && s.instance_id !== 'local' ? `<span class="badge" style="font-size: 0.62rem; background: rgba(139, 92, 246, 0.15); color: #a78bfa;" title="Hardware Node">🖥️ ${this.escapeHtml(s.instance_id)}</span>` : ''}
              </div>
            </div>
          </td>
          <td style="font-family: var(--font-mono); text-align: right;">${Number(s.input_tokens).toLocaleString()}</td>
          <td style="font-family: var(--font-mono); text-align: right;">${Number(s.output_tokens).toLocaleString()}</td>
          <td style="font-family: var(--font-mono); font-weight: 700; color: #fff; text-align: right;">${Number(s.total_tokens).toLocaleString()}</td>
          <td style="font-family: var(--font-mono); color: var(--accent-emerald); text-align: right;">$${Number(s.estimated_cost).toFixed(4)}</td>
          <td style="font-size: 0.78rem; color: var(--text-dim); font-family: var(--font-mono);">${firstTime}</td>
          <td style="font-size: 0.78rem; color: var(--text-dim); font-family: var(--font-mono);">${lastTime}</td>
          <td>
            <span class="badge" style="font-size: 0.72rem; font-family: var(--font-mono); background: rgba(255,255,255,0.06); color: #93c5fd;">⏱️ ${durationStr}</span>
          </td>
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

  // Historical Reporting & Multi-Dimensional Analytics Engine (AIUM-607 / AIUM-801 / AIUM-902 / AIUM-903)
  selectedReportGrouping: 'day',
  reportSortBy: 'period',
  reportSortDir: 'desc',
  lastReportRows: [],
  reportGroupByCols: [],
  reportIncludeGroupTotals: true,
  _draggedReportColKey: null,
  reportColumns: null,

  getDefaultReportColumns() {
    return [
      { key: 'period', label: 'Period / Date', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'provider', label: 'Provider', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'account_id', label: 'Account / Tenant', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'group_key', label: 'Pivot Dimension', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'source', label: 'Traffic Route', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'model', label: 'Model', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'locality_label', label: 'Node Locality', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'account_tier_label', label: 'Account Tier', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'compute_node', label: 'Compute Node', visible: false, align: 'left', groupable: true, sortable: true },
      { key: 'instance_id', label: 'Instance / Node ID', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'client_ip', label: 'Client IP / Alias', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'team_name', label: 'Team', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'user_name', label: 'User / Seat', visible: true, align: 'left', groupable: true, sortable: true },
      { key: 'project_id', label: 'Project', visible: false, align: 'left', groupable: true, sortable: true },
      { key: 'event_count', label: 'Events', visible: true, align: 'right', groupable: false, sortable: true, numeric: true },
      { key: 'input_tokens', label: 'Input', visible: true, align: 'right', groupable: false, sortable: true, numeric: true },
      { key: 'output_tokens', label: 'Output', visible: true, align: 'right', groupable: false, sortable: true, numeric: true },
      { key: 'cache_creation_tokens', label: 'Cache Create', visible: true, align: 'right', groupable: false, sortable: true, numeric: true },
      { key: 'cache_read_tokens', label: 'Cache Read', visible: true, align: 'right', groupable: false, sortable: true, numeric: true },
      { key: 'total_tokens', label: 'Total Tokens', visible: true, align: 'right', groupable: false, sortable: true, numeric: true },
      { key: 'net_cost_usd', label: 'Est. Cost', visible: true, align: 'right', groupable: false, sortable: true, numeric: true },
      { key: 'cost_per_1k', label: 'Cost / 1k', visible: true, align: 'right', groupable: false, sortable: false, numeric: true },
      { key: 'share', label: 'Share', visible: true, align: 'center', groupable: false, sortable: false }
    ];
  },

  ensureReportColumnsInitialized() {
    if (!Array.isArray(this.reportColumns) || this.reportColumns.length === 0) {
      this.reportColumns = this.getDefaultReportColumns();
    }
    return this.reportColumns;
  },

  toggleReportGridCustomizer() {
    const panel = document.getElementById("reports-grid-customizer");
    if (!panel) return;
    const isHidden = panel.style.display === "none";
    panel.style.display = isHidden ? "block" : "none";
    this.renderReportCustomizerControls();
  },

  toggleReportColumnVisibility(colKey) {
    const cols = this.ensureReportColumnsInitialized();
    const target = cols.find(c => c.key === colKey);
    if (target) {
      const visibleCount = cols.filter(c => c.visible).length;
      if (target.visible && visibleCount <= 1) return; // keep at least 1 column visible
      target.visible = !target.visible;
    }
    this.renderReportCustomizerControls();
    this.renderHistoricalReportRows(this.lastReportRows || []);
  },

  setAllReportColumnsVisibility(visible) {
    const cols = this.ensureReportColumnsInitialized();
    cols.forEach((c, idx) => {
      c.visible = visible ? true : (idx === 0 || c.key === 'total_tokens' || c.key === 'net_cost_usd');
    });
    this.renderReportCustomizerControls();
    this.renderHistoricalReportRows(this.lastReportRows || []);
  },

  resetReportColumnsDefault() {
    this.reportColumns = this.getDefaultReportColumns();
    this.reportGroupByCols = [];
    this.reportIncludeGroupTotals = true;
    const chk = document.getElementById("reports-group-totals-chk");
    if (chk) chk.checked = true;
    this.renderReportCustomizerControls();
    this.renderHistoricalReportRows(this.lastReportRows || []);
  },

  toggleReportGroupByCol(colKey) {
    if (!Array.isArray(this.reportGroupByCols)) this.reportGroupByCols = [];
    const idx = this.reportGroupByCols.indexOf(colKey);
    if (idx >= 0) {
      this.reportGroupByCols.splice(idx, 1);
    } else {
      this.reportGroupByCols.push(colKey);
    }
    this.renderReportCustomizerControls();
    this.renderHistoricalReportRows(this.lastReportRows || []);
  },

  clearReportGroupingCols() {
    this.reportGroupByCols = [];
    this.renderReportCustomizerControls();
    this.renderHistoricalReportRows(this.lastReportRows || []);
  },

  toggleReportGroupTotals(checked) {
    this.reportIncludeGroupTotals = !!checked;
    this.renderHistoricalReportRows(this.lastReportRows || []);
  },

  reorderReportColumn(sourceColKey, targetColKey) {
    if (!sourceColKey || !targetColKey || sourceColKey === targetColKey) return;
    const cols = this.ensureReportColumnsInitialized();
    const fromIdx = cols.findIndex(c => c.key === sourceColKey);
    const toIdx = cols.findIndex(c => c.key === targetColKey);
    if (fromIdx < 0 || toIdx < 0) return;
    const [moved] = cols.splice(fromIdx, 1);
    cols.splice(toIdx, 0, moved);
    this.renderReportCustomizerControls();
    this.renderHistoricalReportRows(this.lastReportRows || []);
  },

  onReportColDragStart(event, colKey) {
    this._draggedReportColKey = colKey;
    if (event && event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      try {
        event.dataTransfer.setData("text/plain", colKey);
      } catch (_e) {}
    }
    if (event && event.currentTarget) {
      event.currentTarget.style.opacity = "0.55";
    }
  },

  onReportColDragOver(event) {
    if (event) {
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
      if (event.currentTarget) {
        event.currentTarget.style.outline = "2px dashed #38bdf8";
        event.currentTarget.style.outlineOffset = "-2px";
      }
    }
  },

  onReportColDragLeave(event) {
    if (event && event.currentTarget) {
      event.currentTarget.style.outline = "";
      event.currentTarget.style.outlineOffset = "";
    }
  },

  onReportColDrop(event, targetColKey) {
    if (event) {
      event.preventDefault();
      if (event.currentTarget) {
        event.currentTarget.style.outline = "";
        event.currentTarget.style.outlineOffset = "";
      }
    }
    const sourceKey = this._draggedReportColKey || (event && event.dataTransfer ? event.dataTransfer.getData("text/plain") : null);
    this._draggedReportColKey = null;
    if (sourceKey && targetColKey && sourceKey !== targetColKey) {
      this.reorderReportColumn(sourceKey, targetColKey);
    }
  },

  onReportColDragEnd(event) {
    this._draggedReportColKey = null;
    if (event && event.currentTarget) {
      event.currentTarget.style.opacity = "1";
      event.currentTarget.style.outline = "";
    }
  },

  renderReportCustomizerControls() {
    const cols = this.ensureReportColumnsInitialized();
    const groupByContainer = document.getElementById("reports-groupby-chips");
    const seqContainer = document.getElementById("reports-column-sequence-chips");
    const chkTotals = document.getElementById("reports-group-totals-chk");
    if (chkTotals) chkTotals.checked = !!this.reportIncludeGroupTotals;

    if (groupByContainer) {
      const groupableCols = cols.filter(c => c.groupable);
      groupByContainer.innerHTML = groupableCols.map(c => {
        const orderIdx = (this.reportGroupByCols || []).indexOf(c.key);
        const isSelected = orderIdx >= 0;
        const badge = isSelected ? `<span style="background:#38bdf8; color:#0f172a; border-radius:50%; padding:0 5px; font-size:0.65rem; font-weight:800; margin-right:4px;">${orderIdx + 1}</span>` : '';
        return `
          <button type="button"
                  onclick="App.toggleReportGroupByCol('${c.key}')"
                  style="padding: 4px 10px; font-size: 0.72rem; border-radius: 999px; cursor: pointer; transition: all 0.15s; border: 1px solid ${isSelected ? '#38bdf8' : 'rgba(255,255,255,0.14)'}; background: ${isSelected ? 'rgba(56, 189, 248, 0.2)' : 'rgba(15, 23, 42, 0.65)'}; color: ${isSelected ? '#e0f2fe' : 'var(--text-muted)'}; font-weight: ${isSelected ? '700' : '500'};">
            ${badge}${this.escapeHtml(c.label)}
          </button>
        `;
      }).join("");
    }

    if (seqContainer) {
      seqContainer.innerHTML = cols.map((c, idx) => {
        return `
          <div draggable="true"
               ondragstart="App.onReportColDragStart(event, '${c.key}')"
               ondragover="App.onReportColDragOver(event)"
               ondragleave="App.onReportColDragLeave(event)"
               ondrop="App.onReportColDrop(event, '${c.key}')"
               ondragend="App.onReportColDragEnd(event)"
               title="Drag to reorder column position (#${idx + 1})"
               style="display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 6px; cursor: grab; user-select: none; border: 1px solid ${c.visible ? 'rgba(56, 189, 248, 0.35)' : 'rgba(255,255,255,0.08)'}; background: ${c.visible ? 'rgba(30, 41, 59, 0.9)' : 'rgba(15, 23, 42, 0.45)'}; color: ${c.visible ? '#f8fafc' : 'var(--text-dim)'}; font-size: 0.73rem;">
            <span style="color: var(--text-dim); font-size: 0.7rem; cursor: grab;">⠿</span>
            <input type="checkbox" ${c.visible ? 'checked' : ''} onchange="App.toggleReportColumnVisibility('${c.key}')" style="cursor: pointer; accent-color: #38bdf8;">
            <span>${this.escapeHtml(c.label)}</span>
          </div>
        `;
      }).join("");
    }
  },

  renderReportTableHeaders() {
    const headRow = document.getElementById("reports-table-head-row");
    if (!headRow) return;
    const cols = this.ensureReportColumnsInitialized().filter(c => c.visible);
    headRow.innerHTML = cols.map(c => {
      const isSorted = this.reportSortBy === c.key;
      const sortArrow = isSorted ? (this.reportSortDir === 'asc' ? ' ▲' : ' ▼') : (c.sortable ? ' ⇅' : '');
      const clickAttr = c.sortable ? `onclick="App.sortReportsTable('${c.key}')"` : '';
      return `
        <th draggable="true"
            ondragstart="App.onReportColDragStart(event, '${c.key}')"
            ondragover="App.onReportColDragOver(event)"
            ondragleave="App.onReportColDragLeave(event)"
            ondrop="App.onReportColDrop(event, '${c.key}')"
            ondragend="App.onReportColDragEnd(event)"
            ${clickAttr}
            title="Drag header left/right to reorder column${c.sortable ? ' • Click to sort' : ''}"
            style="text-align: ${c.align || 'left'}; cursor: ${c.sortable ? 'pointer' : 'grab'}; user-select: none; white-space: nowrap; position: relative;">
          <span style="opacity: 0.45; font-size: 0.68rem; margin-right: 3px; cursor: grab;">⠿</span>${this.escapeHtml(c.label)}<span style="font-size: 0.68rem; color: ${isSorted ? '#38bdf8' : 'var(--text-dim)'};">${sortArrow}</span>
        </th>
      `;
    }).join("");
  },

  setReportGrouping(group) {
    this.selectedReportGrouping = group;
    ['hour', 'day', 'week', 'month', 'year'].forEach(g => {
      const btn = document.getElementById(`slice-btn-${g}`);
      if (btn) {
        btn.className = (g === group) ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
      }
    });
    this.loadHistoricalReport();
  },

  handleDateRangeChange() {
    const rangeSelect = document.getElementById("report-date-range-select");
    const startInput = document.getElementById("report-filter-start-date");
    const endInput = document.getElementById("report-filter-end-date");
    if (rangeSelect && rangeSelect.value !== "custom") {
      if (startInput) startInput.value = "";
      if (endInput) endInput.value = "";
    }
    this.loadHistoricalReport();
  },

  sortReportsTable(columnKey) {
    if (this.reportSortBy === columnKey) {
      this.reportSortDir = this.reportSortDir === 'desc' ? 'asc' : 'desc';
    } else {
      this.reportSortBy = columnKey;
      this.reportSortDir = 'desc';
    }
    if (Array.isArray(this.lastReportRows) && this.lastReportRows.length > 0) {
      this.renderHistoricalReportRows(this.lastReportRows);
    } else {
      this.loadHistoricalReport();
    }
  },

  _collectReportFilterParams() {
    const group = this.selectedReportGrouping || 'day';
    const rangeSelect = document.getElementById("report-date-range-select");
    const rangeVal = rangeSelect ? rangeSelect.value : '7d';

    const prov = document.getElementById("report-filter-provider")?.value || '';
    const acct = document.getElementById("report-filter-account")?.value?.trim() || '';
    const dim = document.getElementById("report-filter-dimension")?.value || '';
    const sourceVal = document.getElementById("report-filter-source")?.value?.trim() || '';
    const modelVal = document.getElementById("report-filter-model")?.value?.trim() || '';
    const instanceVal = document.getElementById("report-filter-instance")?.value?.trim() || '';
    const clientIpVal = document.getElementById("report-filter-client-ip")?.value?.trim() || '';
    const team = document.getElementById("report-filter-team")?.value?.trim() || '';
    const user = document.getElementById("report-filter-user")?.value?.trim() || '';

    const customStart = document.getElementById("report-filter-start-date")?.value?.trim() || '';
    const customEnd = document.getElementById("report-filter-end-date")?.value?.trim() || '';

    let startDate = customStart || null;
    let endDate = customEnd || null;
    const now = new Date();
    const rangeHoursMap = {
      '1h': 1,
      '3h': 3,
      '6h': 6,
      '12h': 12,
      '24h': 24,
      '48h': 48,
      '3d': 72,
      '5d': 120,
      '7d': 168,
      '10d': 240,
      '15d': 360,
      '30d': 720,
      '90d': 2160,
      '3m': 2160,
      '6m': 4320,
      '12m': 8760
    };
    if (!startDate && rangeVal !== 'custom') {
      if (rangeVal === 'today') {
        startDate = now.toISOString().substring(0, 10);
      } else if (rangeHoursMap[rangeVal]) {
        const hrs = rangeHoursMap[rangeVal];
        const cutoff = new Date(now.getTime() - hrs * 3600000);
        startDate = hrs < 24 ? cutoff.toISOString() : cutoff.toISOString().substring(0, 10);
      }
    }

    const params = new URLSearchParams({ group_by: group });
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    if (prov) params.set("provider", prov);
    if (acct) params.set("account_id", acct);
    if (dim) params.set("dimension", dim);
    if (sourceVal) params.set("source", sourceVal);
    if (modelVal) params.set("model", modelVal);
    if (instanceVal) params.set("instance_id", instanceVal);
    if (clientIpVal) params.set("client_ip", clientIpVal);
    if (team) params.set("team_name", team);
    if (user) params.set("user_name", user);
    if (this.reportSortBy) params.set("sort_by", this.reportSortBy);
    if (this.reportSortDir) params.set("sort_dir", this.reportSortDir);
    return params;
  },

  async loadHistoricalReport() {
    const tbody = document.getElementById("reports-table-body");
    if (!tbody) return;

    this.renderReportCustomizerControls();
    this.renderReportTableHeaders();

    const params = this._collectReportFilterParams();

    try {
      const res = await fetch(`/api/reports/history?${params.toString()}`);
      if (!res.ok) return;
      const data = await res.json();

      const summary = data.summary || {};
      const totTokEl = document.getElementById("rep-tot-tokens");
      const totCostEl = document.getElementById("rep-tot-cost");
      const totSavingsEl = document.getElementById("rep-tot-savings");
      const totEvtEl = document.getElementById("rep-tot-events");
      const totDimEl = document.getElementById("rep-tot-records") || document.getElementById("rep-tot-dims");
      const totCacheEl = document.getElementById("rep-tot-cache");
      const totCacheSubEl = document.getElementById("rep-tot-cache-sub");

      const totCacheAll = Number((summary.cache_creation_tokens || 0) + (summary.cache_read_tokens || 0));
      if (totTokEl) totTokEl.innerText = Number(summary.total_tokens || 0).toLocaleString();
      if (totCacheEl) totCacheEl.innerText = totCacheAll.toLocaleString();
      if (totCacheSubEl) {
        totCacheSubEl.innerText = `Create: ${Number(summary.cache_creation_tokens || 0).toLocaleString()} | Read: ${Number(summary.cache_read_tokens || 0).toLocaleString()}`;
      }
      if (totCostEl) {
        totCostEl.innerText = `$${Number(summary.total_estimated_cost || 0).toFixed(4)}`;
      }
      if (totSavingsEl) {
        const totSav = Math.abs(Number(summary.total_estimated_savings_usd || 0));
        totSavingsEl.innerText = `(-$${totSav.toFixed(4)})`;
      }
      if (totEvtEl) totEvtEl.innerText = Number(summary.total_events || 0).toLocaleString();
      if (totDimEl) totDimEl.innerText = `${Number(summary.distinct_dimensions || (data.rows ? data.rows.length : 0))} slices`;

      this.lastReportRows = data.rows || [];
      this.renderHistoricalReportRows(this.lastReportRows);
      this.loadPivotMatrix();
    } catch (e) {
      console.error("Error loading historical report:", e);
    }
  },

  _isLocalModelReportRow(row) {
    if (!row) return false;
    if (row.is_local_model === true) return true;
    const prov = String(row.provider || '').toLowerCase();
    const src = String(row.source || '').toLowerCase();
    return prov === 'ollama' || prov === 'local' || src.includes('ollama');
  },

  formatReportEstCostCell(row, isSubtotal = false) {
    const isLocal = this._isLocalModelReportRow(row);
    const netVal = row.net_cost_usd !== undefined ? Number(row.net_cost_usd) : (isLocal ? -Math.abs(Number(row.estimated_savings_usd || ((row.total_tokens || 0) / 1000000.0) * 6.0)) : Number(row.estimated_cost || 0));
    if (isLocal || netVal < 0) {
      const absSavings = Math.abs(netVal || Number(row.estimated_savings_usd || 0));
      return `<span title="Local Model Estimated Cloud Savings (at $6.00/1M frontier benchmark)" style="color: #c084fc; background: rgba(192, 132, 252, 0.14); border: 1px solid rgba(192, 132, 252, 0.35); padding: 2px 6px; border-radius: 4px; font-weight: 700; font-family: var(--font-mono); white-space: nowrap;">(-$${absSavings.toFixed(4)})</span>`;
    }
    const cloudCost = Number(row.estimated_cost !== undefined ? row.estimated_cost : netVal);
    if (isSubtotal && Number(row.estimated_savings_usd || 0) > 0) {
      return `
        <div style="display:flex; flex-direction:column; align-items:flex-end; gap:2px;">
          <span style="color: #34d399; font-weight: 700; font-family: var(--font-mono);">$${cloudCost.toFixed(4)}</span>
          <span style="color: #c084fc; font-size: 0.68rem; font-family: var(--font-mono);" title="Includes Local Model Savings">(-$${Number(row.estimated_savings_usd).toFixed(4)} saved)</span>
        </div>
      `;
    }
    return `<span style="color: #34d399; font-weight: 700; font-family: var(--font-mono);">$${cloudCost.toFixed(4)}</span>`;
  },

  _renderSingleReportCell(col, r, maxTokens, isSubtotal = false) {
    const key = col.key;
    const isLocal = this._isLocalModelReportRow(r);
    if (key === 'period') {
      return `<td style="font-family: var(--font-mono); font-weight: 600; color: #fff; white-space: nowrap;">${this.escapeHtml(r.period || '—')}</td>`;
    }
    if (key === 'provider') {
      const pName = String(r.provider || '—').toUpperCase();
      const badgeColor = isLocal ? '#c084fc' : '#38bdf8';
      return `<td><span style="font-weight: 700; font-size: 0.75rem; color: ${badgeColor};">${this.escapeHtml(pName)}</span></td>`;
    }
    if (key === 'account_id') {
      return `<td style="font-size: 0.78rem; color: #e2e8f0;">${this.escapeHtml(r.account_id || 'default')}</td>`;
    }
    if (key === 'group_key') {
      return `<td><strong style="color: #60a5fa; font-size: 0.8rem;">${this.escapeHtml(r.group_key || r.provider || 'All')}</strong></td>`;
    }
    if (key === 'source') {
      return `<td><span style="font-size: 0.72rem; color: #94a3b8; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono);">${this.escapeHtml(r.source || 'direct')}</span></td>`;
    }
    if (key === 'model') {
      return `<td style="font-family: var(--font-mono); font-size: 0.76rem; color: #f1f5f9;">${this.escapeHtml(r.model || 'default')}</td>`;
    }
    if (key === 'locality_label') {
      const loc = r.locality || (isLocal ? 'local' : 'cloud');
      const locLbl = r.locality_label || (loc === 'remote_lan' ? 'Remote LAN Node' : (loc === 'local' ? 'Local Node (This PC)' : 'Cloud API'));
      const locColor = loc === 'remote_lan' ? '#22d3ee' : (loc === 'local' ? '#c084fc' : '#94a3b8');
      return `<td><span style="font-size: 0.72rem; color: ${locColor}; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px; font-weight: 600;">${this.escapeHtml(locLbl)}</span></td>`;
    }
    if (key === 'account_tier_label') {
      const tier = r.account_tier || '';
      const tierLbl = r.account_tier_label || r.team_name || 'Standard';
      const tierColor = tier === 'personal_pro' ? '#fbbf24' : (tier === 'team_org' ? '#f43f5e' : '#a78bfa');
      return `<td><span style="font-size: 0.72rem; color: ${tierColor}; font-weight: 600;">${this.escapeHtml(tierLbl)}</span></td>`;
    }
    if (key === 'compute_node') {
      return `<td style="font-family: var(--font-mono); font-size: 0.74rem; color: #cbd5e1;">${this.escapeHtml(r.compute_node || r.instance_id || 'local')}</td>`;
    }
    if (key === 'instance_id') {
      return `<td style="font-family: var(--font-mono); font-size: 0.74rem; color: var(--text-muted);">${this.escapeHtml(r.instance_id || 'local')}</td>`;
    }
    if (key === 'client_ip') {
      const label = r.client_alias && r.client_alias !== r.client_ip
        ? `${r.client_alias} (${r.client_ip || '127.0.0.1'})`
        : (r.client_ip || r.client_alias || '127.0.0.1');
      return `<td style="font-family: var(--font-mono); font-size: 0.74rem; color: var(--text-muted);">${this.escapeHtml(label)}</td>`;
    }
    if (key === 'team_name') {
      return `<td style="font-size: 0.76rem; color: var(--text-muted);">${this.escapeHtml(r.team_name || 'default')}</td>`;
    }
    if (key === 'user_name') {
      return `<td style="font-size: 0.76rem; color: var(--text-muted);">${this.escapeHtml(r.user_name || 'local-user')}</td>`;
    }
    if (key === 'project_id') {
      return `<td style="font-size: 0.75rem; color: var(--text-dim);">${this.escapeHtml(r.project_id || 'default')}</td>`;
    }
    if (key === 'event_count') {
      return `<td style="font-family: var(--font-mono); color: var(--text-muted); text-align: right;">${Number(r.event_count || 0).toLocaleString()}</td>`;
    }
    if (key === 'input_tokens') {
      return `<td style="font-family: var(--font-mono); text-align: right;">${Number(r.input_tokens || 0).toLocaleString()}</td>`;
    }
    if (key === 'output_tokens') {
      return `<td style="font-family: var(--font-mono); text-align: right;">${Number(r.output_tokens || 0).toLocaleString()}</td>`;
    }
    if (key === 'cache_creation_tokens') {
      return `<td style="font-family: var(--font-mono); text-align: right; color: #c084fc;">${Number(r.cache_creation_tokens || 0).toLocaleString()}</td>`;
    }
    if (key === 'cache_read_tokens') {
      return `<td style="font-family: var(--font-mono); text-align: right; color: #a78bfa;">${Number(r.cache_read_tokens || 0).toLocaleString()}</td>`;
    }
    if (key === 'total_tokens') {
      return `<td style="font-family: var(--font-mono); font-weight: 700; color: #38bdf8; text-align: right;">${Number(r.total_tokens || 0).toLocaleString()}</td>`;
    }
    if (key === 'net_cost_usd') {
      return `<td style="text-align: right;">${this.formatReportEstCostCell(r, isSubtotal)}</td>`;
    }
    if (key === 'cost_per_1k') {
      const totTok = Number(r.total_tokens || 0);
      const netVal = r.net_cost_usd !== undefined ? Number(r.net_cost_usd) : Number(r.estimated_cost || 0);
      if (totTok <= 0) {
        return `<td style="font-family: var(--font-mono); color: var(--text-dim); font-size: 0.75rem; text-align: right;">$0.0000</td>`;
      }
      if (isLocal || netVal < 0) {
        const savPer1k = ((Math.abs(netVal || Number(r.estimated_savings_usd || 0)) / totTok) * 1000).toFixed(4);
        return `<td style="font-family: var(--font-mono); color: #c084fc; font-size: 0.75rem; text-align: right;">(-$${savPer1k})</td>`;
      }
      const c1k = ((Number(r.estimated_cost || 0) / totTok) * 1000).toFixed(4);
      return `<td style="font-family: var(--font-mono); color: var(--text-dim); font-size: 0.75rem; text-align: right;">$${c1k}</td>`;
    }
    if (key === 'share') {
      const pct = Math.min(100, Math.max(3, Math.round(((r.total_tokens || 0) / Math.max(1, maxTokens)) * 100)));
      return `
        <td style="text-align: center;">
          <div style="background: rgba(255,255,255,0.05); border-radius: 4px; height: 10px; width: 80px; margin: 0 auto; overflow: hidden;">
            <div style="width: ${pct}%; height: 100%; background: linear-gradient(90deg, ${isLocal ? '#a855f7, #ec4899' : '#3b82f6, #06b6d4'}); border-radius: 4px;"></div>
          </div>
        </td>
      `;
    }
    return `<td>${this.escapeHtml(String(r[key] ?? '—'))}</td>`;
  },

  _aggregateReportGroup(groupRows, groupDescriptor) {
    const agg = {
      period: `Σ Group Total (${groupRows.length})`,
      provider: groupDescriptor.provider || '—',
      account_id: groupDescriptor.account_id || '—',
      group_key: groupDescriptor.label || 'Group Subtotal',
      source: groupDescriptor.source || '—',
      model: groupDescriptor.model || '—',
      locality_label: groupDescriptor.locality_label || '—',
      account_tier_label: groupDescriptor.account_tier_label || '—',
      compute_node: groupDescriptor.compute_node || '—',
      instance_id: groupDescriptor.instance_id || '—',
      client_ip: groupDescriptor.client_ip || '—',
      team_name: groupDescriptor.team_name || '—',
      user_name: groupDescriptor.user_name || '—',
      project_id: groupDescriptor.project_id || '—',
      event_count: 0,
      input_tokens: 0,
      output_tokens: 0,
      cache_creation_tokens: 0,
      cache_read_tokens: 0,
      total_tokens: 0,
      estimated_cost: 0,
      estimated_savings_usd: 0,
      net_cost_usd: 0,
      is_local_model: groupRows.length > 0 && groupRows.every(r => this._isLocalModelReportRow(r))
    };
    groupRows.forEach(r => {
      agg.event_count += Number(r.event_count || 0);
      agg.input_tokens += Number(r.input_tokens || 0);
      agg.output_tokens += Number(r.output_tokens || 0);
      agg.cache_creation_tokens += Number(r.cache_creation_tokens || 0);
      agg.cache_read_tokens += Number(r.cache_read_tokens || 0);
      agg.total_tokens += Number(r.total_tokens || 0);
      agg.estimated_cost += Number(r.estimated_cost || 0);
      const isLoc = this._isLocalModelReportRow(r);
      const sav = Number(r.estimated_savings_usd || (isLoc ? ((r.total_tokens || 0) / 1000000.0) * 6.0 : 0));
      agg.estimated_savings_usd += sav;
      const net = r.net_cost_usd !== undefined ? Number(r.net_cost_usd) : (isLoc ? -sav : Number(r.estimated_cost || 0));
      agg.net_cost_usd += net;
    });
    return agg;
  },

  renderHistoricalReportRows(rows) {
    const tbody = document.getElementById("reports-table-body");
    if (!tbody) return;

    this.renderReportTableHeaders();
    const visibleCols = this.ensureReportColumnsInitialized().filter(c => c.visible);
    const colSpan = Math.max(1, visibleCols.length);

    if (!rows || rows.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="${colSpan}" style="text-align: center; color: var(--text-dim); padding: 24px;">
            No usage activity found for the selected time slice and filters.
          </td>
        </tr>
      `;
      return;
    }

    const sorted = [...rows];
    const key = this.reportSortBy || 'period';
    const dir = this.reportSortDir === 'asc' ? 1 : -1;
    sorted.sort((a, b) => {
      const va = a[key] ?? '';
      const vb = b[key] ?? '';
      if (typeof va === 'number' && typeof vb === 'number') {
        return (va - vb) * dir;
      }
      return String(va).localeCompare(String(vb)) * dir;
    });

    const maxTokens = Math.max(...sorted.map(r => r.total_tokens || 0), 1);
    const groupCols = Array.isArray(this.reportGroupByCols) ? this.reportGroupByCols : [];
    const htmlRows = [];

    if (groupCols.length > 0) {
      const groupsMap = new Map();
      sorted.forEach(r => {
        const keyParts = groupCols.map(gk => `${gk}:${r[gk] ?? 'default'}`);
        const compositeKey = keyParts.join('||');
        if (!groupsMap.has(compositeKey)) {
          const descriptor = {};
          const labelParts = [];
          const allCols = this.ensureReportColumnsInitialized();
          groupCols.forEach(gk => {
            const val = r[gk] || 'default';
            descriptor[gk] = val;
            const colMeta = allCols.find(c => c.key === gk);
            labelParts.push(`${colMeta ? colMeta.label : gk}: ${val}`);
          });
          descriptor.label = labelParts.join(' • ');
          groupsMap.set(compositeKey, { descriptor, items: [] });
        }
        groupsMap.get(compositeKey).items.push(r);
      });

      groupsMap.forEach(groupEntry => {
        const { descriptor, items } = groupEntry;
        // Group Header Banner Row
        htmlRows.push(`
          <tr class="report-group-header-row" style="background: rgba(56, 189, 248, 0.08); border-top: 1px solid rgba(56, 189, 248, 0.25);">
            <td colspan="${colSpan}" style="padding: 7px 12px; font-size: 0.76rem; font-weight: 700; color: #38bdf8;">
              📂 Group: ${this.escapeHtml(descriptor.label)} <span style="color: var(--text-dim); font-weight: 500; margin-left: 6px;">(${items.length} line item${items.length === 1 ? '' : 's'})</span>
            </td>
          </tr>
        `);

        // Individual Line Items in Group
        items.forEach(r => {
          const cells = visibleCols.map(c => this._renderSingleReportCell(c, r, maxTokens, false)).join("");
          htmlRows.push(`<tr>${cells}</tr>`);
        });

        // Group Aggregate Subtotal Line-Item at End of Group
        if (this.reportIncludeGroupTotals) {
          const subtotalRow = this._aggregateReportGroup(items, descriptor);
          const subtotalCells = visibleCols.map((c, idx) => {
            if (idx === 0) {
              return `<td style="font-family: var(--font-mono); font-weight: 800; color: #38bdf8; white-space: nowrap;">Σ Subtotal (${this.escapeHtml(descriptor.label)})</td>`;
            }
            if (!c.numeric && c.key !== 'share' && !groupCols.includes(c.key)) {
              return `<td style="color: var(--text-dim); font-size: 0.72rem; font-style: italic;">(${items.length} items)</td>`;
            }
            return this._renderSingleReportCell(c, subtotalRow, maxTokens, true);
          }).join("");
          htmlRows.push(`
            <tr class="report-group-subtotal-row" style="background: rgba(15, 23, 42, 0.92); border-top: 1px dashed rgba(56, 189, 248, 0.45); border-bottom: 2px solid rgba(56, 189, 248, 0.3); font-weight: 700;">
              ${subtotalCells}
            </tr>
          `);
        }
      });
    } else {
      sorted.forEach(r => {
        const cells = visibleCols.map(c => this._renderSingleReportCell(c, r, maxTokens, false)).join("");
        htmlRows.push(`<tr>${cells}</tr>`);
      });
    }

    // Grand Total Footer Line-Item
    if (sorted.length > 1) {
      const grandTotal = this._aggregateReportGroup(sorted, { label: 'Grand Total' });
      const grandTotalCells = visibleCols.map((c, idx) => {
        if (idx === 0) {
          return `<td style="font-family: var(--font-mono); font-weight: 800; color: #f8fafc; white-space: nowrap;">∑ GRAND TOTAL (${sorted.length} rows)</td>`;
        }
        if (!c.numeric && c.key !== 'share') {
          return `<td style="color: var(--text-dim); font-size: 0.72rem;">All Filtered</td>`;
        }
        return this._renderSingleReportCell(c, grandTotal, Math.max(grandTotal.total_tokens, 1), true);
      }).join("");
      htmlRows.push(`
        <tr class="report-grand-total-row" style="background: rgba(30, 41, 59, 0.95); border-top: 2px solid rgba(255, 255, 255, 0.25); font-weight: 800;">
          ${grandTotalCells}
        </tr>
      `);
    }

    tbody.innerHTML = htmlRows.join("");
  },

  async loadPivotMatrix() {
    const tbody = document.getElementById("pivot-matrix-table-body");
    if (!tbody) return;

    const dims = document.getElementById("pivot-dimensions-select")?.value || "platform,model,source";
    const win = document.getElementById("pivot-window-select")?.value || "24h";
    const prov = document.getElementById("report-filter-provider")?.value || "";
    const src = document.getElementById("report-filter-source")?.value || "";
    const mdl = document.getElementById("report-filter-model")?.value?.trim() || "";
    const inst = document.getElementById("report-filter-instance")?.value?.trim() || "";
    const cip = document.getElementById("report-filter-client-ip")?.value?.trim() || "";

    const params = new URLSearchParams({ dimensions: dims, window: win });
    if (prov) params.set("filter_platform", prov);
    if (src) params.set("filter_source", src);
    if (mdl) params.set("filter_model", mdl);
    if (inst) params.set("filter_instance", inst);
    if (cip) params.set("filter_client", cip);

    try {
      const res = await fetch(`/api/usage/pivot?${params.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      const rows = data.rows || [];
      if (!rows.length) {
        tbody.innerHTML = `
          <tr>
            <td colspan="7" style="text-align: center; color: var(--text-dim); padding: 18px;">
              No pivot telemetry recorded for the selected window.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = rows.map(r => {
        const keyParts = [];
        if (r.group) keyParts.push(`🏷️ ${r.group}`);
        if (r.provider) keyParts.push(r.provider.toUpperCase());
        if (r.account_id) keyParts.push(r.account_id);
        if (r.client_alias || r.client_ip) keyParts.push(`${r.client_alias || r.client_ip}`);
        if (r.instance_id) keyParts.push(`Node: ${r.instance_id}`);
        if (r.project_id) keyParts.push(`Proj: ${r.project_id}`);
        if (r.model) keyParts.push(r.model);
        if (r.source) keyParts.push(`[${r.source}]`);
        const compositeLabel = keyParts.join("  •  ") || "All";

        return `
          <tr>
            <td style="font-weight: 600; color: #e2e8f0; font-size: 0.8rem;">${this.escapeHtml(compositeLabel)}</td>
            <td style="font-family: var(--font-mono); text-align: right; color: var(--text-muted);">${Number(r.request_count || 0).toLocaleString()}</td>
            <td style="font-family: var(--font-mono); text-align: right;">${Number(r.input_tokens || 0).toLocaleString()}</td>
            <td style="font-family: var(--font-mono); text-align: right;">${Number(r.output_tokens || 0).toLocaleString()}</td>
            <td style="font-family: var(--font-mono); font-weight: 700; color: #38bdf8; text-align: right;">${Number(r.total_tokens || 0).toLocaleString()}</td>
            <td style="font-family: var(--font-mono); font-weight: 700; color: #34d399; text-align: right;">$${Number(r.estimated_cost || 0).toFixed(4)}</td>
            <td style="font-family: var(--font-mono); text-align: right; color: #c084fc;">${Number(r.percentage_share || 0).toFixed(1)}%</td>
          </tr>
        `;
      }).join("");
    } catch (e) {
      console.warn("Error loading pivot matrix:", e);
    }
  },

  exportReportsCsv() {
    const params = this._collectReportFilterParams();
    params.set("format", "csv");
    window.location.href = `/api/reports/history?${params.toString()}`;
  },

  generateInlineSparkline(points, color = "#06b6d4") {
    if (!points || points.length < 2) return "";
    const min = Math.min(...points);
    const max = Math.max(...points);
    const isAllZero = points.every(p => p === 0);
    const w = 110;
    const h = 26;
    const pad = 3;

    if (isAllZero || (min === 0 && max === 0)) {
      const yZero = (h - pad).toFixed(1);
      return `
        <svg width="${w}" height="${h}" style="background: rgba(0,0,0,0.25); border-radius: 4px; border: 1px solid rgba(255,255,255,0.06);" title="No activity in window (0 tokens)">
          <line x1="${pad}" y1="${yZero}" x2="${w - pad}" y2="${yZero}" stroke="rgba(255,255,255,0.18)" stroke-width="1.5" stroke-dasharray="2,2"/>
          <text x="${w / 2}" y="${h / 2 + 3}" fill="#64748b" font-size="8" text-anchor="middle" font-family="monospace">0 t (idle)</text>
        </svg>
      `;
    }

    const range = Math.max(1, max - min);
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
    this._lastLocalWindowUpdateTs = Date.now();
    const btnBal = document.getElementById("view-mode-btn-balances");
    const btnTrd = document.getElementById("view-mode-btn-trends");
    const trendWinCtrl = document.getElementById("trend-window-control");
    const viewModeSelect = document.getElementById("cfg-default-view-mode");
    if (btnBal) btnBal.className = mode === 'balances' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    if (btnTrd) btnTrd.className = mode === 'trends' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    if (trendWinCtrl) trendWinCtrl.style.display = mode === 'trends' ? 'flex' : 'none';
    if (viewModeSelect) viewModeSelect.value = mode;
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: { widget_view_mode: mode } })
    }).catch(() => {});
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
      const refreshCadence = document.getElementById("cfg-ui-refresh-cadence");
      const topRefreshCadence = document.getElementById("ui-refresh-cadence-select");
      const ollamaSync = document.getElementById("cfg-ollama-sync");
      const viewModeSelect = document.getElementById("cfg-default-view-mode");
      const defTrendWinSelect = document.getElementById("cfg-default-trend-window");

      if (autoResize && st.widget_auto_resize !== undefined) autoResize.checked = !!st.widget_auto_resize;
      if (fadeUnpinned && st.widget_fade_unpinned !== undefined) fadeUnpinned.checked = !!st.widget_fade_unpinned;
      if (hideParentExpand && st.widget_hide_parent_chart_on_expand !== undefined) hideParentExpand.checked = !!st.widget_hide_parent_chart_on_expand;
      if (showAxisLabels && st.show_axis_labels !== undefined) {
        showAxisLabels.checked = !!st.show_axis_labels;
        this.showAxisLabels = !!st.show_axis_labels;
      }
      if (themeSelect && st.widget_theme) themeSelect.value = st.widget_theme;
      if (pollCadence && st.poll_cadence_seconds) pollCadence.value = st.poll_cadence_seconds;
      if (st.ui_refresh_interval_seconds) {
        const intervalSec = Math.max(30, Math.min(300, parseInt(st.ui_refresh_interval_seconds, 10) || 30));
        if (refreshCadence) refreshCadence.value = intervalSec;
        if (topRefreshCadence) topRefreshCadence.value = intervalSec;
        this.refreshCadenceSeconds = intervalSec;
        this.resetPollingInterval(intervalSec);
      }
      if (ollamaSync && st.ollama_sync_interval) ollamaSync.value = st.ollama_sync_interval;
      if (viewModeSelect && st.widget_view_mode) viewModeSelect.value = st.widget_view_mode;
      const syncedWin = st.active_trend_window || st.default_trend_window;
      if (syncedWin) {
        this.chartWindow = syncedWin;
        this.trendWindow = syncedWin;
        if (defTrendWinSelect) defTrendWinSelect.value = syncedWin;
        const cWinSel = document.getElementById("chart-window-select");
        const tWinSel = document.getElementById("trend-window-select");
        if (cWinSel) cWinSel.value = syncedWin;
        if (tWinSel) tWinSel.value = syncedWin;
      }

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

      // Quota Tracking Mode (AIUM-618)
      const trackingMode = st.quota_tracking_mode || "individual";
      const radInd = document.getElementById("cfg-tracking-mode-individual");
      const radTeam = document.getElementById("cfg-tracking-mode-team");
      if (radInd && radTeam) {
        radInd.checked = (trackingMode === "individual");
        radTeam.checked = (trackingMode === "team");
      }
      this.updateTrackingModeBadges(trackingMode);

      // Proxy Bridges & Network Ports Configuration (AIUM-707)
      const ollamaPortInput = document.getElementById("cfg-ollama-emulator-port");
      const proxyPortInput = document.getElementById("cfg-transparent-proxy-port");
      const defWinInput = document.getElementById("cfg-default-session-window");
      const defSessInput = document.getElementById("cfg-default-session-limit");
      const defDailyInput = document.getElementById("cfg-default-daily-limit");

      const ollamaPort = st.ollama_emulator_port || 8989;
      const proxyPort = st.transparent_proxy_port || 8766;

      if (ollamaPortInput) ollamaPortInput.value = ollamaPort;
      if (proxyPortInput) proxyPortInput.value = proxyPort;
      if (defWinInput) defWinInput.value = st.default_session_window_minutes || 15;
      if (defSessInput) defSessInput.value = st.default_session_token_limit || 25000;
      if (defDailyInput) defDailyInput.value = st.default_daily_token_limit || 250000;

      // Update Live Proxy Bridge endpoints in the guidance ribbon
      const bridgeOllamaUrl = document.getElementById("bridge-guide-ollama-url");
      const bridgeOpenAiUrl = document.getElementById("bridge-guide-openai-url");
      const bridgeProxyUrl = document.getElementById("bridge-guide-proxy-url");
      if (bridgeOllamaUrl) bridgeOllamaUrl.innerText = `http://127.0.0.1:${ollamaPort}`;
      if (bridgeOpenAiUrl) bridgeOpenAiUrl.innerText = `http://127.0.0.1:${ollamaPort}/v1`;
      if (bridgeProxyUrl) bridgeProxyUrl.innerText = `http://127.0.0.1:${proxyPort}`;

      // Load Windows Auto-Start & Background Service status (AIUM-901)
      this.loadWindowsServiceStatus(false);
    } catch (e) {
      console.warn("Error loading settings:", e);
    }
  },

  async loadWindowsServiceStatus(includeLogs = false) {
    try {
      const res = await fetch(`/api/system/startup?logs=${includeLogs ? "true" : "false"}`);
      if (!res.ok) return;
      const data = await res.json();
      this.renderWindowsServiceStatus(data);
    } catch (e) {
      console.warn("Error loading Windows service status:", e);
    }
  },

  renderWindowsServiceStatus(data) {
    if (!data) return;
    const startup = data.startup || data;
    const enabledChk = document.getElementById("cfg-win-autostart-enabled");
    const widgetChk = document.getElementById("cfg-win-autostart-widget");
    const watchdogChk = document.getElementById("cfg-win-autostart-watchdog");
    const methodSel = document.getElementById("cfg-win-autostart-method");

    if (enabledChk) enabledChk.checked = !!startup.enabled;
    if (widgetChk) widgetChk.checked = !!startup.launch_widget;
    if (watchdogChk && startup.auto_restart_on_crash !== undefined) {
      watchdogChk.checked = !!startup.auto_restart_on_crash;
    }
    if (methodSel && startup.preferred_method) {
      methodSel.value = startup.preferred_method;
    }

    const startupBadge = document.getElementById("win-startup-badge");
    if (startupBadge) {
      if (startup.enabled) {
        const methodLabel = startup.method === "task_scheduler" ? "Task Scheduler" : (startup.method === "both" ? "Dual" : "Registry Run");
        startupBadge.innerText = `🟢 Auto-Start Active (${methodLabel})`;
        startupBadge.style.background = "rgba(16, 185, 129, 0.15)";
        startupBadge.style.color = "#34d399";
        startupBadge.style.borderColor = "rgba(16, 185, 129, 0.35)";
      } else {
        startupBadge.innerText = "⚪ Auto-Start Disabled";
        startupBadge.style.background = "rgba(148, 163, 184, 0.15)";
        startupBadge.style.color = "#94a3b8";
        startupBadge.style.borderColor = "rgba(148, 163, 184, 0.25)";
      }
    }

    const runningBadge = document.getElementById("win-service-running-badge");
    if (runningBadge) {
      if (data.running) {
        const modeTxt = data.mode === "daemon" ? "Daemon" : "Active";
        runningBadge.innerText = `⚡ ${modeTxt} (PID ${data.pid || "--"})`;
        runningBadge.style.background = "rgba(56, 189, 248, 0.15)";
        runningBadge.style.color = "#38bdf8";
      } else {
        runningBadge.innerText = "⏹ Stopped";
        runningBadge.style.background = "rgba(239, 68, 68, 0.15)";
        runningBadge.style.color = "#f87171";
      }
    }

    const pidEl = document.getElementById("win-svc-pid");
    if (pidEl) pidEl.innerText = data.pid ? `${data.pid}` : "--";

    const uptimeEl = document.getElementById("win-svc-uptime");
    if (uptimeEl) {
      const sec = parseInt(data.uptime_seconds || 0, 10);
      if (sec > 3600) {
        uptimeEl.innerText = `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
      } else if (sec > 60) {
        uptimeEl.innerText = `${Math.floor(sec / 60)}m ${sec % 60}s`;
      } else {
        uptimeEl.innerText = `${sec}s`;
      }
    }

    const logSizeEl = document.getElementById("win-svc-log-size");
    if (logSizeEl) {
      const kb = ((data.log_size_bytes || 0) / 1024).toFixed(1);
      logSizeEl.innerText = `${kb} KB`;
    }

    const cmdEl = document.getElementById("win-svc-cmd");
    if (cmdEl && startup.command) {
      cmdEl.innerText = startup.command;
    }

    const logOut = document.getElementById("win-service-log-output");
    if (logOut && Array.isArray(data.recent_logs)) {
      logOut.innerText = data.recent_logs.length ? data.recent_logs.join("\n") : "No daemon log entries recorded yet.";
    }
  },

  async applyWindowsStartupConfig() {
    const enabledChk = document.getElementById("cfg-win-autostart-enabled");
    const widgetChk = document.getElementById("cfg-win-autostart-widget");
    const watchdogChk = document.getElementById("cfg-win-autostart-watchdog");
    const methodSel = document.getElementById("cfg-win-autostart-method");

    const payload = {
      enabled: enabledChk ? enabledChk.checked : false,
      launch_widget: widgetChk ? widgetChk.checked : false,
      auto_restart_on_crash: watchdogChk ? watchdogChk.checked : true,
      method: methodSel ? methodSel.value : "registry"
    };

    try {
      const res = await fetch("/api/system/startup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        await this.loadWindowsServiceStatus(false);
        if (typeof this.showToast === "function") {
          this.showToast(payload.enabled ? "Windows Auto-Start enabled." : "Windows Auto-Start disabled.", "success");
        }
      }
    } catch (e) {
      console.warn("Failed applying Windows startup config:", e);
    }
  },

  async controlWindowsService(action) {
    try {
      const widgetChk = document.getElementById("cfg-win-autostart-widget");
      const res = await fetch("/api/system/service", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: action,
          deferred: true,
          launch_widget: widgetChk ? widgetChk.checked : false
        })
      });
      if (res.ok) {
        if (action === "clear_logs") {
          await this.loadWindowsServiceStatus(true);
        } else if (action === "restart") {
          setTimeout(() => this.loadWindowsServiceStatus(true), 2200);
        } else {
          await this.loadWindowsServiceStatus(true);
        }
      }
    } catch (e) {
      console.warn("Error controlling Windows service:", e);
    }
  },

  toggleServiceLogViewer() {
    const panel = document.getElementById("win-service-log-panel");
    if (!panel) return;
    const isHidden = panel.style.display === "none";
    panel.style.display = isHidden ? "block" : "none";
    if (isHidden) {
      this.loadWindowsServiceStatus(true);
    }
  },

  async saveSettings() {
    const autoResize = document.getElementById("cfg-widget-auto-resize");
    const fadeUnpinned = document.getElementById("cfg-widget-fade-unpinned");
    const hideParentExpand = document.getElementById("cfg-widget-hide-parent-on-expand");
    const showAxisLabels = document.getElementById("cfg-show-axis-labels");
    const themeSelect = document.getElementById("cfg-widget-theme");
    const pollCadence = document.getElementById("cfg-poll-cadence");
    const refreshCadence = document.getElementById("cfg-ui-refresh-cadence");
    const ollamaSync = document.getElementById("cfg-ollama-sync");
    const viewModeSelect = document.getElementById("cfg-default-view-mode");
    const defTrendWinSelect = document.getElementById("cfg-default-trend-window");

    const checkedFont = document.querySelector("input[name='cfg-font-scale']:checked");
    const pinned = [];
    document.querySelectorAll(".cfg-pin-check:checked").forEach(c => pinned.push(c.value));

    const hiddenPlatforms = [];
    ["claude", "gemini", "chatgpt", "ollama", "copilot"].forEach(p => {
      const chk = document.getElementById(`vis-chk-${p}`);
      if (chk && !chk.checked) hiddenPlatforms.push(p);
    });

    const trackingModeRad = document.querySelector("input[name='cfg-tracking-mode']:checked");
    const quotaTrackingMode = trackingModeRad ? trackingModeRad.value : (this.appSettings?.quota_tracking_mode || "individual");

    // Bridge ports & defaults (AIUM-707)
    const ollamaPortInput = document.getElementById("cfg-ollama-emulator-port");
    const proxyPortInput = document.getElementById("cfg-transparent-proxy-port");
    const defWinInput = document.getElementById("cfg-default-session-window");
    const defSessInput = document.getElementById("cfg-default-session-limit");
    const defDailyInput = document.getElementById("cfg-default-daily-limit");

    const payload = {
      widget_auto_resize: autoResize ? autoResize.checked : true,
      widget_fade_unpinned: fadeUnpinned ? fadeUnpinned.checked : false,
      widget_hide_parent_chart_on_expand: hideParentExpand ? hideParentExpand.checked : false,
      show_axis_labels: showAxisLabels ? showAxisLabels.checked : true,
      widget_theme: themeSelect ? themeSelect.value : "obsidian_neon",
      widget_font_size: checkedFont ? checkedFont.value : "standard",
      poll_cadence_seconds: pollCadence ? parseInt(pollCadence.value, 10) || 4 : 4,
      ui_refresh_interval_seconds: refreshCadence ? Math.max(30, Math.min(300, parseInt(refreshCadence.value, 10) || 30)) : 30,
      ollama_sync_interval: ollamaSync ? parseInt(ollamaSync.value, 10) || 15 : 15,
      widget_view_mode: viewModeSelect ? viewModeSelect.value : "balances",
      default_trend_window: defTrendWinSelect ? defTrendWinSelect.value : (this.chartWindow || "24h"),
      active_trend_window: defTrendWinSelect ? defTrendWinSelect.value : (this.chartWindow || "24h"),
      pinned_items: pinned,
      quota_tracking_mode: quotaTrackingMode,
      ollama_emulator_port: parseInt(ollamaPortInput ? ollamaPortInput.value : "8989", 10) || 8989,
      transparent_proxy_port: parseInt(proxyPortInput ? proxyPortInput.value : "8766", 10) || 8766,
      default_session_window_minutes: parseInt(defWinInput ? defWinInput.value : "15", 10) || 15,
      default_session_token_limit: parseInt(defSessInput ? defSessInput.value : "25000", 10) || 25000,
      default_daily_token_limit: parseInt(defDailyInput ? defDailyInput.value : "250000", 10) || 250000,
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
        if (payload.ui_refresh_interval_seconds) {
          this.resetPollingInterval(payload.ui_refresh_interval_seconds);
          const topSelect = document.getElementById("ui-refresh-cadence-select");
          if (topSelect) topSelect.value = payload.ui_refresh_interval_seconds;
        }

        // Live update bridge guidance ribbon endpoints
        const bridgeOllamaUrl = document.getElementById("bridge-guide-ollama-url");
        const bridgeOpenAiUrl = document.getElementById("bridge-guide-openai-url");
        const bridgeProxyUrl = document.getElementById("bridge-guide-proxy-url");
        if (bridgeOllamaUrl) bridgeOllamaUrl.innerText = `http://127.0.0.1:${payload.ollama_emulator_port}`;
        if (bridgeOpenAiUrl) bridgeOpenAiUrl.innerText = `http://127.0.0.1:${payload.ollama_emulator_port}/v1`;
        if (bridgeProxyUrl) bridgeProxyUrl.innerText = `http://127.0.0.1:${payload.transparent_proxy_port}`;

        // Also persist to visibility endpoint
        await fetch("/api/settings/visibility", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload.estate_visibility)
        }).catch(() => {});
        alert("✅ Configuration successfully saved and encrypted into Windows DPAPI storage!");
        this.updateTrackingModeBadges(payload.quota_tracking_mode);
        await this.loadUsageData();
      }
    } catch (e) {
      alert("❌ Error saving settings: " + e.message);
    }
  },

  onTrackingModeOptionChange(mode) {
    this.updateTrackingModeBadges(mode);
  },

  updateTrackingModeBadges(mode) {
    const badge = document.getElementById("tracking-mode-active-badge");
    if (badge) {
      if (mode === "individual") {
        badge.innerText = "👤 Individual Direct Active";
        badge.style.background = "rgba(56, 189, 248, 0.15)";
        badge.style.color = "#38bdf8";
        badge.style.borderColor = "rgba(56, 189, 248, 0.3)";
      } else {
        badge.innerText = "👥 Team Pool Active";
        badge.style.background = "rgba(168, 85, 247, 0.15)";
        badge.style.color = "#c084fc";
        badge.style.borderColor = "rgba(168, 85, 247, 0.3)";
      }
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
          ${this.formatLocalDateTime(e.recorded_at)}
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

  // =========================================================================
  // Remote AI Managed Nodes, Device Inventory & LAN Discovery (AIUM-703, AIUM-704)
  // =========================================================================
  _attachedQueryFiles: [],
  _detectedAdapters: [],

  async fetchDetectedAdapters() {
    try {
      const res = await fetch("/api/discovery/adapters");
      const data = await res.json();
      if (res.ok && data.success && Array.isArray(data.adapters)) {
        this._detectedAdapters = data.adapters;
        const presetSelect = document.getElementById("lan-preset-select");
        const targetSpecInput = document.getElementById("lan-target-spec-input");
        if (presetSelect && this._detectedAdapters.length > 0) {
          const nonLoop = this._detectedAdapters.find(a => !a.ip.startsWith("127.")) || this._detectedAdapters[0];
          const autoOpt = presetSelect.querySelector('option[value="auto"]');
          if (autoOpt) {
            autoOpt.innerText = `Auto-Detect (${nonLoop.name}: ${nonLoop.subnet})`;
          }
          if (targetSpecInput && (!targetSpecInput.value || targetSpecInput.value === "10.1.7.0/24")) {
            targetSpecInput.value = nonLoop.subnet;
          }
        }
      }
    } catch (e) {
      console.warn("Could not fetch network adapters:", e);
    }
  },

  onSubnetPresetChange(presetValue) {
    const input = document.getElementById("lan-target-spec-input");
    if (!input) return;
    if (presetValue === "auto") {
      const nonLoop = (this._detectedAdapters || []).find(a => !a.ip.startsWith("127.")) || (this._detectedAdapters && this._detectedAdapters[0]);
      input.value = nonLoop ? nonLoop.subnet : "10.1.7.0/24";
    } else if (presetValue === "custom") {
      input.focus();
      input.select();
    } else {
      input.value = presetValue;
    }
  },

  toggleScanGuidance() {
    const panel = document.getElementById("lan-scan-guidance-panel");
    if (panel) {
      panel.style.display = panel.style.display === "none" ? "block" : "none";
    }
  },

  async scanLANAIServices() {
    const btn = document.getElementById("btn-scan-lan");
    const box = document.getElementById("lan-scan-results-box");
    const grid = document.getElementById("lan-discovered-nodes-grid");
    const statusText = document.getElementById("lan-scan-status-text");
    const targetSpecInput = document.getElementById("lan-target-spec-input");
    const secPortsInput = document.getElementById("lan-secondary-ports-input");

    const spec = (targetSpecInput && targetSpecInput.value.trim()) || "10.1.7.0/24";

    const platforms = [];
    if (document.getElementById("chk-platform-ollama")?.checked) platforms.push("ollama");
    if (document.getElementById("chk-platform-lmstudio")?.checked) platforms.push("lmstudio");
    if (document.getElementById("chk-platform-vllm")?.checked) platforms.push("vllm");
    if (document.getElementById("chk-platform-oobabooga")?.checked) platforms.push("oobabooga");
    if (document.getElementById("chk-platform-tabby")?.checked) platforms.push("tabby_kobold");
    if (document.getElementById("chk-platform-openwebui")?.checked) platforms.push("open_webui");

    const secPorts = (secPortsInput && secPortsInput.value.trim())
      ? secPortsInput.value.split(",").map(p => parseInt(p.trim(), 10)).filter(p => !isNaN(p))
      : [];

    if (btn) {
      btn.disabled = true;
      btn.innerText = "⏳ Scanning Network...";
    }
    if (box) box.style.display = "block";
    if (statusText) statusText.innerText = `Sweeping target range [${spec}] for selected platforms (${platforms.join(", ")})...`;
    if (grid) grid.innerHTML = '<div style="color: var(--text-dim); font-size: 0.8rem; padding: 10px;">Probing network hosts and fingerprinting AI endpoints... please wait ~2-3 seconds.</div>';

    try {
      const res = await fetch("/api/discovery/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          range: spec,
          platforms: platforms,
          secondary_ports: secPorts,
          timeout: 0.4
        })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        const candidates = data.candidates || [];
        if (statusText) {
          statusText.innerText = `Scan Complete: Discovered ${candidates.length} exposed AI instance(s) matching selected platforms.`;
        }
        if (candidates.length === 0) {
          if (grid) {
            grid.innerHTML = `
              <div style="color: var(--text-muted); font-size: 0.8rem; padding: 10px; grid-column: 1 / -1;">
                No exposed AI instances detected in range <code>${this.escapeHtml(spec)}</code>.<br>
                Ensure target devices have their firewall port open and local engines bound to <code>0.0.0.0</code> (e.g. <code>OLLAMA_HOST=0.0.0.0</code> on Windows).
              </div>
            `;
          }
        } else {
          if (grid) {
            grid.innerHTML = candidates.map(c => {
              const alias = c.alias || c.ip;
              return `
                <div style="background: rgba(15,23,42,0.95); border: 1px solid rgba(34,211,238,0.3); border-radius: var(--radius-sm); padding: 12px; display: flex; flex-direction: column; justify-content: space-between;">
                  <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                      <div>
                        <strong style="color: #fff; font-size: 0.88rem; display: block;">${this.escapeHtml(alias)}</strong>
                        <code style="font-size: 0.72rem; color: #38bdf8; font-family: var(--font-mono);">${c.ip}:${c.port}</code>
                      </div>
                      <span class="badge" style="background: rgba(34,211,238,0.15); color: #22d3ee; font-size: 0.68rem; text-transform: uppercase;">● ${c.engine}</span>
                    </div>
                    <div style="font-size: 0.72rem; color: var(--text-dim); margin-bottom: 6px;">
                      Latency: <span style="color: var(--accent-cyan); font-weight: 600;">${c.latency_ms}ms</span> &bull; Version: ${c.version || 'unknown'}
                    </div>
                    <div style="font-size: 0.72rem; color: var(--text-muted); margin-bottom: 10px; max-height: 48px; overflow-y: auto;">
                      ${(c.models && c.models.length > 0) ? c.models.map(m => `<span style="display: inline-block; background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 3px; margin: 2px;">${m.name || m}</span>`).join(' ') : 'No installed models listed'}
                    </div>
                  </div>
                  <div style="display: flex; gap: 6px;">
                    <button class="btn btn-primary btn-sm" style="font-size: 0.74rem; flex: 1;" onclick="window.App.quickRegisterNode('${c.endpoint}', '${this.escapeHtml(alias)} (${c.ip})', '${c.engine}', ${JSON.stringify(c.models || []).replace(/"/g, '&quot;')}, 1, 'Active Compute')">
                      ➕ Add to Compute Pool
                    </button>
                  </div>
                </div>
              `;
            }).join('');
          }
        }
        await this.loadDeviceInventory();
      } else {
        if (statusText) statusText.innerText = `Scan error: ${data.error || 'Request failed'}`;
      }
    } catch (e) {
      console.error("Scan LAN error:", e);
      if (statusText) statusText.innerText = "Network scan error: check console logs.";
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = "<span>📡</span> Scan Network";
      }
    }
  },

  async loadDeviceInventory() {
    const listEl = document.getElementById("lan-device-inventory-list");
    if (!listEl) return;

    try {
      const res = await fetch("/api/discovery/inventory");
      const data = await res.json();
      const inventory = (data && data.inventory) || [];

      if (inventory.length === 0) {
        listEl.innerHTML = `
          <div style="background: rgba(0,0,0,0.15); border: 1px dashed var(--border-subtle); border-radius: var(--radius-sm); padding: 12px; color: var(--text-dim); font-size: 0.78rem; text-align: center; grid-column: 1 / -1;">
            No known devices recorded in inventory yet. Click "Scan Network" to sweep your subnet and discover active hosts.
          </div>
        `;
        return;
      }

      listEl.innerHTML = inventory.map(dev => {
        let stateBadge = '';
        let borderColor = 'var(--border-subtle)';
        if (dev.state === 'KNOWN_SERVICES') {
          stateBadge = '<span class="badge" style="background: rgba(34,211,238,0.15); color: #22d3ee; border: 1px solid rgba(34,211,238,0.4); font-size: 0.68rem;">● Known Services</span>';
          borderColor = 'rgba(34,211,238,0.3)';
        } else if (dev.state === 'NO_SERVICES') {
          stateBadge = '<span class="badge" style="background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.4); font-size: 0.68rem;">● No AI Services</span>';
          borderColor = 'rgba(239,68,68,0.3)';
        } else {
          stateBadge = '<span class="badge" style="background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.4); font-size: 0.68rem;">● Pending / Unscanned</span>';
          borderColor = 'rgba(245,158,11,0.3)';
        }

        const isTrusted = dev.is_trusted !== 0;
        const trustBadge = isTrusted
          ? '<span class="badge" style="background: rgba(16,185,129,0.12); color: #34d399; font-size: 0.66rem;">🛡️ Trusted</span>'
          : '<span class="badge" style="background: rgba(239,68,68,0.15); color: #f87171; font-size: 0.66rem; font-weight: 700;">🚨 UNTRUSTED</span>';

        const services = dev.discovered_services || [];
        const servicesHtml = services.length > 0
          ? services.map(s => `<span style="display: inline-block; background: rgba(34,211,238,0.1); color: #a5f3fc; padding: 1px 6px; border-radius: 3px; margin: 2px; font-size: 0.7rem;">${s.engine} :${s.port}</span>`).join(' ')
          : '<span style="color: var(--text-muted); font-size: 0.7rem;">No AI ports responsive</span>';

        return `
          <div style="background: rgba(15,23,42,0.85); border: 1px solid ${borderColor}; border-radius: var(--radius-sm); padding: 10px 12px; display: flex; flex-direction: column; justify-content: space-between;">
            <div>
              <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;">
                <div>
                  <strong style="color: #fff; font-size: 0.88rem;">${this.escapeHtml(dev.alias)}</strong>
                  <code style="display: block; font-size: 0.72rem; color: var(--text-dim); font-family: var(--font-mono);">${this.escapeHtml(dev.ip)}</code>
                </div>
                ${stateBadge}
              </div>
              <div style="display: flex; gap: 6px; align-items: center; margin: 6px 0;">
                ${trustBadge}
                <span class="badge" style="background: rgba(255,255,255,0.06); color: var(--text-dim); font-size: 0.66rem;">${this.escapeHtml(dev.compute_group || 'Active Compute')}</span>
              </div>
              <div style="margin: 6px 0;">
                ${servicesHtml}
              </div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 6px; margin-top: 6px;">
              <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 6px;" onclick="window.App.toggleDeviceTrust('${this.escapeHtml(dev.alias)}', ${isTrusted ? 1 : 0})">
                ${isTrusted ? 'Mark Untrusted' : 'Mark Trusted'}
              </button>
              ${services.length > 0 ? `
                <button class="btn btn-primary btn-sm" style="font-size: 0.68rem; padding: 2px 8px;" onclick="window.App.quickRegisterNode('http://${dev.ip}:${services[0].port}', '${this.escapeHtml(dev.alias)}', '${services[0].engine}', ${JSON.stringify(services[0].models || []).replace(/"/g, '&quot;')}, ${isTrusted ? 1 : 0}, '${dev.compute_group || 'Active Compute'}')">
                  ➕ Add to Pool
                </button>
              ` : `
                <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 6px; color: #f87171;" onclick="window.App.deleteDeviceFromInventory('${this.escapeHtml(dev.alias)}')">
                  🗑️
                </button>
              `}
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      console.error("Error loading device inventory:", e);
    }
  },

  async toggleDeviceTrust(alias, currentTrust) {
    const newTrust = currentTrust ? 0 : 1;
    try {
      const dev = await (await fetch(`/api/discovery/inventory`)).json();
      const item = (dev.inventory || []).find(d => d.alias === alias);
      if (!item) return;

      await fetch("/api/discovery/inventory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          alias: alias,
          ip: item.ip,
          state: item.state,
          is_trusted: newTrust,
          compute_group: newTrust === 0 ? "Quarantined" : (item.compute_group === "Quarantined" ? "Active Compute" : item.compute_group),
          discovered_services: item.discovered_services || [],
          notes: item.notes || ""
        })
      });
      await this.loadDeviceInventory();
      await this.loadManagedNodes();
    } catch (e) {
      alert("Error toggling device trust: " + e.message);
    }
  },

  async deleteDeviceFromInventory(alias) {
    if (!confirm(`Remove ${alias} from device inventory?`)) return;
    try {
      await fetch(`/api/discovery/inventory?alias=${encodeURIComponent(alias)}`, { method: "DELETE" });
      await this.loadDeviceInventory();
    } catch (e) {
      alert("Error deleting device: " + e.message);
    }
  },

  async quickRegisterNode(endpoint, name, engine, models, isTrusted = 1, computeGroup = "Active Compute") {
    const concurrencyStr = prompt(`Set Max Concurrency for ${name} (requests allowed simultaneously):`, "1");
    if (concurrencyStr === null) return;
    const maxConcur = parseInt(concurrencyStr, 10) || 1;

    try {
      const res = await fetch("/api/discovery/nodes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name,
          endpoint: endpoint,
          engine: engine,
          max_concurrency: maxConcur,
          queue_timeout_seconds: 30.0,
          priority: isTrusted ? 5 : 1,
          is_trusted: isTrusted,
          compute_group: isTrusted ? computeGroup : "Quarantined",
          models: models || []
        })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        await this.loadManagedNodes();
        const box = document.getElementById("lan-scan-results-box");
        if (box) box.style.display = "none";
      } else {
        alert(data.error || "Failed to register node");
      }
    } catch (e) {
      console.error("Error registering node:", e);
      alert("Network error registering node");
    }
  },

  async openAddCustomNodeModal() {
    const endpoint = prompt("Enter Node Endpoint URL (e.g. http://10.1.7.74:11434):", "http://10.1.7.74:11434");
    if (!endpoint) return;
    const name = prompt("Enter Friendly Hostname/Name for Node:", "ASUS ROG (Jamese-PC)");
    if (!name) return;
    const engine = prompt("Enter Engine (ollama, lmstudio, vllm):", "ollama") || "ollama";
    const isTrustedChoice = confirm("Mark this device as a TRUSTED resource? (Cancel for Untrusted)");
    const isTrusted = isTrustedChoice ? 1 : 0;
    const group = isTrusted ? (prompt("Compute Group ('Active Compute', 'Staging', etc.):", "Active Compute") || "Active Compute") : "Quarantined";

    try {
      const res = await fetch("/api/discovery/nodes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name,
          endpoint: endpoint,
          engine: engine,
          max_concurrency: 1,
          queue_timeout_seconds: 30.0,
          priority: isTrusted ? 5 : 1,
          is_trusted: isTrusted,
          compute_group: group
        })
      });
      if (res.ok) {
        await this.loadManagedNodes();
      } else {
        alert("Failed to add custom node");
      }
    } catch (e) {
      alert("Error adding node: " + e.message);
    }
  },

  async loadManagedNodes() {
    const listEl = document.getElementById("managed-nodes-list");
    if (!listEl) return;

    try {
      const [nodesRes, telemRes] = await Promise.all([
        fetch("/api/discovery/nodes"),
        fetch("/api/discovery/telemetry")
      ]);
      const nodesData = await nodesRes.json();
      const telemData = await telemRes.json();

      const nodes = (nodesData && nodesData.nodes) || [];
      const telem = (telemData && telemData.telemetry && telemData.telemetry.nodes) || {};

      this.populateQueryTargetDropdown(nodes);

      if (nodes.length === 0) {
        listEl.innerHTML = `
          <div style="background: rgba(0,0,0,0.2); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 14px; color: var(--text-dim); font-size: 0.8rem; text-align: center; grid-column: 1 / -1;">
            No remote compute nodes registered. Click "Scan Network" or "Add Custom Endpoint" to register instances.
          </div>
        `;
        return;
      }

      listEl.innerHTML = nodes.map(n => {
        const nTelem = telem[n.id] || { active_requests: 0, queued_requests: 0, total_tokens_routed: 0 };
        const statusColor = n.status === 'ONLINE' ? '#34d399' : (n.status === 'BUSY' ? '#fbbf24' : '#f87171');
        const isTrusted = n.is_trusted !== 0;

        const trustBadge = isTrusted
          ? '<span class="badge" style="background: rgba(16,185,129,0.15); color: #34d399; font-size: 0.66rem; font-weight: 600;">🛡️ Trusted</span>'
          : '<span class="badge" style="background: rgba(239,68,68,0.2); color: #f87171; font-size: 0.66rem; font-weight: 700; border: 1px solid #ef4444;">🚨 UNTRUSTED</span>';

        const groupBadge = `<span class="badge" style="background: rgba(6,182,212,0.12); color: var(--accent-cyan); font-size: 0.66rem;">Group: ${this.escapeHtml(n.compute_group || 'Active Compute')}</span>`;

        const engineIcons = {
          ollama: '🦙 Ollama',
          lmstudio: '🤖 LM Studio',
          vllm: '⚡ vLLM / LocalAI',
          oobabooga: '📜 Text Gen WebUI',
          tabby_kobold: '🐱 Tabby / Kobold',
          open_webui: '🌐 Open WebUI'
        };
        const engineLabel = engineIcons[n.engine?.toLowerCase()] || `⚡ ${(n.engine || 'ollama').toUpperCase()}`;

        let modelsList = [];
        try {
          modelsList = Array.isArray(n.models) ? n.models : JSON.parse(n.models_json || "[]");
        } catch(e) { modelsList = []; }

        const modelsChips = modelsList.length > 0
          ? modelsList.map(m => {
              const mName = typeof m === 'object' ? (m.name || 'model') : String(m);
              const mParam = (typeof m === 'object' && m.parameter_size) ? ` (${m.parameter_size})` : '';
              return `<span style="display: inline-flex; align-items: center; background: rgba(34,211,238,0.08); border: 1px solid rgba(34,211,238,0.25); color: #a5f3fc; font-size: 0.67rem; padding: 1px 6px; border-radius: 4px; font-family: var(--font-mono); margin: 2px; cursor: pointer;" title="Click to use in Query Console" onclick="window.App.selectNodeAndModel('${n.id}', '${this.escapeHtml(mName)}')">🏷️ ${this.escapeHtml(mName)}${mParam}</span>`;
            }).join('')
          : '<span style="color: var(--text-dim); font-size: 0.68rem; font-style: italic;">No installed models listed</span>';

        const cardBorder = isTrusted ? 'var(--border-subtle)' : '1px solid rgba(239, 68, 68, 0.45)';
        const firstModel = modelsList.length > 0 ? (typeof modelsList[0] === 'object' ? (modelsList[0].name || '') : String(modelsList[0])) : 'llama3:latest';

        return `
          <div style="background: rgba(15,23,42,0.92); border: ${cardBorder}; border-radius: var(--radius-sm); padding: 12px; display: flex; flex-direction: column; justify-content: space-between;">
            <div>
              <!-- Prominent Alias & IP Header -->
              <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                <div>
                  <strong style="color: ${isTrusted ? '#fff' : '#fca5a5'}; font-size: 0.92rem; display: flex; align-items: center; gap: 5px;">
                    <span>💻</span> ${this.escapeHtml(n.name)}
                  </strong>
                  <code style="font-size: 0.72rem; color: #38bdf8; font-family: var(--font-mono);">${this.escapeHtml(n.endpoint)}</code>
                </div>
                <div style="display: flex; gap: 4px; align-items: center;">
                  <span class="badge" style="background: rgba(34,211,238,0.12); color: #22d3ee; font-size: 0.66rem;">${engineLabel}</span>
                  <span class="badge" style="background: rgba(255,255,255,0.06); color: ${statusColor}; font-size: 0.66rem; border: 1px solid rgba(255,255,255,0.1);">
                    ● ${n.status}
                  </span>
                </div>
              </div>

              <!-- Badges & Sub-strip -->
              <div style="display: flex; gap: 5px; margin: 6px 0; font-size: 0.68rem; flex-wrap: wrap;">
                ${trustBadge}
                ${groupBadge}
                <span class="badge" style="background: rgba(255,255,255,0.05); color: #e2e8f0; font-size: 0.66rem;">Priority: ${n.priority || 5}</span>
                <span class="badge" style="background: rgba(6,182,212,0.1); color: var(--accent-cyan); font-size: 0.66rem;">Max Concur: ${n.max_concurrency}</span>
              </div>

              <!-- Available Models List (Compact Chip Cluster) -->
              <div style="margin: 8px 0 6px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                  <span style="font-size: 0.7rem; color: var(--text-dim); font-weight: 600;">Available Models (${modelsList.length}):</span>
                  <button type="button" class="btn btn-secondary btn-sm" style="font-size: 0.64rem; padding: 1px 5px;" onclick="window.App.selectNodeAndModel('${n.id}', '${this.escapeHtml(firstModel)}')">⚡ Query Node</button>
                </div>
                <div style="max-height: 58px; overflow-y: auto; background: rgba(0,0,0,0.25); border-radius: 4px; padding: 4px 6px;">
                  ${modelsChips}
                </div>
              </div>

              <!-- Live High-Density Telemetry Strip -->
              <div style="display: flex; gap: 8px; margin: 6px 0; font-size: 0.68rem; color: var(--text-dim); border-top: 1px dashed rgba(255,255,255,0.06); padding-top: 6px;">
                <span>Active: <strong style="color: #67e8f9;">${nTelem.active_requests}</strong></span>
                <span>Queued: <strong style="color: #fbbf24;">${nTelem.queued_requests}</strong></span>
                <span>Tokens: <strong style="color: #f1f5f9;">${(nTelem.total_tokens_routed || 0).toLocaleString()}</strong></span>
              </div>
            </div>

            <!-- Action Buttons -->
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 6px;">
              <div style="display: flex; gap: 4px;">
                <button class="btn btn-secondary btn-sm" style="font-size: 0.66rem; padding: 2px 6px;" onclick="window.App.toggleNodeTrust('${n.id}', ${isTrusted ? 1 : 0})">
                  ${isTrusted ? 'Mark Untrusted' : 'Mark Trusted'}
                </button>
                <button class="btn btn-secondary btn-sm" style="font-size: 0.66rem; padding: 2px 6px;" onclick="window.App.changeNodeGroup('${n.id}', '${this.escapeHtml(n.compute_group || 'Active Compute')}')">
                  Group...
                </button>
              </div>
              <button class="btn btn-secondary btn-sm" style="font-size: 0.66rem; color: #f87171; padding: 2px 6px;" onclick="window.App.deleteManagedNode('${n.id}')">
                🗑️
              </button>
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      console.error("Error loading managed nodes:", e);
    }
  },

  selectNodeAndModel(nodeId, modelName) {
    const targetSelect = document.getElementById("query-target-select");
    const modelInput = document.getElementById("query-model-input");
    const promptInput = document.getElementById("query-prompt-input");

    if (targetSelect) {
      targetSelect.value = "node:" + nodeId;
      this.onQueryTargetChanged(targetSelect.value);
    }
    if (modelInput && modelName) {
      modelInput.value = modelName;
    }
    if (promptInput) {
      promptInput.focus();
      promptInput.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  },

  // --- Proxy Bridges Guidance & Helper Methods (AIUM-707) ---
  copyToClipboard(text, btnElement) {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        if (btnElement) {
          const orig = btnElement.innerHTML;
          btnElement.innerHTML = "✓ Copied!";
          btnElement.style.color = "#34d399";
          setTimeout(() => {
            btnElement.innerHTML = orig;
            btnElement.style.color = "";
          }, 2000);
        }
      }).catch(() => {
        this.fallbackCopyText(text, btnElement);
      });
    } else {
      this.fallbackCopyText(text, btnElement);
    }
  },

  fallbackCopyText(text, btnElement) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      if (btnElement) {
        const orig = btnElement.innerHTML;
        btnElement.innerHTML = "✓ Copied!";
        btnElement.style.color = "#34d399";
        setTimeout(() => {
          btnElement.innerHTML = orig;
          btnElement.style.color = "";
        }, 2000);
      }
    } catch (err) {
      console.warn("Fallback copy failed:", err);
    }
    document.body.removeChild(ta);
  },

  switchBridgeGuideTab(tabId) {
    document.querySelectorAll(".bridge-tab-btn").forEach(btn => {
      btn.className = "btn btn-sm btn-secondary bridge-tab-btn";
    });
    const activeBtn = document.getElementById(`btn-guide-${tabId}`);
    if (activeBtn) {
      activeBtn.className = "btn btn-sm btn-primary bridge-tab-btn";
    }

    document.querySelectorAll(".bridge-guide-pane").forEach(pane => {
      pane.style.display = "none";
    });
    const activePane = document.getElementById(`pane-guide-${tabId}`);
    if (activePane) {
      activePane.style.display = "block";
    }
  },

  allClients: [],
  clientFilterQuery: "",

  async loadClientQuotas() {
    const listEl = document.getElementById("lan-client-quotas-list");
    if (!listEl) return;

    try {
      const res = await fetch("/api/discovery/clients");
      const data = await res.json();
      const clients = (data && data.clients) || [];
      this.allClients = clients;

      // Update Aggregate Summary Bar
      const totalEl = document.getElementById("client-stat-total");
      const governedEl = document.getElementById("client-stat-governed");
      const unresEl = document.getElementById("client-stat-unrestricted");
      const blockedEl = document.getElementById("client-stat-blocked");
      const bypassEl = document.getElementById("client-stat-bypassed");

      let totalCount = clients.length;
      let blockedCount = 0;
      let unresCount = 0;
      let bypassCount = 0;
      let governedCount = 0;

      clients.forEach(c => {
        if (c.is_blocked !== 0) {
          blockedCount++;
        } else if (c.is_unrestricted !== 0) {
          unresCount++;
        } else if (c.is_bypass_active) {
          bypassCount++;
        } else {
          governedCount++;
        }
      });

      if (totalEl) totalEl.innerText = totalCount;
      if (blockedEl) blockedEl.innerText = blockedCount;
      if (unresEl) unresEl.innerText = unresCount;
      if (bypassEl) bypassEl.innerText = bypassCount;
      if (governedEl) governedEl.innerText = governedCount;

      this.filterClientCards(this.clientFilterQuery);
    } catch (e) {
      console.error("Error loading client quotas:", e);
    }
  },

  filterClientCards(query) {
    this.clientFilterQuery = (query || "").trim().toLowerCase();
    if (!this.allClients) return;
    if (!this.clientFilterQuery) {
      this.renderClientCards(this.allClients);
      return;
    }
    const filtered = this.allClients.filter(c => {
      const ip = (c.client_ip || "").toLowerCase();
      const alias = (c.alias || "").toLowerCase();
      const notes = (c.notes || "").toLowerCase();
      const isBlocked = c.is_blocked !== 0;
      const isUnres = c.is_unrestricted !== 0;
      const isBypass = !!c.is_bypass_active;
      const statusStr = isBlocked ? "blocked" : (isUnres ? "unrestricted" : (isBypass ? "bypass" : "governed"));
      return ip.includes(this.clientFilterQuery) ||
             alias.includes(this.clientFilterQuery) ||
             notes.includes(this.clientFilterQuery) ||
             statusStr.includes(this.clientFilterQuery);
    });
    this.renderClientCards(filtered);
  },

  renderClientCards(clients) {
    const listEl = document.getElementById("lan-client-quotas-list");
    if (!listEl) return;

    if (!clients || clients.length === 0) {
      listEl.innerHTML = `
        <div style="background: rgba(0,0,0,0.2); border: 1px dashed var(--border-subtle); border-radius: var(--radius-sm); padding: 14px; color: var(--text-dim); font-size: 0.78rem; text-align: center; grid-column: 1 / -1;">
          ${this.clientFilterQuery ? `No connected clients match the search "<strong>${this.escapeHtml(this.clientFilterQuery)}</strong>".` : 'No connecting clients registered yet. As external platforms and IDEs make requests to the Ollama bridge (port 8989) or transparent proxy (port 8766), their IP addresses and hostnames will be automatically discovered and governed here.'}
        </div>
      `;
      return;
    }

    listEl.innerHTML = clients.map(c => {
      const isBlocked = c.is_blocked !== 0;
      const isUnrestricted = c.is_unrestricted !== 0 && !isBlocked;
      const isBypass = c.is_bypass_active && !isUnrestricted && !isBlocked;

      let statusBadge = '<span class="badge" style="background: rgba(6,182,212,0.15); color: #67e8f9; font-size: 0.66rem;">🛡️ Governed</span>';
      let cardBorder = 'var(--border-subtle)';
      let cardBg = 'rgba(15,23,42,0.85)';

      if (isBlocked) {
        statusBadge = '<span class="badge" style="background: rgba(239,68,68,0.25); color: #f87171; border: 1px solid rgba(239,68,68,0.4); font-size: 0.66rem; font-weight: 700;">🚫 BLOCKED (HTTP 403)</span>';
        cardBorder = '1px solid rgba(239,68,68,0.5)';
        cardBg = 'rgba(30,12,16,0.85)';
      } else if (isUnrestricted) {
        statusBadge = '<span class="badge" style="background: rgba(16,185,129,0.2); color: #34d399; font-size: 0.66rem; font-weight: 700;">⚡ UNRESTRICTED</span>';
        cardBorder = '1px solid rgba(16,185,129,0.4)';
      } else if (isBypass) {
        statusBadge = '<span class="badge" style="background: rgba(245,158,11,0.2); color: #fbbf24; font-size: 0.66rem; font-weight: 700;">⏳ TEMPORARY BYPASS ACTIVE</span>';
        cardBorder = '1px solid rgba(245,158,11,0.4)';
      }

      const sessLimit = c.session_token_limit || 25000;
      const sessUsed = c.session_tokens_used || 0;
      const sessPct = Math.min(100, Math.round((sessUsed / sessLimit) * 100));

      const dailyLimit = c.daily_token_limit || 250000;
      const dailyUsed = c.daily_tokens_used || 0;
      const dailyPct = Math.min(100, Math.round((dailyUsed / dailyLimit) * 100));

      const sessBarColor = isBlocked ? '#ef4444' : (sessPct > 85 ? 'var(--accent-rose)' : (sessPct > 60 ? 'var(--accent-amber)' : 'var(--accent-cyan)'));
      const dailyBarColor = isBlocked ? '#ef4444' : (dailyPct > 85 ? 'var(--accent-rose)' : (dailyPct > 60 ? 'var(--accent-amber)' : 'var(--accent-purple)'));

      return `
        <div style="background: ${cardBg}; border: ${cardBorder}; border-radius: var(--radius-sm); padding: 12px; display: flex; flex-direction: column; justify-content: space-between;">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
              <div>
                <strong style="color: #fff; font-size: 0.88rem; display: block;">💻 ${this.escapeHtml(c.alias || c.client_ip)}</strong>
                <code style="font-size: 0.72rem; color: #38bdf8; font-family: var(--font-mono);">${this.escapeHtml(c.client_ip)}</code>
              </div>
              ${statusBadge}
            </div>

            <div style="display: flex; gap: 6px; margin: 6px 0; font-size: 0.7rem; color: var(--text-muted); align-items: center; flex-wrap: wrap;">
              <span class="badge" style="background: rgba(255,255,255,0.06); color: #e2e8f0;">Priority: ${c.priority || 5}</span>
              <span style="color: var(--text-dim); font-size: 0.68rem;">Window: ${c.session_window_minutes || 15}m</span>
              ${c.notes ? `<span style="color: var(--text-dim); font-size: 0.68rem; font-style: italic;">• ${this.escapeHtml(c.notes)}</span>` : ''}
            </div>

            <!-- Session Burst Window Meter -->
            <div style="margin: 8px 0 6px 0;">
              <div style="display: flex; justify-content: space-between; font-size: 0.68rem; margin-bottom: 3px;">
                <span style="color: var(--text-dim);">Session Burst (${c.session_window_minutes || 15}m):</span>
                <span style="color: ${sessBarColor}; font-weight: 600;">${sessUsed.toLocaleString()} / ${sessLimit.toLocaleString()} tok (${sessPct}%)</span>
              </div>
              <div style="width: 100%; height: 5px; background: rgba(0,0,0,0.4); border-radius: 3px; overflow: hidden;">
                <div style="width: ${sessPct}%; height: 100%; background: ${sessBarColor}; transition: width 0.3s;"></div>
              </div>
            </div>

            <!-- Daily Rolling Quota Meter -->
            <div style="margin-bottom: 8px;">
              <div style="display: flex; justify-content: space-between; font-size: 0.68rem; margin-bottom: 3px;">
                <span style="color: var(--text-dim);">Daily Quota (24h):</span>
                <span style="color: ${dailyBarColor}; font-weight: 600;">${dailyUsed.toLocaleString()} / ${dailyLimit.toLocaleString()} tok (${dailyPct}%)</span>
              </div>
              <div style="width: 100%; height: 5px; background: rgba(0,0,0,0.4); border-radius: 3px; overflow: hidden;">
                <div style="width: ${dailyPct}%; height: 100%; background: ${dailyBarColor}; transition: width 0.3s;"></div>
              </div>
            </div>
          </div>

          <!-- Governance Action Toolbar -->
          <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 8px; margin-top: 6px; gap: 4px; flex-wrap: wrap;">
            <div style="display: flex; gap: 4px; align-items: center; flex-wrap: wrap;">
              <!-- 1-Click Block/Unblock -->
              ${isBlocked ? `
                <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 7px; color: #34d399; border-color: rgba(16,185,129,0.3);" onclick="window.App.toggleBlockClient('${this.escapeHtml(c.client_ip)}', false)" title="Unblock this client">🔓 Unblock</button>
              ` : `
                <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 7px; color: #f87171; border-color: rgba(239,68,68,0.3);" onclick="window.App.toggleBlockClient('${this.escapeHtml(c.client_ip)}', true)" title="Block client immediately (HTTP 403)">🚫 Block</button>
              `}

              <!-- 1-Click Unrestrict / Restrict -->
              ${isUnrestricted ? `
                <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 7px; color: #38bdf8;" onclick="window.App.toggleUnrestrictClient('${this.escapeHtml(c.client_ip)}', false)" title="Apply standard quota governance">🛡️ Restrict</button>
              ` : `
                <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 7px; color: #34d399;" onclick="window.App.toggleUnrestrictClient('${this.escapeHtml(c.client_ip)}', true)" title="Permanently unrestrict client">⚡ Unrestrict</button>
              `}

              <!-- Quick Temporary Bypasses -->
              <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 5px;" onclick="window.App.quickSetClientBypass('${this.escapeHtml(c.client_ip)}', 60)" title="Elevate with temporary bypass for 1 hour">+1h</button>
              <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 5px;" onclick="window.App.quickSetClientBypass('${this.escapeHtml(c.client_ip)}', 240)" title="Elevate with temporary bypass for 4 hours">+4h</button>
              <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 5px;" onclick="window.App.quickSetClientBypass('${this.escapeHtml(c.client_ip)}', 1440)" title="Elevate with temporary bypass for 24 hours">+24h</button>
              ${isBypass ? `<button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 5px; color: #f87171;" onclick="window.App.quickSetClientBypass('${this.escapeHtml(c.client_ip)}', 0)" title="Cancel temporary bypass">✕ Clear</button>` : ''}
            </div>

            <div style="display: flex; gap: 4px; align-items: center;">
              <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 6px;" onclick="window.App.openConfigureClientModal('${this.escapeHtml(c.client_ip)}')" title="Configure exact burst limits and window size">⚙️ Edit</button>
              <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; padding: 2px 6px;" onclick="window.App.resetClientTokens('${this.escapeHtml(c.client_ip)}')" title="Reset burst window and daily token counts">🔄 Reset</button>
              <button class="btn btn-secondary btn-sm" style="font-size: 0.68rem; color: #f87171; padding: 2px 6px;" onclick="window.App.deleteClientQuota('${this.escapeHtml(c.client_ip)}')" title="Delete custom policy">🗑️</button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  },

  async toggleBlockClient(clientIp, shouldBlock) {
    try {
      const res = await fetch("/api/discovery/clients", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_ip: clientIp,
          action: shouldBlock ? "block" : "unblock"
        })
      });
      if (res.ok) {
        await this.loadClientQuotas();
      } else {
        const d = await res.json().catch(() => ({}));
        alert(d.error || "Failed to toggle block status");
      }
    } catch (e) {
      alert("Error toggling block: " + e.message);
    }
  },

  async toggleUnrestrictClient(clientIp, shouldUnrestrict) {
    try {
      const res = await fetch("/api/discovery/clients", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_ip: clientIp,
          action: shouldUnrestrict ? "unrestrict" : "restrict"
        })
      });
      if (res.ok) {
        await this.loadClientQuotas();
      } else {
        const d = await res.json().catch(() => ({}));
        alert(d.error || "Failed to toggle unrestrict status");
      }
    } catch (e) {
      alert("Error toggling unrestrict: " + e.message);
    }
  },

  openConfigureClientModal(clientIp = "") {
    const modal = document.getElementById("client-quota-config-modal");
    if (!modal) return;

    const ipInput = document.getElementById("client-quota-form-ip");
    const aliasInput = document.getElementById("client-quota-form-alias");
    const winInput = document.getElementById("client-quota-form-window");
    const sessInput = document.getElementById("client-quota-form-session-limit");
    const dailyInput = document.getElementById("client-quota-form-daily-limit");
    const prioInput = document.getElementById("client-quota-form-priority");
    const unresInput = document.getElementById("client-quota-form-unrestricted");
    const blockedInput = document.getElementById("client-quota-form-blocked");
    const bypassInput = document.getElementById("client-quota-form-bypass-mins");
    const notesInput = document.getElementById("client-quota-form-notes");

    if (ipInput) {
      ipInput.value = clientIp || "192.168.2.";
      ipInput.disabled = !!clientIp;
    }
    if (aliasInput) aliasInput.value = "";
    if (winInput) winInput.value = "15";
    if (sessInput) sessInput.value = "25000";
    if (dailyInput) dailyInput.value = "250000";
    if (prioInput) prioInput.value = "5";
    if (unresInput) unresInput.checked = false;
    if (blockedInput) blockedInput.checked = false;
    if (bypassInput) bypassInput.value = "0";
    if (notesInput) notesInput.value = "";

    // If editing existing client, pre-fill values
    if (clientIp) {
      fetch("/api/discovery/clients")
        .then(r => r.json())
        .then(d => {
          const match = (d.clients || []).find(c => c.client_ip === clientIp);
          if (match) {
            if (aliasInput) aliasInput.value = match.alias || "";
            if (winInput) winInput.value = match.session_window_minutes || 15;
            if (sessInput) sessInput.value = match.session_token_limit || 25000;
            if (dailyInput) dailyInput.value = match.daily_token_limit || 250000;
            if (prioInput) prioInput.value = match.priority || 5;
            if (unresInput) unresInput.checked = match.is_unrestricted !== 0;
            if (blockedInput) blockedInput.checked = match.is_blocked !== 0;
            if (notesInput) notesInput.value = match.notes || "";
          }
        })
        .catch(() => {});
    }

    modal.classList.add("active");
  },

  closeClientQuotaModal() {
    const modal = document.getElementById("client-quota-config-modal");
    if (modal) modal.classList.remove("active");
  },

  async submitClientQuotaForm() {
    const ipInput = document.getElementById("client-quota-form-ip");
    const aliasInput = document.getElementById("client-quota-form-alias");
    const winInput = document.getElementById("client-quota-form-window");
    const sessInput = document.getElementById("client-quota-form-session-limit");
    const dailyInput = document.getElementById("client-quota-form-daily-limit");
    const prioInput = document.getElementById("client-quota-form-priority");
    const unresInput = document.getElementById("client-quota-form-unrestricted");
    const blockedInput = document.getElementById("client-quota-form-blocked");
    const bypassInput = document.getElementById("client-quota-form-bypass-mins");
    const notesInput = document.getElementById("client-quota-form-notes");

    const clientIp = (ipInput && ipInput.value.trim()) || "";
    if (!clientIp) {
      alert("Please enter a valid Client IP address.");
      return;
    }

    const payload = {
      client_ip: clientIp,
      alias: (aliasInput && aliasInput.value.trim()) || null,
      session_window_minutes: parseInt(winInput ? winInput.value : "15", 10) || 15,
      session_token_limit: parseInt(sessInput ? sessInput.value : "25000", 10) || 25000,
      daily_token_limit: parseInt(dailyInput ? dailyInput.value : "250000", 10) || 250000,
      priority: parseInt(prioInput ? prioInput.value : "5", 10) || 5,
      is_unrestricted: (unresInput && unresInput.checked) ? 1 : 0,
      is_blocked: (blockedInput && blockedInput.checked) ? 1 : 0,
      notes: (notesInput && notesInput.value.trim()) || ""
    };

    const bypassMins = parseFloat(bypassInput ? bypassInput.value : "0") || 0;
    if (bypassMins > 0) {
      const now = new Date();
      now.setMinutes(now.getMinutes() + bypassMins);
      payload.bypass_until = now.toISOString();
    }

    try {
      const res = await fetch("/api/discovery/clients", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.closeClientQuotaModal();
        await this.loadClientQuotas();
      } else {
        alert(data.error || "Failed to save client quota");
      }
    } catch (e) {
      alert("Error saving client policy: " + e.message);
    }
  },

  async quickSetClientBypass(clientIp, minutes) {
    try {
      const res = await fetch("/api/discovery/clients/bypass", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_ip: clientIp, duration_minutes: minutes })
      });
      if (res.ok) {
        await this.loadClientQuotas();
      }
    } catch (e) {
      alert("Error updating bypass: " + e.message);
    }
  },

  async resetClientTokens(clientIp) {
    if (!confirm(`Reset token counters for client ${clientIp}? This will clear burst and daily usage.`)) return;
    try {
      const res = await fetch(`/api/discovery/clients?client_ip=${encodeURIComponent(clientIp)}&action=reset`, { method: "DELETE" });
      if (res.ok) {
        await this.loadClientQuotas();
      }
    } catch (e) {
      alert("Error resetting tokens: " + e.message);
    }
  },

  async deleteClientQuota(clientIp) {
    if (!confirm(`Delete custom quota policy for ${clientIp}? Client will revert to default limits.`)) return;
    try {
      const res = await fetch(`/api/discovery/clients?client_ip=${encodeURIComponent(clientIp)}`, { method: "DELETE" });
      if (res.ok) {
        await this.loadClientQuotas();
      }
    } catch (e) {
      alert("Error deleting client policy: " + e.message);
    }
  },

  async toggleNodeTrust(nodeId, currentTrust) {
    const newTrust = currentTrust ? 0 : 1;
    try {
      await fetch("/api/discovery/nodes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_id: nodeId,
          is_trusted: newTrust,
          compute_group: newTrust === 0 ? "Quarantined" : "Active Compute"
        })
      });
      await this.loadManagedNodes();
    } catch (e) {
      alert("Error updating node trust: " + e.message);
    }
  },

  async changeNodeGroup(nodeId, currentGroup) {
    const newGroup = prompt(`Assign new compute group for this node (e.g. 'Active Compute', 'Staging', 'Offline'):`, currentGroup);
    if (!newGroup || newGroup === currentGroup) return;

    try {
      await fetch("/api/discovery/nodes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_id: nodeId,
          compute_group: newGroup
        })
      });
      await this.loadManagedNodes();
    } catch (e) {
      alert("Error updating compute group: " + e.message);
    }
  },

  populateQueryTargetDropdown(nodes) {
    const select = document.getElementById("query-target-select");
    if (!select) return;

    const currentVal = select.value;
    select.innerHTML = `
      <option value="pool" data-trusted="1">🚀 [Active Compute Pool] Auto-Route to Trusted Nodes (Failover Protected)</option>
    `;

    nodes.forEach(n => {
      const isTrusted = n.is_trusted !== 0;
      const opt = document.createElement("option");
      opt.value = "node:" + n.id;
      opt.setAttribute("data-trusted", isTrusted ? "1" : "0");
      if (isTrusted) {
        opt.innerText = `🛡️ ${n.name} (${n.endpoint}) [${n.compute_group || 'Active Compute'}]`;
      } else {
        opt.innerText = `🚨 [UNTRUSTED] ${n.name} (${n.endpoint}) [Quarantined]`;
        opt.style.color = "#f87171";
      }
      select.appendChild(opt);
    });

    if (currentVal) {
      select.value = currentVal;
    }
    this.onQueryTargetChanged(select.value);
  },

  onQueryTargetChanged(targetValue) {
    const select = document.getElementById("query-target-select");
    const warningBanner = document.getElementById("query-untrusted-warning-banner");
    const fileAlert = document.getElementById("query-file-untrusted-alert");

    const selectedOpt = select && select.options[select.selectedIndex];
    const isTrusted = selectedOpt ? selectedOpt.getAttribute("data-trusted") !== "0" : true;

    if (!isTrusted) {
      if (warningBanner) warningBanner.style.display = "block";
      if (fileAlert && (this._attachedQueryFiles || []).length > 0) {
        fileAlert.style.display = "block";
      }
    } else {
      if (warningBanner) warningBanner.style.display = "none";
      if (fileAlert) fileAlert.style.display = "none";
    }
  },

  handleQueryFilesSelected(files) {
    if (!files || files.length === 0) return;
    this._attachedQueryFiles = this._attachedQueryFiles || [];

    Array.from(files).forEach(f => {
      const reader = new FileReader();
      reader.onload = (e) => {
        this._attachedQueryFiles.push({
          filename: f.name,
          size: f.size,
          content: e.target.result
        });
        this.renderAttachedQueryFiles();
      };
      reader.readAsText(f);
    });
  },

  renderAttachedQueryFiles() {
    const container = document.getElementById("query-attached-files-container");
    const fileAlert = document.getElementById("query-file-untrusted-alert");
    const select = document.getElementById("query-target-select");
    const selectedOpt = select && select.options[select.selectedIndex];
    const isTrusted = selectedOpt ? selectedOpt.getAttribute("data-trusted") !== "0" : true;

    if (!container) return;

    if (!this._attachedQueryFiles || this._attachedQueryFiles.length === 0) {
      container.innerHTML = '<span style="font-size: 0.72rem; color: var(--text-dim); font-style: italic;">No context files attached. Click "Attach Files..." or drag &amp; drop code/text files here.</span>';
      if (fileAlert) fileAlert.style.display = "none";
      return;
    }

    container.innerHTML = this._attachedQueryFiles.map((f, idx) => `
      <span style="display: inline-flex; align-items: center; gap: 5px; background: rgba(6,182,212,0.15); border: 1px solid rgba(6,182,212,0.3); color: #67e8f9; font-size: 0.72rem; padding: 2px 8px; border-radius: 4px;">
        <span>📄 ${this.escapeHtml(f.filename)}</span>
        <span style="color: var(--text-dim); font-size: 0.65rem;">(${Math.round(f.size / 1024 * 10) / 10}KB)</span>
        <button type="button" onclick="window.App.removeAttachedQueryFile(${idx})" style="background: none; border: none; color: #f87171; cursor: pointer; padding: 0 2px; font-weight: bold;">✕</button>
      </span>
    `).join('');

    if (fileAlert) {
      fileAlert.style.display = !isTrusted ? "block" : "none";
    }
  },

  removeAttachedQueryFile(index) {
    if (this._attachedQueryFiles && this._attachedQueryFiles.length > index) {
      this._attachedQueryFiles.splice(index, 1);
      this.renderAttachedQueryFiles();
    }
  },

  async executeGovernedQuery() {
    const select = document.getElementById("query-target-select");
    const modelInput = document.getElementById("query-model-input");
    const promptInput = document.getElementById("query-prompt-input");
    const statusText = document.getElementById("query-run-status-text");
    const resultBox = document.getElementById("query-result-box");
    const nodeBadge = document.getElementById("query-result-node-badge");
    const modelBadge = document.getElementById("query-result-model-badge");
    const metricsEl = document.getElementById("query-result-metrics");
    const contentEl = document.getElementById("query-result-content");
    const btn = document.getElementById("btn-run-query");

    const target = (select && select.value) || "pool";
    const model = (modelInput && modelInput.value.trim()) || "llama3:latest";
    const prompt = (promptInput && promptInput.value.trim()) || "";

    if (!prompt) {
      alert("Please enter a prompt or instruction for the query.");
      return;
    }

    const selectedOpt = select && select.options[select.selectedIndex];
    const isUntrusted = selectedOpt && selectedOpt.getAttribute("data-trusted") === "0";

    if (isUntrusted) {
      const confirmRun = confirm(
        "⚠️ CAUTION: You are about to dispatch this query and attached files to an UNTRUSTED compute node.\n\n" +
        "Untrusted nodes are not verified and should never receive sensitive data or confidential source code.\n\n" +
        "Do you want to proceed anyway?"
      );
      if (!confirmRun) return;
    }

    if (btn) {
      btn.disabled = true;
      btn.innerText = "⏳ Dispatching...";
    }
    if (statusText) statusText.innerText = "Routing query through traffic governor queue...";
    if (resultBox) resultBox.style.display = "none";

    try {
      const res = await fetch("/api/discovery/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target: target,
          model: model,
          prompt: prompt,
          files: this._attachedQueryFiles || []
        })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        if (statusText) statusText.innerText = `Query completed successfully in ${data.queue_time_ms}ms.`;
        if (resultBox) resultBox.style.display = "block";
        if (nodeBadge) {
          nodeBadge.innerText = `Node: ${data.node_name || data.node_id}`;
          nodeBadge.style.color = data.is_untrusted_warning ? "#f87171" : "#67e8f9";
        }
        if (modelBadge) modelBadge.innerText = `Model: ${data.model}`;
        if (metricsEl) {
          metricsEl.innerText = `Input: ${data.input_tokens} • Output: ${data.output_tokens} • Queue/Latency: ${data.queue_time_ms}ms • Cost: $0.00`;
        }

        let respHtml = "";
        if (data.is_untrusted_warning) {
          respHtml += `<div style="background: rgba(239,68,68,0.2); border-left: 3px solid #ef4444; color: #fca5a5; padding: 6px 10px; margin-bottom: 8px; font-size: 0.74rem;">${this.escapeHtml(data.warning_message)}</div>\n`;
        }
        respHtml += this.escapeHtml(data.response || "(Empty response received)");
        if (contentEl) contentEl.innerHTML = respHtml;

        await this.loadManagedNodes();
        await this.loadClientQuotas();
      } else {
        if (statusText) statusText.innerText = `Query failed: ${data.error || 'Server error'}`;
        alert(`Error executing query: ${data.error || 'Unknown error'}`);
      }
    } catch (e) {
      console.error("Query execution error:", e);
      if (statusText) statusText.innerText = "Network error: check server logs.";
      alert("Network error: " + e.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = "<span>🚀</span> Execute Governed Query";
      }
    }
  },

  async deleteManagedNode(nodeId) {
    if (!confirm("Are you sure you want to remove this node from the managed pool?")) return;
    try {
      const res = await fetch(`/api/discovery/nodes?id=${encodeURIComponent(nodeId)}`, { method: "DELETE" });
      if (res.ok) {
        await this.loadManagedNodes();
      }
    } catch (e) {
      alert("Error removing node: " + e.message);
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
  },

  formatLocalDateTime(isoStr) {
    if (!isoStr) return "-";
    try {
      let s = String(isoStr).trim();
      if (!s) return "-";
      if (!s.endsWith("Z") && !/[+-]\d{2}:?\d{2}$/.test(s)) {
        s += "Z";
      }
      const d = new Date(s);
      if (isNaN(d.getTime())) return String(isoStr).replace("T", " ").substring(0, 19);
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      const hrs = String(d.getHours()).padStart(2, "0");
      const mins = String(d.getMinutes()).padStart(2, "0");
      const secs = String(d.getSeconds()).padStart(2, "0");
      return `${year}-${month}-${day} ${hrs}:${mins}:${secs}`;
    } catch (e) {
      return String(isoStr).replace("T", " ").substring(0, 19);
    }
  },

  formatLocalTime(isoStr) {
    if (!isoStr) return "-";
    try {
      let s = String(isoStr).trim();
      if (!s) return "-";
      if (!s.endsWith("Z") && !/[+-]\d{2}:?\d{2}$/.test(s)) {
        s += "Z";
      }
      const d = new Date(s);
      if (isNaN(d.getTime())) return String(isoStr);
      const hrs = String(d.getHours()).padStart(2, "0");
      const mins = String(d.getMinutes()).padStart(2, "0");
      return `${hrs}:${mins}`;
    } catch (e) {
      return String(isoStr);
    }
  },

  formatDuration(startIso, endIso) {
    if (!startIso || !endIso) return "-";
    try {
      let s1 = String(startIso).trim();
      let s2 = String(endIso).trim();
      if (!s1.endsWith("Z") && !/[+-]\d{2}:?\d{2}$/.test(s1)) s1 += "Z";
      if (!s2.endsWith("Z") && !/[+-]\d{2}:?\d{2}$/.test(s2)) s2 += "Z";
      const d1 = new Date(s1);
      const d2 = new Date(s2);
      const diffSec = Math.max(0, Math.floor((d2.getTime() - d1.getTime()) / 1000));
      if (diffSec < 60) return `${diffSec}s`;
      const mins = Math.floor(diffSec / 60);
      const secs = diffSec % 60;
      if (mins < 60) return `${mins}m ${secs}s`;
      const hrs = Math.floor(mins / 60);
      const remMins = mins % 60;
      if (hrs < 24) return `${hrs}h ${remMins}m`;
      const days = Math.floor(hrs / 24);
      const remHrs = hrs % 24;
      return `${days}d ${remHrs}h`;
    } catch (e) {
      return "-";
    }
  }
};

document.addEventListener("DOMContentLoaded", () => {
  window.App.init();
});
