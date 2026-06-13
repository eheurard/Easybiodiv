# Page « Données ESG » — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une page « Données ESG » au dashboard, entre « Vue d'ensemble » et « Analyse des risques », montrant la tendance carbone, les politiques d'entreprise (`Company_Policy`) et des blocs Market/News en placeholder.

**Architecture:** Page Django classique calquée sur les pages existantes (vue page + vue API JSON, helper `_get_esg_data`, template `extends base.html`, JS natif par page, CSS vanilla avec les tokens du projet). Le modèle `Carbon_emission` est corrigé pour autoriser plusieurs scopes par an, et des données démo sont ajoutées pour Acme.

**Tech Stack:** Django, SQLite (dev), HTML/CSS/JS vanilla (aucun framework frontend), SVG construit à la main pour le graphique.

**Référence spec:** `docs/superpowers/specs/2026-06-13-donnees-esg-page-design.md`

**Convention commandes:** venv actif (`./venv/scripts/activate.ps1`). Lancer les tests avec `python manage.py test`.

---

## File Structure

| Fichier | Responsabilité | Action |
|---|---|---|
| `dashboard/models.py` | Modèle `Carbon_emission` (Meta + `__str__`) | Modifier |
| `dashboard/migrations/0021_alter_carbon_emission_unique_together.py` | Migration du changement `unique_together` | Créer (auto) |
| `dashboard/views.py` | `_get_esg_data`, helper `_linear_projection`, vues `esg`/`esg_data` | Modifier |
| `dashboard/urls.py` | Routes page + API | Modifier |
| `dashboard/management/commands/populate_acme.py` | Données carbone démo | Modifier |
| `templates/base.html` | Item de navigation « Données ESG » | Modifier |
| `dashboard/templates/dashboard/esg.html` | Template de la page | Créer |
| `dashboard/static/dashboard/js/esg.js` | Combobox, graphique SVG, rendus, onglets | Créer |
| `dashboard/static/dashboard/css/style.css` | Styles `esg-*` | Modifier (append) |
| `dashboard/tests.py` | Tests helper + vues + page | Modifier (append) |

---

## Task 1: Corriger le modèle `Carbon_emission` + migration

**Files:**
- Modify: `dashboard/models.py:356-366`
- Create: `dashboard/migrations/0021_alter_carbon_emission_unique_together.py` (auto)
- Test: `dashboard/tests.py` (append)

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `dashboard/tests.py` :

```python
from django.db import IntegrityError, transaction
from .models import Carbon_emission


class CarbonEmissionModelTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='CarbonCorp')

    def test_multiple_scopes_same_year_allowed(self):
        Carbon_emission.objects.create(
            company=self.company, year=2024, scope='Scope 1', carbon_emission=10.0
        )
        Carbon_emission.objects.create(
            company=self.company, year=2024, scope='Scope 2', carbon_emission=5.0
        )
        self.assertEqual(
            Carbon_emission.objects.filter(company=self.company, year=2024).count(), 2
        )

    def test_duplicate_company_year_scope_rejected(self):
        Carbon_emission.objects.create(
            company=self.company, year=2024, scope='Scope 1', carbon_emission=10.0
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Carbon_emission.objects.create(
                    company=self.company, year=2024, scope='Scope 1', carbon_emission=99.0
                )

    def test_str_does_not_raise(self):
        e = Carbon_emission.objects.create(
            company=self.company, year=2024, scope='Scope 1', carbon_emission=10.0
        )
        self.assertEqual(str(e), 'CarbonCorp - 2024 - Scope 1')
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python manage.py test dashboard.tests.CarbonEmissionModelTests -v 2`
Expected: FAIL — `test_multiple_scopes_same_year_allowed` lève `IntegrityError` (contrainte `('company','year')`), et `test_str_does_not_raise` lève `AttributeError` (`business_activity`).

- [ ] **Step 3: Corriger le modèle**

Dans `dashboard/models.py`, remplacer la classe `Carbon_emission` (actuellement lignes 356-366) par :

```python
class Carbon_emission(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    year = models.IntegerField()
    scope = models.CharField(max_length=255)
    carbon_emission = models.FloatField(default=0)

    def __str__(self):
        return f"{self.company.name} - {self.year} - {self.scope}"

    class Meta:
        unique_together = ('company', 'year', 'scope')
```

- [ ] **Step 4: Générer la migration**

Run: `python manage.py makemigrations dashboard --name alter_carbon_emission_unique_together`
Expected: crée `dashboard/migrations/0021_alter_carbon_emission_unique_together.py` avec `AlterUniqueTogether(name='carbon_emission', unique_together={('company', 'year', 'scope')})`.

- [ ] **Step 5: Appliquer la migration et relancer les tests**

Run: `python manage.py migrate dashboard; python manage.py test dashboard.tests.CarbonEmissionModelTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add dashboard/models.py dashboard/migrations/0021_alter_carbon_emission_unique_together.py dashboard/tests.py
git commit -m "fix(carbon): autoriser plusieurs scopes par an + corriger __str__"
```

---

## Task 2: `_get_esg_data` — agrégation carbone + projection

**Files:**
- Modify: `dashboard/views.py` (imports + nouvelles fonctions)
- Test: `dashboard/tests.py` (append)

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `dashboard/tests.py` :

