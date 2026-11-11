/**
 * AI Usage Monitor - Shared Core Chart Renderer
 * Canonical SVG sparkline and chart generation utilities with zero-dependency native SVG.
 * Ensures crisp un-stretched scaling, vector-effect non-scaling strokes, and honest zero baselines.
 */

(function () {
  'use strict';

  /**
   * Generates a crisp, responsive SVG sparkline string.
   * Uses vector-effect="non-scaling-stroke", linearGradient fill, and honest zero baseline (never fake wave multipliers).
   * 
   * @param {Array<number>|number} points Data points array or single value
   * @param {string} color Stroke color
   * @param {Object} options Optional display parameters
   * @returns {string} SVG markup string
   */
  function generateSparklineSvg(points, color = '#06b6d4', options = {}) {
    const w = options.width || 110;
    const h = options.height || 26;
    const pad = options.pad !== undefined ? options.pad : 3;
    const maxWidth = options.maxWidth || 140;

    let rawPoints = [];
    if (Array.isArray(points)) {
      rawPoints = points.map(p => (typeof p === 'number' && !isNaN(p) ? p : 0));
    } else if (typeof points === 'number' && !isNaN(points)) {
      rawPoints = [0, 0, 0, 0, 0, 0, 0, points];
    } else {
      rawPoints = [0, 0, 0, 0, 0, 0, 0, 0];
    }

    if (rawPoints.length < 2) {
      rawPoints = rawPoints.length === 1 ? [rawPoints[0], rawPoints[0]] : [0, 0];
    }

    const min = Math.min(...rawPoints);
    const max = Math.max(...rawPoints);
    const isAllZero = rawPoints.every(p => p === 0);

    // Honest flat baseline for idle state (zero activity)
    if (isAllZero || (min === 0 && max === 0)) {
      const yZero = (h - pad).toFixed(1);
      return `
        <svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" style="max-width: ${maxWidth}px; background: rgba(0,0,0,0.25); border-radius: 4px; border: 1px solid rgba(255,255,255,0.06); display: block;" title="No activity in window (0 tokens)">
          <line x1="${pad}" y1="${yZero}" x2="${w - pad}" y2="${yZero}" stroke="rgba(255,255,255,0.18)" stroke-width="1.5" vector-effect="non-scaling-stroke" stroke-dasharray="2,2"/>
          <text x="${w / 2}" y="${h / 2 + 3}" fill="#64748b" font-size="8" text-anchor="middle" font-family="monospace">0 t (idle)</text>
        </svg>
      `;
    }

    const range = Math.max(1, max - min);
    const n = rawPoints.length;
    const step = (w - pad * 2) / (n - 1);

    const coordsArr = rawPoints.map((p, idx) => {
      const x = pad + (idx * step);
      const y = h - pad - ((p - min) / range) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const polyPoints = coordsArr.join(' ');

    const firstX = pad.toFixed(1);
    const lastX = (pad + (n - 1) * step).toFixed(1);
    const lastVal = rawPoints[n - 1];
    const lastY = (h - pad - ((lastVal - min) / range) * (h - pad * 2)).toFixed(1);
    const bottomY = (h - pad).toFixed(1);

    const gradId = `spark-grad-${Math.random().toString(36).substring(2, 9)}`;
    const showFill = options.showFill !== false;
    const defs = showFill
      ? `<defs><linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${color}" stop-opacity="0.35"/><stop offset="100%" stop-color="${color}" stop-opacity="0.02"/></linearGradient></defs>`
      : '';
    const fillPolygon = showFill
      ? `<polygon fill="url(#${gradId})" points="${firstX},${bottomY} ${polyPoints} ${lastX},${bottomY}"/>`
      : '';

    return `
      <svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" style="max-width: ${maxWidth}px; background: rgba(0,0,0,0.25); border-radius: 4px; border: 1px solid rgba(255,255,255,0.06); display: block;">
        ${defs}
        ${fillPolygon}
        <polyline fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke" points="${polyPoints}" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="${lastX}" cy="${lastY}" r="2.5" fill="${color}" stroke="#ffffff" stroke-width="1"/>
      </svg>
    `;
  }

  /**
   * Generates a multi-series sparkline SVG string.
   * 
   * @param {Array<Object>} seriesList List of series objects { label, color, points: [...] }
   * @param {number} width 
   * @param {number} height 
   * @param {Object} options 
   * @returns {string} SVG markup string
   */
  function generateMultiSparklineSvg(seriesList, width = 110, height = 26, options = {}) {
    if (!seriesList || seriesList.length === 0) return '';
    const pad = options.pad !== undefined ? options.pad : 3;

    let allPoints = [];
    seriesList.forEach(s => {
      if (Array.isArray(s.points)) {
        allPoints = allPoints.concat(s.points);
      }
    });

    const isAllZero = allPoints.length === 0 || allPoints.every(p => Number(p) === 0);
    if (isAllZero) {
      const yZero = (height - pad).toFixed(1);
      return `
        <svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" style="max-width: 140px; background: rgba(0,0,0,0.25); border-radius: 4px; border: 1px solid rgba(255,255,255,0.06); display: block;" title="No activity in window (0 tokens)">
          <line x1="${pad}" y1="${yZero}" x2="${width - pad}" y2="${yZero}" stroke="rgba(255,255,255,0.18)" stroke-width="1.5" vector-effect="non-scaling-stroke" stroke-dasharray="2,2"/>
          <text x="${width / 2}" y="${height / 2 + 3}" fill="#64748b" font-size="8" text-anchor="middle" font-family="monospace">0 t (idle)</text>
        </svg>
      `;
    }

    const maxVal = Math.max(...allPoints, 1);
    const minVal = Math.min(...allPoints, 0);
    const range = (maxVal - minVal) || 1;
    const n = Math.max(...seriesList.map(s => (s.points || []).length));
    const step = n > 1 ? (width - pad * 2) / (n - 1) : (width - pad * 2);

    const linesHtml = seriesList.map(s => {
      const pts = (s.points || []).map((val, idx) => {
        const x = pad + (idx * step);
        const y = height - pad - ((val - minVal) / range) * (height - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(' ');

      const lastVal = s.points && s.points.length > 0 ? s.points[s.points.length - 1] : 0;
      const lastX = (pad + ((s.points || []).length - 1) * step).toFixed(1);
      const lastY = (height - pad - ((lastVal - minVal) / range) * (height - pad * 2)).toFixed(1);

      return `
        <polyline fill="none" stroke="${s.color || '#06b6d4'}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round" points="${pts}" />
        <circle cx="${lastX}" cy="${lastY}" r="2.5" fill="${s.color || '#06b6d4'}" stroke="#ffffff" stroke-width="1" />
      `;
    }).join('');

    return `
      <svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" style="max-width: 140px; background: rgba(0,0,0,0.25); border-radius: 4px; border: 1px solid rgba(255,255,255,0.06); display: block;">
        ${linesHtml}
      </svg>
    `;
  }

  const ChartRenderer = {
    generateSparklineSvg,
    generateMultiSparklineSvg
  };

  // Attach to window namespace
  if (typeof window !== 'undefined') {
    window.AIUMCore = window.AIUMCore || {};
    window.AIUMCore.ChartRenderer = ChartRenderer;
  }

  // Node / CommonJS export support for automated verification
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChartRenderer;
  }
})();
