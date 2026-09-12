'use strict';

// ── Vue d'ensemble : carte multi-modes ──────────────────────────────────────
// Les boutons du panneau droit basculent la carte entre plusieurs modes. Chaque
// mode charge à la demande les données de sa page de référence (API existantes,
// URL dans OVERVIEW_API), puis rend son panneau, ses points, sa légende et son
// tiroir bas via les modules partagés. Les réponses sont gardées en cache pour
// l'entreprise courante ; changer d'entreprise vide le cache.

const SELECTED_COMPANY_KEY = 'selected-company-id'; // partagé entre pages
const OV_MODE_KEY = 'overview-mode';

// Palette catégorielle par type d'asset — teintes fixes dérivées de la charte
// Terra Insight, validées (bande de clarté OKLCH, plancher de chroma, séparation
// daltonisme protan/deutan sur toutes les paires, contraste). Ordre figé : ne pas
// réordonner ni cycler ces teintes.
const ASSET_TYPE_COLORS = {
  Smelter: '#a32c33',
  Mine: '#cf6228',
  Factory: '#d0901e',
  Paper: '#3e6200',
  Forest: '#47a566',
  Renewable: '#007149',
  Airport: '#28a0c7',
  Refinery: '#374b99',
  Aluminium: '#8d6cc2',
  Office: '#873e79',
};
const ASSET_TYPE_FALLBACK_COLOR = ASSET_TYPE_COLORS.Factory;

const OV = {
  map: null,
  companyId: null,
  mode: 'pays',
  cache: {},           // source ('company', 'locate'…) → réponse de l'API
  pending: {},         // source → requête en cours (évite les doublons)
  companyReady: null,  // promesse : données entreprise chargées et appliquées
  features: [],        // points du mode actif (source 'ov-assets')
  countryCoords: {},   // pays → somme des coordonnées de ses actifs (zoom)
  assetFilter: '',     // mode asset : type d'actif filtré ('' = tous)
  assetSortDir: 'desc',
};

// Registre des modes. source : clé de OVERVIEW_API ; drawer : tiroir bas
// ('policy' ou 'risque') ; popupHtml : null si le mode n'a pas de popup.
const OV_MODES = {
  pays: {
    title: 'Exposition par pays',
    source: 'company',
    drawer: 'policy',
    renderPanel: ovRenderCountries,
    mapFeatures: ovPaysFeatures,
    legendHtml: ovPaysLegendHtml,
    popupHtml: ovPaysPopupHtml,
  },
  asset: {
    title: 'Sites localisés',
    source: 'locate',
    drawer: 'policy',
    renderPanel: ovRenderAssetPanel,
    mapFeatures: ovAssetFeatures,
    legendHtml: () => LocateView.legendHtml(),
    popupHtml: (p) => LocateView.popupHtml(p),
  },
};

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl || !document.getElementById('overview-map')) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  ovInitMap();
  ovInitControls();

  let storedMode = null;
  try { storedMode = localStorage.getItem(OV_MODE_KEY); } catch (e) { /* stockage indisponible */ }
  OV.mode = ovValidMode(storedMode);
  ovSyncModeUi();

  const savedId = parseInt(localStorage.getItem(SELECTED_COMPANY_KEY), 10);
  const saved = savedId ? companies.find((c) => c.id === savedId) : null;

  if (saved && initialData && savedId !== initialData.company_id) {
    ovInitCombobox(companies, { company_name: saved.name });
    ovSelectCompany(savedId, null);
  } else if (initialData) {
    ovInitCombobox(companies, initialData);
    ovSelectCompany(initialData.company_id, initialData);
  } else {
    ovInitCombobox(companies, null);
    ovRenderMode();
  }
});


// ── Carte ──────────────────────────────────────────────────────────────────

