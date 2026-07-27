# Plan C — Inventaire mesuré (Flow / AssetInventory) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le modèle `Asset_consumption` (colonnes figées, sans année) par un inventaire mesuré générique `AssetInventory` (asset × `Flow` × année), et exposer un service `measured_vs_modeled` qui conserve EN PARALLÈLE la mesure terrain et l'impact ACV modélisé — sans changer la forme JSON de sortie des vues.

**Architecture:** `Flow` est un catalogue de flux physiques mesurés (eau, énergie, CO₂, déchets, surface), apparié aux `ImpactCategory` par un slug `theme`. `AssetInventory(asset, flow, year, value)` généralise `Asset_consumption`. Un service `measured_vs_modeled(asset, theme, year)` renvoie la mesure (inventaire) ET l'impact modélisé (production × CF) pour un même thème. La vue `leap_evaluate` lit son bloc consommation depuis `AssetInventory`.

**Tech Stack:** Django 5 (TestCase), SQLite. Aucune dépendance nouvelle.

## Global Constraints

- Python **3.11+**, PEP 8, lignes **≤ 100 caractères**.
- **Aucune** dépendance nouvelle. **Compatible SQLite** (`FloatField`/`FK`/`CharField`/`IntegerField`/`DateTime`). Pas de PostGIS, pas de `JSONField` Postgres-only.
- On **reste dans l'app `dashboard`** (sauf le nécessaire dans `imports`).
- **La forme JSON de sortie de `leap_evaluate` reste identique** (golden). Acme n'a aucune donnée de consommation → la partie consommation reste à 0, invariante.
- **Une migration = un changement logique** ; migrations réversibles et **auto-suffisantes** (helpers figés, pas d'import de constante vivante — leçon Plans A/B).
- Commande de test : `.venv\Scripts\python.exe manage.py test dashboard` ; suite projet : `.venv\Scripts\python.exe manage.py test`.
- Ne redirige jamais la sortie des tests vers un fichier du repo.
- Dernière migration existante : `0035_tier_max_validator` → les nouvelles s'enchaînent à partir de `0036`.

## File Structure

- `dashboard/models.py` — ajoute `Flow`, `AssetInventory` (fin de fichier) ; retire `Asset_consumption` (Task 9).
- `dashboard/services/impacts.py` — ajoute `measured_vs_modeled(asset, theme, year)`.
- `dashboard/migrations/0036..0040` + helpers figés `_seed_flows.py`, `_asset_consumption_to_inventory.py`.
- `dashboard/views.py` — bascule le bloc consommation de `_get_leap_evaluate_data` sur `AssetInventory`.
- `dashboard/tests.py` — tests modèles + service ; adapte `LeapEvaluateDataTests` (Asset_consumption → AssetInventory).
- `dashboard/admin.py` — enregistre `Flow`/`AssetInventory`, retire `Asset_consumption` (Task 9).
- `imports/services/importer.py` + `imports/services/constants.py` — `_import_asset_consumption` crée des `AssetInventory` (feuille + colonne `year`).

**Contrat clé :** `Flow.theme` == `ImpactCategory.theme` (slugs `water`/`carbon`/`land`…) → `measured_vs_modeled` apparie les deux chemins. Acme n'a pas d'inventaire → `leap_evaluate` golden invariant.

---

### Task 1 : Modèle `Flow`

**Files:**
- Modify: `dashboard/models.py` (fin de fichier)
- Create: `dashboard/migrations/0036_flow.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces: `Flow(key [unique], name, unit, theme)`.

- [ ] **Step 1 : Écrire le test**

```python
class FlowModelTests(TestCase):

    def test_create_and_str(self):
        from .models import Flow
        f = Flow.objects.create(key='water', name='Consommation eau', unit='m³',
                                theme='water')
        self.assertEqual(str(f), 'water')
        self.assertEqual(f.theme, 'water')

    def test_key_unique(self):
        from django.db import IntegrityError, transaction
        from .models import Flow
        Flow.objects.create(key='co2', name='CO2', unit='t')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Flow.objects.create(key='co2', name='CO2 bis', unit='t')
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.FlowModelTests`
Expected : FAIL (`cannot import name 'Flow'`).

- [ ] **Step 3 : Ajouter le modèle**

À la fin de `dashboard/models.py` :
```python
class Flow(models.Model):
    """Flux physique mesuré (inventaire) ; `theme` l'apparie aux ImpactCategory."""
    key = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=50, blank=True)
    theme = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return self.key
