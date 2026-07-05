from django.test import TestCase
from dashboard.models import (
    Country, SubnationalRegion, Commodity, CharacterizationFactor, Policy_Type,
    Policy_Subcategory, Policy_Level, Company, Asset, Production, Company_Revenue,
    Ownership, Company_Policy,
)
from imports.services.importer import save_import


def _ok(data):
    return {'status': 'ok', 'data': data}

def _dup(data):
    return {'status': 'duplicate', 'data': data}

def _err(data, msg='err'):
    return {'status': 'error', 'message': msg, 'data': data}


class ImporterCountryTest(TestCase):
    def test_creates_country(self):
        counts = save_import({'Country': [
            _ok({'name': 'France', 'water_ownership': 'pub',
                 'land_ownership': 'priv', 'water_Governance': '', 'land_Governance': ''}),
        ]})
        self.assertEqual(counts['Country'], 1)
        self.assertTrue(Country.objects.filter(name='France').exists())

    def test_skips_duplicate_and_error_rows(self):
        counts = save_import({'Country': [
            _ok({'name': 'France', 'water_ownership': 'pub',
                 'land_ownership': 'priv', 'water_Governance': '', 'land_Governance': ''}),
            _dup({'name': 'Germany', 'water_ownership': 'pub',
                  'land_ownership': 'priv', 'water_Governance': '', 'land_Governance': ''}),
            _err({'name': 'Bad', 'water_ownership': '', 'land_ownership': '',
                  'water_Governance': '', 'land_Governance': ''}),
        ]})
        self.assertEqual(counts['Country'], 1)
        self.assertFalse(Country.objects.filter(name='Germany').exists())

    def test_topological_order_subnational_references_country(self):
        counts = save_import({
            'Country': [
                _ok({'name': 'France', 'water_ownership': 'pub',
                     'land_ownership': 'priv', 'water_Governance': '', 'land_Governance': ''}),
            ],
            'SubnationalRegion': [
                _ok({'name': 'Bretagne', 'description': '', 'country_name': 'France'}),
            ],
        })
        self.assertEqual(counts['Country'], 1)
        self.assertEqual(counts['SubnationalRegion'], 1)
        self.assertTrue(SubnationalRegion.objects.filter(name='Bretagne').exists())

    def test_asset_imports_without_subnational_region(self):
        counts = save_import({
            'Country': [
                _ok({'name': 'France', 'water_ownership': 'pub',
                     'land_ownership': 'priv', 'water_Governance': '', 'land_Governance': ''}),
            ],
            'Asset': [
                _ok({'name': 'Usine A', 'description': '', 'latitude': '48.85',
                     'longitude': '2.35', 'country_name': 'France',
                     'subnational_region_name': ''}),
            ],
        })
        self.assertEqual(counts['Asset'], 1)
        asset = Asset.objects.get(name='Usine A')
        self.assertIsNone(asset.subnational_region)

    def test_commodity_import_creates_global_characterization_factor(self):
        """Regression: _import_commodity must no longer pass impact_* kwargs to
        Commodity() — impact values now become global CharacterizationFactor rows."""
        counts = save_import({'Commodity': [
            _ok({'name': 'Soy', 'description': '', 'unit': 'tonnes',
                 'biodiversity_loss_class': 'Agriculture',
                 'impact_endpoint_ReCiPe2016_ecosystem_diversity': '0.5'}),
        ]})
        self.assertEqual(counts['Commodity'], 1)
        commodity = Commodity.objects.get(name='Soy')
        cf = CharacterizationFactor.objects.get(
            commodity=commodity,
            category__key='impact_endpoint_ReCiPe2016_ecosystem_diversity',
            region=None, country=None,
        )
        self.assertEqual(cf.value, 0.5)

    def test_import_production_maps_scope_to_tier(self):
        """Regression: _import_production must map the sheet's `scope` column
        (direct/tier 1/tier 2/raw material) to the model's `tier` integer field,
        since dependencies now groups productions by `tier`."""
        country = Country.objects.create(
            name='France', water_ownership='pub', land_ownership='priv')
        Asset.objects.create(
            name='Usine A', latitude=48.85, longitude=2.35, country=country)
        Commodity.objects.create(name='Soy')
        counts = save_import({'Production': [
            _ok({'asset_name': 'Usine A', 'commodity_name': 'Soy', 'scope': 'tier 1',
                 'year': '2024', 'production': '100'}),
        ]})
        self.assertEqual(counts['Production'], 1)
        production = Production.objects.get(asset__name='Usine A', commodity__name='Soy')
        self.assertEqual(production.tier, 1)

    def test_returns_empty_for_empty_input(self):
        counts = save_import({})
        self.assertEqual(counts, {})

    def test_transaction_rollback_does_not_partial_import(self):
        """If an unexpected error occurs mid-import, nothing is saved."""
        from unittest.mock import patch
        with patch('dashboard.models.Country.objects.create', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                save_import({'Country': [
                    _ok({'name': 'France', 'water_ownership': 'pub',
                         'land_ownership': 'priv', 'water_Governance': '', 'land_Governance': ''}),
                ]})
        self.assertFalse(Country.objects.filter(name='France').exists())
