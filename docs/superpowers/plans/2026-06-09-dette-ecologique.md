# Dette écologique Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Renommer "Risque de transition" en "Mesure d'empreinte" (y compris les vues, URLs, fichiers JS et template), puis créer la page "Dette écologique" avec une carte MapLibre GL affichant des marqueurs pie chart SVG dont la taille est proportionnelle au Lbiodiv calculé par asset ou par région subnational.

**Architecture:** Pattern identique aux autres pages du dashboard : vue Django + endpoint JSON API, données initiales injectées via `json_script`, switch entreprise via fetch côté client. Les marqueurs pie chart sont des éléments SVG attachés via `maplibregl.Marker`.

**Tech Stack:** Django, Python 3.11, MapLibre GL JS v4 (CDN), vanilla JS ES6, pytest-django.

---

## File Map

| Fichier | Action |
|---------|--------|
| `dashboard/templates/dashboard/transition_risk.html` | Renommer → `mesure_empreinte.html` + 4 edits |
| `dashboard/static/dashboard/js/transition_risk.js` | Renommer → `mesure_empreinte.js` + 2 edits |
| `dashboard/views.py` | Renommer 3 symboles, ajouter `_BIODIV_LOSS_FIELDS` + 3 nouvelles fonctions |
| `dashboard/urls.py` | Renommer 2 URL entries + ajouter 2 nouvelles |
| `templates/base.html` | Mettre à jour sidebar : label + URL + block mesure_empreinte ; ajouter entrée dette_ecologique |
| `dashboard/templates/dashboard/dette_ecologique.html` | Créer |
| `dashboard/static/dashboard/js/dette_ecologique.js` | Créer |
| `dashboard/static/dashboard/css/style.css` | Ajouter section `.de-*` |
| `dashboard/tests.py` | Ajouter `DetteEcologiqueDataTests` + `DetteEcologiqueViewTests` |

---

## Task 1 — Renommer "Risque de transition" → "Mesure d'empreinte"

**Files:**
- Rename: `dashboard/templates/dashboard/transition_risk.html` → `dashboard/templates/dashboard/mesure_empreinte.html`
- Rename: `dashboard/static/dashboard/js/transition_risk.js` → `dashboard/static/dashboard/js/mesure_empreinte.js`
- Modify: `dashboard/views.py`
- Modify: `dashboard/urls.py`
- Modify: `templates/base.html`

- [ ] **Step 1.1: Renommer les fichiers**

```powershell
Move-Item dashboard/templates/dashboard/transition_risk.html dashboard/templates/dashboard/mesure_empreinte.html
Move-Item dashboard/static/dashboard/js/transition_risk.js dashboard/static/dashboard/js/mesure_empreinte.js
```

- [ ] **Step 1.2: Mettre à jour le template mesure_empreinte.html**

Ouvrir `dashboard/templates/dashboard/mesure_empreinte.html` et appliquer ces 4 changements :

Ligne 4 — titre :
```
{% block title %}Risque de transition — Easybiodiv{% endblock %}
```
→
```
{% block title %}Mesure d'empreinte — Easybiodiv{% endblock %}
```

Ligne 7 — nav block :
```
{% block nav_transition_risk %}active{% endblock %}
```
→
```
{% block nav_mesure_empreinte %}active{% endblock %}
```

Ligne 83 — variable JS et URL :
```html
<script>var TRANSITION_RISK_API_URL = "{% url 'dashboard:transition_risk_data' pk=0 %}";</script>
```
→
```html
<script>var MESURE_EMPREINTE_API_URL = "{% url 'dashboard:mesure_empreinte_data' pk=0 %}";</script>
```

Ligne 84 — script src :
```html
<script src="{% static 'dashboard/js/transition_risk.js' %}" defer></script>
```
→
```html
<script src="{% static 'dashboard/js/mesure_empreinte.js' %}" defer></script>
```

- [ ] **Step 1.3: Mettre à jour mesure_empreinte.js**

Dans `dashboard/static/dashboard/js/mesure_empreinte.js`, remplacer les deux occurrences de `TRANSITION_RISK_API_URL` par `MESURE_EMPREINTE_API_URL` (lignes 16 et 72).

- [ ] **Step 1.4: Renommer dans views.py**

Dans `dashboard/views.py`, appliquer les renommages suivants (rechercher/remplacer exact) :

| Avant | Après |
|-------|-------|
| `_get_transition_risk_data` | `_get_mesure_empreinte_data` |
| `transition_risk` (les deux vues) | `mesure_empreinte` et `mesure_empreinte_data` |
| `'dashboard/transition_risk.html'` (deux occurrences dans render()) | `'dashboard/mesure_empreinte.html'` |

