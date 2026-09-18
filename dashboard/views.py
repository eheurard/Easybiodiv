import json
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .models import (
    Asset, Carbon_emission, Company, Company_Policy,
    Company_Revenue, Company_Revenue_Sector, Currency, DisclosureRequirement,
    E4Assessment, Ownership, Portfolio, PortfolioHolding,
)
from .forms import StressTestForm, PortfolioForm, PortfolioHoldingForm
from .services.market import get_market_data, DEFAULT_RANGE
from .services.impacts import build_cf_index, cf_value, CAT_ECOSYSTEM_DIVERSITY
from .services.supply import TIER_LABELS, TIER_TO_SCOPE
from .services.hazards import PHYSICAL_RISKS
from .services.stress_test import get_stress_test_data
from .services import flows as flow_service

from .compliance_catalog import APPLICABLE_DRS, DR_CATALOG

DR_STATUS_LABELS = {s.value: s.label for s in DisclosureRequirement.Status}
LEAP_STATUS_LABELS = {s.value: s.label for s in E4Assessment.LeapStatus}
MATERIALITY_LABELS = {s.value: s.label for s in E4Assessment.Materiality}


SCORE_MAP = {'VL': 0.0, 'L': 0.2, 'M': 0.5, 'H': 0.7, 'VH': 1.0}

SERVICES = [
    {'key': 'water',                'name': 'Approvisionnement en eau', 'category': 'provisioning'},
    {'key': 'soil_quality',         'name': 'Qualité des sols',         'category': 'provisioning'},
    {'key': 'carbon_sequestration', 'name': 'Séquestration carbone',    'category': 'regulation'},
    {'key': 'water_purification',   'name': "Épuration de l'eau",       'category': 'regulation'},
    {'key': 'pest_control',         'name': 'Contrôle des ravageurs',   'category': 'regulation'},
    {'key': 'pollination',          'name': 'Pollinisation',            'category': 'regulation'},
]

_COMMODITY_DEP_FIELDS = {
    'water':                'dependency_water',
    'soil_quality':         'dependency_soil_quality',
    'carbon_sequestration': 'dependency_carbon_sequestration',
    'water_purification':   'dependency_water_purification',
    'pest_control':         'dependency_pest_control',
    'pollination':          'dependency_pollination',
}

_SUBSECTOR_DEP_FIELDS = {
    'water':                'Water_dependency',
    'soil_quality':         'Soil_quality_dependency',
    'carbon_sequestration': 'Carbon_Sequestration',
    'water_purification':   'Water_purification_dependency',
    'pest_control':         'Pest_control_dependency',
    'pollination':          'Pollination_dependency',
}

# Inventaire mesuré affiché (informatif) sur la vue risque : sous-ensemble de flux.
_RISK_INVENTORY_KEYS = ('water', 'co2', 'surface_area')
_RISK_INVENTORY_LABELS = {
    'water': 'Consommation eau',
    'co2': 'Émissions CO₂',
    'surface_area': 'Usage des sols',
}


def _exposure_label(score):
    if score >= 0.7:
        return 'Critical'
    if score >= 0.5:
        return 'High'
    if score >= 0.2:
        return 'Moderate'
    return 'Low'


def _commodity_dep_scores(commodity):
    return {svc['key']: SCORE_MAP[getattr(commodity, _COMMODITY_DEP_FIELDS[svc['key']])]
            for svc in SERVICES}


def _get_dependencies_data(company):
    empty = {
        'company_id': company.pk,
        'company_name': company.name,
        'year': None,
        'global_exposure_score': 0,
        'critical_nodes': 0,
        'primary_service': None,
        'supply_chain': [],
        'service_exposure': {'total_revenue': None, 'currency': None, 'categories': []},
        'revenue_segments': [],
    }

    all_productions = flow_service.company_productions(company)
    if not all_productions:
        return empty

    max_year = max(p.year for p in all_productions)
    productions = [p for p in all_productions if p.year == max_year]

    # --- KPIs ---
    all_scores = []
    critical_nodes = set()
    service_totals = {svc['key']: [] for svc in SERVICES}

    for p in productions:
        scores = _commodity_dep_scores(p.what)
        all_scores.extend(scores.values())
        for key, val in scores.items():
            service_totals[key].append(val)
        if any(v >= 0.7 for v in scores.values()):
            critical_nodes.add((p.what_id, p.tier))

    global_score = sum(all_scores) / len(all_scores) if all_scores else 0

    service_avgs = {
        key: (sum(vals) / len(vals) if vals else 0)
        for key, vals in service_totals.items()
    }

    primary_key = max(service_avgs, key=service_avgs.get)
    primary_svc = next(s for s in SERVICES if s['key'] == primary_key)

    # --- Supply Chain ---
    scope_groups = defaultdict(list)
    for p in productions:
        scope_groups[p.tier].append(_commodity_dep_scores(p.what))

    supply_chain = []
    for tier in sorted(scope_groups):
        if tier not in TIER_TO_SCOPE:
            continue
        group = scope_groups[tier]
        scope = TIER_TO_SCOPE[tier]
        svc_avgs = {
            svc['key']: sum(s[svc['key']] for s in group) / len(group)
            for svc in SERVICES
        }
        services_out = []
        for svc in sorted(SERVICES, key=lambda s: -svc_avgs[s['key']]):
            score = svc_avgs[svc['key']]
            if score < 0.2:
                continue
            services_out.append({
                'key': svc['key'],
                'name': svc['name'],
                'score': round(score, 3),
                'label': _exposure_label(score),
            })
            if len(services_out) == 4:
                break
        if services_out:
            supply_chain.append({
                'scope': scope,
                'label': TIER_LABELS[tier],
                'services': services_out,
            })

    # --- Service Exposure ---
    revenue_obj = (
        Company_Revenue.objects.filter(company=company).order_by('-year').first()
    )
    total_revenue = revenue_obj.revenue if revenue_obj else None
    currency = revenue_obj.currency if revenue_obj else None

    categories = []
    for cat_name, cat_keys in [
        ('Services de provisionnement', ['water', 'soil_quality']),
        ('Services de régulation',      ['carbon_sequestration', 'water_purification',
                                          'pest_control', 'pollination']),
    ]:
        svcs_out = []
        for key in cat_keys:
            score = service_avgs[key]
            svc_info = next(s for s in SERVICES if s['key'] == key)
            svcs_out.append({
                'key': key,
                'name': svc_info['name'],
                'score': round(score, 3),
                'revenue_exposure': (
                    round(score * total_revenue) if total_revenue is not None else None
                ),
            })
        categories.append({'name': cat_name, 'services': svcs_out})

    # --- Revenue Segments (grouped by sector) ---
    rev_sector_qs = (
        Company_Revenue_Sector.objects.filter(company=company)
        .select_related('subsector__sector')
        .order_by('subsector_id', '-year')
    )
    seen = {}
    for rs in rev_sector_qs:
        if rs.subsector_id not in seen:
            seen[rs.subsector_id] = rs

    sector_groups = defaultdict(list)
    for rs in seen.values():
        sub = rs.subsector
        scores = {svc['key']: SCORE_MAP[getattr(sub, _SUBSECTOR_DEP_FIELDS[svc['key']])]
                  for svc in SERVICES}
        dep_score = sum(scores.values()) / len(scores)
        sector_groups[sub.sector.name].append({
            'subsector': sub.name,
            'revenue': rs.revenue,
            'dep_score': round(dep_score, 3),
            'revenue_at_risk': round(dep_score * rs.revenue),
            'exposure_label': _exposure_label(dep_score),
            'services': [
                {
                    'key': svc['key'],
                    'name': svc['name'],
                    'score': round(scores[svc['key']], 3),
                    'label': _exposure_label(scores[svc['key']]),
                }
                for svc in SERVICES
            ],
        })

    revenue_segments = []
    for sector_name, subsectors in sector_groups.items():
        total_revenue = sum(s['revenue'] for s in subsectors)
        avg_dep_score = sum(s['dep_score'] for s in subsectors) / len(subsectors)
        revenue_segments.append({
            'sector': sector_name,
            'revenue': total_revenue,
            'dep_score': round(avg_dep_score, 3),
            'revenue_at_risk': round(avg_dep_score * total_revenue),
            'exposure_label': _exposure_label(avg_dep_score),
            'subsectors': sorted(subsectors, key=lambda x: -x['revenue']),
        })
    revenue_segments.sort(key=lambda x: -x['revenue'])

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'year': max_year,
        'global_exposure_score': round(global_score, 3),
        'critical_nodes': len(critical_nodes),
        'primary_service': {
            'key': primary_svc['key'],
            'name': primary_svc['name'],
            'score': round(service_avgs[primary_key], 3),
        },
        'supply_chain': supply_chain,
        'service_exposure': {
            'total_revenue': total_revenue,
            'currency': currency,
            'categories': categories,
        },
        'revenue_segments': revenue_segments,
    }


