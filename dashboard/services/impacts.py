"""Service central du chemin ACV : résolution régionalisée des facteurs de
caractérisation (CF) et helpers de calcul d'impact.

`ImpactCategory.key` == nom de colonne legacy → les vues gardent les mêmes clés
de sortie qu'avant la refonte.
"""
from dashboard.models import CharacterizationFactor

CAT_ECOSYSTEM_DIVERSITY = 'impact_endpoint_ReCiPe2016_ecosystem_diversity'

# Figé : les 16 colonnes d'impact historiques de Commodity, dans l'ordre.
# Sert au backfill (Task 6) et reste stable même après suppression des colonnes.
LEGACY_IMPACT_COLUMNS = [
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


def build_cf_index(commodity_ids=None, category_keys=None):
    """Charge en masse les CF pertinents en un dict de résolution.

    Clé : (commodity_id, category_key, locus) où locus vaut
    ('region', region_id) | ('country', country_id) | ('global', None).
    """
    qs = CharacterizationFactor.objects.select_related('category')
    if commodity_ids is not None:
        qs = qs.filter(commodity_id__in=commodity_ids)
    if category_keys is not None:
        qs = qs.filter(category__key__in=category_keys)
    index = {}
    for cf in qs:
        if cf.region_id is not None:
            locus = ('region', cf.region_id)
        elif cf.country_id is not None:
            locus = ('country', cf.country_id)
        else:
            locus = ('global', None)
        index[(cf.commodity_id, cf.category.key, locus)] = cf.value
    return index


def cf_value(cf_index, commodity_id, category_key, region_id=None,
             country_id=None):
    """Fallback : région → pays → global → 0.0."""
    if region_id is not None:
        v = cf_index.get((commodity_id, category_key, ('region', region_id)))
        if v is not None:
            return v
    if country_id is not None:
        v = cf_index.get(
            (commodity_id, category_key, ('country', country_id))
        )
        if v is not None:
            return v
    return cf_index.get(
        (commodity_id, category_key, ('global', None)), 0.0
    )


def legacy_cf_rows(values):
    """(col_name, valeur) pour les 16 colonnes legacy ; défaut 0.0 si absente."""
    return [(col, values.get(col, 0.0)) for col in LEGACY_IMPACT_COLUMNS]


def measured_vs_modeled(asset, theme, year):
    """Apparie, pour un asset/thème/année : la mesure terrain (lignes d'inventaire
    de Flow dont la commodité porte ce theme) et l'impact ACV modélisé
    (production × CF des catégories portant ce theme). Renvoie
    {'measured': float, 'modeled': float}.
    """
    from dashboard.models import ImpactCategory, Production
    from dashboard.services.flows import inventory_total
    measured = inventory_total(asset, theme, year)
    cat_keys = list(
        ImpactCategory.objects.filter(theme=theme).values_list('key', flat=True)
    )
    cf_index = build_cf_index(category_keys=cat_keys)
    modeled = 0.0
    for p in Production.objects.filter(asset=asset, year=year).select_related('commodity'):
        for key in cat_keys:
            modeled += p.production * cf_value(
                cf_index, p.commodity_id, key,
                asset.subnational_region_id, asset.country_id,
            )
    return {'measured': measured, 'modeled': modeled}
