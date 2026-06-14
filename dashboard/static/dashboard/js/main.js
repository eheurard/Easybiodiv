const SELECTED_COMPANY_KEY = 'selected-company-id';

const MAP_STYLES = {
  classic: 'https://tiles.openfreemap.org/styles/liberty',
  grayscale: 'https://tiles.openfreemap.org/styles/positron',
  satellite: {
    version: 8,
    sources: {
      satellite: {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256,
        attribution: 'Tiles © Esri',
      },
    },
    layers: [{ id: 'satellite-bg', type: 'raster', source: 'satellite' }],
  },
};

let _countryCoords = {};

document.addEventListener('DOMContentLoaded', () => {

  // ── Sidebar toggle ──────────────────────────────────────────────────────
  const layout = document.getElementById('app-layout');
  const toggleBtn = document.getElementById('sidebar-toggle');

  if (layout && toggleBtn) {
    const STORAGE_KEY = 'sidebar-collapsed';
    const isCollapsed = localStorage.getItem(STORAGE_KEY) === '1';

    if (isCollapsed) applyCollapsed(true, false);

    toggleBtn.addEventListener('click', () => {
      const collapsed = layout.classList.toggle('sidebar-collapsed');
      localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
      toggleBtn.setAttribute('aria-expanded', String(!collapsed));
      toggleBtn.setAttribute('aria-label', collapsed ? 'Développer le menu' : 'Réduire le menu');
      if (collapsed) {
        document.querySelectorAll('.sidebar__nav-details').forEach(d => d.removeAttribute('open'));
      }
    });

    function applyCollapsed(collapsed, animate) {
      if (!animate) layout.style.transition = 'none';
      layout.classList.toggle('sidebar-collapsed', collapsed);
      toggleBtn.setAttribute('aria-expanded', String(!collapsed));
      toggleBtn.setAttribute('aria-label', collapsed ? 'Développer le menu' : 'Réduire le menu');
      if (collapsed) {
        document.querySelectorAll('.sidebar__nav-details').forEach(d => d.removeAttribute('open'));
      }
      if (!animate) requestAnimationFrame(() => { layout.style.transition = ''; });
    }
  }

  // ── Legacy test button ──────────────────────────────────────────────────
  const testBtn = document.getElementById('test-btn');
  if (testBtn) {
    testBtn.addEventListener('click', () => {
      const isActive = testBtn.classList.toggle('active');
      testBtn.setAttribute('aria-pressed', String(isActive));
    });
  }

  // ── User menu dropdown ──────────────────────────────────────────────────
  const userMenuBtn = document.getElementById('user-menu-btn');
  const userDropdown = document.getElementById('user-dropdown');

  if (userMenuBtn && userDropdown) {
    function openMenu() {
      userDropdown.removeAttribute('hidden');
      userMenuBtn.setAttribute('aria-expanded', 'true');
    }
    function closeMenu() {
      userDropdown.setAttribute('hidden', '');
      userMenuBtn.setAttribute('aria-expanded', 'false');
    }

    userMenuBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      userDropdown.hasAttribute('hidden') ? openMenu() : closeMenu();
    });

    document.addEventListener('click', closeMenu);
    userDropdown.addEventListener('click', (e) => e.stopPropagation());
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closeMenu(); userMenuBtn.focus(); }
    });
  }

  // ── Overview page ──────────────────────────────────────────────────────
  // Gated on #overview-map so this block runs ONLY on the overview page: other
  // pages (transition_risk, dependencies, physical_risk) also emit #companies-data
  // but have their own combobox/fetch logic and no COMPANY_API_URL.
  const companiesEl = document.getElementById('companies-data');
  if (companiesEl && document.getElementById('overview-map')) {
    const companies = JSON.parse(companiesEl.textContent);
    const initialDataEl = document.getElementById('initial-data');
    const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;
    const overviewMap = initMap();

    const savedId = parseInt(localStorage.getItem(SELECTED_COMPANY_KEY), 10);
    const savedExists = savedId && companies.some(c => c.id === savedId);

    if (savedExists && initialData && savedId !== initialData.company_id) {
      fetchCompany(savedId, overviewMap);
      const saved = companies.find(c => c.id === savedId);
      initCombobox(companies, { company_name: saved.name }, overviewMap);
    } else {
      if (initialData) updateDashboard(initialData, overviewMap);
      initCombobox(companies, initialData, overviewMap);
    }

    // Map layer toggle
    document.querySelectorAll('.map-layer-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.map-layer-btn').forEach((b) => b.classList.remove('map-layer-btn--active'));
        btn.classList.add('map-layer-btn--active');
        switchMapStyle(overviewMap, btn.dataset.layer);
      });
    });

    // Country click → zoom on map
    const countryList = document.getElementById('country-list');
    if (countryList) {
      countryList.addEventListener('click', (e) => {
        const item = e.target.closest('[data-country]');
        if (!item || !overviewMap) return;
        const coords = _countryCoords[item.dataset.country];
        if (!coords) return;
        overviewMap.flyTo({
          center: [coords.sumLng / coords.n, coords.sumLat / coords.n],
          zoom: 5,
          duration: 1200,
        });
      });
    }

    // Asset click → zoom on map
    const assetListEl = document.getElementById('asset-list');
    if (assetListEl) {
      assetListEl.addEventListener('click', (e) => {
        const item = e.target.closest('[data-lng]');
        if (!item || !overviewMap) return;
        const lng = parseFloat(item.dataset.lng);
        const lat = parseFloat(item.dataset.lat);
        if (isNaN(lng) || isNaN(lat)) return;
        overviewMap.flyTo({ center: [lng, lat], zoom: 12, duration: 1200 });
      });
    }

    // Exposition panel tab switching
    const panelTabs = document.querySelectorAll('.country-panel__tab');

    // Place indicator on the active tab without animation (initial render)
    const initTab = document.querySelector('.country-panel__tab--active');
    if (initTab) moveTabIndicator(initTab, false);

    panelTabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        if (tab.classList.contains('country-panel__tab--active')) return;

        panelTabs.forEach((t) => {
          t.classList.remove('country-panel__tab--active');
          t.setAttribute('aria-pressed', 'false');
        });
        tab.classList.add('country-panel__tab--active');
        tab.setAttribute('aria-pressed', 'true');

        // Slide the indicator immediately
        moveTabIndicator(tab, true);

        const targetId = tab.dataset.tab === 'pays' ? 'country-view' : 'asset-view';
        const currentView = document.querySelector('.country-panel__view--active');
        const nextView = document.getElementById(targetId);

        if (!currentView || !nextView || currentView === nextView) return;

        currentView.classList.add('country-panel__view--leaving');
        setTimeout(() => {
          currentView.classList.remove('country-panel__view--active', 'country-panel__view--leaving');
          nextView.classList.add('country-panel__view--active');
        }, 200);
      });
    });
  }

});


