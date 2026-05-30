# Dependencies Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/dependencies/` page that displays ecosystem service dependency analysis per company — supply chain reliance by scope tier, service exposure, and revenue by economic segment.

**Architecture:** New view function `_get_dependencies_data(company)` in `dashboard/views.py` backed by module-level constants (`SCORE_MAP`, `SERVICES`, etc.). Template and JS follow the exact pattern of `transition_risk.html` / `transition_risk.js`. CSS appended to the existing `style.css`.

**Tech Stack:** Django (CBV-free, FBV pattern), vanilla JS, existing CSS tokens in `style.css`.

---

## File Map

| Action | Path |
|---|---|
| Modify | `dashboard/views.py` — add constants + `_get_dependencies_data()` + 2 views |
| Modify | `dashboard/urls.py` — add 2 URL patterns |
| Modify | `dashboard/tests.py` — add `DependenciesDataTests` + `DependenciesPageTests` |
| Modify | `dashboard/static/dashboard/css/style.css` — append dependencies section |
| Create | `dashboard/templates/dashboard/dependencies.html` |
| Create | `dashboard/static/dashboard/js/dependencies.js` |
| Modify | `templates/base.html` — fix sidebar link |

---

## Task 1 — Backend constants + `_get_dependencies_data()`

**Files:**
- Modify: `dashboard/views.py`
- Modify: `dashboard/tests.py`

- [ ] **Step 1.1 — Write failing tests for score conversion and data function**

In `dashboard/tests.py`, add after the existing imports block:

```python
from .models import (
    Asset, Commodity, Company, Company_Policy, Company_Revenue,
    Company_Revenue_Sector, Country, Ownership, Policy_Level,
    Policy_Subcategory, Policy_Type, Production, Sector, SubnationalRegion,
    SubSector,
)
```

Replace the existing import block (lines 4-8) with the above. Then add this test class at the end of the file:

