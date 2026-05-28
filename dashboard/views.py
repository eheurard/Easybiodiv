import json
from collections import defaultdict

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import Asset, Company


def _get_company_data(company):
    assets = list(
        Asset.objects.filter(ownership__Company=company)
        .select_related('country', 'subnational_region', 'commodity')
        .distinct()
    )

    country_names = set()
    commodity_names = set()
    region_names = set()
    country_assets = defaultdict(list)

    for asset in assets:
        country_names.add(asset.country.name)
        commodity_names.add(asset.commodity.name)
        region_names.add(asset.subnational_region.name)
        country_assets[asset.country.name].append(asset.commodity.name)

    countries = []
    for country_name, commodities in sorted(
        country_assets.items(), key=lambda x: -len(x[1])
    ):
        counts = defaultdict(int)
        for c in commodities:
            counts[c] += 1
        countries.append({
            'name': country_name,
            'asset_count': len(commodities),
            'commodities': [
                {'name': n, 'count': v}
                for n, v in sorted(counts.items(), key=lambda x: -x[1])
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
                'commodity': asset.commodity.name,
                'region': asset.subnational_region.name,
            },
        }
        for asset in assets
    ]

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'asset_count': len(assets),
        'country_count': len(country_names),
        'commodity_count': len(commodity_names),
        'region_count': len(region_names),
        'countries': countries,
        'geojson': {'type': 'FeatureCollection', 'features': features},
    }


def index(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = json.dumps(_get_company_data(first))
    return render(request, 'dashboard/index.html', {
        'companies_json': json.dumps(companies),
        'initial_data': initial_data,
    })


@require_GET
def company_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_company_data(company))
