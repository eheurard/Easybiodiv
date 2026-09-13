from django.test import TestCase
from dashboard.models import (
    Asset, AssetInventory, CharacterizationFactor, ClimateScenario, Commodity,
    Company, Company_Policy, Country, Exchange, Policy_Level, Policy_Subcategory,
    Policy_Type, Production, ScenarioVariable, Sector, SectorCreditProfile,
    SubnationalRegion, SupplyNode,
)
from imports.services.importer import save_import

CAT_ECOSYSTEM = 'impact_endpoint_ReCiPe2016_ecosystem_diversity'


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
                 'land_ownership': 'priv', 'water_governance': '', 'land_governance': ''}),
        ]})
        self.assertEqual(counts['Country'], 1)
        self.assertTrue(Country.objects.filter(name='France').exists())

    def test_skips_duplicate_and_error_rows(self):
        counts = save_import({'Country': [
            _ok({'name': 'France', 'water_ownership': 'pub',
                 'land_ownership': 'priv', 'water_governance': '', 'land_governance': ''}),
            _dup({'name': 'Germany', 'water_ownership': 'pub',
                  'land_ownership': 'priv', 'water_governance': '', 'land_governance': ''}),
            _err({'name': 'Bad', 'water_ownership': '', 'land_ownership': '',
                  'water_governance': '', 'land_governance': ''}),
        ]})
        self.assertEqual(counts['Country'], 1)
        self.assertFalse(Country.objects.filter(name='Germany').exists())

    def test_topological_order_subnational_references_country(self):
        counts = save_import({
            'Country': [
                _ok({'name': 'France', 'water_ownership': 'pub',
                     'land_ownership': 'priv', 'water_governance': '', 'land_governance': ''}),
            ],
            'SubnationalRegion': [
                _ok({'name': 'Bretagne', 'country_name': 'France',
                     'Mean_X': '-2.9', 'Mean_Y': '48.2'}),
            ],
        })
        self.assertEqual(counts['Country'], 1)
        self.assertEqual(counts['SubnationalRegion'], 1)
        region = SubnationalRegion.objects.get(name='Bretagne')
        self.assertAlmostEqual(region.Mean_X, -2.9)
        self.assertAlmostEqual(region.Mean_Y, 48.2)

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
                         'land_ownership': 'priv', 'water_governance': '', 'land_governance': ''}),
                ]})
        self.assertFalse(Country.objects.filter(name='France').exists())


class ImporterAssetTest(TestCase):
    def setUp(self):
        self.country = Country.objects.create(
            name='France', water_ownership='pub', land_ownership='priv')

    def test_asset_imports_without_subnational_region(self):
        counts = save_import({'Asset': [
            _ok({'name': 'Usine A', 'description': '', 'latitude': '48.85',
                 'longitude': '2.35', 'country_name': 'France',
                 'subnational_region_name': ''}),
        ]})
        self.assertEqual(counts['Asset'], 1)
        self.assertIsNone(Asset.objects.get(name='Usine A').subnational_region)

    def test_asset_imports_type_and_sensitive_zone(self):
        save_import({'Asset': [
            _ok({'name': 'Mine B', 'latitude': '45.0', 'longitude': '3.0',
                 'country_name': 'France', 'type': 'Mine',
                 'near_sensitive_zone': 'TRUE', 'sensitive_zone_type': 'NATURA_2000',
                 'sensitive_zone_name': 'Gorges du Tarn',
                 'sensitive_zone_area_ha': '1250'}),
        ]})
        asset = Asset.objects.get(name='Mine B')
        self.assertEqual(asset.type, 'Mine')
        self.assertTrue(asset.near_sensitive_zone)
        self.assertEqual(asset.sensitive_zone_type, 'NATURA_2000')
        self.assertEqual(asset.sensitive_zone_name, 'Gorges du Tarn')
        self.assertAlmostEqual(asset.sensitive_zone_area_ha, 1250.0)

    def test_asset_type_defaults_to_factory_when_blank(self):
        save_import({'Asset': [
            _ok({'name': 'Usine C', 'latitude': '45.0', 'longitude': '3.0',
                 'country_name': 'France', 'type': ''}),
        ]})
        self.assertEqual(Asset.objects.get(name='Usine C').type, 'Factory')


