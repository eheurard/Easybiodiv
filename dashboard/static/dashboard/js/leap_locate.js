const LL_COMPANY_KEY = 'selected-company-id'; // partagé entre pages risques

const LL_STATE = { data: null, map: null, filter: 'all' };

const LL_BAND_COLORS = {
  Low:      '#dac1ba',
  Moderate: '#feb87c',
  High:     '#af5d43',
  Critical: '#91452d',
};
const LL_SENSITIVE_RING = '#3d6b4f';

function llBand(score) {
  if (score >= 0.7) return 'Critical';
  if (score >= 0.5) return 'High';
  if (score >= 0.2) return 'Moderate';
  return 'Low';
}

function llPct(v) { return (Number(v) * 100).toFixed(0) + '%'; }

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl || !document.getElementById('leap-locate-map')) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  LL_STATE.map = llInitMap();
  llInitFilters();
  llInitStyleToggle();

  const savedId = parseInt(localStorage.getItem(LL_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    llFetch(savedId).then(data => llInitCombobox(companies, data || initialData));
  } else {
    if (initialData) llRender(initialData);
    llInitCombobox(companies, initialData);
  }
});

function llFetch(id) {
  return fetch(LEAP_LOCATE_API_URL.replace('/0/', '/' + id + '/'))
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => { llRender(data); return data; })
    .catch(err => console.error('leap_locate fetch failed:', err));
}

function llInitCombobox(companies, initialData) {
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
    localStorage.setItem(LL_COMPANY_KEY, id);
    llFetch(id);
  });

  document.addEventListener('click', (e) => { if (!combobox.contains(e.target)) closeList(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeList(); });
}

function llInitFilters() {
  const group = document.querySelector('.ll-filters');
  if (!group) return;
  group.addEventListener('click', (e) => {
    const btn = e.target.closest('.leap-filter');
    if (!btn) return;
    LL_STATE.filter = btn.dataset.filter;
    group.querySelectorAll('.leap-filter').forEach(b => {
      const active = b === btn;
      b.classList.toggle('leap-filter--active', active);
      b.setAttribute('aria-pressed', String(active));
    });
    llSyncMapData();
    llRenderList();
  });
}

function llInitStyleToggle() {
  document.querySelectorAll('.map-layer-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.map-layer-btn').forEach((b) => b.classList.remove('map-layer-btn--active'));
      btn.classList.add('map-layer-btn--active');
      const style = MAP_STYLES[btn.dataset.layer] || MAP_STYLES.classic;
      const map = LL_STATE.map;
      if (!map) return;
      map.setStyle(style);
      map.once('styledata', () => {
        if (map.getSource('ll-assets')) return;
        llAddSourceAndLayer(map);
        llSyncMapData();
      });
    });
  });
}

function llFilteredFeatures() {
  const all = (LL_STATE.data && LL_STATE.data.geojson) ? LL_STATE.data.geojson.features : [];
  if (LL_STATE.filter === 'sensitive') return all.filter(f => f.properties.near_sensitive_zone);
  if (LL_STATE.filter === 'water') return all.filter(f => f.properties.risk_water >= 0.5);
  return all;
}

function llStyledFeatures() {
  return llFilteredFeatures().map(f => ({
    type: 'Feature',
    geometry: f.geometry,
    properties: Object.assign({}, f.properties, {
      color: LL_BAND_COLORS[llBand(f.properties.risk_water)],
      sensitive: !!f.properties.near_sensitive_zone,
    }),
  }));
}

