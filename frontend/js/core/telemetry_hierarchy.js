/**
 * AI Usage Monitor - Shared Core Telemetry Hierarchy
 * Canonical hierarchy extraction and punctuation-agnostic series resolution.
 * Shared across Full Web UI, Floating Mini Widget, and Windows Tray.
 */

(function () {
  'use strict';

  const HONEST_ZERO_BASELINE = [0, 0, 0, 0, 0, 0, 0, 0];

  /**
   * Extracts real server points for a child branch (model, account, or tier) from hierarchical trends cache.
   * Performs punctuation-agnostic ID matching (handling colons, underscores, dashes, spaces).
   * Always returns real server points or an honest flat zero baseline (never synthetic wave multipliers).
   * 
   * @param {Object} hierTrends Cached trends map or trend response object
   * @param {string} providerKey Provider identifier (claude, gemini, ollama, etc.)
   * @param {string} childId Child branch identifier or model name
   * @param {number} fallbackTotalTokens Fallback token total (used only if explicit points absent)
   * @returns {Array<number>} Real timeseries points or zero baseline
   */
  function extractChildRealPoints(hierTrends, providerKey, childId, fallbackTotalTokens = 0) {
    if (!hierTrends || !childId) {
      return [...HONEST_ZERO_BASELINE];
    }

    let targetPayload = null;

    // Check if hierTrends is a direct trend response object with .series
    if (Array.isArray(hierTrends.series)) {
      targetPayload = hierTrends;
    } else if (typeof hierTrends === 'object') {
      const pKey = String(providerKey || '').toLowerCase();

      // Look for exact or prefix matching cache key
      for (const [k, val] of Object.entries(hierTrends)) {
        if (!val || !Array.isArray(val.series)) continue;
        const normK = k.toLowerCase();
        if (normK.startsWith(pKey + '_') || normK === pKey || (val.provider && String(val.provider).toLowerCase() === pKey)) {
          targetPayload = val;
          break;
        }
      }

      // Fallback: search values for matching provider
      if (!targetPayload) {
        targetPayload = Object.values(hierTrends).find(c => c && String(c.provider || '').toLowerCase() === pKey && Array.isArray(c.series));
      }
    }

    if (targetPayload && Array.isArray(targetPayload.series) && targetPayload.series.length > 0) {
      const normChild = String(childId || '').toLowerCase().replace(/[^a-z0-9]/g, '');
      if (!normChild) return [...HONEST_ZERO_BASELINE];

      const match = targetPayload.series.find(s => {
        const sid = String(s.id || s.key || '').toLowerCase().replace(/[^a-z0-9]/g, '');
        const sName = String(s.name || s.label || '').toLowerCase().replace(/[^a-z0-9]/g, '');
        if (sid) {
          if (sid === normChild || sid.includes(normChild) || (sid.length >= 3 && normChild.includes(sid))) {
            return true;
          }
        }
        if (sName) {
          if (sName === normChild || sName.includes(normChild) || (sName.length >= 3 && normChild.includes(sName))) {
            return true;
          }
        }
        return false;
      });

      if (match && Array.isArray(match.points) && match.points.length > 0) {
        return match.points;
      }
    }

    return [...HONEST_ZERO_BASELINE];
  }

  const TelemetryHierarchy = {
    HONEST_ZERO_BASELINE,
    extractChildRealPoints
  };

  // Attach to window namespace
  if (typeof window !== 'undefined') {
    window.AIUMCore = window.AIUMCore || {};
    window.AIUMCore.TelemetryHierarchy = TelemetryHierarchy;
  }

  // Node / CommonJS export support for automated verification
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = TelemetryHierarchy;
  }
})();
