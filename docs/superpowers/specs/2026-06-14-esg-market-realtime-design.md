# Market Intelligence temps réel (page Données ESG) — Design

**Date :** 2026-06-14
**Statut :** approuvé

## Objectif

Remplacer les données démo codées en dur de la section **Market Intelligence**
(page Données ESG) par des données de marché temps réel, en s'appuyant sur le
`ticker` du modèle `Company`. Approche la plus simple possible.

## Contexte actuel

- `dashboard/views.py` → `_get_esg_data(company)` construit un dict `market`
  entièrement codé en dur (`is_demo: True`).
- `dashboard/static/dashboard/js/esg.js` → `esgRenderMarket()` consomme :
  `is_demo, ticker, isin, price, currency, change_pct, market_cap,
  esg_rating, relative_perf, sparkline`.
- `Company` possède déjà `isin` et `ticker` (défaut `"0"`).
- Deux chemins passent par `_get_esg_data` : rendu initial serveur (`esg`)
  et endpoint AJAX (`esg_data`). Modifier la source couvre les deux.

## Décisions

- **Source :** Yahoo Finance, endpoint sans clé
  `https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=1d`.
- **Champs temps réel :** `price`, `currency`, `change_pct`, `sparkline`.
- **Champs non disponibles en gratuit** (`market_cap`, `esg_rating`,
  `relative_perf`) → `None`, **masqués** dans l'UI.
- **Pas de nouvelle dépendance** : `urllib` (stdlib).
- **Appel côté serveur uniquement** (Yahoo bloque le CORS navigateur).

## Architecture

### 1. `dashboard/services/market.py` (nouveau)

```
get_market_data(company) -> dict
```

- Si `company.ticker` vide ou `"0"` → repli démo (`is_demo=True`).
- Sinon, lecture du cache (clé `esg_market:{ticker}`, TTL 15 min).
  - Cache miss → requête Yahoo via `urllib.request` avec header
    `User-Agent` (Yahoo refuse l'UA Python par défaut), timeout ~4 s.
  - Parse `chart.result[0]` :
    - `price` = `meta.regularMarketPrice`
    - `currency` = `meta.currency`
    - `prev_close` = `meta.chartPreviousClose`
    - `change_pct` = `(price - prev_close) / prev_close * 100`, arrondi 2 déc.
    - `sparkline` = `indicators.quote[0].close` (valeurs `null` filtrées)
  - Mise en cache du résultat.
- Toute erreur (réseau, timeout, parsing, HTTP ≠ 200) → repli démo.

Dict retourné :
```python
{
  'is_demo': bool,
  'isin': company.isin,
  'ticker': company.ticker,
  'price': float,
  'currency': str,
  'change_pct': float,
  'market_cap': None,
  'esg_rating': None,
  'relative_perf': None,
  'sparkline': list[float],
}
```

Le repli démo réutilise les valeurs actuellement codées en dur.

### 2. `dashboard/views.py`

`_get_esg_data` : remplacer le dict `market` littéral par
`get_market_data(company)`.

### 3. `dashboard/static/dashboard/js/esg.js`

`esgStatRow(label, value)` : retourner `''` quand `value` est `null`/`undefined`
(la ligne disparaît au lieu d'afficher `—`). `market_cap`, `esg_rating`,
`relative_perf` deviennent donc invisibles tant qu'ils valent `None`.

## Cache

- `django.core.cache` (défaut LocMemCache, compatible SQLite/cPanel).
- TTL 15 min → pas d'appel Yahoo à chaque chargement, évite le bannissement IP.

## Tests (`dashboard/tests.py`)

- Parsing OK : `urllib`/réponse Yahoo mockée → champs corrects, `is_demo=False`.
- Repli erreur réseau : exception mockée → `is_demo=True`, valeurs démo.
- Repli sans ticker : `ticker="0"` → `is_demo=True`, aucun appel réseau.

## Contraintes respectées

- Aucune dépendance nouvelle, `urllib` stdlib.
- Compatible SQLite ↔ PostgreSQL/PostGIS.
- cPanel-friendly (pas de processus long, pas de build Node).
- Repli gracieux : la page ne casse jamais.
