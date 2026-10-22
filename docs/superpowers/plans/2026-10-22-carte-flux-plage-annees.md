# Carte des flux — plage d'années, suppression par années, légende interactive — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** remplacer l'année unique de la carte des flux par une plage [D, F] qui affiche
la ligne la plus récente de chaque « même flux », faire choisir les années à supprimer
(flux et retrait de liens, avec une option séparée de fin de détention), et rendre la
légende cliquable pour masquer / réafficher une nature de flux.

**Architecture :** le serveur calcule le périmètre sur la plage, la déduplication « même
flux » et les listes d'années à supprimer (services testés) ; l'API passe de `year` à
`start`/`end` ; le JS remplace le sélecteur d'année par deux champs, ajoute une boîte de
dialogue « choix des années » et le filtre de légende.

**Tech Stack :** Django 6.0.5, Python 3.11+, SQLite, pytest-django, JS vanilla + SVG.

**Spec :** `docs/superpowers/specs/2026-10-22-carte-interactive-flux-design.md` §10 (fait
autorité ; §4–§5 pour le reste de la page déjà construite).

## Global Constraints

- Toutes les contraintes du plan précédent restent valables
  (`docs/superpowers/plans/2026-10-22-carte-interactive-flux.md`, section Global
  Constraints) : vanilla JS + SVG natif, seul `dashboard/services/flows.py` filtre
  `Flow` (exception déjà admise : `Flow.objects.get(pk=…)` dans `views_flow_map.py`),
  écritures par formulaires / JSON `{'errors': …}`, écritures réservées au rôle
  `CREATOR`, i18n complète, lignes Python ≤ 100 caractères, commits en français terminés
  par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Années bornées 1900–2100 (constantes `YEAR_MIN` / `YEAR_MAX` existantes), et
  `start ≤ end`.
- GNU gettext n'est pas installé : nouvelles chaînes ajoutées à la main dans
  `locale/en/LC_MESSAGES/django.po` / `djangojs.po`, `.mo` compilés avec `polib` installé
  dans un dossier temporaire (`pip install --target <scratch>`), jamais ajouté à
  `requirements.txt`.
- Ne jamais écrire dans le vrai `db.sqlite3` pendant les vérifications manuelles
  (travailler sur une copie).

## Review Focus

1. **Plage d'une seule année** (D = F) : la carte se comporte exactement comme l'ancienne
   carte à année unique. → Tâche 1, `test_single_year_range_matches_year_view`.
2. **Flux dont l'actif n'était pas détenu certaines années de la plage** : seules les
   années détenues comptent, à l'affichage comme dans la liste des années à supprimer.
   → Tâche 2, `test_flow_years_skip_years_outside_perimeter`.
3. **Suppression avec une année hors plage dans la requête** (client modifié) : refusée
   (400), rien supprimé. → Tâche 3, `test_delete_flow_rejects_year_outside_range`.
4. **Retrait de liens sans aucune année cochée et option de détention décochée** : 400,
   rien modifié. → Tâche 3, `test_unlink_with_nothing_selected_is_refused`.
5. **Plage inversée** (`start > end`) dans l'URL : 400 lisible, pas de carte vide
   silencieuse. → Tâche 3, `test_data_rejects_inverted_range`.

---

### Task 1 : périmètre et données de la carte sur une plage

**Files :**
- Modify : `dashboard/services/flows.py`, `dashboard/services/flow_map.py`
- Test : `dashboard/tests_flow_map.py`