Les fonctions résultantes doivent être :
```python
@login_required
@require_GET
def mesure_empreinte(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_mesure_empreinte_data(first)
    return render(request, 'dashboard/mesure_empreinte.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@login_required
@require_GET
def mesure_empreinte_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_mesure_empreinte_data(company))
```

- [ ] **Step 1.5: Mettre à jour urls.py**

Remplacer les deux entrées transition_risk dans `dashboard/urls.py` :

```python
# Avant
path('transition-risk/', views.transition_risk, name='transition_risk'),
path('api/company/<int:pk>/transition-risk/', views.transition_risk_data, name='transition_risk_data'),

# Après
path('mesure-empreinte/', views.mesure_empreinte, name='mesure_empreinte'),
path('api/company/<int:pk>/mesure-empreinte/', views.mesure_empreinte_data, name='mesure_empreinte_data'),
```

- [ ] **Step 1.6: Mettre à jour base.html**

Dans `templates/base.html`, remplacer le bloc de navigation "Risque de transition" (lignes 64-68) :

```html
<li>
  <a href="{% url 'dashboard:transition_risk' %}"
     class="sidebar__nav-sublink {% block nav_transition_risk %}{% endblock %}"
     aria-label="Risque de transition">
    Risque de transition
  </a>
</li>
```
→
```html
<li>
  <a href="{% url 'dashboard:mesure_empreinte' %}"
     class="sidebar__nav-sublink {% block nav_mesure_empreinte %}{% endblock %}"
     aria-label="Mesure d'empreinte">
    Mesure d'empreinte
  </a>
</li>
```

- [ ] **Step 1.7: Vérifier que les tests existants passent**

```bash
pytest dashboard/tests.py -v
```

Attendu : tous les tests passent (aucun test ne devrait référencer l'ancienne URL — si c'est le cas, les mettre à jour pour utiliser `dashboard:mesure_empreinte`).

- [ ] **Step 1.8: Commit**

```bash
git add dashboard/templates/dashboard/mesure_empreinte.html \
        dashboard/static/dashboard/js/mesure_empreinte.js \
        dashboard/views.py dashboard/urls.py templates/base.html
git commit -m "refactor(dashboard): rename transition_risk → mesure_empreinte"
```

---

## Task 2 — Backend : `_get_dette_ecologique_data`

**Files:**
- Modify: `dashboard/views.py`
- Test: `dashboard/tests.py`

- [ ] **Step 2.0: Appliquer les migrations en attente**

Les migrations `0015_commodity_biodiversity_loss_class_and_more.py` et `0016_alter_asset_subnational_region.py` sont sur le disque mais pas encore appliquées.

```bash
python manage.py migrate
```

Attendu : `Applying dashboard.0015_commodity_biodiversity_loss_class_and_more... OK` et `0016... OK`.

- [ ] **Step 2.1: Écrire les tests qui échouent**

Ajouter à `dashboard/tests.py`, après les imports existants, le bloc suivant :

```python
from .views import _get_dette_ecologique_data
```

Puis ajouter la classe de test à la fin du fichier :

