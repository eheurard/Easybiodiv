'use strict';

// Comparaison d'une surface avec une ville : deux cercles concentriques sur
// le centre de la ville choisie, sur fond satellite. L'un a l'aire de la
// surface comparée (rempli), l'autre celle de la ville (pointillé), pour
// l'échelle. La forme réelle des territoires n'est pas représentée.
//
// Composant partagé (gabarit dashboard/_city_compare.html) : onglet Land use
// de la page ESG et onglet Impact de Portfolio analysis. Usage :
//   const cc = CityCompare.create(rootEl, { fill: '#6B7B3A', line: '#dfe8b8' });
//   cc.setMeasures([{ key, label, m2 }], 'cléPréférée');
//   cc.show();   // à l'affichage de l'onglet : une carte MapLibre créée dans
//                // un conteneur masqué n'a pas de taille.
// Le fond satellite est identique dans les deux thèmes : pas de rejeu au
// changement de thème. Dépend de main.js (escHtml, APP_LOCALE, mapStyleFor).
window.CityCompare = (function () {
  // Superficie administrative (km²) et centre-ville. Ordre d'affichage.
  const CITIES = [
    { key: 'paris', name: gettext('Paris'), lat: 48.8566, lng: 2.3522, areaKm2: 105.4 },
    { key: 'lyon', name: gettext('Lyon'), lat: 45.7640, lng: 4.8357, areaKm2: 47.87 },
    { key: 'marseille', name: gettext('Marseille'), lat: 43.2965, lng: 5.3698, areaKm2: 240.6 },
    { key: 'toulouse', name: gettext('Toulouse'), lat: 43.6047, lng: 1.4442, areaKm2: 118.3 },
    { key: 'bordeaux', name: gettext('Bordeaux'), lat: 44.8378, lng: -0.5792, areaKm2: 49.36 },
    { key: 'nantes', name: gettext('Nantes'), lat: 47.2184, lng: -1.5536, areaKm2: 65.19 },
    { key: 'lille', name: gettext('Lille'), lat: 50.6292, lng: 3.0573, areaKm2: 34.51 },
    { key: 'brussels', name: gettext('Bruxelles (Région capitale)'), lat: 50.8467, lng: 4.3525, areaKm2: 161.4 },
    { key: 'geneva', name: gettext('Genève'), lat: 46.2044, lng: 6.1432, areaKm2: 15.93 },
    { key: 'london', name: gettext('Londres (Grand Londres)'), lat: 51.5074, lng: -0.1278, areaKm2: 1572 },
    { key: 'berlin', name: gettext('Berlin'), lat: 52.5200, lng: 13.4050, areaKm2: 891.1 },
    { key: 'madrid', name: gettext('Madrid'), lat: 40.4168, lng: -3.7038, areaKm2: 604.3 },
    { key: 'rome', name: gettext('Rome'), lat: 41.9028, lng: 12.4964, areaKm2: 1287.4 },
    { key: 'new-york', name: gettext('New York'), lat: 40.7128, lng: -74.0060, areaKm2: 783.8 },
    { key: 'montreal', name: gettext('Montréal'), lat: 45.5019, lng: -73.5674, areaKm2: 365.1 },
    { key: 'sao-paulo', name: gettext('São Paulo'), lat: -23.5505, lng: -46.6333, areaKm2: 1521.1 },
    { key: 'santiago', name: gettext('Santiago du Chili (commune)'), lat: -33.4489, lng: -70.6693, areaKm2: 22.4 },
    { key: 'sydney', name: gettext('Sydney (City of Sydney)'), lat: -33.8688, lng: 151.2093, areaKm2: 26.15 },
    { key: 'tokyo', name: gettext('Tokyo (23 arrondissements)'), lat: 35.6812, lng: 139.7671, areaKm2: 627.6 },
    { key: 'singapore', name: gettext('Singapour'), lat: 1.3521, lng: 103.8198, areaKm2: 735.2 },
  ];
  // Choix de ville partagé entre les pages (préférence de l'utilisateur).
  const STORAGE_KEY = 'esg-city-compare';
  const CITY_LINE = '#ffffff';
  const M2_PER_KM2 = 1e6;

  function savedCity() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      if (CITIES.some(c => c.key === saved.city)) return saved.city;
    } catch (e) { /* stockage indisponible */ }
    return 'paris';
  }

  function saveCity(key) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ city: key })); } catch (e) { /* ignoré */ }
  }

  function fmt(value, digits) {
    return value.toLocaleString(APP_LOCALE, { maximumFractionDigits: digits });
  }

  function fmtArea(m2) {
    if (m2 >= M2_PER_KM2) {
      const km2 = m2 / M2_PER_KM2;
      return fmt(km2, km2 >= 100 ? 0 : km2 >= 10 ? 1 : 2) + ' km²';
    }
    if (m2 >= 1e4) return fmt(m2 / 1e4, 0) + ' ha';
    return fmt(m2, 0) + ' m²';
  }

  function radiusMeters(m2) { return Math.sqrt(m2 / Math.PI); }

  function fmtLength(meters) {
    return meters >= 1000 ? fmt(meters / 1000, 1) + ' km' : fmt(meters, 0) + ' m';
  }

  // Pourcentage lisible même pour une surface minuscule face à la ville.
  function fmtPct(pct) {
    return pct >= 1
      ? fmt(pct, pct >= 10 ? 0 : 1)
      : pct.toLocaleString(APP_LOCALE, { maximumSignificantDigits: 2 });
  }

  // Polygone d'un cercle géographique (approximation locale, suffisante pour
  // des rayons de quelques centaines de kilomètres).
  function circle(lat, lng, radius) {
    const coords = [];
    const latRad = lat * Math.PI / 180;
    for (let i = 0; i <= 96; i++) {
      const theta = (i / 96) * 2 * Math.PI;
      coords.push([
        lng + (radius * Math.sin(theta)) / (111320 * Math.cos(latRad)),
        lat + (radius * Math.cos(theta)) / 110540,
      ]);
    }
    return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] }, properties: {} };
  }

  function bounds(feature) {
    const ring = feature.geometry.coordinates[0];
    const lngs = ring.map(p => p[0]);
    const lats = ring.map(p => p[1]);
    return [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]];
  }

  function create(root, options) {
    if (!root) return null;
    const opts = Object.assign({
      fill: '#6B7B3A',          // accent du sous-onglet Land use
      line: '#dfe8b8',          // même teinte, éclaircie pour l'imagerie satellite
      emptyMessage: gettext('Aucune surface à comparer.'),
    }, options || {});
    const el = name => root.querySelector('[data-cc="' + name + '"]');
    const state = { measures: [], measureKey: null, cityKey: savedCity(), map: null, ready: false };

    const city = () => CITIES.find(c => c.key === state.cityKey) || CITIES[0];
    const currentMeasure = () =>
      state.measures.find(m => m.key === state.measureKey) || state.measures[0] || null;

    // ── Contrôles ────────────────────────────────────────────────────────

    function renderSelect() {
      const select = el('select');
      if (!select || select.options.length) return;
      select.innerHTML = CITIES.map(c =>
        '<option value="' + c.key + '">' + escHtml(c.name) + '</option>').join('');
      select.value = state.cityKey;
      select.addEventListener('change', () => {
        state.cityKey = select.value;
        saveCity(state.cityKey);
        update(true);
      });
    }

    function renderMeasures() {
      const host = el('measures');
      if (!host) return;
      const current = currentMeasure();
      host.innerHTML = state.measures.length
        ? state.measures.map(m =>
            '<button type="button" class="esg-city__measure" data-measure="' + escHtml(m.key) + '"' +
            ' aria-pressed="' + (current && m.key === current.key) + '">' +
            '<span>' + escHtml(m.label) + '</span>' +
            '<span class="esg-city__measure-value">' + fmtArea(m.m2) + '</span></button>'
          ).join('')
        : '<p class="esg-city__none">' + escHtml(opts.emptyMessage) + '</p>';
      host.querySelectorAll('.esg-city__measure').forEach(btn => {
        btn.addEventListener('click', () => {
          state.measureKey = btn.dataset.measure;
          renderMeasures();
          update(true);
        });
      });
    }

    function renderFacts() {
      const facts = el('facts');
      const ratio = el('ratio');
      if (!facts || !ratio) return;
      const c = city();
      const m = currentMeasure();
      const cityM2 = c.areaKm2 * M2_PER_KM2;
      const row = (label, value) => '<dt>' + escHtml(label) + '</dt><dd>' + value + '</dd>';
      facts.innerHTML =
        row(gettext('Surface équivalente'), m ? fmtArea(m.m2) : '—') +
        row(gettext('Rayon du cercle'), m ? fmtLength(radiusMeters(m.m2)) : '—') +
        row(interpolate(gettext('Superficie de %(city)s'), { city: c.name }, true), fmtArea(cityM2));
      if (!m) {
        ratio.textContent = '';
        return;
      }
      const r = m.m2 / cityM2;
      ratio.textContent = r >= 1
        ? interpolate(gettext('≈ %(ratio)s fois la superficie de %(city)s'),
            { ratio: fmt(r, r >= 10 ? 0 : 1), city: c.name }, true)
        : interpolate(gettext('≈ %(pct)s % de la superficie de %(city)s'),
            { pct: fmtPct(r * 100), city: c.name }, true);
    }

    // ── Carte ────────────────────────────────────────────────────────────

    function addLayers() {
      const map = state.map;
      const empty = { type: 'FeatureCollection', features: [] };
      ['cc-company', 'cc-city', 'cc-center'].forEach(id => {
        if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: empty });
      });
      map.addLayer({
        id: 'cc-city-line', type: 'line', source: 'cc-city',
        paint: {
          'line-color': CITY_LINE, 'line-width': 1.5, 'line-opacity': 0.9,
          'line-dasharray': [3, 2],
        },
      });
      map.addLayer({
        id: 'cc-center-dot', type: 'circle', source: 'cc-center',
        paint: {
          'circle-radius': 4, 'circle-color': opts.fill,
          'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.5,
        },
      });
      map.addLayer({
        id: 'cc-company-fill', type: 'fill', source: 'cc-company',
        paint: { 'fill-color': opts.fill, 'fill-opacity': 0.4 },
      });
      map.addLayer({
        id: 'cc-company-line', type: 'line', source: 'cc-company',
        paint: { 'line-color': opts.line, 'line-width': 2 },
      });
    }

    function updateMap(animate) {
      const map = state.map;
      if (!map || !state.ready) return;
      const c = city();
      const m = currentMeasure();
      const cityCircle = circle(c.lat, c.lng, radiusMeters(c.areaKm2 * M2_PER_KM2));
      const companyCircle = m ? circle(c.lat, c.lng, radiusMeters(m.m2)) : null;
      map.getSource('cc-city').setData(cityCircle);
      map.getSource('cc-company').setData(
        companyCircle || { type: 'FeatureCollection', features: [] });
      map.getSource('cc-center').setData({
        type: 'Feature', geometry: { type: 'Point', coordinates: [c.lng, c.lat] }, properties: {},
      });
      // Cadrage sur le plus grand des deux cercles.
      const larger = companyCircle && m.m2 > c.areaKm2 * M2_PER_KM2 ? companyCircle : cityCircle;
      map.fitBounds(bounds(larger), { padding: 32, maxZoom: 14, duration: animate ? 700 : 0 });
    }

    function update(animate) {
      renderFacts();
      updateMap(animate);
    }

    function initMap() {
      const container = el('map');
      if (!container || typeof maplibregl === 'undefined') return;
      state.map = new maplibregl.Map({
        container: container,
        style: mapStyleFor('satellite'),
        center: [city().lng, city().lat],
        zoom: 9,
        attributionControl: { compact: true },
      });
      // La page défile : pas de zoom à la molette, boutons de zoom à la place.
      state.map.scrollZoom.disable();
      state.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
      state.map.on('load', () => {
        addLayers();
        state.ready = true;
        updateMap(false);
      });
    }

    // ── API ──────────────────────────────────────────────────────────────

    function setMeasures(measures, preferredKey) {
      state.measures = measures.filter(m => m.m2 > 0);
      if (preferredKey) state.measureKey = preferredKey;
      renderSelect();
      renderMeasures();
      update(false);
    }

    function show() {
      if (!state.map) {
        initMap();
      } else {
        state.map.resize();
        updateMap(false);
      }
    }

    return { setMeasures, show };
  }

  return { create, CITIES };
})();