```python
class EsgDataCarbonTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='esguser', password='pass')
        self.client.force_login(self.user)
        self.company = Company.objects.create(name='EsgCorp')

    def _carbon(self, year, scope, val):
        Carbon_emission.objects.create(
            company=self.company, year=year, scope=scope, carbon_emission=val
        )

    def test_historical_sums_scopes_per_year(self):
        from .views import _get_esg_data
        self._carbon(2022, 'Scope 1', 10.0)
        self._carbon(2022, 'Scope 2', 5.0)
        self._carbon(2023, 'Scope 1', 8.0)
        data = _get_esg_data(self.company)
        hist = data['carbon']['historical']
        self.assertEqual([h['year'] for h in hist], [2022, 2023])
        self.assertAlmostEqual(hist[0]['total'], 15.0, places=2)
        self.assertAlmostEqual(hist[0]['scopes']['Scope 1'], 10.0, places=2)

    def test_projection_extends_to_2030(self):
        from .views import _get_esg_data
        self._carbon(2022, 'Scope 1', 20.0)
        self._carbon(2023, 'Scope 1', 10.0)
        data = _get_esg_data(self.company)
        proj = data['carbon']['projection']
        self.assertTrue(proj, 'projection should not be empty with 2 points')
        self.assertEqual(proj[-1]['year'], 2030)
        # Anchor: premier point de projection = dernier point historique
        self.assertEqual(proj[0]['year'], 2023)

    def test_reduction_pct_negative_when_declining(self):
        from .views import _get_esg_data
        self._carbon(2022, 'Scope 1', 20.0)
        self._carbon(2023, 'Scope 1', 10.0)
        data = _get_esg_data(self.company)
        self.assertEqual(data['carbon']['latest_year'], 2023)
        self.assertAlmostEqual(data['carbon']['latest_total'], 10.0, places=2)
        self.assertLess(data['carbon']['reduction_pct'], 0)

    def test_no_carbon_data_is_empty(self):
        from .views import _get_esg_data
        data = _get_esg_data(self.company)
        self.assertEqual(data['carbon']['historical'], [])
        self.assertEqual(data['carbon']['projection'], [])
        self.assertIsNone(data['carbon']['latest_year'])
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python manage.py test dashboard.tests.EsgDataCarbonTests -v 2`
Expected: FAIL — `ImportError: cannot import name '_get_esg_data'`.

- [ ] **Step 3: Implémenter le helper carbone**

Dans `dashboard/views.py`, ajouter `Carbon_emission` à l'import depuis `.models` (bloc lignes 10-14) :

```python
from .models import (
    Asset, Carbon_emission, Commodity, Company, Company_Policy, Company_Revenue,
    Company_Revenue_Sector, DisclosureRequirement, E4Assessment, Ownership,
    Production,
)
```

Puis ajouter, avant la définition de `def index(` (vers la ligne 1021), ce bloc :

