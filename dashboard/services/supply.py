"""Service du graphe fournisseurs : vocabulaire des tiers et traversée amont.

`TIER_LABELS[tier]` reproduit exactement l'ancien `_SCOPE_LABELS[scope]` ;
`TIER_TO_SCOPE` permet aux vues d'émettre la même clé `scope` qu'avant.
"""
TIER_DIRECT, TIER_1, TIER_2, TIER_RAW = 0, 1, 2, 3

TIER_LABELS = {
    0: 'Opérations directes',
    1: "Tier 1 : Chaîne d'approvisionnement",
    2: 'Tier 2 : Approvisionnement amont',
    3: 'Matières premières',
}

SCOPE_TO_TIER = {'direct': 0, 'tier 1': 1, 'tier 2': 2, 'raw material': 3}
TIER_TO_SCOPE = {tier: scope for scope, tier in SCOPE_TO_TIER.items()}