```python
class DetteEcologiqueDataTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='TestCorp')
        self.country = Country.objects.create(
            name='France',
            water_ownership='Public',
            land_ownership='Private',
            biodiversity_loss_agriculture=2.0,
            biodiversity_loss_urbanization=3.0,
            biodiversity_loss_mining=1.5,
        )
        self.region = SubnationalRegion.objects.create(
            name='IDF', country=self.country,
            restoration_cost_m2=10.0,
            Mean_X=2.3, Mean_Y=48.8,
        )
        self.commodity_agri = Commodity.objects.create(
            name='Soja',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
            biodiversity_loss_class='Agriculture',
        )
        self.asset = Asset.objects.create(
            name='Site A', latitude=48.8, longitude=2.3,
            country=self.country, subnational_region=self.region,
        )
        Ownership.objects.create(Asset=self.asset, Company=self.company, ownership='100%')

    def test_no_assets_returns_empty(self):
        other = Company.objects.create(name='Empty')
        result = _get_dette_ecologique_data(other)
        self.assertEqual(result['total_lbiodiv'], 0)
        self.assertEqual(result['assets'], [])
        self.assertEqual(result['regions'], [])

    def test_excludes_asset_without_region(self):
        asset_no_region = Asset.objects.create(
            name='No Region', latitude=0.0, longitude=0.0,
            country=self.country, subnational_region=None,
        )
        Ownership.objects.create(Asset=asset_no_region, Company=self.company, ownership='100%')
        Production.objects.create(
            asset=asset_no_region, commodity=self.commodity_agri, year=2024, production=100.0,
        )
        result = _get_dette_ecologique_data(self.company)
        asset_ids = [a['id'] for a in result['assets']]
        self.assertNotIn(asset_no_region.pk, asset_ids)

    def test_lbiodiv_formula_agriculture(self):
        # 2.0 * 10.0 * 100.0 * 0.5 = 1000.0
        Production.objects.create(
            asset=self.asset, commodity=self.commodity_agri, year=2024, production=100.0,
        )
        result = _get_dette_ecologique_data(self.company)
        self.assertAlmostEqual(result['total_lbiodiv'], 1000.0, places=2)

    def test_lbiodiv_formula_urbanisation(self):
        # biodiversity_loss_urbanization=3.0 → 3.0 * 10.0 * 100.0 * 0.5 = 1500.0
        commodity_urb = Commodity.objects.create(
            name='Béton',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
            biodiversity_loss_class='Urbanisation',
        )
        Production.objects.create(
            asset=self.asset, commodity=commodity_urb, year=2024, production=100.0,
        )
        result = _get_dette_ecologique_data(self.company)
        self.assertAlmostEqual(result['total_lbiodiv'], 1500.0, places=2)

    def test_lbiodiv_formula_mining(self):
        # biodiversity_loss_mining=1.5 → 1.5 * 10.0 * 100.0 * 0.5 = 750.0
        commodity_min = Commodity.objects.create(
            name='Lithium',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
            biodiversity_loss_class='Mining',
        )
        Production.objects.create(
            asset=self.asset, commodity=commodity_min, year=2024, production=100.0,
        )
        result = _get_dette_ecologique_data(self.company)
        self.assertAlmostEqual(result['total_lbiodiv'], 750.0, places=2)

    def test_latest_year_only(self):
        Production.objects.create(
            asset=self.asset, commodity=self.commodity_agri, year=2022, production=999.0,
        )
        Production.objects.create(
            asset=self.asset, commodity=self.commodity_agri, year=2024, production=100.0,
        )
        # Only 2024 : 2.0 * 10.0 * 100.0 * 0.5 = 1000.0
        result = _get_dette_ecologique_data(self.company)
        self.assertAlmostEqual(result['total_lbiodiv'], 1000.0, places=2)

    def test_region_aggregation(self):
        asset2 = Asset.objects.create(
            name='Site B', latitude=48.9, longitude=2.4,
            country=self.country, subnational_region=self.region,
        )
        Ownership.objects.create(Asset=asset2, Company=self.company, ownership='100%')
        Production.objects.create(
            asset=self.asset, commodity=self.commodity_agri, year=2024, production=100.0,
        )
        Production.objects.create(
            asset=asset2, commodity=self.commodity_agri, year=2024, production=50.0,
        )
        result = _get_dette_ecologique_data(self.company)
        self.assertEqual(len(result['regions']), 1)
        # 2.0*10.0*100.0*0.5 + 2.0*10.0*50.0*0.5 = 1000 + 500 = 1500
        self.assertAlmostEqual(result['regions'][0]['total_lbiodiv'], 1500.0, places=2)
```

- [ ] **Step 2.2: Vérifier que les tests échouent**

```bash
pytest dashboard/tests.py::DetteEcologiqueDataTests -v
```

Attendu : `ImportError: cannot import name '_get_dette_ecologique_data'`

- [ ] **Step 2.3: Implémenter `_get_dette_ecologique_data` dans views.py**

Ajouter juste avant la définition des vues (après `_get_mesure_empreinte_data`) :

