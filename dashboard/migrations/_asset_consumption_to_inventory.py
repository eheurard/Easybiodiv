"""Conversion figée Asset_consumption → AssetInventory (instantané de migration)."""
from django.db.models import Max

# colonne Asset_consumption → clé de Flow (figé)
_COL_TO_FLOW = {
    'surface_area': 'surface_area',
    'water_consumption': 'water',
    'energy_consumption': 'energy',
    'CO2_emissions': 'co2',
    'waste_generated': 'waste',
}
_DEFAULT_YEAR = 2024


def migrate(AssetConsumption, AssetInventory, Flow, Production):
    flows = {f.key: f for f in Flow.objects.all()}
    for ac in AssetConsumption.objects.all():
        if not ac.asset_id:
            continue
        year = Production.objects.filter(asset_id=ac.asset_id).aggregate(
            m=Max('year')
        )['m'] or _DEFAULT_YEAR
        for col, flow_key in _COL_TO_FLOW.items():
            value = getattr(ac, col, 0.0)
            if value:
                AssetInventory.objects.get_or_create(
                    asset_id=ac.asset_id, flow=flows[flow_key], year=year,
                    defaults={'value': value},
                )