```python
ESG_PROJECTION_END_YEAR = 2030


def _linear_projection(points, end_year):
    """Extrapolation linéaire (moindres carrés) des totaux annuels.

    `points` : liste de (year, total) triée par année croissante.
    Retourne [{'year', 'total'}] du dernier point historique (ancre) jusqu'à
    `end_year` inclus. Renvoie [] si moins de 2 points ou pente indéfinie.
    """
    if len(points) < 2:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return []
    slope = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n)) / denom
    intercept = mean_y - slope * mean_x
    last_year = xs[-1]
    out = [{'year': last_year, 'total': round(ys[-1], 2)}]
    for yr in range(last_year + 1, end_year + 1):
        val = slope * yr + intercept
        out.append({'year': yr, 'total': round(max(val, 0.0), 2)})
    return out


def _get_esg_carbon(company):
    emissions = Carbon_emission.objects.filter(company=company).order_by('year')
    by_year = defaultdict(lambda: {'total': 0.0, 'scopes': defaultdict(float)})
    for e in emissions:
        by_year[e.year]['total'] += e.carbon_emission
        by_year[e.year]['scopes'][e.scope] += e.carbon_emission

    historical = [
        {
            'year': y,
            'total': round(d['total'], 2),
            'scopes': {k: round(v, 2) for k, v in d['scopes'].items()},
        }
        for y, d in sorted(by_year.items())
    ]

    projection = _linear_projection(
        [(h['year'], h['total']) for h in historical], ESG_PROJECTION_END_YEAR
    )

    if historical:
        first_total = historical[0]['total']
        latest = historical[-1]
        latest_year = latest['year']
        latest_total = latest['total']
        reduction_pct = (
            round((latest_total - first_total) / first_total * 100, 1)
            if first_total else None
        )
    else:
        latest_year = latest_total = reduction_pct = None

    return {
        'historical': historical,
        'projection': projection,
        'latest_year': latest_year,
        'latest_total': latest_total,
        'reduction_pct': reduction_pct,
        'unit': 'tCO2e',
    }


def _get_esg_data(company):
    return {
        'company_id': company.pk,
        'company_name': company.name,
        'carbon': _get_esg_carbon(company),
    }
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `python manage.py test dashboard.tests.EsgDataCarbonTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "feat(esg): agrégation carbone + projection linéaire dans _get_esg_data"
```

---

## Task 3: `_get_esg_data` — politiques (featured + framework)

**Files:**
- Modify: `dashboard/views.py` (`_get_esg_data` + helper politiques)
- Test: `dashboard/tests.py` (append)

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `dashboard/tests.py` :

```python
class EsgDataPoliciesTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='PolCorp')
        self.ptype = Policy_Type.objects.create(name='Risque Réglementaire')
        self.sub = Policy_Subcategory.objects.create(
            policy_type=self.ptype, name='EUDR'
        )

    def _policy(self, level_name, score, comment=''):
        level = Policy_Level.objects.create(
            subcategory=self.sub, name=level_name, score=score,
            description=f'desc {level_name}',
        )
        Company_Policy.objects.create(
            company=self.company, policy_level=level,
            policy_date='2024-01-01', comment=comment,
        )

    def test_featured_is_two_highest_scores(self):
        from .views import _get_esg_data
        self._policy('Faible', 0.2)
        self._policy('Fort', 0.9)
        self._policy('Moyen', 0.5)
        data = _get_esg_data(self.company)
        featured = data['policies']['featured']
        self.assertEqual(len(featured), 2)
        self.assertEqual(featured[0]['level'], 'Fort')
        self.assertEqual(featured[1]['level'], 'Moyen')
        self.assertEqual(featured[0]['tags'], ['Risque Réglementaire', 'Fort'])

    def test_framework_lists_all_policies(self):
        from .views import _get_esg_data
        self._policy('Faible', 0.2)
        self._policy('Fort', 0.9)
        data = _get_esg_data(self.company)
        self.assertEqual(len(data['policies']['framework']), 2)
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python manage.py test dashboard.tests.EsgDataPoliciesTests -v 2`
Expected: FAIL — `KeyError: 'policies'`.

- [ ] **Step 3: Implémenter le helper politiques**

Dans `dashboard/views.py`, ajouter cette fonction juste avant `def _get_esg_data(`:

```python
def _get_esg_policies(company):
    policies_qs = (
        Company_Policy.objects.filter(company=company)
        .select_related('policy_level__subcategory__policy_type')
    )
    items = []
    for cp in policies_qs:
        pl = cp.policy_level
        if pl is None:
            continue
        sub = pl.subcategory
        items.append({
            'type': sub.policy_type.name,
            'subcategory': sub.name,
            'level': pl.name,
            'description': pl.description,
            'score': pl.score,
            'date': cp.policy_date.isoformat() if cp.policy_date else None,
            'comment': cp.comment,
        })

    featured = sorted(
        items, key=lambda x: (x['score'] if x['score'] is not None else 0.0),
        reverse=True,
    )[:2]
    featured_out = [{
        'type': it['type'],
        'subcategory': it['subcategory'],
        'level': it['level'],
        'description': it['description'],
        'score': it['score'],
        'date': it['date'],
        'comment': it['comment'],
        'tags': [it['type'], it['level']],
    } for it in featured]

    framework = sorted(items, key=lambda x: (x['type'], x['subcategory']))
    framework_out = [{
        'type': it['type'],
        'subcategory': it['subcategory'],
        'level': it['level'],
        'score': it['score'],
        'date': it['date'],
    } for it in framework]

    return {'featured': featured_out, 'framework': framework_out}
```

Puis modifier `_get_esg_data` pour ajouter la clé `policies` :

```python
def _get_esg_data(company):
    return {
        'company_id': company.pk,
        'company_name': company.name,
        'carbon': _get_esg_carbon(company),
        'policies': _get_esg_policies(company),
    }
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `python manage.py test dashboard.tests.EsgDataPoliciesTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "feat(esg): politiques featured + framework dans _get_esg_data"
```

---

## Task 4: `_get_esg_data` — placeholders market / news / social / governance

**Files:**
- Modify: `dashboard/views.py` (`_get_esg_data`)
- Test: `dashboard/tests.py` (append)

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `dashboard/tests.py` :

```python
class EsgDataPlaceholdersTests(TestCase):

    def test_market_news_social_governance_present(self):
        from .views import _get_esg_data
        company = Company.objects.create(name='PlhCorp', isin='FR0000', ticker='PLH')
        data = _get_esg_data(company)
        self.assertTrue(data['market']['is_demo'])
        self.assertEqual(data['market']['ticker'], 'PLH')
        self.assertEqual(data['market']['isin'], 'FR0000')
        self.assertEqual(data['news'], [])
        self.assertFalse(data['social']['available'])
        self.assertFalse(data['governance']['available'])
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python manage.py test dashboard.tests.EsgDataPlaceholdersTests -v 2`
Expected: FAIL — `KeyError: 'market'`.

- [ ] **Step 3: Implémenter les placeholders**

Dans `dashboard/views.py`, remplacer `_get_esg_data` par :

```python
def _get_esg_data(company):
    return {
        'company_id': company.pk,
        'company_name': company.name,
        'carbon': _get_esg_carbon(company),
        'policies': _get_esg_policies(company),
        'market': {
            'is_demo': True,
            'isin': company.isin,
            'ticker': company.ticker,
            'price': 142.85,
            'currency': 'EUR',
            'change_pct': 2.4,
            'market_cap': '4.2B',
            'esg_rating': 'AA+',
            'relative_perf': '+12.5% vs MSCI ESG',
            'sparkline': [35, 32, 38, 30, 25, 28, 20, 22, 15, 18, 5],
        },
        'news': [],
        'social': {'available': False},
        'governance': {'available': False},
    }
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `python manage.py test dashboard.tests.EsgDataPlaceholdersTests -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "feat(esg): placeholders market/news/social/governance"
```

---

## Task 5: Vues + URLs (page + API)

**Files:**
- Modify: `dashboard/views.py` (vues `esg`, `esg_data`)
- Modify: `dashboard/urls.py`
- Test: `dashboard/tests.py` (append)

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `dashboard/tests.py` :

```python
class EsgViewTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='vuser', password='pass')
        self.company = Company.objects.create(name='ViewCorp')

    def test_page_requires_login(self):
        response = self.client.get(reverse('dashboard:esg'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_page_200_when_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard:esg'))
        self.assertEqual(response.status_code, 200)

    def test_api_returns_json(self):
        self.client.force_login(self.user)
        url = reverse('dashboard:esg_data', kwargs={'pk': self.company.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/json', response['Content-Type'])

    def test_api_404_for_unknown_company(self):
        self.client.force_login(self.user)
        url = reverse('dashboard:esg_data', kwargs={'pk': 99999})
        self.assertEqual(self.client.get(url).status_code, 404)
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python manage.py test dashboard.tests.EsgViewTests -v 2`
Expected: FAIL — `NoReverseMatch: 'esg' is not a valid view function or pattern name`.

- [ ] **Step 3: Ajouter les vues**

Dans `dashboard/views.py`, ajouter après la vue `index` (vers la ligne 1030) :

```python
@login_required
@require_GET
def esg(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_esg_data(first)
    return render(request, 'dashboard/esg.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@login_required
@require_GET
def esg_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_esg_data(company))
```

- [ ] **Step 4: Ajouter les routes**

Dans `dashboard/urls.py`, ajouter ces deux lignes dans `urlpatterns` (après la ligne `path('', views.index, name='index'),`) :

```python
    path('esg-data/', views.esg, name='esg'),
    path('api/company/<int:pk>/esg-data/', views.esg_data, name='esg_data'),
```

- [ ] **Step 5: Lancer le test pour vérifier qu'il passe**

Run: `python manage.py test dashboard.tests.EsgViewTests -v 2`
Expected: PASS (4 tests). Note : le rendu de `esg.html` réussit une fois le template créé (Task 7) ; si `test_page_200_when_logged_in` échoue ici avec `TemplateDoesNotExist`, c'est attendu — il repassera après la Task 7. Les 3 autres tests doivent passer.

- [ ] **Step 6: Commit**

```bash
git add dashboard/views.py dashboard/urls.py dashboard/tests.py
git commit -m "feat(esg): vues page + API et routes"
```

---

## Task 6: Item de navigation dans `base.html`

**Files:**
- Modify: `templates/base.html:49-50`

- [ ] **Step 1: Insérer l'item de menu**

Dans `templates/base.html`, entre le `</li>` de « Vue d'ensemble » (ligne 49) et le `<li>` du groupe « Analyse des risques » (ligne 50), insérer :

```html
          <li>
            <a href="{% url 'dashboard:esg' %}" class="sidebar__nav-link {% block nav_esg %}{% endblock %}" aria-label="Données ESG">
              <svg class="sidebar__nav-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M3 17V3M3 17h14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                <rect x="6" y="10" width="2.5" height="4" stroke="currentColor" stroke-width="1.3"/>
                <rect x="11" y="6" width="2.5" height="8" stroke="currentColor" stroke-width="1.3"/>
              </svg>
              <span class="sidebar__nav-label">Données ESG</span>
            </a>
          </li>
```

- [ ] **Step 2: Vérification manuelle**

Run: `python manage.py runserver` puis ouvrir `http://127.0.0.1:8000/esg-data/` (connecté).
Expected: le lien « Données ESG » apparaît dans la barre latérale entre « Vue d'ensemble » et « Analyse des risques ». (La page elle-même sera complétée en Task 7.)

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat(esg): item de navigation Données ESG"
```

---

## Task 7: Template `esg.html`

**Files:**
- Create: `dashboard/templates/dashboard/esg.html`

- [ ] **Step 1: Créer le template**

Créer `dashboard/templates/dashboard/esg.html` avec :

```html
{% extends "base.html" %}
{% load static %}

{% block title %}Données ESG — Easybiodiv{% endblock %}

{% block nav_esg %}active{% endblock %}

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
<div class="esg-page">

  <div class="esg-theme-tabs" role="tablist" aria-label="Thème ESG">
    <button class="esg-theme-tab esg-theme-tab--active" data-theme="environmental" role="tab" aria-selected="true">Environmental</button>
    <button class="esg-theme-tab" data-theme="social" role="tab" aria-selected="false">Social</button>
    <button class="esg-theme-tab" data-theme="governance" role="tab" aria-selected="false">Governance</button>
  </div>

  <!-- ── Environmental ─────────────────────────────────────────────── -->
  <div class="esg-theme-panel esg-theme-panel--active" data-theme-panel="environmental">
    <div class="esg-grid">

      <div class="esg-grid__main">

        <section class="card esg-chart">
          <div class="esg-chart__head">
            <div>
              <h3 class="esg-chart__title">Tendance des émissions carbone</h3>
              <p class="esg-chart__sub">Historique et projection (<span data-esg="carbon-unit">tCO2e</span>)</p>
            </div>
            <div class="esg-chart__legend">
              <span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--solid"></span>Historique</span>
              <span class="esg-chart__legend-item"><span class="esg-chart__line esg-chart__line--dashed"></span>Projection 2030</span>
            </div>
          </div>
          <div class="esg-chart__kpis">
            <div class="esg-chart__kpi">
              <span class="esg-chart__kpi-value" data-esg="carbon-latest">—</span>
              <span class="esg-chart__kpi-label label-caps">Dernier total</span>
            </div>
            <div class="esg-chart__kpi">
              <span class="esg-chart__kpi-value" data-esg="carbon-reduction">—</span>
              <span class="esg-chart__kpi-label label-caps">Évolution</span>
            </div>
          </div>
          <div class="esg-chart__canvas" id="esg-chart-canvas" aria-label="Graphique des émissions carbone">
            <p class="esg-empty" id="esg-chart-empty" hidden>Aucune donnée carbone disponible.</p>
          </div>
        </section>

        <section class="esg-featured" id="esg-featured" aria-label="Politiques en avant"></section>

        <section class="card esg-framework">
          <div class="esg-framework__head">
            <h4 class="esg-framework__title label-caps">Cadre des politiques d'entreprise</h4>
          </div>
          <div class="esg-framework__list" id="esg-framework-list"></div>
        </section>

      </div>

      <aside class="esg-grid__side">

        <section class="card esg-market">
          <div class="esg-market__head">
            <h3 class="esg-market__title label-caps">Market Intelligence</h3>
            <span class="esg-market__demo" id="esg-market-demo" hidden>Démo</span>
          </div>
          <div class="esg-market__body" id="esg-market-body"></div>
        </section>

        <section class="card esg-news">
          <div class="esg-news__head">
            <h3 class="esg-news__title label-caps">Latest ESG News</h3>
          </div>
          <div class="esg-news__body" id="esg-news-body">
            <p class="esg-empty">No news yet</p>
          </div>
        </section>

        <div class="esg-decoration" aria-hidden="true">
          <span class="esg-decoration__title">Grounded Intelligence</span>
          <span class="esg-decoration__sub label-caps">Preserving Biodiversity</span>
        </div>

      </aside>

    </div>
  </div>

  <!-- ── Social ────────────────────────────────────────────────────── -->
  <div class="esg-theme-panel" data-theme-panel="social" hidden>
    <div class="card esg-coming">
      <p class="esg-empty">Social — à venir, aucune donnée disponible.</p>
    </div>
  </div>

  <!-- ── Governance ────────────────────────────────────────────────── -->
  <div class="esg-theme-panel" data-theme-panel="governance" hidden>
    <div class="card esg-coming">
      <p class="esg-empty">Governance — à venir, aucune donnée disponible.</p>
    </div>
  </div>

</div>
{% endblock %}

{% block extra_js %}
{{ companies|json_script:"esg-companies" }}
{{ initial_data|json_script:"esg-data" }}
<script>var ESG_API_URL = "{% url 'dashboard:esg_data' pk=0 %}".replace('0/', '');</script>
<script src="{% static 'dashboard/js/esg.js' %}"></script>
{% endblock %}
```

- [ ] **Step 2: Vérifier que la vue page rend bien 200**

Run: `python manage.py test dashboard.tests.EsgViewTests -v 2`
Expected: PASS (4 tests, y compris `test_page_200_when_logged_in`).

- [ ] **Step 3: Commit**

```bash
git add dashboard/templates/dashboard/esg.html
git commit -m "feat(esg): template de la page Données ESG"
```

---

## Task 8: JS `esg.js`

**Files:**
- Create: `dashboard/static/dashboard/js/esg.js`

- [ ] **Step 1: Créer le fichier JS**

Créer `dashboard/static/dashboard/js/esg.js` avec le contenu complet suivant :

```javascript
'use strict';

const ESG_COMPANY_KEY = 'selected-company-id';

const ESG_STATE = { data: null };

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('esg-companies');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('esg-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  esgInitThemeTabs();

  const savedId = parseInt(localStorage.getItem(ESG_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    fetch(ESG_API_URL.replace('/0/', '/' + savedId + '/'))
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => { esgRender(data); esgInitCombobox(companies, data); })
      .catch(err => { console.error('esg fetch failed:', err); esgInitCombobox(companies, initialData); if (initialData) esgRender(initialData); });
  } else {
    if (initialData) esgRender(initialData);
    esgInitCombobox(companies, initialData);
  }
});


function esgInitThemeTabs() {
  const tabs = document.querySelectorAll('.esg-theme-tab');
  const panels = document.querySelectorAll('.esg-theme-panel');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const theme = tab.dataset.theme;
      tabs.forEach(t => {
        const active = t === tab;
        t.classList.toggle('esg-theme-tab--active', active);
        t.setAttribute('aria-selected', String(active));
      });
      panels.forEach(p => {
        const active = p.dataset.themePanel === theme;
        p.classList.toggle('esg-theme-panel--active', active);
        if (active) { p.removeAttribute('hidden'); } else { p.setAttribute('hidden', ''); }
      });
    });
  });
}


