# Page commodités et modificateurs — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une page dédiée de création / modification des commodités (sources, facteurs
midpoint et endpoint régionalisés) et des modificateurs propres à chaque commodité,
cochables sur les flux, qui ajustent en % les facteurs des flux de production.

**Architecture:** Trois nouveaux modèles (`CommoditySource`, `CommodityModifier`,
`ModifierEffect`) et un M2M `Flow.modifiers`. La formule d'ajustement vit dans
`dashboard/services/impacts.py` (`flow_cf_value`) ; chaque calcul `quantité × CF` sur
les productions l'appelle. La page commodité est rendue côté serveur (formulaires Django,
POST → redirection), avec un sélecteur de lieu par paramètre GET ; la carte des flux
reçoit des cases à cocher en JS natif.

**Tech Stack:** Django 6, SQLite / PostgreSQL, HTML + CSS + JS natif, pytest-django,
openpyxl (import / export existants).

**Spec:** `docs/superpowers/specs/2026-10-24-commodites-modificateurs-design.md` (lire en
entier avant toute tâche).

## Global Constraints

- Pas de framework JS ; JS natif chargé en `defer` ; pas de dépendance npm ni Python nouvelle.
- Code identique sous SQLite et PostgreSQL (aucune fonction propre à un SGBD).
- Tout texte visible marqué pour la traduction : `{% translate %}`, `gettext_lazy`
  (constantes, `TextChoices`, `verbose_name`), `gettext` en fonction, `gettext()` /
  `interpolate(…, true)` / `ngettext()` en JS ; placeholders `%(nom)s`, jamais de f-string.
- Nouveaux modèles : `created_at` (`auto_now_add`), `updated_at` (`auto_now`),
  `created_by` (FK `AUTH_USER_MODEL`, `SET_NULL`, `null=True`, `related_name='+'`).
- Une migration = un changement logique, nommée (`makemigrations --name …`).
- Lignes ≤ 100 caractères, PEP 8, imports stdlib / Django / tiers / locaux.
- Couleurs par tokens `--color-*` de `DESIGN.md`, thèmes clair et sombre ; BEM léger.
- Formule : `facteur_ajusté = F × max(0, 1 + Σ percent / 100)` ; effets additifs ; `percent ≥ -100`.
- Seuls les flux PRODUCTION des actifs détenus voient leur impact ajusté ; ailleurs, labels.
- Lecture de `Flow` uniquement via `dashboard/services/flows.py` (règle existante).
- Python du projet : `./venv/Scripts/python.exe` (Git Bash) ; tests : `./venv/Scripts/python.exe -m pytest`.

## Review Focus

1. **Facteur « 0 » vs champ vide** sur la grille de facteurs : `0` est un vrai facteur
   (conservé), seul un champ vide supprime le CF. → test dans la tâche 9.
2. **Changement de commodité d'un flux sans `modifier_ids` dans le corps** (client ancien,
   appel partiel) : les modificateurs de l'ancienne commodité ne doivent jamais survivre.
   → test dans la tâche 5.
3. **Import Excel de deux lignes soja certifié / classique** de mêmes extrémités et année :
   elles ne sont pas des doublons. → test dans la tâche 7.
4. **N+1 requêtes** : charger les productions ou le périmètre de la carte avec des
   modificateurs ne fait pas une requête par flux. → `assertNumQueries` dans la tâche 2.
5. **Saisie à la virgule** (`-10,5`, `3 200,5`) pour les effets et les facteurs, comme
   `FlowMapFlowForm.clean_quantity`. → tests dans les tâches 9 et 10.

---

### Task 1: Modèles, migrations, admin

**Files:**
- Modify: `dashboard/models.py` (après `CharacterizationFactor`, et `Flow`)
- Create: 3 migrations dans `dashboard/migrations/`
- Modify: `dashboard/admin.py`, `dashboard/admin_site.py` (groupe « Impacts & inventaire (ACV) »)
- Test: `dashboard/tests_commodities.py` (nouveau)