def _get_company_data(company):
    assets = list(
        Asset.objects.owned_by(company).select_related('country', 'subnational_region')
    )
    prods_by_asset = defaultdict(list)
    for p in flow_service.productions([a.pk for a in assets]):
        prods_by_asset[p.from_asset_id].append(p)

    cf_index = build_cf_index(
        commodity_ids=[p.what_id for prods in prods_by_asset.values() for p in prods],
        category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )

    country_names = set()
    commodity_names = set()
    region_names = set()
    # country_name -> {'asset_count': int, 'commodity_assets': {commodity_name: asset_count}}
    country_data = defaultdict(lambda: {'asset_count': 0, 'commodity_assets': defaultdict(int)})

    for asset in assets:
        asset_commodities = {p.what.name for p in prods_by_asset[asset.pk]}
        country_names.add(asset.country.name)
        if asset.subnational_region is not None:
            region_names.add(asset.subnational_region.name)
        commodity_names.update(asset_commodities)
        cd = country_data[asset.country.name]
        cd['asset_count'] += 1
        for c in asset_commodities:
            cd['commodity_assets'][c] += 1

    countries = []
    for country_name, cd in sorted(
        country_data.items(), key=lambda x: (-x[1]['asset_count'], x[0])
    ):
        countries.append({
            'name': country_name,
            'asset_count': cd['asset_count'],
            'commodities': [
                {'name': n, 'count': v}
                for n, v in sorted(cd['commodity_assets'].items(), key=lambda x: (-x[1], x[0]))
            ],
        })

    features = []
    for asset in assets:
        prods_all = prods_by_asset[asset.pk]
        latest_year = max((p.year for p in prods_all), default=None)
        recent_prods = [p for p in prods_all if p.year == latest_year] if latest_year else []

        footprint = sum(
            p.quantity * cf_value(
                cf_index, p.what_id, CAT_ECOSYSTEM_DIVERSITY,
                asset.subnational_region_id, asset.country_id,
            )
            for p in recent_prods
        )

        restoration_cost = (
            asset.subnational_region.restoration_cost_m2
            if asset.subnational_region
            else asset.country.restoration_cost_m2
        )
        dette_eco = 0.0
        for p in recent_prods:
            field = _BIODIV_LOSS_FIELDS.get(
                p.what.biodiversity_loss_class, 'biodiversity_loss_agriculture'
            )
            biodiv_loss = getattr(asset.country, field, 0.0)
            dette_eco += (
                biodiv_loss
                * restoration_cost
                * p.quantity
                * cf_value(
                    cf_index, p.what_id, CAT_ECOSYSTEM_DIVERSITY,
                    asset.subnational_region_id, asset.country_id,
                )
            )

        productions_data = [
            {
                'commodity': p.what.name,
                'quantity': round(p.quantity, 2),
                'unit': p.what.unit,
                'revenue': round(p.estimated_revenue or 0.0, 2),
            }
            for p in sorted(recent_prods, key=lambda x: -x.quantity)
        ]

        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [asset.longitude, asset.latitude],
            },
            'properties': {
                'name': asset.name,
                'type': asset.type,
                'country': asset.country.name,
                'commodities': ', '.join(sorted({p.what.name for p in prods_all})),
                'region': asset.subnational_region.name if asset.subnational_region else '',
                'year': latest_year,
                'productions': productions_data,
                'footprint': round(footprint, 6),
                'dette_eco': round(dette_eco, 2),
            },
        })

    # Policies grouped by type with average score
    policies_qs = (
        Company_Policy.objects
        .filter(company=company)
        .select_related('policy_level__subcategory__policy_type')
        .order_by(
            'policy_level__subcategory__policy_type__name',
            'policy_level__subcategory__name',
        )
    )
    type_groups = defaultdict(list)
    for cp in policies_qs:
        pl = cp.policy_level
        sub = pl.subcategory
        type_groups[sub.policy_type.name].append({
            'subcategory': sub.name,
            'level': pl.name,
            'score': pl.score,
        })

    policies = []
    for type_name, entries in sorted(type_groups.items()):
        scores = [e['score'] for e in entries if e['score'] is not None]
        policies.append({
            'type': type_name,
            'avg_score': round(sum(scores) / len(scores), 2) if scores else None,
            'entries': entries,
        })

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'asset_count': len(assets),
        'country_count': len(country_names),
        'commodity_count': len(commodity_names),
        'region_count': len(region_names),
        'countries': countries,
        'geojson': {'type': 'FeatureCollection', 'features': features},
        'policies': policies,
    }


def _get_mesure_empreinte_data(company):
    assets = list(
        Asset.objects.owned_by(company)
        .select_related('country')
        .distinct()
    )

    empty = {
        'company_id': company.pk,
        'company_name': company.name,
        'year': None,
        'total_impact': 0,
        'commodities': [],
        'assets': [],
        'countries': [],
        'sankey_links': [],
    }

    if not assets:
        return empty

    asset_ids = [a.pk for a in assets]

    productions = flow_service.latest_productions(asset_ids)
    if not productions:
        return empty

    # ref_year is the most recent data year across all assets (assets may contribute different years)
    ref_year = max(p.year for p in productions)

    cf_index = build_cf_index(
        commodity_ids=[p.what_id for p in productions],
        category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )

    commodity_impact = defaultdict(float)
    asset_impact = defaultdict(float)
    asset_meta = {}
    link_commodity_asset = defaultdict(float)

    for p in productions:
        asset = p.from_asset
        impact = p.quantity * cf_value(
            cf_index, p.what_id, CAT_ECOSYSTEM_DIVERSITY,
            asset.subnational_region_id, asset.country_id,
        )
        commodity_impact[p.what.name] += impact
        asset_impact[asset.pk] += impact
        asset_meta.setdefault(asset.pk, {'name': asset.name, 'country': asset.country.name})
        link_commodity_asset[(p.what.name, asset.pk)] += impact

    country_impact = defaultdict(float)
    for aid, imp in asset_impact.items():
        country_impact[asset_meta[aid]['country']] += imp

    total = sum(asset_impact.values())
    if total == 0:
        return {**empty, 'year': ref_year}

    def norm(v):
        return round(v / total, 4)

    commodities = sorted(
        [{'name': k, 'impact': round(v, 4), 'pct': norm(v)} for k, v in commodity_impact.items()],
        key=lambda x: -x['pct'],
    )
    assets_list = sorted(
        [
            {
                'id': aid,
                'name': asset_meta[aid]['name'],
                'country': asset_meta[aid]['country'],
                'impact': round(imp, 4),
                'pct': norm(imp),
            }
            for aid, imp in asset_impact.items()
        ],
        key=lambda x: -x['pct'],
    )
    countries = sorted(
        [{'name': k, 'impact': round(v, 4), 'pct': norm(v)} for k, v in country_impact.items()],
        key=lambda x: -x['pct'],
    )

    sankey_links = []
    for (cname, aid), imp in link_commodity_asset.items():
        sankey_links.append({
            'source': f'commodity:{cname}',
            'target': f'asset:{aid}',
            'value': norm(imp),
        })
    for aid, imp in asset_impact.items():
        sankey_links.append({
            'source': f'asset:{aid}',
            'target': f'country:{asset_meta[aid]["country"]}',
            'value': norm(imp),
        })
    for cname, imp in country_impact.items():
        sankey_links.append({
            'source': f'country:{cname}',
            'target': f'company:{company.pk}',
            'value': norm(imp),
        })

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'year': ref_year,
        'total_impact': round(total, 4),
        'commodities': commodities,
        'assets': assets_list,
        'countries': countries,
        'sankey_links': sankey_links,
    }


