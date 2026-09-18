"""Crée les 5 commodités techniques lues par le code (spec 2026-09-18 §3.5).

Copie figée de TECHNICAL_COMMODITIES : une migration n'importe pas de constante
vivante.
"""
from django.db import migrations

TECHNICAL_COMMODITIES = [
    # (key, name, unit, theme)
    ('water', 'Eau', 'm³', 'water'),
    ('energy', 'Énergie', 'MWh', 'energy'),
    ('co2', 'CO₂', 'tCO₂e', 'carbon'),
    ('waste', 'Déchets', 't', 'waste'),
    ('surface_area', 'Surface occupée', 'm²', 'land'),
]


def seed(apps, schema_editor):
    Commodity = apps.get_model('dashboard', 'Commodity')
    for key, name, unit, theme in TECHNICAL_COMMODITIES:
        Commodity.objects.update_or_create(
            key=key, defaults={'name': name, 'unit': unit, 'theme': theme},
        )


def unseed(apps, schema_editor):
    Commodity = apps.get_model('dashboard', 'Commodity')
    Commodity.objects.filter(key__in=[row[0] for row in TECHNICAL_COMMODITIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0049_commodity_key_theme'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
