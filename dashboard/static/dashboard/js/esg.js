'use strict';

const ESG_COMPANY_KEY = 'selected-company-id';

const ESG_STATE = { data: null, pollutionKey: null, pollutionView: 'assets' };

let esgScopeView = false;
const SCOPE_COLORS = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948'];

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('esg-companies');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('esg-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  esgInitThemeTabs();
  esgInitSubTabs();
  esgInitPollutionView();

  const scopeToggle = document.getElementById('esg-scope-toggle');
  if (scopeToggle) {
    scopeToggle.addEventListener('click', () => {
      esgScopeView = !esgScopeView;
      scopeToggle.setAttribute('aria-pressed', String(esgScopeView));
      if (ESG_STATE.data) esgRenderChart(ESG_STATE.data.carbon);
    });
  }

  const savedId = parseInt(localStorage.getItem(ESG_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    fetch(ESG_API_URL.replace('/0/', '/' + savedId + '/'))
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => { esgRender(data); esgInitCombobox(companies, data); })
      .catch(err => { console.error('esg fetch failed:', err); esgInitCombobox(companies, initialData); if (initialData) esgRender(initialData); });
  } else {
    if (initialData) esgRender(initialData);
    esgInitCombobox(companies, initialData);
  }
});


function esgInitThemeTabs() {
  const tabs = document.querySelectorAll('.esg-theme-tab');
  const panels = document.querySelectorAll('.esg-theme-panel');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const theme = tab.dataset.theme;
      tabs.forEach(t => {
        const active = t === tab;
        t.classList.toggle('esg-theme-tab--active', active);
        t.setAttribute('aria-selected', String(active));
      });
      panels.forEach(p => {
        const active = p.dataset.themePanel === theme;
        p.classList.toggle('esg-theme-panel--active', active);
        if (active) { p.removeAttribute('hidden'); } else { p.setAttribute('hidden', ''); }
      });
    });
  });
}


function esgInitSubTabs() {
  const subTabs = document.querySelectorAll('.esg-sub-tab');
  const subPanels = document.querySelectorAll('.esg-sub-panel');
  subTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const sub = tab.dataset.sub;
      subTabs.forEach(t => {
        const active = t === tab;
        t.classList.toggle('esg-sub-tab--active', active);
        t.setAttribute('aria-selected', String(active));
      });
      subPanels.forEach(p => {
        const active = p.dataset.subPanel === sub;
        p.classList.toggle('esg-sub-panel--active', active);
        if (active) { p.removeAttribute('hidden'); } else { p.setAttribute('hidden', ''); }
      });
    });
  });
}


function esgRender(data) {
  ESG_STATE.data = data;
  esgRenderCarbon(data.carbon);
  esgRenderLandUse(data.land_use);
  esgRenderPollution(data.pollution);
  esgRenderResourceUse(data.resource_use);
  esgRenderInvasive(data.invasive_species);
  esgRenderFeatured(data.policies.featured);
  esgRenderFramework(data.policies.framework);
  esgRenderMarket(data.market);
}


function esgRenderCarbon(carbon) {
  const unitEl = document.querySelector('[data-esg="carbon-unit"]');
  if (unitEl) unitEl.textContent = carbon.unit || 'tCO2e';

  const latestEl = document.querySelector('[data-esg="carbon-latest"]');
  if (latestEl) {
    latestEl.textContent = carbon.latest_total != null
      ? esgFmtNum(carbon.latest_total) + ' ' + (carbon.unit || '') : '—';
  }

  const redEl = document.querySelector('[data-esg="carbon-reduction"]');
  if (redEl) {
    if (carbon.reduction_pct == null) {
      redEl.textContent = '—';
      redEl.className = 'esg-chart__kpi-value';
    } else {
      const sign = carbon.reduction_pct > 0 ? '+' : '';
      redEl.textContent = sign + carbon.reduction_pct + '%';
      redEl.className = 'esg-chart__kpi-value ' +
        (carbon.reduction_pct <= 0 ? 'esg-chart__kpi-value--good' : 'esg-chart__kpi-value--bad');
    }
  }

  esgRenderChart(carbon);
}


const M2_PER_HA = 10000;


