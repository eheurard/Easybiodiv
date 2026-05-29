# Transition Risk Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Risque de transition" page (sub-item of an accordion "Analyse des risques" in the sidebar) showing per-commodity / per-asset / per-country ecosystem impact bars and a horizontal SVG Sankey diagram.

**Architecture:** New view + JSON endpoint in `dashboard/views.py`, new template, CSS additions to `style.css`, new JS module `transition_risk.js`. The sidebar in `base.html` is converted to a `<details>` accordion for "Analyse des risques".

**Tech Stack:** Django FBV, vanilla JS (SVG Bézier Sankey), CSS custom properties already defined in `style.css`.

---

## File Map

| Action  | Path |
|---------|------|
| Modify  | `dashboard/views.py` |
| Modify  | `dashboard/urls.py` |
| Modify  | `templates/base.html` |
| Modify  | `dashboard/static/dashboard/css/style.css` |
| Modify  | `dashboard/static/dashboard/js/main.js` |
| Modify  | `dashboard/tests.py` |
| Create  | `dashboard/templates/dashboard/transition_risk.html` |
| Create  | `dashboard/static/dashboard/js/transition_risk.js` |

---

## Task 1 — Tests for `transition_risk_data` JSON endpoint

**Files:**
- Modify: `dashboard/tests.py`

- [ ] **Step 1: Append the test class to `dashboard/tests.py`**

Add after the existing `DashboardIndexViewTests` class (keep all existing code untouched):

```python
class TransitionRiskDataViewTests(TestCase):

    def _setup_company(self, impact_factor=2.0, production_qty=100.0, year=2024):
        company = Company.objects.create(name='RiskCorp')
        country = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private'
        )
        region = SubnationalRegion.objects.create(name='Amazonie', country=country)
        commodity = Commodity.objects.create(
            name='Soja',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=impact_factor,
        )
        asset = Asset.objects.create(
            name='Ferme A', latitude=-5.0, longitude=-55.0,
            country=country, subnational_region=region,
        )
        Ownership.objects.create(Asset=asset, Company=company, ownership='100%')
        Production.objects.create(
            Asset=asset, commodity=commodity, year=year, production=production_qty
        )
        return company, country, commodity, asset

    def test_returns_200(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_content_type_is_json(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertIn('application/json', response['Content-Type'])

    def test_total_impact_equals_production_times_factor(self):
        company, *_ = self._setup_company(impact_factor=3.0, production_qty=50.0)
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        self.assertAlmostEqual(data['total_impact'], 150.0, places=2)

    def test_single_commodity_pct_is_one(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        self.assertEqual(len(data['commodities']), 1)
        self.assertAlmostEqual(data['commodities'][0]['pct'], 1.0, places=3)

    def test_uses_latest_year_only(self):
        company, country, commodity, asset = self._setup_company(
            impact_factor=2.0, production_qty=10.0, year=2022
        )
        # Add a newer production — this one should be used
        Production.objects.create(
            Asset=asset, commodity=commodity, year=2024, production=100.0
        )
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        # 100 * 2.0 = 200, not 10 * 2.0 = 20
        self.assertAlmostEqual(data['total_impact'], 200.0, places=2)
        self.assertEqual(data['year'], 2024)

    def test_sankey_links_commodity_to_asset(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        sources = [lk['source'] for lk in data['sankey_links']]
        self.assertTrue(any(s.startswith('commodity:') for s in sources))

    def test_sankey_links_asset_to_country(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        sources = [lk['source'] for lk in data['sankey_links']]
        self.assertTrue(any(s.startswith('asset:') for s in sources))

    def test_sankey_links_country_to_company(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        sources = [lk['source'] for lk in data['sankey_links']]
        self.assertTrue(any(s.startswith('country:') for s in sources))

    def test_empty_company_returns_zero_impact(self):
        empty = Company.objects.create(name='EmptyRisk')
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': empty.pk})
        data = json.loads(self.client.get(url).content)
        self.assertEqual(data['total_impact'], 0)
        self.assertEqual(data['commodities'], [])
        self.assertEqual(data['sankey_links'], [])

    def test_not_found_returns_404(self):
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_post_not_allowed(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 405)

    def test_two_commodities_pct_sum_to_one(self):
        company = Company.objects.create(name='MultiCorp')
        country = Country.objects.create(
            name='ArgentineT', water_ownership='Pub', land_ownership='Priv'
        )
        region = SubnationalRegion.objects.create(name='Pampa', country=country)
        asset = Asset.objects.create(
            name='Estancia', latitude=-30.0, longitude=-65.0,
            country=country, subnational_region=region,
        )
        Ownership.objects.create(Asset=asset, Company=company, ownership='100%')
        c1 = Commodity.objects.create(
            name='Maïs', impact_endpoint_ReCiPe2016_ecosystem_diversity=1.0
        )
        c2 = Commodity.objects.create(
            name='Blé', impact_endpoint_ReCiPe2016_ecosystem_diversity=3.0
        )
        Production.objects.create(Asset=asset, commodity=c1, year=2024, production=100.0)
        Production.objects.create(Asset=asset, commodity=c2, year=2024, production=100.0)

        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)

        pct_sum = sum(c['pct'] for c in data['commodities'])
        self.assertAlmostEqual(pct_sum, 1.0, places=3)
        # Blé has 3x impact → sorted first
        self.assertEqual(data['commodities'][0]['name'], 'Blé')


class TransitionRiskPageViewTests(TestCase):

    def test_returns_200(self):
        response = self.client.get(reverse('dashboard:transition_risk'))
        self.assertEqual(response.status_code, 200)

    def test_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:transition_risk'))
        self.assertTemplateUsed(response, 'dashboard/transition_risk.html')

    def test_companies_in_context(self):
        Company.objects.create(name='ZetaRisk')
        response = self.client.get(reverse('dashboard:transition_risk'))
        self.assertIn('companies', response.context)
```

