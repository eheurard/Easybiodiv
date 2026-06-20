# LEAP — Onglets + page Locate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une barre d'onglets LEAP (Locate/Evaluate/Assess/Prepare) sous « Entreprise » sur la page Mesure d'empreinte, et créer la page Locate (carte MapLibre + liste des sites + filtres).

**Architecture:** Une vue / un template / un JS par page, comme le reste du dashboard. Barre d'onglets = partial Django partagé inclus en tête de contenu. Locate ajoute un endpoint JSON GeoJSON ; Evaluate/Prepare sont des stubs sans endpoint.

**Tech Stack:** Django (CBV/FBV classiques), HTML/CSS/JS vanilla, MapLibre GL JS 4 (CDN), tests via `python manage.py test dashboard`.

**Pré-requis env :** activer le venv avant de lancer les tests : `./venv/scripts/activate.ps1` (PowerShell).

---

### Task 1 : Backend — données Locate + vues + URLs

**Files:**
- Modify: `dashboard/views.py` (ajouter `_get_leap_locate_data`, `leap_locate`, `leap_locate_data`, `leap_evaluate`, `leap_prepare`)
- Modify: `dashboard/urls.py`
- Test: `dashboard/tests.py`

- [ ] **Step 1 : Écrire les tests (échec attendu)**

Ajouter à la fin de `dashboard/tests.py` (le helper `_make_world()` existe déjà en haut du fichier) :

```python
class LeapLocateDataTests(TestCase):
    def setUp(self):
        self.company, self.country, self.region, self.commodity, self.asset = _make_world()
        self.asset.near_sensitive_zone = True
        self.asset.sensitive_zone_type = Asset.SensitiveZoneType.NATURA_2000
        self.asset.sensitive_zone_name = 'Forêt de Fontainebleau'
        self.asset.sensitive_zone_area_ha = 250.0
        self.asset.risk_water = 0.6
        self.asset.risk_water_stress = 0.3
        self.asset.save()
        self.url = reverse('dashboard:leap_locate_data', kwargs={'pk': self.company.pk})

    def test_endpoint_returns_200_json(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_geojson_feature_properties(self):
        from .views import _get_leap_locate_data
        data = _get_leap_locate_data(self.company)
        feats = data['geojson']['features']
        self.assertEqual(len(feats), 1)
        props = feats[0]['properties']
        self.assertEqual(props['name'], 'Site Paris')
        self.assertTrue(props['near_sensitive_zone'])
        self.assertEqual(props['sensitive_zone_type'], 'Natura 2000')
        self.assertEqual(props['sensitive_zone_area_ha'], 250.0)
        self.assertEqual(props['risk_water'], 0.6)
        self.assertEqual(feats[0]['geometry']['coordinates'], [2.3522, 48.8566])

    def test_company_without_assets_returns_empty(self):
        empty_company = Company.objects.create(name='EmptyCorp')
        from .views import _get_leap_locate_data
        data = _get_leap_locate_data(empty_company)
        self.assertEqual(data['geojson']['features'], [])


class LeapPagesTests(TestCase):
    def setUp(self):
        self.company, *_ = _make_world()

    def test_locate_page_200(self):
        response = self.client.get(reverse('dashboard:leap_locate'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/leap_locate.html')

    def test_evaluate_page_200(self):
        response = self.client.get(reverse('dashboard:leap_evaluate'))
        self.assertEqual(response.status_code, 200)

    def test_prepare_page_200(self):
        response = self.client.get(reverse('dashboard:leap_prepare'))
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2 : Lancer les tests (échec attendu)**

Run: `python manage.py test dashboard.tests.LeapLocateDataTests dashboard.tests.LeapPagesTests`
Expected: FAIL (`Reverse for 'leap_locate_data' not found` / `_get_leap_locate_data` introuvable).

- [ ] **Step 3 : Implémenter la fonction de données**

Ajouter dans `dashboard/views.py` (après `_get_mesure_empreinte_data`, avant `_BIODIV_LOSS_FIELDS`) :

```python
def _get_leap_locate_data(company):
    assets = list(
        Asset.objects.filter(ownership__Company=company)
        .select_related('country', 'subnational_region')
        .distinct()
    )
    features = []
    for a in assets:
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [a.longitude, a.latitude]},
            'properties': {
                'name': a.name,
                'country': a.country.name,
                'region': a.subnational_region.name if a.subnational_region else '',
                'near_sensitive_zone': a.near_sensitive_zone,
                'sensitive_zone_type': (
                    a.get_sensitive_zone_type_display() if a.sensitive_zone_type else ''
                ),
                'sensitive_zone_name': a.sensitive_zone_name,
                'sensitive_zone_area_ha': round(a.sensitive_zone_area_ha, 2),
                'risk_water': round(a.risk_water, 4),
                'risk_water_stress': round(a.risk_water_stress, 4),
            },
        })
    return {
        'company_id': company.pk,
        'company_name': company.name,
        'geojson': {'type': 'FeatureCollection', 'features': features},
    }
