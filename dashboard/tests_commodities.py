import importlib

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import (
    Asset, CharacterizationFactor, Commodity, CommodityModifier, CommoditySource,
    Company, Country, Ownership, SubnationalRegion,
    Flow, ImpactCategory, ImpactMethod, ModifierEffect,
    invalid_modifiers, source_codes,
)
from .services.esg_environment import owned_asset_impacts
from .services.flows import productions
from .services.impacts import (
    CAT_ECOSYSTEM_DIVERSITY, build_cf_index, flow_cf_value, measured_vs_modeled,
)
from .services.stress_test import get_stress_test_data
from .testing import make_production, make_supply


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


class ModifierFormulaTests(TestCase):
    def setUp(self):
        self.soy = Commodity.objects.create(name='Soja')
        self.land = _category('land_use')
        self.climate = _category('climate')
        CharacterizationFactor.objects.create(
            category=self.land, commodity=self.soy, value=1000.0,
        )
        self.country = Country.objects.create(name='BR')
        self.asset = Asset.objects.create(
            name='Ferme', latitude=1.0, longitude=2.0, country=self.country,
        )
        self.flow = make_production(
            commodity=self.soy, year=2024, production=10, asset=self.asset,
        )

    def _tick(self, flow, *percents, category=None):
        for i, pct in enumerate(percents):
            mod = CommodityModifier.objects.create(
                commodity=flow.what, name=f'M{flow.pk}-{i}',
            )
            ModifierEffect.objects.create(
                modifier=mod, category=category or self.land, percent=pct,
            )
            flow.modifiers.add(mod)

    def _value(self, key='land_use', **kwargs):
        flow = productions([self.asset.pk])[0]
        return flow_cf_value(build_cf_index(), flow, key, **kwargs)

    def test_no_modifier_unchanged(self):
        self.assertEqual(self._value(), 1000.0)

    def test_single_modifier(self):
        self._tick(self.flow, -10)
        self.assertAlmostEqual(self._value(), 900.0)

    def test_modifiers_add_up(self):
        self._tick(self.flow, -10, -5)
        self.assertAlmostEqual(self._value(), 850.0)

    def test_floor_at_zero(self):
        self._tick(self.flow, -80, -40)
        self.assertEqual(self._value(), 0.0)

    def test_positive_effect(self):
        self._tick(self.flow, 20)
        self.assertAlmostEqual(self._value(), 1200.0)

    def test_category_without_effect_unchanged(self):
        CharacterizationFactor.objects.create(
            category=self.climate, commodity=self.soy, value=50.0,
        )
        self._tick(self.flow, -10)
        self.assertEqual(self._value('climate'), 50.0)

    def test_regional_factor_with_modifier(self):
        region = SubnationalRegion.objects.create(name='MT', country=self.country)
        CharacterizationFactor.objects.create(
            category=self.land, commodity=self.soy, region=region, value=2000.0,
        )
        self._tick(self.flow, -10)
        self.assertAlmostEqual(self._value(region_id=region.pk), 1800.0)

    def test_productions_prefetch_no_n_plus_one(self):
        cf_index = build_cf_index()

        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                for flow in productions([self.asset.pk]):
                    flow_cf_value(cf_index, flow, 'land_use')
            return len(ctx)

        self._tick(self.flow, -10, -5)
        one = count_queries()
        for _ in range(4):
            flow = make_production(
                commodity=self.soy, year=2024, production=1, asset=self.asset,
            )
            self._tick(flow, -10, -5)
        self.assertEqual(count_queries(), one)


class ModifierPropagationTests(TestCase):
    """Les modificateurs cochés sur une production ajustent les vues d'impact."""

    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.country = Country.objects.create(name='BR')
        self.region = SubnationalRegion.objects.create(
            name='MT', country=self.country, restoration_cost_m2=1.0,
        )
        self.asset = Asset.objects.create(
            name='Ferme', latitude=1.0, longitude=2.0, country=self.country,
            subnational_region=self.region,
        )
        Ownership.objects.create(asset=self.asset, company=self.company, share=1)
        self.soy = Commodity.objects.create(name='Soja')
        self.eco = ImpactCategory.objects.filter(key=CAT_ECOSYSTEM_DIVERSITY).first()             or _category(CAT_ECOSYSTEM_DIVERSITY)
        self.land = _category('land_use')
        for cat in (self.eco, self.land):
            CharacterizationFactor.objects.create(
                category=cat, commodity=self.soy, value=10.0,
            )
        self.flow = make_production(
            commodity=self.soy, year=2024, production=4, asset=self.asset,
        )

    def _tick(self, flow, percent, *categories):
        mod = CommodityModifier.objects.create(commodity=flow.what, name=f'M{flow.pk}')
        for cat in categories:
            ModifierEffect.objects.create(modifier=mod, category=cat, percent=percent)
        flow.modifiers.add(mod)

    def _get(self, name):
        response = self.client.get(reverse(f'dashboard:{name}', args=[self.company.pk]))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _footprint(self):
        return self._get('company_data')['geojson']['features'][0]['properties']['footprint']

    def test_overview_footprint_uses_modifier(self):
        before = self._footprint()
        self.assertEqual(before, 40.0)
        self._tick(self.flow, -50, self.eco)
        self.assertAlmostEqual(self._footprint(), before / 2)

    def test_esg_environment_uses_modifier(self):
        assets = [self.asset]
        self._tick(self.flow, -50, self.land)
        by_asset, by_commodity = owned_asset_impacts(assets, ['land_use'])
        self.assertAlmostEqual(by_asset[self.asset.pk]['land_use'], 20.0)
        self.assertEqual(list(by_commodity), ['Soja'])
        self.assertAlmostEqual(by_commodity['Soja']['land_use'], 20.0)

    def test_supply_modifier_changes_nothing(self):
        other = Asset.objects.create(
            name='Silo', latitude=3.0, longitude=4.0, country=self.country,
            subnational_region=self.region,
        )
        supply = make_supply(
            what=self.soy, year=2024, quantity=5, origin=other, destination=self.asset,
        )
        names = ('company_data', 'mesure_empreinte_data', 'dette_ecologique_data')
        before = {name: self._get(name) for name in names}
        self._tick(supply, -50, self.eco, self.land)
        after = {name: self._get(name) for name in names}
        self.assertEqual(before, after)

    def test_stress_test_ignores_modifier(self):
        before = get_stress_test_data(self.company)
        self._tick(self.flow, -50, self.eco, self.land)
        self.assertEqual(get_stress_test_data(self.company), before)

    def test_measured_vs_modeled_uses_modifier(self):
        self.land.theme = 'water'
        self.land.save()
        before = measured_vs_modeled(self.asset, 'water', 2024)['modeled']
        self.assertEqual(before, 40.0)
        self._tick(self.flow, -50, self.land)
        self.assertAlmostEqual(measured_vs_modeled(self.asset, 'water', 2024)['modeled'], 20.0)