function ovInitMap() {
  const map = new maplibregl.Map({
    container: 'overview-map',
    style: mapStyleFor('classic'),
    center: [0, 20],
    zoom: 1.5,
  });
  OV.map = map;

  map.on('load', () => {
    ovAddAssetsLayer();
    // Écouteurs délégués à la couche : posés une fois, ils survivent aux setStyle.
    map.on('click', 'ov-assets-layer', (e) => {
      const popupHtml = OV_MODES[OV.mode].popupHtml;
      if (!popupHtml) return;
      new maplibregl.Popup({ maxWidth: '300px' })
        .setLngLat(e.lngLat)
        .setHTML(popupHtml(e.features[0].properties))
        .addTo(map);
    });
    map.on('mouseenter', 'ov-assets-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'ov-assets-layer', () => { map.getCanvas().style.cursor = ''; });
  });
}

// Source et couche des points. Idempotent : appelé au chargement puis après
// chaque setStyle, qui peut les détruire. Couleur, rayon, opacité et contour
// sont lus dans les propriétés calculées par le mode actif.
function ovAddAssetsLayer() {
  const map = OV.map;
  if (!map.getSource('ov-assets')) {
    map.addSource('ov-assets', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: OV.features },
    });
  }
  if (!map.getLayer('ov-assets-layer')) {
    map.addLayer({
      id: 'ov-assets-layer',
      type: 'circle',
      source: 'ov-assets',
      paint: {
        'circle-radius': ['get', 'radius'],
        'circle-color': ['get', 'color'],
        'circle-opacity': ['coalesce', ['get', 'opacity'], 1],
        'circle-stroke-width': ['coalesce', ['get', 'stroke'], 1.5],
        'circle-stroke-color': '#ffffff',
      },
    });
  }
}

function ovSetMapFeatures(features) {
  OV.features = features;
  const src = OV.map && OV.map.getSource('ov-assets');
  if (src) src.setData({ type: 'FeatureCollection', features: features });
}

// Rejoue un fond (sélecteur ou bascule jour/nuit) puis reconstruit nos couches.
// « idle » est le seul signal fiable après setStyle (voir leap_locate.js).
function ovApplyStyle(styleName) {
  const map = OV.map;
  if (!map) return;
  map.setStyle(mapStyleFor(styleName));
  map.once('idle', () => {
    ovAddAssetsLayer();
  });
}

// Le fond suit le theme : meme bouton actif, variante claire ou sombre.
document.addEventListener('themechange', () => {
  if (OV.map) ovApplyStyle(activeMapStyleName());
});


// ── Contrôles ──────────────────────────────────────────────────────────────

function ovInitControls() {
  document.querySelectorAll('.ov-mode-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      // Un clic sur le mode déjà actif ne relance le chargement qu'après une erreur.
      const status = document.getElementById('ov-status');
      if (btn.dataset.mode === OV.mode && status && status.hidden) return;
      ovSetMode(btn.dataset.mode);
    });
  });

  // Fonds de carte : seulement les boutons [data-layer] (pas la supply chain).
  document.querySelectorAll('.map-layer-btn[data-layer]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.map-layer-btn[data-layer]')
        .forEach((b) => b.classList.remove('map-layer-btn--active'));
      btn.classList.add('map-layer-btn--active');
      ovApplyStyle(btn.dataset.layer);
    });
  });

  // Pays → zoom sur le barycentre de ses actifs.
  const countryList = document.getElementById('country-list');
  if (countryList) {
    countryList.addEventListener('click', (e) => {
      const item = e.target.closest('[data-country]');
      if (!item || !OV.map) return;
      const coords = OV.countryCoords[item.dataset.country];
      if (!coords) return;
      OV.map.flyTo({
        center: [coords.sumLng / coords.n, coords.sumLat / coords.n],
        zoom: 5,
        duration: 1200,
      });
    });
  }

  // Listes d'assets (modes asset et dette) → zoom sur l'asset.
  document.querySelectorAll('.ov-list').forEach((list) => {
    list.addEventListener('click', (e) => {
      const item = e.target.closest('[data-lng]');
      if (!item || !OV.map) return;
      const lng = parseFloat(item.dataset.lng);
      const lat = parseFloat(item.dataset.lat);
      if (isNaN(lng) || isNaN(lat)) return;
      OV.map.flyTo({ center: [lng, lat], zoom: 9, duration: 1200 });
    });
  });

  // Mode asset : filtre par type d'actif + tri par revenu associé.
  const filter = document.getElementById('asset-type-filter');
  if (filter) {
    filter.addEventListener('change', () => {
      OV.assetFilter = filter.value;
      ovRenderAssetList();
    });
  }
  const sortBtn = document.getElementById('asset-sort-btn');
  if (sortBtn) {
    sortBtn.addEventListener('click', () => {
      OV.assetSortDir = OV.assetSortDir === 'desc' ? 'asc' : 'desc';
      const asc = OV.assetSortDir === 'asc';
      sortBtn.setAttribute('aria-pressed', String(asc));
      document.getElementById('asset-sort-label').textContent =
        asc ? 'Revenu croissant' : 'Revenu décroissant';
      ovRenderAssetList();
    });
  }
}


