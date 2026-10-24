from django.db import migrations


def backfill(apps, schema_editor):
    """Une CommoditySource (type « Autre ») par couple (commodité, source, référence)
    non vide des facteurs de caractérisation ; les valeurs de facteur sont intactes."""
    CommoditySource = apps.get_model('dashboard', 'CommoditySource')
    CharacterizationFactor = apps.get_model('dashboard', 'CharacterizationFactor')
    sources = {}
    for cf in CharacterizationFactor.objects.all().order_by('pk'):
        source, reference = cf.source.strip(), cf.reference.strip()
        if not source and not reference:
            continue
        key = (cf.commodity_id, source, reference)
        if key not in sources:
            sources[key] = CommoditySource.objects.create(
                commodity_id=cf.commodity_id, kind='OTHER',
                title=source or reference, reference=reference,
            )
        CharacterizationFactor.objects.filter(pk=cf.pk).update(
            commodity_source=sources[key],
        )


def unbackfill(apps, schema_editor):
    apps.get_model('dashboard', 'CharacterizationFactor').objects.update(
        commodity_source=None,
    )
    apps.get_model('dashboard', 'CommoditySource').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0058_add_commodity_source'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
