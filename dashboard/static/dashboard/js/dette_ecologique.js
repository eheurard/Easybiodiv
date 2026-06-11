'use strict';

const DE_COMPANY_KEY = 'selected-company-id';

const DE_PIE_COLORS = [
  '#2d6a4f', '#74c69d', '#d4a373', '#e76f51',
  '#457b9d', '#e9c46a', '#8338ec', '#f4a261',
];

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
    style: 'https://tiles.openfreemap.org/styles/liberty',
    center: [0, 20],
    zoom: 1.5,
  });
}


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
        deUpdatePointCountKpi(DE_STATE.data);
      }
    });
  });
}


function deRender(data) {
  DE_STATE.data = data;
  deBuildColorMap(data.commodities);
  deRenderKpis(data);
  deRenderLegend(data.commodities);
  deRenderMarkers(data);
}


function deBuildColorMap(commodities) {
  DE_STATE.colorMap = {};
  [...commodities]
    .sort((a, b) => a.name.localeCompare(b.name))
    .forEach((c, i) => {
      DE_STATE.colorMap[c.name] = DE_PIE_COLORS[i % DE_PIE_COLORS.length];
    });
}


function deRenderKpis(data) {
  const elImpact = document.getElementById('de-total-lbiodiv');
  if (elImpact) elImpact.textContent = data.total_lbiodiv ? deFmtLbiodiv(data.total_lbiodiv) : '—';

  const elYear = document.getElementById('de-year');
  if (elYear) elYear.textContent = data.year != null ? data.year : '—';

  const elTop = document.getElementById('de-top-commodity');
  if (elTop) elTop.textContent = data.commodities.length ? data.commodities[0].name : '—';

  deUpdatePointCountKpi(data);
}


function deUpdatePointCountKpi(data) {
  const points = DE_STATE.mode === 'asset' ? data.assets : data.regions;
  const elCount = document.getElementById('de-point-count');
  if (elCount) elCount.textContent = points.length || '—';
  const elLabel = document.getElementById('de-point-count-label');
  if (elLabel) elLabel.textContent = DE_STATE.mode === 'asset' ? 'Assets' : 'Régions';
}


function deRenderLegend(commodities) {
  const list = document.getElementById('de-legend-list');
  if (!list) return;
  list.innerHTML = commodities.slice(0, 8).map(c => {
    const color = DE_STATE.colorMap[c.name] || '#ccc';
    return (
      '<li class="de-legend__item">' +
      '<span class="de-legend__swatch" style="background:' + color + '"></span>' +
      '<span class="de-legend__name">' + escHtml(c.name) + '</span>' +
      '<span class="de-legend__pct">' + (c.pct * 100).toFixed(1) + '%</span>' +
      '</li>'
    );
  }).join('');
}


function deRenderMarkers(data) {
  DE_STATE.markers.forEach(m => m.remove());
  DE_STATE.markers = [];

  const points = DE_STATE.mode === 'asset' ? data.assets : data.regions;
  if (!points.length) return;

  const maxLbiodiv = points.reduce((m, p) => p.total_lbiodiv > m ? p.total_lbiodiv : m, 0);
  const MIN_R = 8, MAX_R = 30;

  points.forEach(point => {
    const r = maxLbiodiv > 0
      ? Math.max(MIN_R, MAX_R * Math.sqrt(point.total_lbiodiv / maxLbiodiv))
      : MIN_R;
    const el = deBuildPieEl(point, r);
    const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
      .setLngLat([point.longitude, point.latitude])
      .addTo(DE_STATE.map);
    DE_STATE.markers.push(marker);
  });
}


function deBuildPieEl(point, r) {
  const size = r * 2;
  const cx = r, cy = r;
  const NS = 'http://www.w3.org/2000/svg';

  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('viewBox', '0 0 ' + size + ' ' + size);
  svg.style.cursor = 'pointer';
  svg.style.overflow = 'visible';

  if (point.commodities.length === 1) {
    const color = DE_STATE.colorMap[point.commodities[0].name] || '#ccc';
    const disc = document.createElementNS(NS, 'circle');
    disc.setAttribute('cx', cx);
    disc.setAttribute('cy', cy);
    disc.setAttribute('r', r);
    disc.setAttribute('fill', color);
    svg.appendChild(disc);
  } else {
    let startAngle = -Math.PI / 2;
    point.commodities.forEach(c => {
      const slice = c.pct * 2 * Math.PI;
      const endAngle = startAngle + slice;
      const x1 = cx + r * Math.cos(startAngle);
      const y1 = cy + r * Math.sin(startAngle);
      const x2 = cx + r * Math.cos(endAngle);
      const y2 = cy + r * Math.sin(endAngle);
      const large = slice > Math.PI ? 1 : 0;
      const color = DE_STATE.colorMap[c.name] || '#ccc';

      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d',
        'M' + cx + ',' + cy +
        ' L' + x1 + ',' + y1 +
        ' A' + r + ',' + r + ' 0 ' + large + ',1 ' + x2 + ',' + y2 + ' Z'
      );
      path.setAttribute('fill', color);
      path.setAttribute('stroke', '#fff');
      path.setAttribute('stroke-width', '1');
      svg.appendChild(path);
      startAngle = endAngle;
    });
  }

  const border = document.createElementNS(NS, 'circle');
  border.setAttribute('cx', cx);
  border.setAttribute('cy', cy);
  border.setAttribute('r', r);
  border.setAttribute('fill', 'none');
  border.setAttribute('stroke', '#fff');
  border.setAttribute('stroke-width', '2');
  svg.appendChild(border);

  svg.addEventListener('mouseenter', e => deShowTooltip(point, e));
  svg.addEventListener('mousemove', e => deMoveTooltip(e));
  svg.addEventListener('mouseleave', deHideTooltip);

  return svg;
}


function deShowTooltip(point, e) {
  const tip = document.getElementById('de-tooltip');
  if (!tip) return;
  const top3 = point.commodities.slice(0, 3);
  tip.innerHTML =
    '<strong>' + escHtml(point.name) + '</strong><br>' +
    'Lbiodiv : ' + deFmtLbiodiv(point.total_lbiodiv) + '<br>' +
    top3.map(c =>
      '<span class="de-tooltip__swatch" style="background:' + (DE_STATE.colorMap[c.name] || '#ccc') + '"></span>' +
      escHtml(c.name) + ' : ' + (c.pct * 100).toFixed(1) + '%'
    ).join('<br>');
  tip.hidden = false;
  deMoveTooltip(e);
}


function deMoveTooltip(e) {
  const tip = document.getElementById('de-tooltip');
  const mapEl = document.getElementById('de-map');
  if (!tip || !mapEl) return;
  const rect = mapEl.getBoundingClientRect();
  tip.style.left = (e.clientX - rect.left + 14) + 'px';
  tip.style.top  = (e.clientY - rect.top  + 14) + 'px';
}


function deHideTooltip() {
  const tip = document.getElementById('de-tooltip');
  if (tip) tip.hidden = true;
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


function deFmtLbiodiv(val) {
  if (val >= 1e9) return (val / 1e9).toFixed(2) + ' G';
  if (val >= 1e6) return (val / 1e6).toFixed(2) + ' M';
  if (val >= 1e3) return (val / 1e3).toFixed(2) + ' k';
  return val.toFixed(2);
}