function esgRenderLandUse(land) {
  const setText = (key, text) => {
    const el = document.querySelector('[data-esg="' + key + '"]');
    if (el) el.textContent = text;
  };
  setText('land-impact', land.total_impact != null
    ? esgFmtLand(land.total_impact) + ' m²a' : '—');
  setText('land-surface', land.total_surface != null
    ? esgFmtLand(land.total_surface / M2_PER_HA) + ' ha' : '—');
  setText('land-intensity', land.intensity != null
    ? land.intensity.toFixed(2) : '—');

  const groupEl = document.querySelector('[data-esg="land-group"]');
  if (groupEl) {
    if (land.declared_group) {
      setText('land-group-value', esgFmtLand(land.declared_group.value / M2_PER_HA) +
        ' ha (' + land.declared_group.year + ')');
      groupEl.removeAttribute('hidden');
    } else {
      groupEl.setAttribute('hidden', '');
    }
  }

  const tbody = document.getElementById('esg-land-rows');
  const empty = document.getElementById('esg-land-empty');
  if (!tbody) return;
  if (empty) empty.hidden = land.assets.length > 0;
  const maxImpact = Math.max(0, ...land.assets.map(a => a.impact || 0));
  const maxSurface = Math.max(0, ...land.assets.map(a => a.surface || 0));
  tbody.innerHTML = land.assets.map(a =>
    '<tr>' +
    '<th scope="row">' + escHtml(a.name) + '</th>' +
    '<td>' + escHtml(a.country || '—') + '</td>' +
    esgLandCell(a.impact, a.impact_year, maxImpact, 1, 'impact') +
    esgLandCell(a.surface, a.surface_year, maxSurface, M2_PER_HA, 'surface') +
    '</tr>'
  ).join('');
}


function esgFmtLand(val) {
  return Math.abs(val) < 10 ? val.toFixed(1) : esgFmtNum(val);
}


function esgLandCell(value, year, max, divisor, variant) {
  if (value == null) return '<td class="esg-table__num">—</td>';
  const pct = max > 0 ? (value / max * 100).toFixed(1) : 0;
  const muted = variant === 'surface' ? ' esg-table__bar--muted' : '';
  return '<td class="esg-table__num">' +
    '<span class="esg-table__value">' + esgFmtLand(value / divisor) +
    ' <span class="esg-table__year">' + year + '</span></span>' +
    '<span class="esg-table__bar' + muted + '" style="width:' + pct + '%"></span>' +
    '</td>';
}


// ── Pollution, Resource use, Invasive species ──────────────────────────────

function esgSetText(key, text) {
  const el = document.querySelector('[data-esg="' + key + '"]');
  if (el) el.textContent = text;
}


// Quantité compacte, en HTML : k / M / G au-delà de 10 000, notation ×10ⁿ sous
// 0,01 (les pressions de pollution s'étalent de 1e-6 à 1e9).
function esgFmtQty(val) {
  if (val == null) return '—';
  const abs = Math.abs(val);
  const loc = (v, digits) => v.toLocaleString(APP_LOCALE, { maximumFractionDigits: digits });
  if (abs === 0) return '0';
  if (abs >= 1e9) return loc(val / 1e9, 1) + ' G';
  if (abs >= 1e6) return loc(val / 1e6, 1) + ' M';
  if (abs >= 1e4) return loc(val / 1e3, 1) + ' k';
  if (abs >= 1) return loc(val, abs >= 100 ? 0 : 1);
  if (abs >= 0.01) return loc(val, 3);
  const exp = Math.floor(Math.log10(abs));
  return loc(val / Math.pow(10, exp), 2) + '×10<sup>' + exp + '</sup>';
}


function esgFmtShare(value, total) {
  if (!total) return '—';
  return (value / total * 100).toLocaleString(APP_LOCALE, {
    minimumFractionDigits: 1, maximumFractionDigits: 1,
  }) + ' %';
}


function esgHeadCell(label, unit, numeric) {
  return '<th scope="col"' + (numeric ? ' class="esg-table__num"' : '') + '>' + escHtml(label) +
    (unit ? ' <span class="esg-table__unit">(' + escHtml(unit) + ')</span>' : '') + '</th>';
}


// Cellule numérique avec barre proportionnelle au maximum de la colonne.
function esgQtyCell(value, max, year) {
  if (value == null) return '<td class="esg-table__num">—</td>';
  const pct = max > 0 ? (value / max * 100).toFixed(1) : 0;
  return '<td class="esg-table__num">' +
    '<span class="esg-table__value">' + esgFmtQty(value) +
    (year ? ' <span class="esg-table__year">' + year + '</span>' : '') + '</span>' +
    '<span class="esg-table__bar" style="width:' + pct + '%"></span>' +
    '</td>';
}


function esgEmptyRow(colspan, message) {
  return '<tr><td colspan="' + colspan + '" class="esg-table__none">' + escHtml(message) + '</td></tr>';
}