// ── Modes ──────────────────────────────────────────────────────────────────

// Mode demandé s'il existe et n'est pas verrouillé, sinon « pays ».
function ovValidMode(mode) {
  if (!Object.prototype.hasOwnProperty.call(OV_MODES, mode)) return 'pays';
  const btn = document.querySelector(`.ov-mode-btn[data-mode="${mode}"]`);
  return btn && !btn.disabled ? mode : 'pays';
}

function ovSetMode(mode) {
  OV.mode = ovValidMode(mode);
  try { localStorage.setItem(OV_MODE_KEY, OV.mode); } catch (e) { /* stockage indisponible */ }
  ovSyncModeUi();
  ovRenderMode();
}

function ovSyncModeUi() {
  document.querySelectorAll('.ov-mode-btn').forEach((b) => {
    const active = b.dataset.mode === OV.mode;
    b.classList.toggle('ov-mode-btn--active', active);
    b.setAttribute('aria-pressed', String(active));
  });
  const title = document.getElementById('ov-panel-title');
  if (title) title.textContent = OV_MODES[OV.mode].title;
}

// Rend le mode actif : données (cache ou réseau), puis panneau, carte, légende
// et tiroir. Un rendu devenu obsolète (mode ou entreprise changés) est ignoré.
function ovRenderMode() {
  const mode = OV.mode;
  const cfg = OV_MODES[mode];
  if (OV.companyId == null) {
    ovShowView(mode);
    return;
  }
  if (!OV.cache.company || !OV.cache[cfg.source]) {
    ovClearModeDisplay();
    ovShowStatus('Chargement…');
  }
  Promise.all([ovCompanyReady(), ovLoad(cfg.source)])
    .then(([, data]) => { if (OV.mode === mode) ovApplyMode(mode, data); })
    .catch((err) => {
      if (err && err.kind === 'stale') return;
      console.error(`overview : chargement du mode « ${mode} » impossible`, err);
      if (OV.mode !== mode) return;
      ovShowStatus(err && err.kind === 'session'
        ? 'Session expirée — reconnectez-vous.'
        : 'Impossible de charger les données.');
    });
}

function ovApplyMode(mode, data) {
  const cfg = OV_MODES[mode];
  ovShowStatus('');
  ovShowView(mode);
  cfg.renderPanel(data);
  ovSetMapFeatures(cfg.mapFeatures(data));
  ovSetLegend(cfg.legendHtml(data));
  ovSetDrawer(cfg.drawer);
}

// Vide la carte, la légende et les tiroirs le temps d'un chargement.
function ovClearModeDisplay() {
  ovSetMapFeatures([]);
  ovSetLegend('');
  ovSetDrawer(null);
}

function ovShowStatus(message) {
  const el = document.getElementById('ov-status');
  if (!el) return;
  el.textContent = message;
  el.hidden = !message;
  if (message) {
    document.querySelectorAll('[data-view]')
      .forEach((v) => v.classList.remove('country-panel__view--active'));
  }
}

