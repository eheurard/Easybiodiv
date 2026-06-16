# LEAP — Barre d'onglets + page Locate

**Date :** 2026-06-16
**Statut :** Validé (design)

## Contexte

La page « Mesure d'empreinte » (`dashboard:mesure_empreinte`, URL `/mesure-empreinte/`)
présente l'empreinte écosystème d'une entreprise. Elle correspond conceptuellement à
la phase **Assess** du framework TNFD/LEAP (Locate → Evaluate → Assess → Prepare).

On introduit une navigation par onglets LEAP en haut de la page (sous le sélecteur
« Entreprise ») permettant de circuler entre 4 sous-pages. La phase **Locate** est
développée entièrement ; **Evaluate** et **Prepare** sont des stubs « bientôt
disponible » ; **Assess** reste la page actuelle (inchangée hormis l'ajout de la barre).

## Objectifs

1. Barre d'onglets LEAP partagée, présente sur les 4 pages, sous « Entreprise ».
   Chaque onglet = grande lettre (L/E/A/P) + sous-titre (nom complet). Onglet actif
   souligné/mis en avant.
2. Page **Locate** : carte MapLibre des sites + panneau latéral liste des sites +
   filtres + sélecteur de style de carte. Pas de bandeau KPI.
3. Pages **Evaluate** / **Prepare** : stubs minimalistes (barre d'onglets + message).

## Non-objectifs

- Pas de KPI sur Locate.
- Pas de modification de la logique de la page Assess existante (hors insertion de la barre).
- Pas de changement du lien sidebar « Mesure d'empreinte » (continue de pointer sur Assess).
- Le contenu réel d'Evaluate/Prepare est hors périmètre.

## Architecture

Cohérent avec le pattern existant : **une vue / un template / un JS par page**.

### URLs (`dashboard/urls.py`)

```
path('leap/locate/',   views.leap_locate,   name='leap_locate')
path('api/company/<int:pk>/leap-locate/', views.leap_locate_data, name='leap_locate_data')
path('leap/evaluate/', views.leap_evaluate, name='leap_evaluate')
path('leap/prepare/',  views.leap_prepare,  name='leap_prepare')
```

`/mesure-empreinte/` (Assess) reste inchangé.

### Barre d'onglets — partial partagé

`templates/dashboard/_leap_tabs.html`, inclus en tête du `{% block content %}` de
chaque page LEAP :

```django
{% include "dashboard/_leap_tabs.html" with active="locate" %}
```

Les 4 onglets sont des `<a href>` (liens vers chaque URL). L'onglet dont la clé `==`
`active` reçoit la classe `leap-tab--active` (+ `aria-current="page"`).

Structure d'un onglet :

```html
<a class="leap-tab leap-tab--active" href="…" aria-current="page">
  <span class="leap-tab__letter">L</span>
  <span class="leap-tab__name">Locate</span>
</a>
```

Mapping onglet → URL :

| clé        | lettre | nom      | url                         |
|------------|--------|----------|-----------------------------|
| `locate`   | L      | Locate   | `dashboard:leap_locate`     |
| `evaluate` | E      | Evaluate | `dashboard:leap_evaluate`   |
| `assess`   | A      | Assess   | `dashboard:mesure_empreinte`|
| `prepare`  | P      | Prepare  | `dashboard:leap_prepare`    |

CSS dans `dashboard/static/dashboard/css/style.css` : `.leap-tabs` (rangée flex,
marge basse), `.leap-tab`, `.leap-tab--active`, `.leap-tab__letter` (grande lettre),
`.leap-tab__name` (sous-texte label-caps). Respecter `DESIGN.md` (palette terre).

## Page Locate

### Backend — `_get_leap_locate_data(company)`

Itère sur les actifs de l'entreprise (`Asset.objects.filter(ownership__Company=company)
.select_related('country', 'subnational_region').distinct()`), renvoie un GeoJSON
`FeatureCollection`. Chaque feature :

```json
{
  "type": "Feature",
  "geometry": {"type": "Point", "coordinates": [lng, lat]},
  "properties": {
    "name": "...",
    "country": "...",
    "region": "...",
    "near_sensitive_zone": true,
    "sensitive_zone_type": "Natura 2000",   // get_sensitive_zone_type_display() ou ""
    "sensitive_zone_name": "...",
    "sensitive_zone_area_ha": 412.0,
    "risk_water": 0.6,
    "risk_water_stress": 0.3
  }
}
```

Payload renvoyé :

```json
{
  "company_id": ..., "company_name": "...",
  "geojson": {"type": "FeatureCollection", "features": [...]}
}
```

Vue `leap_locate(request)` (login_required, require_GET) : liste des entreprises +
`initial_data` (première entreprise), rend `dashboard/leap_locate.html`.
Vue `leap_locate_data(request, pk)` : `JsonResponse(_get_leap_locate_data(company))`.

### Template — `dashboard/leap_locate.html`

- Étend `base.html`, ouvre le groupe nav Risks (`nav_risks_open`), marque le sous-lien
  « Mesure d'empreinte » actif (`nav_mesure_empreinte`) pour cohérence sidebar.
- `extra_css` : feuille MapLibre (`maplibre-gl@4`).
- `header_left` : combobox entreprise (copie identique des autres pages).
- `content` :
  - `{% include "dashboard/_leap_tabs.html" with active="locate" %}`
  - Rangée carte + panneau (réutilise classes `map-card-wrap`, `map-card`,
    `map-legend`, `card`) :
    - Carte `#leap-locate-map`.
    - Filtres (chips) : `Tous` / `Zones sensibles` / `Risque eau élevé`
      (`.leap-filter`, bouton actif `--active`, `data-filter="all|sensitive|water"`).
    - Sélecteur de style : boutons `Classique / Gris / Satellite`
      (réutilise `.map-layer-btn`, `data-layer`).
    - Légende : 4 niveaux risque eau (palette `#dac1ba/#feb87c/#af5d43/#91452d`) +
      repère « proche zone sensible » (halo).
    - Panneau latéral `#leap-locate-list` : liste des sites.
- `extra_js` : script MapLibre, `companies-data` + `initial-data` (json_script),
  `var LEAP_LOCATE_API_URL = "{% url 'dashboard:leap_locate_data' pk=0 %}";`,
  `<script src="…/leap_locate.js" defer>`.

### Front — `dashboard/static/dashboard/js/leap_locate.js`

État module `LL_STATE = { data, map, filter: 'all' }`. Réutilise `escHtml`,
`fmtNum`, `MAP_STYLES` de `main.js` (chargé globalement avant les scripts de page).

- **Combobox** : `llInitCombobox(companies, initialData)` — calqué sur
  `prInitCombobox` de `physical_risk.js`, clé localStorage partagée
  `'selected-company-id'`, fetch via `LEAP_LOCATE_API_URL.replace('/0/', '/'+id+'/')`.
- **Carte** : `llInitMap()` — calqué sur `prInitMap`. Source `ll-assets`, layer
  `ll-assets-layer` type `circle` avec :
  - `circle-color` = couleur niveau risque eau (`['get','color']`).
  - `circle-stroke-width` = `['case', ['get','sensitive'], 3, 1.5]`.
  - `circle-stroke-color` = `['case', ['get','sensitive'], '<halo>', '#ffffff']`
    (halo = couleur d'accent du design, ex. vert forêt `#3d6b4f`).
  - Popup au clic : nom, pays/région, badge zone sensible (type, nom, surface),
    risque eau & stress hydrique en %.
- **Style toggle** : réutilise `MAP_STYLES` + ré-ajout source/layer sur `styledata`
  (même mécanique que `switchMapStyle` de `main.js`, adaptée à la source `ll-assets`).
- **Filtres** : `data-filter` →
  - `all` : tous les sites.
  - `sensitive` : `near_sensitive_zone === true`.
  - `water` : `risk_water >= 0.5`.
  Met à jour la source carte (geojson filtré) **et** la liste.
- **Rendu liste** `llRenderList(features)` : par site → nom, badge type de zone si
  applicable, surface (ha), barres/jauges risque eau & stress hydrique (réutilise
  l'échelle de bandes `Low/Moderate/High/Critical`). Clic sur un item → `flyTo`
  sur les coordonnées (pattern asset-list de `main.js`).
- Bandes risque : helper local `llBand(score)` (≥0.7 Critical, ≥0.5 High, ≥0.2
  Moderate, sinon Low) + table couleurs (mêmes que `PR_BAND_COLORS`).

## Stubs Evaluate / Prepare

Vues `leap_evaluate` / `leap_prepare` (login_required, require_GET) : rendent
`dashboard/leap_evaluate.html` / `dashboard/leap_prepare.html`. Chaque template
étend `base.html`, inclut la barre d'onglets (`active="evaluate"` / `"prepare"`),
le combobox entreprise (pour cohérence visuelle), et affiche un encart
« Phase Evaluate — bientôt disponible » (`.leap-stub`). Pas d'endpoint JSON.

## Tests

Fichier `dashboard/tests.py` (ou miroir existant) — ajouter :

- `_get_leap_locate_data` : entreprise avec ≥1 actif → geojson contient les features
  attendues (coordonnées, `near_sensitive_zone`, `risk_water`) ; entreprise sans actif
  → `features` vide.
- Vue `leap_locate` : GET 200, template `dashboard/leap_locate.html`.
- Endpoint `leap_locate_data` : GET 200, `Content-Type` JSON, clé `geojson`.
- Vues stub `leap_evaluate` / `leap_prepare` : GET 200.

Vérifier compatibilité SQLite (aucune fonction Postgres/PostGIS — on lit
`latitude`/`longitude` en FloatField).

## Risques / points d'attention

- `main.js` doit rester chargé avant `leap_locate.js` (il l'est via `base.html`)
  pour exposer `escHtml`, `fmtNum`, `MAP_STYLES`.
- Le toggle de style recrée la source — bien ré-appliquer le geojson filtré courant.
- Garder la barre d'onglets accessible (rôle de navigation, `aria-current`).
