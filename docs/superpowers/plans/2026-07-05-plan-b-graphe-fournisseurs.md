# Plan B — Graphe fournisseurs (SupplyNode / Exchange) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le duo `Production.scope` (enum plat) + `Supply_chain` (Asset↔Asset) par un graphe dirigé `SupplyNode` (résolution variable asset/région/pays) + `Exchange` multi-tiers, avec `Production.tier` (entier) comme vocabulaire unifié — sans changer la forme JSON de sortie des vues.

**Architecture:** `SupplyNode` est un sommet dont la localisation peut être un `Asset` précis ou un couple `(région|pays)`. `Exchange` est une arête dirigée fournisseur→consommateur (multi-tiers). `Production.tier` (PositiveSmallInteger) remplace `Production.scope`. Un module `dashboard/services/supply.py` porte le vocabulaire `tier` partagé et la traversée `upstream_chain`. Les vues `dependencies` et `leap_locate` basculent sur ces modèles ; leur sortie JSON reste identique (filet golden).

**Tech Stack:** Django 5 (TestCase), SQLite. Aucune dépendance nouvelle.

## Global Constraints

- Python **3.11+**, PEP 8, lignes **≤ 100 caractères**.
- **Aucun** framework frontend ; **aucune** dépendance nouvelle.
- **Compatible SQLite** : `FloatField`/`FK`/`CharField`/`IntegerField`/`PositiveSmallIntegerField`/`BooleanField`/`DateTime`. Pas de PostGIS, pas de `JSONField` Postgres-only.
- On **reste dans l'app `dashboard`** (sauf le nécessaire dans `imports`).
- **La forme JSON de sortie des vues `dependencies` et `leap_locate` reste identique** (golden). En particulier, `dependencies` continue d'émettre la clé `scope` (chaîne `direct`/`tier 1`/…) dérivée de `tier`.
- **Une migration = un changement logique** ; migrations réversibles et **auto-suffisantes** (pas d'import de constante vivante — leçon Plan A).
- Commande de test : `.venv\Scripts\python.exe manage.py test dashboard` (Windows PowerShell). Suite projet : `.venv\Scripts\python.exe manage.py test`.
- Ne redirige jamais la sortie des tests vers un fichier du repo.
- Dernière migration existante : `0028_drop_commodity_impact_columns` → les nouvelles migrations s'enchaînent à partir de `0029`.

## File Structure

- `dashboard/models.py` — ajoute `SupplyNode`, `Exchange` (fin de fichier) ; ajoute `Production.tier` ; à la fin, retire `Production.scope` et le modèle `Supply_chain`.
- `dashboard/services/supply.py` — **nouveau** : `TIER_LABELS`, `SCOPE_TO_TIER`, `TIER_TO_SCOPE`, `TIER_DIRECT/1/2/RAW`, `upstream_chain(...)`.
- `dashboard/migrations/0029..0034` — schéma + data (une par tâche).
- `dashboard/migrations/_scope_tier.py`, `_supply_chain_to_graph.py` — helpers de data migration **figés** (préfixe `_`, non traités comme migrations).
- `dashboard/views.py` — bascule `_get_dependencies_data` (scope→tier) et `_get_leap_locate_data` (Supply_chain→Exchange). Constantes `_SCOPE_LABELS`/`_SCOPE_ORDER` remplacées par les imports depuis `services/supply.py`.
- `dashboard/tests.py` — étend `GOLDEN_VIEWS` ; adapte `DependenciesDataTests` (scope→tier) et `LeapLocateDataTests` (Supply_chain→Exchange) ; ajoute tests modèles + service.
- `dashboard/admin.py` — enregistre `SupplyNode`/`Exchange` ; retire `Supply_chain` au nettoyage.
- `dashboard/management/commands/populate_acme.py` — `Production` créé avec `tier` (mappé depuis les scopes actuels).
- `imports/services/importer.py` + `imports/services/constants.py` — `_import_production` mappe la colonne `scope` de la feuille vers `tier`.

**Contrat clé :** `TIER_LABELS[tier]` reproduit exactement l'ancien `_SCOPE_LABELS[scope]`, et `dependencies` émet `scope = TIER_TO_SCOPE[tier]` → forme de sortie inchangée. `Supply_chain` d'acme est **vide** (populate_acme n'en crée pas) → la partie `suppliers`/`supplier_links` de `leap_locate` reste vide (golden invariant) ; le graphe est exercé par les tests unitaires.

---

### Task 1 : Étendre le filet golden aux 2 vues de B

Capture la sortie ACTUELLE de `dependencies` et `leap_locate` avant toute modification.

**Files:**
- Modify: `dashboard/tests.py` (liste `GOLDEN_VIEWS`)
- Modify: `dashboard/golden/` (2 nouveaux fichiers via record)

**Interfaces:**
- Consumes: `GoldenViewOutputTests` (Plan A), `GOLDEN_VIEWS`.

- [ ] **Step 1 : Ajouter les 2 vues à GOLDEN_VIEWS**

Dans `dashboard/tests.py`, dans la liste `GOLDEN_VIEWS`, ajouter deux entrées :
```python
    ('dependencies',        'dashboard:dependencies_data'),
    ('leap_locate',         'dashboard:leap_locate_data'),
```

- [ ] **Step 2 : Enregistrer la référence**

Run (PowerShell) :
```
$env:GOLDEN_RECORD=1; .venv\Scripts\python.exe manage.py test dashboard.tests.GoldenViewOutputTests; Remove-Item Env:\GOLDEN_RECORD
```
Expected : `OK` ; `dashboard/golden/dependencies.json` et `dashboard/golden/leap_locate.json` créés (leap_locate a `suppliers.features == []` et `supplier_links.features == []` sur acme).

- [ ] **Step 3 : Vérifier le mode assert**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.GoldenViewOutputTests`
Expected : PASS.

- [ ] **Step 4 : Commit**

```bash
git add dashboard/tests.py dashboard/golden/dependencies.json dashboard/golden/leap_locate.json
git commit -m "test(golden): fige dependencies et leap_locate (baseline pré-graphe)"
```

---

### Task 2 : Vocabulaire `tier` partagé (`services/supply.py`)

**Files:**
- Create: `dashboard/services/supply.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces: `TIER_DIRECT=0`, `TIER_1=1`, `TIER_2=2`, `TIER_RAW=3` ; `TIER_LABELS: dict[int,str]` ; `SCOPE_TO_TIER: dict[str,int]` ; `TIER_TO_SCOPE: dict[int,str]`.

- [ ] **Step 1 : Écrire le test**

```python
class TierVocabTests(TestCase):

    def test_labels_match_legacy_scope_labels(self):
        from .services.supply import TIER_LABELS, TIER_TO_SCOPE, SCOPE_TO_TIER
        self.assertEqual(TIER_LABELS[0], 'Opérations directes')
        self.assertEqual(TIER_LABELS[1], "Tier 1 : Chaîne d'approvisionnement")
        self.assertEqual(TIER_LABELS[2], 'Tier 2 : Approvisionnement amont')
        self.assertEqual(TIER_LABELS[3], 'Matières premières')

    def test_scope_tier_roundtrip(self):
        from .services.supply import SCOPE_TO_TIER, TIER_TO_SCOPE
        self.assertEqual(SCOPE_TO_TIER['direct'], 0)
        self.assertEqual(SCOPE_TO_TIER['tier 1'], 1)
        self.assertEqual(SCOPE_TO_TIER['tier 2'], 2)
        self.assertEqual(SCOPE_TO_TIER['raw material'], 3)
        for scope, tier in SCOPE_TO_TIER.items():
            self.assertEqual(TIER_TO_SCOPE[tier], scope)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.TierVocabTests`
Expected : FAIL (`No module named 'dashboard.services.supply'`).

- [ ] **Step 3 : Écrire le module**

Créer `dashboard/services/supply.py` :
```python
"""Service du graphe fournisseurs : vocabulaire des tiers et traversée amont.

`TIER_LABELS[tier]` reproduit exactement l'ancien `_SCOPE_LABELS[scope]` ;
`TIER_TO_SCOPE` permet aux vues d'émettre la même clé `scope` qu'avant.
"""
TIER_DIRECT, TIER_1, TIER_2, TIER_RAW = 0, 1, 2, 3

TIER_LABELS = {
    0: 'Opérations directes',
    1: "Tier 1 : Chaîne d'approvisionnement",
    2: 'Tier 2 : Approvisionnement amont',
    3: 'Matières premières',
}

SCOPE_TO_TIER = {'direct': 0, 'tier 1': 1, 'tier 2': 2, 'raw material': 3}
TIER_TO_SCOPE = {tier: scope for scope, tier in SCOPE_TO_TIER.items()}
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.TierVocabTests`
Expected : PASS.

- [ ] **Step 5 : Commit**

```bash
git add dashboard/services/supply.py dashboard/tests.py
git commit -m "feat(service): vocabulaire tier partagé (TIER_LABELS/SCOPE_TO_TIER)"
```

---

### Task 3 : Modèle `SupplyNode`

**Files:**
- Modify: `dashboard/models.py` (fin de fichier)
- Create: `dashboard/migrations/0029_supplynode.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces: `SupplyNode(asset?, region?, country?, commodity?, name, is_external, created_at, updated_at)` ; propriétés `resolution`, `effective_region_id`, `effective_country_id` ; `clean()` exige ≥1 localisation.

- [ ] **Step 1 : Écrire le test**

```python
class SupplyNodeModelTests(TestCase):

    def _country_region(self):
        from .models import Country, SubnationalRegion
        c = Country.objects.create(name='Brésil', water_ownership='X', land_ownership='Y')
        r = SubnationalRegion.objects.create(name='Pará', country=c)
        return c, r

    def test_asset_node_resolution_and_effective_location(self):
        from .models import SupplyNode, Asset
        c, r = self._country_region()
        a = Asset.objects.create(name='Ferme', latitude=-3.0, longitude=-47.0, country=c,
                                 subnational_region=r)
        node = SupplyNode.objects.create(asset=a)
        self.assertEqual(node.resolution, 'asset')
        self.assertEqual(node.effective_region_id, r.pk)
        self.assertEqual(node.effective_country_id, c.pk)

    def test_country_node_resolution(self):
        from .models import SupplyNode
        c, r = self._country_region()
        node = SupplyNode.objects.create(country=c, name='Fournisseur BR')
        self.assertEqual(node.resolution, 'country')
        self.assertIsNone(node.effective_region_id)
        self.assertEqual(node.effective_country_id, c.pk)

    def test_clean_requires_a_location(self):
        from django.core.exceptions import ValidationError
        from .models import SupplyNode
        with self.assertRaises(ValidationError):
            SupplyNode(name='vide').clean()
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.SupplyNodeModelTests`
Expected : FAIL (`cannot import name 'SupplyNode'`).

- [ ] **Step 3 : Ajouter le modèle**

À la fin de `dashboard/models.py` :
```python
class SupplyNode(models.Model):
    """Sommet du graphe fournisseurs, à résolution variable (asset/région/pays)."""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, null=True, blank=True)
    region = models.ForeignKey(
        SubnationalRegion, on_delete=models.CASCADE, null=True, blank=True
    )
    country = models.ForeignKey(Country, on_delete=models.CASCADE, null=True, blank=True)
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255, blank=True)
    is_external = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if not (self.asset_id or self.region_id or self.country_id):
            raise ValidationError(
                'Un SupplyNode requiert au moins asset, region ou country.'
            )

    @property
    def resolution(self):
        if self.asset_id:
            return 'asset'
        if self.region_id:
            return 'region'
        return 'country'

    @property
    def effective_region_id(self):
        return self.asset.subnational_region_id if self.asset_id else self.region_id

    @property
    def effective_country_id(self):
        return self.asset.country_id if self.asset_id else self.country_id

    def __str__(self):
        if self.asset_id:
            return self.asset.name
        return self.name or f'{self.resolution} node #{self.pk}'
