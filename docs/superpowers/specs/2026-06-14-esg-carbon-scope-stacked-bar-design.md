# Spec : Barres empilées par scope — Graphe tendance carbone ESG

**Date** : 2026-06-14  
**Périmètre** : `dashboard/static/dashboard/js/esg.js`, `dashboard/templates/dashboard/esg.html`, `dashboard/static/dashboard/css/style.css`  
**Backend** : aucun changement requis (les données `scopes` sont déjà dans l'API)

---

## Contexte

Le graphe "Tendance des émissions carbone" affiche une ligne historique (SVG natif) et une projection en pointillés. L'API retourne déjà `historical[i].scopes` : un dict `{ "Scope 1": float, "Scope 2": float, … }` par année. L'objectif est d'ajouter un mode "vue par scope" activable via un bouton toggle.

---

## 1. Bouton toggle

### Placement
Dans `.esg-chart__head`, à droite de la div `.esg-chart__legend` existante :

```html
<button id="esg-scope-toggle" class="esg-chart__scope-btn" aria-pressed="false" title="Afficher par scope">
  <!-- icône SVG barres empilées 16×16 -->
  <span>Par scope</span>
</button>
```

### Comportement
- Au clic, toggle `aria-pressed` entre `"true"` et `"false"`.
- Met à jour la variable de module `esgScopeView` (boolean, initialement `false`).
- Rappelle `esgRenderChart(ESG_STATE.data.carbon)` pour re-rendre le graphe.

### Styles (`style.css`)
- Repos : border `1px solid var(--color-outline)`, fond transparent, texte `var(--color-on-surface-variant)`.
- Actif (`[aria-pressed="true"]`) : fond `var(--color-primary)`, texte blanc, border de même couleur.
- Transition `background 0.15s, color 0.15s`.

### Légende dynamique
- Barres désactivées : légende HTML existante (Historique / Projection 2030), inchangée.
- Barres activées : la légende est remplacée dynamiquement par des pastilles colorées par scope + label. La paire Historique/Projection reste présente mais réduite (opacity 0.5).

---

## 2. Barres empilées SVG

### Collecte des scopes
Au début de `esgRenderChart`, si `esgScopeView === true` :
```js
const allScopes = [...new Set(hist.flatMap(h => Object.keys(h.scopes || {})))].sort();
```
Tri alphabétique pour stabilité des couleurs entre re-rendus.

### Palette de couleurs
```js
const SCOPE_COLORS = ['#4e79a7','#f28e2b','#e15759','#76b7b2','#59a14f','#edc948'];
// assigné par index : allScopes[i] → SCOPE_COLORS[i % SCOPE_COLORS.length]
```

### Géométrie des barres
- `barWidth = Math.min(plotW / Math.max(hist.length, 1) * 0.6, 60)` — largeur max 60px.
- Barres centrées sur `xOf(year)` : `x = xOf(year) - barWidth / 2`.
- Empilement de bas en haut : `cumY` part de `yOf(0)`, chaque rect monte de `(scopeVal / maxVal) * plotH`.
- `opacity="0.75"` sur chaque rect pour laisser la ligne visible par-dessus.
- Classe CSS : `esg-chart__bar` (pour éventuellement cibler en CSS).

### Ordre de rendu dans le SVG
1. Grille (inchangée)
2. **Barres empilées** ← nouvelles, si mode actif
3. Ligne historique (inchangée, passe par-dessus)
4. Ligne de projection (inchangée)
5. Dots (inchangés, restent au-dessus)

---

## 3. Tooltip custom

### Structure HTML
Un seul div injecté une fois dans `.esg-chart__canvas` au moment du premier rendu :
```html
<div id="esg-chart-tooltip" class="esg-chart__tooltip" hidden></div>
```

### Déclenchement
- `mousemove` sur le SVG : calcule l'année la plus proche par position x (distance minimale parmi `hist` + `proj`).
- `mouseleave` sur le SVG : masque le tooltip.

### Positionnement
Coordonnées relatives au `.esg-chart__canvas` (via `getBoundingClientRect`), décalage `+12px` en x, `-8px` en y. Contraint pour rester dans les bords du canvas.

### Contenu (mode barres actif)
```
2023
● Scope 1   1 234 tCO2e   62.0%
● Scope 2     456 tCO2e   23.0%
● Scope 3     302 tCO2e   15.0%
─────────────────────────────────
Total       1 992 tCO2e
```
- Pastille colorée (`●`) de la couleur du scope.
- Valeur formatée via `esgFmtNum()` existant.
- Pourcentage = `(scopeVal / yearTotal * 100).toFixed(1) + '%'`.

### Contenu (mode ligne seul)
Même tooltip mais uniquement : `[année] — [total] [unit]`. Remplace les `<title>` SVG actuels sur les dots.

### Styles (`style.css`)
```css
.esg-chart__tooltip {
  position: absolute; pointer-events: none; z-index: 10;
  background: var(--color-surface-container);
  border: 1px solid var(--color-outline-variant);
  border-radius: 8px; padding: 10px 14px;
  font-size: 13px; color: var(--color-on-surface);
  box-shadow: 0 4px 16px rgba(0,0,0,.12);
  min-width: 180px;
}
```

---

## Fichiers touchés

| Fichier | Changements |
|---|---|
| `dashboard/templates/dashboard/esg.html` | Ajout bouton `#esg-scope-toggle` dans `.esg-chart__head` |
| `dashboard/static/dashboard/js/esg.js` | Variable `esgScopeView`, logique barres dans `esgRenderChart`, tooltip custom |
| `dashboard/static/dashboard/css/style.css` | `.esg-chart__scope-btn`, `.esg-chart__bar`, `.esg-chart__tooltip` |

## Fichiers non touchés

- `dashboard/views.py` — aucun changement backend
- `dashboard/models.py` — aucun changement
- Toute autre page ou app

---

## Contraintes

- Vanilla JS uniquement (pas de Chart.js ni autre lib).
- Le tooltip doit fonctionner que les barres soient actives ou non.
- Le bouton doit être accessible (`aria-pressed`, `title`, navigable au clavier).
- La couleur des scopes est stable tant que la liste des scopes ne change pas entre deux rendus.
