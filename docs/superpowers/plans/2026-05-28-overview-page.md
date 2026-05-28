# Overview Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the overview dashboard page with a company combobox in the header, KPI cards, a MapLibre GL JS map, and a country-exposure panel with commodity breakdown.

**Architecture:** Django serves the index page with all companies pre-loaded as JSON, plus initial KPI/GeoJSON data for the first company. A `GET /dashboard/api/company/<pk>/` endpoint returns the same data for any company. Vanilla JS updates KPI cards, the map source, and the country list on company selection — no full page reload.

**Tech Stack:** Django 6 (FBV), SQLite, MapLibre GL JS 4 (CDN), OpenFreeMap tiles (no API key), vanilla JS, BEM CSS.

---

## File map

| File | Change |
|---|---|
| `dashboard/tests.py` | Add `CompanyDataViewTests` (7 cases) + extend `DashboardIndexViewTests` (3 cases) |
| `dashboard/views.py` | Add `_get_company_data()`, `company_data()`, update `index()` |
| `dashboard/urls.py` | Add `api/company/<int:pk>/` route |
| `templates/base.html` | Wrap header-left content in `{% block header_left %}` |
| `dashboard/templates/dashboard/index.html` | Full rewrite: combobox block, KPI row, map, country panel |
| `dashboard/static/dashboard/css/style.css` | Append: combobox, KPI row, map card, country panel styles |
| `dashboard/static/dashboard/js/main.js` | Append: `initMap`, `updateDashboard`, `fetchCompany`, `initCombobox` |

---

## Task 1: `company_data` JSON endpoint

**Files:**
- Modify: `dashboard/tests.py`
- Modify: `dashboard/views.py`
- Modify: `dashboard/urls.py`

- [ ] **Step 1.1 — Write failing tests**

Replace the contents of `dashboard/tests.py` with:

```python
import json
from django.test import TestCase
from django.urls import reverse
from .models import Asset, Commodity, Company, Country, Ownership, SubnationalRegion


def _make_world():
    """Return (company, country, region, commodity, asset) with one ownership."""
    company = Company.objects.create(name='TestCorp')
    country = Country.objects.create(
        name='France', water_ownership='Public', land_ownership='Private'
    )
    region = SubnationalRegion.objects.create(name='Île-de-France', country=country)
    commodity = Commodity.objects.create(name='Soja')
    asset = Asset.objects.create(
        name='Site Paris', latitude=48.8566, longitude=2.3522,
        country=country, subnational_region=region, commodity=commodity,
    )
    Ownership.objects.create(Asset=asset, Company=company, ownership='100%')
    return company, country, region, commodity, asset


class CompanyDataViewTests(TestCase):

    def setUp(self):
        self.company, self.country, self.region, self.commodity, self.asset = _make_world()
        self.url = reverse('dashboard:company_data', kwargs={'pk': self.company.pk})

    def test_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_content_type_is_json(self):
        response = self.client.get(self.url)
        self.assertIn('application/json', response['Content-Type'])

    def test_kpi_counts(self):
        response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertEqual(data['asset_count'], 1)
        self.assertEqual(data['country_count'], 1)
        self.assertEqual(data['commodity_count'], 1)
        self.assertEqual(data['region_count'], 1)

    def test_countries_with_commodities(self):
        response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertEqual(len(data['countries']), 1)
        c = data['countries'][0]
        self.assertEqual(c['name'], 'France')
        self.assertEqual(c['asset_count'], 1)
        self.assertEqual(c['commodities'], [{'name': 'Soja', 'count': 1}])

    def test_geojson_feature_coordinates(self):
        response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertEqual(data['geojson']['type'], 'FeatureCollection')
        feature = data['geojson']['features'][0]
        self.assertEqual(feature['geometry']['type'], 'Point')
        self.assertEqual(feature['geometry']['coordinates'], [2.3522, 48.8566])
        self.assertEqual(feature['properties']['name'], 'Site Paris')

    def test_empty_company_returns_zeros(self):
        empty = Company.objects.create(name='EmptyCorp')
        url = reverse('dashboard:company_data', kwargs={'pk': empty.pk})
        response = self.client.get(url)
        data = json.loads(response.content)
        self.assertEqual(data['asset_count'], 0)
        self.assertEqual(data['countries'], [])
        self.assertEqual(data['geojson']['features'], [])

    def test_not_found_returns_404(self):
        url = reverse('dashboard:company_data', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_post_not_allowed(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 405)


class DashboardIndexViewTests(TestCase):

    def test_index_returns_200(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)

    def test_index_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertTemplateUsed(response, 'dashboard/index.html')

    def test_companies_json_in_context(self):
        Company.objects.create(name='Zeta Corp')
        Company.objects.create(name='Alpha Corp')
        response = self.client.get(reverse('dashboard:index'))
        companies = json.loads(response.context['companies_json'])
        self.assertEqual(len(companies), 2)
        self.assertEqual(companies[0]['name'], 'Alpha Corp')  # ordered by name

    def test_initial_data_present_with_companies(self):
        _make_world()
        response = self.client.get(reverse('dashboard:index'))
        self.assertIsNotNone(response.context['initial_data'])
        data = json.loads(response.context['initial_data'])
        self.assertIn('asset_count', data)

    def test_initial_data_none_without_companies(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertIsNone(response.context['initial_data'])
```

