"""Recrée Ownership (spec 2026-09-18 §3.6 et §7).

Pas de migration des données (décision 2 de la spec) : l'ancienne table, dont la
part était un texte aux formats mêlés, est supprimée puis recréée vide. Regroupe
les étapes `clear_ownership` et `ownership_cleanup` du tableau §7.
"""
from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

YEAR_HELP_TEXT = (
    'Le détenteur d’une année est celui du 31 décembre : pour une cession en juin '
    '2024, le vendeur finit en 2023 et l’acheteur commence en 2024. Vide = sans limite.'
)


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0050_seed_technical_commodities'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel(name='Ownership'),
        migrations.CreateModel(
            name='Ownership',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('share', models.DecimalField(
                    decimal_places=4, max_digits=5,
                    help_text='Entre 0 et 1 : 0,75 = 75 %.',
                    validators=[
                        django.core.validators.MinValueValidator(Decimal('0.0001')),
                        django.core.validators.MaxValueValidator(Decimal('1')),
                    ],
                    verbose_name='Part de détention')),
                ('start_year', models.PositiveSmallIntegerField(
                    blank=True, null=True, help_text=YEAR_HELP_TEXT,
                    verbose_name='Année de début')),
                ('end_year', models.PositiveSmallIntegerField(
                    blank=True, null=True, help_text=YEAR_HELP_TEXT,
                    verbose_name='Année de fin')),
                ('description', models.TextField(blank=True, verbose_name='Description')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Modifié le')),
                ('asset', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='ownerships',
                    to='dashboard.asset', verbose_name='Actif')),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='ownerships',
                    to='dashboard.company', verbose_name='Entreprise')),
                ('created_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Créé par')),
            ],
            options={
                'verbose_name': 'Détention',
                'verbose_name_plural': 'Détentions',
                'constraints': [
                    models.CheckConstraint(
                        condition=models.Q(('share__gt', 0), ('share__lte', 1)),
                        name='ownership_share_range',
                        violation_error_message=(
                            'La part de détention doit être comprise entre 0 (exclu) et 1.'
                        ),
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ('start_year__isnull', True), ('end_year__isnull', True),
                            ('start_year__lte', models.F('end_year')), _connector='OR',
                        ),
                        name='ownership_years_ordered',
                        violation_error_message="L'année de début doit précéder l'année de fin.",
                    ),
                ],
            },
        ),
    ]
