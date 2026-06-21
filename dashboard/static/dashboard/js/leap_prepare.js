const LP_COMPANY_KEY = 'selected-company-id'; // partagé entre pages

let LP_AREA_CHART = null;

const LP_STATE = {
  data: null,
  groupBy: 'asset',            // 'asset' | 'commodity'
  prodDelta: {},               // asset_id -> delta (ex. 0.10 = +10%)
  impactDelta: {},             // commodity_id -> delta
  areaView: 'total',           // 'total' | 'commodity'
};

const LP_GOOD = '#2d6a4f';
const LP_BAD = '#ba1a1a';
const LP_GREY = '#87736d';
const LP_INK = '#1b1c19';   // = --color-on-surface (var() non résolu dans les attributs SVG)
const LP_SVG_NS = 'http://www.w3.org/2000/svg';

function lpFmt(v) {
  v = Number(v) || 0;
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toLocaleString('fr-FR', { maximumFractionDigits: 0 });
  if (abs >= 1)    return v.toLocaleString('fr-FR', { maximumFractionDigits: 2 });
  if (abs === 0)   return '0';
  return v.toLocaleString('fr-FR', { maximumFractionDigits: 4 });
}

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl || !document.getElementById('lp-dumbbell')) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  lpInitGroupBy();
  lpInitReset();
  lpInitAreaToggle();

  const savedId = parseInt(localStorage.getItem(LP_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    lpFetch(savedId).then(data => lpInitCombobox(companies, data || initialData));
  } else {
    if (initialData) lpLoad(initialData);
    lpInitCombobox(companies, initialData);
  }
});

function lpFetch(id) {
  return fetch(LEAP_PREPARE_API_URL.replace('/0/', '/' + id + '/'))
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => { lpLoad(data); return data; })
    .catch(err => console.error('leap_prepare fetch failed:', err));
}

// Charge un nouveau jeu de données : remet les leviers à zéro puis rend tout.
function lpLoad(data) {
  LP_STATE.data = data;
  LP_STATE.prodDelta = {};
  LP_STATE.impactDelta = {};
  (data.assets || []).forEach(a => { LP_STATE.prodDelta[a.id] = 0; });
  (data.commodities || []).forEach(c => { LP_STATE.impactDelta[c.id] = 0; });
  lpRenderLevers();
  lpRecompute();
}

