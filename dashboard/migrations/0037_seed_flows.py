from django.db import migrations

# (key, name, unit, theme)
FLOWS = [
    ('water', 'Consommation eau', 'm³', 'water'),
    ('energy', 'Consommation énergie', 'MWh', 'energy'),
    ('co2', 'Émissions CO₂', 'tCO₂e', 'carbon'),
    ('waste', 'Déchets générés', 't', 'waste'),
    ('surface_area', 'Surface', 'm²', 'land'),
]


def seed(apps, schema_editor):
    Flow = apps.get_model('dashboard', 'Flow')
    for key, name, unit, theme in FLOWS:
        Flow.objects.get_or_create(
            key=key, defaults={'name': name, 'unit': unit, 'theme': theme}
        )


def unseed(apps, schema_editor):
    Flow = apps.get_model('dashboard', 'Flow')
    Flow.objects.filter(key__in=[f[0] for f in FLOWS]).delete()


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0036_flow')]
    operations = [migrations.RunPython(seed, unseed)]