```python
class DependenciesDataTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='depuser', password='testpass')
        self.client.force_login(self.user)

        self.company = Company.objects.create(name='DepCorp')
        self.country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private'
        )
        self.region = SubnationalRegion.objects.create(name='IDF', country=self.country)
        # Commodity with known dependency scores: water=H(0.7), soil=M(0.5), rest=VL(0.0)
        self.commodity = Commodity.objects.create(
            name='TestCom',
            dependency_water='H',
            dependency_soil_quality='M',
            dependency_carbon_sequestration='VL',
            dependency_water_purification='VL',
            dependency_pest_control='VL',
            dependency_pollination='VL',
        )
        Production.objects.create(
            company=self.company,
            commodity=self.commodity,
            year=2024,
            production=100.0,
            scope='direct',
        )

    def test_score_map_conversion(self):
        from .views import SCORE_MAP
        self.assertEqual(SCORE_MAP['VL'], 0.0)
        self.assertEqual(SCORE_MAP['L'],  0.2)
        self.assertEqual(SCORE_MAP['M'],  0.5)
        self.assertEqual(SCORE_MAP['H'],  0.7)
        self.assertEqual(SCORE_MAP['VH'], 1.0)

    def test_global_exposure_score(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        # 6 services: water=0.7, soil=0.5, rest=0.0 → avg = (0.7+0.5+0+0+0+0)/6
        expected = round((0.7 + 0.5) / 6, 3)
        self.assertAlmostEqual(data['global_exposure_score'], expected, places=3)

    def test_critical_nodes_counts_h_or_vh(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        # water=H(0.7) → this commodity×scope is critical
        self.assertEqual(data['critical_nodes'], 1)

    def test_primary_service_is_highest_avg(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        self.assertEqual(data['primary_service']['key'], 'water')
        self.assertAlmostEqual(data['primary_service']['score'], 0.7, places=3)

    def test_supply_chain_grouped_by_scope(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        scopes = [t['scope'] for t in data['supply_chain']]
        self.assertIn('direct', scopes)

    def test_supply_chain_only_shows_services_above_threshold(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        direct_tier = next(t for t in data['supply_chain'] if t['scope'] == 'direct')
        # Only water(0.7) and soil(0.5) are >= 0.2
        service_keys = [s['key'] for s in direct_tier['services']]
        self.assertIn('water', service_keys)
        self.assertIn('soil_quality', service_keys)
        self.assertNotIn('pollination', service_keys)

    def test_supply_chain_labels(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        direct_tier = next(t for t in data['supply_chain'] if t['scope'] == 'direct')
        water_svc = next(s for s in direct_tier['services'] if s['key'] == 'water')
        self.assertEqual(water_svc['label'], 'Critical')
        soil_svc = next(s for s in direct_tier['services'] if s['key'] == 'soil_quality')
        self.assertEqual(soil_svc['label'], 'High')

    def test_empty_company_returns_defaults(self):
        from .views import _get_dependencies_data
        empty = Company.objects.create(name='Empty')
        data = _get_dependencies_data(empty)
        self.assertIsNone(data['year'])
        self.assertEqual(data['global_exposure_score'], 0)
        self.assertEqual(data['critical_nodes'], 0)
        self.assertIsNone(data['primary_service'])
        self.assertEqual(data['supply_chain'], [])

    def test_revenue_segments_sorted_by_revenue_desc(self):
        from .views import _get_dependencies_data
        sector = Sector.objects.create(name='Agri')
        sub1 = SubSector.objects.create(
            name='Céréales', sector=sector,
            Water_dependency='H', Pollination_dependency='VL',
            Soil_quality_dependency='VL', Carbon_Sequestration='VL',
            Water_purification_dependency='VL', Pest_control_dependency='VL',
        )
        sub2 = SubSector.objects.create(
            name='Légumes', sector=sector,
            Water_dependency='L', Pollination_dependency='VL',
            Soil_quality_dependency='VL', Carbon_Sequestration='VL',
            Water_purification_dependency='VL', Pest_control_dependency='VL',
        )
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=sub1, year=2024, revenue=12_000_000
        )
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=sub2, year=2024, revenue=5_000_000
        )
        data = _get_dependencies_data(self.company)
        self.assertEqual(len(data['revenue_segments']), 2)
        self.assertEqual(data['revenue_segments'][0]['subsector'], 'Céréales')
        self.assertEqual(data['revenue_segments'][0]['exposure_label'], 'High')
        self.assertEqual(data['revenue_segments'][1]['subsector'], 'Légumes')
        self.assertEqual(data['revenue_segments'][1]['exposure_label'], 'Low')

    def test_uses_latest_year_only(self):
        from .views import _get_dependencies_data
        commodity2 = Commodity.objects.create(
            name='OldCom',
            dependency_water='VH',
            dependency_soil_quality='VH',
            dependency_carbon_sequestration='VH',
            dependency_water_purification='VH',
            dependency_pest_control='VH',
            dependency_pollination='VH',
        )
        # Older year — should be ignored
        Production.objects.create(
            company=self.company, commodity=commodity2, year=2020,
            production=999.0, scope='direct',
        )
        data = _get_dependencies_data(self.company)
        self.assertEqual(data['year'], 2024)
        # primary service should still reflect 2024 commodity, not 2020 VH one
        expected_score = round((0.7 + 0.5) / 6, 3)
        self.assertAlmostEqual(data['global_exposure_score'], expected_score, places=3)

    def test_productions_via_asset_included(self):
        from .views import _get_dependencies_data
        asset = Asset.objects.create(
            name='Site B', latitude=0.0, longitude=0.0,
            country=self.country, subnational_region=self.region,
        )
        Ownership.objects.create(Asset=asset, Company=self.company, ownership='100%')
        commodity_vh = Commodity.objects.create(
            name='AssetCom',
            dependency_water='VH',
            dependency_soil_quality='VH',
            dependency_carbon_sequestration='VH',
            dependency_water_purification='VH',
            dependency_pest_control='VH',
            dependency_pollination='VH',
        )
        Production.objects.create(
            asset=asset, commodity=commodity_vh, year=2024,
            production=50.0, scope='tier 1',
        )
        data = _get_dependencies_data(self.company)
        # 'tier 1' scope should appear because asset-linked production was included
        scopes = [t['scope'] for t in data['supply_chain']]
        self.assertIn('tier 1', scopes)

    def test_service_exposure_with_revenue(self):
        from .views import _get_dependencies_data
        Company_Revenue.objects.create(
            company=self.company, year=2024, revenue=10_000_000, currency='EUR'
        )
        data = _get_dependencies_data(self.company)
        se = data['service_exposure']
        self.assertEqual(se['total_revenue'], 10_000_000)
        self.assertEqual(se['currency'], 'EUR')
        water_svc = next(
            s for cat in se['categories'] for s in cat['services'] if s['key'] == 'water'
        )
        self.assertAlmostEqual(water_svc['revenue_exposure'], round(0.7 * 10_000_000), delta=1)

    def test_service_exposure_without_revenue(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        se = data['service_exposure']
        self.assertIsNone(se['total_revenue'])
        water_svc = next(
            s for cat in se['categories'] for s in cat['services'] if s['key'] == 'water'
        )
        self.assertIsNone(water_svc['revenue_exposure'])
```

- [ ] **Step 1.2 — Run tests to confirm they fail**

```
python manage.py test dashboard.tests.DependenciesDataTests -v 2
```

Expected: Multiple failures with `ImportError: cannot import name 'SCORE_MAP'` or similar.

- [ ] **Step 1.3 — Add constants and helper functions to `views.py`**

At the top of `dashboard/views.py`, after the existing imports, add:

```python
from django.db.models import Q
from .models import Asset, Company, Company_Policy, Company_Revenue, Company_Revenue_Sector, Production
```

Replace the existing import line `from .models import Asset, Company, Company_Policy, Production` with the above.

Then add these constants after the imports, before the first function:

