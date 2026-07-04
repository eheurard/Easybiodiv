"""Backfill réutilisable : colonnes d'impact de Commodity → CF globales.

Séparé de la migration pour être testable ; utilise l'injection des modèles
afin de fonctionner aussi bien avec les modèles historiques (apps.get_model)
qu'avec les modèles courants (tests).
"""
from dashboard.services.impacts import LEGACY_IMPACT_COLUMNS


def backfill(Commodity, CharacterizationFactor, get_category):
    for commodity in Commodity.objects.all():
        for col in LEGACY_IMPACT_COLUMNS:
            value = getattr(commodity, col, 0.0)
            CharacterizationFactor.objects.get_or_create(
                commodity=commodity,
                category=get_category(col),
                region=None,
                country=None,
                defaults={'value': value},
            )