class ImporterCharacterizationFactorTest(TestCase):
    def setUp(self):
        self.country = Country.objects.create(
            name='France', water_ownership='pub', land_ownership='priv')
        self.region = SubnationalRegion.objects.create(
            name='Bretagne', country=self.country)
        self.commodity = Commodity.objects.create(name='Soy')

    def test_blank_location_creates_global_factor(self):
        counts = save_import({'CharacterizationFactor': [
            _ok({'category_key': CAT_ECOSYSTEM, 'commodity_name': 'Soy',
                 'country_name': '', 'subnational_region_name': '', 'value': '0.5'}),
        ]})
        self.assertEqual(counts['CharacterizationFactor'], 1)
        cf = CharacterizationFactor.objects.get(
            commodity=self.commodity, category__key=CAT_ECOSYSTEM,
            region=None, country=None)
        self.assertAlmostEqual(cf.value, 0.5)

    def test_region_and_country_factors_coexist(self):
        counts = save_import({'CharacterizationFactor': [
            _ok({'category_key': CAT_ECOSYSTEM, 'commodity_name': 'Soy',
                 'country_name': 'France', 'subnational_region_name': '', 'value': '1.5'}),
            _ok({'category_key': CAT_ECOSYSTEM, 'commodity_name': 'Soy',
                 'country_name': '', 'subnational_region_name': 'Bretagne', 'value': '2.5'}),
        ]})
        self.assertEqual(counts['CharacterizationFactor'], 2)
        country_cf = CharacterizationFactor.objects.get(
            commodity=self.commodity, country=self.country, region=None)
        region_cf = CharacterizationFactor.objects.get(
            commodity=self.commodity, region=self.region)
        self.assertAlmostEqual(country_cf.value, 1.5)
        self.assertAlmostEqual(region_cf.value, 2.5)

    def test_unknown_category_key_is_skipped(self):
        counts = save_import({'CharacterizationFactor': [
            _ok({'category_key': 'nope', 'commodity_name': 'Soy',
                 'country_name': '', 'subnational_region_name': '', 'value': '1'}),
        ]})
        self.assertEqual(counts['CharacterizationFactor'], 0)

    def test_commodity_import_no_longer_creates_factors(self):
        """Les 16 colonnes impact_* ont disparu du template : importer une
        commodity ne doit plus créer de CF à zéro."""
        save_import({'Commodity': [
            _ok({'name': 'Wheat', 'description': '', 'unit': 'tonnes',
                 'biodiversity_loss_class': 'Agriculture'}),
        ]})
        commodity = Commodity.objects.get(name='Wheat')
        self.assertEqual(
            CharacterizationFactor.objects.filter(commodity=commodity).count(), 0)


class ImporterAssetInventoryTest(TestCase):
    def setUp(self):
        country = Country.objects.create(
            name='France', water_ownership='pub', land_ownership='priv')
        self.asset = Asset.objects.create(
            name='Usine A', latitude=48.85, longitude=2.35, country=country)

    def test_creates_inventory_row(self):
        counts = save_import({'AssetInventory': [
            _ok({'asset_name': 'Usine A', 'flow_key': 'water', 'year': '2024',
                 'value': '100', 'source': 'relevé', 'reference': 'R-1'}),
        ]})
        self.assertEqual(counts['AssetInventory'], 1)
        inventory = AssetInventory.objects.get(
            asset=self.asset, flow__key='water', year=2024)
        self.assertAlmostEqual(inventory.value, 100.0)
        self.assertEqual(inventory.source, 'relevé')

    def test_unknown_flow_key_is_skipped(self):
        counts = save_import({'AssetInventory': [
            _ok({'asset_name': 'Usine A', 'flow_key': 'nope', 'year': '2024',
                 'value': '100'}),
        ]})
        self.assertEqual(counts['AssetInventory'], 0)


