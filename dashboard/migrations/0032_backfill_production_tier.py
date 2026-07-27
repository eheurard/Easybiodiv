from django.db import migrations
from dashboard.migrations import _scope_tier


def run(apps, schema_editor):
    Production = apps.get_model('dashboard', 'Production')
    _scope_tier.backfill(Production)


def undo(apps, schema_editor):
    Production = apps.get_model('dashboard', 'Production')
    Production.objects.update(tier=0)


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0031_production_tier')]
    operations = [migrations.RunPython(run, undo)]