```python
_BIODIV_LOSS_FIELDS = {
    'Agriculture':  'biodiversity_loss_agriculture',
    'Urbanisation': 'biodiversity_loss_urbanization',
    'Mining':       'biodiversity_loss_mining',
}


def _get_dette_ecologique_data(company):
    empty = {
        'company_id': company.pk,
        'company_name': company.name,
        'year': None,
        'total_lbiodiv': 0,
        'commodities': [],
        'assets': [],
        'regions': [],
    }

    assets = list(
        Asset.objects.filter(ownership__Company=company)
        .select_related('country', 'subnational_region')
        .distinct()
    )
    assets = [a for a in assets if a.subnational_region_id is not None]

    if not assets:
        return empty

    asset_ids = [a.pk for a in assets]

    latest_years = dict(
        Production.objects.filter(asset_id__in=asset_ids)
        .values('asset_id')
        .annotate(max_year=Max('year'))
        .values_list('asset_id', 'max_year')
    )
    if not latest_years:
        return empty

    ref_year = max(latest_years.values())

    productions = list(
        Production.objects.filter(asset_id__in=asset_ids)
        .select_related('commodity', 'asset__country', 'asset__subnational_region')
    )
    productions = [p for p in productions if latest_years.get(p.asset_id) == p.year]

    asset_map = {a.pk: a for a in assets}
    asset_comm = defaultdict(lambda: defaultdict(float))
    global_comm = defaultdict(float)

    for p in productions:
        asset = asset_map.get(p.asset_id)
        if asset is None:
            continue
        field = _BIODIV_LOSS_FIELDS.get(
            p.commodity.biodiversity_loss_class, 'biodiversity_loss_agriculture'
        )
        biodiv_loss = getattr(asset.country, field, 0.0)
        restoration = asset.subnational_region.restoration_cost_m2
        lbiodiv = (
            biodiv_loss
            * restoration
            * p.production
            * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
        )
        asset_comm[p.asset_id][p.commodity.name] += lbiodiv
        global_comm[p.commodity.name] += lbiodiv

    total = sum(global_comm.values())
    if total == 0:
        return {**empty, 'year': ref_year}

    commodities = sorted(
        [{'name': k, 'lbiodiv': round(v, 4), 'pct': round(v / total, 4)}
         for k, v in global_comm.items()],
        key=lambda x: -x['lbiodiv'],
    )

    assets_out = []
    for asset in assets:
        ac = asset_comm.get(asset.pk, {})
        asset_total = sum(ac.values())
        if asset_total == 0:
            continue
        assets_out.append({
            'id': asset.pk,
            'name': asset.name,
            'latitude': asset.latitude,
            'longitude': asset.longitude,
            'total_lbiodiv': round(asset_total, 4),
            'pct': round(asset_total / total, 4),
            'commodities': sorted(
                [{'name': k, 'lbiodiv': round(v, 4), 'pct': round(v / asset_total, 4)}
                 for k, v in ac.items()],
                key=lambda x: -x['lbiodiv'],
            ),
        })
    assets_out.sort(key=lambda x: -x['total_lbiodiv'])

    region_comm = defaultdict(lambda: defaultdict(float))
    region_meta = {}
    for asset in assets:
        reg = asset.subnational_region
        if reg is None:
            continue
        region_meta[reg.pk] = reg
        for comm_name, val in asset_comm.get(asset.pk, {}).items():
            region_comm[reg.pk][comm_name] += val

    regions_out = []
    for reg_pk, reg in region_meta.items():
        rc = region_comm[reg_pk]
        reg_total = sum(rc.values())
        if reg_total == 0:
            continue
        regions_out.append({
            'id': reg.pk,
            'name': reg.name,
            'latitude': reg.Mean_Y,
            'longitude': reg.Mean_X,
            'total_lbiodiv': round(reg_total, 4),
            'pct': round(reg_total / total, 4),
            'commodities': sorted(
                [{'name': k, 'lbiodiv': round(v, 4), 'pct': round(v / reg_total, 4)}
                 for k, v in rc.items()],
                key=lambda x: -x['lbiodiv'],
            ),
        })
    regions_out.sort(key=lambda x: -x['total_lbiodiv'])

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'year': ref_year,
        'total_lbiodiv': round(total, 4),
        'commodities': commodities,
        'assets': assets_out,
        'regions': regions_out,
    }
```

- [ ] **Step 2.4: Vérifier que les tests passent**

```bash
pytest dashboard/tests.py::DetteEcologiqueDataTests -v
```

Attendu : 7 tests PASSED.

- [ ] **Step 2.5: Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "feat(dashboard): add _get_dette_ecologique_data with tests"
```

---

## Task 3 — Backend : vues + URLs + test de navigation

**Files:**
- Modify: `dashboard/views.py`
- Modify: `dashboard/urls.py`
- Modify: `templates/base.html`
- Test: `dashboard/tests.py`

- [ ] **Step 3.1: Écrire les tests de vue qui échouent**

Ajouter dans `dashboard/tests.py` :

```python
from django.contrib.auth import get_user_model


class DetteEcologiqueViewTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='tester', password='pass')
        self.client.login(username='tester', password='pass')

    def test_mesure_empreinte_returns_200(self):
        response = self.client.get(reverse('dashboard:mesure_empreinte'))
        self.assertEqual(response.status_code, 200)

    def test_dette_ecologique_returns_200(self):
        response = self.client.get(reverse('dashboard:dette_ecologique'))
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 3.2: Vérifier que le test dette_ecologique échoue**

```bash
pytest dashboard/tests.py::DetteEcologiqueViewTests -v
```

Attendu : `test_mesure_empreinte_returns_200` PASSED (déjà implémenté), `test_dette_ecologique_returns_200` FAILED avec NoReverseMatch.

- [ ] **Step 3.3: Ajouter les vues dans views.py**

Ajouter à la fin de `dashboard/views.py` :

```python
@login_required
@require_GET
def dette_ecologique(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_dette_ecologique_data(first)
    return render(request, 'dashboard/dette_ecologique.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@login_required
@require_GET
def dette_ecologique_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_dette_ecologique_data(company))
```