function ovShowView(mode) {
  document.querySelectorAll('[data-view]').forEach((v) => {
    v.classList.toggle('country-panel__view--active', v.dataset.view === mode);
  });
}

function ovSetLegend(html) {
  const el = document.getElementById('ov-mode-legend');
  if (!el) return;
  el.innerHTML = html;
  el.hidden = !html;
}

// Tiroir bas : « Politiques » (si l'entreprise en a) ou « Détail par actif ».
function ovSetDrawer(kind) {
  const policy = document.getElementById('policy-section');
  const detail = document.getElementById('pr-detail-section');
  const company = OV.cache.company;
  const hasPolicies = !!(company && company.policies && company.policies.length);
  if (policy) policy.hidden = !(kind === 'policy' && hasPolicies);
  if (detail) detail.hidden = kind !== 'risque';
}


// ── Données ────────────────────────────────────────────────────────────────

function ovSelectCompany(id, initialData) {
  OV.companyId = id;
  OV.cache = initialData ? { company: initialData } : {};
  OV.pending = {};
  OV.companyReady = null;
  ovRenderMode();
}

function ovError(kind) {
  const err = new Error(kind);
  err.kind = kind;
  return err;
}

// Réponse de l'API `source` pour l'entreprise courante, depuis le cache ou le
// réseau. Rejette avec kind 'stale' si l'entreprise a changé entre-temps, et
// 'session' si la réponse n'est pas du JSON (redirection vers la connexion).
function ovLoad(source) {
  if (OV.cache[source]) return Promise.resolve(OV.cache[source]);
  if (OV.pending[source]) return OV.pending[source];
  const companyId = OV.companyId;
  const url = OVERVIEW_API[source].replace('/0/', `/${companyId}/`);
  const request = fetch(url, { headers: { Accept: 'application/json' } })
    .then((r) => {
      if (r.redirected) throw ovError('session');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      if (!(r.headers.get('Content-Type') || '').includes('application/json')) {
        throw ovError('session');
      }
      return r.json();
    })
    .then((data) => {
      if (companyId !== OV.companyId) throw ovError('stale');
      OV.cache[source] = data;
      return data;
    })
    .catch((err) => {
      throw companyId !== OV.companyId ? ovError('stale') : err;
    })
    .finally(() => {
      if (OV.pending[source] === request) delete OV.pending[source];
    });
  OV.pending[source] = request;
  return request;
}

// Données entreprise chargées puis appliquées (barycentres, politiques…), une
// fois par entreprise. En cas d'échec, la promesse est oubliée : un nouveau
// rendu réessaiera.
function ovCompanyReady() {
  if (OV.companyReady) return OV.companyReady;
  const ready = ovLoad('company').then((data) => {
    ovApplyCompany(data);
    return data;
  });
  OV.companyReady = ready;
  ready.catch(() => { if (OV.companyReady === ready) OV.companyReady = null; });
  return ready;
}

function ovApplyCompany(data) {
  OV.countryCoords = {};
  ovFeatureList(data.geojson).forEach((f) => {
    const country = f.properties.country;
    const [lng, lat] = f.geometry.coordinates;
    if (!OV.countryCoords[country]) OV.countryCoords[country] = { sumLat: 0, sumLng: 0, n: 0 };
    OV.countryCoords[country].sumLat += lat;
    OV.countryCoords[country].sumLng += lng;
    OV.countryCoords[country].n += 1;
  });
  ovRenderPolicies(data);
}

function ovFeatureList(geojson) {
  return geojson && geojson.features ? geojson.features : [];
}

// Copie d'un point avec les propriétés de style lues par ov-assets-layer.
function ovStyled(feature, style) {
  return {
    type: 'Feature',
    geometry: feature.geometry,
    properties: Object.assign({}, feature.properties, style),
  };
}


// ── Mode « Exposition pays » ───────────────────────────────────────────────

