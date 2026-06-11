const ME_COMPANY_KEY = 'selected-company-id';

let currentData = null;

const treeState = {
  selected: null,   // string node id ou null
  threshold: 0,     // float 0–1 (ex. 0.05 = 5 %)
  commodity: null,  // string nom commodité ou null = toutes
};

document.addEventListener('DOMContentLoaded', () => {
  initTreeFilters();

  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  const savedId = parseInt(localStorage.getItem(ME_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    // Saved company differs from server-rendered default — fetch it
    fetch(MESURE_EMPREINTE_API_URL.replace('/0/', '/' + savedId + '/'))
      .then(r => r.json())
      .then(data => {
        renderTransitionRisk(data);
        initTrCombobox(companies, data);
      });
  } else {
    if (initialData) renderTransitionRisk(initialData);
    initTrCombobox(companies, initialData);
  }
});


function initTrCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');

  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData) input.value = initialData.company_name;

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
    localStorage.setItem(ME_COMPANY_KEY, id);
    fetch(MESURE_EMPREINTE_API_URL.replace('/0/', '/' + id + '/'))
      .then(r => r.json())
      .then(data => renderTransitionRisk(data));
  });

  document.addEventListener('click', (e) => {
    if (!combobox.contains(e.target)) closeList();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeList();
  });
}


function initTreeFilters() {
  const slider = document.getElementById('tree-threshold');
  const label  = document.getElementById('tree-threshold-label');
  if (!slider) return;

  slider.addEventListener('input', () => {
    const pct = parseInt(slider.value, 10);
    if (label) label.textContent = `≥ ${pct} %`;
    treeState.threshold = pct / 100;
    treeState.selected = null;
    hideTreePanel();
    if (currentData) renderTree(currentData);
  });

  const closeBtn = document.getElementById('tree-panel-close');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      treeState.selected = null;
      resetTreeHighlight();
      hideTreePanel();
    });
  }
}


function buildCommodityPills(data) {
  const container = document.getElementById('tree-commodity-filters');
  if (!container) return;

  treeState.commodity = null;

  const names = data.commodities.map(c => c.name);

  let html = '<span class="label-caps">Commodité</span>';
  html += '<button class="tr-tree-commodity-pill tr-tree-commodity-pill--active" data-commodity="">Toutes</button>';
  names.forEach(name => {
    html += `<button class="tr-tree-commodity-pill" data-commodity="${escHtml(name)}">${escHtml(name)}</button>`;
  });
  container.innerHTML = html;

  container.querySelectorAll('.tr-tree-commodity-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      const val = btn.dataset.commodity || null;
      treeState.commodity = val;
      treeState.selected = null;

      container.querySelectorAll('.tr-tree-commodity-pill').forEach(b =>
        b.classList.remove('tr-tree-commodity-pill--active')
      );
      btn.classList.add('tr-tree-commodity-pill--active');

      hideTreePanel();
      if (currentData) renderTree(currentData);
    });
  });
}


function renderTransitionRisk(data) {
  currentData = data;

  const kpiImpact = document.getElementById('tr-total-impact');
  if (kpiImpact) kpiImpact.textContent = data.total_impact
    ? data.total_impact.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
    : '—';

  const kpiYear = document.getElementById('tr-year');
  if (kpiYear) kpiYear.textContent = data.year || '—';

  const kpiCommodities = document.getElementById('tr-commodity-count');
  if (kpiCommodities) kpiCommodities.textContent = data.commodities.length;

  const kpiAssets = document.getElementById('tr-asset-count');
  if (kpiAssets) kpiAssets.textContent = data.assets.length;

  renderBars('commodity-bars', data.commodities);
  renderBars('asset-bars', data.assets);
  renderBars('country-bars', data.countries);
  renderSankey(data);
  buildCommodityPills(data);
  renderTree(data);
}


const BAR_COLORS = [
  '#91452d', '#af5d43', '#865220', '#feb87c',
  '#625a4e', '#7b7366', '#954830', '#dac1ba',
];