- [ ] **Step 2: Run tests — expect failures (URL + view not yet created)**

```
python manage.py test dashboard.tests.TransitionRiskDataViewTests dashboard.tests.TransitionRiskPageViewTests -v 2
```

Expected: errors like `NoReverseMatch: Reverse for 'transition_risk_data' not found` — that is correct.

---

## Task 2 — Implement `_get_transition_risk_data`, `transition_risk_data`, `transition_risk` in views.py

**Files:**
- Modify: `dashboard/views.py`

- [ ] **Step 1: Add imports at top of `dashboard/views.py`**

The file currently starts with:
```python
from collections import defaultdict

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import Asset, Company, Company_Policy
```

Replace with:
```python
from collections import defaultdict

from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import Asset, Company, Company_Policy, Production
```

- [ ] **Step 2: Add `_get_transition_risk_data` function after the existing `_get_company_data` function (before `def index`)**

```python
def _get_transition_risk_data(company):
    assets = list(
        Asset.objects.filter(ownership__Company=company)
        .select_related('country')
        .distinct()
    )

    empty = {
        'company_id': company.pk,
        'company_name': company.name,
        'year': None,
        'total_impact': 0,
        'commodities': [],
        'assets': [],
        'countries': [],
        'sankey_links': [],
    }

    if not assets:
        return empty

    asset_ids = [a.pk for a in assets]

    latest_years = dict(
        Production.objects.filter(Asset_id__in=asset_ids)
        .values('Asset_id')
        .annotate(max_year=Max('year'))
        .values_list('Asset_id', 'max_year')
    )

    if not latest_years:
        return empty

    ref_year = max(latest_years.values())

    productions = list(
        Production.objects.filter(Asset_id__in=asset_ids)
        .select_related('commodity', 'Asset__country')
    )
    productions = [p for p in productions if latest_years.get(p.Asset_id) == p.year]

    commodity_impact = defaultdict(float)
    asset_impact = defaultdict(float)
    asset_meta = {}
    link_commodity_asset = defaultdict(float)

    for p in productions:
        impact = p.production * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
        commodity_impact[p.commodity.name] += impact
        asset_impact[p.Asset_id] += impact
        asset_meta[p.Asset_id] = {'name': p.Asset.name, 'country': p.Asset.country.name}
        link_commodity_asset[(p.commodity.name, p.Asset_id)] += impact

    country_impact = defaultdict(float)
    for aid, imp in asset_impact.items():
        country_impact[asset_meta[aid]['country']] += imp

    total = sum(asset_impact.values())
    if total == 0:
        return {**empty, 'year': ref_year}

    def norm(v):
        return round(v / total, 4)

    commodities = sorted(
        [{'name': k, 'impact': round(v, 4), 'pct': norm(v)} for k, v in commodity_impact.items()],
        key=lambda x: -x['pct'],
    )
    assets_list = sorted(
        [
            {
                'id': aid,
                'name': asset_meta[aid]['name'],
                'country': asset_meta[aid]['country'],
                'impact': round(imp, 4),
                'pct': norm(imp),
            }
            for aid, imp in asset_impact.items()
        ],
        key=lambda x: -x['pct'],
    )
    countries = sorted(
        [{'name': k, 'impact': round(v, 4), 'pct': norm(v)} for k, v in country_impact.items()],
        key=lambda x: -x['pct'],
    )

    sankey_links = []
    for (cname, aid), imp in link_commodity_asset.items():
        sankey_links.append({
            'source': f'commodity:{cname}',
            'target': f'asset:{aid}',
            'value': norm(imp),
        })
    for aid, imp in asset_impact.items():
        sankey_links.append({
            'source': f'asset:{aid}',
            'target': f'country:{asset_meta[aid]["country"]}',
            'value': norm(imp),
        })
    for cname, imp in country_impact.items():
        sankey_links.append({
            'source': f'country:{cname}',
            'target': f'company:{company.pk}',
            'value': norm(imp),
        })

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'year': ref_year,
        'total_impact': round(total, 4),
        'commodities': commodities,
        'assets': assets_list,
        'countries': countries,
        'sankey_links': sankey_links,
    }
```

