# Tree Interactivity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre le graphe "Répartition hiérarchique" interactif — clic sur un nœud met en évidence ses connexions et ouvre un panneau latéral ; deux filtres (seuil d'impact, commodité) déclenchent un re-rendu.

**Architecture:** Refacto de `renderTree()` vers du DOM natif SVG (`createElementNS`) afin d'attacher les event listeners à la création. Un objet `treeState` module-level pilote la sélection et les filtres. Les filtres déclenchent un re-rendu complet ; le clic met à jour les opacités sans re-rendu.

**Tech Stack:** Django templates, SVG vanilla JS (`document.createElementNS`), CSS vanilla. Aucune dépendance nouvelle.

---

## File Map

| Fichier | Rôle des changements |
|---|---|
| `dashboard/templates/dashboard/mesure_empreinte.html` | Ajouter barre filtres, wrapper `.tr-tree-body`, div panneau |
| `dashboard/static/dashboard/js/mesure_empreinte.js` | `treeState`, `currentData`, `initTreeFilters()`, `buildCommodityPills()`, refacto `renderTree()`, `handleNodeClick()`, `applyTreeHighlight()`, `resetTreeHighlight()`, `buildPanelHTML()`, `showTreePanel()`, `hideTreePanel()` |
| `dashboard/static/dashboard/css/style.css` | Styles filtres, panneau, pills commodité |

---

## Task 1: Structure HTML — barre de filtres + panneau latéral

**Files:**
- Modify: `dashboard/templates/dashboard/mesure_empreinte.html:77-83`

- [ ] **Step 1 : Remplacer le bloc `.tr-tree-card` existant**

Remplacer dans `mesure_empreinte.html` (bloc lignes 77-83) :

```html
  <!-- Tree diagram -->
  <div class="card tr-tree-card">
    <div class="label-caps tr-tree-card__title">Répartition hiérarchique</div>
    <div class="tr-tree-wrap">
      <svg id="tree-svg" class="tr-tree-svg" role="img" aria-label="Diagramme arborescent de l'impact"></svg>
    </div>
  </div>
```

Par :

```html
  <!-- Tree diagram -->
  <div class="card tr-tree-card">
    <div class="label-caps tr-tree-card__title">Répartition hiérarchique</div>

    <div class="tr-tree-filters">
      <div class="tr-tree-filter-group">
        <label class="label-caps" for="tree-threshold">Seuil</label>
        <input type="range" id="tree-threshold" min="0" max="30" value="0" step="1">
        <span id="tree-threshold-label">≥ 0 %</span>
      </div>
      <div class="tr-tree-filter-sep"></div>
      <div class="tr-tree-filter-group" id="tree-commodity-filters">
        <span class="label-caps">Commodité</span>
      </div>
    </div>

    <div class="tr-tree-body">
      <div class="tr-tree-wrap">
        <svg id="tree-svg" class="tr-tree-svg" role="img" aria-label="Diagramme arborescent de l'impact"></svg>
      </div>
      <div class="tr-tree-panel" id="tree-panel" hidden>
        <button class="tr-tree-panel__close" id="tree-panel-close" aria-label="Fermer le panneau">×</button>
        <div id="tree-panel-content"></div>
      </div>
    </div>
  </div>
```

- [ ] **Step 2 : Vérifier que la page se charge sans erreur**

Démarrer le serveur :
```powershell
.\venv\Scripts\Activate.ps1
python manage.py runserver
```
Naviguer vers la page `mesure_empreinte`. La carte "Répartition hiérarchique" doit s'afficher avec la barre de filtres vide (le slider est visible) et le graphe SVG en dessous. Aucune erreur console.

- [ ] **Step 3 : Commit**

```bash
git add dashboard/templates/dashboard/mesure_empreinte.html
git commit -m "feat(tree): add filter bar and side panel HTML structure"
```

---

## Task 2: CSS — filtres, panneau, pills

**Files:**
- Modify: `dashboard/static/dashboard/css/style.css` (ajouter après le bloc `/* ─── Tree diagram ─── */`)

- [ ] **Step 1 : Ajouter les styles**

Localiser la fin du bloc `/* ─── Tree diagram ─── */` dans `style.css` (après `.tr-tree-svg`) et ajouter :