// ── Combobox entreprise (aligné sur leap_locate.js) ─────────────────────────
function lpInitCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');
  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData && initialData.company_name) input.value = initialData.company_name;

  function buildList(filter) {
    const q = filter.toLowerCase();
    const matched = companies.filter(c => c.name.toLowerCase().includes(q));
    listbox.innerHTML = matched.map(c =>
      `<li role="option" data-id="${c.id}" class="company-combobox__option${c.id === selected ? ' selected' : ''}">${escHtml(c.name)}</li>`
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

  listbox.addEventListener('click', (e) => {
    const opt = e.target.closest('[role="option"]');
    if (!opt) return;
    const id = parseInt(opt.dataset.id, 10);
    selected = id;
    input.value = opt.textContent;
    closeList();
    localStorage.setItem(LP_COMPANY_KEY, id);
    lpFetch(id);
  });

  document.addEventListener('click', (e) => { if (!combobox.contains(e.target)) closeList(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeList(); });
}

// ── Leviers ─────────────────────────────────────────────────────────────────
function lpInitGroupBy() {
  const sel = document.getElementById('lp-group-by');
  if (!sel) return;
  sel.addEventListener('change', () => {
    LP_STATE.groupBy = sel.value;
    lpRenderDumbbell();
  });
}

function lpInitReset() {
  const btn = document.getElementById('lp-reset');
  if (!btn) return;
  btn.addEventListener('click', () => {
    Object.keys(LP_STATE.prodDelta).forEach(k => { LP_STATE.prodDelta[k] = 0; });
    Object.keys(LP_STATE.impactDelta).forEach(k => { LP_STATE.impactDelta[k] = 0; });
    lpRenderLevers();
    lpRecompute();
  });
}

function lpCommodityMap() {
  const m = {};
  (LP_STATE.data.commodities || []).forEach(c => { m[c.id] = c; });
  return m;
}

function lpRenderLevers() {
  const data = LP_STATE.data;
  const prodBox = document.getElementById('lp-prod-levers');
  const impBox = document.getElementById('lp-impact-levers');
  if (!data || !prodBox || !impBox) return;

  // Production par asset : valeur de base = somme des qty des lignes de l'asset.
  const assets = data.assets || [];
  if (!assets.length) {
    prodBox.innerHTML = '<p class="lp-empty">Aucun asset à simuler.</p>';
  } else {
    prodBox.innerHTML = assets.map(a => {
      const base = a.lines.reduce((s, l) => s + l.qty, 0);
      const unit = (a.lines[0] && a.lines[0].unit) || '';
      return lpLeverRow('prod', a.id, a.name, base, unit, 0);
    }).join('');
  }

  const commodities = data.commodities || [];
  if (!commodities.length) {
    impBox.innerHTML = '<p class="lp-empty">Aucune commodité à simuler.</p>';
  } else {
    impBox.innerHTML = commodities.map(c =>
      lpLeverRow('impact', c.id, c.name, c.impact_factor, '', 4)
    ).join('');
  }

  lpBindLevers(prodBox, 'prod');
  lpBindLevers(impBox, 'impact');
}

// kind: 'prod' | 'impact' ; base = valeur actuelle ; digits = décimales du champ.
function lpLeverRow(kind, id, name, base, unit, digits) {
  const unitHtml = unit ? `<span class="lp-lever__unit">${escHtml(unit)}</span>` : '';
  const val = base.toFixed(digits);
  return `
    <div class="lp-lever" data-kind="${kind}" data-id="${id}" data-base="${base}">
      <div class="lp-lever__top">
        <span class="lp-lever__name">${escHtml(name)}</span>
        <span class="lp-lever__delta" data-role="delta">0 %</span>
      </div>
      <div class="lp-lever__controls">
        <input type="range" class="lp-lever__slider" min="-100" max="100" step="1" value="0"
               aria-label="Variation ${escHtml(name)}">
        <input type="number" class="lp-lever__input" step="any" min="0" value="${val}"
               data-digits="${digits}" aria-label="Valeur ${escHtml(name)}">
        ${unitHtml}
      </div>
    </div>`;
}

function lpBindLevers(box, kind) {
  const store = kind === 'prod' ? LP_STATE.prodDelta : LP_STATE.impactDelta;
  box.querySelectorAll('.lp-lever').forEach(row => {
    const id = parseInt(row.dataset.id, 10);
    const base = parseFloat(row.dataset.base);
    const slider = row.querySelector('.lp-lever__slider');
    const input = row.querySelector('.lp-lever__input');
    const deltaEl = row.querySelector('[data-role="delta"]');
    const digits = parseInt(input.dataset.digits, 10) || 0;

    function setDelta(delta) {
      store[id] = delta;
      const pct = Math.round(delta * 100);
      deltaEl.textContent = (pct > 0 ? '+' : '') + pct + ' %';
      deltaEl.style.color = pct < 0 ? LP_GOOD : (pct > 0 ? LP_BAD : '');
      lpRecompute();
    }

    slider.addEventListener('input', () => {
      const delta = parseInt(slider.value, 10) / 100;
      input.value = (base * (1 + delta)).toFixed(digits);
      setDelta(delta);
    });
    input.addEventListener('input', () => {
      const next = parseFloat(input.value);
      if (isNaN(next) || base === 0) return;
      const delta = next / base - 1;
      slider.value = Math.max(-100, Math.min(100, Math.round(delta * 100)));
      setDelta(delta);
    });
  });
}

// ── Calcul + agrégation ──────────────────────────────────────────────────────
// Renvoie [{key, name, current, future}] selon LP_STATE.groupBy, + totaux.
function lpComputeItems() {
  const data = LP_STATE.data;
  const commMap = lpCommodityMap();
  const byAsset = {};
  const byCommodity = {};
  let totalCur = 0, totalFut = 0;

  (data.assets || []).forEach(a => {
    const pd = LP_STATE.prodDelta[a.id] || 0;
    a.lines.forEach(l => {
      const comm = commMap[l.commodity_id];
      if (!comm) return;
      const id = LP_STATE.impactDelta[l.commodity_id] || 0;
      const cur = l.qty * comm.impact_factor;
      const fut = l.qty * (1 + pd) * comm.impact_factor * (1 + id);
      totalCur += cur; totalFut += fut;

      if (!byAsset[a.id]) byAsset[a.id] = { key: a.id, name: a.name, current: 0, future: 0 };
      byAsset[a.id].current += cur; byAsset[a.id].future += fut;

      if (!byCommodity[comm.id]) byCommodity[comm.id] = { key: comm.id, name: comm.name, current: 0, future: 0 };
      byCommodity[comm.id].current += cur; byCommodity[comm.id].future += fut;
    });
  });

  const src = LP_STATE.groupBy === 'commodity' ? byCommodity : byAsset;
  const items = Object.values(src).sort((x, y) => y.current - x.current);
  return { items, totalCur, totalFut };
}

function lpRecompute() {
  if (!LP_STATE.data) return;
  const { totalCur, totalFut } = lpComputeItems();
  lpRenderKpis(totalCur, totalFut);
  lpRenderDumbbell();
}

function lpRenderKpis(totalCur, totalFut) {
  const curEl = document.getElementById('lp-impact-current');
  const futEl = document.getElementById('lp-impact-future');
  const varEl = document.getElementById('lp-variation');
  const pill = document.getElementById('lp-variation-pill');
  if (curEl) curEl.textContent = lpFmt(totalCur);
  if (futEl) futEl.textContent = lpFmt(totalFut);

  if (varEl) {
    if (totalCur === 0) {
      varEl.textContent = '—';
      if (pill) pill.hidden = true;
    } else {
      const pct = (totalFut - totalCur) / totalCur * 100;
      varEl.textContent = (pct > 0 ? '+' : '') + pct.toFixed(1) + ' %';
      if (pill) {
        if (Math.abs(pct) < 0.05) {
          pill.hidden = true;
        } else {
          pill.hidden = false;
          const good = pct < 0;
          pill.textContent = good ? 'Mieux' : 'Moins bien';
          pill.className = 'lp-pill ' + (good ? 'lp-pill--good' : 'lp-pill--bad');
        }
      }
    }
  }

  lpRenderAreaChart(totalCur, totalFut);

  // Ligne total sous le dumbbell.
  const tCur = document.getElementById('lp-total-current');
  const tFut = document.getElementById('lp-total-future');
  const tDelta = document.getElementById('lp-total-delta');
  if (tCur) tCur.textContent = lpFmt(totalCur);
  if (tFut) tFut.textContent = lpFmt(totalFut);
  if (tDelta) {
    const diff = totalFut - totalCur;
    if (Math.abs(diff) < 1e-9) {
      tDelta.textContent = '±0';
      tDelta.className = 'lp-total__delta';
    } else {
      const good = diff < 0;
      tDelta.textContent = (diff > 0 ? '▲ +' : '▼ ') + lpFmt(diff);
      tDelta.className = 'lp-total__delta ' + (good ? 'lp-total__delta--good' : 'lp-total__delta--bad');
    }
  }
}

// ── Graphique aire T → T+1 ────────────────────────────────────────────────────
const LP_PALETTE = [
  '#91452d', '#865220', '#2d6a4f', '#625a4e', '#1a5276',
  '#6c3483', '#117a65', '#b7770d', '#922b21', '#1f618d',
];

function lpHexAlpha(hex, a) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

function lpCommByImpact() {
  const data = LP_STATE.data;
  if (!data) return [];
  const commMap = lpCommodityMap();
  const byCommodity = {};
  (data.assets || []).forEach(a => {
    const pd = LP_STATE.prodDelta[a.id] || 0;
    a.lines.forEach(l => {
      const comm = commMap[l.commodity_id];
      if (!comm) return;
      const id = LP_STATE.impactDelta[l.commodity_id] || 0;
      const cur = l.qty * comm.impact_factor;
      const fut = l.qty * (1 + pd) * comm.impact_factor * (1 + id);
      if (!byCommodity[comm.id]) byCommodity[comm.id] = { name: comm.name, current: 0, future: 0 };
      byCommodity[comm.id].current += cur;
      byCommodity[comm.id].future += fut;
    });
  });
  return Object.values(byCommodity).sort((a, b) => b.current - a.current);
}

function lpAreaDatasets(totalCur, totalFut) {
  if (LP_STATE.areaView === 'total') {
    return [{
      label: 'Total',
      data: [totalCur, totalFut],
      borderColor: LP_PALETTE[0],
      backgroundColor: lpHexAlpha(LP_PALETTE[0], 0.15),
      borderWidth: 2.5,
      pointBackgroundColor: LP_PALETTE[0],
      pointRadius: 5,
      pointHoverRadius: 7,
      fill: true,
      tension: 0,
    }];
  }

  // Aire empilée : chaque commodité remplit vers la précédente (stacked)
  return lpCommByImpact().map((c, i) => {
    const color = LP_PALETTE[i % LP_PALETTE.length];
    return {
      label: c.name,
      data: [c.current, c.future],
      borderColor: color,
      backgroundColor: lpHexAlpha(color, 0.15),
      borderWidth: 1.5,
      pointBackgroundColor: color,
      pointRadius: 3,
      pointHoverRadius: 5,
      fill: true,
      tension: 0,
    };
  });
}

function lpRenderAreaChart(totalCur, totalFut) {
  const canvas = document.getElementById('lp-area-chart');
  if (!canvas || typeof Chart === 'undefined') return;

  const stacked = LP_STATE.areaView === 'commodity';
  const datasets = lpAreaDatasets(totalCur, totalFut);

  if (LP_AREA_CHART) {
    LP_AREA_CHART.data.datasets = datasets;
    LP_AREA_CHART.options.plugins.legend.display = stacked;
    LP_AREA_CHART.options.scales.y.stacked = stacked;
    LP_AREA_CHART.update('active');
    return;
  }

  const ctx = canvas.getContext('2d');
  LP_AREA_CHART = new Chart(ctx, {
    type: 'line',
    data: { labels: ['T', 'T+1'], datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: stacked,
          position: 'bottom',
          labels: {
            font: { family: 'Inter, sans-serif', size: 11 },
            color: '#54433e',
            boxWidth: 12,
            padding: 10,
          },
        },
        tooltip: {
          mode: 'index',
          callbacks: {
            label: (item) => ' ' + item.dataset.label + ' : ' + lpFmt(item.parsed.y),
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            font: { family: 'Inter, sans-serif', size: 13, weight: '600' },
            color: '#1b1c19',
          },
          border: { color: '#dac1ba' },
        },
        y: {
          stacked: false,
          beginAtZero: true,
          grid: { color: '#f0eee9' },
          ticks: {
            font: { family: 'Inter, sans-serif', size: 11 },
            color: '#87736d',
            callback: (v) => lpFmt(v),
          },
          border: { display: false },
        },
      },
    },
  });
}

