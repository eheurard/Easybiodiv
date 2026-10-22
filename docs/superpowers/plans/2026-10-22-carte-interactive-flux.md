# Carte interactive des flux — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** une page qui dessine, pour une entreprise et une année, ses actifs, ses
partenaires et le milieu en blocs reliés par des courbes, et permet d'y ajouter,
modifier et supprimer des flux, des détentions et des groupes d'actifs.

**Architecture :** le serveur calcule tout ce qui est testable : périmètre, clés de
blocs, colonnes du rangement, groupes, et expose une API JSON interne (lecture +
écritures via formulaires Django). Le navigateur dessine en SVG natif (agrégation des
flèches, groupes repliés / dépliés, zoom, masquage) et pilote un panneau latéral pour
les saisies. Un nouveau modèle `AssetGroup` (+ `AssetGroupMember`) ; aucune autre
modification de schéma.

**Tech Stack :** Django 6.0.5, Python 3.11+, SQLite (dev et prod), pytest-django,
JS vanilla + SVG, MapLibre GL 4 (CDN, déjà utilisé) pour la mini-carte de création
d'actif.

**Spec :** `docs/superpowers/specs/2026-10-22-carte-interactive-flux-design.md`
Maquettes : `.superpowers/brainstorm/30-1792658953/content/carte-flux.html` (style
« A — Courbe lisse ») et `fiche-flux.html`.

## Global Constraints

- HTML / CSS / JS vanilla, aucune bibliothèque de graphe ; SVG natif. MapLibre via
  `https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js` (même URL que les autres pages).
- Code compatible SQLite **et** PostgreSQL : champs standards, `UniqueConstraint`
  simple, pas de fonctions spécifiques.
- **Seul `dashboard/services/flows.py` filtre `Flow`** (règle du module). Les autres
  modules appellent ses fonctions. Les écritures (`save`, `delete`) d'un `Flow` déjà
  obtenu sont permises ailleurs.
- Chaque nouveau modèle déclare `verbose_name` et `verbose_name_plural`, chaque champ
  `verbose_name` (sinon `tests_admin_console.py::ModelLabelTests` échoue).
- Nouveau modèle métier : `created_at`, `updated_at`, `created_by`.
- Écritures uniquement via `forms.ModelForm` / `forms.Form` ; réponse
  `JsonResponse({'errors': {champ: [messages]}}, status=400)` comme `portfolio_save`.
- Écritures réservées à `User.role == 'CREATOR'` ; lecture ouverte (comme les autres
  pages du dashboard, pas de `login_required`).
- Tout texte visible est traduisible : `{% translate %}` dans les gabarits,
  `gettext`/`gettext_lazy` en Python, `gettext()`/`interpolate()` en JS. Pas de
  f-string dans un message traduit. Nombres affichés via `toLocaleString(APP_LOCALE)`.
- Charte `DESIGN.md` (palette Terra Insight). Couleurs par nature (maquette validée) :
  SUPPLY `#91452d`, CONSUMPTION `#3d7ea6`, EMISSION `#7b7366`, WASTE `#8a8f3c`,
  PRODUCTION `#d08a3a` ; bandeau milieu fond `#e3ecdf`, trait `#6f8f68`.
- Lignes ≤ 100 caractères ; imports triés stdlib / Django / tiers / locaux.
- Commandes depuis la racine, sous PowerShell, avec `.\venv\Scripts\python.exe`.
- Commits en français, à l'impératif, un sujet par commit, terminés par
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Ne jamais lancer `GOLDEN_RECORD=1` ; ne pas toucher aux migrations existantes.

## Review Focus

1. **Quantité saisie à la française** (« 12 400 », « 12,5 ») : acceptée et lue
   12400 / 12.5, pas d'erreur « nombre invalide ». → Tâche 5,
   `test_create_flow_accepts_french_number`.
2. **Latitude / longitude hors bornes** à la création d'un actif (lat 95) : refusée avec
   un message sur le champ, pas d'actif enregistré. → Tâche 6,
   `test_create_asset_rejects_latitude_out_of_range`.
3. **Actif déjà détenu à 100 % par une autre entreprise** coché « détenu » : refus
   lisible venant d'`Ownership.clean`, pas d'erreur 500. → Tâche 6,
   `test_ownership_over_full_share_is_refused`.
4. **Approvisionnement d'un bloc vers lui-même** (clic « + » puis le même bloc) :
   message `SUPPLY_SELF_LOOP_MESSAGE`, pas d'IntegrityError. → Tâche 5,
   `test_create_supply_to_itself_returns_rule_message`.
5. **Flux supprimé entre-temps** (autre onglet) puis modifié : 404 JSON, le panneau
   affiche « Ce flux n'existe plus » et recharge la carte. → Tâche 5,
   `test_update_missing_flow_returns_404`.

---

## Carte des fichiers

