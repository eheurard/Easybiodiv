'use strict';

// Rendu partagé de la dette écologique : KPI (fragment _de_kpis.html), légende
// des commodités, infobulle des camemberts et liste d'assets au format Locate.
// Utilisé par la page Dette écologique et par le mode « Dette écologique » de
// la Vue d'ensemble. Les camemberts sont dessinés par PieMarkers.
// Dépend de escHtml (main.js).
window.DetteView = (function () {
  function fmtLbiodiv(val) {
    if (val >= 1e9) return '$' + (val / 1e9).toFixed(2) + ' G';
    if (val >= 1e6) return '$' + (val / 1e6).toFixed(2) + ' M';
    if (val >= 1e3) return '$' + (val / 1e3).toFixed(2) + ' k';
    return '$' + val.toFixed(2);
  }

  function fmtPct(v) { return (v * 100).toFixed(1) + '%'; }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function renderKpis(data, mode) {
    setText('de-total-lbiodiv', data.total_lbiodiv ? fmtLbiodiv(data.total_lbiodiv) : '—');
    setText('de-year', data.year != null ? data.year : '—');
    setText('de-top-commodity', data.commodities.length ? data.commodities[0].name : '—');
    renderPointCount(data, mode);
  }

  // Nombre de points affichés : assets ou régions selon le regroupement.
  function renderPointCount(data, mode) {
    const points = mode === 'asset' ? data.assets : data.regions;
    setText('de-point-count', points.length || '—');
    setText('de-point-count-label', mode === 'asset' ? 'Assets' : 'Régions');
  }

  function legendItemsHtml(commodities, colors) {
    return commodities.slice(0, 8).map(c => {
      const color = colors[c.name] || '#ccc';
      return (
        '<li class="de-legend__item">' +
        '<span class="de-legend__swatch" style="background:' + color + '"></span>' +
        '<span class="de-legend__name">' + escHtml(c.name) + '</span>' +
        '<span class="de-legend__pct">' + fmtPct(c.pct) + '</span>' +
        '</li>'
      );
    }).join('');
  }

  // Gestionnaires de survol pour PieMarkers.render : infobulle positionnée dans
  // le repère de mapEl (le canevas remplit la scène carte).
  function tooltipHandlers(tipEl, mapEl, colors) {
    function move(e) {
      if (!tipEl || !mapEl) return;
      const rect = mapEl.getBoundingClientRect();
      tipEl.style.left = (e.clientX - rect.left + 14) + 'px';
      tipEl.style.top  = (e.clientY - rect.top  + 14) + 'px';
    }
    return {
      onEnter(point, e) {
        if (!tipEl) return;
        const top3 = point.commodities.slice(0, 3).map(c =>
          `<div class="asset-popup__prod-row">
            <span class="asset-popup__prod-dot" style="background:${colors[c.name] || '#ccc'}"></span>
            <span class="asset-popup__prod-name">${escHtml(c.name)}</span>
            <span class="asset-popup__prod-qty">${fmtPct(c.pct)}</span>
          </div>`).join('');
        tipEl.innerHTML = `
          <div class="asset-popup">
            <div class="asset-popup__header">
              <div class="asset-popup__name">${escHtml(point.name)}</div>
            </div>
            <div class="asset-popup__body">
              <div class="asset-popup__section-title">Principales commodités</div>
              ${top3}
              <div class="asset-popup__divider"></div>
              <div class="asset-popup__metrics">
                <div class="asset-popup__metric asset-popup__metric--risk">
                  <div class="asset-popup__metric-value">${fmtLbiodiv(point.total_lbiodiv)}</div>
                  <div class="asset-popup__metric-label">Lbiodiv</div>
                </div>
              </div>
            </div>
          </div>`;
        tipEl.hidden = false;
        move(e);
      },
      onMove: move,
      onLeave() { if (tipEl) tipEl.hidden = true; },
    };
  }

  // Liste d'assets au format Locate : part du total, répartition par commodité
  // (pastilles aux couleurs des camemberts), Lbiodiv.
  function assetListHtml(assets, colors) {
    return assets.map(a => {
      const comms = a.commodities.map(c =>
        `<span class="ll-prod"><span class="ll-prod__name">` +
        `<span class="de-tooltip__swatch" style="background:${colors[c.name] || '#ccc'}"></span>` +
        `${escHtml(c.name)}</span><span class="ll-prod__qty">${fmtPct(c.pct)}</span></span>`
      ).join('');
      return `
      <div class="ll-item ll-item--clickable" data-lng="${a.longitude}" data-lat="${a.latitude}">
        <div class="ll-item__top">
          <span class="ll-item__name">${escHtml(a.name)}</span>
          <span class="ll-item__badge">${fmtPct(a.pct)} du total</span>
        </div>
        <div class="ll-item__prods">${comms}</div>
        <div class="ll-item__revenue">Lbiodiv&nbsp;: <strong>${fmtLbiodiv(a.total_lbiodiv)}</strong></div>
      </div>`;
    }).join('');
  }

  return { fmtLbiodiv, renderKpis, renderPointCount, legendItemsHtml, tooltipHandlers, assetListHtml };
})();