// Pictogrammes des milieux récepteurs (trait 1,3 px, comme les sous-onglets).
const ESG_MEDIA_ICONS = {
  air: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">' +
    '<path d="M1.5 5h7.5a2 2 0 10-2-2M1.5 8.5h10a1.8 1.8 0 11-1.8 1.8M1.5 12h5" ' +
    'stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  water: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">' +
    '<path d="M7 1.5L4 6.5a3.5 3.5 0 107 0L7 1.5z" stroke="currentColor" stroke-width="1.3" ' +
    'stroke-linejoin="round"/></svg>',
  soil: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">' +
    '<path d="M1.5 5.5h11M1.5 9h11M1.5 12.5h11" stroke="currentColor" stroke-width="1.3" ' +
    'stroke-linecap="round"/><path d="M7 5.5V2M5.5 3.5L7 2l1.5 1.5" stroke="currentColor" ' +
    'stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};


function esgPollutionIndicators(pollution) {
  return pollution.media.reduce((all, medium) => all.concat(medium.indicators), []);
}


function esgRenderPollution(pollution) {
  const mediaEl = document.getElementById('esg-pollution-media');
  if (!mediaEl || !pollution) return;

  const withData = esgPollutionIndicators(pollution).filter(i => i.total != null);
  const empty = document.getElementById('esg-pollution-empty');
  const breakdown = document.getElementById('esg-pollution-breakdown');
  if (empty) empty.hidden = withData.length > 0;
  if (breakdown) breakdown.hidden = withData.length === 0;

  // L'indicateur choisi survit au changement d'entreprise s'il y a des données.
  if (!withData.some(i => i.key === ESG_STATE.pollutionKey)) {
    ESG_STATE.pollutionKey = withData.length ? withData[0].key : null;
  }

  mediaEl.innerHTML = pollution.media.map(medium =>
    '<div class="esg-media__group">' +
    '<h4 class="esg-media__title label-caps">' + (ESG_MEDIA_ICONS[medium.key] || '') +
    escHtml(medium.name) + '</h4>' +
    medium.indicators.map(i =>
      '<button type="button" class="esg-indicator" data-key="' + escHtml(i.key) + '"' +
      ' aria-pressed="' + (i.key === ESG_STATE.pollutionKey) + '"' +
      (i.total == null ? ' disabled' : '') + '>' +
      '<span class="esg-indicator__name">' + escHtml(i.name) + '</span>' +
      '<span class="esg-indicator__value">' + esgFmtQty(i.total) +
      (i.total != null ? '<span class="esg-indicator__unit">' + escHtml(i.unit) + '</span>' : '') +
      '</span></button>'
    ).join('') +
    '</div>'
  ).join('');

  mediaEl.querySelectorAll('.esg-indicator').forEach(btn => {
    btn.addEventListener('click', () => {
      ESG_STATE.pollutionKey = btn.dataset.key;
      mediaEl.querySelectorAll('.esg-indicator').forEach(b => {
        b.setAttribute('aria-pressed', String(b === btn));
      });
      esgRenderPollutionBreakdown();
    });
  });
  esgRenderPollutionBreakdown();
}


function esgRenderPollutionBreakdown() {
  const pollution = ESG_STATE.data && ESG_STATE.data.pollution;
  const head = document.getElementById('esg-pollution-head');
  const rows = document.getElementById('esg-pollution-rows');
  const title = document.getElementById('esg-pollution-selected');
  if (!pollution || !head || !rows) return;

  const indicator = esgPollutionIndicators(pollution).find(i => i.key === ESG_STATE.pollutionKey);
  if (!indicator) {
    head.innerHTML = '';
    rows.innerHTML = '';
    return;
  }
  if (title) title.textContent = indicator.name;

  const byAsset = ESG_STATE.pollutionView === 'assets';
  const items = byAsset ? indicator.assets : indicator.commodities;
  const max = Math.max(0, ...items.map(r => r.value));
  head.innerHTML = '<tr>' +
    esgHeadCell(byAsset ? gettext('Actif') : gettext('Commodité')) +
    (byAsset ? esgHeadCell(gettext('Pays')) : '') +
    esgHeadCell(gettext('Pression'), indicator.unit, true) +
    esgHeadCell(gettext('Part'), '', true) +
    '</tr>';
  rows.innerHTML = items.map(r =>
    '<tr>' +
    '<th scope="row">' + escHtml(r.name) + '</th>' +
    (byAsset ? '<td>' + escHtml(r.country || '—') + '</td>' : '') +
    esgQtyCell(r.value, max, byAsset ? r.year : null) +
    '<td class="esg-table__num esg-table__share">' + esgFmtShare(r.value, indicator.total) + '</td>' +
    '</tr>'
  ).join('');
}


function esgInitPollutionView() {
  const buttons = document.querySelectorAll('[data-pollution-view]');
  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      ESG_STATE.pollutionView = btn.dataset.pollutionView;
      buttons.forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
      esgRenderPollutionBreakdown();
    });
  });
}


