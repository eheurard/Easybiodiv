# Page « Risque physique » Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public "Risque physique" dashboard page showing physical-risk KPIs, a risk-sized asset map, a hazard ranking that doubles as a selector, and a per-asset risk table.

**Architecture:** Mirror the existing `transition_risk` / `dependencies` pages — a pure-Python data builder returns a JSON-serializable dict, two function views (`@require_GET`, **no login**) serve the page and the API, and a dedicated vanilla-JS file renders KPIs, a MapLibre map, the ranking/selector, and the table. Switching hazard or the 5/10-year horizon is client-side only; switching company refetches.

**Tech Stack:** Django (function views, ORM aggregation), vanilla JS, MapLibre GL (already used on the overview), CSS with the existing design tokens. Tests: `django.test.TestCase` run via `python manage.py test dashboard`.

**Spec:** `docs/superpowers/specs/2026-06-02-physical-risk-page-design.md`

**Environment note:** Commands assume the venv is active. On Windows: `venv\Scripts\activate`. Run tests with `python manage.py test dashboard`.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `dashboard/views.py` | `PHYSICAL_RISKS` constant + `_get_physical_risk_data` builder + `physical_risk` / `physical_risk_data` views | Modify |
| `dashboard/urls.py` | Two new routes | Modify |
| `dashboard/tests.py` | `PhysicalRiskDataTests`, `PhysicalRiskPageViewTests` | Modify |
| `templates/dashboard/physical_risk.html` | Page markup (KPIs, map, ranking, table) | Create |
| `templates/base.html` | Wire the "Risque physique" sidebar sublink + `nav_physical_risk` block | Modify |
| `dashboard/static/dashboard/js/physical_risk.js` | Combobox, render, map, hazard selector, horizon toggle | Create |
| `dashboard/static/dashboard/css/style.css` | `pr-*` layout/component styles | Modify (append) |

---

## Task 1: Backend data builder `_get_physical_risk_data`

**Files:**
- Modify: `dashboard/views.py`
- Test: `dashboard/tests.py`

The builder reads all of a company's assets (via `Ownership`), computes per-hazard company vulnerability (mean across policies, default `1.0`), per-asset exposition (sum of `estimated_revenue` for the asset's latest production year), and assembles KPIs, a hazard ranking, and a per-asset payload.

- [ ] **Step 1: Write the failing tests**

Add to the end of `dashboard/tests.py`:

