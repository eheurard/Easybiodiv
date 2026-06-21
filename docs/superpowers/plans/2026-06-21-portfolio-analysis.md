# Portfolio Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the "Portfolio analysis" page with a tabbed shell whose first tab (Création) lets a user create/edit a fund — name, size, currency, benchmark, and a weighted list of companies, each with an optional equity/bond detail popup — persisted to the database.

**Architecture:** Add `Portfolio` and `PortfolioHolding` models to the existing `dashboard` app. A single page view (`portfolio_analysis`) renders a JS-tabbed shell; the Création tab is fully built, the 5 other tabs are placeholders. Two JSON endpoints handle persistence: `portfolio_save` (POST, validated through Django forms) and `portfolio_detail` (GET, to rehydrate the form). Frontend is vanilla JS + a native `<dialog>` for the financial popup, matching the existing ESG/LEAP patterns.

**Tech Stack:** Django (existing), SQLite (dev), vanilla HTML/CSS/JS, Django `TestCase`.

## Global Constraints

- Python 3.11+, PEP 8, lines ≤ 100 characters.
- No frontend framework; vanilla HTML/CSS/JS only; scripts loaded with `defer`/at end of body via `{% block extra_js %}`.
- Code MUST work identically on SQLite and PostgreSQL — no JSONField, no Postgres-only types, no PostGIS in shared code.
- Forms validated via `forms.ModelForm`/`forms.Form` — never raw POST handling.
- URL namespacing: `dashboard:<name>`; reverse via namespaced names.
- Models carry `created_at`, `updated_at`, `created_by` (FK User); prefer `models.TextChoices`.
- One migration = one logical change; name it explicitly.
- CSRF active everywhere; JSON POST must send `X-CSRFToken`.
- All new views decorated `@login_required`.
- Tests: ≥1 nominal + ≥1 error case per model/view/form; run with `python manage.py test dashboard`.
- Activate the venv before running commands: `./venv/scripts/activate.ps1` (PowerShell).

---

### Task 1: Data models + migration

**Files:**
- Modify: `dashboard/models.py` (append after `Carbon_emission`, end of file)
- Modify: `dashboard/tests.py` (append a new test class at end)
- Create: `dashboard/migrations/0XXX_add_portfolio_models.py` (generated)

**Interfaces:**
- Produces:
  - `Portfolio(name, size, currency→Currency, benchmark→self|null, is_benchmark, created_at, updated_at, created_by)` with `related_name='holdings'` reverse from holdings and `related_name='benchmarked_by'` on `benchmark`.
  - `PortfolioHolding(portfolio→Portfolio, company→Company, amount, weight, instrument_type, maturity_date, coupon_rate, face_value)`; `PortfolioHolding.Instrument` TextChoices with values `'EQUITY'`/`'BOND'`; `unique_together = ('portfolio', 'company')`.

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/tests.py`:

```python
class PortfolioModelTests(TestCase):

    def setUp(self):
        from .models import Currency
        self.eur = Currency.objects.create(code='EUR', name='Euro', symbol='€')
        self.company = Company.objects.create(name='PortCorp')

    def test_create_portfolio_with_holding(self):
        from .models import Portfolio, PortfolioHolding
        pf = Portfolio.objects.create(name='Fonds A', size=1000.0, currency=self.eur)
        PortfolioHolding.objects.create(
            portfolio=pf, company=self.company, amount=500.0, weight=50.0,
        )
        self.assertEqual(pf.holdings.count(), 1)
        holding = pf.holdings.first()
        self.assertEqual(holding.instrument_type, 'EQUITY')
        self.assertIsNone(holding.maturity_date)

    def test_holding_unique_per_company(self):
        from django.db import IntegrityError, transaction
        from .models import Portfolio, PortfolioHolding
        pf = Portfolio.objects.create(name='Fonds B', size=0, currency=self.eur)
        PortfolioHolding.objects.create(portfolio=pf, company=self.company)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PortfolioHolding.objects.create(portfolio=pf, company=self.company)

    def test_benchmark_self_reference(self):
        from .models import Portfolio
        bench = Portfolio.objects.create(
            name='Indice', size=0, currency=self.eur, is_benchmark=True,
        )
        pf = Portfolio.objects.create(
            name='Fonds C', size=0, currency=self.eur, benchmark=bench,
        )
        self.assertEqual(pf.benchmark, bench)
        self.assertIn(pf, bench.benchmarked_by.all())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test dashboard.tests.PortfolioModelTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'Portfolio'`.

- [ ] **Step 3: Add the models**

Append to the end of `dashboard/models.py`:

```python
class Portfolio(models.Model):
    name = models.CharField(max_length=255)
    size = models.FloatField(default=0)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    benchmark = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='benchmarked_by',
    )
    is_benchmark = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )

    def __str__(self):
        return self.name


class PortfolioHolding(models.Model):
    class Instrument(models.TextChoices):
        EQUITY = 'EQUITY', 'Action (Equity)'
        BOND = 'BOND', 'Obligation (Bond)'

    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name='holdings',
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    amount = models.FloatField(default=0)
    weight = models.FloatField(default=0)
    instrument_type = models.CharField(
        max_length=10, choices=Instrument.choices, default=Instrument.EQUITY,
    )
    maturity_date = models.DateField(null=True, blank=True)
    coupon_rate = models.FloatField(null=True, blank=True)
    face_value = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ('portfolio', 'company')

    def __str__(self):
        return f"{self.portfolio.name} — {self.company.name}"
```

- [ ] **Step 4: Generate the migration**

Run: `python manage.py makemigrations dashboard --name add_portfolio_models`
Expected: creates `dashboard/migrations/0XXX_add_portfolio_models.py` adding `Portfolio` and `PortfolioHolding`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.PortfolioModelTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add dashboard/models.py dashboard/migrations/ dashboard/tests.py
git commit -m "feat(portfolio): modeles Portfolio et PortfolioHolding"
```

---

### Task 2: Validation forms

**Files:**
- Create: `dashboard/forms.py`
- Modify: `dashboard/tests.py` (append test class)

