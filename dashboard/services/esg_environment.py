"""Onglets environnementaux de la page ESG : pollution, utilisation des
ressources et espèces exotiques envahissantes.

Même périmètre que l'onglet Land use : actifs détenus aujourd'hui par
l'entreprise, chacun à sa dernière année de données, comptés à 100 % (sans
pondération par la part de détention, comme la page Comparer). Les impacts
modélisés sont `production × facteur de caractérisation` ReCiPe 2016 midpoint,
régionalisé (région, sinon pays, sinon global).
"""
from collections import defaultdict

from django.utils.translation import gettext_lazy as _

from ..models import Asset, ImpactCategory, TECHNICAL_COMMODITIES
from . import flows as flow_service
from .impacts import build_cf_index, cf_value

# Unités ReCiPe 2016 midpoint, utilisées quand la catégorie n'a pas d'unité en base.
RECIPE_MIDPOINT_UNITS = {
    'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity': 'kg 1,4-DCB',
    'impact_midpoint_ReCiPe2016_freshwater_eutrophication': 'kg P eq',
    'impact_midpoint_ReCiPe2016_marine_eutrophication': 'kg N eq',
    'impact_midpoint_ReCiPe2016_terrestrial_acidification': 'kg SO₂ eq',
    'impact_midpoint_ReCiPe2016_soil_acidification': 'kg SO₂ eq',
    'impact_midpoint_ReCiPe2016_ozonedepletion': 'kg CFC-11 eq',
    'impact_midpoint_ReCiPe2016_resource_depletion_fossil': 'kg oil eq',
    'impact_midpoint_ReCiPe2016_resource_depletion_minerals': 'kg Cu eq',
}

# Pressions de pollution (ESRS E2), rangées par milieu récepteur.
POLLUTION_MEDIA = [
    ('air', _('Air'), [
        ('impact_midpoint_ReCiPe2016_terrestrial_acidification', _('Acidification terrestre')),
        ('impact_midpoint_ReCiPe2016_ozonedepletion', _("Appauvrissement de l'ozone")),
    ]),
    ('water', _('Eau'), [
        ('impact_midpoint_ReCiPe2016_freshwater_eutrophication', _('Eutrophisation eau douce')),
        ('impact_midpoint_ReCiPe2016_marine_eutrophication', _('Eutrophisation marine')),
        ('impact_midpoint_ReCiPe2016_freshwater_ecotoxicity', _('Écotoxicité eau douce')),
    ]),
    ('soil', _('Sol'), [
        ('impact_midpoint_ReCiPe2016_soil_acidification', _('Acidification des sols')),
    ]),
]

# Utilisation des ressources (ESRS E3 / E5) : inventaire mesuré par actif…
RESOURCE_INVENTORY = [
    ('water', _('Eau consommée')),
    ('energy', _('Énergie consommée')),
    ('waste', _('Déchets générés')),
]
# … et raréfaction des ressources modélisée (ReCiPe 2016 midpoint).
RESOURCE_SCARCITY = [
    ('impact_midpoint_ReCiPe2016_resource_depletion_fossil', _('Ressources fossiles')),
    ('impact_midpoint_ReCiPe2016_resource_depletion_minerals', _('Ressources minérales')),
]

# Espèces exotiques envahissantes : criblage indicatif des voies d'introduction
# (classification CBD 2014). Aucune donnée d'occurrence n'est mesurée.
IAS_CULTIVATION_TYPES = {'Forest'}   # plantations : introduction volontaire, échappement
IAS_DISTURBANCE_TYPES = {'Mine'}     # sols mis à nu, corridors d'accès
IAS_TRANSPORT_TYPES = {'Airport'}    # plateforme de transport : passagers clandestins
IAS_LEVELS = ['low', 'moderate', 'high']
IAS_LEVEL_LABELS = {'low': _('Faible'), 'moderate': _('Modéré'), 'high': _('Élevé')}
IAS_ACTIVITY_LABELS = {
    'cultivation': _('Cultures et plantations'),
    'disturbance': _('Perturbation des sols'),
}