class ImporterProductionTest(TestCase):
    def setUp(self):
        self.country = Country.objects.create(
            name='France', water_ownership='pub', land_ownership='priv')
        Asset.objects.create(
            name='Usine A', latitude=48.85, longitude=2.35, country=self.country)
        Commodity.objects.create(name='Soy')
        Company.objects.create(name='Acme')

    def test_tier_column_is_stored(self):
        counts = save_import({'Production': [
            _ok({'asset_name': 'Usine A', 'commodity_name': 'Soy', 'tier': '2',
                 'year': '2024', 'production': '100'}),
        ]})
        self.assertEqual(counts['Production'], 1)
        self.assertEqual(Production.objects.get().tier, 2)

    def test_tier_is_clamped_to_model_range(self):
        save_import({'Production': [
            _ok({'asset_name': 'Usine A', 'commodity_name': 'Soy', 'tier': '9',
                 'year': '2024', 'production': '100'}),
        ]})
        self.assertEqual(Production.objects.get().tier, 3)

    def test_optional_fks_are_wired(self):
        save_import({'Production': [
            _ok({'asset_name': 'Usine A', 'commodity_name': 'Soy',
                 'company_name': 'Acme', 'country_name': 'France',
                 'subnational_region_name': '',
                 'tier': '0', 'year': '2024', 'production': '100'}),
        ]})
        production = Production.objects.get()
        self.assertEqual(production.company.name, 'Acme')
        self.assertEqual(production.country, self.country)


class ImporterSupplyGraphTest(TestCase):
    def setUp(self):
        self.country = Country.objects.create(
            name='France', water_ownership='pub', land_ownership='priv')
        self.asset = Asset.objects.create(
            name='Usine A', latitude=48.85, longitude=2.35, country=self.country)
        self.commodity = Commodity.objects.create(name='Soy')

    def test_creates_nodes_and_exchange(self):
        counts = save_import({
            'SupplyNode': [
                _ok({'node_ref': 'N1', 'asset_name': 'Usine A',
                     'subnational_region_name': '', 'country_name': '',
                     'commodity_name': '', 'is_external': 'FALSE'}),
                _ok({'node_ref': 'N2', 'asset_name': '',
                     'subnational_region_name': '', 'country_name': 'France',
                     'commodity_name': 'Soy', 'is_external': 'TRUE'}),
            ],
            'Exchange': [
                _ok({'supplier_ref': 'N2', 'consumer_ref': 'N1',
                     'commodity_name': 'Soy', 'quantity': '500', 'year': '2024',
                     'tier': '1', 'data_confidence': ''}),
            ],
        })
        self.assertEqual(counts['SupplyNode'], 2)
        self.assertEqual(counts['Exchange'], 1)
        exchange = Exchange.objects.get()
        self.assertEqual(exchange.consumer.asset, self.asset)
        self.assertTrue(exchange.supplier.is_external)
        self.assertAlmostEqual(exchange.quantity, 500.0)
        self.assertEqual(exchange.tier, 1)
        # data_confidence vide → hérite de la résolution du fournisseur
        self.assertEqual(exchange.data_confidence, 'country')

    def test_reuses_existing_node_instead_of_duplicating(self):
        existing = SupplyNode.objects.create(asset=self.asset)
        counts = save_import({'SupplyNode': [
            _ok({'node_ref': 'N1', 'asset_name': 'Usine A',
                 'subnational_region_name': '', 'country_name': '',
                 'commodity_name': '', 'is_external': ''}),
        ]})
        self.assertEqual(counts['SupplyNode'], 0)
        self.assertEqual(SupplyNode.objects.filter(asset=self.asset).count(), 1)
        self.assertEqual(SupplyNode.objects.get(asset=self.asset).pk, existing.pk)

    def test_exchange_with_unknown_node_ref_is_skipped(self):
        counts = save_import({
            'SupplyNode': [
                _ok({'node_ref': 'N1', 'asset_name': 'Usine A',
                     'subnational_region_name': '', 'country_name': '',
                     'commodity_name': '', 'is_external': ''}),
            ],
            'Exchange': [
                _ok({'supplier_ref': 'GHOST', 'consumer_ref': 'N1',
                     'commodity_name': 'Soy', 'quantity': '500', 'year': '2024',
                     'tier': '1', 'data_confidence': ''}),
            ],
        })
        self.assertEqual(counts['Exchange'], 0)


