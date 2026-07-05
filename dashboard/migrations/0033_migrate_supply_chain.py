from django.db import migrations
from dashboard.migrations import _supply_chain_to_graph


def run(apps, schema_editor):
    _supply_chain_to_graph.migrate(
        apps.get_model('dashboard', 'Supply_chain'),
        apps.get_model('dashboard', 'SupplyNode'),
        apps.get_model('dashboard', 'Exchange'),
    )


def undo(apps, schema_editor):
    apps.get_model('dashboard', 'Exchange').objects.all().delete()
    apps.get_model('dashboard', 'SupplyNode').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [('dashboard', '0032_backfill_production_tier')]

    operations = [migrations.RunPython(run, undo)]