- [ ] **Step 3: Add the two views at the bottom of `dashboard/views.py`**

```python
def transition_risk(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_transition_risk_data(first)
    return render(request, 'dashboard/transition_risk.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def transition_risk_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_transition_risk_data(company))
```

- [ ] **Step 4: Run tests — all transition risk tests should pass now except `TransitionRiskPageViewTests` (template missing)**

```
python manage.py test dashboard.tests.TransitionRiskDataViewTests -v 2
```

Expected: all green. `TransitionRiskPageViewTests` will still fail with `NoReverseMatch` — that is expected.

- [ ] **Step 5: Commit**

```bash
git add dashboard/views.py
git commit -m "feat: add _get_transition_risk_data and transition risk views"
```

---

## Task 3 — Add URL routes

**Files:**
- Modify: `dashboard/urls.py`

- [ ] **Step 1: Replace the contents of `dashboard/urls.py`**

```python
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/company/<int:pk>/', views.company_data, name='company_data'),
    path('transition-risk/', views.transition_risk, name='transition_risk'),
    path('api/company/<int:pk>/transition-risk/', views.transition_risk_data, name='transition_risk_data'),
]
```

- [ ] **Step 2: Run all tests**

```
python manage.py test dashboard -v 2
```

Expected: `TransitionRiskPageViewTests.test_returns_200` and `test_companies_in_context` fail with `TemplateDoesNotExist` — that is expected. `TransitionRiskDataViewTests` all pass.

- [ ] **Step 3: Commit**

```bash
git add dashboard/urls.py
git commit -m "feat: add transition-risk URL routes"
```

