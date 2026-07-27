# Plan A — Facteurs de caractérisation régionalisés (chemin ACV) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer les 16 colonnes d'impact figées de `Commodity` par une table `CharacterizationFactor` régionalisée (fallback région→pays→global), centraliser le calcul d'impact dans une couche service, et basculer les 6 vues consommatrices — sans changer la forme JSON de sortie.

**Architecture:** Un catalogue (`ImpactMethod`, `ImpactCategory`) décrit les axes d'impact ; `CharacterizationFactor` porte la valeur par (catégorie × commodity × lieu). Un service `dashboard/services/impacts.py` charge les CF en masse et résout le fallback. Les vues appellent le service au lieu de lire des attributs de `Commodity`. Un filet de tests « golden » capture la sortie JSON actuelle et vérifie l'invariance à chaque étape.

**Tech Stack:** Django 5 (TestCase), SQLite en dev, Python 3.11+. Aucune dépendance nouvelle.

## Global Constraints

- Python **3.11+**, PEP 8, lignes **≤ 100 caractères**.
- **Aucun** framework frontend ; **aucune** dépendance nouvelle.
- **Compatible SQLite** : que `FloatField`/`FK`/`CharField`/`IntegerField`/`BooleanField`. Pas de PostGIS, pas de `JSONField` Postgres-only, pas de numpy.
- On **reste dans l'app `dashboard`**. Pas de découpage en `apps/`.
- **La forme JSON de sortie de chaque vue reste identique** (garantie par les golden tests).
- **Une migration = un changement logique**. Nommer explicitement (`makemigrations dashboard --name <nom>`).
- Commande de test : `.venv\Scripts\python.exe manage.py test dashboard` (Windows PowerShell). Une classe : `.venv\Scripts\python.exe manage.py test dashboard.tests.<Classe>`.
- Commande de migration : `.venv\Scripts\python.exe manage.py makemigrations dashboard --name <nom>` puis (implicite au test) la base de test applique les migrations.
- Modèles concernés existants : `dashboard/models.py`. Vues : `dashboard/views.py`. Tests : `dashboard/tests.py`. Seed démo : `dashboard/management/commands/populate_acme.py`. Admin : `dashboard/admin.py`.

---

## File Structure

- `dashboard/models.py` — ajoute `ImpactMethod`, `ImpactCategory`, `CharacterizationFactor` (à la fin, après `Carbon_emission`).
- `dashboard/services/impacts.py` — **nouveau** : `LEGACY_IMPACT_COLUMNS`, `CAT_ECOSYSTEM_DIVERSITY`, `build_cf_index()`, `cf_value()`, `legacy_cf_rows()`.
- `dashboard/services/__init__.py` — existe déjà (paquet `services`).
- `dashboard/migrations/00XX_*.py` — migrations de schéma + data (une par tâche).
- `dashboard/golden/` — **nouveau dossier** : snapshots JSON de référence (`company_data.json`, etc.).
- `dashboard/tests.py` — ajoute `_make_cf()` helper, `GoldenViewOutputTests`, et adapte les setups couplés aux colonnes.
- `dashboard/views.py` — bascule 6 fonctions `_get_*_data` sur le service.
- `dashboard/admin.py` — enregistre les 3 nouveaux modèles.
- `dashboard/management/commands/populate_acme.py` — crée des CF globales miroir des colonnes, puis (au nettoyage) retire les kwargs de colonnes.

**Contrat clé :** `ImpactCategory.key` **est** le nom de colonne legacy (ex. `impact_endpoint_ReCiPe2016_ecosystem_diversity`). Les listes `_IMPACT_FIELDS` / `_EVALUATE_IMPACT_FIELDS` de `views.py` gardent ces chaînes comme clés → la forme de sortie ne bouge pas.

---

### Task 1 : Filet de sécurité « golden » (capture de la sortie actuelle)

Établit la référence AVANT toute modification. En mode enregistrement (`GOLDEN_RECORD=1`), le test écrit les fichiers ; sinon il compare.

**Files:**
- Create: `dashboard/golden/` (dossier, via le test en mode record)
- Modify: `dashboard/tests.py` (ajouter une classe en fin de fichier)

**Interfaces:**
- Produces: classe `GoldenViewOutputTests` ; constante interne `GOLDEN_VIEWS` (liste de `(nom_fichier, url_name)`). Aucun autre module n'en dépend.

- [ ] **Step 1 : Écrire le test golden (mode record + assert)**

Ajouter à la fin de `dashboard/tests.py` :

```python
import os
from pathlib import Path
from django.core.management import call_command

GOLDEN_DIR = Path(__file__).resolve().parent / 'golden'

# Vues du chemin ACV dont la forme de sortie doit rester invariante.
GOLDEN_VIEWS = [
    ('company_data',        'dashboard:company_data'),
    ('mesure_empreinte',    'dashboard:mesure_empreinte_data'),
    ('leap_evaluate',       'dashboard:leap_evaluate_data'),
    ('leap_prepare',        'dashboard:leap_prepare_data'),
    ('dette_ecologique',    'dashboard:dette_ecologique_data'),
    ('compare',             'dashboard:compare_data'),
]


class GoldenViewOutputTests(TestCase):
    """Snapshot des sorties JSON sur le jeu déterministe `populate_acme`.

    Enregistrer la référence :  GOLDEN_RECORD=1 python manage.py test
        dashboard.tests.GoldenViewOutputTests
    Vérifier (défaut) :         python manage.py test
        dashboard.tests.GoldenViewOutputTests
    """

    @classmethod
    def setUpTestData(cls):
        call_command('populate_acme')
        from django.contrib.auth import get_user_model
        User = get_user_model()
        cls.user = User.objects.create_user(username='golden', password='x')
        cls.acme = Company.objects.get(name='Acme Corp')

    def _fetch(self, url_name):
        self.client.force_login(self.user)
        url = reverse(url_name, kwargs={'pk': self.acme.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url_name)
        return json.loads(response.content)

    def test_golden_outputs_match(self):
        record = os.environ.get('GOLDEN_RECORD') == '1'
        if record:
            GOLDEN_DIR.mkdir(exist_ok=True)
        for fname, url_name in GOLDEN_VIEWS:
            payload = self._fetch(url_name)
            path = GOLDEN_DIR / f'{fname}.json'
            if record:
                path.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
                    encoding='utf-8',
                )
                continue
            self.assertTrue(path.exists(), f'Golden manquant : {path} (lancer GOLDEN_RECORD=1)')
            expected = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(payload, expected, f'Sortie modifiée pour {fname}')
```

- [ ] **Step 2 : Enregistrer la référence (comportement actuel)**

Run (PowerShell) :
```
$env:GOLDEN_RECORD=1; .venv\Scripts\python.exe manage.py test dashboard.tests.GoldenViewOutputTests; Remove-Item Env:\GOLDEN_RECORD
```
Expected : `OK` ; 6 fichiers créés dans `dashboard/golden/` (`company_data.json`, `mesure_empreinte.json`, `leap_evaluate.json`, `leap_prepare.json`, `dette_ecologique.json`, `compare.json`).