**Interfaces :**
- Produces :
  - `flows.range_perimeter_flows(company, start: int, end: int, touching=None) -> list[Flow]` : union, pour chaque année `y` de `[start, end]`, de `perimeter_flows(company, y, touching)` ; triée par `(year, pk)`. (Implémentation libre — boucle par année acceptable — mais résultat identique à cette union.)
  - `flow_map.flow_key(flow) -> tuple` : `(kind, what_id, endpoint_key(flow, 'from'), endpoint_key(flow, 'to'), scope)`.
  - `flow_map.latest_flows(flows: list[Flow]) -> list[Flow]` : pour chaque `flow_key`, garde **toutes** les lignes de l'année maximale de cette clé ; ordre `(year, pk)`.
  - `flow_map.owned_assets_in_range(company, start, end) -> QuerySet[Asset]` : actifs ayant une détention par `company` qui chevauche `[start, end]` (`start_year` nul ou ≤ end, `end_year` nul ou ≥ start), triés par pk.
  - `flow_map.build_flow_map(company, start: int | None, end: int | None, user) -> dict` : **remplace** la signature `(company, year, user)`. Clé `'year'` remplacée par `'start'` et `'end'` ; `'years'` = années de `perimeter_years` ∪ {année en cours} ∪ {start, end}, trié. Défaut (`start` et `end` à None) : première et dernière de `perimeter_years`, sinon année en cours pour les deux. Un seul des deux à None → `ValueError`. Blocs du périmètre = entreprise + `owned_assets_in_range` ; flux dessinés = `latest_flows(range_perimeter_flows(...))` ; chaque flux sérialisé garde `'year'`. Rangement et groupes calculés sur ces flux affichés.

- [ ] **Step 1 : tests qui échouent** (`RangeFlowMapTests`)

```python
def test_latest_year_wins_for_same_flow(self):
    old = make_supply(what=self.soja, year=2021, quantity=5,
                      origin=self.cargill, destination=self.vevey)
    new = make_supply(what=self.soja, year=2023, quantity=7,
                      origin=self.cargill, destination=self.vevey)
    data = build_flow_map(self.acme, 2020, 2024, AnonymousUser())
    self.assertEqual([f['id'] for f in data['flows']], [new.pk])
    self.assertEqual(data['flows'][0]['year'], 2023)

def test_different_scope_is_another_flow(self): ...       # deux émissions, scopes ≠ → 2 flux
def test_same_year_duplicates_are_both_kept(self): ...    # même clé, même année → 2 flux
def test_asset_owned_part_of_range_is_owned_block(self): ...
def test_flow_of_year_asset_not_owned_is_excluded(self): ...
def test_default_range_spans_known_years(self):           # flux 2019 et 2022 → start 2019, end 2022
def test_single_year_range_matches_year_view(self): ...   # D = F : mêmes blocs / flux que le périmètre de l'année
def test_one_bound_missing_raises(self): ...
```

Mettre à jour les tests existants de `build_flow_map` (signature `(company, year, user)`) vers `(company, y, y, user)` et la clé `'year'` vers `'start'`/`'end'`.

- [ ] **Step 2 :** `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow_map.py -k "Range or BuildFlowMap"` → FAIL.
- [ ] **Step 3 : implémenter.**
- [ ] **Step 4 :** relancer → PASS.
- [ ] **Step 5 : commit** `feat(flux): carte sur une plage d'années, flux le plus récent`

---

### Task 2 : années à supprimer et retrait de liens sur une plage

**Files :**
- Modify : `dashboard/services/flow_map.py`
- Test : `dashboard/tests_flow_map.py`

**Interfaces :**
- Consumes : `range_perimeter_flows`, `flow_key` (tâche 1).
- Produces :
  - `flow_years(company, start, end, flow) -> list[dict]` : `[{'year': int, 'count': int}]` croissant, années de `[start, end]` où des lignes de même `flow_key` que `flow` figurent dans `range_perimeter_flows` (donc dans le périmètre).
  - `delete_flow_years(company, start, end, flow, years: list[int]) -> int` : supprime, dans une transaction, les lignes de même clé de ces années **parmi celles du périmètre** ; renvoie le nombre supprimé. `years` vide ou contenant une année hors `[start, end]` → `ValueError`.
  - `unlink_preview(company, start, end, key) -> dict` : `{'years': [{'year', 'flows'}], 'ownership': bool, 'ownership_year': int | None, 'co_owners': [str]}`. `years` = années de la plage où `range_perimeter_flows(..., touching=…)` a des flux, avec leur nombre. `ownership` = l'actif est dans `owned_assets_in_range`. `ownership_year` = plus ancienne année de `years`, sinon `start` si `ownership`, sinon None. `co_owners` = noms (triés) des autres entreprises ayant une détention de l'actif qui chevauche la plage. **Remplace** la signature `(company, year, key)`.
  - `unlink(company, start, end, key, years: list[int], ownership_year: int | None) -> dict` : `{'flows': int, 'ownership': bool}` ; supprime les flux du bloc dans le périmètre pour les années `years` ; si `ownership_year` n'est pas None, applique `end_ownership(company, asset, ownership_year, end)`. `years` vide **et** `ownership_year` None → `ValueError` ; année hors plage → `ValueError` ; `ownership_year` fourni pour un bloc qui n'est pas un actif détenu → `ValueError`. Clés refusées comme avant (entreprise elle-même, groupe, milieu, inconnu).
  - `end_ownership(company, asset, year: int, until: int) -> None` : **remplace** `(company, asset, year)`. Détentions valides en `year` : supprimées si `start_year == year`, sinon `end_year = year - 1` ; détentions avec `year < start_year ≤ until` : supprimées ; `start_year > until` : intactes.