function ovRenderCountries(data) {
  const list = document.getElementById('country-list');
  if (!list) return;
  if (data.countries.length === 0) {
    list.innerHTML = '<p class="country-panel__empty">Aucun actif pour cette entreprise.</p>';
    return;
  }
  list.innerHTML = data.countries
    .map((c) => {
      const hasCoords = !!OV.countryCoords[c.name];
      const tags = c.commodities
        .map((cm, i) =>
          `<span class="country-item__tag${i === 0 ? ' country-item__tag--primary' : ''}">${escHtml(cm.name)} ×${cm.count}</span>`
        )
        .join('');
      return `
        <div class="country-item${hasCoords ? ' country-item--clickable' : ''}" data-country="${escHtml(c.name)}">
          <div class="country-item__top">
            <span class="country-item__name">${escHtml(c.name)}</span>
            <span class="country-item__count">${c.asset_count} actif${c.asset_count > 1 ? 's' : ''}</span>
          </div>
          <div class="country-item__tags">${tags}</div>
        </div>`;
    })
    .join('');
}

function ovPaysFeatures(data) {
  return ovFeatureList(data.geojson).map((f) => ovStyled(f, {
    color: ASSET_TYPE_COLORS[f.properties.type] || ASSET_TYPE_FALLBACK_COLOR,
    radius: 7,
    opacity: 1,
    stroke: 2,
  }));
}

// Légende dynamique : ne liste que les types réellement présents dans les
// données affichées, dans l'ordre fixe de la palette (jamais alphabétique).
function ovPaysLegendHtml(data) {
  const present = new Set(ovFeatureList(data.geojson).map((f) => f.properties.type).filter(Boolean));
  const items = Object.keys(ASSET_TYPE_COLORS).filter((t) => present.has(t));
  if (items.length === 0) return '';
  return `
    <p class="map-legend__title">Type d'actif</p>
    <ul class="map-legend__list">
      ${items.map((t) => `
        <li>
          <span class="map-legend__dot" style="background:${ASSET_TYPE_COLORS[t]}"></span>
          <span>${escHtml(t)}</span>
        </li>
      `).join('')}
    </ul>
  `;
}

function ovPaysPopupHtml(p) {
  // Sur une source GeoJSON, MapLibre sérialise les propriétés non primitives.
  let productions = p.productions;
  if (typeof productions === 'string') {
    try { productions = JSON.parse(productions); } catch (_) { productions = []; }
  }
  productions = productions || [];

  const metaParts = [p.country, p.region].filter(Boolean);
  const yearLabel = p.year ? ` — ${p.year}` : '';

  const prodsHtml = productions.length > 0
    ? productions.map((prod) =>
        `<div class="asset-popup__prod-row">
          <span class="asset-popup__prod-dot"></span>
          <span class="asset-popup__prod-name">${escHtml(prod.commodity)}</span>
          <span class="asset-popup__prod-qty">${fmtNum(prod.quantity)}&nbsp;${escHtml(prod.unit)}</span>
        </div>`
      ).join('')
    : '<p class="asset-popup__no-data">Aucune production enregistrée</p>';

  const footprintVal = (typeof p.footprint === 'number' && p.footprint > 0)
    ? fmtFootprint(p.footprint)
    : '—';

  const detteVal = (typeof p.dette_eco === 'number' && p.dette_eco > 0)
    ? fmtEuro(p.dette_eco)
    : '—';

  return `
    <div class="asset-popup">
      <div class="asset-popup__header">
        <div class="asset-popup__name">${escHtml(p.name)}</div>
        <div class="asset-popup__meta">${metaParts.map(escHtml).join(' · ')}</div>
      </div>
      <div class="asset-popup__body">
        <div class="asset-popup__section-title">Productions${yearLabel}</div>
        ${prodsHtml}
        <div class="asset-popup__divider"></div>
        <div class="asset-popup__metrics">
          <div class="asset-popup__metric">
            <div class="asset-popup__metric-value">${footprintVal}</div>
            <div class="asset-popup__metric-label">Empreinte biodiversité</div>
          </div>
          <div class="asset-popup__metric asset-popup__metric--risk">
            <div class="asset-popup__metric-value">${detteVal}</div>
            <div class="asset-popup__metric-label">Dette écologique</div>
          </div>
        </div>
      </div>
    </div>`;
}