- [ ] **Step 3 : Vérifier le mode assert (sans record)**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.GoldenViewOutputTests`
Expected : PASS (la sortie courante == référence tout juste écrite).

- [ ] **Step 4 : Commit**

```bash
git add dashboard/tests.py dashboard/golden/
git commit -m "test(golden): fige la sortie JSON des vues ACV (baseline pré-refonte)"
```

---

### Task 2 : Modèles catalogue `ImpactMethod` + `ImpactCategory`

**Files:**
- Modify: `dashboard/models.py` (fin de fichier)
- Create: `dashboard/migrations/00XX_impact_catalog.py` (via makemigrations)
- Test: `dashboard/tests.py` (nouvelle classe)

**Interfaces:**
- Produces: `ImpactMethod(name, version, description)` ; `ImpactCategory(method FK, key [unique], name, unit, level, theme)` ; `ImpactCategory.Level.MIDPOINT` / `.ENDPOINT`.

- [ ] **Step 1 : Écrire le test**

Ajouter à `dashboard/tests.py` :

```python
class ImpactCatalogModelTests(TestCase):

    def test_method_str(self):
        from .models import ImpactMethod
        m = ImpactMethod.objects.create(name='ReCiPe2016', version='1.1')
        self.assertEqual(str(m), 'ReCiPe2016')

    def test_category_str_and_level(self):
        from .models import ImpactMethod, ImpactCategory
        m = ImpactMethod.objects.create(name='ReCiPe2016')
        c = ImpactCategory.objects.create(
            method=m, key='impact_midpoint_ReCiPe2016_land_use',
            name='Utilisation des terres', level=ImpactCategory.Level.MIDPOINT,
        )
        self.assertEqual(c.level, 'MIDPOINT')
        self.assertIn('land_use', str(c))

    def test_category_key_is_unique(self):
        from django.db import IntegrityError, transaction
        from .models import ImpactMethod, ImpactCategory
        m = ImpactMethod.objects.create(name='ReCiPe2016')
        ImpactCategory.objects.create(method=m, key='dup', name='A')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ImpactCategory.objects.create(method=m, key='dup', name='B')
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.ImpactCatalogModelTests`
Expected : FAIL (`cannot import name 'ImpactMethod'`).

- [ ] **Step 3 : Ajouter les modèles**

À la fin de `dashboard/models.py` :

```python
class ImpactMethod(models.Model):
    """Méthode de caractérisation LCA (ReCiPe2016, GBS, …)."""
    name = models.CharField(max_length=100, unique=True)
    version = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class ImpactCategory(models.Model):
    """Axe d'impact ACV. `key` == nom de colonne legacy (contrat de sortie)."""

    class Level(models.TextChoices):
        MIDPOINT = 'MIDPOINT', 'Midpoint'
        ENDPOINT = 'ENDPOINT', 'Endpoint'

    method = models.ForeignKey(
        ImpactMethod, on_delete=models.CASCADE, related_name='categories'
    )
    key = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=50, blank=True)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.MIDPOINT)
    theme = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return f'{self.method.name} — {self.key}'
```

- [ ] **Step 4 : Générer la migration**

Run : `.venv\Scripts\python.exe manage.py makemigrations dashboard --name impact_catalog`
Expected : `Migrations for 'dashboard': 00XX_impact_catalog.py … Create model ImpactMethod, ImpactCategory`.

- [ ] **Step 5 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.ImpactCatalogModelTests`
Expected : PASS.

- [ ] **Step 6 : Commit**

```bash
git add dashboard/models.py dashboard/migrations/00XX_impact_catalog.py dashboard/tests.py
git commit -m "feat(models): catalogue ImpactMethod/ImpactCategory"
```

---

### Task 3 : Modèle `CharacterizationFactor`

**Files:**
- Modify: `dashboard/models.py` (fin de fichier)
- Create: `dashboard/migrations/00XX_characterization_factor.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces: `CharacterizationFactor(category FK, commodity FK, region FK/null, country FK/null, value, source, reference, created_at, updated_at)`.

- [ ] **Step 1 : Écrire le test**

```python
class CharacterizationFactorModelTests(TestCase):

    def _cat(self):
        from .models import ImpactMethod, ImpactCategory
        m = ImpactMethod.objects.create(name='ReCiPe2016')
        return ImpactCategory.objects.create(
            method=m, key='impact_endpoint_ReCiPe2016_ecosystem_diversity',
            name='Diversité des écosystèmes', level=ImpactCategory.Level.ENDPOINT,
        )

    def test_global_cf_has_null_location(self):
        from .models import CharacterizationFactor, Commodity
        cat = self._cat()
        com = Commodity.objects.create(name='Soja')
        cf = CharacterizationFactor.objects.create(category=cat, commodity=com, value=0.5)
        self.assertIsNone(cf.region_id)
        self.assertIsNone(cf.country_id)
        self.assertIn('Soja', str(cf))

    def test_region_and_country_cf(self):
        from .models import CharacterizationFactor, Commodity, Country, SubnationalRegion
        cat = self._cat()
        com = Commodity.objects.create(name='Soja')
        country = Country.objects.create(
            name='Brésil', water_ownership='X', land_ownership='Y'
        )
        region = SubnationalRegion.objects.create(name='Pará', country=country)
        CharacterizationFactor.objects.create(
            category=cat, commodity=com, country=country, value=0.7
        )
        CharacterizationFactor.objects.create(
            category=cat, commodity=com, region=region, value=0.9
        )
        self.assertEqual(CharacterizationFactor.objects.filter(commodity=com).count(), 2)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.CharacterizationFactorModelTests`
Expected : FAIL (`cannot import name 'CharacterizationFactor'`).

- [ ] **Step 3 : Ajouter le modèle**

À la fin de `dashboard/models.py` :

```python
class CharacterizationFactor(models.Model):
    """Facteur de caractérisation régionalisé : impact par unité de commodity.

    Résolution du lieu : region renseigné → région ; sinon country → pays ;
    sinon (les deux null) → global.
    """
    category = models.ForeignKey(
        ImpactCategory, on_delete=models.CASCADE, related_name='factors'
    )
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE, related_name='cfs')
    region = models.ForeignKey(
        SubnationalRegion, on_delete=models.CASCADE, null=True, blank=True
    )
    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, null=True, blank=True
    )
    value = models.FloatField(default=0.0)
    source = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # NB SQLite : les NULL sont distincts dans une contrainte unique ; l'unicité
        # du CF global (region=country=null) est garantie applicativement par
        # get_or_create côté backfill et populate_acme.
        unique_together = ('category', 'commodity', 'region', 'country')

    def __str__(self):
        return f'{self.commodity.name} — {self.category.key}'
```

- [ ] **Step 4 : Générer la migration**

Run : `.venv\Scripts\python.exe manage.py makemigrations dashboard --name characterization_factor`
Expected : crée `00XX_characterization_factor.py` (Create model CharacterizationFactor).

- [ ] **Step 5 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.CharacterizationFactorModelTests`
Expected : PASS.

- [ ] **Step 6 : Commit**

```bash
git add dashboard/models.py dashboard/migrations/00XX_characterization_factor.py dashboard/tests.py
git commit -m "feat(models): CharacterizationFactor régionalisé"
```

---

### Task 4 : Data migration — seed du catalogue (16 catégories + 2 méthodes)

**Files:**
- Create: `dashboard/migrations/00XX_seed_impact_catalog.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces (en base après migration) : `ImpactMethod` `ReCiPe2016` et `GBS` ; 16 `ImpactCategory` dont `key` ∈ noms de colonnes legacy.

- [ ] **Step 1 : Écrire le test (état attendu après migration)**

```python
class SeedImpactCatalogTests(TestCase):

    def test_two_methods_seeded(self):
        from .models import ImpactMethod
        names = set(ImpactMethod.objects.values_list('name', flat=True))
        self.assertTrue({'ReCiPe2016', 'GBS'}.issubset(names))

    def test_sixteen_categories_seeded(self):
        from .models import ImpactCategory
        self.assertEqual(ImpactCategory.objects.count(), 16)

    def test_ecosystem_diversity_is_endpoint(self):
        from .models import ImpactCategory
        cat = ImpactCategory.objects.get(
            key='impact_endpoint_ReCiPe2016_ecosystem_diversity'
        )
        self.assertEqual(cat.level, 'ENDPOINT')
        self.assertEqual(cat.method.name, 'ReCiPe2016')

    def test_gbs_categories_use_gbs_method(self):
        from .models import ImpactCategory
        cat = ImpactCategory.objects.get(key='impact_endpoint_GBS_terrestrial_static')
        self.assertEqual(cat.method.name, 'GBS')
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.SeedImpactCatalogTests`
Expected : FAIL (`ImpactCategory.objects.count()` == 0).

- [ ] **Step 3 : Créer la data migration**

Créer `dashboard/migrations/00XX_seed_impact_catalog.py` (remplacer `00YY_characterization_factor` par la dépendance réelle) :

```python
from django.db import migrations