function renderBars(containerId, items) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = '<p class="tr-empty">Aucune donnée disponible.</p>';
    return;
  }

  container.innerHTML = items.slice(0, 8).map((item, i) => `
    <div class="tr-bar-row">
      <span class="tr-bar-label" title="${escHtml(item.name)}">${escHtml(item.name)}</span>
      <div class="tr-bar-track">
        <div class="tr-bar-fill" style="width:${(item.pct * 100).toFixed(1)}%;background-color:${BAR_COLORS[i % BAR_COLORS.length]}"></div>
      </div>
      <span class="tr-bar-pct data-tabular">${(item.pct * 100).toFixed(1)}&nbsp;%</span>
    </div>
  `).join('');
}


const SANKEY_COLORS = ['#91452d', '#865220', '#625a4e', '#4a7a5c'];

const TREE_NODE_W = 100;
const TREE_NODE_H = 32;
const TREE_NODE_GAP = 14;
const TREE_COL_X = [20, 250, 470, 700];
const TREE_COL_LABELS = ['COMMODITÉS', 'ACTIFS', 'PAYS', 'COMPANY'];
const TREE_COLORS = ['#4a7a5c', '#625a4e', '#865220', '#91452d'];
const TREE_TOP = 28;
const SVG_NS = 'http://www.w3.org/2000/svg';
let _treeNodeEls  = {};
let _treeLinkEls  = [];