```

- [ ] **Step 4 : Générer la migration**

Run : `.venv\Scripts\python.exe manage.py makemigrations dashboard --name flow`
Expected : `0036_flow.py`.

- [ ] **Step 5 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.FlowModelTests`
Expected : PASS.

- [ ] **Step 6 : Commit**

```bash
git add dashboard/models.py dashboard/migrations/0036_flow.py dashboard/tests.py
git commit -m "feat(models): Flow (catalogue de flux mesurés)"
```

---

### Task 2 : Data migration — seed des `Flow`

**Files:**
- Create: `dashboard/migrations/0037_seed_flows.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces (en base) : 5 `Flow` (`water`, `energy`, `co2`, `waste`, `surface_area`) avec `theme`.

- [ ] **Step 1 : Écrire le test**

```python
class SeedFlowsTests(TestCase):

    def test_five_flows_seeded(self):
        from .models import Flow
        keys = set(Flow.objects.values_list('key', flat=True))
        self.assertEqual(keys, {'water', 'energy', 'co2', 'waste', 'surface_area'})

    def test_themes(self):
        from .models import Flow
        self.assertEqual(Flow.objects.get(key='water').theme, 'water')
        self.assertEqual(Flow.objects.get(key='co2').theme, 'carbon')
        self.assertEqual(Flow.objects.get(key='surface_area').theme, 'land')
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.SeedFlowsTests`
Expected : FAIL (0 Flow).

- [ ] **Step 3 : Créer la data migration**

Créer `dashboard/migrations/0037_seed_flows.py` :
```python
from django.db import migrations

# (key, name, unit, theme)
FLOWS = [
    ('water', 'Consommation eau', 'm³', 'water'),
    ('energy', 'Consommation énergie', 'MWh', 'energy'),
    ('co2', 'Émissions CO₂', 'tCO₂e', 'carbon'),
    ('waste', 'Déchets générés', 't', 'waste'),
    ('surface_area', 'Surface', 'm²', 'land'),
]


def seed(apps, schema_editor):
    Flow = apps.get_model('dashboard', 'Flow')
    for key, name, unit, theme in FLOWS:
        Flow.objects.get_or_create(
            key=key, defaults={'name': name, 'unit': unit, 'theme': theme}
        )


def unseed(apps, schema_editor):
    Flow = apps.get_model('dashboard', 'Flow')
    Flow.objects.filter(key__in=[f[0] for f in FLOWS]).delete()


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0036_flow')]
    operations = [migrations.RunPython(seed, unseed)]
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.SeedFlowsTests`
Expected : PASS.

- [ ] **Step 5 : Commit**

```bash
git add dashboard/migrations/0037_seed_flows.py dashboard/tests.py
git commit -m "feat(migration): seed des Flow (eau/énergie/CO2/déchets/surface)"
```

---

### Task 3 : Modèle `AssetInventory`

**Files:**
- Modify: `dashboard/models.py` (après `Flow`)
- Create: `dashboard/migrations/0038_assetinventory.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces: `AssetInventory(asset, flow, year, value, source, reference)` ; `unique_together (asset, flow, year)`.

- [ ] **Step 1 : Écrire le test**

```python
class AssetInventoryModelTests(TestCase):

    def _asset(self):
        from .models import Asset, Country
        c = Country.objects.create(name='FR', water_ownership='X', land_ownership='Y')
        return Asset.objects.create(name='Site', latitude=1.0, longitude=1.0, country=c)

    def test_create(self):
        from .models import AssetInventory, Flow
        a = self._asset()
        f = Flow.objects.create(key='water', name='Eau', unit='m³', theme='water')
        inv = AssetInventory.objects.create(asset=a, flow=f, year=2024, value=100.0)
        self.assertEqual(inv.value, 100.0)
        self.assertIn('Site', str(inv))

    def test_unique_per_asset_flow_year(self):
        from django.db import IntegrityError, transaction
        from .models import AssetInventory, Flow
        a = self._asset()
        f = Flow.objects.create(key='co2', name='CO2', unit='t', theme='carbon')
        AssetInventory.objects.create(asset=a, flow=f, year=2024, value=1.0)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AssetInventory.objects.create(asset=a, flow=f, year=2024, value=2.0)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.AssetInventoryModelTests`