**Interfaces:**
- Produces:
  - `CommoditySource(commodity, kind, title, reference, created_*)`, `kind` ∈
    `CommoditySource.Kind` = `AGRIBALYSE`, `ECOINVENT`, `ARTICLE`, `CERTIFICATION`, `OTHER` ;
    `related_name='sources'` ; `ordering = ('pk',)`.
  - `CharacterizationFactor.commodity_source` : FK `CommoditySource`, `SET_NULL`, null,
    `related_name='factors'`. `CharacterizationFactor.clean()` refuse une source d'une
    autre commodité.
  - `CommodityModifier(commodity, name, description, source, created_*)`,
    `related_name='modifiers'`, `UniqueConstraint(commodity, name)`, `ordering=('name',)` ;
    `clean()` refuse une `source` d'une autre commodité.
  - `ModifierEffect(modifier, category, percent, created_*)`, `related_name='effects'`,
    `percent` avec `MinValueValidator(-100)`, `UniqueConstraint(modifier, category)`.
  - `Flow.modifiers` : `ManyToManyField(CommodityModifier, blank=True, related_name='flows')`.
  - `invalid_modifiers(commodity, modifiers) -> list[CommodityModifier]` (module
    `dashboard/models.py`, fonction libre) : ceux dont `commodity_id != commodity.pk`.
  - `source_codes(commodity) -> dict[int, str]` : `{source.pk: 'S1', …}` par ordre de pk.

- [ ] **Step 1: Write the failing tests** (`dashboard/tests_commodities.py`, classe `CommodityModelTests(TestCase)`)

  - `test_source_codes_follow_creation_order` : deux sources → `{s1.pk: 'S1', s2.pk: 'S2'}`.
  - `test_effect_below_minus_100_rejected` : `ModifierEffect(percent=-100.5).full_clean()`
    lève `ValidationError` sur `percent` ; `-100` passe.
  - `test_modifier_name_unique_per_commodity` : même nom sur la même commodité →
    `IntegrityError` ; même nom sur une autre commodité → accepté.
  - `test_effect_unique_per_category` : deux effets même (modifier, category) → `IntegrityError`.
  - `test_modifier_source_from_other_commodity_rejected` : `full_clean()` lève sur `source`.
  - `test_cf_source_from_other_commodity_rejected` : idem sur `commodity_source`.
  - `test_invalid_modifiers` : modificateur du café passé pour le soja → renvoyé ; celui du soja → non.
  - `test_deleting_modifier_removes_it_from_flows` : flux avec le modificateur, `modifier.delete()`
    → `flow.modifiers.count() == 0`, le flux existe toujours.

- [ ] **Step 2: Run** `./venv/Scripts/python.exe -m pytest dashboard/tests_commodities.py -v` → FAIL (ImportError).

- [ ] **Step 3: Implement the models**, `verbose_name` en `gettext_lazy`, puis trois migrations :
  `--name add_commodity_source` (modèle + FK sur CF), `--name backfill_commodity_sources`
  (RunPython vide `makemigrations --empty`, voir step 4), `--name add_commodity_modifiers`
  (modificateur, effet, M2M). Enregistrer les trois modèles dans `dashboard/admin.py` et dans
  `GROUPS` de `admin_site.py` (groupe ACV, après `CharacterizationFactor`).

- [ ] **Step 4: Data migration** `backfill_commodity_sources` : pour chaque couple distinct
  (`commodity_id`, `source.strip()`, `reference.strip()`) des CF où l'un des deux est non vide,
  créer `CommoditySource(kind='OTHER', title=source or reference, reference=reference)` et
  renseigner `commodity_source` des CF du couple. Valeurs de facteur intactes. `reverse_code` :
  vide les FK et supprime les sources. Le corps vit dans une fonction de module
  `backfill(apps, schema_editor)` de la migration ; le test
  `test_backfill_links_existing_factors` l'importe (`importlib.import_module`) et l'appelle
  avec `django.apps.apps` sur trois CF (deux de même source, un sans source) : 1 source créée,
  2 CF liés, le 3ᵉ sans source, valeurs inchangées.

- [ ] **Step 5: Run** les tests de la tâche + `./venv/Scripts/python.exe -m pytest dashboard/tests_admin_console.py imports/tests/test_constants.py` → PASS.

- [ ] **Step 6: Commit** `feat(models): sources et modificateurs de commodité`

---

### Task 2: Formule d'ajustement et préchargement

**Files:**
- Modify: `dashboard/services/impacts.py`, `dashboard/services/flows.py`
- Test: `dashboard/tests_commodities.py` (classe `ModifierFormulaTests`)

