import io
import openpyxl
from django.test import TestCase
from dashboard.models import (
    Asset, CharacterizationFactor, ClimateScenario, Commodity, Company, Country,
    Policy_Subcategory, Policy_Type, Sector, SubSector,
)
from imports.services.excel_parser import parse_file
from imports.services.constants import SHEET_COLUMNS

CAT_ECOSYSTEM = 'impact_endpoint_ReCiPe2016_ecosystem_diversity'


def _make_xlsx(sheet_data):
    """Build an in-memory .xlsx from {sheet_name: [[header…], [row…], …]}."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sheet_name, rows in sheet_data.items():
        ws = wb.create_sheet(sheet_name)
        for r_idx, row in enumerate(rows, 1):
            for c_idx, val in enumerate(row, 1):
                ws.cell(r_idx, c_idx, val)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _sheet(sheet_name, *row_dicts):
    """Build [header, …rows] for a sheet using its full column list."""
    cols = SHEET_COLUMNS[sheet_name]
    return [cols] + [[d.get(c, '') for c in cols] for d in row_dicts]


class ParserCountryTest(TestCase):
    def test_valid_row_is_ok(self):
        buf = _make_xlsx({'Country': _sheet(
            'Country',
            {'name': 'France', 'water_ownership': 'public', 'land_ownership': 'private'},
        )})
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'ok')
        self.assertEqual(result['Country'][0]['data']['name'], 'France')

    def test_missing_required_field_is_error(self):
        buf = _make_xlsx({'Country': _sheet(
            'Country', {'water_ownership': 'public', 'land_ownership': 'private'},
        )})
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'error')
        self.assertIn('name', result['Country'][0]['message'])

    def test_existing_db_record_is_duplicate(self):
        Country.objects.create(name='France', water_ownership='pub', land_ownership='priv')
        buf = _make_xlsx({'Country': _sheet(
            'Country',
            {'name': 'France', 'water_ownership': 'public', 'land_ownership': 'private'},
        )})
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'duplicate')

    def test_case_insensitive_duplicate_detection(self):
        Country.objects.create(name='France', water_ownership='pub', land_ownership='priv')
        buf = _make_xlsx({'Country': _sheet(
            'Country',
            {'name': 'FRANCE', 'water_ownership': 'public', 'land_ownership': 'private'},
        )})
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'duplicate')

    def test_within_file_duplicate_is_duplicate(self):
        row = {'name': 'France', 'water_ownership': 'public', 'land_ownership': 'private'}
        buf = _make_xlsx({'Country': _sheet('Country', row, row)})
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'ok')
        self.assertEqual(result['Country'][1]['status'], 'duplicate')

    def test_empty_rows_are_skipped(self):
        buf = _make_xlsx({'Country': _sheet('Country', {})})
        result = parse_file(buf)
        self.assertEqual(result['Country'], [])


class ParserFKTest(TestCase):
    def test_invalid_fk_is_error(self):
        buf = _make_xlsx({'SubnationalRegion': _sheet(
            'SubnationalRegion', {'name': 'Bretagne', 'country_name': 'NonExistent'},
        )})
        result = parse_file(buf)
        self.assertEqual(result['SubnationalRegion'][0]['status'], 'error')
        self.assertIn('country_name', result['SubnationalRegion'][0]['message'])

    def test_valid_fk_from_db_is_ok(self):
        Country.objects.create(name='France', water_ownership='pub', land_ownership='priv')
        buf = _make_xlsx({'SubnationalRegion': _sheet(
            'SubnationalRegion', {'name': 'Bretagne', 'country_name': 'France'},
        )})
        result = parse_file(buf)
        self.assertEqual(result['SubnationalRegion'][0]['status'], 'ok')

    def test_fk_resolved_from_same_file(self):
        """SubnationalRegion can reference a Country defined in the same file."""
        buf = _make_xlsx({
            'Country': _sheet('Country', {
                'name': 'NewCountry', 'water_ownership': 'pub', 'land_ownership': 'priv'}),
            'SubnationalRegion': _sheet('SubnationalRegion', {
                'name': 'NewRegion', 'country_name': 'NewCountry'}),
        })
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'ok')
        self.assertEqual(result['SubnationalRegion'][0]['status'], 'ok')

    def test_policy_level_subcategory_fk(self):
        pt = Policy_Type.objects.create(name='TypeA')
        Policy_Subcategory.objects.create(name='SubA', policy_type=pt)
        buf = _make_xlsx({'Policy_Level': _sheet('Policy_Level', {
            'name': 'Level1', 'score': '3.0',
            'subcategory_name': 'SubA', 'policy_type_name': 'TypeA'})})
        result = parse_file(buf)
        self.assertEqual(result['Policy_Level'][0]['status'], 'ok')

    def test_sector_fk_resolved_from_db(self):
        """Régression : un Sector déjà en base doit être référençable sans être
        redéclaré dans le fichier."""
        Sector.objects.create(name='Agriculture')
        buf = _make_xlsx({'SubSector': _sheet(
            'SubSector', {'name': 'Céréales', 'sector_name': 'Agriculture'})})
        result = parse_file(buf)
        self.assertEqual(result['SubSector'][0]['status'], 'ok')

    def test_subsector_fk_resolved_from_db(self):
        """Régression : subsector_name n'était résolvable ni depuis la base ni
        depuis le fichier, ce qui rejetait toute ligne Company_Revenue_Sector."""
        sector = Sector.objects.create(name='Agriculture')
        SubSector.objects.create(name='Céréales', sector=sector)
        Company.objects.create(name='Acme')
        buf = _make_xlsx({'Company_Revenue_Sector': _sheet(
            'Company_Revenue_Sector',
            {'company_name': 'Acme', 'subsector_name': 'Céréales',
             'sector_name': 'Agriculture', 'year': '2024', 'revenue': '1000'})})
        result = parse_file(buf)
        self.assertEqual(result['Company_Revenue_Sector'][0]['status'], 'ok')


class ParserKeyBasedFKTest(TestCase):
    """Les catalogues (ImpactCategory, Flow, ClimateScenario) se référencent par
    `key` et non par `name`."""

    def setUp(self):
        self.country = Country.objects.create(
            name='France', water_ownership='pub', land_ownership='priv')
        self.asset = Asset.objects.create(
            name='Usine A', latitude=48.85, longitude=2.35, country=self.country)
        Commodity.objects.create(name='Soy')

    def test_known_flow_key_is_ok(self):
        buf = _make_xlsx({'AssetInventory': _sheet('AssetInventory', {
            'asset_name': 'Usine A', 'flow_key': 'water',
            'year': '2024', 'value': '100'})})
        result = parse_file(buf)
        self.assertEqual(result['AssetInventory'][0]['status'], 'ok')

    def test_unknown_flow_key_is_error(self):
        buf = _make_xlsx({'AssetInventory': _sheet('AssetInventory', {
            'asset_name': 'Usine A', 'flow_key': 'nope',
            'year': '2024', 'value': '100'})})
        result = parse_file(buf)
        self.assertEqual(result['AssetInventory'][0]['status'], 'error')
        self.assertIn('flow_key', result['AssetInventory'][0]['message'])

    def test_known_impact_category_key_is_ok(self):
        buf = _make_xlsx({'CharacterizationFactor': _sheet('CharacterizationFactor', {
            'category_key': CAT_ECOSYSTEM, 'commodity_name': 'Soy', 'value': '0.5'})})
        result = parse_file(buf)
        self.assertEqual(result['CharacterizationFactor'][0]['status'], 'ok')

    def test_unknown_impact_category_key_is_error(self):
        buf = _make_xlsx({'CharacterizationFactor': _sheet('CharacterizationFactor', {
            'category_key': 'nope', 'commodity_name': 'Soy', 'value': '0.5'})})
        result = parse_file(buf)
        self.assertEqual(result['CharacterizationFactor'][0]['status'], 'error')

    def test_existing_characterization_factor_is_duplicate(self):
        from dashboard.models import ImpactCategory
        CharacterizationFactor.objects.create(
            category=ImpactCategory.objects.get(key=CAT_ECOSYSTEM),
            commodity=Commodity.objects.get(name='Soy'),
            country=self.country, value=1.0,
        )
        buf = _make_xlsx({'CharacterizationFactor': _sheet('CharacterizationFactor', {
            'category_key': CAT_ECOSYSTEM, 'commodity_name': 'Soy',
            'country_name': 'France', 'value': '2.0'})})
        result = parse_file(buf)
        self.assertEqual(result['CharacterizationFactor'][0]['status'], 'duplicate')

    def test_scenario_key_resolved_from_same_file(self):
        buf = _make_xlsx({
            'ClimateScenario': _sheet('ClimateScenario', {
                'key': 'custom', 'name': 'Maison', 'family': 'ORDERLY'}),
            'ScenarioVariable': _sheet('ScenarioVariable', {
                'scenario_key': 'custom', 'year': '2030',
                'key': 'carbon_price', 'value': '180'}),
        })
        result = parse_file(buf)
        self.assertEqual(result['ClimateScenario'][0]['status'], 'ok')
        self.assertEqual(result['ScenarioVariable'][0]['status'], 'ok')

    def test_scenario_key_resolved_from_seeded_db(self):
        seeded = ClimateScenario.objects.first()
        buf = _make_xlsx({'ScenarioVariable': _sheet('ScenarioVariable', {
            'scenario_key': seeded.key, 'year': '2077',
            'key': 'carbon_price', 'value': '900'})})
        result = parse_file(buf)
        self.assertEqual(result['ScenarioVariable'][0]['status'], 'ok')

    def test_unknown_scenario_key_is_error(self):
        buf = _make_xlsx({'ScenarioVariable': _sheet('ScenarioVariable', {
            'scenario_key': 'ghost', 'year': '2030',
            'key': 'carbon_price', 'value': '180'})})
        result = parse_file(buf)
        self.assertEqual(result['ScenarioVariable'][0]['status'], 'error')


class ParserSupplyNodeRefTest(TestCase):
    def setUp(self):
        country = Country.objects.create(
            name='France', water_ownership='pub', land_ownership='priv')
        Asset.objects.create(
            name='Usine A', latitude=48.85, longitude=2.35, country=country)
        Commodity.objects.create(name='Soy')

    def test_exchange_ref_resolved_from_supply_node_sheet(self):
        buf = _make_xlsx({
            'SupplyNode': _sheet(
                'SupplyNode',
                {'node_ref': 'N1', 'asset_name': 'Usine A'},
                {'node_ref': 'N2', 'country_name': 'France', 'commodity_name': 'Soy'}),
            'Exchange': _sheet('Exchange', {
                'supplier_ref': 'N2', 'consumer_ref': 'N1', 'commodity_name': 'Soy',
                'quantity': '500', 'year': '2024', 'tier': '1'}),
        })
        result = parse_file(buf)
        self.assertEqual(result['Exchange'][0]['status'], 'ok')

    def test_node_without_any_location_is_error(self):
        """SupplyNode.clean() exige asset, region ou country ; create() ne
        l'appelle pas, la garde doit donc vivre dans le parseur."""
        buf = _make_xlsx({'SupplyNode': _sheet('SupplyNode', {'node_ref': 'N1'})})
        result = parse_file(buf)
        self.assertEqual(result['SupplyNode'][0]['status'], 'error')
        self.assertIn('au moins', result['SupplyNode'][0]['message'])

    def test_node_located_by_country_only_is_ok(self):
        buf = _make_xlsx({'SupplyNode': _sheet(
            'SupplyNode', {'node_ref': 'N1', 'country_name': 'France'})})
        result = parse_file(buf)
        self.assertEqual(result['SupplyNode'][0]['status'], 'ok')

    def test_exchange_with_undeclared_ref_is_error(self):
        buf = _make_xlsx({
            'SupplyNode': _sheet('SupplyNode', {'node_ref': 'N1', 'asset_name': 'Usine A'}),
            'Exchange': _sheet('Exchange', {
                'supplier_ref': 'GHOST', 'consumer_ref': 'N1', 'commodity_name': 'Soy',
                'quantity': '500', 'year': '2024', 'tier': '1'}),
        })
        result = parse_file(buf)
        self.assertEqual(result['Exchange'][0]['status'], 'error')
        self.assertIn('supplier_ref', result['Exchange'][0]['message'])


