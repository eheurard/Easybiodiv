from django.db import migrations
from dashboard.migrations import _asset_consumption_to_inventory as conv


def run(apps, schema_editor):
    conv.migrate(
        apps.get_model('dashboard', 'Asset_consumption'),
        apps.get_model('dashboard', 'AssetInventory'),
        apps.get_model('dashboard', 'Flow'),
        apps.get_model('dashboard', 'Production'),
    )


def undo(apps, schema_editor):
    apps.get_model('dashboard', 'AssetInventory').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0038_assetinventory')]
    operations = [migrations.RunPython(run, undo)]
