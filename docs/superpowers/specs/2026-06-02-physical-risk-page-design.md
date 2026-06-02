# Page « Risque physique » — Design

Date : 2026-06-02
Statut : validé (design)

## 1. Objectif

Ajouter une page **Risque physique** au dashboard, accessible depuis le menu
« Analyse des risques » (le sous-lien existe déjà mais pointe sur `#`). La page
évalue l'exposition financière des actifs d'une entreprise aux aléas physiques,
modulée par les politiques de l'entreprise.

Elle affiche :

1. **3 cartes KPI** (globales, tous aléas) : nombre d'actifs à risque élevé,
   vulnérabilité moyenne, perte annuelle projetée (toggle 5 ans / 10 ans).
2. **Une carte géographique** des actifs, points dimensionnés selon le risque
   physique de l'aléa sélectionné.
3. **Un classement** des catégories de risque (qui sert aussi de sélecteur d'aléa).
4. **Un tableau** par actif : Asset | Hazard | Exposition | Vulnérabilité | Risk.

## 2. Architecture

La page reprend exactement le pattern des pages `transition_risk` et
`dependencies` : un builder de données → JSON, deux vues, des URLs, un template
et un fichier JS dédié. **Aucune nouvelle dépendance** (MapLibre GL est déjà
chargé par la page Vue d'ensemble).

| Élément | Fichier | Détail |
|---|---|---|
| Builder | `dashboard/views.py` | `_get_physical_risk_data(company)` |
| Vue page | `dashboard/views.py` | `physical_risk(request)` — `@require_GET` (page publique, pas de login) |
| Vue API | `dashboard/views.py` | `physical_risk_data(request, pk)` — `@require_GET`, renvoie `JsonResponse` (page publique, pas de login) |
| URLs | `dashboard/urls.py` | `physical-risk/` et `api/company/<int:pk>/physical-risk/` |
| Template | `templates/dashboard/physical_risk.html` | extends `base.html`, charge MapLibre CSS/JS, réutilise le combobox entreprise |
| Nav | `templates/base.html` | brancher le sous-lien « Risque physique » sur l'URL + ajouter le bloc `nav_physical_risk` actif |
| JS | `dashboard/static/dashboard/js/physical_risk.js` | combobox + render + carte + sélecteur d'aléa |

La vue `physical_risk` rend la page avec l'entreprise initiale (première par nom,
ou celle persistée en `localStorage` côté client, comme les autres pages). Le
changement d'entreprise déclenche un fetch sur l'API ; le changement d'aléa et le
toggle 5/10 ans sont **purement client-side** (recalcul, pas de refetch).

## 3. Les 15 catégories de risque

Tous les champs `Asset.risk_*` comptent comme risque physique. Chacun est en
correspondance 1:1 avec un champ `Policy_Level.vulnerability_*` de même suffixe.

Défini comme une liste `PHYSICAL_RISKS` dans `views.py` (clé → libellé FR) :

| Clé (`risk_` / `vulnerability_`) | Libellé FR | Groupe |
|---|---|---|
| `water` | Eau | Services écosystémiques |
| `pollination` | Pollinisation | Services écosystémiques |
| `soil_quality` | Qualité des sols | Services écosystémiques |
| `carbon_sequestration` | Séquestration carbone | Services écosystémiques |
| `water_purification` | Épuration de l'eau | Services écosystémiques |
| `pest_control` | Contrôle des ravageurs | Services écosystémiques |
| `water_stress` | Stress hydrique | Aléas climatiques |
| `wildfire` | Incendie | Aléas climatiques |
| `cyclone` | Cyclone | Aléas climatiques |
| `drought` | Sécheresse | Aléas climatiques |
| `flood` | Inondation | Aléas climatiques |
| `coastal_inundation` | Submersion côtière | Aléas climatiques |
| `heatwave` | Canicule | Aléas climatiques |
| `temperature_variation` | Variation de température | Aléas climatiques |
| `precipitation_variation` | Variation des précipitations | Aléas climatiques |

Le champ `Groupe` est porté dans le payload pour un éventuel sous-titrage du
classement, mais le classement reste **une seule liste triée** (pas deux blocs).

## 4. Formules

Les actifs d'une entreprise sont récupérés via `Asset.objects.filter(
ownership__Company=company).distinct()`, comme sur les autres pages.

- **Exposition(asset)** = somme des `estimated_revenue` des `Production` de cet
  actif pour son **année de production la plus récente** (cohérent avec la prise
  de « dernière année » des autres pages). Pas de production → exposition `0`.
- **Vulnérabilité(aléa)** = **moyenne** des `vulnerability_<aléa>` sur toutes les
  `Company_Policy` de l'entreprise (via `policy_level`). Aucune politique → `1.0`
  (valeur par défaut du champ).
- **Risk(asset, aléa)** = `risk_<aléa>(asset) × Exposition(asset) × Vulnérabilité(aléa)`.

Note : la vulnérabilité est une constante par aléa au niveau entreprise (elle ne
varie pas d'un actif à l'autre).

## 5. Cartes KPI (globales, tous aléas confondus)

1. **Actifs à risque élevé** : nombre d'actifs dont le **max** des 15 `risk_*`
   est **≥ 0.7** (palier « Critical » déjà utilisé via `_exposure_label`).
2. **Vulnérabilité moyenne** : moyenne des 15 `vulnerability_*` sur l'ensemble des
   politiques de l'entreprise (moyenne des moyennes par aléa). Aucune politique → `1.0`.
3. **Perte annuelle projetée** : `Σ_assets Σ_aléas Risk(asset, aléa)`.
   - Toggle **5 ans / 10 ans** : multiplie la valeur annuelle par 5 ou 10
     (cumul linéaire), calculé **côté client** sans refetch.
   - Le payload fournit la valeur annuelle ; le JS applique le multiplicateur.

## 6. Classement par catégorie (= sélecteur d'aléa)

Les 15 catégories sont classées **par ordre décroissant** de la **moyenne, sur les
actifs, de `Risk(asset, aléa)`** pour cette catégorie.

- Le classement **fait office de sélecteur** : cliquer une ligne sélectionne
  l'aléa correspondant et met à jour la carte + le tableau (recalcul client-side).
- **Sélection par défaut = la catégorie en tête du classement.**
- La ligne sélectionnée est visuellement mise en évidence (`aria-pressed` /
  classe `--selected`).
- Chaque ligne montre : libellé, valeur du classement (risk moyen) sous forme de
  barre proportionnelle (comme les `tr-bar-*`).

## 7. Carte géographique

MapLibre GL (style `openfreemap/liberty`, comme la Vue d'ensemble). Un cercle par
actif :

- **Rayon ∝ Risk(asset, aléa sélectionné)**, normalisé au max des actifs en vue
  (les actifs sans risque → rayon minimal). Recalculé au changement d'aléa.
- **Couleur** par palier de hazard (`risk_<aléa>` de l'actif) selon
  `_exposure_label` (Low / Moderate / High / Critical).
- **Popup** au clic : nom de l'actif, hazard, exposition, risk.
- Implémentation : le JS construit le GeoJSON à partir de la liste `assets` du
  payload ; au changement d'aléa il recalcule la propriété `radius`/`risk` de
  chaque feature et appelle `setData`. `circle-radius` = `['get','radius']`.

## 8. Tableau (réactif à l'aléa sélectionné)

Colonnes : **Asset | Hazard (`risk_<aléa>`) | Exposition (€) | Vulnérabilité
(`vuln_<aléa>` moyenne) | Risk (= produit)**.

- Trié par **Risk décroissant**.
- Re-rendu au changement d'aléa (client-side).
- Exposition formatée en euros (`toLocaleString('fr-FR')`), hazard/vulnérabilité à
  2–3 décimales.

## 9. Forme du payload JSON

Tout est transmis en une fois pour permettre le changement d'aléa et le toggle
5/10 ans sans refetch. Le changement d'entreprise refetch.

```jsonc
{
  "company_id": 1,
  "company_name": "ACME",
  "kpis": {
    "assets_high_risk": 3,        // max hazard >= 0.7
    "avg_vulnerability": 1.12,    // moyenne des 15 vuln sur les politiques
    "annual_loss": 1234567.0      // Σ_assets Σ_aléas Risk ; JS × 5 ou × 10
  },
  "hazards": [                    // 15 entrées, triées desc par avg_risk
    {
      "key": "flood",
      "name": "Inondation",
      "group": "Aléas climatiques",
      "vulnerability": 1.2,       // moyenne entreprise pour cet aléa
      "avg_risk": 45678.0         // métrique du classement (risk moyen / actif)
    }
    // ...
  ],
  "assets": [
    {
      "id": 10,
      "name": "Site A",
      "latitude": 1.23,
      "longitude": 4.56,
      "country": "France",
      "exposition": 500000.0,
      "risk": {                   // les 15 risk_* de l'actif
        "flood": 0.8,
        "wildfire": 0.2
        // ...
      }
    }
    // ...
  ]
}
```

Le JS calcule, pour l'aléa sélectionné `k` :
`risk_asset = assets[i].risk[k] × assets[i].exposition × hazards[k].vulnerability`.

## 10. Cas limites

- **Entreprise sans actif** : `assets: []`, KPI à `0`, classement à `0`, carte et
  tableau vides (message « Aucun actif »).
- **Entreprise sans politique** : toutes les vulnérabilités = `1.0`.
- **Actif sans production** : exposition = `0` (donc risk = `0`, rayon minimal).
- **Aucune entreprise en base** : `initial_data = None` (comme les autres vues).

## 11. Tests (CLAUDE.md : ≥ 1 cas nominal + 1 cas d'erreur par vue)

`dashboard/tests.py` (ou `dashboard/tests/`) :

- `_get_physical_risk_data` — fixture minimale (1 entreprise, 2 actifs, productions,
  ≥ 2 politiques) : vérifier KPIs (compte risque élevé, vuln moyenne, perte
  annuelle), ordre du classement, valeurs de Risk d'une ligne du tableau, et la
  moyenne de vulnérabilité sur plusieurs politiques.
- Cas limites : entreprise sans actif (zéros, listes vides) ; entreprise sans
  politique (vuln = 1.0).
- Vue `physical_risk` : `200` (accessible sans connexion).
- Vue `physical_risk_data` : `200` + forme JSON attendue (accessible sans
  connexion) ; `404` sur pk inexistant.

## 12. Conformité projet

- JS vanilla, pas de framework frontend ; MapLibre déjà utilisé.
- Compatible SQLite/PostgreSQL (agrégations Django ORM standard, aucune fonction
  PostGIS).
- CBV non requis (vues fonctionnelles cohérentes avec les pages risque existantes).
- Style CSS : préfixe `pr-*` (miroir de la convention `tr-*`), réutilisation des
  classes `kpi-card`, `card`, `map-card` existantes.
```