- [ ] **Step 1 : tests qui échouent** (`RangeDeletionTests` ; adapter `UnlinkTests` aux nouvelles signatures)

```python
def test_flow_years_lists_years_with_counts(self): ...         # 2021, 2023 → [{2021,1},{2023,1}]
def test_flow_years_skip_years_outside_perimeter(self): ...    # actif non détenu en 2021 → seule 2023
def test_delete_flow_years_only_checked(self):
    # lignes 2021 et 2023 ; delete [2021] → 2023 reste
def test_delete_flow_years_rejects_out_of_range(self): ...     # ValueError, rien supprimé
def test_unlink_preview_range(self): ...                        # years + counts, ownership_year, co_owners
def test_unlink_selected_years_only(self): ...
def test_unlink_with_ownership_option(self):
    # détention 2015– ; unlink(..., years=[2022], ownership_year=2022, end=2024)
    # → end_year 2021 ; une détention 2023–2023 du même actif → supprimée ;
    #   une détention 2026– → intacte
def test_unlink_without_ownership_option_keeps_ownership(self): ...
def test_unlink_nothing_selected_raises(self): ...
```

- [ ] **Step 2 :** lancer → FAIL. **Step 3 :** implémenter. **Step 4 :** relancer → PASS.
- [ ] **Step 5 : commit** `feat(flux): suppression par années et retrait de liens sur une plage`

---

### Task 3 : API sur une plage

**Files :**
- Modify : `dashboard/views_flow_map.py`, `dashboard/urls.py`, `locale/en/LC_MESSAGES/django.po` (+ `.mo`)
- Test : `dashboard/tests_flow_map.py`