```css
/* ─── Tree — filter bar ──────────────────────────────────────────────────── */
.tr-tree-filters {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--color-border, #e8e0db);
  flex-wrap: wrap;
}

.tr-tree-filter-group {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-muted, #625a4e);
}

.tr-tree-filter-group .label-caps {
  margin-bottom: 0;
}

.tr-tree-filter-sep {
  width: 1px;
  height: 18px;
  background: var(--color-border, #e8e0db);
  flex-shrink: 0;
}

.tr-tree-commodity-pill {
  background: #e8e0db;
  color: #625a4e;
  border: none;
  border-radius: 12px;
  padding: 3px 10px;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s, color 0.15s;
}

.tr-tree-commodity-pill--active {
  background: #865220;
  color: white;
}

.tr-tree-commodity-pill--active[data-commodity=""] {
  background: #4a7a5c;
}

/* ─── Tree — body (svg + panel side by side) ─────────────────────────────── */
.tr-tree-body {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  min-height: 0;
}

.tr-tree-body .tr-tree-wrap {
  flex: 1 1 auto;
  min-width: 0;
}

/* ─── Tree — side panel ──────────────────────────────────────────────────── */
.tr-tree-panel {
  width: 180px;
  flex-shrink: 0;
  border-left: 1px solid var(--color-border, #e8e0db);
  padding: 14px 12px;
  font-size: 11px;
  color: #2d2520;
  position: relative;
}

.tr-tree-panel__close {
  position: absolute;
  top: 8px;
  right: 10px;
  background: none;
  border: none;
  font-size: 18px;
  color: #b09e98;
  cursor: pointer;
  line-height: 1;
  padding: 0;
}

.tr-tree-panel__close:hover {
  color: #625a4e;
}

.tr-tree-panel__title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 700;
  color: #2d2520;
  padding-right: 20px;
}

.tr-tree-panel__badge {
  display: inline-block;
  border-radius: 4px;
  padding: 2px 7px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.06em;
  margin-bottom: 10px;
}

.tr-tree-panel__section {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: #87736d;
  margin: 10px 0 4px;
  padding-top: 8px;
  border-top: 1px solid #f0e8e4;
}

.tr-tree-panel__row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 11px;
  color: #625a4e;
  margin-bottom: 3px;
}

.tr-tree-panel__row b {
  color: #2d2520;
  font-weight: 600;
}
```

- [ ] **Step 2 : Vérifier visuellement**

Recharger la page. La barre de filtres doit être séparée du graphe par une ligne. Le panneau n'est pas visible (il est `hidden`). Pas d'erreur console.

- [ ] **Step 3 : Commit**

```bash
git add dashboard/static/dashboard/css/style.css
git commit -m "feat(tree): add CSS for filter bar, commodity pills, side panel"
```

---

## Task 3: État module + `initTreeFilters()` + mise à jour de `renderTransitionRisk()`

**Files:**
- Modify: `dashboard/static/dashboard/js/mesure_empreinte.js`

- [ ] **Step 1 : Ajouter les variables module-level**

En haut de `mesure_empreinte.js`, juste après la ligne `const ME_COMPANY_KEY = 'selected-company-id';`, ajouter :

```js
let currentData = null;

const treeState = {
  selected: null,   // string node id ou null
  threshold: 0,     // float 0–1 (ex. 0.05 = 5 %)
  commodity: null,  // string nom commodité ou null = toutes
};
```

- [ ] **Step 2 : Ajouter `initTreeFilters()`**

Ajouter cette fonction après `initTrCombobox` (avant `renderTransitionRisk`) :

```js
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
```

- [ ] **Step 3 : Mettre à jour `renderTransitionRisk()` et l'écouteur DOMContentLoaded**

Dans `renderTransitionRisk(data)`, ajouter `currentData = data;` comme première ligne du corps de la fonction, et appeler `buildCommodityPills(data)` juste avant `renderTree(data)` :

```js
function renderTransitionRisk(data) {
  currentData = data;  // ← ajouter

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
  buildCommodityPills(data);  // ← ajouter (avant renderTree)
  renderTree(data);
}
```

Dans le bloc `document.addEventListener('DOMContentLoaded', ...)`, ajouter l'appel `initTreeFilters()` avant le code existant :

```js
document.addEventListener('DOMContentLoaded', () => {
  initTreeFilters();  // ← ajouter

  const companiesEl = document.getElementById('companies-data');
  // ... reste inchangé
});
```

- [ ] **Step 4 : Vérifier**

