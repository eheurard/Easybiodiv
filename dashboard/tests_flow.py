"""Tests de la refonte « table Flow unique » (spec 2026-09-18)."""
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import TECHNICAL_COMMODITIES, Commodity


class TechnicalCommodityTests(TestCase):

    def test_five_technical_commodities_are_seeded(self):
        seeded = {
            c.key: (c.name, c.unit, c.theme)
            for c in Commodity.objects.exclude(key=None)
        }
        self.assertEqual(seeded, {
            'water': ('Eau', 'm³', 'water'),
            'energy': ('Énergie', 'MWh', 'energy'),
            'co2': ('CO₂', 'tCO₂e', 'carbon'),
            'waste': ('Déchets', 't', 'waste'),
            'surface_area': ('Surface occupée', 'm²', 'land'),
        })

    def test_key_is_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Commodity.objects.create(name='Eau bis', key='water')

    def test_several_commodities_can_have_no_key(self):
        Commodity.objects.create(name='Soja')
        Commodity.objects.create(name='Blé')
        self.assertEqual(
            Commodity.objects.filter(key=None, name__in=['Soja', 'Blé']).count(), 2)

    def test_technical_recreates_a_missing_commodity(self):
        Commodity.objects.filter(key='co2').delete()
        co2 = Commodity.objects.technical('co2')
        self.assertEqual((co2.name, co2.unit, co2.theme), TECHNICAL_COMMODITIES['co2'])
