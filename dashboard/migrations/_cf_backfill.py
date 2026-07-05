"""Backfill réutilisable : colonnes d'impact de Commodity → CF globales.

Séparé de la migration pour être testable ; utilise l'injection des modèles
afin de fonctionner aussi bien avec les modèles historiques (apps.get_model)
qu'avec les modèles courants (tests).
"""
# Figé : les 16 colonnes d'impact historiques de Commodity (instantané de migration).
# Ne pas coupler à dashboard.services.impacts (constante vivante) — une migration
# doit rester auto-suffisante.
_LEGACY_IMPACT_COLUMNS = [
    'impact_midpoint_ReCiPe2016_water_consumption',
    'impact_midpoint_ReCiPe2016_climate_change',
    'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity',
    'impact_midpoint_ReCiPe2016_freshwater_eutrophication',
    'impact_midpoint_ReCiPe2016_marine_eutrophication',
    'impact_midpoint_ReCiPe2016_terrestrial_acidification',
    'impact_midpoint_ReCiPe2016_soil_acidification',
    'impact_midpoint_ReCiPe2016_ozonedepletion',
    'impact_midpoint_ReCiPe2016_resource_depletion_fossil',
    'impact_midpoint_ReCiPe2016_resource_depletion_minerals',
    'impact_midpoint_ReCiPe2016_land_use',
    'impact_endpoint_ReCiPe2016_human_health',
    'impact_endpoint_ReCiPe2016_ecosystem_diversity',
    'impact_endpoint_ReCiPe2016_resource_availability',
    'impact_endpoint_GBS_terrestrial_dynamic',
    'impact_endpoint_GBS_terrestrial_static',
]


def backfill(Commodity, CharacterizationFactor, get_category):
    for commodity in Commodity.objects.all():
        for col in _LEGACY_IMPACT_COLUMNS:
            value = getattr(commodity, col, 0.0)
            CharacterizationFactor.objects.get_or_create(
                commodity=commodity,
                category=get_category(col),
                region=None,
                country=None,
                defaults={'value': value},
            )