```python
SCORE_MAP = {'VL': 0.0, 'L': 0.2, 'M': 0.5, 'H': 0.7, 'VH': 1.0}

SERVICES = [
    {'key': 'water',                'name': 'Approvisionnement en eau', 'category': 'provisioning'},
    {'key': 'soil_quality',         'name': 'Qualité des sols',         'category': 'provisioning'},
    {'key': 'carbon_sequestration', 'name': 'Séquestration carbone',    'category': 'regulation'},
    {'key': 'water_purification',   'name': 'Épuration de l\'eau',      'category': 'regulation'},
    {'key': 'pest_control',         'name': 'Contrôle des ravageurs',   'category': 'regulation'},
    {'key': 'pollination',          'name': 'Pollinisation',            'category': 'regulation'},
]

_COMMODITY_DEP_FIELDS = {
    'water':                'dependency_water',
    'soil_quality':         'dependency_soil_quality',
    'carbon_sequestration': 'dependency_carbon_sequestration',
    'water_purification':   'dependency_water_purification',
    'pest_control':         'dependency_pest_control',
    'pollination':          'dependency_pollination',
}

_SUBSECTOR_DEP_FIELDS = {
    'water':                'Water_dependency',
    'soil_quality':         'Soil_quality_dependency',
    'carbon_sequestration': 'Carbon_Sequestration',
    'water_purification':   'Water_purification_dependency',
    'pest_control':         'Pest_control_dependency',
    'pollination':          'Pollination_dependency',
}

_SCOPE_LABELS = {
    'direct':       'Opérations directes',
    'tier 1':       'Tier 1 : Chaîne d\'approvisionnement',
    'tier 2':       'Tier 2 : Approvisionnement amont',
    'raw material': 'Matières premières',
}

_SCOPE_ORDER = ['direct', 'tier 1', 'tier 2', 'raw material']


def _exposure_label(score):
    if score >= 0.7:
        return 'Critical'
    if score >= 0.5:
        return 'High'
    if score >= 0.2:
        return 'Moderate'
    return 'Low'


def _commodity_dep_scores(commodity):
    return {svc['key']: SCORE_MAP[getattr(commodity, _COMMODITY_DEP_FIELDS[svc['key']])]
            for svc in SERVICES}
```

- [ ] **Step 1.4 — Add `_get_dependencies_data()` function to `views.py`**

Add after `_commodity_dep_scores` (still before the existing view functions):

```python
def _get_dependencies_data(company):
    empty = {
        'company_id': company.pk,
        'company_name': company.name,
        'year': None,
        'global_exposure_score': 0,
        'critical_nodes': 0,
        'primary_service': None,
        'supply_chain': [],
        'service_exposure': {'total_revenue': None, 'currency': None, 'categories': []},
        'revenue_segments': [],
    }

    productions_qs = Production.objects.filter(
        Q(company=company) | Q(asset__ownership__Company=company)
    ).select_related('commodity').distinct()

    max_year = productions_qs.aggregate(Max('year'))['year__max']
    if max_year is None:
        return empty

    productions = list(productions_qs.filter(year=max_year))

    # --- KPIs ---
    all_scores = []
    critical_nodes = set()
    service_totals = {svc['key']: [] for svc in SERVICES}

    for p in productions:
        scores = _commodity_dep_scores(p.commodity)
        all_scores.extend(scores.values())
        for key, val in scores.items():
            service_totals[key].append(val)
        if any(v >= 0.7 for v in scores.values()):
            critical_nodes.add((p.commodity_id, p.scope))

    global_score = sum(all_scores) / len(all_scores) if all_scores else 0

    service_avgs = {
        key: (sum(vals) / len(vals) if vals else 0)
        for key, vals in service_totals.items()
    }

    primary_key = max(service_avgs, key=service_avgs.get)
    primary_svc = next(s for s in SERVICES if s['key'] == primary_key)

    # --- Supply Chain ---
    scope_groups = defaultdict(list)
    for p in productions:
        scope_groups[p.scope].append(_commodity_dep_scores(p.commodity))

    supply_chain = []
    for scope in _SCOPE_ORDER:
        if scope not in scope_groups:
            continue
        group = scope_groups[scope]
        svc_avgs = {
            svc['key']: sum(s[svc['key']] for s in group) / len(group)
            for svc in SERVICES
        }
        services_out = []
        for svc in sorted(SERVICES, key=lambda s: -svc_avgs[s['key']]):
            score = svc_avgs[svc['key']]
            if score < 0.2:
                continue
            services_out.append({
                'key': svc['key'],
                'name': svc['name'],
                'score': round(score, 3),
                'label': _exposure_label(score),
            })
            if len(services_out) == 4:
                break
        if services_out:
            supply_chain.append({
                'scope': scope,
                'label': _SCOPE_LABELS[scope],
                'services': services_out,
            })

    # --- Service Exposure ---
    revenue_obj = (
        Company_Revenue.objects.filter(company=company).order_by('-year').first()
    )
    total_revenue = revenue_obj.revenue if revenue_obj else None
    currency = revenue_obj.currency if revenue_obj else None

    categories = []
    for cat_name, cat_keys in [
        ('Services de provisionnement', ['water', 'soil_quality']),
        ('Services de régulation',      ['carbon_sequestration', 'water_purification',
                                          'pest_control', 'pollination']),
    ]:
        svcs_out = []
        for key in cat_keys:
            score = service_avgs[key]
            svc_info = next(s for s in SERVICES if s['key'] == key)
            svcs_out.append({
                'key': key,
                'name': svc_info['name'],
                'score': round(score, 3),
                'revenue_exposure': (
                    round(score * total_revenue) if total_revenue is not None else None
                ),
            })
        categories.append({'name': cat_name, 'services': svcs_out})

    # --- Revenue Segments ---
    rev_sector_qs = (
        Company_Revenue_Sector.objects.filter(company=company)
        .select_related('subsector__sector')
        .order_by('subsector_id', '-year')
    )
    seen = {}
    for rs in rev_sector_qs:
        if rs.subsector_id not in seen:
            seen[rs.subsector_id] = rs

    revenue_segments = []
    for rs in sorted(seen.values(), key=lambda x: -x.revenue):
        sub = rs.subsector
        scores = [SCORE_MAP[getattr(sub, _SUBSECTOR_DEP_FIELDS[svc['key']])] for svc in SERVICES]
        dep_score = sum(scores) / len(scores)
        revenue_segments.append({
            'subsector': sub.name,
            'sector': sub.sector.name,
            'revenue': rs.revenue,
            'dep_score': round(dep_score, 3),
            'exposure_label': _exposure_label(dep_score),
        })

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'year': max_year,
        'global_exposure_score': round(global_score, 3),
        'critical_nodes': len(critical_nodes),
        'primary_service': {
            'key': primary_svc['key'],
            'name': primary_svc['name'],
            'score': round(service_avgs[primary_key], 3),
        },
        'supply_chain': supply_chain,
        'service_exposure': {
            'total_revenue': total_revenue,
            'currency': currency,
            'categories': categories,
        },
        'revenue_segments': revenue_segments,
    }
```