**Interfaces :**
- Consumes : tâches 1–2.
- Produces (namespace `dashboard`) :
  - `_parse_range(request.GET) -> (start, end)` : `start` et `end` tous deux absents → `(None, None)` ; un seul présent, non entier, hors 1900–2100 → 400 `{'errors': {'start'|'end': [...]}}` ; `start > end` → 400 `{'errors': {'end': [_('La fin de la plage doit suivre son début.')]}}`.
  - `GET api/flow-map/<company_pk>/?start=&end=` → `flow_map_data` (remplace `?year=`).
  - `GET api/flow-map/<int:company_pk>/flows/<int:pk>/years/?start=&end=` → `flow_map_flow_years` (lecture ouverte) → `{'years': [{'year', 'count'}]}` ; plage obligatoire.
  - `POST api/flow-map/<int:company_pk>/flows/<int:pk>/delete/` → `flow_map_flow_delete` (**remplace** l'ancienne route sans entreprise ; Créateur) : corps `{start, end, years: [int]}` → 200 `{'deleted': int}` ; `ValueError` → 400 ; flux absent → 404 JSON existant.
  - `flow_map_unlink` : GET `?start=&end=&block=` → `unlink_preview` ; POST (Créateur) même query + corps JSON `{years: [int], ownership_year: int | null}` → `unlink`.
  - Le page view `flow_map` passe `build_flow_map(company, None, None, user)` en données initiales.

- [ ] **Step 1 : tests qui échouent** — adapter `FlowMapPageTests`, `FlowWriteApiTests` (delete), `MapApiTests` (unlink) aux nouvelles routes et paramètres, et ajouter :

```python
def test_data_uses_range(self): ...                      # ?start=2020&end=2024 → data['start'], data['end']
def test_data_rejects_inverted_range(self): ...          # 400, 'end' in errors
def test_data_rejects_single_bound(self): ...
def test_flow_years_endpoint(self): ...
def test_delete_flow_selected_years(self): ...
def test_delete_flow_rejects_year_outside_range(self): ...   # 400, rien supprimé
def test_delete_flow_refused_for_subscriber(self): ...       # 403
def test_unlink_with_years_and_ownership_year(self): ...
def test_unlink_with_nothing_selected_is_refused(self): ...  # 400, rien modifié
```

- [ ] **Step 2 :** lancer → FAIL. **Step 3 :** implémenter (+ entrées EN des nouveaux messages, `.mo` recompilé). **Step 4 :** relancer → PASS, puis la suite complète.
- [ ] **Step 5 : commit** `feat(flux): API de la carte sur une plage d'années`

---

### Task 4 : interface — plage, choix des années, légende cliquable

**Files :**
- Modify : `dashboard/static/dashboard/js/flow_map.js`, `flow_map_draw.js`, `flow_map_panel.js`, `flow_map_blocks.js`, `flow_map_ui.js` (si un composant partagé y a sa place), `dashboard/static/dashboard/css/flow_map.css`, `dashboard/templates/dashboard/flow_map.html` (+ partiels), `locale/en/LC_MESSAGES/djangojs.po` (+ `.mo`), `django.po` (+ `.mo`) pour les nouvelles chaînes de gabarit.

**Interfaces :**
- Consumes : routes de la tâche 3.
- Produces : `FlowMapPanel.chooseYears(options) -> Promise<result | null>` — boîte de dialogue accessible (même modale que `confirm`) listant des années à cases **toutes cochées par défaut**, avec un message, et un bloc optionnel « Mettre fin à la détention par %(company)s à partir de [année] » (case cochée par défaut + `<select>` des années de la plage pré-rempli). `result = {years: [int], ownershipYear: int | null}` ; `null` si annulé. Bouton de confirmation désactivé quand aucune année n'est cochée et que l'option de détention est absente ou décochée.

Comportements (spec §10) :
- Barre d'outils : « De » / « À » (années `years` + saisie libre bornée 1900–2100) à la place du sélecteur d'année ; `De ≤ À` contrôlé côté client (message, pas de requête) ; valeurs par défaut = `start`/`end` du modèle ; la plage reste celle choisie quand on change d'entreprise (dans la session de la page).
- Étiquette de flèche : année ajoutée (« Soja · 2021 ») si tous les flux de la flèche ont la même année et qu'elle diffère de `end` ; panneau : année de chaque flux visible (sélecteur de flux et formulaire).
- Nouveau flux : année pré-remplie avec `end`. Ajout d'un actif « détenu » : champ année ajouté à la fiche de détention, pré-rempli avec `end`, envoyé à la place de l'année unique.
- Supprimer un flux : `GET flow_map_flow_years` → `chooseYears` (message « Supprimer « %(flow)s » pour les années : ») → `POST flow_map_flow_delete` avec les années cochées.
- Supprimer les liens : `GET flow_map_unlink` → `chooseYears` avec les années et leurs nombres de flux (`ngettext` « %(year)s — %(n)s flux »), le bloc de détention si `ownership` (année par défaut `ownership_year`), la phrase des copropriétaires si `co_owners` → `POST` `{years, ownership_year}`.
- Légende : chaque entrée devient un bouton (`aria-pressed`) qui masque / réaffiche les flèches de cette nature (`state.hiddenKinds`), entrée estompée quand masquée, utilisable au clavier ; les blocs restent affichés.

- [ ] **Step 1 : implémenter.**
- [ ] **Step 2 : vérification manuelle** (Edge sans affichage piloté par un script Node, sur une **copie** de la base, comme les tâches 7–9 du plan précédent) : plage par défaut ; plage 2020–2024 avec un flux en 2021 et 2023 → seule 2023 affichée, étiquette sans année ; flux seulement en 2021 → étiquette « · 2021 » ; plage inversée → message ; suppression d'un flux en décochant une année → l'autre reste ; retrait de liens d'un actif détenu avec et sans l'option de détention ; légende : masquer / réafficher une nature au clic et au clavier ; Abonné : aucune action d'écriture ; anglais via le drapeau. Console sans erreur.
- [ ] **Step 3 :** `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow_map.py` → PASS.
- [ ] **Step 4 : commit** `feat(flux): plage d'années, choix des années à supprimer et légende cliquable`