def significant(value, digits=4):
    """Arrondi à `digits` chiffres significatifs : les impacts vont de 1e-6
    (ozone) à 1e9 (écotoxicité), un arrondi décimal fixe les écraserait."""
    return float(f'{value:.{digits}g}')


def owned_assets(company):
    return list(
        Asset.objects.owned_by(company)
        .select_related('country').distinct().order_by('name')
    )


def owned_asset_impacts(assets, category_keys):
    """Impacts midpoint des actifs, à leur dernière année de production.

    Retourne (by_asset, by_commodity) :
      by_asset     {asset_pk: {'year': année, clé: valeur, …}} (actifs produisant)
      by_commodity {nom de commodité: {clé: valeur}}
    """
    asset_map = {a.pk: a for a in assets}
    productions = flow_service.latest_productions(list(asset_map))
    cf_index = build_cf_index(
        commodity_ids={p.what_id for p in productions}, category_keys=category_keys,
    )
    by_asset = {}
    by_commodity = defaultdict(lambda: defaultdict(float))
    for p in productions:
        asset = asset_map[p.from_asset_id]
        entry = by_asset.setdefault(
            asset.pk, {'year': p.year, **{key: 0.0 for key in category_keys}},
        )
        for key in category_keys:
            value = p.quantity * cf_value(
                cf_index, p.what_id, key, asset.subnational_region_id, asset.country_id,
            )
            entry[key] += value
            by_commodity[p.what.name][key] += value
    return by_asset, by_commodity


def impact_units(keys):
    """Unité de chaque catégorie : celle de la base, sinon l'unité ReCiPe."""
    stored = dict(
        ImpactCategory.objects.filter(key__in=keys).values_list('key', 'unit')
    )
    return {key: stored.get(key) or RECIPE_MIDPOINT_UNITS.get(key, '') for key in keys}


def _country(asset):
    return asset.country.name if asset.country else None


def get_pollution(company):
    keys = [key for _m, _l, indicators in POLLUTION_MEDIA for key, _n in indicators]
    assets = owned_assets(company)
    by_asset, by_commodity = owned_asset_impacts(assets, keys)
    units = impact_units(keys)

    media = []
    for medium, label, indicators in POLLUTION_MEDIA:
        items = []
        for key, name in indicators:
            asset_rows = sorted(
                (
                    {'name': a.name, 'country': _country(a),
                     'value': significant(by_asset[a.pk][key]),
                     'year': by_asset[a.pk]['year']}
                    for a in assets if a.pk in by_asset and by_asset[a.pk][key] > 0
                ),
                key=lambda row: -row['value'],
            )
            commodity_rows = sorted(
                (
                    {'name': commodity, 'value': significant(values[key])}
                    for commodity, values in by_commodity.items() if values[key] > 0
                ),
                key=lambda row: -row['value'],
            )
            total = sum(by_asset[pk][key] for pk in by_asset)
            items.append({
                'key': key,
                'name': name,
                'unit': units[key],
                'total': significant(total) if total > 0 else None,
                'assets': asset_rows,
                'commodities': commodity_rows,
            })
        media.append({'key': medium, 'name': label, 'indicators': items})
    return {'asset_count': len(assets), 'media': media}