```python
class PhysicalRiskDataTests(TestCase):

    def setUp(self):
        from .models import Ownership
        self.company = Company.objects.create(name='PhysCorp')
        self.country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private'
        )
        self.region = SubnationalRegion.objects.create(name='IDF', country=self.country)
        self.commodity = Commodity.objects.create(name='Soja')

        # Asset A1: flood=0.8 (high risk), drought=0.5, rest 0
        self.a1 = Asset.objects.create(
            name='Site A1', latitude=48.0, longitude=2.0,
            country=self.country, subnational_region=self.region,
            risk_flood=0.8, risk_drought=0.5,
        )
        # Asset A2: flood=0.2, rest 0 (not high risk)
        self.a2 = Asset.objects.create(
            name='Site A2', latitude=43.0, longitude=5.0,
            country=self.country, subnational_region=self.region,
            risk_flood=0.2,
        )
        Ownership.objects.create(Asset=self.a1, Company=self.company, ownership='100%')
        Ownership.objects.create(Asset=self.a2, Company=self.company, ownership='100%')

        # Exposition: A1 latest year 2024 = 1000 (older 2022 ignored); A2 2024 = 500
        Production.objects.create(
            asset=self.a1, commodity=self.commodity, year=2022,
            production=1.0, estimated_revenue=9999.0,
        )
        Production.objects.create(
            asset=self.a1, commodity=self.commodity, year=2024,
            production=1.0, estimated_revenue=1000.0,
        )
        Production.objects.create(
            asset=self.a2, commodity=self.commodity, year=2024,
            production=1.0, estimated_revenue=500.0,
        )

        # Policies: two levels with vulnerability_flood 1.0 and 1.5 -> mean 1.25
        pt = Policy_Type.objects.create(name='Climat')
        sub = Policy_Subcategory.objects.create(name='Adaptation', policy_type=pt)
        lvl1 = Policy_Level.objects.create(
            name='Niveau 1', subcategory=sub, vulnerability_flood=1.0
        )
        lvl2 = Policy_Level.objects.create(
            name='Niveau 2', subcategory=sub, vulnerability_flood=1.5
        )
        Company_Policy.objects.create(company=self.company, policy_level=lvl1)
        Company_Policy.objects.create(company=self.company, policy_level=lvl2)

    def test_exposition_uses_latest_year_only(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        a1 = next(a for a in data['assets'] if a['name'] == 'Site A1')
        self.assertAlmostEqual(a1['exposition'], 1000.0, places=2)

    def test_vulnerability_is_mean_across_policies(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        flood = next(h for h in data['hazards'] if h['key'] == 'flood')
        self.assertAlmostEqual(flood['vulnerability'], 1.25, places=3)

    def test_assets_high_risk_count(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        # only A1 has a hazard >= 0.7 (flood 0.8)
        self.assertEqual(data['kpis']['assets_high_risk'], 1)

    def test_annual_loss(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        # A1: flood 0.8*1000*1.25=1000 + drought 0.5*1000*1.0=500 = 1500
        # A2: flood 0.2*500*1.25=125 = 125  -> total 1625
        self.assertAlmostEqual(data['kpis']['annual_loss'], 1625.0, places=2)

    def test_avg_vulnerability(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        # 14 hazards at 1.0 + flood 1.25, over 15
        self.assertAlmostEqual(data['kpis']['avg_vulnerability'], (14 + 1.25) / 15, places=4)

    def test_ranking_sorted_flood_first(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        # flood avg_risk = (1000+125)/2 = 562.5 ; drought = (500+0)/2 = 250
        self.assertEqual(data['hazards'][0]['key'], 'flood')
        self.assertAlmostEqual(data['hazards'][0]['avg_risk'], 562.5, places=2)
        drought = next(h for h in data['hazards'] if h['key'] == 'drought')
        self.assertAlmostEqual(drought['avg_risk'], 250.0, places=2)

    def test_assets_carry_all_15_risk_keys(self):
        from .views import _get_physical_risk_data, PHYSICAL_RISKS
        data = _get_physical_risk_data(self.company)
        a1 = next(a for a in data['assets'] if a['name'] == 'Site A1')
        self.assertEqual(set(a1['risk'].keys()), {r['key'] for r in PHYSICAL_RISKS})
        self.assertEqual(len(PHYSICAL_RISKS), 15)

    def test_empty_company_defaults(self):
        from .views import _get_physical_risk_data
        empty = Company.objects.create(name='EmptyPhys')
        data = _get_physical_risk_data(empty)
        self.assertEqual(data['assets'], [])
        self.assertEqual(data['kpis']['assets_high_risk'], 0)
        self.assertEqual(data['kpis']['annual_loss'], 0)
        # no policies -> every vulnerability defaults to 1.0
        self.assertAlmostEqual(data['kpis']['avg_vulnerability'], 1.0, places=4)
        self.assertTrue(all(h['avg_risk'] == 0.0 for h in data['hazards']))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test dashboard.tests.PhysicalRiskDataTests`
Expected: FAIL — `ImportError: cannot import name '_get_physical_risk_data'` (and `PHYSICAL_RISKS`).

- [ ] **Step 3: Implement the constant and builder**

In `dashboard/views.py`, add the `PHYSICAL_RISKS` constant after the existing `_SCOPE_ORDER` block (the other module-level constants):

```python
PHYSICAL_RISKS = [
    {'key': 'water',                   'name': 'Eau',                          'group': 'Services écosystémiques'},
    {'key': 'pollination',             'name': 'Pollinisation',                'group': 'Services écosystémiques'},
    {'key': 'soil_quality',            'name': 'Qualité des sols',             'group': 'Services écosystémiques'},
    {'key': 'carbon_sequestration',    'name': 'Séquestration carbone',        'group': 'Services écosystémiques'},
    {'key': 'water_purification',      'name': "Épuration de l'eau",           'group': 'Services écosystémiques'},
    {'key': 'pest_control',            'name': 'Contrôle des ravageurs',       'group': 'Services écosystémiques'},
    {'key': 'water_stress',            'name': 'Stress hydrique',              'group': 'Aléas climatiques'},
    {'key': 'wildfire',                'name': 'Incendie',                     'group': 'Aléas climatiques'},
    {'key': 'cyclone',                 'name': 'Cyclone',                      'group': 'Aléas climatiques'},
    {'key': 'drought',                 'name': 'Sécheresse',                   'group': 'Aléas climatiques'},
    {'key': 'flood',                   'name': 'Inondation',                   'group': 'Aléas climatiques'},
    {'key': 'coastal_inundation',      'name': 'Submersion côtière',           'group': 'Aléas climatiques'},
    {'key': 'heatwave',                'name': 'Canicule',                     'group': 'Aléas climatiques'},
    {'key': 'temperature_variation',   'name': 'Variation de température',      'group': 'Aléas climatiques'},
    {'key': 'precipitation_variation', 'name': 'Variation des précipitations', 'group': 'Aléas climatiques'},
]
```

