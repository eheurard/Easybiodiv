# Design — Page Vue d'ensemble (Overview)

**Date :** 2026-05-28
**Statut :** Approuvé

---

## Objectif

Créer la page Vue d'ensemble du dashboard Easybiodiv permettant à l'utilisateur de :
1. Sélectionner une entreprise par nom dans le header (combobox avec recherche filtrante)
2. Visualiser les KPI clés de l'entreprise (nombre d'actifs, pays, commodités, régions)
3. Voir la localisation des actifs sur une carte interactive (MapLibre GL JS)
4. Explorer l'exposition géographique avec les commodités associées par pays

---

## Layout général (approuvé : Option B)

```
┌─────────────────────────────────────────────────────────┐
│ HEADER : [Combobox entreprise]          [🔔] [Avatar]   │
├─────────────────────────────────────────────────────────┤
│  [12 actifs]  [5 pays]  [4 commodités]  [8 régions]     │  ← KPI row
├──────────────────────────────┬──────────────────────────┤
│                              │  Exposition par pays      │
│      MapLibre GL JS          │  🇫🇷 France — 4 actifs   │
│      (markers actifs)        │   Soja×2  Bœuf×2         │
│                              │  🇩🇪 Allemagne — 3       │
│                              │   Huile de palme×3       │
│                              │  🇧🇷 Brésil — 3          │
│           (2/3)              │         (1/3)             │
└──────────────────────────────┴──────────────────────────┘
```

---

## Composants

### 1. Combobox entreprise (header)

- Remplace la barre de recherche générique dans `base.html` **uniquement sur la page index**
  (via `{% block %}` dédié ou surcharge du bloc header dans le template de la page)
- Input texte avec filtre JS côté client sur la liste des entreprises
- La liste est injectée au chargement de la page via le contexte Django (toutes les entreprises)
- Au choix d'une entreprise : `fetch('/dashboard/api/company/<id>/')` → mise à jour JS sans rechargement
- Fermeture du dropdown au clic extérieur et à `Escape`
- Affiche le nom de l'entreprise sélectionnée dans l'input ; placeholder "Rechercher une entreprise…"
- Accessibilité : `role="combobox"`, `aria-expanded`, `aria-autocomplete="list"`

### 2. KPI cards

Quatre cartes en ligne :
| Métrique | Source JSON | Clé |
|---|---|---|
| Actifs totaux | `asset_count` | int |
| Pays | `country_count` | int |
| Commodités | `commodity_count` | int |
| Régions subn. | `region_count` | int |

Mise à jour du DOM : sélection de l'élément par `data-kpi="asset_count"` etc.

### 3. Carte MapLibre GL JS

- Chargée via CDN : `https://unpkg.com/maplibre-gl@latest/dist/maplibre-gl.js`
- Tuiles : **OpenFreeMap** (Liberty style) — aucune clé API requise
  `https://tiles.openfreemap.org/styles/liberty`
- Markers : cercles SVG en `--color-primary` (`#91452d`) avec bordure blanche
- Données des actifs : GeoJSON `FeatureCollection` calculé côté Django, injecté dans la réponse JSON sous la clé `geojson`
- Mise à jour des markers : `map.getSource('assets').setData(geojson)` — la carte n'est pas recréée
- Popup au clic sur un marker : nom de l'actif, pays, région, commodité
- Comportement initial : si aucune entreprise sélectionnée, carte vide centrée sur le monde

### 4. Exposition par pays

- Liste scrollable des pays (triés par nombre d'actifs décroissant)
- Chaque entrée : drapeau (emoji), nom du pays, compteur d'actifs, tags commodités
- Données issues de la clé JSON `countries` :
  ```json
  [
    {
      "name": "France",
      "asset_count": 4,
      "commodities": [
        {"name": "Soja", "count": 2},
        {"name": "Bœuf", "count": 2}
      ]
    }
  ]
  ```
- Deux styles de tags : `--color-primary` pour le premier tag, neutre pour les suivants

---

## Backend

### Endpoint JSON

**Route :** `GET /dashboard/api/company/<int:pk>/`
**Vue :** FBV `company_data(request, pk)` dans `dashboard/views.py`
**Décorateur :** `@require_GET`
**Réponse :** `JsonResponse`

```json
{
  "company_id": 1,
  "company_name": "Acme Corp",
  "asset_count": 12,
  "country_count": 5,
  "commodity_count": 4,
  "region_count": 8,
  "countries": [
    {
      "name": "France",
      "asset_count": 4,
      "commodities": [{"name": "Soja", "count": 2}, {"name": "Bœuf", "count": 2}]
    }
  ],
  "geojson": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [2.3522, 48.8566]},
        "properties": {"name": "Site Paris", "country": "France", "commodity": "Soja", "region": "Île-de-France"}
      }
    ]
  }
}
```

### Requêtes Django

- Assets d'une entreprise : `Asset.objects.filter(ownership__Company=company).select_related('country', 'subnational_region', 'commodity')`
- Agrégation pays : `annotate(asset_count=Count('id'))` groupé par `country`
- Agrégation commodités par pays : boucle Python (faible volume de données)

### Vue index

- Passe au template : `companies` (queryset de toutes les `Company`) pour alimenter le combobox
- Sélection initiale : première entreprise en base (ou aucune si base vide)
- Passe `initial_data` (JSON sérialisé) pour hydratation côté JS sans fetch supplémentaire au chargement

---

## URLs

```python
# dashboard/urls.py
path('', views.index, name='index'),
path('api/company/<int:pk>/', views.company_data, name='company_data'),
```

---

## Frontend (vanilla JS)

Fichier : `dashboard/static/dashboard/js/main.js` (extension du fichier existant)

Modules logiques (pas de fichiers séparés, fonctions nommées) :
- `initCombobox(companies)` — filtre, sélection, accessibilité
- `initMap()` — initialisation MapLibre, source GeoJSON vide
- `updateDashboard(data)` — met à jour KPI, carte, liste pays
- `fetchCompany(id)` — `fetch` + appel `updateDashboard`

---

## Migrations

Le modèle `dashboard` est déjà défini mais sans migration. Il faudra créer la migration initiale :
```
python manage.py makemigrations dashboard --name initial
```

---

## Tests

- `test_company_data_view` : vérifie le JSON retourné pour une entreprise avec des actifs
- `test_company_data_no_assets` : entreprise sans actifs → counts à 0, listes vides
- `test_company_data_not_found` : pk inexistant → 404
- `test_index_view` : vérifie que la liste des entreprises est dans le contexte

---

## Hors périmètre

- Pagination de la liste pays
- Clustering des markers MapLibre
- Filtres par commodité ou région sur la carte
- Persistance de la sélection d'entreprise entre sessions (localStorage)
