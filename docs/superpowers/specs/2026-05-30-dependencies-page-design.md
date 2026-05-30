# Spec : Page Dépendances Écosystémiques

**Date :** 2026-05-30  
**Statut :** Approuvé

---

## 1. Objectif

Ajouter une page **Dépendances** (`/dependencies/`) au dashboard Easybiodiv qui permet de visualiser pour une entreprise :
- Son exposition globale aux services écosystémiques via sa chaîne d'approvisionnement (Supply Chain Reliance)
- La répartition par type de service (Service Exposure)
- La dépendance de ses revenus par segment économique (Revenue Dependence by Economic Segment)

Le design s'inspire de la maquette fournie (style KPI + cards + barres horizontales) et s'intègre dans le système de design existant (tokens CSS, sidebar, header).

---

## 2. Modèles utilisés

### Conversion des scores qualitatifs

Tous les champs `DEPENDENCY_CHOICES` (VL, L, M, H, VH) sont convertis en valeurs numériques :

| Label | Score |
|---|---|
| VL (Very Low) | 0.0 |
| L (Low) | 0.2 |
| M (Medium) | 0.5 |
| H (High) | 0.7 |
| VH (Very High) | 1.0 |

Fonction helper Python : `SCORE_MAP = {'VL': 0.0, 'L': 0.2, 'M': 0.5, 'H': 0.7, 'VH': 1.0}`

### Les 6 services écosystémiques

| Clé interne | Nom affiché | Catégorie CICES |
|---|---|---|
| `water` | Approvisionnement en eau | Provisionnement |
| `soil_quality` | Qualité des sols | Provisionnement |
| `carbon_sequestration` | Séquestration carbone | Régulation |
| `water_purification` | Épuration de l'eau | Régulation |
| `pest_control` | Contrôle des ravageurs | Régulation |
| `pollination` | Pollinisation | Régulation |

### Champs source par modèle

**`Commodity`** → `dependency_water`, `dependency_pollination`, `dependency_soil_quality`, `dependency_carbon_sequestration`, `dependency_water_purification`, `dependency_pest_control`

**`SubSector`** → `Water_dependency`, `Pollination_dependency`, `Soil_quality_dependency`, `Carbon_Sequestration`, `Water_purification_dependency`, `Pest_control_dependency`

---

## 3. Calculs métier

### 3.1 Données de production de la company

Récupérer l'union des productions liées à la company par les **deux voies** :

```python
from django.db.models import Q

productions_qs = Production.objects.filter(
    Q(company=company) |
    Q(asset__ownership__Company=company)
).select_related('commodity', 'asset').distinct()
```

- Prendre uniquement l'année la plus récente : `max_year = productions_qs.aggregate(Max('year'))['year__max']`. Si `None` → pas de données.
- Filtrer ensuite : `productions = productions_qs.filter(year=max_year)`.
- Pour chaque `Production`, les scores de dépendance sont ceux de la commodité associée.

### 3.2 Score de dépendance d'une commodité

```python
def commodity_dep_scores(commodity):
    return {
        'water': SCORE_MAP[commodity.dependency_water],
        'soil_quality': SCORE_MAP[commodity.dependency_soil_quality],
        'carbon_sequestration': SCORE_MAP[commodity.dependency_carbon_sequestration],
        'water_purification': SCORE_MAP[commodity.dependency_water_purification],
        'pest_control': SCORE_MAP[commodity.dependency_pest_control],
        'pollination': SCORE_MAP[commodity.dependency_pollination],
    }
```

### 3.3 KPI 1 — Score d'exposition global

- Pour chaque `Production` de la company (dernière année), récupérer les 6 scores de dépendance de la commodité.
- Moyenne simple sur toutes les productions × tous les services → score entre 0 et 1.
- Affiché en pourcentage (ex : `42 %`).

### 3.4 KPI 2 — Nœuds critiques

- Nombre de combinaisons `(commodity, scope)` distinctes dans les productions de la company où **au moins un** score de dépendance ≥ 0.7 (H ou VH).

### 3.5 KPI 3 — Service principal

- Pour chaque service, calculer la moyenne des scores sur toutes les productions (sans pondération par volume).
- Retourner le nom du service avec le score moyen le plus élevé.

### 3.6 Supply Chain Reliance

- Grouper les `Production` par `scope` : `direct`, `tier 1`, `tier 2`, `raw material`.
- Pour chaque scope group : calculer, pour chacun des 6 services, la **moyenne des scores** sur les commodités du groupe.
- Retourner pour chaque scope :
  - Liste de tous les services avec leur score moyen
  - Label d'exposition : Critical (≥0.7), High (≥0.5), Moderate (≥0.2), Low (<0.2)
