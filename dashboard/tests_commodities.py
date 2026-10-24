import importlib

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import (
    CharacterizationFactor, Commodity, CommodityModifier, CommoditySource, Company,
    Flow, ImpactCategory, ImpactMethod, ModifierEffect,
    invalid_modifiers, source_codes,
)
from .testing import make_production


def _category(key='climate'):
    method, _ = ImpactMethod.objects.get_or_create(name='M')
    return ImpactCategory.objects.create(
        method=method, key=key, name=key, level=ImpactCategory.Level.MIDPOINT,
    )


class CommodityModelTests(TestCase):
    def setUp(self):
        self.coffee = Commodity.objects.create(name='Café')
        self.soy = Commodity.objects.create(name='Soja')

    def test_source_codes_follow_creation_order(self):
        s1 = CommoditySource.objects.create(commodity=self.coffee, title='A')
        s2 = CommoditySource.objects.create(commodity=self.coffee, title='B')
        CommoditySource.objects.create(commodity=self.soy, title='C')
        self.assertEqual(source_codes(self.coffee), {s1.pk: 'S1', s2.pk: 'S2'})

    def test_effect_below_minus_100_rejected(self):
        mod = CommodityModifier.objects.create(commodity=self.coffee, name='Bio')
        cat = _category()
        with self.assertRaises(ValidationError) as ctx:
            ModifierEffect(modifier=mod, category=cat, percent=-100.5).full_clean()
        self.assertIn('percent', ctx.exception.message_dict)
        ModifierEffect(modifier=mod, category=cat, percent=-100).full_clean()

    def test_modifier_name_unique_per_commodity(self):
        CommodityModifier.objects.create(commodity=self.coffee, name='Bio')
        with self.assertRaises(IntegrityError), transaction.atomic():
            CommodityModifier.objects.create(commodity=self.coffee, name='Bio')
        CommodityModifier.objects.create(commodity=self.soy, name='Bio')

    def test_effect_unique_per_category(self):
        mod = CommodityModifier.objects.create(commodity=self.coffee, name='Bio')
        cat = _category()
        ModifierEffect.objects.create(modifier=mod, category=cat, percent=-10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModifierEffect.objects.create(modifier=mod, category=cat, percent=5)

    def test_modifier_source_from_other_commodity_rejected(self):
        source = CommoditySource.objects.create(commodity=self.soy, title='S')
        mod = CommodityModifier(commodity=self.coffee, name='Bio', source=source)
        with self.assertRaises(ValidationError) as ctx:
            mod.full_clean()
        self.assertIn('source', ctx.exception.message_dict)

    def test_cf_source_from_other_commodity_rejected(self):
        source = CommoditySource.objects.create(commodity=self.soy, title='S')
        cf = CharacterizationFactor(
            category=_category(), commodity=self.coffee, value=1.0,
            commodity_source=source,
        )
        with self.assertRaises(ValidationError) as ctx:
            cf.full_clean()
        self.assertIn('commodity_source', ctx.exception.message_dict)

    def test_invalid_modifiers(self):
        coffee_mod = CommodityModifier.objects.create(commodity=self.coffee, name='Bio')
        soy_mod = CommodityModifier.objects.create(commodity=self.soy, name='Bio')
        result = invalid_modifiers(self.soy, [coffee_mod, soy_mod])
        self.assertEqual(result, [coffee_mod])

    def test_deleting_modifier_removes_it_from_flows(self):
        mod = CommodityModifier.objects.create(commodity=self.coffee, name='Bio')
        flow = make_production(
            commodity=self.coffee, year=2024, production=1.0,
            company=Company.objects.create(name='Acme'),
        )
        flow.modifiers.add(mod)
        mod.delete()
        self.assertEqual(flow.modifiers.count(), 0)
        self.assertTrue(Flow.objects.filter(pk=flow.pk).exists())

    def test_backfill_links_existing_factors(self):
        migration = importlib.import_module(
            'dashboard.migrations.0059_backfill_commodity_sources'
        )
        cat1, cat2, cat3 = _category('a'), _category('b'), _category('c')
        cf1 = CharacterizationFactor.objects.create(
            category=cat1, commodity=self.coffee, value=1.5, source=' Agri ',
            reference='ref',
        )
        cf2 = CharacterizationFactor.objects.create(
            category=cat2, commodity=self.coffee, value=2.5, source='Agri',
            reference='ref ',
        )
        cf3 = CharacterizationFactor.objects.create(
            category=cat3, commodity=self.coffee, value=3.5,
        )
        migration.backfill(apps, None)
        self.assertEqual(CommoditySource.objects.count(), 1)
        source = CommoditySource.objects.get()
        self.assertEqual(source.kind, CommoditySource.Kind.OTHER)
        for cf in (cf1, cf2, cf3):
            cf.refresh_from_db()
        self.assertEqual(cf1.commodity_source, source)
        self.assertEqual(cf2.commodity_source, source)
        self.assertIsNone(cf3.commodity_source)
        self.assertEqual((cf1.value, cf2.value, cf3.value), (1.5, 2.5, 3.5))