---

## Task 4 — Create template `transition_risk.html`

**Files:**
- Create: `dashboard/templates/dashboard/transition_risk.html`

- [ ] **Step 1: Create the template file**

```html
{% extends "base.html" %}
{% load static %}

{% block title %}Risque de transition — Easybiodiv{% endblock %}

{% block nav_risks %}active{% endblock %}
{% block nav_transition_risk %}active{% endblock %}

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
<div class="tr-page">

  <!-- KPI band -->
  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="tr-total-impact">—</div>
      <div class="kpi-card__label label-caps">Impact écosystème total</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="tr-year">—</div>
      <div class="kpi-card__label label-caps">Année de référence</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="tr-commodity-count">—</div>
      <div class="kpi-card__label label-caps">Commodités</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="tr-asset-count">—</div>
      <div class="kpi-card__label label-caps">Actifs</div>
    </div>
  </div>

  <!-- Bar charts row -->
  <div class="tr-bars-row">
    <div class="card tr-bars-card">
      <div class="label-caps tr-bars-card__title">Par commodité</div>
      <div id="commodity-bars" class="tr-bars-list"></div>
    </div>
    <div class="card tr-bars-card">
      <div class="label-caps tr-bars-card__title">Par actif</div>
      <div id="asset-bars" class="tr-bars-list"></div>
    </div>
    <div class="card tr-bars-card">
      <div class="label-caps tr-bars-card__title">Par pays</div>
      <div id="country-bars" class="tr-bars-list"></div>
    </div>
  </div>

  <!-- Sankey diagram -->
  <div class="card tr-sankey-card">
    <div class="label-caps tr-sankey-card__title">Décomposition de l'impact</div>
    <div class="tr-sankey-wrap">
      <svg id="sankey-svg" class="tr-sankey-svg" aria-label="Diagramme Sankey de l'impact"></svg>
    </div>
  </div>

</div>
{% endblock %}

{% block extra_js %}
{{ companies|json_script:"companies-data" }}
{{ initial_data|json_script:"initial-data" }}
<script>var TRANSITION_RISK_API_URL = "{% url 'dashboard:transition_risk_data' pk=0 %}".replace('0/', '');</script>
<script src="{% static 'dashboard/js/transition_risk.js' %}" defer></script>
{% endblock %}
```

- [ ] **Step 2: Run all tests**

```
python manage.py test dashboard -v 2
```

Expected: all tests green.

- [ ] **Step 3: Commit**

```bash
git add dashboard/templates/dashboard/transition_risk.html
git commit -m "feat: add transition risk page template"
```

---

## Task 5 — Add CSS for transition risk components

**Files:**
- Modify: `dashboard/static/dashboard/css/style.css`

- [ ] **Step 1: Append the following CSS block at the end of `style.css`**