def _get_leap_locate_data(company):
    assets = list(
        Asset.objects.owned_by(company).select_related('country', 'subnational_region')
    )
    asset_ids = [a.pk for a in assets]
    recent_by_asset = defaultdict(list)
    for p in flow_service.latest_productions(asset_ids):
        recent_by_asset[p.from_asset_id].append(p)
    asset_id_set = set(asset_ids)

    # Part de détention actuelle de la société sélectionnée pour chaque asset.
    ownership_map = {
        o.asset_id: o.share_label
        for o in Ownership.objects.valid_in().filter(asset_id__in=asset_ids, company=company)
    }

    features = []
    for a in assets:
        # Données de production directe (opérations propres de la société).
        recent_prods = recent_by_asset[a.pk]

        productions = [
            {
                'commodity': p.what.name,
                'quantity': round(p.quantity, 2),
                'unit': p.what.unit,
                'revenue': round(p.estimated_revenue or 0.0, 2),
            }
            for p in sorted(recent_prods, key=lambda x: -x.quantity)
        ]
        revenue_total = round(sum(p.estimated_revenue or 0.0 for p in recent_prods), 2)
        asset_types = sorted({
            p.what.get_biodiversity_loss_class_display() for p in recent_prods
        })

        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [a.longitude, a.latitude]},
            'properties': {
                'name': a.name,
                'country': a.country.name,
                'region': a.subnational_region.name if a.subnational_region else '',
                'type': a.type,
                'asset_type': ', '.join(asset_types),
                'ownership': ownership_map.get(a.pk, ''),
                'productions': productions,
                'revenue_total': revenue_total,
            },
        })

    # Fournisseurs : flux SUPPLY vers un actif détenu (trait fournisseur → actif)
    # ou vers la société elle-même (point sans trait : elle n'a pas de
    # coordonnées). Dernière année connue de chaque destination.
    suppliers = {}          # 'asset-<pk>' / 'region-<pk>' -> Feature point
    supplier_links = []     # une LineString fournisseur -> asset par lien
    for flow in flow_service.supplies_to(asset_ids, company=company):
        if flow.from_asset_id:
            sup = flow.from_asset
            sup_id = f'asset-{sup.pk}'
            coords = [sup.longitude, sup.latitude]
            sup_name, sup_country = sup.name, sup.country.name
            sup_is_owned = sup.pk in asset_id_set
        elif flow.from_region_id:
            reg = flow.from_region
            sup_id = f'region-{reg.pk}'
            coords = [reg.Mean_X, reg.Mean_Y]
            sup_name, sup_country = reg.name, reg.country.name
            sup_is_owned = False
        else:
            continue  # pays ou entreprise d'origine : pas de coordonnées → ignoré

        # Un fournisseur qui est lui-même un asset affiché (détenu par la société)
        # garde son lien, mais pas de marqueur fournisseur en doublon.
        if not sup_is_owned:
            feat = suppliers.get(sup_id)
            if feat is None:
                feat = {
                    'type': 'Feature',
                    'geometry': {'type': 'Point', 'coordinates': coords},
                    'properties': {
                        'id': sup_id,
                        'name': sup_name,
                        'country': sup_country,
                        'commodities': [],
                    },
                }
                suppliers[sup_id] = feat
            commodities = feat['properties']['commodities']
            if flow.what.name not in commodities:
                commodities.append(flow.what.name)

        cons_asset = flow.to_asset
        if cons_asset is None:
            continue  # destination = la société : point fournisseur sans trait

        supplier_links.append({
            'type': 'Feature',
            'geometry': {
                'type': 'LineString',
                'coordinates': [coords, [cons_asset.longitude, cons_asset.latitude]],
            },
            'properties': {
                'supplier': sup_name,
                'asset': cons_asset.name,
                'commodity': flow.what.name,
            },
        })

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'geojson': {'type': 'FeatureCollection', 'features': features},
        'suppliers': {'type': 'FeatureCollection', 'features': list(suppliers.values())},
        'supplier_links': {'type': 'FeatureCollection', 'features': supplier_links},
    }


# Impacts midpoint ReCiPe 2016 portés par les commodités : étiquettes FR pour la
# phase LEAP Evaluate (classement + sélecteur de dimensionnement des points).
_EVALUATE_IMPACT_FIELDS = [
    ('impact_midpoint_ReCiPe2016_water_consumption',          'Consommation eau'),
    ('impact_midpoint_ReCiPe2016_climate_change',             'Changement climatique'),
    ('impact_midpoint_ReCiPe2016_freshwater_ecotoxicity',     'Écotoxicité eau douce'),
    ('impact_midpoint_ReCiPe2016_freshwater_eutrophication',  'Eutrophisation eau douce'),
    ('impact_midpoint_ReCiPe2016_marine_eutrophication',      'Eutrophisation marine'),
    ('impact_midpoint_ReCiPe2016_terrestrial_acidification',  'Acidification terrestre'),
    ('impact_midpoint_ReCiPe2016_soil_acidification',         'Acidification des sols'),
    ('impact_midpoint_ReCiPe2016_ozonedepletion',             "Appauvrissement de l'ozone"),
    ('impact_midpoint_ReCiPe2016_resource_depletion_fossil',  'Épuisement ressources fossiles'),
    ('impact_midpoint_ReCiPe2016_resource_depletion_minerals','Épuisement ressources minérales'),
    ('impact_midpoint_ReCiPe2016_land_use',                   'Utilisation des terres'),
]


def _get_leap_evaluate_data(company):
    assets = list(
        Asset.objects.owned_by(company)
        .select_related('country', 'subnational_region')
        .distinct()
    )
    asset_ids = [a.pk for a in assets]

    # Consommation mesurée : année d'inventaire la plus récente de chaque asset.
    inventory = flow_service.latest_inventory(asset_ids, ('water', 'co2', 'waste'))
    consumption = {
        asset_id: {key: entry['value'] for key, entry in entries.items()}
        for asset_id, entries in inventory.items()
    }

    # Productions de l'année la plus récente de chaque asset.
    productions = flow_service.latest_productions(asset_ids)

    _evaluate_keys = [f for f, _ in _EVALUATE_IMPACT_FIELDS]
    asset_loc = {a.pk: (a.subnational_region_id, a.country_id) for a in assets}
    cf_index = build_cf_index(
        commodity_ids=[p.what_id for p in productions],
        category_keys=_evaluate_keys,
    )

    # Somme des impacts midpoint par asset : production × facteur de la commodité.
    asset_impacts = defaultdict(lambda: {f: 0.0 for f, _ in _EVALUATE_IMPACT_FIELDS})
    for p in productions:
        ai = asset_impacts[p.from_asset_id]
        region_id, country_id = asset_loc.get(p.from_asset_id, (None, None))
        for f in _evaluate_keys:
            ai[f] += p.quantity * cf_value(
                cf_index, p.what_id, f, region_id, country_id,
            )

    assets_out = []
    for a in assets:
        cons = consumption.get(a.pk, {})
        ai = asset_impacts.get(a.pk, {f: 0.0 for f, _ in _EVALUATE_IMPACT_FIELDS})
        assets_out.append({
            'id': a.pk,
            'name': a.name,
            'latitude': a.latitude,
            'longitude': a.longitude,
            'country': a.country.name,
            'water_consumption': round(cons.get('water', 0.0), 2),
            'co2_emissions': round(cons.get('co2', 0.0), 2),
            'waste_generated': round(cons.get('waste', 0.0), 2),
            'near_sensitive_zone': a.near_sensitive_zone,
            'sensitive_zone_type': (
                a.get_sensitive_zone_type_display() if a.sensitive_zone_type else ''
            ),
            'impacts': {f: round(ai[f], 4) for f, _ in _EVALUATE_IMPACT_FIELDS},
        })

    impacts = []
    for f, label in _EVALUATE_IMPACT_FIELDS:
        total = sum(asset_impacts[a.pk][f] for a in assets)
        impacts.append({'key': f, 'name': label, 'total': round(total, 4)})
    impacts.sort(key=lambda x: -x['total'])

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'impacts': impacts,
        'assets': assets_out,
    }


def _get_leap_prepare_data(company):
    assets = list(Asset.objects.owned_by(company))
    prods_by_asset = defaultdict(list)
    for p in flow_service.productions([a.pk for a in assets]):
        prods_by_asset[p.from_asset_id].append(p)

    all_commodity_ids = [p.what_id for prods in prods_by_asset.values() for p in prods]
    cf_index = build_cf_index(
        commodity_ids=all_commodity_ids, category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )

    commodities = {}
    assets_out = []
    years = []
    for a in assets:
        prods = prods_by_asset[a.pk]
        latest = max((p.year for p in prods), default=None)
        if latest is None:
            continue
        years.append(latest)

        line_qty = defaultdict(float)
        line_unit = {}
        for p in prods:
            if p.year != latest:
                continue
            c = p.what
            commodities.setdefault(c.pk, {
                'id': c.pk,
                'name': c.name,
                'impact_factor': cf_value(
                    cf_index, c.pk, CAT_ECOSYSTEM_DIVERSITY,
                ),
            })
            line_qty[c.pk] += p.quantity
            line_unit[c.pk] = c.unit

        lines = [
            {'commodity_id': cid, 'qty': round(q, 4), 'unit': line_unit[cid]}
            for cid, q in line_qty.items()
        ]
        if lines:
            assets_out.append({'id': a.pk, 'name': a.name, 'lines': lines})

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'year': max(years) if years else None,
        'commodities': sorted(commodities.values(), key=lambda c: c['name']),
        'assets': sorted(assets_out, key=lambda a: a['name']),
    }


