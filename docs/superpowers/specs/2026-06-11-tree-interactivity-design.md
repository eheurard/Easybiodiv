# Design — Répartition hiérarchique interactive

**Date :** 2026-06-11  
**Scope :** `dashboard/static/dashboard/js/mesure_empreinte.js`, `dashboard/templates/dashboard/mesure_empreinte.html`, `dashboard/static/dashboard/css/style.css`

---

## 1. Objectif

Rendre le graphe "Répartition hiérarchique" (SVG, page `mesure_empreinte`) interactif :

- Cliquer sur un nœud met en évidence toutes ses connexions (links + nœuds reliés) et ouvre un panneau latéral avec les détails.
- Un filtre par seuil d'impact et un filtre par commodité permettent de réduire le graphe aux nœuds pertinents.

---

## 2. Décisions de design

| Sujet | Choix | Raison |
|---|---|---|
| Déclencheur | Clic (persistant) | Fonctionne sur mobile, permet d'explorer calmement |
| Affichage infos | Panneau latéral | Plus de place pour les détails (liste actifs/commodités) |
| Filtres | Barre dédiée sous le titre | Toujours visible, ne compresse pas le titre |
| Implémentation SVG | DOM natif (`createElementNS`) | Permet d'attacher les event listeners à la création, code propre |

---

## 3. Architecture

### 3.1 État local

Un objet `treeState` est déclaré au niveau module dans `mesure_empreinte.js` :

```js
const treeState = {
  selected: null,      // node id string ou null
  threshold: 0,        // float 0–1 (ex. 0.05 = 5 %)
  commodity: null,     // string (nom commodité) ou null = toutes
};
```

Un module-level `currentData` stocke le dernier objet `data` reçu depuis l'API afin que les filtres puissent déclencher un re-rendu sans nouveau fetch.

### 3.2 Barre de filtres (HTML)

Nouvelle `<div class="tr-tree-filters">` insérée entre le titre et le SVG dans la card `.tr-tree-card` :

```html
<div class="tr-tree-filters">
  <div class="tr-tree-filter-group">
    <label class="label-caps" for="tree-threshold">Seuil</label>
    <input type="range" id="tree-threshold" min="0" max="30" value="0" step="1">
    <span id="tree-threshold-label">≥ 0 %</span>
  </div>
  <div class="tr-tree-filter-sep"></div>
  <div class="tr-tree-filter-group" id="tree-commodity-filters">
    <span class="label-caps">Commodité</span>
    <!-- pills injectées dynamiquement par JS -->
  </div>
</div>
```

Les pills commodité sont injectées par `buildCommodityPills(data)` après chaque chargement de données.

### 3.3 Layout SVG + panneau

```html
<div class="tr-tree-body">
  <div class="tr-tree-wrap">
    <svg id="tree-svg" ...></svg>
  </div>
  <div class="tr-tree-panel" id="tree-panel" hidden>
    <button class="tr-tree-panel__close" id="tree-panel-close">×</button>
    <div id="tree-panel-content"></div>
  </div>
</div>
```

`.tr-tree-body` est `display:flex; flex-direction:row`. Le panneau a une largeur fixe (180 px) et est masqué par `hidden` / `display:none` jusqu'à sélection.

### 3.4 Refacto `renderTree(data)`

La fonction est réécrite pour utiliser `document.createElementNS(SVG_NS, ...)` et `appendChild`.

**Structure produite :**

```
<svg id="tree-svg">
  <g id="tree-links">                    ← paths, ajoutés en premier (z-order bas)
    <path data-src="commodity:Cuivre" data-tgt="asset:42" .../>
    ...
  </g>
  <g id="tree-nodes">
    <g class="tree-node" data-id="country:Australia" style="cursor:pointer">
      <rect .../>
      <text .../> <!-- label -->
      <text .../> <!-- pct -->
    </g>
    ...
  </g>
</svg>
```

Chaque `<g class="tree-node">` reçoit un écouteur `click` à la création.

**Filtrage au rendu :**

