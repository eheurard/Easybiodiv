"""Aller-retour complet : template généré → fichier rempli → parse → import.

C'est le test qui garantit que les en-têtes émis par `build_template()` sont
exactement ceux que `parse_file()` attend, et que l'ordre d'import résout bien
les FK déclarées dans un seul et même classeur.
"""
import io

import openpyxl
from django.test import TestCase

from dashboard.models import (
    Asset, CharacterizationFactor, ClimateScenario, Commodity,
    Country, Exchange, ScenarioVariable, Sector, SectorCreditProfile,
    SupplyNode,
)
from imports.services.excel_parser import parse_file
from imports.services.excel_template import build_template
from imports.services.importer import save_import

CAT_ECOSYSTEM = 'impact_endpoint_ReCiPe2016_ecosystem_diversity'


def _fill(wb, sheet_name, *row_dicts):
    """Append rows to a generated sheet, matching values to its real headers."""
    ws = wb[sheet_name]
    header = [c.value for c in ws[1]]
    for data in row_dicts:
        unknown = set(data) - set(header)
        assert not unknown, f'{sheet_name} : colonnes inconnues {unknown}'
        ws.append([data.get(col, None) for col in header])


class RoundTripTest(TestCase):
    def setUp(self):
        wb = openpyxl.load_workbook(build_template())

        _fill(wb, 'Country', {
            'name': 'Testland', 'water_ownership': 'public',
            'land_ownership': 'private', 'restoration_cost_m2': 12.5})
        _fill(wb, 'SubnationalRegion', {
            'name': 'Testrégion', 'country_name': 'Testland',
            'Mean_X': 1.5, 'Mean_Y': 45.0})
        _fill(wb, 'Commodity', {
            'name': 'Testsoja', 'unit': 'tonnes',
            'biodiversity_loss_class': 'Agriculture', 'dependency_water': 'H'})
        _fill(wb, 'CharacterizationFactor',
              {'category_key': CAT_ECOSYSTEM, 'commodity_name': 'Testsoja',
               'value': 0.4},
              {'category_key': CAT_ECOSYSTEM, 'commodity_name': 'Testsoja',
               'subnational_region_name': 'Testrégion', 'value': 0.9})
        _fill(wb, 'Sector', {'name': 'Testsecteur', 'NACE_code': 'Z'})
        _fill(wb, 'SectorCreditProfile', {
            'sector_name': 'Testsecteur', 'pd_baseline': 0.04,
            'ebitda_margin': 0.2, 'carbon_pass_through': 0.6})
        _fill(wb, 'Company', {'name': 'Testcorp', 'isin': 'FR0000'})
        _fill(wb, 'Asset', {
            'name': 'Testusine', 'latitude': 45.0, 'longitude': 1.5,
            'country_name': 'Testland', 'subnational_region_name': 'Testrégion',
            'type': 'Factory', 'near_sensitive_zone': 'TRUE',
            'sensitive_zone_type': 'NATURA_2000', 'sensitive_zone_area_ha': 300})
        _fill(wb, 'SupplyNode',
              {'node_ref': 'AVAL', 'asset_name': 'Testusine'},
              {'node_ref': 'AMONT', 'country_name': 'Testland',
               'commodity_name': 'Testsoja', 'is_external': 'TRUE'})
        _fill(wb, 'Exchange', {
            'supplier_ref': 'AMONT', 'consumer_ref': 'AVAL',
            'commodity_name': 'Testsoja', 'quantity': 800, 'year': 2024,
            'tier': 1, 'data_confidence': 'country'})
        _fill(wb, 'ClimateScenario', {
            'key': 'test_orderly', 'name': 'Scénario test', 'family': 'ORDERLY',
            'warming_c': 1.5, 'order': 99})
        _fill(wb, 'ScenarioVariable',
              {'scenario_key': 'test_orderly', 'year': 2030,
               'key': 'carbon_price', 'value': 200},
              {'scenario_key': 'test_orderly', 'year': 2030,
               'key': 'hazard_multiplier', 'value': 1.3})

        buf = io.BytesIO()
        wb.save(buf)
        self.workbook_bytes = buf.getvalue()
        self.parsed = self._parse()

    def _parse(self):
        return parse_file(io.BytesIO(self.workbook_bytes))

    def test_every_filled_row_parses_without_error(self):
        errors = {
            sheet: [r['message'] for r in rows if r['status'] == 'error']
            for sheet, rows in self.parsed.items()
            if any(r['status'] == 'error' for r in rows)
        }
        self.assertEqual(errors, {})

    def test_import_persists_the_whole_workbook(self):
        counts = save_import(self.parsed)

        self.assertEqual(counts['Country'], 1)
        self.assertEqual(counts['CharacterizationFactor'], 2)
        self.assertEqual(counts['SupplyNode'], 2)
        self.assertEqual(counts['Exchange'], 1)
        self.assertEqual(counts['ScenarioVariable'], 2)

        region_cf = CharacterizationFactor.objects.get(
            commodity__name='Testsoja', region__name='Testrégion')
        self.assertAlmostEqual(region_cf.value, 0.9)
        global_cf = CharacterizationFactor.objects.get(
            commodity__name='Testsoja', region=None, country=None)
        self.assertAlmostEqual(global_cf.value, 0.4)

        asset = Asset.objects.get(name='Testusine')
        self.assertTrue(asset.near_sensitive_zone)
        self.assertEqual(asset.sensitive_zone_type, 'NATURA_2000')
        self.assertEqual(asset.subnational_region.name, 'Testrégion')

        exchange = Exchange.objects.get(commodity__name='Testsoja')
        self.assertEqual(exchange.consumer.asset, asset)
        self.assertTrue(exchange.supplier.is_external)
        self.assertEqual(exchange.tier, 1)
        self.assertAlmostEqual(exchange.quantity, 800.0)

        scenario = ClimateScenario.objects.get(key='test_orderly')
        self.assertEqual(scenario.family, ClimateScenario.Family.ORDERLY)
        self.assertAlmostEqual(
            ScenarioVariable.objects.get(
                scenario=scenario, key='carbon_price').value, 200.0)

        profile = SectorCreditProfile.objects.get(sector__name='Testsecteur')
        self.assertAlmostEqual(profile.pd_baseline, 0.04)

        # Le référentiel géographique et les commodités ont bien été créés.
        self.assertTrue(Country.objects.filter(name='Testland').exists())
        self.assertTrue(Commodity.objects.filter(name='Testsoja').exists())
        self.assertTrue(Sector.objects.filter(name='Testsecteur').exists())
        self.assertEqual(SupplyNode.objects.filter(asset=asset).count(), 1)

    def test_reuploading_the_same_workbook_creates_nothing_new(self):
        """Le vrai flux : le fichier est ré-analysé avant d'être ré-importé."""
        save_import(self.parsed)
        before = {
            model.__name__: model.objects.count()
            for model in (Asset, CharacterizationFactor, SupplyNode, Exchange,
                          ScenarioVariable)
        }

        reparsed = self._parse()
        counts = save_import(reparsed)

        self.assertEqual(
            {sheet: n for sheet, n in counts.items() if n}, {},
            'un second upload du même fichier ne doit rien créer')
        for model in (Asset, CharacterizationFactor, SupplyNode, Exchange,
                      ScenarioVariable):
            self.assertEqual(model.objects.count(), before[model.__name__],
                             f'{model.__name__} a été dupliqué')

    def test_supply_graph_idempotence_relies_on_the_importer(self):
        """SupplyNode/Exchange n'ont pas de clé comparable en base : le parseur
        les revoit en 'ok', c'est le get_or_create de l'importeur qui protège."""
        save_import(self.parsed)
        reparsed = self._parse()

        statuses = {r['status'] for r in reparsed['SupplyNode']}
        self.assertEqual(statuses, {'ok'})

        save_import(reparsed)
        self.assertEqual(SupplyNode.objects.count(), 2)
        self.assertEqual(Exchange.objects.count(), 1)