_BIODIV_LOSS_FIELDS = {
    'Agriculture':  'biodiversity_loss_agriculture',
    'Urbanisation': 'biodiversity_loss_urbanization',
    'Mining':       'biodiversity_loss_mining',
}


def _get_dette_ecologique_data(company):
    empty = {
        'company_id': company.pk,
        'company_name': company.name,
        'year': None,
        'total_lbiodiv': 0,
        'commodities': [],
        'assets': [],
        'regions': [],
    }

    assets = list(
        Asset.objects.owned_by(company)
        .select_related('country', 'subnational_region')
        .distinct()
    )
    assets = [a for a in assets if a.subnational_region_id is not None]

    if not assets:
        return empty

    asset_ids = [a.pk for a in assets]

    productions = flow_service.latest_productions(asset_ids)
    if not productions:
        return empty

    ref_year = max(p.year for p in productions)

    cf_index = build_cf_index(
        commodity_ids=[p.what_id for p in productions],
        category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )

    asset_map = {a.pk: a for a in assets}
    asset_comm = defaultdict(lambda: defaultdict(float))
    global_comm = defaultdict(float)

    for p in productions:
        asset = asset_map.get(p.from_asset_id)
        if asset is None:
            continue
        field = _BIODIV_LOSS_FIELDS.get(
            p.what.biodiversity_loss_class, 'biodiversity_loss_agriculture'
        )
        biodiv_loss = getattr(asset.country, field, 0.0)
        restoration = asset.subnational_region.restoration_cost_m2
        lbiodiv = (
            biodiv_loss
            * restoration
            * p.quantity
            * cf_value(
                cf_index, p.what_id, CAT_ECOSYSTEM_DIVERSITY,
                asset.subnational_region_id, asset.country_id,
            )
        )
        asset_comm[p.from_asset_id][p.what.name] += lbiodiv
        global_comm[p.what.name] += lbiodiv

    total = sum(global_comm.values())
    if total == 0:
        return {**empty, 'year': ref_year}

    commodities = sorted(
        [{'name': k, 'lbiodiv': round(v, 4), 'pct': round(v / total, 4)}
         for k, v in global_comm.items()],
        key=lambda x: -x['lbiodiv'],
    )

    assets_out = []
    for asset in assets:
        ac = asset_comm.get(asset.pk, {})
        asset_total = sum(ac.values())
        if asset_total == 0:
            continue
        assets_out.append({
            'id': asset.pk,
            'name': asset.name,
            'latitude': asset.latitude,
            'longitude': asset.longitude,
            'total_lbiodiv': round(asset_total, 4),
            'pct': round(asset_total / total, 4),
            'commodities': sorted(
                [{'name': k, 'lbiodiv': round(v, 4), 'pct': round(v / asset_total, 4)}
                 for k, v in ac.items()],
                key=lambda x: -x['lbiodiv'],
            ),
        })
    assets_out.sort(key=lambda x: -x['total_lbiodiv'])

    region_comm = defaultdict(lambda: defaultdict(float))
    region_meta = {}
    for asset in assets:
        reg = asset.subnational_region
        if reg is None:
            continue
        region_meta[reg.pk] = reg
        for comm_name, val in asset_comm.get(asset.pk, {}).items():
            region_comm[reg.pk][comm_name] += val

    regions_out = []
    for reg_pk, reg in region_meta.items():
        rc = region_comm[reg_pk]
        reg_total = sum(rc.values())
        if reg_total == 0:
            continue
        regions_out.append({
            'id': reg.pk,
            'name': reg.name,
            'latitude': reg.Mean_Y,
            'longitude': reg.Mean_X,
            'total_lbiodiv': round(reg_total, 4),
            'pct': round(reg_total / total, 4),
            'commodities': sorted(
                [{'name': k, 'lbiodiv': round(v, 4), 'pct': round(v / reg_total, 4)}
                 for k, v in rc.items()],
                key=lambda x: -x['lbiodiv'],
            ),
        })
    regions_out.sort(key=lambda x: -x['total_lbiodiv'])

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'year': ref_year,
        'total_lbiodiv': round(total, 4),
        'commodities': commodities,
        'assets': assets_out,
        'regions': regions_out,
    }


def _get_physical_risk_data(company):
    assets = list(
        Asset.objects.owned_by(company)
        .select_related('country')
        .distinct()
    )

    # --- Vulnerability: mean of vulnerability_<key> across the company's policies ---
    levels = [
        cp.policy_level
        for cp in Company_Policy.objects.filter(company=company)
        .select_related('policy_level__subcategory__policy_type')
        if cp.policy_level_id
    ]

    def _vuln(key):
        vals = [getattr(level, f'vulnerability_{key}') for level in levels]
        return sum(vals) / len(vals) if vals else 1.0

    vulnerabilities = {r['key']: _vuln(r['key']) for r in PHYSICAL_RISKS}

    def _vuln_detail(key):
        return [
            {
                'policy': f"{level.subcategory.name} — {level.name}",
                'value': round(getattr(level, f'vulnerability_{key}'), 4),
            }
            for level in levels
        ]

    # --- Exposition: sum of estimated_revenue for each asset's latest production year ---
    asset_ids = [a.pk for a in assets]

    # Inventaire mesuré (informatif) : flux du sous-ensemble, année d'inventaire la
    # plus récente de l'asset, valeurs non nulles. N'entre PAS dans la perte.
    inventory = flow_service.latest_inventory(asset_ids, _RISK_INVENTORY_KEYS)

    def _inventory_for(asset_id):
        entries = inventory.get(asset_id, {})
        return [
            {
                'name': _RISK_INVENTORY_LABELS[key],
                'value': round(entries[key]['value'], 2),
                'unit': entries[key]['unit'],
            }
            for key in _RISK_INVENTORY_KEYS
            if key in entries and entries[key]['value']
        ]

    exposition = defaultdict(float)
    for p in flow_service.latest_productions(asset_ids):
        exposition[p.from_asset_id] += p.estimated_revenue or 0.0

    # --- Per-asset payload + KPI accumulation ---
    assets_out = []
    assets_high_risk = 0
    annual_loss = 0.0
    risk_cache = {}
    for a in assets:
        risk_vals = {r['key']: getattr(a, f"risk_{r['key']}") for r in PHYSICAL_RISKS}
        risk_cache[a.pk] = risk_vals
        expo = exposition.get(a.pk, 0.0)
        if max(risk_vals.values()) >= 0.7:
            assets_high_risk += 1
        for key, hazard in risk_vals.items():
            annual_loss += hazard * expo * vulnerabilities[key]
        assets_out.append({
            'id': a.pk,
            'name': a.name,
            'latitude': a.latitude,
            'longitude': a.longitude,
            'country': a.country.name,
            'exposition': round(expo, 2),
            'risk': {k: round(v, 4) for k, v in risk_vals.items()},
            'inventory': _inventory_for(a.pk),
        })

    # --- Hazard ranking (also drives the client-side selector) ---
    n_assets = len(assets)
    hazards = []
    for r in PHYSICAL_RISKS:
        key = r['key']
        total = sum(
            risk_cache[a.pk][key] * exposition.get(a.pk, 0.0) * vulnerabilities[key]
            for a in assets
        )
        hazards.append({
            'key': key,
            'name': r['name'],
            'group': r['group'],
            'vulnerability': round(vulnerabilities[key], 4),
            'vulnerability_detail': _vuln_detail(key),
            'avg_risk': round(total / n_assets, 2) if n_assets else 0.0,
        })
    hazards.sort(key=lambda h: -h['avg_risk'])

    avg_vulnerability = sum(vulnerabilities.values()) / len(PHYSICAL_RISKS)

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'kpis': {
            'assets_high_risk': assets_high_risk,
            'avg_vulnerability': round(avg_vulnerability, 4),
            'annual_loss': round(annual_loss, 2),
        },
        'hazards': hazards,
        'assets': assets_out,
    }