```

- [ ] **Step 4 : Implémenter les vues**

Ajouter dans `dashboard/views.py` (après `mesure_empreinte_data`) :

```python
@login_required
@require_GET
def leap_locate(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_leap_locate_data(first)
    return render(request, 'dashboard/leap_locate.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@login_required
@require_GET
def leap_locate_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_leap_locate_data(company))


@login_required
@require_GET
def leap_evaluate(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    return render(request, 'dashboard/leap_evaluate.html', {'companies': companies})


@login_required
@require_GET
def leap_prepare(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    return render(request, 'dashboard/leap_prepare.html', {'companies': companies})
```

- [ ] **Step 5 : Déclarer les URLs**

Dans `dashboard/urls.py`, ajouter après la ligne `mesure_empreinte_data` (ligne 13) :

```python
    path('leap/locate/', views.leap_locate, name='leap_locate'),
    path('api/company/<int:pk>/leap-locate/', views.leap_locate_data, name='leap_locate_data'),
    path('leap/evaluate/', views.leap_evaluate, name='leap_evaluate'),
    path('leap/prepare/', views.leap_prepare, name='leap_prepare'),
```

Note : les templates n'existent pas encore (Tasks 3 & 5), donc les tests de pages échoueront jusqu'à leur création. Les tests de données (`LeapLocateDataTests.test_geojson_feature_properties`, `test_company_without_assets_returns_empty`) doivent passer dès maintenant.

- [ ] **Step 6 : Lancer les tests de données**

Run: `python manage.py test dashboard.tests.LeapLocateDataTests.test_geojson_feature_properties dashboard.tests.LeapLocateDataTests.test_company_without_assets_returns_empty`
Expected: PASS (2 tests).

- [ ] **Step 7 : Commit**

```bash
git add dashboard/views.py dashboard/urls.py dashboard/tests.py
git commit -m "feat(leap): backend donnees Locate + vues LEAP + urls"
```

---

### Task 2 : Barre d'onglets LEAP (partial + CSS)

**Files:**
- Create: `templates/dashboard/_leap_tabs.html`
- Modify: `dashboard/static/dashboard/css/style.css` (append)

- [ ] **Step 1 : Créer le partial**

Le chemin global `templates/` est utilisé pour `base.html` ; placer le partial sous
`templates/dashboard/_leap_tabs.html` (inclus via `"dashboard/_leap_tabs.html"`).

```django
{% comment %}Barre d'onglets LEAP. Usage : {% include "dashboard/_leap_tabs.html" with active="locate" %}{% endcomment %}
<nav class="leap-tabs" aria-label="Phases LEAP">
  <a class="leap-tab {% if active == 'locate' %}leap-tab--active{% endif %}"
     href="{% url 'dashboard:leap_locate' %}"
     {% if active == 'locate' %}aria-current="page"{% endif %}>
    <span class="leap-tab__letter">L</span>
    <span class="leap-tab__name label-caps">Locate</span>
  </a>
  <a class="leap-tab {% if active == 'evaluate' %}leap-tab--active{% endif %}"
     href="{% url 'dashboard:leap_evaluate' %}"
     {% if active == 'evaluate' %}aria-current="page"{% endif %}>
    <span class="leap-tab__letter">E</span>
    <span class="leap-tab__name label-caps">Evaluate</span>
  </a>
  <a class="leap-tab {% if active == 'assess' %}leap-tab--active{% endif %}"
     href="{% url 'dashboard:mesure_empreinte' %}"
     {% if active == 'assess' %}aria-current="page"{% endif %}>
    <span class="leap-tab__letter">A</span>
    <span class="leap-tab__name label-caps">Assess</span>
  </a>
  <a class="leap-tab {% if active == 'prepare' %}leap-tab--active{% endif %}"
     href="{% url 'dashboard:leap_prepare' %}"
     {% if active == 'prepare' %}aria-current="page"{% endif %}>
    <span class="leap-tab__letter">P</span>
    <span class="leap-tab__name label-caps">Prepare</span>
  </a>
</nav>
```

- [ ] **Step 2 : Ajouter le CSS de la barre d'onglets**

Append à `dashboard/static/dashboard/css/style.css` :

```css
/* ── LEAP tabs ────────────────────────────────────────────────────────── */
.leap-tabs {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.leap-tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 92px;
  padding: 10px 16px;
  border: 1px solid var(--color-outline-variant);
  border-radius: 12px;
  background: var(--color-surface-container-lowest);
  color: var(--color-on-surface-variant);
  text-decoration: none;
  transition: background .15s ease, border-color .15s ease, color .15s ease;
}
.leap-tab:hover {
  background: var(--color-surface-container);
  border-color: var(--color-outline);
}
.leap-tab__letter {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
}
.leap-tab__name {
  color: inherit;
}
.leap-tab--active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--color-on-primary);
}
.leap-tab--active:hover {
  background: var(--color-primary);
  border-color: var(--color-primary);
}
```

- [ ] **Step 3 : Vérifier (pas de test auto)**

Vérification visuelle reportée à la Task 5 (intégration sur Assess) et Task 3 (Locate).
Pas de test unitaire pour du CSS pur.

- [ ] **Step 4 : Commit**

```bash
git add templates/dashboard/_leap_tabs.html dashboard/static/dashboard/css/style.css
git commit -m "feat(leap): partial barre d'onglets LEAP + styles"
```

---

### Task 3 : Page Locate — template

**Files:**
- Create: `dashboard/templates/dashboard/leap_locate.html`

- [ ] **Step 1 : Créer le template**

```django
{% extends "base.html" %}
{% load static %}

{% block title %}Locate — Easybiodiv{% endblock %}

{% block nav_risks_open %}open{% endblock %}
{% block nav_mesure_empreinte %}active{% endblock %}

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
<div class="leap-page">
  {% include "dashboard/_leap_tabs.html" with active="locate" %}

  <div class="ll-mid-row">
    <div class="map-card-wrap">
      <div class="map-card" id="leap-locate-map" aria-label="Carte des sites (Locate)"></div>

      <div class="ll-filters" role="group" aria-label="Filtres des sites">
        <button type="button" class="leap-filter leap-filter--active" data-filter="all" aria-pressed="true">Tous</button>
        <button type="button" class="leap-filter" data-filter="sensitive" aria-pressed="false">Zones sensibles</button>
        <button type="button" class="leap-filter" data-filter="water" aria-pressed="false">Risque eau élevé</button>
      </div>

      <div class="map-layer-toggle" role="group" aria-label="Style de carte">
        <button class="map-layer-btn map-layer-btn--active" data-layer="classic">Classique</button>
        <button class="map-layer-btn" data-layer="grayscale">Gris</button>
        <button class="map-layer-btn" data-layer="satellite">Satellite</button>
      </div>

      <div class="map-legend" aria-label="Légende">
        <p class="map-legend__title">Risque hydrique</p>
        <ul class="map-legend__list">
          <li><span class="map-legend__dot" style="background:#dac1ba"></span>Faible</li>
          <li><span class="map-legend__dot" style="background:#feb87c"></span>Modéré</li>
          <li><span class="map-legend__dot" style="background:#af5d43"></span>Élevé</li>
          <li><span class="map-legend__dot" style="background:#91452d"></span>Critique</li>
          <li><span class="map-legend__dot map-legend__dot--ring"></span>Proche zone sensible</li>
        </ul>
      </div>
    </div>

    <div class="card ll-list-card">
      <div class="label-caps ll-list-card__title">Sites localisés</div>
      <div id="leap-locate-list" class="ll-list">
        <p class="ll-empty">Sélectionnez une entreprise.</p>
      </div>
    </div>
  </div>
</div>
{% endblock %}

{% block extra_js %}
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
{{ companies|json_script:"companies-data" }}
{{ initial_data|json_script:"initial-data" }}
<script>var LEAP_LOCATE_API_URL = "{% url 'dashboard:leap_locate_data' pk=0 %}";</script>
<script src="{% static 'dashboard/js/leap_locate.js' %}" defer></script>
{% endblock %}
```

- [ ] **Step 2 : Lancer le test de page**

Run: `python manage.py test dashboard.tests.LeapPagesTests.test_locate_page_200`
Expected: PASS.

- [ ] **Step 3 : Commit**

```bash
git add dashboard/templates/dashboard/leap_locate.html
git commit -m "feat(leap): template page Locate"
```

---

### Task 4 : Page Locate — JS + CSS spécifiques

**Files:**
- Create: `dashboard/static/dashboard/js/leap_locate.js`
- Modify: `dashboard/static/dashboard/css/style.css` (append)

- [ ] **Step 1 : Créer le JS**

`main.js` est chargé globalement avant ce script (via `base.html`) et expose
`escHtml`, `fmtNum`, `MAP_STYLES`. Créer `dashboard/static/dashboard/js/leap_locate.js` :

```javascript
const LL_COMPANY_KEY = 'selected-company-id'; // partagé entre pages risques

const LL_STATE = { data: null, map: null, filter: 'all' };

const LL_BAND_COLORS = {
  Low:      '#dac1ba',
  Moderate: '#feb87c',
  High:     '#af5d43',
  Critical: '#91452d',
};
const LL_SENSITIVE_RING = '#3d6b4f';

function llBand(score) {
  if (score >= 0.7) return 'Critical';
  if (score >= 0.5) return 'High';
  if (score >= 0.2) return 'Moderate';
  return 'Low';
}

function llPct(v) { return (Number(v) * 100).toFixed(0) + '%'; }

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl || !document.getElementById('leap-locate-map')) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  LL_STATE.map = llInitMap();
  llInitFilters();
  llInitStyleToggle();

  const savedId = parseInt(localStorage.getItem(LL_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    llFetch(savedId).then(() => llInitCombobox(companies, { company_id: savedId, company_name: (companies.find(c => c.id === savedId) || {}).name }));
  } else {
    if (initialData) llRender(initialData);
    llInitCombobox(companies, initialData);
  }
});