Then add the builder function (place it next to the other `_get_*` builders, e.g. after `_get_transition_risk_data`):

```python
def _get_physical_risk_data(company):
    assets = list(
        Asset.objects.filter(ownership__Company=company)
        .select_related('country')
        .distinct()
    )

    # --- Vulnerability: mean of vulnerability_<key> across the company's policies ---
    levels = [
        cp.policy_level
        for cp in Company_Policy.objects.filter(company=company).select_related('policy_level')
        if cp.policy_level_id
    ]

    def _vuln(key):
        vals = [getattr(level, f'vulnerability_{key}') for level in levels]
        return sum(vals) / len(vals) if vals else 1.0

    vulnerabilities = {r['key']: _vuln(r['key']) for r in PHYSICAL_RISKS}

    # --- Exposition: sum of estimated_revenue for each asset's latest production year ---
    asset_ids = [a.pk for a in assets]
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

    # --- Per-asset payload + KPI accumulation ---
    assets_out = []
    assets_high_risk = 0
    annual_loss = 0.0
    for a in assets:
        risk_vals = {r['key']: getattr(a, f"risk_{r['key']}") for r in PHYSICAL_RISKS}
        expo = exposition.get(a.pk, 0.0)
        if max(risk_vals.values()) >= 0.7:
            assets_high_risk += 1
        for key, hazard in risk_vals.items():
            annual_loss += hazard * expo * vulnerabilities[key]
        assets_out.append({
            'id': a.pk,
            'name': a.name,
            'latitude': a.latitude,
            'longitude': a.longitude,
            'country': a.country.name,
            'exposition': round(expo, 2),
            'risk': {k: round(v, 4) for k, v in risk_vals.items()},
        })

    # --- Hazard ranking (also drives the client-side selector) ---
    n_assets = len(assets)
    hazards = []
    for r in PHYSICAL_RISKS:
        key = r['key']
        total = sum(
            getattr(a, f"risk_{key}") * exposition.get(a.pk, 0.0) * vulnerabilities[key]
            for a in assets
        )
        hazards.append({
            'key': key,
            'name': r['name'],
            'group': r['group'],
            'vulnerability': round(vulnerabilities[key], 4),
            'avg_risk': round(total / n_assets, 2) if n_assets else 0.0,
        })
    hazards.sort(key=lambda h: -h['avg_risk'])

    avg_vulnerability = sum(vulnerabilities.values()) / len(PHYSICAL_RISKS)

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'kpis': {
            'assets_high_risk': assets_high_risk,
            'avg_vulnerability': round(avg_vulnerability, 4),
            'annual_loss': round(annual_loss, 2),
        },
        'hazards': hazards,
        'assets': assets_out,
    }
```

