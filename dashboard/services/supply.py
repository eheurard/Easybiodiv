"""Service du graphe fournisseurs : vocabulaire des tiers et traversée amont.

`TIER_LABELS[tier]` reproduit exactement l'ancien `_SCOPE_LABELS[scope]` ;
`TIER_TO_SCOPE` permet aux vues d'émettre la même clé `scope` qu'avant.
"""
from dashboard.models import Exchange

TIER_DIRECT, TIER_1, TIER_2, TIER_RAW = 0, 1, 2, 3

TIER_LABELS = {
    0: 'Opérations directes',
    1: "Tier 1 : Chaîne d'approvisionnement",
    2: 'Tier 2 : Approvisionnement amont',
    3: 'Matières premières',
}

SCOPE_TO_TIER = {'direct': 0, 'tier 1': 1, 'tier 2': 2, 'raw material': 3}
TIER_TO_SCOPE = {tier: scope for scope, tier in SCOPE_TO_TIER.items()}


def upstream_chain(node, year, max_depth=5):
    """Remonte les Exchange amont depuis `node` (année donnée),
    borné et anti-cycle."""
    seen_nodes = {node.pk}
    frontier = [node.pk]
    edges = []
    depth = 0
    while frontier and depth < max_depth:
        exchanges = list(
            Exchange.objects.filter(consumer_id__in=frontier, year=year)
            .select_related('supplier', 'consumer', 'commodity')
        )
        edges.extend(exchanges)
        next_frontier = []
        for ex in exchanges:
            if ex.supplier_id not in seen_nodes:
                seen_nodes.add(ex.supplier_id)
                next_frontier.append(ex.supplier_id)
        frontier = next_frontier
        depth += 1
    return edges