- [ ] **Step 1.2 — Run tests to confirm they fail**

```
python manage.py test dashboard
```

Expected: several failures including `NoReverseMatch` for `company_data` and `KeyError` for `companies_json`.

- [ ] **Step 1.3 — Implement the endpoint in `dashboard/views.py`**

Replace `dashboard/views.py` with:

```python
import json
from collections import defaultdict

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import Asset, Company, Ownership


def _get_company_data(company):
    assets = list(
        Asset.objects.filter(ownership__Company=company)
        .select_related('country', 'subnational_region', 'commodity')
        .distinct()
    )

    country_names = set()
    commodity_names = set()
    region_names = set()
    country_assets = defaultdict(list)

    for asset in assets:
        country_names.add(asset.country.name)
        commodity_names.add(asset.commodity.name)
        region_names.add(asset.subnational_region.name)
        country_assets[asset.country.name].append(asset.commodity.name)

    countries = []
    for country_name, commodities in sorted(
        country_assets.items(), key=lambda x: -len(x[1])
    ):
        counts = defaultdict(int)
        for c in commodities:
            counts[c] += 1
        countries.append({
            'name': country_name,
            'asset_count': len(commodities),
            'commodities': [
                {'name': n, 'count': v}
                for n, v in sorted(counts.items(), key=lambda x: -x[1])
            ],
        })

    features = [
        {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [asset.longitude, asset.latitude],
            },
            'properties': {
                'name': asset.name,
                'country': asset.country.name,
                'commodity': asset.commodity.name,
                'region': asset.subnational_region.name,
            },
        }
        for asset in assets
    ]

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'asset_count': len(assets),
        'country_count': len(country_names),
        'commodity_count': len(commodity_names),
        'region_count': len(region_names),
        'countries': countries,
        'geojson': {'type': 'FeatureCollection', 'features': features},
    }


def index(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = json.dumps(_get_company_data(first))
    return render(request, 'dashboard/index.html', {
        'companies_json': json.dumps(companies),
        'initial_data': initial_data,
    })


@require_GET
def company_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_company_data(company))
```

- [ ] **Step 1.4 — Register the URL in `dashboard/urls.py`**

Replace `dashboard/urls.py` with:

```python
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/company/<int:pk>/', views.company_data, name='company_data'),
]
```

- [ ] **Step 1.5 — Run all tests and confirm they pass**

```
python manage.py test dashboard
```

Expected: `Ran 13 tests in X.XXXs — OK`

- [ ] **Step 1.6 — Commit**

```
git add dashboard/tests.py dashboard/views.py dashboard/urls.py
git commit -m "feat: add company_data JSON endpoint and update index view"
```

---

## Task 2: Add `{% block header_left %}` to base.html

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 2.1 — Wrap the header search div in a block**

In `templates/base.html`, find the block starting at line 116:

```html
        <div class="app-header__search">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
            <path d="M13 13l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <input type="search" class="app-header__search-input form-input" placeholder="Rechercher sites, entreprises..." aria-label="Rechercher">
        </div>
```

Replace it with:

```html
        {% block header_left %}
        <div class="app-header__search">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
            <path d="M13 13l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <input type="search" class="app-header__search-input form-input" placeholder="Rechercher sites, entreprises..." aria-label="Rechercher">
        </div>
        {% endblock header_left %}
```

- [ ] **Step 2.2 — Confirm existing tests still pass**

```
python manage.py test dashboard
```

Expected: `Ran 13 tests — OK`

- [ ] **Step 2.3 — Commit**

```
git add templates/base.html
git commit -m "feat: add header_left block to base template"
```

---

## Task 3: Overview page template

**Files:**
- Modify: `dashboard/templates/dashboard/index.html`

- [ ] **Step 3.1 — Rewrite `dashboard/templates/dashboard/index.html`**