Avant de créer les éléments, `renderTree` filtre :
1. **Seuil** : exclut les nœuds avec `pct < treeState.threshold` (sauf le nœud company qui est toujours inclus).
2. **Commodité** : si `treeState.commodity !== null`, ne conserve que les nœuds et links connectés à cette commodité (transitivement : commodité → actifs liés → pays liés → company).

Les links dont la source ou la cible est absente après filtrage sont simplement ignorés.

### 3.5 Logique de sélection (clic)

```
onClick(nodeId):
  if treeState.selected === nodeId:
    → désélectionner : treeState.selected = null
    → reset opacity de tous les <g.tree-node> et <path> à 1
    → masquer le panneau
  else:
    → treeState.selected = nodeId
    → calculer connectedIds = ensemble des node ids reliés à nodeId par au moins un link
    → pour chaque <g.tree-node> : opacity = connectedIds.has(id) ? 1 : 0.15
    → pour chaque <path> : opacity = (src === nodeId || tgt === nodeId) ? 1 : 0.12
    → mettre à jour le panneau (voir §3.6)
    → afficher le panneau
```

La mise en évidence est bidirectionnelle : si on clique sur un actif, ses commodités ET son pays sont mis en évidence.

### 3.6 Contenu du panneau latéral

Le panneau affiche du HTML généré par `buildPanelHTML(nodeId, data)` :

| Type nœud | Contenu panneau |
|---|---|
| `commodity:X` | Nom, badge "COMMODITÉ", impact %, liste des actifs connectés avec leur % |
| `asset:X` | Nom, badge "ACTIF", impact %, pays, liste des commodités connectées |
| `country:X` | Nom, badge "PAYS", impact %, liste des actifs connectés avec leur % |
| `company:X` | Nom, badge "ENTREPRISE", 100 %, nombre de pays, d'actifs, de commodités |

### 3.7 Re-rendu sur changement de filtre

```
onThresholdChange(value):
  treeState.threshold = value / 100
  treeState.selected = null
  renderTree(currentData)
  hidePanel()

onCommodityChange(name):            // null = toutes
  treeState.commodity = name
  treeState.selected = null
  renderTree(currentData)
  hidePanel()
```

Les pills commodité sont régénérées à chaque `renderTransitionRisk(data)` pour refléter les commodités disponibles. Le slider est réinitialisé à 0 lors d'un changement de société.

---

## 4. CSS

Nouveaux blocs dans `style.css` :

- `.tr-tree-filters` — flex row, padding, border-bottom
- `.tr-tree-filter-group` — flex row, gap, align-items center
- `.tr-tree-filter-sep` — séparateur vertical 1 px
- `.tr-tree-commodity-pill` / `.tr-tree-commodity-pill--active` — pills arrondie, couleur terre
- `.tr-tree-body` — flex row
- `.tr-tree-panel` — width 180 px, border-left, padding, font-size small
- `.tr-tree-panel__close` — bouton ×, position absolute top-right du panneau
- `.tr-tree-panel__badge` — badge de type (PAYS, ACTIF…)
- `.tr-tree-panel__section` — titre de section dans le panneau
- `.tr-tree-panel__row` — ligne clé/valeur dans le panneau

---

## 5. Fichiers modifiés

| Fichier | Changement |
|---|---|
| `dashboard/templates/dashboard/mesure_empreinte.html` | Ajoute `.tr-tree-filters`, `.tr-tree-body`, `.tr-tree-panel` dans la card |
| `dashboard/static/dashboard/js/mesure_empreinte.js` | `treeState`, `currentData`, refacto `renderTree()`, `buildCommodityPills()`, `buildPanelHTML()`, handlers filtre/clic |
| `dashboard/static/dashboard/css/style.css` | Styles pour filtres, panneau, pills |

Aucune modification backend. Aucune nouvelle dépendance.

---

## 6. Hors scope

- Animation de transition (fade) sur le changement d'opacité — la mise à jour est instantanée.
- Export / partage de la vue filtrée.
- Persistance des filtres entre navigations (localStorage).
- Lien cliquable vers la fiche de l'actif depuis le panneau.