class ParserChoiceFieldTest(TestCase):
    def test_invalid_scenario_family_is_error(self):
        buf = _make_xlsx({'ClimateScenario': _sheet('ClimateScenario', {
            'key': 'custom', 'name': 'Maison', 'family': 'CHAOTIC'})})
        result = parse_file(buf)
        self.assertEqual(result['ClimateScenario'][0]['status'], 'error')
        self.assertIn('family', result['ClimateScenario'][0]['message'])

    def test_valid_family_is_case_insensitive(self):
        buf = _make_xlsx({'ClimateScenario': _sheet('ClimateScenario', {
            'key': 'custom', 'name': 'Maison', 'family': 'orderly'})})
        result = parse_file(buf)
        self.assertEqual(result['ClimateScenario'][0]['status'], 'ok')

    def test_blank_choice_is_accepted(self):
        buf = _make_xlsx({'ClimateScenario': _sheet('ClimateScenario', {
            'key': 'custom', 'name': 'Maison', 'family': ''})})
        result = parse_file(buf)
        self.assertEqual(result['ClimateScenario'][0]['status'], 'ok')

    def test_invalid_asset_type_is_error(self):
        Country.objects.create(name='France', water_ownership='pub', land_ownership='priv')
        buf = _make_xlsx({'Asset': _sheet('Asset', {
            'name': 'Usine A', 'latitude': '48.85', 'longitude': '2.35',
            'country_name': 'France', 'type': 'Spaceport'})})
        result = parse_file(buf)
        self.assertEqual(result['Asset'][0]['status'], 'error')
        self.assertIn('type', result['Asset'][0]['message'])
