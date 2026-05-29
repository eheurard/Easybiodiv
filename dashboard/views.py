from collections import defaultdict

from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import Asset, Company, Company_Policy, Production


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
        Production.objects.filter(Asset_id__in=asset_ids)
        .values('Asset_id')
        .annotate(max_year=Max('year'))
        .values_list('Asset_id', 'max_year')
    )

    if not latest_years:
        return empty

    ref_year = max(latest_years.values())

    productions = list(
        Production.objects.filter(Asset_id__in=asset_ids)
        .select_related('commodity', 'Asset__country')
    )
    productions = [p for p in productions if latest_years.get(p.Asset_id) == p.year]

    commodity_impact = defaultdict(float)
    asset_impact = defaultdict(float)
    asset_meta = {}
    link_commodity_asset = defaultdict(float)

    for p in productions:
        impact = p.production * p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
        commodity_impact[p.commodity.name] += impact
        asset_impact[p.Asset_id] += impact
        asset_meta[p.Asset_id] = {'name': p.Asset.name, 'country': p.Asset.country.name}
        link_commodity_asset[(p.commodity.name, p.Asset_id)] += impact

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


@require_GET
def transition_risk_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_transition_risk_data(company))
