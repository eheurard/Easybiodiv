const LE_COMPANY_KEY = 'selected-company-id'; // partagé entre les pages risques/LEAP

const LE_STATE = {
  data: null,
  selectedKey: null, // impact actuellement sélectionné (dimensionne les points)
  map: null,
};

// Échelle séquentielle (clair → foncé) selon l'ampleur de l'impact de l'asset.
const LE_BAND_COLORS = {
  Low:      '#dac1ba',
  Moderate: '#feb87c',
  High:     '#af5d43',
  VeryHigh: '#91452d',
};

function leBand(ratio) {
  if (ratio >= 0.66) return 'VeryHigh';
  if (ratio >= 0.33) return 'High';
  if (ratio > 0)     return 'Moderate';
  return 'Low';
}

// Formatage des valeurs d'impact (pas des euros) avec une précision adaptée.
function leFmt(v) {
  v = Number(v) || 0;
  if (v === 0) return '0';
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toLocaleString('fr-FR', { maximumFractionDigits: 0 });
  if (abs >= 1)    return v.toLocaleString('fr-FR', { maximumFractionDigits: 2 });
  return v.toLocaleString('fr-FR', { maximumFractionDigits: 4 });
}

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl || !document.getElementById('leap-evaluate-map')) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  LE_STATE.map = leInitMap();
  leInitStyleToggle();

  const savedId = parseInt(localStorage.getItem(LE_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    leFetch(savedId).then(data => leInitCombobox(companies, data || initialData));
  } else {
    if (initialData) leRender(initialData);
    leInitCombobox(companies, initialData);
  }
});

function leFetch(id) {
  return fetch(LEAP_EVALUATE_API_URL.replace('/0/', '/' + id + '/'))
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => { leRender(data); return data; })
    .catch(err => console.error('leap_evaluate fetch failed:', err));
}


// ── Combobox entreprise (composant partagé company_combobox.js) ─────────────
function leInitCombobox(companies, initialData) {
  CompanyCombobox.init({
    root: document.getElementById('company-combobox'),
    companies,
    selected: initialData,
    onSelect: (id) => leFetch(id),
  });
}


// ── Rendu principal ─────────────────────────────────────────────────────────
function leRender(data) {
  LE_STATE.data = data;
  // Conserve l'impact sélectionné s'il existe encore, sinon prend le 1er du classement.
  const keys = (data.impacts || []).map(i => i.key);
  if (!LE_STATE.selectedKey || !keys.includes(LE_STATE.selectedKey)) {
    LE_STATE.selectedKey = keys.length ? keys[0] : null;
  }
  leRenderRanking(data);
  leSyncMapData();
}


// ── Classement des impacts (sert aussi de sélecteur) ────────────────────────
function leRenderRanking(data) {
  const container = document.getElementById('le-ranking');
  if (!container) return;
  if (!data.impacts || data.impacts.length === 0) {
    container.innerHTML = '<p class="pr-empty">Aucune donnée disponible.</p>';
    return;
  }
  const maxTotal = data.impacts.reduce((m, i) => i.total > m ? i.total : m, 0) || 1;
  container.innerHTML = data.impacts.map(i => {
    const pct = (i.total / maxTotal) * 100;
    const isSel = i.key === LE_STATE.selectedKey;
    const sel = isSel ? ' pr-rank-row--selected' : '';
    return `
      <button type="button"
        class="pr-rank-row${sel}"
        data-key="${i.key}"
        aria-pressed="${isSel}">
        <span class="pr-rank-row__name">${escHtml(i.name)}</span>
        <span class="pr-rank-row__track">
          <span class="pr-rank-row__fill" style="width:${pct.toFixed(1)}%"></span>
        </span>
        <span class="pr-rank-row__val data-tabular">${leFmt(i.total)}</span>
      </button>`;
  }).join('');

  container.querySelectorAll('.pr-rank-row').forEach(row => {
    row.addEventListener('click', () => leSelectImpact(row.dataset.key));
  });
}

function leSelectImpact(key) {
  LE_STATE.selectedKey = key;
  const container = document.getElementById('le-ranking');
  if (container) {
    container.querySelectorAll('.pr-rank-row').forEach(row => {
      const active = row.dataset.key === key;
      row.classList.toggle('pr-rank-row--selected', active);
      row.setAttribute('aria-pressed', String(active));
    });
  }
  leSyncMapData();
}

function leCurrentImpact() {
  if (!LE_STATE.data || !LE_STATE.selectedKey) return null;
  return LE_STATE.data.impacts.find(i => i.key === LE_STATE.selectedKey) || null;
}


// ── Carte ────────────────────────────────────────────────────────────────────
function leInitMap() {
  const container = document.getElementById('leap-evaluate-map');
  if (!container || typeof maplibregl === 'undefined') return null;

  const map = new maplibregl.Map({
    container: 'leap-evaluate-map',
    style: mapStyleFor('classic'),
    center: [0, 20],
    zoom: 1.5,
  });

  map.on('load', () => {
    leAddSourceAndLayer(map);
    leSyncMapData();
  });

  return map;
}