- Affichage : 2 à 4 services par scope tier (ceux avec le score le plus élevé, ≥ 0.2)

**Mapping scope → label affiché :**

| Scope | Label |
|---|---|
| `direct` | Opérations directes |
| `tier 1` | Tier 1 : Chaîne d'approvisionnement |
| `tier 2` | Tier 2 : Approvisionnement amont |
| `raw material` | Matières premières |

### 3.7 Service Exposure (panneau droit)

- Pour chaque service, calculer la moyenne des scores sur toutes les productions de la company.
- Calculer une valeur monétaire indicative : `revenue_exposure = avg_dep_score × total_revenue` (total des revenus de la dernière année depuis `Company_Revenue`).
- Grouper en catégories CICES : Provisionnement (water, soil_quality) / Régulation (carbon_sequestration, water_purification, pest_control, pollination).
- Si pas de `Company_Revenue`, afficher les scores sans montant.

### 3.8 Revenue Dependence by Economic Segment

- Récupérer tous les `Company_Revenue_Sector` pour la company. Pour chaque subsecteur, prendre la ligne avec la dernière année disponible (`max(year)` par subsecteur).
- Pour chaque subsecteur, calculer le score moyen de ses 6 champs de dépendance.
- Trier par revenu décroissant.
- Étiquette d'exposition : High (score ≥ 0.5), Moderate (≥ 0.2), Low (<0.2).
- Afficher comme barre horizontale avec revenu + label.

---

## 4. API Django

### Vue principale

```
GET /dependencies/
```
- Paramètre : premier `Company` par défaut
- Contexte template : `companies`, `initial_data`
- Décoré `@login_required`

### API JSON

```
GET /api/company/<pk>/dependencies/
```
- Retourne le dictionnaire complet : KPIs + supply_chain + services + segments

**Structure JSON retournée :**

```json
{
  "company_id": 1,
  "company_name": "Acme Corp",
  "year": 2024,
  "global_exposure_score": 0.42,
  "critical_nodes": 5,
  "primary_service": {"key": "water", "name": "Approvisionnement en eau", "score": 0.68},
  "supply_chain": [
    {
      "scope": "direct",
      "label": "Opérations directes",
      "services": [
        {"key": "water", "name": "Approvisionnement en eau", "score": 0.7, "label": "Critical"},
        {"key": "soil_quality", "name": "Qualité des sols", "score": 0.5, "label": "High"}
      ]
    }
  ],
  "service_exposure": {
    "total_revenue": 50000000,
    "currency": "EUR",
    "categories": [
      {
        "name": "Services de provisionnement",
        "services": [
          {"key": "water", "name": "Approvisionnement en eau", "score": 0.62, "revenue_exposure": 31000000},
          {"key": "soil_quality", "name": "Qualité des sols", "score": 0.45, "revenue_exposure": 22500000}
        ]
      },
      {
        "name": "Services de régulation",
        "services": [
          {"key": "carbon_sequestration", "name": "Séquestration carbone", "score": 0.35, "revenue_exposure": 17500000},
          {"key": "water_purification", "name": "Épuration de l'eau", "score": 0.28, "revenue_exposure": 14000000},
          {"key": "pest_control", "name": "Contrôle des ravageurs", "score": 0.20, "revenue_exposure": 10000000},
          {"key": "pollination", "name": "Pollinisation", "score": 0.15, "revenue_exposure": 7500000}
        ]
      }
    ]
  },
  "revenue_segments": [
    {
      "subsector": "Agriculture céréalière",
      "sector": "Agriculture",
      "revenue": 12500000,
      "dep_score": 0.65,
      "exposure_label": "High"
    }
  ]
}
```

---

## 5. Template et structure HTML

**Fichier :** `dashboard/templates/dashboard/dependencies.html`

```
{% extends "base.html" %}
→ block nav_dependencies → active
→ block header_left → company combobox (identique à transition_risk)
→ block content → .dep-page
```

**Structure `.dep-page` :**

```
.dep-page
  .kpi-row                          ← 3 KPI cards
  .dep-main-row
    .card.dep-supply-chain          ← Supply Chain Reliance (col gauche ~60%)
    .card.dep-service-exposure      ← Service Exposure (col droite ~40%)
  .card.dep-revenue-segments        ← Revenue Dependence (pleine largeur)
```

### KPI cards

Même composant `.kpi-card` que les pages existantes.