# (method_name, key, name, level, theme). key == nom de colonne legacy.
CATEGORIES = [
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_water_consumption',
     'Consommation eau', 'MIDPOINT', 'water'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_climate_change',
     'Changement climatique', 'MIDPOINT', 'carbon'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity',
     'Écotoxicité eau douce', 'MIDPOINT', 'water'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_freshwater_eutrophication',
     'Eutrophisation eau douce', 'MIDPOINT', 'water'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_marine_eutrophication',
     'Eutrophisation marine', 'MIDPOINT', 'water'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_terrestrial_acidification',
     'Acidification terrestre', 'MIDPOINT', ''),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_soil_acidification',
     'Acidification des sols', 'MIDPOINT', 'land'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_ozonedepletion',
     "Appauvrissement de l'ozone", 'MIDPOINT', ''),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_resource_depletion_fossil',
     'Épuisement ressources fossiles', 'MIDPOINT', ''),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_resource_depletion_minerals',
     'Épuisement ressources minérales', 'MIDPOINT', ''),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_land_use',
     'Utilisation des terres', 'MIDPOINT', 'land'),
    ('ReCiPe2016', 'impact_endpoint_ReCiPe2016_human_health',
     'Santé humaine', 'ENDPOINT', ''),
    ('ReCiPe2016', 'impact_endpoint_ReCiPe2016_ecosystem_diversity',
     'Diversité des écosystèmes', 'ENDPOINT', 'land'),
    ('ReCiPe2016', 'impact_endpoint_ReCiPe2016_resource_availability',
     'Disponibilité ressources', 'ENDPOINT', ''),
    ('GBS', 'impact_endpoint_GBS_terrestrial_dynamic',
     'Terrestre dynamique (GBS)', 'ENDPOINT', 'land'),
    ('GBS', 'impact_endpoint_GBS_terrestrial_static',
     'Terrestre statique (GBS)', 'ENDPOINT', 'land'),
]


def seed(apps, schema_editor):
    ImpactMethod = apps.get_model('dashboard', 'ImpactMethod')
    ImpactCategory = apps.get_model('dashboard', 'ImpactCategory')
    methods = {}
    for name in ('ReCiPe2016', 'GBS'):
        methods[name] = ImpactMethod.objects.get_or_create(name=name)[0]
    for method_name, key, label, level, theme in CATEGORIES:
        ImpactCategory.objects.get_or_create(
            key=key,
            defaults={
                'method': methods[method_name],
                'name': label, 'level': level, 'theme': theme,
            },
        )


def unseed(apps, schema_editor):
    ImpactCategory = apps.get_model('dashboard', 'ImpactCategory')
    ImpactMethod = apps.get_model('dashboard', 'ImpactMethod')
    ImpactCategory.objects.filter(key__in=[c[1] for c in CATEGORIES]).delete()
    ImpactMethod.objects.filter(name__in=('ReCiPe2016', 'GBS')).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '00YY_characterization_factor'),
    ]
    operations = [migrations.RunPython(seed, unseed)]
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.SeedImpactCatalogTests`
Expected : PASS (4 tests).

- [ ] **Step 5 : Commit**

```bash
git add dashboard/migrations/00XX_seed_impact_catalog.py dashboard/tests.py
git commit -m "feat(migration): seed du catalogue d'impact (16 catégories)"
```

---

### Task 5 : Couche service `impacts.py` (`build_cf_index`, `cf_value`, `legacy_cf_rows`)

**Files:**
- Create: `dashboard/services/impacts.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces:
  - `LEGACY_IMPACT_COLUMNS: list[str]` (16 noms de colonnes, figés).
  - `CAT_ECOSYSTEM_DIVERSITY = 'impact_endpoint_ReCiPe2016_ecosystem_diversity'`.
  - `build_cf_index(commodity_ids=None, category_keys=None) -> dict[(int, str, tuple), float]`.
  - `cf_value(cf_index, commodity_id, category_key, region_id=None, country_id=None) -> float`.
  - `legacy_cf_rows(values: dict[str, float]) -> list[tuple[str, float]]`.

- [ ] **Step 1 : Écrire le test**

```python
class CfServiceTests(TestCase):

    def setUp(self):
        from .models import (
            ImpactMethod, ImpactCategory, CharacterizationFactor,
            Commodity, Country, SubnationalRegion,
        )
        # NB : nom de méthode non-seedé (ReCiPe2016/GBS sont créés par la
        # migration 0026) et clé de catégorie non-seedée, pour éviter toute
        # collision d'unicité avec le catalogue seedé.
        self.method = ImpactMethod.objects.create(name='TestMethod')
        self.cat = ImpactCategory.objects.create(
            method=self.method, key='k_eco', name='Eco',
            level=ImpactCategory.Level.ENDPOINT,
        )
        self.com = Commodity.objects.create(name='Soja')
        self.country = Country.objects.create(
            name='Brésil', water_ownership='X', land_ownership='Y'
        )
        self.region = SubnationalRegion.objects.create(name='Pará', country=self.country)
        CharacterizationFactor.objects.create(category=self.cat, commodity=self.com, value=1.0)
        CharacterizationFactor.objects.create(
            category=self.cat, commodity=self.com, country=self.country, value=2.0
        )
        CharacterizationFactor.objects.create(
            category=self.cat, commodity=self.com, region=self.region, value=3.0
        )

    def test_region_wins(self):
        from .services.impacts import build_cf_index, cf_value
        idx = build_cf_index([self.com.pk], ['k_eco'])
        self.assertEqual(
            cf_value(idx, self.com.pk, 'k_eco', self.region.pk, self.country.pk), 3.0
        )

    def test_country_when_no_region_cf(self):
        from .services.impacts import build_cf_index, cf_value
        idx = build_cf_index([self.com.pk], ['k_eco'])
        # region_id inconnu en base -> retombe sur pays
        self.assertEqual(cf_value(idx, self.com.pk, 'k_eco', 99999, self.country.pk), 2.0)

    def test_global_fallback(self):
        from .services.impacts import build_cf_index, cf_value
        idx = build_cf_index([self.com.pk], ['k_eco'])
        self.assertEqual(cf_value(idx, self.com.pk, 'k_eco', None, None), 1.0)

    def test_missing_returns_zero(self):
        from .services.impacts import build_cf_index, cf_value
        idx = build_cf_index([self.com.pk], ['k_eco'])
        self.assertEqual(cf_value(idx, self.com.pk, 'inconnue', None, None), 0.0)

    def test_legacy_cf_rows_maps_16_columns(self):
        from .services.impacts import legacy_cf_rows, LEGACY_IMPACT_COLUMNS
        rows = legacy_cf_rows({'impact_midpoint_ReCiPe2016_land_use': 6.5})
        self.assertEqual(len(rows), 16)
        self.assertEqual(len(LEGACY_IMPACT_COLUMNS), 16)
        as_dict = dict(rows)
        self.assertEqual(as_dict['impact_midpoint_ReCiPe2016_land_use'], 6.5)
        self.assertEqual(as_dict['impact_endpoint_GBS_terrestrial_static'], 0.0)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.CfServiceTests`
Expected : FAIL (`No module named 'dashboard.services.impacts'`).

- [ ] **Step 3 : Écrire le service**

Créer `dashboard/services/impacts.py` :