function esgRenderResourceUse(resource) {
  const kpis = document.getElementById('esg-resource-kpis');
  if (!kpis || !resource) return;

  const tile = (label, total, unit, sub, modelled) =>
    '<div class="esg-kpi' + (modelled ? ' esg-kpi--modelled' : '') + '">' +
    '<span class="esg-kpi__label label-caps">' + escHtml(label) + '</span>' +
    '<span class="esg-kpi__value">' + esgFmtQty(total) +
    (total != null ? '<span class="esg-kpi__unit">' + escHtml(unit) + '</span>' : '') + '</span>' +
    '<span class="esg-kpi__sub">' + sub + '</span>' +
    '</div>';
  kpis.innerHTML =
    resource.inventory.map(i => tile(
      i.name, i.total, i.unit,
      i.declared_group
        ? escHtml(gettext('Déclaré groupe :')) + ' ' + esgFmtQty(i.declared_group.value) + ' ' +
          escHtml(i.unit) + ' (' + i.declared_group.year + ')'
        : escHtml(i.total != null
          ? gettext('Mesuré, somme des actifs') : gettext('Aucune donnée mesurée')),
      false,
    )).join('') +
    resource.scarcity.map(s => tile(
      s.name, s.total, s.unit, escHtml(gettext('Modélisé, ReCiPe 2016')), true,
    )).join('');

  const assets = resource.assets;
  const empty = document.getElementById('esg-resource-empty');
  if (empty) empty.hidden = assets.length > 0;

  const table = (headId, rowsId, columns, valueOf, yearOf, noneMessage) => {
    const head = document.getElementById(headId);
    const rows = document.getElementById(rowsId);
    if (!head || !rows) return;
    if (!assets.length) {
      head.innerHTML = '';
      rows.innerHTML = '';
      return;
    }
    head.innerHTML = '<tr>' + esgHeadCell(gettext('Actif')) + esgHeadCell(gettext('Pays')) +
      columns.map(c => esgHeadCell(c.name, c.unit, true)).join('') + '</tr>';
    const maxes = columns.map(c => Math.max(0, ...assets.map(a => valueOf(a, c.key) || 0)));
    const measured = assets.some(a => columns.some(c => valueOf(a, c.key) != null));
    rows.innerHTML = measured
      ? assets.map(a =>
          '<tr>' +
          '<th scope="row">' + escHtml(a.name) + '</th>' +
          '<td>' + escHtml(a.country || '—') + '</td>' +
          columns.map((c, idx) => esgQtyCell(valueOf(a, c.key), maxes[idx], yearOf(a, c.key))).join('') +
          '</tr>'
        ).join('')
      : esgEmptyRow(columns.length + 2, noneMessage);
  };

  table(
    'esg-resource-inventory-head', 'esg-resource-inventory-rows', resource.inventory,
    (a, key) => (a[key] ? a[key].value : null),
    (a, key) => (a[key] ? a[key].year : null),
    gettext('Aucune mesure par actif : seules des valeurs consolidées sont déclarées.'),
  );
  table(
    'esg-resource-scarcity-head', 'esg-resource-scarcity-rows', resource.scarcity,
    // Zéro = aucun facteur de caractérisation pour les productions de l'actif.
    (a, key) => (a.scarcity && a.scarcity[key] ? a.scarcity[key] : null),
    (a) => a.scarcity_year,
    gettext('Aucun facteur de raréfaction pour les productions de ces actifs.'),
  );
}


function esgRenderInvasive(ias) {
  const tbody = document.getElementById('esg-ias-rows');
  if (!tbody || !ias) return;

  esgSetText('ias-screened', ias.counts.screened);
  esgSetText('ias-pathway', ias.counts.with_pathway);
  esgSetText('ias-high', ias.counts.high);
  esgSetText('ias-sensitive', ias.counts.sensitive);

  const empty = document.getElementById('esg-ias-empty');
  if (empty) empty.hidden = ias.assets.length > 0;

  const flag = (label, detail) =>
    '<span class="esg-flag">' + escHtml(label) + '</span>' +
    (detail ? '<br><span class="esg-flag__detail">' + escHtml(detail) + '</span>' : '');

  tbody.innerHTML = ias.assets.map(a => {
    let trade = '—';
    if (a.trade) {
      trade = a.trade_origins.length
        ? flag(gettext('Importations'), a.trade_origins.join(', '))
        : flag(gettext('Plateforme de transport'));
    }
    return '<tr>' +
      '<th scope="row">' + escHtml(a.name) + '</th>' +
      '<td>' + escHtml(a.country || '—') + '</td>' +
      '<td>' + trade + '</td>' +
      '<td>' + (a.activity ? flag(a.activity_label) : '—') + '</td>' +
      '<td>' + (a.sensitive ? flag(a.sensitive_label || gettext('Oui')) : '—') + '</td>' +
      '<td class="esg-table__num"><span class="esg-level esg-level--' + escHtml(a.level) + '">' +
      escHtml(a.level_label) + '</span></td>' +
      '</tr>';
  }).join('');
}