| Fichier | Rôle | Tâches |
|---|---|---|
| `dashboard/models.py` | `AssetGroup`, `AssetGroupMember` | 1 |
| `dashboard/migrations/0057_add_asset_group.py` | migration | 1 |
| `dashboard/admin.py`, `dashboard/admin_site.py` | admin des groupes | 1 |
| `dashboard/services/flows.py` | `perimeter_flows`, `perimeter_years` | 2 |
| `dashboard/services/flow_map.py` (nouveau) | clés de blocs, colonnes, données de la carte, retrait de liens | 3, 4 |
| `dashboard/forms.py` | formulaires de la carte | 5, 6 |
| `dashboard/decorators.py` (nouveau) | `creator_required_json` | 5 |
| `dashboard/views_flow_map.py` (nouveau) | page + API JSON de la carte | 5, 6, 7 |
| `dashboard/urls.py` | routes | 5, 6, 7 |
| `dashboard/templates/dashboard/flow_map.html` (nouveau) | gabarit | 7 |
| `templates/base.html` | lien dans le pied de barre latérale | 7 |
| `dashboard/static/dashboard/css/flow_map.css` (nouveau) | styles de la page | 7, 8, 9 |
| `dashboard/static/dashboard/js/flow_map_draw.js` (nouveau) | rendu SVG pur | 7 |
| `dashboard/static/dashboard/js/flow_map.js` (nouveau) | contrôleur de page | 7, 8, 9 |
| `dashboard/static/dashboard/js/flow_map_panel.js` (nouveau) | panneau latéral, fiches, recherche | 8, 9 |
| `dashboard/tests_flow_map.py` (nouveau) | tous les tests Python de la fonctionnalité | 1–7 |
| `locale/en/LC_MESSAGES/*.po/.mo` | traductions | 10 |
| `CLAUDE.md` | mention du modèle `AssetGroup` et de la page | 10 |

## Clés de blocs (contrat partagé serveur ↔ JS)

Chaînes : `company:<id>`, `asset:<id>`, `country:<id>`, `region:<id>`, `group:<id>`,
`environment`, `unknown-in` (origine inconnue), `unknown-out` (destination inconnue).
Un côté de flux vide (ni FK ni milieu) vaut `unknown-in` côté origine et `unknown-out`
côté destination.

---

### Task 1 : modèle des groupes d'actifs

**Files :**
- Modify : `dashboard/models.py` (après `Ownership`)
- Create : `dashboard/migrations/0057_add_asset_group.py` (via `makemigrations --name add_asset_group`)
- Modify : `dashboard/admin.py`, `dashboard/admin_site.py` (`GROUPS`, groupe « Entreprises & actifs », après `m.Ownership`)
- Test : `dashboard/tests_flow_map.py`

**Interfaces :**
- Produces :
  - `AssetGroup(name: CharField 255, company: FK Company CASCADE related_name='asset_groups', created_at, updated_at, created_by: FK user SET_NULL)` ; verbose_name « Groupe d'actifs » / « Groupes d'actifs » ; `__str__` = `name`.
  - `AssetGroupMember(group: FK AssetGroup CASCADE related_name='members', asset: FK Asset CASCADE related_name='+', company: FK Company CASCADE related_name='+')` ; verbose_name « Membre de groupe » / « Membres de groupe » ; `UniqueConstraint(fields=['company', 'asset'], name='asset_group_member_one_group_per_company', violation_error_message="Cet actif appartient déjà à un groupe de cette entreprise.")`. `save()` recopie `company_id = group.company_id`.
  - `AssetGroup.set_members(asset_ids: Iterable[int]) -> None` : remplace les membres (suppression des absents, création des nouveaux), dans une transaction.

- [ ] **Step 1 : écrire les tests qui échouent** (`AssetGroupModelTests`)

```python
def test_set_members_replaces_members(self):
    group = AssetGroup.objects.create(name='Usines Europe', company=self.acme)
    group.set_members([self.a1.pk, self.a2.pk])
    group.set_members([self.a2.pk, self.a3.pk])
    self.assertEqual(
        sorted(group.members.values_list('asset_id', flat=True)), [self.a2.pk, self.a3.pk])

def test_member_copies_group_company(self):
    group = AssetGroup.objects.create(name='G', company=self.acme)
    group.set_members([self.a1.pk])
    self.assertEqual(group.members.get().company_id, self.acme.pk)

def test_asset_cannot_be_in_two_groups_of_same_company(self):
    g1 = AssetGroup.objects.create(name='G1', company=self.acme)
    g2 = AssetGroup.objects.create(name='G2', company=self.acme)
    g1.set_members([self.a1.pk])
    with self.assertRaises(IntegrityError), transaction.atomic():
        g2.set_members([self.a1.pk])

def test_asset_can_be_grouped_by_two_companies(self):
    other = Company.objects.create(name='Other')
    AssetGroup.objects.create(name='G1', company=self.acme).set_members([self.a1.pk])
    AssetGroup.objects.create(name='G2', company=other).set_members([self.a1.pk])
    self.assertEqual(AssetGroupMember.objects.filter(asset=self.a1).count(), 2)
```

`setUp` : `self.acme`, un `Country`, trois `Asset` (`a1`, `a2`, `a3` ; lat/long quelconques).

- [ ] **Step 2 :** `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow_map.py -v` → FAIL (ImportError `AssetGroup`).
- [ ] **Step 3 : implémenter les deux modèles, `set_members`, la migration `0057_add_asset_group`, l'admin** (`AssetGroupAdmin` avec `AssetGroupMember` en `TabularInline` sans le champ `company`, `search_fields=('name', 'company__name')`, `list_display=('name', 'company')`). Ajouter `m.AssetGroup` à `GROUPS` (après `m.Ownership`). `AssetGroupMember` n'est **pas** enregistré dans l'admin (inline seulement) : le contrôle de `tests_admin_console.py` ne porte que sur les modèles enregistrés, il n'a donc pas à figurer dans `GROUPS`.
- [ ] **Step 4 :** `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow_map.py dashboard/tests_admin_console.py -v` → PASS.
- [ ] **Step 5 : commit** `feat(flux): modèle des groupes d'actifs`

