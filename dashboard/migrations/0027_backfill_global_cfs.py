from django.db import migrations
from dashboard.migrations import _cf_backfill


def run(apps, schema_editor):
    Commodity = apps.get_model('dashboard', 'Commodity')
    CharacterizationFactor = apps.get_model('dashboard', 'CharacterizationFactor')
    ImpactCategory = apps.get_model('dashboard', 'ImpactCategory')
    cats = {c.key: c for c in ImpactCategory.objects.all()}
    _cf_backfill.backfill(Commodity, CharacterizationFactor, lambda key: cats[key])


def undo(apps, schema_editor):
    CharacterizationFactor = apps.get_model('dashboard', 'CharacterizationFactor')
    CharacterizationFactor.objects.filter(region__isnull=True, country__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0026_seed_impact_catalog'),
    ]
    operations = [migrations.RunPython(run, undo)]