function renderSankey(data) {
  const svg = document.getElementById('sankey-svg');
  if (!svg) return;

  if (!data.sankey_links || data.sankey_links.length === 0) {
    svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" font-size="13" font-family="Inter,sans-serif" fill="#87736d">Aucune donnée à afficher.</text>';
    svg.setAttribute('viewBox', '0 0 600 120');
    return;
  }

  const W = 900, H = 380;
  const NODE_W = 14;
  const NODE_GAP = 10;
  const TOP_MARGIN = 30;
  const AVAIL_H = H - TOP_MARGIN - 16;

  const COL_X = [60, 270, 500, 730];
  const COL_LABELS = ['COMMODITÉS', 'ACTIFS', 'PAYS', 'COMPANY'];

  const nodes = {};

  data.commodities.forEach(c => {
    nodes[`commodity:${c.name}`] = { label: c.name, col: 0, pct: c.pct, y: 0, h: 0 };
  });
  data.assets.forEach(a => {
    nodes[`asset:${a.id}`] = { label: a.name, col: 1, pct: a.pct, y: 0, h: 0 };
  });
  data.countries.forEach(c => {
    nodes[`country:${c.name}`] = { label: c.name, col: 2, pct: c.pct, y: 0, h: 0 };
  });
  nodes[`company:${data.company_id}`] = {
    label: data.company_name, col: 3, pct: 1.0, y: 0, h: 0
  };

  const cols = [[], [], [], []];
  Object.entries(nodes).forEach(([id, n]) => { n.id = id; cols[n.col].push(n); });

  // Map each asset to its dominant country (highest link value)
  const assetToCountry = {};
  const assetToCountryValue = {};
  data.sankey_links.forEach(link => {
    if (link.source.startsWith('asset:') && link.target.startsWith('country:')) {
      const prev = assetToCountryValue[link.source] || 0;
      if (link.value > prev) {
        assetToCountry[link.source] = link.target;
        assetToCountryValue[link.source] = link.value;
      }
    }
  });

  // Sort countries by pct desc to define grouping order
  cols[2].sort((a, b) => b.pct - a.pct);
  const countryOrder = cols[2].map(c => c.id);

  // Group assets by their dominant country, then order by country rank
  const assetsByCountry = {};
  cols[1].forEach(asset => {
    const cid = assetToCountry[asset.id] || '__none__';
    if (!assetsByCountry[cid]) assetsByCountry[cid] = [];
    assetsByCountry[cid].push(asset);
  });
  const orderedAssets = [];
  countryOrder.forEach(cid => {
    (assetsByCountry[cid] || []).sort((a, b) => b.pct - a.pct).forEach(a => orderedAssets.push(a));
  });
  (assetsByCountry['__none__'] || []).sort((a, b) => b.pct - a.pct).forEach(a => orderedAssets.push(a));
  cols[1] = orderedAssets;

  cols.forEach((colNodes, colIdx) => {
    if (colIdx !== 1) colNodes.sort((a, b) => b.pct - a.pct);
    const totalPct = colNodes.reduce((s, n) => s + n.pct, 0) || 1;
    const totalGap = (colNodes.length - 1) * NODE_GAP;
    let y = TOP_MARGIN;
    colNodes.forEach(n => {
      n.h = Math.max(10, (n.pct / totalPct) * (AVAIL_H - totalGap));
      n.y = y;
      y += n.h + NODE_GAP;
    });
  });

  const srcOffset = {};
  const tgtOffset = {};

  let paths = '';
  let nodeRects = '';
  let labels = '';

  data.sankey_links.forEach(link => {
    const src = nodes[link.source];
    const tgt = nodes[link.target];
    if (!src || !tgt) return;

    if (srcOffset[link.source] === undefined) srcOffset[link.source] = 0;
    if (tgtOffset[link.target] === undefined) tgtOffset[link.target] = 0;

    const ribbonH = Math.max(1.5, link.value * AVAIL_H);

    const x1 = COL_X[src.col] + NODE_W;
    const y1t = src.y + srcOffset[link.source];
    const x2 = COL_X[tgt.col];
    const y2t = tgt.y + tgtOffset[link.target];
    const mx = (x1 + x2) / 2;

    const color = SANKEY_COLORS[src.col % SANKEY_COLORS.length];

    paths += `<path d="M${x1},${y1t} C${mx},${y1t} ${mx},${y2t} ${x2},${y2t} ` +
             `L${x2},${y2t + ribbonH} C${mx},${y2t + ribbonH} ${mx},${y1t + ribbonH} ${x1},${y1t + ribbonH} Z" ` +
             `fill="${color}" fill-opacity="0.18" stroke="none"/>`;

    srcOffset[link.source] += ribbonH;
    tgtOffset[link.target] += ribbonH;
  });

  Object.values(nodes).forEach(n => {
    const x = COL_X[n.col];
    const color = SANKEY_COLORS[n.col % SANKEY_COLORS.length];
    nodeRects += `<rect x="${x}" y="${n.y}" width="${NODE_W}" height="${n.h}" rx="3" fill="${color}"/>`;

    const maxLen = 16;
    const shortLabel = n.label.length > maxLen ? n.label.slice(0, maxLen - 1) + '…' : n.label;
    if (n.col < 3) {
      const lx = x + NODE_W + 6;
      const ly = n.y + n.h / 2;
      labels += `<text x="${lx}" y="${ly}" dy="0.35em" font-size="11" font-family="Inter,sans-serif" fill="#54433e" text-anchor="start">${escHtml(shortLabel)}</text>`;
    } else {
      const lx = x - 6;
      const ly = n.y + n.h / 2;
      labels += `<text x="${lx}" y="${ly}" dy="0.35em" font-size="11" font-family="Inter,sans-serif" fill="#54433e" text-anchor="end">${escHtml(shortLabel)}</text>`;
    }
  });

  let headers = '';
  COL_X.forEach((x, i) => {
    headers += `<text x="${x}" y="16" font-size="9" font-family="Inter,sans-serif" fill="#87736d" text-anchor="start" font-weight="700" letter-spacing="0.08em">${escHtml(COL_LABELS[i])}</text>`;
  });

  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.innerHTML = headers + paths + nodeRects + labels;
}


