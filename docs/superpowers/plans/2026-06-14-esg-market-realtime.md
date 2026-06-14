# Market Intelligence temps réel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alimenter la section Market Intelligence (page Données ESG) avec des données de marché temps réel issues de Yahoo Finance, via le `ticker` du modèle `Company`.

**Architecture:** Un module service `dashboard/services/market.py` récupère cours/variation/sparkline côté serveur (urllib stdlib) avec cache Django 15 min et repli gracieux sur la démo. `_get_esg_data` appelle ce service ; le JS masque les champs nuls. Couvre rendu initial serveur + endpoint AJAX puisque les deux passent par `_get_esg_data`.

**Tech Stack:** Django, `urllib.request` (stdlib), `django.core.cache`, JS vanilla, Django `TestCase` (`python manage.py test`).

---

## File Structure

- **Create** `dashboard/services/__init__.py` — package marker (peut déjà exister si `imports/services` est un modèle ; ici c'est le package `dashboard.services`).
- **Create** `dashboard/services/market.py` — `get_market_data(company)` + helpers de parsing/repli.
- **Modify** `dashboard/views.py` — `_get_esg_data` utilise `get_market_data`.
- **Modify** `dashboard/static/dashboard/js/esg.js` — `esgStatRow` saute les valeurs nulles.
- **Modify** `dashboard/tests.py` — tests du service (parsing, repli réseau, repli sans ticker).

---

### Task 1: Module service `market.py` avec repli sans ticker

**Files:**
- Create: `dashboard/services/__init__.py`
- Create: `dashboard/services/market.py`
- Test: `dashboard/tests.py`

- [ ] **Step 1: Créer le package**

Créer `dashboard/services/__init__.py` vide.

- [ ] **Step 2: Écrire le test de repli sans ticker**

Ajouter à `dashboard/tests.py` :

```python
from unittest import mock
from dashboard.services import market as market_service


class MarketDataTests(TestCase):
    def test_no_ticker_returns_demo_without_network(self):
        company = Company.objects.create(name='NoTicker', isin='0', ticker='0')
        with mock.patch('dashboard.services.market.urlopen') as m:
            data = market_service.get_market_data(company)
        m.assert_not_called()
        self.assertTrue(data['is_demo'])
        self.assertEqual(data['ticker'], '0')
        self.assertIsNone(data['market_cap'])
        self.assertIsNone(data['esg_rating'])
        self.assertIsNone(data['relative_perf'])
        self.assertIn('price', data)
        self.assertIsInstance(data['sparkline'], list)
```

- [ ] **Step 3: Lancer le test (échec attendu)**

Run: `python manage.py test dashboard.tests.MarketDataTests.test_no_ticker_returns_demo_without_network`
Expected: FAIL (ModuleNotFoundError `dashboard.services.market`).

- [ ] **Step 4: Implémenter `market.py` (repli + squelette)**

Créer `dashboard/services/market.py` :

```python
"""Données de marché temps réel pour la section Market Intelligence.

Source : Yahoo Finance, endpoint chart sans clé. Repli gracieux sur des
valeurs démo si le ticker est absent ou si l'appel échoue.
"""
import json
from urllib.request import Request, urlopen

from django.core.cache import cache

CACHE_TTL = 60 * 15  # 15 minutes
TIMEOUT = 4  # secondes
USER_AGENT = "Mozilla/5.0 (compatible; Easybiodiv/1.0)"
CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{ticker}?range=1mo&interval=1d"
)

_DEMO_SPARKLINE = [35, 32, 38, 30, 25, 28, 20, 22, 15, 18, 5]


def _demo_payload(company):
    return {
        'is_demo': True,
        'isin': company.isin,
        'ticker': company.ticker,
        'price': 142.85,
        'currency': 'EUR',
        'change_pct': 2.4,
        'market_cap': None,
        'esg_rating': None,
        'relative_perf': None,
        'sparkline': list(_DEMO_SPARKLINE),
    }


def get_market_data(company):
    ticker = (company.ticker or '').strip()
    if not ticker or ticker == '0':
        return _demo_payload(company)
    return _demo_payload(company)  # remplacé en Task 2
```

- [ ] **Step 5: Lancer le test (succès attendu)**

Run: `python manage.py test dashboard.tests.MarketDataTests.test_no_ticker_returns_demo_without_network`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/services/__init__.py dashboard/services/market.py dashboard/tests.py
git commit -m "feat(esg): service market.py avec repli demo sans ticker"
```

---

### Task 2: Fetch Yahoo + parsing + cache

**Files:**
- Modify: `dashboard/services/market.py`
- Test: `dashboard/tests.py`

- [ ] **Step 1: Écrire le test de parsing (réponse Yahoo mockée)**

Ajouter à `MarketDataTests` :

```python
def _yahoo_response(self):
    return json.dumps({
        'chart': {'result': [{
            'meta': {
                'regularMarketPrice': 150.0,
                'chartPreviousClose': 120.0,
                'currency': 'USD',
            },
            'indicators': {'quote': [{'close': [100.0, None, 110.0, 150.0]}]},
        }], 'error': None}
    }).encode('utf-8')

def test_parses_yahoo_response(self):
    company = Company.objects.create(name='Acme', isin='US0001', ticker='ACME')
    cm = mock.MagicMock()
    cm.read.return_value = self._yahoo_response()
    cm.__enter__.return_value = cm
    cm.getcode.return_value = 200
    with mock.patch('dashboard.services.market.urlopen', return_value=cm):
        data = market_service.get_market_data(company)
    self.assertFalse(data['is_demo'])
    self.assertEqual(data['price'], 150.0)
    self.assertEqual(data['currency'], 'USD')
    self.assertEqual(data['change_pct'], 25.0)  # (150-120)/120*100
    self.assertEqual(data['sparkline'], [100.0, 110.0, 150.0])  # null filtré
    self.assertEqual(data['ticker'], 'ACME')
```

- [ ] **Step 2: Lancer le test (échec attendu)**

Run: `python manage.py test dashboard.tests.MarketDataTests.test_parses_yahoo_response`
Expected: FAIL (`is_demo` True, données démo).

- [ ] **Step 3: Implémenter fetch/parsing/cache**

Dans `dashboard/services/market.py`, remplacer le corps de `get_market_data` et ajouter les helpers :

```python
def _fetch_chart(ticker):
    req = Request(
        CHART_URL.format(ticker=ticker),
        headers={'User-Agent': USER_AGENT},
    )
    with urlopen(req, timeout=TIMEOUT) as resp:
        if resp.getcode() != 200:
            raise ValueError('HTTP %s' % resp.getcode())
        return json.loads(resp.read().decode('utf-8'))


def _parse_chart(payload, company):
    result = payload['chart']['result'][0]
    meta = result['meta']
    price = meta['regularMarketPrice']
    prev = meta['chartPreviousClose']
    closes = result['indicators']['quote'][0]['close']
    sparkline = [c for c in closes if c is not None]
    change_pct = round((price - prev) / prev * 100, 2) if prev else 0.0
    return {
        'is_demo': False,
        'isin': company.isin,
        'ticker': company.ticker,
        'price': price,
        'currency': meta.get('currency') or 'EUR',
        'change_pct': change_pct,
        'market_cap': None,
        'esg_rating': None,
        'relative_perf': None,
        'sparkline': sparkline,
    }


def get_market_data(company):
    ticker = (company.ticker or '').strip()
    if not ticker or ticker == '0':
        return _demo_payload(company)

    cache_key = 'esg_market:%s' % ticker
    cached = cache.get(cache_key)
    if cached is not None:
        cached = dict(cached)
        cached['isin'] = company.isin
        return cached

    try:
        payload = _fetch_chart(ticker)
        data = _parse_chart(payload, company)
    except Exception:
        return _demo_payload(company)

    cache.set(cache_key, data, CACHE_TTL)
    return data
```

Supprimer la ligne `return _demo_payload(company)  # remplacé en Task 2`.

- [ ] **Step 4: Lancer les tests du service**

Run: `python manage.py test dashboard.tests.MarketDataTests`
Expected: PASS (les 2 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/services/market.py dashboard/tests.py
git commit -m "feat(esg): fetch Yahoo Finance + parsing + cache 15 min"
```

---

### Task 3: Test du repli réseau

**Files:**
- Test: `dashboard/tests.py`

- [ ] **Step 1: Écrire le test de repli sur erreur réseau**

Ajouter à `MarketDataTests` :

```python
def test_network_error_returns_demo(self):
    company = Company.objects.create(name='Boom', isin='US0002', ticker='BOOM')
    with mock.patch('dashboard.services.market.urlopen',
                    side_effect=OSError('timeout')):
        data = market_service.get_market_data(company)
    self.assertTrue(data['is_demo'])
    self.assertEqual(data['ticker'], 'BOOM')
```

- [ ] **Step 2: Lancer le test (succès attendu)**

Run: `python manage.py test dashboard.tests.MarketDataTests.test_network_error_returns_demo`
Expected: PASS (le `except Exception` de Task 2 couvre déjà ce cas).

- [ ] **Step 3: Commit**

```bash
git add dashboard/tests.py
git commit -m "test(esg): repli demo sur erreur reseau"
```

---

### Task 4: Câbler `_get_esg_data`

**Files:**
- Modify: `dashboard/views.py:1141-1162`

- [ ] **Step 1: Importer le service**

En haut de `dashboard/views.py`, parmi les imports locaux, ajouter :

```python
from .services.market import get_market_data
```

- [ ] **Step 2: Remplacer le dict `market` codé en dur**

Dans `_get_esg_data`, remplacer le bloc :

```python
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
```

par :

```python
        'market': get_market_data(company),
```

- [ ] **Step 3: Vérifier l'endpoint manuellement**

Run: `python manage.py shell -c "from dashboard.models import Company; from dashboard.views import _get_esg_data; print(_get_esg_data(Company.objects.first())['market'])"`
Expected: dict `market` avec `is_demo` (True ou False selon ticker), sans erreur.

- [ ] **Step 4: Lancer toute la suite dashboard**

Run: `python manage.py test dashboard`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/views.py
git commit -m "feat(esg): brancher get_market_data dans _get_esg_data"
```

---

### Task 5: Masquer les champs nuls côté JS

**Files:**
- Modify: `dashboard/static/dashboard/js/esg.js:302-307`

- [ ] **Step 1: Modifier `esgStatRow` pour sauter les valeurs nulles**

Remplacer la fonction `esgStatRow` :

```javascript
function esgStatRow(label, value) {
  return '<div class="esg-market__stat">' +
    '<span class="esg-market__stat-label">' + escHtml(label) + '</span>' +
    '<span class="esg-market__stat-value">' + escHtml(String(value != null ? value : '—')) + '</span>' +
    '</div>';
}
```

par :

```javascript
function esgStatRow(label, value) {
  if (value == null) return '';
  return '<div class="esg-market__stat">' +
    '<span class="esg-market__stat-label">' + escHtml(label) + '</span>' +
    '<span class="esg-market__stat-value">' + escHtml(String(value)) + '</span>' +
    '</div>';
}
```

- [ ] **Step 2: Vérification manuelle navigateur**

Run: `python manage.py runserver` puis ouvrir la page Données ESG.
Expected: section Market Intelligence affiche cours/variation/sparkline + ISIN ; les lignes Capitalisation / Notation ESG / Perf. relative sont absentes (données réelles). Badge « Démo » visible seulement si repli.

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/dashboard/js/esg.js
git commit -m "feat(esg): masquer les lignes market sans valeur"
```

---

## Self-Review

- **Spec coverage :** source Yahoo (Task 2), champs temps réel price/currency/change_pct/sparkline (Task 2), champs masqués → None + JS (Tasks 2 & 5), urllib stdlib (Task 1-2), cache 15 min (Task 2), repli sans ticker (Task 1) / erreur (Task 3), câblage `_get_esg_data` couvrant les 2 chemins (Task 4), tests (Tasks 1-3). ✔
- **Placeholder scan :** la ligne marquée `# remplacé en Task 2` est explicitement supprimée en Task 2 Step 3. Aucun autre placeholder. ✔
- **Type consistency :** clés du dict identiques entre `_demo_payload` et `_parse_chart` (is_demo, isin, ticker, price, currency, change_pct, market_cap, esg_rating, relative_perf, sparkline) ; `get_market_data`, `urlopen`, `cache` cohérents entre tâches. ✔