function esgRender(data) {
  ESG_STATE.data = data;
  esgRenderCarbon(data.carbon);
  esgRenderFeatured(data.policies.featured);
  esgRenderFramework(data.policies.framework);
  esgRenderMarket(data.market);
}


function esgRenderCarbon(carbon) {
  const unitEl = document.querySelector('[data-esg="carbon-unit"]');
  if (unitEl) unitEl.textContent = carbon.unit || 'tCO2e';

  const latestEl = document.querySelector('[data-esg="carbon-latest"]');
  if (latestEl) {
    latestEl.textContent = carbon.latest_total != null
      ? esgFmtNum(carbon.latest_total) + ' ' + (carbon.unit || '') : '—';
  }

  const redEl = document.querySelector('[data-esg="carbon-reduction"]');
  if (redEl) {
    if (carbon.reduction_pct == null) {
      redEl.textContent = '—';
      redEl.className = 'esg-chart__kpi-value';
    } else {
      const sign = carbon.reduction_pct > 0 ? '+' : '';
      redEl.textContent = sign + carbon.reduction_pct + '%';
      redEl.className = 'esg-chart__kpi-value ' +
        (carbon.reduction_pct <= 0 ? 'esg-chart__kpi-value--good' : 'esg-chart__kpi-value--bad');
    }
  }

  esgRenderChart(carbon);
}


