"""Fabriques de données de test pour la table Flow (spec 2026-09-18).

Hors motif de collecte pytest (`tests.py`, `test_*.py`, `tests_*.py`) : ce module
n'est pas un fichier de tests, il est importé par eux.
"""
from .models import Commodity, Flow, FlowKind

# Nature du flux d'une mesure d'inventaire, selon la commodité technique.
_INVENTORY_KIND = {
    'water': FlowKind.CONSUMPTION,
    'energy': FlowKind.CONSUMPTION,
    'surface_area': FlowKind.CONSUMPTION,
    'co2': FlowKind.EMISSION,
    'waste': FlowKind.WASTE,
}


def make_inventory(*, asset, key, year, value):
    """Mesure d'inventaire : consommation prélevée dans le milieu, ou émission /
    déchet rejetés dans le milieu."""
    kind = _INVENTORY_KIND[key]
    if kind == FlowKind.CONSUMPTION:
        ends = {'from_environment': True, 'to_asset': asset}
    else:
        ends = {'from_asset': asset, 'to_environment': True}
    return Flow.objects.create(
        kind=kind, what=Commodity.objects.technical(key), year=year, quantity=value,
        **ends,
    )


def make_production(*, commodity, year, production, asset=None, company=None,
                    estimated_revenue=0.0, tier=0):
    """Flux PRODUCTION, avec la signature de l'ancien Production.objects.create
    pour limiter la réécriture des tests. Un actif l'emporte sur l'entreprise :
    une production n'a qu'une origine."""
    return Flow.objects.create(
        kind=FlowKind.PRODUCTION, what=commodity,
        from_asset=asset, from_company=None if asset is not None else company,
        year=year, quantity=production, estimated_revenue=estimated_revenue, tier=tier,
    )
