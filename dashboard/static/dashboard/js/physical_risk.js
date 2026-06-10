const PR_COMPANY_KEY = 'selected-company-id'; // shared localStorage slot across risk pages

const PR_STATE = {
  data: null,
  selectedKey: null,
  horizon: 5,
  map: null,
};

const PR_BAND_COLORS = {
  Low:      '#dac1ba',
  Moderate: '#feb87c',
  High:     '#af5d43',
  Critical: '#91452d',
};

function prBand(score) {
  if (score >= 0.7) return 'Critical';
  if (score >= 0.5) return 'High';
  if (score >= 0.2) return 'Moderate';
  return 'Low';
}

function prFmtEuro(v) {
  return Math.round(v).toLocaleString('fr-FR') + ' €';
}

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  PR_STATE.map = prInitMap();
  prInitHorizon();

  const savedId = parseInt(localStorage.getItem(PR_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    fetch(PHYSICAL_RISK_API_URL.replace('/0/', '/' + savedId + '/'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(data => { prRender(data); prInitCombobox(companies, data); })
      .catch(err => console.error('physical_risk fetch failed:', err));
  } else {
    if (initialData) prRender(initialData);
    prInitCombobox(companies, initialData);
  }
});


// ── Combobox (mirrors transition_risk.js) ──────────────────────────────────
function prInitCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');
  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData) input.value = initialData.company_name;

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
    localStorage.setItem(PR_COMPANY_KEY, id);
    fetch(PHYSICAL_RISK_API_URL.replace('/0/', '/' + id + '/'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(data => prRender(data))
      .catch(err => console.error('physical_risk fetch failed:', err));
  });

  document.addEventListener('click', (e) => {
    if (!combobox.contains(e.target)) closeList();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeList();
  });
}


// ── Horizon toggle (5 / 10 years) ──────────────────────────────────────────
function prInitHorizon() {
  const group = document.querySelector('.pr-horizon');
  if (!group) return;
  group.addEventListener('click', (e) => {
    const btn = e.target.closest('.pr-horizon__btn');
    if (!btn) return;
    PR_STATE.horizon = parseInt(btn.dataset.years, 10);
    group.querySelectorAll('.pr-horizon__btn').forEach(b => {
      const active = b === btn;
      b.classList.toggle('active', active);
      b.setAttribute('aria-pressed', String(active));
    });
    prRenderLoss();
  });
}


// ── Top-level render ───────────────────────────────────────────────────────
function prRender(data) {
  PR_STATE.data = data;
  PR_STATE.selectedKey = data.hazards && data.hazards.length ? data.hazards[0].key : null;
  prRenderKpis(data);
  prRenderRanking(data);
  prSyncMapData();
  prRenderTable();
}

function prRenderKpis(data) {
  const highRisk = document.getElementById('pr-high-risk');
  if (highRisk) highRisk.textContent = data.kpis.assets_high_risk;
  const avgVuln = document.getElementById('pr-avg-vuln');
  if (avgVuln) {
    const av = data.kpis.avg_vulnerability;
    avgVuln.textContent = av != null ? (av * 100).toFixed(1) + '%' : '—';
  }
  prRenderLoss();
}

function prRenderLoss() {
  const el = document.getElementById('pr-annual-loss');
  if (!el || !PR_STATE.data) return;
  const loss = PR_STATE.data.kpis.annual_loss;
  el.textContent = loss != null ? prFmtEuro(loss * PR_STATE.horizon) : '—';
}


// ── Ranking (doubles as hazard selector) ───────────────────────────────────
function prRenderRanking(data) {
  const container = document.getElementById('pr-ranking');
  if (!container) return;
  if (!data.hazards || data.hazards.length === 0) {
    container.innerHTML = '<p class="pr-empty">Aucune donnée disponible.</p>';
    return;
  }
  const maxRisk = data.hazards.reduce((m, h) => h.avg_risk > m ? h.avg_risk : m, 0) || 1;
  container.innerHTML = data.hazards.map(h => {
    const pct = (h.avg_risk / maxRisk) * 100;
    const isSel = h.key === PR_STATE.selectedKey;
    const sel = isSel ? ' pr-rank-row--selected' : '';
    return `
      <button type="button"
        class="pr-rank-row${sel}"
        data-key="${h.key}"
        aria-pressed="${isSel}">
        <span class="pr-rank-row__name">${escHtml(h.name)}</span>
        <span class="pr-rank-row__track">
          <span class="pr-rank-row__fill" style="width:${pct.toFixed(1)}%"></span>
        </span>
        <span class="pr-rank-row__val data-tabular">${prFmtEuro(h.avg_risk)}</span>
      </button>`;
  }).join('');

  container.querySelectorAll('.pr-rank-row').forEach(row => {
    row.addEventListener('click', () => prSelectHazard(row.dataset.key));
  });
}