```css
/* ═══════════════════════════════════════════════════════════════════════════
   TRANSITION RISK PAGE
   ═══════════════════════════════════════════════════════════════════════════ */

/* ─── Bar charts ─────────────────────────────────────────────────────────── */
.tr-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.tr-bars-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

@media (max-width: 900px) {
  .tr-bars-row { grid-template-columns: 1fr; }
}

.tr-bars-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tr-bars-card__title {
  margin-bottom: 4px;
}

.tr-bars-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tr-bar-row {
  display: grid;
  grid-template-columns: 110px 1fr 44px;
  align-items: center;
  gap: 8px;
}

.tr-bar-label {
  font-size: var(--text-body-sm-size);
  color: var(--color-on-surface-variant);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tr-bar-track {
  height: 8px;
  background-color: var(--color-surface-container-high);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.tr-bar-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width 0.4s ease;
  min-width: 2px;
}

.tr-bar-pct {
  font-size: var(--text-body-sm-size);
  color: var(--color-on-surface-variant);
  text-align: right;
}

.tr-empty {
  font-size: var(--text-body-sm-size);
  color: var(--color-on-surface-variant);
  font-style: italic;
}

/* ─── Sankey ─────────────────────────────────────────────────────────────── */
.tr-sankey-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tr-sankey-card__title {
  margin-bottom: 4px;
}

.tr-sankey-wrap {
  width: 100%;
  overflow-x: auto;
}

.tr-sankey-svg {
  width: 100%;
  height: auto;
  min-width: 600px;
  display: block;
}

/* ─── Sidebar accordion ──────────────────────────────────────────────────── */
.sidebar__nav-details {
  list-style: none;
}

.sidebar__nav-details > summary {
  list-style: none;
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 10px;
  border-radius: var(--radius-md);
  color: var(--color-on-surface-variant);
  font-size: var(--text-body-sm-size);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.sidebar__nav-details > summary::-webkit-details-marker { display: none; }

.sidebar__nav-details > summary:hover {
  background-color: var(--color-surface-container);
  color: var(--color-on-surface);
}

.sidebar__nav-details > summary.active,
.sidebar__nav-details[open] > summary {
  color: var(--color-on-surface);
}

.sidebar__nav-chevron {
  margin-left: auto;
  flex-shrink: 0;
  transition: transform 0.2s ease;
  color: var(--color-on-surface-variant);
}

.sidebar__nav-details[open] > summary .sidebar__nav-chevron {
  transform: rotate(90deg);
}

.sidebar__nav-sub {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 4px 0 4px 32px;
}

.sidebar__nav-sublink {
  display: block;
  padding: 7px 10px;
  border-radius: var(--radius-md);
  color: var(--color-on-surface-variant);
  text-decoration: none;
  font-size: 13px;
  font-weight: 400;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.sidebar__nav-sublink:hover {
  background-color: var(--color-surface-container);
  color: var(--color-on-surface);
}

.sidebar__nav-sublink.active {
  background-color: var(--color-primary);
  color: var(--color-on-primary);
  font-weight: 500;
}

/* Collapsed sidebar hides sub-nav labels */
.sidebar-collapsed .sidebar__nav-sub {
  display: none;
}

.sidebar-collapsed .sidebar__nav-chevron {
  display: none;
}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/static/dashboard/css/style.css
git commit -m "feat: add CSS for transition risk page and sidebar accordion"
```

---

## Task 6 — Create `transition_risk.js` (bar charts + Sankey SVG)

**Files:**
- Create: `dashboard/static/dashboard/js/transition_risk.js`

- [ ] **Step 1: Create the file**