function esgRenderChart(carbon) {
  const canvas = document.getElementById('esg-chart-canvas');
  const empty = document.getElementById('esg-chart-empty');
  if (!canvas) return;

  canvas.querySelectorAll('svg').forEach(s => s.remove());

  const hist = carbon.historical || [];
  if (!hist.length) {
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;

  const proj = carbon.projection || [];
  const allYears = hist.map(h => h.year).concat(proj.map(p => p.year));
  const allTotals = hist.map(h => h.total).concat(proj.map(p => p.total));
  const minYear = Math.min(...allYears);
  const maxYear = Math.max(...allYears);
  const maxVal = Math.max(...allTotals, 1);

  const W = 1000, H = 320;
  const padL = 56, padR = 16, padT = 16, padB = 32;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('class', 'esg-chart__svg');

  const xOf = yr => padL + (maxYear === minYear ? 0 : (yr - minYear) / (maxYear - minYear) * plotW);
  const yOf = v => padT + plotH - (v / maxVal) * plotH;

  // Gridlines + Y labels (5 niveaux)
  for (let i = 0; i <= 4; i++) {
    const val = maxVal * i / 4;
    const y = yOf(val);
    const line = document.createElementNS(NS, 'line');
    line.setAttribute('x1', padL); line.setAttribute('x2', W - padR);
    line.setAttribute('y1', y); line.setAttribute('y2', y);
    line.setAttribute('class', 'esg-chart__grid');
    svg.appendChild(line);

    const label = document.createElementNS(NS, 'text');
    label.setAttribute('x', padL - 8); label.setAttribute('y', y + 4);
    label.setAttribute('text-anchor', 'end');
    label.setAttribute('class', 'esg-chart__axis-label');
    label.textContent = esgFmtNum(Math.round(val));
    svg.appendChild(label);
  }

  // X labels (par année historique + dernière projection)
  const xYears = hist.map(h => h.year);
  if (proj.length) xYears.push(proj[proj.length - 1].year);
  xYears.forEach(yr => {
    const label = document.createElementNS(NS, 'text');
    label.setAttribute('x', xOf(yr)); label.setAttribute('y', H - 10);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('class', 'esg-chart__axis-label');
    label.textContent = yr;
    svg.appendChild(label);
  });

  const histPath = hist.map((h, i) => (i ? 'L' : 'M') + xOf(h.year) + ',' + yOf(h.total)).join(' ');
  const histLine = document.createElementNS(NS, 'path');
  histLine.setAttribute('d', histPath);
  histLine.setAttribute('class', 'esg-chart__path esg-chart__path--hist');
  svg.appendChild(histLine);

  if (proj.length) {
    const projPath = proj.map((p, i) => (i ? 'L' : 'M') + xOf(p.year) + ',' + yOf(p.total)).join(' ');
    const projLine = document.createElementNS(NS, 'path');
    projLine.setAttribute('d', projPath);
    projLine.setAttribute('class', 'esg-chart__path esg-chart__path--proj');
    svg.appendChild(projLine);
  }

  hist.forEach(h => {
    const dot = document.createElementNS(NS, 'circle');
    dot.setAttribute('cx', xOf(h.year)); dot.setAttribute('cy', yOf(h.total));
    dot.setAttribute('r', 4);
    dot.setAttribute('class', 'esg-chart__dot');
    const title = document.createElementNS(NS, 'title');
    title.textContent = h.year + ' : ' + esgFmtNum(h.total) + ' ' + (carbon.unit || '');
    dot.appendChild(title);
    svg.appendChild(dot);
  });

  canvas.appendChild(svg);
}


function esgRenderFeatured(featured) {
  const wrap = document.getElementById('esg-featured');
  if (!wrap) return;
  if (!featured || !featured.length) {
    wrap.innerHTML = '<p class="esg-empty">Aucune politique enregistrée.</p>';
    return;
  }
  wrap.innerHTML = featured.map(p => {
    const tags = (p.tags || []).map(t =>
      '<span class="esg-policy-card__tag">' + escHtml(t) + '</span>').join('');
    const score = p.score != null
      ? '<span class="esg-policy-card__score">' + Math.round(p.score * 100) + '</span>' : '';
    return (
      '<article class="card esg-policy-card">' +
      '<div class="esg-policy-card__head">' +
      '<h4 class="esg-policy-card__title">' + escHtml(p.subcategory) + '</h4>' +
      score +
      '</div>' +
      '<p class="esg-policy-card__level">' + escHtml(p.level) + '</p>' +
      '<p class="esg-policy-card__desc">' + escHtml(p.description || '') + '</p>' +
      '<div class="esg-policy-card__tags">' + tags + '</div>' +
      '</article>'
    );
  }).join('');
}


function esgRenderFramework(framework) {
  const list = document.getElementById('esg-framework-list');
  if (!list) return;
  if (!framework || !framework.length) {
    list.innerHTML = '<p class="esg-empty">Aucune politique enregistrée.</p>';
    return;
  }
  list.innerHTML = framework.map(p => {
    const sub = [p.level, p.date].filter(Boolean).join(' • ');
    return (
      '<div class="esg-framework__item">' +
      '<div class="esg-framework__item-text">' +
      '<p class="esg-framework__item-name">' + escHtml(p.subcategory) + '</p>' +
      '<p class="esg-framework__item-sub">' + escHtml(sub) + '</p>' +
      '</div>' +
      '<span class="esg-framework__item-type">' + escHtml(p.type) + '</span>' +
      '</div>'
    );
  }).join('');
}


function esgRenderMarket(market) {
  const body = document.getElementById('esg-market-body');
  const demo = document.getElementById('esg-market-demo');
  if (!body) return;
  if (demo) demo.hidden = !market.is_demo;

  const spark = esgSparkline(market.sparkline || []);
  const changeClass = (market.change_pct >= 0) ? 'esg-market__change--up' : 'esg-market__change--down';
  const changeSign = (market.change_pct >= 0) ? '+' : '';

  body.innerHTML =
    '<div class="esg-market__price-row">' +
    '<div><p class="esg-market__price-label label-caps">Cours (' + escHtml(market.ticker || '—') + ')</p>' +
    '<p class="esg-market__price">' + esgFmtMoney(market.price, market.currency) + '</p></div>' +
    '<div class="esg-market__change ' + changeClass + '">' + changeSign + market.change_pct + '%</div>' +
    '</div>' +
    spark +
    '<div class="esg-market__stats">' +
    esgStatRow('Capitalisation', market.market_cap) +
    esgStatRow('Notation ESG', market.esg_rating) +
    esgStatRow('Perf. relative', market.relative_perf) +
    esgStatRow('ISIN', market.isin) +
    '</div>';
}


function esgStatRow(label, value) {
  return '<div class="esg-market__stat">' +
    '<span class="esg-market__stat-label">' + escHtml(label) + '</span>' +
    '<span class="esg-market__stat-value">' + escHtml(String(value != null ? value : '—')) + '</span>' +
    '</div>';
}


function esgSparkline(points) {
  if (!points.length) return '';
  const max = Math.max(...points, 1);
  const stepX = 200 / (points.length - 1 || 1);
  const d = points.map((p, i) =>
    (i ? 'L' : 'M') + (i * stepX).toFixed(1) + ',' + (40 - (p / max) * 35).toFixed(1)).join(' ');
  return '<svg class="esg-market__spark" viewBox="0 0 200 40" preserveAspectRatio="none">' +
    '<path d="' + d + '" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
}


function esgInitCombobox(companies, initialData) {
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
    localStorage.setItem(ESG_COMPANY_KEY, id);
    fetch(ESG_API_URL.replace('/0/', '/' + id + '/'))
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => esgRender(data))
      .catch(err => console.error('esg fetch failed:', err));
  });

  document.addEventListener('click', e => {
    if (!combobox.contains(e.target)) closeList();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeList();
  });
}


