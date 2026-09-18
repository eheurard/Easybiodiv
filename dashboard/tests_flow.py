"""Tests de la refonte « table Flow unique » (spec 2026-09-18)."""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from .models import (
    ALL_ENDPOINTS, FLOW_RULES, TECHNICAL_COMMODITIES, Asset, Commodity, Company, Country,
    Flow, FlowKind, FlowScope, Ownership, SubnationalRegion,
)
from .services import flows as flow_service
from .testing import make_inventory, make_production


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


class FlowRulesTests(TestCase):

    def setUp(self):
        self.wheat = Commodity.objects.create(name='Blé')
        # Objets distincts de chaque côté : un approvisionnement ne peut pas
        # relier un lieu à lui-même.
        self.objects = {}
        for side, suffix in (('from', 'A'), ('to', 'B')):
            country = Country.objects.create(
                name=f'Pays {suffix}', water_ownership='Public', land_ownership='Private')
            self.objects[side] = {
                'country': country,
                'region': SubnationalRegion.objects.create(
                    name=f'Région {suffix}', country=country),
                'asset': Asset.objects.create(
                    name=f'Actif {suffix}', latitude=1.0, longitude=2.0, country=country),
                'company': Company.objects.create(name=f'Entreprise {suffix}'),
            }

    def _ends(self, side, endpoint):
        if endpoint is None:
            return {}
        if endpoint == 'environment':
            return {f'{side}_environment': True}
        return {f'{side}_{endpoint}': self.objects[side][endpoint]}

    def _create(self, kind, origin, destination, **extra):
        return Flow.objects.create(
            kind=kind, what=self.wheat, year=2024, quantity=1.0,
            **self._ends('from', origin), **self._ends('to', destination), **extra,
        )

    def test_database_accepts_exactly_the_combinations_of_flow_rules(self):
        for kind, rule in FLOW_RULES.items():
            for origin in ALL_ENDPOINTS:
                for destination in ALL_ENDPOINTS:
                    allowed = origin in rule.origins and destination in rule.destinations
                    with self.subTest(kind=kind, origin=origin, destination=destination):
                        if allowed:
                            with transaction.atomic():
                                self._create(kind, origin, destination).delete()
                        else:
                            with self.assertRaises(IntegrityError), transaction.atomic():
                                self._create(kind, origin, destination)

    def test_two_origins_are_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Flow.objects.create(
                kind=FlowKind.SUPPLY, what=self.wheat, year=2024, quantity=1.0,
                from_asset=self.objects['from']['asset'],
                from_country=self.objects['from']['country'],
                to_company=self.objects['to']['company'],
            )

    def test_supply_from_an_asset_to_itself_is_rejected(self):
        asset = self.objects['from']['asset']
        with self.assertRaises(IntegrityError), transaction.atomic():
            Flow.objects.create(
                kind=FlowKind.SUPPLY, what=self.wheat, year=2024, quantity=1.0,
                from_asset=asset, to_asset=asset,
            )

    def test_estimated_revenue_only_on_production(self):
        self._create(FlowKind.PRODUCTION, 'asset', None, estimated_revenue=10.0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._create(FlowKind.EMISSION, 'asset', 'environment', estimated_revenue=10.0)

    def test_scope_defaults_to_undefined(self):
        flow = self._create(FlowKind.EMISSION, 'company', 'environment')
        self.assertEqual(flow.scope, FlowScope.UNDEFINED)

    def test_endpoint_types_and_str(self):
        flow = self._create(FlowKind.CONSUMPTION, 'environment', 'asset')
        self.assertEqual((flow.origin_type, flow.destination_type), ('environment', 'asset'))
        self.assertEqual(str(flow), 'Consommation — Blé (2024)')

    def test_a_commodity_in_use_cannot_be_deleted(self):
        self._create(FlowKind.PRODUCTION, 'asset', None)
        with self.assertRaises(ProtectedError):
            self.wheat.delete()


class LatestInventoryTests(TestCase):

    def setUp(self):
        country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private')
        self.mine = Asset.objects.create(name='Mine', latitude=1.0, longitude=2.0, country=country)
        self.plant = Asset.objects.create(
            name='Usine', latitude=1.0, longitude=2.0, country=country)

    def test_values_are_summed_for_the_latest_year_of_each_asset(self):
        make_inventory(asset=self.mine, key='water', year=2023, value=10.0)
        make_inventory(asset=self.mine, key='water', year=2024, value=100.0)
        make_inventory(asset=self.mine, key='water', year=2024, value=5.0)
        make_inventory(asset=self.mine, key='co2', year=2024, value=50.0)
        make_inventory(asset=self.plant, key='waste', year=2022, value=7.0)
        result = flow_service.latest_inventory(
            [self.mine.pk, self.plant.pk], ('water', 'co2', 'waste'))
        self.assertEqual(result[self.mine.pk], {
            'water': {'value': 105.0, 'unit': 'm³'},
            'co2': {'value': 50.0, 'unit': 'tCO₂e'},
        })
        self.assertEqual(result[self.plant.pk], {'waste': {'value': 7.0, 'unit': 't'}})

    def test_keys_outside_the_selection_do_not_shift_the_year(self):
        make_inventory(asset=self.mine, key='water', year=2023, value=10.0)
        make_inventory(asset=self.mine, key='energy', year=2024, value=999.0)
        result = flow_service.latest_inventory([self.mine.pk], ('water',))
        self.assertEqual(result[self.mine.pk], {'water': {'value': 10.0, 'unit': 'm³'}})

    def test_inventory_total_by_theme_and_year(self):
        make_inventory(asset=self.mine, key='water', year=2024, value=100.0)
        make_inventory(asset=self.mine, key='water', year=2023, value=1.0)
        self.assertEqual(flow_service.inventory_total(self.mine, 'water', 2024), 100.0)


class FlowAdminTests(TestCase):

    def setUp(self):
        self.root = get_user_model().objects.create_superuser(
            'root', 'root@example.com', 'pass')
        self.client.force_login(self.root)
        country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private')
        self.asset = Asset.objects.create(
            name='Usine', latitude=1.0, longitude=2.0, country=country)
        self.co2 = Commodity.objects.technical('co2')

    def _post(self, **ends):
        data = {
            'kind': 'EMISSION', 'what': self.co2.pk, 'scope': 'undefined',
            'year': 2024, 'quantity': 5, 'tier': 0,
        }
        data.update(ends)
        return self.client.post(reverse('admin:dashboard_flow_add'), data)

    def test_rule_violation_is_shown_in_the_form(self):
        response = self._post(from_asset=self.asset.pk)  # émission sans destination
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'va vers le milieu')
        self.assertFalse(Flow.objects.exists())

    def test_valid_emission_is_saved_with_its_author(self):
        response = self._post(from_asset=self.asset.pk, to_environment='on')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Flow.objects.get().created_by, self.root)