---

### Task 2 : lecture du périmètre dans `flows.py`

**Files :**
- Modify : `dashboard/services/flows.py`
- Test : `dashboard/tests_flow_map.py`

**Interfaces :**
- Produces :
  - `perimeter_flows(company, year, touching=None) -> QuerySet[Flow]` : flux de l'année `year` dont une extrémité est `company` ou un actif de `Asset.objects.owned_by(company, year)` ; `select_related(*_ENDPOINT_RELATIONS)`, `order_by('pk')`. `touching` : `(endpoint, pk)` avec `endpoint` ∈ `ENDPOINT_ASSET`, `ENDPOINT_REGION`, `ENDPOINT_COUNTRY`, `ENDPOINT_COMPANY` → ne garde que les flux dont l'origine ou la destination est cet élément.
  - `perimeter_years(company) -> list[int]` : années (triées croissantes, sans doublon) des flux touchant `company` ou un actif qu'elle détient **cette année-là** (même règle que `perimeter_flows`).

- [ ] **Step 1 : tests qui échouent** (`PerimeterFlowsTests`). Données : Acme détient `vevey` (2020–), `rotterdam` (2020–2023) ; Cargill ; Brésil.

```python
def test_includes_flows_touching_company_or_owned_assets(self):
    f1 = make_supply(what=self.soja, year=2024, quantity=5,
                     origin=self.cargill, destination=self.vevey)
    f2 = make_declared_emission(company=self.acme, year=2024, scope='Scope 1', value=3)
    self.assertEqual(list(perimeter_flows(self.acme, 2024)), [f1, f2])

def test_excludes_other_year_and_outside_flows(self):
    make_supply(what=self.soja, year=2023, quantity=5,
                origin=self.cargill, destination=self.vevey)
    make_supply(what=self.soja, year=2024, quantity=5,
                origin=self.brazil, destination=self.cargill)
    self.assertEqual(list(perimeter_flows(self.acme, 2024)), [])

def test_excludes_asset_no_longer_owned(self):
    make_inventory(asset=self.rotterdam, key='water', year=2024, value=1)
    self.assertEqual(list(perimeter_flows(self.acme, 2024)), [])

def test_touching_filters_on_one_block(self):
    f1 = make_supply(what=self.soja, year=2024, quantity=5,
                     origin=self.cargill, destination=self.vevey)
    make_inventory(asset=self.vevey, key='water', year=2024, value=1)
    self.assertEqual(
        list(perimeter_flows(self.acme, 2024, touching=(ENDPOINT_COMPANY, self.cargill.pk))),
        [f1])

def test_perimeter_years(self):
    make_inventory(asset=self.vevey, key='water', year=2022, value=1)
    make_inventory(asset=self.rotterdam, key='water', year=2021, value=1)
    make_inventory(asset=self.rotterdam, key='water', year=2024, value=1)  # plus détenu
    self.assertEqual(perimeter_years(self.acme), [2021, 2022])
```

- [ ] **Step 2 :** lancer `dashboard/tests_flow_map.py -k Perimeter` → FAIL.
- [ ] **Step 3 : implémenter.** `perimeter_years` : itérer sur les années distinctes des flux touchant l'entreprise ou un actif qu'elle a détenu à un moment (`Ownership.objects.filter(company=...)`), puis ne garder que celles où `perimeter_flows(company, y).exists()`.
- [ ] **Step 4 :** relancer → PASS.
- [ ] **Step 5 : commit** `feat(flux): lecture du périmètre d'une entreprise`

---

### Task 3 : données de la carte et rangement en colonnes

**Files :**
- Create : `dashboard/services/flow_map.py`
- Test : `dashboard/tests_flow_map.py`

**Interfaces :**
- Consumes : `perimeter_flows`, `perimeter_years` (tâche 2) ; `AssetGroup` (tâche 1).
- Produces :
  - `endpoint_key(flow, side: str) -> str` (`side` ∈ `'from'`, `'to'`) selon le contrat des clés.
  - `parse_key(key: str) -> tuple[str, int | None]` : `'asset:5'` → `('asset', 5)`, `'environment'` → `('environment', None)`, `'unknown-in'`/`'unknown-out'` → `(None, None)` ; `ValueError` sinon.
  - `endpoint_fields(side: str, key: str) -> dict` : champs de formulaire `Flow` d'un côté, ex. `('from', 'asset:5')` → `{'from_asset': 5, 'from_region': None, 'from_country': None, 'from_company': None, 'from_environment': False}`. Refuse `group:*` (`ValueError`).
  - `assign_columns(nodes: list[str], edges: list[tuple[str, str]]) -> dict[str, int]`.
  - `build_flow_map(company, year: int | None, user) -> dict` (forme ci-dessous). `year=None` → défaut : dernière de `perimeter_years`, sinon année en cours.

**Algorithme de `assign_columns`** (pas déterminé par les tests seuls) : ignorer les
arêtes touchant `environment` ; casser les cycles en retirant les arêtes arrière
trouvées par un DFS qui visite les nœuds dans l'ordre de `nodes` ; colonne = longueur
du plus long chemin entrant (sources = 0) ; nœud isolé = 0 ; `unknown-out`, s'il est
présent, est forcé à `max(autres colonnes) + 1`. `environment` n'a pas de colonne.