```javascript
document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  if (initialData) renderTransitionRisk(initialData);
  initTrCombobox(companies, initialData);
});


function initTrCombobox(companies, initialData) {
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
    fetch(TRANSITION_RISK_API_URL + id + '/')
      .then(r => r.json())
      .then(data => renderTransitionRisk(data));
  });

  document.addEventListener('click', (e) => {
    if (!combobox.contains(e.target)) closeList();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeList();
  });
}


function renderTransitionRisk(data) {
  const kpiImpact = document.getElementById('tr-total-impact');
  if (kpiImpact) kpiImpact.textContent = data.total_impact
    ? data.total_impact.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
    : '—';

  const kpiYear = document.getElementById('tr-year');
  if (kpiYear) kpiYear.textContent = data.year || '—';

  const kpiCommodities = document.getElementById('tr-commodity-count');
  if (kpiCommodities) kpiCommodities.textContent = data.commodities.length;

  const kpiAssets = document.getElementById('tr-asset-count');
  if (kpiAssets) kpiAssets.textContent = data.assets.length;

  renderBars('commodity-bars', data.commodities);
  renderBars('asset-bars', data.assets);
  renderBars('country-bars', data.countries);
  renderSankey(data);
}


const BAR_COLORS = [
  '#91452d', '#af5d43', '#865220', '#feb87c',
  '#625a4e', '#7b7366', '#954830', '#dac1ba',
];

function renderBars(containerId, items) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = '<p class="tr-empty">Aucune donnée disponible.</p>';
    return;
  }

  container.innerHTML = items.slice(0, 8).map((item, i) => `
    <div class="tr-bar-row">
      <span class="tr-bar-label" title="${escHtml(item.name)}">${escHtml(item.name)}</span>
      <div class="tr-bar-track">
        <div class="tr-bar-fill" style="width:${(item.pct * 100).toFixed(1)}%;background-color:${BAR_COLORS[i % BAR_COLORS.length]}"></div>
      </div>
      <span class="tr-bar-pct data-tabular">${(item.pct * 100).toFixed(1)}&nbsp;%</span>
    </div>
  `).join('');
}


const SANKEY_COLORS = ['#91452d', '#865220', '#625a4e', '#4a7a5c'];

function renderSankey(data) {
  const svg = document.getElementById('sankey-svg');
  if (!svg) return;

  if (!data.sankey_links || data.sankey_links.length === 0) {
    svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" font-size="13" font-family="Inter,sans-serif" fill="#87736d">Aucune donnée à afficher.</text>';
    svg.setAttribute('viewBox', '0 0 600 120');
    return;
  }

  const W = 900, H = 380;
  const NODE_W = 14;
  const NODE_GAP = 10;         // px between stacked nodes
  const TOP_MARGIN = 30;       // room for column headers
  const AVAIL_H = H - TOP_MARGIN - 16;

  // Column x positions
  const COL_X = [60, 270, 500, 730];
  const COL_LABELS = ['COMMODITÉS', 'ACTIFS', 'PAYS', 'COMPANY'];

  // Build node registry
  const nodes = {};

  data.commodities.forEach(c => {
    nodes[`commodity:${c.name}`] = { label: c.name, col: 0, pct: c.pct, y: 0, h: 0 };
  });
  data.assets.forEach(a => {
    nodes[`asset:${a.id}`] = { label: a.name, col: 1, pct: a.pct, y: 0, h: 0 };
  });
  data.countries.forEach(c => {
    nodes[`country:${c.name}`] = { label: c.name, col: 2, pct: c.pct, y: 0, h: 0 };
  });
  nodes[`company:${data.company_id}`] = {
    label: data.company_name, col: 3, pct: 1.0, y: 0, h: 0
  };

  // Layout nodes per column
  const cols = [[], [], [], []];
  Object.entries(nodes).forEach(([id, n]) => { n.id = id; cols[n.col].push(n); });

  cols.forEach(colNodes => {
    colNodes.sort((a, b) => b.pct - a.pct);
    const totalPct = colNodes.reduce((s, n) => s + n.pct, 0) || 1;
    const totalGap = (colNodes.length - 1) * NODE_GAP;
    let y = TOP_MARGIN;
    colNodes.forEach(n => {
      n.h = Math.max(10, (n.pct / totalPct) * (AVAIL_H - totalGap));
      n.y = y;
      y += n.h + NODE_GAP;
    });
  });

  // Track link offsets per node side
  const srcOffset = {};
  const tgtOffset = {};

  let paths = '';
  let nodeRects = '';
  let labels = '';

  // Draw links (behind nodes)
  data.sankey_links.forEach(link => {
    const src = nodes[link.source];
    const tgt = nodes[link.target];
    if (!src || !tgt) return;

    if (srcOffset[link.source] === undefined) srcOffset[link.source] = 0;
    if (tgtOffset[link.target] === undefined) tgtOffset[link.target] = 0;

    const srcTotal = src.h;
    const tgtTotal = tgt.h;
    const ribbonH = Math.max(1.5, link.value * AVAIL_H);

    const x1 = COL_X[src.col] + NODE_W;
    const y1t = src.y + srcOffset[link.source];
    const x2 = COL_X[tgt.col];
    const y2t = tgt.y + tgtOffset[link.target];
    const mx = (x1 + x2) / 2;

    const color = SANKEY_COLORS[src.col % SANKEY_COLORS.length];

    paths += `<path d="M${x1},${y1t} C${mx},${y1t} ${mx},${y2t} ${x2},${y2t} ` +
             `L${x2},${y2t + ribbonH} C${mx},${y2t + ribbonH} ${mx},${y1t + ribbonH} ${x1},${y1t + ribbonH} Z" ` +
             `fill="${color}" fill-opacity="0.18" stroke="none"/>`;

    srcOffset[link.source] += ribbonH;
    tgtOffset[link.target] += ribbonH;
  });

  // Draw nodes and labels
  Object.values(nodes).forEach(n => {
    const x = COL_X[n.col];
    const color = SANKEY_COLORS[n.col % SANKEY_COLORS.length];
    nodeRects += `<rect x="${x}" y="${n.y}" width="${NODE_W}" height="${n.h}" rx="3" fill="${color}"/>`;

    const maxLen = 16;
    const shortLabel = n.label.length > maxLen ? n.label.slice(0, maxLen - 1) + '…' : n.label;
    if (n.col < 3) {
      const lx = x + NODE_W + 6;
      const ly = n.y + n.h / 2;
      labels += `<text x="${lx}" y="${ly}" dy="0.35em" font-size="11" font-family="Inter,sans-serif" fill="#54433e" text-anchor="start">${escHtml(shortLabel)}</text>`;
    } else {
      const lx = x - 6;
      const ly = n.y + n.h / 2;
      labels += `<text x="${lx}" y="${ly}" dy="0.35em" font-size="11" font-family="Inter,sans-serif" fill="#54433e" text-anchor="end">${escHtml(shortLabel)}</text>`;
    }
  });

  // Column headers
  let headers = '';
  COL_X.forEach((x, i) => {
    headers += `<text x="${x}" y="16" font-size="9" font-family="Inter,sans-serif" fill="#87736d" text-anchor="start" font-weight="700" letter-spacing="0.08em">${escHtml(COL_LABELS[i])}</text>`;
  });

  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.innerHTML = headers + paths + nodeRects + labels;
}
```

- [ ] **Step 2: Verify the page renders correctly in the browser**

```
python manage.py runserver
```

Open `http://127.0.0.1:8000/transition-risk/` — you should see the KPI cards, three bar charts, and the Sankey SVG placeholder (or real data if seeded).

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/dashboard/js/transition_risk.js
git commit -m "feat: add transition risk JS — bar charts and SVG Sankey"
```

---

## Task 7 — Sidebar accordion in `base.html`

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Replace the "Analyse des risques" `<li>` in `templates/base.html`**

Find and replace this exact block (lines 51–58):

```html
          <li>
            <a href="#" class="sidebar__nav-link {% block nav_risks %}{% endblock %}" aria-label="Analyse des risques">
              <svg class="sidebar__nav-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M10 3L18 17H2L10 3z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                <path d="M10 8v4M10 13.5v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              <span class="sidebar__nav-label">Analyse des risques</span>
            </a>
          </li>
