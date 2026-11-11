/**
 * AI Usage Monitor - Shared Core API Client
 * Canonical data fetching, settings persistence, and multi-surface synchronization.
 * Connects Full Web UI, Floating Mini Widget, and Windows Tray.
 */

(function () {
  'use strict';

  const THEMES = {
    obsidian: {
      bg: 'rgba(8, 11, 17, 0.98)',
      cardBg: 'rgba(15, 22, 36, 0.94)',
      border: 'rgba(255, 255, 255, 0.12)'
    },
    obsidian_neon: {
      bg: 'rgba(8, 11, 17, 0.98)',
      cardBg: 'rgba(15, 22, 36, 0.94)',
      border: 'rgba(255, 255, 255, 0.12)'
    },
    cyberpunk: {
      bg: 'rgba(10, 8, 20, 0.98)',
      cardBg: 'rgba(26, 16, 45, 0.94)',
      border: 'rgba(244, 63, 94, 0.3)'
    },
    cyberpunk_pulse: {
      bg: 'rgba(10, 8, 20, 0.98)',
      cardBg: 'rgba(26, 16, 45, 0.94)',
      border: 'rgba(244, 63, 94, 0.3)'
    },
    matrix: {
      bg: 'rgba(4, 15, 8, 0.98)',
      cardBg: 'rgba(8, 28, 16, 0.94)',
      border: 'rgba(16, 185, 129, 0.3)'
    },
    matrix_emerald: {
      bg: 'rgba(4, 15, 8, 0.98)',
      cardBg: 'rgba(8, 28, 16, 0.94)',
      border: 'rgba(16, 185, 129, 0.3)'
    },
    midnight: {
      bg: 'rgba(15, 23, 42, 0.98)',
      cardBg: 'rgba(30, 41, 59, 0.94)',
      border: 'rgba(148, 163, 184, 0.2)'
    },
    midnight_slate: {
      bg: 'rgba(15, 23, 42, 0.98)',
      cardBg: 'rgba(30, 41, 59, 0.94)',
      border: 'rgba(148, 163, 184, 0.2)'
    }
  };

  /**
   * Fetches all server settings.
   * @returns {Promise<Object>}
   */
  async function getSettings() {
    const res = await fetch('/api/settings');
    if (!res.ok) {
      throw new Error(`Failed to fetch settings: HTTP ${res.status}`);
    }
    return await res.json();
  }

  /**
   * Saves partial settings dictionary to backend storage.
   * @param {Object} partialSettings 
   * @returns {Promise<Object>}
   */
  async function saveSettings(partialSettings) {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings: partialSettings })
    });
    if (!res.ok) {
      throw new Error(`Failed to save settings: HTTP ${res.status}`);
    }
    return await res.json();
  }

  /**
   * Returns available UI theme configurations.
   * @returns {Promise<Object>}
   */
  async function getThemes() {
    return THEMES;
  }

  /**
   * Returns telemetry hierarchy structure and definitions.
   * @returns {Promise<Object>}
   */
  async function getHierarchies() {
    try {
      const res = await fetch('/api/taxonomy');
      if (res.ok) return await res.json();
    } catch (_) {}
    return {
      providers: ['claude', 'gemini', 'chatgpt', 'ollama', 'copilot'],
      scopes: ['individual', 'team', 'enterprise']
    };
  }

  /**
   * Fetches hierarchical trends series for a provider and window.
   * Flexible signature supporting (windowStr, bucketMins, mode, scope) or (provider, windowStr, bucketMins, mode, scope).
   */
  async function getHierarchicalTrends(arg1 = '24h', arg2 = 5, arg3 = 'interval_delta', arg4 = 'individual', arg5 = 'claude') {
    let provider = 'claude';
    let windowStr = '24h';
    let bucketMins = 5;
    let mode = 'interval_delta';
    let scope = 'individual';

    const KNOWN_PROVIDERS = ['claude', 'gemini', 'chatgpt', 'ollama', 'copilot'];
    if (typeof arg1 === 'string' && KNOWN_PROVIDERS.includes(arg1.toLowerCase())) {
      provider = arg1.toLowerCase();
      windowStr = arg2 || '24h';
      bucketMins = arg3 || 5;
      mode = arg4 || 'interval_delta';
      scope = arg5 || 'individual';
    } else {
      windowStr = arg1 || '24h';
      bucketMins = arg2 || 5;
      mode = arg3 || 'interval_delta';
      scope = arg4 || 'individual';
      if (typeof arg5 === 'string' && KNOWN_PROVIDERS.includes(arg5.toLowerCase())) {
        provider = arg5.toLowerCase();
      }
    }

    const params = new URLSearchParams({
      provider: provider,
      window: windowStr,
      bucket_minutes: String(bucketMins),
      mode: mode,
      scope: scope
    });
    const res = await fetch(`/api/usage/trends/hierarchy?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch hierarchical trends: HTTP ${res.status}`);
    }
    return await res.json();
  }

  /**
   * Fetches granular timeseries breakdown.
   */
  async function getGranularTimeseries(windowStr = '24h', bucketMins = 5, mode = 'interval_delta', breakdown = 'consolidated', scope = 'individual') {
    const params = new URLSearchParams({
      window: windowStr,
      bucket_minutes: String(bucketMins),
      mode: mode,
      breakdown: breakdown,
      scope: scope
    });
    const res = await fetch(`/api/usage/timeseries?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch granular timeseries: HTTP ${res.status}`);
    }
    return await res.json();
  }

  /**
   * Synchronizes active application icon across localStorage, Web UI, Mini Widget, and Windows Tray.
   * @param {string} iconId 
   * @returns {Promise<Object>}
   */
  async function syncActiveIcon(iconId) {
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.setItem('aium_active_icon', iconId);
      } catch (_) {}
    }
    return await saveSettings({ active_icon: iconId });
  }

  const ApiClient = {
    getSettings,
    saveSettings,
    getThemes,
    getHierarchies,
    getHierarchicalTrends,
    getGranularTimeseries,
    syncActiveIcon
  };

  // Attach to window namespace
  if (typeof window !== 'undefined') {
    window.AIUMCore = window.AIUMCore || {};
    window.AIUMCore.ApiClient = ApiClient;
  }

  // Node / CommonJS export support for automated verification
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ApiClient;
  }
})();