Expected : FAIL (`cannot import name 'AssetInventory'`).

- [ ] **Step 3 : Ajouter le modèle**

Après `Flow` dans `dashboard/models.py` :
```python
class AssetInventory(models.Model):
    """Inventaire mesuré à l'échelle asset (généralise Asset_consumption)."""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='inventory')
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE)
    year = models.IntegerField()
    value = models.FloatField(default=0.0)
    source = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ('asset', 'flow', 'year')

    def __str__(self):
        return f'{self.asset.name} — {self.flow.key} {self.year}'
```

- [ ] **Step 4 : Générer la migration**

Run : `.venv\Scripts\python.exe manage.py makemigrations dashboard --name assetinventory`
Expected : `0038_assetinventory.py`.

- [ ] **Step 5 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.AssetInventoryModelTests`
Expected : PASS.

- [ ] **Step 6 : Commit**

```bash
git add dashboard/models.py dashboard/migrations/0038_assetinventory.py dashboard/tests.py
git commit -m "feat(models): AssetInventory (inventaire mesuré par flow/année)"
```

---

### Task 4 : Data migration — `Asset_consumption` → `AssetInventory`

**Files:**
- Create: `dashboard/migrations/_asset_consumption_to_inventory.py` (helper figé) + `dashboard/migrations/0039_migrate_asset_consumption.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces (en base) : pour chaque `Asset_consumption`, une `AssetInventory` par mesure **non nulle** ; année = prod. la plus récente de l'asset, sinon `2024`.

- [ ] **Step 1 : Écrire le test (helper)**

```python
class AssetConsumptionToInventoryTests(TestCase):

    def test_converts_nonzero_measures(self):
        from .models import (
            Asset_consumption, AssetInventory, Flow, Asset, Country,
            Commodity, Production,
        )
        from dashboard.migrations import _asset_consumption_to_inventory as conv
        # Flows seedés par 0037 ; on récupère
        c = Country.objects.create(name='FR', water_ownership='X', land_ownership='Y')
        a = Asset.objects.create(name='Site', latitude=1.0, longitude=1.0, country=c)
        com = Commodity.objects.create(name='Soja')
        Production.objects.create(asset=a, commodity=com, year=2023, production=1.0)
        Asset_consumption.objects.create(
            asset=a, water_consumption=100.0, CO2_emissions=50.0,
            waste_generated=0.0, energy_consumption=0.0, surface_area=0.0,
        )
        conv.migrate(Asset_consumption, AssetInventory, Flow, Production)
        # 2 mesures non nulles → 2 lignes, année = 2023 (dernière prod)
        self.assertEqual(AssetInventory.objects.filter(asset=a).count(), 2)
        water = AssetInventory.objects.get(asset=a, flow__key='water')
        self.assertEqual(water.value, 100.0)
        self.assertEqual(water.year, 2023)
        self.assertEqual(AssetInventory.objects.get(asset=a, flow__key='co2').value, 50.0)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.AssetConsumptionToInventoryTests`
Expected : FAIL (module `_asset_consumption_to_inventory` absent).

- [ ] **Step 3 : Écrire le helper + la migration**

