# LEAP / Prepare — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire la page LEAP/Prepare : un simulateur client comparant l'impact écosystèmes actuel d'une entreprise à un état T+1 obtenu en faisant varier la production par asset et le facteur d'impact par commodité.

**Architecture:** Builder Django `_get_leap_prepare_data` renvoyant l'état de référence (lignes de production de l'année la plus récente + facteurs d'impact), exposé par une vue page + une vue API JSON. Toute la simulation (leviers, recalcul, dumbbell SVG) est en JavaScript vanilla côté client, sans librairie ni écriture en base.

**Tech Stack:** Django (CBV/FBV `@login_required` + `@require_GET`), SQLite, HTML/CSS/JS vanilla, SVG inline (pas de Chart.js). Tests : `django.test.TestCase`.

## Global Constraints

- Python 3.11+, PEP 8, lignes ≤ 100 caractères.
- Aucun framework frontend, aucune dépendance npm, pas de Chart.js — visuels en CSS + SVG inline (cf. sankey `mesure_empreinte.js`, barres `compare.js`).
- Code identique SQLite / PostgreSQL : pas de champ ni fonction Postgres-only.
- Pas de migration, pas de nouveau modèle (simulation 100 % côté client).
- Namespacing URL par app : `dashboard:<name>`.
- Helpers JS globaux disponibles via `main.js` déjà chargé par `base.html` : `escHtml`, `fmtNum`, `MAP_STYLES`.
- localStorage partagé entre pages : clé `'selected-company-id'`.
- Couleurs : vert « mieux » = `#2d6a4f`, rouge « moins bien » = `var(--color-error)` (#ba1a1a), accent = `var(--color-primary)` (#91452d).
- Impact = `impact_endpoint_ReCiPe2016_ecosystem_diversity` ; **plus bas = mieux**.
- Environnement Python : `./venv/scripts/activate.ps1` ; tests via `python manage.py test`.

---

### Task 1: Backend — builder `_get_leap_prepare_data`

**Files:**
- Modify: `dashboard/views.py` (ajouter la fonction près de `_get_leap_locate_data` / `_get_leap_evaluate_data`)
- Test: `dashboard/tests.py` (nouvelle classe `LeapPrepareDataTests`)

**Interfaces:**
- Consumes: modèles `Asset`, `Production`, `Ownership`, `Commodity` ; `django.db.models.Prefetch`, `Max` (déjà importés dans `views.py`).
- Produces: `_get_leap_prepare_data(company) -> dict` avec les clés :
  `company_id:int`, `company_name:str`, `year:int|None`,
  `commodities: list[{id:int, name:str, impact_factor:float}]`,
  `assets: list[{id:int, name:str, lines: list[{commodity_id:int, qty:float, unit:str}]}]`.

- [ ] **Step 1: Write the failing tests**

Ajouter dans `dashboard/tests.py` (à placer avant `class DetteEcologiqueDataTests`) :

```python
class LeapPrepareDataTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='prepuser', password='testpass')
        self.client.force_login(self.user)

        self.company = Company.objects.create(name='PrepCorp')
        self.country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private'
        )
        # impact_endpoint_ReCiPe2016_ecosystem_diversity = 0.5
        self.commodity = Commodity.objects.create(
            name='Soja', unit='tonnes',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
        )
        self.asset = Asset.objects.create(
            name='Site A', latitude=48.0, longitude=2.0, country=self.country,
        )
        Ownership.objects.create(Asset=self.asset, Company=self.company, ownership='100%')
        Production.objects.create(
            asset=self.asset, commodity=self.commodity, year=2024, production=100.0,
        )

    def test_payload_shape(self):
        from .views import _get_leap_prepare_data
        data = _get_leap_prepare_data(self.company)
        self.assertEqual(data['company_id'], self.company.pk)
        self.assertEqual(data['year'], 2024)
        self.assertEqual(len(data['assets']), 1)
        asset = data['assets'][0]
        self.assertEqual(asset['name'], 'Site A')
        self.assertEqual(asset['lines'], [
            {'commodity_id': self.commodity.pk, 'qty': 100.0, 'unit': 'tonnes'}
        ])

    def test_commodity_impact_factor(self):
        from .views import _get_leap_prepare_data
        data = _get_leap_prepare_data(self.company)
        self.assertEqual(len(data['commodities']), 1)
        self.assertEqual(data['commodities'][0]['id'], self.commodity.pk)
        self.assertAlmostEqual(data['commodities'][0]['impact_factor'], 0.5, places=4)

    def test_uses_latest_year_only(self):
        from .views import _get_leap_prepare_data
        Production.objects.create(
            asset=self.asset, commodity=self.commodity, year=2020, production=999.0,
        )
        data = _get_leap_prepare_data(self.company)
        self.assertEqual(data['year'], 2024)
        # une seule ligne, qty de 2024 (100) et non 2020 (999)
        self.assertEqual(len(data['assets'][0]['lines']), 1)
        self.assertAlmostEqual(data['assets'][0]['lines'][0]['qty'], 100.0, places=2)

    def test_aggregates_same_commodity_lines_in_asset(self):
        from .views import _get_leap_prepare_data
        # deux productions même asset/commodité/année -> agrégées en une ligne
        Production.objects.create(
            asset=self.asset, commodity=self.commodity, year=2024, production=50.0,
        )
        data = _get_leap_prepare_data(self.company)
        self.assertEqual(len(data['assets'][0]['lines']), 1)
        self.assertAlmostEqual(data['assets'][0]['lines'][0]['qty'], 150.0, places=2)

    def test_empty_company(self):
        from .views import _get_leap_prepare_data
        empty = Company.objects.create(name='EmptyPrep')
        data = _get_leap_prepare_data(empty)
        self.assertIsNone(data['year'])
        self.assertEqual(data['assets'], [])
        self.assertEqual(data['commodities'], [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/scripts/activate.ps1; python manage.py test dashboard.tests.LeapPrepareDataTests -v 2`
Expected: FAIL avec `ImportError: cannot import name '_get_leap_prepare_data'`.

- [ ] **Step 3: Implement the builder**

Dans `dashboard/views.py`, ajouter (après `_get_leap_evaluate_data`, avant `_BIODIV_LOSS_FIELDS`) :

```python
def _get_leap_prepare_data(company):
    assets = list(
        Asset.objects.filter(ownership__Company=company)
        .prefetch_related(
            Prefetch('production_set',
                     queryset=Production.objects.select_related('commodity'))
        )
        .distinct()
    )

    commodities = {}
    assets_out = []
    years = []
    for a in assets:
        prods = list(a.production_set.all())
        latest = max((p.year for p in prods), default=None)
        if latest is None:
            continue
        years.append(latest)

        line_qty = defaultdict(float)
        line_unit = {}
        for p in prods:
            if p.year != latest:
                continue
            c = p.commodity
            commodities.setdefault(c.pk, {
                'id': c.pk,
                'name': c.name,
                'impact_factor': c.impact_endpoint_ReCiPe2016_ecosystem_diversity,
            })
            line_qty[c.pk] += p.production
            line_unit[c.pk] = c.unit

        lines = [
            {'commodity_id': cid, 'qty': round(q, 4), 'unit': line_unit[cid]}
            for cid, q in line_qty.items()
        ]
        if lines:
            assets_out.append({'id': a.pk, 'name': a.name, 'lines': lines})

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'year': max(years) if years else None,
        'commodities': sorted(commodities.values(), key=lambda c: c['name']),
        'assets': sorted(assets_out, key=lambda a: a['name']),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/scripts/activate.ps1; python manage.py test dashboard.tests.LeapPrepareDataTests -v 2`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "feat(leap): builder _get_leap_prepare_data (etat de reference T0)"
```

---

### Task 2: Backend — vue page + API + route

**Files:**
- Modify: `dashboard/views.py` (enrichir `leap_prepare`, ajouter `leap_prepare_data`)
- Modify: `dashboard/urls.py` (route API)
- Test: `dashboard/tests.py` (étendre `LeapPrepareDataTests` avec page + API)

**Interfaces:**
- Consumes: `_get_leap_prepare_data` (Task 1) ; helpers `render`, `get_object_or_404`, `JsonResponse`, décorateurs `login_required`, `require_GET` (déjà importés).
- Produces: vue `leap_prepare_data(request, pk)` ; route nommée `dashboard:leap_prepare_data` (`api/company/<int:pk>/leap-prepare/`) ; contexte template `{'companies', 'initial_data'}` pour `leap_prepare`.

- [ ] **Step 1: Write the failing tests**

Ajouter ces méthodes à la classe `LeapPrepareDataTests` dans `dashboard/tests.py` :

```python
    def test_page_returns_200(self):
        response = self.client.get(reverse('dashboard:leap_prepare'))
        self.assertEqual(response.status_code, 200)

    def test_page_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:leap_prepare'))
        self.assertTemplateUsed(response, 'dashboard/leap_prepare.html')

    def test_page_redirects_anonymous(self):
        self.client.logout()
        response = self.client.get(reverse('dashboard:leap_prepare'))
        self.assertEqual(response.status_code, 302)

    def test_page_initial_data_present(self):
        response = self.client.get(reverse('dashboard:leap_prepare'))
        self.assertIsNotNone(response.context['initial_data'])
        self.assertIn('assets', response.context['initial_data'])

    def test_api_returns_200_json(self):
        url = reverse('dashboard:leap_prepare_data', kwargs={'pk': self.company.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/json', response['Content-Type'])

    def test_api_404_on_missing_company(self):
        url = reverse('dashboard:leap_prepare_data', kwargs={'pk': 99999})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_api_post_not_allowed(self):
        url = reverse('dashboard:leap_prepare_data', kwargs={'pk': self.company.pk})
        self.assertEqual(self.client.post(url).status_code, 405)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/scripts/activate.ps1; python manage.py test dashboard.tests.LeapPrepareDataTests -v 2`
Expected: FAIL — `NoReverseMatch` pour `dashboard:leap_prepare_data` et/ou `KeyError: 'initial_data'`.

- [ ] **Step 3: Enrichir la vue page + ajouter la vue API**

Dans `dashboard/views.py`, remplacer la vue existante :

```python
@login_required
@require_GET
def leap_prepare(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    return render(request, 'dashboard/leap_prepare.html', {'companies': companies})
```

par :

```python
@login_required
@require_GET
def leap_prepare(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_leap_prepare_data(first)
    return render(request, 'dashboard/leap_prepare.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@login_required
@require_GET
def leap_prepare_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_leap_prepare_data(company))
```

- [ ] **Step 4: Ajouter la route API**

Dans `dashboard/urls.py`, après la ligne `path('leap/prepare/', views.leap_prepare, name='leap_prepare'),` ajouter :

```python
    path('api/company/<int:pk>/leap-prepare/', views.leap_prepare_data, name='leap_prepare_data'),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./venv/scripts/activate.ps1; python manage.py test dashboard.tests.LeapPrepareDataTests -v 2`
Expected: PASS (12 tests). Note : `test_page_*` passent car le template stub `leap_prepare.html` existe déjà.

- [ ] **Step 6: Commit**

```bash
git add dashboard/views.py dashboard/urls.py dashboard/tests.py
git commit -m "feat(leap): vue page + API leap_prepare_data + route"
```

---

### Task 3: Frontend — template page + styles CSS

**Files:**
- Modify: `dashboard/templates/dashboard/leap_prepare.html` (remplace entièrement le stub)
- Modify: `dashboard/static/dashboard/css/style.css` (ajouter le bloc `lp-*` en fin de fichier)
- Test: `dashboard/tests.py` (étendre `LeapPrepareDataTests` avec des `assertContains`)

**Interfaces:**
- Consumes: contexte `companies` + `initial_data` (Task 2) ; partial `dashboard/_leap_tabs.html` ; route `dashboard:leap_prepare_data`.
- Produces: DOM consommé par le JS (Task 4) — ids : `companies-data`, `initial-data`, `company-combobox`, `company-search`, `company-listbox`, `lp-impact-current`, `lp-impact-future`, `lp-variation`, `lp-variation-pill`, `lp-prod-levers`, `lp-impact-levers`, `lp-reset`, `lp-group-by`, `lp-dumbbell`, `lp-total-current`, `lp-total-future`, `lp-total-delta` ; variable globale `LEAP_PREPARE_API_URL`.

- [ ] **Step 1: Write the failing tests**

Ajouter à la classe `LeapPrepareDataTests` dans `dashboard/tests.py` :

```python
    def test_page_contains_simulator_elements(self):
        response = self.client.get(reverse('dashboard:leap_prepare'))
        self.assertContains(response, 'id="lp-dumbbell"')
        self.assertContains(response, 'id="lp-prod-levers"')
        self.assertContains(response, 'id="lp-impact-levers"')
        self.assertContains(response, 'id="lp-group-by"')
        self.assertContains(response, 'id="lp-reset"')

    def test_page_loads_prepare_js_and_api_url(self):
        response = self.client.get(reverse('dashboard:leap_prepare'))
        self.assertContains(response, 'js/leap_prepare.js')
        self.assertContains(response, 'LEAP_PREPARE_API_URL')
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/scripts/activate.ps1; python manage.py test dashboard.tests.LeapPrepareDataTests.test_page_contains_simulator_elements dashboard.tests.LeapPrepareDataTests.test_page_loads_prepare_js_and_api_url -v 2`
Expected: FAIL (le stub ne contient pas ces ids).

- [ ] **Step 3: Remplacer le template**

Écrire `dashboard/templates/dashboard/leap_prepare.html` :

```html
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

  <!-- Bandeau comparaison -->
  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="lp-impact-current">—</div>
      <div class="kpi-card__label label-caps">Impact actuel</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="lp-impact-future">—</div>
      <div class="kpi-card__label label-caps">Impact T+1 (simulé)</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="lp-variation">—</div>
      <div class="kpi-card__label label-caps">Variation
        <span class="lp-pill" id="lp-variation-pill" hidden></span>
      </div>
    </div>
  </div>

  <!-- Leviers + dumbbell -->
  <div class="lp-mid-row">
    <aside class="card lp-levers">
      <div class="lp-levers__head">
        <span class="label-caps">Leviers</span>
        <button type="button" class="lp-reset" id="lp-reset">Réinitialiser</button>
      </div>

      <div class="lp-levers__group">
        <p class="lp-levers__title label-caps">Production par asset</p>
        <div id="lp-prod-levers" class="lp-levers__list">
          <p class="pr-empty">Sélectionnez une entreprise.</p>
        </div>
      </div>

      <div class="lp-levers__group">
        <p class="lp-levers__title label-caps">Facteur d'impact par commodité</p>
        <div id="lp-impact-levers" class="lp-levers__list">
          <p class="pr-empty">Sélectionnez une entreprise.</p>
        </div>
      </div>
    </aside>

    <div class="card lp-chart-card">
      <div class="lp-chart-card__head">
        <span class="label-caps">Comparaison actuel → T+1</span>
        <label class="lp-group-by">
          <span class="label-caps">Détail</span>
          <select id="lp-group-by" class="lp-select">
            <option value="asset">Par asset</option>
            <option value="commodity">Par commodité</option>
          </select>
        </label>
      </div>
      <svg id="lp-dumbbell" class="lp-dumbbell" role="img"
           aria-label="Comparaison de l'impact actuel et T+1"></svg>
      <div class="lp-total">
        <span class="lp-total__label label-caps">Total entreprise</span>
        <span class="lp-total__values data-tabular">
          <span id="lp-total-current">—</span>
          <span class="lp-total__arrow">→</span>
          <span id="lp-total-future">—</span>
          <span id="lp-total-delta" class="lp-total__delta"></span>
        </span>
      </div>
    </div>
  </div>
</div>
{% endblock %}

{% block extra_js %}
{{ companies|json_script:"companies-data" }}
{{ initial_data|json_script:"initial-data" }}
<script>var LEAP_PREPARE_API_URL = "{% url 'dashboard:leap_prepare_data' pk=0 %}";</script>
<script src="{% static 'dashboard/js/leap_prepare.js' %}" defer></script>
{% endblock %}
```

- [ ] **Step 4: Ajouter les styles CSS**

Ajouter à la fin de `dashboard/static/dashboard/css/style.css` :

```css
/* ── LEAP / Prepare ───────────────────────────────────────────────────────── */
.lp-mid-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 20px;
}
.lp-levers { flex: 1; min-width: 280px; max-width: 380px; }
.lp-chart-card { flex: 2; }

.lp-levers__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.lp-reset {
  border: 1px solid var(--color-outline);
  background: transparent;
  color: var(--color-on-surface-variant);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  font-family: var(--font-family);
  cursor: pointer;
}
.lp-reset:hover { background: var(--color-surface-variant); }

.lp-levers__group { margin-top: 14px; }
.lp-levers__title { color: var(--color-on-surface-variant); margin: 0 0 8px; }
.lp-levers__list { display: flex; flex-direction: column; gap: 12px; }

.lp-lever__top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}
.lp-lever__name {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lp-lever__delta { font-size: 11px; color: var(--color-on-surface-variant); white-space: nowrap; }
.lp-lever__controls { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.lp-lever__slider { flex: 1; accent-color: var(--color-primary); }
.lp-lever__input {
  width: 78px;
  border: 1px solid var(--color-outline-variant);
  border-radius: 6px;
  padding: 3px 6px;
  font-size: 12px;
  font-family: var(--font-family);
  text-align: right;
}
.lp-lever__unit { font-size: 11px; color: var(--color-outline); min-width: 44px; }

.lp-chart-card__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.lp-group-by { display: inline-flex; align-items: center; gap: 8px; }
.lp-select {
  border: 1px solid var(--color-outline);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
  font-family: var(--font-family);
  background: var(--color-surface-container-lowest);
  color: var(--color-on-surface);
  cursor: pointer;
}
.lp-dumbbell { width: 100%; display: block; }

.lp-pill {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .03em;
  border-radius: 8px;
  padding: 1px 7px;
  margin-left: 6px;
}
.lp-pill--good { background: #d3e9dd; color: #2d6a4f; }
.lp-pill--bad  { background: var(--color-error-container); color: var(--color-on-error-container); }

.lp-total {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-outline-variant);
}
.lp-total__values { display: inline-flex; align-items: baseline; gap: 8px; font-weight: 600; }
.lp-total__arrow { color: var(--color-outline); }
.lp-total__delta { font-size: 13px; font-weight: 700; }
.lp-total__delta--good { color: #2d6a4f; }
.lp-total__delta--bad  { color: var(--color-error); }

.lp-empty { font-size: var(--text-body-sm-size); color: var(--color-outline); font-style: italic; }

@media (max-width: 900px) {
  .lp-mid-row { flex-direction: column; }
  .lp-levers { max-width: none; width: 100%; }
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./venv/scripts/activate.ps1; python manage.py test dashboard.tests.LeapPrepareDataTests -v 2`
Expected: PASS (14 tests).

- [ ] **Step 6: Commit**

```bash
git add dashboard/templates/dashboard/leap_prepare.html dashboard/static/dashboard/css/style.css dashboard/tests.py
git commit -m "feat(leap): page Prepare (template + styles simulateur)"
```

---

### Task 4: Frontend — simulateur JS + dumbbell SVG

**Files:**
- Create: `dashboard/static/dashboard/js/leap_prepare.js`

**Interfaces:**
- Consumes: DOM ids de la Task 3 ; `LEAP_PREPARE_API_URL` ; helpers globaux `escHtml`, `fmtNum` (de `main.js`) ; payload de l'API (Task 1/2).
- Produces: comportement page (aucun export ; script `defer` auto-exécuté au `DOMContentLoaded`).

- [ ] **Step 1: Écrire le simulateur**

Créer `dashboard/static/dashboard/js/leap_prepare.js` :

```javascript
const LP_COMPANY_KEY = 'selected-company-id'; // partagé entre pages

const LP_STATE = {
  data: null,
  groupBy: 'asset',            // 'asset' | 'commodity'
  prodDelta: {},               // asset_id -> delta (ex. 0.10 = +10%)
  impactDelta: {},             // commodity_id -> delta
};

const LP_GOOD = '#2d6a4f';
const LP_BAD = '#ba1a1a';
const LP_GREY = '#87736d';
const LP_INK = '#1b1c19';   // = --color-on-surface (var() non résolu dans les attributs SVG)
const LP_SVG_NS = 'http://www.w3.org/2000/svg';

function lpFmt(v) {
  v = Number(v) || 0;
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toLocaleString('fr-FR', { maximumFractionDigits: 0 });
  if (abs >= 1)    return v.toLocaleString('fr-FR', { maximumFractionDigits: 2 });
  if (abs === 0)   return '0';
  return v.toLocaleString('fr-FR', { maximumFractionDigits: 4 });
}

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl || !document.getElementById('lp-dumbbell')) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  lpInitGroupBy();
  lpInitReset();

  const savedId = parseInt(localStorage.getItem(LP_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    lpFetch(savedId).then(data => lpInitCombobox(companies, data || initialData));
  } else {
    if (initialData) lpLoad(initialData);
    lpInitCombobox(companies, initialData);
  }
});

function lpFetch(id) {
  return fetch(LEAP_PREPARE_API_URL.replace('/0/', '/' + id + '/'))
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => { lpLoad(data); return data; })
    .catch(err => console.error('leap_prepare fetch failed:', err));
}

// Charge un nouveau jeu de données : remet les leviers à zéro puis rend tout.
function lpLoad(data) {
  LP_STATE.data = data;
  LP_STATE.prodDelta = {};
  LP_STATE.impactDelta = {};
  (data.assets || []).forEach(a => { LP_STATE.prodDelta[a.id] = 0; });
  (data.commodities || []).forEach(c => { LP_STATE.impactDelta[c.id] = 0; });
  lpRenderLevers();
  lpRecompute();
}

// ── Combobox entreprise (aligné sur leap_locate.js) ─────────────────────────
function lpInitCombobox(companies, initialData) {
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
    localStorage.setItem(LP_COMPANY_KEY, id);
    lpFetch(id);
  });

  document.addEventListener('click', (e) => { if (!combobox.contains(e.target)) closeList(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeList(); });
}

// ── Leviers ─────────────────────────────────────────────────────────────────
function lpInitGroupBy() {
  const sel = document.getElementById('lp-group-by');
  if (!sel) return;
  sel.addEventListener('change', () => {
    LP_STATE.groupBy = sel.value;
    lpRenderDumbbell();
  });
}

function lpInitReset() {
  const btn = document.getElementById('lp-reset');
  if (!btn) return;
  btn.addEventListener('click', () => {
    Object.keys(LP_STATE.prodDelta).forEach(k => { LP_STATE.prodDelta[k] = 0; });
    Object.keys(LP_STATE.impactDelta).forEach(k => { LP_STATE.impactDelta[k] = 0; });
    lpRenderLevers();
    lpRecompute();
  });
}

function lpCommodityMap() {
  const m = {};
  (LP_STATE.data.commodities || []).forEach(c => { m[c.id] = c; });
  return m;
}

function lpRenderLevers() {
  const data = LP_STATE.data;
  const prodBox = document.getElementById('lp-prod-levers');
  const impBox = document.getElementById('lp-impact-levers');
  if (!data || !prodBox || !impBox) return;

  // Production par asset : valeur de base = somme des qty des lignes de l'asset.
  const assets = data.assets || [];
  if (!assets.length) {
    prodBox.innerHTML = '<p class="lp-empty">Aucun asset à simuler.</p>';
  } else {
    prodBox.innerHTML = assets.map(a => {
      const base = a.lines.reduce((s, l) => s + l.qty, 0);
      const unit = (a.lines[0] && a.lines[0].unit) || '';
      return lpLeverRow('prod', a.id, a.name, base, unit, 0);
    }).join('');
  }

  const commodities = data.commodities || [];
  if (!commodities.length) {
    impBox.innerHTML = '<p class="lp-empty">Aucune commodité à simuler.</p>';
  } else {
    impBox.innerHTML = commodities.map(c =>
      lpLeverRow('impact', c.id, c.name, c.impact_factor, '', 4)
    ).join('');
  }

  lpBindLevers(prodBox, 'prod');
  lpBindLevers(impBox, 'impact');
}

// kind: 'prod' | 'impact' ; base = valeur actuelle ; digits = décimales du champ.
function lpLeverRow(kind, id, name, base, unit, digits) {
  const unitHtml = unit ? `<span class="lp-lever__unit">${escHtml(unit)}</span>` : '';
  const val = base.toFixed(digits);
  return `
    <div class="lp-lever" data-kind="${kind}" data-id="${id}" data-base="${base}">
      <div class="lp-lever__top">
        <span class="lp-lever__name">${escHtml(name)}</span>
        <span class="lp-lever__delta" data-role="delta">0 %</span>
      </div>
      <div class="lp-lever__controls">
        <input type="range" class="lp-lever__slider" min="-100" max="100" step="1" value="0"
               aria-label="Variation ${escHtml(name)}">
        <input type="number" class="lp-lever__input" step="any" min="0" value="${val}"
               data-digits="${digits}" aria-label="Valeur ${escHtml(name)}">
        ${unitHtml}
      </div>
    </div>`;
}

function lpBindLevers(box, kind) {
  const store = kind === 'prod' ? LP_STATE.prodDelta : LP_STATE.impactDelta;
  box.querySelectorAll('.lp-lever').forEach(row => {
    const id = parseInt(row.dataset.id, 10);
    const base = parseFloat(row.dataset.base);
    const slider = row.querySelector('.lp-lever__slider');
    const input = row.querySelector('.lp-lever__input');
    const deltaEl = row.querySelector('[data-role="delta"]');
    const digits = parseInt(input.dataset.digits, 10) || 0;

    function setDelta(delta) {
      store[id] = delta;
      const pct = Math.round(delta * 100);
      deltaEl.textContent = (pct > 0 ? '+' : '') + pct + ' %';
      deltaEl.style.color = pct < 0 ? LP_GOOD : (pct > 0 ? LP_BAD : '');
      lpRecompute();
    }

    slider.addEventListener('input', () => {
      const delta = parseInt(slider.value, 10) / 100;
      input.value = (base * (1 + delta)).toFixed(digits);
      setDelta(delta);
    });
    input.addEventListener('input', () => {
      const next = parseFloat(input.value);
      if (isNaN(next) || base === 0) return;
      const delta = next / base - 1;
      slider.value = Math.max(-100, Math.min(100, Math.round(delta * 100)));
      setDelta(delta);
    });
  });
}

// ── Calcul + agrégation ──────────────────────────────────────────────────────
// Renvoie [{key, name, current, future}] selon LP_STATE.groupBy, + totaux.
function lpComputeItems() {
  const data = LP_STATE.data;
  const commMap = lpCommodityMap();
  const byAsset = {};
  const byCommodity = {};
  let totalCur = 0, totalFut = 0;

  (data.assets || []).forEach(a => {
    const pd = LP_STATE.prodDelta[a.id] || 0;
    a.lines.forEach(l => {
      const comm = commMap[l.commodity_id];
      if (!comm) return;
      const id = LP_STATE.impactDelta[l.commodity_id] || 0;
      const cur = l.qty * comm.impact_factor;
      const fut = l.qty * (1 + pd) * comm.impact_factor * (1 + id);
      totalCur += cur; totalFut += fut;

      if (!byAsset[a.id]) byAsset[a.id] = { key: a.id, name: a.name, current: 0, future: 0 };
      byAsset[a.id].current += cur; byAsset[a.id].future += fut;

      if (!byCommodity[comm.id]) byCommodity[comm.id] = { key: comm.id, name: comm.name, current: 0, future: 0 };
      byCommodity[comm.id].current += cur; byCommodity[comm.id].future += fut;
    });
  });

  const src = LP_STATE.groupBy === 'commodity' ? byCommodity : byAsset;
  const items = Object.values(src).sort((x, y) => y.current - x.current);
  return { items, totalCur, totalFut };
}

function lpRecompute() {
  if (!LP_STATE.data) return;
  const { totalCur, totalFut } = lpComputeItems();
  lpRenderKpis(totalCur, totalFut);
  lpRenderDumbbell();
}

function lpRenderKpis(totalCur, totalFut) {
  const curEl = document.getElementById('lp-impact-current');
  const futEl = document.getElementById('lp-impact-future');
  const varEl = document.getElementById('lp-variation');
  const pill = document.getElementById('lp-variation-pill');
  if (curEl) curEl.textContent = lpFmt(totalCur);
  if (futEl) futEl.textContent = lpFmt(totalFut);

  if (varEl) {
    if (totalCur === 0) {
      varEl.textContent = '—';
      if (pill) pill.hidden = true;
    } else {
      const pct = (totalFut - totalCur) / totalCur * 100;
      varEl.textContent = (pct > 0 ? '+' : '') + pct.toFixed(1) + ' %';
      if (pill) {
        if (Math.abs(pct) < 0.05) {
          pill.hidden = true;
        } else {
          pill.hidden = false;
          const good = pct < 0;
          pill.textContent = good ? 'Mieux' : 'Moins bien';
          pill.className = 'lp-pill ' + (good ? 'lp-pill--good' : 'lp-pill--bad');
        }
      }
    }
  }

  // Ligne total sous le dumbbell.
  const tCur = document.getElementById('lp-total-current');
  const tFut = document.getElementById('lp-total-future');
  const tDelta = document.getElementById('lp-total-delta');
  if (tCur) tCur.textContent = lpFmt(totalCur);
  if (tFut) tFut.textContent = lpFmt(totalFut);
  if (tDelta) {
    const diff = totalFut - totalCur;
    if (Math.abs(diff) < 1e-9) {
      tDelta.textContent = '±0';
      tDelta.className = 'lp-total__delta';
    } else {
      const good = diff < 0;
      tDelta.textContent = (diff > 0 ? '▲ +' : '▼ ') + lpFmt(diff);
      tDelta.className = 'lp-total__delta ' + (good ? 'lp-total__delta--good' : 'lp-total__delta--bad');
    }
  }
}

// ── Dumbbell SVG ──────────────────────────────────────────────────────────────
function lpRenderDumbbell() {
  const svg = document.getElementById('lp-dumbbell');
  if (!svg || !LP_STATE.data) return;
  const { items } = lpComputeItems();

  while (svg.firstChild) svg.removeChild(svg.firstChild);

  if (!items.length) {
    svg.setAttribute('viewBox', '0 0 600 80');
    const t = document.createElementNS(LP_SVG_NS, 'text');
    t.setAttribute('x', '300'); t.setAttribute('y', '44');
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('font-size', '13'); t.setAttribute('fill', LP_GREY);
    t.setAttribute('font-family', 'Inter, sans-serif');
    t.textContent = 'Aucune donnée à simuler.';
    svg.appendChild(t);
    return;
  }

  const W = 600;
  const rowH = 34;
  const padTop = 16, padBottom = 8;
  const labelW = 150, valueW = 70;
  const x0 = labelW;
  const x1 = W - valueW;
  const H = padTop + items.length * rowH + padBottom;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

  const maxVal = items.reduce(
    (m, it) => Math.max(m, it.current, it.future), 0
  ) || 1;
  const scale = (v) => x0 + (x1 - x0) * (v / maxVal);

  items.forEach((it, i) => {
    const cy = padTop + i * rowH + rowH / 2;
    const xc = scale(it.current);
    const xf = scale(it.future);
    const good = it.future < it.current;
    const changed = Math.abs(it.future - it.current) > 1e-9;
    const color = !changed ? LP_GREY : (good ? LP_GOOD : LP_BAD);

    // libellé
    const label = document.createElementNS(LP_SVG_NS, 'text');
    label.setAttribute('x', '0');
    label.setAttribute('y', String(cy + 4));
    label.setAttribute('font-size', '12');
    label.setAttribute('fill', LP_INK);
    label.setAttribute('font-family', 'Inter, sans-serif');
    label.textContent = it.name.length > 22 ? it.name.slice(0, 21) + '…' : it.name;
    svg.appendChild(label);

    // segment actuel → T+1
    const line = document.createElementNS(LP_SVG_NS, 'line');
    line.setAttribute('x1', String(xc)); line.setAttribute('y1', String(cy));
    line.setAttribute('x2', String(xf)); line.setAttribute('y2', String(cy));
    line.setAttribute('stroke', color); line.setAttribute('stroke-width', '2.5');
    svg.appendChild(line);

    // point actuel (gris)
    const dotC = document.createElementNS(LP_SVG_NS, 'circle');
    dotC.setAttribute('cx', String(xc)); dotC.setAttribute('cy', String(cy));
    dotC.setAttribute('r', '5'); dotC.setAttribute('fill', LP_GREY);
    svg.appendChild(dotC);

    // point T+1 (coloré)
    const dotF = document.createElementNS(LP_SVG_NS, 'circle');
    dotF.setAttribute('cx', String(xf)); dotF.setAttribute('cy', String(cy));
    dotF.setAttribute('r', '5'); dotF.setAttribute('fill', color);
    svg.appendChild(dotF);

    // étiquette Δ %
    const pct = it.current ? (it.future - it.current) / it.current * 100 : 0;
    const dlabel = document.createElementNS(LP_SVG_NS, 'text');
    dlabel.setAttribute('x', String(W));
    dlabel.setAttribute('y', String(cy + 4));
    dlabel.setAttribute('text-anchor', 'end');
    dlabel.setAttribute('font-size', '11');
    dlabel.setAttribute('fill', color);
    dlabel.setAttribute('font-family', 'Inter, sans-serif');
    dlabel.textContent = (pct > 0 ? '+' : '') + pct.toFixed(0) + ' %';
    svg.appendChild(dlabel);
  });
}
```

- [ ] **Step 2: Vérification manuelle (pas d'infra de test JS dans le projet)**

Lancer le serveur :

Run: `./venv/scripts/activate.ps1; python manage.py runserver`

Puis dans le navigateur (connecté), aller sur `/leap/prepare/` et vérifier :
1. La page charge avec la 1ʳᵉ entreprise ; KPIs « Impact actuel » et « T+1 » égaux, variation `±0`/`—`.
2. Les leviers « Production par asset » et « Facteur d'impact par commodité » s'affichent.
3. Bouger un slider production : le champ numérique se met à jour, le `Δ %` s'affiche, KPIs T+1 et dumbbell se recalculent en direct.
4. Saisir une valeur dans un champ numérique : le slider se cale et le calcul suit.
5. Baisser un levier → segment/point T+1 **vert**, pastille **Mieux** ; augmenter → **rouge**, **Moins bien**.
6. Le menu déroulant « Par asset / Par commodité » change le regroupement du dumbbell.
7. « Réinitialiser » remet tous les leviers à 0 et l'état T+1 = actuel.
8. Changer d'entreprise via la combobox recharge les données et remet les leviers à zéro.
9. Console navigateur sans erreur JS.

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/dashboard/js/leap_prepare.js
git commit -m "feat(leap): simulateur Prepare (leviers + dumbbell SVG)"
```

---

### Task 5: Vérification finale

**Files:** aucun (validation transverse)

- [ ] **Step 1: Suite de tests complète de l'app**

Run: `./venv/scripts/activate.ps1; python manage.py test dashboard -v 1`
Expected: PASS (aucune régression ; nouveaux tests `LeapPrepareDataTests` inclus).

- [ ] **Step 2: System check**

Run: `./venv/scripts/activate.ps1; python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 3: Revue diff finale**

Run: `git log --oneline feat/leap-prepare ^main; git diff --stat main...feat/leap-prepare`
Vérifier : 4 commits feature + 1 commit spec, fichiers attendus uniquement (`views.py`, `urls.py`, `leap_prepare.html`, `style.css`, `leap_prepare.js`, `tests.py`, docs).
```
```

(Pas de commit à cette étape — purement de la validation.)
