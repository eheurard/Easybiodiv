from django.db import migrations

# (method_name, key, name, level, theme). key == nom de colonne legacy.
CATEGORIES = [
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_water_consumption',
     'Consommation eau', 'MIDPOINT', 'water'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_climate_change',
     'Changement climatique', 'MIDPOINT', 'carbon'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity',
     'Écotoxicité eau douce', 'MIDPOINT', 'water'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_freshwater_eutrophication',
     'Eutrophisation eau douce', 'MIDPOINT', 'water'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_marine_eutrophication',
     'Eutrophisation marine', 'MIDPOINT', 'water'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_terrestrial_acidification',
     'Acidification terrestre', 'MIDPOINT', ''),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_soil_acidification',
     'Acidification des sols', 'MIDPOINT', 'land'),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_ozonedepletion',
     "Appauvrissement de l'ozone", 'MIDPOINT', ''),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_resource_depletion_fossil',
     'Épuisement ressources fossiles', 'MIDPOINT', ''),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_resource_depletion_minerals',
     'Épuisement ressources minérales', 'MIDPOINT', ''),
    ('ReCiPe2016', 'impact_midpoint_ReCiPe2016_land_use',
     'Utilisation des terres', 'MIDPOINT', 'land'),
    ('ReCiPe2016', 'impact_endpoint_ReCiPe2016_human_health',
     'Santé humaine', 'ENDPOINT', ''),
    ('ReCiPe2016', 'impact_endpoint_ReCiPe2016_ecosystem_diversity',
     'Diversité des écosystèmes', 'ENDPOINT', 'land'),
    ('ReCiPe2016', 'impact_endpoint_ReCiPe2016_resource_availability',
     'Disponibilité ressources', 'ENDPOINT', ''),
    ('GBS', 'impact_endpoint_GBS_terrestrial_dynamic',
     'Terrestre dynamique (GBS)', 'ENDPOINT', 'land'),
    ('GBS', 'impact_endpoint_GBS_terrestrial_static',
     'Terrestre statique (GBS)', 'ENDPOINT', 'land'),
]


def seed(apps, schema_editor):
    ImpactMethod = apps.get_model('dashboard', 'ImpactMethod')
    ImpactCategory = apps.get_model('dashboard', 'ImpactCategory')
    methods = {}
    for name in ('ReCiPe2016', 'GBS'):
        methods[name] = ImpactMethod.objects.get_or_create(name=name)[0]
    for method_name, key, label, level, theme in CATEGORIES:
        ImpactCategory.objects.get_or_create(
            key=key,
            defaults={
                'method': methods[method_name],
                'name': label, 'level': level, 'theme': theme,
            },
        )


def unseed(apps, schema_editor):
    ImpactCategory = apps.get_model('dashboard', 'ImpactCategory')
    ImpactMethod = apps.get_model('dashboard', 'ImpactMethod')
    ImpactCategory.objects.filter(key__in=[c[1] for c in CATEGORIES]).delete()
    ImpactMethod.objects.filter(name__in=('ReCiPe2016', 'GBS')).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0025_characterization_factor'),
    ]
    operations = [migrations.RunPython(seed, unseed)]
