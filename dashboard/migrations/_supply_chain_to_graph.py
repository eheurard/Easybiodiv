"""Conversion figée Supply_chain → SupplyNode + Exchange."""
_CONF = {
    'country level': 'country',
    'sub_region level': 'region',
    'asset level': 'asset'
}


def _node_for_asset(SupplyNode, asset_id):
    node, _ = SupplyNode.objects.get_or_create(
        asset_id=asset_id, region=None, country=None, commodity=None,
        defaults={'is_external': False},
    )
    return node


def migrate(Supply_chain, SupplyNode, Exchange):
    for sc in Supply_chain.objects.all():
        if not sc.asset_id or not sc.supplier_id:
            continue
        consumer = _node_for_asset(SupplyNode, sc.asset_id)
        supplier = _node_for_asset(SupplyNode, sc.supplier_id)
        Exchange.objects.get_or_create(
            supplier=supplier, consumer=consumer,
            commodity_id=sc.commodity_id,
            year=sc.year,
            defaults={
                'quantity': sc.quantity,
                'tier': 1,
                'data_confidence': _CONF.get(
                    sc.supplier_data_confidence, 'country'
                ),
            },
        )
