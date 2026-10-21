"""Vocabulaire des tiers de la chaîne d'approvisionnement.

`TIER_LABELS[tier]` reproduit exactement l'ancien `_SCOPE_LABELS[scope]` ;
`TIER_TO_SCOPE` permet aux vues d'émettre la même clé `scope` qu'avant.
"""
from django.utils.translation import gettext_lazy as _

TIER_DIRECT, TIER_1, TIER_2, TIER_RAW = 0, 1, 2, 3

TIER_LABELS = {
    0: _('Opérations directes'),
    1: _("Tier 1 : Chaîne d'approvisionnement"),
    2: _('Tier 2 : Approvisionnement amont'),
    3: _('Matières premières'),
}

SCOPE_TO_TIER = {'direct': 0, 'tier 1': 1, 'tier 2': 2, 'raw material': 3}
TIER_TO_SCOPE = {tier: scope for scope, tier in SCOPE_TO_TIER.items()}
