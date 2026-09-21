"""Aller-retour de l'export : Flow en base → classeur → parse → import.

C'est ce test qui garantit que `build_flow_export()` écrit un fichier que
`parse_file()` accepte sans erreur, et que les flux réimportés sont identiques
aux flux exportés — y compris leurs extrémités, qui ne voyagent que par leur nom.
"""
from django.test import TestCase

from dashboard.models import (
    Asset, Commodity, Company, Country, Flow, FlowKind, FlowScope, Ownership,
    SubnationalRegion,
)
from dashboard.testing import (
    make_declared_emission, make_inventory, make_production, make_supply,
)
from imports.services.excel_export import build_flow_export, flow_row, flows_of
from imports.services.excel_parser import parse_file
from imports.services.importer import save_import


class FlowExportTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(name='Testland')
        cls.region = SubnationalRegion.objects.create(
            name='Testrégion', country=cls.country, Mean_X=1.0, Mean_Y=45.0)
        cls.company = Company.objects.create(name='Testco')
        cls.other = Company.objects.create(name='Autreco')
        cls.asset = Asset.objects.create(
            name='Site test', country=cls.country, subnational_region=cls.region,
            latitude=45.0, longitude=1.0)
        cls.other_asset = Asset.objects.create(
            name='Site tiers', country=cls.country, latitude=46.0, longitude=2.0)
        Ownership.objects.create(asset=cls.asset, company=cls.company, share='1')
        Ownership.objects.create(asset=cls.other_asset, company=cls.other, share='1')
        cls.wheat = Commodity.objects.create(name='Testblé', unit='tonnes')

        # Un flux par type d'extrémité rencontré dans les jeux réels.
        make_production(commodity=cls.wheat, year=2024, production=1_000,
                        asset=cls.asset, estimated_revenue=500_000.0)
        make_inventory(asset=cls.asset, key='water', year=2024, value=12_345.0)
        make_inventory(asset=cls.asset, key='co2', year=2024, value=678.0)
        make_supply(what=cls.wheat, year=2024, quantity=300,
                    origin=cls.region, destination=cls.asset, tier=2)
        make_supply(what=cls.wheat, year=2024, quantity=100,
                    origin=cls.country, destination=cls.company, tier=3)
        make_declared_emission(company=cls.company, year=2024,
                               scope=FlowScope.SCOPE_1, value=900.0)
        # Flux d'une autre entreprise : sert au filtrage.
        make_production(commodity=cls.wheat, year=2024, production=42,
                        asset=cls.other_asset)

    def test_export_keeps_only_the_requested_companies(self):
        exported = flows_of([self.company])
        self.assertEqual(exported.count(), 6)
        self.assertEqual(flows_of([]).count(), 7)

    def test_endpoints_travel_as_type_and_name(self):
        supply = Flow.objects.get(kind=FlowKind.SUPPLY, from_region=self.region)
        row = flow_row(supply)
        self.assertEqual(row['from_type'], 'region')
        self.assertEqual(row['from_name'], 'Testrégion')
        self.assertEqual(row['to_type'], 'asset')
        self.assertEqual(row['to_name'], 'Site test')

        water = Flow.objects.get(what__key='water')
        self.assertEqual(flow_row(water)['from_type'], 'milieu')
        self.assertEqual(flow_row(water)['from_name'], '')

        production = Flow.objects.get(kind=FlowKind.PRODUCTION, from_asset=self.asset)
        self.assertEqual(flow_row(production)['to_type'], '')
        self.assertEqual(flow_row(production)['to_name'], '')

    def test_export_reimports_identically(self):
        buffer, count = build_flow_export([self.company])
        self.assertEqual(count, 6)
        before = sorted(
            tuple(flow_row(flow).items()) for flow in flows_of([self.company])
        )

        Flow.objects.filter(pk__in=[f.pk for f in flows_of([self.company])]).delete()
        parsed = parse_file(buffer)
        self.assertEqual([row['status'] for row in parsed['Flow']], ['ok'] * 6)

        save_import(parsed)
        after = sorted(
            tuple(flow_row(flow).items()) for flow in flows_of([self.company])
        )
        self.assertEqual(after, before)

    def test_reexporting_an_already_loaded_file_flags_duplicates(self):
        buffer, _ = build_flow_export([self.company])
        parsed = parse_file(buffer)
        self.assertEqual({row['status'] for row in parsed['Flow']}, {'duplicate'})
