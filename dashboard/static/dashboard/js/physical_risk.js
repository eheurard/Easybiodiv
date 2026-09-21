const PR_COMPANY_KEY = 'selected-company-id'; // shared localStorage slot across risk pages

const PR_STATE = {
  data: null,
  selectedKey: null,
  horizon: 5,
  map: null,
};

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl || !document.getElementById('pr-map')) return;

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


// ── Combobox (composant partagé company_combobox.js) ───────────────────────
function prInitCombobox(companies, initialData) {
  CompanyCombobox.init({
    root: document.getElementById('company-combobox'),
    companies,
    selected: initialData,
    onSelect: (id) => {
      fetch(PHYSICAL_RISK_API_URL.replace('/0/', '/' + id + '/'))
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .then(data => prRender(data))
        .catch(err => console.error('physical_risk fetch failed:', err));
    },
  });
}


// ── Horizon toggle (5 / 10 years) ──────────────────────────────────────────
function prInitHorizon() {
  PhysicalRiskView.bindHorizon(document.querySelector('.pr-horizon'), (years) => {
    PR_STATE.horizon = years;
    PhysicalRiskView.renderLoss(PR_STATE.data, PR_STATE.horizon);
  });
}


// ── Top-level render ───────────────────────────────────────────────────────
// KPI, classement, tableau, geojson et popup vivent dans physical_risk_view.js,
// partagé avec la Vue d'ensemble.
function prRender(data) {
  PR_STATE.data = data;
  PR_STATE.selectedKey = data.hazards && data.hazards.length ? data.hazards[0].key : null;
  PhysicalRiskView.renderKpis(data, PR_STATE.horizon);
  PhysicalRiskView.renderRanking(data, PR_STATE.selectedKey, prSelectHazard);
  prSyncMapData();
  PhysicalRiskView.renderTable(data, PR_STATE.selectedKey);
}

// Le classement sert de sélecteur d'aléa : carte et tableau suivent.
function prSelectHazard(key) {
  PR_STATE.selectedKey = key;
  PhysicalRiskView.markSelected(key);
  prSyncMapData();
  PhysicalRiskView.renderTable(PR_STATE.data, key);
}


// ── Map ────────────────────────────────────────────────────────────────────
function prInitMap() {
  const container = document.getElementById('pr-map');
  if (!container || typeof maplibregl === 'undefined') return null;

  const map = new maplibregl.Map({
    container: 'pr-map',
    style: mapStyleFor('classic'),
    center: [0, 20],
    zoom: 1.5,
  });

  map.on('load', () => {
    prAddSourceAndLayer(map);

    map.on('click', 'pr-assets-layer', (e) => {
      new maplibregl.Popup()
        .setLngLat(e.lngLat)
        .setHTML(PhysicalRiskView.popupHtml(e.features[0].properties))
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


// Source et couche des actifs. Idempotent : appele au chargement, puis apres
// chaque setStyle, qui les detruit. Les ecouteurs de clic/survol sont poses
// une seule fois dans prInitMap et survivent au changement de style.
function prAddSourceAndLayer(map) {
  if (!map.getSource('pr-assets')) {
    map.addSource('pr-assets', { type: 'geojson', data: prBuildGeojson() });
  }
  if (!map.getLayer('pr-assets-layer')) {
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
  }
}


// Le fond suit le theme : on reconstruit la source et la couche sur le nouveau
// style (replayMapStyle, main.js), puis on y repousse les donnees.
document.addEventListener('themechange', () => {
  const map = PR_STATE.map;
  if (!map) return;
  replayMapStyle(map, mapStyleFor('classic'), () => {
    prAddSourceAndLayer(map);
    // Repousser explicitement : juste apres un changement de style,
    // map.loaded() peut encore etre faux et prSyncMapData mettrait les donnees
    // en attente dans _prPendingGeojson sans que rien ne les reprenne.
    const src = map.getSource('pr-assets');
    if (src) src.setData(prBuildGeojson());
  });
});

function prBuildGeojson() {
  return PhysicalRiskView.buildGeojson(PR_STATE.data, PR_STATE.selectedKey);
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
