"""Lecture de la table Flow (spec 2026-09-18 §4).

Seul module qui filtre `Flow` : les vues appellent ces fonctions et ne
construisent jamais de requête `Flow` elles-mêmes.
"""
from collections import defaultdict

from django.db.models import Q

from dashboard.models import (
    _ENDPOINT_FIELD_SUFFIX, Asset, Flow, FlowKind, FlowScope, Ownership,
)

_OUTGOING_INVENTORY_KINDS = (FlowKind.EMISSION, FlowKind.WASTE)

_ENDPOINT_RELATIONS = (
    'what', 'from_asset', 'from_region', 'from_country', 'from_company',
    'to_asset', 'to_region', 'to_country', 'to_company',
)


def flows_with_endpoints():
    """Tous les flux, avec leurs extrémités préchargées (imports/services/
    excel_parser.py : détection des doublons de la feuille Flow)."""
    return Flow.objects.select_related(*_ENDPOINT_RELATIONS)


def _touches_q(company, asset_ids):
    """Q vrai quand une extrémité du flux est `company` ou l'un des actifs."""
    return (
        Q(from_company=company) | Q(to_company=company)
        | Q(from_asset_id__in=asset_ids) | Q(to_asset_id__in=asset_ids)
    )


def _touching(flows, touching):
    """Restreint `flows` à ceux dont l'origine ou la destination est l'élément
    `touching` = (endpoint, pk) ; inchangé si `touching` est None."""
    if touching is None:
        return flows
    endpoint, pk = touching
    suffix = _ENDPOINT_FIELD_SUFFIX[endpoint]
    return flows.filter(Q(**{f'from_{suffix}_id': pk}) | Q(**{f'to_{suffix}_id': pk}))


def perimeter_flows(company, year, touching=None):
    """Flux de l'année `year` dont une extrémité est `company` ou un actif
    qu'elle détient cette année-là. `touching` = (endpoint, pk) ne garde que
    les flux dont l'origine ou la destination est cet élément."""
    asset_ids = Asset.objects.owned_by(company, year).values('pk')
    flows = (
        Flow.objects.filter(year=year)
        .filter(_touches_q(company, asset_ids))
        .select_related(*_ENDPOINT_RELATIONS)
        .order_by('pk')
    )
    return _touching(flows, touching)


def ownerships_in_range(company, start, end):
    """Détentions de `company` valides au moins une année de [start, end]."""
    return Ownership.objects.filter(
        Q(start_year__isnull=True) | Q(start_year__lte=end),
        Q(end_year__isnull=True) | Q(end_year__gte=start),
        company=company,
    )


def range_perimeter_flows(company, start, end, touching=None):
    """Union, pour chaque année de [start, end], de perimeter_flows(company,
    année, touching), triée par (année, pk) : la détention d'un actif est
    vérifiée l'année du flux."""
    ownerships = ownerships_in_range(company, start, end)
    held = defaultdict(list)
    for asset_id, first, last in ownerships.values_list('asset_id', 'start_year', 'end_year'):
        held[asset_id].append((first, last))

    def owned(asset_id, year):
        return any(
            (first is None or first <= year) and (last is None or last >= year)
            for first, last in held.get(asset_id, ())
        )

    flows = _touching(
        Flow.objects.filter(year__gte=start, year__lte=end)
        .filter(_touches_q(company, ownerships.values('asset_id')))
        .select_related(*_ENDPOINT_RELATIONS)
        .order_by('year', 'pk'),
        touching,
    )
    return [
        flow for flow in flows
        if company.pk in (flow.from_company_id, flow.to_company_id)
        or owned(flow.from_asset_id, flow.year) or owned(flow.to_asset_id, flow.year)
    ]


def perimeter_years(company):
    """Années (croissantes) des flux du périmètre de `company`, avec la règle
    de détention de perimeter_flows()."""
    ever_owned = Ownership.objects.filter(company=company).values('asset_id')
    years = (
        Flow.objects.filter(_touches_q(company, ever_owned))
        .order_by().values_list('year', flat=True).distinct()
    )
    return sorted(year for year in years if perimeter_flows(company, year).exists())


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


def _latest_years(rows):
    """{asset_id: année la plus récente} parmi des lignes d'inventaire."""
    latest = {}
    for flow in rows:
        asset_id = _inventory_asset_id(flow)
        latest[asset_id] = max(latest.get(asset_id, flow.year), flow.year)
    return latest


def latest_inventory_years(asset_ids, keys):
    """{asset_id: année} retenue par latest_inventory() pour ces clés."""
    return _latest_years(_inventory_rows(asset_ids).filter(what__key__in=keys))


def latest_inventory(asset_ids, keys):
    """{asset_id: {key: {'value', 'unit'}}} : valeurs sommées par commodité
    technique, pour l'année la plus récente de chaque actif parmi les lignes des
    clés demandées. Une production plus récente ne décale pas l'inventaire."""
    rows = list(_inventory_rows(asset_ids).filter(what__key__in=keys))
    latest = _latest_years(rows)
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