No new imports are required: `Asset`, `Company_Policy`, `Production`, `Max`, and `defaultdict` are already imported at the top of `views.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.PhysicalRiskDataTests`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "feat(physical-risk): data builder for physical risk page"
```

---

## Task 2: Views and URLs

**Files:**
- Modify: `dashboard/views.py`
- Modify: `dashboard/urls.py`
- Test: `dashboard/tests.py`

- [ ] **Step 1: Write the failing tests**

Add to the end of `dashboard/tests.py`:

```python
class PhysicalRiskPageViewTests(TestCase):

    def test_page_returns_200_without_login(self):
        response = self.client.get(reverse('dashboard:physical_risk'))
        self.assertEqual(response.status_code, 200)

    def test_page_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:physical_risk'))
        self.assertTemplateUsed(response, 'dashboard/physical_risk.html')

    def test_companies_in_context(self):
        Company.objects.create(name='CtxPhys')
        response = self.client.get(reverse('dashboard:physical_risk'))
        self.assertIn('companies', response.context)

    def test_initial_data_none_without_companies(self):
        response = self.client.get(reverse('dashboard:physical_risk'))
        self.assertIsNone(response.context['initial_data'])

    def test_initial_data_present_with_companies(self):
        Company.objects.create(name='HasDataPhys')
        response = self.client.get(reverse('dashboard:physical_risk'))
        self.assertIsNotNone(response.context['initial_data'])
        self.assertIn('kpis', response.context['initial_data'])

    def test_api_returns_200_without_login(self):
        company = Company.objects.create(name='ApiPhys')
        url = reverse('dashboard:physical_risk_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_api_content_type_is_json(self):
        company = Company.objects.create(name='JsonPhys')
        url = reverse('dashboard:physical_risk_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertIn('application/json', response['Content-Type'])

    def test_api_404_on_missing_company(self):
        url = reverse('dashboard:physical_risk_data', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_api_post_not_allowed(self):
        company = Company.objects.create(name='PostPhys')
        url = reverse('dashboard:physical_risk_data', kwargs={'pk': company.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 405)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test dashboard.tests.PhysicalRiskPageViewTests`
Expected: FAIL — `NoReverseMatch: 'physical_risk' is not a valid view function or pattern name`.

- [ ] **Step 3: Add the views**

In `dashboard/views.py`, add after the `dependencies_data` view (end of file). Note: **no `@login_required`** — the page is public:

```python
@require_GET
def physical_risk(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_physical_risk_data(first)
    return render(request, 'dashboard/physical_risk.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def physical_risk_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_physical_risk_data(company))
```

- [ ] **Step 4: Add the URLs**

In `dashboard/urls.py`, add inside `urlpatterns` after the dependencies routes:

```python
    path('physical-risk/', views.physical_risk, name='physical_risk'),
    path('api/company/<int:pk>/physical-risk/', views.physical_risk_data, name='physical_risk_data'),
```

- [ ] **Step 5: Create a placeholder template so the page view resolves**

The view renders `dashboard/physical_risk.html`, which Task 3 builds fully. Create a minimal version now so Task 2's tests pass:

Create `templates/dashboard/physical_risk.html`:

```html
{% extends "base.html" %}
{% block title %}Risque physique — Easybiodiv{% endblock %}
{% block content %}<div class="pr-page"></div>{% endblock %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.PhysicalRiskPageViewTests`
Expected: PASS (9 tests).

- [ ] **Step 7: Commit**

```bash
git add dashboard/views.py dashboard/urls.py dashboard/tests.py templates/dashboard/physical_risk.html
git commit -m "feat(physical-risk): page and API views + routes"
```

---

## Task 3: Full template + sidebar navigation

**Files:**
- Modify: `templates/dashboard/physical_risk.html` (replace placeholder)
- Modify: `templates/base.html`

- [ ] **Step 1: Replace the template with the full markup**

Overwrite `templates/dashboard/physical_risk.html` with:

```html
{% extends "base.html" %}
{% load static %}

{% block title %}Risque physique — Easybiodiv{% endblock %}

{% block nav_risks_open %}open{% endblock %}
{% block nav_physical_risk %}active{% endblock %}

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
<div class="pr-page">

  <!-- KPI band -->
  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="pr-high-risk">—</div>
      <div class="kpi-card__label label-caps">Actifs à risque élevé</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="pr-avg-vuln">—</div>
      <div class="kpi-card__label label-caps">Vulnérabilité moyenne</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="pr-annual-loss">—</div>
      <div class="kpi-card__label label-caps">Perte projetée</div>
      <div class="pr-horizon" role="group" aria-label="Horizon de projection">
        <button type="button" class="pr-horizon__btn active" data-years="5" aria-pressed="true">5 ans</button>
        <button type="button" class="pr-horizon__btn" data-years="10" aria-pressed="false">10 ans</button>
      </div>
    </div>
  </div>

  <!-- Map + ranking -->
  <div class="pr-mid-row">
    <div class="map-card" id="pr-map" aria-label="Carte des actifs par risque physique"></div>
    <div class="card pr-ranking-card">
      <div class="label-caps pr-ranking-card__title">Classement des risques</div>
      <div id="pr-ranking" class="pr-ranking-list">
        <p class="pr-empty">Sélectionnez une entreprise.</p>
      </div>
    </div>
  </div>

  <!-- Detail table -->
  <div class="card pr-table-card">
    <div class="pr-table-card__head">
      <span class="label-caps pr-table-card__title">Détail par actif</span>
      <span class="pr-table-card__hazard" id="pr-selected-hazard">—</span>
    </div>
    <div class="pr-table-wrap">
      <table class="pr-table">
        <thead>
          <tr>
            <th>Actif</th>
            <th>Hazard</th>
            <th>Exposition</th>
            <th>Vulnérabilité</th>
            <th>Risk</th>
          </tr>
        </thead>
        <tbody id="pr-table-body"></tbody>
      </table>
    </div>
  </div>

</div>
{% endblock %}

{% block extra_js %}
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
{{ companies|json_script:"companies-data" }}
{{ initial_data|json_script:"initial-data" }}
<script>var PHYSICAL_RISK_API_URL = "{% url 'dashboard:physical_risk_data' pk=0 %}";</script>
<script src="{% static 'dashboard/js/physical_risk.js' %}" defer></script>
{% endblock %}
```

- [ ] **Step 2: Wire the sidebar sublink in `base.html`**

In `templates/base.html`, replace the inert "Risque physique" sublink (currently around lines 70-74):

```html
                <li>
                  <a href="#" class="sidebar__nav-sublink" aria-label="Risque physique">
                    Risque physique
                  </a>
                </li>
```

with:

```html
                <li>
                  <a href="{% url 'dashboard:physical_risk' %}"
                     class="sidebar__nav-sublink {% block nav_physical_risk %}{% endblock %}"
                     aria-label="Risque physique">
                    Risque physique
                  </a>
                </li>
```

- [ ] **Step 3: Verify the project still checks and the page renders**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

Then start the server (`python manage.py runserver`) and open `http://127.0.0.1:8000/physical-risk/`. Expected: page loads with the KPI band, an empty map container, the ranking card, and the table header (the map/ranking/table stay empty until Task 4 adds the JS). The sidebar "Risque physique" link is highlighted and points to `/physical-risk/`.

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard/physical_risk.html templates/base.html
git commit -m "feat(physical-risk): page template + sidebar navigation"
```

---

## Task 4: Client-side rendering (`physical_risk.js`)

**Files:**
- Create: `dashboard/static/dashboard/js/physical_risk.js`

This file mirrors `transition_risk.js`'s combobox/fetch pattern, and adds: KPI rendering with a 5/10-year horizon toggle, a clickable hazard ranking (the selector), a MapLibre map with risk-sized circles, and a per-asset table. `escHtml` is defined globally in `main.js` (loaded before this file), so it is reused.

- [ ] **Step 1: Create the file**

Create `dashboard/static/dashboard/js/physical_risk.js`:

```javascript
const PR_COMPANY_KEY = 'selected-company-id';

const PR_STATE = {
  data: null,
  selectedKey: null,
  horizon: 5,
  map: null,
};

const PR_BAND_COLORS = {
  Low:      '#dac1ba',
  Moderate: '#feb87c',
  High:     '#af5d43',
  Critical: '#91452d',
};

function prBand(score) {
  if (score >= 0.7) return 'Critical';
  if (score >= 0.5) return 'High';
  if (score >= 0.2) return 'Moderate';
  return 'Low';
}

function prFmtEuro(v) {
  return Math.round(v).toLocaleString('fr-FR') + ' €';
}

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  PR_STATE.map = prInitMap();
  prInitHorizon();

  const savedId = parseInt(localStorage.getItem(PR_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    fetch(PHYSICAL_RISK_API_URL.replace('/0/', '/' + savedId + '/'))
      .then(r => r.json())
      .then(data => { prRender(data); prInitCombobox(companies, data); });
  } else {
    if (initialData) prRender(initialData);
    prInitCombobox(companies, initialData);
  }
});


// ── Combobox (mirrors transition_risk.js) ──────────────────────────────────
function prInitCombobox(companies, initialData) {
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
    localStorage.setItem(PR_COMPANY_KEY, id);
    fetch(PHYSICAL_RISK_API_URL.replace('/0/', '/' + id + '/'))
      .then(r => r.json())
      .then(data => prRender(data));
  });

  document.addEventListener('click', (e) => {
    if (!combobox.contains(e.target)) closeList();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeList();
  });
}


// ── Horizon toggle (5 / 10 years) ──────────────────────────────────────────
function prInitHorizon() {
  const group = document.querySelector('.pr-horizon');
  if (!group) return;
  group.addEventListener('click', (e) => {
    const btn = e.target.closest('.pr-horizon__btn');
    if (!btn) return;
    PR_STATE.horizon = parseInt(btn.dataset.years, 10);
    group.querySelectorAll('.pr-horizon__btn').forEach(b => {
      const active = b === btn;
      b.classList.toggle('active', active);
      b.setAttribute('aria-pressed', String(active));
    });
    prRenderLoss();
  });
}


// ── Top-level render ───────────────────────────────────────────────────────
function prRender(data) {
  PR_STATE.data = data;
  PR_STATE.selectedKey = data.hazards && data.hazards.length ? data.hazards[0].key : null;
  prRenderKpis(data);
  prRenderRanking(data);
  prSyncMapData();
  prRenderTable();
}

function prRenderKpis(data) {
  const highRisk = document.getElementById('pr-high-risk');
  if (highRisk) highRisk.textContent = data.kpis.assets_high_risk;
  const avgVuln = document.getElementById('pr-avg-vuln');
  if (avgVuln) avgVuln.textContent = data.kpis.avg_vulnerability.toFixed(2);
  prRenderLoss();
}

function prRenderLoss() {
  const el = document.getElementById('pr-annual-loss');
  if (!el || !PR_STATE.data) return;
  el.textContent = prFmtEuro(PR_STATE.data.kpis.annual_loss * PR_STATE.horizon);
}


// ── Ranking (doubles as hazard selector) ───────────────────────────────────
function prRenderRanking(data) {
  const container = document.getElementById('pr-ranking');
  if (!container) return;
  if (!data.hazards || data.hazards.length === 0) {
    container.innerHTML = '<p class="pr-empty">Aucune donnée disponible.</p>';
    return;
  }
  const maxRisk = Math.max(...data.hazards.map(h => h.avg_risk), 0) || 1;
  container.innerHTML = data.hazards.map(h => {
    const pct = (h.avg_risk / maxRisk) * 100;
    const sel = h.key === PR_STATE.selectedKey ? ' pr-rank-row--selected' : '';
    return `
      <button type="button" class="pr-rank-row${sel}" data-key="${h.key}" aria-pressed="${h.key === PR_STATE.selectedKey}">
        <span class="pr-rank-row__name">${escHtml(h.name)}</span>
        <span class="pr-rank-row__track"><span class="pr-rank-row__fill" style="width:${pct.toFixed(1)}%"></span></span>
        <span class="pr-rank-row__val data-tabular">${prFmtEuro(h.avg_risk)}</span>
      </button>`;
  }).join('');

  container.querySelectorAll('.pr-rank-row').forEach(row => {
    row.addEventListener('click', () => prSelectHazard(row.dataset.key));
  });
}

function prSelectHazard(key) {
  PR_STATE.selectedKey = key;
  const container = document.getElementById('pr-ranking');
  if (container) {
    container.querySelectorAll('.pr-rank-row').forEach(row => {
      const active = row.dataset.key === key;
      row.classList.toggle('pr-rank-row--selected', active);
      row.setAttribute('aria-pressed', String(active));
    });
  }
  prSyncMapData();
  prRenderTable();
}

function prCurrentHazard() {
  if (!PR_STATE.data || !PR_STATE.selectedKey) return null;
  return PR_STATE.data.hazards.find(h => h.key === PR_STATE.selectedKey) || null;
}


// ── Table (reactive to selected hazard) ────────────────────────────────────
function prRenderTable() {
  const body = document.getElementById('pr-table-body');
  const hazardLabel = document.getElementById('pr-selected-hazard');
  if (!body) return;

  const hazard = prCurrentHazard();
  if (hazardLabel) hazardLabel.textContent = hazard ? hazard.name : '—';

  const data = PR_STATE.data;
  if (!data || !hazard || data.assets.length === 0) {
    body.innerHTML = '<tr><td colspan="5" class="pr-empty">Aucun actif.</td></tr>';
    return;
  }

  const key = hazard.key;
  const vuln = hazard.vulnerability;
  const rows = data.assets.map(a => {
    const hz = a.risk[key] || 0;
    const risk = hz * a.exposition * vuln;
    return { name: a.name, hz: hz, expo: a.exposition, risk: risk };
  }).sort((x, y) => y.risk - x.risk);

  body.innerHTML = rows.map(r => `
    <tr>
      <td>${escHtml(r.name)}</td>
      <td class="data-tabular">${r.hz.toFixed(3)}</td>
      <td class="data-tabular">${prFmtEuro(r.expo)}</td>
      <td class="data-tabular">${vuln.toFixed(2)}</td>
      <td class="data-tabular pr-table__risk">${prFmtEuro(r.risk)}</td>
    </tr>`).join('');
}


// ── Map ────────────────────────────────────────────────────────────────────
function prInitMap() {
  const container = document.getElementById('pr-map');
  if (!container || typeof maplibregl === 'undefined') return null;

  const map = new maplibregl.Map({
    container: 'pr-map',
    style: 'https://tiles.openfreemap.org/styles/liberty',
    center: [0, 20],
    zoom: 1.5,
  });

  map.on('load', () => {
    map.addSource('pr-assets', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
    map.addLayer({
      id: 'pr-assets-layer',
      type: 'circle',
      source: 'pr-assets',
      paint: {
        'circle-radius': ['get', 'radius'],
        'circle-color': ['get', 'color'],
        'circle-opacity': 0.75,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff',
      },
    });

    map.on('click', 'pr-assets-layer', (e) => {
      const p = e.features[0].properties;
      new maplibregl.Popup()
        .setLngLat(e.lngLat)
        .setHTML(
          `<strong>${escHtml(p.name)}</strong><br>` +
          `${escHtml(p.hazardName)} : ${Number(p.hazard).toFixed(3)}<br>` +
          `Exposition : ${prFmtEuro(Number(p.exposition))}<br>` +
          `Risk : ${prFmtEuro(Number(p.risk))}`
        )
        .addTo(map);
    });
    map.on('mouseenter', 'pr-assets-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'pr-assets-layer', () => { map.getCanvas().style.cursor = ''; });

    if (window._prPendingGeojson) {
      map.getSource('pr-assets').setData(window._prPendingGeojson);
      window._prPendingGeojson = null;
    }
  });

  return map;
}

function prBuildGeojson() {
  const data = PR_STATE.data;
  const hazard = prCurrentHazard();
  if (!data || !hazard) return { type: 'FeatureCollection', features: [] };

  const key = hazard.key;
  const vuln = hazard.vulnerability;
  const risks = data.assets.map(a => (a.risk[key] || 0) * a.exposition * vuln);
  const maxRisk = Math.max(...risks, 0) || 1;

  const features = data.assets.map((a, i) => {
    const hz = a.risk[key] || 0;
    const risk = risks[i];
    const radius = 6 + 18 * (risk / maxRisk);
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [a.longitude, a.latitude] },
      properties: {
        name: a.name,
        hazardName: hazard.name,
        hazard: hz,
        exposition: a.exposition,
        risk: risk,
        radius: radius,
        color: PR_BAND_COLORS[prBand(hz)],
      },
    };
  });
  return { type: 'FeatureCollection', features: features };
}

function prSyncMapData() {
  const map = PR_STATE.map;
  const geojson = prBuildGeojson();
  if (!map) return;
  if (map.loaded() && map.getSource('pr-assets')) {
    map.getSource('pr-assets').setData(geojson);
  } else {
    window._prPendingGeojson = geojson;
  }
}
```

- [ ] **Step 2: Verify in the browser**

Start the server (`python manage.py runserver`) and open `http://127.0.0.1:8000/physical-risk/`. Verify:
- The 3 KPI cards show numbers; clicking **10 ans** roughly doubles the projected loss, **5 ans** halves it back.
- The ranking lists hazards with bars; the top one is pre-selected (highlighted).
- Clicking a different ranking row updates the table's hazard column, vulnerability, risk, and resizes the map circles; the table header shows the selected hazard name.
- The map shows circles sized by risk, colored by hazard band, with a popup on click.
- Switching company in the combobox refreshes everything.

(There is no JS unit-test harness in this project; verification is manual, consistent with the existing pages.)

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/dashboard/js/physical_risk.js
git commit -m "feat(physical-risk): client rendering, map, ranking selector, table"
```

---

## Task 5: Styles (`pr-*`)

**Files:**
- Modify: `dashboard/static/dashboard/css/style.css` (append)

Reuses existing `kpi-row`, `kpi-card`, `kpi-card__value`, `kpi-card__label`, `card`, `map-card`, `label-caps`, `data-tabular`. Adds only the page-specific `pr-*` rules.

- [ ] **Step 1: Append the styles**

Append to the end of `dashboard/static/dashboard/css/style.css`:

```css
/* ─── Physical risk page ─────────────────────────────────────────────────── */
.pr-empty {
  font-size: var(--text-body-sm-size);
  color: var(--color-outline);
  font-style: italic;
}

.pr-horizon {
  display: inline-flex;
  gap: 4px;
  margin-top: 10px;
}

.pr-horizon__btn {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-outline-variant);
  background: var(--color-surface-container-lowest);
  color: var(--color-on-surface-variant);
  cursor: pointer;
}

.pr-horizon__btn.active {
  background: var(--color-primary);
  color: var(--color-on-primary);
  border-color: var(--color-primary);
}

.pr-mid-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 20px;
}

.pr-mid-row .map-card {
  flex: 2;
}

.pr-ranking-card {
  flex: 1;
  max-height: 420px;
  overflow-y: auto;
}

.pr-ranking-card__title {
  margin-bottom: 12px;
  display: block;
}

.pr-rank-row {
  display: grid;
  grid-template-columns: 1fr 80px auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 8px;
  margin-bottom: 4px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: none;
  cursor: pointer;
  text-align: left;
  font-size: var(--text-body-sm-size);
  color: var(--color-on-surface);
}

.pr-rank-row:hover {
  background: var(--color-surface-container-low);
}

.pr-rank-row--selected {
  background: var(--color-surface-container);
  border-color: var(--color-primary);
}

.pr-rank-row__name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pr-rank-row__track {
  height: 6px;
  border-radius: 3px;
  background: var(--color-surface-dim);
  overflow: hidden;
}

.pr-rank-row__fill {
  display: block;
  height: 100%;
  background: var(--color-primary);
}

.pr-rank-row__val {
  font-size: 11px;
  color: var(--color-on-surface-variant);
  white-space: nowrap;
}

.pr-table-card__head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 12px;
}

.pr-table-card__hazard {
  font-size: var(--text-body-sm-size);
  font-weight: 700;
  color: var(--color-primary);
}

.pr-table-wrap {
  overflow-x: auto;
}

.pr-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-body-sm-size);
}