```

Replace with:

```html
          <li>
            <details class="sidebar__nav-details" id="nav-risks-group" {% block nav_risks_open %}{% endblock %}>
              <summary class="sidebar__nav-link" aria-label="Analyse des risques">
                <svg class="sidebar__nav-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path d="M10 3L18 17H2L10 3z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                  <path d="M10 8v4M10 13.5v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
                <span class="sidebar__nav-label">Analyse des risques</span>
                <svg class="sidebar__nav-chevron" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                  <path d="M5 3l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </summary>
              <ul class="sidebar__nav-sub" role="list">
                <li>
                  <a href="{% url 'dashboard:transition_risk' %}"
                     class="sidebar__nav-sublink {% block nav_transition_risk %}{% endblock %}"
                     aria-label="Risque de transition">
                    Risque de transition
                  </a>
                </li>
                <li>
                  <a href="#" class="sidebar__nav-sublink" aria-label="Risque physique">
                    Risque physique
                  </a>
                </li>
              </ul>
            </details>
          </li>
```

- [ ] **Step 2: In `templates/base.html`, add a new block override definition near the top of `<nav>`**

The `{% block nav_risks_open %}` block will be output as `open` when on any risks sub-page. This is driven by `{% block nav_transition_risk %}active{% endblock %}` in the template, but we need `nav_risks_open` to emit `open`.

In `transition_risk.html`, the block `{% block nav_risks %}active{% endblock %}` is no longer used for CSS class — instead add:

```html
{% block nav_risks_open %}open{% endblock %}
```

Open `dashboard/templates/dashboard/transition_risk.html` and replace:

```html
{% block nav_risks %}active{% endblock %}
{% block nav_transition_risk %}active{% endblock %}
```

with:

```html
{% block nav_risks_open %}open{% endblock %}
{% block nav_transition_risk %}active{% endblock %}
```

- [ ] **Step 3: Add JS to close the accordion when the sidebar is collapsed** 

In `dashboard/static/dashboard/js/main.js`, find the sidebar toggle click handler:

```javascript
    toggleBtn.addEventListener('click', () => {
      const collapsed = layout.classList.toggle('sidebar-collapsed');
      localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
      toggleBtn.setAttribute('aria-expanded', String(!collapsed));
      toggleBtn.setAttribute('aria-label', collapsed ? 'Développer le menu' : 'Réduire le menu');
    });
