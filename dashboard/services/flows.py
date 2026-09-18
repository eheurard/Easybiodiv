"""Lecture de la table Flow (spec 2026-09-18 §4).

Seul module qui filtre `Flow` : les vues appellent ces fonctions et ne
construisent jamais de requête `Flow` elles-mêmes.
"""
from collections import defaultdict

from django.db.models import Q

from dashboard.models import Flow, FlowKind

_OUTGOING_INVENTORY_KINDS = (FlowKind.EMISSION, FlowKind.WASTE)


def _inventory_rows(asset_ids):
    """Lignes d'inventaire mesuré des actifs : consommations qui y entrent,
    émissions et déchets qui en sortent, commodités à clé technique."""
    return (
        Flow.objects.filter(what__key__isnull=False)
        .filter(
            Q(kind=FlowKind.CONSUMPTION, to_asset_id__in=asset_ids)
            | Q(kind__in=_OUTGOING_INVENTORY_KINDS, from_asset_id__in=asset_ids)
        )
        .select_related('what')
        .order_by('pk')
    )


def _inventory_asset_id(flow):
    """Actif mesuré : destination d'une consommation, origine sinon."""
    if flow.kind == FlowKind.CONSUMPTION:
        return flow.to_asset_id
    return flow.from_asset_id


def latest_inventory(asset_ids, keys):
    """{asset_id: {key: {'value', 'unit'}}} : valeurs sommées par commodité
    technique, pour l'année la plus récente de chaque actif parmi les lignes des
    clés demandées. Une production plus récente ne décale pas l'inventaire."""
    rows = list(_inventory_rows(asset_ids).filter(what__key__in=keys))
    latest = {}
    for flow in rows:
        asset_id = _inventory_asset_id(flow)
        latest[asset_id] = max(latest.get(asset_id, flow.year), flow.year)
    result = defaultdict(dict)
    for flow in rows:
        asset_id = _inventory_asset_id(flow)
        if flow.year != latest[asset_id]:
            continue
        entry = result[asset_id].setdefault(
            flow.what.key, {'value': 0.0, 'unit': flow.what.unit})
        entry['value'] += flow.quantity
    return dict(result)


def inventory_total(asset, theme, year):
    """Somme des mesures d'inventaire d'un actif, une année, pour un thème."""
    return sum(
        flow.quantity
        for flow in _inventory_rows([asset.pk]).filter(what__theme=theme, year=year)
    )
