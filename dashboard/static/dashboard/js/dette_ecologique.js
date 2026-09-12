'use strict';

const DE_COMPANY_KEY = 'selected-company-id';

const DE_STATE = {
  data: null,
  mode: 'asset',
  map: null,
  markers: [],
  colorMap: {},
};

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('de-companies');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('de-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  DE_STATE.map = deInitMap();
  deInitToggle();

  const savedId = parseInt(localStorage.getItem(DE_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  DE_STATE.map.on('load', () => {
    if (savedExists && initialData && savedId !== initialData.company_id) {
      fetch(DE_API_URL.replace('/0/', '/' + savedId + '/'))
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(data => { deRender(data); deInitCombobox(companies, data); })
        .catch(err => { console.error('dette_ecologique fetch failed:', err); deInitCombobox(companies, initialData); });
    } else {
      if (initialData) deRender(initialData);
      deInitCombobox(companies, initialData);
    }
  });
});


function deInitMap() {
  return new maplibregl.Map({
    container: 'de-map',
    style: mapStyleFor('classic'),
    center: [0, 20],
    zoom: 1.5,
  });
}


// Les points sont des marqueurs DOM (maplibregl.Marker) : ils survivent a un
// setStyle, il suffit donc de rejouer le fond.
document.addEventListener('themechange', () => {
  if (DE_STATE.map) DE_STATE.map.setStyle(mapStyleFor('classic'));
});


function deInitToggle() {
  document.querySelectorAll('.de-toggle__btn').forEach(btn => {
    btn.addEventListener('click', () => {
      DE_STATE.mode = btn.dataset.mode;
      document.querySelectorAll('.de-toggle__btn').forEach(b => {
        const active = b === btn;
        b.classList.toggle('de-toggle__btn--active', active);
        b.setAttribute('aria-pressed', String(active));
      });
      if (DE_STATE.data) {
        deRenderMarkers(DE_STATE.data);
        DetteView.renderPointCount(DE_STATE.data, DE_STATE.mode);
      }
    });
  });
}


// KPI, légende et infobulle : dette_view.js ; camemberts : pie_markers.js.
function deRender(data) {
  DE_STATE.data = data;
  DE_STATE.colorMap = PieMarkers.colorMap(data.commodities);
  DetteView.renderKpis(data, DE_STATE.mode);
  const list = document.getElementById('de-legend-list');
  if (list) list.innerHTML = DetteView.legendItemsHtml(data.commodities, DE_STATE.colorMap);
  deRenderMarkers(data);
}


function deRenderMarkers(data) {
  DE_STATE.markers.forEach(m => m.remove());
  const points = DE_STATE.mode === 'asset' ? data.assets : data.regions;
  const handlers = DetteView.tooltipHandlers(
    document.getElementById('de-tooltip'), document.getElementById('de-map'), DE_STATE.colorMap
  );
  DE_STATE.markers = PieMarkers.render(DE_STATE.map, points, DE_STATE.colorMap, handlers);
}


function deInitCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');
  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData) input.value = initialData.company_name;

  function buildList(filter) {
    const q = filter.toLowerCase();
    listbox.innerHTML = companies
      .filter(c => c.name.toLowerCase().includes(q))
      .map(c =>
        '<li role="option" data-id="' + c.id + '" class="company-combobox__option' +
        (c.id === selected ? ' selected' : '') + '">' + escHtml(c.name) + '</li>'
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

  listbox.addEventListener('click', e => {
    const opt = e.target.closest('[role="option"]');
    if (!opt) return;
    const id = parseInt(opt.dataset.id, 10);
    selected = id;
    input.value = opt.textContent;
    closeList();
    localStorage.setItem(DE_COMPANY_KEY, id);
    fetch(DE_API_URL.replace('/0/', '/' + id + '/'))
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => deRender(data))
      .catch(err => console.error('dette_ecologique fetch failed:', err));
  });

  document.addEventListener('click', e => {
    if (!combobox.contains(e.target)) closeList();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeList();
  });
}
