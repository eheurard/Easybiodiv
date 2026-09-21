const LL_COMPANY_KEY = 'selected-company-id'; // partagé entre pages risques

const LL_STATE = {
  data: null,
  map: null,
  supply: null,        // instance SupplyChain (courbes, flèches, fournisseurs)
  assetsBound: false,  // évènements de la couche assets déjà liés ?
};

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
  CompanyCombobox.init({
    root: document.getElementById('company-combobox'),
    companies,
    selected: initialData,
    onSelect: (id) => llFetch(id),
  });
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
      const map = LL_STATE.map;
      if (!map) return;
      llApplyStyle(map, mapStyleFor(btn.dataset.layer));
    });
  });
}

// Rejoue un fond de carte puis reconstruit toutes nos couches sur le nouveau
// style (replayMapStyle, main.js). Partagé entre le sélecteur de fond et la
// bascule jour/nuit. L'animation des flèches est suspendue le temps du
// chargement.
function llApplyStyle(map, style) {
  const supply = LL_STATE.supply;
  if (supply) supply.stop();
  replayMapStyle(map, style, () => {
    llAddSourceAndLayer(map);
    llSyncMapData();           // repeupler les assets avant les fournisseurs
    if (supply) {
      supply.addLayers('ll-assets-layer');
      supply.resume();
    }
  });
}

// Le fond suit le theme : meme bouton actif, variante claire ou sombre.
document.addEventListener('themechange', () => {
  if (LL_STATE.map) llApplyStyle(LL_STATE.map, mapStyleFor(activeMapStyleName()));
});

function llFeatures() {
  return (LL_STATE.data && LL_STATE.data.geojson) ? LL_STATE.data.geojson.features : [];
}

// Marqueurs colorés et dimensionnés par revenu associé (relatif au max courant).
function llStyledFeatures() {
  return LocateView.styleFeatures(llFeatures());
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
    new maplibregl.Popup({ maxWidth: '280px' })
      .setLngLat(e.lngLat)
      .setHTML(LocateView.popupHtml(e.features[0].properties))
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
    style: mapStyleFor('classic'),
    center: [0, 20],
    zoom: 1.5,
  });
  LL_STATE.supply = SupplyChain.create(map, {
    legend: {
      box: document.getElementById('ll-commodity-legend'),
      list: document.getElementById('ll-commodity-legend-list'),
    },
  });
  map.on('load', () => {
    llAddSourceAndLayer(map);
    LL_STATE.supply.addLayers('ll-assets-layer');
    if (window._llPending) { map.getSource('ll-assets').setData(window._llPending); window._llPending = null; }
    LL_STATE.supply.resume();
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
  if (LL_STATE.supply) LL_STATE.supply.setData(data);
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
  el.innerHTML = LocateView.listHtml(features);

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

// Bascule « Supply chain » : l'état du bouton est géré ici, les couches et la
// légende par l'instance SupplyChain.
function llInitSupplierToggle() {
  const btn = document.getElementById('ll-supplier-toggle');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const supply = LL_STATE.supply;
    if (!supply) return;
    const visible = !supply.isVisible();
    supply.setVisible(visible);
    btn.classList.toggle('map-layer-btn--active', visible);
    btn.setAttribute('aria-pressed', String(visible));
  });
}