**Forme de `build_flow_map`** :

```python
{
  'company': {'id': int, 'name': str},
  'year': int,
  'years': list[int],          # perimeter_years ∪ {année en cours} ∪ {year}, trié
  'can_edit': bool,            # user.is_authenticated and user.role == 'CREATOR'
  'blocks': [{'key', 'type', 'id', 'name', 'owned': bool, 'group': 'group:<id>' | None,
              'column': int}],  # company, actifs détenus, autres extrémités, unknown-*
  'groups': [{'key', 'id', 'name', 'members': [clé d'actif], 'owned': bool,
              'column': int}],
  'flows': [{'id', 'kind', 'kind_label', 'from', 'to', 'what': {'id', 'name', 'unit'},
             'quantity', 'year', 'tier', 'scope', 'source', 'reference'}],
}
```

Règles : `type` ∈ `company`, `asset`, `country`, `region`, `unknown` ; `owned` vrai
pour l'entreprise et ses actifs détenus ; les groupes de l'entreprise ne sont listés que
s'ils ont au moins un membre parmi les blocs, avec ces membres seulement ; colonnes
calculées **groupes repliés** (chaque membre remplacé par la clé du groupe, arêtes
internes au groupe retirées) ; un membre reçoit la colonne de son groupe.

- [ ] **Step 1 : tests qui échouent**

```python
class AssignColumnsTests(SimpleTestCase):
    def test_chain_left_to_right(self):
        cols = assign_columns(['a', 'b', 'c'], [('a', 'b'), ('b', 'c')])
        self.assertEqual(cols, {'a': 0, 'b': 1, 'c': 2})
    def test_longest_path_wins(self):
        cols = assign_columns(['a', 'b', 'c'], [('a', 'b'), ('b', 'c'), ('a', 'c')])
        self.assertEqual(cols['c'], 2)
    def test_cycle_does_not_loop(self):
        cols = assign_columns(['a', 'b'], [('a', 'b'), ('b', 'a')])
        self.assertEqual(cols, {'a': 0, 'b': 1})
    def test_environment_ignored_and_unknown_out_last(self):
        cols = assign_columns(
            ['a', 'b', 'c', 'unknown-out'],
            [('a', 'b'), ('b', 'c'), ('a', 'unknown-out'), ('environment', 'b')])
        self.assertEqual(cols['unknown-out'], 3)
        self.assertNotIn('environment', cols)

class EndpointKeyTests(TestCase):
    # endpoint_key / parse_key / endpoint_fields sur un flux de chaque forme,
    # dont production (to = 'unknown-out') et consommation d'origine inconnue
    # (from = 'unknown-in') ; endpoint_fields('from', 'group:1') lève ValueError.

class BuildFlowMapTests(TestCase):
    def test_blocks_and_flows(self):
        # Acme détient vevey ; Cargill → vevey (SUPPLY), milieu → vevey (eau),
        # production vevey ; données = build_flow_map(acme, 2024, AnonymousUser())
        self.assertEqual({b['key'] for b in data['blocks']},
                         {f'company:{acme.pk}', f'asset:{vevey.pk}',
                          f'company:{cargill.pk}', 'unknown-out'})
        self.assertEqual(len(data['flows']), 3)
        self.assertFalse(data['can_edit'])
    def test_default_year_is_latest_with_flows_else_current(self): ...
    def test_group_collapsed_for_layout_and_members_share_column(self):
        # groupe {vevey, rotterdam} ; Cargill → vevey : la colonne du groupe vaut
        # celle de Cargill + 1 et vevey/rotterdam ont la colonne du groupe
    def test_group_without_present_member_is_omitted(self): ...
    def test_can_edit_for_creator(self): ...
```

- [ ] **Step 2 :** lancer → FAIL.
- [ ] **Step 3 : implémenter `dashboard/services/flow_map.py`** (lit `Flow` uniquement via `flows.py`).
- [ ] **Step 4 :** relancer → PASS.
- [ ] **Step 5 : commit** `feat(flux): données et rangement de la carte des flux`

---

### Task 4 : retrait des liens d'un bloc

**Files :**
- Modify : `dashboard/services/flow_map.py`
- Test : `dashboard/tests_flow_map.py`

**Interfaces :**
- Consumes : `perimeter_flows(..., touching=...)`, `parse_key`.
- Produces :
  - `unlink_preview(company, year: int, key: str) -> dict` : `{'flows': int, 'ownership': bool}`. `ownership` vrai si `key` est un actif détenu par `company` en `year`.
  - `unlink(company, year: int, key: str) -> dict` : même forme, effectue la suppression dans une transaction : supprime `perimeter_flows(company, year, touching=…)` ; si actif détenu, `end_ownership(company, asset, year)`. N'efface jamais l'élément, ne touche pas aux groupes.
  - `end_ownership(company, asset, year: int) -> None` : pour chaque détention `valid_in(year)` de ce couple : supprimée si `start_year == year`, sinon `end_year = year - 1`. Détentions commençant après `year` : intactes.
  - `key` refusé (`ValueError`) pour `company:<id de company>`, `group:*`, `environment`, `unknown-*`.

