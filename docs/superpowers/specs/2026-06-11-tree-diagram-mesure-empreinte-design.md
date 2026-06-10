# Diagramme arborescent — Mesure d'empreinte

**Date :** 2026-06-11
**Statut :** Approuvé

---

## Objectif

Ajouter un diagramme hiérarchique (DAG gauche → droite) sous le Sankey existant dans la page "Mesure d'empreinte", représentant la répartition de l'empreinte biodiversité selon l'ordre : **Commodités → Actifs → Pays → Company**.

---

## Contexte

La page `mesure_empreinte.html` contient déjà :
- Une bande de KPI
- Trois barres horizontales (par commodité, actif, pays)
- Un diagramme Sankey SVG (`renderSankey(data)` dans `mesure_empreinte.js`)

Le nouveau diagramme vient **compléter** le Sankey en bas de page avec une représentation en arbre plus lisible, sans remplacer ni modifier l'existant.

---

## Choix de design

| Question | Choix retenu |
|---|---|
| Orientation | Gauche → droite (Commodités à gauche, Company à droite) |
| Taille des nœuds | Uniforme (tous identiques), % affiché en texte |
| Connexions | Tous les liens affichés (DAG, pas arbre strict) |
| Rendu | SVG pur, nouvelle carte séparée |

---

## Architecture

### HTML — `mesure_empreinte.html`

Ajouter une nouvelle carte **après** la carte Sankey existante (`.tr-sankey-card`) :

```html
<div class="card tr-tree-card">
  <div class="label-caps tr-tree-card__title">Répartition hiérarchique</div>
  <div class="tr-tree-wrap">
    <svg id="tree-svg" class="tr-tree-svg" aria-label="Diagramme arborescent de l'impact"></svg>
  </div>
</div>
```

### JS — `mesure_empreinte.js`

Nouvelle fonction `renderTree(data)` appelée depuis `renderTransitionRisk(data)` (après `renderSankey`).

**Layout algorithm :**
1. 4 colonnes à X fixes : `[60, 260, 490, 720]` (similaire au Sankey)
2. Nœuds par colonne :
   - Col 0 : `data.commodities` (triés par `pct` décroissant)
   - Col 1 : `data.assets` (triés par `pct` décroissant)
   - Col 2 : `data.countries` (triés par `pct` décroissant)
   - Col 3 : nœud unique `data.company_name`
3. Espacement vertical régulier dans chaque colonne (`NODE_H = 32`, `NODE_GAP = 14`)
4. Hauteur totale SVG calculée dynamiquement selon la colonne la plus peuplée

**Nœuds :**
- Rectangle `width=100, height=32, rx=4`
- Ligne 1 : `label` (tronqué à 14 caractères si nécessaire)
- Ligne 2 : `pct` en % (sauf Company qui affiche "100 %")
- Couleur par colonne : `['#4a7a5c', '#625a4e', '#865220', '#91452d']`

**Liens (courbes de Bézier) :**
- Source : `data.sankey_links` (mêmes données que le Sankey existant)
- Dessinés **avant** les nœuds pour ne pas les masquer
- Courbe : `M x1,ymid C mx,ymid mx,ymid2 x2,ymid2` (Bézier cubique horizontal)
- `stroke-width` : `Math.max(1, link.value * 20)` (proportionnel à la valeur)
- `stroke-opacity` : `0.25`
- Couleur : celle de la colonne source

**En-têtes de colonnes :**
- Texte `COMMODITÉS`, `ACTIFS`, `PAYS`, `COMPANY` en `font-size:9, font-weight:700, fill:#87736d`

### CSS — `style.css`

```css
.tr-tree-card { margin-top: 1.5rem; }
.tr-tree-card__title { margin-bottom: 0.75rem; }
.tr-tree-wrap { overflow-x: auto; }
.tr-tree-svg { width: 100%; min-width: 600px; display: block; }
```

---

## Données

**Aucun changement backend.** La fonction `_get_mesure_empreinte_data()` renvoie déjà :
- `commodities` : `[{name, pct}, ...]`
- `assets` : `[{id, name, pct}, ...]`
- `countries` : `[{name, pct}, ...]`
- `company_id`, `company_name`
- `sankey_links` : `[{source, target, value}, ...]`

Les clés de nœuds dans `sankey_links` suivent le format `commodity:<name>`, `asset:<id>`, `country:<name>`, `company:<id>` — identique au Sankey.

---

## Cas limites

| Cas | Comportement |
|---|---|
| Aucune donnée (`sankey_links` vide) | Message "Aucune donnée à afficher." centré dans le SVG |
| Label trop long (> 14 chars) | Tronqué avec `…` |
| Beaucoup de nœuds (> 10 commodités) | SVG s'étire en hauteur, carte scrollable horizontalement si trop large |

---

## Fichiers modifiés

| Fichier | Modification |
|---|---|
| `dashboard/templates/dashboard/mesure_empreinte.html` | +1 bloc `<div class="card tr-tree-card">` |
| `dashboard/static/dashboard/js/mesure_empreinte.js` | +fonction `renderTree(data)`, +appel dans `renderTransitionRisk` |
| `dashboard/static/dashboard/css/style.css` | +4 règles CSS pour `.tr-tree-card` |
