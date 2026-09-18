# Table `Flow` unique — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** remplacer `Production`, `AssetInventory`, l'ancien `Flow`, `SupplyNode`, `Exchange` et `Carbon_emission` par une table `Flow` unique, et refondre `Ownership`, sans changer les sorties JSON des pages.

**Architecture:** une table `Flow` (nature `kind`, commodité `what`, `scope`, 8 clés étrangères d'extrémité + 2 booléens « milieu ») dont les règles par nature vivent dans un dictionnaire `FLOW_RULES` qui génère les contraintes en base. Un seul module, `dashboard/services/flows.py`, lit la table ; les vues l'appellent. On migre domaine par domaine (inventaire, production, approvisionnement, émissions) : chaque tâche bascule les lectures d'un domaine puis supprime l'ancien modèle, et se termine avec la suite de tests verte et les fichiers golden inchangés.

**Tech Stack:** Django 6.0.5, Python 3.11+, SQLite (dev et prod), pytest-django, openpyxl.

**Spec:** `docs/superpowers/specs/2026-09-18-table-flow-unique-design.md`

## Global Constraints

- Code compatible SQLite **et** PostgreSQL : uniquement champs standards, `ForeignKey`, `CheckConstraint`. Pas de `JSONField` spécifique PostgreSQL, pas de `nulls_distinct`.
- Chaque modèle `dashboard` déclare `verbose_name` **et** `verbose_name_plural` ; chaque champ déclare `verbose_name` (sinon `dashboard/tests_admin_console.py::ModelLabelTests` échoue).
- Nouveau code : champs en `snake_case`, classes en `CamelCase` sans underscore ; lignes ≤ 100 caractères ; imports triés stdlib / Django / tiers / locaux.
- Pas de migration des données existantes (spec, décision 2) : les anciennes tables sont supprimées avec leur contenu.
- Ne jamais supprimer ni modifier une migration historique (`0001` à `0048`).
- Les 9 fichiers `dashboard/golden/*.json` doivent rester **strictement identiques**. Ne jamais lancer `GOLDEN_RECORD=1`.
- Une migration = un changement logique, avec un nom explicite. La numérotation diffère du tableau §7 de la spec (autorisé par la note de ce §7) : 0049 à 0057, voir la carte des fichiers.
- Toutes les commandes se lancent depuis la racine du dépôt, sous PowerShell, avec le Python du venv : `.\venv\Scripts\python.exe`.
- Commits en français, à l'impératif, un sujet par commit, terminés par la ligne `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Écart assumé avec la spec §6.1 : les messages d'erreur d'import ne sont pas préfixés d'un numéro de ligne, car l'aperçu (`imports/templates/imports/preview.html`) affiche déjà chaque message sur sa ligne.

## Carte des fichiers

| Fichier | Rôle | Tâches |
|---|---|---|
| `dashboard/models.py` | `Commodity.key/theme`, `TECHNICAL_COMMODITIES`, `Ownership` refondu, `AssetQuerySet.owned_by`, `Flow` + `FLOW_RULES` ; suppression des anciens modèles | 1, 2, 3, 4, 5, 6, 7 |
| `dashboard/services/flows.py` (nouveau) | seul lecteur de `Flow` : inventaire, productions, approvisionnements, émissions déclarées | 4, 5, 6, 7 |
| `dashboard/testing.py` (nouveau) | fabriques de données de test `make_*` (hors collecte pytest) | 4, 5, 6, 7 |
| `dashboard/views.py` | bascule des lectures vers `flows.py` et `owned_by` | 2, 4, 5, 6, 7 |
| `dashboard/services/stress_test.py` | `company_snapshot` : émissions déclarées, exposition, `owned_by(company, year)` | 2, 5, 7 |
| `dashboard/services/impacts.py` | `measured_vs_modeled` porté sur `Flow` | 4, 5 |
| `dashboard/services/supply.py` | suppression de `upstream_chain` | 6 |
| `dashboard/admin.py`, `dashboard/admin_site.py` | `FlowAdmin`, `OwnershipAdmin`, groupe « Flux » | 1, 2, 4, 5, 6, 7 |
| `dashboard/management/commands/populate_acme.py` | données de démo sous la nouvelle forme | 2, 5, 7 |
| `dashboard/management/commands/backup_sqlite.py` (nouveau) | sauvegarde avant `migrate` | 9 |
| `imports/services/cells.py` (nouveau) | lecture des parts de détention et des années facultatives | 2 |
| `imports/services/constants.py`, `excel_parser.py`, `importer.py`, `excel_template.py` | feuilles `Commodity`, `Ownership`, `Flow` ; retrait des feuilles supprimées | 1, 2, 3, 4, 5, 6, 7, 8 |
| `dashboard/tests_flow.py` (nouveau) | tests de `Flow`, `FLOW_RULES`, `flows.py`, `FlowAdmin` | 1, 4, 5, 6, 7 |
| `dashboard/tests_ownership.py` (nouveau) | tests d'`Ownership` et `owned_by` | 2, 3 |
| `imports/tests/test_commodity_sheet.py`, `test_ownership_sheet.py`, `test_flow_sheet.py` (nouveaux) | tests d'import | 1, 2, 3, 8 |
| `.cpanel.yml`, `docs/deploiement-production.md`, `CLAUDE.md` | déploiement et documentation | 9 |

Migrations créées :

| # | Nom | Tâche |
|---|---|---|
| 0049 | `commodity_key_theme` | 1 |
| 0050 | `seed_technical_commodities` | 1 |
| 0051 | `recreate_ownership` (regroupe `clear_ownership` + `ownership_cleanup` de la spec) | 2 |
| 0052 | `delete_inventory_models` | 4 |
| 0053 | `flow` | 4 |
| 0054 | `delete_production` | 5 |
| 0055 | `delete_supply_graph` | 6 |
| 0056 | `delete_carbon_emission` | 7 |

---

### Task 0 : branche de travail

**Files:** aucun fichier de code.

- [ ] **Step 1 : créer la branche**

```powershell
git switch -c feat/table-flow
```

- [ ] **Step 2 : commiter la spec et le plan**

```powershell
git add docs/superpowers/specs/2026-09-18-table-flow-unique-design.md docs/superpowers/plans/2026-09-18-table-flow-unique.md
git commit -m "docs: spec et plan de la table Flow unique" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

- [ ] **Step 3 : vérifier le point de départ**

Run: `.\venv\Scripts\python.exe -m pytest -q`
Expected: toute la suite passe. Si ce n'est pas le cas, s'arrêter et signaler les échecs existants avant de toucher au code.

---

### Task 1 : `Commodity.key`, `Commodity.theme` et les 5 commodités techniques

**Files:**
- Modify: `dashboard/models.py` (constantes d'aide, `TECHNICAL_COMMODITIES`, `CommodityQuerySet`, champs de `Commodity`)
- Create: `dashboard/migrations/0049_commodity_key_theme.py` (générée)
- Create: `dashboard/migrations/0050_seed_technical_commodities.py`
- Modify: `dashboard/admin.py` (`CommodityAdmin`)
- Modify: `imports/services/constants.py`, `imports/services/excel_parser.py`, `imports/services/importer.py`
- Modify: `dashboard/tests.py` (`GoldenViewOutputTests.setUp`)
- Create: `dashboard/tests_flow.py`, `imports/tests/test_commodity_sheet.py`

**Interfaces:**
- Produces: `dashboard.models.TECHNICAL_COMMODITIES: dict[str, tuple[name, unit, theme]]` ; `Commodity.objects.technical(key) -> Commodity` (recrée la ligne si elle manque) ; champs `Commodity.key` (`str | None`, unique) et `Commodity.theme` (`str`).
- Produces (import) : `excel_parser._ROW_CHECKS: dict[sheet_name, callable(data, context) -> str | None]` et `context` (dict partagé par tout un `parse_file`), réutilisés aux tâches 2 et 8.

- [ ] **Step 1 : écrire les tests du modèle**

Créer `dashboard/tests_flow.py` :

```python
"""Tests de la refonte « table Flow unique » (spec 2026-09-18)."""
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import TECHNICAL_COMMODITIES, Commodity


class TechnicalCommodityTests(TestCase):

    def test_five_technical_commodities_are_seeded(self):
        seeded = {
            c.key: (c.name, c.unit, c.theme)
            for c in Commodity.objects.exclude(key=None)
        }
        self.assertEqual(seeded, {
            'water': ('Eau', 'm³', 'water'),
            'energy': ('Énergie', 'MWh', 'energy'),
            'co2': ('CO₂', 'tCO₂e', 'carbon'),
            'waste': ('Déchets', 't', 'waste'),
            'surface_area': ('Surface occupée', 'm²', 'land'),
        })

    def test_key_is_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Commodity.objects.create(name='Eau bis', key='water')

    def test_several_commodities_can_have_no_key(self):
        Commodity.objects.create(name='Soja')
        Commodity.objects.create(name='Blé')
        self.assertEqual(
            Commodity.objects.filter(key=None, name__in=['Soja', 'Blé']).count(), 2)

    def test_technical_recreates_a_missing_commodity(self):
        Commodity.objects.filter(key='co2').delete()
        co2 = Commodity.objects.technical('co2')
        self.assertEqual((co2.name, co2.unit, co2.theme), TECHNICAL_COMMODITIES['co2'])
```

- [ ] **Step 2 : écrire les tests d'import**

Créer `imports/tests/test_commodity_sheet.py` :

```python
from django.test import TestCase

from dashboard.models import Commodity
from imports.services.excel_parser import parse_file
from imports.services.importer import save_import
from imports.tests.test_excel_parser import _make_xlsx, _sheet


class CommoditySheetTests(TestCase):

    def _parse(self, *rows):
        return parse_file(_make_xlsx({'Commodity': _sheet('Commodity', *rows)}))

    def test_key_and_theme_are_imported(self):
        parsed = self._parse(
            {'name': 'Méthane', 'unit': 'tCO₂e', 'key': 'CH4', 'theme': 'carbon'})
        self.assertEqual(parsed['Commodity'][0]['status'], 'ok')
        save_import(parsed)
        methane = Commodity.objects.get(key='ch4')
        self.assertEqual((methane.name, methane.theme), ('Méthane', 'carbon'))

    def test_blank_key_is_stored_as_null(self):
        save_import(self._parse({'name': 'Soja', 'unit': 'tonnes'}))
        self.assertIsNone(Commodity.objects.get(name='Soja').key)

    def test_key_used_by_another_commodity_is_error(self):
        row = self._parse({'name': 'Eau douce', 'unit': 'm³', 'key': 'WATER'})['Commodity'][0]
        self.assertEqual(row['status'], 'error')
        self.assertIn('water', row['message'].lower())

    def test_same_key_twice_in_the_file_is_error(self):
        rows = self._parse(
            {'name': 'Méthane', 'unit': 't', 'key': 'ch4'},
            {'name': 'Méthane fossile', 'unit': 't', 'key': 'ch4'},
        )['Commodity']
        self.assertEqual([r['status'] for r in rows], ['ok', 'error'])

    def test_reuploading_a_seeded_commodity_is_duplicate_not_error(self):
        row = self._parse({'name': 'Eau', 'unit': 'm³', 'key': 'water'})['Commodity'][0]
        self.assertEqual(row['status'], 'duplicate')
```

- [ ] **Step 3 : vérifier que les tests échouent**

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow.py imports/tests/test_commodity_sheet.py -q`
Expected: FAIL (`ImportError: cannot import name 'TECHNICAL_COMMODITIES'`).

- [ ] **Step 4 : déplacer les deux textes d'aide**

Dans `dashboard/models.py`, couper le bloc suivant (situé juste avant `class ImpactMethod`) :

```python
KEY_HELP_TEXT = (
    'Identifiant technique repris tel quel dans les clés JSON des vues. '
    'Ne pas modifier sur un enregistrement existant sans vérifier les '
    'vues qui le consomment.'
)

THEME_HELP_TEXT = (
    'Clé d’appariement entre mesure et modèle : un inventaire d’actif '
    'est comparé aux catégories d’impact qui portent le même thème.'
)
```

et le coller juste après la définition de `UNDOCUMENTED_SCALE_HELP_TEXT`, en haut du fichier. `Commodity` en a besoin et est défini plus haut que `ImpactMethod`.

- [ ] **Step 5 : ajouter les commodités techniques et les champs**

Toujours dans `dashboard/models.py`, juste avant `class Commodity (models.Model):`, ajouter :

```python
# Commodités techniques lues par le code (clés JSON des vues, inventaire mesuré,
# émissions déclarées) : key -> (name, unit, theme). La migration
# 0050_seed_technical_commodities en garde une copie figée.
TECHNICAL_COMMODITIES = {
    'water': ('Eau', 'm³', 'water'),
    'energy': ('Énergie', 'MWh', 'energy'),
    'co2': ('CO₂', 'tCO₂e', 'carbon'),
    'waste': ('Déchets', 't', 'waste'),
    'surface_area': ('Surface occupée', 'm²', 'land'),
}


class CommodityQuerySet(models.QuerySet):

    def technical(self, key):
        """Commodité technique `key`, recréée si elle manque (base vidée par un
        test transactionnel, ou ligne supprimée à la main)."""
        name, unit, theme = TECHNICAL_COMMODITIES[key]
        commodity, _ = self.get_or_create(
            key=key, defaults={'name': name, 'unit': unit, 'theme': theme},
        )
        return commodity
```

Dans `class Commodity`, juste après le champ `unit`, ajouter :

```python
    key = models.CharField(
        max_length=50, unique=True, null=True, blank=True,
        verbose_name='Clé technique', help_text=KEY_HELP_TEXT,
    )
    theme = models.CharField(
        max_length=30, blank=True, default='', verbose_name='Thème',
        help_text=THEME_HELP_TEXT,
    )
```

et, juste avant `class Meta:` de `Commodity` :

```python
    objects = CommodityQuerySet.as_manager()
```

- [ ] **Step 6 : générer la migration de schéma**

Run: `.\venv\Scripts\python.exe manage.py makemigrations dashboard --name commodity_key_theme`
Expected: `dashboard\migrations\0049_commodity_key_theme.py` avec deux `AddField` (`key`, `theme`), sans question interactive.

- [ ] **Step 7 : écrire la migration de seed**

Créer `dashboard/migrations/0050_seed_technical_commodities.py` :

```python
"""Crée les 5 commodités techniques lues par le code (spec 2026-09-18 §3.5).

Copie figée de TECHNICAL_COMMODITIES : une migration n'importe pas de constante
vivante.
"""
from django.db import migrations

TECHNICAL_COMMODITIES = [
    # (key, name, unit, theme)
    ('water', 'Eau', 'm³', 'water'),
    ('energy', 'Énergie', 'MWh', 'energy'),
    ('co2', 'CO₂', 'tCO₂e', 'carbon'),
    ('waste', 'Déchets', 't', 'waste'),
    ('surface_area', 'Surface occupée', 'm²', 'land'),
]


def seed(apps, schema_editor):
    Commodity = apps.get_model('dashboard', 'Commodity')
    for key, name, unit, theme in TECHNICAL_COMMODITIES:
        Commodity.objects.update_or_create(
            key=key, defaults={'name': name, 'unit': unit, 'theme': theme},
        )


def unseed(apps, schema_editor):
    Commodity = apps.get_model('dashboard', 'Commodity')
    Commodity.objects.filter(key__in=[row[0] for row in TECHNICAL_COMMODITIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0049_commodity_key_theme'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
```

- [ ] **Step 8 : lancer les tests du modèle**

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow.py -q`
Expected: 4 passed.

- [ ] **Step 9 : ajouter les colonnes à la feuille `Commodity`**

Dans `imports/services/constants.py`, remplacer l'entrée `'Commodity'` de `SHEET_COLUMNS` par :

```python
    'Commodity': [
        'name', 'description', 'unit', 'key', 'theme', 'biodiversity_loss_class',
        'dependency_water', 'dependency_pollination', 'dependency_soil_quality',
        'dependency_carbon_sequestration', 'dependency_water_purification', 'dependency_pest_control',
    ],
```

- [ ] **Step 10 : ajouter les contrôles propres à une feuille dans l'analyseur**

Dans `imports/services/excel_parser.py` :

1. Remplacer le corps de `parse_file` par :

```python
    wb = openpyxl.load_workbook(source)
    file_names = _collect_file_names(wb)
    db_name_cache = _build_db_name_cache()
    context = _build_row_check_context()

    result = {}
    for sheet_name in SHEET_COLUMNS:
        if sheet_name not in wb.sheetnames:
            continue
        result[sheet_name] = _parse_sheet(
            wb[sheet_name], sheet_name, file_names, db_name_cache, context)
    return result
```

2. Ajouter, juste avant `def _parse_sheet` :

```python
def _build_row_check_context():
    """État partagé par les contrôles propres à une feuille (voir _ROW_CHECKS)
    pendant toute l'analyse d'un classeur."""
    return {
        'commodity_key_owner': {
            key.lower(): name.lower()
            for name, key in Commodity.objects.exclude(key=None).values_list('name', 'key')
        },
        'file_commodity_key_owner': {},
    }


def _commodity_row_error(data, context):
    """Commodity.key est unique : une clé déjà prise par une autre commodité, en
    base ou plus haut dans le fichier, ferait échouer tout l'import."""
    key = data.get('key', '').strip().lower()
    if not key:
        return None
    name = data['name'].strip().lower()
    for owners in (context['commodity_key_owner'], context['file_commodity_key_owner']):
        owner = owners.get(key)
        if owner is not None and owner != name:
            return f"Clé déjà utilisée par une autre commodité : '{data['key']}'"
    context['file_commodity_key_owner'].setdefault(key, name)
    return None


# Contrôles propres à une feuille, appliqués ligne par ligne après les
# énumérations et avant la détection des doublons.
_ROW_CHECKS = {
    'Commodity': _commodity_row_error,
}
```

3. Changer la signature de `_parse_sheet` en `def _parse_sheet(ws, sheet_name, file_names, db_name_cache, context):` et insérer, juste après le bloc `# Enumerations` (après son `continue`) et avant `# Duplicate check` :

```python
        # Contrôles propres à la feuille
        row_check = _ROW_CHECKS.get(sheet_name)
        row_error = row_check(data, context) if row_check else None
        if row_error:
            rows_out.append({'status': 'error', 'message': row_error, 'data': data})
            continue
```

- [ ] **Step 11 : importer `key` et `theme`**

Dans `imports/services/importer.py`, dans `_import_commodity`, ajouter ces deux arguments à `Commodity.objects.create(...)`, juste après `unit=...` :

```python
            key=(d.get('key') or '').strip().lower() or None,
            theme=_s(d.get('theme')),
```

puis, après `lookup['commodity'][d['name'].lower()] = obj`, ajouter :

```python
        if obj.key:
            lookup['commodity_key'][obj.key] = obj
```

Dans `_build_lookup`, ajouter après la ligne `'commodity': ...` :

```python
        'commodity_key': {o.key.lower(): o for o in Commodity.objects.exclude(key=None)},
```

- [ ] **Step 12 : afficher la clé dans l'admin**

Dans `dashboard/admin.py`, dans `CommodityAdmin`, remplacer `search_fields` et `list_display` par :

```python
    search_fields = ('name', 'key')
    list_display = ('name', 'key', 'unit', 'theme', 'biodiversity_loss_class')
```

- [ ] **Step 13 : garder les identifiants figés du golden**

`GoldenViewOutputTests` est le seul test transactionnel : il s'exécute en dernier, sur une base qui contient encore les données créées par migration, dont désormais les 5 commodités techniques (identifiants 1 à 5). Sans correction, les commodités de `populate_acme` prendraient les identifiants 6 à 9 et `dashboard/golden/leap_prepare.json`, qui contient des `commodity_id`, ne correspondrait plus. Sur PostgreSQL, la remise à zéro des séquences provoquerait même un conflit de clé primaire.

Dans `dashboard/tests.py`, `GoldenViewOutputTests.setUp`, insérer avant `call_command('populate_acme')` :

```python
        # Les commodités techniques créées par migration occuperaient les premiers
        # identifiants : on les retire pour garder les PK figés dans les golden.
        # populate_acme recrée celles dont il a besoin (Commodity.objects.technical).
        Commodity.objects.exclude(key=None).delete()
```

- [ ] **Step 14 : lancer toute la suite**

Run: `.\venv\Scripts\python.exe -m pytest -q`
Expected: tout passe, dont les 5 tests de `imports/tests/test_commodity_sheet.py` ; `git status dashboard/golden` n'affiche rien.

- [ ] **Step 15 : commit**

```powershell
git add dashboard/models.py dashboard/migrations/0049_commodity_key_theme.py dashboard/migrations/0050_seed_technical_commodities.py dashboard/admin.py dashboard/tests.py dashboard/tests_flow.py imports/services/constants.py imports/services/excel_parser.py imports/services/importer.py imports/tests/test_commodity_sheet.py
git commit -m "feat(commodity): clé technique, thème et commodités techniques" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2 : refonte d'`Ownership` et `Asset.objects.owned_by`

**Files:**
- Modify: `dashboard/models.py` (imports, `AssetQuerySet`, `Asset.objects`, `OwnershipQuerySet`, `Ownership`)
- Create: `dashboard/migrations/0051_recreate_ownership.py`
- Modify: `dashboard/views.py`, `dashboard/services/stress_test.py`, `dashboard/admin.py`, `dashboard/management/commands/populate_acme.py`
- Create: `imports/services/cells.py`
- Modify: `imports/services/constants.py`, `imports/services/excel_parser.py`, `imports/services/importer.py`
- Modify: `dashboard/tests.py` (26 créations d'`Ownership`)
- Create: `dashboard/tests_ownership.py`, `imports/tests/test_ownership_sheet.py`

**Interfaces:**
- Consumes: `_ROW_CHECKS` et `context` de l'analyseur (tâche 1).
- Produces: `Asset.objects.owned_by(company, year=None) -> QuerySet[Asset]` trié par `pk` ; `Ownership.objects.valid_in(year=None) -> QuerySet[Ownership]` ; `Ownership.share: Decimal` ; `Ownership.share_label -> str` (`'75%'`) ; `imports.services.cells.parse_share(value) -> Decimal | None` et `parse_optional_year(value) -> int | None` (lève `ValueError` si illisible).

- [ ] **Step 1 : écrire les tests du modèle**

Créer `dashboard/tests_ownership.py` :

```python
"""Détention actif ↔ entreprise (spec 2026-09-18 §3.6)."""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Asset, Company, Country, Ownership


def _country():
    return Country.objects.create(
        name='France', water_ownership='Public', land_ownership='Private')


def _asset(name, country):
    return Asset.objects.create(name=name, latitude=1.0, longitude=2.0, country=country)


class OwnershipModelTests(TestCase):

    def setUp(self):
        self.asset = _asset('Site', _country())
        self.company = Company.objects.create(name='Acme')

    def test_share_is_stored_as_decimal(self):
        o = Ownership.objects.create(asset=self.asset, company=self.company, share='0.75')
        o.refresh_from_db()
        self.assertEqual(o.share, Decimal('0.7500'))

    def test_share_label_matches_the_legacy_display(self):
        cases = [('1', '100%'), ('0.75', '75%'), ('0.6', '60%'), ('0.3333', '33.33%')]
        for share, label in cases:
            with self.subTest(share=share):
                o = Ownership(asset=self.asset, company=self.company, share=Decimal(share))
                self.assertEqual(o.share_label, label)

    def test_share_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ownership.objects.create(asset=self.asset, company=self.company, share=0)

    def test_share_cannot_exceed_one(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ownership.objects.create(asset=self.asset, company=self.company, share='1.5')

    def test_start_year_cannot_follow_end_year(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ownership.objects.create(
                asset=self.asset, company=self.company, share=1,
                start_year=2025, end_year=2024,
            )

    def test_str(self):
        o = Ownership.objects.create(asset=self.asset, company=self.company, share=1)
        self.assertEqual(str(o), 'Site - Acme')


class OwnedByTests(TestCase):

    def setUp(self):
        self.country = _country()
        self.company = Company.objects.create(name='Acme')

    def _held(self, name, **years):
        asset = _asset(name, self.country)
        Ownership.objects.create(asset=asset, company=self.company, share=1, **years)
        return asset

    def test_without_year_returns_current_holdings(self):
        current = self._held('Actuel')
        self._held('Cédé', end_year=2023)
        self.assertEqual(list(Asset.objects.owned_by(self.company)), [current])

    def test_with_year_applies_the_validity_period(self):
        always = self._held('Toujours')
        sold = self._held('Cédé', end_year=2023)
        bought = self._held('Acquis', start_year=2024)
        self.assertEqual(list(Asset.objects.owned_by(self.company, 2023)), [always, sold])
        self.assertEqual(list(Asset.objects.owned_by(self.company, 2024)), [always, bought])

    def test_other_companies_are_ignored(self):
        other = Company.objects.create(name='Autre')
        Ownership.objects.create(asset=_asset('Voisin', self.country), company=other, share=1)
        self.assertEqual(list(Asset.objects.owned_by(self.company)), [])

    def test_two_periods_do_not_duplicate_the_asset(self):
        asset = _asset('Deux périodes', self.country)
        Ownership.objects.create(asset=asset, company=self.company, share='0.5', end_year=2022)
        Ownership.objects.create(
            asset=asset, company=self.company, share='0.75', start_year=2023)
        self.assertEqual(list(Asset.objects.owned_by(self.company, 2024)), [asset])
        self.assertEqual(list(Asset.objects.owned_by(self.company)), [asset])
```

- [ ] **Step 2 : écrire les tests de lecture des cellules et de la feuille**

Créer `imports/tests/test_ownership_sheet.py` :

```python
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from dashboard.models import Asset, Company, Country, Ownership
from imports.services.cells import parse_optional_year, parse_share
from imports.services.excel_parser import parse_file
from imports.services.importer import save_import
from imports.tests.test_excel_parser import _make_xlsx, _sheet


class ParseShareTests(SimpleTestCase):

    def test_accepted_formats(self):
        cases = {
            '0.75': '0.7500', '75%': '0.7500', '75 %': '0.7500', '0,75': '0.7500',
            '1': '1.0000', '100%': '1.0000',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_share(raw), Decimal(expected))

    def test_rejected_values(self):
        for raw in ('', None, '1.5', '150%', '0', '-0.2', 'abc', 'nan'):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_share(raw))

    def test_optional_year(self):
        self.assertIsNone(parse_optional_year(''))
        self.assertEqual(parse_optional_year('2024.0'), 2024)
        with self.assertRaises(ValueError):
            parse_optional_year('fin')


class OwnershipSheetTests(TestCase):

    def setUp(self):
        country = Country.objects.create(
            name='France', water_ownership='pub', land_ownership='priv')
        Asset.objects.create(name='Usine A', latitude=1.0, longitude=2.0, country=country)
        Company.objects.create(name='Acme')

    def _row(self, **values):
        row = {'asset_name': 'Usine A', 'company_name': 'Acme', 'share': '75%'}
        row.update(values)
        return row

    def _parse(self, *rows):
        return parse_file(_make_xlsx({'Ownership': _sheet('Ownership', *rows)}))

    def test_percent_share_is_imported_as_decimal(self):
        parsed = self._parse(self._row(start_year='2024'))
        self.assertEqual(parsed['Ownership'][0]['status'], 'ok')
        save_import(parsed)
        o = Ownership.objects.get()
        self.assertEqual((o.share, o.start_year, o.end_year), (Decimal('0.7500'), 2024, None))

    def test_invalid_share_is_error(self):
        row = self._parse(self._row(share='1.5'))['Ownership'][0]
        self.assertEqual(row['status'], 'error')
        self.assertIn('share', row['message'])

    def test_invalid_year_is_error(self):
        row = self._parse(self._row(end_year='fin'))['Ownership'][0]
        self.assertEqual(row['status'], 'error')
        self.assertIn('end_year', row['message'])

    def test_start_after_end_is_error(self):
        row = self._parse(self._row(start_year='2025', end_year='2024'))['Ownership'][0]
        self.assertEqual(row['status'], 'error')
```

- [ ] **Step 3 : vérifier que les tests échouent**

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_ownership.py imports/tests/test_ownership_sheet.py -q`
Expected: FAIL (erreurs d'import : `cells` introuvable, champs `asset`/`share` inconnus).

- [ ] **Step 4 : imports de `models.py`**

En tête de `dashboard/models.py`, remplacer les trois lignes d'import par :

```python
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
```

- [ ] **Step 5 : `AssetQuerySet`**

Juste avant `class Asset(models.Model):`, ajouter :

```python
class AssetQuerySet(models.QuerySet):

    def owned_by(self, company, year=None):
        """Actifs détenus par `company` l'année `year` ; sans année, périmètre
        actuel (spec §3.6). Trié par pk pour un ordre stable."""
        held = Ownership.objects.valid_in(year).filter(company=company).values('asset_id')
        return self.filter(pk__in=held).order_by('pk')
```

et dans `class Asset`, juste avant son `class Meta:` :

```python
    objects = AssetQuerySet.as_manager()
```

- [ ] **Step 6 : réécrire `Ownership`**

Remplacer toute la classe `Ownership` actuelle par :

```python
class OwnershipQuerySet(models.QuerySet):

    def valid_in(self, year=None):
        """Détentions valides l'année `year` ; sans année, celles en cours (sans
        `end_year`). Convention : détenteur au 31 décembre (spec §3.6)."""
        if year is None:
            return self.filter(end_year__isnull=True)
        return self.filter(
            Q(start_year__isnull=True) | Q(start_year__lte=year),
            Q(end_year__isnull=True) | Q(end_year__gte=year),
        )


OWNERSHIP_YEAR_HELP_TEXT = (
    'Le détenteur d’une année est celui du 31 décembre : pour une cession en juin '
    '2024, le vendeur finit en 2023 et l’acheteur commence en 2024. Vide = sans limite.'
)


class Ownership(models.Model):
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name='ownerships', verbose_name='Actif',
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='ownerships',
        verbose_name='Entreprise',
    )
    share = models.DecimalField(
        max_digits=5, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001')), MaxValueValidator(Decimal('1'))],
        verbose_name='Part de détention', help_text='Entre 0 et 1 : 0,75 = 75 %.',
    )
    start_year = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Année de début',
        help_text=OWNERSHIP_YEAR_HELP_TEXT,
    )
    end_year = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Année de fin',
        help_text=OWNERSHIP_YEAR_HELP_TEXT,
    )
    description = models.TextField(blank=True, verbose_name='Description')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Créé le')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Modifié le')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='Créé par',
    )

    objects = OwnershipQuerySet.as_manager()

    class Meta:
        verbose_name = 'Détention'
        verbose_name_plural = 'Détentions'
        constraints = [
            models.CheckConstraint(
                name='ownership_share_range',
                condition=Q(share__gt=0) & Q(share__lte=1),
                violation_error_message=(
                    'La part de détention doit être comprise entre 0 (exclu) et 1.'
                ),
            ),
            models.CheckConstraint(
                name='ownership_years_ordered',
                condition=(
                    Q(start_year__isnull=True) | Q(end_year__isnull=True)
                    | Q(start_year__lte=F('end_year'))
                ),
                violation_error_message="L'année de début doit précéder l'année de fin.",
            ),
        ]

    def __str__(self):
        return f'{self.asset.name} - {self.company.name}'

    @property
    def share_label(self):
        """Part au format affiché : Decimal('0.75') → '75%'."""
        return f'{(Decimal(self.share) * 100).normalize():f}%'
```

- [ ] **Step 7 : écrire la migration**

Créer `dashboard/migrations/0051_recreate_ownership.py`. Les chaînes `help_text` et `violation_error_message` doivent être identiques à celles du modèle (Step 6) :

```python
"""Recrée Ownership (spec 2026-09-18 §3.6 et §7).

Pas de migration des données (décision 2 de la spec) : l'ancienne table, dont la
part était un texte aux formats mêlés, est supprimée puis recréée vide. Regroupe
les étapes `clear_ownership` et `ownership_cleanup` du tableau §7.
"""
from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

YEAR_HELP_TEXT = (
    'Le détenteur d’une année est celui du 31 décembre : pour une cession en juin '
    '2024, le vendeur finit en 2023 et l’acheteur commence en 2024. Vide = sans limite.'
)


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0050_seed_technical_commodities'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel(name='Ownership'),
        migrations.CreateModel(
            name='Ownership',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('share', models.DecimalField(
                    decimal_places=4, max_digits=5,
                    help_text='Entre 0 et 1 : 0,75 = 75 %.',
                    validators=[
                        django.core.validators.MinValueValidator(Decimal('0.0001')),
                        django.core.validators.MaxValueValidator(Decimal('1')),
                    ],
                    verbose_name='Part de détention')),
                ('start_year', models.PositiveSmallIntegerField(
                    blank=True, null=True, help_text=YEAR_HELP_TEXT,
                    verbose_name='Année de début')),
                ('end_year', models.PositiveSmallIntegerField(
                    blank=True, null=True, help_text=YEAR_HELP_TEXT,
                    verbose_name='Année de fin')),
                ('description', models.TextField(blank=True, verbose_name='Description')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Modifié le')),
                ('asset', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='ownerships',
                    to='dashboard.asset', verbose_name='Actif')),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='ownerships',
                    to='dashboard.company', verbose_name='Entreprise')),
                ('created_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Créé par')),
            ],
            options={
                'verbose_name': 'Détention',
                'verbose_name_plural': 'Détentions',
                'constraints': [
                    models.CheckConstraint(
                        condition=models.Q(('share__gt', 0), ('share__lte', 1)),
                        name='ownership_share_range',
                        violation_error_message=(
                            'La part de détention doit être comprise entre 0 (exclu) et 1.'
                        ),
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ('start_year__isnull', True), ('end_year__isnull', True),
                            ('start_year__lte', models.F('end_year')), _connector='OR',
                        ),
                        name='ownership_years_ordered',
                        violation_error_message="L'année de début doit précéder l'année de fin.",
                    ),
                ],
            },
        ),
    ]
```

- [ ] **Step 8 : vérifier que la migration décrit exactement le modèle**

Run: `.\venv\Scripts\python.exe manage.py makemigrations dashboard --check --dry-run`
Expected: `No changes detected`. Si Django propose des opérations sur `Ownership`, corriger `0051_recreate_ownership.py` (jamais le modèle) jusqu'à obtenir ce message.

- [ ] **Step 9 : lancer les tests du modèle**

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_ownership.py -q`
Expected: 10 passed.

- [ ] **Step 10 : basculer les vues sur `owned_by`**

Dans `dashboard/views.py` :

1. Remplacer toutes les occurrences de la chaîne `Asset.objects.filter(ownership__Company=company)` par `Asset.objects.owned_by(company)` (11 occurrences). Les `.distinct()` qui suivent peuvent rester : ils sont inoffensifs.
2. Dans `_get_compliance_data`, remplacer

```python
        Asset.objects
        .filter(ownership__Company=company, near_sensitive_zone=True)
```

par

```python
        Asset.objects.owned_by(company)
        .filter(near_sensitive_zone=True)
```

3. Dans `_get_dependencies_data`, remplacer `Q(company=company) | Q(asset__ownership__Company=company)` par `Q(company=company) | Q(asset__in=Asset.objects.owned_by(company))`.
4. Dans `_get_leap_locate_data`, remplacer le bloc `ownership_map = {...}` (commentaire compris) par :

```python
    # Part de détention actuelle de la société sélectionnée pour chaque asset.
    ownership_map = {
        o.asset_id: o.share_label
        for o in Ownership.objects.valid_in().filter(asset_id__in=asset_ids, company=company)
    }
```

Vérification : `Select-String -Path dashboard\views.py -Pattern 'ownership__'` ne renvoie plus rien.

- [ ] **Step 11 : stress test**

Dans `dashboard/services/stress_test.py`, fonction `company_snapshot`, remplacer

```python
    assets = list(Asset.objects.filter(ownership__Company=company).distinct())
```

par

```python
    assets = list(Asset.objects.owned_by(company, year))
```

- [ ] **Step 12 : admin**

Dans `dashboard/admin.py`, remplacer `OwnershipAdmin` par :

```python
@admin.register(Ownership)
class OwnershipAdmin(admin.ModelAdmin):
    search_fields = ('asset__name', 'company__name')
    list_display = ('asset', 'company', 'share_percent', 'start_year', 'end_year')
    list_filter = ('company',)
    autocomplete_fields = ('asset', 'company')

    @admin.display(description='Part de détention')
    def share_percent(self, obj):
        return obj.share_label
```

- [ ] **Step 13 : `populate_acme`**

Dans `dashboard/management/commands/populate_acme.py`, ajouter `from decimal import Decimal` en première ligne, puis remplacer le bloc « Propriétés » par :

```python
        for asset, share in [
            (a_bretagne, Decimal('1')),
            (a_occitanie, Decimal('1')),
            (a_mato_grosso, Decimal('0.75')),
            (a_para, Decimal('1')),
            (a_sumatra, Decimal('0.6')),
        ]:
            Ownership.objects.get_or_create(
                asset=asset, company=acme, defaults={'share': share})
```

- [ ] **Step 14 : adapter les 26 créations d'`Ownership` des tests existants**

Toutes ont la forme `Ownership.objects.create(Asset=X, Company=Y, ownership='100%')`. Créer puis exécuter ce script dans le scratchpad (pas dans le dépôt) :

```python
import pathlib
import re

path = pathlib.Path('dashboard/tests.py')
source = path.read_text(encoding='utf-8')
source, count = re.subn(
    r"Ownership\.objects\.create\(Asset=([^,]+), Company=([^,]+), ownership='100%'\)",
    r"Ownership.objects.create(asset=\1, company=\2, share=1)",
    source,
)
path.write_text(source, encoding='utf-8')
print(count)
```

Expected: `26`. Vérification : `Select-String -Path dashboard\tests.py -Pattern 'Asset=|Company=|ownership='` ne renvoie plus aucune création d'`Ownership`.

- [ ] **Step 15 : module de lecture des cellules**

Créer `imports/services/cells.py` :

```python
"""Lecture des cellules à format métier, partagée par l'analyseur et l'importeur."""
from decimal import Decimal, InvalidOperation

SHARE_QUANTUM = Decimal('0.0001')


def parse_share(value):
    """Part de détention : '75%', '75 %', '0.75' ou '0,75' → Decimal('0.7500').

    Renvoie None si la valeur est vide, illisible ou hors de ]0, 1]. Sans « % »,
    une valeur supérieure à 1 est refusée (75 ou 0,75 ?) ; '1' vaut 100 %.
    """
    text = str(value if value is not None else '').strip().replace(',', '.')
    if not text:
        return None
    percent = text.endswith('%')
    if percent:
        text = text[:-1].strip()
    try:
        share = Decimal(text)
    except InvalidOperation:
        return None
    if not share.is_finite():
        return None
    if percent:
        share = share / 100
    if not 0 < share <= 1:
        return None
    return share.quantize(SHARE_QUANTUM)


def parse_optional_year(value):
    """Année facultative : '' → None ; '2024' ou '2024.0' → 2024.

    Lève ValueError si la cellule n'est pas une année lisible.
    """
    text = str(value if value is not None else '').strip()
    if not text:
        return None
    return int(float(text))
```

- [ ] **Step 16 : feuille `Ownership`**

Dans `imports/services/constants.py` :
- `SHEET_COLUMNS['Ownership']` devient `['asset_name', 'company_name', 'share', 'start_year', 'end_year', 'description']` ;
- `REQUIRED_FIELDS['Ownership']` devient `['asset_name', 'company_name', 'share']` ;
- `DUPLICATE_CRITERIA['Ownership']` devient `['asset_name', 'company_name', 'start_year']`.

Dans `imports/services/excel_parser.py` :
- ajouter `from .cells import parse_optional_year, parse_share` aux imports locaux ;
- dans `_EXISTING_KEY_QUERIES`, remplacer l'entrée `'Ownership'` par `'Ownership': (Ownership, ['asset__name', 'company__name', 'start_year']),` ;
- ajouter, juste avant `_ROW_CHECKS` :

```python
def _ownership_row_error(data, context):
    """Part lisible dans ]0, 1] et années cohérentes (spec §6.2)."""
    if parse_share(data.get('share')) is None:
        return (
            f"Part invalide pour 'share' : '{data.get('share')}' "
            "(attendu : 0.75 ou 75%, au plus 1)"
        )
    years = {}
    for column in ('start_year', 'end_year'):
        try:
            years[column] = parse_optional_year(data.get(column))
        except ValueError:
            return f"Année invalide pour '{column}' : '{data.get(column)}'"
    start, end = years['start_year'], years['end_year']
    if start is not None and end is not None and start > end:
        return "L'année de début ('start_year') doit précéder l'année de fin ('end_year')"
    return None
```

- ajouter `'Ownership': _ownership_row_error,` dans `_ROW_CHECKS`.

Dans `imports/services/importer.py`, ajouter `from .cells import parse_optional_year, parse_share` aux imports locaux et remplacer `_import_ownership` par :

```python
def _import_ownership(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        asset = _get(lookup, 'asset', d['asset_name'])
        company = _get(lookup, 'company', d['company_name'])
        share = parse_share(d.get('share'))
        if not asset or not company or share is None:
            continue
        Ownership.objects.create(
            asset=asset, company=company, share=share,
            start_year=parse_optional_year(d.get('start_year')),
            end_year=parse_optional_year(d.get('end_year')),
            description=_s(d.get('description')),
        )
        created += 1
    return created
```

- [ ] **Step 17 : lancer toute la suite, golden compris**

Run: `.\venv\Scripts\python.exe -m pytest -q`
Expected: tout passe. `GoldenViewOutputTests` passe sans modification des fichiers golden (la part s'affiche toujours `"100%"`, `"75%"`, `"60%"`). `git status dashboard/golden` n'affiche rien.

- [ ] **Step 18 : commit**

```powershell
git add dashboard imports
git commit -m "refactor(ownership): part décimale, années de validité et owned_by" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3 : contrôles de chevauchement et de somme des parts

**Files:**
- Modify: `dashboard/models.py` (fonctions de période, messages, `Ownership.clean`)
- Modify: `imports/services/excel_parser.py` (seconde passe sur la feuille `Ownership`)
- Modify: `dashboard/tests_ownership.py`, `imports/tests/test_ownership_sheet.py`

**Interfaces:**
- Consumes: `Ownership`, `parse_share`, `parse_optional_year` (tâche 2).
- Produces: `dashboard.models.periods_overlap(first, second) -> bool` avec `first`/`second` = `(start_year, end_year)` ; `share_overflow_year(holdings) -> int | None` avec `holdings` = itérable de `(share, start_year, end_year)` ; `OWNERSHIP_OVERLAP_MESSAGE: str` ; `share_overflow_message(year) -> str`.

- [ ] **Step 1 : écrire les tests du modèle**

Ajouter à `dashboard/tests_ownership.py` (compléter les imports : `from django.core.exceptions import ValidationError`, `from django.test import SimpleTestCase, TestCase`, et `from .models import (Asset, Company, Country, Ownership, periods_overlap, share_overflow_year)`) :

```python
class OwnershipPeriodHelpersTests(SimpleTestCase):

    def test_periods_overlap(self):
        self.assertTrue(periods_overlap((None, 2023), (2023, None)))
        self.assertFalse(periods_overlap((None, 2023), (2024, None)))
        self.assertTrue(periods_overlap((None, None), (2010, 2012)))

    def test_share_overflow_year(self):
        half = Decimal('0.5')
        self.assertIsNone(share_overflow_year([(half, None, None), (half, None, None)]))
        self.assertEqual(
            share_overflow_year([(Decimal('0.6'), 2020, None), (half, 2022, 2025)]), 2022)


class OwnershipCleanTests(TestCase):

    def setUp(self):
        self.asset = _asset('Site', _country())
        self.acme = Company.objects.create(name='Acme')
        self.other = Company.objects.create(name='Autre')

    def _clean(self, **fields):
        Ownership(asset=self.asset, **fields).full_clean()

    def test_overlapping_periods_for_the_same_company_are_rejected(self):
        Ownership.objects.create(
            asset=self.asset, company=self.acme, share='0.5', end_year=2023)
        with self.assertRaisesMessage(ValidationError, 'chevauche'):
            self._clean(company=self.acme, share='0.5', start_year=2023)

    def test_consecutive_periods_are_accepted(self):
        Ownership.objects.create(
            asset=self.asset, company=self.acme, share='0.5', end_year=2023)
        self._clean(company=self.acme, share='0.75', start_year=2024)

    def test_total_share_above_one_is_rejected_with_its_year(self):
        Ownership.objects.create(
            asset=self.asset, company=self.acme, share='0.6', start_year=2020)
        with self.assertRaisesMessage(ValidationError, 'dépasse 100 % en 2022'):
            self._clean(company=self.other, share='0.5', start_year=2022)

    def test_total_share_of_exactly_one_is_accepted(self):
        Ownership.objects.create(asset=self.asset, company=self.acme, share='0.6')
        self._clean(company=self.other, share='0.4')

    def test_sale_then_purchase_does_not_add_up(self):
        Ownership.objects.create(asset=self.asset, company=self.acme, share=1, end_year=2023)
        self._clean(company=self.other, share=1, start_year=2024)
```

- [ ] **Step 2 : écrire les tests de la seconde passe d'import**

Ajouter à `imports/tests/test_ownership_sheet.py` :

```python
class OwnershipSheetSecondPassTests(TestCase):

    def setUp(self):
        country = Country.objects.create(
            name='France', water_ownership='pub', land_ownership='priv')
        self.asset = Asset.objects.create(
            name='Usine A', latitude=1.0, longitude=2.0, country=country)
        self.acme = Company.objects.create(name='Acme')
        Company.objects.create(name='Autre')

    def _row(self, **values):
        row = {'asset_name': 'Usine A', 'company_name': 'Acme', 'share': '50%'}
        row.update(values)
        return row

    def _statuses(self, *rows):
        parsed = parse_file(_make_xlsx({'Ownership': _sheet('Ownership', *rows)}))
        return parsed['Ownership']

    def test_overlap_with_the_database_is_error(self):
        Ownership.objects.create(asset=self.asset, company=self.acme, share='0.5')
        rows = self._statuses(self._row(start_year='2024'))
        self.assertEqual(rows[0]['status'], 'error')
        self.assertIn('chevauche', rows[0]['message'])

    def test_total_above_one_within_the_file_is_error(self):
        rows = self._statuses(
            self._row(share='60%'), self._row(company_name='Autre', share='50%'))
        self.assertEqual([r['status'] for r in rows], ['ok', 'error'])
        self.assertIn('100 %', rows[1]['message'])

    def test_consecutive_periods_in_the_file_are_ok(self):
        rows = self._statuses(
            self._row(end_year='2023'), self._row(share='75%', start_year='2024'))
        self.assertEqual([r['status'] for r in rows], ['ok', 'ok'])
```

- [ ] **Step 3 : vérifier que les tests échouent**

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_ownership.py imports/tests/test_ownership_sheet.py -q`
Expected: FAIL (`cannot import name 'periods_overlap'`).

- [ ] **Step 4 : fonctions de période et `clean()`**

Dans `dashboard/models.py`, ajouter `from decimal import Decimal, InvalidOperation` (à la place de `from decimal import Decimal`) et `from django.core.exceptions import ValidationError`. Juste avant `class OwnershipQuerySet`, ajouter :

```python
OWNERSHIP_OVERLAP_MESSAGE = (
    'Cette entreprise détient déjà cet actif sur une période qui chevauche celle-ci.'
)


def share_overflow_message(year):
    """Message d'erreur quand la somme des parts d'un actif dépasse 1."""
    when = f' en {year}' if year else ''
    return f'La somme des parts de cet actif dépasse 100 %{when}.'


def _year_bounds(start, end):
    """Période [start, end] en années ; une borne vide est ouverte."""
    return (start if start is not None else 0, end if end is not None else 9999)


def periods_overlap(first, second):
    """Deux périodes (start_year, end_year) ont-elles une année en commun ?"""
    first_start, first_end = _year_bounds(*first)
    second_start, second_end = _year_bounds(*second)
    return first_start <= second_end and second_start <= first_end


def share_overflow_year(holdings):
    """Première année où la somme des parts dépasse 1, ou None (0 si la période
    fautive n'a pas d'année de début).

    `holdings` : itérable de (share, start_year, end_year). La somme n'augmente
    qu'au début d'une période : tester ces années suffit.
    """
    bounded = [(share, *_year_bounds(start, end)) for share, start, end in holdings]
    for year in sorted({start for _, start, _ in bounded}):
        total = sum(share for share, start, end in bounded if start <= year <= end)
        if total > 1:
            return year
    return None
```

Dans `class Ownership`, juste après `__str__`, ajouter :

```python
    def clean(self):
        """Pas de chevauchement pour un même couple actif / entreprise, et somme
        des parts d'un actif ≤ 1 chaque année (spec §3.6)."""
        super().clean()
        if self.asset_id is None or self.company_id is None:
            return
        try:
            share = Decimal(str(self.share))
        except (InvalidOperation, TypeError):
            return  # clean_fields() signale déjà la part illisible
        mine = (self.start_year, self.end_year)
        others = list(Ownership.objects.filter(asset_id=self.asset_id).exclude(pk=self.pk))
        for other in others:
            same_company = other.company_id == self.company_id
            if same_company and periods_overlap(mine, (other.start_year, other.end_year)):
                raise ValidationError(OWNERSHIP_OVERLAP_MESSAGE)
        year = share_overflow_year(
            [(share, *mine)] + [(o.share, o.start_year, o.end_year) for o in others]
        )
        if year is not None:
            raise ValidationError(share_overflow_message(year))
```

- [ ] **Step 5 : seconde passe dans l'analyseur**

Dans `imports/services/excel_parser.py` :

1. Ajouter `from collections import defaultdict` en tête (stdlib) et compléter l'import de `dashboard.models` avec `OWNERSHIP_OVERLAP_MESSAGE, periods_overlap, share_overflow_message, share_overflow_year`.
2. Dans `parse_file`, remplacer les deux lignes `result[sheet_name] = _parse_sheet(...)` par :

```python
        rows = _parse_sheet(wb[sheet_name], sheet_name, file_names, db_name_cache, context)
        sheet_check = _SHEET_CHECKS.get(sheet_name)
        if sheet_check:
            sheet_check(rows)
        result[sheet_name] = rows
```

3. Ajouter, juste après la définition de `_ROW_CHECKS` :

```python
def _mark_error(row, message):
    row['status'] = 'error'
    row['message'] = message


def _ownership_sheet_check(rows):
    """Seconde passe sur la feuille Ownership (spec §6.2) : chaque ligne 'ok' est
    confrontée à la base et aux lignes 'ok' qui la précèdent dans le fichier."""
    holdings = defaultdict(list)  # nom d'actif -> [(entreprise, part, début, fin, ligne)]
    for o in Ownership.objects.select_related('asset', 'company'):
        holdings[o.asset.name.lower()].append(
            (o.company.name.lower(), o.share, o.start_year, o.end_year, None))
    for row in rows:
        if row['status'] != 'ok':
            continue
        d = row['data']
        holdings[d['asset_name'].strip().lower()].append((
            d['company_name'].strip().lower(),
            parse_share(d['share']),
            parse_optional_year(d.get('start_year')),
            parse_optional_year(d.get('end_year')),
            row,
        ))
    for entries in holdings.values():
        for index, (company, share, start, end, row) in enumerate(entries):
            if row is None:
                continue
            kept = [e for e in entries[:index] if e[4] is None or e[4]['status'] == 'ok']
            if any(c == company and periods_overlap((start, end), (s, f))
                   for c, _, s, f, _ in kept):
                _mark_error(row, OWNERSHIP_OVERLAP_MESSAGE)
                continue
            year = share_overflow_year(
                [(sh, s, f) for _, sh, s, f, _ in kept] + [(share, start, end)])
            if year is not None:
                _mark_error(row, share_overflow_message(year))


# Contrôles portant sur toute une feuille, après l'analyse ligne par ligne.
_SHEET_CHECKS = {
    'Ownership': _ownership_sheet_check,
}
```

- [ ] **Step 6 : lancer les tests**

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_ownership.py imports/tests/test_ownership_sheet.py -q`
Expected: tout passe.

- [ ] **Step 7 : lancer toute la suite**

Run: `.\venv\Scripts\python.exe -m pytest -q`
Expected: tout passe.

- [ ] **Step 8 : commit**

```powershell
git add dashboard/models.py dashboard/tests_ownership.py imports/services/excel_parser.py imports/tests/test_ownership_sheet.py
git commit -m "feat(ownership): refuse les chevauchements et les parts au-delà de 100 %" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4 : table `Flow` et inventaire mesuré

L'ancien `Flow` (catalogue) et `AssetInventory` disparaissent, la nouvelle table `Flow` est créée, et les deux pages qui lisaient l'inventaire (LEAP Evaluate, Risque physique) basculent sur `flows.latest_inventory`. `Production`, `SupplyNode`, `Exchange` et `Carbon_emission` restent en place jusqu'aux tâches 5 à 7.

Changement de comportement voulu : l'année d'inventaire la plus récente d'un actif se calcule désormais sur les seules commodités demandées. Sur LEAP Evaluate, une mesure d'énergie plus récente que la mesure d'eau ne vide plus la colonne eau. Risque physique se comportait déjà ainsi.

**Files:**
- Modify: `dashboard/models.py` (suppression de l'ancien `Flow` et d'`AssetInventory`, section « Flux »)
- Create: `dashboard/migrations/0052_delete_inventory_models.py`, `dashboard/migrations/0053_flow.py` (générée)
- Create: `dashboard/services/flows.py`, `dashboard/testing.py`
- Modify: `dashboard/views.py`, `dashboard/services/impacts.py`, `dashboard/admin.py`, `dashboard/admin_site.py`
- Modify: `imports/services/constants.py`, `excel_parser.py`, `importer.py`, `excel_template.py`
- Modify: `dashboard/tests_flow.py`, `dashboard/tests.py`, `dashboard/tests_admin_console.py`, `imports/tests/test_importer.py`, `imports/tests/test_excel_parser.py`, `imports/tests/test_roundtrip.py`

**Interfaces:**
- Consumes: `Commodity.objects.technical(key)` (tâche 1).
- Produces (`dashboard.models`) : `Flow` ; `FlowKind` (`PRODUCTION`, `SUPPLY`, `CONSUMPTION`, `EMISSION`, `WASTE`) ; `FlowScope` (`'Scope 1'`, `'Scope 2'`, `'Scope 3'`, `'Scope 1+2'`, `'Scope 1+2+3'`, `'undefined'`) ; constantes `ENDPOINT_ASSET = 'asset'`, `ENDPOINT_REGION = 'region'`, `ENDPOINT_COUNTRY = 'country'`, `ENDPOINT_COMPANY = 'company'`, `ENDPOINT_ENVIRONMENT = 'environment'`, `LOCATED_ENDPOINTS`, `ALL_ENDPOINTS` (les quatre + `'environment'` + `None`) ; `FLOW_RULES: dict[str, FlowRule(origins, destinations, message)]` indexé par valeur de `FlowKind` ; `SUPPLY_SELF_LOOP_MESSAGE`, `REVENUE_PRODUCTION_ONLY_MESSAGE` ; `Flow.origin_type` / `Flow.destination_type -> str | None`.
- Produces (`dashboard.services.flows`) : `latest_inventory(asset_ids, keys) -> {asset_id: {key: {'value': float, 'unit': str}}}` ; `inventory_total(asset, theme, year) -> float`.
- Produces (`dashboard.testing`) : `make_inventory(*, asset, key, year, value) -> Flow`.

- [ ] **Step 1 : écrire les tests de la table et de l'inventaire**

Dans `dashboard/tests_flow.py`, remplacer le bloc d'imports par :

```python
"""Tests de la refonte « table Flow unique » (spec 2026-09-18)."""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from .models import (
    ALL_ENDPOINTS, FLOW_RULES, TECHNICAL_COMMODITIES, Asset, Commodity, Company, Country,
    Flow, FlowKind, FlowScope, SubnationalRegion,
)
from .services import flows as flow_service
from .testing import make_inventory
```

puis ajouter en fin de fichier :

```python
class FlowRulesTests(TestCase):

    def setUp(self):
        self.wheat = Commodity.objects.create(name='Blé')
        # Objets distincts de chaque côté : un approvisionnement ne peut pas
        # relier un lieu à lui-même.
        self.objects = {}
        for side, suffix in (('from', 'A'), ('to', 'B')):
            country = Country.objects.create(
                name=f'Pays {suffix}', water_ownership='Public', land_ownership='Private')
            self.objects[side] = {
                'country': country,
                'region': SubnationalRegion.objects.create(
                    name=f'Région {suffix}', country=country),
                'asset': Asset.objects.create(
                    name=f'Actif {suffix}', latitude=1.0, longitude=2.0, country=country),
                'company': Company.objects.create(name=f'Entreprise {suffix}'),
            }

    def _ends(self, side, endpoint):
        if endpoint is None:
            return {}
        if endpoint == 'environment':
            return {f'{side}_environment': True}
        return {f'{side}_{endpoint}': self.objects[side][endpoint]}

    def _create(self, kind, origin, destination, **extra):
        return Flow.objects.create(
            kind=kind, what=self.wheat, year=2024, quantity=1.0,
            **self._ends('from', origin), **self._ends('to', destination), **extra,
        )

    def test_database_accepts_exactly_the_combinations_of_flow_rules(self):
        for kind, rule in FLOW_RULES.items():
            for origin in ALL_ENDPOINTS:
                for destination in ALL_ENDPOINTS:
                    allowed = origin in rule.origins and destination in rule.destinations
                    with self.subTest(kind=kind, origin=origin, destination=destination):
                        if allowed:
                            with transaction.atomic():
                                self._create(kind, origin, destination).delete()
                        else:
                            with self.assertRaises(IntegrityError), transaction.atomic():
                                self._create(kind, origin, destination)

    def test_two_origins_are_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Flow.objects.create(
                kind=FlowKind.SUPPLY, what=self.wheat, year=2024, quantity=1.0,
                from_asset=self.objects['from']['asset'],
                from_country=self.objects['from']['country'],
                to_company=self.objects['to']['company'],
            )

    def test_supply_from_an_asset_to_itself_is_rejected(self):
        asset = self.objects['from']['asset']
        with self.assertRaises(IntegrityError), transaction.atomic():
            Flow.objects.create(
                kind=FlowKind.SUPPLY, what=self.wheat, year=2024, quantity=1.0,
                from_asset=asset, to_asset=asset,
            )

    def test_estimated_revenue_only_on_production(self):
        self._create(FlowKind.PRODUCTION, 'asset', None, estimated_revenue=10.0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._create(FlowKind.EMISSION, 'asset', 'environment', estimated_revenue=10.0)

    def test_scope_defaults_to_undefined(self):
        flow = self._create(FlowKind.EMISSION, 'company', 'environment')
        self.assertEqual(flow.scope, FlowScope.UNDEFINED)

    def test_endpoint_types_and_str(self):
        flow = self._create(FlowKind.CONSUMPTION, 'environment', 'asset')
        self.assertEqual((flow.origin_type, flow.destination_type), ('environment', 'asset'))
        self.assertEqual(str(flow), 'Consommation — Blé (2024)')

    def test_a_commodity_in_use_cannot_be_deleted(self):
        self._create(FlowKind.PRODUCTION, 'asset', None)
        with self.assertRaises(ProtectedError):
            self.wheat.delete()


class LatestInventoryTests(TestCase):

    def setUp(self):
        country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private')
        self.mine = Asset.objects.create(name='Mine', latitude=1.0, longitude=2.0, country=country)
        self.plant = Asset.objects.create(
            name='Usine', latitude=1.0, longitude=2.0, country=country)

    def test_values_are_summed_for_the_latest_year_of_each_asset(self):
        make_inventory(asset=self.mine, key='water', year=2023, value=10.0)
        make_inventory(asset=self.mine, key='water', year=2024, value=100.0)
        make_inventory(asset=self.mine, key='water', year=2024, value=5.0)
        make_inventory(asset=self.mine, key='co2', year=2024, value=50.0)
        make_inventory(asset=self.plant, key='waste', year=2022, value=7.0)
        result = flow_service.latest_inventory(
            [self.mine.pk, self.plant.pk], ('water', 'co2', 'waste'))
        self.assertEqual(result[self.mine.pk], {
            'water': {'value': 105.0, 'unit': 'm³'},
            'co2': {'value': 50.0, 'unit': 'tCO₂e'},
        })
        self.assertEqual(result[self.plant.pk], {'waste': {'value': 7.0, 'unit': 't'}})

    def test_keys_outside_the_selection_do_not_shift_the_year(self):
        make_inventory(asset=self.mine, key='water', year=2023, value=10.0)
        make_inventory(asset=self.mine, key='energy', year=2024, value=999.0)
        result = flow_service.latest_inventory([self.mine.pk], ('water',))
        self.assertEqual(result[self.mine.pk], {'water': {'value': 10.0, 'unit': 'm³'}})

    def test_inventory_total_by_theme_and_year(self):
        make_inventory(asset=self.mine, key='water', year=2024, value=100.0)
        make_inventory(asset=self.mine, key='water', year=2023, value=1.0)
        self.assertEqual(flow_service.inventory_total(self.mine, 'water', 2024), 100.0)


class FlowAdminTests(TestCase):

    def setUp(self):
        self.root = get_user_model().objects.create_superuser(
            'root', 'root@example.com', 'pass')
        self.client.force_login(self.root)
        country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private')
        self.asset = Asset.objects.create(
            name='Usine', latitude=1.0, longitude=2.0, country=country)
        self.co2 = Commodity.objects.technical('co2')

    def _post(self, **ends):
        data = {
            'kind': 'EMISSION', 'what': self.co2.pk, 'scope': 'undefined',
            'year': 2024, 'quantity': 5, 'tier': 0,
        }
        data.update(ends)
        return self.client.post(reverse('admin:dashboard_flow_add'), data)

    def test_rule_violation_is_shown_in_the_form(self):
        response = self._post(from_asset=self.asset.pk)  # émission sans destination
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'va vers le milieu')
        self.assertFalse(Flow.objects.exists())

    def test_valid_emission_is_saved_with_its_author(self):
        response = self._post(from_asset=self.asset.pk, to_environment='on')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Flow.objects.get().created_by, self.root)
```

- [ ] **Step 2 : vérifier que les tests échouent**

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow.py -q`
Expected: FAIL (`cannot import name 'ALL_ENDPOINTS'`).

- [ ] **Step 3 : supprimer l'ancien catalogue et `AssetInventory`**

Dans `dashboard/models.py`, supprimer entièrement `class Flow(models.Model):` (le catalogue `key`/`name`/`unit`/`theme`) et `class AssetInventory(models.Model):`. Garder `KEY_HELP_TEXT` et `THEME_HELP_TEXT` : `ImpactCategory` et `Commodity` s'en servent.

Créer `dashboard/migrations/0052_delete_inventory_models.py` (écrite à la main : si Django la générait en même temps que le nouveau `Flow`, il verrait une modification de l'ancien `Flow` au lieu d'une suppression suivie d'une création) :

```python
"""Supprime l'inventaire mesuré historique (spec 2026-09-18 §7).

AssetInventory et le catalogue Flow sont remplacés par la table Flow unique
(migration suivante). Pas de migration des données (décision 2 de la spec).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0051_recreate_ownership'),
    ]

    operations = [
        migrations.DeleteModel(name='AssetInventory'),
        migrations.DeleteModel(name='Flow'),
    ]
```

- [ ] **Step 4 : ajouter la section « Flux » au modèle**

En tête de `dashboard/models.py`, ajouter aux imports de la bibliothèque standard :

```python
import operator
from collections import namedtuple
from functools import reduce
```

Juste après la classe `Ownership` (avant `class E4Assessment`), ajouter :

```python
# ── Flux : table Flow unique (spec 2026-09-18) ────────────────────────────────

ENDPOINT_ASSET = 'asset'
ENDPOINT_REGION = 'region'
ENDPOINT_COUNTRY = 'country'
ENDPOINT_COMPANY = 'company'
ENDPOINT_ENVIRONMENT = 'environment'
# Extrémités « lieu ou entreprise ». None désigne un côté vide (inconnu).
LOCATED_ENDPOINTS = (ENDPOINT_ASSET, ENDPOINT_REGION, ENDPOINT_COUNTRY, ENDPOINT_COMPANY)
ALL_ENDPOINTS = LOCATED_ENDPOINTS + (ENDPOINT_ENVIRONMENT, None)


class FlowKind(models.TextChoices):
    PRODUCTION = 'PRODUCTION', 'Production'
    SUPPLY = 'SUPPLY', 'Approvisionnement'
    CONSUMPTION = 'CONSUMPTION', 'Consommation'
    EMISSION = 'EMISSION', 'Émission'
    WASTE = 'WASTE', 'Déchet'


class FlowScope(models.TextChoices):
    SCOPE_1 = 'Scope 1', 'Scope 1'
    SCOPE_2 = 'Scope 2', 'Scope 2'
    SCOPE_3 = 'Scope 3', 'Scope 3'
    SCOPE_1_2 = 'Scope 1+2', 'Scope 1+2'
    SCOPE_1_2_3 = 'Scope 1+2+3', 'Scope 1+2+3'
    UNDEFINED = 'undefined', 'Non défini'


FlowRule = namedtuple('FlowRule', ['origins', 'destinations', 'message'])

# Types d'extrémité autorisés par nature de flux (spec §3.4). Source unique des
# contraintes en base et des messages d'erreur de l'import Excel.
FLOW_RULES = {
    FlowKind.PRODUCTION.value: FlowRule(
        (ENDPOINT_ASSET, ENDPOINT_COMPANY), (None,),
        "Une production part d'un actif ou d'une entreprise, sans destination.",
    ),
    FlowKind.SUPPLY.value: FlowRule(
        LOCATED_ENDPOINTS, LOCATED_ENDPOINTS,
        'Un approvisionnement va d’un actif, d’une région, d’un pays ou d’une '
        'entreprise vers un autre actif, région, pays ou entreprise.',
    ),
    FlowKind.CONSUMPTION.value: FlowRule(
        (ENDPOINT_ENVIRONMENT, None), (ENDPOINT_ASSET, ENDPOINT_COMPANY),
        'Une consommation vient du milieu ou d’une origine inconnue et va vers un '
        'actif ou une entreprise.',
    ),
    FlowKind.EMISSION.value: FlowRule(
        (ENDPOINT_ASSET, ENDPOINT_COMPANY), (ENDPOINT_ENVIRONMENT,),
        "Une émission part d'un actif ou d'une entreprise et va vers le milieu.",
    ),
    FlowKind.WASTE.value: FlowRule(
        (ENDPOINT_ASSET, ENDPOINT_COMPANY), (ENDPOINT_ENVIRONMENT, None, ENDPOINT_ASSET),
        "Un déchet part d'un actif ou d'une entreprise et va vers le milieu, un actif "
        '(site de traitement) ou une destination inconnue.',
    ),
}

SUPPLY_SELF_LOOP_MESSAGE = 'Un approvisionnement ne peut pas relier un lieu à lui-même.'
REVENUE_PRODUCTION_ONLY_MESSAGE = 'Seule une production porte un revenu estimé.'

# Suffixe du champ clé étrangère de chaque type d'extrémité : from_<suffixe>.
_ENDPOINT_FIELD_SUFFIX = {
    ENDPOINT_ASSET: 'asset',
    ENDPOINT_REGION: 'region',
    ENDPOINT_COUNTRY: 'country',
    ENDPOINT_COMPANY: 'company',
}


def endpoint_q(side, endpoint):
    """Q vrai quand le côté `side` ('from' ou 'to') vaut exactement `endpoint`."""
    condition = Q(**{f'{side}_environment': endpoint == ENDPOINT_ENVIRONMENT})
    for candidate, suffix in _ENDPOINT_FIELD_SUFFIX.items():
        condition &= Q(**{f'{side}_{suffix}__isnull': candidate != endpoint})
    return condition


def _endpoints_q(side, endpoints):
    return reduce(operator.or_, (endpoint_q(side, endpoint) for endpoint in endpoints))


def _flow_constraints():
    """Contraintes de Flow (spec §3.3 et §3.4), générées depuis FLOW_RULES."""
    distinct_ends = reduce(operator.and_, (
        ~Q(**{f'from_{suffix}': F(f'to_{suffix}')})
        for suffix in _ENDPOINT_FIELD_SUFFIX.values()
    ))
    constraints = [
        models.CheckConstraint(
            name='flow_single_origin',
            condition=_endpoints_q('from', ALL_ENDPOINTS),
            violation_error_message='Un flux a au plus une origine.',
        ),
        models.CheckConstraint(
            name='flow_single_destination',
            condition=_endpoints_q('to', ALL_ENDPOINTS),
            violation_error_message='Un flux a au plus une destination.',
        ),
        models.CheckConstraint(
            name='flow_located_end',
            condition=(
                _endpoints_q('from', LOCATED_ENDPOINTS) | _endpoints_q('to', LOCATED_ENDPOINTS)
            ),
            violation_error_message=(
                "L'origine ou la destination doit être un actif, une région, un pays ou "
                'une entreprise.'
            ),
        ),
        models.CheckConstraint(
            name='flow_environment_one_end',
            condition=~Q(from_environment=True, to_environment=True),
            violation_error_message=(
                'Le milieu ne peut pas être à la fois origine et destination.'
            ),
        ),
        models.CheckConstraint(
            name='flow_revenue_production_only',
            condition=Q(estimated_revenue__isnull=True) | Q(kind=FlowKind.PRODUCTION.value),
            violation_error_message=REVENUE_PRODUCTION_ONLY_MESSAGE,
        ),
        models.CheckConstraint(
            name='flow_supply_distinct_ends',
            condition=~Q(kind=FlowKind.SUPPLY.value) | distinct_ends,
            violation_error_message=SUPPLY_SELF_LOOP_MESSAGE,
        ),
    ]
    for kind, rule in FLOW_RULES.items():
        constraints.append(models.CheckConstraint(
            name=f'flow_rule_{kind.lower()}',
            condition=~Q(kind=kind) | (
                _endpoints_q('from', rule.origins) & _endpoints_q('to', rule.destinations)
            ),
            violation_error_message=rule.message,
        ))
    return constraints


FLOW_ENDPOINT_HELP_TEXT = (
    'Au plus un champ renseigné par côté (actif, région, pays, entreprise ou milieu). '
    'Tout vide = inconnu (acheteur ou origine non renseignés).'
)


def _flow_endpoint(model, side, label):
    """Clé étrangère d'extrémité d'un Flow (from_* ou to_*)."""
    return models.ForeignKey(
        model, on_delete=models.CASCADE, null=True, blank=True,
        related_name='flows_out' if side == 'from' else 'flows_in',
        verbose_name=f"{'Origine' if side == 'from' else 'Destination'} — {label}",
        help_text=FLOW_ENDPOINT_HELP_TEXT,
    )


class Flow(models.Model):
    """Quantité d'une commodité, une année, d'une origine vers une destination
    (spec 2026-09-18). Remplace Production, AssetInventory, SupplyNode, Exchange
    et Carbon_emission."""

    Kind = FlowKind
    Scope = FlowScope

    kind = models.CharField(
        max_length=12, choices=FlowKind.choices, verbose_name='Nature du flux',
    )
    what = models.ForeignKey(
        Commodity, on_delete=models.PROTECT, related_name='flows',
        verbose_name='Commodité',
    )
    scope = models.CharField(
        max_length=12, choices=FlowScope.choices, default=FlowScope.UNDEFINED,
        verbose_name='Scope GES',
    )

    from_asset = _flow_endpoint(Asset, 'from', 'actif')
    from_region = _flow_endpoint(SubnationalRegion, 'from', 'région')
    from_country = _flow_endpoint(Country, 'from', 'pays')
    from_company = _flow_endpoint(Company, 'from', 'entreprise')
    from_environment = models.BooleanField(
        default=False, verbose_name='Origine — milieu',
        help_text='Prélevé dans le milieu naturel, à proximité de la destination.',
    )

    to_asset = _flow_endpoint(Asset, 'to', 'actif')
    to_region = _flow_endpoint(SubnationalRegion, 'to', 'région')
    to_country = _flow_endpoint(Country, 'to', 'pays')
    to_company = _flow_endpoint(Company, 'to', 'entreprise')
    to_environment = models.BooleanField(
        default=False, verbose_name='Destination — milieu',
        help_text='Rejeté dans le milieu naturel, à proximité de l’origine.',
    )

    year = models.IntegerField(verbose_name='Année')
    quantity = models.FloatField(
        verbose_name='Quantité', help_text="Exprimée dans l'unité de la commodité.",
    )
    tier = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(3)], verbose_name='Tier',
        help_text=TIER_HELP_TEXT,
    )
    estimated_revenue = models.FloatField(
        null=True, blank=True, verbose_name='Revenu estimé',
        help_text='Production uniquement. ' + UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    source = models.CharField(max_length=255, blank=True, verbose_name='Source')
    reference = models.CharField(max_length=255, blank=True, verbose_name='Référence')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Créé le')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Modifié le')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='Créé par',
    )

    class Meta:
        verbose_name = 'Flux'
        verbose_name_plural = 'Flux'
        constraints = _flow_constraints()

    def __str__(self):
        return f'{self.get_kind_display()} — {self.what.name} ({self.year})'

    def _endpoint_type(self, side):
        if getattr(self, f'{side}_environment'):
            return ENDPOINT_ENVIRONMENT
        for endpoint, suffix in _ENDPOINT_FIELD_SUFFIX.items():
            if getattr(self, f'{side}_{suffix}_id') is not None:
                return endpoint
        return None

    @property
    def origin_type(self):
        return self._endpoint_type('from')

    @property
    def destination_type(self):
        return self._endpoint_type('to')
```

- [ ] **Step 5 : (rappel) ordre de génération de la migration**

Ne pas lancer `makemigrations` maintenant : il importe les vues, qui référencent encore `AssetInventory`. La migration `0053_flow` se génère au Step 12, une fois les étapes 6 à 11 faites. Elle ne doit contenir qu'un `CreateModel` de `Flow` avec ses 11 contraintes. Si elle contient des `RemoveField`/`AddField`, c'est que `0052_delete_inventory_models.py` n'est pas prise en compte : vérifier sa dépendance.

- [ ] **Step 6 : service de lecture et fabrique de test**

Créer `dashboard/services/flows.py` :

```python
"""Lecture de la table Flow (spec 2026-09-18 §4).

Seul module qui filtre `Flow` : les vues appellent ces fonctions et ne
construisent jamais de requête `Flow` elles-mêmes.
"""
from collections import defaultdict

from django.db.models import Q

from dashboard.models import Flow, FlowKind

_OUTGOING_INVENTORY_KINDS = (FlowKind.EMISSION, FlowKind.WASTE)


def _inventory_rows(asset_ids):
    """Lignes d'inventaire mesuré des actifs : consommations qui y entrent,
    émissions et déchets qui en sortent, commodités à clé technique."""
    return (
        Flow.objects.filter(what__key__isnull=False)
        .filter(
            Q(kind=FlowKind.CONSUMPTION, to_asset_id__in=asset_ids)
            | Q(kind__in=_OUTGOING_INVENTORY_KINDS, from_asset_id__in=asset_ids)
        )
        .select_related('what')
        .order_by('pk')
    )


def _inventory_asset_id(flow):
    """Actif mesuré : destination d'une consommation, origine sinon."""
    if flow.kind == FlowKind.CONSUMPTION:
        return flow.to_asset_id
    return flow.from_asset_id


def latest_inventory(asset_ids, keys):
    """{asset_id: {key: {'value', 'unit'}}} : valeurs sommées par commodité
    technique, pour l'année la plus récente de chaque actif parmi les lignes des
    clés demandées. Une production plus récente ne décale pas l'inventaire."""
    rows = list(_inventory_rows(asset_ids).filter(what__key__in=keys))
    latest = {}
    for flow in rows:
        asset_id = _inventory_asset_id(flow)
        latest[asset_id] = max(latest.get(asset_id, flow.year), flow.year)
    result = defaultdict(dict)
    for flow in rows:
        asset_id = _inventory_asset_id(flow)
        if flow.year != latest[asset_id]:
            continue
        entry = result[asset_id].setdefault(
            flow.what.key, {'value': 0.0, 'unit': flow.what.unit})
        entry['value'] += flow.quantity
    return dict(result)


def inventory_total(asset, theme, year):
    """Somme des mesures d'inventaire d'un actif, une année, pour un thème."""
    return sum(
        flow.quantity
        for flow in _inventory_rows([asset.pk]).filter(what__theme=theme, year=year)
    )
```

Créer `dashboard/testing.py` :

```python
"""Fabriques de données de test pour la table Flow (spec 2026-09-18).

Hors motif de collecte pytest (`tests.py`, `test_*.py`, `tests_*.py`) : ce module
n'est pas un fichier de tests, il est importé par eux.
"""
from .models import Commodity, Flow, FlowKind

# Nature du flux d'une mesure d'inventaire, selon la commodité technique.
_INVENTORY_KIND = {
    'water': FlowKind.CONSUMPTION,
    'energy': FlowKind.CONSUMPTION,
    'surface_area': FlowKind.CONSUMPTION,
    'co2': FlowKind.EMISSION,
    'waste': FlowKind.WASTE,
}


def make_inventory(*, asset, key, year, value):
    """Mesure d'inventaire : consommation prélevée dans le milieu, ou émission /
    déchet rejetés dans le milieu."""
    kind = _INVENTORY_KIND[key]
    if kind == FlowKind.CONSUMPTION:
        ends = {'from_environment': True, 'to_asset': asset}
    else:
        ends = {'from_asset': asset, 'to_environment': True}
    return Flow.objects.create(
        kind=kind, what=Commodity.objects.technical(key), year=year, quantity=value,
        **ends,
    )
```

- [ ] **Step 7 : basculer les vues d'inventaire**

Dans `dashboard/views.py` :

1. Retirer `AssetInventory` de l'import `from .models import (...)` et ajouter `from .services import flows as flow_service` après les autres imports de `.services`.
2. Dans `_get_leap_evaluate_data`, remplacer le bloc qui commence par `# Consommation mesurée : année d'inventaire la plus récente de chaque asset.` et se termine par `consumption[inv.asset_id][inv.flow.key] += inv.value` par :

```python
    # Consommation mesurée : année d'inventaire la plus récente de chaque asset.
    inventory = flow_service.latest_inventory(asset_ids, ('water', 'co2', 'waste'))
    consumption = {
        asset_id: {key: entry['value'] for key, entry in entries.items()}
        for asset_id, entries in inventory.items()
    }
```

puis, plus bas dans la même fonction, remplacer

```python
        cons = consumption.get(a.pk, {'water': 0.0, 'co2': 0.0, 'waste': 0.0})
```

par `cons = consumption.get(a.pk, {})`, et les trois lignes `round(cons['water'], 2)`, `round(cons['co2'], 2)`, `round(cons['waste'], 2)` par `round(cons.get('water', 0.0), 2)`, `round(cons.get('co2', 0.0), 2)`, `round(cons.get('waste', 0.0), 2)`.

3. Dans `_get_physical_risk_data`, remplacer le bloc qui commence par `latest_inv_years = dict(` (juste après le commentaire « Inventaire mesuré (informatif) ») et se termine à la fin de la fonction interne `_inventory_for` par :

```python
    inventory = flow_service.latest_inventory(asset_ids, _RISK_INVENTORY_KEYS)

    def _inventory_for(asset_id):
        entries = inventory.get(asset_id, {})
        return [
            {
                'name': _RISK_INVENTORY_LABELS[key],
                'value': round(entries[key]['value'], 2),
                'unit': entries[key]['unit'],
            }
            for key in _RISK_INVENTORY_KEYS
            if key in entries and entries[key]['value']
        ]
```

- [ ] **Step 8 : `measured_vs_modeled`**

Dans `dashboard/services/impacts.py`, fonction `measured_vs_modeled`, remplacer

```python
    from dashboard.models import AssetInventory, ImpactCategory, Production
    measured = sum(
        inv.value
        for inv in AssetInventory.objects.filter(
            asset=asset, year=year, flow__theme=theme
        )
    )
```

par

```python
    from dashboard.models import ImpactCategory, Production
    from dashboard.services.flows import inventory_total
    measured = inventory_total(asset, theme, year)
```

et, dans la docstring, remplacer `(AssetInventory dont le flow porte ce theme)` par `(lignes d'inventaire de Flow dont la commodité porte ce theme)`.

- [ ] **Step 9 : admin**

Dans `dashboard/admin.py` :

1. Dans l'import `from .models import (...)`, retirer `AssetInventory` (garder `Flow`, qui désigne désormais la nouvelle table).
2. Supprimer les classes `FlowAdmin` (ancienne) et `AssetInventoryAdmin`.
3. Ajouter à leur place :

```python
def _endpoint_label(flow, side):
    """Libellé d'une extrémité : lieu ou entreprise, « Milieu », ou « — » si vide."""
    if getattr(flow, f'{side}_environment'):
        return 'Milieu'
    for suffix in ('asset', 'region', 'country', 'company'):
        target = getattr(flow, f'{side}_{suffix}')
        if target is not None:
            return str(target)
    return '—'


@admin.register(Flow)
class FlowAdmin(admin.ModelAdmin):
    search_fields = (
        'what__name', 'from_asset__name', 'from_company__name',
        'to_asset__name', 'to_company__name',
    )
    list_display = ('kind', 'what', 'scope', 'origin', 'destination', 'year', 'quantity')
    list_filter = ('kind', 'scope', 'year', 'tier')
    autocomplete_fields = (
        'what', 'from_asset', 'from_region', 'from_country', 'from_company',
        'to_asset', 'to_region', 'to_country', 'to_company',
    )
    fieldsets = (
        (None, {'fields': (
            'kind', 'what', 'scope', 'year', 'quantity', 'tier', 'estimated_revenue',
            'source', 'reference',
        )}),
        ('Origine', {'fields': (
            'from_asset', 'from_region', 'from_country', 'from_company', 'from_environment',
        )}),
        ('Destination', {'fields': (
            'to_asset', 'to_region', 'to_country', 'to_company', 'to_environment',
        )}),
    )

    @admin.display(description='Origine')
    def origin(self, obj):
        return _endpoint_label(obj, 'from')

    @admin.display(description='Destination')
    def destination(self, obj):
        return _endpoint_label(obj, 'to')

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
```

Dans `dashboard/admin_site.py`, remplacer les deux entrées de `GROUPS` concernées par :

```python
    ('Flux', [m.Flow, m.Production, m.SupplyNode, m.Exchange]),
    ('Impacts & inventaire (ACV)', [
        m.ImpactMethod, m.ImpactCategory, m.CharacterizationFactor,
    ]),
```

Dans `dashboard/tests_admin_console.py`, ligne `self.assertContains(response, 'Chaîne d&#x27;approvisionnement')`, remplacer la chaîne attendue par `'Flux'`.

- [ ] **Step 10 : retirer la feuille d'import `AssetInventory`**

Dans `imports/services/constants.py` : supprimer l'entrée `'AssetInventory'` de `SHEET_COLUMNS`, `FK_FIELDS`, `REQUIRED_FIELDS` et `DUPLICATE_CRITERIA` ; retirer `'AssetInventory'` d'`IMPORT_ORDER` ; supprimer l'entrée `'flow': (None, 'key'),` de `MODEL_KEY_TO_SOURCE`.

Dans `imports/services/excel_parser.py` : retirer `AssetInventory` et `Flow` de l'import `dashboard.models` ; supprimer `'flow': keys(Flow.objects, 'key'),` de `_build_db_name_cache` et l'entrée `'AssetInventory'` de `_EXISTING_KEY_QUERIES`.

Dans `imports/services/importer.py` : retirer `AssetInventory` et `Flow` de l'import ; supprimer la fonction `_import_asset_inventory`, son entrée dans `_IMPORTERS` et la ligne `'flow': ...` de `_build_lookup`.

Dans `imports/services/excel_template.py` : retirer `Flow` de l'import et supprimer la ligne `('Flows (flow_key)', Flow.objects.values_list('key', flat=True)),`.

- [ ] **Step 11 : adapter les tests existants**

Dans `dashboard/tests.py` :

1. Supprimer les classes `AssetInventoryModelTests`, `FlowModelTests`, `SeedFlowsTests` et `AssetConsumptionMigrateHelperTests` (elles testent des modèles supprimés).
2. Ajouter `from .testing import make_inventory` après les imports de `.models`.
3. Dans `PhysicalRiskDataTests.test_inventory_subset_latest_year_ordered`, remplacer les lignes allant de `from .models import AssetInventory, Flow` à la dernière `AssetInventory.objects.create(...)` par :

```python
        from .views import _get_physical_risk_data
        make_inventory(asset=self.a1, key='water', year=2023, value=10.0)
        make_inventory(asset=self.a1, key='water', year=2024, value=100.0)
        make_inventory(asset=self.a1, key='co2', year=2024, value=50.0)
        make_inventory(asset=self.a1, key='energy', year=2024, value=999.0)
```

4. Dans `LeapEvaluateDataTests.setUp`, supprimer la ligne `from .models import AssetInventory, Flow` et remplacer les trois `AssetInventory.objects.create(...)` par :

```python
        make_inventory(asset=self.asset, key='water', year=2024, value=100.0)
        make_inventory(asset=self.asset, key='co2', year=2024, value=50.0)
        make_inventory(asset=self.asset, key='waste', year=2024, value=25.0)
```

5. Dans `LeapEvaluateDataTests.test_consumption_uses_latest_inventory_year_only`, supprimer `from .models import AssetInventory, Flow` et remplacer l'`AssetInventory.objects.create(...)` par `make_inventory(asset=self.asset, key='water', year=2023, value=10.0)`.
6. Dans `MeasuredVsModeledTests.test_pairs_measured_and_modeled`, retirer `Flow, AssetInventory,` de l'import local et remplacer les deux lignes `water = Flow.objects.get(key='water')` et `AssetInventory.objects.create(asset=asset, flow=water, year=2024, value=100.0)` par `make_inventory(asset=asset, key='water', year=2024, value=100.0)`.

Dans `imports/tests/test_importer.py` : supprimer la classe `ImporterAssetInventoryTest` et retirer `AssetInventory` de l'import.

Dans `imports/tests/test_excel_parser.py` : supprimer `test_known_flow_key_is_ok` et `test_unknown_flow_key_is_error` de `ParserKeyBasedFKTest`, et remplacer sa docstring par `"""Les catalogues (ImpactCategory, ClimateScenario) se référencent par \`key\` et non par \`name\`."""`.

Dans `imports/tests/test_roundtrip.py` : supprimer l'appel `_fill(wb, 'AssetInventory', {...})`, les deux lignes `inventory = AssetInventory.objects.get(...)` / `self.assertAlmostEqual(inventory.value, 4200.0)`, retirer `AssetInventory` de l'import et des deux tuples de modèles de `test_reuploading_the_same_workbook_creates_nothing_new`.

- [ ] **Step 12 : générer la migration (Step 5), puis lancer les tests de la tâche**

Run: `.\venv\Scripts\python.exe manage.py makemigrations dashboard --name flow`, puis `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow.py -q`
Expected: tous les tests de `tests_flow.py` passent (le test en matrice couvre 180 combinaisons).

- [ ] **Step 13 : lancer toute la suite**

Run: `.\venv\Scripts\python.exe -m pytest -q`
Expected: tout passe ; `git status dashboard/golden` n'affiche rien. Vérifier aussi `Select-String -Path dashboard\*.py,dashboard\services\*.py,imports\services\*.py -Pattern 'AssetInventory'` : aucun résultat.

- [ ] **Step 14 : commit**

```powershell
git add dashboard imports
git commit -m "feat(flow): table Flow unique et inventaire mesuré" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5 : productions → flux PRODUCTION

Toutes les lectures de `Production` passent par `flows.productions`, `flows.latest_productions` ou `flows.company_productions`, puis le modèle `Production` est supprimé. Les sorties JSON ne doivent pas bouger : les fichiers golden servent de filet.

**Files:**
- Modify: `dashboard/services/flows.py`, `dashboard/testing.py`
- Modify: `dashboard/views.py` (11 fonctions), `dashboard/services/stress_test.py`, `dashboard/services/impacts.py`
- Modify: `dashboard/management/commands/populate_acme.py`
- Modify: `dashboard/models.py` (suppression de `Production`) ; Create: `dashboard/migrations/0054_delete_production.py` (générée)
- Modify: `dashboard/admin.py`, `dashboard/admin_site.py`
- Modify: `imports/services/constants.py`, `excel_parser.py`, `importer.py`
- Modify: `dashboard/tests_flow.py`, `dashboard/tests.py`, `imports/tests/test_importer.py`, `imports/tests/test_roundtrip.py`

**Interfaces:**
- Consumes: `Asset.objects.owned_by` (tâche 2), `Flow`, `FlowKind`, `make_inventory` (tâche 4).
- Produces (`dashboard.services.flows`) : `productions(asset_ids) -> list[Flow]` (toutes années, triés par `pk`, `select_related` sur `what` et `from_asset__country` / `from_asset__subnational_region`) ; `latest_productions(asset_ids) -> list[Flow]` (même tri, année la plus récente de chaque actif) ; `company_productions(company) -> list[Flow]`.
- Produces (`dashboard.testing`) : `make_production(*, commodity, year, production, asset=None, company=None, estimated_revenue=0.0, tier=0) -> Flow`.
- Convention pour les vues : une production `f` expose `f.what` (commodité), `f.quantity`, `f.from_asset` / `f.from_asset_id`, `f.estimated_revenue` (peut valoir `None` : toujours lire `f.estimated_revenue or 0.0`).

- [ ] **Step 1 : écrire les tests du service**

Dans `dashboard/tests_flow.py`, ajouter `Ownership` à l'import de `.models` et remplacer `from .testing import make_inventory` par `from .testing import make_inventory, make_production`. Ajouter en fin de fichier :

```python
class ProductionServiceTests(TestCase):

    def setUp(self):
        country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private')
        self.company = Company.objects.create(name='Acme')
        self.a1 = Asset.objects.create(name='A1', latitude=1.0, longitude=2.0, country=country)
        self.a2 = Asset.objects.create(name='A2', latitude=1.0, longitude=2.0, country=country)
        Ownership.objects.create(asset=self.a1, company=self.company, share=1)
        self.soy = Commodity.objects.create(name='Soja')

    def _produce(self, **kwargs):
        return make_production(commodity=self.soy, production=1.0, **kwargs)

    def test_productions_keep_creation_order_across_years(self):
        first = self._produce(asset=self.a1, year=2024)
        second = self._produce(asset=self.a1, year=2023)
        self.assertEqual(flow_service.productions([self.a1.pk]), [first, second])

    def test_latest_productions_keep_the_latest_year_of_each_asset(self):
        self._produce(asset=self.a1, year=2023)
        recent = self._produce(asset=self.a1, year=2024)
        older_asset = self._produce(asset=self.a2, year=2022)
        self.assertEqual(
            flow_service.latest_productions([self.a1.pk, self.a2.pk]), [recent, older_asset])

    def test_other_kinds_are_not_productions(self):
        make_inventory(asset=self.a1, key='co2', year=2024, value=5.0)
        self.assertEqual(flow_service.productions([self.a1.pk]), [])

    def test_company_productions_merge_the_company_and_its_assets(self):
        own = self._produce(asset=self.a1, year=2024)
        declared = self._produce(company=self.company, year=2024)
        self._produce(asset=self.a2, year=2024)  # actif non détenu
        self.assertEqual(flow_service.company_productions(self.company), [own, declared])

    def test_a_more_recent_production_does_not_shift_the_inventory_year(self):
        make_inventory(asset=self.a1, key='water', year=2023, value=10.0)
        self._produce(asset=self.a1, year=2024)
        result = flow_service.latest_inventory([self.a1.pk], ('water',))
        self.assertEqual(result[self.a1.pk]['water']['value'], 10.0)
```

- [ ] **Step 2 : vérifier que les tests échouent**

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow.py -q`
Expected: FAIL (`cannot import name 'make_production'`).

- [ ] **Step 3 : fabrique et service**

Ajouter à `dashboard/testing.py` :

```python
def make_production(*, commodity, year, production, asset=None, company=None,
                    estimated_revenue=0.0, tier=0):
    """Flux PRODUCTION, avec la signature de l'ancien Production.objects.create
    pour limiter la réécriture des tests. Un actif l'emporte sur l'entreprise :
    une production n'a qu'une origine."""
    return Flow.objects.create(
        kind=FlowKind.PRODUCTION, what=commodity,
        from_asset=asset, from_company=None if asset is not None else company,
        year=year, quantity=production, estimated_revenue=estimated_revenue, tier=tier,
    )
```

Dans `dashboard/services/flows.py`, remplacer `from dashboard.models import Flow, FlowKind` par `from dashboard.models import Asset, Flow, FlowKind` et ajouter en fin de fichier :

```python
def productions(asset_ids):
    """Flux PRODUCTION des actifs donnés, toutes années, dans l'ordre de création
    (déterminisme SQLite/PostgreSQL : le sankey de Mesure d'empreinte en dépend)."""
    return list(
        Flow.objects.filter(kind=FlowKind.PRODUCTION, from_asset_id__in=asset_ids)
        .select_related('what', 'from_asset__country', 'from_asset__subnational_region')
        .order_by('pk')
    )


def latest_productions(asset_ids):
    """Comme productions(), en ne gardant que l'année la plus récente de chaque actif."""
    rows = productions(asset_ids)
    latest = {}
    for flow in rows:
        latest[flow.from_asset_id] = max(latest.get(flow.from_asset_id, flow.year), flow.year)
    return [flow for flow in rows if flow.year == latest[flow.from_asset_id]]


def company_productions(company):
    """Flux PRODUCTION déclarés par l'entreprise ou par les actifs qu'elle détient
    aujourd'hui, toutes années, dans l'ordre de création."""
    owned = Asset.objects.owned_by(company).values('pk')
    return list(
        Flow.objects.filter(kind=FlowKind.PRODUCTION)
        .filter(Q(from_company=company) | Q(from_asset__in=owned))
        .select_related('what')
        .order_by('pk')
    )
```

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow.py -q`
Expected: tout passe.

- [ ] **Step 4 : `_get_dependencies_data`**

Remplacer

```python
    productions_qs = Production.objects.filter(
        Q(company=company) | Q(asset__in=Asset.objects.owned_by(company))
    ).select_related('commodity').distinct()

    max_year = productions_qs.aggregate(Max('year'))['year__max']
    if max_year is None:
        return empty

    productions = list(productions_qs.filter(year=max_year))
```

par

```python
    all_productions = flow_service.company_productions(company)
    if not all_productions:
        return empty

    max_year = max(p.year for p in all_productions)
    productions = [p for p in all_productions if p.year == max_year]
```

puis, dans la même fonction : `_commodity_dep_scores(p.commodity)` (deux occurrences) devient `_commodity_dep_scores(p.what)`, et `critical_nodes.add((p.commodity_id, p.tier))` devient `critical_nodes.add((p.what_id, p.tier))`.

- [ ] **Step 5 : `_get_company_data`**

Remplacer

```python
    assets = list(
        Asset.objects.owned_by(company)
        .select_related('country', 'subnational_region')
        .prefetch_related('production_set__commodity')
        .distinct()
    )

    cf_index = build_cf_index(
        commodity_ids=[p.commodity_id for a in assets for p in a.production_set.all()],
        category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )
```

par

```python
    assets = list(
        Asset.objects.owned_by(company).select_related('country', 'subnational_region')
    )
    prods_by_asset = defaultdict(list)
    for p in flow_service.productions([a.pk for a in assets]):
        prods_by_asset[p.from_asset_id].append(p)

    cf_index = build_cf_index(
        commodity_ids=[p.what_id for prods in prods_by_asset.values() for p in prods],
        category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )
```

Puis, dans la suite de la fonction :
- `asset_commodities = {p.commodity.name for p in asset.production_set.all()}` → `asset_commodities = {p.what.name for p in prods_by_asset[asset.pk]}` ;
- `prods_all = list(asset.production_set.all())` → `prods_all = prods_by_asset[asset.pk]` ;
- dans le calcul de `footprint` et de `dette_eco` : `p.production` → `p.quantity`, `p.commodity_id` → `p.what_id`, `p.commodity.biodiversity_loss_class` → `p.what.biodiversity_loss_class` ;
- remplacer la liste `productions_data` par :

```python
        productions_data = [
            {
                'commodity': p.what.name,
                'quantity': round(p.quantity, 2),
                'unit': p.what.unit,
                'revenue': round(p.estimated_revenue or 0.0, 2),
            }
            for p in sorted(recent_prods, key=lambda x: -x.quantity)
        ]
```

- `'commodities': ', '.join(sorted({p.commodity.name for p in prods_all})),` → `'commodities': ', '.join(sorted({p.what.name for p in prods_all})),`.

- [ ] **Step 6 : `_get_mesure_empreinte_data`**

Remplacer le bloc allant de `latest_years = dict(` jusqu'à la boucle `for p in productions:` incluse (fin : `link_commodity_asset[(p.commodity.name, p.asset_id)] += impact`) par :

```python
    productions = flow_service.latest_productions(asset_ids)
    if not productions:
        return empty

    # ref_year is the most recent data year across all assets (assets may contribute different years)
    ref_year = max(p.year for p in productions)

    cf_index = build_cf_index(
        commodity_ids=[p.what_id for p in productions],
        category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )

    commodity_impact = defaultdict(float)
    asset_impact = defaultdict(float)
    asset_meta = {}
    link_commodity_asset = defaultdict(float)

    for p in productions:
        asset = p.from_asset
        impact = p.quantity * cf_value(
            cf_index, p.what_id, CAT_ECOSYSTEM_DIVERSITY,
            asset.subnational_region_id, asset.country_id,
        )
        commodity_impact[p.what.name] += impact
        asset_impact[asset.pk] += impact
        asset_meta.setdefault(asset.pk, {'name': asset.name, 'country': asset.country.name})
        link_commodity_asset[(p.what.name, asset.pk)] += impact
```

- [ ] **Step 7 : `_get_leap_locate_data` (partie productions)**

Remplacer

```python
    assets = list(
        Asset.objects.owned_by(company)
        .select_related('country', 'subnational_region')
        .prefetch_related(
            Prefetch('production_set', queryset=Production.objects.select_related('commodity')),
        )
        .distinct()
    )
    asset_ids = [a.pk for a in assets]
```

par

```python
    assets = list(
        Asset.objects.owned_by(company).select_related('country', 'subnational_region')
    )
    asset_ids = [a.pk for a in assets]
    recent_by_asset = defaultdict(list)
    for p in flow_service.latest_productions(asset_ids):
        recent_by_asset[p.from_asset_id].append(p)
```

puis, dans la boucle `for a in assets:`, remplacer les lignes allant de `# Données de production directe` à la définition de `asset_types` incluse par :

```python
        # Données de production directe (opérations propres de la société).
        recent_prods = recent_by_asset[a.pk]

        productions = [
            {
                'commodity': p.what.name,
                'quantity': round(p.quantity, 2),
                'unit': p.what.unit,
                'revenue': round(p.estimated_revenue or 0.0, 2),
            }
            for p in sorted(recent_prods, key=lambda x: -x.quantity)
        ]
        revenue_total = round(sum(p.estimated_revenue or 0.0 for p in recent_prods), 2)
        asset_types = sorted({
            p.what.get_biodiversity_loss_class_display() for p in recent_prods
        })
```

- [ ] **Step 8 : `_get_leap_evaluate_data` (partie productions)**

Remplacer

```python
    # Productions de l'année la plus récente de chaque asset.
    latest_years = dict(
        Production.objects.filter(asset_id__in=asset_ids)
        .values('asset_id')
        .annotate(max_year=Max('year'))
        .values_list('asset_id', 'max_year')
    )
    productions = [
        p for p in Production.objects.filter(asset_id__in=asset_ids).select_related('commodity')
        if latest_years.get(p.asset_id) == p.year
    ]
```

par

```python
    # Productions de l'année la plus récente de chaque asset.
    productions = flow_service.latest_productions(asset_ids)
```

puis `commodity_ids=[p.commodity_id for p in productions]` → `commodity_ids=[p.what_id for p in productions]`, et remplacer la boucle `for p in productions:` du calcul d'impacts par :

```python
    for p in productions:
        ai = asset_impacts[p.from_asset_id]
        region_id, country_id = asset_loc.get(p.from_asset_id, (None, None))
        for f in _evaluate_keys:
            ai[f] += p.quantity * cf_value(
                cf_index, p.what_id, f, region_id, country_id,
            )
```

- [ ] **Step 9 : `_get_leap_prepare_data`**

Remplacer

```python
    assets = list(
        Asset.objects.owned_by(company)
        .prefetch_related(
            Prefetch('production_set',
                     queryset=Production.objects.select_related('commodity'))
        )
        .distinct()
    )

    all_commodity_ids = [
        p.commodity_id for a in assets for p in a.production_set.all()
    ]
```

par

```python
    assets = list(Asset.objects.owned_by(company))
    prods_by_asset = defaultdict(list)
    for p in flow_service.productions([a.pk for a in assets]):
        prods_by_asset[p.from_asset_id].append(p)

    all_commodity_ids = [p.what_id for prods in prods_by_asset.values() for p in prods]
```

puis `prods = list(a.production_set.all())` → `prods = prods_by_asset[a.pk]`, `c = p.commodity` → `c = p.what`, `line_qty[c.pk] += p.production` → `line_qty[c.pk] += p.quantity`.

- [ ] **Step 10 : `_get_dette_ecologique_data` et `_company_ecological_debt`**

Dans les **deux** fonctions, remplacer le bloc allant de `latest_years = dict(` à la ligne qui filtre `productions` sur `latest_years` incluse. Dans `_get_dette_ecologique_data` :

```python
    productions = flow_service.latest_productions(asset_ids)
    if not productions:
        return empty

    ref_year = max(p.year for p in productions)
```

Dans `_company_ecological_debt` :

```python
    productions = flow_service.latest_productions(asset_ids)
    if not productions:
        return result
```

Puis, dans les deux fonctions : `commodity_ids=[p.commodity_id for p in productions]` → `commodity_ids=[p.what_id for p in productions]` ; `asset_map.get(p.asset_id)` → `asset_map.get(p.from_asset_id)` ; `p.commodity.biodiversity_loss_class` → `p.what.biodiversity_loss_class` ; `p.production` → `p.quantity` ; `p.commodity_id` → `p.what_id` ; `p.commodity.name` → `p.what.name`. Dans `_get_dette_ecologique_data`, `asset_comm[p.asset_id][...]` devient `asset_comm[p.from_asset_id][...]`.

- [ ] **Step 11 : `_get_physical_risk_data` et `_company_physical_risks`**

Dans `_get_physical_risk_data`, remplacer

```python
    latest_years = dict(
        Production.objects.filter(asset_id__in=asset_ids)
        .values('asset_id')
        .annotate(max_year=Max('year'))
        .values_list('asset_id', 'max_year')
    )
    exposition = defaultdict(float)
    for p in Production.objects.filter(asset_id__in=asset_ids).values(
        'asset_id', 'year', 'estimated_revenue'
    ):
        if latest_years.get(p['asset_id']) == p['year']:
            exposition[p['asset_id']] += p['estimated_revenue']
```

par

```python
    exposition = defaultdict(float)
    for p in flow_service.latest_productions(asset_ids):
        exposition[p.from_asset_id] += p.estimated_revenue or 0.0
```

Dans `_company_physical_risks`, remplacer le bloc allant de `latest_years = dict(` à `weights[p.asset_id] += p.estimated_revenue or 0.0` par :

```python
    weights = {a.pk: 0.0 for a in assets}
    for p in flow_service.latest_productions(asset_ids):
        weights[p.from_asset_id] += p.estimated_revenue or 0.0
```

- [ ] **Step 12 : `_get_comparison_data` et `_company_endpoint_impacts`**

Dans `_get_comparison_data`, supprimer le bloc `latest_years = dict(...)` placé avant `result = {`, puis remplacer

```python
    if not latest_years:
        return result

    productions = list(
        Production.objects.filter(asset_id__in=asset_ids)
        .select_related('commodity', 'asset__country', 'asset__subnational_region')
    )
    productions = [p for p in productions if latest_years.get(p.asset_id) == p.year]
```

par

```python
    productions = flow_service.latest_productions(asset_ids)
    if not productions:
        return result
```

et, dans la boucle : `asset_map.get(p.asset_id)` → `asset_map.get(p.from_asset_id)`, `p.production` → `p.quantity`, `p.commodity_id` → `p.what_id`, `getattr(p.commodity, f, 'VL')` → `getattr(p.what, f, 'VL')`, `p.commodity.biodiversity_loss_class` → `p.what.biodiversity_loss_class` ; `commodity_ids=[p.commodity_id ...]` → `commodity_ids=[p.what_id ...]`.

Dans `_company_endpoint_impacts`, remplacer tout le corps après `totals = {k: 0.0 for k in category_keys}` par :

```python
    asset_ids = list(Asset.objects.owned_by(company).values_list('pk', flat=True))
    productions = flow_service.latest_productions(asset_ids)
    if not productions:
        return totals
    cf_index = build_cf_index(
        commodity_ids=[p.what_id for p in productions],
        category_keys=category_keys,
    )
    for p in productions:
        for key in category_keys:
            totals[key] += p.quantity * cf_value(
                cf_index, p.what_id, key,
                p.from_asset.subnational_region_id, p.from_asset.country_id,
            )
    return totals
```

- [ ] **Step 13 : imports de `views.py`**

Retirer `Production` de l'import `from .models import (...)`. Vérifier avec `Select-String -Path dashboard\views.py -Pattern 'Max\(|Prefetch\(|\bQ\('` quels noms restent utilisés et retirer de `from django.db.models import ...` ceux qui ne le sont plus. Vérification finale : `Select-String -Path dashboard\views.py -Pattern 'Production|production_set|\.commodity_id|p\.production'` ne renvoie rien.

- [ ] **Step 14 : stress test**

Dans `dashboard/services/stress_test.py`, retirer `Production` de l'import `from ..models import (...)`, ajouter `from .flows import latest_productions  # noqa: E402` sous `from .hazards import PHYSICAL_RISKS`, et remplacer dans `company_snapshot` le bloc allant de `latest_years = dict(` à la fin de la boucle qui remplit `exposure_by_asset` par :

```python
    exposure_by_asset = {}
    for p in latest_productions([asset.pk for asset in assets]):
        exposure_by_asset[p.from_asset_id] = (
            exposure_by_asset.get(p.from_asset_id, 0.0) + (p.estimated_revenue or 0.0)
        )
```

Supprimer la ligne `asset_ids = [asset.pk for asset in assets]` si elle n'est plus utilisée, et `from django.db.models import Max  # noqa: E402` si `Max` n'apparaît plus dans le fichier.

- [ ] **Step 15 : `measured_vs_modeled`, partie modélisée**

Dans `dashboard/services/impacts.py`, remplacer

```python
    from dashboard.models import ImpactCategory, Production
    from dashboard.services.flows import inventory_total
```

par

```python
    from dashboard.models import ImpactCategory
    from dashboard.services.flows import inventory_total, productions
```

et la boucle de calcul de `modeled` par :

```python
    for p in productions([asset.pk]):
        if p.year != year:
            continue
        for key in cat_keys:
            modeled += p.quantity * cf_value(
                cf_index, p.what_id, key,
                asset.subnational_region_id, asset.country_id,
            )
```

Dans la docstring, `(production × CF des catégories portant ce theme)` reste exact.

- [ ] **Step 16 : `populate_acme`**

Dans `dashboard/management/commands/populate_acme.py`, retirer `Production` de l'import et ajouter `Flow, FlowKind`. Remplacer la boucle `for asset, commodity, scope, year, qty, revenue in productions:` par (même ordre de création, pour que les identifiants restent ceux du golden) :

```python
        for asset, commodity, scope, year, qty, revenue in productions:
            Flow.objects.get_or_create(
                kind=FlowKind.PRODUCTION,
                what=commodity,
                from_asset=asset,
                tier=SCOPE_TO_TIER[scope],
                year=year,
                defaults={'quantity': qty, 'estimated_revenue': revenue},
            )
```

- [ ] **Step 17 : supprimer le modèle `Production`**

Dans `dashboard/models.py`, supprimer la classe `Production`, mais **garder** la constante `TIER_HELP_TEXT` déclarée juste avant : `Flow` l'utilise. Dans `dashboard/admin.py`, retirer `Production` de l'import et supprimer `ProductionAdmin`. Dans `dashboard/admin_site.py`, le groupe devient `('Flux', [m.Flow, m.SupplyNode, m.Exchange]),`.

Dans `imports/services/constants.py`, supprimer l'entrée `'Production'` de `SHEET_COLUMNS`, `FK_FIELDS`, `REQUIRED_FIELDS`, `DUPLICATE_CRITERIA` et d'`IMPORT_ORDER`. Dans `excel_parser.py`, retirer `Production` de l'import et de `_EXISTING_KEY_QUERIES`. Dans `importer.py`, retirer `Production` de l'import, supprimer `_import_production` et son entrée dans `_IMPORTERS`.

Run: `.\venv\Scripts\python.exe manage.py makemigrations dashboard --name delete_production`
Expected: `0054_delete_production.py` avec un seul `DeleteModel(name='Production')`.

- [ ] **Step 18 : adapter les tests existants**

Dans `dashboard/tests.py`, supprimer la classe `SupplyChainDroppedTests` (elle crée une `Production` pour vérifier l'absence d'un champ supprimé en juillet). Puis exécuter ce script dans le scratchpad :

```python
import pathlib
import re

path = pathlib.Path('dashboard/tests.py')
source = path.read_text(encoding='utf-8')
source, count = re.subn(r'\bProduction\.objects\.create\(', 'make_production(', source)
source = source.replace(
    'Production.objects.filter(asset=self.asset).update(estimated_revenue=50000.0)',
    "Flow.objects.filter(kind='PRODUCTION', from_asset=self.asset)"
    '.update(estimated_revenue=50000.0)',
)
path.write_text(source, encoding='utf-8')
print(count)
```

Puis, à la main : retirer `Production` de chaque `from .models import` du fichier (en tête et dans les imports locaux), ajouter `Flow` à l'import de tête, et remplacer `from .testing import make_inventory` par `from .testing import make_inventory, make_production`.

Vérification : `Select-String -Path dashboard\tests.py -Pattern '\bProduction\b'` ne renvoie plus rien.

Dans `imports/tests/test_importer.py`, supprimer la classe `ImporterProductionTest` et retirer `Production` de l'import. Dans `imports/tests/test_roundtrip.py`, supprimer l'appel `_fill(wb, 'Production', {...})`, les trois lignes `production = Production.objects.get(asset=asset)` et les deux `assertEqual` qui suivent, et retirer `Production` de l'import et des deux tuples de modèles.

- [ ] **Step 19 : lancer toute la suite, golden compris**

Run: `.\venv\Scripts\python.exe -m pytest -q`
Expected: tout passe. `GoldenViewOutputTests` passe **sans** modification : `git status dashboard/golden` n'affiche rien. Si un golden diffère, comparer l'ordre des productions (`order_by('pk')`) et l'ordre des actifs (`owned_by` trie par `pk`) avant toute autre piste.

- [ ] **Step 20 : commit**

```powershell
git add dashboard imports
git commit -m "refactor(flow): les productions deviennent des flux PRODUCTION" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6 : approvisionnements → flux SUPPLY

La carte des fournisseurs de LEAP Locate lit `flows.supplies_to`, puis `SupplyNode`, `Exchange` et `upstream_chain` sont supprimés.

**Files:**
- Modify: `dashboard/services/flows.py`, `dashboard/testing.py`, `dashboard/views.py` (`_get_leap_locate_data`)
- Modify: `dashboard/services/supply.py` (suppression d'`upstream_chain`)
- Modify: `dashboard/models.py` (suppression de `SupplyNode`, `Exchange`) ; Create: `dashboard/migrations/0055_delete_supply_graph.py` (générée)
- Modify: `dashboard/admin.py`, `dashboard/admin_site.py`
- Modify: `imports/services/constants.py`, `excel_parser.py`, `importer.py`, `excel_template.py`
- Modify: `dashboard/tests_flow.py`, `dashboard/tests.py`, `imports/tests/test_constants.py`, `imports/tests/test_excel_parser.py`, `imports/tests/test_importer.py`, `imports/tests/test_roundtrip.py`

**Interfaces:**
- Consumes: `Flow`, `FlowKind`, `flows.latest_productions` (tâche 5).
- Produces (`dashboard.services.flows`) : `supplies_to(asset_ids, company=None) -> list[Flow]` : flux SUPPLY dont la destination est l'un des actifs (ou `company` si fournie), dernière année de chaque destination, triés par `pk`.
- Produces (`dashboard.testing`) : `make_supply(*, what, year, quantity, origin, destination, tier=0) -> Flow`, où `origin` / `destination` sont une instance d'`Asset`, `SubnationalRegion`, `Country` ou `Company`.
- JSON de LEAP Locate : `suppliers.features[].properties.id` vaut `'asset-<pk>'` ou `'region-<pk>'`.

- [ ] **Step 1 : écrire les tests du service**

Dans `dashboard/tests_flow.py`, remplacer l'import de `.testing` par `from .testing import make_inventory, make_production, make_supply` et ajouter :

```python
class SupplyServiceTests(TestCase):

    def setUp(self):
        country = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private')
        self.region = SubnationalRegion.objects.create(name='Pará', country=country)
        self.company = Company.objects.create(name='Acme')
        self.plant = Asset.objects.create(
            name='Usine', latitude=1.0, longitude=2.0, country=country)
        self.farm = Asset.objects.create(
            name='Ferme', latitude=-3.0, longitude=-47.0, country=country)
        self.soy = Commodity.objects.create(name='Soja')

    def _supply(self, year, origin, destination):
        return make_supply(
            what=self.soy, year=year, quantity=1.0, origin=origin, destination=destination)

    def test_supplies_to_the_assets_and_optionally_to_the_company(self):
        to_plant = self._supply(2024, self.farm, self.plant)
        to_company = self._supply(2024, self.region, self.company)
        self.assertEqual(flow_service.supplies_to([self.plant.pk]), [to_plant])
        self.assertEqual(
            flow_service.supplies_to([self.plant.pk], company=self.company),
            [to_plant, to_company])

    def test_only_the_latest_year_of_each_destination_is_kept(self):
        self._supply(2023, self.farm, self.plant)
        recent = self._supply(2024, self.farm, self.plant)
        company_2023 = self._supply(2023, self.region, self.company)
        self.assertEqual(
            flow_service.supplies_to([self.plant.pk], company=self.company),
            [recent, company_2023])
```

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow.py -q`
Expected: FAIL (`cannot import name 'make_supply'`).

- [ ] **Step 2 : fabrique et service**

Dans `dashboard/testing.py`, remplacer l'import par `from .models import Asset, Commodity, Company, Country, Flow, FlowKind, SubnationalRegion` et ajouter :

```python
# Suffixe du champ d'extrémité selon le type de l'objet : from_<suffixe>.
_END_FIELD = {Asset: 'asset', SubnationalRegion: 'region', Country: 'country', Company: 'company'}


def make_supply(*, what, year, quantity, origin, destination, tier=0):
    """Flux SUPPLY entre deux lieux ou entreprises (Asset, SubnationalRegion,
    Country ou Company)."""
    return Flow.objects.create(
        kind=FlowKind.SUPPLY, what=what, year=year, quantity=quantity, tier=tier,
        **{f'from_{_END_FIELD[type(origin)]}': origin},
        **{f'to_{_END_FIELD[type(destination)]}': destination},
    )
```

Dans `dashboard/services/flows.py`, ajouter :

```python
def supplies_to(asset_ids, company=None):
    """Flux SUPPLY vers ces actifs (et vers `company` si fournie), en ne gardant
    que la dernière année connue de chaque destination."""
    destination = Q(to_asset_id__in=asset_ids)
    if company is not None:
        destination |= Q(to_company=company)
    rows = list(
        Flow.objects.filter(kind=FlowKind.SUPPLY).filter(destination)
        .select_related(
            'what', 'from_asset__country', 'from_region__country', 'to_asset',
        )
        .order_by('pk')
    )

    def _destination(flow):
        return ('asset', flow.to_asset_id) if flow.to_asset_id else ('company', flow.to_company_id)

    latest = {}
    for flow in rows:
        key = _destination(flow)
        latest[key] = max(latest.get(key, flow.year), flow.year)
    return [flow for flow in rows if flow.year == latest[_destination(flow)]]
```

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow.py -q`
Expected: tout passe.

- [ ] **Step 3 : adapter les tests de LEAP Locate**

Dans `dashboard/tests.py`, ajouter `make_supply` à l'import de `.testing`, puis dans `LeapLocateDataTests` :

1. Dans `test_supplier_features_and_links` et `test_supplier_that_is_owned_asset_has_no_point_but_keeps_link`, remplacer les lignes allant de `from .models import Exchange, SupplyNode` à la fin de l'appel `Exchange.objects.create(...)` par :

```python
        make_supply(
            what=self.commodity, year=2024, quantity=100.0, tier=1,
            origin=supplier_asset, destination=self.asset,
        )
```

2. Dans `test_supplier_features_and_links`, ajouter après `self.assertEqual(sp['commodities'], ['Soja'])` :

```python
        self.assertEqual(sp['id'], f'asset-{supplier_asset.pk}')
```

3. Ajouter à la classe :

```python
    def test_supply_to_the_company_shows_a_point_without_link(self):
        make_supply(
            what=self.commodity, year=2024, quantity=10.0,
            origin=self.region, destination=self.company,
        )
        from .views import _get_leap_locate_data
        data = _get_leap_locate_data(self.company)
        sup_feats = data['suppliers']['features']
        self.assertEqual(len(sup_feats), 1)
        self.assertEqual(sup_feats[0]['properties']['id'], f'region-{self.region.pk}')
        self.assertEqual(sup_feats[0]['properties']['name'], 'Île-de-France')
        self.assertEqual(data['supplier_links']['features'], [])
```

4. Supprimer les classes `SupplyNodeModelTests`, `ExchangeModelTests` et `UpstreamChainTests`.

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests.py -k LeapLocate -q`
Expected: FAIL sur `test_supply_to_the_company_shows_a_point_without_link` et sur les assertions d'identifiant (la vue lit encore `Exchange`).

- [ ] **Step 4 : basculer la carte des fournisseurs**

Dans `dashboard/views.py`, `_get_leap_locate_data`, remplacer tout le bloc qui commence par le commentaire `# Fournisseurs : Exchange relie un SupplyNode fournisseur à un SupplyNode` et se termine juste avant `return {` par :

```python
    # Fournisseurs : flux SUPPLY vers un actif détenu (trait fournisseur → actif)
    # ou vers la société elle-même (point sans trait : elle n'a pas de
    # coordonnées). Dernière année connue de chaque destination.
    suppliers = {}          # 'asset-<pk>' / 'region-<pk>' -> Feature point
    supplier_links = []     # une LineString fournisseur -> asset par lien
    for flow in flow_service.supplies_to(asset_ids, company=company):
        if flow.from_asset_id:
            sup = flow.from_asset
            sup_id = f'asset-{sup.pk}'
            coords = [sup.longitude, sup.latitude]
            sup_name, sup_country = sup.name, sup.country.name
            sup_is_owned = sup.pk in asset_id_set
        elif flow.from_region_id:
            reg = flow.from_region
            sup_id = f'region-{reg.pk}'
            coords = [reg.Mean_X, reg.Mean_Y]
            sup_name, sup_country = reg.name, reg.country.name
            sup_is_owned = False
        else:
            continue  # pays ou entreprise d'origine : pas de coordonnées → ignoré

        # Un fournisseur qui est lui-même un asset affiché (détenu par la société)
        # garde son lien, mais pas de marqueur fournisseur en doublon.
        if not sup_is_owned:
            feat = suppliers.get(sup_id)
            if feat is None:
                feat = {
                    'type': 'Feature',
                    'geometry': {'type': 'Point', 'coordinates': coords},
                    'properties': {
                        'id': sup_id,
                        'name': sup_name,
                        'country': sup_country,
                        'commodities': [],
                    },
                }
                suppliers[sup_id] = feat
            commodities = feat['properties']['commodities']
            if flow.what.name not in commodities:
                commodities.append(flow.what.name)

        cons_asset = flow.to_asset
        if cons_asset is None:
            continue  # destination = la société : point fournisseur sans trait

        supplier_links.append({
            'type': 'Feature',
            'geometry': {
                'type': 'LineString',
                'coordinates': [coords, [cons_asset.longitude, cons_asset.latitude]],
            },
            'properties': {
                'supplier': sup_name,
                'asset': cons_asset.name,
                'commodity': flow.what.name,
            },
        })
```

Retirer `Exchange` de l'import `from .models import (...)` de `views.py`.

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests.py -k LeapLocate -q`
Expected: tout passe.

- [ ] **Step 5 : supprimer `upstream_chain`**

Dans `dashboard/services/supply.py`, supprimer la ligne `from dashboard.models import Exchange` et la fonction `upstream_chain`. Remplacer la docstring du module par :

```python
"""Vocabulaire des tiers de la chaîne d'approvisionnement.

`TIER_LABELS[tier]` reproduit exactement l'ancien `_SCOPE_LABELS[scope]` ;
`TIER_TO_SCOPE` permet aux vues d'émettre la même clé `scope` qu'avant.
"""
```

- [ ] **Step 6 : supprimer les modèles et leur import**

Dans `dashboard/models.py`, supprimer `SUPPLY_NODE_LOCATION_HELP_TEXT`, `class SupplyNode` et `class Exchange`. Dans `dashboard/admin.py`, retirer `SupplyNode, Exchange` de l'import et supprimer `SupplyNodeAdmin` et `ExchangeAdmin`. Dans `dashboard/admin_site.py`, le groupe devient `('Flux', [m.Flow]),`.

Dans `imports/services/constants.py` : supprimer les entrées `'SupplyNode'` et `'Exchange'` de `SHEET_COLUMNS` (avec le commentaire « Graphe d'approvisionnement » qui les précède), `FK_FIELDS`, `REQUIRED_FIELDS`, `DUPLICATE_CRITERIA`, `CHOICE_FIELDS` et `IMPORT_ORDER` ; supprimer l'entrée `'SupplyNode'` d'`AT_LEAST_ONE_OF` (le dictionnaire reste, vide : `AT_LEAST_ONE_OF = {}`) ; supprimer `'supply_node': ...` et son commentaire de `MODEL_KEY_TO_SOURCE`.

Dans `imports/services/excel_parser.py` : supprimer `'supply_node': set(),` et son commentaire de `_build_db_name_cache`, ainsi que le commentaire `# SupplyNode / Exchange : ...` de `_EXISTING_KEY_QUERIES`.

Dans `imports/services/importer.py` : retirer `Exchange` et `SupplyNode` de l'import, supprimer `_import_supply_node`, `_import_exchange`, leurs entrées dans `_IMPORTERS`, et `'supply_node': {},` (avec son commentaire) de `_build_lookup`.

Dans `imports/services/excel_template.py` : supprimer la ligne `("Exchange — data_confidence", CHOICE_FIELDS['Exchange']['data_confidence']),`.

Run: `.\venv\Scripts\python.exe manage.py makemigrations dashboard --name delete_supply_graph`
Expected: `0055_delete_supply_graph.py` avec `DeleteModel` pour `Exchange` et `SupplyNode`.

- [ ] **Step 7 : adapter les tests d'import**

- `imports/tests/test_constants.py` : retirer `Exchange` de l'import, supprimer `test_exchange_data_confidence`, et remplacer `FILE_LOCAL_COLUMNS = {'SupplyNode': {'node_ref'}}` (et son commentaire) par `FILE_LOCAL_COLUMNS = {}`.
- `imports/tests/test_excel_parser.py` : supprimer la classe `ParserSupplyNodeRefTest`.
- `imports/tests/test_importer.py` : supprimer la classe `ImporterSupplyGraphTest` et retirer `Exchange`, `SupplyNode` de l'import.
- `imports/tests/test_roundtrip.py` : supprimer les appels `_fill(wb, 'SupplyNode', ...)` et `_fill(wb, 'Exchange', ...)`, les deux `assertEqual(counts['SupplyNode'|'Exchange'], ...)`, le bloc `exchange = Exchange.objects.get(...)` et ses quatre assertions, la ligne `self.assertEqual(SupplyNode.objects.filter(asset=asset).count(), 1)`, le test `test_supply_graph_idempotence_relies_on_the_importer`, et retirer `Exchange`, `SupplyNode` de l'import et des deux tuples de modèles.

- [ ] **Step 8 : lancer toute la suite**

Run: `.\venv\Scripts\python.exe -m pytest -q`
Expected: tout passe ; `git status dashboard/golden` n'affiche rien ; `Select-String -Path dashboard\*.py,dashboard\services\*.py,imports\services\*.py -Pattern 'SupplyNode|Exchange|upstream_chain'` ne renvoie rien.

- [ ] **Step 9 : commit**

```powershell
git add dashboard imports
git commit -m "refactor(flow): la carte des fournisseurs lit les flux SUPPLY" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7 : émissions déclarées → flux EMISSION de l'entreprise

La page ESG et le stress test lisent `flows.declared_emissions`, qui résout les scopes (détail prioritaire sur l'agrégat). `Carbon_emission` est supprimé. Deux bugs disparaissent : le double comptage d'un « Scope 1+2 » ajouté aux scopes détaillés sur la page ESG, et le zéro du stress test pour une entreprise qui ne déclare que « Scope 1+2 ».

**Files:**
- Modify: `dashboard/services/flows.py`, `dashboard/testing.py`
- Modify: `dashboard/views.py` (`_get_esg_carbon`), `dashboard/services/stress_test.py` (`company_snapshot`, `get_stress_test_data`)
- Modify: `dashboard/management/commands/populate_acme.py`
- Modify: `dashboard/models.py` (suppression de `Carbon_emission`) ; Create: `dashboard/migrations/0056_delete_carbon_emission.py` (générée)
- Modify: `dashboard/admin.py`, `dashboard/admin_site.py`
- Modify: `imports/services/constants.py`, `excel_parser.py`, `importer.py`
- Modify: `dashboard/tests_flow.py`, `dashboard/tests.py`, `dashboard/tests_stress_test.py`

**Interfaces:**
- Consumes: `Commodity.objects.technical('co2')` (tâche 1), `Flow`, `FlowKind`, `FlowScope` (tâche 4).
- Produces (`dashboard.services.flows`) : `resolve_scopes(values: dict[str, float]) -> dict[str, float]` ; `declared_emissions(company) -> dict[int, dict[str, float]]` (années croissantes, libellés de scope en chaînes simples).
- Produces (`dashboard.testing`) : `make_declared_emission(*, company, year, scope, value) -> Flow`.
- `company_snapshot(company, year)` renvoie en plus `scope12_combined: bool` et `unsplit_total: float` (clés internes : le JSON du stress test ne les expose pas, le golden ne bouge pas).

- [ ] **Step 1 : écrire les tests du service**

Dans `dashboard/tests_flow.py`, ajouter `SimpleTestCase` à l'import de `django.test`, remplacer l'import de `.testing` par `from .testing import make_declared_emission, make_inventory, make_production, make_supply` et ajouter :

```python
class ResolveScopesTests(SimpleTestCase):

    def test_detailed_scopes_win_over_the_aggregate(self):
        self.assertEqual(
            flow_service.resolve_scopes(
                {'Scope 1': 22.8, 'Scope 2': 7.5, 'Scope 1+2': 30.3, 'Scope 3': 584.0}),
            {'Scope 1': 22.8, 'Scope 2': 7.5, 'Scope 3': 584.0},
        )

    def test_aggregate_is_used_when_the_detail_is_missing(self):
        self.assertEqual(
            flow_service.resolve_scopes({'Scope 1+2': 32.6, 'Scope 3': 572.5}),
            {'Scope 1+2': 32.6, 'Scope 3': 572.5},
        )

    def test_unsplittable_totals_only_count_when_alone(self):
        self.assertEqual(
            flow_service.resolve_scopes({'Scope 1+2+3': 100.0, 'undefined': 5.0}),
            {'Scope 1+2+3': 100.0})
        self.assertEqual(flow_service.resolve_scopes({'undefined': 5.0}), {'undefined': 5.0})
        self.assertEqual(
            flow_service.resolve_scopes({'Scope 1': 1.0, 'undefined': 5.0}), {'Scope 1': 1.0})


class DeclaredEmissionsTests(TestCase):

    def setUp(self):
        country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private')
        self.company = Company.objects.create(name='Acme')
        self.asset = Asset.objects.create(
            name='Usine', latitude=1.0, longitude=2.0, country=country)
        Ownership.objects.create(asset=self.asset, company=self.company, share=1)

    def _declare(self, year, scope, value):
        make_declared_emission(company=self.company, year=year, scope=scope, value=value)

    def test_years_are_sorted_and_scopes_resolved(self):
        self._declare(2023, 'Scope 1+2', 10.0)
        self._declare(2022, 'Scope 1', 4.0)
        self._declare(2022, 'Scope 1+2', 9.0)
        result = flow_service.declared_emissions(self.company)
        self.assertEqual(list(result), [2022, 2023])
        self.assertEqual(result[2022], {'Scope 1': 4.0})
        self.assertEqual(result[2023], {'Scope 1+2': 10.0})

    def test_co2_measured_on_an_asset_is_not_declared(self):
        make_inventory(asset=self.asset, key='co2', year=2024, value=99.0)
        self.assertEqual(flow_service.declared_emissions(self.company), {})
```

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow.py -q`
Expected: FAIL (`cannot import name 'make_declared_emission'`).

- [ ] **Step 2 : fabrique et service**

Ajouter à `dashboard/testing.py` :

```python
def make_declared_emission(*, company, year, scope, value):
    """Émission déclarée par l'entreprise (ancien Carbon_emission)."""
    return Flow.objects.create(
        kind=FlowKind.EMISSION, what=Commodity.objects.technical('co2'),
        from_company=company, to_environment=True, scope=scope, year=year, quantity=value,
    )
```

Dans `dashboard/services/flows.py`, remplacer l'import des modèles par `from dashboard.models import Asset, Flow, FlowKind, FlowScope` et ajouter :

```python
# Libellés de scope en chaînes simples : ce sont les clés des dictionnaires
# renvoyés aux vues et sérialisés en JSON.
_SCOPE_1 = FlowScope.SCOPE_1.value
_SCOPE_2 = FlowScope.SCOPE_2.value
_SCOPE_3 = FlowScope.SCOPE_3.value
_SCOPE_1_2 = FlowScope.SCOPE_1_2.value
# Totaux impossibles à ventiler, par ordre de préférence.
_UNSPLIT_TOTALS = (FlowScope.SCOPE_1_2_3.value, FlowScope.UNDEFINED.value)


def resolve_scopes(values):
    """Scopes retenus pour une année, {scope: tCO₂e} → {scope: tCO₂e} (spec §4).

    Scopes 1 et 2 détaillés s'ils existent, sinon Scope 1+2 ; plus le Scope 3.
    Un total non ventilable (1+2+3, puis undefined) ne compte que seul.
    """
    kept = {}
    detailed = {s: values[s] for s in (_SCOPE_1, _SCOPE_2) if s in values}
    if detailed:
        kept.update(detailed)
    elif _SCOPE_1_2 in values:
        kept[_SCOPE_1_2] = values[_SCOPE_1_2]
    if _SCOPE_3 in values:
        kept[_SCOPE_3] = values[_SCOPE_3]
    if not kept:
        for scope in _UNSPLIT_TOTALS:
            if scope in values:
                kept[scope] = values[scope]
                break
    return kept


def declared_emissions(company):
    """{année: {scope: tCO₂e}} des émissions déclarées par l'entreprise, scopes
    résolus, années croissantes. Le CO₂ mesuré sur ses actifs n'y entre jamais."""
    raw = defaultdict(lambda: defaultdict(float))
    rows = Flow.objects.filter(
        kind=FlowKind.EMISSION, from_company=company, what__key='co2',
    ).order_by('year', 'pk')
    for flow in rows:
        raw[flow.year][str(flow.scope)] += flow.quantity
    return {year: resolve_scopes(dict(values)) for year, values in sorted(raw.items())}
```

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_flow.py -q`
Expected: tout passe.

- [ ] **Step 3 : écrire les tests de la page ESG et du stress test**

Dans `dashboard/tests.py`, ajouter `make_declared_emission` à l'import de `.testing`, supprimer la classe `CarbonEmissionModelTests`, et dans `EsgDataCarbonTests` :

1. remplacer le corps de `_carbon` par :

```python
        make_declared_emission(company=self.company, year=year, scope=scope, value=val)
```

2. ajouter :

```python
    def test_aggregate_scope_is_not_double_counted(self):
        from .views import _get_esg_data
        self._carbon(2022, 'Scope 1', 22.8)
        self._carbon(2022, 'Scope 2', 7.5)
        self._carbon(2022, 'Scope 1+2', 30.3)
        hist = _get_esg_data(self.company)['carbon']['historical']
        self.assertAlmostEqual(hist[0]['total'], 30.3, places=2)
        self.assertNotIn('Scope 1+2', hist[0]['scopes'])
```

Dans `dashboard/tests_stress_test.py`, ajouter `from dashboard.testing import make_declared_emission` aux imports et, en fin de fichier :

```python
class CompanySnapshotScopesTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Mine SA')

    def _declare(self, scope, value, year=2024):
        make_declared_emission(company=self.company, year=year, scope=scope, value=value)

    def test_scope_1_2_counts_when_the_detail_is_missing(self):
        self._declare('Scope 1+2', 30.0)
        snapshot = company_snapshot(self.company, 2024)
        self.assertEqual(snapshot['scope1'] + snapshot['scope2'], 30.0)
        self.assertTrue(snapshot['scope12_combined'])

    def test_the_detail_wins_over_the_aggregate(self):
        self._declare('Scope 1', 20.0)
        self._declare('Scope 2', 10.0)
        self._declare('Scope 1+2', 30.0)
        snapshot = company_snapshot(self.company, 2024)
        self.assertEqual((snapshot['scope1'], snapshot['scope2']), (20.0, 10.0))
        self.assertFalse(snapshot['scope12_combined'])

    def test_an_unsplit_total_is_reported_apart(self):
        self._declare('Scope 1+2+3', 50.0)
        snapshot = company_snapshot(self.company, 2024)
        self.assertEqual(snapshot['scope1'] + snapshot['scope2'] + snapshot['scope3'], 0.0)
        self.assertEqual(snapshot['unsplit_total'], 50.0)

    def test_an_unsplit_total_produces_its_own_warning(self):
        Company_Revenue.objects.create(
            company=self.company, year=2024, revenue=1_000_000.0, currency='EUR')
        self._declare('Scope 1+2+3', 50.0)
        warnings = get_stress_test_data(self.company)['warnings']
        self.assertTrue(any('non ventilées' in w for w in warnings), warnings)
        self.assertFalse(any("Aucune donnée d'émissions" in w for w in warnings), warnings)
```

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests.py -k EsgDataCarbon -q` puis `.\venv\Scripts\python.exe -m pytest dashboard/tests_stress_test.py -k CompanySnapshotScopes -q`
Expected: FAIL (les vues lisent encore `Carbon_emission`).

- [ ] **Step 4 : page ESG**

Dans `dashboard/views.py`, remplacer le début de `_get_esg_carbon` (de `emissions = Carbon_emission...` à la fin de la construction de `historical`) par :

```python
def _get_esg_carbon(company):
    historical = [
        {
            'year': year,
            'total': round(sum(scopes.values()), 2),
            'scopes': {scope: round(value, 2) for scope, value in scopes.items()},
        }
        for year, scopes in flow_service.declared_emissions(company).items()
    ]
```

et retirer `Carbon_emission` de l'import `from .models import (...)`.

- [ ] **Step 5 : stress test**

Dans `dashboard/services/stress_test.py` :

1. retirer `Carbon_emission` de l'import `from ..models import (...)` et remplacer `from .flows import latest_productions  # noqa: E402` par `from .flows import declared_emissions, latest_productions  # noqa: E402` ;
2. dans `company_snapshot`, remplacer

```python
    emissions = {}
    for row in Carbon_emission.objects.filter(company=company, year=year):
        normalized = row.scope.strip().lower().replace(' ', '')
        emissions[normalized] = emissions.get(normalized, 0.0) + row.carbon_emission
```

par

```python
    # Scopes déjà résolus : détail prioritaire sur l'agrégat (spec §4). Un Scope
    # 1+2 non détaillé est porté par `scope1` ; les totaux non ventilables
    # (Scope 1+2+3, undefined) restent à part.
    scopes = declared_emissions(company).get(year, {})
```

et, dans le `return`, remplacer les trois lignes `'scope1'`, `'scope2'`, `'scope3'` par :

```python
        'scope1': scopes.get('Scope 1', 0.0) + scopes.get('Scope 1+2', 0.0),
        'scope2': scopes.get('Scope 2', 0.0),
        'scope3': scopes.get('Scope 3', 0.0),
        'scope12_combined': 'Scope 1+2' in scopes,
        'unsplit_total': scopes.get('Scope 1+2+3', 0.0) + scopes.get('undefined', 0.0),
```

3. dans `get_stress_test_data`, remplacer

```python
    if snapshot['scope1'] + snapshot['scope2'] + snapshot['scope3'] == 0:
        warnings.append(
            f"Aucune donnée d'émissions pour {reference_year} : le canal "
            f"transition est nul."
        )
```

par

```python
    if snapshot['unsplit_total']:
        warnings.append(
            f"Émissions {reference_year} non ventilées par scope (Scope 1+2+3 ou "
            f"non défini) : le canal transition est nul."
        )
    elif snapshot['scope1'] + snapshot['scope2'] + snapshot['scope3'] == 0:
        warnings.append(
            f"Aucune donnée d'émissions pour {reference_year} : le canal "
            f"transition est nul."
        )
    if snapshot['scope12_combined']:
        warnings.append(
            f"Scopes 1 et 2 déclarés ensemble pour {reference_year} (Scope 1+2) : "
            f"comptés en scope 1."
        )
```

Run: les deux commandes du Step 3.
Expected: tout passe.

- [ ] **Step 6 : `populate_acme`**

Dans `populate_acme.py`, retirer `Carbon_emission` de l'import et remplacer la boucle `for yr, scope, val in carbon_rows:` par :

```python
        co2 = Commodity.objects.technical('co2')
        for yr, scope, val in carbon_rows:
            Flow.objects.get_or_create(
                kind=FlowKind.EMISSION, what=co2, from_company=acme,
                to_environment=True, scope=scope, year=yr,
                defaults={'quantity': float(val)},
            )
```

- [ ] **Step 7 : supprimer `Carbon_emission`**

Dans `dashboard/models.py`, supprimer `class Carbon_emission`. Dans `dashboard/admin.py`, retirer `Carbon_emission` de l'import et supprimer `CarbonEmissionAdmin`. Dans `dashboard/admin_site.py`, retirer `m.Carbon_emission` du groupe « Entreprises & actifs ».

Dans `imports/services/constants.py`, supprimer l'entrée `'Carbon_emission'` de `SHEET_COLUMNS`, `FK_FIELDS`, `REQUIRED_FIELDS`, `DUPLICATE_CRITERIA` et d'`IMPORT_ORDER`. Dans `excel_parser.py`, retirer `Carbon_emission` de l'import et de `_EXISTING_KEY_QUERIES`. Dans `importer.py`, retirer `Carbon_emission` de l'import, supprimer `_import_carbon_emission` et son entrée dans `_IMPORTERS`.

Dans `dashboard/tests.py`, retirer `Carbon_emission` des imports.

Run: `.\venv\Scripts\python.exe manage.py makemigrations dashboard --name delete_carbon_emission`
Expected: `0056_delete_carbon_emission.py` avec un seul `DeleteModel(name='Carbon_emission')`.

- [ ] **Step 8 : lancer toute la suite**

Run: `.\venv\Scripts\python.exe -m pytest -q`
Expected: tout passe, golden compris (Acme ne déclare que des scopes détaillés : `climate_stress_test.json` ne change pas) ; `git status dashboard/golden` n'affiche rien ; `Select-String -Path dashboard\*.py,dashboard\services\*.py,dashboard\management\commands\*.py,imports\services\*.py -Pattern 'Carbon_emission'` ne renvoie rien.

- [ ] **Step 9 : commit**

```powershell
git add dashboard imports
git commit -m "refactor(flow): émissions déclarées en flux EMISSION, scopes résolus" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8 : feuille d'import `Flow`

**Files:**
- Modify: `imports/services/constants.py`, `imports/services/excel_parser.py`, `imports/services/importer.py`, `imports/services/excel_template.py`
- Create: `imports/tests/test_flow_sheet.py`
- Modify: `imports/tests/test_constants.py`, `imports/tests/test_roundtrip.py`

**Interfaces:**
- Consumes: `FLOW_RULES`, `FlowKind`, `FlowScope`, `ENDPOINT_ENVIRONMENT`, `LOCATED_ENDPOINTS`, `SUPPLY_SELF_LOOP_MESSAGE`, `REVENUE_PRODUCTION_ONLY_MESSAGE`, `Flow.origin_type` / `destination_type` (tâche 4) ; `_ROW_CHECKS` et `context` de l'analyseur (tâche 1) ; `lookup['commodity_key']` de l'importeur (tâche 1).
- Produces (`imports.services.constants`) : `ENDPOINT_TYPES = ['asset', 'region', 'country', 'company', 'milieu']`, `ENDPOINT_TYPE_MODEL_KEYS` (type du classeur → clé du lookup), `REMOVED_SHEETS`.

- [ ] **Step 1 : écrire les tests**

Créer `imports/tests/test_flow_sheet.py` :

```python
import openpyxl
from django.test import TestCase

from dashboard.models import (
    FLOW_RULES, REVENUE_PRODUCTION_ONLY_MESSAGE, Asset, Commodity, Company, Country, Flow,
    FlowKind,
)
from imports.services.excel_parser import parse_file
from imports.services.excel_template import build_template
from imports.services.importer import save_import
from imports.tests.test_excel_parser import _make_xlsx, _sheet


class FlowSheetTests(TestCase):

    def setUp(self):
        self.brazil = Country.objects.create(
            name='Brésil', water_ownership='pub', land_ownership='priv')
        self.mine = Asset.objects.create(
            name='Mine', latitude=1.0, longitude=2.0, country=self.brazil)
        self.acme = Company.objects.create(name='Acme')
        Commodity.objects.create(name='Bœuf')

    def _row(self, **values):
        row = {
            'kind': 'SUPPLY', 'what': 'Bœuf', 'from_type': 'country', 'from_name': 'Brésil',
            'to_type': 'company', 'to_name': 'Acme', 'year': '2026', 'quantity': '1000',
        }
        row.update(values)
        return row

    def _parse(self, *rows):
        return parse_file(_make_xlsx({'Flow': _sheet('Flow', *rows)}))

    def test_one_row_of_each_kind_is_imported(self):
        parsed = self._parse(
            self._row(),
            self._row(kind='PRODUCTION', from_type='asset', from_name='Mine',
                      to_type='', to_name='', estimated_revenue='500'),
            self._row(kind='CONSUMPTION', what='water', from_type='milieu', from_name='',
                      to_type='asset', to_name='Mine'),
            self._row(kind='EMISSION', what='co2', scope='scope 1', from_type='company',
                      from_name='Acme', to_type='milieu', to_name=''),
            self._row(kind='WASTE', what='waste', from_type='asset', from_name='Mine',
                      to_type='', to_name=''),
        )
        self.assertEqual([r['status'] for r in parsed['Flow']], ['ok'] * 5)
        self.assertEqual(save_import(parsed)['Flow'], 5)
        supply = Flow.objects.get(kind=FlowKind.SUPPLY)
        self.assertEqual(
            (supply.from_country, supply.to_company, supply.quantity),
            (self.brazil, self.acme, 1000.0))
        production = Flow.objects.get(kind=FlowKind.PRODUCTION)
        self.assertEqual((production.from_asset, production.estimated_revenue), (self.mine, 500.0))
        consumption = Flow.objects.get(kind=FlowKind.CONSUMPTION)
        self.assertEqual((consumption.from_environment, consumption.what.key), (True, 'water'))
        emission = Flow.objects.get(kind=FlowKind.EMISSION)
        self.assertEqual((emission.scope, emission.to_environment), ('Scope 1', True))

    def test_lowercase_kind_is_accepted(self):
        self.assertEqual(self._parse(self._row(kind='supply'))['Flow'][0]['status'], 'ok')

    def test_unknown_commodity_is_error(self):
        row = self._parse(self._row(what='Licorne'))['Flow'][0]
        self.assertEqual(row['status'], 'error')
        self.assertIn('what', row['message'])

    def test_name_next_to_milieu_is_error(self):
        row = self._parse(self._row(
            kind='EMISSION', what='co2', from_type='company', from_name='Acme',
            to_type='milieu', to_name='Océan'))['Flow'][0]
        self.assertEqual(row['status'], 'error')
        self.assertIn('to_name', row['message'])

    def test_unknown_endpoint_name_is_error(self):
        row = self._parse(self._row(from_name='Atlantide'))['Flow'][0]
        self.assertEqual(row['status'], 'error')
        self.assertIn('from_name', row['message'])

    def test_rule_violation_uses_the_model_message(self):
        row = self._parse(self._row(
            kind='EMISSION', what='co2', from_type='company', from_name='Acme',
            to_type='', to_name=''))['Flow'][0]
        self.assertEqual(row['status'], 'error')
        self.assertEqual(row['message'], FLOW_RULES['EMISSION'].message)

    def test_revenue_outside_production_is_error(self):
        row = self._parse(self._row(estimated_revenue='10'))['Flow'][0]
        self.assertEqual(row['message'], REVENUE_PRODUCTION_ONLY_MESSAGE)

    def test_existing_flow_is_duplicate_even_when_what_is_given_by_key(self):
        Flow.objects.create(
            kind=FlowKind.EMISSION, what=Commodity.objects.technical('co2'),
            from_company=self.acme, to_environment=True, year=2024, quantity=1.0)
        row = self._parse(self._row(
            kind='EMISSION', what='CO2', from_type='company', from_name='Acme',
            to_type='milieu', to_name='', year='2024'))['Flow'][0]
        self.assertEqual(row['status'], 'duplicate')

    def test_removed_sheet_is_reported(self):
        parsed = parse_file(_make_xlsx({'Production': [['asset_name'], ['Mine']]}))
        self.assertEqual(parsed['Production'][0]['status'], 'error')
        self.assertIn('Flow', parsed['Production'][0]['message'])

    def test_reference_sheet_lists_units_keys_and_endpoint_types(self):
        ws = openpyxl.load_workbook(build_template())['_Référence']
        values = {cell.value for row in ws.iter_rows() for cell in row}
        self.assertIn('CO₂ — tCO₂e — co2', values)
        self.assertIn('milieu', values)
```

Dans `imports/tests/test_constants.py`, ajouter `Flow` et `LOCATED_ENDPOINTS` à l'import de `dashboard.models`, ajouter `ENDPOINT_TYPES` à l'import de `imports.services.constants`, remplacer `FILE_LOCAL_COLUMNS = {}` par :

```python
    # Colonnes volontairement sans champ : la feuille Flow décrit chaque extrémité
    # par un type et un nom, traduits vers les clés étrangères à l'import.
    FILE_LOCAL_COLUMNS = {'Flow': {'from_type', 'from_name', 'to_type', 'to_name'}}
```

et ajouter à `ChoiceFieldsMatchModelTest` :

```python
    def test_flow_kind(self):
        self.assertEqual(CHOICE_FIELDS['Flow']['kind'], _model_choice_values(Flow, 'kind'))

    def test_flow_scope(self):
        self.assertEqual(CHOICE_FIELDS['Flow']['scope'], _model_choice_values(Flow, 'scope'))

    def test_endpoint_types_cover_the_model(self):
        self.assertEqual(
            [t for t in ENDPOINT_TYPES if t != 'milieu'], list(LOCATED_ENDPOINTS))
```

Run: `.\venv\Scripts\python.exe -m pytest imports/tests/test_flow_sheet.py imports/tests/test_constants.py -q`
Expected: FAIL (feuille `Flow` inconnue).

- [ ] **Step 2 : constantes**

Dans `imports/services/constants.py` :

1. Ajouter à `SHEET_COLUMNS`, juste après l'entrée `'Asset'` :

```python
    # Flux : une quantité d'une commodité, une année, d'une origine vers une
    # destination. from_type / to_type : asset, region, country, company, milieu,
    # ou vide (inconnu) ; *_name reste vide pour milieu et inconnu. `what` accepte
    # le nom ou la clé technique de la commodité.
    'Flow': [
        'kind', 'what', 'scope', 'from_type', 'from_name', 'to_type', 'to_name',
        'year', 'quantity', 'tier', 'estimated_revenue', 'source', 'reference',
    ],
```

2. Ajouter `'Flow': ['kind', 'what', 'year', 'quantity'],` à `REQUIRED_FIELDS` et `'Flow': ['kind', 'what', 'scope', 'from_type', 'from_name', 'to_type', 'to_name', 'year'],` à `DUPLICATE_CRITERIA`.
3. Ajouter, juste avant `CHOICE_FIELDS` :

```python
# Types d'extrémité de la feuille Flow. Les quatre premiers reprennent les
# constantes ENDPOINT_* du modèle ; 'milieu' correspond à ENDPOINT_ENVIRONMENT.
ENDPOINT_TYPES = ['asset', 'region', 'country', 'company', 'milieu']

# Type d'extrémité → clé du dictionnaire de résolution des noms (lookup).
ENDPOINT_TYPE_MODEL_KEYS = {
    'asset': 'asset',
    'region': 'subnational_region',
    'country': 'country',
    'company': 'company',
}

# Feuilles remplacées par Flow (spec 2026-09-18 §6.1) : un classeur qui les
# contient encore reçoit une erreur explicite au lieu d'être ignoré.
REMOVED_SHEETS = ['Production', 'AssetInventory', 'SupplyNode', 'Exchange', 'Carbon_emission']
```

4. Ajouter à `CHOICE_FIELDS` :

```python
    'Flow': {
        'kind': ['PRODUCTION', 'SUPPLY', 'CONSUMPTION', 'EMISSION', 'WASTE'],
        'scope': ['Scope 1', 'Scope 2', 'Scope 3', 'Scope 1+2', 'Scope 1+2+3', 'undefined'],
        'from_type': ENDPOINT_TYPES,
        'to_type': ENDPOINT_TYPES,
    },
```

5. Dans `IMPORT_ORDER`, insérer `'Flow'` juste après `'Asset'`.

- [ ] **Step 3 : analyseur**

Dans `imports/services/excel_parser.py` :

1. Compléter l'import de `dashboard.models` avec `ENDPOINT_ENVIRONMENT, FLOW_RULES, REVENUE_PRODUCTION_ONLY_MESSAGE, SUPPLY_SELF_LOOP_MESSAGE, Flow, FlowKind`, et celui de `.constants` avec `ENDPOINT_TYPE_MODEL_KEYS, REMOVED_SHEETS`.
2. Remplacer le corps de `parse_file` par :

```python
    wb = openpyxl.load_workbook(source)
    file_names = _collect_file_names(wb)
    db_name_cache = _build_db_name_cache()
    context = _build_row_check_context(wb, file_names, db_name_cache)

    result = {}
    for sheet_name in REMOVED_SHEETS:
        if sheet_name in wb.sheetnames:
            result[sheet_name] = [{
                'status': 'error',
                'message': (
                    f"La feuille {sheet_name} n'existe plus : utilisez la feuille Flow."
                ),
                'data': {},
            }]
    for sheet_name in SHEET_COLUMNS:
        if sheet_name not in wb.sheetnames:
            continue
        rows = _parse_sheet(wb[sheet_name], sheet_name, file_names, db_name_cache, context)
        sheet_check = _SHEET_CHECKS.get(sheet_name)
        if sheet_check:
            sheet_check(rows)
        result[sheet_name] = rows
    return result
```

3. Remplacer `_build_row_check_context` par :

```python
def _sheet_values(wb, sheet_name, columns):
    """Valeurs texte des colonnes demandées d'une feuille, une tuple par ligne."""
    if sheet_name not in wb.sheetnames:
        return []
    ws = wb[sheet_name]
    header = [c.value for c in ws[1]]
    indexes = [header.index(c) if c in header else None for c in columns]
    values = []
    for row in ws.iter_rows(min_row=2):
        values.append(tuple(
            str(row[i].value).strip()
            if i is not None and i < len(row) and row[i].value is not None else ''
            for i in indexes
        ))
    return values


def _build_row_check_context(wb, file_names, db_name_cache):
    """État partagé par les contrôles propres à une feuille (voir _ROW_CHECKS)
    pendant toute l'analyse d'un classeur."""
    commodity_names = {}  # nom ou clé, en minuscules -> nom de la commodité
    for name, key in Commodity.objects.values_list('name', 'key'):
        commodity_names[name.lower()] = name.lower()
        if key:
            commodity_names[key.lower()] = name.lower()
    for name, key in _sheet_values(wb, 'Commodity', ('name', 'key')):
        if name:
            commodity_names.setdefault(name.lower(), name.lower())
            if key:
                commodity_names.setdefault(key.lower(), name.lower())
    return {
        'file_names': file_names,
        'db_name_cache': db_name_cache,
        'commodity_names': commodity_names,
        'commodity_key_owner': {
            key.lower(): name.lower()
            for name, key in Commodity.objects.exclude(key=None).values_list('name', 'key')
        },
        'file_commodity_key_owner': {},
    }
```

4. Ajouter, juste avant `_ROW_CHECKS` :

```python
def _sheet_endpoint(value):
    """Type d'extrémité du classeur → type du modèle ('milieu' → environment,
    vide → None)."""
    value = (value or '').strip().lower()
    if not value:
        return None
    return ENDPOINT_ENVIRONMENT if value == 'milieu' else value


def _flow_row_error(data, context):
    """Contrôles de la feuille Flow (spec §6.1) : commodité, extrémités, puis
    règles FLOW_RULES avec le message même de la contrainte en base."""
    if data['what'].strip().lower() not in context['commodity_names']:
        return f"Commodité introuvable pour 'what' : '{data['what']}' (nom ou clé)"
    for side in ('from', 'to'):
        endpoint_type = data.get(f'{side}_type', '').strip().lower()
        name = data.get(f'{side}_name', '').strip()
        if endpoint_type in ('', 'milieu'):
            if name:
                shown = endpoint_type or 'vide'
                return f"'{side}_name' doit rester vide quand '{side}_type' vaut « {shown} »"
            continue
        if not name:
            return f"'{side}_name' est obligatoire quand '{side}_type' vaut « {endpoint_type} »"
        model_key = ENDPOINT_TYPE_MODEL_KEYS[endpoint_type]
        if not _can_resolve(model_key, name, context['file_names'], context['db_name_cache']):
            return f"Valeur introuvable pour '{side}_name' : '{name}'"
    kind = data['kind'].strip().upper()
    rule = FLOW_RULES[kind]
    origin = _sheet_endpoint(data.get('from_type'))
    destination = _sheet_endpoint(data.get('to_type'))
    if origin not in rule.origins or destination not in rule.destinations:
        return rule.message
    same_place = (
        origin is not None and origin == destination
        and data['from_name'].strip().lower() == data['to_name'].strip().lower()
    )
    if kind == FlowKind.SUPPLY.value and same_place:
        return SUPPLY_SELF_LOOP_MESSAGE
    if data.get('estimated_revenue') and kind != FlowKind.PRODUCTION.value:
        return REVENUE_PRODUCTION_ONLY_MESSAGE
    return None


def _flow_duplicate_key(data, context):
    """Clé de doublon normalisée : `what` ramené au nom de la commodité, scope
    vide = 'undefined'."""
    what = data['what'].strip().lower()
    return (
        data['kind'].strip().lower(),
        context['commodity_names'].get(what, what),
        (data.get('scope') or 'undefined').strip().lower(),
        data.get('from_type', '').strip().lower(),
        data.get('from_name', '').strip().lower(),
        data.get('to_type', '').strip().lower(),
        data.get('to_name', '').strip().lower(),
        data.get('year', '').strip(),
    )


def _flow_end(flow, side):
    """(type du classeur, nom en minuscules) d'une extrémité d'un Flow en base."""
    endpoint = flow.origin_type if side == 'from' else flow.destination_type
    if endpoint is None:
        return '', ''
    if endpoint == ENDPOINT_ENVIRONMENT:
        return 'milieu', ''
    return endpoint, getattr(flow, f'{side}_{endpoint}').name.lower()


def _existing_flow_keys():
    keys = set()
    rows = Flow.objects.select_related(
        'what', 'from_asset', 'from_region', 'from_country', 'from_company',
        'to_asset', 'to_region', 'to_country', 'to_company',
    )
    for flow in rows:
        keys.add((
            flow.kind.lower(), flow.what.name.lower(), flow.scope.lower(),
            *_flow_end(flow, 'from'), *_flow_end(flow, 'to'), str(flow.year),
        ))
    return keys
```

5. Ajouter `'Flow': _flow_row_error,` à `_ROW_CHECKS` et, juste après `_ROW_CHECKS` :

```python
# Feuilles dont la clé de doublon demande une normalisation : (clé du fichier,
# clés existantes en base).
_DUPLICATE_KEYS = {
    'Flow': (_flow_duplicate_key, _existing_flow_keys),
}
```

6. Dans `_existing_keys(sheet_name)`, ajouter en première ligne du corps :

```python
    if sheet_name in _DUPLICATE_KEYS:
        return _DUPLICATE_KEYS[sheet_name][1]()
```

7. Dans `_parse_sheet`, remplacer la ligne `key = tuple(data.get(f, '').strip().lower() for f in dup_criteria)` par :

```python
        if sheet_name in _DUPLICATE_KEYS:
            key = _DUPLICATE_KEYS[sheet_name][0](data, context)
        else:
            key = tuple(data.get(f, '').strip().lower() for f in dup_criteria)
```

- [ ] **Step 4 : importeur**

Dans `imports/services/importer.py`, ajouter `Flow, FlowScope` à l'import de `dashboard.models` et `ENDPOINT_TYPE_MODEL_KEYS` à celui de `.constants`, puis ajouter avant `_IMPORTERS` :

```python
# 'scope 1' → 'Scope 1' : le classeur accepte n'importe quelle casse.
_SCOPES = {scope.lower(): scope for scope in FlowScope.values}


def _endpoint_kwargs(side, d, lookup):
    """Champs d'une extrémité de Flow : {} si vide, None si le nom est introuvable."""
    endpoint_type = (d.get(f'{side}_type') or '').strip().lower()
    if endpoint_type == 'milieu':
        return {f'{side}_environment': True}
    if not endpoint_type:
        return {}
    target = _get(lookup, ENDPOINT_TYPE_MODEL_KEYS[endpoint_type], d.get(f'{side}_name', ''))
    return {f'{side}_{endpoint_type}': target} if target else None


def _import_flow(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        alias = d['what'].strip().lower()
        what = lookup['commodity'].get(alias) or lookup['commodity_key'].get(alias)
        origin = _endpoint_kwargs('from', d, lookup)
        destination = _endpoint_kwargs('to', d, lookup)
        if what is None or origin is None or destination is None:
            continue
        revenue = d.get('estimated_revenue')
        Flow.objects.create(
            kind=d['kind'].strip().upper(),
            what=what,
            scope=_SCOPES.get((d.get('scope') or '').strip().lower(), FlowScope.UNDEFINED),
            year=_i(d.get('year')),
            quantity=_f(d.get('quantity')),
            tier=_tier(d.get('tier')),
            estimated_revenue=_f(revenue) if revenue else None,
            source=_s(d.get('source')),
            reference=_s(d.get('reference')),
            **origin, **destination,
        )
        created += 1
    return created
```

et ajouter `'Flow': _import_flow,` à `_IMPORTERS`, juste après `'Asset': _import_asset,`.

- [ ] **Step 5 : modèle Excel**

Dans `imports/services/excel_template.py`, ajouter `ENDPOINT_TYPES` à l'import de `.constants`, puis :

1. ajouter avant `_build_reference_sheet` :

```python
def _commodity_label(commodity):
    """« CO₂ — tCO₂e — co2 » : nom, unité et, s'il y en a une, clé technique."""
    parts = [commodity.name, commodity.unit]
    if commodity.key:
        parts.append(commodity.key)
    return ' — '.join(parts)
```

2. dans `db_sections`, remplacer `('Commodities', Commodity.objects.values_list('name', flat=True)),` par :

```python
        ('Commodities (nom — unité — clé)',
         [_commodity_label(c) for c in Commodity.objects.order_by('name')]),
```

3. ajouter en tête de `enum_sections` :

```python
        ("Flow — kind", CHOICE_FIELDS['Flow']['kind']),
        ("Flow — scope (vide = undefined)", CHOICE_FIELDS['Flow']['scope']),
        ("Flow — from_type / to_type (vide = inconnu)", ENDPOINT_TYPES),
```

- [ ] **Step 6 : aller-retour complet**

Dans `imports/tests/test_roundtrip.py`, ajouter `Flow` à l'import de `dashboard.models`, puis dans `setUp`, juste après `_fill(wb, 'Asset', {...})` :

```python
        _fill(wb, 'Flow',
              {'kind': 'PRODUCTION', 'what': 'Testsoja', 'from_type': 'asset',
               'from_name': 'Testusine', 'year': 2024, 'quantity': 1000, 'tier': 0,
               'estimated_revenue': 250000},
              {'kind': 'SUPPLY', 'what': 'Testsoja', 'from_type': 'country',
               'from_name': 'Testland', 'to_type': 'asset', 'to_name': 'Testusine',
               'year': 2024, 'quantity': 800, 'tier': 1},
              {'kind': 'CONSUMPTION', 'what': 'water', 'from_type': 'milieu',
               'to_type': 'asset', 'to_name': 'Testusine', 'year': 2024,
               'quantity': 4200, 'source': 'compteur'})
```

Dans `test_import_persists_the_whole_workbook`, ajouter après les assertions sur `asset` :

```python
        self.assertEqual(counts['Flow'], 3)
        supply = Flow.objects.get(kind='SUPPLY')
        self.assertEqual((supply.from_country.name, supply.to_asset), ('Testland', asset))
        self.assertEqual(supply.tier, 1)
        water = Flow.objects.get(kind='CONSUMPTION')
        self.assertTrue(water.from_environment)
        self.assertAlmostEqual(water.quantity, 4200.0)
```

et ajouter `Flow` aux deux tuples de modèles de `test_reuploading_the_same_workbook_creates_nothing_new`.

- [ ] **Step 7 : lancer toute la suite**

Run: `.\venv\Scripts\python.exe -m pytest -q`
Expected: tout passe.

- [ ] **Step 8 : commit**

```powershell
git add imports
git commit -m "feat(imports): feuille Flow et erreur explicite pour les feuilles supprimées" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9 : sauvegarde avant migration et documentation

**Files:**
- Create: `dashboard/management/commands/backup_sqlite.py`, `dashboard/tests_backup.py`
- Modify: `.cpanel.yml`, `.gitignore`, `docs/deploiement-production.md`, `CLAUDE.md`

**Interfaces:**
- Produces: commande `python manage.py backup_sqlite [--source CHEMIN]` : copie cohérente de la base SQLite (API `backup` du module `sqlite3`) vers `<fichier>.pre-deploy`, écrasée à chaque appel. Sans `--source`, elle lit la base Django et ne fait rien si celle-ci n'est pas SQLite ; si le fichier source n'existe pas, elle ne fait rien.

- [ ] **Step 1 : écrire les tests**

Créer `dashboard/tests_backup.py` :

```python
"""Sauvegarde SQLite lancée par .cpanel.yml avant migrate (spec 2026-09-18 §9)."""
import io
import sqlite3
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase


class BackupSqliteCommandTests(SimpleTestCase):

    def test_copies_the_database_next_to_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'db.sqlite3'
            connection = sqlite3.connect(source)
            connection.execute('CREATE TABLE t (x INTEGER)')
            connection.execute('INSERT INTO t VALUES (42)')
            connection.commit()
            connection.close()

            call_command('backup_sqlite', source=str(source), stdout=io.StringIO())

            backup = sqlite3.connect(Path(tmp) / 'db.sqlite3.pre-deploy')
            value = backup.execute('SELECT x FROM t').fetchone()[0]
            backup.close()
            self.assertEqual(value, 42)

    def test_a_missing_database_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            call_command('backup_sqlite', source=str(Path(tmp) / 'absente.sqlite3'), stdout=out)
            self.assertIn('aucune sauvegarde', out.getvalue())
            self.assertEqual(list(Path(tmp).iterdir()), [])
```

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_backup.py -q`
Expected: FAIL (`Unknown command: 'backup_sqlite'`).

- [ ] **Step 2 : écrire la commande**

Créer `dashboard/management/commands/backup_sqlite.py` :

```python
"""Sauvegarde cohérente de la base SQLite avant une migration (spec 2026-09-18 §9)."""
import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = (
        "Copie la base SQLite dans <fichier>.pre-deploy avec l'API backup de sqlite3 "
        '(cohérente en mode WAL, contrairement à une copie de fichier). Écrase la '
        'sauvegarde précédente. Lancée par .cpanel.yml avant migrate.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--source', help='Fichier SQLite à sauvegarder (défaut : base Django).')

    def handle(self, *args, **options):
        source = options['source']
        if source is None:
            if connection.vendor != 'sqlite':
                self.stdout.write('Base non SQLite : aucune sauvegarde.')
                return
            source = connection.settings_dict['NAME']
        source = Path(source)
        if not source.is_file():
            self.stdout.write(f'{source} introuvable : aucune sauvegarde.')
            return
        target = source.with_name(f'{source.name}.pre-deploy')
        src = sqlite3.connect(source)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        self.stdout.write(f'Sauvegarde écrite : {target}')
```

Run: `.\venv\Scripts\python.exe -m pytest dashboard/tests_backup.py -q`
Expected: 2 passed.

- [ ] **Step 3 : brancher la commande sur le déploiement (configuration de production)**

Dans `.cpanel.yml`, insérer juste avant la ligne `- $VENV/python manage.py migrate --noinput` :

```yaml
    - $VENV/python manage.py backup_sqlite
```

Dans `.gitignore`, ajouter sous `*.sqlite3_init` :

```
*.sqlite3.pre-deploy
```

Sans cette ligne, la sauvegarde apparaîtrait comme fichier non suivi dans le dépôt du serveur, ce qui bloque le déploiement suivant (`docs/deploiement-production.md` §5).

- [ ] **Step 4 : documentation de déploiement**

Dans `docs/deploiement-production.md` :

1. §5, dans la phrase « Le déploiement est piloté par `.cpanel.yml` (…) », ajouter `backup_sqlite` en tête de la liste entre parenthèses, avant `migrate`.
2. Remplacer tout le §6 par :

```markdown
## 6. Migrations futures

Après transfert du code, `.cpanel.yml` lance d'abord `python manage.py
backup_sqlite`, qui écrit une copie cohérente de la base dans
`db.sqlite3.pre-deploy` (API `backup` de SQLite, sûre en mode WAL), puis
`migrate`. Ce fichier est écrasé à chaque déploiement : il ne protège que le
dernier. Il est ignoré par git (`*.sqlite3.pre-deploy`), il ne bloque donc pas
les déploiements suivants.

Retour arrière après une migration ratée : revenir au commit précédent, arrêter
l'application, remplacer `db.sqlite3` par `db.sqlite3.pre-deploy` et supprimer
`db.sqlite3-wal` et `db.sqlite3-shm`, puis redémarrer (`touch tmp/restart.txt`).

### Refonte de la table Flow (septembre 2026)

Le déploiement de `feat/table-flow` supprime, sans les recopier, les données de
`Production`, `AssetInventory`, `SupplyNode`, `Exchange`, `Carbon_emission` et
`Ownership` (spec `docs/superpowers/specs/2026-09-18-table-flow-unique-design.md`,
décision 2).

1. Déployer à un moment calme : Git Version Control → Update from Remote.
2. Vérifier dans le journal de déploiement la ligne `Sauvegarde écrite :`.
3. Télécharger le nouveau modèle Excel depuis `/imports/`, remplir les feuilles
   `Ownership` et `Flow` (et `Commodity` si besoin), puis importer.

Entre les étapes 1 et 3, les pages affichent des entreprises sans production ni
émission.
```

- [ ] **Step 5 : `CLAUDE.md`**

1. §2, remplacer la ligne du tableau `| Base de données    | **SQLite** en dev → migration **PostgreSQL + PostGIS** en prod         |` par :

```markdown
| Base de données    | **SQLite** en dev **et en prod** (o2switch, voir `docs/deploiement-production.md`) ; code gardé compatible PostgreSQL |
```

2. §4, remplacer `(~33 modèles)` par `(~28 modèles)`.
3. §4, dans la puce `Asset`, remplacer la phrase « Le lien Asset ↔ Company passe par `Ownership`. » par :

```markdown
  Le lien Asset ↔ Company passe par `Ownership` : part décimale (`share`, entre 0
  et 1) et années de validité (`start_year`, `end_year`). Lire le périmètre d'une
  entreprise avec `Asset.objects.owned_by(company, year=None)`.
```

4. §4 « Activité et finance », remplacer la puce `Production` (deux lignes) par :

```markdown
- `Flow` : table unique des flux (spec
  `docs/superpowers/specs/2026-09-18-table-flow-unique-design.md`). Une ligne = une
  quantité d'une commodité (`what`), une année, d'une origine (`from_*`) vers une
  destination (`to_*`) : actif, région, pays, entreprise, milieu
  (`*_environment`) ou vide (inconnu). `kind` : PRODUCTION, SUPPLY, CONSUMPTION,
  EMISSION, WASTE ; les extrémités autorisées par nature sont dans `FLOW_RULES`,
  qui génère les contraintes en base. Lecture **uniquement** via
  `dashboard/services/flows.py`.
```

5. §4, remplacer la puce « `ESG_data`, `Carbon_emission` : indicateurs extra-financiers par entreprise. » par :

```markdown
- `ESG_data` : indicateurs extra-financiers par entreprise. Les émissions déclarées
  sont des flux EMISSION de l'entreprise vers le milieu, avec leur `scope`.
```

6. §4 « Impacts », remplacer les deux puces `Flow` + `AssetInventory` et `SupplyNode` + `Exchange` par :

```markdown
- Inventaire mesuré (eau, énergie, CO₂, déchets, surface) et approvisionnement :
  flux `Flow` (CONSUMPTION, EMISSION, WASTE, SUPPLY). Les commodités techniques
  lues par le code ont une `Commodity.key` (`TECHNICAL_COMMODITIES`).
```

7. §4 « Conventions » :
   - dans la liste des modèles qui ont `created_at` / `updated_at`, remplacer `SupplyNode` et `Exchange` par `Flow` et `Ownership` ;
   - dans la liste des modèles qui ont `created_by`, remplacer `Exchange` par `Flow`, `Ownership` ;
   - dans les exemples de nommage historique, remplacer « `Ownership.Asset` en capitale » par `Policy_Level`.

Garder la largeur de ligne du fichier (environ 85 caractères).

- [ ] **Step 6 : commit**

```powershell
git add dashboard/management/commands/backup_sqlite.py dashboard/tests_backup.py .cpanel.yml .gitignore docs/deploiement-production.md CLAUDE.md
git commit -m "chore(deploy): sauvegarde SQLite avant migrate et documentation de la table Flow" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10 : vérification finale

**Files:** aucun, sauf correction d'un écart trouvé ici.

- [ ] **Step 1 : aucune migration en attente**

Run: `.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run`
Expected: `No changes detected`.

- [ ] **Step 2 : suite complète et couverture**

Run: `.\venv\Scripts\python.exe -m pytest --cov -q`
Expected: tout passe ; la couverture totale reste ≥ 70 % ; `dashboard/services/flows.py` est couvert à plus de 90 %.

- [ ] **Step 3 : golden intacts**

Run: `git diff --stat main -- dashboard/golden`
Expected: aucune sortie.

- [ ] **Step 4 : plus de référence aux anciens modèles**

Run: `git grep -n -E "\b(Production|AssetInventory|SupplyNode|Exchange|Carbon_emission)\b|ownership__|production_set|upstream_chain" -- "*.py" ":!dashboard/migrations"`
Expected: seulement des libellés texte (par exemple `'Production'` dans `FlowKind`, `REMOVED_SHEETS`, un message d'erreur) ; aucune classe, requête ou import. Corriger toute autre occurrence.

- [ ] **Step 5 : essai sur une copie de la base locale**

```powershell
Copy-Item db.sqlite3 "$env:TEMP\easybiodiv-avant-flow.sqlite3"
.\venv\Scripts\python.exe manage.py backup_sqlite
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py populate_acme
.\venv\Scripts\python.exe manage.py runserver
```

Expected: `migrate` applique 0049 à 0056 sans erreur ; `populate_acme` réussit. Ouvrir la vue d'ensemble, Mesure d'empreinte, LEAP (Locate, Evaluate, Prepare), Dépendances, Risque physique, Dette écologique, Comparaison, ESG, Stress test et l'import (`/imports/`, télécharger le modèle) pour Acme Corp : aucune erreur 500. Dans la console d'administration, créer un flux EMISSION sans destination : le formulaire affiche « Une émission part d'un actif ou d'une entreprise et va vers le milieu. ». Arrêter le serveur ; la base locale d'avant la refonte reste disponible dans `%TEMP%\easybiodiv-avant-flow.sqlite3`.

- [ ] **Step 6 : rendre compte**

Résumer à l'utilisateur : commits de la branche, résultat des tests et de la couverture, écarts éventuels avec la spec. Ne pas fusionner ni pousser sans son accord.