```

- [ ] **Step 4 : Générer la migration**

Run : `.venv\Scripts\python.exe manage.py makemigrations dashboard --name supplynode`
Expected : `0029_supplynode.py` (Create model SupplyNode).

- [ ] **Step 5 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.SupplyNodeModelTests`
Expected : PASS.

- [ ] **Step 6 : Commit**

```bash
git add dashboard/models.py dashboard/migrations/0029_supplynode.py dashboard/tests.py
git commit -m "feat(models): SupplyNode (graphe fournisseurs, résolution variable)"
```

---

### Task 4 : Modèle `Exchange`

**Files:**
- Modify: `dashboard/models.py` (après `SupplyNode`)
- Create: `dashboard/migrations/0030_exchange.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces: `Exchange(supplier→SupplyNode 'outgoing', consumer→SupplyNode 'incoming', commodity, quantity, year, tier, data_confidence, created_at, updated_at, created_by)`.

- [ ] **Step 1 : Écrire le test**

```python
class ExchangeModelTests(TestCase):

    def test_directed_edge(self):
        from .models import Exchange, SupplyNode, Asset, Country, Commodity
        c = Country.objects.create(name='Brésil', water_ownership='X', land_ownership='Y')
        a1 = Asset.objects.create(name='Usine', latitude=0.0, longitude=0.0, country=c)
        a2 = Asset.objects.create(name='Ferme', latitude=-3.0, longitude=-47.0, country=c)
        consumer = SupplyNode.objects.create(asset=a1)
        supplier = SupplyNode.objects.create(asset=a2)
        com = Commodity.objects.create(name='Soja')
        ex = Exchange.objects.create(
            supplier=supplier, consumer=consumer, commodity=com,
            quantity=100.0, year=2024, tier=1,
        )
        self.assertEqual(consumer.incoming.count(), 1)
        self.assertEqual(supplier.outgoing.count(), 1)
        self.assertEqual(ex.tier, 1)
        self.assertEqual(ex.data_confidence, 'country')
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.ExchangeModelTests`
Expected : FAIL (`cannot import name 'Exchange'`).

- [ ] **Step 3 : Ajouter le modèle**

Après `SupplyNode` dans `dashboard/models.py` :
```python
class Exchange(models.Model):
    """Arête dirigée fournisseur → consommateur du graphe d'approvisionnement."""
    supplier = models.ForeignKey(
        SupplyNode, on_delete=models.CASCADE, related_name='outgoing'
    )
    consumer = models.ForeignKey(
        SupplyNode, on_delete=models.CASCADE, related_name='incoming'
    )
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE)
    quantity = models.FloatField()
    year = models.IntegerField()
    tier = models.PositiveSmallIntegerField(default=0)
    data_confidence = models.CharField(
        max_length=16,
        choices=[('asset', 'asset'), ('region', 'region'), ('country', 'country')],
        default='country',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f'{self.supplier} → {self.consumer} ({self.commodity.name}, {self.year})'
```

- [ ] **Step 4 : Générer la migration**

Run : `.venv\Scripts\python.exe manage.py makemigrations dashboard --name exchange`
Expected : `0030_exchange.py`.

- [ ] **Step 5 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.ExchangeModelTests`
Expected : PASS.

- [ ] **Step 6 : Commit**

```bash
git add dashboard/models.py dashboard/migrations/0030_exchange.py dashboard/tests.py
git commit -m "feat(models): Exchange (arête dirigée multi-tiers)"
```

---

### Task 5 : `Production.tier` + backfill depuis `scope`

**Files:**
- Modify: `dashboard/models.py` (`Production` : ajouter `tier`)
- Create: `dashboard/migrations/0031_production_tier.py` (auto) + `dashboard/migrations/0032_backfill_production_tier.py` (data) + `dashboard/migrations/_scope_tier.py` (helper figé)
- Test: `dashboard/tests.py`

**Interfaces:**
- Consumes: `SCOPE_TO_TIER` (concept ; le helper de migration fige sa propre copie).
- Produces: `Production.tier` (PositiveSmallInteger, default 0), backfillé depuis `scope`. `scope` reste présent (retiré au nettoyage, Task 12).

- [ ] **Step 1 : Écrire le test (backfill helper, pur)**

```python
class ProductionTierBackfillTests(TestCase):

    def test_backfill_maps_scope_to_tier(self):
        from .models import Production, Commodity, Company
        from dashboard.migrations import _scope_tier
        com = Commodity.objects.create(name='Soja')
        company = Company.objects.create(name='C')
        p_direct = Production.objects.create(
            commodity=com, company=company, year=2024, production=1.0, scope='direct'
        )
        p_t1 = Production.objects.create(
            commodity=com, company=company, year=2024, production=1.0, scope='tier 1'
        )
        _scope_tier.backfill(Production)
        p_direct.refresh_from_db()
        p_t1.refresh_from_db()
        self.assertEqual(p_direct.tier, 0)
        self.assertEqual(p_t1.tier, 1)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.ProductionTierBackfillTests`
Expected : FAIL (`Production has no field named 'tier'` puis module absent).

- [ ] **Step 3 : Ajouter le champ `tier` sur `Production`**

Dans `dashboard/models.py`, classe `Production`, ajouter après `scope` :
```python
    tier = models.PositiveSmallIntegerField(default=0)
```

- [ ] **Step 4 : Migration de schéma + helper figé + data migration**

Run : `.venv\Scripts\python.exe manage.py makemigrations dashboard --name production_tier`
Expected : `0031_production_tier.py` (AddField tier).

Créer `dashboard/migrations/_scope_tier.py` (helper figé, préfixe `_` = non-migration) :
```python
"""Backfill figé scope→tier pour Production (instantané de migration)."""
_SCOPE_TO_TIER = {'direct': 0, 'tier 1': 1, 'tier 2': 2, 'raw material': 3}


def backfill(Production):
    for scope, tier in _SCOPE_TO_TIER.items():
        Production.objects.filter(scope=scope).update(tier=tier)
```

Créer `dashboard/migrations/0032_backfill_production_tier.py` :
```python
from django.db import migrations
from dashboard.migrations import _scope_tier


def run(apps, schema_editor):
    Production = apps.get_model('dashboard', 'Production')
    _scope_tier.backfill(Production)


def undo(apps, schema_editor):
    Production = apps.get_model('dashboard', 'Production')
    Production.objects.update(tier=0)


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0031_production_tier')]
    operations = [migrations.RunPython(run, undo)]
```

- [ ] **Step 5 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.ProductionTierBackfillTests`
Expected : PASS.

- [ ] **Step 6 : Commit**

```bash
git add dashboard/models.py dashboard/migrations/0031_production_tier.py dashboard/migrations/0032_backfill_production_tier.py dashboard/migrations/_scope_tier.py dashboard/tests.py
git commit -m "feat(models): Production.tier + backfill depuis scope"
```

---

### Task 6 : Data migration `Supply_chain` → `SupplyNode` + `Exchange`

**Files:**
- Create: `dashboard/migrations/_supply_chain_to_graph.py` (helper figé) + `dashboard/migrations/0033_migrate_supply_chain.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces (en base) : pour chaque `Supply_chain`, un `SupplyNode(asset=asset)` consommateur, un `SupplyNode(asset=supplier)` fournisseur, un `Exchange(tier=1, data_confidence dérivé)`.

- [ ] **Step 1 : Écrire le test (helper)**

```python
class SupplyChainToGraphTests(TestCase):

    def test_converts_supply_chain_to_exchange(self):
        from .models import (
            Supply_chain, Exchange, SupplyNode, Asset, Country, Commodity,
        )
        from dashboard.migrations import _supply_chain_to_graph
        c = Country.objects.create(name='Brésil', water_ownership='X', land_ownership='Y')
        a = Asset.objects.create(name='Usine', latitude=0.0, longitude=0.0, country=c)
        sup = Asset.objects.create(name='Ferme', latitude=-3.0, longitude=-47.0, country=c)
        com = Commodity.objects.create(name='Soja')
        Supply_chain.objects.create(
            asset=a, supplier=sup, commodity=com, quantity=50.0, year=2024,
        )
        _supply_chain_to_graph.migrate(Supply_chain, SupplyNode, Exchange)
        self.assertEqual(Exchange.objects.count(), 1)
        ex = Exchange.objects.get()
        self.assertEqual(ex.consumer.asset_id, a.pk)
        self.assertEqual(ex.supplier.asset_id, sup.pk)
        self.assertEqual(ex.quantity, 50.0)
        self.assertEqual(ex.tier, 1)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.SupplyChainToGraphTests`
Expected : FAIL (module `_supply_chain_to_graph` absent).

- [ ] **Step 3 : Écrire le helper + la migration**

Créer `dashboard/migrations/_supply_chain_to_graph.py` :
```python
"""Conversion figée Supply_chain → SupplyNode + Exchange."""
_CONF = {'country level': 'country', 'sub_region level': 'region', 'asset level': 'asset'}


def _node_for_asset(SupplyNode, asset_id):
    node, _ = SupplyNode.objects.get_or_create(
        asset_id=asset_id, region=None, country=None, commodity=None,
        defaults={'is_external': False},
    )
    return node


def migrate(Supply_chain, SupplyNode, Exchange):
    for sc in Supply_chain.objects.all():
        if not sc.asset_id or not sc.supplier_id:
            continue
        consumer = _node_for_asset(SupplyNode, sc.asset_id)
        supplier = _node_for_asset(SupplyNode, sc.supplier_id)
        Exchange.objects.get_or_create(
            supplier=supplier, consumer=consumer, commodity_id=sc.commodity_id,
            year=sc.year,
            defaults={
                'quantity': sc.quantity, 'tier': 1,
                'data_confidence': _CONF.get(sc.supplier_data_confidence, 'country'),
            },
        )
```

Créer `dashboard/migrations/0033_migrate_supply_chain.py` :
```python
from django.db import migrations
from dashboard.migrations import _supply_chain_to_graph


def run(apps, schema_editor):
    _supply_chain_to_graph.migrate(
        apps.get_model('dashboard', 'Supply_chain'),
        apps.get_model('dashboard', 'SupplyNode'),
        apps.get_model('dashboard', 'Exchange'),
    )


def undo(apps, schema_editor):
    apps.get_model('dashboard', 'Exchange').objects.all().delete()
    apps.get_model('dashboard', 'SupplyNode').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0032_backfill_production_tier')]
    operations = [migrations.RunPython(run, undo)]
```

- [ ] **Step 4 : Lancer, vérifier le succès + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.SupplyChainToGraphTests dashboard.tests.GoldenViewOutputTests`
Expected : PASS (acme sans Supply_chain → aucun Exchange créé → golden inchangé).

- [ ] **Step 5 : Commit**

```bash
git add dashboard/migrations/_supply_chain_to_graph.py dashboard/migrations/0033_migrate_supply_chain.py dashboard/tests.py
git commit -m "feat(migration): Supply_chain → SupplyNode/Exchange"
```

---

### Task 7 : Traversée `upstream_chain` (`services/supply.py`)

**Files:**
- Modify: `dashboard/services/supply.py`
- Test: `dashboard/tests.py`

**Interfaces:**
- Produces: `upstream_chain(node, year, max_depth=5) -> list[Exchange]` — remonte les `Exchange` amont (consumer == node, puis leurs suppliers, etc.), avec garde anti-cycle.

- [ ] **Step 1 : Écrire le test**

```python
class UpstreamChainTests(TestCase):

    def test_multitier_traversal_with_cycle_guard(self):
        from .models import Exchange, SupplyNode, Asset, Country, Commodity
        from .services.supply import upstream_chain
        c = Country.objects.create(name='BR', water_ownership='X', land_ownership='Y')
        a = Asset.objects.create(name='A', latitude=0.0, longitude=0.0, country=c)
        b = Asset.objects.create(name='B', latitude=1.0, longitude=1.0, country=c)
        d = Asset.objects.create(name='D', latitude=2.0, longitude=2.0, country=c)
        na = SupplyNode.objects.create(asset=a)
        nb = SupplyNode.objects.create(asset=b)
        nd = SupplyNode.objects.create(asset=d)
        com = Commodity.objects.create(name='Soja')
        # a <- b <- d  (deux tiers) + un cycle d -> b (doit être borné)
        Exchange.objects.create(supplier=nb, consumer=na, commodity=com, quantity=1, year=2024)
        Exchange.objects.create(supplier=nd, consumer=nb, commodity=com, quantity=1, year=2024)
        Exchange.objects.create(supplier=nb, consumer=nd, commodity=com, quantity=1, year=2024)
        chain = upstream_chain(na, 2024)
        # 3 arêtes atteignables sans boucler indéfiniment
        self.assertGreaterEqual(len(chain), 2)
        self.assertLessEqual(len(chain), 3)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.UpstreamChainTests`
Expected : FAIL (`cannot import name 'upstream_chain'`).

- [ ] **Step 3 : Ajouter la fonction**

Ajouter à `dashboard/services/supply.py` :
```python
from dashboard.models import Exchange


def upstream_chain(node, year, max_depth=5):
    """Remonte les Exchange amont depuis `node` (année donnée), borné et anti-cycle."""
    seen_nodes = {node.pk}
    frontier = [node.pk]
    edges = []
    depth = 0
    while frontier and depth < max_depth:
        exchanges = list(
            Exchange.objects.filter(consumer_id__in=frontier, year=year)
            .select_related('supplier', 'consumer', 'commodity')
        )
        edges.extend(exchanges)
        next_frontier = []
        for ex in exchanges:
            if ex.supplier_id not in seen_nodes:
                seen_nodes.add(ex.supplier_id)
                next_frontier.append(ex.supplier_id)
        frontier = next_frontier
        depth += 1
    return edges
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.UpstreamChainTests`
Expected : PASS.

- [ ] **Step 5 : Commit**

```bash
git add dashboard/services/supply.py dashboard/tests.py
git commit -m "feat(service): upstream_chain (traversée multi-tiers + anti-cycle)"
```

---

### Task 8 : Bascule `_get_dependencies_data` (scope → tier, sortie préservée)

**Files:**
- Modify: `dashboard/views.py` (`_get_dependencies_data`, constantes `_SCOPE_LABELS`/`_SCOPE_ORDER`)
- Modify: `dashboard/tests.py` (`DependenciesDataTests`)

**Interfaces:**
- Consumes: `TIER_LABELS`, `TIER_TO_SCOPE` de `services/supply.py`.

- [ ] **Step 1 : Adapter les tests (scope → tier)**

Dans `DependenciesDataTests`, remplacer les `scope='direct'` par `tier=0` et `scope='tier 1'` par `tier=1` dans les `Production.objects.create(...)` (lignes ~381, ~533, ~559). Les assertions sur `data['supply_chain'][…]['scope']` (chaînes `direct`/`tier 1`) restent inchangées (la vue continue d'émettre `scope`).

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.DependenciesDataTests`
Expected : FAIL (la vue groupe encore par `scope`, mais les productions n'ont plus de scope explicite → tout tombe en `direct` par défaut ; certaines assertions `tier 1` échouent).

- [ ] **Step 3 : Basculer la vue**

Dans `dashboard/views.py`, ajouter en tête l'import :
```python
from .services.supply import TIER_LABELS, TIER_TO_SCOPE
```

Remplacer les constantes `_SCOPE_LABELS` (≈ lignes 53-58) et `_SCOPE_ORDER` (≈ ligne 60) — les supprimer (elles ne servent plus). Dans `_get_dependencies_data` :

- Remplacer `critical_nodes.add((p.commodity_id, p.scope))` par `critical_nodes.add((p.commodity_id, p.tier))`.
- Remplacer le groupement `scope_groups[p.scope].append(...)` par `scope_groups[p.tier].append(...)`.
- Remplacer la boucle `for scope in _SCOPE_ORDER: if scope not in scope_groups: continue` par :
```python
    for tier in sorted(scope_groups):
        group = scope_groups[tier]
        scope = TIER_TO_SCOPE[tier]
```
et, dans l'`append` du `supply_chain`, remplacer `'label': _SCOPE_LABELS[scope]` par `'label': TIER_LABELS[tier]` (le champ `'scope': scope` reste, avec `scope = TIER_TO_SCOPE[tier]`).

- [ ] **Step 4 : Lancer, vérifier le succès + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.DependenciesDataTests dashboard.tests.GoldenViewOutputTests`
Expected : PASS (golden `dependencies.json` inchangé : mêmes clés `scope`/`label`).

- [ ] **Step 5 : Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "refactor(views): dependencies groupe par tier (sortie scope préservée)"
```

---

### Task 9 : Bascule `_get_leap_locate_data` (Supply_chain → Exchange/SupplyNode)

**Files:**
- Modify: `dashboard/views.py` (`_get_leap_locate_data`)
- Modify: `dashboard/tests.py` (`LeapLocateDataTests`)

**Interfaces:**
- Consumes: `Exchange`, `SupplyNode`.

**Principe :** la partie `features` (assets détenus) est inchangée. La partie `suppliers`/`supplier_links` provient désormais des `Exchange` dont le `consumer` est un `SupplyNode(asset=<asset détenu>)`. Coordonnées du fournisseur : `supplier.asset` → coords de l'asset ; sinon `supplier.region` → `Mean_X`/`Mean_Y` ; sinon (pays seul, sans coords) → le lien est ignoré.

- [ ] **Step 1 : Adapter les tests (Supply_chain → Exchange)**

Dans `LeapLocateDataTests`, remplacer les deux `Supply_chain.objects.create(asset=…, supplier=…, commodity=…, quantity=…, year=…)` (≈ lignes 1780, 1813) par la création d'un graphe équivalent :
```python
        from .models import Exchange, SupplyNode
        consumer = SupplyNode.objects.create(asset=<asset consommateur>)
        supplier = SupplyNode.objects.create(asset=<asset fournisseur>)
        Exchange.objects.create(
            supplier=supplier, consumer=consumer, commodity=<commodity>,
            quantity=<qty>, year=<year>, tier=1,
        )
```
(remplacer les `<…>` par les variables locales déjà présentes dans chaque test ; conserver les assertions sur `data['suppliers']` / `data['supplier_links']`).

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.LeapLocateDataTests`
Expected : FAIL (la vue lit encore `asset_productions`/Supply_chain → suppliers vides).

- [ ] **Step 3 : Basculer la vue**

Dans `dashboard/views.py`, ajouter l'import :
```python
from .models import Exchange, SupplyNode
```
(fusionner avec l'import `.models` existant plutôt que dupliquer.)

Dans `_get_leap_locate_data`, remplacer le prefetch de `asset_productions` (Supply_chain) et la boucle qui en dérive `suppliers`/`supplier_links` par une requête unique sur `Exchange` groupée par asset consommateur :
```python
    asset_id_set = set(asset_ids)
    exchanges = list(
        Exchange.objects.filter(consumer__asset_id__in=asset_ids)
        .select_related(
            'supplier', 'supplier__asset', 'supplier__asset__country',
            'supplier__region', 'supplier__region__country', 'supplier__country',
            'consumer', 'consumer__asset', 'commodity',
        )
    )
    # dernière année par asset consommateur
    latest_sc_year = {}
    for ex in exchanges:
        aid = ex.consumer.asset_id
        latest_sc_year[aid] = max(latest_sc_year.get(aid, ex.year), ex.year)
```
Puis construire `suppliers` (dict par node) et `supplier_links` en itérant `exchanges` filtrés sur `ex.year == latest_sc_year[ex.consumer.asset_id]`. Pour chaque `ex` :
```python
        sup = ex.supplier
        cons_asset = ex.consumer.asset
        if sup.asset_id:
            coords = [sup.asset.longitude, sup.asset.latitude]
            sup_name, sup_country = sup.asset.name, sup.asset.country.name
            sup_is_owned = sup.asset_id in asset_id_set
        elif sup.region_id:
            coords = [sup.region.Mean_X, sup.region.Mean_Y]
            sup_name = sup.name or sup.region.name
            sup_country = sup.region.country.name
            sup_is_owned = False
        else:
            continue  # pays seul : pas de coordonnées → lien ignoré
```
Reproduire ensuite la même structure de sortie qu'avant : marqueur fournisseur (sauf si `sup_is_owned`, pour ne pas doublonner un asset détenu) et une `LineString` [coords → coords de `cons_asset`] avec `{'supplier','asset','commodity'}`. Les clés de sortie (`geojson`, `suppliers`, `supplier_links` avec leurs `properties`) sont **identiques** à l'existant.

- [ ] **Step 4 : Lancer, vérifier le succès + golden**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.LeapLocateDataTests dashboard.tests.GoldenViewOutputTests`
Expected : PASS (acme sans Exchange → `suppliers`/`supplier_links` vides comme la baseline ; `features` inchangées).

- [ ] **Step 5 : Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "refactor(views): leap_locate via Exchange/SupplyNode"
```

---

### Task 10 : `imports` — `Production.scope` → `tier`

**Files:**
- Modify: `imports/services/importer.py` (`_import_production`)
- Modify: `imports/tests/test_importer.py`

**Principe :** la feuille garde sa colonne `scope` (valeurs `direct`/`tier 1`/…) ; l'importer la mappe vers `tier`. `constants.py` reste inchangé (colonne `scope` toujours attendue).

- [ ] **Step 1 : Écrire/adapter le test**

Dans `imports/tests/test_importer.py`, ajouter un test : importer une feuille `Production` avec `scope='tier 1'` et vérifier que la `Production` créée a `tier == 1` (et non une exception). Respecter les fixtures/`save_import` existants du fichier.

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test imports.tests.test_importer`
Expected : FAIL (le test attend `tier`, l'importer pose encore `scope`).

- [ ] **Step 3 : Basculer l'importer**

Dans `imports/services/importer.py`, en tête, ajouter :
```python
from dashboard.services.supply import SCOPE_TO_TIER
```
Dans `_import_production`, remplacer le kwarg `scope=d.get('scope') or 'direct'` de `Production.objects.create(...)` par :
```python
            tier=SCOPE_TO_TIER.get(d.get('scope') or 'direct', 0),
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test imports`
Expected : PASS.

- [ ] **Step 5 : Commit**

```bash
git add imports/services/importer.py imports/tests/test_importer.py
git commit -m "fix(imports): _import_production mappe scope de la feuille vers tier"
```

---

### Task 11 : `populate_acme` — `Production` en `tier`

**Files:**
- Modify: `dashboard/management/commands/populate_acme.py`
- Test: golden (déjà) + `dashboard.tests.PopulateAcmeE4Tests` inchangé

- [ ] **Step 1 : Basculer la liste des productions**

Dans `populate_acme.py`, la liste `productions` utilise des chaînes scope (`"direct"`, `"tier 1"`). Ajouter en tête l'import :
```python
from dashboard.services.supply import SCOPE_TO_TIER
```
Dans la boucle qui crée les `Production` (`Production.objects.get_or_create(... scope=scope ...)`), remplacer le champ `scope=scope` par `tier=SCOPE_TO_TIER[scope]` (les tuples de la liste `productions` gardent la chaîne, on la mappe à la création). Concrètement, dans le `get_or_create`, remplacer la clé `scope=scope,` par `tier=SCOPE_TO_TIER[scope],`.

- [ ] **Step 2 : Vérifier golden + suite**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.GoldenViewOutputTests dashboard.tests.PopulateAcmeE4Tests`
Expected : PASS (dependencies émet toujours les mêmes `scope`/labels dérivés de `tier` ; les productions acme ont les bons tiers).

- [ ] **Step 3 : Suite complète**

Run : `.venv\Scripts\python.exe manage.py test dashboard`
Expected : PASS.

- [ ] **Step 4 : Commit**

```bash
git add dashboard/management/commands/populate_acme.py
git commit -m "feat(seed): populate_acme crée les Production avec tier"
```

---

### Task 12 : Nettoyage — drop `Supply_chain` + `Production.scope` + admin

**Files:**
- Modify: `dashboard/models.py` (retirer `Production.scope` et le modèle `Supply_chain`)
- Modify: `dashboard/admin.py` (retirer `Supply_chain`, enregistrer `SupplyNode`/`Exchange`)
- Create: `dashboard/migrations/0034_drop_scope_and_supply_chain.py`
- Test: `dashboard/tests.py`

- [ ] **Step 1 : Écrire le test de suppression**

```python
class SupplyChainDroppedTests(TestCase):

    def test_production_has_no_scope_and_supply_chain_gone(self):
        from .models import Production, Commodity, Company
        com = Commodity.objects.create(name='X')
        company = Company.objects.create(name='C')
        p = Production.objects.create(commodity=com, company=company, year=2024,
                                      production=1.0, tier=1)
        self.assertFalse(hasattr(p, 'scope'))
        import dashboard.models as m
        self.assertFalse(hasattr(m, 'Supply_chain'))
```

- [ ] **Step 2 : Retirer `scope` et `Supply_chain` du modèle**

Dans `dashboard/models.py` : supprimer le champ `scope` de `Production` ; supprimer entièrement la classe `Supply_chain`. Vérifier qu'aucun code hors migrations ne référence plus `Supply_chain` :
`git grep -n "Supply_chain\|\.scope" -- dashboard/views.py dashboard/models.py dashboard/admin.py imports/` (ne doit rester que `Carbon_emission.scope` / `carbon` scope, sans rapport).

- [ ] **Step 3 : Admin**

Dans `dashboard/admin.py` : retirer `Supply_chain` des imports et son `@admin.register(Supply_chain)` (classe `SupplyChainAdmin`). Ajouter :
```python
@admin.register(SupplyNode)
class SupplyNodeAdmin(admin.ModelAdmin):
    search_fields = ('name', 'asset__name', 'region__name', 'country__name')
    list_display = ('__str__', 'resolution', 'is_external')
    list_filter = ('is_external',)
    autocomplete_fields = ('asset', 'region', 'country', 'commodity')


@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    search_fields = ('supplier__name', 'consumer__name', 'commodity__name')
    list_display = ('__str__', 'tier', 'year', 'data_confidence')
    list_filter = ('tier', 'year', 'data_confidence')
    autocomplete_fields = ('supplier', 'consumer', 'commodity', 'created_by')
```
(ajouter `SupplyNode, Exchange` aux imports `from .models import (...)`.)

- [ ] **Step 4 : Migration**

Run : `.venv\Scripts\python.exe manage.py makemigrations dashboard --name drop_scope_and_supply_chain`
Expected : `0034_...` (RemoveField Production.scope + DeleteModel Supply_chain).

- [ ] **Step 5 : Suite complète + golden + vérif**

Run : `.venv\Scripts\python.exe manage.py test`
Expected : PASS (projet entier, golden inclus).
Run : `git grep -n "Supply_chain" -- dashboard/ imports/`
Expected : plus aucune occurrence hors `dashboard/migrations/` (historique + helper figé).

- [ ] **Step 6 : Commit**

```bash
git add dashboard/models.py dashboard/admin.py dashboard/migrations/0034_drop_scope_and_supply_chain.py dashboard/tests.py
git commit -m "refactor: drop Supply_chain + Production.scope (graphe = source unique)"
```

---

## Self-Review

**Couverture du spec (Plan B) :**
- §5.3 `SupplyNode` + `Exchange` → Tasks 3, 4.
- §5.5 vocabulaire `tier` → Task 2 ; `Production.tier` → Task 5.
- §5.6 `Production.scope → tier` (mapping `direct→0…raw→3`), suppression `Supply_chain` → Tasks 5, 12.
- §6 `services/supply.py : upstream_chain` → Task 7.
- §8.3 migrations (graphe, tier, migration Supply_chain) → Tasks 3-6, 12.
- §9 vues `leap_locate` + `dependencies`, imports, populate_acme, admin → Tasks 8-12.
- §11 golden + traversée + tests → Task 1, 7, tests par tâche.
- Hors périmètre Plan B : `AssetInventory`/`Flow` (Plan C) ; peupler le graphe fournisseurs d'acme (déféré — le graphe est couvert par tests unitaires ; leap_locate d'acme reste vide, golden invariant).

**Scan placeholders :** aucun « TBD/TODO ». Les `<…>` de la Task 9 Step 1 sont des variables locales à substituer, explicitement décrites.

**Cohérence des types/noms :** `SupplyNode`, `Exchange(supplier/consumer/tier/data_confidence)`, `Production.tier`, `SCOPE_TO_TIER`/`TIER_TO_SCOPE`/`TIER_LABELS`, `upstream_chain(node, year, max_depth=5)` — cohérents entre définitions (Tasks 2-7) et usages (Tasks 8-12). Migrations `0029`→`0034`, dépendances chaînées. Helpers de migration **figés** (préfixe `_`, pas d'import de constante vivante — leçon de la revue finale du Plan A).

**Décision de sortie préservée :** `dependencies` émet toujours la clé `scope` (chaîne) dérivée de `tier` via `TIER_TO_SCOPE`, et le label via `TIER_LABELS[tier]` (== ancien `_SCOPE_LABELS`). `leap_locate` conserve `features`/`suppliers`/`supplier_links`. Golden invariant sur acme.