- [ ] **Step 3.4: Ajouter les URLs dans urls.py**

Dans `dashboard/urls.py`, ajouter après les entrées mesure_empreinte :

```python
path('dette-ecologique/', views.dette_ecologique, name='dette_ecologique'),
path('api/company/<int:pk>/dette-ecologique/', views.dette_ecologique_data, name='dette_ecologique_data'),
```

- [ ] **Step 3.5: Ajouter l'entrée sidebar dans base.html**

Dans `templates/base.html`, après le `</li>` qui clôt l'entrée "Risque physique", ajouter :

```html
<li>
  <a href="{% url 'dashboard:dette_ecologique' %}"
     class="sidebar__nav-sublink {% block nav_dette_ecologique %}{% endblock %}"
     aria-label="Dette écologique">
    Dette écologique
  </a>
</li>
```

- [ ] **Step 3.6: Créer un template vide temporaire pour que la vue ne plante pas**

Créer `dashboard/templates/dashboard/dette_ecologique.html` avec contenu minimal :

```html
{% extends "base.html" %}
{% block title %}Dette écologique — Easybiodiv{% endblock %}
{% block nav_risks_open %}open{% endblock %}
{% block nav_dette_ecologique %}active{% endblock %}
{% block content %}<p>Coming soon</p>{% endblock %}
```

- [ ] **Step 3.7: Vérifier que les tests de vue passent**

```bash
pytest dashboard/tests.py::DetteEcologiqueViewTests -v
```

Attendu : 2 tests PASSED.

- [ ] **Step 3.8: Commit**

```bash
git add dashboard/views.py dashboard/urls.py templates/base.html \
        dashboard/templates/dashboard/dette_ecologique.html dashboard/tests.py
git commit -m "feat(dashboard): add dette_ecologique views, URLs and nav entry"
```

---

## Task 4 — CSS pour la page dette_ecologique

**Files:**
- Modify: `dashboard/static/dashboard/css/style.css`

- [ ] **Step 4.1: Ajouter les classes CSS**

Ajouter à la fin de `dashboard/static/dashboard/css/style.css` :

```css
/* ── Dette écologique ─────────────────────────────────────────────────────── */

.de-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
  height: 100%;
  box-sizing: border-box;
}

.de-toggle-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.de-toggle-label {
  color: var(--color-on-surface-variant);
  font-size: 11px;
}

.de-toggle {
  display: flex;
  border: 1.5px solid var(--color-outline-variant);
  border-radius: var(--radius-full);
  overflow: hidden;
  background: var(--color-surface-container-low);
}

.de-toggle__btn {
  padding: 4px 14px;
  font-size: 12px;
  font-family: inherit;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-on-surface-variant);
  transition: background 0.15s, color 0.15s;
  line-height: 1.5;
}

.de-toggle__btn--active {
  background: var(--color-primary);
  color: var(--color-on-primary);
}

.de-map-card {
  flex: 1;
  position: relative;
  min-height: 420px;
  padding: 0;
  overflow: hidden;
}

.de-map {
  width: 100%;
  height: 100%;
  min-height: 420px;
}

.de-legend {
  position: absolute;
  bottom: 24px;
  right: 12px;
  background: rgba(251, 249, 244, 0.96);
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  max-width: 190px;
  z-index: 10;
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
}

.de-legend__title {
  font-size: 10px;
  color: var(--color-on-surface-variant);
  margin-bottom: 6px;
}

.de-legend__list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.de-legend__item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.de-legend__swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}

.de-legend__name {
  flex: 1;
  color: var(--color-on-surface);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.de-legend__pct {
  color: var(--color-on-surface-variant);
  font-variant-numeric: tabular-nums;
}

.de-tooltip {
  position: absolute;
  background: var(--color-surface-container-lowest);
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-md);
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.6;
  pointer-events: none;
  z-index: 20;
  max-width: 210px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
}

.de-tooltip__swatch {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  margin-right: 4px;
  vertical-align: middle;
}
```

- [ ] **Step 4.2: Commit**

```bash
git add dashboard/static/dashboard/css/style.css
git commit -m "feat(dashboard): add dette_ecologique CSS"
```

---

## Task 5 — Template dette_ecologique.html (version complète)

**Files:**
- Modify: `dashboard/templates/dashboard/dette_ecologique.html`

- [ ] **Step 5.1: Remplacer le template temporaire par la version complète**

Écraser `dashboard/templates/dashboard/dette_ecologique.html` avec :

