/**
 * AI Usage Monitor - Shared Core Formatters
 * Canonical formatting utilities for tokens, currency, countdowns, timestamps, and safe HTML escaping.
 * Shared across Full Web UI, Floating Mini Widget, and Native Tray components.
 */

(function () {
  'use strict';

  const PROVIDER_COLORS = {
    claude: '#f59e0b',
    ollama: '#10b981',
    gemini: '#3b82f6',
    copilot: '#8b5cf6',
    chatgpt: '#10b981'
  };

  const PROVIDER_NAMES = {
    claude: 'Claude',
    ollama: 'Ollama',
    gemini: 'Google Gemini',
    copilot: 'M365 Copilot',
    chatgpt: 'ChatGPT'
  };

  /**
   * Formats token quantities into human-readable compact notation (e.g. 1.2M, 45.3k, 850).
   * @param {number|string} n 
   * @returns {string}
   */
  function formatTokens(n) {
    if (n === null || n === undefined || isNaN(n)) return '0';
    const num = Number(n);
    if (num === 0) return '0';
    const sign = num < 0 ? '-' : '';
    const abs = Math.abs(num);
    if (abs >= 1e9) {
      return sign + (abs / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
    }
    if (abs >= 1e6) {
      return sign + (abs / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
    }
    if (abs >= 1e3) {
      return sign + (abs / 1e3).toFixed(1).replace(/\.0$/, '') + 'k';
    }
    return sign + Math.round(abs).toString();
  }

  /**
   * Formats USD currency values ($0.00, $0.0042, etc.).
   * @param {number|string} usd 
   * @param {number} decimals 
   * @returns {string}
   */
  function formatCurrency(usd, decimals = 2) {
    if (usd === null || usd === undefined || isNaN(usd)) return '$0.00';
    const num = Number(usd);
    if (num === 0) return '$0.00';
    const sign = num < 0 ? '-$' : '$';
    const abs = Math.abs(num);
    if (abs > 0 && abs < 0.01 && decimals <= 2) {
      return sign + abs.toFixed(4);
    }
    return sign + abs.toFixed(decimals);
  }

  /**
   * Formats reset epoch or ISO timestamp into compact countdown string (e.g. '2h 14m' or '45m 12s').
   * @param {number|string} resetEpochOrIso 
   * @param {string} fallbackStr 
   * @returns {string}
   */
  function formatCountdown(resetEpochOrIso, fallbackStr = '') {
    if (!resetEpochOrIso) return fallbackStr;
    let targetSec = 0;
    if (typeof resetEpochOrIso === 'number') {
      targetSec = resetEpochOrIso > 1e11 ? resetEpochOrIso / 1000 : resetEpochOrIso;
    } else {
      const s = String(resetEpochOrIso).trim();
      if (!s) return fallbackStr;
      if (/^\d+(\.\d+)?$/.test(s)) {
        const n = parseFloat(s);
        targetSec = n > 1e11 ? n / 1000 : n;
      } else {
        const ms = new Date(s).getTime();
        if (isNaN(ms)) return fallbackStr;
        targetSec = ms / 1000;
      }
    }
    const nowSec = Date.now() / 1000;
    const diffSec = Math.max(0, Math.floor(targetSec - nowSec));
    if (diffSec <= 0) return fallbackStr || '0m 0s';
    if (diffSec >= 3600) {
      const hrs = Math.floor(diffSec / 3600);
      const mins = Math.floor((diffSec % 3600) / 60);
      return `${hrs}h ${mins}m`;
    }
    const mins = Math.floor(diffSec / 60);
    const secs = diffSec % 60;
    return `${mins}m ${secs}s`;
  }

  /**
   * Formats an ISO string to local date and time: YYYY-MM-DD HH:MM:SS.
   * @param {string} isoStr 
   * @returns {string}
   */
  function formatLocalDateTime(isoStr) {
    if (!isoStr) return '-';
    try {
      let s = String(isoStr).trim();
      if (!s) return '-';
      if (/^\d{4}-\d{2}-\d{2}T\d{2}$/.test(s)) {
        s += ':00';
      }
      if (!s.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(s)) {
        s += 'Z';
      }
      const d = new Date(s);
      if (isNaN(d.getTime())) return String(isoStr).replace('T', ' ').substring(0, 19);
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      const hrs = String(d.getHours()).padStart(2, '0');
      const mins = String(d.getMinutes()).padStart(2, '0');
      const secs = String(d.getSeconds()).padStart(2, '0');
      return `${year}-${month}-${day} ${hrs}:${mins}:${secs}`;
    } catch (e) {
      return String(isoStr).replace('T', ' ').substring(0, 19);
    }
  }

  /**
   * Formats an ISO string to local time: HH:MM.
   * @param {string} isoStr 
   * @returns {string}
   */
  function formatLocalTime(isoStr) {
    if (!isoStr) return '-';
    try {
      let s = String(isoStr).trim();
      if (!s) return '-';
      if (/^\d{4}-\d{2}-\d{2}T\d{2}$/.test(s)) {
        s += ':00';
      }
      if (!s.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(s)) {
        s += 'Z';
      }
      const d = new Date(s);
      if (isNaN(d.getTime())) return String(isoStr);
      const hrs = String(d.getHours()).padStart(2, '0');
      const mins = String(d.getMinutes()).padStart(2, '0');
      return `${hrs}:${mins}`;
    } catch (e) {
      return String(isoStr);
    }
  }

  /**
   * Formats duration between start and end timestamps into compact representation.
   * @param {string} startIso 
   * @param {string} endIso 
   * @returns {string}
   */
  function formatDuration(startIso, endIso) {
    if (!startIso || !endIso) return '-';
    try {
      let s1 = String(startIso).trim();
      let s2 = String(endIso).trim();
      if (!s1.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(s1)) s1 += 'Z';
      if (!s2.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(s2)) s2 += 'Z';
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
      return '-';
    }
  }

  /**
   * Escapes HTML special characters to prevent XSS injection.
   * @param {string} str 
   * @returns {string}
   */
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  const Formatters = {
    PROVIDER_COLORS,
    PROVIDER_NAMES,
    formatTokens,
    formatCurrency,
    formatCountdown,
    formatLocalDateTime,
    formatLocalTime,
    formatDuration,
    escapeHtml
  };

  // Attach to window namespace
  if (typeof window !== 'undefined') {
    window.AIUMCore = window.AIUMCore || {};
    window.AIUMCore.Formatters = Formatters;
  }

  // Node / CommonJS export support for automated verification
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Formatters;
  }
})();