**Interfaces:**
- Consumes: modèles de la tâche 1.
- Produces:
  - `modifier_multiplier(flow, category_key: str) -> float` : `max(0.0, 1 + Σ effect.percent / 100)`
    sur `flow.modifiers.all()` → `m.effects.all()` dont `effect.category.key == category_key`.
    Utilise uniquement les relations préchargées (pas de `.filter()`).
  - `flow_cf_value(cf_index, flow, category_key, region_id=None, country_id=None) -> float`
    = `cf_value(cf_index, flow.what_id, category_key, region_id, country_id) * modifier_multiplier(flow, category_key)`.
  - `flows.MODIFIER_PREFETCH = 'modifiers__effects__category'`, ajouté par
    `prefetch_related` dans `productions()`, `perimeter_flows()`, `range_perimeter_flows()`,
    `flows_with_endpoints()`.

- [ ] **Step 1: Write the failing tests** (CF global soja usage des sols = 1000 ; flux PRODUCTION) :
  - `test_no_modifier_unchanged` → 1000.
  - `test_single_modifier` (−10) → 900.
  - `test_modifiers_add_up` (−10, −5) → 850 (pas 855).
  - `test_floor_at_zero` (−80, −40) → 0.0.
  - `test_positive_effect` (+20) → 1200.
  - `test_category_without_effect_unchanged` : effet sur usage des sols, lecture du climat → valeur de base.
  - `test_regional_factor_with_modifier` : CF région 2000, −10 → 1800 avec `region_id`.
  - `test_productions_prefetch_no_n_plus_one` : 5 flux avec 2 modificateurs chacun ;
    `with self.assertNumQueries(N)` où N est constant (mesurer avec 1 flux puis 5 : même nombre).

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** les deux fonctions et le préchargement.
- [ ] **Step 4: Run** tâche + `./venv/Scripts/python.exe -m pytest dashboard/tests_flow.py dashboard/tests_flow_map.py` → PASS.
- [ ] **Step 5: Commit** `feat(impacts): ajustement des facteurs par les modificateurs du flux`

---

### Task 3: Appliquer la formule à tous les calculs de production

