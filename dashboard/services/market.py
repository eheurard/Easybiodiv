"""Données de marché temps réel pour la section Market Intelligence.

Source : Yahoo Finance, endpoint chart sans clé. Repli gracieux sur des
valeurs démo si le ticker est absent ou si l'appel échoue.

Le sparkline et la variation (%) couvrent une période sélectionnable
(3 mois, 6 mois, depuis le 1er janvier, 5 ans). La variation représente la
performance sur la période (dernier cours vs premier cours).
"""
import json
from urllib.request import Request, urlopen

from django.core.cache import cache

CACHE_TTL = 60 * 15  # 15 minutes
TIMEOUT = 4  # secondes
USER_AGENT = "Mozilla/5.0 (compatible; Easybiodiv/1.0)"
CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{ticker}?range={range}&interval={interval}"
)

# Périodes proposées dans le filtre → intervalle Yahoo adapté
# (1wk pour 5y afin d'alléger le nombre de points).
RANGE_INTERVALS = {
    '3mo': '1d',
    '6mo': '1d',
    'ytd': '1d',
    '5y': '1wk',
}
DEFAULT_RANGE = '3mo'

_DEMO_SPARKLINE = [35, 32, 38, 30, 25, 28, 20, 22, 15, 18, 5]


def normalize_range(range_key):
    """Retourne une période valide (repli sur DEFAULT_RANGE)."""
    return range_key if range_key in RANGE_INTERVALS else DEFAULT_RANGE


def _demo_payload(company, range_key):
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
        'range': range_key,
        'sparkline': list(_DEMO_SPARKLINE),
    }


def _fetch_chart(ticker, range_key):
    url = CHART_URL.format(
        ticker=ticker, range=range_key, interval=RANGE_INTERVALS[range_key],
    )
    req = Request(url, headers={'User-Agent': USER_AGENT})
    with urlopen(req, timeout=TIMEOUT) as resp:
        if resp.getcode() != 200:
            raise ValueError('HTTP %s' % resp.getcode())
        return json.loads(resp.read().decode('utf-8'))


def _parse_chart(payload, company, range_key):
    result = payload['chart']['result'][0]
    meta = result['meta']
    closes = [c for c in result['indicators']['quote'][0]['close'] if c is not None]
    if len(closes) >= 2 and closes[0]:
        change_pct = round((closes[-1] - closes[0]) / closes[0] * 100, 2)
    else:
        change_pct = 0.0
    return {
        'is_demo': False,
        'isin': company.isin,
        'ticker': company.ticker,
        'price': meta['regularMarketPrice'],
        'currency': meta.get('currency') or 'EUR',
        'change_pct': change_pct,
        'market_cap': None,
        'esg_rating': None,
        'relative_perf': None,
        'range': range_key,
        'sparkline': closes,
    }


def get_market_data(company, range_key=DEFAULT_RANGE):
    range_key = normalize_range(range_key)
    ticker = (company.ticker or '').strip()
    if not ticker or ticker == '0':
        return _demo_payload(company, range_key)

    cache_key = 'esg_market:%s:%s' % (ticker, range_key)
    cached = cache.get(cache_key)
    if cached is not None:
        cached = dict(cached)
        cached['isin'] = company.isin
        return cached

    try:
        payload = _fetch_chart(ticker, range_key)
        data = _parse_chart(payload, company, range_key)
    except Exception:
        return _demo_payload(company, range_key)

    cache.set(cache_key, data, CACHE_TTL)
    return data