```

Replace with:

```javascript
    toggleBtn.addEventListener('click', () => {
      const collapsed = layout.classList.toggle('sidebar-collapsed');
      localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
      toggleBtn.setAttribute('aria-expanded', String(!collapsed));
      toggleBtn.setAttribute('aria-label', collapsed ? 'Développer le menu' : 'Réduire le menu');
      if (collapsed) {
        document.querySelectorAll('.sidebar__nav-details').forEach(d => d.removeAttribute('open'));
      }
    });
```

- [ ] **Step 4: Run all tests**

```
python manage.py test dashboard -v 2
```

Expected: all tests green.

- [ ] **Step 5: Open the app in a browser and verify**

```
python manage.py runserver
```

Check:
- Sidebar shows "Analyse des risques" with a chevron
- Clicking it expands to show "Risque de transition" and "Risque physique"
- Clicking "Risque de transition" navigates to `/transition-risk/`
- Accordion stays open on the transition risk page
- Collapsing the sidebar closes the accordion

- [ ] **Step 6: Commit**

```bash
git add templates/base.html dashboard/templates/dashboard/transition_risk.html dashboard/static/dashboard/js/main.js
git commit -m "feat: convert sidebar risks entry to accordion with transition risk sub-item"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Sidebar accordion "Analyse des risques" | Task 7 |
| Sub-item "Risque de transition" | Task 7 |
| Impact par commodité (somme, dernière année) | Task 2 |
| Impact par asset | Task 2 |
| Impact par pays | Task 2 |
| Normalisation en % | Task 2 |
| Barres horizontales par commodité / asset / pays | Task 4, 5, 6 |
| Sankey SVG natif commodités→assets→pays→company | Task 6 |
| Sélecteur d'entreprise réutilisé | Task 4, 6 |
| Aucune migration requise | ✅ modèles existants |
| Compatible SQLite/PostgreSQL | ✅ ORM standard |
| Tests | Task 1 |

**Placeholder scan:** Aucun TBD ou TODO dans le plan. ✅

**Type consistency:** `_get_transition_risk_data` retourne `assets_list` avec clé `id` — le JS Sankey utilise `a.id` dans `data.assets.forEach`. ✅ `sankey_links` source/target utilisent `asset:{aid}` côté Python et `asset:${a.id}` côté JS. ✅
