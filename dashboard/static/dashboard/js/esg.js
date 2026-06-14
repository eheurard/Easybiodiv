'use strict';

const ESG_COMPANY_KEY = 'selected-company-id';

const ESG_STATE = { data: null };

let esgScopeView = false;
const SCOPE_COLORS = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948'];

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('esg-companies');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('esg-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  esgInitThemeTabs();

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


function esgRender(data) {
  ESG_STATE.data = data;
  esgRenderCarbon(data.carbon);
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
      html += '<div class="esg-chart__tooltip-total"><span>Total</span><span>' +
        esgFmtNum(total) + ' ' + escHtml(unitStr) + '</span></div>';
    } else {
      html += '<div class="esg-chart__tooltip-row"><span>' +
        esgFmtNum(total) + ' ' + escHtml(unitStr) + '</span></div>';
      if (nearest.isProj) {
        html += '<div style="font-size:11px;color:var(--color-on-surface-variant);margin-top:4px">Projection</div>';
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
    wrap.innerHTML = '<p class="esg-empty">Aucune politique enregistrée.</p>';
    return;
  }
  wrap.innerHTML = featured.map(p => {
    const tags = (p.tags || []).map(t =>
      '<span class="esg-policy-card__tag">' + escHtml(t) + '</span>').join('');
    const score = p.score != null
      ? '<span class="esg-policy-card__score">' + Math.round(p.score * 100) + '</span>' : '';
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
    list.innerHTML = '<p class="esg-empty">Aucune politique enregistrée.</p>';
    return;
  }
  list.innerHTML = filtered.map((p, i) => {
    const year = p.date ? (p.date.match(/\d{4}/) || [''])[0] : '';
    const sub = [p.level, year].filter(Boolean).join(' • ');
    const scoreVal = p.score != null ? Math.round(p.score * 100) : null;
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
  return '<div class="esg-market__ranges" role="group" aria-label="Période">' +
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
    '<div><p class="esg-market__price-label label-caps">Cours (' + escHtml(market.ticker || '—') + ')</p>' +
    '<p class="esg-market__price">' + esgFmtMoney(market.price, market.currency) + '</p></div>' +
    '<div class="esg-market__change" id="esg-market-change"></div>' +
    '</div>' +
    esgRangeButtons(active) +
    '<div id="esg-market-spark">' + esgSparkline(market.sparkline || []) + '</div>' +
    '<div class="esg-market__stats">' +
    esgStatRow('Capitalisation', market.market_cap) +
    esgStatRow('Notation ESG', market.esg_rating) +
    esgStatRow('Perf. relative', market.relative_perf) +
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
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');
  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData) input.value = initialData.company_name;

  function buildList(filter) {
    const q = filter.toLowerCase();
    listbox.innerHTML = companies
      .filter(c => c.name.toLowerCase().includes(q))
      .map(c =>
        '<li role="option" data-id="' + c.id + '" class="company-combobox__option' +
        (c.id === selected ? ' selected' : '') + '">' + escHtml(c.name) + '</li>'
      ).join('');
  }

  function openList() {
    buildList(input.value);
    listbox.removeAttribute('hidden');
    combobox.setAttribute('aria-expanded', 'true');
    if (chevron) chevron.style.transform = 'rotate(180deg)';
  }

  function closeList() {
    listbox.setAttribute('hidden', '');
    combobox.setAttribute('aria-expanded', 'false');
    if (chevron) chevron.style.transform = '';
  }

  input.addEventListener('focus', () => openList());
  input.addEventListener('input', () => { buildList(input.value); openList(); });

  listbox.addEventListener('click', e => {
    const opt = e.target.closest('[role="option"]');
    if (!opt) return;
    const id = parseInt(opt.dataset.id, 10);
    selected = id;
    input.value = opt.textContent;
    closeList();
    localStorage.setItem(ESG_COMPANY_KEY, id);
    fetch(ESG_API_URL.replace('/0/', '/' + id + '/'))
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => esgRender(data))
      .catch(err => console.error('esg fetch failed:', err));
  });

  document.addEventListener('click', e => {
    if (!combobox.contains(e.target)) closeList();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeList();
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
    '<span class="esg-chart__line esg-chart__line--solid"></span>Historique' +
    '</span>' +
    '<span class="esg-chart__legend-item" style="opacity:.5">' +
    '<span class="esg-chart__line esg-chart__line--dashed"></span>Projection 2030' +
    '</span>';
}


function esgResetLegend() {
  const legendEl = document.querySelector('.esg-chart__legend');
  if (!legendEl) return;
  legendEl.innerHTML =
    '<span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--solid"></span>Historique</span>' +
    '<span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--dashed"></span>Projection 2030</span>';
}


function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