function llAddSourceAndLayer(map) {
  map.addSource('ll-assets', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addLayer({
    id: 'll-assets-layer',
    type: 'circle',
    source: 'll-assets',
    paint: {
      'circle-radius': 8,
      'circle-color': ['get', 'color'],
      'circle-opacity': 0.8,
      'circle-stroke-width': ['case', ['get', 'sensitive'], 3, 1.5],
      'circle-stroke-color': ['case', ['get', 'sensitive'], LL_SENSITIVE_RING, '#ffffff'],
    },
  });
  map.on('click', 'll-assets-layer', (e) => {
    const p = e.features[0].properties;
    const meta = [p.country, p.region].filter(Boolean).map(escHtml).join(' · ');
    const zoneType = p.sensitive_zone_type || '';
    const zone = zoneType
      ? `<div class="ll-popup__zone">${escHtml(zoneType)}${p.sensitive_zone_name ? ' — ' + escHtml(p.sensitive_zone_name) : ''} (${fmtNum(p.sensitive_zone_area_ha)} ha)</div>`
      : '';
    new maplibregl.Popup({ maxWidth: '280px' })
      .setLngLat(e.lngLat)
      .setHTML(
        `<div class="ll-popup"><strong>${escHtml(p.name)}</strong><div class="ll-popup__meta">${meta}</div>${zone}` +
        `<div class="ll-popup__risk">Risque eau : ${llPct(p.risk_water)} · Stress hydrique : ${llPct(p.risk_water_stress)}</div></div>`
      )
      .addTo(map);
  });
  map.on('mouseenter', 'll-assets-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'll-assets-layer', () => { map.getCanvas().style.cursor = ''; });
}

function llInitMap() {
  const container = document.getElementById('leap-locate-map');
  if (!container || typeof maplibregl === 'undefined') return null;
  const map = new maplibregl.Map({
    container: 'leap-locate-map',
    style: MAP_STYLES.classic,
    center: [0, 20],
    zoom: 1.5,
  });
  map.on('load', () => {
    llAddSourceAndLayer(map);
    if (window._llPending) { map.getSource('ll-assets').setData(window._llPending); window._llPending = null; }
  });
  return map;
}

function llSyncMapData() {
  const map = LL_STATE.map;
  const geojson = { type: 'FeatureCollection', features: llStyledFeatures() };
  if (!map) return;
  if (map.loaded() && map.getSource('ll-assets')) {
    map.getSource('ll-assets').setData(geojson);
  } else {
    window._llPending = geojson;
  }
}

function llRender(data) {
  LL_STATE.data = data;
  llSyncMapData();
  llRenderList();
}

function llRenderList() {
  const el = document.getElementById('leap-locate-list');
  if (!el) return;
  const features = llFilteredFeatures();
  if (features.length === 0) {
    el.innerHTML = '<p class="ll-empty">Aucun site pour ce filtre.</p>';
    return;
  }
  el.innerHTML = features.map(f => {
    const p = f.properties;
    const [lng, lat] = f.geometry.coordinates;
    const badge = p.sensitive_zone_type
      ? `<span class="ll-item__badge">${escHtml(p.sensitive_zone_type)}</span>`
      : (p.near_sensitive_zone ? '<span class="ll-item__badge">Zone sensible</span>' : '');
    const area = (p.sensitive_zone_area_ha > 0)
      ? `<span class="ll-item__area">${fmtNum(p.sensitive_zone_area_ha)} ha</span>` : '';
    return `
      <div class="ll-item ll-item--clickable" data-lng="${lng}" data-lat="${lat}">
        <div class="ll-item__top">
          <span class="ll-item__name">${escHtml(p.name)}</span>
          ${badge}
        </div>
        <div class="ll-item__zone">${escHtml(p.sensitive_zone_name || '')} ${area}</div>
        <div class="ll-item__bars">
          <div class="ll-bar">
            <span class="ll-bar__label">Eau</span>
            <span class="ll-bar__track"><span class="ll-bar__fill" style="width:${llPct(p.risk_water)};background:${LL_BAND_COLORS[llBand(p.risk_water)]}"></span></span>
          </div>
          <div class="ll-bar">
            <span class="ll-bar__label">Stress</span>
            <span class="ll-bar__track"><span class="ll-bar__fill" style="width:${llPct(p.risk_water_stress)};background:${LL_BAND_COLORS[llBand(p.risk_water_stress)]}"></span></span>
          </div>
        </div>
      </div>`;
  }).join('');

  el.querySelectorAll('.ll-item--clickable').forEach(item => {
    item.addEventListener('click', () => {
      const lng = parseFloat(item.dataset.lng);
      const lat = parseFloat(item.dataset.lat);
      if (LL_STATE.map && !isNaN(lng) && !isNaN(lat)) {
        LL_STATE.map.flyTo({ center: [lng, lat], zoom: 9, duration: 1200 });
      }
    });
  });
}