```html
{% extends "base.html" %}
{% load static %}

{% block title %}Dette écologique — Easybiodiv{% endblock %}

{% block nav_risks_open %}open{% endblock %}
{% block nav_dette_ecologique %}active{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css">
{% endblock %}

{% block header_left %}
<div class="company-combobox" id="company-combobox" role="combobox"
     aria-expanded="false" aria-haspopup="listbox" aria-owns="company-listbox">
  <span class="company-combobox__label label-caps">Entreprise</span>
  <div class="company-combobox__input-wrap">
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <circle cx="6" cy="6" r="4.5" stroke="currentColor" stroke-width="1.3"/>
      <path d="M10 10l2.5 2.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
    </svg>
    <input type="text" id="company-search" class="company-combobox__input"
           placeholder="Rechercher une entreprise…"
           autocomplete="off" aria-autocomplete="list"
           aria-controls="company-listbox" aria-label="Sélectionner une entreprise">
    <svg class="company-combobox__chevron" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M3 5l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
  </div>
  <ul id="company-listbox" class="company-combobox__listbox" role="listbox" hidden></ul>
</div>
{% endblock header_left %}

{% block content %}
<div class="de-page">

  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="de-total-lbiodiv">—</div>
      <div class="kpi-card__label label-caps">Lbiodiv total</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="de-year">—</div>
      <div class="kpi-card__label label-caps">Année de référence</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="de-point-count">—</div>
      <div class="kpi-card__label label-caps" id="de-point-count-label">Assets</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="de-top-commodity">—</div>
      <div class="kpi-card__label label-caps">Top commodité</div>
    </div>
  </div>

  <div class="de-toggle-row">
    <span class="label-caps de-toggle-label">Regrouper par :</span>
    <div class="de-toggle" role="group" aria-label="Mode d'affichage">
      <button class="de-toggle__btn de-toggle__btn--active"
              data-mode="asset" aria-pressed="true">Par asset</button>
      <button class="de-toggle__btn"
              data-mode="region" aria-pressed="false">Par région subnational</button>
    </div>
  </div>

  <div class="card de-map-card">
    <div id="de-map" class="de-map"></div>
    <div class="de-legend" id="de-legend" aria-label="Légende commodités">
      <div class="de-legend__title label-caps">Commodités</div>
      <ul class="de-legend__list" id="de-legend-list"></ul>
    </div>
    <div class="de-tooltip" id="de-tooltip" hidden></div>
  </div>

</div>
{% endblock %}

{% block extra_js %}
{{ initial_data|json_script:"de-data" }}
{{ companies|json_script:"de-companies" }}
<script>var DE_API_URL = "{% url 'dashboard:dette_ecologique_data' pk=0 %}";</script>
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
<script src="{% static 'dashboard/js/dette_ecologique.js' %}" defer></script>
{% endblock %}
```

- [ ] **Step 5.2: Vérifier la page en navigateur**

```bash
python manage.py runserver
```

