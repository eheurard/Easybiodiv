# ESG Carbon Scope Stacked Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un bouton toggle dans le graphe "Tendance des émissions carbone" qui superpose des barres empilées par scope sur la ligne existante, avec un tooltip custom affichant valeur exacte et pourcentage par scope.

**Architecture:** Tout en frontend vanilla JS/CSS/HTML. L'API retourne déjà `historical[i].scopes` (dict scope→valeur), donc aucun changement backend. On modifie `esgRenderChart()` pour rendre des `<rect>` SVG empilés quand la variable d'état `esgScopeView` est `true`, et on ajoute un `<div>` tooltip positionné au `mousemove`.

**Tech Stack:** SVG natif, JS ES6 vanilla, CSS custom properties Django existantes

---

## Fichiers touchés

| Fichier | Rôle |
|---|---|
| `dashboard/static/dashboard/css/style.css` | Styles toggle button, barres, tooltip, légende |
| `dashboard/templates/dashboard/esg.html` | Bouton `#esg-scope-toggle` dans `.esg-chart__head` |
| `dashboard/static/dashboard/js/esg.js` | Variable d'état, barres SVG, tooltip, légende dynamique |

---

## Task 1: CSS — Styles pour bouton toggle, barres et tooltip

**Files:**
- Modify: `dashboard/static/dashboard/css/style.css` (après `.esg-chart__dot { fill: var(--color-primary); }`)

- [ ] **Step 1: Ajouter les nouveaux styles CSS**

Dans `style.css`, localise la ligne `.esg-chart__dot { fill: var(--color-primary); }` (ligne ~3138) et insère immédiatement après :

```css
.esg-chart__scope-btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border: 1px solid var(--color-outline); border-radius: 6px; background: transparent; color: var(--color-on-surface-variant); font-size: 12px; font-family: var(--font-family); cursor: pointer; transition: background .15s, color .15s, border-color .15s; white-space: nowrap; }
.esg-chart__scope-btn:hover { background: var(--color-surface-variant); }
.esg-chart__scope-btn[aria-pressed="true"] { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.esg-chart__bar { cursor: default; }
.esg-chart__tooltip { position: absolute; pointer-events: none; z-index: 10; background: var(--color-surface-container, #f4f4f4); border: 1px solid var(--color-outline-variant, #ccc); border-radius: 8px; padding: 10px 14px; font-size: 13px; color: var(--color-on-surface); box-shadow: 0 4px 16px rgba(0,0,0,.12); min-width: 180px; white-space: nowrap; }
.esg-chart__tooltip-year { font-weight: 600; margin-bottom: 6px; font-size: 14px; }
.esg-chart__tooltip-row { display: flex; align-items: center; gap: 8px; padding: 2px 0; }
.esg-chart__tooltip-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.esg-chart__tooltip-name { flex: 1; }
.esg-chart__tooltip-val { font-variant-numeric: tabular-nums; }
.esg-chart__tooltip-pct { color: var(--color-on-surface-variant); min-width: 42px; text-align: right; }
.esg-chart__tooltip-sep { border: none; border-top: 1px solid var(--color-outline-variant, #ccc); margin: 6px 0; }
.esg-chart__tooltip-total { display: flex; gap: 8px; font-weight: 600; }
.esg-chart__legend-dot { width: 12px; height: 12px; border-radius: 2px; flex-shrink: 0; }
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/static/dashboard/css/style.css
git commit -m "style(esg): add scope toggle button, stacked bar and tooltip CSS"
```

---

## Task 2: HTML — Bouton toggle dans l'en-tête du graphe

**Files:**
- Modify: `dashboard/templates/dashboard/esg.html`

- [ ] **Step 1: Ajouter le bouton toggle**

Dans `esg.html`, localise le bloc `.esg-chart__head`. La div `.esg-chart__legend` est son dernier enfant direct. Ajoute le bouton **après** cette div, à l'intérieur de `.esg-chart__head` :

Avant :
```html
          <div class="esg-chart__legend">
              <span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--solid"></span>Historique</span>
              <span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--dashed"></span>Projection 2030</span>
            </div>
          </div>
```