```django
{% extends "base.html" %}
{% load static %}

{% block title %}Vue d'ensemble — Easybiodiv{% endblock %}

{% block nav_overview %}active{% endblock %}

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
<div class="overview-page">

  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-card__value" data-kpi="asset_count">—</div>
      <div class="kpi-card__label label-caps">Actifs totaux</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value" data-kpi="country_count">—</div>
      <div class="kpi-card__label label-caps">Pays</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value" data-kpi="commodity_count">—</div>
      <div class="kpi-card__label label-caps">Commodités</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value" data-kpi="region_count">—</div>
      <div class="kpi-card__label label-caps">Régions</div>
    </div>
  </div>

  <div class="overview-bottom">
    <div class="map-card" id="overview-map" aria-label="Carte des actifs"></div>
    <div class="country-panel card">
      <div class="country-panel__header label-caps">Exposition par pays</div>
      <div class="country-panel__list" id="country-list">
        <p class="country-panel__empty">Sélectionnez une entreprise pour afficher l'exposition.</p>
      </div>
    </div>
  </div>

</div>
{% endblock %}

{% block extra_js %}
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
<script>
  const COMPANIES = {{ companies_json|safe }};
  const INITIAL_DATA = {{ initial_data|default:"null"|safe }};
  const COMPANY_API_URL = "{% url 'dashboard:company_data' pk=0 %}".replace('0/', '');
</script>
{% endblock %}
```

- [ ] **Step 3.2 — Confirm tests still pass**

```
python manage.py test dashboard
```

Expected: `Ran 13 tests — OK`

- [ ] **Step 3.3 — Commit**

```
git add dashboard/templates/dashboard/index.html
git commit -m "feat: add overview page template with combobox, KPI cards, map and country panel"
```

---

## Task 4: CSS for new components

**Files:**
- Modify: `dashboard/static/dashboard/css/style.css`

- [ ] **Step 4.1 — Append styles to `dashboard/static/dashboard/css/style.css`**

Add at the end of the file:

```css
/* ─── Company Combobox ───────────────────────────────────────────────────── */
.company-combobox {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
}

.company-combobox__label {
  flex-shrink: 0;
  white-space: nowrap;
}

.company-combobox__input-wrap {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--color-surface-container-lowest);
  border: 1.5px solid var(--color-primary);
  border-radius: var(--radius-base);
  padding: 6px 10px;
  min-width: 200px;
  box-shadow: 0 0 0 3px rgba(145, 69, 45, 0.08);
  color: var(--color-outline);
  cursor: pointer;
}

.company-combobox__input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-family: var(--font-family);
  font-size: var(--text-body-sm-size);
  font-weight: 600;
  color: var(--color-on-surface);
  cursor: pointer;
  min-width: 0;
}

.company-combobox__input::placeholder {
  color: var(--color-outline);
  font-weight: 400;
}

.company-combobox__chevron {
  flex-shrink: 0;
  color: var(--color-on-surface-variant);
  transition: transform var(--sidebar-transition);
}

.company-combobox[aria-expanded="true"] .company-combobox__chevron {
  transform: rotate(180deg);
}

.company-combobox__listbox {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: var(--color-surface-container-lowest);
  border: var(--border-card);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-modal);
  list-style: none;
  max-height: 240px;
  overflow-y: auto;
  z-index: 300;
  padding: 4px 0;
}

.company-combobox__option {
  padding: 8px 14px;
  font-size: var(--text-body-sm-size);
  color: var(--color-on-surface);
  cursor: pointer;
  outline: none;
}

.company-combobox__option:hover,
.company-combobox__option:focus {
  background: var(--color-surface-container-low);
  color: var(--color-primary);
}

/* ─── KPI row ────────────────────────────────────────────────────────────── */
.kpi-row {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}

.kpi-card {
  flex: 1;
  background: var(--color-surface-container-lowest);
  border: var(--border-card);
  border-radius: var(--radius-lg);
  padding: 20px 24px;
}

.kpi-card__value {
  font-size: 32px;
  font-weight: 700;
  color: var(--color-primary);
  line-height: 1;
  margin-bottom: 6px;
  font-variant-numeric: tabular-nums;
}

/* ─── Overview bottom (map + country panel) ──────────────────────────────── */
.overview-bottom {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.map-card {
  flex: 2;
  height: 420px;
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: var(--border-card);
  background: var(--color-surface-container-low);
}

/* ─── Country panel ──────────────────────────────────────────────────────── */
.country-panel {
  flex: 1;
  max-height: 420px;
  overflow-y: auto;
}

.country-panel__header {
  margin-bottom: 12px;
}

.country-panel__empty {
  font-size: var(--text-body-sm-size);
  color: var(--color-outline);
  font-style: italic;
}

.country-item {
  border: var(--border-card);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  margin-bottom: 8px;
}

.country-item__top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.country-item__name {
  font-size: var(--text-body-sm-size);
  font-weight: 600;
  color: var(--color-on-surface);
}

.country-item__count {
  font-size: var(--text-body-sm-size);
  font-weight: 700;
  color: var(--color-primary);
}

.country-item__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.country-item__tag {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 500;
  background: var(--color-surface-container-low);
  border: var(--border-card);
  color: var(--color-on-surface-variant);
}

.country-item__tag--primary {
  background: #fff8f6;
  border-color: var(--color-inverse-primary);
  color: var(--color-primary);
}
```