Naviguer vers `http://localhost:8000/dette-ecologique/` (après login). La page doit afficher les KPIs, le toggle et un conteneur de carte vide (le JS n'existe pas encore). Pas d'erreur 500.

- [ ] **Step 5.3: Commit**

```bash
git add dashboard/templates/dashboard/dette_ecologique.html
git commit -m "feat(dashboard): complete dette_ecologique template"
```

---

## Task 6 — JS : dette_ecologique.js

**Files:**
- Create: `dashboard/static/dashboard/js/dette_ecologique.js`

- [ ] **Step 6.1: Créer le fichier JS**

Créer `dashboard/static/dashboard/js/dette_ecologique.js` avec le contenu suivant :

```javascript
'use strict';

const DE_COMPANY_KEY = 'selected-company-id';

const DE_PIE_COLORS = [
  '#2d6a4f', '#74c69d', '#d4a373', '#e76f51',
  '#457b9d', '#e9c46a', '#8338ec', '#f4a261',
];

const DE_STATE = {
  data: null,
  mode: 'asset',
  map: null,
  markers: [],
  colorMap: {},
};

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('de-companies');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('de-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  DE_STATE.map = deInitMap();
  deInitToggle();

  const savedId = parseInt(localStorage.getItem(DE_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  DE_STATE.map.on('load', () => {
    if (savedExists && initialData && savedId !== initialData.company_id) {
      fetch(DE_API_URL.replace('/0/', '/' + savedId + '/'))
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(data => { deRender(data); deInitCombobox(companies, data); })
        .catch(err => { console.error('dette_ecologique fetch failed:', err); deInitCombobox(companies, initialData); });
    } else {
      if (initialData) deRender(initialData);
      deInitCombobox(companies, initialData);
    }
  });
});


function deInitMap() {
  return new maplibregl.Map({
    container: 'de-map',
    style: 'https://demotiles.maplibre.org/style.json',
    center: [0, 20],
    zoom: 1.5,
  });
}


function deInitToggle() {
  document.querySelectorAll('.de-toggle__btn').forEach(btn => {
    btn.addEventListener('click', () => {
      DE_STATE.mode = btn.dataset.mode;
      document.querySelectorAll('.de-toggle__btn').forEach(b => {
        const active = b === btn;
        b.classList.toggle('de-toggle__btn--active', active);
        b.setAttribute('aria-pressed', String(active));
      });
      if (DE_STATE.data) {
        deRenderMarkers(DE_STATE.data);
        deUpdatePointCountKpi(DE_STATE.data);
      }
    });
  });
}


function deRender(data) {
  DE_STATE.data = data;
  deBuildColorMap(data.commodities);
  deRenderKpis(data);
  deRenderLegend(data.commodities);
  deRenderMarkers(data);
}


function deBuildColorMap(commodities) {
  DE_STATE.colorMap = {};
  [...commodities]
    .sort((a, b) => a.name.localeCompare(b.name))
    .forEach((c, i) => {
      DE_STATE.colorMap[c.name] = DE_PIE_COLORS[i % DE_PIE_COLORS.length];
    });
}


function deRenderKpis(data) {
  const elImpact = document.getElementById('de-total-lbiodiv');
  if (elImpact) elImpact.textContent = data.total_lbiodiv ? deFmtLbiodiv(data.total_lbiodiv) : '—';

  const elYear = document.getElementById('de-year');
  if (elYear) elYear.textContent = data.year != null ? data.year : '—';

  const elTop = document.getElementById('de-top-commodity');
  if (elTop) elTop.textContent = data.commodities.length ? data.commodities[0].name : '—';

  deUpdatePointCountKpi(data);
}


function deUpdatePointCountKpi(data) {
  const points = DE_STATE.mode === 'asset' ? data.assets : data.regions;
  const elCount = document.getElementById('de-point-count');
  if (elCount) elCount.textContent = points.length || '—';
  const elLabel = document.getElementById('de-point-count-label');
  if (elLabel) elLabel.textContent = DE_STATE.mode === 'asset' ? 'Assets' : 'Régions';
}


function deRenderLegend(commodities) {
  const list = document.getElementById('de-legend-list');
  if (!list) return;
  list.innerHTML = commodities.slice(0, 8).map(c => {
    const color = DE_STATE.colorMap[c.name] || '#ccc';
    return (
      '<li class="de-legend__item">' +
      '<span class="de-legend__swatch" style="background:' + color + '"></span>' +
      '<span class="de-legend__name">' + escHtml(c.name) + '</span>' +
      '<span class="de-legend__pct">' + (c.pct * 100).toFixed(1) + '%</span>' +
      '</li>'
    );
  }).join('');
}


function deRenderMarkers(data) {
  DE_STATE.markers.forEach(m => m.remove());
  DE_STATE.markers = [];

  const points = DE_STATE.mode === 'asset' ? data.assets : data.regions;
  if (!points.length) return;

  const maxLbiodiv = points.reduce((m, p) => p.total_lbiodiv > m ? p.total_lbiodiv : m, 0);
  const MIN_R = 18, MAX_R = 60;

  points.forEach(point => {
    const r = maxLbiodiv > 0
      ? MIN_R + (MAX_R - MIN_R) * Math.sqrt(point.total_lbiodiv / maxLbiodiv)
      : MIN_R;
    const el = deBuildPieEl(point, r);
    const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
      .setLngLat([point.longitude, point.latitude])
      .addTo(DE_STATE.map);
    DE_STATE.markers.push(marker);
  });
}


function deBuildPieEl(point, r) {
  const size = r * 2;
  const cx = r, cy = r;
  const NS = 'http://www.w3.org/2000/svg';

  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('viewBox', '0 0 ' + size + ' ' + size);
  svg.style.cursor = 'pointer';
  svg.style.overflow = 'visible';

  let startAngle = -Math.PI / 2;
  point.commodities.forEach(c => {
    const slice = c.pct * 2 * Math.PI;
    const endAngle = startAngle + slice;
    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle);
    const y2 = cy + r * Math.sin(endAngle);
    const large = slice > Math.PI ? 1 : 0;
    const color = DE_STATE.colorMap[c.name] || '#ccc';

    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d',
      'M' + cx + ',' + cy +
      ' L' + x1 + ',' + y1 +
      ' A' + r + ',' + r + ' 0 ' + large + ',1 ' + x2 + ',' + y2 + ' Z'
    );
    path.setAttribute('fill', color);
    path.setAttribute('stroke', '#fff');
    path.setAttribute('stroke-width', '1');
    svg.appendChild(path);
    startAngle = endAngle;
  });

  const border = document.createElementNS(NS, 'circle');
  border.setAttribute('cx', cx);
  border.setAttribute('cy', cy);
  border.setAttribute('r', r);
  border.setAttribute('fill', 'none');
  border.setAttribute('stroke', '#fff');
  border.setAttribute('stroke-width', '2');
  svg.appendChild(border);

  svg.addEventListener('mouseenter', e => deShowTooltip(point, e));
  svg.addEventListener('mousemove', e => deMoveTooltip(e));
  svg.addEventListener('mouseleave', deHideTooltip);

  return svg;
}


function deShowTooltip(point, e) {
  const tip = document.getElementById('de-tooltip');
  if (!tip) return;
  const top3 = point.commodities.slice(0, 3);
  tip.innerHTML =
    '<strong>' + escHtml(point.name) + '</strong><br>' +
    'Lbiodiv : ' + deFmtLbiodiv(point.total_lbiodiv) + '<br>' +
    top3.map(c =>
      '<span class="de-tooltip__swatch" style="background:' + (DE_STATE.colorMap[c.name] || '#ccc') + '"></span>' +
      escHtml(c.name) + ' : ' + (c.pct * 100).toFixed(1) + '%'
    ).join('<br>');
  tip.hidden = false;
  deMoveTooltip(e);
}


function deMoveTooltip(e) {
  const tip = document.getElementById('de-tooltip');
  const mapEl = document.getElementById('de-map');
  if (!tip || !mapEl) return;
  const rect = mapEl.getBoundingClientRect();
  tip.style.left = (e.clientX - rect.left + 14) + 'px';
  tip.style.top  = (e.clientY - rect.top  + 14) + 'px';
}


function deHideTooltip() {
  const tip = document.getElementById('de-tooltip');
  if (tip) tip.hidden = true;
}


function deInitCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');
  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData) input.value = initialData.company_name;

  function buildList(filter) {
    const q = filter.toLowerCase();
    listbox.innerHTML = companies
      .filter(c => c.name.toLowerCase().includes(q))
      .map(c =>
        '<li role="option" data-id="' + c.id + '" class="company-combobox__option' +
        (c.id === selected ? ' selected' : '') + '">' + escHtml(c.name) + '</li>'
      ).join('');
  }

  function openList() {
    buildList(input.value);
    listbox.removeAttribute('hidden');
    combobox.setAttribute('aria-expanded', 'true');
    if (chevron) chevron.style.transform = 'rotate(180deg)';
  }

  function closeList() {
    listbox.setAttribute('hidden', '');
    combobox.setAttribute('aria-expanded', 'false');
    if (chevron) chevron.style.transform = '';
  }

  input.addEventListener('focus', () => openList());
  input.addEventListener('input', () => { buildList(input.value); openList(); });

  listbox.addEventListener('click', e => {
    const opt = e.target.closest('[role="option"]');
    if (!opt) return;
    const id = parseInt(opt.dataset.id, 10);
    selected = id;
    input.value = opt.textContent;
    closeList();
    localStorage.setItem(DE_COMPANY_KEY, id);
    fetch(DE_API_URL.replace('/0/', '/' + id + '/'))
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => deRender(data))
      .catch(err => console.error('dette_ecologique fetch failed:', err));
  });

  document.addEventListener('click', e => {
    if (!combobox.contains(e.target)) closeList();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeList();
  });
}


function deFmtLbiodiv(val) {
  if (val >= 1e9) return (val / 1e9).toFixed(2) + ' G';
  if (val >= 1e6) return (val / 1e6).toFixed(2) + ' M';
  if (val >= 1e3) return (val / 1e3).toFixed(2) + ' k';
  return val.toFixed(2);
}
```

- [ ] **Step 6.2: Vérifier la page complète en navigateur**

```bash
python manage.py runserver
```

1. Se connecter, naviguer vers `http://localhost:8000/dette-ecologique/`.
2. La carte MapLibre s'affiche avec des marqueurs pie chart pour chaque asset.
3. Le toggle "Par région subnational" regroupe les points par région.
4. Les KPIs (Lbiodiv total, année, compteur, top commodité) se mettent à jour.
5. La légende flottante liste les commodités avec couleurs et pourcentages.
6. Le survol d'un marqueur affiche le tooltip avec nom, Lbiodiv et top 3 commodités.
7. Le switch entreprise dans le combobox recharge les données via l'API.

- [ ] **Step 6.3: Vérifier que "Mesure d'empreinte" fonctionne toujours**

Naviguer vers `http://localhost:8000/mesure-empreinte/` — la page doit s'afficher normalement (même contenu qu'avant le renommage).

- [ ] **Step 6.4: Lancer la suite de tests complète**

```bash
pytest dashboard/tests.py -v
```

Attendu : tous les tests PASSED.

- [ ] **Step 6.5: Commit final**

```bash
git add dashboard/static/dashboard/js/dette_ecologique.js
git commit -m "feat(dashboard): add dette_ecologique JS — map + pie chart markers"
```
