'use strict';

// Rendu partagé de la phase LEAP Locate : style des points par revenu associé,
// cartes de la liste « Sites localisés », popup d'asset et légende. Utilisé par
// la page Locate et par le mode « Exposition asset » de la Vue d'ensemble.
// Dépend des utilitaires globaux de main.js (escHtml, fmtNum, fmtEuro).
window.LocateView = (function () {
  // Échelle séquentielle (clair → foncé) utilisée pour le revenu associé.
  const REVENUE_COLORS = {
    Low:      '#dac1ba',
    Moderate: '#feb87c',
    High:     '#af5d43',
    VeryHigh: '#91452d',
  };
  const REVENUE_LABELS = {
    Low: 'Faible', Moderate: 'Modéré', High: 'Élevé', VeryHigh: 'Très élevé',
  };

  function revenueBand(ratio) {
    if (ratio >= 0.66) return 'VeryHigh';
    if (ratio >= 0.33) return 'High';
    if (ratio > 0)     return 'Moderate';
    return 'Low';
  }

  function euro(v) { return fmtEuro(Math.round(Number(v) || 0)); }

  // Sur une source GeoJSON, MapLibre sérialise les propriétés non primitives.
  function parseList(value) {
    if (typeof value === 'string') {
      try { return JSON.parse(value); } catch (_) { return []; }
    }
    return value || [];
  }

  // Marqueurs colorés et dimensionnés par revenu associé (relatif au max courant).
  function styleFeatures(features) {
    const maxRev = features.reduce((m, f) => Math.max(m, f.properties.revenue_total || 0), 0) || 1;
    return features.map(f => {
      const ratio = (f.properties.revenue_total || 0) / maxRev;
      return {
        type: 'Feature',
        geometry: f.geometry,
        properties: Object.assign({}, f.properties, {
          color: REVENUE_COLORS[revenueBand(ratio)],
          radius: 6 + 18 * ratio,
        }),
      };
    });
  }

  function prodLine(p) {
    const qty = `${fmtNum(p.quantity)} ${escHtml(p.unit)}`;
    return `<span class="ll-prod"><span class="ll-prod__name">${escHtml(p.commodity)}</span>`
      + `<span class="ll-prod__qty">${qty}</span></span>`;
  }

  // Cartes de la liste ; data-lng / data-lat servent au zoom au clic.
  function listHtml(features) {
    return features.map(f => {
      const p = f.properties;
      const [lng, lat] = f.geometry.coordinates;
      const badge = p.asset_type ? `<span class="ll-item__badge">${escHtml(p.asset_type)}</span>` : '';
      const own = p.ownership
        ? `<div class="ll-item__meta">Détention : <strong>${escHtml(p.ownership)}</strong></div>` : '';
      const prods = parseList(p.productions);
      const prodHtml = prods.length
        ? `<div class="ll-item__prods">${prods.map(prodLine).join('')}</div>` : '';
      return `
      <div class="ll-item ll-item--clickable" data-lng="${lng}" data-lat="${lat}">
        <div class="ll-item__top">
          <span class="ll-item__name">${escHtml(p.name)}</span>
          ${badge}
        </div>
        ${own}
        ${prodHtml}
        <div class="ll-item__revenue">Revenu associé&nbsp;: <strong>${euro(p.revenue_total)}</strong></div>
      </div>`;
    }).join('');
  }

  function popupHtml(p) {
    const prods = parseList(p.productions);
    const meta = [p.country, p.region].filter(Boolean).map(escHtml).join(' · ');
    const type = p.asset_type ? `<div class="ll-popup__row">Type : ${escHtml(p.asset_type)}</div>` : '';
    const own  = p.ownership ? `<div class="ll-popup__row">Détention : ${escHtml(p.ownership)}</div>` : '';
    const prodHtml = prods.length
      ? `<div class="ll-popup__prods">${prods.map(prodLine).join('')}</div>`
      : '<div class="ll-popup__row">Aucune production</div>';
    return `<div class="ll-popup"><strong>${escHtml(p.name)}</strong>` +
      `<div class="ll-popup__meta">${meta}</div>${type}${own}${prodHtml}` +
      `<div class="ll-popup__revenue">Revenu associé : ${euro(p.revenue_total)}</div></div>`;
  }

  function legendHtml() {
    const items = Object.keys(REVENUE_COLORS).map(k =>
      `<li><span class="map-legend__dot" style="background:${REVENUE_COLORS[k]}"></span>${REVENUE_LABELS[k]}</li>`
    ).join('');
    return `<p class="map-legend__title">Revenu associé</p><ul class="map-legend__list">${items}</ul>`;
  }

  return { REVENUE_COLORS, revenueBand, styleFeatures, prodLine, listHtml, popupHtml, legendHtml };
})();