_IMPACT_FIELDS = [
    ('impact_midpoint_ReCiPe2016_water_consumption',          'Conso. eau (ReCiPe midpoint)'),
    ('impact_midpoint_ReCiPe2016_climate_change',             'Changement climatique (ReCiPe)'),
    ('impact_midpoint_ReCiPe2016_freshwater_ecotoxicity',     'Écotoxicité eau douce (ReCiPe)'),
    ('impact_midpoint_ReCiPe2016_freshwater_eutrophication',  'Eutrophisation eau douce (ReCiPe)'),
    ('impact_midpoint_ReCiPe2016_marine_eutrophication',      'Eutrophisation marine (ReCiPe)'),
    ('impact_midpoint_ReCiPe2016_terrestrial_acidification',  'Acidification terrestre (ReCiPe)'),
    ('impact_midpoint_ReCiPe2016_soil_acidification',         'Acidification sols (ReCiPe)'),
    ('impact_midpoint_ReCiPe2016_ozonedepletion',             'Dépletion ozone (ReCiPe)'),
    ('impact_midpoint_ReCiPe2016_resource_depletion_fossil',  'Dépletion fossile (ReCiPe)'),
    ('impact_midpoint_ReCiPe2016_resource_depletion_minerals','Dépletion minéraux (ReCiPe)'),
    ('impact_midpoint_ReCiPe2016_land_use',                   "Utilisation des terres (ReCiPe)"),
    ('impact_endpoint_ReCiPe2016_human_health',               'Santé humaine (ReCiPe endpoint)'),
    ('impact_endpoint_ReCiPe2016_ecosystem_diversity',        'Diversité écosystèmes (ReCiPe endpoint)'),
    ('impact_endpoint_ReCiPe2016_resource_availability',      'Disponibilité ressources (ReCiPe endpoint)'),
    ('impact_endpoint_GBS_terrestrial_dynamic',               'Terrestre dynamique (GBS endpoint)'),
    ('impact_endpoint_GBS_terrestrial_static',                'Terrestre statique (GBS endpoint)'),
]

_DEPENDENCY_FIELDS = [
    ('dependency_water',                "Dépendance eau"),
    ('dependency_pollination',          'Dépendance pollinisation'),
    ('dependency_soil_quality',         'Dépendance qualité sols'),
    ('dependency_carbon_sequestration', 'Dépendance séquestration carbone'),
    ('dependency_water_purification',   "Dépendance épuration eau"),
    ('dependency_pest_control',         'Dépendance contrôle ravageurs'),
]

METRICS = (
    [
        {'key': 'number_of_assets', 'label': "Nombre d'actifs"},
        {'key': 'total_lbiodiv',    'label': 'Dette écologique (L biodiv)'},
    ]
    + [{'key': f'total_{f}', 'label': label} for f, label in _IMPACT_FIELDS]
    + [{'key': f'avg_{f}',   'label': label} for f, label in _DEPENDENCY_FIELDS]
)


def _get_comparison_data(company):
    assets = list(
        Asset.objects.owned_by(company)
        .select_related('country', 'subnational_region')
        .distinct()
    )
    asset_ids = [a.pk for a in assets]

    result = {
        'company_id': company.pk,
        'company_name': company.name,
        'number_of_assets': len(assets),
        'total_lbiodiv': 0,
        **{f'total_{f}': 0 for f, _ in _IMPACT_FIELDS},
        **{f'avg_{f}': 0  for f, _ in _DEPENDENCY_FIELDS},
    }
    productions = flow_service.latest_productions(asset_ids)
    if not productions:
        return result

    _impact_keys = [f for f, _ in _IMPACT_FIELDS]
    cf_index = build_cf_index(
        commodity_ids=[p.what_id for p in productions],
        category_keys=_impact_keys,
    )

    asset_map     = {a.pk: a for a in assets}
    impact_totals = {f: 0.0 for f, _ in _IMPACT_FIELDS}
    dep_scores    = {f: []  for f, _ in _DEPENDENCY_FIELDS}
    total_lbiodiv = 0.0

    for p in productions:
        asset = asset_map.get(p.from_asset_id)
        for f in _impact_keys:
            impact_totals[f] += p.quantity * cf_value(
                cf_index, p.what_id, f,
                asset.subnational_region_id if asset else None,
                asset.country_id if asset else None,
            )
        for f, _ in _DEPENDENCY_FIELDS:
            dep_scores[f].append(SCORE_MAP.get(getattr(p.what, f, 'VL'), 0.0))

        if asset and asset.subnational_region:
            biodiv_field = _BIODIV_LOSS_FIELDS.get(
                p.what.biodiversity_loss_class, 'biodiversity_loss_agriculture'
            )
            total_lbiodiv += (
                getattr(asset.country, biodiv_field, 0.0)
                * asset.subnational_region.restoration_cost_m2
                * p.quantity
                * cf_value(
                    cf_index, p.what_id, CAT_ECOSYSTEM_DIVERSITY,
                    asset.subnational_region_id, asset.country_id,
                )
            )

    result['total_lbiodiv'] = round(total_lbiodiv, 4)
    for f, _ in _IMPACT_FIELDS:
        result[f'total_{f}'] = round(impact_totals[f], 4)
    for f, _ in _DEPENDENCY_FIELDS:
        sc = dep_scores[f]
        result[f'avg_{f}'] = round(sum(sc) / len(sc), 4) if sc else 0

    return result


def _compliance_suggestions(company, has_sensitive_sites):
    """Suggestions de statut dérivées des données existantes (indicatives)."""
    suggestions = {}
    if Company_Policy.objects.filter(company=company).exists():
        suggestions['E4_2'] = 'PARTIAL'
    if has_sensitive_sites:
        suggestions['E4_5'] = 'PARTIAL'
    return suggestions


def _build_disclosure_requirements(version, dr_state, suggestions):
    """Fusionne le catalogue réglementaire avec l'état DB des DR applicables."""
    out = []
    for code in APPLICABLE_DRS[version]:
        meta = DR_CATALOG[code]
        dr = dr_state.get(code)
        status = dr.status if dr else 'NOT_STARTED'
        out.append({
            'code': code,
            'code_label': code.replace('_', '-'),
            'title': meta['title'],
            'description': meta['description'],
            'reference': meta['reference'],
            'is_conditional': (code == 'E4_1' and version == 'AMENDED_2025'),
            'status': status,
            'status_label': DR_STATUS_LABELS[status],
            'justification': dr.justification if dr else '',
            'auto_suggestion': suggestions.get(code),
            'auto_suggestion_label': DR_STATUS_LABELS.get(suggestions.get(code)),
        })
    return out


def _build_leap(assessment, sensitive_sites_count, company):
    """Construit les 3 phases LEAP (statut/notes + résumé dérivé des données)."""
    dep = _get_dependencies_data(company)
    primary = dep.get('primary_service')
    emp = _get_mesure_empreinte_data(company)
    summaries = {
        'locate': f"{sensitive_sites_count} site(s) en/près d'une zone sensible",
        'evaluate': (
            f"Dépendance principale : {primary['name']}"
            if primary else "Aucune dépendance évaluée"
        ),
        'assess': f"Empreinte écosystèmes : {emp.get('total_impact', 0)}",
    }
    phases = [
        ('locate', 'Locate', 'leap_locate_status', 'leap_locate_notes'),
        ('evaluate', 'Evaluate', 'leap_evaluate_status', 'leap_evaluate_notes'),
        ('assess', 'Assess', 'leap_assess_status', 'leap_assess_notes'),
    ]
    out = []
    for key, label, status_field, notes_field in phases:
        status = getattr(assessment, status_field) if assessment else 'TODO'
        notes = getattr(assessment, notes_field) if assessment else ''
        out.append({
            'phase': key,
            'label': label,
            'status': status,
            'status_label': LEAP_STATUS_LABELS[status],
            'notes': notes,
            'derived_summary': summaries[key],
        })
    return out


def _compliance_synthesis(drs):
    """Calcule le % de conformité et les comptes par statut sur les DR applicables."""
    counts = {s.value: 0 for s in DisclosureRequirement.Status}
    for d in drs:
        counts[d['status']] += 1
    applicable = [d for d in drs if d['status'] != 'NOT_APPLICABLE']
    score = sum(
        1.0 if d['status'] == 'COMPLIANT' else 0.5 if d['status'] == 'PARTIAL' else 0.0
        for d in applicable
    )
    pct = round(100 * score / len(applicable)) if applicable else 0
    return {
        'compliance_pct': pct,
        'counts_by_status': counts,
        'applicable_count': len(applicable),
    }