Recharger la page. Déplacer le slider → la valeur "≥ X %" doit se mettre à jour dans le label. Aucune erreur console (la fonction `buildCommodityPills` n'existe pas encore, ça va provoquer une erreur — c'est normal à ce stade ; on peut commenter l'appel temporairement pour tester).

- [ ] **Step 5 : Commit**

```bash
git add dashboard/static/dashboard/js/mesure_empreinte.js
git commit -m "feat(tree): add treeState, currentData, initTreeFilters"
```

---

## Task 4: `buildCommodityPills()` — pills dynamiques

**Files:**
- Modify: `dashboard/static/dashboard/js/mesure_empreinte.js`

- [ ] **Step 1 : Ajouter `buildCommodityPills()`**

Ajouter cette fonction après `initTreeFilters()` :

```js
function buildCommodityPills(data) {
  const container = document.getElementById('tree-commodity-filters');
  if (!container) return;

  // Réinitialiser le filtre commodité (pas le slider qui est géré séparément)
  treeState.commodity = null;

  const names = data.commodities.map(c => c.name);

  // Reconstruire les pills
  // On garde le <span class="label-caps"> et on ajoute les boutons
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

      // Mise à jour visuelle des pills
      container.querySelectorAll('.tr-tree-commodity-pill').forEach(b =>
        b.classList.remove('tr-tree-commodity-pill--active')
      );
      btn.classList.add('tr-tree-commodity-pill--active');

      hideTreePanel();
      if (currentData) renderTree(currentData);
    });
  });
}
```

- [ ] **Step 2 : Vérifier**

Recharger la page avec une entreprise ayant des données. Les pills de commodité doivent apparaître dans la barre de filtres. Cliquer sur une commodité doit mettre la pill en évidence couleur terre. Aucune erreur console.

- [ ] **Step 3 : Commit**

```bash
git add dashboard/static/dashboard/js/mesure_empreinte.js
git commit -m "feat(tree): add buildCommodityPills with click handlers"
```

---

## Task 5: Refacto `renderTree()` — DOM natif + filtrage

**Files:**
- Modify: `dashboard/static/dashboard/js/mesure_empreinte.js`

- [ ] **Step 1 : Ajouter les variables module-level pour les refs SVG courantes**

Juste après les constantes `TREE_*` existantes, ajouter :

```js
const SVG_NS = 'http://www.w3.org/2000/svg';
let _treeNodeEls  = {};  // id → <g> element courant
let _treeLinkEls  = [];  // [{el, src, tgt}] courant
```

- [ ] **Step 2 : Remplacer entièrement `renderTree()`**

Supprimer la fonction `renderTree()` existante et la remplacer par :

```js
function renderTree(data) {
  const svg = document.getElementById('tree-svg');
  if (!svg) return;

  // Reset refs
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

  // ── 1. Construire tous les nœuds ──────────────────────────────────────────
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

  // ── 2. Appliquer les filtres ───────────────────────────────────────────────
  const { threshold, commodity } = treeState;

  // Filtre seuil (le nœud company est toujours visible)
  let visibleIds = new Set(
    Object.entries(allNodes)
      .filter(([id, n]) => n.col === 3 || n.pct >= threshold)
      .map(([id]) => id)
  );

  // Filtre commodité (propagation transitive commodity → assets → countries → company)
  if (commodity) {
    const commodityId = `commodity:${commodity}`;
    if (visibleIds.has(commodityId)) {
      const connected = new Set([commodityId, `company:${data.company_id}`]);
      // commodity → assets
      data.sankey_links.forEach(link => {
        if (link.source === commodityId && visibleIds.has(link.target))
          connected.add(link.target);
      });
      // assets liés → countries
      data.sankey_links.forEach(link => {
        if (connected.has(link.source) && link.source.startsWith('asset:') && visibleIds.has(link.target))
          connected.add(link.target);
      });
      visibleIds = connected;
    } else {
      // La commodité est sous le seuil : ne garder que company
      visibleIds = new Set([`company:${data.company_id}`]);
    }
  }

  // Links visibles : source ET cible présentes
  const visibleLinks = data.sankey_links.filter(
    l => visibleIds.has(l.source) && visibleIds.has(l.target)
  );

  // Nœuds visibles avec leur id
  const nodes = {};
  Object.entries(allNodes).forEach(([id, n]) => {
    if (visibleIds.has(id)) nodes[id] = { ...n, id };
  });

  // ── 3. Disposition (même logique que l'original) ───────────────────────────
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

  // ── 4. Vider le SVG ───────────────────────────────────────────────────────
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  // ── 5. En-têtes de colonnes ───────────────────────────────────────────────
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

  // ── 6. Liens (z-order bas) ────────────────────────────────────────────────
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

  // ── 7. Nœuds (z-order haut) ───────────────────────────────────────────────
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

    // Event listener
    g.addEventListener('click', () => handleNodeClick(n.id, data));

    gNodes.appendChild(g);
    _treeNodeEls[n.id] = g;
  });
  svg.appendChild(gNodes);

  // ── 8. Compression des labels débordants ─────────────────────────────────
  const availW = TREE_NODE_W - 12;
  svg.querySelectorAll('.tree-lbl').forEach(t => {
    if (t.getComputedTextLength && t.getComputedTextLength() > availW) {
      t.setAttribute('textLength', availW);
      t.setAttribute('lengthAdjust', 'spacingAndGlyphs');
    }
  });
}
```

- [ ] **Step 3 : Vérifier**

Recharger la page. Le graphe doit s'afficher identiquement à avant (sans interactivité encore). Déplacer le slider : les nœuds sous le seuil doivent disparaître. Cliquer sur une pill commodité : seuls les nœuds connectés à cette commodité doivent rester. Aucune erreur console.

- [ ] **Step 4 : Commit**

```bash
git add dashboard/static/dashboard/js/mesure_empreinte.js
git commit -m "feat(tree): rewrite renderTree() with DOM native SVG + threshold/commodity filtering"
```

---

## Task 6: Sélection par clic + mise en évidence

**Files:**
- Modify: `dashboard/static/dashboard/js/mesure_empreinte.js`

- [ ] **Step 1 : Ajouter `handleNodeClick()`, `applyTreeHighlight()`, `resetTreeHighlight()`**

Ajouter ces trois fonctions après `renderTree()` :

```js
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
  // Nœuds directement reliés à nodeId par un lien
  const connectedIds = new Set([nodeId]);
  _treeLinkEls.forEach(({ src, tgt }) => {
    if (src === nodeId) connectedIds.add(tgt);
    if (tgt === nodeId) connectedIds.add(src);
  });

  // Opacité des groupes nœuds
  Object.entries(_treeNodeEls).forEach(([id, g]) => {
    g.style.opacity = connectedIds.has(id) ? '1' : '0.15';
  });

  // Opacité des liens
  _treeLinkEls.forEach(({ el, src, tgt }) => {
    const active = src === nodeId || tgt === nodeId;
    el.setAttribute('stroke-opacity', active ? '0.9' : '0.06');
  });
}

function resetTreeHighlight() {
  Object.values(_treeNodeEls).forEach(g => { g.style.opacity = '1'; });
  _treeLinkEls.forEach(({ el }) => { el.setAttribute('stroke-opacity', '0.25'); });
}
```

- [ ] **Step 2 : Vérifier**

Recharger la page. Cliquer sur un nœud (ex. un pays) : les nœuds non connectés doivent passer à 15 % d'opacité, les liens connectés doivent ressortir clairement. Recliquer sur le même nœud : tout revient à l'état normal. Aucune erreur console.

- [ ] **Step 3 : Commit**

```bash
git add dashboard/static/dashboard/js/mesure_empreinte.js
git commit -m "feat(tree): add node click selection and connection highlighting"
```

---

## Task 7: Panneau latéral — affichage et contenu

**Files:**
- Modify: `dashboard/static/dashboard/js/mesure_empreinte.js`

- [ ] **Step 1 : Ajouter `hideTreePanel()`, `showTreePanel()`, `buildPanelHTML()`**

Ajouter ces fonctions après `resetTreeHighlight()` :

```js
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
```

- [ ] **Step 2 : Vérifier le panneau pour chaque type de nœud**

Recharger la page.
- Cliquer sur une **commodité** → le panneau affiche le nom, badge "COMMODITÉ", impact %, liste des actifs liés.
- Cliquer sur un **actif** → badge "ACTIF", impact %, pays, liste des commodités.
- Cliquer sur un **pays** → badge "PAYS", impact %, liste des actifs.
- Cliquer sur la **company** → badge "ENTREPRISE", 100 %, compteurs pays/actifs/commodités.
- Cliquer sur × → panneau fermé, opacités réinitialisées.
- Changer de société via le combobox → panneau fermé, slider remis à 0, pills regénérées.

- [ ] **Step 3 : Commit**

```bash
git add dashboard/static/dashboard/js/mesure_empreinte.js
git commit -m "feat(tree): add side panel with per-node-type detail content"
```

---

## Task 8: QA finale + nettoyage

**Files:**
- Modify: `dashboard/static/dashboard/js/mesure_empreinte.js` (si corrections nécessaires)

- [ ] **Step 1 : Test scénario complet**

1. Choisir une entreprise avec plusieurs commodités, actifs et pays.
2. Slider seuil à 10 % → les nœuds sous 10 % disparaissent + leurs liens.
3. Cliquer sur une pill commodité → seul le sous-graphe de cette commodité est visible.
4. Cliquer sur un pays visible → highlight + panneau s'ouvre avec les bons actifs.
5. Recliquer sur le même pays → désélection, tout revient à l'état normal.
6. Cliquer × dans le panneau → même effet.
7. Changer de société → slider remis à 0, filtres réinitialisés, panneau fermé.
8. Aucune erreur console dans tous les scénarios.

- [ ] **Step 2 : Vérifier qu'aucun code mort n'a été laissé**

Vérifier dans `mesure_empreinte.js` qu'il n'y a plus de code de l'ancienne `renderTree()` (l'ancienne générait des strings HTML et appelait `svg.innerHTML`). La nouvelle fonction utilise uniquement `createElementNS` et `appendChild`.

- [ ] **Step 3 : Commit final si des corrections ont été apportées**

```bash
git add dashboard/static/dashboard/js/mesure_empreinte.js
git commit -m "fix(tree): QA corrections post-implémentation"
```