function renderTree(data) {
  const svg = document.getElementById('tree-svg');
  if (!svg) return;

  _treeNodeEls = {};
  _treeLinkEls = [];

  if (!data.sankey_links || data.sankey_links.length === 0) {
    svg.setAttribute('viewBox', '0 0 820 120');
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const t = document.createElementNS(SVG_NS, 'text');
    t.setAttribute('x', '50%');
    t.setAttribute('y', '50%');
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('font-size', '13');
    t.setAttribute('font-family', 'Inter,sans-serif');
    t.setAttribute('fill', '#87736d');
    t.textContent = 'Aucune donnée à afficher.';
    svg.appendChild(t);
    return;
  }

  const allNodes = {};
  data.commodities.forEach(c => {
    allNodes[`commodity:${c.name}`] = { label: c.name, col: 0, pct: c.pct };
  });
  data.assets.forEach(a => {
    allNodes[`asset:${a.id}`] = { label: a.name, col: 1, pct: a.pct };
  });
  data.countries.forEach(c => {
    allNodes[`country:${c.name}`] = { label: c.name, col: 2, pct: c.pct };
  });
  allNodes[`company:${data.company_id}`] = { label: data.company_name, col: 3, pct: 1.0 };

  const { threshold, commodity } = treeState;

  let visibleIds = new Set(
    Object.entries(allNodes)
      .filter(([id, n]) => n.col === 3 || n.pct >= threshold)
      .map(([id]) => id)
  );

  if (commodity) {
    const commodityId = `commodity:${commodity}`;
    if (visibleIds.has(commodityId)) {
      const connected = new Set([commodityId, `company:${data.company_id}`]);
      data.sankey_links.forEach(link => {
        if (link.source === commodityId && visibleIds.has(link.target))
          connected.add(link.target);
      });
      data.sankey_links.forEach(link => {
        if (connected.has(link.source) && link.source.startsWith('asset:') && visibleIds.has(link.target))
          connected.add(link.target);
      });
      visibleIds = connected;
    } else {
      visibleIds = new Set([`company:${data.company_id}`]);
    }
  }

  const visibleLinks = data.sankey_links.filter(
    l => visibleIds.has(l.source) && visibleIds.has(l.target)
  );

  const nodes = {};
  Object.entries(allNodes).forEach(([id, n]) => {
    if (visibleIds.has(id)) nodes[id] = { ...n, id };
  });

  const cols = [[], [], [], []];
  Object.values(nodes).forEach(n => cols[n.col].push(n));
  cols.forEach(col => col.sort((a, b) => b.pct - a.pct));

  const maxNodes = Math.max(...cols.map(c => c.length), 1);
  const H = TREE_TOP + maxNodes * (TREE_NODE_H + TREE_NODE_GAP) + 10;

  cols.forEach(colNodes => {
    const colH = colNodes.length * (TREE_NODE_H + TREE_NODE_GAP) - TREE_NODE_GAP;
    let y = TREE_TOP + Math.max(0, (H - TREE_TOP - 10 - colH) / 2);
    colNodes.forEach(n => { n.y = y; y += TREE_NODE_H + TREE_NODE_GAP; });
  });

  const W = TREE_COL_X[3] + TREE_NODE_W + 20;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

  while (svg.firstChild) svg.removeChild(svg.firstChild);

  const gHeaders = document.createElementNS(SVG_NS, 'g');
  TREE_COL_X.forEach((x, i) => {
    const t = document.createElementNS(SVG_NS, 'text');
    t.setAttribute('x', x);
    t.setAttribute('y', '16');
    t.setAttribute('font-size', '8');
    t.setAttribute('font-family', 'Inter,sans-serif');
    t.setAttribute('fill', '#87736d');
    t.setAttribute('font-weight', '700');
    t.setAttribute('letter-spacing', '0.08em');
    t.textContent = TREE_COL_LABELS[i];
    gHeaders.appendChild(t);
  });
  svg.appendChild(gHeaders);

  const gLinks = document.createElementNS(SVG_NS, 'g');
  visibleLinks.forEach(link => {
    const src = nodes[link.source];
    const tgt = nodes[link.target];
    if (!src || !tgt) return;

    const x1 = TREE_COL_X[src.col] + TREE_NODE_W;
    const y1 = src.y + TREE_NODE_H / 2;
    const x2 = TREE_COL_X[tgt.col];
    const y2 = tgt.y + TREE_NODE_H / 2;
    const mx = (x1 + x2) / 2;
    const sw = Math.max(1, link.value * 20);

    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', TREE_COLORS[src.col]);
    path.setAttribute('stroke-width', sw);
    path.setAttribute('stroke-opacity', '0.25');
    gLinks.appendChild(path);
    _treeLinkEls.push({ el: path, src: link.source, tgt: link.target });
  });
  svg.appendChild(gLinks);

  const gNodes = document.createElementNS(SVG_NS, 'g');
  Object.values(nodes).forEach(n => {
    const x     = TREE_COL_X[n.col];
    const color = TREE_COLORS[n.col];
    const pctText = n.col === 3 ? '100 %' : `${(n.pct * 100).toFixed(1)} %`;

    const g = document.createElementNS(SVG_NS, 'g');
    g.setAttribute('class', 'tree-node');
    g.style.cursor = 'pointer';

    const rect = document.createElementNS(SVG_NS, 'rect');
    rect.setAttribute('x', x);
    rect.setAttribute('y', n.y);
    rect.setAttribute('width', TREE_NODE_W);
    rect.setAttribute('height', TREE_NODE_H);
    rect.setAttribute('rx', '4');
    rect.setAttribute('fill', color);

    const tLabel = document.createElementNS(SVG_NS, 'text');
    tLabel.setAttribute('class', 'tree-lbl');
    tLabel.setAttribute('x', x + TREE_NODE_W / 2);
    tLabel.setAttribute('y', n.y + 12);
    tLabel.setAttribute('text-anchor', 'middle');
    tLabel.setAttribute('font-size', '10');
    tLabel.setAttribute('font-family', 'Inter,sans-serif');
    tLabel.setAttribute('fill', 'white');
    tLabel.setAttribute('font-weight', '600');
    tLabel.textContent = n.label;

    const tPct = document.createElementNS(SVG_NS, 'text');
    tPct.setAttribute('x', x + TREE_NODE_W / 2);
    tPct.setAttribute('y', n.y + 26);
    tPct.setAttribute('text-anchor', 'middle');
    tPct.setAttribute('font-size', '9');
    tPct.setAttribute('font-family', 'Inter,sans-serif');
    tPct.setAttribute('fill', 'rgba(255,255,255,0.75)');
    tPct.textContent = pctText;

    g.appendChild(rect);
    g.appendChild(tLabel);
    g.appendChild(tPct);

    g.addEventListener('click', () => handleNodeClick(n.id, data));

    gNodes.appendChild(g);
    _treeNodeEls[n.id] = g;
  });
  svg.appendChild(gNodes);

  const availW = TREE_NODE_W - 12;
  svg.querySelectorAll('.tree-lbl').forEach(t => {
    if (t.getComputedTextLength && t.getComputedTextLength() > availW) {
      t.setAttribute('textLength', availW);
      t.setAttribute('lengthAdjust', 'spacingAndGlyphs');
    }
  });
}


