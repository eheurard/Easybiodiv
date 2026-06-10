const ME_COMPANY_KEY = 'selected-company-id';

document.addEventListener('DOMContentLoaded', () => {
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


function renderTransitionRisk(data) {
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

  if (!data.sankey_links || data.sankey_links.length === 0) {
    svg.setAttribute('viewBox', '0 0 820 120');
    svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" font-size="13" font-family="Inter,sans-serif" fill="#87736d">Aucune donnée à afficher.</text>';
    return;
  }

  // Build node map: key → {label, col, pct, y}
  const nodes = {};
  data.commodities.forEach(c => {
    nodes[`commodity:${c.name}`] = { label: c.name, col: 0, pct: c.pct };
  });
  data.assets.forEach(a => {
    nodes[`asset:${a.id}`] = { label: a.name, col: 1, pct: a.pct };
  });
  data.countries.forEach(c => {
    nodes[`country:${c.name}`] = { label: c.name, col: 2, pct: c.pct };
  });
  nodes[`company:${data.company_id}`] = { label: data.company_name, col: 3, pct: 1.0 };

  // Sort each column by pct descending
  const cols = [[], [], [], []];
  Object.entries(nodes).forEach(([id, n]) => { n.id = id; cols[n.col].push(n); });
  cols.forEach(col => col.sort((a, b) => b.pct - a.pct));

  // Compute y positions — center each column vertically
  const maxNodes = Math.max(...cols.map(c => c.length));
  const H = TREE_TOP + maxNodes * (TREE_NODE_H + TREE_NODE_GAP) + 10;

  cols.forEach(colNodes => {
    const colH = colNodes.length * (TREE_NODE_H + TREE_NODE_GAP) - TREE_NODE_GAP;
    let y = TREE_TOP + Math.max(0, (H - TREE_TOP - 10 - colH) / 2);
    colNodes.forEach(n => { n.y = y; y += TREE_NODE_H + TREE_NODE_GAP; });
  });

  const W = TREE_COL_X[3] + TREE_NODE_W + 20;

  // Render order: headers → links → node rects → labels
  let headers = '';
  TREE_COL_X.forEach((x, i) => {
    headers += `<text x="${x}" y="16" font-size="8" font-family="Inter,sans-serif" fill="#87736d" font-weight="700" letter-spacing="0.08em">${escHtml(TREE_COL_LABELS[i])}</text>`;
  });

  let paths = '';
  data.sankey_links.forEach(link => {
    const src = nodes[link.source];
    const tgt = nodes[link.target];
    if (!src || !tgt) return;
    const x1 = TREE_COL_X[src.col] + TREE_NODE_W;
    const y1 = src.y + TREE_NODE_H / 2;
    const x2 = TREE_COL_X[tgt.col];
    const y2 = tgt.y + TREE_NODE_H / 2;
    const mx = (x1 + x2) / 2;
    const sw = Math.max(1, link.value * 20);
    paths += `<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" fill="none" stroke="${TREE_COLORS[src.col]}" stroke-width="${sw}" stroke-opacity="0.25"/>`;
  });

  let nodeRects = '';
  let labels = '';
  const maxLen = 14;
  Object.values(nodes).forEach(n => {
    const x = TREE_COL_X[n.col];
    const shortLabel = n.label.length > maxLen ? n.label.slice(0, maxLen - 1) + '…' : n.label;
    const pctText = n.col === 3 ? '100 %' : `${(n.pct * 100).toFixed(1)} %`;
    nodeRects += `<rect x="${x}" y="${n.y}" width="${TREE_NODE_W}" height="${TREE_NODE_H}" rx="4" fill="${TREE_COLORS[n.col]}"/>`;
    labels += `<text x="${x + TREE_NODE_W / 2}" y="${n.y + 12}" text-anchor="middle" font-size="10" font-family="Inter,sans-serif" fill="white" font-weight="600">${escHtml(shortLabel)}</text>`;
    labels += `<text x="${x + TREE_NODE_W / 2}" y="${n.y + 25}" text-anchor="middle" font-size="9" font-family="Inter,sans-serif" fill="rgba(255,255,255,0.75)">${pctText}</text>`;
  });

  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.innerHTML = headers + paths + nodeRects + labels;
}