function esgFmtNum(val) {
  if (Math.abs(val) >= 1e6) return (val / 1e6).toFixed(1) + ' M';
  if (Math.abs(val) >= 1e3) return (val / 1e3).toFixed(1) + ' k';
  return String(Math.round(val));
}


function esgFmtMoney(val, currency) {
  const sym = currency === 'EUR' ? '€' : (currency === 'USD' ? '$' : '');
  return sym + Number(val).toFixed(2);
}


function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
```

- [ ] **Step 2: Vérification manuelle**

Run: `python manage.py runserver`, ouvrir `http://127.0.0.1:8000/esg-data/` connecté, sélectionner Acme Corp (après Task 10 pour les données carbone).
Expected (sans données carbone, ex. autre entreprise) : le bloc graphique affiche « Aucune donnée carbone disponible » ; les politiques, le bloc market (badge Démo, sparkline) et « No news yet » s'affichent ; les onglets Social/Governance basculent vers l'état « à venir ».

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/dashboard/js/esg.js
git commit -m "feat(esg): JS combobox, graphique SVG, rendus et onglets"
```

---

## Task 9: Styles CSS `esg-*`

**Files:**
- Modify: `dashboard/static/dashboard/css/style.css` (append)

- [ ] **Step 1: Ajouter les styles**

Ajouter à la fin de `dashboard/static/dashboard/css/style.css` :

```css
/* ─── ESG page ──────────────────────────────────────────────────────────── */
.esg-page { display: flex; flex-direction: column; gap: 24px; }