```python
"""Service central du chemin ACV : résolution régionalisée des facteurs de
caractérisation (CF) et helpers de calcul d'impact.

`ImpactCategory.key` == nom de colonne legacy → les vues gardent les mêmes clés
de sortie qu'avant la refonte.
"""
from dashboard.models import CharacterizationFactor

CAT_ECOSYSTEM_DIVERSITY = 'impact_endpoint_ReCiPe2016_ecosystem_diversity'

# Figé : les 16 colonnes d'impact historiques de Commodity, dans l'ordre.
# Sert au backfill (Task 6) et reste stable même après suppression des colonnes.
LEGACY_IMPACT_COLUMNS = [
    'impact_midpoint_ReCiPe2016_water_consumption',
    'impact_midpoint_ReCiPe2016_climate_change',
    'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity',
    'impact_midpoint_ReCiPe2016_freshwater_eutrophication',
    'impact_midpoint_ReCiPe2016_marine_eutrophication',
    'impact_midpoint_ReCiPe2016_terrestrial_acidification',
    'impact_midpoint_ReCiPe2016_soil_acidification',
    'impact_midpoint_ReCiPe2016_ozonedepletion',
    'impact_midpoint_ReCiPe2016_resource_depletion_fossil',
    'impact_midpoint_ReCiPe2016_resource_depletion_minerals',
    'impact_midpoint_ReCiPe2016_land_use',
    'impact_endpoint_ReCiPe2016_human_health',
    'impact_endpoint_ReCiPe2016_ecosystem_diversity',
    'impact_endpoint_ReCiPe2016_resource_availability',
    'impact_endpoint_GBS_terrestrial_dynamic',
    'impact_endpoint_GBS_terrestrial_static',
]


def build_cf_index(commodity_ids=None, category_keys=None):
    """Charge en masse les CF pertinents en un dict de résolution.

    Clé : (commodity_id, category_key, locus) où locus vaut
    ('region', region_id) | ('country', country_id) | ('global', None).
    """
    qs = CharacterizationFactor.objects.select_related('category')
    if commodity_ids is not None:
        qs = qs.filter(commodity_id__in=commodity_ids)
    if category_keys is not None:
        qs = qs.filter(category__key__in=category_keys)
    index = {}
    for cf in qs:
        if cf.region_id is not None:
            locus = ('region', cf.region_id)
        elif cf.country_id is not None:
            locus = ('country', cf.country_id)
        else:
            locus = ('global', None)
        index[(cf.commodity_id, cf.category.key, locus)] = cf.value
    return index


def cf_value(cf_index, commodity_id, category_key, region_id=None, country_id=None):
    """Fallback : région → pays → global → 0.0."""
    if region_id is not None:
        v = cf_index.get((commodity_id, category_key, ('region', region_id)))
        if v is not None:
            return v
    if country_id is not None:
        v = cf_index.get((commodity_id, category_key, ('country', country_id)))
        if v is not None:
            return v
    return cf_index.get((commodity_id, category_key, ('global', None)), 0.0)


def legacy_cf_rows(values):
    """(col_name, valeur) pour les 16 colonnes legacy ; défaut 0.0 si absente."""
    return [(col, values.get(col, 0.0)) for col in LEGACY_IMPACT_COLUMNS]
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.CfServiceTests`
Expected : PASS (5 tests).

- [ ] **Step 5 : Commit**

```bash
git add dashboard/services/impacts.py dashboard/tests.py
git commit -m "feat(service): résolution régionalisée des CF (fallback lieu)"
```

---

### Task 6 : Data migration — backfill des colonnes vers CF globales

**Files:**
- Create: `dashboard/migrations/00XX_backfill_global_cfs.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Consumes: `LEGACY_IMPACT_COLUMNS` (service), `ImpactCategory` seedées (Task 4).
- Produces (en base) : une CF globale par (commodity, catégorie) valant l'ancienne colonne.

- [ ] **Step 1 : Écrire le test (via une commande de vérification post-migration)**

Le backfill s'exécute sur les données existantes au moment de la migration. On le teste en s'assurant qu'une commodité créée AVANT une nouvelle exécution du backfill obtient ses CF. On expose une fonction réutilisable et on la teste directement.

```python
class BackfillGlobalCfsTests(TestCase):

    def test_backfill_creates_global_cf_per_column(self):
        from .models import Commodity, CharacterizationFactor
        from dashboard.migrations import _cf_backfill  # module d'aide (Step 3)
        com = Commodity.objects.create(
            name='Soja',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
            impact_midpoint_ReCiPe2016_land_use=6.5,
        )
        _cf_backfill.backfill(Commodity, CharacterizationFactor, _get_category)
        eco = CharacterizationFactor.objects.get(
            commodity=com, category__key='impact_endpoint_ReCiPe2016_ecosystem_diversity',
            region__isnull=True, country__isnull=True,
        )
        self.assertEqual(eco.value, 0.5)
        land = CharacterizationFactor.objects.get(
            commodity=com, category__key='impact_midpoint_ReCiPe2016_land_use',
            region__isnull=True, country__isnull=True,
        )
        self.assertEqual(land.value, 6.5)
        self.assertEqual(CharacterizationFactor.objects.filter(commodity=com).count(), 16)


def _get_category(key):
    from .models import ImpactCategory
    return ImpactCategory.objects.get(key=key)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.BackfillGlobalCfsTests`
Expected : FAIL (`No module named 'dashboard.migrations._cf_backfill'`).

- [ ] **Step 3 : Écrire le helper backfill + la migration**

Créer `dashboard/migrations/_cf_backfill.py` (préfixe `_` → non traité comme migration) :

```python
"""Backfill réutilisable : colonnes d'impact de Commodity → CF globales.

Séparé de la migration pour être testable ; utilise l'injection des modèles
afin de fonctionner aussi bien avec les modèles historiques (apps.get_model)
qu'avec les modèles courants (tests).
"""
from dashboard.services.impacts import LEGACY_IMPACT_COLUMNS


def backfill(Commodity, CharacterizationFactor, get_category):
    for commodity in Commodity.objects.all():
        for col in LEGACY_IMPACT_COLUMNS:
            value = getattr(commodity, col, 0.0)
            CharacterizationFactor.objects.get_or_create(
                commodity=commodity,
                category=get_category(col),
                region=None,
                country=None,
                defaults={'value': value},
            )
```

Créer `dashboard/migrations/00XX_backfill_global_cfs.py` :

```python
from django.db import migrations
from dashboard.migrations import _cf_backfill


def run(apps, schema_editor):
    Commodity = apps.get_model('dashboard', 'Commodity')
    CharacterizationFactor = apps.get_model('dashboard', 'CharacterizationFactor')
    ImpactCategory = apps.get_model('dashboard', 'ImpactCategory')
    cats = {c.key: c for c in ImpactCategory.objects.all()}
    _cf_backfill.backfill(Commodity, CharacterizationFactor, lambda key: cats[key])