- [ ] **Step 4.2 — Commit**

```
git add dashboard/static/dashboard/css/style.css
git commit -m "feat: add CSS for combobox, KPI cards, map card and country panel"
```

---

## Task 5: JavaScript — map, combobox, data update

**Files:**
- Modify: `dashboard/static/dashboard/js/main.js`

- [ ] **Step 5.1 — Append the overview JS to `dashboard/static/dashboard/js/main.js`**

Add after the closing `});` of the existing `DOMContentLoaded` block (i.e., at the very end of the file):

```javascript
// ── Overview page ───────────────────────────────────────────────────────────
if (typeof COMPANIES !== 'undefined') {
  const overviewMap = initMap();
  if (INITIAL_DATA) updateDashboard(INITIAL_DATA, overviewMap);
  initCombobox(COMPANIES, overviewMap);
}

function initMap() {
  const container = document.getElementById('overview-map');
  if (!container) return null;

  const map = new maplibregl.Map({
    container: 'overview-map',
    style: 'https://tiles.openfreemap.org/styles/liberty',
    center: [0, 20],
    zoom: 1.5,
  });

  map.on('load', () => {
    map.addSource('assets', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
    map.addLayer({
      id: 'assets-layer',
      type: 'circle',
      source: 'assets',
      paint: {
        'circle-radius': 7,
        'circle-color': '#91452d',
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff',
      },
    });

    map.on('click', 'assets-layer', (e) => {
      const p = e.features[0].properties;
      new maplibregl.Popup()
        .setLngLat(e.lngLat)
        .setHTML(
          `<strong>${p.name}</strong><br>` +
          `${p.country} — ${p.commodity}<br>` +
          `<small>${p.region}</small>`
        )
        .addTo(map);
    });
    map.on('mouseenter', 'assets-layer', () => {
      map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', 'assets-layer', () => {
      map.getCanvas().style.cursor = '';
    });

    if (window._pendingGeojson) {
      map.getSource('assets').setData(window._pendingGeojson);
      window._pendingGeojson = null;
    }
  });

  return map;
}

function updateDashboard(data, map) {
  ['asset_count', 'country_count', 'commodity_count', 'region_count'].forEach((key) => {
    const el = document.querySelector(`[data-kpi="${key}"]`);
    if (el) el.textContent = data[key];
  });

  if (map) {
    if (map.loaded()) {
      map.getSource('assets').setData(data.geojson);
    } else {
      window._pendingGeojson = data.geojson;
    }
  }

  const list = document.getElementById('country-list');
  if (!list) return;
  if (data.countries.length === 0) {
    list.innerHTML = '<p class="country-panel__empty">Aucun actif pour cette entreprise.</p>';
    return;
  }
  list.innerHTML = data.countries
    .map((c) => {
      const tags = c.commodities
        .map((cm, i) =>
          `<span class="country-item__tag${i === 0 ? ' country-item__tag--primary' : ''}">${cm.name} ×${cm.count}</span>`
        )
        .join('');
      return `
        <div class="country-item">
          <div class="country-item__top">
            <span class="country-item__name">${c.name}</span>
            <span class="country-item__count">${c.asset_count} actif${c.asset_count > 1 ? 's' : ''}</span>
          </div>
          <div class="country-item__tags">${tags}</div>
        </div>`;
    })
    .join('');
}

function fetchCompany(id, map) {
  fetch(COMPANY_API_URL + id + '/')
    .then((r) => r.json())
    .then((data) => updateDashboard(data, map));
}

function initCombobox(companies, map) {
  const input = document.getElementById('company-search');
  const listbox = document.getElementById('company-listbox');
  const combobox = document.getElementById('company-combobox');
  if (!input || !listbox || !combobox) return;

  function renderOptions(query) {
    const q = query.toLowerCase();
    const filtered = companies.filter((c) => c.name.toLowerCase().includes(q));
    listbox.innerHTML = filtered
      .map(
        (c) =>
          `<li class="company-combobox__option" role="option" data-id="${c.id}" tabindex="-1">${c.name}</li>`
      )
      .join('');
    const open = filtered.length > 0;
    listbox.hidden = !open;
    combobox.setAttribute('aria-expanded', String(open));
  }

  function selectCompany(id, name) {
    input.value = name;
    listbox.hidden = true;
    combobox.setAttribute('aria-expanded', 'false');
    fetchCompany(id, map);
  }

  input.addEventListener('input', () => renderOptions(input.value));
  input.addEventListener('focus', () => renderOptions(input.value));

  listbox.addEventListener('click', (e) => {
    const opt = e.target.closest('[data-id]');
    if (opt) selectCompany(Number(opt.dataset.id), opt.textContent.trim());
  });

  document.addEventListener('click', (e) => {
    if (!combobox.contains(e.target)) {
      listbox.hidden = true;
      combobox.setAttribute('aria-expanded', 'false');
    }
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      listbox.hidden = true;
      combobox.setAttribute('aria-expanded', 'false');
    }
    if (e.key === 'ArrowDown') {
      const first = listbox.querySelector('[data-id]');
      if (first) { e.preventDefault(); first.focus(); }
    }
  });

  listbox.addEventListener('keydown', (e) => {
    const opts = [...listbox.querySelectorAll('[data-id]')];
    const idx = opts.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' && idx < opts.length - 1) {
      e.preventDefault(); opts[idx + 1].focus();
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (idx > 0) opts[idx - 1].focus(); else input.focus();
    }
    if (e.key === 'Enter' && idx >= 0) {
      selectCompany(Number(opts[idx].dataset.id), opts[idx].textContent.trim());
    }
    if (e.key === 'Escape') { listbox.hidden = true; input.focus(); }
  });

  if (INITIAL_DATA && companies.length > 0) {
    input.value = INITIAL_DATA.company_name;
  }
}
```