- [ ] **Step 1 : tests qui échouent** (`UnlinkTests`)

```python
def test_preview_counts_only_displayed_year(self):
    # Cargill → vevey en 2023 et 2024 (×2)
    self.assertEqual(unlink_preview(self.acme, 2024, f'company:{self.cargill.pk}'),
                     {'flows': 2, 'ownership': False})

def test_unlink_external_company_keeps_company_and_other_years(self):
    unlink(self.acme, 2024, f'company:{self.cargill.pk}')
    self.assertTrue(Company.objects.filter(pk=self.cargill.pk).exists())
    self.assertEqual(Flow.objects.filter(year=2023).count(), 1)

def test_unlink_owned_asset_ends_ownership_previous_year(self):
    # détention vevey 2020– ; unlink 2024 → end_year 2023, actif conservé
def test_unlink_ownership_starting_that_year_is_deleted(self): ...
def test_unlink_keeps_later_ownership(self):
    # détentions 2020–2022 et 2025– ; unlink 2021 → la seconde est intacte
def test_unlink_keeps_group_membership(self): ...
def test_unlink_refuses_the_company_itself(self):
    with self.assertRaises(ValueError):
        unlink(self.acme, 2024, f'company:{self.acme.pk}')
```

- [ ] **Step 2 :** lancer → FAIL. **Step 3 :** implémenter. **Step 4 :** relancer → PASS.
- [ ] **Step 5 : commit** `feat(flux): retrait des liens d'un bloc avec le périmètre`

---

### Task 5 : API d'écriture des flux

**Files :**
- Create : `dashboard/decorators.py`, `dashboard/views_flow_map.py`
- Modify : `dashboard/forms.py`, `dashboard/urls.py`
- Test : `dashboard/tests_flow_map.py`