function scoreColor(score) {
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

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtNum(n) {
  return Number(n).toLocaleString('fr-FR', { maximumFractionDigits: 0 });
}

function fmtEuro(n) {
  if (n >= 1e6) return `${(n / 1e6).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} M€`;
  if (n >= 1e3) return `${(n / 1e3).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} k€`;
  return `${n.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} €`;
}

function fmtFootprint(n) {
  if (n === 0) return '—';
  if (n >= 1e3) return `${(n / 1e3).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} k`;
  if (n >= 1) return n.toLocaleString('fr-FR', { maximumFractionDigits: 3 });
  const exp = Math.floor(Math.log10(Math.abs(n)));
  const mantissa = (n / Math.pow(10, exp)).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
  return `${mantissa}×10<sup>${exp}</sup>`;
}

function addAssetsLayer(map) {
  map.addLayer({
    id: 'assets-layer',
    type: 'circle',
    source: 'assets',
    paint: {
      'circle-radius': 7,
      'circle-color': '#91452d',
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
    },
  });
  map.on('click', 'assets-layer', (e) => {
    const p = e.features[0].properties;

    let productions = [];
    try { productions = JSON.parse(p.productions || '[]'); } catch (_) {}

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

    const html = `
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

    new maplibregl.Popup({ maxWidth: '300px' })
      .setLngLat(e.lngLat)
      .setHTML(html)
      .addTo(map);
  });
  map.on('mouseenter', 'assets-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'assets-layer', () => { map.getCanvas().style.cursor = ''; });
}

function switchMapStyle(map, styleName) {
  const style = MAP_STYLES[styleName] || MAP_STYLES.classic;
  const currentData = map._assetsGeojson || { type: 'FeatureCollection', features: [] };
  map.setStyle(style);
  map.once('styledata', () => {
    if (map.getSource('assets')) return;
    map.addSource('assets', { type: 'geojson', data: currentData });
    addAssetsLayer(map);
  });
}

function initMap() {
  const container = document.getElementById('overview-map');
  if (!container) return null;

  const map = new maplibregl.Map({
    container: 'overview-map',
    style: MAP_STYLES.classic,
    center: [0, 20],
    zoom: 1.5,
  });

  map.on('load', () => {
    map.addSource('assets', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
    addAssetsLayer(map);

    if (window._pendingGeojson) {
      map.getSource('assets').setData(window._pendingGeojson);
      map._assetsGeojson = window._pendingGeojson;
      window._pendingGeojson = null;
    }
  });

  return map;
}

function updateDashboard(data, map) {
  ['asset_count', 'country_count', 'commodity_count', 'region_count'].forEach((key) => {
    const el = document.querySelector(`[data-kpi="${key}"]`);
    if (el) el.textContent = data[key];
  });

  if (map) {
    map._assetsGeojson = data.geojson;
    if (map.loaded()) {
      map.getSource('assets').setData(data.geojson);
    } else {
      window._pendingGeojson = data.geojson;
    }
  }

  // Build country → centroid from geojson features
  _countryCoords = {};
  if (data.geojson && data.geojson.features) {
    data.geojson.features.forEach((f) => {
      const country = f.properties.country;
      const [lng, lat] = f.geometry.coordinates;
      if (!_countryCoords[country]) _countryCoords[country] = { sumLat: 0, sumLng: 0, n: 0 };
      _countryCoords[country].sumLat += lat;
      _countryCoords[country].sumLng += lng;
      _countryCoords[country].n += 1;
    });
  }

  const list = document.getElementById('country-list');
  if (!list) return;
  if (data.countries.length === 0) {
    list.innerHTML = '<p class="country-panel__empty">Aucun actif pour cette entreprise.</p>';
    return;
  }
  list.innerHTML = data.countries
    .map((c) => {
      const hasCoords = !!_countryCoords[c.name];
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

  renderAssetList(data);

  // Policy section
  const policySection = document.getElementById('policy-section');
  const policyRow = document.getElementById('policy-types-row');
  if (!policySection || !policyRow) return;
  if (!data.policies || data.policies.length === 0) {
    policySection.hidden = true;
    return;
  }
  policySection.hidden = false;
  policyRow.innerHTML = data.policies
    .map((pt) => {
      const avgDisplay = pt.avg_score !== null ? pt.avg_score.toFixed(2) : '—';
      const avgColor = pt.avg_score !== null ? scoreColor(pt.avg_score) : null;
      const rows = pt.entries
        .map((e) => {
          const sc = e.score !== null ? Number(e.score) : null;
          const levelStyle = sc !== null
            ? ` style="background:${scoreColor(sc)};color:#fff;border-color:transparent"`
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

  policyRow.querySelectorAll('.policy-accordion-header').forEach((btn) => {
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

function fetchCompany(id, map) {
  fetch(COMPANY_API_URL + id + '/')
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then((data) => updateDashboard(data, map))
    .catch((err) => console.error('fetchCompany failed:', err));
}

function initCombobox(companies, initialData, map) {
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
    fetchCompany(id, map);
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

function moveTabIndicator(tab, animate) {
  const indicator = document.querySelector('.country-panel__tab-indicator');
  if (!indicator || !tab) return;
  const container = tab.closest('.country-panel__tabs');
  if (!container) return;

  const tabRect = tab.getBoundingClientRect();
  const containerRect = container.getBoundingClientRect();

  if (!animate) {
    indicator.style.transition = 'none';
    requestAnimationFrame(() => { indicator.style.transition = ''; });
  }
  indicator.style.left = (tabRect.left - containerRect.left) + 'px';
  indicator.style.width = tabRect.width + 'px';
}

function renderAssetList(data) {
  const el = document.getElementById('asset-list');
  if (!el) return;

  const features = (data.geojson && data.geojson.features) ? data.geojson.features : [];

  if (features.length === 0) {
    el.innerHTML = '<p class="country-panel__empty">Aucun actif pour cette entreprise.</p>';
    return;
  }

  const sorted = [...features].sort(
    (a, b) => (b.properties.footprint || 0) - (a.properties.footprint || 0)
  );

  el.innerHTML = sorted.map((f, idx) => {
    const p = f.properties;
    let productions = [];
    try { productions = JSON.parse(p.productions || '[]'); } catch (_) {}

    const commodities = productions.length > 0
      ? [...new Set(productions.map((pr) => pr.commodity))]
      : (p.commodities ? p.commodities.split(', ').filter(Boolean) : []);

    const footprintHtml = (p.footprint && p.footprint > 0) ? fmtFootprint(p.footprint) : '—';
    const commTags = commodities
      .map((c) => `<span class="asset-card__comm-tag">${escHtml(c)}</span>`)
      .join('');

    const [lng, lat] = f.geometry.coordinates;
    return `
      <div class="asset-card asset-card--clickable" data-lng="${lng}" data-lat="${lat}">
        <div class="asset-card__rank">#${idx + 1}</div>
        <div class="asset-card__body">
          <div class="asset-card__top">
            <span class="asset-card__name">${escHtml(p.name)}</span>
            <span class="asset-card__footprint">${footprintHtml}</span>
          </div>
          <div class="asset-card__commodities">${commTags}</div>
        </div>
      </div>`;
  }).join('');
}
