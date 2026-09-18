from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from dashboard.models import Asset, Company, Country, Ownership
from imports.services.cells import parse_optional_year, parse_share
from imports.services.excel_parser import parse_file
from imports.services.importer import save_import
from imports.tests.test_excel_parser import _make_xlsx, _sheet


class ParseShareTests(SimpleTestCase):

    def test_accepted_formats(self):
        cases = {
            '0.75': '0.7500', '75%': '0.7500', '75 %': '0.7500', '0,75': '0.7500',
            '1': '1.0000', '100%': '1.0000',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_share(raw), Decimal(expected))

    def test_rejected_values(self):
        for raw in ('', None, '1.5', '150%', '0', '-0.2', 'abc', 'nan'):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_share(raw))

    def test_optional_year(self):
        self.assertIsNone(parse_optional_year(''))
        self.assertEqual(parse_optional_year('2024.0'), 2024)
        with self.assertRaises(ValueError):
            parse_optional_year('fin')


class OwnershipSheetTests(TestCase):

    def setUp(self):
        country = Country.objects.create(
            name='France', water_ownership='pub', land_ownership='priv')
        Asset.objects.create(name='Usine A', latitude=1.0, longitude=2.0, country=country)
        Company.objects.create(name='Acme')

    def _row(self, **values):
        row = {'asset_name': 'Usine A', 'company_name': 'Acme', 'share': '75%'}
        row.update(values)
        return row

    def _parse(self, *rows):
        return parse_file(_make_xlsx({'Ownership': _sheet('Ownership', *rows)}))

    def test_percent_share_is_imported_as_decimal(self):
        parsed = self._parse(self._row(start_year='2024'))
        self.assertEqual(parsed['Ownership'][0]['status'], 'ok')
        save_import(parsed)
        o = Ownership.objects.get()
        self.assertEqual((o.share, o.start_year, o.end_year), (Decimal('0.7500'), 2024, None))

    def test_invalid_share_is_error(self):
        row = self._parse(self._row(share='1.5'))['Ownership'][0]
        self.assertEqual(row['status'], 'error')
        self.assertIn('share', row['message'])

    def test_invalid_year_is_error(self):
        row = self._parse(self._row(end_year='fin'))['Ownership'][0]
        self.assertEqual(row['status'], 'error')
        self.assertIn('end_year', row['message'])

    def test_start_after_end_is_error(self):
        row = self._parse(self._row(start_year='2025', end_year='2024'))['Ownership'][0]
        self.assertEqual(row['status'], 'error')