// ── Mode « Exposition asset » ──────────────────────────────────────────────

function ovAssetFeatures(data) {
  return LocateView.styleFeatures(ovFeatureList(data.geojson))
    .map((f) => ovStyled(f, { opacity: 0.8, stroke: 1.5 }));
}

function ovRenderAssetPanel(data) {
  ovPopulateTypeFilter(ovFeatureList(data.geojson));
  ovRenderAssetList();
}

// Types présents : d'abord dans l'ordre de la palette, puis ceux hors palette.
function ovPopulateTypeFilter(features) {
  const toolbar = document.getElementById('asset-list-toolbar');
  const select = document.getElementById('asset-type-filter');
  if (!toolbar || !select) return;
  toolbar.hidden = features.length === 0;
  if (features.length === 0) return;

  const present = new Set(features.map((f) => f.properties.type).filter(Boolean));
  const types = Object.keys(ASSET_TYPE_COLORS).filter((t) => present.has(t));
  present.forEach((t) => { if (!types.includes(t)) types.push(t); });

  if (OV.assetFilter && !present.has(OV.assetFilter)) OV.assetFilter = '';
  select.innerHTML = '<option value="">Tous les types</option>' +
    types.map((t) => `<option value="${escHtml(t)}">${escHtml(t)}</option>`).join('');
  select.value = OV.assetFilter;
}

function ovRenderAssetList() {
  const el = document.getElementById('ov-asset-list');
  const data = OV.cache.locate;
  if (!el || !data) return;

  const all = ovFeatureList(data.geojson);
  if (all.length === 0) {
    el.innerHTML = '<p class="ll-empty">Aucun site.</p>';
    return;
  }
  const features = OV.assetFilter
    ? all.filter((f) => f.properties.type === OV.assetFilter)
    : all;
  if (features.length === 0) {
    el.innerHTML = '<p class="ll-empty">Aucun actif pour ce type.</p>';
    return;
  }
  const dir = OV.assetSortDir === 'asc' ? 1 : -1;
  const sorted = [...features].sort(
    (a, b) => dir * ((a.properties.revenue_total || 0) - (b.properties.revenue_total || 0))
  );
  el.innerHTML = LocateView.listHtml(sorted);
}


// ── Politiques (tiroir bas) ────────────────────────────────────────────────

function ovScoreColor(score) {
  const s = Math.max(0, Math.min(100, score));
  const red    = [185,  28,  28];  // #b91c1c — rouge, proche de la couleur erreur du design
  const orange = [201, 106,  16];  // #c96a10 — ambre chaud, harmonieux avec le secondaire #865220
  const green  = [ 61, 107,  79];  // #3d6b4f — vert forêt terreux
  let from, to, t;
  if (s <= 50) { from = red;    to = orange; t = s / 50; }
  else         { from = orange; to = green;  t = (s - 50) / 50; }
  const r = Math.round(from[0] + t * (to[0] - from[0]));
  const g = Math.round(from[1] + t * (to[1] - from[1]));
  const b = Math.round(from[2] + t * (to[2] - from[2]));
  return `rgb(${r},${g},${b})`;
}

