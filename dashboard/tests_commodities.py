import importlib

from django.apps import apps
from django.contrib.auth import get_user_model
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


class LeapPrepareModifierTests(TestCase):
    """LEAP Prepare : facteur par ligne (actif, commodité) pondéré par les quantités."""

    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.country = Country.objects.create(name='BR')
        self.asset = Asset.objects.create(
            name='Ferme', latitude=1.0, longitude=2.0, country=self.country,
        )
        Ownership.objects.create(asset=self.asset, company=self.company, share=1)
        self.soy = Commodity.objects.create(name='Soja')
        self.eco = ImpactCategory.objects.filter(key=CAT_ECOSYSTEM_DIVERSITY).first() \
            or _category(CAT_ECOSYSTEM_DIVERSITY)
        CharacterizationFactor.objects.create(
            category=self.eco, commodity=self.soy, value=1.0,
        )

    def _data(self):
        from .views import _get_leap_prepare_data
        return _get_leap_prepare_data(self.company)

    def test_line_factor_weighted_by_quantity(self):
        certified = make_production(
            commodity=self.soy, year=2024, production=30000, asset=self.asset,
        )
        make_production(commodity=self.soy, year=2024, production=15000, asset=self.asset)
        mod = CommodityModifier.objects.create(commodity=self.soy, name='Certifié')
        ModifierEffect.objects.create(modifier=mod, category=self.eco, percent=-10)
        certified.modifiers.add(mod)
        lines = self._data()['assets'][0]['lines']
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['qty'], 45000)
        self.assertAlmostEqual(
            lines[0]['impact_factor'], (30000 * 0.9 + 15000 * 1.0) / 45000,
        )

    def test_line_factor_without_modifier_equals_commodity_factor(self):
        make_production(commodity=self.soy, year=2024, production=10, asset=self.asset)
        data = self._data()
        self.assertEqual(
            data['assets'][0]['lines'][0]['impact_factor'],
            data['commodities'][0]['impact_factor'],
        )


class CommodityPageTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.creator = user_model.objects.create_user('createur', password='x', role='CREATOR')
        self.subscriber = user_model.objects.create_user('abonne', password='x')
        self.soy = Commodity.objects.create(name='Soja', unit='tonnes')
        Commodity.objects.create(name='Café')
        CommodityModifier.objects.create(commodity=self.soy, name='Certifié')
        self.list_url = reverse('dashboard:commodity_list')
        self.detail_url = reverse('dashboard:commodity_detail', args=[self.soy.pk])

    def _identity_data(self, **extra):
        data = {'name': 'Soja', 'unit': 'tonnes', 'description': '',
                'biodiversity_loss_class': 'Agriculture'}
        for field in ('water', 'pollination', 'soil_quality', 'carbon_sequestration',
                      'water_purification', 'pest_control'):
            data[f'dependency_{field}'] = 'VL'
        data.update(extra)
        return data

    def _sources_data(self, rows):
        data = {'sources-TOTAL_FORMS': str(len(rows)), 'sources-INITIAL_FORMS': '0',
                'sources-MIN_NUM_FORMS': '0', 'sources-MAX_NUM_FORMS': '1000'}
        for i, row in enumerate(rows):
            for key, value in row.items():
                data[f'sources-{i}-{key}'] = value
        return data

    def test_list_requires_login(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response['Location'])

    def test_list_shows_counts(self):
        CharacterizationFactor.objects.create(
            commodity=self.soy, category=_category(), value=1.0)
        self.client.force_login(self.subscriber)
        response = self.client.get(self.list_url)
        self.assertContains(response, 'Soja')
        self.assertContains(response, 'Café')
        row = next(r for r in response.context['rows'] if r['commodity'] == self.soy)
        self.assertEqual((row['factor_count'], row['modifier_count']), (1, 1))
        filtered = self.client.get(self.list_url, {'q': 'soj'})
        names = [r['commodity'].name for r in filtered.context['rows']]
        self.assertEqual(names, ['Soja'])

    def test_detail_read_only_for_subscriber(self):
        self.client.force_login(self.subscriber)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="commodity-identity-form"')
        self.assertNotContains(response, 'id="commodity-sources-form"')
        self.assertFalse(response.context['can_edit'])

    def test_detail_read_only_shows_dependency_labels(self):
        self.client.force_login(self.subscriber)
        response = self.client.get(self.detail_url)
        self.assertContains(response, '<dd>Very low</dd>')
        self.assertNotContains(response, '<dd>VL</dd>')

    def test_detail_editable_for_creator(self):
        self.client.force_login(self.creator)
        response = self.client.get(self.detail_url)
        self.assertTrue(response.context['can_edit'])
        self.assertContains(response, 'id="commodity-identity-form"')
        self.assertContains(response, 'id="commodity-sources-form"')

    def test_subscriber_post_forbidden(self):
        self.client.force_login(self.subscriber)
        url = reverse('dashboard:commodity_identity', args=[self.soy.pk])
        self.assertEqual(self.client.post(url, self._identity_data()).status_code, 403)
        create = reverse('dashboard:commodity_create')
        self.assertEqual(self.client.post(create, {'name': 'X'}).status_code, 403)

    def test_anonymous_post_redirects_to_login(self):
        url = reverse('dashboard:commodity_identity', args=[self.soy.pk])
        self.assertEqual(self.client.post(url, self._identity_data()).status_code, 302)

    def test_create_commodity(self):
        self.client.force_login(self.creator)
        data = self._identity_data(name='Blé', unit='')
        response = self.client.post(reverse('dashboard:commodity_create'), data)
        wheat = Commodity.objects.get(name='Blé')
        self.assertRedirects(
            response, reverse('dashboard:commodity_detail', args=[wheat.pk]))
        self.assertEqual(wheat.unit, 'tonnes')

    def test_create_commodity_missing_name(self):
        self.client.force_login(self.creator)
        response = self.client.post(
            reverse('dashboard:commodity_create'), self._identity_data(name=''))
        self.assertEqual(response.status_code, 200)
        self.assertIn('name', response.context['form'].errors)

    def test_identity_update_keeps_lieu(self):
        self.client.force_login(self.creator)
        url = reverse('dashboard:commodity_identity', args=[self.soy.pk]) + '?lieu=pays-3'
        response = self.client.post(url, self._identity_data(name='Soja bio'))
        self.assertRedirects(
            response, self.detail_url + '?lieu=pays-3', fetch_redirect_response=False)
        self.soy.refresh_from_db()
        self.assertEqual(self.soy.name, 'Soja bio')

    def test_identity_error_renders_detail(self):
        self.client.force_login(self.creator)
        url = reverse('dashboard:commodity_identity', args=[self.soy.pk])
        response = self.client.post(url, self._identity_data(name=''))
        self.assertEqual(response.status_code, 200)
        self.assertIn('name', response.context['identity_form'].errors)
        self.soy.refresh_from_db()
        self.assertEqual(self.soy.name, 'Soja')

    def test_technical_key_read_only(self):
        water = Commodity.objects.get(key='water')
        self.client.force_login(self.creator)
        response = self.client.get(reverse('dashboard:commodity_detail', args=[water.pk]))
        self.assertContains(response, 'water')
        self.assertNotIn('key', response.context['identity_form'].fields)

    def test_sources_formset_add_and_delete(self):
        self.client.force_login(self.creator)
        url = reverse('dashboard:commodity_sources', args=[self.soy.pk])
        data = self._sources_data([
            {'kind': 'ARTICLE', 'title': 'Étude', 'reference': 'doi:1'}])
        response = self.client.post(url, data)
        self.assertRedirects(response, self.detail_url, fetch_redirect_response=False)
        source = CommoditySource.objects.get(commodity=self.soy)
        self.assertEqual(source.created_by, self.creator)
        self.assertEqual(source.title, 'Étude')
        page = self.client.get(self.detail_url)
        self.assertEqual(page.context['source_codes'][source.pk], 'S1')

        delete = {
            'sources-TOTAL_FORMS': '1', 'sources-INITIAL_FORMS': '1',
            'sources-MIN_NUM_FORMS': '0', 'sources-MAX_NUM_FORMS': '1000',
            'sources-0-id': str(source.pk), 'sources-0-commodity': str(self.soy.pk),
            'sources-0-kind': 'ARTICLE', 'sources-0-title': 'Étude',
            'sources-0-DELETE': 'on',
        }
        self.client.post(url, delete)
        self.assertFalse(CommoditySource.objects.filter(commodity=self.soy).exists())

    def test_sources_formset_error_renders_detail(self):
        self.client.force_login(self.creator)
        url = reverse('dashboard:commodity_sources', args=[self.soy.pk])
        data = self._sources_data([{'kind': 'ARTICLE', 'title': '', 'reference': 'x'}])
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CommoditySource.objects.exists())
