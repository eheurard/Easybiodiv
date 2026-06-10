# Diagramme arborescent — Mesure d'empreinte — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un diagramme hiérarchique SVG (gauche → droite, Commodités → Actifs → Pays → Company) sous le Sankey existant dans la page "Mesure d'empreinte", sans modification backend.

**Architecture:** Nouvelle carte `.tr-tree-card` ajoutée au template HTML après la carte Sankey. Une fonction `renderTree(data)` en JS vanilla construit un SVG avec 4 colonnes de nœuds uniformes reliés par des courbes de Bézier ; épaisseur des lignes proportionnelle à `link.value`. Les données (`sankey_links`, `commodities`, `assets`, `countries`) sont déjà renvoyées par l'API existante.

**Tech Stack:** Django templates, SVG pur, JS vanilla (pas de dépendances), CSS3.

**Spec:** `docs/superpowers/specs/2026-06-11-tree-diagram-mesure-empreinte-design.md`

---

## Fichiers modifiés

| Fichier | Rôle |
|---|---|
| `dashboard/static/dashboard/css/style.css` | +4 règles CSS pour `.tr-tree-card` |
| `dashboard/templates/dashboard/mesure_empreinte.html` | +bloc HTML nouvelle carte arbre |
| `dashboard/static/dashboard/js/mesure_empreinte.js` | +`renderTree(data)` + appel depuis `renderTransitionRisk` |

---

## Task 1 — CSS : styles de la carte arbre

**Files:**
- Modify: `dashboard/static/dashboard/css/style.css` (après la section `/* ─── Sankey ───… */`, ligne ~1554)

- [ ] **Step 1 : Ajouter les règles CSS**

Dans `style.css`, à la suite du bloc `.tr-sankey-svg { … }` (ligne 1554), insérer :

```css

/* ─── Tree diagram ───────────────────────────────────────────────────────── */
.tr-tree-card {
  display: flex;
  flex-direction: column;
  margin-top: 1.5rem;
}

.tr-tree-card__title {
  margin-bottom: 4px;
}

.tr-tree-wrap {
  width: 100%;
  overflow-x: auto;
}

.tr-tree-svg {
  width: 100%;
  height: auto;
  min-width: 600px;
  display: block;
}
```

- [ ] **Step 2 : Commit**

```bash
git add dashboard/static/dashboard/css/style.css
git commit -m "style: add tr-tree-card CSS for hierarchy diagram"
```

---

## Task 2 — HTML : ajouter la carte dans le template

**Files:**
- Modify: `dashboard/templates/dashboard/mesure_empreinte.html`

- [ ] **Step 1 : Ajouter le bloc HTML**

Dans `mesure_empreinte.html`, après la carte Sankey existante (bloc `<!-- Sankey diagram -->`, qui se termine à `</div>` avant `</div>` de `.tr-page`), ajouter :

```html
  <!-- Tree diagram -->
  <div class="card tr-tree-card">
    <div class="label-caps tr-tree-card__title">Répartition hiérarchique</div>
    <div class="tr-tree-wrap">
      <svg id="tree-svg" class="tr-tree-svg" aria-label="Diagramme arborescent de l'impact"></svg>
    </div>
  </div>
```

Le fichier doit ressembler à ceci autour de cette zone :

```html
  <!-- Sankey diagram -->
  <div class="card tr-sankey-card">
    <div class="label-caps tr-sankey-card__title">Décomposition de l'impact</div>
    <div class="tr-sankey-wrap">
      <svg id="sankey-svg" class="tr-sankey-svg" aria-label="Diagramme Sankey de l'impact"></svg>
    </div>
  </div>

  <!-- Tree diagram -->
  <div class="card tr-tree-card">
    <div class="label-caps tr-tree-card__title">Répartition hiérarchique</div>
    <div class="tr-tree-wrap">
      <svg id="tree-svg" class="tr-tree-svg" aria-label="Diagramme arborescent de l'impact"></svg>
    </div>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 2 : Commit**

```bash
git add dashboard/templates/dashboard/mesure_empreinte.html
git commit -m "feat: add tree diagram card to mesure_empreinte template"
```

---

## Task 3 — JS : implémenter `renderTree(data)`

**Files:**
- Modify: `dashboard/static/dashboard/js/mesure_empreinte.js`

- [ ] **Step 1 : Ajouter les constantes en haut du fichier**

Après la ligne `const SANKEY_COLORS = […];` (ligne ~135), ajouter :

```js
const TREE_NODE_W = 100;
const TREE_NODE_H = 32;
const TREE_NODE_GAP = 14;
const TREE_COL_X = [20, 250, 470, 700];
const TREE_COL_LABELS = ['COMMODITÉS', 'ACTIFS', 'PAYS', 'COMPANY'];
const TREE_COLORS = ['#4a7a5c', '#625a4e', '#865220', '#91452d'];
const TREE_TOP = 28;
```

- [ ] **Step 2 : Ajouter l'appel à `renderTree` dans `renderTransitionRisk`**

Dans la fonction `renderTransitionRisk(data)` (ligne ~87), après l'appel `renderSankey(data);`, ajouter :

```js
  renderTree(data);
```

- [ ] **Step 3 : Ajouter la fonction `renderTree` à la fin du fichier**

Après la fonction `renderSankey` (fin du fichier, ligne ~275), ajouter :

```js

function renderTree(data) {
  const svg = document.getElementById('tree-svg');
  if (!svg) return;

  if (!data.sankey_links || data.sankey_links.length === 0) {
    svg.setAttribute('viewBox', '0 0 800 120');
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
    const pctText = n.col === 3 ? '100 %' : `${(n.pct * 100).toFixed(1)} %`;
    nodeRects += `<rect x="${x}" y="${n.y}" width="${TREE_NODE_W}" height="${TREE_NODE_H}" rx="4" fill="${TREE_COLORS[n.col]}"/>`;
    labels += `<text x="${x + TREE_NODE_W / 2}" y="${n.y + 12}" text-anchor="middle" font-size="10" font-family="Inter,sans-serif" fill="white" font-weight="600">${escHtml(shortLabel)}</text>`;
    labels += `<text x="${x + TREE_NODE_W / 2}" y="${n.y + 25}" text-anchor="middle" font-size="9" font-family="Inter,sans-serif" fill="rgba(255,255,255,0.75)">${pctText}</text>`;
  });

  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.innerHTML = headers + paths + nodeRects + labels;
}
```

- [ ] **Step 4 : Vérifier visuellement**

Lancer le serveur de développement :

```powershell
cd c:\Users\eloua\Documents\Easybiodiv
.\venv\Scripts\Activate.ps1
python manage.py runserver
```

Ouvrir `http://127.0.0.1:8000/` → aller sur la page "Mesure d'empreinte" → sélectionner une entreprise avec des données.

Vérifications attendues :
- Le nouveau diagramme "Répartition hiérarchique" apparaît **sous** le Sankey
- 4 colonnes visibles avec en-têtes COMMODITÉS / ACTIFS / PAYS / COMPANY
- Nœuds colorés par colonne (vert → brun foncé → brun orange → rouge brun)
- Lignes courbes entre les colonnes, plus épaisses pour les liens dominants
- Si aucune entreprise n'a de données : message "Aucune donnée à afficher."

- [ ] **Step 5 : Commit**

```bash
git add dashboard/static/dashboard/js/mesure_empreinte.js
git commit -m "feat: add renderTree() hierarchy diagram to mesure_empreinte page"
```
