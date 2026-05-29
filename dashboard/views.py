from collections import defaultdict

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import Asset, Company, Company_Policy


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
