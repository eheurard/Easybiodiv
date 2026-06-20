# LEAP / Prepare — Simulateur d'impact T+1

> Spec de conception. Page Prepare de la phase LEAP : comparaison de l'état d'impact
> actuel vs un état futur (T+1) simulé en faisant varier production et facteur d'impact.

## 1. Objectif

Permettre à l'utilisateur de simuler l'évolution de l'empreinte « diversité des
écosystèmes » (`impact_endpoint_ReCiPe2016_ecosystem_diversity`) d'une entreprise en
ajustant deux familles de leviers, et de comparer visuellement l'**état actuel** à un
**état T+1 (simulé)** : impact total, sens du changement (mieux / moins bien), et détail
par asset ou par commodité.

Plus l'impact est **bas**, mieux c'est (réduction de l'empreinte écosystèmes).

## 2. Périmètre

- Simulation **100 % côté client** : aucune écriture en base, aucun modèle/migration.
  Au rechargement, on repart de l'état actuel.
- Réutilise les conventions des pages LEAP existantes (Locate / Evaluate / Assess) :
  combobox entreprise, onglets `_leap_tabs.html`, cartes KPI, classes CSS maison.
- Pas de librairie de graphiques (cohérent avec le projet) : visuels en **CSS** et
  **SVG inline**, comme le sankey de la page Assess et les barres de la page Compare.

Hors périmètre : sauvegarde de scénarios, projections multi-années (T+2, T+3…),
autres indicateurs d'impact que `ecosystem_diversity`.

## 3. Architecture

Aligné sur le pattern existant (cf. `leap_locate` / `leap_evaluate`) :

- **Vue** `leap_prepare(request)` — déjà présente avec `@login_required` + `@require_GET`.
  Enrichie pour passer `companies` et `initial_data` (comme les autres pages LEAP).
- **API** `leap_prepare_data(request, pk)` — `@login_required` + `@require_GET`, renvoie
  `JsonResponse(_get_leap_prepare_data(company))`.
- **Route** nouvelle : `api/company/<int:pk>/leap-prepare/` → `dashboard:leap_prepare_data`.
- **Builder** `_get_leap_prepare_data(company)` dans `views.py`.
- **Template** `dashboard/templates/dashboard/leap_prepare.html` (remplace le stub actuel).
- **JS** `dashboard/static/dashboard/js/leap_prepare.js` (préfixe `lp`), chargé en `defer`.
  S'appuie sur les helpers globaux de `main.js` (`escHtml`, `fmtNum`) déjà chargés par
  `base.html`.

## 4. Payload API (`_get_leap_prepare_data`)

```json
{
  "company_id": 1,
  "company_name": "Acme Corp",
  "year": 2024,
  "commodities": [
    {"id": 3, "name": "Soja", "impact_factor": 0.5}
  ],
  "assets": [
    {"id": 2, "name": "Site Paris",
     "lines": [{"commodity_id": 3, "qty": 100.0, "unit": "tonnes"}]}
  ]
}
```

Règles :
- Assets = ceux détenus par la société (`Asset.objects.filter(ownership__Company=company)`),
  `distinct()`.
- `lines` = productions de l'**année la plus récente de chaque asset** uniquement
  (même logique « latest year per asset » que `_get_mesure_empreinte_data`).
- `impact_factor` = `commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity`.
- `year` = année de référence = max des années retenues (peut être `null` si aucun asset
  / aucune production).
- Ne sont incluses dans `commodities` que les commodités effectivement présentes dans au
  moins une ligne (évite un payload pollué).
- Impact d'une ligne = `qty × impact_factor`. Aucun calcul T+1 côté serveur.

## 5. Modèle de simulation (côté client)

Deux familles de leviers, chacune en **% de variation** appliqué à la valeur actuelle :

- **Production / asset** : un levier par asset, multiplicateur `(1 + Δprod_asset)`
  appliqué à **toutes** les lignes de production de cet asset.
- **Facteur d'impact / commodité** : un levier par commodité, multiplicateur
  `(1 + Δfacteur_commodité)` appliqué au `impact_factor`, donc à **tous** les assets
  produisant cette commodité.

Formule par ligne :

```
impact_actuel(ligne)  = qty × impact_factor
impact_T1(ligne)      = qty × (1 + Δprod_asset) × impact_factor × (1 + Δfacteur_commodité)
```

Agrégations :
- **Total entreprise** = somme des lignes (actuel et T+1).
- **Par asset** = somme des lignes de l'asset.
- **Par commodité** = somme des lignes de la commodité.

Contrôles :
- Chaque levier = **slider −100 % → +100 %** couplé à un **champ numérique éditable**
  (valeur absolue : tonnes pour la production, valeur décimale pour le facteur).
  Slider et champ sont synchronisés dans les deux sens.
- Plage des sliders : −100 % à +100 %, pas de 1 %. Le champ numérique peut dépasser
  +100 % (saisie libre ≥ 0) ; le slider se cale alors à sa borne.
- Bouton **Réinitialiser** : remet tous les leviers à 0 % (état actuel).

## 6. Mise en page

1. **Bandeau KPI** (3 cartes, classe `kpi-row` / `kpi-card`) :
   - `Impact actuel` — total de référence.
   - `Impact T+1 (simulé)` — total recalculé en direct.
   - `Variation` — `%` + pastille **Mieux** (vert) si T+1 < actuel, **Moins bien**
     (rouge) si T+1 > actuel, neutre si égal.

2. **Rangée 2 colonnes** :
   - **Gauche — panneau de leviers** : deux groupes (« Production par asset »,
     « Facteur d'impact par commodité »), chaque ligne = label + slider + champ numérique
     + valeur recalculée affichée. Bouton « Réinitialiser » en tête de panneau.
   - **Droite — dumbbell** : en-tête avec un **menu déroulant « Par asset / Par
     commodité »** qui pilote le regroupement des lignes du graphe.

3. **Ligne Total** sous le dumbbell : actuel → T+1 et Δ, reprenant la sémantique couleur.

## 7. Visuel dumbbell (SVG inline)

- Une ligne par item (asset ou commodité selon le menu déroulant).
- **Point gris** = impact actuel, **point coloré** = impact T+1, reliés par un segment.
- Couleur du segment + du point T+1 : **vert** si baisse d'impact (T+1 < actuel, bien),
  **rouge** si hausse (T+1 > actuel), neutre si inchangé.
- Échelle horizontale commune à tous les items (max = plus grande des deux valeurs sur
  l'ensemble), pour comparabilité.
- Étiquette Δ (%) en bout de ligne.
- Recalcul à chaque changement de levier (re-render du SVG) ; re-tri optionnel par impact
  actuel décroissant pour stabilité visuelle.
- Palette reprise des couleurs existantes (`style.css` : verts/rouges déjà utilisés pour
  les variations, ex. ESG / compare). Pas de nouvelle palette introduite.

## 8. Cas limites

- **Entreprise sans asset / sans production** : `assets: []`, `commodities: []`,
  `year: null`. Page affiche un état vide (« Sélectionnez une entreprise. » /
  « Aucune donnée à simuler. »), KPIs à `—`.
- **Impact total actuel = 0** : variation `%` non calculable → affichage `—` (pas de
  division par zéro), pastille neutre.
- **Asset sans ligne sur l'année de référence** : exclu des leviers production et du
  dumbbell.

## 9. Tests

Backend (`dashboard/tests.py`, classe `LeapPrepareTests`) :
- payload : forme générale, `impact_factor` = champ commodité correct.
- `lines` n'utilisent que l'année la plus récente par asset (`test_uses_latest_year_only`).
- `commodities` ne liste que les commodités présentes.
- entreprise vide → `assets == []`, `year is None`.
- page : 200 authentifié, 302 (redirect) anonyme, bon template, `companies` en contexte,
  `initial_data` présent/`None` selon présence d'entreprises.
- API : 200 + content-type JSON, 404 si pk inconnu, 405 si POST.

La logique de simulation et le rendu dumbbell sont en **JS pur** ; le projet n'a pas
d'infrastructure de test JS → vérification manuelle (chargement page, sliders, menu
déroulant, réinitialisation), comme pour les autres pages LEAP.

## 10. Fichiers touchés

- `dashboard/views.py` — `_get_leap_prepare_data`, enrichissement `leap_prepare`,
  ajout `leap_prepare_data`.
- `dashboard/urls.py` — route API `leap-prepare`.
- `dashboard/templates/dashboard/leap_prepare.html` — page (remplace le stub).
- `dashboard/static/dashboard/js/leap_prepare.js` — simulateur + dumbbell.
- `dashboard/static/dashboard/css/style.css` — styles `lp-*` (leviers, dumbbell) si les
  classes existantes ne suffisent pas.
- `dashboard/tests.py` — `LeapPrepareTests`.