- [ ] **Step 5.2 — Run all tests one final time**

```
python manage.py test dashboard
```

Expected: `Ran 13 tests — OK`

- [ ] **Step 5.3 — Commit**

```
git add dashboard/static/dashboard/js/main.js
git commit -m "feat: add overview JS — combobox, MapLibre map, KPI update, country panel"
```

---

## Task 6: Smoke test in the browser

- [ ] **Step 6.1 — Run the dev server**

```
python manage.py runserver
```

- [ ] **Step 6.2 — Create test data via the Django shell** (only needed if database is empty)

```
python manage.py shell
```

```python
from dashboard.models import *
fr = Country.objects.create(name='France', water_ownership='Public', land_ownership='Public')
br = Country.objects.create(name='Brésil', water_ownership='Private', land_ownership='Mixed')
ile = SubnationalRegion.objects.create(name='Île-de-France', country=fr)
ama = SubnationalRegion.objects.create(name='Amazonie', country=br)
soja = Commodity.objects.create(name='Soja')
boeuf = Commodity.objects.create(name='Bœuf')
a1 = Asset.objects.create(name='Site Paris', latitude=48.85, longitude=2.35, country=fr, subnational_region=ile, commodity=soja)
a2 = Asset.objects.create(name='Site Lyon', latitude=45.75, longitude=4.83, country=fr, subnational_region=ile, commodity=boeuf)
a3 = Asset.objects.create(name='Fazenda Norte', latitude=-3.1, longitude=-60.0, country=br, subnational_region=ama, commodity=soja)
corp = Company.objects.create(name='Acme Corp')
Ownership.objects.create(Asset=a1, Company=corp, ownership='100%')
Ownership.objects.create(Asset=a2, Company=corp, ownership='100%')
Ownership.objects.create(Asset=a3, Company=corp, ownership='51%')
exit()
```

- [ ] **Step 6.3 — Verify in browser**

Open `http://localhost:8000/dashboard/`.

Check:
- [ ] Company combobox appears in header where the search bar was
- [ ] KPI cards show values (3 actifs, 2 pays, 2 commodités, 2 régions)
- [ ] MapLibre map loads with 3 markers
- [ ] Clicking a marker shows a popup with name, country, commodity, region
- [ ] Country panel shows France and Brésil with commodity tags
- [ ] Typing in the combobox filters the list
- [ ] Selecting a company (if you create a second one) updates all panels without page reload