def get_resource_use(company):
    assets = owned_assets(company)
    asset_ids = [a.pk for a in assets]
    scarcity_keys = [key for key, _n in RESOURCE_SCARCITY]
    by_asset, _by_commodity = owned_asset_impacts(assets, scarcity_keys)
    units = impact_units(scarcity_keys)

    # Une requête par clé : latest_inventory retient une seule année par actif
    # pour l'ensemble des clés demandées, ce qui écarterait un déchet mesuré
    # une année plus tôt que l'eau.
    inventory = {
        key: (
            flow_service.latest_inventory(asset_ids, [key]),
            flow_service.latest_inventory_years(asset_ids, [key]),
        )
        for key, _n in RESOURCE_INVENTORY
    }

    rows = []
    for asset in assets:
        row = {'name': asset.name, 'country': _country(asset)}
        for key, _n in RESOURCE_INVENTORY:
            values, years = inventory[key]
            entry = values.get(asset.pk, {}).get(key)
            row[key] = (
                {'value': significant(entry['value']), 'year': years[asset.pk]}
                if entry else None
            )
        impact = by_asset.get(asset.pk)
        row['scarcity'] = (
            {key: significant(impact[key]) for key in scarcity_keys} if impact else None
        )
        row['scarcity_year'] = impact['year'] if impact else None
        rows.append(row)

    def _total(values):
        values = [v for v in values if v is not None]
        return significant(sum(values)) if values else None

    inventory_out = [{
        'key': key,
        'name': name,
        'unit': TECHNICAL_COMMODITIES[key][1],
        'total': _total(row[key]['value'] if row[key] else None for row in rows),
        # Seules les consommations sont déclarées au niveau du groupe.
        'declared_group': (
            flow_service.latest_declared_consumption(company, key)
            if key != 'waste' else None
        ),
    } for key, name in RESOURCE_INVENTORY]

    # Un total nul signifie « aucun facteur de caractérisation » : rendu None
    # pour ne pas afficher un zéro trompeur.
    scarcity_out = [{
        'key': key,
        'name': name,
        'unit': units[key],
        'total': _total(
            row['scarcity'][key] if row['scarcity'] else None for row in rows
        ) or None,
    } for key, name in RESOURCE_SCARCITY]

    return {'inventory': inventory_out, 'scarcity': scarcity_out, 'assets': rows}


def _supply_origin_country(flow):
    """Pays d'origine d'un approvisionnement, ou None s'il est inconnu."""
    if flow.from_asset_id:
        return flow.from_asset.country
    if flow.from_region_id:
        return flow.from_region.country
    return flow.from_country


def get_invasive_species(company):
    assets = owned_assets(company)
    asset_ids = [a.pk for a in assets]

    cultivated = {
        p.from_asset_id for p in flow_service.latest_productions(asset_ids)
        if p.what.biodiversity_loss_class == 'Agriculture'
    }
    imports = defaultdict(set)
    for flow in flow_service.supplies_to(asset_ids):
        origin = _supply_origin_country(flow)
        destination = flow.to_asset
        if origin is not None and destination is not None and origin.pk != destination.country_id:
            imports[destination.pk].add(origin.name)

    rows = []
    for asset in assets:
        origins = sorted(imports.get(asset.pk, ()))
        trade = bool(origins) or asset.type in IAS_TRANSPORT_TYPES
        if asset.pk in cultivated or asset.type in IAS_CULTIVATION_TYPES:
            activity = 'cultivation'
        elif asset.type in IAS_DISTURBANCE_TYPES:
            activity = 'disturbance'
        else:
            activity = None
        pathways = int(trade) + int(activity is not None)
        level = pathways
        # Un récepteur sensible aggrave l'exposition, sans en créer à lui seul.
        if pathways and asset.near_sensitive_zone:
            level += 1
        level = IAS_LEVELS[min(level, len(IAS_LEVELS) - 1)]
        rows.append({
            'name': asset.name,
            'country': _country(asset),
            'trade': trade,
            'trade_origins': origins,
            'activity': activity,
            'activity_label': IAS_ACTIVITY_LABELS.get(activity, ''),
            'sensitive': asset.near_sensitive_zone,
            'sensitive_label': (
                asset.get_sensitive_zone_type_display() or asset.sensitive_zone_name
                if asset.near_sensitive_zone else ''
            ),
            'level': level,
            'level_label': IAS_LEVEL_LABELS[level],
        })
    rows.sort(key=lambda row: (-IAS_LEVELS.index(row['level']), row['name']))
    return {
        'assets': rows,
        'counts': {
            'screened': len(rows),
            'high': sum(1 for row in rows if row['level'] == 'high'),
            'with_pathway': sum(1 for row in rows if row['trade'] or row['activity']),
            'sensitive': sum(1 for row in rows if row['sensitive']),
        },
    }
