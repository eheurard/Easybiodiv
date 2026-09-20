"""Supprime l'inventaire mesuré historique (spec 2026-09-18 §7).

AssetInventory et le catalogue Flow sont remplacés par la table Flow unique
(migration suivante). Pas de migration des données (décision 2 de la spec).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0051_recreate_ownership'),
    ]

    operations = [
        migrations.DeleteModel(name='AssetInventory'),
        migrations.DeleteModel(name='Flow'),
    ]
