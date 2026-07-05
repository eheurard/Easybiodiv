"""Backfill figé scope→tier pour Production (instantané de migration)."""
_SCOPE_TO_TIER = {'direct': 0, 'tier 1': 1, 'tier 2': 2, 'raw material': 3}


def backfill(Production):
    for scope, tier in _SCOPE_TO_TIER.items():
        Production.objects.filter(scope=scope).update(tier=tier)
