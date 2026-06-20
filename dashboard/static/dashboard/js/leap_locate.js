const LL_COMPANY_KEY = 'selected-company-id'; // partagé entre pages risques

const LL_STATE = {
  data: null,
  map: null,
  suppliersVisible: false, // état de la bascule "Fournisseurs"
  supplierLinks: [],       // courbes de Bézier mises en cache pour l'animation
  animFrame: null,         // id requestAnimationFrame de l'animation des flèches
  bound: false,            // évènements fournisseurs déjà liés à la carte ?
};

const LL_SUPPLIER_COLOR = '#1f6f5c'; // teal, couleur par défaut / repli

// Palette catégorielle pour distinguer les commodités sur les flèches/courbes.
const LL_COMMODITY_PALETTE = [
  '#1f6f5c', '#c2603f', '#e0a83c', '#4f7cac', '#8a5a9e',
  '#6b8f3d', '#cf5d8a', '#3d9fa3', '#b5793b', '#7a6cc4',
];

// Nom d'image MapLibre déterministe pour une couleur donnée.
function llArrowImageName(color) { return 'll-arrow-' + color.replace('#', ''); }

// Construit la table commodité -> couleur (ordre alphabétique = stable).
function llBuildCommodityColors() {
  const links = (LL_STATE.data && LL_STATE.data.supplier_links
    && LL_STATE.data.supplier_links.features) || [];
  const names = Array.from(
    new Set(links.map(f => f.properties && f.properties.commodity).filter(Boolean))
  ).sort();
  const map = {};
  names.forEach((n, i) => { map[n] = LL_COMMODITY_PALETTE[i % LL_COMMODITY_PALETTE.length]; });
  return map;
}

// Échelle séquentielle (clair → foncé) utilisée pour le revenu associé.
const LL_REVENUE_COLORS = {
  Low:      '#dac1ba',
  Moderate: '#feb87c',
  High:     '#af5d43',
  VeryHigh: '#91452d',
};

function llRevenueBand(ratio) {
  if (ratio >= 0.66) return 'VeryHigh';
  if (ratio >= 0.33) return 'High';
  if (ratio > 0)     return 'Moderate';
  return 'Low';
}

function llEuro(v) { return fmtEuro(Math.round(Number(v) || 0)); }

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl || !document.getElementById('leap-locate-map')) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  LL_STATE.map = llInitMap();
  llInitStyleToggle();
  llInitPanelToggle();
  llInitSupplierToggle();

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

function llInitPanelToggle() {
  const wrap   = document.querySelector('.ll-map-wrap');
  const toggle = document.getElementById('ll-panel-toggle');
  const reopen = document.getElementById('ll-panel-reopen');
  if (!wrap || !toggle || !reopen) return;

  function setCollapsed(collapsed) {
    wrap.classList.toggle('ll-collapsed', collapsed);
    toggle.setAttribute('aria-expanded', String(!collapsed));
    reopen.setAttribute('aria-expanded', String(!collapsed));
  }

  toggle.addEventListener('click', () => setCollapsed(true));
  reopen.addEventListener('click', () => setCollapsed(false));
}

function llInitStyleToggle() {
  // Cibler uniquement les boutons de fond de carte (data-layer) : la bascule
  // "Fournisseurs" partage la classe .map-layer-btn mais ne doit PAS déclencher
  // un setStyle (qui détruirait toutes les couches).
  document.querySelectorAll('.map-layer-btn[data-layer]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.map-layer-btn[data-layer]').forEach((b) => b.classList.remove('map-layer-btn--active'));
      btn.classList.add('map-layer-btn--active');
      const style = MAP_STYLES[btn.dataset.layer] || MAP_STYLES.classic;
      const map = LL_STATE.map;
      if (!map) return;
      // isStyleLoaded() n'est pas fiable juste après setStyle : pour un style
      // chargé par URL (classique/gris) il renvoie encore « true » pour
      // l'ANCIEN style, puis le nouveau style se charge et efface nos sources.
      // « idle » est le seul signal fiable (nouveau style + tuiles prêts), mais
      // il ne se déclenche jamais tant que l'animation des flèches tourne : on
      // la stoppe le temps du rechargement, puis on reconstruit et on relance.
      const wasAnimating = LL_STATE.suppliersVisible;
      llStopArrowAnim();
      map.setStyle(style);
      map.once('idle', () => {
        llAddSourceAndLayer(map);
        llSyncMapData();           // repeupler les assets avant les fournisseurs
        llAddSupplierLayers(map);
        llSyncSupplierData();
        if (wasAnimating) llStartArrowAnim();
      });
    });
  });
}