def _get_compliance_data(company):
    assessment = (
        E4Assessment.objects
        .filter(company=company)
        .order_by('-reporting_year', '-updated_at')
        .first()
    )

    sensitive_assets = list(
        Asset.objects.owned_by(company)
        .filter(near_sensitive_zone=True)
        .distinct()
    )
    e4_5_metric = {
        'sites_count': len(sensitive_assets),
        'total_area_ha': round(sum(a.sensitive_zone_area_ha for a in sensitive_assets), 2),
        'sites': [
            {
                'name': a.name,
                'zone_type': a.get_sensitive_zone_type_display() if a.sensitive_zone_type else '',
                'zone_name': a.sensitive_zone_name,
                'area_ha': round(a.sensitive_zone_area_ha, 2),
            }
            for a in sensitive_assets
        ],
    }

    suggestions = _compliance_suggestions(company, bool(sensitive_assets))

    if assessment is None:
        version = E4Assessment.StandardVersion.AMENDED_2025
        version_label = E4Assessment.StandardVersion.AMENDED_2025.label
        materiality_status = 'NOT_ASSESSED'
        materiality_justification = ''
        reporting_year = None
        dr_state = {}
    else:
        version = assessment.standard_version
        version_label = assessment.get_standard_version_display()
        materiality_status = assessment.materiality_status
        materiality_justification = assessment.materiality_justification
        reporting_year = assessment.reporting_year
        dr_state = {dr.code: dr for dr in assessment.disclosure_requirements.all()}

    if materiality_status == 'NOT_MATERIAL':
        drs = []
    else:
        drs = _build_disclosure_requirements(version, dr_state, suggestions)

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'configured': assessment is not None,
        'standard_version': version,
        'standard_version_label': version_label,
        'reporting_year': reporting_year,
        'materiality': {
            'status': materiality_status,
            'status_label': MATERIALITY_LABELS[materiality_status],
            'is_material': materiality_status == 'MATERIAL',
            'justification': materiality_justification,
        },
        'leap': _build_leap(assessment, len(sensitive_assets), company),
        'disclosure_requirements': drs,
        'synthesis': _compliance_synthesis(drs),
        'e4_5_metric': e4_5_metric,
    }


ESG_PROJECTION_END_YEAR = 2030


def _linear_projection(points, end_year):
    """Extrapolation linéaire (moindres carrés) des totaux annuels.

    `points` : liste de (year, total) triée par année croissante.
    Retourne [{'year', 'total'}] du dernier point historique (ancre) jusqu'à
    `end_year` inclus. Renvoie [] si moins de 2 points ou pente indéfinie.
    """
    if len(points) < 2:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return []
    slope = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n)) / denom
    intercept = mean_y - slope * mean_x
    last_year = xs[-1]
    out = [{'year': last_year, 'total': round(ys[-1], 2)}]
    for yr in range(last_year + 1, end_year + 1):
        val = slope * yr + intercept
        out.append({'year': yr, 'total': round(max(val, 0.0), 2)})
    return out


def _get_esg_carbon(company):
    emissions = Carbon_emission.objects.filter(company=company).order_by('year')
    by_year = defaultdict(lambda: {'total': 0.0, 'scopes': defaultdict(float)})
    for e in emissions:
        by_year[e.year]['total'] += e.carbon_emission
        by_year[e.year]['scopes'][e.scope] += e.carbon_emission

    historical = [
        {
            'year': y,
            'total': round(d['total'], 2),
            'scopes': {k: round(v, 2) for k, v in d['scopes'].items()},
        }
        for y, d in sorted(by_year.items())
    ]

    projection = _linear_projection(
        [(h['year'], h['total']) for h in historical], ESG_PROJECTION_END_YEAR
    )

    if historical:
        first_total = historical[0]['total']
        latest = historical[-1]
        latest_year = latest['year']
        latest_total = latest['total']
        reduction_pct = (
            round((latest_total - first_total) / first_total * 100, 1)
            if first_total else None
        )
    else:
        latest_year = latest_total = reduction_pct = None

    return {
        'historical': historical,
        'projection': projection,
        'latest_year': latest_year,
        'latest_total': latest_total,
        'reduction_pct': reduction_pct,
        'unit': 'tCO2e',
    }


def _get_esg_policies(company):
    policies_qs = (
        Company_Policy.objects.filter(company=company)
        .select_related('policy_level__subcategory__policy_type')
    )
    items = []
    for cp in policies_qs:
        pl = cp.policy_level
        if pl is None:
            continue
        sub = pl.subcategory
        items.append({
            'type': sub.policy_type.name,
            'subcategory': sub.name,
            'level': pl.name,
            'description': pl.description,
            'score': pl.score,
            'date': cp.policy_date.isoformat() if cp.policy_date else None,
            'comment': cp.comment,
        })

    featured = sorted(
        items, key=lambda x: (x['score'] if x['score'] is not None else 0.0),
        reverse=True,
    )[:2]
    featured_out = [{
        'type': it['type'],
        'subcategory': it['subcategory'],
        'level': it['level'],
        'description': it['description'],
        'score': it['score'],
        'date': it['date'],
        'comment': it['comment'],
        'tags': [it['type'], it['level']],
    } for it in featured]

    framework = sorted(items, key=lambda x: (x['type'], x['subcategory']))
    framework_out = [{
        'type': it['type'],
        'subcategory': it['subcategory'],
        'level': it['level'],
        'score': it['score'],
        'date': it['date'],
    } for it in framework]

    return {'featured': featured_out, 'framework': framework_out}


def _get_esg_data(company):
    return {
        'company_id': company.pk,
        'company_name': company.name,
        'carbon': _get_esg_carbon(company),
        'policies': _get_esg_policies(company),
        'market': get_market_data(company),
        'news': [],
        'social': {'available': False},
        'governance': {'available': False},
    }


