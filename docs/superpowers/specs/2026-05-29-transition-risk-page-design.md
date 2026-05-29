# Spec : Page « Risque de transition »

**Date :** 2026-05-29  
**Statut :** Approuvé

---

## 1. Contexte & objectif

Ajouter une page **Risque de transition** accessible depuis un accordion "Analyse des risques" dans la sidebar. Cette page visualise l'impact sur la diversité des écosystèmes (`impact_endpoint_ReCiPe2016_ecosystem_diversity`) lié aux commodités produites par les assets d'une entreprise.

---

## 2. Architecture

Pas de nouvelle app Django. Tout s'intègre dans l'app `dashboard` existante.

**Fichiers modifiés :**
- `dashboard/views.py` — 2 nouvelles fonctions : `transition_risk` (vue page) et `transition_risk_data` (endpoint JSON)
- `dashboard/urls.py` — 2 nouvelles routes
- `templates/base.html` — sidebar : "Analyse des risques" devient un accordion avec sous-item "Risque de transition"

**Fichiers créés :**
- `dashboard/templates/dashboard/transition_risk.html`

---

## 3. Données & calculs

### Année de référence
Pour chaque asset, on retient la **dernière année disponible** dans `Production` (max `year` parmi ses productions).

### Formule d'impact
```
impact(production) = production.production × commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
```

### Agrégats
- **Par commodité** : somme des impacts de toutes les productions (année réf.) de cette commodité, tous assets confondus
- **Par asset** : somme des impacts de toutes les productions (année réf.) de cet asset
- **Par pays** : somme des impacts de tous les assets appartenant à ce pays

### Normalisation
Chaque agrégat est exprimé en **% du total global** (somme de tous les impacts = 100 %).

### Flux Sankey
Quatre colonnes : Commodités → Assets → Pays → Company.  
Chaque flux (arc) = part d'impact normalisée partagée entre deux nœuds connectés.

---

## 4. Endpoint JSON

`GET /api/company/<pk>/transition-risk/`

Réponse :
```json
{
  "company_name": "...",
  "year": 2024,
  "total_impact": 1234.56,
  "commodities": [{"name": "Soja", "impact": 45.2, "pct": 0.452}],
  "assets":      [{"name": "Farm A", "impact": 32.1, "pct": 0.321}],
  "countries":   [{"name": "Brésil", "impact": 58.0, "pct": 0.580}],
  "sankey_links": [
    {"source": "commodity:Soja", "target": "asset:Farm A", "value": 0.30},
    ...
  ]
}
```

---

## 5. Layout de la page

```
┌─────────────────────────────────────────────────────┐
│  RISQUE DE TRANSITION                               │
│  KPI : Impact total écosystème (unité PDF/ha)       │
├──────────────┬──────────────┬──────────────────────┤
│ Par commodité│  Par asset   │  Par pays            │
│ ░░░░░░ 45%   │  ░░░░░ 32%   │  ░░░░░░░░ 58%        │
│ ░░░░ 30%     │  ░░░░ 28%    │  ░░░░░ 30%           │
│ ░░ 25%       │  …           │  ░░ 12%              │
├─────────────────────────────────────────────────────┤
│  DÉCOMPOSITION DE L'IMPACT — Sankey SVG natif       │
│                                                     │
│  Commodités   Assets      Pays        Company       │
│  ┌──────┐                                          │
│  │      ├────╮           ┌──────┐   ┌──────────┐  │
│  └──────┘    ╰───────────┤      ├───┤          │  │
│  ┌──────┐    ╭───────────┤      │   │  [name]  │  │
│  │      ├────╯  ╭────────┤      ├───┤          │  │
│  └──────┘       │        └──────┘   └──────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 6. Composants visuels

### Barres de classement
- Barres horizontales `<div>` avec `width: {pct}%`
- Couleur : dégradé `--color-primary` → `--color-secondary`
- Label à gauche, valeur % à droite
- Style `card` cohérent avec le dashboard existant

### Sankey SVG natif
- Rendu `<svg>` responsive via `viewBox` calculé en JS
- Nœuds : rectangles arrondis (rx=4), couleur par colonne
- Flux : courbes de Bézier cubiques (`path` SVG avec `C`)
- Largeur des flux proportionnelle au `value` normalisé
- Palette : `--color-primary`, `--color-secondary`, `--color-tertiary`, `--color-outline-variant`
- Tooltip au survol (JS natif, `title` SVG ou `div` positionné)

---

## 7. Sidebar — Accordion

"Analyse des risques" devient un `<details>`/`<summary>` (ou JS toggle) avec :
```
▶ Analyse des risques
   └─ Risque de transition   ← lien actif
   └─ Risque physique        ← placeholder (href="#")
```

Pas de changement dans le reste du layout.

---

## 8. Contraintes

- JS vanilla uniquement — pas de D3 ni autre lib
- Compatible SQLite et PostgreSQL
- Sélecteur d'entreprise réutilisé depuis le dashboard principal (même combobox)
- Aucune migration requise — modèles existants suffisants
