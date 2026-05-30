from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from django.db.models import Q
from .models import Asset, Company, Company_Policy, Company_Revenue, Company_Revenue_Sector, Production


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

    # --- Revenue Segments ---
    rev_sector_qs = (
        Company_Revenue_Sector.objects.filter(company=company)
        .select_related('subsector__sector')
        .order_by('subsector_id', '-year')
    )
    seen = {}
    for rs in rev_sector_qs:
        if rs.subsector_id not in seen:
            seen[rs.subsector_id] = rs

    _RATING_ORDER = ['VL', 'L', 'M', 'H', 'VH']
    _RATING_LABEL = {'VL': 'Low', 'L': 'Low', 'M': 'Moderate', 'H': 'High', 'VH': 'Critical'}

    revenue_segments = []
    for rs in sorted(seen.values(), key=lambda x: -x.revenue):
        sub = rs.subsector
        scores = [SCORE_MAP[getattr(sub, _SUBSECTOR_DEP_FIELDS[svc['key']])] for svc in SERVICES]
        dep_score = sum(scores) / len(scores)
        ratings = [getattr(sub, _SUBSECTOR_DEP_FIELDS[svc['key']]) for svc in SERVICES]
        max_rating = max(ratings, key=lambda r: _RATING_ORDER.index(r))
        revenue_segments.append({
            'subsector': sub.name,
            'sector': sub.sector.name,
            'revenue': rs.revenue,
            'dep_score': round(dep_score, 3),
            'exposure_label': _RATING_LABEL[max_rating],
        })

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

    features = [
        {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [asset.longitude, asset.latitude],
            },
            'properties': {
                'name': asset.name,
                'country': asset.country.name,
                'commodities': ', '.join(sorted({p.commodity.name for p in asset.production_set.all()})),
                'region': asset.subnational_region.name,
            },
        }
        for asset in assets
    ]

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


def _get_transition_risk_data(company):
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
def transition_risk(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_transition_risk_data(first)
    return render(request, 'dashboard/transition_risk.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@login_required
@require_GET
def transition_risk_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_transition_risk_data(company))


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
