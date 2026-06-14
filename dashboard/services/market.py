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