.esg-theme-tabs {
  display: inline-flex; gap: 4px; padding: 4px;
  background: var(--color-surface-container);
  border: 1px solid var(--color-outline-variant);
  border-radius: 10px; align-self: flex-start;
}
.esg-theme-tab {
  border: none; background: transparent; cursor: pointer;
  padding: 8px 24px; border-radius: 7px;
  font-family: var(--font-family); font-size: 14px; font-weight: 600;
  color: var(--color-on-surface-variant); transition: background .15s, color .15s;
}
.esg-theme-tab--active {
  background: var(--color-surface-container-lowest);
  color: var(--color-primary);
  box-shadow: 0 1px 3px rgba(0,0,0,.08);
}

.esg-grid {
  display: grid; grid-template-columns: 2fr 1fr; gap: 24px; align-items: start;
}
.esg-grid__main { display: flex; flex-direction: column; gap: 24px; min-width: 0; }
.esg-grid__side { display: flex; flex-direction: column; gap: 24px; min-width: 0; }
@media (max-width: 1100px) { .esg-grid { grid-template-columns: 1fr; } }

/* Chart */
.esg-chart__head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.esg-chart__title { font-size: 20px; font-weight: 600; color: var(--color-primary); margin: 0 0 4px; }
.esg-chart__sub { font-size: 14px; color: var(--color-on-surface-variant); margin: 0; }
.esg-chart__legend { display: flex; gap: 16px; flex-wrap: wrap; }
.esg-chart__legend-item { display: flex; align-items: center; gap: 6px; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--color-on-surface-variant); }
.esg-chart__line { width: 16px; height: 0; border-top: 2px solid var(--color-primary); }
.esg-chart__line--dashed { border-top-style: dashed; }
.esg-chart__kpis { display: flex; gap: 32px; margin-bottom: 16px; }
.esg-chart__kpi { display: flex; flex-direction: column; gap: 2px; }
.esg-chart__kpi-value { font-size: 22px; font-weight: 600; color: var(--color-on-surface); }
.esg-chart__kpi-value--good { color: #2d6a4f; }
.esg-chart__kpi-value--bad { color: var(--color-error); }
.esg-chart__kpi-label { color: var(--color-on-surface-variant); }
.esg-chart__canvas { width: 100%; height: 320px; position: relative; }
.esg-chart__svg { width: 100%; height: 100%; display: block; }
.esg-chart__grid { stroke: var(--color-outline-variant); stroke-width: 1; opacity: .5; }
.esg-chart__axis-label { fill: var(--color-on-surface-variant); font-size: 11px; font-family: var(--font-family); }
.esg-chart__path { fill: none; stroke: var(--color-primary); stroke-width: 3; }
.esg-chart__path--proj { stroke-dasharray: 8 6; opacity: .8; }
.esg-chart__dot { fill: var(--color-primary); }

/* Featured policy cards */
.esg-featured { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 700px) { .esg-featured { grid-template-columns: 1fr; } }
.esg-policy-card { display: flex; flex-direction: column; gap: 10px; }
.esg-policy-card__head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.esg-policy-card__title { font-size: 16px; font-weight: 700; color: var(--color-primary); margin: 0; }
.esg-policy-card__score { font-size: 13px; font-weight: 700; color: var(--color-on-secondary-container); background: var(--color-secondary-container); border-radius: 8px; padding: 2px 8px; }
.esg-policy-card__level { font-size: 13px; font-weight: 600; color: var(--color-on-surface); margin: 0; }
.esg-policy-card__desc { font-size: 14px; color: var(--color-on-surface-variant); margin: 0; line-height: 1.5; }
.esg-policy-card__tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: auto; }
.esg-policy-card__tag { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .02em; color: var(--color-on-primary-fixed-variant, var(--color-primary)); background: var(--color-surface-container-high); border-radius: 8px; padding: 3px 10px; }

/* Framework list */
.esg-framework__head { padding-bottom: 12px; border-bottom: 1px solid var(--color-outline-variant); margin-bottom: 4px; }
.esg-framework__title { color: var(--color-primary); margin: 0; }
.esg-framework__item { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 14px 0; border-bottom: 1px solid var(--color-outline-variant); }
.esg-framework__item:last-child { border-bottom: none; }
.esg-framework__item-name { font-size: 15px; font-weight: 700; color: var(--color-on-surface); margin: 0 0 2px; }
.esg-framework__item-sub { font-size: 13px; color: var(--color-on-surface-variant); margin: 0; }
.esg-framework__item-type { font-size: 11px; font-weight: 600; color: var(--color-on-surface-variant); white-space: nowrap; }

