from django.test import TestCase

from dashboard.models import Commodity
from imports.services.excel_parser import parse_file
from imports.services.importer import save_import
from imports.tests.test_excel_parser import _make_xlsx, _sheet


class CommoditySheetTests(TestCase):

    def _parse(self, *rows):
        return parse_file(_make_xlsx({'Commodity': _sheet('Commodity', *rows)}))

    def test_key_and_theme_are_imported(self):
        parsed = self._parse(
            {'name': 'Méthane', 'unit': 'tCO₂e', 'key': 'CH4', 'theme': 'carbon'})
        self.assertEqual(parsed['Commodity'][0]['status'], 'ok')
        save_import(parsed)
        methane = Commodity.objects.get(key='ch4')
        self.assertEqual((methane.name, methane.theme), ('Méthane', 'carbon'))

    def test_blank_key_is_stored_as_null(self):
        save_import(self._parse({'name': 'Soja', 'unit': 'tonnes'}))
        self.assertIsNone(Commodity.objects.get(name='Soja').key)

    def test_key_used_by_another_commodity_is_error(self):
        row = self._parse({'name': 'Eau douce', 'unit': 'm³', 'key': 'WATER'})['Commodity'][0]
        self.assertEqual(row['status'], 'error')
        self.assertIn('water', row['message'].lower())

    def test_same_key_twice_in_the_file_is_error(self):
        rows = self._parse(
            {'name': 'Méthane', 'unit': 't', 'key': 'ch4'},
            {'name': 'Méthane fossile', 'unit': 't', 'key': 'ch4'},
        )['Commodity']
        self.assertEqual([r['status'] for r in rows], ['ok', 'error'])

    def test_reuploading_a_seeded_commodity_is_duplicate_not_error(self):
        row = self._parse({'name': 'Eau', 'unit': 'm³', 'key': 'water'})['Commodity'][0]
        self.assertEqual(row['status'], 'duplicate')