.pr-table th {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-outline-variant);
  color: var(--color-on-surface-variant);
  font-weight: 600;
}

.pr-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-surface-container-high);
  color: var(--color-on-surface);
}

.pr-table th:not(:first-child),
.pr-table td:not(:first-child) {
  text-align: right;
}

.pr-table__risk {
  font-weight: 700;
  color: var(--color-primary);
}
```

- [ ] **Step 2: Verify in the browser**

Reload `http://127.0.0.1:8000/physical-risk/`. Verify the layout: KPI band on top, map (≈2/3 width) beside the ranking card (≈1/3), the detail table below. The horizon toggle, selected ranking row, and risk column are styled with the brand palette. Confirm there is no horizontal overflow on a normal-width window.

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/dashboard/css/style.css
git commit -m "feat(physical-risk): page styles"
```

---

## Task 6: Full-suite verification

- [ ] **Step 1: Run the full dashboard test suite**

Run: `python manage.py test dashboard`
Expected: all tests pass (existing suite + the 17 new physical-risk tests), no errors.

- [ ] **Step 2: Run Django system check**

Run: `python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 3: Final manual smoke test**

With `python manage.py runserver`: log out (the page must work anonymously), open `/physical-risk/`, switch companies, switch hazards, toggle 5/10 years, click a map circle. Everything updates without console errors.