Après :
```html
          <div class="esg-chart__legend">
              <span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--solid"></span>Historique</span>
              <span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--dashed"></span>Projection 2030</span>
            </div>
            <button id="esg-scope-toggle" class="esg-chart__scope-btn" aria-pressed="false" title="Afficher les émissions par scope">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <rect x="1" y="9" width="3" height="4" rx="0.5" fill="currentColor"/>
                <rect x="5.5" y="5" width="3" height="8" rx="0.5" fill="currentColor"/>
                <rect x="10" y="2" width="3" height="11" rx="0.5" fill="currentColor"/>
              </svg>
              Par scope
            </button>
          </div>
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/templates/dashboard/esg.html
git commit -m "feat(esg): add scope toggle button in carbon chart header"
```

---

## Task 3: JS — Variable d'état, toggle handler, fonctions légende

**Files:**
- Modify: `dashboard/static/dashboard/js/esg.js`

- [ ] **Step 1: Ajouter la variable d'état et la palette de couleurs**

En haut de `esg.js`, après `const ESG_STATE = { data: null };` (ligne 5), ajoute :

```js
let esgScopeView = false;
const SCOPE_COLORS = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948'];
```

- [ ] **Step 2: Brancher le toggle handler dans DOMContentLoaded**

Dans le listener `DOMContentLoaded` (ligne 7), après l'appel `esgInitThemeTabs();` (ligne 15), ajoute :

```js
  const scopeToggle = document.getElementById('esg-scope-toggle');
  if (scopeToggle) {
    scopeToggle.addEventListener('click', () => {
      esgScopeView = !esgScopeView;
      scopeToggle.setAttribute('aria-pressed', String(esgScopeView));
      if (ESG_STATE.data) esgRenderChart(ESG_STATE.data.carbon);
    });
  }
```

- [ ] **Step 3: Ajouter esgUpdateLegend et esgResetLegend**

Ajoute ces deux fonctions à la fin de `esg.js`, juste avant `function escHtml(str)` :

```js
function esgUpdateLegend(allScopes, scopeColorMap) {
  const legendEl = document.querySelector('.esg-chart__legend');
  if (!legendEl) return;
  legendEl.innerHTML =
    allScopes.map(scope =>
      '<span class="esg-chart__legend-item">' +
      '<span class="esg-chart__legend-dot" style="background:' + scopeColorMap[scope] + '"></span>' +
      escHtml(scope) +
      '</span>'
    ).join('') +
    '<span class="esg-chart__legend-item" style="opacity:.5">' +
    '<span class="esg-chart__line esg-chart__line--solid"></span>Historique' +
    '</span>' +
    '<span class="esg-chart__legend-item" style="opacity:.5">' +
    '<span class="esg-chart__line esg-chart__line--dashed"></span>Projection 2030' +
    '</span>';
}


function esgResetLegend() {
  const legendEl = document.querySelector('.esg-chart__legend');
  if (!legendEl) return;
  legendEl.innerHTML =
    '<span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--solid"></span>Historique</span>' +
    '<span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--dashed"></span>Projection 2030</span>';
}
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/static/dashboard/js/esg.js
git commit -m "feat(esg): add scope view state, toggle handler and legend helpers"
```

---

## Task 4: JS — esgRenderChart (barres) + esgInitChartTooltip (tooltip)

Ces deux fonctions sont interdépendantes (`esgRenderChart` appelle `esgInitChartTooltip`) et sont implémentées ensemble.

**Files:**
- Modify: `dashboard/static/dashboard/js/esg.js`

- [ ] **Step 1: Remplacer esgRenderChart**