**Files:**
- Modify: `dashboard/views.py` (sites `cf_value(cf_index, p.what_id, …)` ≈ l. 311, 333, 452,
  691, 840, 1107, 1123, 1914, 2116 — refaire l'inventaire par `grep -n "cf_value" dashboard`),
  `dashboard/services/esg_environment.py` (≈ l. 104), `dashboard/services/impacts.py`
  (`measured_vs_modeled`)
- Test: `dashboard/tests_commodities.py` (classe `ModifierPropagationTests`)

**Interfaces:**
- Consumes: `flow_cf_value(cf_index, flow, key, region_id, country_id)` (tâche 2).
- Produces: aucun nouveau nom. Chaque `cf_value(cf_index, p.what_id, …)` sur une production
  `p` devient `flow_cf_value(cf_index, p, …)` avec les mêmes arguments de lieu.
  LEAP Prepare (`_get_leap_prepare_data`, ≈ l. 759) est traité en tâche 4 : ne pas y toucher ici.

- [ ] **Step 1: Write the failing tests** (jeu minimal : entreprise, actif détenu, soja, CF
  global `CAT_ECOSYSTEM_DIVERSITY` et une catégorie midpoint, flux PRODUCTION) :
  - `test_overview_footprint_uses_modifier` : `dashboard:company_data` avant / après avoir coché
    un modificateur −50 % sur la diversité des écosystèmes → l'empreinte est divisée par 2.
  - `test_esg_environment_uses_modifier` : `esg_environment` impacts midpoint par actif et
    `by_commodity` ajustés ; `by_commodity` garde une seule clé « Soja ».
  - `test_supply_modifier_changes_nothing` : modificateur sur un flux SUPPLY vers l'actif →
    sorties de `company_data`, `mesure_empreinte_data`, `dette_ecologique_data` identiques.
  - `test_stress_test_ignores_modifier` : `climate_stress_test_data` identique avec et sans
    modificateur sur la production (spec § 5.2, hors périmètre).
  - `test_measured_vs_modeled_uses_modifier`.

- [ ] **Step 2: Run** → FAIL sur les trois tests « uses_modifier ».
- [ ] **Step 3: Implement** le remplacement à chaque site ; importer `flow_cf_value` à côté de `cf_value`.
- [ ] **Step 4: Run** `./venv/Scripts/python.exe -m pytest dashboard` → PASS, golden
  `GoldenViewOutputTests` **inchangé** (aucun modificateur dans `populate_acme` à ce stade).
- [ ] **Step 5: Commit** `feat(impacts): modificateurs pris en compte dans les vues d'impact`

---

### Task 4: LEAP Prepare — facteur par ligne

**Files:**
- Modify: `dashboard/views.py` (`_get_leap_prepare_data`), `dashboard/static/dashboard/js/leap_prepare.js`
  (≈ l. 205-206 et 302-303), `dashboard/golden/leap_prepare.json` (réenregistré)
- Test: `dashboard/tests_commodities.py` (classe `LeapPrepareModifierTests`)

**Interfaces:**
- Consumes: `flow_cf_value` (tâche 2), sans lieu (facteur global, comme aujourd'hui).
- Produces: chaque élément de `assets[].lines` gagne `impact_factor: float` = moyenne pondérée
  par les quantités des `flow_cf_value(cf_index, p, CAT_ECOSYSTEM_DIVERSITY)` de la ligne
  (facteur de base si la somme des quantités est 0). `commodities[].impact_factor` reste le
  facteur global non ajusté (affiché par le levier).

- [ ] **Step 1: Write the failing tests**
  - `test_line_factor_weighted_by_quantity` : 30 000 t certifié (−10 %) + 15 000 t classique,
    CF 1,0 → `line['impact_factor'] == pytest.approx((30000*0.9 + 15000*1.0) / 45000)` ;
    `line['qty'] == 45000` ; une seule ligne pour (actif, soja).
  - `test_line_factor_without_modifier_equals_commodity_factor`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** côté serveur ; en JS, `cur` et `fut` utilisent `l.impact_factor`
  au lieu de `comm.impact_factor` (le levier `impactDelta` s'applique toujours par-dessus).
- [ ] **Step 4: Réenregistrer le golden** : `GOLDEN_RECORD=1 ./venv/Scripts/python.exe -m pytest dashboard/tests.py -k Golden`,
  puis vérifier par `git diff dashboard/golden/` que **seul** `leap_prepare.json` change, et
  seulement par l'ajout de `impact_factor` dans les lignes.
- [ ] **Step 5: Run** `./venv/Scripts/python.exe -m pytest dashboard` → PASS.
- [ ] **Step 6: Commit** `feat(leap): facteur ajusté par ligne dans LEAP Prepare`

---

### Task 5: Carte des flux — backend

**Files:**
- Modify: `dashboard/forms.py` (`FlowMapFlowForm`), `dashboard/views_flow_map.py`
  (`_form_data`, `flow_map_flow_create`, `flow_map_flow_update`, nouvelle vue),
  `dashboard/services/flow_map.py` (`_serialize_flow`, `flow_key`), `dashboard/urls.py`
- Test: `dashboard/tests_flow_map.py`

**Interfaces:**
- Consumes: `Flow.modifiers`, `invalid_modifiers` (tâche 1), préchargement (tâche 2).
- Produces:
  - Corps JSON création / modification : `modifier_ids: list[int]` (facultatif).
  - `FlowMapFlowForm.modifiers` : `ModelMultipleChoiceField(CommodityModifier, required=False)` ;
    `clean()` ajoute une erreur `modifiers` = « Ce modificateur n'appartient pas à cette
    commodité. » si `invalid_modifiers(...)` est non vide ; `save()` enregistre le M2M.
  - `_form_data` : `modifier_ids` absent à la modification → modificateurs actuels **si la
    commodité ne change pas**, sinon `[]`.
  - `_serialize_flow(flow)['modifiers'] = [{'id', 'name'}]` (ordre par nom).
  - `flow_key(flow)` = tuple actuel + `tuple(sorted(m.pk for m in flow.modifiers.all()))`.
  - `GET api/flow-map/commodities/<int:pk>/modifiers/` → `dashboard:flow_map_commodity_modifiers`,
    lecture ouverte, `{'modifiers': [{'id', 'name'}]}`, 404 JSON si la commodité n'existe pas.

- [ ] **Step 1: Write the failing tests**
  - `test_create_flow_with_modifiers` (201, M2M enregistré).
  - `test_modifier_of_other_commodity_rejected` (400, erreur sur `modifiers`).
  - `test_update_changing_commodity_without_modifier_ids_clears_them` (Review Focus 2).
  - `test_update_without_modifier_ids_keeps_them_when_commodity_unchanged`.
  - `test_serialized_flow_lists_modifiers`.
  - `test_flow_key_distinguishes_modifier_sets` : deux SUPPLY Mato Grosso → usine même année,
    l'un certifié → clés différentes ; `flow_years` et la suppression par années d'une ligne
    laissent l'autre intacte.
  - `test_commodity_modifiers_endpoint` (liste triée ; 404 inconnu).
- [ ] **Step 2: Run** `./venv/Scripts/python.exe -m pytest dashboard/tests_flow_map.py -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(flow-map): modificateurs sur les flux (API)`

---

### Task 6: Carte des flux — panneau

**Files:**
- Modify: `dashboard/templates/dashboard/_flow_map_panel.html`, `dashboard/static/dashboard/js/flow_map_panel.js`,
  `dashboard/static/dashboard/css/flow_map.css`, `dashboard/templates/dashboard/flow_map.html`
  (URL de l'endpoint dans la config `urls` passée au JS)
- Test: `dashboard/tests_flow_map.py` (rendu du gabarit)

**Interfaces:**
- Consumes: `flow_map_commodity_modifiers`, `modifier_ids`, `flow.modifiers` (tâche 5).
- Produces (DOM) : `<fieldset id="fm-modifiers" hidden>` avec légende « Modificateurs »,
  liste `#fm-modifiers-list` de cases à cocher, note `#fm-modifiers-note` « Sur ce flux, les
  modificateurs sont des labels : ils ne changent pas les calculs d'impact. » visible quand
  le flux n'est pas une PRODUCTION d'un actif détenu (origine `asset-<pk>` dont le bloc est
  dans le périmètre détenu de la carte).

- [ ] **Step 1: Write the failing test** `test_panel_renders_modifier_fieldset` : la page
  `dashboard:flow_map` contient `id="fm-modifiers"` et l'URL de l'endpoint.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** : `setWhat(item)` charge les modificateurs de la commodité
  (fieldset caché si aucun) et vide la sélection quand la commodité change ; à l'ouverture
  d'un flux existant, coche `flow.modifiers` ; `save()` envoie toujours `modifier_ids` ; la
  liste des lignes d'une flèche affiche « Soja · Certifié RTRS · 40 000 t · 2025 » (noms des
  modificateurs joints par « , »). Nouvelles chaînes en `gettext`.
- [ ] **Step 4: Vérification manuelle** (`./venv/Scripts/python.exe manage.py runserver`,
  compte Créateur) : créer un modificateur dans l'admin, cocher sur un flux, rouvrir, changer
  de commodité → cases vidées. Thème clair et sombre, navigation clavier dans les cases.
- [ ] **Step 5: Run** `./venv/Scripts/python.exe -m pytest dashboard/tests_flow_map.py` → PASS.
- [ ] **Step 6: Commit** `feat(flow-map): cases à cocher des modificateurs dans le panneau`

---

### Task 7: Import / export Excel

**Files:**
- Modify: `imports/services/constants.py` (`SHEET_COLUMNS['Flow']` : ajouter `'modifiers'`
  en dernière colonne ; clé de doublon de la feuille Flow ≈ l. 164 : ajouter `'modifiers'`),
  `imports/services/excel_export.py` (`flows_of`, `flow_row`),
  `imports/services/excel_parser.py` (`_build_row_check_context`, `_flow_row_error`,
  `_flow_duplicate_key`, `_existing_flow_keys`), `imports/services/importer.py`
  (`_import_flow`, `_import_characterization_factor`)
- Test: `imports/tests/test_flow_sheet.py`, `imports/tests/test_roundtrip.py`, `imports/tests/test_importer.py`

**Interfaces:**
- Consumes: modèles de la tâche 1 ; `flows_with_endpoints()` préchargé (tâche 2).
- Produces:
  - Cellule `modifiers` : noms séparés par `;`, espaces autour ignorés, casse ignorée ;
    export trié par nom, joint par `'; '`.
  - Contexte du parseur : `context['modifier_names'] = {nom_commodité_minuscule: {nom_modificateur_minuscule}}`
    (modificateurs en base uniquement).
  - Erreur de ligne : « Modificateur introuvable pour la commodité « %(what)s » : « %(name)s » ».
  - Clé de doublon : tuple actuel + `frozenset` des noms de modificateurs en minuscules.
  - `_import_characterization_factor` : `CommoditySource.objects.get_or_create(commodity=…,
    kind='OTHER', title=source or reference, reference=reference)` quand source ou référence
    est non vide, puis `commodity_source` renseigné.

- [ ] **Step 1: Write the failing tests**
  - `test_flow_modifiers_roundtrip` : export puis import d'un flux à deux modificateurs →
    mêmes modificateurs.
  - `test_unknown_modifier_rejected` : message exact ci-dessus.
  - `test_certified_and_classic_rows_not_duplicates` (Review Focus 3) : deux lignes identiques
    sauf `modifiers` (`Certifié RTRS` / vide) → aucune erreur de doublon, deux flux créés.
  - `test_cf_import_links_commodity_source` : deux CF de même source → une seule `CommoditySource`.
- [ ] **Step 2: Run** `./venv/Scripts/python.exe -m pytest imports -v` → FAIL.
- [ ] **Step 3: Implement.** Mettre à jour le modèle de classeur vide s'il est généré depuis
  `SHEET_COLUMNS` (vérifier `imports/tests/test_excel_template.py`).
- [ ] **Step 4: Run** `./venv/Scripts/python.exe -m pytest imports` → PASS.
- [ ] **Step 5: Commit** `feat(imports): modificateurs dans la feuille Flow`

---

### Task 8: Page commodités — liste, création, fiche (identité et sources)

**Files:**
- Create: `dashboard/views_commodities.py`, `dashboard/forms_commodities.py`,
  `dashboard/templates/dashboard/commodity_list.html`, `dashboard/templates/dashboard/commodity_detail.html`,
  `dashboard/templates/dashboard/commodity_form.html`, `dashboard/static/dashboard/css/commodities.css`
- Modify: `dashboard/decorators.py`, `dashboard/urls.py`, `templates/base.html` (lien de pied
  de barre latérale « Commodités », pour tout utilisateur connecté, après « Carte des flux »)
- Test: `dashboard/tests_commodities.py` (classe `CommodityPageTests`)

**Interfaces:**
- Consumes: `source_codes` (tâche 1).
- Produces:
  - `creator_required(view)` dans `dashboard/decorators.py` : anonyme → redirection login
    (`redirect_to_login`) ; connecté non Créateur → `PermissionDenied` (403).
  - URL (namespace `dashboard`) :
    `commodites/` → `commodity_list` ; `commodites/nouvelle/` → `commodity_create` ;
    `commodites/<int:pk>/` → `commodity_detail` ; `commodites/<int:pk>/identite/` →
    `commodity_identity` (POST) ; `commodites/<int:pk>/sources/` → `commodity_sources` (POST).
  - `CommodityIdentityForm(ModelForm)` : `name`, `unit`, `description`,
    `biodiversity_loss_class` + les 6 `dependency_*`.
  - `CommoditySourceFormSet` : `inlineformset_factory(Commodity, CommoditySource,
    fields=('kind', 'title', 'reference'), extra=1, can_delete=True)`.
  - Contexte de `commodity_detail` réutilisé par les tâches 9-10 : `commodity`, `can_edit`,
    `identity_form`, `source_formset`, `source_codes`.

- [ ] **Step 1: Write the failing tests**
  - `test_list_requires_login` (302 vers login) ; `test_list_shows_counts` (nom, unité,
    nombre de facteurs, nombre de modificateurs ; filtre `?q=soj`).
  - `test_detail_read_only_for_subscriber` (200, pas de `<form` d'édition, `can_edit` False).
  - `test_subscriber_post_forbidden` (403 sur `commodity_identity` et `commodity_create`).
  - `test_create_commodity` (Créateur → redirection vers la fiche ; unité vide → « tonnes »).
  - `test_create_commodity_missing_name` (200, erreur sur `name`).
  - `test_technical_key_read_only` : la fiche d'une commodité `key='water'` affiche la clé,
    le formulaire n'a pas de champ `key`.
  - `test_sources_formset_add_and_delete` ; `created_by` renseigné à la création.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Vues FBV `@require_GET` / `@require_POST`, `@login_required`
  (lecture) et `@creator_required` (écriture), POST → redirection vers la fiche avec le même
  `?lieu=` ; en cas d'erreur, la fiche est rendue avec le formulaire en erreur (status 200).
  Dépendances dans un `<details>` replié. Styles dans `commodities.css` chargé par les
  gabarits de la page.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(commodites): page liste et fiche commodité`

---

### Task 9: Fiche — facteurs midpoint / endpoint par lieu

**Files:**
- Create: `dashboard/services/commodity_sheet.py`
- Modify: `dashboard/views_commodities.py`, `dashboard/forms_commodities.py`,
  `dashboard/templates/dashboard/commodity_detail.html`, `dashboard/urls.py`, `commodities.css`
- Test: `dashboard/tests_commodities.py` (classes `CommoditySheetServiceTests`, `FactorGridViewTests`)

**Interfaces:**
- Consumes: `CharacterizationFactor`, `ImpactCategory.Level`, `source_codes`.
- Produces (`commodity_sheet.py`) :
  - `parse_location(value: str | None) -> tuple[str, int | None]` : `'global'` / `None` / invalide
    → `('global', None)` ; `'country-<pk>'` → `('country', pk)` ; `'region-<pk>'` → `('region', pk)`.
  - `location_chips(commodity, current) -> list[dict]` : `{'key', 'label', 'active'}` ; `Global`
    en premier, puis pays et `Pays › Région` ayant au moins un CF (tri par libellé), plus le
    lieu courant s'il n'a encore aucun CF.
  - `factor_rows(commodity, location, level) -> list[dict]` : une ligne par `ImpactCategory`
    du niveau (ordre `pk`) : `{'category', 'value' (float|None), 'source_id', 'inherited'
    (float|None), 'inherited_from' (str|None)}`. Héritage : région → pays de la région → global ;
    pays → global ; global → aucun.
  - `save_factors(commodity, location, values: dict[int, tuple[float | None, int | None]], user)` :
    par catégorie, `None` supprime le CF du lieu, une valeur (y compris `0.0`) crée ou met à
    jour le CF avec `commodity_source`.
  - `FactorGridForm(commodity, location)` : pour chaque catégorie, `value_<cat_pk>` (CharField
    facultatif, virgule décimale et espaces acceptés, comme `clean_quantity` mais négatif et 0
    permis) et `source_<cat_pk>` (choix parmi les sources de la commodité).
  - URL `commodites/<int:pk>/facteurs/` → `commodity_factors` (POST, champ caché `lieu`).
  - Le sélecteur « + pays ou région » est un `<form method="get">` avec un `<select name="lieu">`
    (pays, puis régions groupées par pays en `<optgroup>`).

- [ ] **Step 1: Write the failing tests**
  - `test_parse_location` (les trois formes + valeur invalide → global).
  - `test_inherited_from_country_then_global` : CF global 42, pays Brésil 2400 sur une autre
    catégorie ; lieu Mato Grosso → `inherited == 2400`, `inherited_from == 'Brésil'` ; l'autre →
    `42`, `'Global'`.
  - `test_region_inherits_global_when_country_empty`.
  - `test_midpoint_and_endpoint_rows_separated` : `factor_rows(..., MIDPOINT)` ne contient que
    des catégories midpoint.
  - `test_zero_is_kept_empty_deletes` (Review Focus 1) : POST `value_X='0'` → CF 0.0 existe ;
    POST `value_X=''` → CF supprimé.
  - `test_comma_decimal_accepted` : `'3 200,5'` → 3200.5 ; `'abc'` → erreur de champ.
  - `test_chips_list_locations_with_factors`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Le gabarit affiche deux blocs (midpoint, endpoint) avec un badge
  distinct, les valeurs héritées en placeholder gris « 2 400 ← Brésil » (`toLocaleString` côté
  serveur via `floatformat` / `localize`), unité de la catégorie, sélecteur de source `S…`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(commodites): facteurs midpoint et endpoint régionalisés`

---

### Task 10: Fiche — modificateurs

**Files:**
- Modify: `dashboard/views_commodities.py`, `dashboard/forms_commodities.py`,
  `dashboard/services/commodity_sheet.py`, `commodity_detail.html`, `dashboard/urls.py`, `commodities.css`
- Create: `dashboard/static/dashboard/js/commodities.js` (confirmation de suppression)
- Test: `dashboard/tests_commodities.py` (classe `ModifierPageTests`)

**Interfaces:**
- Consumes: `factor_rows` / résolution de lieu (tâche 9), `modifier_multiplier` n'est pas
  réutilisable (il prend un flux) : l'aperçu calcule `base × max(0, 1 + percent/100)` pour un
  modificateur seul.
- Produces:
  - `CommodityModifierForm(ModelForm)` : `name`, `description`, `source` (sources de la
    commodité uniquement).
  - `ModifierEffectFormSet` : `inlineformset_factory(CommodityModifier, ModifierEffect,
    fields=('category', 'percent'), extra=1, can_delete=True)`, `percent` accepte la virgule.
  - `modifier_cards(commodity, location) -> list[dict]` : `{'modifier', 'flow_count',
    'effects': [{'effect', 'level', 'adjusted'}]}`, `adjusted` calculé sur le facteur résolu
    du lieu courant (`None` si aucun facteur).
  - URL : `commodites/<int:pk>/modificateurs/nouveau/` → `commodity_modifier_create` ;
    `commodites/<int:pk>/modificateurs/<int:mpk>/` → `commodity_modifier_update` ;
    `commodites/<int:pk>/modificateurs/<int:mpk>/supprimer/` → `commodity_modifier_delete`
    (toutes POST, Créateur ; `mpk` d'une autre commodité → 404).
  - Bouton de suppression : `data-confirm` = `ngettext` « Supprimer « %(name)s » ? Il est
    coché sur %(n)s flux, dont les impacts seront recalculés. » ; `commodities.js` (defer)
    appelle `confirm()` et annule l'envoi si refus.

- [ ] **Step 1: Write the failing tests**
  - `test_create_modifier_with_effects` (−10 usage des sols, −15 diversité → 2 effets, `created_by`).
  - `test_duplicate_name_rejected` (erreur de formulaire, pas d'`IntegrityError`).
  - `test_effect_below_minus_100_rejected`.
  - `test_percent_comma_accepted` (`'-10,5'` → −10.5).
  - `test_delete_used_modifier` : modificateur coché sur 2 flux → suppression → 302, flux
    intacts sans modificateur ; la fiche avant suppression affiche `flow_count == 2`.
  - `test_modifier_of_other_commodity_404`.
  - `test_adjusted_preview` : base 3200, −10 → `adjusted == 2880`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Chaque carte : nom, source `S…`, tableau des effets (badge mid / end,
  % signé, facteur ajusté), formulaire d'édition visible pour les Créateurs ; « + Nouveau
  modificateur » en bas du bloc. Rappel en tête de bloc : « Propres à cette commodité. Les
  effets de plusieurs modificateurs cochés s'additionnent ; le facteur ne descend jamais sous 0. »
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(commodites): édition des modificateurs et de leurs effets`

---

### Task 11: Démo, traductions, documentation

**Files:**
- Modify: `dashboard/management/commands/populate_acme.py`, `locale/en/LC_MESSAGES/django.po|.mo`,
  `locale/en/LC_MESSAGES/djangojs.po|.mo`, `CLAUDE.md` (§ 4 « Activité et finance » / « Impacts »),
  `.gitignore` (ajouter `.superpowers/`)
- Test: suite complète

**Interfaces:**
- Consumes: tout ce qui précède.

- [ ] **Step 1: Démo.** Dans `populate_acme` : `CommoditySource` « Rapport RTRS » (CERTIFICATION)
  pour le soja ; modificateur « Certifié RTRS » (−10 % usage des sols midpoint, −15 % diversité
  des écosystèmes endpoint) ; le SUPPLY `from_region=mato_grosso → a_bretagne` est scindé
  chaque année en deux lignes : certifiée (2023 : 25 000 ; 2024 : 30 000) et classique
  (2023 : 15 000 ; 2024 : 15 000), totaux inchangés (40 000 / 45 000). Aucune production modifiée.
- [ ] **Step 2: Run** `./venv/Scripts/python.exe -m pytest dashboard/tests.py -k Golden`. Si un
  golden diffère, ce ne peut être que par un décalage de PK de flux : vérifier le diff, et
  réenregistrer seulement dans ce cas (aucune valeur d'impact ne doit bouger).
- [ ] **Step 3: Traductions** : les trois commandes `makemessages` / `compilemessages` de
  `CLAUDE.md` ; traduire toutes les nouvelles entrées anglaises (aucune `fuzzy`, aucune vide).
- [ ] **Step 4: CLAUDE.md** : mentionner `CommoditySource`, `CommodityModifier`,
  `ModifierEffect`, `Flow.modifiers`, `flow_cf_value` et la page `/commodites/` ; ajouter
  `tests_commodities.py` à la liste des fichiers de tests de `dashboard`.
- [ ] **Step 5: Run** `./venv/Scripts/python.exe -m pytest` (suite complète, ≈ 4 min) → PASS.
- [ ] **Step 6: Commit** `chore: démo soja certifié, traductions et documentation`