**Interfaces :**
- Consumes : `endpoint_fields`, `parse_key` (tâche 3).
- Produces :
  - `creator_required_json(view)` : anonyme ou non-Créateur → `JsonResponse({'errors': {'__all__': [_('Accès réservé aux créateurs.')]}}, status=403)`.
  - `FlowMapFlowForm(forms.ModelForm)` sur `Flow`, champs : `kind, what, scope, from_asset, from_region, from_country, from_company, from_environment, to_asset, to_region, to_country, to_company, to_environment, year, quantity, tier, source, reference` (tous les champs d'extrémité sont dans le formulaire pour que `full_clean` valide les `CheckConstraint`). `quantity` : `forms.CharField` converti dans `clean_quantity` → `float` après retrait des espaces (dont U+00A0 et U+202F) et remplacement de `,` par `.` ; message `_('Quantité invalide.')` ; strictement > 0 sinon `_('La quantité doit être positive.')`.
  - Routes (namespace `dashboard`), toutes `POST`, JSON en corps :
    - `api/flow-map/flows/` → `flow_map_flow_create` : corps `{kind, what_id, quantity, year, tier?, scope?, source?, reference?, from: clé, to: clé}` → 201 `{'id': int}`.
    - `api/flow-map/flows/<int:pk>/` → `flow_map_flow_update` : mêmes champs **sans** `from`/`to` (extrémités de l'instance conservées) → 200 `{'id'}`.
    - `api/flow-map/flows/<int:pk>/delete/` → `flow_map_flow_delete` → 200 `{'deleted': pk}`.
  - `created_by = request.user` à la création. Clé invalide (`ValueError`) → 400 `{'errors': {'__all__': [...]}}`. `pk` absent → 404 JSON `{'errors': {'__all__': [_("Ce flux n'existe plus.")]}}`.

- [ ] **Step 1 : tests qui échouent** (`FlowWriteApiTests`, client connecté en Créateur sauf mention)

```python
def test_anonymous_and_subscriber_are_refused(self):  # 403 JSON, aucun Flow créé
def test_create_supply(self):
    r = self._post('dashboard:flow_map_flow_create', {
        'kind': 'SUPPLY', 'what_id': self.soja.pk, 'quantity': 12, 'year': 2024,
        'from': f'company:{self.cargill.pk}', 'to': f'asset:{self.vevey.pk}'})
    self.assertEqual(r.status_code, 201)
    flow = Flow.objects.get(pk=r.json()['id'])
    self.assertEqual((flow.from_company, flow.to_asset, flow.created_by),
                     (self.cargill, self.vevey, self.creator))
def test_create_consumption_from_environment(self): ...
def test_create_production_to_unknown(self):  # to = 'unknown-out' → tous les to_* vides
def test_create_flow_accepts_french_number(self):
    # quantity '12 400,5' → 12400.5
def test_create_supply_to_itself_returns_rule_message(self):
    # from = to = asset:vevey → 400, SUPPLY_SELF_LOOP_MESSAGE dans errors['__all__']
def test_kind_forbidden_by_rules_returns_rule_message(self):
    # EMISSION de 'country:…' vers 'environment' → 400, message FLOW_RULES['EMISSION']
def test_update_keeps_endpoints(self):
    # corps avec from/to différents → ignorés, quantité mise à jour
def test_update_missing_flow_returns_404(self): ...
def test_delete(self): ...
```

- [ ] **Step 2 :** lancer → FAIL.
- [ ] **Step 3 : implémenter** formulaire, décorateur, vues (`require_POST`, `json.loads`, construire le dict de données du formulaire à partir du corps et d'`endpoint_fields`), routes.
- [ ] **Step 4 :** relancer → PASS.
- [ ] **Step 5 : commit** `feat(flux): API d'écriture des flux de la carte`

---

### Task 6 : API de recherche, création d'éléments, détentions, groupes, retrait

**Files :**
- Modify : `dashboard/forms.py`, `dashboard/views_flow_map.py`, `dashboard/urls.py`
- Test : `dashboard/tests_flow_map.py`

**Interfaces :**
- Consumes : `creator_required_json` (5), `unlink_preview`, `unlink` (4), `AssetGroup.set_members` (1).
- Produces (routes namespace `dashboard`) :
  - `GET api/flow-map/search/?type=<asset|company|country|region|commodity>&q=<texte>` → `flow_map_search` (lecture ouverte) : 20 résultats max, `name__icontains=q`, triés par nom ; `q` de moins de 2 caractères → `[]`. Réponse `{'results': [{'id', 'name', 'detail'}]}` ; `detail` = pays pour un actif et une région, unité pour une commodité, `''` sinon. `type` inconnu → 400.
  - `POST api/flow-map/assets/` → `flow_map_asset_create` (`AssetQuickForm`, champs `name, country, subnational_region, type, latitude, longitude` ; latitude ∈ [-90, 90], longitude ∈ [-180, 180] avec message sur le champ) → 201 `{'id', 'name'}`.
  - `POST api/flow-map/companies/` → `flow_map_company_create` (`CompanyQuickForm` : `name`, `isin`, `ticker` facultatifs ; vides → défaut du modèle `"0"`) → 201.
  - `POST api/flow-map/commodities/` → `flow_map_commodity_create` (`CommodityQuickForm` : `name`, `unit` défaut `tonnes`) → 201 `{'id', 'name', 'unit'}`.
  - `POST api/flow-map/ownerships/` → `flow_map_ownership_create` : corps `{company_id, asset_id, share, year}` → `OwnershipQuickForm` (ModelForm, `start_year = year`, `end_year` vide, `share` en fraction 0–1 ; le JS envoie `pourcentage / 100`) → 201. Les erreurs d'`Ownership.clean` (chevauchement, somme des parts) remontent en 400.
  - `POST api/flow-map/<int:company_pk>/groups/` → `flow_map_group_create` : `{name, members: [asset_id]}` → 201 `{'id'}`.
  - `POST api/flow-map/groups/<int:pk>/` → `flow_map_group_update` (même corps) ; `POST api/flow-map/groups/<int:pk>/delete/` → `flow_map_group_delete`.
    `AssetGroupForm.clean` refuse un actif déjà membre d'un **autre** groupe de la même entreprise : `_('« %(asset)s » appartient déjà au groupe « %(group)s ».')`.
  - `GET api/flow-map/<int:company_pk>/unlink/?year=&block=` → `flow_map_unlink` renvoie `unlink_preview` (lecture ouverte) ; `POST` sur la même route (Créateur) exécute `unlink` → `{'flows', 'ownership'}`. `ValueError` → 400.

- [ ] **Step 1 : tests qui échouent** (`MapApiTests`)

```python
def test_search_assets_by_keyword(self):
    r = self.client.get(reverse('dashboard:flow_map_search'), {'type': 'asset', 'q': 'vev'})
    self.assertEqual(r.json()['results'],
                     [{'id': self.vevey.pk, 'name': 'Usine Vevey', 'detail': 'Suisse'}])
def test_search_short_query_returns_nothing(self): ...
def test_create_asset(self): ...
def test_create_asset_rejects_latitude_out_of_range(self):
    # latitude 95 → 400, 'latitude' in errors, Asset.objects.count() inchangé
def test_create_company_with_name_only(self): ...
def test_create_commodity_default_unit(self): ...
def test_create_ownership_starts_at_year(self): ...
def test_ownership_over_full_share_is_refused(self):
    # vevey détenu à 1 par Other depuis 2020 ; Acme share 1 en 2024 → 400 lisible
def test_group_create_update_delete(self): ...
def test_group_refuses_asset_of_another_group(self): ...
def test_unlink_preview_then_unlink(self): ...
def test_writes_refused_for_subscriber(self):  # une route POST de chaque famille → 403
```

- [ ] **Step 2 :** lancer → FAIL. **Step 3 :** implémenter. **Step 4 :** relancer → PASS.
- [ ] **Step 5 : commit** `feat(flux): recherche, créations, détentions, groupes et retrait de liens`

---

### Task 7 : page en lecture — rendu de la carte

**Files :**
- Modify : `dashboard/views_flow_map.py`, `dashboard/urls.py`, `templates/base.html`
- Create : `dashboard/templates/dashboard/flow_map.html`, `dashboard/static/dashboard/css/flow_map.css`, `dashboard/static/dashboard/js/flow_map_draw.js`, `dashboard/static/dashboard/js/flow_map.js`
- Test : `dashboard/tests_flow_map.py`

**Interfaces :**
- Consumes : `build_flow_map` (3) ; `CompanyCombobox` (`company_combobox.js`) ; `escHtml`, `fmtNum`, `APP_LOCALE` (`main.js`).
- Produces :
  - `GET flux/` → `flow_map` (page) ; contexte : `companies` (`id`, `name`), `initial_data` = `build_flow_map(première entreprise, None, user)` ou `None`, `flow_rules` (dict `{kind: {'origins': [...], 'destinations': [...]}}` issu de `FLOW_RULES`, `None` sérialisé `null`), `kinds` (`[{value, label}]`), `can_edit`. Sérialisation via `json_script` (`companies-data`, `initial-data`, `flow-rules`, `flow-kinds`).
  - `GET api/flow-map/<int:company_pk>/?year=` → `flow_map_data` → `JsonResponse(build_flow_map(...))`.
  - `window.FlowMapDraw` : `render(svg, model, state)`, où `state = {expanded: Set<groupKey>, hidden: Set<blockKey>, positions: Map<key,{x,y}>, selectedEdge: string|null}` ; `aggregateEdges(flows, model, state) -> [{key, from, to, kind, flows: [flow], total}]` ; `curve(p0, p3) -> string` (Bézier cubique en S, points de contrôle à mi-distance horizontale ; courbe verticale vers / depuis le bandeau).
  - Lien barre latérale : pied de barre, juste avant « Import / export Excel », libellé `{% translate "Carte des flux" %}`, `{% block nav_flow_map %}`.

Comportements à rendre (spec §4) : bandeau « Environnement » en haut sur toute la
largeur ; blocs par colonne (`column`), ordre vertical libre (limiter les croisements,
ex. barycentre des voisins) ; actifs détenus légèrement teintés ; groupes en « pile de
cartes », repliés par défaut, clic = déplier / replier ; `unknown-*` en pointillés,
affichés seulement s'ils servent ; une courbe par (origine, destination, nature) après
substitution des membres de groupes repliés (arêtes internes au groupe replié non
dessinées), épaisseur bornée 1,5–12 px proportionnelle à la quantité totale (relatif
dans la vue), étiquette « Soja +2 » ; légende des natures ; sélecteur d'année
(`years` + saisie libre d'une année) ; zoom molette et déplacement en glissant le fond
(via `viewBox`) ; glisser un bloc le déplace pour la session ; menu « ⋯ » d'un bloc avec
**Masquer** (pastille « N blocs masqués » pour tout réafficher) ; noms longs tronqués avec
`<title>` ; carte vide → message invitant à ajouter un bloc. Choix d'entreprise
mémorisé comme sur les autres pages (`CompanyCombobox`, `persist: true`).

- [ ] **Step 1 : tests qui échouent**

```python
def test_page_renders_with_initial_data(self):
    r = self.client.get(reverse('dashboard:flow_map'))
    self.assertEqual(r.status_code, 200)
    self.assertContains(r, 'id="flow-rules"')
    self.assertContains(r, 'flow_map.js')
def test_data_endpoint_uses_year(self):
    r = self.client.get(reverse('dashboard:flow_map_data', args=[self.acme.pk]),
                        {'year': 2023})
    self.assertEqual(r.json()['year'], 2023)
def test_data_endpoint_rejects_bad_year(self):  # year='abc' → 400
def test_sidebar_links_to_flow_map(self):
    r = self.client.get(reverse('dashboard:index'))
    self.assertContains(r, reverse('dashboard:flow_map'))
```

- [ ] **Step 2 :** lancer → FAIL. **Step 3 :** implémenter vues, gabarit, CSS, JS de rendu.
- [ ] **Step 4 :** relancer → PASS.
- [ ] **Step 5 : vérification visuelle.** `.\venv\Scripts\python.exe manage.py runserver`, ouvrir `/flux/` sur une entreprise de démo (`populate_acme` si besoin) : bandeau, colonnes amont → aval, courbes lisses colorées, groupe replié / déplié, zoom, masquer / réafficher, changement d'année et d'entreprise, console JS sans erreur, rendu en anglais via le drapeau.
- [ ] **Step 6 : commit** `feat(flux): page Carte des flux en lecture`

---

### Task 8 : saisie des flux sur la carte

**Files :**
- Create : `dashboard/static/dashboard/js/flow_map_panel.js`
- Modify : `dashboard/static/dashboard/js/flow_map.js`, `flow_map_draw.js`, `flow_map.css`, `dashboard/templates/dashboard/flow_map.html`

**Interfaces :**
- Consumes : routes de la tâche 5 ; `flow_map_search` (type `commodity`) et `flow_map_commodity_create` (tâche 6) ; `flow-rules`, `flow-kinds`.
- Produces : `window.FlowMapPanel` : `openNewFlow(fromKey, toKey)`, `openEdge(edge)`, `close()`, `confirm(message) -> Promise<boolean>` (fenêtre modale accessible, réutilisée en tâche 9) ; événement `flowmap:changed` émis après chaque écriture réussie (le contrôleur recharge `flow_map_data`).

Comportements (spec §5.1, §5.2) — seulement si `can_edit` :
- « + » sur les blocs : droite = sortant, gauche = entrant, haut = milieu ; absents sur
  les groupes repliés, `unknown-*` et (haut) sur les pays / régions. Mode « tracé » :
  clic « + », puis clic sur un bloc, sur `unknown-*` ou sur le fond (= inconnu) ;
  Échap annule ; le « + » du haut ouvre directement la fiche avec `environment`.
- Natures proposées = celles dont `flow-rules` admet le type de chaque extrémité
  (`asset`, `region`, `country`, `company`, `environment`, `null`) ; pour le « + » du
  haut : Consommation (milieu → bloc), Émission / Déchet (bloc → milieu). Aucune nature
  possible → message, pas de fiche.
- Fiche : commodité (recherche ≥ 2 caractères + « Créer « … » » qui demande l'unité),
  unité en lecture seule, quantité, année (pré-remplie), repli « Facultatif » : tier
  (0–3), scope (Émission seulement), source, référence. Erreurs serveur affichées
  (champ + `__all__`).
- Clic sur une flèche : panneau ouvert **directement en formulaire modifiable**,
  origine → destination en tête (non modifiables), Enregistrer / Supprimer (confirmation).
  Flèche agrégée : liste compacte des flux en haut (commodité · quantité · unité ;
  actif membre pour un groupe replié), le plus gros sélectionné, formulaire en dessous ;
  « + Ajouter un flux entre ces deux blocs » sauf groupe replié. Flèche en surbrillance
  tant que le panneau est ouvert ; ✕ ou Échap ferme sans enregistrer.
- 404 à l'enregistrement → message « Ce flux n'existe plus. » puis rechargement.
- Panneau et modale utilisables au clavier (focus piégé dans la modale, retour du focus).

- [ ] **Step 1 : implémenter.**
- [ ] **Step 2 : vérification manuelle** (`runserver`, compte Créateur) : créer un approvisionnement Cargill → actif, une consommation d'eau par le « + » du haut, une production vers le fond vide ; modifier une quantité « 12,5 » ; supprimer ; tenter un approvisionnement d'un bloc vers lui-même (message de règle) ; compte Abonné : aucun « + », aucune action d'écriture. Console sans erreur.
- [ ] **Step 3 :** `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow_map.py` → PASS.
- [ ] **Step 4 : commit** `feat(flux): saisie et modification des flux sur la carte`

---

### Task 9 : ajout de blocs, retrait de liens, groupes

**Files :**
- Modify : `flow_map.js`, `flow_map_panel.js`, `flow_map.css`, `flow_map.html` (CSS + script MapLibre)

**Interfaces :**
- Consumes : routes de la tâche 6 ; `FlowMapPanel.confirm`.

Comportements (spec §5.3–§5.5) — seulement si `can_edit` (sauf Masquer, tâche 7) :
- Barre d'outils « + Pays », « + Région », « + Entreprise », « + Actif », « + Groupe
  d'actifs ». Recherche par mot-clé ; « Créer » proposé pour actif / entreprise /
  commodité seulement (jamais pays / région).
- Création d'actif : nom, pays (recherche), région facultative, type, position par clic
  sur une mini-carte MapLibre (style `mapStyleFor(activeMapStyleName())` de `main.js`)
  ou saisie lat / long.
- Ajout d'un actif : case « détenu par <entreprise> » cochée, part 100 % modifiable →
  `flow_map_ownership_create` puis rechargement ; décochée → bloc de session (extérieur,
  colonne 0) jusqu'au premier flux. Pays / région / entreprise ajoutés : blocs de session.
- Menu « ⋯ » : **Supprimer les liens** → `GET flow_map_unlink` puis confirmation
  « Êtes-vous sûr de vouloir supprimer … ? » énumérant `ngettext` « %(n)s flux » et, si
  `ownership`, « … l'actif ne sera plus détenu par %(company)s à partir de %(year)s » →
  `POST`. Absent pour l'entreprise elle-même ; pour un groupe : « Supprimer le groupe »
  (confirmation).
- Groupe : création (nom + cases à cocher des actifs présents, avec filtre ; actifs déjà
  dans un autre groupe désactivés avec le nom du groupe), renommage et membres depuis le
  panneau du groupe.

- [ ] **Step 1 : implémenter.**
- [ ] **Step 2 : vérification manuelle** : ajouter un actif existant détenu (il apparaît dans le périmètre), créer un actif avec la mini-carte, ajouter une entreprise puis tracer un flux vers elle, supprimer les liens d'un fournisseur (confirmation chiffrée, l'entreprise reste dans la recherche), supprimer les liens d'un actif détenu (il disparaît l'année affichée, présent l'année d'avant), créer / modifier / supprimer un groupe, recharger la page : le groupe est toujours là.
- [ ] **Step 3 :** `pytest dashboard/tests_flow_map.py` → PASS.
- [ ] **Step 4 : commit** `feat(flux): ajout de blocs, groupes et retrait de liens sur la carte`

---

### Task 10 : traductions, documentation, suite complète

**Files :**
- Modify : `locale/en/LC_MESSAGES/django.po`, `djangojs.po` (+ `.mo`), `CLAUDE.md`

- [ ] **Step 1 :** régénérer les catalogues (commandes `makemessages` / `compilemessages` de `CLAUDE.md` §5) et traduire toutes les nouvelles chaînes en anglais (aucune entrée `fuzzy` ni vide pour les fichiers de la fonctionnalité).
- [ ] **Step 2 :** `CLAUDE.md` : dans §4 « Activité et finance », une ligne sur `AssetGroup` / `AssetGroupMember` (groupes d'actifs par entreprise, un actif dans un seul groupe par entreprise) ; dans la liste des fichiers de tests `dashboard`, ajouter `tests_flow_map.py`.
- [ ] **Step 3 :** `.\venv\Scripts\python.exe -m pytest` → tout vert (≈ 570 tests + les nouveaux) ; `.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → « No changes detected ».
- [ ] **Step 4 : commit** `chore(flux): traductions et documentation de la carte des flux`