function handleNodeClick(nodeId, data) {
  if (treeState.selected === nodeId) {
    treeState.selected = null;
    resetTreeHighlight();
    hideTreePanel();
  } else {
    treeState.selected = nodeId;
    applyTreeHighlight(nodeId);
    showTreePanel(nodeId, data);
  }
}

function applyTreeHighlight(nodeId) {
  const connectedIds = new Set([nodeId]);

  // Upstream : remonte les liens (tgt → src) pour trouver les ancêtres
  let frontier = [nodeId];
  while (frontier.length > 0) {
    const next = [];
    _treeLinkEls.forEach(({ src, tgt }) => {
      if (frontier.includes(tgt) && !connectedIds.has(src)) {
        connectedIds.add(src); next.push(src);
      }
    });
    frontier = next;
  }

  // Downstream : descend les liens (src → tgt) pour trouver les descendants
  frontier = [nodeId];
  while (frontier.length > 0) {
    const next = [];
    _treeLinkEls.forEach(({ src, tgt }) => {
      if (frontier.includes(src) && !connectedIds.has(tgt)) {
        connectedIds.add(tgt); next.push(tgt);
      }
    });
    frontier = next;
  }

  Object.entries(_treeNodeEls).forEach(([id, g]) => {
    g.style.opacity = connectedIds.has(id) ? '1' : '0.15';
  });

  _treeLinkEls.forEach(({ el, src, tgt }) => {
    const active = connectedIds.has(src) && connectedIds.has(tgt);
    el.setAttribute('stroke-opacity', active ? '0.9' : '0.06');
  });
}

function resetTreeHighlight() {
  Object.values(_treeNodeEls).forEach(g => { g.style.opacity = '1'; });
  _treeLinkEls.forEach(({ el }) => { el.setAttribute('stroke-opacity', '0.25'); });
}


function hideTreePanel() {
  const panel = document.getElementById('tree-panel');
  if (panel) panel.hidden = true;
}

function showTreePanel(nodeId, data) {
  const panel   = document.getElementById('tree-panel');
  const content = document.getElementById('tree-panel-content');
  if (!panel || !content) return;
  content.innerHTML = buildPanelHTML(nodeId, data);
  panel.hidden = false;
}