function llFeatures() {
  return (LL_STATE.data && LL_STATE.data.geojson) ? LL_STATE.data.geojson.features : [];
}

// Marqueurs colorés et dimensionnés par revenu associé (relatif au max courant).
function llStyledFeatures() {
  const all = llFeatures();
  const maxRev = all.reduce((m, f) => Math.max(m, f.properties.revenue_total || 0), 0) || 1;
  return all.map(f => {
    const ratio = (f.properties.revenue_total || 0) / maxRev;
    return {
      type: 'Feature',
      geometry: f.geometry,
      properties: Object.assign({}, f.properties, {
        color: LL_REVENUE_COLORS[llRevenueBand(ratio)],
        radius: 6 + 18 * ratio,
      }),
    };
  });
}

function llProdLine(p) {
  const qty = `${fmtNum(p.quantity)} ${escHtml(p.unit)}`;
  return `<span class="ll-prod"><span class="ll-prod__name">${escHtml(p.commodity)}</span>`
    + `<span class="ll-prod__qty">${qty}</span></span>`;
}

function llAddSourceAndLayer(map) {
  // Idempotent : selon le style, setStyle peut conserver (diff) ou détruire les
  // sources custom. On ne (re)crée que ce qui manque, et on ne lie les
  // évènements qu'une seule fois.
  if (!map.getSource('ll-assets')) {
    map.addSource('ll-assets', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  }
  if (!map.getLayer('ll-assets-layer')) {
    map.addLayer({
      id: 'll-assets-layer',
      type: 'circle',
      source: 'll-assets',
      paint: {
        'circle-radius': ['get', 'radius'],
        'circle-color': ['get', 'color'],
        'circle-opacity': 0.8,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff',
      },
    });
  }
  if (LL_STATE.assetsBound) return;
  LL_STATE.assetsBound = true;
  map.on('click', 'll-assets-layer', (e) => {
    const p = e.features[0].properties;
    // Sur une source GeoJSON, MapLibre sérialise les propriétés non primitives.
    let prods = p.productions;
    if (typeof prods === 'string') { try { prods = JSON.parse(prods); } catch (_) { prods = []; } }
    prods = prods || [];
    const meta = [p.country, p.region].filter(Boolean).map(escHtml).join(' · ');
    const type = p.asset_type ? `<div class="ll-popup__row">Type : ${escHtml(p.asset_type)}</div>` : '';
    const own  = p.ownership ? `<div class="ll-popup__row">Détention : ${escHtml(p.ownership)}</div>` : '';
    const prodHtml = prods.length
      ? `<div class="ll-popup__prods">${prods.map(llProdLine).join('')}</div>`
      : '<div class="ll-popup__row">Aucune production</div>';
    new maplibregl.Popup({ maxWidth: '280px' })
      .setLngLat(e.lngLat)
      .setHTML(
        `<div class="ll-popup"><strong>${escHtml(p.name)}</strong>` +
        `<div class="ll-popup__meta">${meta}</div>${type}${own}${prodHtml}` +
        `<div class="ll-popup__revenue">Revenu associé : ${llEuro(p.revenue_total)}</div></div>`
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
    llAddSupplierLayers(map);
    llBindSupplierEvents(map);
    if (window._llPending) { map.getSource('ll-assets').setData(window._llPending); window._llPending = null; }
    llSyncSupplierData();
    if (LL_STATE.suppliersVisible) llStartArrowAnim();
  });
  return map;
}

function llSyncMapData() {
  const map = LL_STATE.map;
  const geojson = { type: 'FeatureCollection', features: llStyledFeatures() };
  if (!map) return;
  // Dès que la source existe on pousse les données : map.loaded() est faux juste
  // après un setStyle (tuiles en cours), ce qui mettait les assets en attente
  // indéfiniment et vidait la carte. La source suffit pour setData().
  const src = map.getSource('ll-assets');
  if (src) {
    src.setData(geojson);
  } else {
    window._llPending = geojson;
  }
}

function llRender(data) {
  LL_STATE.data = data;
  llSyncMapData();
  llSyncSupplierData();
  llRenderList();
}

function llRenderList() {
  const el = document.getElementById('leap-locate-list');
  if (!el) return;
  const features = llFeatures();
  if (features.length === 0) {
    el.innerHTML = '<p class="ll-empty">Aucun site.</p>';
    return;
  }
  el.innerHTML = features.map(f => {
    const p = f.properties;
    const [lng, lat] = f.geometry.coordinates;
    const badge = p.asset_type ? `<span class="ll-item__badge">${escHtml(p.asset_type)}</span>` : '';
    const own = p.ownership
      ? `<div class="ll-item__meta">Détention : <strong>${escHtml(p.ownership)}</strong></div>` : '';
    const prods = (p.productions || []);
    const prodHtml = prods.length
      ? `<div class="ll-item__prods">${prods.map(llProdLine).join('')}</div>` : '';
    return `
      <div class="ll-item ll-item--clickable" data-lng="${lng}" data-lat="${lat}">
        <div class="ll-item__top">
          <span class="ll-item__name">${escHtml(p.name)}</span>
          ${badge}
        </div>
        ${own}
        ${prodHtml}
        <div class="ll-item__revenue">Revenu associé&nbsp;: <strong>${llEuro(p.revenue_total)}</strong></div>
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

/* ───────────────────────── Fournisseurs ──────────────────────────────────
 * Chaque lien fournisseur → asset est dessiné comme une courbe de Bézier
 * quadratique. De petites flèches glissent le long de la courbe (du
 * fournisseur vers l'asset) via une boucle requestAnimationFrame qui met à
 * jour une source GeoJSON de points orientés.
 * ------------------------------------------------------------------------ */

const LL_ARROWS_PER_LINK = 4; // nombre de flèches simultanées sur chaque courbe
const LL_ARROW_SPEED = 0.006; // progression de la phase par frame (boucle 0→1)
const LL_CURVE_BOW = 0.18;    // amplitude de la courbure (0 = ligne droite)
const LL_CURVE_SAMPLES = 48;  // points échantillonnés pour tracer la courbe

// Point de contrôle : milieu décalé perpendiculairement au segment.
function llControl(p0, p1) {
  const mx = (p0[0] + p1[0]) / 2;
  const my = (p0[1] + p1[1]) / 2;
  const dx = p1[0] - p0[0];
  const dy = p1[1] - p0[1];
  // Vecteur perpendiculaire (-dy, dx) → courbure constante du même côté.
  return [mx - dy * LL_CURVE_BOW, my + dx * LL_CURVE_BOW];
}

function llBez(p0, c, p1, t) {
  const u = 1 - t;
  return [
    u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
    u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1],
  ];
}

function llBezTangent(p0, c, p1, t) {
  const u = 1 - t;
  return [
    2 * u * (c[0] - p0[0]) + 2 * t * (p1[0] - c[0]),
    2 * u * (c[1] - p0[1]) + 2 * t * (p1[1] - c[1]),
  ];
}

// Cap (degrés, sens horaire depuis le nord) pour orienter l'icône flèche.
function llBearing(tan, lat) {
  const dx = tan[0] * Math.cos(lat * Math.PI / 180); // compression des longitudes
  const dy = tan[1];
  return Math.atan2(dx, dy) * 180 / Math.PI;
}

// Icône flèche dessinée sur un canvas, pointant vers le haut (= nord).
function llArrowImage(color) {
  const size = 18;
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const ctx = c.getContext('2d');
  ctx.fillStyle = color || LL_SUPPLIER_COLOR;
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
  ctx.lineWidth = 1.3;
  ctx.beginPath();
  ctx.moveTo(size / 2, 2);          // pointe (haut)
  ctx.lineTo(size - 3, size - 4);   // aile droite
  ctx.lineTo(size / 2, size - 7);   // encoche
  ctx.lineTo(3, size - 4);          // aile gauche
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  return ctx.getImageData(0, 0, size, size);
}

// (Ré)enregistre une icône flèche par couleur de commodité + l'icône par défaut.
function llEnsureArrowImages(map, colorMap) {
  const colors = new Set(Object.values(colorMap || {}));
  colors.add(LL_SUPPLIER_COLOR);
  colors.forEach((col) => {
    const name = llArrowImageName(col);
    if (!map.hasImage(name)) map.addImage(name, llArrowImage(col));
  });
}

function llAddSupplierLayers(map) {
  if (!map.hasImage('ll-arrow')) map.addImage('ll-arrow', llArrowImage(LL_SUPPLIER_COLOR));
  llEnsureArrowImages(map, LL_STATE.commodityColors);
  const vis = LL_STATE.suppliersVisible ? 'visible' : 'none';
  const empty = { type: 'FeatureCollection', features: [] };

  if (!map.getSource('ll-supplier-lines')) {
    map.addSource('ll-supplier-lines', { type: 'geojson', data: empty });
  }
  if (!map.getSource('ll-supplier-arrows')) {
    map.addSource('ll-supplier-arrows', { type: 'geojson', data: empty });
  }
  if (!map.getSource('ll-suppliers')) {
    map.addSource('ll-suppliers', { type: 'geojson', data: empty });
  }

  // Les courbes passent sous les marqueurs d'assets ; flèches et points au-dessus.
  const belowAssets = map.getLayer('ll-assets-layer') ? 'll-assets-layer' : undefined;
  if (!map.getLayer('ll-supplier-lines-layer')) {
    map.addLayer({
      id: 'll-supplier-lines-layer',
      type: 'line',
      source: 'll-supplier-lines',
      layout: { 'line-cap': 'round', 'line-join': 'round', visibility: vis },
      paint: {
        'line-color': ['coalesce', ['get', 'color'], LL_SUPPLIER_COLOR],
        'line-width': 1.6,
        'line-opacity': 0.4,
        'line-dasharray': [2, 2],
      },
    }, belowAssets);
  }
  if (!map.getLayer('ll-supplier-arrows-layer')) {
    map.addLayer({
      id: 'll-supplier-arrows-layer',
      type: 'symbol',
      source: 'll-supplier-arrows',
      layout: {
        'icon-image': ['coalesce', ['get', 'icon'], 'll-arrow'],
        'icon-size': 0.85,
        'icon-rotate': ['get', 'bearing'],
        'icon-rotation-alignment': 'map',
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
        visibility: vis,
      },
    });
  }
  if (!map.getLayer('ll-suppliers-layer')) {
    map.addLayer({
      id: 'll-suppliers-layer',
      type: 'circle',
      source: 'll-suppliers',
      layout: { visibility: vis },
      paint: {
        'circle-radius': 5.5,
        'circle-color': LL_SUPPLIER_COLOR,
        'circle-opacity': 0.9,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff',
      },
    });
  }
}

function llBindSupplierEvents(map) {
  if (LL_STATE.bound) return;
  LL_STATE.bound = true;
  map.on('click', 'll-suppliers-layer', (e) => {
    const p = e.features[0].properties;
    let comms = p.commodities;
    if (typeof comms === 'string') { try { comms = JSON.parse(comms); } catch (_) { comms = []; } }
    comms = comms || [];
    const list = comms.length
      ? `<div class="ll-popup__prods">${comms.map(c =>
          `<span class="ll-prod"><span class="ll-prod__name">${escHtml(c)}</span></span>`).join('')}</div>`
      : '';
    new maplibregl.Popup({ maxWidth: '260px' })
      .setLngLat(e.lngLat)
      .setHTML(
        `<div class="ll-popup"><strong>${escHtml(p.name)}</strong>` +
        `<div class="ll-popup__meta">${escHtml(p.country || '')}</div>` +
        `<div class="ll-popup__row">Fournisseur</div>${list}</div>`
      )
      .addTo(map);
  });
  map.on('mouseenter', 'll-suppliers-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'll-suppliers-layer', () => { map.getCanvas().style.cursor = ''; });
}

// Recalcule courbes + points fournisseurs depuis LL_STATE.data.
function llSyncSupplierData() {
  const map = LL_STATE.map;
  const data = LL_STATE.data;
  if (!map) return;

  LL_STATE.commodityColors = llBuildCommodityColors();
  llEnsureArrowImages(map, LL_STATE.commodityColors);

  const linkFeats = (data && data.supplier_links && data.supplier_links.features) || [];
  const links = [];
  const lineFeats = [];
  linkFeats.forEach(f => {
    const [p0, p1] = f.geometry.coordinates;
    const c = llControl(p0, p1);
    const commodity = f.properties && f.properties.commodity;
    const color = LL_STATE.commodityColors[commodity] || LL_SUPPLIER_COLOR;
    links.push({ p0: p0, c: c, p1: p1, icon: llArrowImageName(color) });
    const pts = [];
    for (let i = 0; i <= LL_CURVE_SAMPLES; i++) pts.push(llBez(p0, c, p1, i / LL_CURVE_SAMPLES));
    lineFeats.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: pts },
      properties: { color: color },
    });
  });
  LL_STATE.supplierLinks = links;
  llRenderCommodityLegend();

  if (map.getSource('ll-supplier-lines')) {
    map.getSource('ll-supplier-lines').setData({ type: 'FeatureCollection', features: lineFeats });
  }
  const supFeats = (data && data.suppliers && data.suppliers.features) || [];
  if (map.getSource('ll-suppliers')) {
    map.getSource('ll-suppliers').setData({ type: 'FeatureCollection', features: supFeats });
  }
  // Si l'animation tourne mais qu'il n'y a plus de lien, la source se vide.
  if (LL_STATE.suppliersVisible) llUpdateArrows(LL_STATE.animPhase || 0);
}

function llUpdateArrows(phase) {
  const map = LL_STATE.map;
  if (!map) return;
  const src = map.getSource('ll-supplier-arrows');
  if (!src) return;
  const feats = [];
  LL_STATE.supplierLinks.forEach(l => {
    for (let k = 0; k < LL_ARROWS_PER_LINK; k++) {
      const t = (phase + k / LL_ARROWS_PER_LINK) % 1;
      const pos = llBez(l.p0, l.c, l.p1, t);
      const tan = llBezTangent(l.p0, l.c, l.p1, t);
      feats.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: pos },
        properties: { bearing: llBearing(tan, pos[1]), icon: l.icon },
      });
    }
  });
  src.setData({ type: 'FeatureCollection', features: feats });
}

function llStartArrowAnim() {
  if (LL_STATE.animFrame) return;
  const step = () => {
    LL_STATE.animPhase = ((LL_STATE.animPhase || 0) + LL_ARROW_SPEED) % 1;
    llUpdateArrows(LL_STATE.animPhase);
    LL_STATE.animFrame = requestAnimationFrame(step);
  };
  LL_STATE.animFrame = requestAnimationFrame(step);
}

function llStopArrowAnim() {
  if (LL_STATE.animFrame) cancelAnimationFrame(LL_STATE.animFrame);
  LL_STATE.animFrame = null;
}

function llSetSuppliersVisible(visible) {
  LL_STATE.suppliersVisible = visible;
  const btn = document.getElementById('ll-supplier-toggle');
  if (btn) {
    btn.classList.toggle('map-layer-btn--active', visible);
    btn.setAttribute('aria-pressed', String(visible));
  }
  const map = LL_STATE.map;
  if (!map) return;
  const vis = visible ? 'visible' : 'none';
  ['ll-supplier-lines-layer', 'll-supplier-arrows-layer', 'll-suppliers-layer'].forEach(id => {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis);
  });
  llRenderCommodityLegend();
  if (visible) llStartArrowAnim(); else llStopArrowAnim();
}

// Légende des couleurs de commodités, visible uniquement avec les fournisseurs.
function llRenderCommodityLegend() {
  const box  = document.getElementById('ll-commodity-legend');
  const list = document.getElementById('ll-commodity-legend-list');
  if (!box || !list) return;
  const colors = LL_STATE.commodityColors || {};
  const names = Object.keys(colors);
  if (!names.length) { box.hidden = true; list.innerHTML = ''; return; }
  list.innerHTML = names.map(n =>
    `<li><span class="map-legend__dot" style="background:${colors[n]}"></span>${escHtml(n)}</li>`
  ).join('');
  box.hidden = !LL_STATE.suppliersVisible;
}

function llInitSupplierToggle() {
  const btn = document.getElementById('ll-supplier-toggle');
  if (!btn) return;
  btn.addEventListener('click', () => llSetSuppliersVisible(!LL_STATE.suppliersVisible));
}