Remplace la fonction `esgRenderChart` existante (lignes 89–178 dans l'original) par la version complète suivante :

```js
function esgRenderChart(carbon) {
  const canvas = document.getElementById('esg-chart-canvas');
  const empty = document.getElementById('esg-chart-empty');
  if (!canvas) return;

  canvas.querySelectorAll('svg').forEach(s => s.remove());

  const hist = carbon.historical || [];
  if (!hist.length) {
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;

  const proj = carbon.projection || [];
  const allYears = hist.map(h => h.year).concat(proj.map(p => p.year));
  const allTotals = hist.map(h => h.total).concat(proj.map(p => p.total));
  const minYear = Math.min(...allYears);
  const maxYear = Math.max(...allYears);
  const maxVal = Math.max(...allTotals, 1);

  const W = 1000, H = 320;
  const padL = 56, padR = 16, padT = 16, padB = 32;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('class', 'esg-chart__svg');

  const xOf = yr => padL + (maxYear === minYear ? 0 : (yr - minYear) / (maxYear - minYear) * plotW);
  const yOf = v => padT + plotH - (v / maxVal) * plotH;

  // Grid lines + Y axis labels
  for (let i = 0; i <= 4; i++) {
    const val = maxVal * i / 4;
    const y = yOf(val);
    const line = document.createElementNS(NS, 'line');
    line.setAttribute('x1', padL); line.setAttribute('x2', W - padR);
    line.setAttribute('y1', y); line.setAttribute('y2', y);
    line.setAttribute('class', 'esg-chart__grid');
    svg.appendChild(line);
    const label = document.createElementNS(NS, 'text');
    label.setAttribute('x', padL - 8); label.setAttribute('y', y + 4);
    label.setAttribute('text-anchor', 'end');
    label.setAttribute('class', 'esg-chart__axis-label');
    label.textContent = esgFmtNum(Math.round(val));
    svg.appendChild(label);
  }

  // X axis labels
  const xYears = hist.map(h => h.year);
  if (proj.length) xYears.push(proj[proj.length - 1].year);
  xYears.forEach(yr => {
    const label = document.createElementNS(NS, 'text');
    label.setAttribute('x', xOf(yr)); label.setAttribute('y', H - 10);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('class', 'esg-chart__axis-label');
    label.textContent = yr;
    svg.appendChild(label);
  });

  // Stacked bars (scope view) — drawn before the line so line appears on top
  let allScopes = [];
  let scopeColorMap = {};
  if (esgScopeView) {
    allScopes = [...new Set(hist.flatMap(h => Object.keys(h.scopes || {})))].sort();
    allScopes.forEach((s, i) => { scopeColorMap[s] = SCOPE_COLORS[i % SCOPE_COLORS.length]; });
    const barWidth = Math.min(plotW / Math.max(hist.length, 1) * 0.6, 60);
    const barBottom = yOf(0);
    hist.forEach(h => {
      let cumY = barBottom;
      allScopes.forEach(scope => {
        const val = (h.scopes && h.scopes[scope]) || 0;
        if (val <= 0) return;
        const barH = (val / maxVal) * plotH;
        const rect = document.createElementNS(NS, 'rect');
        rect.setAttribute('x', xOf(h.year) - barWidth / 2);
        rect.setAttribute('y', cumY - barH);
        rect.setAttribute('width', barWidth);
        rect.setAttribute('height', barH);
        rect.setAttribute('fill', scopeColorMap[scope]);
        rect.setAttribute('opacity', '0.75');
        rect.setAttribute('class', 'esg-chart__bar');
        svg.appendChild(rect);
        cumY -= barH;
      });
    });
    esgUpdateLegend(allScopes, scopeColorMap);
  } else {
    esgResetLegend();
  }

  // Historical line (on top of bars)
  const histPath = hist.map((h, i) => (i ? 'L' : 'M') + xOf(h.year) + ',' + yOf(h.total)).join(' ');
  const histLine = document.createElementNS(NS, 'path');
  histLine.setAttribute('d', histPath);
  histLine.setAttribute('class', 'esg-chart__path esg-chart__path--hist');
  svg.appendChild(histLine);

  // Projection line
  if (proj.length) {
    const projPath = proj.map((p, i) => (i ? 'L' : 'M') + xOf(p.year) + ',' + yOf(p.total)).join(' ');
    const projLine = document.createElementNS(NS, 'path');
    projLine.setAttribute('d', projPath);
    projLine.setAttribute('class', 'esg-chart__path esg-chart__path--proj');
    svg.appendChild(projLine);
  }

  // Dots — title attribute removed; custom tooltip handles hover
  hist.forEach(h => {
    const dot = document.createElementNS(NS, 'circle');
    dot.setAttribute('cx', xOf(h.year)); dot.setAttribute('cy', yOf(h.total));
    dot.setAttribute('r', 4);
    dot.setAttribute('class', 'esg-chart__dot');
    svg.appendChild(dot);
  });

  canvas.appendChild(svg);

  esgInitChartTooltip(canvas, svg, hist, proj, carbon.unit, allScopes, scopeColorMap, xOf);
}
```

- [ ] **Step 2: Ajouter esgInitChartTooltip**

Ajoute cette fonction immédiatement **après** `esgRenderChart`, avant `esgRenderFeatured` :

```js
function esgInitChartTooltip(canvas, svg, hist, proj, unit, allScopes, scopeColorMap, xOf) {
  let tip = document.getElementById('esg-chart-tooltip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'esg-chart-tooltip';
    tip.className = 'esg-chart__tooltip';
    tip.setAttribute('hidden', '');
    canvas.appendChild(tip);
  }

  const projPoints = proj.map(p => ({ year: p.year, total: p.total, scopes: {}, isProj: true }));
  const allPoints = hist.map(h => Object.assign({}, h, { isProj: false })).concat(projPoints);
  const unitStr = unit || 'tCO2e';

  svg.addEventListener('mousemove', e => {
    const svgRect = svg.getBoundingClientRect();
    const canvasRect = canvas.getBoundingClientRect();
    const mouseX = (e.clientX - svgRect.left) * (1000 / svgRect.width);

    let nearest = allPoints[0];
    let minDist = Infinity;
    allPoints.forEach(p => {
      const d = Math.abs(xOf(p.year) - mouseX);
      if (d < minDist) { minDist = d; nearest = p; }
    });

    const scopes = nearest.scopes || {};
    const total = nearest.total;
    let html = '<div class="esg-chart__tooltip-year">' + nearest.year + '</div>';

    if (esgScopeView && !nearest.isProj && allScopes.length) {
      allScopes.forEach(scope => {
        const val = scopes[scope] || 0;
        if (val <= 0) return;
        const pct = total > 0 ? (val / total * 100).toFixed(1) : '0.0';
        html +=
          '<div class="esg-chart__tooltip-row">' +
          '<span class="esg-chart__tooltip-dot" style="background:' + scopeColorMap[scope] + '"></span>' +
          '<span class="esg-chart__tooltip-name">' + escHtml(scope) + '</span>' +
          '<span class="esg-chart__tooltip-val">' + esgFmtNum(val) + '</span>' +
          '<span class="esg-chart__tooltip-pct">' + pct + '%</span>' +
          '</div>';
      });
      html += '<hr class="esg-chart__tooltip-sep">';
      html += '<div class="esg-chart__tooltip-total"><span>Total</span><span>' +
        esgFmtNum(total) + ' ' + escHtml(unitStr) + '</span></div>';
    } else {
      html += '<div class="esg-chart__tooltip-row"><span>' +
        esgFmtNum(total) + ' ' + escHtml(unitStr) + '</span></div>';
      if (nearest.isProj) {
        html += '<div style="font-size:11px;color:var(--color-on-surface-variant);margin-top:4px">Projection</div>';
      }
    }

    tip.innerHTML = html;
    tip.removeAttribute('hidden');

    const tipW = tip.offsetWidth;
    const tipH = tip.offsetHeight;
    const canvasW = canvasRect.width;
    const canvasH = canvasRect.height;
    let left = e.clientX - canvasRect.left + 12;
    let top = e.clientY - canvasRect.top - 8;
    if (left + tipW > canvasW - 4) left = e.clientX - canvasRect.left - tipW - 12;
    if (top + tipH > canvasH - 4) top = canvasH - tipH - 4;
    if (top < 0) top = 4;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  });

  svg.addEventListener('mouseleave', () => tip.setAttribute('hidden', ''));
}
```

- [ ] **Step 3: Vérifier barres + tooltip ensemble**

Lance `python manage.py runserver` et ouvre la page Données ESG.

**Mode ligne seul (bouton inactif) :**
- Survole le graphe → tooltip affiche `[année]` + `[total] tCO2e`
- Survole un point de projection → mention "Projection" visible
- Quitte le graphe → tooltip disparaît

**Mode scope (bouton actif) :**
- Les barres empilées apparaissent, la ligne passe par-dessus
- La légende affiche les pastilles de couleur par scope
- Survole le graphe → tooltip montre une ligne par scope (pastille + nom + valeur + %)
- Les pourcentages d'une même année somment à ~100 %
- Le tooltip reste dans les bords du canvas même en bord gauche/droit

**Toggle retour :**
- Re-clic sur "Par scope" : barres disparaissent, légende revient à l'original

- [ ] **Step 4: Tester changement d'entreprise**

Via le combobox, sélectionne une autre entreprise → le graphe se recharge, les barres et le tooltip fonctionnent correctement avec les données de la nouvelle entreprise.

- [ ] **Step 5: Tester entreprise sans données carbone**

Si une entreprise sans données est disponible, sélectionne-la → le message "Aucune donnée carbone disponible" s'affiche, pas d'erreur console.

- [ ] **Step 6: Commit**

```bash
git add dashboard/static/dashboard/js/esg.js
git commit -m "feat(esg): stacked scope bars and custom hover tooltip on carbon chart"
```