- [ ] **Step 1.5 — Run tests to confirm they pass**

```
python manage.py test dashboard.tests.DependenciesDataTests -v 2
```

Expected: All tests PASS.

- [ ] **Step 1.6 — Commit**

```
git add dashboard/views.py dashboard/tests.py
git commit -m "feat(dependencies): add backend data function and tests"
```

---

## Task 2 — URL wiring + view functions

**Files:**
- Modify: `dashboard/views.py`
- Modify: `dashboard/urls.py`
- Modify: `dashboard/tests.py`

- [ ] **Step 2.1 — Write failing tests for the views**

Add at the end of `dashboard/tests.py`:

```python
class DependenciesPageViewTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='deppage', password='testpass')
        self.client.force_login(self.user)

    def test_redirects_anonymous(self):
        self.client.logout()
        response = self.client.get('/dependencies/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_returns_200_authenticated(self):
        response = self.client.get('/dependencies/')
        self.assertEqual(response.status_code, 200)

    def test_uses_correct_template(self):
        response = self.client.get('/dependencies/')
        self.assertTemplateUsed(response, 'dashboard/dependencies.html')

    def test_companies_in_context(self):
        Company.objects.create(name='CtxCorp')
        response = self.client.get('/dependencies/')
        self.assertIn('companies', response.context)

    def test_initial_data_none_without_companies(self):
        response = self.client.get('/dependencies/')
        self.assertIsNone(response.context['initial_data'])

    def test_api_returns_200(self):
        company = Company.objects.create(name='ApiCorp')
        url = reverse('dashboard:dependencies_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_api_content_type_is_json(self):
        company = Company.objects.create(name='JsonCorp')
        url = reverse('dashboard:dependencies_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertIn('application/json', response['Content-Type'])

    def test_api_404_on_missing_company(self):
        url = reverse('dashboard:dependencies_data', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_api_post_not_allowed(self):
        company = Company.objects.create(name='PostCorp')
        url = reverse('dashboard:dependencies_data', kwargs={'pk': company.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 405)
```

- [ ] **Step 2.2 — Run to confirm failures**

```
python manage.py test dashboard.tests.DependenciesPageViewTests -v 2
```

Expected: Failures with URL resolution errors.

- [ ] **Step 2.3 — Add view functions to `views.py`**

Add at the end of `dashboard/views.py`:

```python
@login_required
@require_GET
def dependencies(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_dependencies_data(first)
    return render(request, 'dashboard/dependencies.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@login_required
@require_GET
def dependencies_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_dependencies_data(company))
```

- [ ] **Step 2.4 — Add URL patterns to `urls.py`**

In `dashboard/urls.py`, add two entries to `urlpatterns`:

```python
path('dependencies/', views.dependencies, name='dependencies'),
path('api/company/<int:pk>/dependencies/', views.dependencies_data, name='dependencies_data'),
```

Full file should look like:

```python
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/company/<int:pk>/', views.company_data, name='company_data'),
    path('transition-risk/', views.transition_risk, name='transition_risk'),
    path('api/company/<int:pk>/transition-risk/', views.transition_risk_data, name='transition_risk_data'),
    path('dependencies/', views.dependencies, name='dependencies'),
    path('api/company/<int:pk>/dependencies/', views.dependencies_data, name='dependencies_data'),
]
```

- [ ] **Step 2.5 — Run tests**

```
python manage.py test dashboard.tests.DependenciesPageViewTests -v 2
```