function lpInitAreaToggle() {
  const btn = document.getElementById('lp-area-toggle');
  if (!btn) return;
  btn.addEventListener('click', () => {
    LP_STATE.areaView = LP_STATE.areaView === 'total' ? 'commodity' : 'total';
    btn.textContent = LP_STATE.areaView === 'total' ? 'Par commodité' : 'Total';
    btn.setAttribute('aria-pressed', LP_STATE.areaView === 'commodity');
    if (LP_STATE.data) lpRecompute();
  });
}

// ── Dumbbell SVG ──────────────────────────────────────────────────────────────
function lpRenderDumbbell() {
  const svg = document.getElementById('lp-dumbbell');
  if (!svg || !LP_STATE.data) return;
  const { items } = lpComputeItems();

  while (svg.firstChild) svg.removeChild(svg.firstChild);

  if (!items.length) {
    svg.setAttribute('viewBox', '0 0 600 80');
    const t = document.createElementNS(LP_SVG_NS, 'text');
    t.setAttribute('x', '300'); t.setAttribute('y', '44');
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('font-size', '13'); t.setAttribute('fill', LP_GREY);
    t.setAttribute('font-family', 'Inter, sans-serif');
    t.textContent = 'Aucune donnée à simuler.';
    svg.appendChild(t);
    return;
  }

  const W = 600;
  const rowH = 34;
  const padTop = 16, padBottom = 8;
  const labelW = 150, valueW = 70;
  const x0 = labelW;
  const x1 = W - valueW;
  const H = padTop + items.length * rowH + padBottom;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

  const maxVal = items.reduce(
    (m, it) => Math.max(m, it.current, it.future), 0
  ) || 1;
  const scale = (v) => x0 + (x1 - x0) * (v / maxVal);

  items.forEach((it, i) => {
    const cy = padTop + i * rowH + rowH / 2;
    const xc = scale(it.current);
    const xf = scale(it.future);
    const good = it.future < it.current;
    const changed = Math.abs(it.future - it.current) > 1e-9;
    const color = !changed ? LP_GREY : (good ? LP_GOOD : LP_BAD);

    // libellé
    const label = document.createElementNS(LP_SVG_NS, 'text');
    label.setAttribute('x', '0');
    label.setAttribute('y', String(cy + 4));
    label.setAttribute('font-size', '12');
    label.setAttribute('fill', LP_INK);
    label.setAttribute('font-family', 'Inter, sans-serif');
    label.textContent = it.name.length > 22 ? it.name.slice(0, 21) + '…' : it.name;
    svg.appendChild(label);

    // segment actuel → T+1
    const line = document.createElementNS(LP_SVG_NS, 'line');
    line.setAttribute('x1', String(xc)); line.setAttribute('y1', String(cy));
    line.setAttribute('x2', String(xf)); line.setAttribute('y2', String(cy));
    line.setAttribute('stroke', color); line.setAttribute('stroke-width', '2.5');
    svg.appendChild(line);

    // point actuel (gris)
    const dotC = document.createElementNS(LP_SVG_NS, 'circle');
    dotC.setAttribute('cx', String(xc)); dotC.setAttribute('cy', String(cy));
    dotC.setAttribute('r', '5'); dotC.setAttribute('fill', LP_GREY);
    svg.appendChild(dotC);

    // point T+1 (coloré)
    const dotF = document.createElementNS(LP_SVG_NS, 'circle');
    dotF.setAttribute('cx', String(xf)); dotF.setAttribute('cy', String(cy));
    dotF.setAttribute('r', '5'); dotF.setAttribute('fill', color);
    svg.appendChild(dotF);

    // étiquette Δ %
    const pct = it.current ? (it.future - it.current) / it.current * 100 : 0;
    const dlabel = document.createElementNS(LP_SVG_NS, 'text');
    dlabel.setAttribute('x', String(W));
    dlabel.setAttribute('y', String(cy + 4));
    dlabel.setAttribute('text-anchor', 'end');
    dlabel.setAttribute('font-size', '11');
    dlabel.setAttribute('fill', color);
    dlabel.setAttribute('font-family', 'Inter, sans-serif');
    dlabel.textContent = (pct > 0 ? '+' : '') + pct.toFixed(0) + ' %';
    svg.appendChild(dlabel);
  });
}