Créer `dashboard/migrations/_asset_consumption_to_inventory.py` (figé) :
```python
"""Conversion figée Asset_consumption → AssetInventory (instantané de migration)."""
from django.db.models import Max

# colonne Asset_consumption → clé de Flow (figé)
_COL_TO_FLOW = {
    'surface_area': 'surface_area',
    'water_consumption': 'water',
    'energy_consumption': 'energy',
    'CO2_emissions': 'co2',
    'waste_generated': 'waste',
}
_DEFAULT_YEAR = 2024


def migrate(AssetConsumption, AssetInventory, Flow, Production):
    flows = {f.key: f for f in Flow.objects.all()}
    for ac in AssetConsumption.objects.all():
        if not ac.asset_id:
            continue
        year = Production.objects.filter(asset_id=ac.asset_id).aggregate(
            m=Max('year')
        )['m'] or _DEFAULT_YEAR
        for col, flow_key in _COL_TO_FLOW.items():
            value = getattr(ac, col, 0.0)
            if value:
                AssetInventory.objects.get_or_create(
                    asset_id=ac.asset_id, flow=flows[flow_key], year=year,
                    defaults={'value': value},
                )
```

Créer `dashboard/migrations/0039_migrate_asset_consumption.py` :
```python
from django.db import migrations
from dashboard.migrations import _asset_consumption_to_inventory as conv


def run(apps, schema_editor):
    conv.migrate(
        apps.get_model('dashboard', 'Asset_consumption'),
        apps.get_model('dashboard', 'AssetInventory'),
        apps.get_model('dashboard', 'Flow'),
        apps.get_model('dashboard', 'Production'),
    )


def undo(apps, schema_editor):
    apps.get_model('dashboard', 'AssetInventory').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0038_assetinventory')]
    operations = [migrations.RunPython(run, undo)]
```

- [ ] **Step 4 : Lancer, vérifier le succès + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.AssetConsumptionToInventoryTests dashboard.tests.GoldenViewOutputTests`
Expected : PASS (acme sans Asset_consumption → aucune AssetInventory → golden inchangé).

- [ ] **Step 5 : Commit**

```bash
git add dashboard/migrations/_asset_consumption_to_inventory.py dashboard/migrations/0039_migrate_asset_consumption.py dashboard/tests.py
git commit -m "feat(migration): Asset_consumption → AssetInventory"
```

---

### Task 5 : Service `measured_vs_modeled`

**Files:**
- Modify: `dashboard/services/impacts.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Consumes: `build_cf_index`, `cf_value` (déjà dans impacts.py).
- Produces: `measured_vs_modeled(asset, theme, year) -> {'measured': float, 'modeled': float}`.

- [ ] **Step 1 : Écrire le test**

```python
class MeasuredVsModeledTests(TestCase):

    def test_pairs_measured_and_modeled(self):
        from .models import (
            Asset, Country, SubnationalRegion, Commodity, Production,
            Flow, AssetInventory, ImpactCategory, CharacterizationFactor,
        )
        from .services.impacts import measured_vs_modeled
        country = Country.objects.create(name='FR', water_ownership='X', land_ownership='Y')
        region = SubnationalRegion.objects.create(name='IDF', country=country)
        asset = Asset.objects.create(name='S', latitude=1.0, longitude=1.0,
                                     country=country, subnational_region=region)
        # mesuré : 100 d'eau (Flow theme 'water')
        water = Flow.objects.get(key='water')  # seedé par 0037
        AssetInventory.objects.create(asset=asset, flow=water, year=2024, value=100.0)
        # modélisé : production 10 × CF(catégorie theme 'water') = 10 × 2 = 20
        com = Commodity.objects.create(name='Soja')
        Production.objects.create(asset=asset, commodity=com, year=2024, production=10.0)
        cat = ImpactCategory.objects.get(
            key='impact_midpoint_ReCiPe2016_water_consumption'
        )  # theme 'water' (seedé Plan A)
        CharacterizationFactor.objects.create(category=cat, commodity=com, value=2.0)
        out = measured_vs_modeled(asset, 'water', 2024)
        self.assertAlmostEqual(out['measured'], 100.0, places=4)
        self.assertAlmostEqual(out['modeled'], 20.0, places=4)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.MeasuredVsModeledTests`
Expected : FAIL (`cannot import name 'measured_vs_modeled'`).

- [ ] **Step 3 : Ajouter la fonction**

