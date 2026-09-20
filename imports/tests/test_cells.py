from django.test import SimpleTestCase

from imports.services.cells import parse_int, parse_number


class ParseNumberTests(SimpleTestCase):

    def test_accepted_formats(self):
        cases = {'12.5': 12.5, '12,5': 12.5, ' 12.5 ': 12.5, '-3': -3.0, '0': 0.0}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_number(raw), expected)

    def test_rejected_values(self):
        for raw in ('', None, 'abc', '12,5x', 'nan', 'inf'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_number(raw)


class ParseIntTests(SimpleTestCase):

    def test_accepted_formats(self):
        self.assertEqual(parse_int('2024'), 2024)
        self.assertEqual(parse_int('2024.0'), 2024)

    def test_rejected_values(self):
        for raw in ('', None, 'FY2024', '2024.5', 'abc'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_int(raw)