/* Market */
.esg-market__head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.esg-market__title { color: var(--color-on-surface-variant); margin: 0; }
.esg-market__demo { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--color-on-secondary-container); background: var(--color-secondary-container); border-radius: 6px; padding: 2px 6px; }
.esg-market__price-row { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 12px; }
.esg-market__price-label { color: var(--color-on-surface-variant); margin: 0 0 2px; }
.esg-market__price { font-size: 28px; font-weight: 700; color: var(--color-primary); margin: 0; }
.esg-market__change { font-size: 14px; font-weight: 700; }
.esg-market__change--up { color: #2d6a4f; }
.esg-market__change--down { color: var(--color-error); }
.esg-market__spark { width: 100%; height: 40px; color: var(--color-primary); opacity: .5; margin-bottom: 12px; }
.esg-market__stats { display: flex; flex-direction: column; gap: 10px; padding-top: 12px; border-top: 1px solid var(--color-outline-variant); }
.esg-market__stat { display: flex; justify-content: space-between; font-size: 14px; }
.esg-market__stat-label { color: var(--color-on-surface-variant); }
.esg-market__stat-value { font-weight: 700; color: var(--color-on-surface); }

/* News + decoration + empty */
.esg-news__head { padding-bottom: 12px; border-bottom: 1px solid var(--color-outline-variant); margin-bottom: 12px; }
.esg-news__title { color: var(--color-on-surface-variant); margin: 0; }
.esg-decoration { height: 160px; border-radius: 12px; border: 1px solid var(--color-outline-variant); display: flex; flex-direction: column; justify-content: flex-end; gap: 2px; padding: 20px; background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-secondary) 100%); }
.esg-decoration__title { color: #fff; font-weight: 700; font-size: 15px; }
.esg-decoration__sub { color: rgba(255,255,255,.85); }
.esg-empty { font-size: 14px; color: var(--color-on-surface-variant); text-align: center; padding: 24px 0; margin: 0; }
.esg-coming { padding: 40px; }
```

- [ ] **Step 2: Vérification manuelle**

Run: `python manage.py runserver`, recharger `http://127.0.0.1:8000/esg-data/`.
Expected : la page est mise en page (2 colonnes), le sélecteur de thème est stylé, les cartes politiques et le bloc market sont propres et alignés sur la charte terracotta.

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/dashboard/css/style.css
git commit -m "feat(esg): styles de la page Données ESG"
```

---

## Task 10: Données carbone démo pour Acme

**Files:**
- Modify: `dashboard/management/commands/populate_acme.py`

- [ ] **Step 1: Importer `Carbon_emission`**

Dans `dashboard/management/commands/populate_acme.py`, ajouter `Carbon_emission` à l'import depuis `..models` (bloc lignes 5-7), par ordre alphabétique :

```python
    Asset, Carbon_emission, Commodity, Company, Company_Policy, Company_Revenue,
    ...
    Ownership, Policy_Level, Policy_Subcategory, Policy_Type, Production,
```

(Conserver les autres noms déjà présents dans l'import.)

- [ ] **Step 2: Ajouter les lignes de données**

Dans le même fichier, juste après le bloc qui crée les `Company_Policy` d'Acme (la boucle `for policy_level, date_str in [...]` se terminant vers la ligne 747), insérer :

```python
        # ── Émissions carbone (démo, tCO2e) ───────────────────────────────────
        carbon_rows = [
            (2018, 'Scope 1', 32000), (2018, 'Scope 2', 18000), (2018, 'Scope 3', 95000),
            (2019, 'Scope 1', 31000), (2019, 'Scope 2', 17500), (2019, 'Scope 3', 92000),
            (2020, 'Scope 1', 28000), (2020, 'Scope 2', 16000), (2020, 'Scope 3', 85000),
            (2021, 'Scope 1', 27000), (2021, 'Scope 2', 15500), (2021, 'Scope 3', 82000),
            (2022, 'Scope 1', 25000), (2022, 'Scope 2', 14000), (2022, 'Scope 3', 78000),
            (2023, 'Scope 1', 23500), (2023, 'Scope 2', 13000), (2023, 'Scope 3', 74000),
            (2024, 'Scope 1', 22000), (2024, 'Scope 2', 12000), (2024, 'Scope 3', 70000),
        ]
        for yr, scope, val in carbon_rows:
            Carbon_emission.objects.get_or_create(
                company=acme, year=yr, scope=scope,
                defaults={'carbon_emission': float(val)},
            )
```

- [ ] **Step 3: Exécuter et vérifier**

Run: `python manage.py populate_acme`
Then: `python manage.py shell -c "from dashboard.models import Carbon_emission, Company; c=Company.objects.get(name='Acme Corp'); print(Carbon_emission.objects.filter(company=c).count())"`
Expected: `21` (7 années × 3 scopes).

> Note : si le nom de l'entreprise diffère de « Acme Corp », adapter le filtre. La variable `acme` du script référence l'entreprise créée — la vérification utilise son nom réel.

- [ ] **Step 4: Vérification manuelle de bout en bout**

Run: `python manage.py runserver`, ouvrir `http://127.0.0.1:8000/esg-data/` connecté, sélectionner Acme Corp.
Expected : le graphique affiche une ligne historique décroissante 2018→2024 + une projection pointillée jusqu'à 2030 ; « Dernier total » ≈ 104,0 k tCO2e ; « Évolution » négative en vert ; 2 cartes politiques (scores les plus élevés) + la liste des 5 politiques.

- [ ] **Step 5: Commit**

```bash
git add dashboard/management/commands/populate_acme.py
git commit -m "feat(esg): données carbone démo pour Acme Corp"
```

---

## Task 11: Suite de tests complète

**Files:**
- (aucun nouveau fichier)

- [ ] **Step 1: Lancer toute la suite de l'app dashboard**

Run: `python manage.py test dashboard -v 1`
Expected: tous les tests passent (existants + nouveaux : `CarbonEmissionModelTests`, `EsgDataCarbonTests`, `EsgDataPoliciesTests`, `EsgDataPlaceholdersTests`, `EsgViewTests`).

- [ ] **Step 2: Corriger toute régression éventuelle**

Si un test échoue, lire le message, corriger la cause, relancer. Ne pas commettre tant que la suite n'est pas verte.

- [ ] **Step 3: Commit final éventuel**

S'il y a eu des corrections :

```bash
git add -A
git commit -m "test(esg): suite verte pour la page Données ESG"
```

---

## Notes de cohérence

- `escHtml` est défini dans `esg.js` (autonome) pour éviter toute dépendance à l'ordre de chargement des scripts.
- La clé `localStorage` `selected-company-id` est partagée avec les autres pages → la sélection d'entreprise persiste à la navigation.
- Le graphique n'utilise aucune dépendance externe (SVG natif), conformément au `CLAUDE.md`.
- Aucune fonctionnalité PostGIS ; compatible SQLite et PostgreSQL.
- Les blocs Market/News sont explicitement « démo »/vides — hors périmètre de câblage réel.
```