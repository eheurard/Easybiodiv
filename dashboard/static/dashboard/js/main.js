const SELECTED_COMPANY_KEY = 'selected-company-id';

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
  const companiesEl = document.getElementById('companies-data');
  if (companiesEl) {
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
  }

});


function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function initMap() {
  const container = document.getElementById('overview-map');
  if (!container) return null;

  const map = new maplibregl.Map({
    container: 'overview-map',
    style: 'https://tiles.openfreemap.org/styles/liberty',
    center: [0, 20],
    zoom: 1.5,
  });

  map.on('load', () => {
    map.addSource('assets', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
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
      new maplibregl.Popup()
        .setLngLat(e.lngLat)
        .setHTML(
          `<strong>${escHtml(p.name)}</strong><br>` +
          `${escHtml(p.country)} — ${escHtml(p.commodities)}<br>` +
          `<small>${escHtml(p.region)}</small>`
        )
        .addTo(map);
    });
    map.on('mouseenter', 'assets-layer', () => {
      map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', 'assets-layer', () => {
      map.getCanvas().style.cursor = '';
    });

    if (window._pendingGeojson) {
      map.getSource('assets').setData(window._pendingGeojson);
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
    if (map.loaded()) {
      map.getSource('assets').setData(data.geojson);
    } else {
      window._pendingGeojson = data.geojson;
    }
  }

  const list = document.getElementById('country-list');
  if (!list) return;
  if (data.countries.length === 0) {
    list.innerHTML = '<p class="country-panel__empty">Aucun actif pour cette entreprise.</p>';
    return;
  }
  list.innerHTML = data.countries
    .map((c) => {
      const tags = c.commodities
        .map((cm, i) =>
          `<span class="country-item__tag${i === 0 ? ' country-item__tag--primary' : ''}">${escHtml(cm.name)} ×${cm.count}</span>`
        )
        .join('');
      return `
        <div class="country-item">
          <div class="country-item__top">
            <span class="country-item__name">${escHtml(c.name)}</span>
            <span class="country-item__count">${c.asset_count} actif${c.asset_count > 1 ? 's' : ''}</span>
          </div>
          <div class="country-item__tags">${tags}</div>
        </div>`;
    })
    .join('');

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
      const rows = pt.entries
        .map((e) => `
          <tr>
            <td>${escHtml(e.subcategory)}</td>
            <td><span class="policy-level">${escHtml(e.level)}</span></td>
            <td class="policy-score">${e.score !== null ? Number(e.score).toFixed(2) : '—'}</td>
          </tr>`)
        .join('');
      return `
        <div class="policy-type-card">
          <div class="policy-type-card__header">
            <span class="policy-type-card__name">${escHtml(pt.type)}</span>
            <span class="policy-type-card__avg">∅ ${escHtml(avgDisplay)}</span>
          </div>
          <table class="policy-table">
            <thead><tr><th>Sous-catégorie</th><th>Niveau</th><th>Score</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
    })
    .join('');
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