function buildPanelHTML(nodeId, data) {
  const colonIdx = nodeId.indexOf(':');
  const type  = nodeId.slice(0, colonIdx);
  const idVal = nodeId.slice(colonIdx + 1);

  const typeLabels = { commodity: 'COMMODITÉ', asset: 'ACTIF', country: 'PAYS', company: 'ENTREPRISE' };
  const typeColors = { commodity: '#865220',   asset: '#625a4e', country: '#4a7a5c', company: '#91452d' };
  const color = typeColors[type] || '#625a4e';
  const label = typeLabels[type] || type.toUpperCase();

  const badge = `<span class="tr-tree-panel__badge" style="background:${color}22;color:${color}">${label}</span>`;

  let name = idVal;
  let pct  = null;
  let body = '';

  if (type === 'commodity') {
    const c = data.commodities.find(c => c.name === idVal);
    if (c) { name = c.name; pct = c.pct; }

    const assets = data.sankey_links
      .filter(l => l.source === nodeId && l.target.startsWith('asset:'))
      .map(l => {
        const aid = l.target.slice('asset:'.length);
        return data.assets.find(a => String(a.id) === aid);
      })
      .filter(Boolean)
      .sort((a, b) => b.pct - a.pct);

    body = '<div class="tr-tree-panel__section">Actifs</div>' +
      (assets.length
        ? assets.map(a => `<div class="tr-tree-panel__row"><span>${escHtml(a.name)}</span><b>${(a.pct * 100).toFixed(1)} %</b></div>`).join('')
        : '<div class="tr-tree-panel__row"><span>—</span></div>');

  } else if (type === 'asset') {
    const a = data.assets.find(a => String(a.id) === idVal);
    if (a) { name = a.name; pct = a.pct; }

    const countryLink = data.sankey_links.find(l => l.source === nodeId && l.target.startsWith('country:'));
    const countryName = countryLink ? countryLink.target.slice('country:'.length) : '—';

    const commodities = data.sankey_links
      .filter(l => l.target === nodeId && l.source.startsWith('commodity:'))
      .map(l => l.source.slice('commodity:'.length));

    body = `<div class="tr-tree-panel__row"><span>Pays</span><b>${escHtml(countryName)}</b></div>` +
      '<div class="tr-tree-panel__section">Commodités</div>' +
      (commodities.length
        ? commodities.map(c => `<div class="tr-tree-panel__row"><span>${escHtml(c)}</span></div>`).join('')
        : '<div class="tr-tree-panel__row"><span>—</span></div>');

  } else if (type === 'country') {
    const c = data.countries.find(c => c.name === idVal);
    if (c) { name = c.name; pct = c.pct; }

    const assets = data.sankey_links
      .filter(l => l.target === nodeId && l.source.startsWith('asset:'))
      .map(l => {
        const aid = l.source.slice('asset:'.length);
        return data.assets.find(a => String(a.id) === aid);
      })
      .filter(Boolean)
      .sort((a, b) => b.pct - a.pct);

    body = '<div class="tr-tree-panel__section">Actifs</div>' +
      (assets.length
        ? assets.map(a => `<div class="tr-tree-panel__row"><span>${escHtml(a.name)}</span><b>${(a.pct * 100).toFixed(1)} %</b></div>`).join('')
        : '<div class="tr-tree-panel__row"><span>—</span></div>');

  } else if (type === 'company') {
    name = data.company_name;
    pct  = 1.0;
    body = `<div class="tr-tree-panel__row"><span>Pays</span><b>${data.countries.length}</b></div>` +
           `<div class="tr-tree-panel__row"><span>Actifs</span><b>${data.assets.length}</b></div>` +
           `<div class="tr-tree-panel__row"><span>Commodités</span><b>${data.commodities.length}</b></div>`;
  }

  const pctLine = pct !== null
    ? `<div class="tr-tree-panel__row"><span>Impact</span><b>${pct === 1.0 ? '100' : (pct * 100).toFixed(1)} %</b></div>`
    : '';

  return `<h4 class="tr-tree-panel__title">${escHtml(name)}</h4>${badge}${pctLine}${body}`;
}
