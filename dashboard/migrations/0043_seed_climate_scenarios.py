"""Seed des scénarios climatiques de référence (NGFS Phase V).

Données figées dans le fichier : la migration ne doit jamais dépendre d'une
constante vivante du code applicatif.

Les trajectoires sont des ordres de grandeur indicatifs cohérents avec les
narratifs NGFS Phase V (novembre 2024). Elles sont marquées comme telles dans
le champ `reference` et doivent être recalées sur le NGFS Scenarios Portal.
"""
from django.db import migrations

SOURCE = (
    'NGFS — Climate Scenarios for Central Banks and Supervisors, '
    'Phase V (nov. 2024)'
)
REFERENCE = (
    'Valeurs indicatives cohérentes avec les narratifs NGFS — '
    'à recaler sur https://www.ngfs.net/ngfs-scenarios-portal/'
)

# (key, name, family, warming_c, order, narrative)
SCENARIOS = [
    (
        'NET_ZERO_2050', 'Net Zero 2050', 'ORDERLY', 1.5, 1,
        "Politiques climatiques ambitieuses et immédiates, neutralité carbone "
        "atteinte vers 2050. Risque de transition élevé mais anticipé, risque "
        "physique contenu.",
    ),
    (
        'BELOW_2C', 'Below 2 °C', 'ORDERLY', 1.7, 2,
        "Durcissement progressif des politiques, réchauffement limité sous 2 °C. "
        "Transition graduelle, risques répartis dans le temps.",
    ),
    (
        'DELAYED_TRANSITION', 'Delayed Transition', 'DISORDERLY', 1.8, 3,
        "Aucune baisse des émissions avant 2030, puis politiques abruptes pour "
        "tenir la cible. Choc de transition tardif et brutal.",
    ),
    (
        'FRAGMENTED_WORLD', 'Fragmented World', 'TOO_LITTLE', 2.3, 4,
        "Ambition climatique divergente selon les pays ; les objectifs net zéro "
        "ne sont atteints que partiellement. Risques de transition ET physiques "
        "élevés.",
    ),
    (
        'CURRENT_POLICIES', 'Current Policies', 'HOT_HOUSE', 3.0, 5,
        "Seules les politiques déjà en vigueur sont maintenues. Risque de "
        "transition faible, risque physique sévère et croissant.",
    ),
]

# key: {year: prix carbone €/tCO₂e}
CARBON_PRICE = {
    'NET_ZERO_2050':      {2025: 80.0, 2030: 190.0, 2040: 400.0, 2050: 570.0},
    'BELOW_2C':           {2025: 80.0, 2030: 110.0, 2040: 220.0, 2050: 350.0},
    'DELAYED_TRANSITION': {2025: 80.0, 2030: 85.0,  2040: 400.0, 2050: 550.0},
    'FRAGMENTED_WORLD':   {2025: 80.0, 2030: 95.0,  2040: 190.0, 2050: 280.0},
    'CURRENT_POLICIES':   {2025: 80.0, 2030: 85.0,  2040: 90.0,  2050: 95.0},
}

# key: {year: multiplicateur d'aléa physique, base 1.0 aujourd'hui}
HAZARD_MULTIPLIER = {
    'NET_ZERO_2050':      {2025: 1.0, 2030: 1.10, 2040: 1.20, 2050: 1.30},
    'BELOW_2C':           {2025: 1.0, 2030: 1.10, 2040: 1.25, 2050: 1.40},
    'DELAYED_TRANSITION': {2025: 1.0, 2030: 1.15, 2040: 1.30, 2050: 1.50},
    'FRAGMENTED_WORLD':   {2025: 1.0, 2030: 1.20, 2040: 1.50, 2050: 1.90},
    'CURRENT_POLICIES':   {2025: 1.0, 2030: 1.25, 2040: 1.70, 2050: 2.40},
}


def seed(apps, schema_editor):
    ClimateScenario = apps.get_model('dashboard', 'ClimateScenario')
    ScenarioVariable = apps.get_model('dashboard', 'ScenarioVariable')

    for key, name, family, warming, order, narrative in SCENARIOS:
        scenario, _ = ClimateScenario.objects.get_or_create(
            key=key,
            defaults={
                'name': name, 'family': family, 'warming_c': warming,
                'order': order, 'narrative': narrative,
                'source': SOURCE, 'reference': REFERENCE,
            },
        )
        for var_key, table in (
            ('carbon_price', CARBON_PRICE),
            ('hazard_multiplier', HAZARD_MULTIPLIER),
        ):
            for year, value in table[key].items():
                ScenarioVariable.objects.get_or_create(
                    scenario=scenario, year=year, key=var_key,
                    defaults={'value': value},
                )


def unseed(apps, schema_editor):
    ClimateScenario = apps.get_model('dashboard', 'ClimateScenario')
    ClimateScenario.objects.filter(key__in=[s[0] for s in SCENARIOS]).delete()


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0042_climate_scenario_models')]
    operations = [migrations.RunPython(seed, unseed)]