**Interfaces:**
- Consumes: `Portfolio`, `PortfolioHolding` from Task 1.
- Produces:
  - `PortfolioForm(forms.ModelForm)` — `Meta.model = Portfolio`, `fields = ['name', 'size', 'currency', 'benchmark']`. (Note: `is_benchmark` and `created_by` are handled in the view, not the form, to avoid checkbox/JSON quirks.)
  - `PortfolioHoldingForm(forms.ModelForm)` — `Meta.model = PortfolioHolding`, `fields = ['company', 'amount', 'weight', 'instrument_type', 'maturity_date', 'coupon_rate', 'face_value']`; `clean_weight` rejects values outside `0..100`.

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/tests.py`:

```python
class PortfolioFormTests(TestCase):

    def setUp(self):
        from .models import Currency
        self.eur = Currency.objects.create(code='EUR', name='Euro', symbol='€')
        self.company = Company.objects.create(name='FormCorp')

    def test_portfolio_form_valid(self):
        from .forms import PortfolioForm
        form = PortfolioForm({
            'name': 'Fonds', 'size': 1000, 'currency': self.eur.pk, 'benchmark': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_portfolio_form_requires_currency(self):
        from .forms import PortfolioForm
        form = PortfolioForm({'name': 'Fonds', 'size': 1000})
        self.assertFalse(form.is_valid())
        self.assertIn('currency', form.errors)

    def test_holding_form_valid(self):
        from .forms import PortfolioHoldingForm
        form = PortfolioHoldingForm({
            'company': self.company.pk, 'amount': 500, 'weight': 50,
            'instrument_type': 'EQUITY',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_holding_form_rejects_weight_over_100(self):
        from .forms import PortfolioHoldingForm
        form = PortfolioHoldingForm({
            'company': self.company.pk, 'amount': 0, 'weight': 150,
            'instrument_type': 'EQUITY',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('weight', form.errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test dashboard.tests.PortfolioFormTests -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.forms'`.

- [ ] **Step 3: Create the forms**

Create `dashboard/forms.py`:

```python
from django import forms

from .models import Portfolio, PortfolioHolding


class PortfolioForm(forms.ModelForm):
    class Meta:
        model = Portfolio
        fields = ['name', 'size', 'currency', 'benchmark']


class PortfolioHoldingForm(forms.ModelForm):
    class Meta:
        model = PortfolioHolding
        fields = [
            'company', 'amount', 'weight', 'instrument_type',
            'maturity_date', 'coupon_rate', 'face_value',
        ]

    def clean_weight(self):
        weight = self.cleaned_data['weight']
        if weight < 0 or weight > 100:
            raise forms.ValidationError('Le poids doit être compris entre 0 et 100.')
        return weight
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.PortfolioFormTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/forms.py dashboard/tests.py
git commit -m "feat(portfolio): formulaires de validation Portfolio/Holding"
```

---

### Task 3: `portfolio_save` view (POST JSON)

**Files:**
- Modify: `dashboard/views.py` (imports near top; new view appended at end)
- Modify: `dashboard/urls.py` (new path)
- Modify: `dashboard/tests.py` (append test class)

**Interfaces:**
- Consumes: `PortfolioForm`, `PortfolioHoldingForm` (Task 2); `Portfolio`, `PortfolioHolding` (Task 1).
- Produces: URL name `dashboard:portfolio_save` at `api/portfolio/save/`. Accepts POST JSON
  `{id?, name, size, currency_id, benchmark_id, is_benchmark, holdings:[{company_id, amount, weight, instrument_type, maturity_date, coupon_rate, face_value}]}`.
  Returns `{id, name}` (200) on success, or `{errors, holdings}` (400) on validation failure.

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/tests.py`:

```python
class PortfolioSaveViewTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        from .models import Currency
        User = get_user_model()
        self.user = User.objects.create_user(username='saver', password='pass')
        self.client.force_login(self.user)
        self.eur = Currency.objects.create(code='EUR', name='Euro', symbol='€')
        self.company = Company.objects.create(name='SaveCorp')
        self.url = reverse('dashboard:portfolio_save')

    def _payload(self, **over):
        data = {
            'name': 'Fonds', 'size': 1000, 'currency_id': self.eur.pk,
            'benchmark_id': None, 'is_benchmark': False,
            'holdings': [{
                'company_id': self.company.pk, 'amount': 500, 'weight': 50,
                'instrument_type': 'EQUITY', 'maturity_date': None,
                'coupon_rate': None, 'face_value': None,
            }],
        }
        data.update(over)
        return data

    def test_save_creates_portfolio_and_holdings(self):
        from .models import Portfolio
        response = self.client.post(
            self.url, data=json.dumps(self._payload()),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        pf = Portfolio.objects.get(name='Fonds')
        self.assertEqual(pf.created_by, self.user)
        self.assertEqual(pf.holdings.count(), 1)

    def test_save_with_bond_fields(self):
        from .models import Portfolio
        payload = self._payload(holdings=[{
            'company_id': self.company.pk, 'amount': 500, 'weight': 50,
            'instrument_type': 'BOND', 'maturity_date': '2030-01-01',
            'coupon_rate': 3.5, 'face_value': 1000,
        }])
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        holding = Portfolio.objects.get(name='Fonds').holdings.first()
        self.assertEqual(holding.instrument_type, 'BOND')
        self.assertAlmostEqual(holding.coupon_rate, 3.5, places=2)

    def test_save_updates_existing_portfolio(self):
        from .models import Portfolio
        first = self.client.post(
            self.url, data=json.dumps(self._payload()),
            content_type='application/json',
        )
        pid = json.loads(first.content)['id']
        self.client.post(
            self.url,
            data=json.dumps(self._payload(id=pid, name='Renommé', holdings=[])),
            content_type='application/json',
        )
        pf = Portfolio.objects.get(pk=pid)
        self.assertEqual(pf.name, 'Renommé')
        self.assertEqual(pf.holdings.count(), 0)

    def test_save_invalid_missing_currency_returns_400(self):
        from .models import Portfolio
        response = self.client.post(
            self.url, data=json.dumps(self._payload(currency_id=None)),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('currency', json.loads(response.content)['errors'])
        self.assertEqual(Portfolio.objects.count(), 0)

    def test_save_duplicate_company_returns_400(self):
        from .models import Portfolio
        row = {
            'company_id': self.company.pk, 'amount': 0, 'weight': 0,
            'instrument_type': 'EQUITY', 'maturity_date': None,
            'coupon_rate': None, 'face_value': None,
        }
        response = self.client.post(
            self.url, data=json.dumps(self._payload(holdings=[row, row])),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Portfolio.objects.count(), 0)

    def test_save_requires_login(self):
        self.client.logout()
        response = self.client.post(
            self.url, data=json.dumps(self._payload()),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test dashboard.tests.PortfolioSaveViewTests -v 2`
Expected: FAIL — `NoReverseMatch: 'portfolio_save'`.

- [ ] **Step 3: Add imports and the view**

In `dashboard/views.py`, update the `django.views.decorators.http` import line to include `require_POST`:

```python
from django.views.decorators.http import require_GET, require_POST
```

Add `Portfolio, PortfolioHolding` to the existing `from .models import (...)` block, and add this import after the models import:

```python
from django.db import transaction
from .forms import PortfolioForm, PortfolioHoldingForm
```

Append at the end of `dashboard/views.py`:

```python
@login_required
@require_POST
def portfolio_save(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'errors': {'__all__': ['JSON invalide']}}, status=400)

    instance = None
    if payload.get('id'):
        instance = get_object_or_404(Portfolio, pk=payload['id'])

    form = PortfolioForm({
        'name': payload.get('name', ''),
        'size': payload.get('size'),
        'currency': payload.get('currency_id'),
        'benchmark': payload.get('benchmark_id'),
    }, instance=instance)

    rows = payload.get('holdings', [])
    holding_forms = []
    holding_errors = []
    seen_companies = set()
    duplicate = False
    for row in rows:
        company_id = row.get('company_id')
        if company_id in seen_companies:
            duplicate = True
        seen_companies.add(company_id)
        hf = PortfolioHoldingForm({
            'company': company_id,
            'amount': row.get('amount') or 0,
            'weight': row.get('weight') or 0,
            'instrument_type': row.get('instrument_type') or 'EQUITY',
            'maturity_date': row.get('maturity_date') or None,
            'coupon_rate': row.get('coupon_rate'),
            'face_value': row.get('face_value'),
        })
        holding_forms.append(hf)
        holding_errors.append({} if hf.is_valid() else hf.errors)

    if not form.is_valid() or any(holding_errors) or duplicate:
        errors = dict(form.errors)
        if duplicate:
            errors['__all__'] = ['Une entreprise ne peut apparaître qu\'une fois.']
        return JsonResponse({'errors': errors, 'holdings': holding_errors}, status=400)

    with transaction.atomic():
        portfolio = form.save(commit=False)
        portfolio.is_benchmark = bool(payload.get('is_benchmark'))
        if portfolio.created_by_id is None:
            portfolio.created_by = request.user
        portfolio.save()
        portfolio.holdings.all().delete()
        for hf in holding_forms:
            holding = hf.save(commit=False)
            holding.portfolio = portfolio
            holding.save()

    return JsonResponse({'id': portfolio.pk, 'name': portfolio.name})
```

In `dashboard/urls.py`, add inside `urlpatterns`:

```python
    path('api/portfolio/save/', views.portfolio_save, name='portfolio_save'),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.PortfolioSaveViewTests -v 2`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/views.py dashboard/urls.py dashboard/tests.py
git commit -m "feat(portfolio): endpoint POST portfolio_save"
```

---

### Task 4: `portfolio_detail` view (GET JSON)

**Files:**
- Modify: `dashboard/views.py` (new view appended at end)
- Modify: `dashboard/urls.py` (new path)
- Modify: `dashboard/tests.py` (append test class)

**Interfaces:**
- Consumes: `Portfolio` (Task 1).
- Produces: URL name `dashboard:portfolio_detail` at `api/portfolio/<int:pk>/`. GET returns
  `{id, name, size, currency_id, benchmark_id, is_benchmark, holdings:[{company_id, company_name, amount, weight, instrument_type, maturity_date, coupon_rate, face_value}]}`; 404 if missing.

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/tests.py`:

```python
class PortfolioDetailViewTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        from .models import Currency, Portfolio, PortfolioHolding
        User = get_user_model()
        self.user = User.objects.create_user(username='detailer', password='pass')
        self.client.force_login(self.user)
        eur = Currency.objects.create(code='EUR', name='Euro', symbol='€')
        self.company = Company.objects.create(name='DetailCorp')
        self.pf = Portfolio.objects.create(name='Fonds D', size=2000, currency=eur)
        PortfolioHolding.objects.create(
            portfolio=self.pf, company=self.company, amount=1000, weight=50,
            instrument_type='BOND', coupon_rate=2.0,
        )

    def test_detail_returns_portfolio_json(self):
        url = reverse('dashboard:portfolio_detail', kwargs={'pk': self.pf.pk})
        data = json.loads(self.client.get(url).content)
        self.assertEqual(data['name'], 'Fonds D')
        self.assertEqual(len(data['holdings']), 1)
        h = data['holdings'][0]
        self.assertEqual(h['company_id'], self.company.pk)
        self.assertEqual(h['company_name'], 'DetailCorp')
        self.assertEqual(h['instrument_type'], 'BOND')

    def test_detail_404_when_missing(self):
        url = reverse('dashboard:portfolio_detail', kwargs={'pk': 99999})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_detail_post_not_allowed(self):
        url = reverse('dashboard:portfolio_detail', kwargs={'pk': self.pf.pk})
        self.assertEqual(self.client.post(url).status_code, 405)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test dashboard.tests.PortfolioDetailViewTests -v 2`
Expected: FAIL — `NoReverseMatch: 'portfolio_detail'`.

- [ ] **Step 3: Add the view and URL**

Append at the end of `dashboard/views.py`:

```python
@login_required
@require_GET
def portfolio_detail(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk)
    holdings = [{
        'company_id': h.company_id,
        'company_name': h.company.name,
        'amount': h.amount,
        'weight': h.weight,
        'instrument_type': h.instrument_type,
        'maturity_date': h.maturity_date.isoformat() if h.maturity_date else None,
        'coupon_rate': h.coupon_rate,
        'face_value': h.face_value,
    } for h in portfolio.holdings.select_related('company').all()]
    return JsonResponse({
        'id': portfolio.pk,
        'name': portfolio.name,
        'size': portfolio.size,
        'currency_id': portfolio.currency_id,
        'benchmark_id': portfolio.benchmark_id,
        'is_benchmark': portfolio.is_benchmark,
        'holdings': holdings,
    })
```

In `dashboard/urls.py`, add inside `urlpatterns`:

```python
    path('api/portfolio/<int:pk>/', views.portfolio_detail, name='portfolio_detail'),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.PortfolioDetailViewTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/views.py dashboard/urls.py dashboard/tests.py
git commit -m "feat(portfolio): endpoint GET portfolio_detail"
```

---

### Task 5: `portfolio_analysis` page view + context

**Files:**
- Modify: `dashboard/views.py` (new view appended at end)
- Modify: `dashboard/urls.py` (new path)
- Modify: `dashboard/tests.py` (append test class)

**Interfaces:**
- Consumes: `Company`, `Currency`, `Portfolio` (Task 1).
- Produces: URL name `dashboard:portfolio_analysis` at `portfolio/`. Renders
  `dashboard/portfolio.html` with context keys: `companies` (`[{id,name,isin,ticker}]`),
  `currencies` (`[{id,code,symbol}]`), `benchmarks` (`[{id,name}]`, only `is_benchmark=True`),
  `portfolios` (`[{id,name}]`, the current user's).

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/tests.py`:

```python
class PortfolioAnalysisPageTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        from .models import Currency, Portfolio
        User = get_user_model()
        self.user = User.objects.create_user(username='pageportf', password='pass')
        self.client.force_login(self.user)
        self.eur = Currency.objects.create(code='EUR', name='Euro', symbol='€')
        Company.objects.create(name='PageCorp')
        Portfolio.objects.create(
            name='Bench', size=0, currency=self.eur, is_benchmark=True,
        )

    def test_page_returns_200(self):
        response = self.client.get(reverse('dashboard:portfolio_analysis'))
        self.assertEqual(response.status_code, 200)

    def test_page_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:portfolio_analysis'))
        self.assertTemplateUsed(response, 'dashboard/portfolio.html')

    def test_context_has_companies_currencies_benchmarks(self):
        response = self.client.get(reverse('dashboard:portfolio_analysis'))
        self.assertEqual(len(response.context['companies']), 1)
        self.assertEqual(len(response.context['currencies']), 1)
        self.assertEqual(len(response.context['benchmarks']), 1)
        self.assertEqual(response.context['benchmarks'][0]['name'], 'Bench')

    def test_page_redirects_anonymous(self):
        self.client.logout()
        response = self.client.get(reverse('dashboard:portfolio_analysis'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test dashboard.tests.PortfolioAnalysisPageTests -v 2`
Expected: FAIL — `NoReverseMatch: 'portfolio_analysis'`.

- [ ] **Step 3: Add the view and URL**

Add `Currency` to the existing `from .models import (...)` block in `dashboard/views.py` if not already present. Append at the end of `dashboard/views.py`:

```python
@login_required
@require_GET
def portfolio_analysis(request):
    companies = list(Company.objects.order_by('name').values(
        'id', 'name', 'isin', 'ticker',
    ))
    currencies = list(Currency.objects.order_by('code').values('id', 'code', 'symbol'))
    benchmarks = list(
        Portfolio.objects.filter(is_benchmark=True).order_by('name').values('id', 'name')
    )
    portfolios = list(
        Portfolio.objects.filter(created_by=request.user).order_by('name')
        .values('id', 'name')
    )
    return render(request, 'dashboard/portfolio.html', {
        'companies': companies,
        'currencies': currencies,
        'benchmarks': benchmarks,
        'portfolios': portfolios,
    })
```

In `dashboard/urls.py`, add inside `urlpatterns`:

```python
    path('portfolio/', views.portfolio_analysis, name='portfolio_analysis'),
```

- [ ] **Step 4: Create a minimal template so the view renders**

Create `dashboard/templates/dashboard/portfolio.html` (placeholder; fleshed out in Task 6):

```django
{% extends "base.html" %}
{% load static %}
{% block title %}Portfolio analysis — Easybiodiv{% endblock %}
{% block content %}<div class="portfolio-page"></div>{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.PortfolioAnalysisPageTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add dashboard/views.py dashboard/urls.py dashboard/templates/dashboard/portfolio.html dashboard/tests.py
git commit -m "feat(portfolio): vue page portfolio_analysis + coquille template"
```

---

### Task 6: Tabbed shell + Création tab template + financial dialog

**Files:**
- Modify: `dashboard/templates/dashboard/portfolio.html` (replace full content)
- Modify: `dashboard/tests.py` (append test class)

**Interfaces:**
- Consumes: context from Task 5; URL names `dashboard:portfolio_save`, `dashboard:portfolio_detail`.
- Produces: DOM contract used by Task 7 JS — element IDs:
  `pf-tabs`, `pf-portfolio-select`, `pf-new-btn`, `pf-name`, `pf-size`, `pf-currency`,
  `pf-benchmark`, `pf-is-benchmark`, `pf-company-search`, `pf-company-listbox`,
  `pf-holdings-body`, `pf-weight-total`, `pf-amount-total`, `pf-save-btn`, `pf-status`,
  `pf-dialog`, `pf-dlg-instrument`, `pf-dlg-bond-fields`, `pf-dlg-maturity`,
  `pf-dlg-coupon`, `pf-dlg-facevalue`, `pf-dlg-validate`, `pf-dlg-cancel`;
  data scripts `pf-companies`, `pf-currencies`, `pf-benchmarks`, `pf-portfolios`;
  globals `PF_SAVE_URL`, `PF_DETAIL_URL`.

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/tests.py`:

```python
class PortfolioTemplateContentTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='tplportf', password='pass')
        self.client.force_login(self.user)

    def test_page_has_tabs_and_form_elements(self):
        response = self.client.get(reverse('dashboard:portfolio_analysis'))
        for needle in [
            'id="pf-tabs"', 'data-tab="creation"', 'data-tab="impact"',
            'data-tab="risque-physique"', 'data-tab="risque-transition"',
            'data-tab="risque-composite"', 'data-tab="scenario"',
            'id="pf-name"', 'id="pf-currency"', 'id="pf-benchmark"',
            'id="pf-holdings-body"', 'id="pf-save-btn"', 'id="pf-dialog"',
        ]:
            self.assertContains(response, needle)

    def test_page_loads_portfolio_js_and_urls(self):
        response = self.client.get(reverse('dashboard:portfolio_analysis'))
        self.assertContains(response, 'js/portfolio.js')
        self.assertContains(response, 'PF_SAVE_URL')
        self.assertContains(response, 'PF_DETAIL_URL')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test dashboard.tests.PortfolioTemplateContentTests -v 2`
Expected: FAIL — page lacks `id="pf-tabs"` etc.

- [ ] **Step 3: Write the full template**

Replace the entire content of `dashboard/templates/dashboard/portfolio.html` with:

```django
{% extends "base.html" %}
{% load static %}

{% block title %}Portfolio analysis — Easybiodiv{% endblock %}

{% block nav_portfolio %}active{% endblock %}

{% block header_left %}
<div class="pf-portfolio-picker">
  <span class="label-caps">Portefeuille</span>
  <select id="pf-portfolio-select" class="form-input" aria-label="Charger un portefeuille">
    <option value="">— Nouveau —</option>
    {% for p in portfolios %}
      <option value="{{ p.id }}">{{ p.name }}</option>
    {% endfor %}
  </select>
  <button type="button" id="pf-new-btn" class="btn btn--ghost">Nouveau portefeuille</button>
</div>
{% endblock header_left %}

{% block content %}
<div class="portfolio-page">

  <div class="pf-tabs" id="pf-tabs" role="tablist" aria-label="Analyse de portefeuille">
    <button class="pf-tab pf-tab--active" data-tab="creation" role="tab" aria-selected="true">Création</button>
    <button class="pf-tab" data-tab="impact" role="tab" aria-selected="false">Impact</button>
    <button class="pf-tab" data-tab="risque-physique" role="tab" aria-selected="false">Risque physique</button>
    <button class="pf-tab" data-tab="risque-transition" role="tab" aria-selected="false">Risque de transition</button>
    <button class="pf-tab" data-tab="risque-composite" role="tab" aria-selected="false">Risque composite</button>
    <button class="pf-tab" data-tab="scenario" role="tab" aria-selected="false">Scénario</button>
  </div>

  <!-- ── Création ─────────────────────────────────────────────────── -->
  <div class="pf-panel pf-panel--active" data-tab-panel="creation">

    <section class="card pf-settings">
      <h3 class="pf-section-title label-caps">Paramètres du fonds</h3>
      <div class="pf-settings__grid">
        <label class="pf-field">
          <span class="label-caps">Nom du fonds</span>
          <input type="text" id="pf-name" class="form-input" placeholder="Mon fonds">
        </label>
        <label class="pf-field">
          <span class="label-caps">Taille du fonds</span>
          <input type="number" id="pf-size" class="form-input" min="0" step="any" value="0">
        </label>
        <label class="pf-field">
          <span class="label-caps">Devise</span>
          <select id="pf-currency" class="form-input"></select>
        </label>
        <label class="pf-field">
          <span class="label-caps">Benchmark</span>
          <select id="pf-benchmark" class="form-input">
            <option value="">Aucun</option>
          </select>
        </label>
        <label class="pf-field pf-field--check">
          <input type="checkbox" id="pf-is-benchmark">
          <span>Utiliser ce fonds comme benchmark</span>
        </label>
      </div>
    </section>

    <section class="card pf-composition">
      <h3 class="pf-section-title label-caps">Composition</h3>

      <div class="pf-add">
        <input type="text" id="pf-company-search" class="form-input"
               placeholder="Rechercher une entreprise à ajouter…"
               autocomplete="off" aria-controls="pf-company-listbox">
        <ul id="pf-company-listbox" class="pf-company-listbox" role="listbox" hidden></ul>
      </div>

      <table class="pf-holdings">
        <thead>
          <tr>
            <th>Entreprise</th>
            <th>Montant</th>
            <th>Poids (%)</th>
            <th>Détails</th>
            <th><span class="visually-hidden">Supprimer</span></th>
          </tr>
        </thead>
        <tbody id="pf-holdings-body"></tbody>
        <tfoot>
          <tr>
            <td class="label-caps">Total</td>
            <td id="pf-amount-total">0</td>
            <td id="pf-weight-total">0 %</td>
            <td colspan="2"></td>
          </tr>
        </tfoot>
      </table>

      <p class="pf-empty" id="pf-empty">Aucune entreprise ajoutée.</p>

      <div class="pf-actions">
        <span id="pf-status" class="pf-status" role="status" aria-live="polite"></span>
        <button type="button" id="pf-save-btn" class="btn btn--primary">Enregistrer le portefeuille</button>
      </div>
    </section>

  </div>

  <!-- ── Onglets à venir ──────────────────────────────────────────── -->
  <div class="pf-panel" data-tab-panel="impact" hidden>
    <div class="card esg-coming"><p class="esg-empty">Impact — à venir, aucune donnée disponible.</p></div>
  </div>
  <div class="pf-panel" data-tab-panel="risque-physique" hidden>
    <div class="card esg-coming"><p class="esg-empty">Risque physique — à venir, aucune donnée disponible.</p></div>
  </div>
  <div class="pf-panel" data-tab-panel="risque-transition" hidden>
    <div class="card esg-coming"><p class="esg-empty">Risque de transition — à venir, aucune donnée disponible.</p></div>
  </div>
  <div class="pf-panel" data-tab-panel="risque-composite" hidden>
    <div class="card esg-coming"><p class="esg-empty">Risque composite — à venir, aucune donnée disponible.</p></div>
  </div>
  <div class="pf-panel" data-tab-panel="scenario" hidden>
    <div class="card esg-coming"><p class="esg-empty">Scénario — à venir, aucune donnée disponible.</p></div>
  </div>

</div>

<!-- ── Pop-up financière ──────────────────────────────────────────── -->
<dialog id="pf-dialog" class="pf-dialog">
  <form method="dialog" class="pf-dialog__form">
    <h3 class="pf-dialog__title" id="pf-dialog-company">Détails financiers</h3>

    <label class="pf-field">
      <span class="label-caps">Type d'instrument</span>
      <select id="pf-dlg-instrument" class="form-input">
        <option value="EQUITY">Action (Equity)</option>
        <option value="BOND">Obligation (Bond)</option>
      </select>
    </label>

    <div id="pf-dlg-bond-fields" class="pf-dialog__bond" hidden>
      <label class="pf-field">
        <span class="label-caps">Maturité</span>
        <input type="date" id="pf-dlg-maturity" class="form-input">
      </label>
      <label class="pf-field">
        <span class="label-caps">Taux de coupon (%)</span>
        <input type="number" id="pf-dlg-coupon" class="form-input" step="any" min="0">
      </label>
      <label class="pf-field">
        <span class="label-caps">Valeur nominale</span>
        <input type="number" id="pf-dlg-facevalue" class="form-input" step="any" min="0">
      </label>
    </div>

    <div class="pf-dialog__actions">
      <button type="button" id="pf-dlg-cancel" class="btn btn--ghost">Annuler</button>
      <button type="button" id="pf-dlg-validate" class="btn btn--primary">Valider</button>
    </div>
  </form>
</dialog>
{% endblock %}

{% block extra_js %}
{{ companies|json_script:"pf-companies" }}
{{ currencies|json_script:"pf-currencies" }}
{{ benchmarks|json_script:"pf-benchmarks" }}
{{ portfolios|json_script:"pf-portfolios" }}
<script>
  var PF_SAVE_URL = "{% url 'dashboard:portfolio_save' %}";
  var PF_DETAIL_URL = "{% url 'dashboard:portfolio_detail' pk=0 %}";
</script>
<script src="{% static 'dashboard/js/portfolio.js' %}" defer></script>
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.PortfolioTemplateContentTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/templates/dashboard/portfolio.html dashboard/tests.py
git commit -m "feat(portfolio): coquille a onglets + onglet Creation + dialog"
```

---

### Task 7: Frontend logic (`portfolio.js`)

**Files:**
- Create: `dashboard/static/dashboard/js/portfolio.js`

**Interfaces:**
- Consumes: DOM contract + data scripts + `PF_SAVE_URL`/`PF_DETAIL_URL` from Task 6.
- Produces: no exports (IIFE). Behaviors: tab switching; company search/add; amount⟷weight
  sync; totals; per-row gear opening the dialog; conditional bond fields; save via fetch
  with `X-CSRFToken`; load existing portfolio via `PF_DETAIL_URL`.

This task has no unit test (vanilla DOM logic, consistent with the existing `*.js` files which are not unit-tested). It is verified manually in Step 3.

- [ ] **Step 1: Write `portfolio.js`**

Create `dashboard/static/dashboard/js/portfolio.js`:

```javascript
(function () {
  'use strict';

  function readJSON(id) {
    var el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : [];
  }

  function getCookie(name) {
    var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? match.pop() : '';
  }

  var COMPANIES = readJSON('pf-companies');
  var CURRENCIES = readJSON('pf-currencies');
  var BENCHMARKS = readJSON('pf-benchmarks');

  // rows: {companyId, companyName, amount, weight, instrument, maturity, coupon, faceValue}
  var rows = [];
  var currentId = null;
  var dialogRowIndex = null;

  var $ = function (id) { return document.getElementById(id); };

  // ── Tabs ────────────────────────────────────────────────────────
  function initTabs() {
    var tabs = document.querySelectorAll('.pf-tab');
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var name = tab.dataset.tab;
        tabs.forEach(function (t) {
          var active = t === tab;
          t.classList.toggle('pf-tab--active', active);
          t.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        document.querySelectorAll('.pf-panel').forEach(function (panel) {
          var active = panel.dataset.tabPanel === name;
          panel.classList.toggle('pf-panel--active', active);
          panel.hidden = !active;
        });
      });
    });
  }

  // ── Select population ────────────────────────────────────────────
  function populateSelects() {
    var cur = $('pf-currency');
    CURRENCIES.forEach(function (c) {
      var o = document.createElement('option');
      o.value = c.id;
      o.textContent = c.code + (c.symbol ? ' (' + c.symbol + ')' : '');
      cur.appendChild(o);
    });
    var bench = $('pf-benchmark');
    BENCHMARKS.forEach(function (b) {
      var o = document.createElement('option');
      o.value = b.id;
      o.textContent = b.name;
      bench.appendChild(o);
    });
  }

  // ── Company search ───────────────────────────────────────────────
  function initCompanySearch() {
    var input = $('pf-company-search');
    var listbox = $('pf-company-listbox');

    function close() { listbox.hidden = true; listbox.innerHTML = ''; }

    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase();
      listbox.innerHTML = '';
      if (!q) { close(); return; }
      var taken = rows.map(function (r) { return r.companyId; });
      var matches = COMPANIES.filter(function (c) {
        return c.name.toLowerCase().indexOf(q) !== -1 && taken.indexOf(c.id) === -1;
      }).slice(0, 8);
      if (!matches.length) { close(); return; }
      matches.forEach(function (c) {
        var li = document.createElement('li');
        li.className = 'pf-company-option';
        li.setAttribute('role', 'option');
        li.textContent = c.name;
        li.addEventListener('click', function () {
          addRow(c.id, c.name);
          input.value = '';
          close();
        });
        listbox.appendChild(li);
      });
      listbox.hidden = false;
    });

    document.addEventListener('click', function (e) {
      if (!input.contains(e.target) && !listbox.contains(e.target)) { close(); }
    });
  }

  // ── Rows ─────────────────────────────────────────────────────────
  function addRow(companyId, companyName, data) {
    data = data || {};
    rows.push({
      companyId: companyId,
      companyName: companyName,
      amount: data.amount || 0,
      weight: data.weight || 0,
      instrument: data.instrument || 'EQUITY',
      maturity: data.maturity || null,
      coupon: (data.coupon === undefined ? null : data.coupon),
      faceValue: (data.faceValue === undefined ? null : data.faceValue),
    });
    render();
  }

  function removeRow(i) { rows.splice(i, 1); render(); }

  function size() { return parseFloat($('pf-size').value) || 0; }

  function render() {
    var body = $('pf-holdings-body');
    body.innerHTML = '';
    rows.forEach(function (r, i) {
      var tr = document.createElement('tr');

      var tdName = document.createElement('td');
      tdName.textContent = r.companyName;
      tr.appendChild(tdName);

      var tdAmount = document.createElement('td');
      var amountInput = document.createElement('input');
      amountInput.type = 'number';
      amountInput.className = 'form-input pf-amount';
      amountInput.min = '0';
      amountInput.step = 'any';
      amountInput.value = r.amount;
      amountInput.addEventListener('input', function () {
        r.amount = parseFloat(amountInput.value) || 0;
        var s = size();
        r.weight = s > 0 ? (r.amount / s) * 100 : 0;
        updateRowWeight(i);
        updateTotals();
      });
      tdAmount.appendChild(amountInput);
      tr.appendChild(tdAmount);

      var tdWeight = document.createElement('td');
      var weightInput = document.createElement('input');
      weightInput.type = 'number';
      weightInput.className = 'form-input pf-weight';
      weightInput.min = '0';
      weightInput.max = '100';
      weightInput.step = 'any';
      weightInput.value = r.weight;
      weightInput.dataset.row = i;
      weightInput.addEventListener('input', function () {
        r.weight = parseFloat(weightInput.value) || 0;
        r.amount = (r.weight / 100) * size();
        amountInput.value = r.amount;
        updateTotals();
      });
      tdWeight.appendChild(weightInput);
      tr.appendChild(tdWeight);

      var tdGear = document.createElement('td');
      var gear = document.createElement('button');
      gear.type = 'button';
      gear.className = 'pf-gear';
      gear.title = 'Détails financiers';
      gear.textContent = '⚙';
      if (r.instrument === 'BOND') { gear.classList.add('pf-gear--filled'); }
      gear.addEventListener('click', function () { openDialog(i); });
      tdGear.appendChild(gear);
      tr.appendChild(tdGear);

      var tdDel = document.createElement('td');
      var del = document.createElement('button');
      del.type = 'button';
      del.className = 'pf-del';
      del.title = 'Supprimer';
      del.textContent = '🗑';
      del.addEventListener('click', function () { removeRow(i); });
      tdDel.appendChild(del);
      tr.appendChild(tdDel);

      body.appendChild(tr);
    });
    $('pf-empty').hidden = rows.length > 0;
    updateTotals();
  }

  function updateRowWeight(i) {
    var input = document.querySelector('.pf-weight[data-row="' + i + '"]');
    if (input) { input.value = rows[i].weight; }
  }

  function updateTotals() {
    var amountTotal = rows.reduce(function (s, r) { return s + (r.amount || 0); }, 0);
    var weightTotal = rows.reduce(function (s, r) { return s + (r.weight || 0); }, 0);
    $('pf-amount-total').textContent = Math.round(amountTotal * 100) / 100;
    var wEl = $('pf-weight-total');
    wEl.textContent = (Math.round(weightTotal * 10) / 10) + ' %';
    wEl.classList.toggle('pf-total--ok', Math.abs(weightTotal - 100) < 0.5);
    wEl.classList.toggle('pf-total--warn', Math.abs(weightTotal - 100) >= 0.5);
  }

  // ── Dialog ───────────────────────────────────────────────────────
  function initDialog() {
    var dlg = $('pf-dialog');
    var instrument = $('pf-dlg-instrument');
    instrument.addEventListener('change', function () {
      $('pf-dlg-bond-fields').hidden = instrument.value !== 'BOND';
    });
    $('pf-dlg-cancel').addEventListener('click', function () { dlg.close(); });
    $('pf-dlg-validate').addEventListener('click', function () {
      var r = rows[dialogRowIndex];
      r.instrument = instrument.value;
      if (r.instrument === 'BOND') {
        r.maturity = $('pf-dlg-maturity').value || null;
        r.coupon = $('pf-dlg-coupon').value === '' ? null : parseFloat($('pf-dlg-coupon').value);
        r.faceValue = $('pf-dlg-facevalue').value === '' ? null : parseFloat($('pf-dlg-facevalue').value);
      } else {
        r.maturity = null; r.coupon = null; r.faceValue = null;
      }
      dlg.close();
      render();
    });
  }

  function openDialog(i) {
    dialogRowIndex = i;
    var r = rows[i];
    $('pf-dialog-company').textContent = 'Détails — ' + r.companyName;
    $('pf-dlg-instrument').value = r.instrument;
    $('pf-dlg-bond-fields').hidden = r.instrument !== 'BOND';
    $('pf-dlg-maturity').value = r.maturity || '';
    $('pf-dlg-coupon').value = (r.coupon === null || r.coupon === undefined) ? '' : r.coupon;
    $('pf-dlg-facevalue').value = (r.faceValue === null || r.faceValue === undefined) ? '' : r.faceValue;
    $('pf-dialog').showModal();
  }

  // ── Save / Load ──────────────────────────────────────────────────
  function save() {
    var payload = {
      id: currentId,
      name: $('pf-name').value,
      size: size(),
      currency_id: $('pf-currency').value || null,
      benchmark_id: $('pf-benchmark').value || null,
      is_benchmark: $('pf-is-benchmark').checked,
      holdings: rows.map(function (r) {
        return {
          company_id: r.companyId,
          amount: r.amount,
          weight: r.weight,
          instrument_type: r.instrument,
          maturity_date: r.maturity,
          coupon_rate: r.coupon,
          face_value: r.faceValue,
        };
      }),
    };
    fetch(PF_SAVE_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify(payload),
    }).then(function (resp) {
      return resp.json().then(function (data) { return { ok: resp.ok, data: data }; });
    }).then(function (res) {
      var status = $('pf-status');
      if (res.ok) {
        currentId = res.data.id;
        status.textContent = 'Portefeuille enregistré.';
        status.className = 'pf-status pf-status--ok';
      } else {
        status.textContent = 'Erreur de validation. Vérifiez les champs.';
        status.className = 'pf-status pf-status--err';
      }
    });
  }

  function loadPortfolio(pk) {
    fetch(PF_DETAIL_URL.replace(/0\/$/, pk + '/'))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        currentId = data.id;
        $('pf-name').value = data.name;
        $('pf-size').value = data.size;
        $('pf-currency').value = data.currency_id || '';
        $('pf-benchmark').value = data.benchmark_id || '';
        $('pf-is-benchmark').checked = !!data.is_benchmark;
        rows = data.holdings.map(function (h) {
          return {
            companyId: h.company_id,
            companyName: h.company_name,
            amount: h.amount,
            weight: h.weight,
            instrument: h.instrument_type,
            maturity: h.maturity_date,
            coupon: h.coupon_rate,
            faceValue: h.face_value,
          };
        });
        render();
      });
  }

  function resetForm() {
    currentId = null;
    rows = [];
    $('pf-name').value = '';
    $('pf-size').value = 0;
    $('pf-currency').selectedIndex = 0;
    $('pf-benchmark').value = '';
    $('pf-is-benchmark').checked = false;
    $('pf-portfolio-select').value = '';
    $('pf-status').textContent = '';
    render();
  }

  function init() {
    initTabs();
    populateSelects();
    initCompanySearch();
    initDialog();
    $('pf-save-btn').addEventListener('click', save);
    $('pf-new-btn').addEventListener('click', resetForm);
    $('pf-portfolio-select').addEventListener('change', function (e) {
      if (e.target.value) { loadPortfolio(e.target.value); } else { resetForm(); }
    });
    render();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
```

- [ ] **Step 2: Run the existing suite to confirm nothing broke**

Run: `python manage.py test dashboard -v 1`
Expected: PASS (all existing + new tests).

- [ ] **Step 3: Manual smoke test**

Run: `python manage.py runserver`, log in, open `/portfolio/`. Verify: tabs switch;
typing in the search adds a company row; editing amount updates weight and vice-versa;
the total turns green near 100%; the ⚙ button opens the dialog; choosing "Obligation"
reveals maturity/coupon/face value; Valider marks the gear; Enregistrer shows
"Portefeuille enregistré."; reload and re-select the saved fund to confirm rehydration.

- [ ] **Step 4: Commit**

```bash
git add dashboard/static/dashboard/js/portfolio.js
git commit -m "feat(portfolio): logique front (onglets, ponderation, dialog, save/load)"
```

---

### Task 8: Sidebar navigation + styles + full verification

**Files:**
- Modify: `templates/base.html` (add nav entry)
- Modify: `dashboard/static/dashboard/css/style.css` (append styles)
- Modify: `dashboard/tests.py` (append nav test class)

**Interfaces:**
- Consumes: URL name `dashboard:portfolio_analysis` (Task 5); `{% block nav_portfolio %}` defined in Task 6 template.

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests.py`:

```python
class PortfolioNavTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='navportf', password='pass')
        self.client.force_login(self.user)

    def test_sidebar_links_to_portfolio(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertContains(response, reverse('dashboard:portfolio_analysis'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.PortfolioNavTests -v 2`
Expected: FAIL — the index page does not yet contain the `/portfolio/` link.

- [ ] **Step 3: Add the sidebar entry**

In `templates/base.html`, add this `<li>` right after the "Comparaison" `<li>` block
(the one ending at line ~117, before the "Conformité CSRD" `<li>`):

```django
          <li>
            <a href="{% url 'dashboard:portfolio_analysis' %}" class="sidebar__nav-link {% block nav_portfolio %}{% endblock %}" aria-label="Portfolio analysis">
              <svg class="sidebar__nav-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <rect x="2.5" y="4" width="15" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
                <path d="M7 4V3a1.5 1.5 0 011.5-1.5h3A1.5 1.5 0 0113 3v1" stroke="currentColor" stroke-width="1.5"/>
                <path d="M2.5 9h15" stroke="currentColor" stroke-width="1.3"/>
              </svg>
              <span class="sidebar__nav-label">Portfolio analysis</span>
            </a>
          </li>
```

- [ ] **Step 4: Append styles**

Append to `dashboard/static/dashboard/css/style.css`:

```css
/* ── Portfolio analysis ─────────────────────────────────────────── */
.pf-portfolio-picker { display: flex; align-items: center; gap: .5rem; }
.pf-tabs { display: flex; gap: .25rem; flex-wrap: wrap; border-bottom: 1px solid var(--color-border, #e2e2e2); margin-bottom: 1.25rem; }
.pf-tab { background: none; border: none; padding: .6rem 1rem; cursor: pointer; color: var(--color-text-muted, #666); border-bottom: 2px solid transparent; font: inherit; }
.pf-tab--active { color: var(--color-primary, #2c7); border-bottom-color: var(--color-primary, #2c7); font-weight: 600; }
.pf-panel { display: none; }
.pf-panel--active { display: block; }
.pf-section-title { margin: 0 0 1rem; }
.pf-settings__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; }
.pf-field { display: flex; flex-direction: column; gap: .35rem; }
.pf-field--check { flex-direction: row; align-items: center; gap: .5rem; }
.pf-composition { margin-top: 1.25rem; }
.pf-add { position: relative; margin-bottom: 1rem; max-width: 420px; }
.pf-company-listbox { position: absolute; z-index: 20; left: 0; right: 0; margin: .25rem 0 0; padding: .25rem; list-style: none; background: #fff; border: 1px solid var(--color-border, #e2e2e2); border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,.08); max-height: 240px; overflow: auto; }
.pf-company-option { padding: .45rem .6rem; cursor: pointer; border-radius: 4px; }
.pf-company-option:hover { background: var(--color-surface-hover, #f3f3f3); }
.pf-holdings { width: 100%; border-collapse: collapse; }
.pf-holdings th, .pf-holdings td { padding: .5rem; text-align: left; border-bottom: 1px solid var(--color-border, #eee); }
.pf-holdings input { width: 100%; max-width: 140px; }
.pf-gear, .pf-del { background: none; border: none; cursor: pointer; font-size: 1.1rem; }
.pf-gear--filled { color: var(--color-primary, #2c7); }
.pf-total--ok { color: #2a9d4a; font-weight: 600; }
.pf-total--warn { color: #c98a00; font-weight: 600; }
.pf-empty { color: var(--color-text-muted, #888); padding: 1rem 0; }
.pf-actions { display: flex; justify-content: flex-end; align-items: center; gap: 1rem; margin-top: 1rem; }
.pf-status--ok { color: #2a9d4a; }
.pf-status--err { color: #c0392b; }
.pf-dialog { border: none; border-radius: 10px; padding: 1.5rem; max-width: 420px; width: 90%; box-shadow: 0 12px 40px rgba(0,0,0,.2); }
.pf-dialog::backdrop { background: rgba(0,0,0,.35); }
.pf-dialog__title { margin: 0 0 1rem; }
.pf-dialog__bond { display: flex; flex-direction: column; gap: .75rem; margin-top: .75rem; }
.pf-dialog__actions { display: flex; justify-content: flex-end; gap: .75rem; margin-top: 1.25rem; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
```

Note: if `.btn`, `.btn--primary`, or `.btn--ghost` classes do not already exist in
`style.css`, add minimal definitions alongside the block above:

```css
.btn { padding: .55rem 1rem; border-radius: 6px; border: 1px solid transparent; cursor: pointer; font: inherit; }
.btn--primary { background: var(--color-primary, #2c7); color: #fff; }
.btn--ghost { background: none; border-color: var(--color-border, #ccc); }
```

(Check first with: `grep -n "\.btn--primary" dashboard/static/dashboard/css/style.css`.)

- [ ] **Step 5: Run the nav test, then the full suite**

Run: `python manage.py test dashboard.tests.PortfolioNavTests -v 2`
Expected: PASS (1 test).

Run: `python manage.py test dashboard -v 1`
Expected: PASS (entire dashboard suite, existing + all portfolio tests).

- [ ] **Step 6: Commit**

```bash
git add templates/base.html dashboard/static/dashboard/css/style.css dashboard/tests.py
git commit -m "feat(portfolio): entree sidebar + styles page Portfolio analysis"
```

---

## Self-Review

**Spec coverage:**
- Models `Portfolio`/`PortfolioHolding`, benchmark self-reference, bond fields → Task 1. ✓
- Validation via Django forms (no raw POST) → Task 2 + used in Task 3. ✓
- `portfolio/` page, `api/portfolio/save/`, `api/portfolio/<pk>/` URLs/views → Tasks 3, 4, 5. ✓
- Context (companies/currencies/benchmarks/portfolios) via `json_script` → Tasks 5, 6. ✓
- Création UI: fund settings, company add, amount⟷weight sync, totals indicator, save → Tasks 6, 7. ✓
- Financial popup (`<dialog>`, equity/bond, conditional bond fields) → Tasks 6, 7. ✓
- Tab shell with 5 placeholders → Task 6. ✓
- Sidebar entry → Task 8. ✓
- Tests (nominal + error per model/form/view) → every task. ✓
- CSRF `X-CSRFToken`, SQLite-safe (no JSONField), `@login_required` → Tasks 3, 7, all views. ✓

**Placeholder scan:** No TBD/TODO; all steps carry concrete code/commands. ✓

**Type consistency:** Field names (`company_id`, `currency_id`, `benchmark_id`,
`instrument_type`, `maturity_date`, `coupon_rate`, `face_value`) are identical across
the save payload (Task 3), detail payload (Task 4), template data contract (Task 6),
and JS (Task 7). Element IDs declared in Task 6 match those referenced in Task 7. ✓
```