---

## Self-Review Notes

- **Spec coverage:** 3 KPI cards w/ 5–10y toggle (Task 3 markup + Task 4 `prRenderKpis`/`prRenderLoss`); risk-sized map (Task 4 `prInitMap`/`prBuildGeojson`); hazard ranking as average Risk per category doubling as selector (Task 1 `hazards`, Task 4 `prRenderRanking`/`prSelectHazard`); table Asset|Hazard|Exposition|Vulnérabilité|Risk (Task 4 `prRenderTable`); public access — no `@login_required` (Task 2 + test `test_page_returns_200_without_login`); all 15 `risk_*` categories (Task 1 `PHYSICAL_RISKS`); vulnerability = mean across policies (Task 1 `_vuln`); exposition = latest production year (Task 1 + test `test_exposition_uses_latest_year_only`); high-risk threshold 0.7 (Task 1 + test); empty-company / no-policy edge cases (Task 1 + test `test_empty_company_defaults`).
- **Naming consistency:** JS map source `pr-assets` and layer `pr-assets-layer` used consistently in `prInitMap`/`prSyncMapData`; `PR_STATE.selectedKey` used everywhere; `prCurrentHazard` returns the hazard object whose `vulnerability`/`name`/`key` are consumed by table, map, and header. Hazard `key` strings match the `risk_<key>` / `vulnerability_<key>` model fields used in Task 1.
- **No placeholders:** every step contains complete code or an exact command + expected output.
```