Ajouter à `dashboard/services/impacts.py` (les imports de modèles vont en tête du fichier avec l'import existant `from dashboard.models import CharacterizationFactor`) :
```python
def measured_vs_modeled(asset, theme, year):
    """Apparie, pour un asset/thème/année : la mesure terrain (AssetInventory dont
    le flow porte ce theme) et l'impact ACV modélisé (production × CF des catégories
    portant ce theme). Renvoie {'measured': float, 'modeled': float}."""
    from dashboard.models import AssetInventory, ImpactCategory, Production
    measured = sum(
        inv.value
        for inv in AssetInventory.objects.filter(
            asset=asset, year=year, flow__theme=theme
        )
    )
    cat_keys = list(
        ImpactCategory.objects.filter(theme=theme).values_list('key', flat=True)
    )
    cf_index = build_cf_index(category_keys=cat_keys)
    modeled = 0.0
    for p in Production.objects.filter(asset=asset, year=year).select_related('commodity'):
        for key in cat_keys:
            modeled += p.production * cf_value(
                cf_index, p.commodity_id, key,
                asset.subnational_region_id, asset.country_id,
            )
    return {'measured': measured, 'modeled': modeled}
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.MeasuredVsModeledTests`
Expected : PASS.

- [ ] **Step 5 : Commit**

```bash
git add dashboard/services/impacts.py dashboard/tests.py
git commit -m "feat(service): measured_vs_modeled (mesure terrain vs impact ACV par thème)"
```

---

### Task 6 : Bascule du bloc consommation de `_get_leap_evaluate_data`

**Files:**
- Modify: `dashboard/views.py` (`_get_leap_evaluate_data`, bloc consommation ~710-716 ; import ligne 11)
- Modify: `dashboard/tests.py` (`LeapEvaluateDataTests`)

- [ ] **Step 1 : Adapter le test**

Dans `LeapEvaluateDataTests.setUp`, remplacer la création `Asset_consumption.objects.create(asset=self.asset, water_consumption=100.0, CO2_emissions=50.0, waste_generated=25.0)` par des `AssetInventory` équivalentes :
```python
        from .models import AssetInventory, Flow
        AssetInventory.objects.create(
            asset=self.asset, flow=Flow.objects.get(key='water'), year=2024, value=100.0
        )
        AssetInventory.objects.create(
            asset=self.asset, flow=Flow.objects.get(key='co2'), year=2024, value=50.0
        )
        AssetInventory.objects.create(
            asset=self.asset, flow=Flow.objects.get(key='waste'), year=2024, value=25.0
        )
```
Les assertions `test_asset_consumption_and_sensitive_zone` (water 100 / co2 50 / waste 25) restent inchangées. Retirer l'import `Asset_consumption` du `setUp` s'il est local.

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.LeapEvaluateDataTests`
Expected : FAIL (la vue lit encore `Asset_consumption` → consommation 0).

- [ ] **Step 3 : Basculer la vue**

Dans `dashboard/views.py`, remplacer `Asset_consumption` par `AssetInventory` dans l'import `.models` (ligne 11). Puis remplacer le bloc (≈ lignes 710-716) :
```python
    consumption = defaultdict(lambda: {'water': 0.0, 'co2': 0.0, 'waste': 0.0})
    for c in Asset_consumption.objects.filter(asset_id__in=asset_ids):
        agg = consumption[c.asset_id]
        agg['water'] += c.water_consumption
        agg['co2'] += c.CO2_emissions
        agg['waste'] += c.waste_generated
```
par :
```python
    consumption = defaultdict(lambda: {'water': 0.0, 'co2': 0.0, 'waste': 0.0})
    for inv in AssetInventory.objects.filter(
        asset_id__in=asset_ids, flow__key__in=('water', 'co2', 'waste')
    ).select_related('flow'):
        consumption[inv.asset_id][inv.flow.key] += inv.value
```

- [ ] **Step 4 : Lancer, vérifier le succès + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.LeapEvaluateDataTests dashboard.tests.GoldenViewOutputTests`
Expected : PASS (golden `leap_evaluate.json` inchangé : acme sans inventaire → consommation 0).

- [ ] **Step 5 : Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "refactor(views): leap_evaluate lit la consommation via AssetInventory"
```

---

### Task 7 : `imports` — `Asset_consumption` → `AssetInventory`

**Files:**
- Modify: `imports/services/importer.py` (`_import_asset_consumption`)
- Modify: `imports/services/constants.py` (feuille `Asset_consumption` : ajouter `year`)
- Modify: `imports/tests/test_importer.py`

**Principe :** la feuille `Asset_consumption` garde ses colonnes de mesure + gagne une colonne `year` (optionnelle, défaut 2024) ; l'importer crée une `AssetInventory` par mesure non nulle via le `Flow` correspondant.

- [ ] **Step 1 : Ajouter `year` à la feuille**

Dans `imports/services/constants.py`, dans `SHEET_COLUMNS['Asset_consumption']`, insérer `'year'` après `'asset_name'` :
```python
    'Asset_consumption': [
        'asset_name', 'year', 'surface_area', 'water_consumption',
        'energy_consumption', 'CO2_emissions', 'waste_generated',
    ],
```

- [ ] **Step 2 : Écrire/adapter le test**

Dans `imports/tests/test_importer.py`, ajouter un test : importer une feuille `Asset_consumption` avec `water_consumption=100`, `year=2024` via `save_import(...)`, et vérifier qu'une `AssetInventory(asset, flow water, year 2024, value 100)` est créée (pas d'exception). Réutiliser les fixtures/patterns existants (lecture préalable du fichier).

- [ ] **Step 3 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test imports.tests.test_importer`
Expected : FAIL (l'importer crée encore `Asset_consumption`, pas d'`AssetInventory`).

- [ ] **Step 4 : Basculer l'importer**

Dans `imports/services/importer.py` : ajouter `AssetInventory`, `Flow` à l'import `from dashboard.models import (...)`. Remplacer le corps de `_import_asset_consumption` :
```python
def _import_asset_consumption(rows, lookup):
    created = 0
    flows = {f.key: f for f in Flow.objects.all()}
    col_to_flow = {
        'surface_area': 'surface_area', 'water_consumption': 'water',
        'energy_consumption': 'energy', 'CO2_emissions': 'co2',
        'waste_generated': 'waste',
    }
    for r in rows:
        d = r['data']
        asset = lookup['asset'].get(d['asset_name'].lower())
        if not asset:
            continue
        try:
            year = int(d['year'])
        except (KeyError, ValueError, TypeError):
            year = 2024
        for col, flow_key in col_to_flow.items():
            value = _f(d.get(col))
            if value and flow_key in flows:
                AssetInventory.objects.get_or_create(
                    asset=asset, flow=flows[flow_key], year=year,
                    defaults={'value': value},
                )
                created += 1
    return created
```

- [ ] **Step 5 : Lancer, vérifier le succès + suite projet**

Run : `.venv\Scripts\python.exe manage.py test imports`
Expected : PASS.
Run : `.venv\Scripts\python.exe manage.py test`
Expected : PASS (projet entier).

- [ ] **Step 6 : Commit**

```bash
git add imports/services/importer.py imports/services/constants.py imports/tests/test_importer.py
git commit -m "fix(imports): _import_asset_consumption crée des AssetInventory"
```

---

### Task 8 : Admin — `Flow` + `AssetInventory`

**Files:**
- Modify: `dashboard/admin.py`

- [ ] **Step 1 : Enregistrer les modèles**

Dans `dashboard/admin.py`, ajouter `Flow, AssetInventory` aux imports `from .models import (...)` et, en fin de fichier :
```python
@admin.register(Flow)
class FlowAdmin(admin.ModelAdmin):
    search_fields = ('key', 'name')
    list_display = ('key', 'name', 'unit', 'theme')
    list_filter = ('theme',)


@admin.register(AssetInventory)
class AssetInventoryAdmin(admin.ModelAdmin):
    search_fields = ('asset__name', 'flow__key')
    list_display = ('asset', 'flow', 'year', 'value')
    list_filter = ('flow', 'year')
    autocomplete_fields = ('asset', 'flow')
```

- [ ] **Step 2 : Vérifier les system checks**

Run : `.venv\Scripts\python.exe manage.py check`
Expected : `System check identified no issues`. (`FlowAdmin` a `search_fields` → l'autocomplete `flow` de `AssetInventoryAdmin` ne déclenche pas admin.E039.)

- [ ] **Step 3 : Commit**

```bash
git add dashboard/admin.py
git commit -m "feat(admin): enregistre Flow et AssetInventory"
```

---

### Task 9 : Nettoyage — drop `Asset_consumption`

**Files:**
- Modify: `dashboard/models.py` (retirer la classe `Asset_consumption`)
- Modify: `dashboard/admin.py` (retirer `Asset_consumption`/`AssetConsumptionAdmin`)
- Create: `dashboard/migrations/0040_drop_asset_consumption.py`
- Test: `dashboard/tests.py`

- [ ] **Step 1 : Écrire le test de suppression**

```python
class AssetConsumptionDroppedTests(TestCase):

    def test_model_gone(self):
        import dashboard.models as m
        self.assertFalse(hasattr(m, 'Asset_consumption'))
```

- [ ] **Step 2 : Retirer le modèle + l'admin + les tests obsolètes**

Dans `dashboard/models.py` : supprimer entièrement la classe `Asset_consumption`.
Dans `dashboard/admin.py` : retirer `Asset_consumption` des imports et son `@admin.register(Asset_consumption)` (classe `AssetConsumptionAdmin`).
**Retirer aussi le test obsolète** `AssetConsumptionToInventoryTests` (Task 4) dans `dashboard/tests.py` : il crée `Asset_consumption.objects.create(...)` (modèle supprimé). La migration `0039` reste couverte (helper figé + golden). Ne pas toucher aux autres classes.

- [ ] **Step 3 : Générer la migration**

Run : `.venv\Scripts\python.exe manage.py makemigrations dashboard --name drop_asset_consumption`
Expected : `0040_drop_asset_consumption.py` (DeleteModel Asset_consumption).

- [ ] **Step 4 : Suite complète + golden + vérif**

Run : `.venv\Scripts\python.exe manage.py test`
Expected : PASS (projet entier, golden inclus).
Run : `git grep -n "Asset_consumption" -- dashboard/ imports/`
Expected : plus aucune occurrence hors `dashboard/migrations/` (historique + helper figé) — en particulier ni `views.py`, ni `admin.py`, ni `imports/`.

- [ ] **Step 5 : Commit**

```bash
git add dashboard/models.py dashboard/admin.py dashboard/migrations/0040_drop_asset_consumption.py dashboard/tests.py
git commit -m "refactor: drop Asset_consumption (AssetInventory = source unique)"
```

---

## Self-Review

**Couverture du spec (Plan C) :**
- §5.1 `Flow` (key/name/unit/theme) → Tasks 1, 2.
- §5.4 `AssetInventory` (asset/flow/année/valeur, unique_together) → Task 3.
- §5.6 suppression `Asset_consumption` → Task 9.
- §6 `measured_vs_modeled` (garder impact ACV + mesure) → Task 5.
- §8.4 migration `Asset_consumption → AssetInventory` (année = prod. récente) → Task 4.
- §9 `leap_evaluate` (partie consommation), imports, admin → Tasks 6, 7, 8.
- `physical_risk` : **inchangé** — il ne lit pas `Asset_consumption` aujourd'hui ; `AssetInventory` est rendu disponible (modèle first-class) pour un usage risque futur, sans modifier la formule (conforme spec §5.4 / hors-périmètre §12).
- §11 golden + tests : `leap_evaluate` déjà dans `GOLDEN_VIEWS` (Plan A), invariant ici (acme sans inventaire) ; tests par tâche.

**Scan placeholders :** aucun « TBD/TODO ».

**Cohérence des types/noms :** `Flow(key/name/unit/theme)`, `AssetInventory(asset/flow/year/value)`, `measured_vs_modeled(asset, theme, year) -> {'measured','modeled'}`, mapping colonne→flow figé, migrations `0036→0040` chaînées, helpers **figés** (préfixe `_`, aucun import de constante vivante). Golden `leap_evaluate` invariant.

**Décision de sortie préservée :** `leap_evaluate` renvoie les mêmes clés (`water_consumption`/`co2_emissions`/`waste_generated`) sommées désormais depuis `AssetInventory` (flows water/co2/waste). Acme sans inventaire → 0 → golden invariant.
