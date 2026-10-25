import importlib

from django.apps import apps
from django.conf import settings
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

    def test_source_reference_accepts_500_characters(self):
        source = CommoditySource(commodity=self.coffee, title='A', reference='r' * 500)
        source.full_clean()
        source.reference = 'r' * 501
        with self.assertRaises(ValidationError) as ctx:
            source.full_clean()
        self.assertIn('reference', ctx.exception.message_dict)

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

    def test_modifier_of_previous_commodity_ignored_after_change(self):
        # Changement de commodité hors formulaire (admin, ORM) : le modificateur du
        # soja resté coché ne doit pas ajuster le facteur du maïs.
        maize = Commodity.objects.create(name='Maïs')
        CharacterizationFactor.objects.create(
            category=self.land, commodity=maize, value=800.0,
        )
        self._tick(self.flow, -50)
        self.assertEqual(self._value(), 500.0)
        Flow.objects.filter(pk=self.flow.pk).update(what=maize)
        self.assertEqual(self._value(), 800.0)

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
        self.assertContains(response, '<dd>Très faible</dd>')
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


class CommoditySheetServiceTests(TestCase):
    def setUp(self):
        from .services import commodity_sheet
        self.svc = commodity_sheet
        self.soy = Commodity.objects.create(name='Soja')
        self.brazil = Country.objects.create(name='Brésil')
        self.mato = SubnationalRegion.objects.create(name='Mato Grosso', country=self.brazil)
        method, _ = ImpactMethod.objects.get_or_create(name='M')
        Level = ImpactCategory.Level
        self.mid_a = ImpactCategory.objects.create(
            method=method, key='t9_mid_a', name='Mid A', level=Level.MIDPOINT)
        self.mid_b = ImpactCategory.objects.create(
            method=method, key='t9_mid_b', name='Mid B', level=Level.MIDPOINT)
        self.end_a = ImpactCategory.objects.create(
            method=method, key='t9_end_a', name='End A', level=Level.ENDPOINT)

    def _row(self, rows, category):
        return next(r for r in rows if r['category'] == category)

    def test_parse_location(self):
        parse = self.svc.parse_location
        self.assertEqual(parse('global'), ('global', None))
        self.assertEqual(parse(None), ('global', None))
        self.assertEqual(parse('country-4'), ('country', 4))
        self.assertEqual(parse('region-7'), ('region', 7))
        for bad in ('country-x', 'region-', 'foo-1', '', 'country-0', 'country--1'):
            self.assertEqual(parse(bad), ('global', None))

    def test_inherited_from_country_then_global(self):
        CharacterizationFactor.objects.create(
            category=self.mid_a, commodity=self.soy, value=42.0)
        CharacterizationFactor.objects.create(
            category=self.mid_b, commodity=self.soy, country=self.brazil, value=2400.0)
        CharacterizationFactor.objects.create(
            category=self.mid_b, commodity=self.soy, value=7.0)
        rows = self.svc.factor_rows(
            self.soy, ('region', self.mato.pk), ImpactCategory.Level.MIDPOINT)
        row_b = self._row(rows, self.mid_b)
        self.assertEqual((row_b['inherited'], row_b['inherited_from']), (2400.0, 'Brésil'))
        row_a = self._row(rows, self.mid_a)
        self.assertEqual((row_a['inherited'], row_a['inherited_from']), (42.0, 'Global'))
        self.assertIsNone(row_a['value'])

    def test_region_inherits_global_when_country_empty(self):
        CharacterizationFactor.objects.create(
            category=self.mid_a, commodity=self.soy, value=42.0)
        rows = self.svc.factor_rows(
            self.soy, ('region', self.mato.pk), ImpactCategory.Level.MIDPOINT)
        row = self._row(rows, self.mid_a)
        self.assertEqual((row['inherited'], row['inherited_from']), (42.0, 'Global'))

    def test_global_has_no_inheritance(self):
        rows = self.svc.factor_rows(self.soy, ('global', None), ImpactCategory.Level.MIDPOINT)
        self.assertTrue(all(r['inherited'] is None for r in rows))

    def test_own_value_and_source(self):
        source = CommoditySource.objects.create(commodity=self.soy, title='A')
        CharacterizationFactor.objects.create(
            category=self.mid_a, commodity=self.soy, region=self.mato, value=5.0,
            commodity_source=source)
        rows = self.svc.factor_rows(
            self.soy, ('region', self.mato.pk), ImpactCategory.Level.MIDPOINT)
        row = self._row(rows, self.mid_a)
        self.assertEqual((row['value'], row['source_id']), (5.0, source.pk))

    def test_midpoint_and_endpoint_rows_separated(self):
        mid = self.svc.factor_rows(self.soy, ('global', None), ImpactCategory.Level.MIDPOINT)
        end = self.svc.factor_rows(self.soy, ('global', None), ImpactCategory.Level.ENDPOINT)
        self.assertTrue(all(
            r['category'].level == ImpactCategory.Level.MIDPOINT for r in mid))
        self.assertTrue(all(
            r['category'].level == ImpactCategory.Level.ENDPOINT for r in end))
        self.assertIn(self.mid_a, [r['category'] for r in mid])
        self.assertIn(self.end_a, [r['category'] for r in end])

    def test_chips_list_locations_with_factors(self):
        argentina = Country.objects.create(name='Argentine')
        CharacterizationFactor.objects.create(
            category=self.mid_a, commodity=self.soy, region=self.mato, value=1.0)
        CharacterizationFactor.objects.create(
            category=self.mid_a, commodity=self.soy, country=argentina, value=1.0)
        chips = self.svc.location_chips(self.soy, ('global', None))
        self.assertEqual([c['key'] for c in chips],
                         ['global', f'country-{argentina.pk}', f'region-{self.mato.pk}'])
        self.assertEqual(chips[2]['label'], 'Brésil › Mato Grosso')
        self.assertEqual([c['active'] for c in chips], [True, False, False])

    def test_chips_include_current_location_without_factor(self):
        chips = self.svc.location_chips(self.soy, ('country', self.brazil.pk))
        self.assertEqual([c['key'] for c in chips], ['global', f'country-{self.brazil.pk}'])
        self.assertEqual([c['active'] for c in chips], [False, True])

    def test_save_zero_kept_none_deletes(self):
        loc = ('region', self.mato.pk)
        self.svc.save_factors(self.soy, loc, {self.mid_a.pk: (0.0, None)}, None)
        cf = CharacterizationFactor.objects.get(commodity=self.soy, category=self.mid_a)
        self.assertEqual((cf.value, cf.region_id, cf.country_id), (0.0, self.mato.pk, None))
        self.svc.save_factors(self.soy, loc, {self.mid_a.pk: (3.0, None)}, None)
        self.assertEqual(CharacterizationFactor.objects.filter(commodity=self.soy).count(), 1)
        self.svc.save_factors(self.soy, loc, {self.mid_a.pk: (None, None)}, None)
        self.assertFalse(CharacterizationFactor.objects.filter(commodity=self.soy).exists())

    def test_save_global_does_not_touch_other_locations(self):
        CharacterizationFactor.objects.create(
            category=self.mid_a, commodity=self.soy, country=self.brazil, value=9.0)
        self.svc.save_factors(self.soy, ('global', None), {self.mid_a.pk: (1.0, None)}, None)
        self.svc.save_factors(self.soy, ('global', None), {self.mid_a.pk: (None, None)}, None)
        self.assertEqual(CharacterizationFactor.objects.filter(commodity=self.soy).count(), 1)


class FactorGridViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.creator = user_model.objects.create_user('createur', password='x', role='CREATOR')
        self.subscriber = user_model.objects.create_user('abonne', password='x')
        self.soy = Commodity.objects.create(name='Soja')
        self.brazil = Country.objects.create(name='Brésil')
        self.mato = SubnationalRegion.objects.create(name='Mato Grosso', country=self.brazil)
        method, _ = ImpactMethod.objects.get_or_create(name='M')
        self.cat = ImpactCategory.objects.create(
            method=method, key='t9_view', name='Vue', level=ImpactCategory.Level.MIDPOINT)
        self.url = reverse('dashboard:commodity_factors', args=[self.soy.pk])
        self.detail = reverse('dashboard:commodity_detail', args=[self.soy.pk])

    def _post(self, value, lieu='global', **extra):
        data = {'lieu': lieu, f'value_{self.cat.pk}': value, f'source_{self.cat.pk}': ''}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_zero_is_kept_empty_deletes(self):
        self.client.force_login(self.creator)
        self._post('0')
        cf = CharacterizationFactor.objects.get(commodity=self.soy, category=self.cat)
        self.assertEqual(cf.value, 0.0)
        self._post('')
        self.assertFalse(CharacterizationFactor.objects.filter(
            commodity=self.soy, category=self.cat).exists())

    def test_comma_decimal_accepted(self):
        self.client.force_login(self.creator)
        self._post('3 200,5')
        self.assertEqual(CharacterizationFactor.objects.get(category=self.cat).value, 3200.5)
        self._post('-10,5')
        self.assertEqual(CharacterizationFactor.objects.get(category=self.cat).value, -10.5)

    def test_invalid_number_is_field_error_and_saves_nothing(self):
        self.client.force_login(self.creator)
        response = self._post('abc')
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'value_{self.cat.pk}', response.context['factor_form'].errors)
        self.assertFalse(CharacterizationFactor.objects.exists())

    def test_redirect_keeps_lieu_and_saves_region(self):
        self.client.force_login(self.creator)
        lieu = f'region-{self.mato.pk}'
        response = self._post('5', lieu=lieu)
        self.assertRedirects(
            response, f'{self.detail}?lieu={lieu}', fetch_redirect_response=False)
        cf = CharacterizationFactor.objects.get(category=self.cat)
        self.assertEqual(cf.region_id, self.mato.pk)

    def test_source_of_other_commodity_rejected(self):
        other = CommoditySource.objects.create(
            commodity=Commodity.objects.create(name='Blé'), title='X')
        self.client.force_login(self.creator)
        response = self._post('1', **{f'source_{self.cat.pk}': str(other.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CharacterizationFactor.objects.exists())

    def test_subscriber_forbidden_and_read_only_page(self):
        self.client.force_login(self.subscriber)
        self.assertEqual(self._post('1').status_code, 403)
        page = self.client.get(self.detail)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'id="commodity-factors-form"')

    def test_page_shows_grid_chips_and_selector_for_creator(self):
        CharacterizationFactor.objects.create(
            category=self.cat, commodity=self.soy, value=2400.0)
        self.client.force_login(self.creator)
        page = self.client.get(self.detail, {'lieu': f'region-{self.mato.pk}'})
        self.assertContains(page, 'id="commodity-factors-form"')
        self.assertContains(page, 'aria-current="true"')
        self.assertContains(page, '<optgroup label="Brésil">')
        self.assertContains(page, 'Brésil › Mato Grosso')
        self.assertContains(page, f'name="value_{self.cat.pk}"')

    def test_tiny_inherited_factor_not_rounded_to_zero(self):
        CharacterizationFactor.objects.create(
            category=self.cat, commodity=self.soy, value=3e-7)
        region = f'region-{self.mato.pk}'
        self.client.force_login(self.creator)
        page = self.client.get(self.detail, {'lieu': region})
        self.assertContains(page, '0,0000003 ← Global')
        self.assertNotContains(page, 'placeholder="0 ←')
        self.client.logout()
        self.client.force_login(self.subscriber)
        page = self.client.get(self.detail, {'lieu': region})
        self.assertContains(page, '0,0000003 ← Global')


class ModifierPageTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.creator = user_model.objects.create_user('createur10', password='x', role='CREATOR')
        self.subscriber = user_model.objects.create_user('abonne10', password='x')
        self.soy = Commodity.objects.create(name='Soja')
        method, _unused = ImpactMethod.objects.get_or_create(name='M')
        self.land = ImpactCategory.objects.create(
            method=method, key='t10_land', name='Usage des sols',
            level=ImpactCategory.Level.MIDPOINT)
        self.div = ImpactCategory.objects.create(
            method=method, key='t10_div', name='Diversité',
            level=ImpactCategory.Level.ENDPOINT)
        self.detail = reverse('dashboard:commodity_detail', args=[self.soy.pk])
        self.create_url = reverse('dashboard:commodity_modifier_create', args=[self.soy.pk])
        self.client.force_login(self.creator)

    def _data(self, name='Bio', rows=(), prefix='mod-new', eprefix='effects-new', **extra):
        data = {f'{prefix}-name': name, f'{prefix}-description': '', f'{prefix}-source': '',
                f'{eprefix}-TOTAL_FORMS': str(len(rows)), f'{eprefix}-INITIAL_FORMS': '0',
                f'{eprefix}-MIN_NUM_FORMS': '0', f'{eprefix}-MAX_NUM_FORMS': '1000'}
        for i, (category, percent) in enumerate(rows):
            data[f'{eprefix}-{i}-category'] = str(category.pk)
            data[f'{eprefix}-{i}-percent'] = percent
        data.update(extra)
        return data

    def test_create_modifier_with_effects(self):
        response = self.client.post(
            self.create_url, self._data(rows=[(self.land, '-10'), (self.div, '-15')]))
        self.assertEqual(response.status_code, 302)
        modifier = CommodityModifier.objects.get(commodity=self.soy, name='Bio')
        self.assertEqual(modifier.created_by, self.creator)
        self.assertEqual(
            {e.category_id: e.percent for e in modifier.effects.all()},
            {self.land.pk: -10.0, self.div.pk: -15.0})

    def test_duplicate_name_rejected(self):
        CommodityModifier.objects.create(commodity=self.soy, name='Bio')
        response = self.client.post(self.create_url, self._data(name='Bio'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['new_modifier_form'].errors['name'])
        self.assertEqual(CommodityModifier.objects.count(), 1)

    def test_effect_below_minus_100_rejected(self):
        response = self.client.post(self.create_url, self._data(rows=[(self.land, '-101')]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CommodityModifier.objects.exists())

    def test_percent_comma_accepted(self):
        self.client.post(self.create_url, self._data(rows=[(self.land, '-10,5')]))
        self.assertEqual(ModifierEffect.objects.get().percent, -10.5)

    def test_update_modifier_effects(self):
        modifier = CommodityModifier.objects.create(commodity=self.soy, name='Bio')
        effect = ModifierEffect.objects.create(
            modifier=modifier, category=self.land, percent=-5)
        url = reverse('dashboard:commodity_modifier_update', args=[self.soy.pk, modifier.pk])
        p, e = f'mod-{modifier.pk}', f'effects-{modifier.pk}'
        data = self._data(name='Bio 2', prefix=p, eprefix=e, rows=[(self.land, '-7,5')])
        data.update({f'{e}-INITIAL_FORMS': '1', f'{e}-0-id': str(effect.pk),
                     f'{e}-0-modifier': str(modifier.pk)})
        self.assertEqual(self.client.post(url, data).status_code, 302)
        modifier.refresh_from_db()
        effect.refresh_from_db()
        self.assertEqual((modifier.name, effect.percent), ('Bio 2', -7.5))

    def test_delete_used_modifier(self):
        modifier = CommodityModifier.objects.create(commodity=self.soy, name='Bio')
        flows = [make_production(commodity=self.soy, year=2024 + i, production=1,
                                 company=Company.objects.create(name=f'C{i}'))
                 for i in range(2)]
        for flow in flows:
            flow.modifiers.add(modifier)
        page = self.client.get(self.detail)
        self.assertEqual(page.context['modifier_cards'][0]['flow_count'], 2)
        self.assertContains(page, 'data-confirm=')
        url = reverse('dashboard:commodity_modifier_delete', args=[self.soy.pk, modifier.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(CommodityModifier.objects.exists())
        for flow in flows:
            flow.refresh_from_db()
            self.assertEqual(flow.modifiers.count(), 0)

    def test_modifier_of_other_commodity_404(self):
        other = CommodityModifier.objects.create(
            commodity=Commodity.objects.create(name='Blé'), name='Bio')
        for name in ('commodity_modifier_update', 'commodity_modifier_delete'):
            url = reverse(f'dashboard:{name}', args=[self.soy.pk, other.pk])
            self.assertEqual(self.client.post(url, {}).status_code, 404)
        self.assertTrue(CommodityModifier.objects.filter(pk=other.pk).exists())

    def test_adjusted_preview(self):
        CharacterizationFactor.objects.create(
            category=self.land, commodity=self.soy, value=3200.0)
        modifier = CommodityModifier.objects.create(commodity=self.soy, name='Bio')
        ModifierEffect.objects.create(modifier=modifier, category=self.land, percent=-10)
        ModifierEffect.objects.create(modifier=modifier, category=self.div, percent=-10)
        from .services.commodity_sheet import modifier_cards
        effects = modifier_cards(self.soy, ('global', None))[0]['effects']
        by_cat = {e['effect'].category_id: e for e in effects}
        self.assertAlmostEqual(by_cat[self.land.pk]['adjusted'], 2880)
        self.assertIsNone(by_cat[self.div.pk]['adjusted'])

    def test_subscriber_forbidden_and_read_only(self):
        CommodityModifier.objects.create(commodity=self.soy, name='Bio')
        self.client.force_login(self.subscriber)
        self.assertEqual(self.client.post(self.create_url, self._data()).status_code, 403)
        page = self.client.get(self.detail)
        self.assertContains(page, 'Bio')
        self.assertNotContains(page, 'data-confirm')

    def _existing(self, *pairs):
        modifier = CommodityModifier.objects.create(commodity=self.soy, name='Bio')
        effects = [ModifierEffect.objects.create(modifier=modifier, category=c, percent=p)
                   for c, p in pairs]
        url = reverse('dashboard:commodity_modifier_update', args=[self.soy.pk, modifier.pk])
        e = f'effects-{modifier.pk}'
        return modifier, effects, url, e

    def _post_effects(self, modifier, url, e, effects, rows):
        """rows : (effect|None, category, percent, delete)."""
        data = self._data(prefix=f'mod-{modifier.pk}', eprefix=e, rows=[])
        data[f'{e}-TOTAL_FORMS'] = str(len(rows))
        data[f'{e}-INITIAL_FORMS'] = str(len(effects))
        for i, (effect, category, percent, delete) in enumerate(rows):
            data[f'{e}-{i}-category'] = str(category.pk)
            data[f'{e}-{i}-percent'] = percent
            if effect:
                data[f'{e}-{i}-id'] = str(effect.pk)
                data[f'{e}-{i}-modifier'] = str(modifier.pk)
            if delete:
                data[f'{e}-{i}-DELETE'] = 'on'
        return self.client.post(url, data)

    def test_delete_and_readd_same_category(self):
        modifier, effects, url, e = self._existing((self.land, -5))
        response = self._post_effects(modifier, url, e, effects, [
            (effects[0], self.land, '-5', True), (None, self.land, '-20', False)])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            [x.percent for x in modifier.effects.filter(category=self.land)], [-20.0])

    def test_swap_categories_never_500(self):
        modifier, effects, url, e = self._existing((self.land, -5), (self.div, -6))
        response = self._post_effects(modifier, url, e, effects, [
            (effects[0], self.div, '-5', False), (effects[1], self.land, '-6', False)])
        self.assertIn(response.status_code, (200, 302))
        self.assertEqual(modifier.effects.count(), 2)

    def test_percent_is_signed(self):
        modifier = CommodityModifier.objects.create(commodity=self.soy, name='Bio')
        ModifierEffect.objects.create(modifier=modifier, category=self.land, percent=20)
        ModifierEffect.objects.create(modifier=modifier, category=self.div, percent=-10)
        page = self.client.get(self.detail)
        self.assertContains(page, '+20 %')
        self.assertContains(page, '−10 %')


class CommodityIdentityTranslationTests(TestCase):
    """Les libellés et choix du formulaire d'identité suivent la langue de l'interface."""

    def setUp(self):
        user_model = get_user_model()
        self.creator = user_model.objects.create_user('cr_i18n', password='x', role='CREATOR')
        self.subscriber = user_model.objects.create_user('ab_i18n', password='x')
        self.soy = Commodity.objects.create(name='Soja')
        self.url = reverse('dashboard:commodity_detail', args=[self.soy.pk])

    def _get(self, user, language):
        self.client.force_login(user)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
        return self.client.get(self.url)

    def test_english_read_only_labels(self):
        response = self._get(self.subscriber, 'en')
        self.assertContains(response, '<dd>Very low</dd>')
        self.assertContains(response, 'Dependency — water supply')
        self.assertContains(response, '<dd>Agriculture</dd>')
        self.assertNotContains(response, 'Dépendance — ')
        self.assertNotContains(response, 'Classe de perte')

    def test_french_read_only_choices(self):
        response = self._get(self.subscriber, 'fr')
        self.assertContains(response, '<dd>Très faible</dd>')
        self.assertContains(response, 'Dépendance — approvisionnement en eau')
        self.assertNotContains(response, 'Very low')

    def test_english_creator_form(self):
        response = self._get(self.creator, 'en')
        self.assertContains(response, '>Very low</option>')
        self.assertContains(response, '>Very high</option>')
        self.assertContains(response, '>Urbanization</option>')
        self.assertContains(response, 'Unit of measure')
        self.assertNotContains(response, 'Dépendance — ')
        self.assertNotContains(response, 'Unité de mesure')
        self.assertNotContains(response, 'Détermine lequel')

    def test_french_creator_form_keeps_codes(self):
        response = self._get(self.creator, 'fr')
        self.assertContains(response, '<option value="VL" selected>Très faible</option>')
        self.assertContains(response, '<option value="Mining">Extraction minière</option>')
        self.assertNotContains(response, 'Very low')


class ModifierEffectCategoryChoicesTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.creator = user_model.objects.create_user('cr_cat', password='x', role='CREATOR')
        self.soy = Commodity.objects.create(name='Soja')
        self.category = ImpactCategory.objects.get(
            key='impact_midpoint_ReCiPe2016_climate_change')
        self.client.force_login(self.creator)
        self.url = reverse('dashboard:commodity_detail', args=[self.soy.pk])

    def _add_modifiers(self, count):
        start = CommodityModifier.objects.filter(commodity=self.soy).count()
        for i in range(start, start + count):
            modifier = CommodityModifier.objects.create(commodity=self.soy, name=f'Mod {i}')
            ModifierEffect.objects.create(
                modifier=modifier, category=self.category, percent=-10)

    def _queries(self):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(self.url).status_code, 200)
        return len(ctx)

    def test_query_count_does_not_grow_per_modifier(self):
        self._add_modifiers(1)
        baseline = self._queries()
        self._add_modifiers(5)
        self.assertLessEqual(self._queries(), baseline + 10)

    def test_category_options_show_name_not_method_and_key(self):
        self._add_modifiers(1)
        response = self.client.get(self.url)
        self.assertContains(response, f'>{self.category.name}</option>')
        self.assertNotContains(response, f'— {self.category.key}</option>')


class PopulateAcmeSoyTests(TestCase):
    """Le soja du Mato Grosso garde les totaux 40 000 / 45 000 à chaque exécution."""

    def _soy_supply(self):
        from django.db.models import Sum
        rows = Flow.objects.filter(
            kind='SUPPLY', what__name='Soja', from_region__name='Mato Grosso',
            to_asset__name__icontains='Bretagne')
        totals = {row['year']: row['total'] for row in
                  rows.values('year').annotate(total=Sum('quantity'))}
        return rows, totals

    def _assert_split(self):
        rows, totals = self._soy_supply()
        self.assertEqual(totals, {2023: 40_000, 2024: 45_000})
        for year in (2023, 2024):
            self.assertEqual(rows.filter(year=year, modifiers__isnull=False).count(), 1)
            self.assertEqual(rows.filter(year=year, modifiers__isnull=True).count(), 1)

    def test_fresh_and_second_run(self):
        from django.core.management import call_command
        call_command('populate_acme')
        self._assert_split()
        call_command('populate_acme')
        self._assert_split()

    def test_rerun_on_legacy_unsplit_database(self):
        from django.core.management import call_command
        call_command('populate_acme')
        rows, _ = self._soy_supply()
        rows.filter(modifiers__isnull=False).delete()
        for year, total in ((2023, 40_000), (2024, 45_000)):
            rows.filter(year=year).update(quantity=total)
        self.assertEqual(self._soy_supply()[1], {2023: 40_000, 2024: 45_000})
        call_command('populate_acme')
        self._assert_split()


class LeapLocateSplitSupplyTests(TestCase):
    """Deux lignes de même fournisseur (scission certifié / classique) = un seul trait."""

    def test_split_supply_draws_one_link(self):
        from .views import _get_leap_locate_data
        country = Country.objects.create(name='Brésil')
        region = SubnationalRegion.objects.create(
            name='Mato Grosso', country=country, Mean_X=-55.0, Mean_Y=-13.0)
        company = Company.objects.create(name='Acme split')
        asset = Asset.objects.create(
            name='Site Bretagne', latitude=48.0, longitude=-3.0, country=country)
        Ownership.objects.create(asset=asset, company=company, share=1)
        soy = Commodity.objects.create(name='Soja')
        modifier = CommodityModifier.objects.create(commodity=soy, name='Certifié')
        make_supply(what=soy, year=2024, quantity=25.0, tier=2, origin=region,
                    destination=asset).modifiers.add(modifier)
        make_supply(what=soy, year=2024, quantity=15.0, tier=2, origin=region,
                    destination=asset)
        data = _get_leap_locate_data(company)
        self.assertEqual(len(data['supplier_links']['features']), 1)
        self.assertEqual(len(data['suppliers']['features']), 1)