function llFetch(id) {
  return fetch(LEAP_LOCATE_API_URL.replace('/0/', '/' + id + '/'))
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => llRender(data))
    .catch(err => console.error('leap_locate fetch failed:', err));
}

function llInitCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');
  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData && initialData.company_name) input.value = initialData.company_name;

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
    localStorage.setItem(LL_COMPANY_KEY, id);
    llFetch(id);
  });

  document.addEventListener('click', (e) => { if (!combobox.contains(e.target)) closeList(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeList(); });
}

function llInitFilters() {
  const group = document.querySelector('.ll-filters');
  if (!group) return;
  group.addEventListener('click', (e) => {
    const btn = e.target.closest('.leap-filter');
    if (!btn) return;
    LL_STATE.filter = btn.dataset.filter;
    group.querySelectorAll('.leap-filter').forEach(b => {
      const active = b === btn;
      b.classList.toggle('leap-filter--active', active);
      b.setAttribute('aria-pressed', String(active));
    });
    llSyncMapData();
    llRenderList();
  });
}

function llInitStyleToggle() {
  document.querySelectorAll('.map-layer-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.map-layer-btn').forEach((b) => b.classList.remove('map-layer-btn--active'));
      btn.classList.add('map-layer-btn--active');
      const style = MAP_STYLES[btn.dataset.layer] || MAP_STYLES.classic;
      const map = LL_STATE.map;
      if (!map) return;
      map.setStyle(style);
      map.once('styledata', () => {
        if (map.getSource('ll-assets')) return;
        llAddSourceAndLayer(map);
        llSyncMapData();
      });
    });
  });
}