Expected: All pass (the template doesn't exist yet, but Django test client will raise `TemplateDoesNotExist` — if tests fail for that reason, create an empty placeholder template `dashboard/templates/dashboard/dependencies.html` with content `{% extends "base.html" %}{% block content %}{% endblock %}` and re-run).

- [ ] **Step 2.6 — Commit**

```
git add dashboard/views.py dashboard/urls.py dashboard/tests.py
git commit -m "feat(dependencies): add view functions and URL patterns"
```

---

## Task 3 — CSS

**Files:**
- Modify: `dashboard/static/dashboard/css/style.css`

- [ ] **Step 3.1 — Append dependencies CSS section to `style.css`**

Add at the end of `dashboard/static/dashboard/css/style.css`:

```css
/* ── Dependencies page ───────────────────────────────────────────────────── */

.dep-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Main two-column row */
.dep-main-row {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.dep-supply-chain {
  flex: 3;
  min-width: 0;
}

.dep-service-exposure {
  flex: 2;
  min-width: 0;
}

@media (max-width: 900px) {
  .dep-main-row {
    flex-direction: column;
  }
}

/* Section headers inside cards */
.dep-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.dep-section-title {
  font-size: var(--text-body-lg-size);
  font-weight: 600;
  color: var(--color-on-surface);
}

/* ── Supply chain tiers ─── */
.dep-tier {
  margin-bottom: 20px;
}

.dep-tier:last-child {
  margin-bottom: 0;
}

.dep-tier__header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.dep-tier__bullet {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-primary);
  flex-shrink: 0;
}

.dep-tier__label {
  font-size: var(--text-body-sm-size);
  font-weight: 600;
  color: var(--color-on-surface);
}

.dep-tier__divider {
  border: none;
  border-top: 1px solid var(--color-outline-variant);
  margin-bottom: 12px;
}

.dep-service-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

/* Individual service card inside a tier */
.dep-service-card {
  background: var(--color-surface-container-low);
  border: var(--border-card);
  border-radius: var(--radius-md);
  padding: 12px 14px;
}

.dep-service-card__top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.dep-service-card__icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: var(--color-on-surface-variant);
}

.dep-service-card__name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-on-surface);
  line-height: 1.3;
}

.dep-reliance-bar {
  height: 4px;
  border-radius: 2px;
  background: var(--color-surface-dim);
  margin-bottom: 6px;
  overflow: hidden;
}

.dep-reliance-bar__fill {
  height: 100%;
  border-radius: 2px;
}

.dep-reliance-bar__fill--critical { background: var(--color-primary); }
.dep-reliance-bar__fill--high     { background: var(--color-secondary); }
.dep-reliance-bar__fill--moderate { background: #8a8a70; }
.dep-reliance-bar__fill--low      { background: var(--color-surface-dim); }

.dep-service-card__label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.dep-service-card__label--critical { color: var(--color-primary); }
.dep-service-card__label--high     { color: var(--color-secondary); }
.dep-service-card__label--moderate { color: #8a8a70; }
.dep-service-card__label--low      { color: var(--color-outline); }

/* ── Service Exposure panel ─── */
.dep-exposure-category {
  margin-bottom: 18px;
}

.dep-exposure-category:last-child {
  margin-bottom: 0;
}

.dep-exposure-cat-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 10px;
}

.dep-exposure-cat-name {
  font-size: var(--text-body-sm-size);
  font-weight: 600;
  color: var(--color-on-surface);
}

.dep-exposure-cat-amount {
  font-size: var(--text-body-sm-size);
  font-weight: 600;
  color: var(--color-on-surface-variant);
}

.dep-exposure-service-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.dep-exposure-service-name {
  flex: 0 0 160px;
  font-size: 13px;
  color: var(--color-on-surface);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dep-exposure-bar-track {
  flex: 1;
  height: 6px;
  background: var(--color-surface-dim);
  border-radius: 3px;
  overflow: hidden;
}

.dep-exposure-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--color-primary);
}

.dep-exposure-amount {
  flex: 0 0 60px;
  text-align: right;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-on-surface);
}

.dep-exposure-note {
  margin-top: 14px;
  padding: 10px 12px;
  background: var(--color-surface-container-low);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--color-on-surface-variant);
  line-height: 1.5;
}

/* ── Revenue segments ─── */
.dep-revenue-segments {
  width: 100%;
}

.dep-revenue-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--color-outline-variant);
}

.dep-revenue-row:last-child {
  border-bottom: none;
}

.dep-revenue-icon {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  color: var(--color-on-surface-variant);
}

.dep-revenue-meta {
  flex: 1;
  min-width: 0;
}

.dep-revenue-subsector {
  font-size: var(--text-body-sm-size);
  font-weight: 500;
  color: var(--color-on-surface);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dep-revenue-sector {
  font-size: 12px;
  color: var(--color-on-surface-variant);
}

.dep-revenue-bar-wrap {
  flex: 2;
  min-width: 0;
}

.dep-revenue-bar-track {
  height: 8px;
  background: var(--color-surface-dim);
  border-radius: 4px;
  overflow: hidden;
}

.dep-revenue-bar-fill {
  height: 100%;
  border-radius: 4px;
}

.dep-revenue-bar-fill--high     { background: var(--color-primary); }
.dep-revenue-bar-fill--moderate { background: var(--color-secondary); }
.dep-revenue-bar-fill--low      { background: var(--color-surface-dim); }

.dep-revenue-amount {
  flex: 0 0 70px;
  text-align: right;
  font-size: var(--text-body-sm-size);
  font-weight: 600;
  color: var(--color-on-surface);
}

.dep-exposure-badge {
  flex: 0 0 90px;
  text-align: right;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.dep-exposure-badge--high     { color: var(--color-primary); }
.dep-exposure-badge--moderate { color: var(--color-secondary); }
.dep-exposure-badge--low      { color: var(--color-outline); }

.dep-empty {
  color: var(--color-on-surface-variant);
  font-size: var(--text-body-sm-size);
  padding: 20px 0;
  text-align: center;
}

/* KPI card icon/subtitle for primary service */
.kpi-card__subtitle {
  font-size: var(--text-body-sm-size);
  color: var(--color-on-surface-variant);
  margin-top: 2px;
}
```

- [ ] **Step 3.2 — Commit**

```
git add dashboard/static/dashboard/css/style.css
git commit -m "feat(dependencies): add CSS for dependencies page"
```

---

## Task 4 — Template

**Files:**
- Create: `dashboard/templates/dashboard/dependencies.html`

- [ ] **Step 4.1 — Create the template**

Create `dashboard/templates/dashboard/dependencies.html` with this content:

```html
{% extends "base.html" %}
{% load static %}

{% block title %}Dépendances — Easybiodiv{% endblock %}

{% block nav_dependencies %}active{% endblock %}

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
<div class="dep-page">

  <!-- KPI band -->
  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-card__label label-caps">Score d'exposition global</div>
      <div class="kpi-card__value data-tabular" id="dep-global-score">—</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__label label-caps">Nœuds critiques</div>
      <div class="kpi-card__value data-tabular" id="dep-critical-nodes">—</div>
      <div class="kpi-card__subtitle">points haute dépendance</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__label label-caps">Service principal</div>
      <div class="kpi-card__value" id="dep-primary-service" style="font-size:20px;line-height:1.2">—</div>
      <div class="kpi-card__subtitle" id="dep-primary-score"></div>
    </div>
  </div>

  <!-- Main row -->
  <div class="dep-main-row">

    <!-- Supply Chain Reliance -->
    <div class="card dep-supply-chain">
      <div class="dep-section-header">
        <span class="dep-section-title">Supply Chain Reliance</span>
      </div>
      <div id="dep-supply-chain-body">
        <p class="dep-empty">Aucune donnée disponible.</p>
      </div>
    </div>

    <!-- Service Exposure -->
    <div class="card dep-service-exposure">
      <div class="dep-section-header">
        <span class="dep-section-title">Service Exposure</span>
      </div>
      <div id="dep-service-exposure-body">
        <p class="dep-empty">Aucune donnée disponible.</p>
      </div>
    </div>

  </div>

  <!-- Revenue Dependence by Economic Segment -->
  <div class="card dep-revenue-segments">
    <div class="dep-section-header">
      <span class="dep-section-title">Dépendance des revenus par segment économique</span>
    </div>
    <div id="dep-revenue-segments-body">
      <p class="dep-empty">Aucune donnée disponible.</p>
    </div>
  </div>

</div>
{% endblock %}

{% block extra_js %}
{{ companies|json_script:"companies-data" }}
{{ initial_data|json_script:"initial-data" }}
<script>var DEPENDENCIES_API_URL = "{% url 'dashboard:dependencies_data' pk=0 %}";</script>
<script src="{% static 'dashboard/js/dependencies.js' %}" defer></script>
{% endblock %}
```

- [ ] **Step 4.2 — Verify page loads (visual check)**

```
python manage.py runserver
```

Navigate to `http://127.0.0.1:8000/dependencies/` (logged in). Confirm the page renders with the 3 KPI cards and 3 empty panels. No JS errors in console yet (JS file missing).

- [ ] **Step 4.3 — Commit**

```
git add dashboard/templates/dashboard/dependencies.html
git commit -m "feat(dependencies): add HTML template"
```

---

## Task 5 — JavaScript

**Files:**
- Create: `dashboard/static/dashboard/js/dependencies.js`

- [ ] **Step 5.1 — Create `dependencies.js`**

Create `dashboard/static/dashboard/js/dependencies.js`:

```javascript
const DEP_COMPANY_KEY = 'selected-company-id';

const SERVICE_ICONS = {
  water: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 3C10 3 4 9.5 4 13a6 6 0 0012 0c0-3.5-6-10-6-10z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
  </svg>`,
  soil_quality: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 15h14M3 11h14M3 7h14" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
  </svg>`,
  carbon_sequestration: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 17V7M10 7C10 7 7 4 4 5M10 7c0 0 3-3 6-2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`,
  water_purification: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M5 5h10l-2 5H7L5 5z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
    <path d="M8 10v5M12 10v5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
  </svg>`,
  pest_control: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 3l6 3.5v7L10 17 4 13.5v-7L10 3z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
  </svg>`,
  pollination: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="10" r="2.5" stroke="currentColor" stroke-width="1.4"/>
    <path d="M10 4v2M10 14v2M4 10h2M14 10h2M5.8 5.8l1.4 1.4M12.8 12.8l1.4 1.4M5.8 14.2l1.4-1.4M12.8 7.2l1.4-1.4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
  </svg>`,
};

const REVENUE_ICON = `<svg class="dep-revenue-icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
  <rect x="3" y="5" width="14" height="12" rx="2" stroke="currentColor" stroke-width="1.4"/>
  <path d="M7 3v4M13 3v4M3 11h14" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
</svg>`;


document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  const savedId = parseInt(localStorage.getItem(DEP_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    fetch(DEPENDENCIES_API_URL.replace('/0/', '/' + savedId + '/'))
      .then(r => r.json())
      .then(data => {
        renderDependencies(data);
        initDepCombobox(companies, data);
      });
  } else {
    if (initialData) renderDependencies(initialData);
    initDepCombobox(companies, initialData);
  }
});


function initDepCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');

  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData) input.value = initialData.company_name;

  function buildList(filter) {
    const q = filter.toLowerCase();
    const matched = companies.filter(c => c.name.toLowerCase().includes(q));
    listbox.innerHTML = matched.map(c =>
      `<li role="option" data-id="${c.id}" class="company-combobox__option${c.id === selected ? ' selected' : ''}">${escHtml(c.name)}</li>`
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

  listbox.addEventListener('click', (e) => {
    const opt = e.target.closest('[role="option"]');
    if (!opt) return;
    const id = parseInt(opt.dataset.id, 10);
    selected = id;
    input.value = opt.textContent;
    closeList();
    localStorage.setItem(DEP_COMPANY_KEY, id);
    fetch(DEPENDENCIES_API_URL.replace('/0/', '/' + id + '/'))
      .then(r => r.json())
      .then(data => renderDependencies(data));
  });

  document.addEventListener('click', (e) => {
    if (!combobox.contains(e.target)) closeList();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeList();
  });
}


function renderDependencies(data) {
  renderKPIs(data);
  renderSupplyChain(data.supply_chain || []);
  renderServiceExposure(data.service_exposure || {});
  renderRevenueSegments(data.revenue_segments || []);
}


function renderKPIs(data) {
  const globalScore = document.getElementById('dep-global-score');
  if (globalScore) {
    globalScore.textContent = data.global_exposure_score != null
      ? Math.round(data.global_exposure_score * 100) + ' %'
      : '—';
  }

  const criticalNodes = document.getElementById('dep-critical-nodes');
  if (criticalNodes) {
    criticalNodes.textContent = data.critical_nodes != null ? data.critical_nodes : '—';
  }

  const primaryService = document.getElementById('dep-primary-service');
  const primaryScore   = document.getElementById('dep-primary-score');
  if (primaryService) {
    primaryService.textContent = data.primary_service ? data.primary_service.name : '—';
  }
  if (primaryScore) {
    primaryScore.textContent = data.primary_service
      ? 'Score : ' + Math.round(data.primary_service.score * 100) + ' %'
      : '';
  }
}


function renderSupplyChain(tiers) {
  const body = document.getElementById('dep-supply-chain-body');
  if (!body) return;

  if (!tiers || tiers.length === 0) {
    body.innerHTML = '<p class="dep-empty">Aucune donnée de production disponible.</p>';
    return;
  }

  body.innerHTML = tiers.map(tier => {
    const cards = tier.services.map(svc => {
      const levelClass = svc.label.toLowerCase();
      const widthPct = Math.round(svc.score * 100);
      const icon = SERVICE_ICONS[svc.key] || '';
      return `
        <div class="dep-service-card">
          <div class="dep-service-card__top">
            ${icon}
            <span class="dep-service-card__name">${escHtml(svc.name)}</span>
          </div>
          <div class="dep-reliance-bar">
            <div class="dep-reliance-bar__fill dep-reliance-bar__fill--${levelClass}"
                 style="width:${widthPct}%"></div>
          </div>
          <span class="dep-service-card__label dep-service-card__label--${levelClass}">${escHtml(svc.label)}</span>
        </div>`;
    }).join('');

    return `
      <div class="dep-tier">
        <div class="dep-tier__header">
          <span class="dep-tier__bullet"></span>
          <span class="dep-tier__label">${escHtml(tier.label)}</span>
        </div>
        <hr class="dep-tier__divider">
        <div class="dep-service-grid">${cards}</div>
      </div>`;
  }).join('');
}


function renderServiceExposure(serviceExposure) {
  const body = document.getElementById('dep-service-exposure-body');
  if (!body) return;

  const categories = serviceExposure.categories || [];
  if (categories.length === 0) {
    body.innerHTML = '<p class="dep-empty">Aucune donnée disponible.</p>';
    return;
  }

  const maxScore = Math.max(
    ...categories.flatMap(cat => cat.services.map(s => s.score)),
    0.01
  );

  const cats = categories.map(cat => {
    const catAmount = cat.services.reduce((sum, s) => sum + (s.revenue_exposure || 0), 0);
    const amountDisplay = catAmount > 0
      ? formatRevenue(catAmount, serviceExposure.currency)
      : '';

    const rows = cat.services.map(svc => {
      const widthPct = Math.round((svc.score / maxScore) * 100);
      const amountStr = svc.revenue_exposure != null
        ? formatRevenue(svc.revenue_exposure, serviceExposure.currency)
        : '';
      return `
        <div class="dep-exposure-service-row">
          <span class="dep-exposure-service-name">${escHtml(svc.name)}</span>
          <div class="dep-exposure-bar-track">
            <div class="dep-exposure-bar-fill" style="width:${widthPct}%"></div>
          </div>
          <span class="dep-exposure-amount">${escHtml(amountStr)}</span>
        </div>`;
    }).join('');

    return `
      <div class="dep-exposure-category">
        <div class="dep-exposure-cat-header">
          <span class="dep-exposure-cat-name">${escHtml(cat.name)}</span>
          ${amountDisplay ? `<span class="dep-exposure-cat-amount">${escHtml(amountDisplay)}</span>` : ''}
        </div>
        ${rows}
      </div>`;
  }).join('');

  const note = serviceExposure.total_revenue != null
    ? '<div class="dep-exposure-note">Valeurs indicatives basées sur le revenu total de l\'entreprise.</div>'
    : '';

  body.innerHTML = cats + note;
}


function renderRevenueSegments(segments) {
  const body = document.getElementById('dep-revenue-segments-body');
  if (!body) return;

  if (!segments || segments.length === 0) {
    body.innerHTML = '<p class="dep-empty">Aucune donnée de revenu par segment.</p>';
    return;
  }

  const maxRevenue = Math.max(...segments.map(s => s.revenue), 1);

  body.innerHTML = segments.map(seg => {
    const widthPct = Math.round((seg.revenue / maxRevenue) * 100);
    const levelClass = seg.exposure_label.toLowerCase();
    const revenueStr = formatRevenue(seg.revenue, null);
    return `
      <div class="dep-revenue-row">
        ${REVENUE_ICON}
        <div class="dep-revenue-meta">
          <div class="dep-revenue-subsector">${escHtml(seg.subsector)}</div>
          <div class="dep-revenue-sector">${escHtml(seg.sector)}</div>
        </div>
        <div class="dep-revenue-bar-wrap">
          <div class="dep-revenue-bar-track">
            <div class="dep-revenue-bar-fill dep-revenue-bar-fill--${levelClass}"
                 style="width:${widthPct}%"></div>
          </div>
        </div>
        <span class="dep-revenue-amount">${escHtml(revenueStr)}</span>
        <span class="dep-exposure-badge dep-exposure-badge--${levelClass}">${escHtml(seg.exposure_label)}</span>
      </div>`;
  }).join('');
}


function formatRevenue(amount, currency) {
  if (amount == null) return '—';
  const sym = currency === 'EUR' ? '€' : (currency ? currency + ' ' : '');
  const abs = Math.abs(amount);
  if (abs >= 1e9) return sym + (amount / 1e9).toFixed(1) + 'Md';
  if (abs >= 1e6) return sym + (amount / 1e6).toFixed(1) + 'M';
  if (abs >= 1e3) return sym + (amount / 1e3).toFixed(0) + 'k';
  return sym + amount.toLocaleString('fr-FR');
}
```

- [ ] **Step 5.2 — Visual verification**

Run `python manage.py runserver`, navigate to `/dependencies/` (logged in). Confirm:
- KPI cards show real values (or `—` for empty company)
- Supply chain tiers render with service cards and colored bars
- Service exposure shows category bars
- Revenue segments show horizontal bars with exposure badges

No JS console errors.

- [ ] **Step 5.3 — Commit**

```
git add dashboard/static/dashboard/js/dependencies.js
git commit -m "feat(dependencies): add JavaScript rendering"
```

---

## Task 6 — Sidebar navigation link

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 6.1 — Fix the sidebar Dépendances link**

In `templates/base.html`, find the anchor tag for "Dépendances" (currently `href="#"`):

```html
<a href="#" class="sidebar__nav-link {% block nav_dependencies %}{% endblock %}" aria-label="Dépendances">
```

Replace with:

```html
<a href="{% url 'dashboard:dependencies' %}" class="sidebar__nav-link {% block nav_dependencies %}{% endblock %}" aria-label="Dépendances">
```

- [ ] **Step 6.2 — Run full test suite**

```
python manage.py test dashboard -v 2
```

Expected: All existing tests plus new `DependenciesDataTests` and `DependenciesPageViewTests` pass.

- [ ] **Step 6.3 — Commit**

```
git add templates/base.html
git commit -m "feat(dependencies): wire sidebar navigation link"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by |
|---|---|
| SCORE_MAP conversion | Task 1, Step 1.3 |
| 6 services + CICES categories | Task 1, Step 1.3 (`SERVICES` constant) |
| KPI 1 — global exposure score | Task 1, Step 1.4 + test `test_global_exposure_score` |
| KPI 2 — critical nodes (≥0.7) | Task 1, Step 1.4 + test `test_critical_nodes_counts_h_or_vh` |
| KPI 3 — primary service | Task 1, Step 1.4 + test `test_primary_service_is_highest_avg` |
| Supply chain by scope (ordered) | Task 1, Step 1.4 (`_SCOPE_ORDER`) |
| Services ≥ 0.2 threshold, max 4 | Task 1, Step 1.4 + test `test_supply_chain_only_shows_services_above_threshold` |
| Exposure labels Critical/High/Moderate/Low | Task 1, Step 1.3 (`_exposure_label`) + tests |
| Productions via asset (union Q) | Task 1, Step 1.4 + test `test_productions_via_asset_included` |
| Latest year only | Task 1, Step 1.4 + test `test_uses_latest_year_only` |
| Service exposure with/without revenue | Task 1 + tests `test_service_exposure_*` |
| Revenue segments sorted desc, latest year per subsector | Task 1 + test `test_revenue_segments_sorted_by_revenue_desc` |
| @login_required on both views | Task 2, Step 2.3 + test `test_redirects_anonymous` |
| URL patterns | Task 2, Step 2.4 |
| CSS design (bars, cards, badges) | Task 3 |
| Template (KPIs + supply chain + exposure + segments) | Task 4 |
| JS render functions | Task 5 |
| Sidebar link | Task 6 |
| Empty company → defaults | test `test_empty_company_returns_defaults` |

No gaps found. All spec requirements have corresponding tasks.