function leAddSourceAndLayer(map) {
  if (!map.getSource('le-assets')) {
    map.addSource('le-assets', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  }
  if (!map.getLayer('le-assets-layer')) {
    map.addLayer({
      id: 'le-assets-layer',
      type: 'circle',
      source: 'le-assets',
      paint: {
        'circle-radius': ['get', 'radius'],
        'circle-color': ['get', 'color'],
        'circle-opacity': 0.8,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff',
      },
    });
  }
  if (LE_STATE.assetsBound) return;
  LE_STATE.assetsBound = true;

  map.on('click', 'le-assets-layer', (e) => {
    const p = e.features[0].properties;
    const sensitive = (String(p.near_sensitive_zone) === 'true')
      ? `Oui${p.sensitive_zone_type ? ' — ' + escHtml(p.sensitive_zone_type) : ''}`
      : 'Non';
    const row = (label, value) =>
      `<div class="asset-popup__row">
        <span class="asset-popup__row-label">${label}</span>
        <span class="asset-popup__row-value">${value}</span>
      </div>`;
    new maplibregl.Popup({ maxWidth: '280px' })
      .setLngLat(e.lngLat)
      .setHTML(`
        <div class="asset-popup">
          <div class="asset-popup__header">
            <div class="asset-popup__name">${escHtml(p.name)}</div>
            <div class="asset-popup__meta">${escHtml(p.country || '')}</div>
          </div>
          <div class="asset-popup__body">
            <div class="asset-popup__rows">
              ${row('Consommation eau', leFmt(p.water_consumption))}
              ${row('Émissions CO₂', leFmt(p.co2_emissions))}
              ${row('Déchets générés', leFmt(p.waste_generated))}
              ${row('Zone sensible', sensitive)}
            </div>
            <div class="asset-popup__divider"></div>
            <div class="asset-popup__metrics">
              <div class="asset-popup__metric">
                <div class="asset-popup__metric-value">${leFmt(p.impactValue)}</div>
                <div class="asset-popup__metric-label">${escHtml(p.impactName)}</div>
              </div>
            </div>
          </div>
        </div>`)
      .addTo(map);
  });
  map.on('mouseenter', 'le-assets-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'le-assets-layer', () => { map.getCanvas().style.cursor = ''; });
}

function leBuildGeojson() {
  const data = LE_STATE.data;
  const impact = leCurrentImpact();
  if (!data || !impact) return { type: 'FeatureCollection', features: [] };

  const key = impact.key;
  const values = data.assets.map(a => (a.impacts && a.impacts[key]) || 0);
  const maxVal = values.reduce((m, v) => v > m ? v : m, 0) || 1;

  const features = data.assets.map((a, i) => {
    const val = values[i];
    const ratio = val / maxVal;
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [a.longitude, a.latitude] },
      properties: {
        name: a.name,
        country: a.country,
        water_consumption: a.water_consumption,
        co2_emissions: a.co2_emissions,
        waste_generated: a.waste_generated,
        near_sensitive_zone: a.near_sensitive_zone,
        sensitive_zone_type: a.sensitive_zone_type,
        impactName: impact.name,
        impactValue: val,
        radius: 6 + 18 * ratio,
        color: LE_BAND_COLORS[leBand(ratio)],
      },
    };
  });
  return { type: 'FeatureCollection', features: features };
}

function leSyncMapData() {
  const map = LE_STATE.map;
  const geojson = leBuildGeojson();
  if (!map) return;
  const src = map.getSource('le-assets');
  if (src) {
    src.setData(geojson);
  } else {
    window._lePending = geojson;
  }
}

// ── Bascule de fond de carte (aligné sur leap_locate.js) ────────────────────
function leInitStyleToggle() {
  document.querySelectorAll('.map-layer-btn[data-layer]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.map-layer-btn[data-layer]').forEach((b) => b.classList.remove('map-layer-btn--active'));
      btn.classList.add('map-layer-btn--active');
      const map = LE_STATE.map;
      if (!map) return;
      leApplyStyle(map, mapStyleFor(btn.dataset.layer));
    });
  });
}

// Rejoue un fond puis reconstruit nos sources/couches custom sur le nouveau
// style (replayMapStyle, main.js).
function leApplyStyle(map, style) {
  replayMapStyle(map, style, () => {
    leAddSourceAndLayer(map);
    leSyncMapData();
  });
}

// Le fond suit le theme : meme bouton actif, variante claire ou sombre.
document.addEventListener('themechange', () => {
  if (LE_STATE.map) leApplyStyle(LE_STATE.map, mapStyleFor(activeMapStyleName()));
});