// Contenu du tiroir « Politiques » ; sa visibilité est gérée par ovSetDrawer.
function ovRenderPolicies(data) {
  const row = document.getElementById('policy-types-row');
  if (!row) return;
  row.innerHTML = (data.policies || [])
    .map((pt) => {
      const avgDisplay = pt.avg_score !== null ? pt.avg_score.toFixed(2) : '—';
      const avgColor = pt.avg_score !== null ? ovScoreColor(pt.avg_score) : null;
      const rows = pt.entries
        .map((e) => {
          const sc = e.score !== null ? Number(e.score) : null;
          const levelStyle = sc !== null
            ? ` style="background:${ovScoreColor(sc)};color:#fff;border-color:transparent"`
            : '';
          return `
          <tr>
            <td>${escHtml(e.subcategory)}</td>
            <td><span class="policy-level"${levelStyle}>${escHtml(e.level)}</span></td>
            <td class="policy-score">${sc !== null ? sc.toFixed(2) : '—'}</td>
          </tr>`;
        })
        .join('');
      return `
        <div class="policy-accordion-item">
          <button class="policy-accordion-header" aria-expanded="false">
            <span class="policy-type-card__name">${escHtml(pt.type)}</span>
            <div class="policy-accordion-header__right">
              <span class="policy-type-card__avg"${avgColor ? ` style="background:${avgColor}"` : ''}>∅ ${escHtml(avgDisplay)}</span>
              <svg class="policy-accordion-chevron" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
          </button>
          <div class="policy-accordion-body" hidden>
            <table class="policy-table">
              <thead><tr><th>Sous-catégorie</th><th>Niveau</th><th>Score</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>`;
    })
    .join('');

  row.querySelectorAll('.policy-accordion-header').forEach((btn) => {
    btn.addEventListener('click', () => {
      const item = btn.closest('.policy-accordion-item');
      const body = item.querySelector('.policy-accordion-body');
      const expanded = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', String(!expanded));
      body.hidden = expanded;
      item.classList.toggle('policy-accordion-item--open', !expanded);
    });
  });
}


// ── Combobox entreprise ────────────────────────────────────────────────────

function ovInitCombobox(companies, initialData) {
  const input = document.getElementById('company-search');
  const listbox = document.getElementById('company-listbox');
  const combobox = document.getElementById('company-combobox');
  if (!input || !listbox || !combobox) return;

  function renderOptions(query) {
    const q = query.toLowerCase();
    const filtered = companies.filter((c) => c.name.toLowerCase().includes(q));
    listbox.innerHTML = filtered
      .map(
        (c) =>
          `<li class="company-combobox__option" role="option" data-id="${c.id}" tabindex="-1">${escHtml(c.name)}</li>`
      )
      .join('');
    const open = filtered.length > 0;
    listbox.hidden = !open;
    combobox.setAttribute('aria-expanded', String(open));
  }

  function selectCompany(id, name) {
    input.value = name;
    listbox.hidden = true;
    combobox.setAttribute('aria-expanded', 'false');
    localStorage.setItem(SELECTED_COMPANY_KEY, id);
    ovSelectCompany(id, null);
  }

  input.addEventListener('input', () => renderOptions(input.value));
  input.addEventListener('focus', () => renderOptions(input.value));

  listbox.addEventListener('click', (e) => {
    const opt = e.target.closest('[data-id]');
    if (opt) selectCompany(Number(opt.dataset.id), opt.textContent.trim());
  });

  document.addEventListener('click', (e) => {
    if (!combobox.contains(e.target)) {
      listbox.hidden = true;
      combobox.setAttribute('aria-expanded', 'false');
    }
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      listbox.hidden = true;
      combobox.setAttribute('aria-expanded', 'false');
    }
    if (e.key === 'ArrowDown') {
      const first = listbox.querySelector('[data-id]');
      if (first) { e.preventDefault(); first.focus(); }
    }
  });

  listbox.addEventListener('keydown', (e) => {
    const opts = [...listbox.querySelectorAll('[data-id]')];
    const idx = opts.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' && idx < opts.length - 1) {
      e.preventDefault(); opts[idx + 1].focus();
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (idx > 0) opts[idx - 1].focus(); else input.focus();
    }
    if (e.key === 'Enter' && idx >= 0) {
      selectCompany(Number(opts[idx].dataset.id), opts[idx].textContent.trim());
    }
    if (e.key === 'Escape') {
      listbox.hidden = true;
      combobox.setAttribute('aria-expanded', 'false');
      input.focus();
    }
  });

  if (initialData && companies.length > 0) {
    input.value = initialData.company_name;
  }
}
