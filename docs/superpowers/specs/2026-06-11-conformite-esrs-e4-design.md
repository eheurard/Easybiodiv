# Design — Page « Conformité CSRD / ESRS E4 »

> Spec validé le 2026-06-11. Visualisation du niveau de conformité d'une entreprise
> au standard européen **ESRS E4 « Biodiversité et écosystèmes »** (CSRD).

## 1. Objectif

Fournir une page web (lecture seule, dans l'app `dashboard`) qui restitue, pour une
entreprise donnée :

- le **verrou de matérialité** (gate) : ESRS E4 ne s'applique que si la biodiversité
  est jugée matérielle via la double évaluation de matérialité (DMA) ;
- une **vue synthétique** (KPIs, % de conformité, métrique E4-5, frise LEAP) ;
- une **vue détaillée** exigence par exigence (les 5 ou 6 Disclosure Requirements).

La saisie/édition des données de conformité se fait **exclusivement via l'admin Django**.
La page consomme ces données et les enrichit de dérivations issues des modèles existants
(`Asset`, `Company_Policy`, `Production`/`Commodity`).

## 2. Décisions de cadrage (validées)

| Sujet | Décision |
|-------|----------|
| Persistance | Nouveaux modèles Django éditables, liés à `Company`. |
| Zones sensibles E4-5 | Flag manuel par site (`Asset`) + saisie ; métrique calculée depuis ces flags. |
| Version du standard | Champ par évaluation (`AMENDED_2025` défaut / `ORIGINAL_2023`). |
| Statuts DR | Auto-suggestion depuis données existantes + override manuel (admin). |
| Surface d'édition | Admin Django uniquement ; la page est en lecture seule. |
| Profondeur LEAP | Synthèse dérivée + statut/notes par phase (pas de workflow lourd). |

## 3. Contraintes (rappel CLAUDE.md)

- Pas de framework frontend : HTML/CSS/JS vanilla, chargement `defer`/fin de body.
- Code identique SQLite & PostgreSQL : **aucun `JSONField`**, uniquement
  `Float/Char/Bool/Text/TextChoices`.
- Conventions modèles : `created_at`, `updated_at`, `created_by` sur les modèles métier ;
  `TextChoices` plutôt que constantes brutes ; migrations nommées (une par changement
  logique).
- Au moins un test par nouveau modèle/vue (cas nominal + cas d'erreur).

## 4. Modèle de données

### 4.1 `E4Assessment` (une évaluation par entreprise)

| Champ | Type | Notes |
|-------|------|-------|
| `company` | FK `Company` | |
| `reporting_year` | `IntegerField` | |
| `standard_version` | `CharField` + `TextChoices` | `AMENDED_2025` (défaut, 5 DR) / `ORIGINAL_2023` (6 DR, E4-1 obligatoire). |
| `materiality_status` | `CharField` + `TextChoices` | `NOT_ASSESSED` (défaut) / `MATERIAL` / `NOT_MATERIAL`. **Verrou de matérialité.** |
| `materiality_justification` | `TextField` (blank) | Justification du screening site-par-site ; surtout requise si `NOT_MATERIAL`. |
| `leap_locate_status` | `CharField` + `TextChoices` | `TODO` (défaut) / `IN_PROGRESS` / `DONE`. |
| `leap_evaluate_status` | idem | |
| `leap_assess_status` | idem | |
| `leap_locate_notes` | `TextField` (blank) | |
| `leap_evaluate_notes` | `TextField` (blank) | |
| `leap_assess_notes` | `TextField` (blank) | |
| `created_at` | `DateTimeField(auto_now_add=True)` | |
| `updated_at` | `DateTimeField(auto_now=True)` | |
| `created_by` | FK `settings.AUTH_USER_MODEL`, null/blank | |

`__str__` → `"{company.name} — E4 {reporting_year}"`. Une évaluation « active » par
entreprise (pas de contrainte stricte d'unicité imposée ; le plus récent
`reporting_year` est retenu par la vue).

### 4.2 `DisclosureRequirement` (état mutable d'un DR)

| Champ | Type | Notes |
|-------|------|-------|
| `assessment` | FK `E4Assessment` (related_name=`disclosure_requirements`) | |
| `code` | `CharField` + `TextChoices` | `E4_1`…`E4_6`. |
| `status` | `CharField` + `TextChoices` | `NOT_STARTED` (défaut) / `NON_COMPLIANT` / `PARTIAL` / `COMPLIANT` / `NOT_APPLICABLE`. |
| `justification` | `TextField` (blank) | Champ preuve/justification. |

`unique_together = (assessment, code)`. Les **métadonnées réglementaires** (intitulé,
description, caractère conditionnel, référence ESRS 2) ne sont **pas** stockées : elles
vivent dans une constante `DR_CATALOG` (voir §6) et sont fusionnées par la vue. Rationale :
source de vérité unique du texte réglementaire, pas de staleness ; les attributs demandés
par la mission (intitulé/description/conditionnel) restent exposés au niveau de l'API.

### 4.3 Ajouts sur `Asset` (E4-5 + LEAP-Locate)

| Champ | Type | Notes |
|-------|------|-------|
| `near_sensitive_zone` | `BooleanField(default=False)` | Site dans/près d'une zone sensible. |
| `sensitive_zone_type` | `CharField` + `TextChoices` (blank) | `NATURA_2000` / `NATIONAL_PROTECTED` / `UNESCO` / `IUCN_KBA` / `OTHER`. |
| `sensitive_zone_name` | `CharField` (blank) | Ex. « Natura 2000 — Camargue ». |
| `sensitive_zone_area_ha` | `FloatField(default=0)` | Surface en hectares pour la métrique E4-5. |

## 5. Catalogue réglementaire (`DR_CATALOG`)

Constante Python dans `views.py` (ou un module `compliance_catalog.py` dédié). Chaque
entrée : `code`, `title`, `description`, `reference` (ESRS 2 GDR-x), `is_conditional`.

- **E4-1** — Plan de transition biodiversité — *conditionnel* : publié seulement si un
  plan existe ; sinon simple déclaration d'absence. Si plan → alignement Cadre mondial
  Kunming-Montréal (stopper/inverser la perte d'ici 2030).
- **E4-2** — Politiques (ESRS 2 GDR-P) — couvre traçabilité produits/matières à impact
  matériel + sites proches de zones sensibles.
- **E4-3** — Actions et ressources (ESRS 2 GDR-A) — hiérarchie d'atténuation
  (éviter → réduire → restaurer → compenser) ; seules les actions engagées/financées comptent.
- **E4-4** — Cibles (ESRS 2 GDR-T) — seuils écologiques, alignement Kunming-Montréal /
  Stratégie UE Biodiversité 2030, offsets, portée géographique, niveau de hiérarchie visé.
- **E4-5** — Métriques d'impact — métrique dure = nombre + surface (ha) des sites
  dans/près de zones sensibles avec impacts négatifs.
- **E4-6** — Effets financiers anticipés — **uniquement en mode `ORIGINAL_2023`**
  (supprimé dans la version amendée).

**Ensemble applicable** :
- `AMENDED_2025` → `[E4_1 (conditionnel), E4_2, E4_3, E4_4, E4_5]`
- `ORIGINAL_2023` → `[E4_1 (obligatoire), E4_2, E4_3, E4_4, E4_5, E4_6]`

(E4-IRO-1 est hors périmètre dans les deux modes : basculé dans ESRS 2.)

## 6. Couche vue

`_get_compliance_data(company)` retourne un dict JSON-sérialisable :

```
{
  company_id, company_name,
  standard_version, standard_version_label,
  reporting_year,
  configured: bool,                       # False si aucun E4Assessment
  materiality: { status, status_label, is_material, justification },
  leap: [ { phase, label, status, status_label, notes, derived_summary } x3 ],
  disclosure_requirements: [
    { code, title, description, reference, is_conditional,
      status, status_label, justification, auto_suggestion } ...
  ],
  synthesis: { compliance_pct, counts_by_status: {...}, applicable_count },
  e4_5_metric: { sites_count, total_area_ha, sites: [ {name, zone_type, zone_name, area_ha} ] }
}
```

**Dérivations** :
- **LEAP-Locate** `derived_summary` : nb de sites en zone sensible (depuis les flags `Asset`).
- **LEAP-Evaluate** : top dépendances (réutilise `SERVICES` / `_commodity_dep_scores`).
- **LEAP-Assess** : résumé d'impact (footprint ReCiPe `impact_endpoint_ReCiPe2016_ecosystem_diversity`).
- **`auto_suggestion`** par DR : ex. E4-2 → `PARTIAL` si l'entreprise a au moins une
  `Company_Policy` ; E4-5 → `PARTIAL` si au moins un site a `near_sensitive_zone`.
  La suggestion est indicative ; le `status` affiché vient de la DB (override manuel).

**Comportement du verrou** :
- `NOT_ASSESSED` ou `configured=False` → bandeau « matérialité non évaluée », invite à
  créer l'évaluation dans l'admin ; DR affichés avec statut DB/suggestion.
- `NOT_MATERIAL` → DR masqués ; mise en avant de `materiality_justification`.
- `MATERIAL` → vue détaillée complète des DR applicables.

**Évaluation retenue** : la plus récente par `reporting_year` pour l'entreprise ;
aucune création automatique (renvoyer un payload `configured=False` sinon).

Endpoints (pattern existant) :
- `compliance(request)` → rend `dashboard/compliance.html` + `initial_data` (1re entreprise).
- `compliance_data(request, pk)` → `JsonResponse(_get_compliance_data(company))`.

URLs ajoutées dans `dashboard/urls.py` :
- `path('compliance/', views.compliance, name='compliance')`
- `path('api/company/<int:pk>/compliance/', views.compliance_data, name='compliance_data')`

## 7. UI (vanilla)

- **Template** `dashboard/templates/dashboard/compliance.html` (extends `base.html`),
  bloc `nav_compliance` actif.
- **JS** `dashboard/static/dashboard/js/compliance.js` : sélecteur d'entreprise →
  `fetch` API → re-render (même structure que `dette_ecologique.js` etc.).
- **CSS** : composants ajoutés à `dashboard/static/dashboard/css/style.css` (BEM léger,
  variables `:root` existantes).
- **Nav** : activer le lien existant « Conformité CSRD » dans `templates/base.html`
  (passage de `href="#"` à `{% url 'dashboard:compliance' %}` + bloc actif).

**Vue synthétique (haut)** : bandeau matérialité (vert `MATERIAL` / gris `NOT_ASSESSED` /
ambre `NOT_MATERIAL`), KPIs (% conformité, DR conformes/applicables, sites E4-5 + ha total),
mini-frise LEAP (3 puces statut).

**Vue détaillée (bas)** : une carte par DR applicable (badge statut coloré, marqueur
« conditionnel » sur E4-1, justification, rappel de la suggestion auto si elle diverge du
statut saisi). Bascule 5 ↔ 6 DR selon `standard_version`. Si `NOT_MATERIAL`, remplacer la
liste de DR par l'encart de justification de non-matérialité.

Accessibilité : badges avec texte (pas couleur seule), ARIA sur le sélecteur, contraste AA.

## 8. Admin

`dashboard/admin.py` :
- `E4AssessmentAdmin` avec `DisclosureRequirementInline` (TabularInline), `list_display`
  (company, reporting_year, standard_version, materiality_status).
- Ajout des champs zones sensibles à l'admin `Asset` (fieldset « Zone sensible (E4-5) »).

→ Toute la saisie de conformité passe par l'admin.

## 9. Tests (`dashboard/tests.py`)

- `materiality_status=MATERIAL` → `disclosure_requirements` non vide, longueur = 5 en
  `AMENDED_2025`.
- `materiality_status=NOT_MATERIAL` → verrou actif, DR masqués côté payload.
- Entreprise sans `E4Assessment` → `configured=False` + suggestions présentes.
- Métrique E4-5 : 2 sites `near_sensitive_zone` (dont surfaces) → `sites_count=2`,
  `total_area_ha` = somme.
- `standard_version=ORIGINAL_2023` → DR inclut `E4_1` (non conditionnel) et `E4_6`.

## 10. Démo (optionnel)

Étendre `dashboard/management/commands/populate_acme.py` pour créer une `E4Assessment`
de démonstration (statut `MATERIAL`, quelques DR, 1–2 sites en zone sensible) afin de
permettre la vérification visuelle immédiate.

## 11. Hors périmètre

- Édition depuis la page (POST/forms) — admin uniquement.
- Données géospatiales réelles de zones protégées (Natura 2000…) — flags manuels seulement.
- Workflow LEAP étape par étape avec livrables.
- Export de rapport CSRD.