class ProductionServiceTests(TestCase):

    def setUp(self):
        country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private')
        self.company = Company.objects.create(name='Acme')
        self.a1 = Asset.objects.create(name='A1', latitude=1.0, longitude=2.0, country=country)
        self.a2 = Asset.objects.create(name='A2', latitude=1.0, longitude=2.0, country=country)
        Ownership.objects.create(asset=self.a1, company=self.company, share=1)
        self.soy = Commodity.objects.create(name='Soja')

    def _produce(self, **kwargs):
        return make_production(commodity=self.soy, production=1.0, **kwargs)

    def test_productions_keep_creation_order_across_years(self):
        first = self._produce(asset=self.a1, year=2024)
        second = self._produce(asset=self.a1, year=2023)
        self.assertEqual(flow_service.productions([self.a1.pk]), [first, second])

    def test_latest_productions_keep_the_latest_year_of_each_asset(self):
        self._produce(asset=self.a1, year=2023)
        recent = self._produce(asset=self.a1, year=2024)
        older_asset = self._produce(asset=self.a2, year=2022)
        self.assertEqual(
            flow_service.latest_productions([self.a1.pk, self.a2.pk]), [recent, older_asset])

    def test_other_kinds_are_not_productions(self):
        make_inventory(asset=self.a1, key='co2', year=2024, value=5.0)
        self.assertEqual(flow_service.productions([self.a1.pk]), [])

    def test_company_productions_merge_the_company_and_its_assets(self):
        own = self._produce(asset=self.a1, year=2024)
        declared = self._produce(company=self.company, year=2024)
        self._produce(asset=self.a2, year=2024)  # actif non détenu
        self.assertEqual(flow_service.company_productions(self.company), [own, declared])

    def test_a_more_recent_production_does_not_shift_the_inventory_year(self):
        make_inventory(asset=self.a1, key='water', year=2023, value=10.0)
        self._produce(asset=self.a1, year=2024)
        result = flow_service.latest_inventory([self.a1.pk], ('water',))
        self.assertEqual(result[self.a1.pk]['water']['value'], 10.0)