def index(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_company_data(first)
    return render(request, 'dashboard/index.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def company_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_company_data(company))


@require_GET
def esg(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_esg_data(first)
    return render(request, 'dashboard/esg.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def esg_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_esg_data(company))


@require_GET
def esg_market(request, pk):
    company = get_object_or_404(Company, pk=pk)
    market = get_market_data(company, request.GET.get('range', DEFAULT_RANGE))
    return JsonResponse({
        'range': market['range'],
        'sparkline': market['sparkline'],
        'change_pct': market['change_pct'],
        'is_demo': market['is_demo'],
    })


@require_GET
def mesure_empreinte(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_mesure_empreinte_data(first)
    return render(request, 'dashboard/mesure_empreinte.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def mesure_empreinte_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_mesure_empreinte_data(company))


@require_GET
def leap_locate(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_leap_locate_data(first)
    return render(request, 'dashboard/leap_locate.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def leap_locate_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_leap_locate_data(company))


@require_GET
def leap_evaluate(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_leap_evaluate_data(first)
    return render(request, 'dashboard/leap_evaluate.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def leap_evaluate_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_leap_evaluate_data(company))


@require_GET
def leap_prepare(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_leap_prepare_data(first)
    return render(request, 'dashboard/leap_prepare.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def leap_prepare_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_leap_prepare_data(company))


@require_GET
def dependencies(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_dependencies_data(first)
    return render(request, 'dashboard/dependencies.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def dependencies_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_dependencies_data(company))


@require_GET
def physical_risk(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_physical_risk_data(first)
    return render(request, 'dashboard/physical_risk.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def physical_risk_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_physical_risk_data(company))


@require_GET
def dette_ecologique(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_dette_ecologique_data(first)
    return render(request, 'dashboard/dette_ecologique.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def dette_ecologique_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_dette_ecologique_data(company))


@require_GET
def compare(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    return render(request, 'dashboard/compare.html', {
        'companies': companies,
        'metrics': METRICS,
    })


@require_GET
def compare_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_comparison_data(company))


@require_GET
def compliance(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_compliance_data(first)
    return render(request, 'dashboard/compliance.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def compliance_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_compliance_data(company))


@require_GET
def climate_stress_test(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = get_stress_test_data(first)
    return render(request, 'dashboard/climate_stress_test.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def climate_stress_test_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    form = StressTestForm(data=request.GET)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    return JsonResponse(get_stress_test_data(company, form.to_params()))


# ---------------------------------------------------------------------------
# Portfolio analysis
# ---------------------------------------------------------------------------


@login_required
@require_GET
def portfolio_analysis(request):
    """Coquille à onglets de la page Portfolio analysis (onglet Création + reports)."""
    companies = list(Company.objects.order_by('name').values(
        'id', 'name', 'isin', 'ticker',
    ))
    currencies = list(Currency.objects.order_by('code').values('id', 'code', 'symbol'))
    visible = Portfolio.objects.visible_to(request.user)
    benchmarks = list(
        visible.filter(is_benchmark=True).order_by('name').values('id', 'name')
    )
    portfolios = list(
        visible.filter(created_by=request.user).order_by('name').values('id', 'name')
    )
    shared_portfolios = list(
        visible.filter(is_shared=True).exclude(created_by=request.user)
        .order_by('name').values('id', 'name')
    )
    return render(request, 'dashboard/portfolio.html', {
        'companies': companies,
        'currencies': currencies,
        'benchmarks': benchmarks,
        'portfolios': portfolios,
        'shared_portfolios': shared_portfolios,
        'can_share': request.user.is_staff,
    })


def _visible_portfolio(request, pk):
    """Portefeuille lisible par l'utilisateur, sinon 404."""
    return get_object_or_404(Portfolio.objects.visible_to(request.user), pk=pk)


@login_required
@require_POST
def portfolio_save(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'errors': {'__all__': ['JSON invalide']}}, status=400)

    instance = None
    if payload.get('id'):
        instance = _visible_portfolio(request, payload['id'])
        if not instance.can_be_edited_by(request.user):
            return JsonResponse(
                {'errors': {'__all__': ['Portefeuille commun : lecture seule.']}},
                status=403,
            )

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
            errors['__all__'] = ["Une entreprise ne peut apparaître qu'une fois."]
        return JsonResponse({'errors': errors, 'holdings': holding_errors}, status=400)

    with transaction.atomic():
        portfolio = form.save(commit=False)
        portfolio.is_benchmark = bool(payload.get('is_benchmark'))
        # Le partage est un acte d'administration : un non-staff ne peut ni
        # rendre un portefeuille commun, ni retirer un partage existant.
        if request.user.is_staff:
            portfolio.is_shared = bool(payload.get('is_shared'))
        if portfolio.created_by_id is None:
            portfolio.created_by = request.user
        portfolio.save()
        portfolio.holdings.all().delete()
        for hf in holding_forms:
            holding = hf.save(commit=False)
            holding.portfolio = portfolio
            holding.save()

    return JsonResponse({'id': portfolio.pk, 'name': portfolio.name})


@login_required
@require_GET
def portfolio_detail(request, pk):
    portfolio = _visible_portfolio(request, pk)
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
        'is_shared': portfolio.is_shared,
        'can_edit': portfolio.can_be_edited_by(request.user),
        'holdings': holdings,
    })


@login_required
@require_POST
def portfolio_duplicate(request, pk):
    """Copie privée d'un portefeuille lisible, éditable par le demandeur."""
    source = _visible_portfolio(request, pk)
    with transaction.atomic():
        copy = Portfolio.objects.create(
            name=f'{source.name} (copie)'[:255],
            size=source.size,
            currency=source.currency,
            benchmark=source.benchmark,
            is_benchmark=False,
            is_shared=False,
            created_by=request.user,
        )
        PortfolioHolding.objects.bulk_create([
            PortfolioHolding(
                portfolio=copy,
                company_id=h.company_id,
                amount=h.amount,
                weight=h.weight,
                instrument_type=h.instrument_type,
                maturity_date=h.maturity_date,
                coupon_rate=h.coupon_rate,
                face_value=h.face_value,
            )
            for h in source.holdings.all()
        ])
    return JsonResponse({'id': copy.pk, 'name': copy.name})


# Méthodes d'impact endpoint exposées dans l'onglet Impact du portefeuille.
# (clé, libellé unité, clé de catégorie d'impact = colonne legacy)
PORTFOLIO_IMPACT_METRICS = [
    ('recipe', 'PDF.m²', 'impact_endpoint_ReCiPe2016_ecosystem_diversity'),
    ('gbs', 'MSA.km²', 'impact_endpoint_GBS_terrestrial_static'),
]


def _company_endpoint_impacts(company, category_keys):
    """Impact endpoint d'une entreprise pour chaque catégorie de `category_keys`.

    Pour chaque asset détenu par l'entreprise (via Ownership), on retient les
    productions de la dernière année disponible et on somme
    `production × CF(commodity, catégorie, région/pays)`. Le facteur de
    caractérisation est résolu via `services.impacts` (région → pays → global).
    Retourne {category_key: total}.
    """
    totals = {k: 0.0 for k in category_keys}
    asset_ids = list(Asset.objects.owned_by(company).values_list('pk', flat=True))
    productions = flow_service.latest_productions(asset_ids)
    if not productions:
        return totals
    cf_index = build_cf_index(
        commodity_ids=[p.what_id for p in productions],
        category_keys=category_keys,
    )
    for p in productions:
        for key in category_keys:
            totals[key] += p.quantity * cf_value(
                cf_index, p.what_id, key,
                p.from_asset.subnational_region_id, p.from_asset.country_id,
            )
    return totals


@login_required
@require_GET
def portfolio_impact(request, pk):
    """Impact financé d'un portefeuille : montant_investi × (impact / EVIC)."""
    portfolio = _visible_portfolio(request, pk)
    holdings = list(portfolio.holdings.select_related('company').all())

    keys = [key for _, _, key in PORTFOLIO_IMPACT_METRICS]
    per_company = {
        h.company_id: _company_endpoint_impacts(h.company, keys) for h in holdings
    }

    # EVIC le plus récent (> 0) pour chaque entreprise du portefeuille.
    company_ids = [h.company_id for h in holdings]
    evic_map = {}
    for rev in (
        Company_Revenue.objects
        .filter(company_id__in=company_ids, evic__gt=0)
        .order_by('company_id', '-year')
    ):
        if rev.company_id not in evic_map:
            evic_map[rev.company_id] = rev.evic

    metrics = {}
    for key, unit, cat_key in PORTFOLIO_IMPACT_METRICS:
        companies = []
        total = 0.0
        for h in holdings:
            impact = per_company[h.company_id][cat_key]
            evic = evic_map.get(h.company_id, 0.0)
            amount = h.amount or 0.0
            weight = h.weight or 0.0
            weighted = amount * (impact / evic) if evic > 0 else 0.0
            total += weighted
            companies.append({
                'name': h.company.name,
                'weight': round(weight, 4),
                'amount': round(amount, 2),
                'evic': round(evic, 2),
                'impact': round(impact, 4),
                'weighted': round(weighted, 4),
            })
        companies.sort(key=lambda c: -c['weighted'])
        metrics[key] = {'unit': unit, 'total': round(total, 4), 'companies': companies}

    return JsonResponse({'id': portfolio.pk, 'name': portfolio.name, 'metrics': metrics})


PHYSICAL_HAZARDS = [
    ('water_stress', 'Stress hydrique', 'risk_water_stress'),
    ('wildfire', 'Feux de forêt', 'risk_wildfire'),
    ('cyclone', 'Cyclone', 'risk_cyclone'),
    ('drought', 'Sécheresse', 'risk_drought'),
    ('flood', 'Inondation', 'risk_flood'),
    ('coastal_inundation', 'Submersion côtière', 'risk_coastal_inundation'),
    ('heatwave', 'Vague de chaleur', 'risk_heatwave'),
    ('temperature_variation', 'Variation de température', 'risk_temperature_variation'),
    ('precipitation_variation', 'Variation des précipitations',
     'risk_precipitation_variation'),
]


def _company_physical_risks(company):
    """Score de risque physique d'une entreprise par aléa.

    Poids d'un asset = somme des `estimated_revenue` de ses productions de la
    dernière année. Score d'un aléa = moyenne des `asset.<champ>` pondérée par ces
    poids ; repli moyenne simple si le revenu total est nul. {hazard_key: score}.
    """
    keys = [key for key, _, _ in PHYSICAL_HAZARDS]
    assets = list(Asset.objects.owned_by(company).distinct())
    if not assets:
        return {k: 0.0 for k in keys}

    asset_ids = [a.pk for a in assets]
    weights = {a.pk: 0.0 for a in assets}
    for p in flow_service.latest_productions(asset_ids):
        weights[p.from_asset_id] += p.estimated_revenue or 0.0

    total_w = sum(weights.values())
    scores = {}
    for key, _, field in PHYSICAL_HAZARDS:
        if total_w > 0:
            scores[key] = sum(
                weights[a.pk] * getattr(a, field) for a in assets
            ) / total_w
        else:
            scores[key] = sum(getattr(a, field) for a in assets) / len(assets)
    return scores


def _portfolio_physical_aggregate(holdings, per_company):
    """Liste des 9 scores agrégés, pondérés par `holding.amount` (4 décimales)."""
    keys = [key for key, _, _ in PHYSICAL_HAZARDS]
    total_amount = sum((h.amount or 0.0) for h in holdings)
    agg = []
    for key in keys:
        if total_amount > 0:
            v = sum(
                (h.amount or 0.0) * per_company[h.company_id][key] for h in holdings
            ) / total_amount
        else:
            v = 0.0
        agg.append(round(v, 4))
    return agg


@login_required
@require_GET
def portfolio_physical_risk(request, pk):
    """Profil de risque physique d'un portefeuille (pondéré par montant investi)."""
    portfolio = _visible_portfolio(request, pk)
    holdings = list(portfolio.holdings.select_related('company').all())
    keys = [key for key, _, _ in PHYSICAL_HAZARDS]

    per_company = {h.company_id: _company_physical_risks(h.company) for h in holdings}

    companies = []
    for h in holdings:
        scores = per_company[h.company_id]
        companies.append({
            'name': h.company.name,
            'amount': round(h.amount or 0.0, 2),
            'weight': round(h.weight or 0.0, 4),
            'scores': [round(scores[k], 4) for k in keys],
        })
    companies.sort(key=lambda c: -sum(c['scores']))

    benchmark = None
    if portfolio.benchmark_id:
        bench_holdings = list(
            portfolio.benchmark.holdings.select_related('company').all()
        )
        bench_per_company = {
            h.company_id: _company_physical_risks(h.company) for h in bench_holdings
        }
        benchmark = _portfolio_physical_aggregate(bench_holdings, bench_per_company)

    return JsonResponse({
        'id': portfolio.pk,
        'name': portfolio.name,
        'hazards': [{'key': k, 'label': label} for k, label, _ in PHYSICAL_HAZARDS],
        'portfolio': _portfolio_physical_aggregate(holdings, per_company),
        'benchmark': benchmark,
        'companies': companies,
    })


def _company_ecological_debt(company):
    """Dette écologique brute (Lbiodiv) d'une entreprise, ventilée par asset,
    région subnational et pays, et par commodité.

    Reprend la formule de `_get_dette_ecologique_data` (facteur de caractérisation
    résolu via `services.impacts`) : pour chaque asset détenu (via Ownership) ayant
    une `subnational_region`, on retient les productions de la dernière année et on
    accumule `Lbiodiv` par commodité dans l'asset, sa région et son pays. Les pays
    accumulent lat/long pour un centroïde calculé en aval.
    """
    result = {'assets': {}, 'regions': {}, 'countries': {}}

    assets = list(
        Asset.objects.owned_by(company)
        .select_related('country', 'subnational_region')
        .distinct()
    )
    assets = [a for a in assets if a.subnational_region_id is not None]
    if not assets:
        return result

    asset_ids = [a.pk for a in assets]
    productions = flow_service.latest_productions(asset_ids)
    if not productions:
        return result

    cf_index = build_cf_index(
        commodity_ids=[p.what_id for p in productions],
        category_keys=[CAT_ECOSYSTEM_DIVERSITY],
    )

    asset_map = {a.pk: a for a in assets}
    counted_country_assets = set()

    for p in productions:
        asset = asset_map.get(p.from_asset_id)
        if asset is None:
            continue
        field = _BIODIV_LOSS_FIELDS.get(
            p.what.biodiversity_loss_class, 'biodiversity_loss_agriculture'
        )
        biodiv_loss = getattr(asset.country, field, 0.0)
        restoration = asset.subnational_region.restoration_cost_m2
        lbiodiv = (
            biodiv_loss * restoration * p.quantity
            * cf_value(
                cf_index, p.what_id, CAT_ECOSYSTEM_DIVERSITY,
                asset.subnational_region_id, asset.country_id,
            )
        )
        name = p.what.name

        a_entry = result['assets'].setdefault(asset.pk, {
            'name': asset.name, 'latitude': asset.latitude,
            'longitude': asset.longitude, 'comm': defaultdict(float),
        })
        a_entry['comm'][name] += lbiodiv

        reg = asset.subnational_region
        r_entry = result['regions'].setdefault(reg.pk, {
            'name': reg.name, 'latitude': reg.Mean_Y, 'longitude': reg.Mean_X,
            'comm': defaultdict(float),
        })
        r_entry['comm'][name] += lbiodiv

        ctry = asset.country
        c_entry = result['countries'].setdefault(ctry.pk, {
            'name': ctry.name, 'lat_sum': 0.0, 'lng_sum': 0.0,
            'n': 0, 'comm': defaultdict(float),
        })
        c_entry['comm'][name] += lbiodiv
        if asset.pk not in counted_country_assets:
            c_entry['lat_sum'] += asset.latitude
            c_entry['lng_sum'] += asset.longitude
            c_entry['n'] += 1
            counted_country_assets.add(asset.pk)

    return result


def _portfolio_financed_debt(holdings, evic_map):
    """Dette écologique financée d'un portefeuille, prête à sérialiser.

    Pour chaque holding : f = amount / EVIC (si EVIC > 0, sinon 0). Multiplie la
    dette brute de l'entreprise (`_company_ecological_debt`) par f, somme à travers
    toutes les entreprises par (asset|région|pays, commodité). Retourne les trois
    listes au même format que `_get_dette_ecologique_data` + total et nb d'entreprises.
    """
    assets = {}
    regions = {}
    countries = {}
    global_comm = defaultdict(float)
    company_count = 0

    for h in holdings:
        evic = evic_map.get(h.company_id, 0.0)
        amount = h.amount or 0.0
        f = (amount / evic) if evic > 0 else 0.0
        if f == 0.0:
            continue
        debt = _company_ecological_debt(h.company)
        contributed = False

        for aid, a in debt['assets'].items():
            entry = assets.setdefault(aid, {
                'name': a['name'], 'latitude': a['latitude'],
                'longitude': a['longitude'], 'comm': defaultdict(float),
            })
            for name, val in a['comm'].items():
                entry['comm'][name] += f * val
                global_comm[name] += f * val
                contributed = contributed or (f * val) > 0

        for rid, r in debt['regions'].items():
            entry = regions.setdefault(rid, {
                'name': r['name'], 'latitude': r['latitude'],
                'longitude': r['longitude'], 'comm': defaultdict(float),
            })
            for name, val in r['comm'].items():
                entry['comm'][name] += f * val

        for cid, c in debt['countries'].items():
            entry = countries.setdefault(cid, {
                'name': c['name'], 'lat_sum': 0.0, 'lng_sum': 0.0,
                'n': 0, 'comm': defaultdict(float),
            })
            entry['lat_sum'] += c['lat_sum']
            entry['lng_sum'] += c['lng_sum']
            entry['n'] += c['n']
            for name, val in c['comm'].items():
                entry['comm'][name] += f * val

        if contributed:
            company_count += 1

    total = sum(global_comm.values())

    def _serialize_point(pid, name, lat, lng, comm):
        pt_total = sum(comm.values())
        return {
            'id': pid, 'name': name,
            'latitude': lat, 'longitude': lng,
            'total_lbiodiv': round(pt_total, 4),
            'pct': round(pt_total / total, 4) if total else 0.0,
            'commodities': sorted(
                [{'name': k, 'lbiodiv': round(v, 4),
                  'pct': round(v / pt_total, 4) if pt_total else 0.0}
                 for k, v in comm.items()],
                key=lambda x: -x['lbiodiv'],
            ),
        }

    assets_out = [
        _serialize_point(aid, a['name'], a['latitude'], a['longitude'], a['comm'])
        for aid, a in assets.items() if sum(a['comm'].values()) > 0
    ]
    assets_out.sort(key=lambda x: -x['total_lbiodiv'])

    regions_out = [
        _serialize_point(rid, r['name'], r['latitude'], r['longitude'], r['comm'])
        for rid, r in regions.items() if sum(r['comm'].values()) > 0
    ]
    regions_out.sort(key=lambda x: -x['total_lbiodiv'])

    countries_out = [
        _serialize_point(
            cid, c['name'],
            c['lat_sum'] / c['n'] if c['n'] else 0.0,
            c['lng_sum'] / c['n'] if c['n'] else 0.0,
            c['comm'],
        )
        for cid, c in countries.items() if sum(c['comm'].values()) > 0
    ]
    countries_out.sort(key=lambda x: -x['total_lbiodiv'])

    commodities = sorted(
        [{'name': k, 'lbiodiv': round(v, 4),
          'pct': round(v / total, 4) if total else 0.0}
         for k, v in global_comm.items() if v > 0],
        key=lambda x: -x['lbiodiv'],
    )

    return {
        'total_lbiodiv': round(total, 4),
        'company_count': company_count,
        'commodities': commodities,
        'assets': assets_out,
        'regions': regions_out,
        'countries': countries_out,
    }


@login_required
@require_GET
def portfolio_transition_risk(request, pk):
    """Risque de transition d'un portefeuille : dette écologique financée."""
    portfolio = _visible_portfolio(request, pk)
    holdings = list(portfolio.holdings.select_related('company').all())

    def _evic_map(hs):
        company_ids = [h.company_id for h in hs]
        out = {}
        for rev in (
            Company_Revenue.objects
            .filter(company_id__in=company_ids, evic__gt=0)
            .order_by('company_id', '-year')
        ):
            if rev.company_id not in out:
                out[rev.company_id] = rev.evic
        return out

    data = _portfolio_financed_debt(holdings, _evic_map(holdings))

    benchmark = None
    if portfolio.benchmark_id:
        bench_holdings = list(
            portfolio.benchmark.holdings.select_related('company').all()
        )
        bench = _portfolio_financed_debt(bench_holdings, _evic_map(bench_holdings))
        benchmark = {'total_lbiodiv': bench['total_lbiodiv']}

    return JsonResponse({
        'id': portfolio.pk,
        'name': portfolio.name,
        'total_lbiodiv': data['total_lbiodiv'],
        'company_count': data['company_count'],
        'commodities': data['commodities'],
        'assets': data['assets'],
        'regions': data['regions'],
        'countries': data['countries'],
        'benchmark': benchmark,
    })
