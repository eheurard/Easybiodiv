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
from imports.services.excel_export import (
    build_flow_export, build_full_export, flow_row, flows_of,
)
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


class FullExportTests(TestCase):
    """Export complet : toutes les feuilles, réimportables sans perte.

    Deux pièges de relecture sont couverts : le parseur lit chaque cellule en
    texte, si bien qu'une date Excel reviendrait « 2024-03-15 00:00:00 », et une
    part de détention doit garder ses quatre décimales.
    """

    @classmethod
    def setUpTestData(cls):
        from datetime import date
        from decimal import Decimal

        from dashboard.models import (
            Company_Policy, Company_Revenue_Sector, Policy_Level, Policy_Subcategory,
            Policy_Type, Sector, SubSector,
        )

        country = Country.objects.create(
            name='Testland', water_ownership='Public', land_ownership='Privé')
        region = SubnationalRegion.objects.create(name='Testrégion', country=country)
        cls.company = Company.objects.create(name='Testco')
        cls.asset = Asset.objects.create(
            name='Site test', country=country, subnational_region=region,
            latitude=45.0, longitude=1.0)
        Ownership.objects.create(
            asset=cls.asset, company=cls.company, share=Decimal('0.575'))
        wheat = Commodity.objects.create(name='Testblé', unit='tonnes')
        make_production(commodity=wheat, year=2024, production=1_000, asset=cls.asset)

        policy_type = Policy_Type.objects.create(name='Réglementaire')
        subcategory = Policy_Subcategory.objects.create(name='EUDR', policy_type=policy_type)
        cls.level = Policy_Level.objects.create(name='Conforme', subcategory=subcategory)
        Company_Policy.objects.create(
            company=cls.company, policy_level=cls.level,
            policy_date=date(2024, 3, 15), comment='Adoptée au conseil de mars')

        sector = Sector.objects.create(name='Agriculture test')
        subsector = SubSector.objects.create(name='Céréales test', sector=sector)
        Company_Revenue_Sector.objects.create(
            company=cls.company, subsector=subsector, year=2024, revenue=1_000_000)

    def _export_delete_reimport(self, queryset):
        """Exporte, supprime `queryset`, puis recharge le classeur exporté."""
        buffer, _ = build_full_export()
        queryset.delete()
        save_import(parse_file(buffer))

    def test_every_importable_sheet_is_exported_with_the_import_headers(self):
        import openpyxl

        from imports.services.constants import SHEET_COLUMNS

        buffer, counts = build_full_export()
        wb = openpyxl.load_workbook(buffer)
        self.assertEqual(wb.sheetnames, list(SHEET_COLUMNS))
        for sheet_name, columns in SHEET_COLUMNS.items():
            header = [cell.value for cell in wb[sheet_name][1]]
            self.assertEqual(header, columns, sheet_name)
        self.assertEqual(counts['Company_Policy'], 1)

    def test_full_export_parses_without_a_single_error(self):
        buffer, _ = build_full_export()
        errors = [
            (sheet, row.get('message'))
            for sheet, rows in parse_file(buffer).items()
            for row in rows if row['status'] == 'error'
        ]
        self.assertEqual(errors, [])

    def test_policy_date_survives_the_round_trip(self):
        from datetime import date

        from dashboard.models import Company_Policy

        self._export_delete_reimport(Company_Policy.objects.all())
        policy = Company_Policy.objects.get(company=self.company)
        self.assertEqual(policy.policy_date, date(2024, 3, 15))
        self.assertEqual(policy.comment, 'Adoptée au conseil de mars')

    def test_ownership_share_keeps_its_four_decimals(self):
        from decimal import Decimal

        self._export_delete_reimport(Ownership.objects.all())
        self.assertEqual(
            Ownership.objects.get(asset=self.asset).share, Decimal('0.5750'))

    def test_policy_without_level_is_exported_and_flagged_on_reimport(self):
        # policy_level est nullable : la ligne sort avec des noms vides au lieu
        # de faire échouer tout l'export, et l'aperçu d'import la signale.
        from dashboard.models import Company_Policy

        Company_Policy.objects.create(
            company=Company.objects.create(name='Sans niveau'), policy_level=None)
        buffer, counts = build_full_export()
        self.assertEqual(counts['Company_Policy'], 2)
        statuses = [row['status'] for row in parse_file(buffer)['Company_Policy']]
        self.assertIn('error', statuses)