class ImporterClimateStressTest(TestCase):
    def test_creates_scenario_and_variables(self):
        counts = save_import({
            'ClimateScenario': [
                _ok({'key': 'custom_net_zero', 'name': 'Net Zero maison',
                     'family': 'ORDERLY', 'warming_c': '1.4',
                     'narrative': 'Trajectoire interne', 'source': 'Interne',
                     'reference': 'DOC-1', 'order': '1'}),
            ],
            'ScenarioVariable': [
                _ok({'scenario_key': 'custom_net_zero', 'year': '2030',
                     'key': 'carbon_price', 'value': '180'}),
                _ok({'scenario_key': 'custom_net_zero', 'year': '2030',
                     'key': 'hazard_multiplier', 'value': '1.2'}),
            ],
        })
        self.assertEqual(counts['ClimateScenario'], 1)
        self.assertEqual(counts['ScenarioVariable'], 2)
        scenario = ClimateScenario.objects.get(key='custom_net_zero')
        self.assertEqual(scenario.family, ClimateScenario.Family.ORDERLY)
        self.assertAlmostEqual(scenario.warming_c, 1.4)
        self.assertEqual(scenario.order, 1)
        price = ScenarioVariable.objects.get(scenario=scenario, key='carbon_price')
        self.assertAlmostEqual(price.value, 180.0)

    def test_variable_attaches_to_seeded_scenario(self):
        """Un scénario déjà en base (seed NGFS) est référençable sans le redéclarer."""
        seeded = ClimateScenario.objects.first()
        self.assertIsNotNone(seeded, 'le seed NGFS doit être présent')
        counts = save_import({'ScenarioVariable': [
            _ok({'scenario_key': seeded.key, 'year': '2077',
                 'key': 'carbon_price', 'value': '900'}),
        ]})
        self.assertEqual(counts['ScenarioVariable'], 1)
        self.assertTrue(ScenarioVariable.objects.filter(
            scenario=seeded, year=2077, key='carbon_price').exists())

    def test_unknown_scenario_key_is_skipped(self):
        counts = save_import({'ScenarioVariable': [
            _ok({'scenario_key': 'ghost', 'year': '2030',
                 'key': 'carbon_price', 'value': '180'}),
        ]})
        self.assertEqual(counts['ScenarioVariable'], 0)


class ImporterSectorCreditProfileTest(TestCase):
    def test_creates_profile(self):
        counts = save_import({
            'Sector': [_ok({'name': 'Agriculture', 'NACE_code': 'A'})],
            'SectorCreditProfile': [
                _ok({'sector_name': 'Agriculture', 'pd_baseline': '0.03',
                     'ebitda_margin': '0.18', 'ebitda_volatility': '0.4',
                     'carbon_pass_through': '0.5', 'source': 'NGFS', 'reference': 'R'}),
            ],
        })
        self.assertEqual(counts['SectorCreditProfile'], 1)
        profile = SectorCreditProfile.objects.get(sector__name='Agriculture')
        self.assertAlmostEqual(profile.pd_baseline, 0.03)
        self.assertAlmostEqual(profile.carbon_pass_through, 0.5)

    def test_blank_values_fall_back_to_model_defaults(self):
        Sector.objects.create(name='Industrie')
        save_import({'SectorCreditProfile': [
            _ok({'sector_name': 'Industrie', 'pd_baseline': '', 'ebitda_margin': '',
                 'ebitda_volatility': '', 'carbon_pass_through': ''}),
        ]})
        profile = SectorCreditProfile.objects.get(sector__name='Industrie')
        self.assertAlmostEqual(profile.pd_baseline, 0.015)
        self.assertAlmostEqual(profile.ebitda_margin, 0.12)

    def test_existing_profile_is_not_duplicated(self):
        sector = Sector.objects.create(name='Industrie')
        SectorCreditProfile.objects.create(sector=sector)
        counts = save_import({'SectorCreditProfile': [
            _ok({'sector_name': 'Industrie', 'pd_baseline': '0.9'}),
        ]})
        self.assertEqual(counts['SectorCreditProfile'], 0)
        self.assertEqual(SectorCreditProfile.objects.filter(sector=sector).count(), 1)


class ImporterCompanyPolicyTest(TestCase):
    def test_comment_is_stored(self):
        Company.objects.create(name='Acme')
        pt = Policy_Type.objects.create(name='TypeA')
        sub = Policy_Subcategory.objects.create(name='SubA', policy_type=pt)
        Policy_Level.objects.create(name='Level1', subcategory=sub)
        counts = save_import({'Company_Policy': [
            _ok({'company_name': 'Acme', 'policy_type_name': 'TypeA',
                 'policy_subcategory_name': 'SubA', 'policy_level_name': 'Level1',
                 'policy_date': '2025-06-01', 'comment': 'validé en CA'}),
        ]})
        self.assertEqual(counts['Company_Policy'], 1)
        self.assertEqual(Company_Policy.objects.get().comment, 'validé en CA')