- **Card 1** — Score d'exposition global : valeur en %, icône graphique
- **Card 2** — Nœuds critiques : nombre entier + label "points haute dépendance"
- **Card 3** — Service principal : nom du service + score

### Supply Chain Reliance

- Header : "Supply Chain Reliance"
- Pour chaque scope (ordonnés direct → tier 1 → tier 2 → raw material) :
  - Puce colorée + label du scope
  - Grille 2×N de cartes service :
    - Icône du service
    - Nom du service
    - Barre colorée (rouge/orange/gris selon niveau)
    - Label textuel (Critical / High / Moderate / Low)
  - Seuls les services avec score ≥ 0.2 sont affichés (au maximum 4)
- Si aucune production pour un scope, ne pas afficher le scope

### Service Exposure

- Header : "Service Exposure"
- Pour chaque catégorie CICES (Provisionnement / Régulation) :
  - Nom catégorie + montant total exposé (si revenu disponible)
  - Barre colorée proportionnelle au score
  - Sous-services en liste
- Note de bas : "Valeurs indicatives basées sur le revenu total"

### Revenue Dependence by Economic Segment

- Header : "Dépendance des revenus par segment économique"
- Pour chaque subsecteur trié par revenu desc :
  - Icône générique secteur
  - Nom du subsecteur
  - Revenu (formaté €/M€)
  - Label d'exposition coloré (rouge=High, orange=Moderate, gris=Low)
  - Barre horizontale proportionnelle au revenu × score

---

## 6. JavaScript

**Fichier :** `dashboard/static/dashboard/js/dependencies.js`

- Même pattern que `transition_risk.js` : combobox company + fetch API + render
- Fonctions :
  - `renderKPIs(data)` — met à jour les 3 KPI cards
  - `renderSupplyChain(data.supply_chain)` — génère les tiers + service cards
  - `renderServiceExposure(data.service_exposure)` — barres par catégorie
  - `renderRevenueSegments(data.revenue_segments)` — barres horizontales
  - `formatRevenue(amount, currency)` — format €12.5M

---

## 7. CSS

Ajouter dans `style.css` (section dédiée `/* ── Dependencies page ── */`) :

- `.dep-page` : layout flex column avec gap
- `.dep-main-row` : flex row, `gap: var(--space-gutter)`, responsive → column en mobile
- `.dep-supply-chain` : flex-grow 3
- `.dep-service-exposure` : flex-grow 2
- `.dep-tier` : section par scope avec puce + header
- `.dep-service-card` : card individuelle service (similaire aux cards de la maquette)
- `.dep-reliance-bar` : barre colorée avec classes `--critical`, `--high`, `--moderate`, `--low`
- `.dep-revenue-row` : ligne avec icône, nom, barre, montant, label
- `.dep-exposure-badge` : badge coloré pour les labels

**Palette de couleurs par niveau :**
- Critical : `var(--color-primary)` (rouge-brun)
- High : `var(--color-secondary)` (orange)
- Moderate : `#8a8a70` (neutre olive)
- Low : `var(--color-surface-dim)` (gris clair)

---

## 8. Navigation

- Dans `base.html` : l'entrée "Dépendances" dans la sidebar pointe déjà sur `#` → modifier pour pointer sur `{% url 'dashboard:dependencies' %}`
- Ajouter `{% block nav_dependencies %}{% endblock %}` (existant) dans le template

---

## 9. URLs

Ajouter dans `dashboard/urls.py` :

```python
path('dependencies/', views.dependencies, name='dependencies'),
path('api/company/<int:pk>/dependencies/', views.dependencies_data, name='dependencies_data'),
```

---

## 10. Tests

**Fichier :** `dashboard/tests.py` (ou dossier `tests/`)

- `test_dependencies_view_redirects_anonymous` : vérifier redirect si non connecté
- `test_dependencies_view_ok` : vérifier HTTP 200 pour user connecté
- `test_dependencies_data_no_production` : JSON correct quand company sans production
- `test_dependencies_data_with_production` : vérifier calcul des scores pour une company avec productions connues
- `test_score_map_conversion` : vérifier la conversion VL→0, H→0.7, etc.
- `test_revenue_segments` : vérifier tri et labels pour une company avec Company_Revenue_Sector

---

## 11. Cas limites

- Company sans production → supply_chain vide, KPIs à 0/None
- Company sans Company_Revenue → service_exposure sans montant, afficher scores uniquement
- Company sans Company_Revenue_Sector → revenue_segments vide
- Scope non représenté → ne pas afficher le tier
- Tous les scores à VL → primary_service = premier service par défaut (alphabétique)