function llFilteredFeatures() {
  const all = (LL_STATE.data && LL_STATE.data.geojson) ? LL_STATE.data.geojson.features : [];
  if (LL_STATE.filter === 'sensitive') return all.filter(f => f.properties.near_sensitive_zone);
  if (LL_STATE.filter === 'water') return all.filter(f => f.properties.risk_water >= 0.5);
  return all;
}

function llStyledFeatures() {
  return llFilteredFeatures().map(f => ({
    type: 'Feature',
    geometry: f.geometry,
    properties: Object.assign({}, f.properties, {
      color: LL_BAND_COLORS[llBand(f.properties.risk_water)],
      sensitive: !!f.properties.near_sensitive_zone,
    }),
  }));
}

function llAddSourceAndLayer(map) {
  map.addSource('ll-assets', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addLayer({
    id: 'll-assets-layer',
    type: 'circle',
    source: 'll-assets',
    paint: {
      'circle-radius': 8,
      'circle-color': ['get', 'color'],
      'circle-opacity': 0.8,
      'circle-stroke-width': ['case', ['get', 'sensitive'], 3, 1.5],
      'circle-stroke-color': ['case', ['get', 'sensitive'], LL_SENSITIVE_RING, '#ffffff'],
    },
  });
  map.on('click', 'll-assets-layer', (e) => {
    const p = e.features[0].properties;
    const meta = [p.country, p.region].filter(Boolean).map(escHtml).join(' · ');
    const zone = p.sensitive_zone_type
      ? `<div class="ll-popup__zone">${escHtml(p.sensitive_zone_type)}${p.sensitive_zone_name ? ' — ' + escHtml(p.sensitive_zone_name) : ''} (${fmtNum(p.sensitive_zone_area_ha)} ha)</div>`
      : '';
    new maplibregl.Popup({ maxWidth: '280px' })
      .setLngLat(e.lngLat)
      .setHTML(
        `<div class="ll-popup"><strong>${escHtml(p.name)}</strong><div class="ll-popup__meta">${meta}</div>${zone}` +
        `<div class="ll-popup__risk">Risque eau : ${llPct(p.risk_water)} · Stress hydrique : ${llPct(p.risk_water_stress)}</div></div>`
      )
      .addTo(map);
  });
  map.on('mouseenter', 'll-assets-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'll-assets-layer', () => { map.getCanvas().style.cursor = ''; });
}

function llInitMap() {
  const container = document.getElementById('leap-locate-map');
  if (!container || typeof maplibregl === 'undefined') return null;
  const map = new maplibregl.Map({
    container: 'leap-locate-map',
    style: MAP_STYLES.classic,
    center: [0, 20],
    zoom: 1.5,
  });
  map.on('load', () => {
    llAddSourceAndLayer(map);
    if (window._llPending) { map.getSource('ll-assets').setData(window._llPending); window._llPending = null; }
  });
  return map;
}

function llSyncMapData() {
  const map = LL_STATE.map;
  const geojson = { type: 'FeatureCollection', features: llStyledFeatures() };
  if (!map) return;
  if (map.loaded() && map.getSource('ll-assets')) {
    map.getSource('ll-assets').setData(geojson);
  } else {
    window._llPending = geojson;
  }
}

function llRender(data) {
  LL_STATE.data = data;
  llSyncMapData();
  llRenderList();
}

function llRenderList() {
  const el = document.getElementById('leap-locate-list');
  if (!el) return;
  const features = llFilteredFeatures();
  if (features.length === 0) {
    el.innerHTML = '<p class="ll-empty">Aucun site pour ce filtre.</p>';
    return;
  }
  el.innerHTML = features.map(f => {
    const p = f.properties;
    const [lng, lat] = f.geometry.coordinates;
    const badge = p.sensitive_zone_type
      ? `<span class="ll-item__badge">${escHtml(p.sensitive_zone_type)}</span>`
      : (p.near_sensitive_zone ? '<span class="ll-item__badge">Zone sensible</span>' : '');
    const area = (p.sensitive_zone_area_ha > 0)
      ? `<span class="ll-item__area">${fmtNum(p.sensitive_zone_area_ha)} ha</span>` : '';
    return `
      <div class="ll-item ll-item--clickable" data-lng="${lng}" data-lat="${lat}">
        <div class="ll-item__top">
          <span class="ll-item__name">${escHtml(p.name)}</span>
          ${badge}
        </div>
        <div class="ll-item__zone">${escHtml(p.sensitive_zone_name || '')} ${area}</div>
        <div class="ll-item__bars">
          <div class="ll-bar">
            <span class="ll-bar__label">Eau</span>
            <span class="ll-bar__track"><span class="ll-bar__fill" style="width:${llPct(p.risk_water)};background:${LL_BAND_COLORS[llBand(p.risk_water)]}"></span></span>
          </div>
          <div class="ll-bar">
            <span class="ll-bar__label">Stress</span>
            <span class="ll-bar__track"><span class="ll-bar__fill" style="width:${llPct(p.risk_water_stress)};background:${LL_BAND_COLORS[llBand(p.risk_water_stress)]}"></span></span>
          </div>
        </div>
      </div>`;
  }).join('');

  el.querySelectorAll('.ll-item--clickable').forEach(item => {
    item.addEventListener('click', () => {
      const lng = parseFloat(item.dataset.lng);
      const lat = parseFloat(item.dataset.lat);
      if (LL_STATE.map && !isNaN(lng) && !isNaN(lat)) {
        LL_STATE.map.flyTo({ center: [lng, lat], zoom: 9, duration: 1200 });
      }
    });
  });
}
```

- [ ] **Step 2 : Ajouter le CSS de la page Locate**

Append à `dashboard/static/dashboard/css/style.css` :

```css
/* ── LEAP Locate page ─────────────────────────────────────────────────── */
.ll-mid-row {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 16px;
  align-items: stretch;
}
@media (max-width: 900px) {
  .ll-mid-row { grid-template-columns: 1fr; }
}
.ll-filters {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  gap: 6px;
  z-index: 2;
}
.leap-filter {
  padding: 5px 12px;
  border: 1px solid var(--color-outline-variant);
  border-radius: 999px;
  background: var(--color-surface-container-lowest);
  color: var(--color-on-surface-variant);
  font-size: 13px;
  cursor: pointer;
}
.leap-filter--active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--color-on-primary);
}
.map-legend__dot--ring {
  background: transparent;
  border: 3px solid #3d6b4f;
  box-sizing: border-box;
}
.ll-list-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ll-list-card__title { margin-bottom: 12px; }
.ll-list { overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.ll-empty { color: var(--color-on-surface-variant); font-size: 14px; }
.ll-item {
  padding: 10px 12px;
  border: 1px solid var(--color-outline-variant);
  border-radius: 10px;
  background: var(--color-surface-container-lowest);
}
.ll-item--clickable { cursor: pointer; }
.ll-item--clickable:hover { border-color: var(--color-outline); }
.ll-item__top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.ll-item__name { font-weight: 600; }
.ll-item__badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--color-secondary-container);
  color: var(--color-on-secondary-container);
  white-space: nowrap;
}
.ll-item__zone { font-size: 12px; color: var(--color-on-surface-variant); min-height: 14px; }
.ll-item__bars { margin-top: 8px; display: flex; flex-direction: column; gap: 5px; }
.ll-bar { display: flex; align-items: center; gap: 8px; }
.ll-bar__label { font-size: 11px; width: 42px; color: var(--color-on-surface-variant); }
.ll-bar__track { flex: 1; height: 6px; border-radius: 999px; background: var(--color-surface-dim); overflow: hidden; }
.ll-bar__fill { display: block; height: 100%; border-radius: 999px; }
.ll-popup__meta { font-size: 12px; color: #54433e; margin: 2px 0; }
.ll-popup__zone { font-size: 12px; margin: 4px 0; }
.ll-popup__risk { font-size: 12px; margin-top: 4px; }
```

- [ ] **Step 3 : Vérifier manuellement la page**

Run (PowerShell, venv activé) : `python manage.py runserver`
Ouvrir `http://127.0.0.1:8000/leap/locate/`, se connecter, sélectionner une entreprise.
Expected : carte avec marqueurs colorés (risque eau), halo vert sur sites zones sensibles, liste à droite, filtres et style toggle fonctionnels, clic site → zoom. Arrêter le serveur (Ctrl+C).

- [ ] **Step 4 : Commit**

```bash
git add dashboard/static/dashboard/js/leap_locate.js dashboard/static/dashboard/css/style.css
git commit -m "feat(leap): JS + styles page Locate"
```

---

### Task 5 : Onglets sur Assess + stubs Evaluate/Prepare

**Files:**
- Modify: `dashboard/templates/dashboard/mesure_empreinte.html`
- Create: `dashboard/templates/dashboard/leap_evaluate.html`
- Create: `dashboard/templates/dashboard/leap_prepare.html`
- Modify: `dashboard/static/dashboard/css/style.css` (append — styles stub)

- [ ] **Step 1 : Insérer la barre d'onglets sur Assess**

Dans `dashboard/templates/dashboard/mesure_empreinte.html`, juste après la ligne
`<div class="tr-page">` (ligne 31), insérer :

```django
  {% include "dashboard/_leap_tabs.html" with active="assess" %}
```

- [ ] **Step 2 : Créer le stub Evaluate**

`dashboard/templates/dashboard/leap_evaluate.html` :

```django
{% extends "base.html" %}
{% load static %}

{% block title %}Evaluate — Easybiodiv{% endblock %}

{% block nav_risks_open %}open{% endblock %}
{% block nav_mesure_empreinte %}active{% endblock %}

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
<div class="leap-page">
  {% include "dashboard/_leap_tabs.html" with active="evaluate" %}
  <div class="card leap-stub">
    <div class="leap-stub__letter">E</div>
    <h2 class="leap-stub__title">Phase Evaluate</h2>
    <p class="leap-stub__text">Bientôt disponible.</p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3 : Créer le stub Prepare**

`dashboard/templates/dashboard/leap_prepare.html` :

```django
{% extends "base.html" %}
{% load static %}

{% block title %}Prepare — Easybiodiv{% endblock %}

{% block nav_risks_open %}open{% endblock %}
{% block nav_mesure_empreinte %}active{% endblock %}

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
<div class="leap-page">
  {% include "dashboard/_leap_tabs.html" with active="prepare" %}
  <div class="card leap-stub">
    <div class="leap-stub__letter">P</div>
    <h2 class="leap-stub__title">Phase Prepare</h2>
    <p class="leap-stub__text">Bientôt disponible.</p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4 : CSS du stub**

Append à `dashboard/static/dashboard/css/style.css` :

```css
/* ── LEAP stub ────────────────────────────────────────────────────────── */
.leap-stub {
  text-align: center;
  padding: 56px 24px;
}
.leap-stub__letter {
  font-size: 56px;
  font-weight: 700;
  color: var(--color-outline-variant);
  line-height: 1;
}
.leap-stub__title {
  margin: 12px 0 4px;
  color: var(--color-on-surface);
}
.leap-stub__text { color: var(--color-on-surface-variant); }
```

- [ ] **Step 5 : Lancer tous les tests LEAP**

Run: `python manage.py test dashboard.tests.LeapLocateDataTests dashboard.tests.LeapPagesTests`
Expected: PASS (tous, dont `test_evaluate_page_200`, `test_prepare_page_200`, `test_locate_page_200`).

- [ ] **Step 6 : Vérifier la non-régression globale**

Run: `python manage.py test dashboard`
Expected: PASS (aucune régression sur les tests existants).

- [ ] **Step 7 : Commit**

```bash
git add dashboard/templates/dashboard/mesure_empreinte.html dashboard/templates/dashboard/leap_evaluate.html dashboard/templates/dashboard/leap_prepare.html dashboard/static/dashboard/css/style.css
git commit -m "feat(leap): onglets sur Assess + stubs Evaluate/Prepare"
```

---

## Vérification finale

- [ ] `python manage.py test dashboard` → tout vert.
- [ ] Navigation manuelle : depuis `/mesure-empreinte/` (Assess), les 4 onglets sont visibles sous « Entreprise » ; clic sur L/E/P navigue vers les pages correspondantes ; l'onglet courant est surligné ; la sélection d'entreprise persiste (localStorage `selected-company-id`) entre Assess et Locate.
- [ ] Page Locate : marqueurs colorés par risque eau, halo vert pour zones sensibles, filtres et style toggle opérationnels, popup et zoom au clic.