def latest_declared_consumption(company, key):
    """{'value', 'year'} de la consommation déclarée au niveau de l'entreprise
    (vers `to_company`, sans ventilation par actif) pour la commodité technique
    `key`, à sa dernière année ; None si rien n'est déclaré."""
    rows = list(Flow.objects.filter(
        kind=FlowKind.CONSUMPTION, to_company=company, what__key=key,
    ))
    if not rows:
        return None
    year = max(flow.year for flow in rows)
    return {'value': sum(f.quantity for f in rows if f.year == year), 'year': year}


def productions(asset_ids):
    """Flux PRODUCTION des actifs donnés, toutes années, dans l'ordre de création
    (déterminisme SQLite/PostgreSQL : le sankey de Mesure d'empreinte en dépend)."""
    return list(
        Flow.objects.filter(kind=FlowKind.PRODUCTION, from_asset_id__in=asset_ids)
        .select_related('what', 'from_asset__country', 'from_asset__subnational_region')
        .order_by('pk')
    )


def latest_productions(asset_ids):
    """Comme productions(), en ne gardant que l'année la plus récente de chaque actif."""
    rows = productions(asset_ids)
    latest = {}
    for flow in rows:
        latest[flow.from_asset_id] = max(latest.get(flow.from_asset_id, flow.year), flow.year)
    return [flow for flow in rows if flow.year == latest[flow.from_asset_id]]


def company_productions(company):
    """Flux PRODUCTION déclarés par l'entreprise ou par les actifs qu'elle détient
    aujourd'hui, toutes années, dans l'ordre de création."""
    owned = Asset.objects.owned_by(company).values('pk')
    return list(
        Flow.objects.filter(kind=FlowKind.PRODUCTION)
        .filter(Q(from_company=company) | Q(from_asset__in=owned))
        .select_related('what')
        .order_by('pk')
    )


def supplies_to(asset_ids, company=None):
    """Flux SUPPLY vers ces actifs (et vers `company` si fournie), en ne gardant
    que la dernière année connue de chaque destination."""
    destination = Q(to_asset_id__in=asset_ids)
    if company is not None:
        destination |= Q(to_company=company)
    rows = list(
        Flow.objects.filter(kind=FlowKind.SUPPLY).filter(destination)
        .select_related(
            'what', 'from_asset__country', 'from_region__country', 'from_country',
            'to_asset',
        )
        .order_by('pk')
    )

    def _destination(flow):
        return ('asset', flow.to_asset_id) if flow.to_asset_id else ('company', flow.to_company_id)

    latest = {}
    for flow in rows:
        key = _destination(flow)
        latest[key] = max(latest.get(key, flow.year), flow.year)
    return [flow for flow in rows if flow.year == latest[_destination(flow)]]


# Libellés de scope en chaînes simples : ce sont les clés des dictionnaires
# renvoyés aux vues et sérialisés en JSON.
_SCOPE_1 = FlowScope.SCOPE_1.value
_SCOPE_2 = FlowScope.SCOPE_2.value
_SCOPE_3 = FlowScope.SCOPE_3.value
_SCOPE_1_2 = FlowScope.SCOPE_1_2.value
# Totaux impossibles à ventiler, par ordre de préférence.
_UNSPLIT_TOTALS = (FlowScope.SCOPE_1_2_3.value, FlowScope.UNDEFINED.value)


def resolve_scopes(values):
    """Scopes retenus pour une année, {scope: tCO₂e} → {scope: tCO₂e} (spec §4).

    Scopes 1 et 2 détaillés s'ils existent, sinon Scope 1+2 ; plus le Scope 3.
    Un total non ventilable (1+2+3, puis undefined) ne compte que seul.
    """
    kept = {}
    detailed = {s: values[s] for s in (_SCOPE_1, _SCOPE_2) if s in values}
    if detailed:
        kept.update(detailed)
    elif _SCOPE_1_2 in values:
        kept[_SCOPE_1_2] = values[_SCOPE_1_2]
    if _SCOPE_3 in values:
        kept[_SCOPE_3] = values[_SCOPE_3]
    if not kept:
        for scope in _UNSPLIT_TOTALS:
            if scope in values:
                kept[scope] = values[scope]
                break
    return kept


def declared_emissions(company):
    """{année: {scope: tCO₂e}} des émissions déclarées par l'entreprise, scopes
    résolus, années croissantes. Le CO₂ mesuré sur ses actifs n'y entre jamais."""
    raw = defaultdict(lambda: defaultdict(float))
    rows = Flow.objects.filter(
        kind=FlowKind.EMISSION, from_company=company, what__key='co2',
    ).order_by('year', 'pk')
    for flow in rows:
        raw[flow.year][str(flow.scope)] += flow.quantity
    return {year: resolve_scopes(dict(values)) for year, values in sorted(raw.items())}