function prSelectHazard(key) {
  PR_STATE.selectedKey = key;
  const container = document.getElementById('pr-ranking');
  if (container) {
    container.querySelectorAll('.pr-rank-row').forEach(row => {
      const active = row.dataset.key === key;
      row.classList.toggle('pr-rank-row--selected', active);
      row.setAttribute('aria-pressed', String(active));
    });
  }
  prSyncMapData();
  prRenderTable();
}

function prCurrentHazard() {
  if (!PR_STATE.data || !PR_STATE.selectedKey) return null;
  return PR_STATE.data.hazards.find(h => h.key === PR_STATE.selectedKey) || null;
}


// ── Table (reactive to selected hazard) ────────────────────────────────────
function prRenderTable() {
  const body = document.getElementById('pr-table-body');
  const hazardLabel = document.getElementById('pr-selected-hazard');
  if (!body) return;

  const hazard = prCurrentHazard();
  if (hazardLabel) hazardLabel.textContent = hazard ? hazard.name : '—';

  const data = PR_STATE.data;
  if (!data || !hazard || data.assets.length === 0) {
    body.innerHTML = '<tr><td colspan="5" class="pr-empty">Aucun actif.</td></tr>';
    return;
  }

  const key = hazard.key;
  const vuln = hazard.vulnerability != null ? hazard.vulnerability : 0;
  const rows = data.assets.map(a => {
    const hz = a.risk[key] || 0;
    const risk = hz * a.exposition * vuln;
    return { name: a.name, hz: hz, expo: a.exposition, risk: risk };
  }).sort((x, y) => y.risk - x.risk);

  body.innerHTML = rows.map(r => `
    <tr>
      <td>${escHtml(r.name)}</td>
      <td class="data-tabular">${(r.hz * 100).toFixed(1)}%</td>
      <td class="data-tabular">${prFmtEuro(r.expo)}</td>
      <td class="data-tabular">${(vuln * 100).toFixed(1)}%</td>
      <td class="data-tabular pr-table__risk">${prFmtEuro(r.risk)}</td>
    </tr>`).join('');
}


// ── Map ────────────────────────────────────────────────────────────────────
function prInitMap() {
  const container = document.getElementById('pr-map');
  if (!container || typeof maplibregl === 'undefined') return null;

  const map = new maplibregl.Map({
    container: 'pr-map',
    style: 'https://tiles.openfreemap.org/styles/liberty',
    center: [0, 20],
    zoom: 1.5,
  });

  map.on('load', () => {
    map.addSource('pr-assets', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
    map.addLayer({
      id: 'pr-assets-layer',
      type: 'circle',
      source: 'pr-assets',
      paint: {
        'circle-radius': ['get', 'radius'],
        'circle-color': ['get', 'color'],
        'circle-opacity': 0.75,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff',
      },
    });

    map.on('click', 'pr-assets-layer', (e) => {
      const p = e.features[0].properties;
      new maplibregl.Popup()
        .setLngLat(e.lngLat)
        .setHTML(
          `<strong>${escHtml(p.name)}</strong><br>` +
          `${escHtml(p.hazardName)} : ${(Number(p.hazard) * 100).toFixed(1)}%<br>` +
          `Exposition : ${prFmtEuro(Number(p.exposition))}<br>` +
          `Risk : ${prFmtEuro(Number(p.risk))}`
        )
        .addTo(map);
    });
    map.on('mouseenter', 'pr-assets-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'pr-assets-layer', () => { map.getCanvas().style.cursor = ''; });

    if (window._prPendingGeojson) {
      map.getSource('pr-assets').setData(window._prPendingGeojson);
      window._prPendingGeojson = null;
    }
  });

  return map;
}

function prBuildGeojson() {
  const data = PR_STATE.data;
  const hazard = prCurrentHazard();
  if (!data || !hazard) return { type: 'FeatureCollection', features: [] };

  const key = hazard.key;
  const vuln = hazard.vulnerability;
  const risks = data.assets.map(a => (a.risk[key] || 0) * a.exposition * vuln);
  const maxRisk = risks.reduce((m, v) => v > m ? v : m, 0) || 1;

  const features = data.assets.map((a, i) => {
    const hz = a.risk[key] || 0;
    const risk = risks[i];
    const radius = 6 + 18 * (risk / maxRisk);
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [a.longitude, a.latitude] },
      properties: {
        name: a.name,
        hazardName: hazard.name,
        hazard: hz,
        exposition: a.exposition,
        risk: risk,
        radius: radius,
        color: PR_BAND_COLORS[prBand(hz)],
      },
    };
  });
  return { type: 'FeatureCollection', features: features };
}

function prSyncMapData() {
  const map = PR_STATE.map;
  const geojson = prBuildGeojson();
  if (!map) return;
  if (map.loaded() && map.getSource('pr-assets')) {
    map.getSource('pr-assets').setData(geojson);
  } else {
    window._prPendingGeojson = geojson;
  }
}
