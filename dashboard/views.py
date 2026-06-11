from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from django.db.models import Q
from .models import Asset, Commodity, Company, Company_Policy, Company_Revenue, Company_Revenue_Sector, Ownership, Production


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

_SCOPE_LABELS = {
    'direct':       'Opérations directes',
    'tier 1':       "Tier 1 : Chaîne d'approvisionnement",
    'tier 2':       "Tier 2 : Approvisionnement amont",
    'raw material': 'Matières premières',
}

_SCOPE_ORDER = ['direct', 'tier 1', 'tier 2', 'raw material']

PHYSICAL_RISKS = [
    {'key': 'water', 'name': 'Eau', 'group': 'Services écosystémiques'},
    {'key': 'pollination', 'name': 'Pollinisation', 'group': 'Services écosystémiques'},
    {'key': 'soil_quality', 'name': 'Qualité des sols', 'group': 'Services écosystémiques'},
    {'key': 'carbon_sequestration', 'name': 'Séquestration carbone',
     'group': 'Services écosystémiques'},
    {'key': 'water_purification', 'name': "Épuration de l'eau",
     'group': 'Services écosystémiques'},
    {'key': 'pest_control', 'name': 'Contrôle des ravageurs',
     'group': 'Services écosystémiques'},
    {'key': 'water_stress', 'name': 'Stress hydrique', 'group': 'Aléas climatiques'},
    {'key': 'wildfire', 'name': 'Incendie', 'group': 'Aléas climatiques'},
    {'key': 'cyclone', 'name': 'Cyclone', 'group': 'Aléas climatiques'},
    {'key': 'drought', 'name': 'Sécheresse', 'group': 'Aléas climatiques'},
    {'key': 'flood', 'name': 'Inondation', 'group': 'Aléas climatiques'},
    {'key': 'coastal_inundation', 'name': 'Submersion côtière', 'group': 'Aléas climatiques'},
    {'key': 'heatwave', 'name': 'Canicule', 'group': 'Aléas climatiques'},
    {'key': 'temperature_variation', 'name': 'Variation de température',
     'group': 'Aléas climatiques'},
    {'key': 'precipitation_variation', 'name': 'Variation des précipitations',
     'group': 'Aléas climatiques'},
]


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

    productions_qs = Production.objects.filter(
        Q(company=company) | Q(asset__ownership__Company=company)
    ).select_related('commodity').distinct()

    max_year = productions_qs.aggregate(Max('year'))['year__max']
    if max_year is None:
        return empty

    productions = list(productions_qs.filter(year=max_year))

    # --- KPIs ---
    all_scores = []
    critical_nodes = set()
    service_totals = {svc['key']: [] for svc in SERVICES}

    for p in productions:
        scores = _commodity_dep_scores(p.commodity)
        all_scores.extend(scores.values())
        for key, val in scores.items():
            service_totals[key].append(val)
        if any(v >= 0.7 for v in scores.values()):
            critical_nodes.add((p.commodity_id, p.scope))

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
        scope_groups[p.scope].append(_commodity_dep_scores(p.commodity))

    supply_chain = []
    for scope in _SCOPE_ORDER:
        if scope not in scope_groups:
            continue
        group = scope_groups[scope]
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
                'label': _SCOPE_LABELS[scope],
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
        Asset.objects.filter(ownership__Company=company)
        .select_related('country', 'subnational_region')
        .prefetch_related('production_set__commodity')
        .distinct()
    )

    country_names = set()
    commodity_names = set()
    region_names = set()
    # country_name -> {'asset_count': int, 'commodity_assets': {commodity_name: asset_count}}
    country_data = defaultdict(lambda: {'asset_count': 0, 'commodity_assets': defaultdict(int)})

    for asset in assets:
        asset_commodities = {p.commodity.name for p in asset.production_set.all()}
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
        country_data.items(), key=lambda x: -x[1]['asset_count']
    ):
        countries.append({
            'name': country_name,
            'asset_count': cd['asset_count'],
            'commodities': [
                {'name': n, 'count': v}
                for n, v in sorted(cd['commodity_assets'].items(), key=lambda x: -x[1])
            ],
        })

    features = []
    for asset in assets:
        prods_all = list(asset.production_set.all())
        latest_year = max((p.year for p in prods_all), default=None)
        recent_prods = [p for p in prods_all if p.year == latest_year] if latest_year else []

        footprint = sum(
            p.production * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
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
                p.commodity.biodiversity_loss_class, 'biodiversity_loss_agriculture'
            )
            biodiv_loss = getattr(asset.country, field, 0.0)
            dette_eco += (
                biodiv_loss
                * restoration_cost
                * p.production
                * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
            )

        productions_data = [
            {
                'commodity': p.commodity.name,
                'quantity': round(p.production, 2),
                'unit': p.commodity.unit,
                'revenue': round(p.estimated_revenue, 2),
            }
            for p in sorted(recent_prods, key=lambda x: -x.production)
        ]

        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [asset.longitude, asset.latitude],
            },
            'properties': {
                'name': asset.name,
                'country': asset.country.name,
                'commodities': ', '.join(sorted({p.commodity.name for p in prods_all})),
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
        Asset.objects.filter(ownership__Company=company)
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

    latest_years = dict(
        Production.objects.filter(asset_id__in=asset_ids)
        .values('asset_id')
        .annotate(max_year=Max('year'))
        .values_list('asset_id', 'max_year')
    )

    if not latest_years:
        return empty

    # ref_year is the most recent data year across all assets (assets may contribute different years)
    ref_year = max(latest_years.values())

    productions = list(
        Production.objects.filter(asset_id__in=asset_ids)
        .select_related('commodity', 'asset__country')
    )
    productions = [p for p in productions if latest_years.get(p.asset_id) == p.year]

    commodity_impact = defaultdict(float)
    asset_impact = defaultdict(float)
    asset_meta = {}
    link_commodity_asset = defaultdict(float)

    for p in productions:
        impact = p.production * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
        commodity_impact[p.commodity.name] += impact
        asset_impact[p.asset_id] += impact
        asset_meta.setdefault(p.asset_id, {'name': p.asset.name, 'country': p.asset.country.name})
        link_commodity_asset[(p.commodity.name, p.asset_id)] += impact

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
        Asset.objects.filter(ownership__Company=company)
        .select_related('country', 'subnational_region')
        .distinct()
    )
    assets = [a for a in assets if a.subnational_region_id is not None]

    if not assets:
        return empty

    asset_ids = [a.pk for a in assets]

    latest_years = dict(
        Production.objects.filter(asset_id__in=asset_ids)
        .values('asset_id')
        .annotate(max_year=Max('year'))
        .values_list('asset_id', 'max_year')
    )
    if not latest_years:
        return empty

    ref_year = max(latest_years.values())

    productions = list(
        Production.objects.filter(asset_id__in=asset_ids)
        .select_related('commodity', 'asset__country', 'asset__subnational_region')
    )
    productions = [p for p in productions if latest_years.get(p.asset_id) == p.year]

    asset_map = {a.pk: a for a in assets}
    asset_comm = defaultdict(lambda: defaultdict(float))
    global_comm = defaultdict(float)

    for p in productions:
        asset = asset_map.get(p.asset_id)
        if asset is None:
            continue
        field = _BIODIV_LOSS_FIELDS.get(
            p.commodity.biodiversity_loss_class, 'biodiversity_loss_agriculture'
        )
        biodiv_loss = getattr(asset.country, field, 0.0)
        restoration = asset.subnational_region.restoration_cost_m2
        lbiodiv = (
            biodiv_loss
            * restoration
            * p.production
            * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
        )
        asset_comm[p.asset_id][p.commodity.name] += lbiodiv
        global_comm[p.commodity.name] += lbiodiv

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
        Asset.objects.filter(ownership__Company=company)
        .select_related('country')
        .distinct()
    )

    # --- Vulnerability: mean of vulnerability_<key> across the company's policies ---
    levels = [
        cp.policy_level
        for cp in Company_Policy.objects.filter(company=company).select_related('policy_level')
        if cp.policy_level_id
    ]

    def _vuln(key):
        vals = [getattr(level, f'vulnerability_{key}') for level in levels]
        return sum(vals) / len(vals) if vals else 1.0

    vulnerabilities = {r['key']: _vuln(r['key']) for r in PHYSICAL_RISKS}

    # --- Exposition: sum of estimated_revenue for each asset's latest production year ---
    asset_ids = [a.pk for a in assets]
    latest_years = dict(
        Production.objects.filter(asset_id__in=asset_ids)
        .values('asset_id')
        .annotate(max_year=Max('year'))
        .values_list('asset_id', 'max_year')
    )
    exposition = defaultdict(float)
    for p in Production.objects.filter(asset_id__in=asset_ids).values(
        'asset_id', 'year', 'estimated_revenue'
    ):
        if latest_years.get(p['asset_id']) == p['year']:
            exposition[p['asset_id']] += p['estimated_revenue']

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
        Asset.objects.filter(ownership__Company=company)
        .select_related('country', 'subnational_region')
        .distinct()
    )
    asset_ids = [a.pk for a in assets]

    latest_years = dict(
        Production.objects.filter(asset_id__in=asset_ids)
        .values('asset_id')
        .annotate(max_year=Max('year'))
        .values_list('asset_id', 'max_year')
    )

    result = {
        'company_id': company.pk,
        'company_name': company.name,
        'number_of_assets': len(assets),
        'total_lbiodiv': 0,
        **{f'total_{f}': 0 for f, _ in _IMPACT_FIELDS},
        **{f'avg_{f}': 0  for f, _ in _DEPENDENCY_FIELDS},
    }
    if not latest_years:
        return result

    productions = list(
        Production.objects.filter(asset_id__in=asset_ids)
        .select_related('commodity', 'asset__country', 'asset__subnational_region')
    )
    productions = [p for p in productions if latest_years.get(p.asset_id) == p.year]

    asset_map     = {a.pk: a for a in assets}
    impact_totals = {f: 0.0 for f, _ in _IMPACT_FIELDS}
    dep_scores    = {f: []  for f, _ in _DEPENDENCY_FIELDS}
    total_lbiodiv = 0.0

    for p in productions:
        for f, _ in _IMPACT_FIELDS:
            impact_totals[f] += p.production * getattr(p.commodity, f, 0.0)
        for f, _ in _DEPENDENCY_FIELDS:
            dep_scores[f].append(SCORE_MAP.get(getattr(p.commodity, f, 'VL'), 0.0))

        asset = asset_map.get(p.asset_id)
        if asset and asset.subnational_region:
            biodiv_field = _BIODIV_LOSS_FIELDS.get(
                p.commodity.biodiversity_loss_class, 'biodiversity_loss_agriculture'
            )
            total_lbiodiv += (
                getattr(asset.country, biodiv_field, 0.0)
                * asset.subnational_region.restoration_cost_m2
                * p.production
                * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
            )

    result['total_lbiodiv'] = round(total_lbiodiv, 4)
    for f, _ in _IMPACT_FIELDS:
        result[f'total_{f}'] = round(impact_totals[f], 4)
    for f, _ in _DEPENDENCY_FIELDS:
        sc = dep_scores[f]
        result[f'avg_{f}'] = round(sum(sc) / len(sc), 4) if sc else 0

    return result


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


@login_required
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


@login_required
@require_GET
def mesure_empreinte_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_mesure_empreinte_data(company))


@login_required
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


@login_required
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


@login_required
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


@login_required
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