function esgRenderChart(carbon) {
  const canvas = document.getElementById('esg-chart-canvas');
  const empty = document.getElementById('esg-chart-empty');
  if (!canvas) return;

  canvas.querySelectorAll('svg').forEach(s => s.remove());
  const existingTip = document.getElementById('esg-chart-tooltip');
  if (existingTip) existingTip.setAttribute('hidden', '');

  const hist = carbon.historical || [];
  if (!hist.length) {
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;

  const proj = carbon.projection || [];
  const allYears = hist.map(h => h.year).concat(proj.map(p => p.year));
  const allTotals = hist.map(h => h.total).concat(proj.map(p => p.total));
  const minYear = Math.min(...allYears);
  const maxYear = Math.max(...allYears);
  const scopeSums = hist.map(h => Object.values(h.scopes || {}).reduce((a, b) => a + b, 0));
  const maxVal = Math.max(...allTotals, ...scopeSums, 1);

  const W = 1000, H = 320;
  const padL = 56, padR = 16, padT = 16, padB = 32;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('class', 'esg-chart__svg');

  const xOf = yr => padL + (maxYear === minYear ? 0 : (yr - minYear) / (maxYear - minYear) * plotW);
  const yOf = v => padT + plotH - (v / maxVal) * plotH;

  // Grid lines + Y axis labels
  for (let i = 0; i <= 4; i++) {
    const val = maxVal * i / 4;
    const y = yOf(val);
    const line = document.createElementNS(NS, 'line');
    line.setAttribute('x1', padL); line.setAttribute('x2', W - padR);
    line.setAttribute('y1', y); line.setAttribute('y2', y);
    line.setAttribute('class', 'esg-chart__grid');
    svg.appendChild(line);
    const label = document.createElementNS(NS, 'text');
    label.setAttribute('x', padL - 8); label.setAttribute('y', y + 4);
    label.setAttribute('text-anchor', 'end');
    label.setAttribute('class', 'esg-chart__axis-label');
    label.textContent = esgFmtNum(Math.round(val));
    svg.appendChild(label);
  }

  // X axis labels
  const xYears = hist.map(h => h.year);
  if (proj.length) xYears.push(proj[proj.length - 1].year);
  xYears.forEach(yr => {
    const label = document.createElementNS(NS, 'text');
    label.setAttribute('x', xOf(yr)); label.setAttribute('y', H - 10);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('class', 'esg-chart__axis-label');
    label.textContent = yr;
    svg.appendChild(label);
  });

  // Stacked bars (scope view) — drawn before the line so line appears on top
  let allScopes = [];
  let scopeColorMap = {};
  if (esgScopeView) {
    allScopes = [...new Set(hist.flatMap(h => Object.keys(h.scopes || {})))].sort();
    allScopes.forEach((s, i) => { scopeColorMap[s] = SCOPE_COLORS[i % SCOPE_COLORS.length]; });
    const barWidth = Math.min(plotW / Math.max(hist.length, 1) * 0.6, 60);
    const barBottom = yOf(0);
    hist.forEach(h => {
      let cumY = barBottom;
      allScopes.forEach(scope => {
        const val = (h.scopes && h.scopes[scope]) || 0;
        if (val <= 0) return;
        const barH = (val / maxVal) * plotH;
        const rect = document.createElementNS(NS, 'rect');
        rect.setAttribute('x', xOf(h.year) - barWidth / 2);
        rect.setAttribute('y', cumY - barH);
        rect.setAttribute('width', barWidth);
        rect.setAttribute('height', barH);
        rect.setAttribute('fill', scopeColorMap[scope]);
        rect.setAttribute('opacity', '0.75');
        rect.setAttribute('class', 'esg-chart__bar');
        svg.appendChild(rect);
        cumY -= barH;
      });
    });
    esgUpdateLegend(allScopes, scopeColorMap);
  } else {
    esgResetLegend();
  }

  // Historical line (on top of bars)
  const histPath = hist.map((h, i) => (i ? 'L' : 'M') + xOf(h.year) + ',' + yOf(h.total)).join(' ');
  const histLine = document.createElementNS(NS, 'path');
  histLine.setAttribute('d', histPath);
  histLine.setAttribute('class', 'esg-chart__path esg-chart__path--hist');
  svg.appendChild(histLine);

  // Projection line
  if (proj.length) {
    const projPath = proj.map((p, i) => (i ? 'L' : 'M') + xOf(p.year) + ',' + yOf(p.total)).join(' ');
    const projLine = document.createElementNS(NS, 'path');
    projLine.setAttribute('d', projPath);
    projLine.setAttribute('class', 'esg-chart__path esg-chart__path--proj');
    svg.appendChild(projLine);
  }

  // Dots — title attribute removed; custom tooltip handles hover
  hist.forEach(h => {
    const dot = document.createElementNS(NS, 'circle');
    dot.setAttribute('cx', xOf(h.year)); dot.setAttribute('cy', yOf(h.total));
    dot.setAttribute('r', 4);
    dot.setAttribute('class', 'esg-chart__dot');
    svg.appendChild(dot);
  });

  canvas.appendChild(svg);

  esgInitChartTooltip(canvas, svg, hist, proj, carbon.unit, allScopes, scopeColorMap, xOf);
}


function esgInitChartTooltip(canvas, svg, hist, proj, unit, allScopes, scopeColorMap, xOf) {
  let tip = document.getElementById('esg-chart-tooltip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'esg-chart-tooltip';
    tip.className = 'esg-chart__tooltip';
    tip.setAttribute('hidden', '');
    canvas.appendChild(tip);
  }

  const projPoints = proj.map(p => ({ year: p.year, total: p.total, scopes: {}, isProj: true }));
  const allPoints = hist.map(h => Object.assign({}, h, { isProj: false })).concat(projPoints);
  const unitStr = unit || 'tCO2e';

  svg.addEventListener('mousemove', e => {
    const svgRect = svg.getBoundingClientRect();
    const canvasRect = canvas.getBoundingClientRect();
    const mouseX = (e.clientX - svgRect.left) * (1000 / svgRect.width);

    let nearest = allPoints[0];
    let minDist = Infinity;
    allPoints.forEach(p => {
      const d = Math.abs(xOf(p.year) - mouseX);
      if (d < minDist) { minDist = d; nearest = p; }
    });

    const scopes = nearest.scopes || {};
    const total = nearest.total;
    let html = '<div class="esg-chart__tooltip-year">' + escHtml(String(nearest.year)) + '</div>';

    if (esgScopeView && !nearest.isProj && allScopes.length) {
      allScopes.forEach(scope => {
        const val = scopes[scope] || 0;
        if (val <= 0) return;
        const pct = total > 0 ? (val / total * 100).toFixed(1) : '0.0';
        html +=
          '<div class="esg-chart__tooltip-row">' +
          '<span class="esg-chart__tooltip-dot" style="background:' + scopeColorMap[scope] + '"></span>' +
          '<span class="esg-chart__tooltip-name">' + escHtml(scope) + '</span>' +
          '<span class="esg-chart__tooltip-val">' + esgFmtNum(val) + '</span>' +
          '<span class="esg-chart__tooltip-pct">' + pct + '%</span>' +
          '</div>';
      });
      html += '<hr class="esg-chart__tooltip-sep">';
      html += '<div class="esg-chart__tooltip-total"><span>' + gettext('Total') + '</span><span>' +
        esgFmtNum(total) + ' ' + escHtml(unitStr) + '</span></div>';
    } else {
      html += '<div class="esg-chart__tooltip-row"><span>' +
        esgFmtNum(total) + ' ' + escHtml(unitStr) + '</span></div>';
      if (nearest.isProj) {
        html += '<div style="font-size:11px;color:var(--color-on-surface-variant);margin-top:4px">' +
          gettext('Projection') + '</div>';
      }
    }

    tip.innerHTML = html;
    tip.removeAttribute('hidden');

    const tipW = tip.offsetWidth;
    const tipH = tip.offsetHeight;
    const canvasW = canvasRect.width;
    const canvasH = canvasRect.height;
    let left = e.clientX - canvasRect.left + 12;
    let top = e.clientY - canvasRect.top - 8;
    if (left + tipW > canvasW - 4) left = e.clientX - canvasRect.left - tipW - 12;
    if (top + tipH > canvasH - 4) top = canvasH - tipH - 4;
    if (top < 0) top = 4;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  });

  svg.addEventListener('mouseleave', () => tip.setAttribute('hidden', ''));
}


function esgRenderFeatured(featured) {
  const wrap = document.getElementById('esg-featured');
  if (!wrap) return;
  if (!featured || !featured.length) {
    wrap.innerHTML = '<p class="esg-empty">' + gettext('Aucune politique enregistrée.') + '</p>';
    return;
  }
  wrap.innerHTML = featured.map(p => {
    const tags = (p.tags || []).map(t =>
      '<span class="esg-policy-card__tag">' + escHtml(t) + '</span>').join('');
    const score = p.score != null
      ? '<span class="esg-policy-card__score">' + Math.round(p.score) + '</span>' : '';
    return (
      '<article class="card esg-policy-card">' +
      '<div class="esg-policy-card__head">' +
      '<h4 class="esg-policy-card__title">' + escHtml(p.subcategory) + '</h4>' +
      score +
      '</div>' +
      '<p class="esg-policy-card__level">' + escHtml(p.level) + '</p>' +
      '<p class="esg-policy-card__desc">' + escHtml(p.description || '') + '</p>' +
      '<div class="esg-policy-card__tags">' + tags + '</div>' +
      '</article>'
    );
  }).join('');
}


const ESG_ENV_POLICY_TYPES = ['Circular', 'Climate', 'Water policy'];

function esgRenderFramework(framework) {
  const list = document.getElementById('esg-framework-list');
  if (!list) return;
  const filtered = (framework || []).filter(p => ESG_ENV_POLICY_TYPES.includes(p.type));
  if (!filtered.length) {
    list.innerHTML = '<p class="esg-empty">' + gettext('Aucune politique enregistrée.') + '</p>';
    return;
  }
  list.innerHTML = filtered.map((p, i) => {
    const year = p.date ? (p.date.match(/\d{4}/) || [''])[0] : '';
    const sub = [p.level, year].filter(Boolean).join(' • ');
    const scoreVal = p.score != null ? Math.round(p.score) : null;
    const scoreHtml = scoreVal != null
      ? '<span class="esg-framework__item-score" style="background:' + esgScoreColor(scoreVal) + '">' + scoreVal + '</span>'
      : '';
    const desc = p.description || '';
    const hasDesc = desc.trim().length > 0;
    const itemId = 'esg-fw-desc-' + i;
    return (
      '<div class="esg-framework__item' + (hasDesc ? ' esg-framework__item--collapsible' : '') + '">' +
      '<div class="esg-framework__item-header"' +
        (hasDesc ? ' role="button" tabindex="0" aria-expanded="false" aria-controls="' + itemId + '"' : '') + '>' +
      '<div class="esg-framework__item-text">' +
      '<p class="esg-framework__item-name">' + escHtml(p.subcategory) + '</p>' +
      '<p class="esg-framework__item-sub">' + escHtml(sub) + '</p>' +
      '</div>' +
      '<div class="esg-framework__item-right">' +
      scoreHtml +
      '<span class="esg-framework__item-type">' + escHtml(p.type) + '</span>' +
      (hasDesc
        ? '<svg class="esg-framework__chevron" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
          '<path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>' +
          '</svg>'
        : '') +
      '</div>' +
      '</div>' +
      (hasDesc
        ? '<div class="esg-framework__item-desc" id="' + itemId + '" hidden>' +
          '<p>' + escHtml(desc) + '</p>' +
          '</div>'
        : '') +
      '</div>'
    );
  }).join('');

  list.querySelectorAll('.esg-framework__item-header[role="button"]').forEach(header => {
    function toggle() {
      const expanded = header.getAttribute('aria-expanded') === 'true';
      header.setAttribute('aria-expanded', String(!expanded));
      const desc = document.getElementById(header.getAttribute('aria-controls'));
      if (desc) { if (expanded) desc.setAttribute('hidden', ''); else desc.removeAttribute('hidden'); }
      const chevron = header.querySelector('.esg-framework__chevron');
      if (chevron) chevron.style.transform = expanded ? '' : 'rotate(180deg)';
    }
    header.addEventListener('click', toggle);
    header.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
  });
}


function esgScoreColor(score) {
  const hue = Math.max(0, Math.min(100, score)) * 1.2;
  return 'hsl(' + hue + ',72%,42%)';
}


const ESG_RANGES = [['3mo', '3M'], ['6mo', '6M'], ['ytd', 'YTD'], ['5y', '5Y']];


function esgRangeButtons(active) {
  return '<div class="esg-market__ranges" role="group" aria-label="' +
    gettext('Période') + '">' +
    ESG_RANGES.map(([key, label]) =>
      '<button type="button" class="esg-market__range' +
      (key === active ? ' esg-market__range--active' : '') +
      '" data-range="' + key + '"' +
      (key === active ? ' aria-current="true"' : '') + '>' + label + '</button>'
    ).join('') +
    '</div>';
}


function esgRenderMarket(market) {
  const body = document.getElementById('esg-market-body');
  const demo = document.getElementById('esg-market-demo');
  if (!body) return;
  if (demo) demo.hidden = !market.is_demo;

  const active = market.range || '3mo';

  body.innerHTML =
    '<div class="esg-market__price-row">' +
    '<div><p class="esg-market__price-label label-caps">' +
    escHtml(interpolate(gettext('Cours (%(ticker)s)'), { ticker: market.ticker || '—' }, true)) +
    '</p>' +
    '<p class="esg-market__price">' + esgFmtMoney(market.price, market.currency) + '</p></div>' +
    '<div class="esg-market__change" id="esg-market-change"></div>' +
    '</div>' +
    esgRangeButtons(active) +
    '<div id="esg-market-spark">' + esgSparkline(market.sparkline || []) + '</div>' +
    '<div class="esg-market__stats">' +
    esgStatRow(gettext('Capitalisation'), market.market_cap) +
    esgStatRow(gettext('Notation ESG'), market.esg_rating) +
    esgStatRow(gettext('Perf. relative'), market.relative_perf) +
    esgStatRow('ISIN', market.isin) +
    '</div>';

  esgUpdateChange(market.change_pct);
  esgBindRangeButtons();
}


function esgUpdateChange(changePct) {
  const el = document.getElementById('esg-market-change');
  if (!el) return;
  const up = changePct >= 0;
  el.className = 'esg-market__change ' + (up ? 'esg-market__change--up' : 'esg-market__change--down');
  el.textContent = (up ? '+' : '') + changePct + '%';
}


function esgSetActiveRange(range) {
  document.querySelectorAll('.esg-market__range').forEach(btn => {
    const active = btn.dataset.range === range;
    btn.classList.toggle('esg-market__range--active', active);
    if (active) { btn.setAttribute('aria-current', 'true'); } else { btn.removeAttribute('aria-current'); }
  });
}


function esgBindRangeButtons() {
  const wrap = document.querySelector('.esg-market__ranges');
  if (!wrap) return;
  wrap.addEventListener('click', (e) => {
    const btn = e.target.closest('.esg-market__range');
    if (btn) esgLoadRange(btn.dataset.range);
  });
}


function esgLoadRange(range) {
  const data = ESG_STATE.data;
  if (!data || !data.market || !data.company_id) return;
  esgSetActiveRange(range);
  fetch(ESG_MARKET_URL.replace('/0/', '/' + data.company_id + '/') + '?range=' + encodeURIComponent(range))
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(d => {
      const sparkEl = document.getElementById('esg-market-spark');
      if (sparkEl) sparkEl.innerHTML = esgSparkline(d.sparkline || []);
      esgUpdateChange(d.change_pct);
      const demo = document.getElementById('esg-market-demo');
      if (demo) demo.hidden = !d.is_demo;
      data.market.range = d.range;
      data.market.sparkline = d.sparkline;
      data.market.change_pct = d.change_pct;
    })
    .catch(err => console.error('esg market range fetch failed:', err));
}


function esgStatRow(label, value) {
  if (value == null) return '';
  return '<div class="esg-market__stat">' +
    '<span class="esg-market__stat-label">' + escHtml(label) + '</span>' +
    '<span class="esg-market__stat-value">' + escHtml(String(value)) + '</span>' +
    '</div>';
}


function esgSparkline(points) {
  if (!points.length) return '';
  const max = Math.max(...points, 1);
  const stepX = 200 / (points.length - 1 || 1);
  const d = points.map((p, i) =>
    (i ? 'L' : 'M') + (i * stepX).toFixed(1) + ',' + (40 - (p / max) * 35).toFixed(1)).join(' ');
  return '<svg class="esg-market__spark" viewBox="0 0 200 40" preserveAspectRatio="none">' +
    '<path d="' + d + '" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
}


function esgInitCombobox(companies, initialData) {
  CompanyCombobox.init({
    root: document.getElementById('company-combobox'),
    companies,
    selected: initialData,
    onSelect: id => {
      fetch(ESG_API_URL.replace('/0/', '/' + id + '/'))
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(data => esgRender(data))
        .catch(err => console.error('esg fetch failed:', err));
    },
  });
}


function esgFmtNum(val) {
  if (Math.abs(val) >= 1e6) return (val / 1e6).toFixed(1) + ' M';
  if (Math.abs(val) >= 1e3) return (val / 1e3).toFixed(1) + ' k';
  return String(Math.round(val));
}


function esgFmtMoney(val, currency) {
  const sym = currency === 'EUR' ? '€' : (currency === 'USD' ? '$' : '');
  return sym + Number(val).toFixed(2);
}


function esgUpdateLegend(allScopes, scopeColorMap) {
  const legendEl = document.querySelector('.esg-chart__legend');
  if (!legendEl) return;
  legendEl.innerHTML =
    allScopes.map(scope =>
      '<span class="esg-chart__legend-item">' +
      '<span class="esg-chart__legend-dot" style="background:' + scopeColorMap[scope] + '"></span>' +
      escHtml(scope) +
      '</span>'
    ).join('') +
    '<span class="esg-chart__legend-item" style="opacity:.5">' +
    '<span class="esg-chart__line esg-chart__line--solid"></span>' + gettext('Historique') +
    '</span>' +
    '<span class="esg-chart__legend-item" style="opacity:.5">' +
    '<span class="esg-chart__line esg-chart__line--dashed"></span>' + gettext('Projection 2030') +
    '</span>';
}


function esgResetLegend() {
  const legendEl = document.querySelector('.esg-chart__legend');
  if (!legendEl) return;
  legendEl.innerHTML =
    '<span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--solid"></span>' +
    gettext('Historique') + '</span>' +
    '<span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--dashed"></span>' +
    gettext('Projection 2030') + '</span>';
}


function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