def undo(apps, schema_editor):
    CharacterizationFactor = apps.get_model('dashboard', 'CharacterizationFactor')
    CharacterizationFactor.objects.filter(region__isnull=True, country__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '00YY_seed_impact_catalog'),
    ]
    operations = [migrations.RunPython(run, undo)]
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.BackfillGlobalCfsTests`
Expected : PASS.

- [ ] **Step 5 : Vérifier golden intact (les vues lisent encore les colonnes)**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.GoldenViewOutputTests`
Expected : PASS (rien n'a changé côté vues).

- [ ] **Step 6 : Commit**

```bash
git add dashboard/migrations/_cf_backfill.py dashboard/migrations/00XX_backfill_global_cfs.py dashboard/tests.py
git commit -m "feat(migration): backfill des CF globales depuis les colonnes Commodity"
```

---

### Task 7 : `populate_acme` crée aussi les CF globales

Nécessaire pour que le jeu golden (reconstruit à chaque test) porte des CF une fois les vues basculées.

**Files:**
- Modify: `dashboard/management/commands/populate_acme.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Consumes: `legacy_cf_rows` (service), `ImpactCategory` seedées.

- [ ] **Step 1 : Écrire le test**

```python
class PopulateAcmeCfTests(TestCase):

    def test_acme_commodities_have_global_cfs(self):
        from .models import Commodity, CharacterizationFactor
        call_command('populate_acme')
        soja = Commodity.objects.get(name='Soja')
        cf = CharacterizationFactor.objects.get(
            commodity=soja,
            category__key='impact_endpoint_ReCiPe2016_ecosystem_diversity',
            region__isnull=True, country__isnull=True,
        )
        self.assertAlmostEqual(cf.value, 0.0048, places=6)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.PopulateAcmeCfTests`
Expected : FAIL (`CharacterizationFactor ... DoesNotExist`).

- [ ] **Step 3 : Ajouter la création des CF dans populate_acme**

Dans `dashboard/management/commands/populate_acme.py`, ajouter en tête l'import :

```python
from dashboard.models import (
    Asset, Carbon_emission, Commodity, Company, Company_Policy, Company_Revenue,
    Company_Revenue_Sector, Country, DisclosureRequirement, E4Assessment,
    Ownership, Policy_Level, Policy_Subcategory, Policy_Type, Production,
    Sector, SubSector, SubnationalRegion, CharacterizationFactor, ImpactCategory,
)
from dashboard.services.impacts import legacy_cf_rows
```

Puis, juste après le bloc de création des 4 commodités (après la création de `palme`, avant `# ── Entreprise ──`), insérer :

```python
        # ── Facteurs de caractérisation globaux (miroir des valeurs ci-dessus) ──
        _categories = {c.key: c for c in ImpactCategory.objects.all()}
        for commodity in (ble, mais, soja, palme):
            values = {col: getattr(commodity, col, 0.0) for col, _ in legacy_cf_rows({})}
            for col, val in legacy_cf_rows(values):
                CharacterizationFactor.objects.get_or_create(
                    commodity=commodity, category=_categories[col],
                    region=None, country=None, defaults={'value': val},
                )
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.PopulateAcmeCfTests`
Expected : PASS.

- [ ] **Step 5 : Vérifier golden toujours vert**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.GoldenViewOutputTests`
Expected : PASS (CF ajoutées mais vues inchangées).

- [ ] **Step 6 : Commit**

```bash
git add dashboard/management/commands/populate_acme.py dashboard/tests.py
git commit -m "feat(seed): populate_acme crée les CF globales miroir des colonnes"
```

---

### Task 8 : Bascule `_get_company_data` (empreinte + dette éco) sur le service

**Files:**
- Modify: `dashboard/views.py` (fonction `_get_company_data`, ~lignes 277-411)
- Test: `dashboard/tests.py` (golden couvre déjà ; ajouter un test de régionalisation)

**Interfaces:**
- Consumes: `build_cf_index`, `cf_value`, `CAT_ECOSYSTEM_DIVERSITY`.

- [ ] **Step 1 : Écrire un test de régionalisation (nouveau comportement additif)**

```python
class CompanyDataRegionalCfTests(TestCase):

    def test_regional_cf_overrides_global_for_footprint(self):
        from .models import (
            Company, Country, SubnationalRegion, Commodity, Asset, Ownership,
            Production, ImpactCategory, CharacterizationFactor,
        )
        from .views import _get_company_data
        company = Company.objects.create(name='RegCorp')
        country = Country.objects.create(name='Brésil', water_ownership='X', land_ownership='Y')
        region = SubnationalRegion.objects.create(name='Pará', country=country)
        com = Commodity.objects.create(name='Soja')
        cat = ImpactCategory.objects.get(
            key='impact_endpoint_ReCiPe2016_ecosystem_diversity'
        )
        CharacterizationFactor.objects.create(category=cat, commodity=com, value=1.0)  # global
        CharacterizationFactor.objects.create(
            category=cat, commodity=com, region=region, value=5.0
        )  # régional
        asset = Asset.objects.create(
            name='Ferme', latitude=-3.0, longitude=-47.0,
            country=country, subnational_region=region,
        )
        Ownership.objects.create(Asset=asset, Company=company, ownership='100%')
        Production.objects.create(asset=asset, commodity=com, year=2024, production=10.0)
        data = _get_company_data(company)
        feature = data['geojson']['features'][0]
        # footprint = 10 * 5.0 (CF régional), pas 10 * 1.0 (global)
        self.assertAlmostEqual(feature['properties']['footprint'], 50.0, places=4)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.CompanyDataRegionalCfTests`
Expected : FAIL (la vue lit encore la colonne globale → footprint 0.0, car la colonne n'est pas renseignée).

- [ ] **Step 3 : Basculer la vue sur le service**

Dans `dashboard/views.py`, ajouter en tête du fichier (après les imports existants) :

```python
from .services.impacts import build_cf_index, cf_value, CAT_ECOSYSTEM_DIVERSITY
```

Dans `_get_company_data`, après la constitution de `assets` (vers la ligne 283), ajouter la construction de l'index CF :

```python
    cf_index = build_cf_index(
        commodity_ids=[p.commodity_id for a in assets for p in a.production_set.all()],
        category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )
```

Remplacer le calcul `footprint` (lignes ~321-323) :

```python
        footprint = sum(
            p.production * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
            for p in recent_prods
        )
```
par :
```python
        footprint = sum(
            p.production * cf_value(
                cf_index, p.commodity_id, CAT_ECOSYSTEM_DIVERSITY,
                asset.subnational_region_id, asset.country_id,
            )
            for p in recent_prods
        )
```

Remplacer, dans la boucle `dette_eco` (lignes ~338-342), le facteur commodité :

```python
            dette_eco += (
                biodiv_loss
                * restoration_cost
                * p.production
                * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
            )
```
par :
```python
            dette_eco += (
                biodiv_loss
                * restoration_cost
                * p.production
                * cf_value(
                    cf_index, p.commodity_id, CAT_ECOSYSTEM_DIVERSITY,
                    asset.subnational_region_id, asset.country_id,
                )
            )
```

- [ ] **Step 4 : Lancer les tests ciblés + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.CompanyDataRegionalCfTests dashboard.tests.CompanyDataViewTests dashboard.tests.GoldenViewOutputTests`
Expected : PASS (régionalisation OK ; golden inchangé car acme n'a que des CF globales == anciennes colonnes).

- [ ] **Step 5 : Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "refactor(views): _get_company_data via service CF régionalisé"
```

---

### Task 9 : Bascule `_get_mesure_empreinte_data`

**Files:**
- Modify: `dashboard/views.py` (`_get_mesure_empreinte_data`, ~lignes 414-530, calcul ligne 462)
- Modify: `dashboard/tests.py` (`MesureEmpreinteDataViewTests` : créer des CF au lieu de colonnes)

**Interfaces:**
- Consumes: `build_cf_index`, `cf_value`, `CAT_ECOSYSTEM_DIVERSITY`.

- [ ] **Step 1 : Ajouter le helper CF de test (une fois pour tout le fichier)**

Ajouter près du haut de `dashboard/tests.py` (après `_make_world`) :

```python
def _make_cf(commodity, category_key, value, region=None, country=None):
    from .models import ImpactCategory, CharacterizationFactor
    cat = ImpactCategory.objects.get(key=category_key)
    return CharacterizationFactor.objects.create(
        commodity=commodity, category=cat, value=value, region=region, country=country,
    )
```

- [ ] **Step 2 : Adapter le setup du test à la nouvelle API**

Dans `MesureEmpreinteDataViewTests._setup_company`, remplacer :

```python
        commodity = Commodity.objects.create(
            name='SojaRisk',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=impact_factor,
        )
```
par :
```python
        commodity = Commodity.objects.create(name='SojaRisk')
        _make_cf(commodity, 'impact_endpoint_ReCiPe2016_ecosystem_diversity', impact_factor)
```

Dans `test_two_commodities_pct_sum_to_one`, remplacer :

```python
        c1 = Commodity.objects.create(
            name='Maïs', impact_endpoint_ReCiPe2016_ecosystem_diversity=1.0
        )
        c2 = Commodity.objects.create(
            name='Blé', impact_endpoint_ReCiPe2016_ecosystem_diversity=3.0
        )
```
par :
```python
        c1 = Commodity.objects.create(name='Maïs')
        _make_cf(c1, 'impact_endpoint_ReCiPe2016_ecosystem_diversity', 1.0)
        c2 = Commodity.objects.create(name='Blé')
        _make_cf(c2, 'impact_endpoint_ReCiPe2016_ecosystem_diversity', 3.0)
```

- [ ] **Step 3 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.MesureEmpreinteDataViewTests`
Expected : FAIL (la vue lit la colonne → impact 0.0, CF ignorées).

- [ ] **Step 4 : Basculer la vue**

Dans `_get_mesure_empreinte_data`, après la constitution de `productions` (vers ligne 454), ajouter :

```python
    cf_index = build_cf_index(
        commodity_ids=[p.commodity_id for p in productions],
        category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )
```

Remplacer la ligne 462 :
```python
        impact = p.production * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
```
par :
```python
        impact = p.production * cf_value(
            cf_index, p.commodity_id, CAT_ECOSYSTEM_DIVERSITY,
            p.asset.subnational_region_id, p.asset.country_id,
        )
```

- [ ] **Step 5 : Lancer, vérifier le succès + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.MesureEmpreinteDataViewTests dashboard.tests.GoldenViewOutputTests`
Expected : PASS.

- [ ] **Step 6 : Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "refactor(views): mesure_empreinte via service CF"
```

---

### Task 10 : Bascule `_get_dette_ecologique_data`

**Files:**
- Modify: `dashboard/views.py` (`_get_dette_ecologique_data`, ~lignes 793-925 ; facteur ligne 850)
- Modify: `dashboard/tests.py` (`DetteEcologiqueDataTests` : CF au lieu de colonnes)

- [ ] **Step 1 : Adapter le setup + les tests**

Dans `DetteEcologiqueDataTests.setUp`, remplacer :

```python
        self.commodity_agri = Commodity.objects.create(
            name='Soja',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
            biodiversity_loss_class='Agriculture',
        )
```
par :
```python
        self.commodity_agri = Commodity.objects.create(
            name='Soja', biodiversity_loss_class='Agriculture',
        )
        _make_cf(self.commodity_agri, 'impact_endpoint_ReCiPe2016_ecosystem_diversity', 0.5)
```

Dans `test_lbiodiv_formula_urbanisation`, remplacer :
```python
        commodity_urb = Commodity.objects.create(
            name='Béton',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
            biodiversity_loss_class='Urbanisation',
        )
```
par :
```python
        commodity_urb = Commodity.objects.create(
            name='Béton', biodiversity_loss_class='Urbanisation',
        )
        _make_cf(commodity_urb, 'impact_endpoint_ReCiPe2016_ecosystem_diversity', 0.5)
```

Dans `test_lbiodiv_formula_mining`, remplacer :
```python
        commodity_min = Commodity.objects.create(
            name='Lithium',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
            biodiversity_loss_class='Mining',
        )
```
par :
```python
        commodity_min = Commodity.objects.create(
            name='Lithium', biodiversity_loss_class='Mining',
        )
        _make_cf(commodity_min, 'impact_endpoint_ReCiPe2016_ecosystem_diversity', 0.5)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.DetteEcologiqueDataTests`
Expected : FAIL (total_lbiodiv 0.0).

- [ ] **Step 3 : Basculer la vue**

Dans `_get_dette_ecologique_data`, après la constitution de `productions` (vers ligne 831), ajouter :

```python
    cf_index = build_cf_index(
        commodity_ids=[p.commodity_id for p in productions],
        category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )
```

Remplacer le bloc `lbiodiv` (lignes ~846-851) :
```python
        lbiodiv = (
            biodiv_loss
            * restoration
            * p.production
            * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
        )
```
par :
```python
        lbiodiv = (
            biodiv_loss
            * restoration
            * p.production
            * cf_value(
                cf_index, p.commodity_id, CAT_ECOSYSTEM_DIVERSITY,
                asset.subnational_region_id, asset.country_id,
            )
        )
```

- [ ] **Step 4 : Lancer, vérifier le succès + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.DetteEcologiqueDataTests dashboard.tests.GoldenViewOutputTests`
Expected : PASS.

- [ ] **Step 5 : Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "refactor(views): dette_ecologique via service CF"
```

---

### Task 11 : Bascule `_get_leap_prepare_data` (facteur global par commodity)

**Files:**
- Modify: `dashboard/views.py` (`_get_leap_prepare_data`, ~lignes 736-783 ; facteur ligne 765)
- Modify: `dashboard/tests.py` (`LeapPrepareDataTests`)

**Note :** `impact_factor` y est une valeur **par commodity** (sans asset) → on utilise le CF **global** (region=country=null), ce qui reproduit exactement l'ancienne colonne globale.

- [ ] **Step 1 : Adapter le setup**

Dans `LeapPrepareDataTests.setUp`, remplacer :
```python
        self.commodity = Commodity.objects.create(
            name='Soja', unit='tonnes',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
        )
```
par :
```python
        self.commodity = Commodity.objects.create(name='Soja', unit='tonnes')
        _make_cf(self.commodity, 'impact_endpoint_ReCiPe2016_ecosystem_diversity', 0.5)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.LeapPrepareDataTests`
Expected : FAIL (`impact_factor` 0.0).

- [ ] **Step 3 : Basculer la vue**

Dans `_get_leap_prepare_data`, après la constitution de `assets` (vers ligne 744), ajouter :
```python
    all_commodity_ids = [
        p.commodity_id for a in assets for p in a.production_set.all()
    ]
    cf_index = build_cf_index(
        commodity_ids=all_commodity_ids, category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )
```

Remplacer le bloc (lignes ~762-766) :
```python
            commodities.setdefault(c.pk, {
                'id': c.pk,
                'name': c.name,
                'impact_factor': c.impact_endpoint_ReCiPe2016_ecosystem_diversity,
            })
```
par :
```python
            commodities.setdefault(c.pk, {
                'id': c.pk,
                'name': c.name,
                'impact_factor': cf_value(
                    cf_index, c.pk, CAT_ECOSYSTEM_DIVERSITY,
                ),
            })
```

- [ ] **Step 4 : Lancer, vérifier le succès + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.LeapPrepareDataTests dashboard.tests.GoldenViewOutputTests`
Expected : PASS.

- [ ] **Step 5 : Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "refactor(views): leap_prepare via CF global par commodity"
```

---

### Task 12 : Bascule `_get_leap_evaluate_data` (11 midpoints)

**Files:**
- Modify: `dashboard/views.py` (`_get_leap_evaluate_data`, ~lignes 667-733 ; boucle 697-700)
- Modify: `dashboard/tests.py` (`LeapEvaluateDataTests`)

**Note :** `_EVALUATE_IMPACT_FIELDS` (lignes 652-664) garde ses clés (== clés de catégorie). Seul le calcul change.

- [ ] **Step 1 : Adapter le setup**

Dans `LeapEvaluateDataTests.setUp`, remplacer :
```python
        self.commodity = Commodity.objects.create(
            name='Soja',
            impact_midpoint_ReCiPe2016_land_use=4.0,
            impact_midpoint_ReCiPe2016_water_consumption=2.0,
        )
```
par :
```python
        self.commodity = Commodity.objects.create(name='Soja')
        _make_cf(self.commodity, 'impact_midpoint_ReCiPe2016_land_use', 4.0)
        _make_cf(self.commodity, 'impact_midpoint_ReCiPe2016_water_consumption', 2.0)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.LeapEvaluateDataTests`
Expected : FAIL (impacts à 0.0).

- [ ] **Step 3 : Basculer la vue**

Dans `_get_leap_evaluate_data`, après la constitution de `productions` (vers ligne 693), ajouter (on réutilise `assets`, déjà chargé avec `select_related('country', 'subnational_region')`, pour éviter tout N+1 sur `p.asset`) :
```python
    _evaluate_keys = [f for f, _ in _EVALUATE_IMPACT_FIELDS]
    asset_loc = {a.pk: (a.subnational_region_id, a.country_id) for a in assets}
    cf_index = build_cf_index(
        commodity_ids=[p.commodity_id for p in productions],
        category_keys=_evaluate_keys,
    )
```

Remplacer la boucle (lignes ~697-700) :
```python
    for p in productions:
        ai = asset_impacts[p.asset_id]
        for f, _ in _EVALUATE_IMPACT_FIELDS:
            ai[f] += p.production * getattr(p.commodity, f, 0.0)
```
par :
```python
    for p in productions:
        ai = asset_impacts[p.asset_id]
        region_id, country_id = asset_loc.get(p.asset_id, (None, None))
        for f in _evaluate_keys:
            ai[f] += p.production * cf_value(
                cf_index, p.commodity_id, f, region_id, country_id,
            )
```

- [ ] **Step 4 : Lancer, vérifier le succès + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.LeapEvaluateDataTests dashboard.tests.GoldenViewOutputTests`
Expected : PASS.

- [ ] **Step 5 : Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "refactor(views): leap_evaluate (midpoints) via service CF"
```

---

### Task 13 : Bascule `_get_comparison_data` (16 catégories)

**Files:**
- Modify: `dashboard/views.py` (`_get_comparison_data`, ~lignes 1068-1130 ; boucle 1106-1107 et dette 1116-1121)
- Modify: `dashboard/tests.py` (ajouter un test ciblé — aucun test unitaire n'existe pour cette vue)

- [ ] **Step 1 : Écrire un test de la vue comparaison sur CF**

```python
class ComparisonDataCfTests(TestCase):

    def test_totals_use_cf(self):
        from .models import (
            Company, Country, SubnationalRegion, Commodity, Asset, Ownership, Production,
        )
        from .views import _get_comparison_data
        company = Company.objects.create(name='CmpCorp')
        country = Country.objects.create(name='France', water_ownership='X', land_ownership='Y')
        region = SubnationalRegion.objects.create(
            name='IDF', country=country, restoration_cost_m2=10.0
        )
        com = Commodity.objects.create(name='Soja', biodiversity_loss_class='Agriculture')
        _make_cf(com, 'impact_midpoint_ReCiPe2016_land_use', 4.0)
        _make_cf(com, 'impact_endpoint_ReCiPe2016_ecosystem_diversity', 0.5)
        asset = Asset.objects.create(
            name='S', latitude=48.0, longitude=2.0, country=country, subnational_region=region,
        )
        Ownership.objects.create(Asset=asset, Company=company, ownership='100%')
        Production.objects.create(asset=asset, commodity=com, year=2024, production=10.0)
        data = _get_comparison_data(company)
        self.assertAlmostEqual(data['total_impact_midpoint_ReCiPe2016_land_use'], 40.0, places=2)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.ComparisonDataCfTests`
Expected : FAIL (total 0.0).

- [ ] **Step 3 : Basculer la vue**

Dans `_get_comparison_data`, après la constitution de `productions` (vers ligne 1098), ajouter :
```python
    _impact_keys = [f for f, _ in _IMPACT_FIELDS]
    cf_index = build_cf_index(
        commodity_ids=[p.commodity_id for p in productions],
        category_keys=_impact_keys,
    )
```

Remplacer, dans la boucle `for p in productions:` (lignes ~1106-1107) :
```python
        for f, _ in _IMPACT_FIELDS:
            impact_totals[f] += p.production * getattr(p.commodity, f, 0.0)
```
par :
```python
        for f in _impact_keys:
            impact_totals[f] += p.production * cf_value(
                cf_index, p.commodity_id, f,
                asset.subnational_region_id if asset else None,
                asset.country_id if asset else None,
            )
```

**Note :** dans cette boucle, `asset = asset_map.get(p.asset_id)` est déjà défini plus bas (ligne ~1111) ; déplacer cette ligne AVANT la boucle `for f` (juste après `for p in productions:`) pour qu'`asset` soit disponible. Concrètement, remplacer :
```python
    for p in productions:
        for f, _ in _IMPACT_FIELDS:
            impact_totals[f] += p.production * getattr(p.commodity, f, 0.0)
        for f, _ in _DEPENDENCY_FIELDS:
            dep_scores[f].append(SCORE_MAP.get(getattr(p.commodity, f, 'VL'), 0.0))

        asset = asset_map.get(p.asset_id)
```
par :
```python
    for p in productions:
        asset = asset_map.get(p.asset_id)
        for f in _impact_keys:
            impact_totals[f] += p.production * cf_value(
                cf_index, p.commodity_id, f,
                asset.subnational_region_id if asset else None,
                asset.country_id if asset else None,
            )
        for f, _ in _DEPENDENCY_FIELDS:
            dep_scores[f].append(SCORE_MAP.get(getattr(p.commodity, f, 'VL'), 0.0))
```

Remplacer aussi, dans le calcul `total_lbiodiv` (lignes ~1116-1121), le facteur commodité :
```python
            total_lbiodiv += (
                getattr(asset.country, biodiv_field, 0.0)
                * asset.subnational_region.restoration_cost_m2
                * p.production
                * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
            )
```
par :
```python
            total_lbiodiv += (
                getattr(asset.country, biodiv_field, 0.0)
                * asset.subnational_region.restoration_cost_m2
                * p.production
                * cf_value(
                    cf_index, p.commodity_id, CAT_ECOSYSTEM_DIVERSITY,
                    asset.subnational_region_id, asset.country_id,
                )
            )
```

- [ ] **Step 4 : Lancer, vérifier le succès + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.ComparisonDataCfTests dashboard.tests.GoldenViewOutputTests`
Expected : PASS.

- [ ] **Step 5 : Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "refactor(views): comparaison (16 catégories) via service CF"
```

---

### Task 14 : Nettoyage — suppression des 16 colonnes + admin + vérification globale

**Files:**
- Modify: `dashboard/models.py` (retirer les 16 champs `impact_*` de `Commodity`)
- Modify: `dashboard/management/commands/populate_acme.py` (retirer les kwargs `impact_*`)
- Modify: `dashboard/admin.py` (enregistrer les 3 nouveaux modèles)
- Create: `dashboard/migrations/00XX_drop_commodity_impact_columns.py`
- Test: `dashboard/tests.py`

- [ ] **Step 1 : Écrire le test de suppression**

```python
class CommodityColumnsDroppedTests(TestCase):

    def test_impact_columns_removed(self):
        from .models import Commodity
        com = Commodity.objects.create(name='X')
        self.assertFalse(hasattr(com, 'impact_endpoint_ReCiPe2016_ecosystem_diversity'))
        self.assertFalse(hasattr(com, 'impact_midpoint_ReCiPe2016_land_use'))

    def test_dependency_fields_still_present(self):
        from .models import Commodity
        com = Commodity.objects.create(name='X', dependency_water='H')
        self.assertEqual(com.dependency_water, 'H')
        self.assertEqual(com.biodiversity_loss_class, 'Agriculture')
```

- [ ] **Step 2 : Retirer les kwargs `impact_*` de populate_acme**

Dans `dashboard/management/commands/populate_acme.py`, retirer des 4 blocs `Commodity.objects.get_or_create(...)` toutes les lignes `"impact_midpoint_..."` et `"impact_endpoint_..."`, MAIS conserver le bloc de création des CF (Task 7) — il devient la **seule** source des valeurs. Déplacer les valeurs numériques dans un dict local juste avant la création des CF.

Remplacer, pour `ble`, le `defaults` :
```python
            defaults={
                "description": "Triticum aestivum — céréale tempérée",
                "unit": "tonnes",
                "impact_midpoint_ReCiPe2016_water_consumption": 1.21,
                "impact_midpoint_ReCiPe2016_climate_change": 0.29,
                "impact_midpoint_ReCiPe2016_freshwater_ecotoxicity": 0.008,
                "impact_midpoint_ReCiPe2016_land_use": 2.8,
                "impact_endpoint_ReCiPe2016_ecosystem_diversity": 0.0014,
                "impact_endpoint_GBS_terrestrial_dynamic": 0.42,
                "impact_endpoint_GBS_terrestrial_static": 0.38,
                "dependency_water": "H",
                ...
                "biodiversity_loss_class": "Agriculture",
            },
```
par (garder uniquement description/unit/dependency/biodiversity_loss_class) :
```python
            defaults={
                "description": "Triticum aestivum — céréale tempérée",
                "unit": "tonnes",
                "dependency_water": "H",
                "dependency_pollination": "L",
                "dependency_soil_quality": "VH",
                "dependency_carbon_sequestration": "M",
                "dependency_water_purification": "H",
                "dependency_pest_control": "H",
                "biodiversity_loss_class": "Agriculture",
            },
```

Faire de même pour `mais`, `soja`, `palme` (retirer les 7 kwargs `impact_*`). Puis remplacer le bloc CF de la Task 7 par une version portant les valeurs explicitement :

```python
        # ── Facteurs de caractérisation globaux ────────────────────────────────
        _cf_values = {
            ble: {
                'impact_midpoint_ReCiPe2016_water_consumption': 1.21,
                'impact_midpoint_ReCiPe2016_climate_change': 0.29,
                'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity': 0.008,
                'impact_midpoint_ReCiPe2016_land_use': 2.8,
                'impact_endpoint_ReCiPe2016_ecosystem_diversity': 0.0014,
                'impact_endpoint_GBS_terrestrial_dynamic': 0.42,
                'impact_endpoint_GBS_terrestrial_static': 0.38,
            },
            mais: {
                'impact_midpoint_ReCiPe2016_water_consumption': 1.58,
                'impact_midpoint_ReCiPe2016_climate_change': 0.33,
                'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity': 0.012,
                'impact_midpoint_ReCiPe2016_land_use': 3.1,
                'impact_endpoint_ReCiPe2016_ecosystem_diversity': 0.0017,
                'impact_endpoint_GBS_terrestrial_dynamic': 0.48,
                'impact_endpoint_GBS_terrestrial_static': 0.43,
            },
            soja: {
                'impact_midpoint_ReCiPe2016_water_consumption': 2.14,
                'impact_midpoint_ReCiPe2016_climate_change': 0.72,
                'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity': 0.021,
                'impact_midpoint_ReCiPe2016_land_use': 6.5,
                'impact_endpoint_ReCiPe2016_ecosystem_diversity': 0.0048,
                'impact_endpoint_GBS_terrestrial_dynamic': 1.12,
                'impact_endpoint_GBS_terrestrial_static': 0.95,
            },
            palme: {
                'impact_midpoint_ReCiPe2016_water_consumption': 3.45,
                'impact_midpoint_ReCiPe2016_climate_change': 1.82,
                'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity': 0.038,
                'impact_midpoint_ReCiPe2016_land_use': 12.0,
                'impact_endpoint_ReCiPe2016_ecosystem_diversity': 0.0095,
                'impact_endpoint_GBS_terrestrial_dynamic': 2.45,
                'impact_endpoint_GBS_terrestrial_static': 2.10,
            },
        }
        _categories = {c.key: c for c in ImpactCategory.objects.all()}
        for commodity, values in _cf_values.items():
            for col, val in legacy_cf_rows(values):
                CharacterizationFactor.objects.get_or_create(
                    commodity=commodity, category=_categories[col],
                    region=None, country=None, defaults={'value': val},
                )
```

- [ ] **Step 3 : Retirer les 16 champs de `Commodity`**

Dans `dashboard/models.py`, supprimer de la classe `Commodity` les 16 lignes `impact_midpoint_*` / `impact_endpoint_*` (lignes ~40-56). Conserver `name`, `description`, `unit`, les 6 `dependency_*`, `biodiversity_loss_class`.

**Retirer aussi le test devenu obsolète** : dans `dashboard/tests.py`, supprimer la classe `BackfillGlobalCfsTests` **et** la fonction module `_get_category` qu'elle utilise (Task 6) — elles créent une `Commodity(impact_...=...)` qui n'existe plus. La migration de backfill reste couverte par les golden tests (équivalence colonnes→CF déjà figée). Ne pas toucher aux autres classes (déjà adaptées aux CF en Tasks 9-12).

- [ ] **Step 4 : Générer la migration de suppression**

Run : `.venv\Scripts\python.exe manage.py makemigrations dashboard --name drop_commodity_impact_columns`
Expected : `Remove field impact_... from commodity` ×16.

- [ ] **Step 5 : Enregistrer les nouveaux modèles dans l'admin**

Dans `dashboard/admin.py`, ajouter aux imports `ImpactMethod, ImpactCategory, CharacterizationFactor` et en fin de fichier :

```python
@admin.register(ImpactMethod)
class ImpactMethodAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    list_display = ('name', 'version')


@admin.register(ImpactCategory)
class ImpactCategoryAdmin(admin.ModelAdmin):
    search_fields = ('key', 'name')
    list_display = ('key', 'method', 'level', 'theme')
    list_filter = ('method', 'level')
    autocomplete_fields = ('method',)


@admin.register(CharacterizationFactor)
class CharacterizationFactorAdmin(admin.ModelAdmin):
    search_fields = ('commodity__name', 'category__key')
    list_display = ('commodity', 'category', 'region', 'country', 'value')
    list_filter = ('category__method', 'category__level')
    autocomplete_fields = ('category', 'commodity', 'region', 'country')
```

Ajouter `search_fields` à `ImpactMethodAdmin` est requis par les `autocomplete_fields` — déjà présent ci-dessus.

- [ ] **Step 6 : Lancer TOUTE la suite + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard`
Expected : PASS (toute la suite, golden inclus).

- [ ] **Step 7 : Vérifier qu'aucune référence aux colonnes ne subsiste**

Run : `git grep -n "impact_endpoint_ReCiPe2016_ecosystem_diversity\|impact_midpoint_ReCiPe2016" -- dashboard/models.py dashboard/views.py`
Expected : les seules occurrences sont des **clés de catégorie** (chaînes dans `_IMPACT_FIELDS`, `_EVALUATE_IMPACT_FIELDS`, `CAT_ECOSYSTEM_DIVERSITY`), **aucun** `getattr`/attribut de modèle.

- [ ] **Step 8 : Commit**

```bash
git add dashboard/models.py dashboard/admin.py dashboard/management/commands/populate_acme.py dashboard/migrations/00XX_drop_commodity_impact_columns.py dashboard/tests.py
git commit -m "refactor: supprime les colonnes d'impact de Commodity (CF = source unique)"
```

---

## Self-Review

**Couverture du spec (Plan A) :**
- §5.1 catalogue (ImpactMethod/ImpactCategory) → Tasks 2, 4. `Flow` est **hors Plan A** (Plan C).
- §5.2 CharacterizationFactor régionalisé → Task 3.
- §6/§7 service + fallback → Task 5.
- §8.1-8.2 seed + backfill → Tasks 4, 6.
- §8.5 bascule vues (chemin ACV) → Tasks 8-13.
- §8.6 nettoyage (drop colonnes) → Task 14.
- §9 mise à jour pages ACV → Tasks 8-13 (+ populate_acme Tasks 7, 14 ; admin Task 14).
- §11 golden + fallback + tests → Tasks 1, 5, et tests par vue.
- Hors périmètre Plan A : `leap_locate`/`dependencies`/`physical_risk` (B), `AssetInventory` (C). Le `theme` est seedé (Task 4) mais exploité en C.

**Scan placeholders :** aucun « TBD/TODO ». Les `00XX`/`00YY` sont des numéros de migration à résoudre à la génération (instructions explicites données).

**Cohérence des types/noms :** `cf_value(cf_index, commodity_id, category_key, region_id, country_id)`, `build_cf_index(commodity_ids, category_keys)`, `CAT_ECOSYSTEM_DIVERSITY`, `_make_cf(commodity, category_key, value, region, country)` — signatures identiques entre définition (Task 5) et usages (Tasks 8-13). `ImpactCategory.key` == nom de colonne legacy partout.

**Point d'attention connu :** la double définition des 16 clés (migration seed Task 4 + `LEGACY_IMPACT_COLUMNS` Task 5) est volontaire (migration figée vs constante runtime). Les valeurs numériques d'acme existent en deux endroits transitoirement (colonnes + CF) jusqu'à la Task 14 qui supprime les colonnes.
