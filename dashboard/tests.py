import json
from django.test import TestCase
from django.urls import reverse
from .models import (
    Asset, Commodity, Company, Company_Policy, Company_Revenue,
    Company_Revenue_Sector, Country, Ownership, Policy_Level,
    Policy_Subcategory, Policy_Type, Production, Sector, SubnationalRegion,
    SubSector,
)


def _make_world():
    """Return (company, country, region, commodity, asset) with one ownership and one production."""
    company = Company.objects.create(name='TestCorp')
    country = Country.objects.create(
        name='France', water_ownership='Public', land_ownership='Private'
    )
    region = SubnationalRegion.objects.create(name='Île-de-France', country=country)
    commodity = Commodity.objects.create(name='Soja')
    asset = Asset.objects.create(
        name='Site Paris', latitude=48.8566, longitude=2.3522,
        country=country, subnational_region=region,
    )
    Ownership.objects.create(Asset=asset, Company=company, ownership='100%')
    Production.objects.create(asset=asset, commodity=commodity, year=2024, production=100.0)
    return company, country, region, commodity, asset


class CompanyDataViewTests(TestCase):

    def setUp(self):
        self.company, self.country, self.region, self.commodity, self.asset = _make_world()
        self.url = reverse('dashboard:company_data', kwargs={'pk': self.company.pk})

    def test_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_content_type_is_json(self):
        response = self.client.get(self.url)
        self.assertIn('application/json', response['Content-Type'])

    def test_kpi_counts(self):
        response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertEqual(data['asset_count'], 1)
        self.assertEqual(data['country_count'], 1)
        self.assertEqual(data['commodity_count'], 1)
        self.assertEqual(data['region_count'], 1)

    def test_countries_with_commodities(self):
        response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertEqual(len(data['countries']), 1)
        c = data['countries'][0]
        self.assertEqual(c['name'], 'France')
        self.assertEqual(c['asset_count'], 1)
        self.assertEqual(c['commodities'], [{'name': 'Soja', 'count': 1}])

    def test_geojson_feature_coordinates(self):
        response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertEqual(data['geojson']['type'], 'FeatureCollection')
        feature = data['geojson']['features'][0]
        self.assertEqual(feature['geometry']['type'], 'Point')
        self.assertEqual(feature['geometry']['coordinates'], [2.3522, 48.8566])
        self.assertEqual(feature['properties']['name'], 'Site Paris')

    def test_empty_company_returns_zeros(self):
        empty = Company.objects.create(name='EmptyCorp')
        url = reverse('dashboard:company_data', kwargs={'pk': empty.pk})
        response = self.client.get(url)
        data = json.loads(response.content)
        self.assertEqual(data['asset_count'], 0)
        self.assertEqual(data['countries'], [])
        self.assertEqual(data['geojson']['features'], [])

    def test_not_found_returns_404(self):
        url = reverse('dashboard:company_data', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_post_not_allowed(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 405)

    def test_policies_grouped_by_type_with_avg_score(self):
        pt = Policy_Type.objects.create(name='Biodiversité')
        sub1 = Policy_Subcategory.objects.create(name='Approvisionnement', policy_type=pt)
        sub2 = Policy_Subcategory.objects.create(name='Reporting', policy_type=pt)
        level1 = Policy_Level.objects.create(name='Avancé', score=0.8, subcategory=sub1)
        level2 = Policy_Level.objects.create(name='Basique', score=0.4, subcategory=sub2)
        Company_Policy.objects.create(company=self.company, policy_level=level1)
        Company_Policy.objects.create(company=self.company, policy_level=level2)

        response = self.client.get(self.url)
        data = json.loads(response.content)

        self.assertEqual(len(data['policies']), 1)
        pt_data = data['policies'][0]
        self.assertEqual(pt_data['type'], 'Biodiversité')
        self.assertAlmostEqual(pt_data['avg_score'], 0.6, places=1)
        self.assertEqual(len(pt_data['entries']), 2)
        entry_subs = {e['subcategory'] for e in pt_data['entries']}
        self.assertEqual(entry_subs, {'Approvisionnement', 'Reporting'})

    def test_policies_empty_when_none(self):
        response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertEqual(data['policies'], [])


class DashboardIndexViewTests(TestCase):

    def test_index_returns_200(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)

    def test_index_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertTemplateUsed(response, 'dashboard/index.html')

    def test_companies_in_context(self):
        Company.objects.create(name='Zeta Corp')
        Company.objects.create(name='Alpha Corp')
        response = self.client.get(reverse('dashboard:index'))
        companies = response.context['companies']
        self.assertEqual(len(companies), 2)
        self.assertEqual(companies[0]['name'], 'Alpha Corp')  # ordered by name

    def test_initial_data_present_with_companies(self):
        _make_world()
        response = self.client.get(reverse('dashboard:index'))
        self.assertIsNotNone(response.context['initial_data'])
        data = response.context['initial_data']
        self.assertIn('asset_count', data)

    def test_initial_data_none_without_companies(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertIsNone(response.context['initial_data'])


class TransitionRiskDataViewTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)

    def _setup_company(self, impact_factor=2.0, production_qty=100.0, year=2024):
        company = Company.objects.create(name='RiskCorp')
        country = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private'
        )
        region = SubnationalRegion.objects.create(name='Amazonie', country=country)
        commodity = Commodity.objects.create(
            name='SojaRisk',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=impact_factor,
        )
        asset = Asset.objects.create(
            name='Ferme A', latitude=-5.0, longitude=-55.0,
            country=country, subnational_region=region,
        )
        Ownership.objects.create(Asset=asset, Company=company, ownership='100%')
        Production.objects.create(
            asset=asset, commodity=commodity, year=year, production=production_qty
        )
        return company, country, commodity, asset

    def test_returns_200(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_content_type_is_json(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertIn('application/json', response['Content-Type'])

    def test_total_impact_equals_production_times_factor(self):
        company, *_ = self._setup_company(impact_factor=3.0, production_qty=50.0)
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        self.assertAlmostEqual(data['total_impact'], 150.0, places=2)

    def test_single_commodity_pct_is_one(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        self.assertEqual(len(data['commodities']), 1)
        self.assertAlmostEqual(data['commodities'][0]['pct'], 1.0, places=3)

    def test_uses_latest_year_only(self):
        company, country, commodity, asset = self._setup_company(
            impact_factor=2.0, production_qty=10.0, year=2022
        )
        # Add a newer production — this one should be used
        Production.objects.create(
            asset=asset, commodity=commodity, year=2024, production=100.0
        )
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        # 100 * 2.0 = 200, not 10 * 2.0 = 20
        self.assertAlmostEqual(data['total_impact'], 200.0, places=2)
        self.assertEqual(data['year'], 2024)
        # 220 = 10×2 + 100×2 — would appear if both years were summed
        self.assertNotAlmostEqual(data['total_impact'], 220.0, places=2)

    def test_sankey_links_commodity_to_asset(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        sources = [lk['source'] for lk in data['sankey_links']]
        self.assertTrue(any(s.startswith('commodity:') for s in sources))

    def test_sankey_links_asset_to_country(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        sources = [lk['source'] for lk in data['sankey_links']]
        self.assertTrue(any(s.startswith('asset:') for s in sources))

    def test_sankey_links_country_to_company(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        sources = [lk['source'] for lk in data['sankey_links']]
        self.assertTrue(any(s.startswith('country:') for s in sources))

    def test_empty_company_returns_zero_impact(self):
        empty = Company.objects.create(name='EmptyRisk')
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': empty.pk})
        data = json.loads(self.client.get(url).content)
        self.assertEqual(data['total_impact'], 0)
        self.assertEqual(data['commodities'], [])
        self.assertEqual(data['sankey_links'], [])

    def test_not_found_returns_404(self):
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_post_not_allowed(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        response = self.client.post(url)
        # Authenticated POST is blocked by @require_GET → 405
        self.assertEqual(response.status_code, 405)

    def test_two_commodities_pct_sum_to_one(self):
        company = Company.objects.create(name='MultiCorp')
        country = Country.objects.create(
            name='Argentine', water_ownership='Pub', land_ownership='Priv'
        )
        region = SubnationalRegion.objects.create(name='Pampa', country=country)
        asset = Asset.objects.create(
            name='Estancia', latitude=-30.0, longitude=-65.0,
            country=country, subnational_region=region,
        )
        Ownership.objects.create(Asset=asset, Company=company, ownership='100%')
        c1 = Commodity.objects.create(
            name='Maïs', impact_endpoint_ReCiPe2016_ecosystem_diversity=1.0
        )
        c2 = Commodity.objects.create(
            name='Blé', impact_endpoint_ReCiPe2016_ecosystem_diversity=3.0
        )
        Production.objects.create(asset=asset, commodity=c1, year=2024, production=100.0)
        Production.objects.create(asset=asset, commodity=c2, year=2024, production=100.0)

        url = reverse('dashboard:transition_risk_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)

        pct_sum = sum(c['pct'] for c in data['commodities'])
        self.assertAlmostEqual(pct_sum, 1.0, places=3)
        # Blé has 3x impact → sorted first
        self.assertEqual(data['commodities'][0]['name'], 'Blé')


class TransitionRiskPageViewTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='pageuser', password='testpass')
        self.client.force_login(self.user)

    def test_returns_200(self):
        response = self.client.get(reverse('dashboard:transition_risk'))
        self.assertEqual(response.status_code, 200)

    def test_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:transition_risk'))
        self.assertTemplateUsed(response, 'dashboard/transition_risk.html')

    def test_companies_in_context(self):
        Company.objects.create(name='ZetaRisk')
        response = self.client.get(reverse('dashboard:transition_risk'))
        self.assertIn('companies', response.context)

    def test_initial_data_none_without_companies(self):
        response = self.client.get(reverse('dashboard:transition_risk'))
        self.assertIsNone(response.context['initial_data'])

    def test_initial_data_present_with_companies(self):
        company, *_ = _make_world()
        response = self.client.get(reverse('dashboard:transition_risk'))
        self.assertIsNotNone(response.context['initial_data'])
        self.assertIn('total_impact', response.context['initial_data'])


class DependenciesDataTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='depuser', password='testpass')
        self.client.force_login(self.user)

        self.company = Company.objects.create(name='DepCorp')
        self.country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private'
        )
        self.region = SubnationalRegion.objects.create(name='IDF', country=self.country)
        # Commodity with known dependency scores: water=H(0.7), soil=M(0.5), rest=VL(0.0)
        self.commodity = Commodity.objects.create(
            name='TestCom',
            dependency_water='H',
            dependency_soil_quality='M',
            dependency_carbon_sequestration='VL',
            dependency_water_purification='VL',
            dependency_pest_control='VL',
            dependency_pollination='VL',
        )
        Production.objects.create(
            company=self.company,
            commodity=self.commodity,
            year=2024,
            production=100.0,
            scope='direct',
        )

    def test_score_map_conversion(self):
        from .views import SCORE_MAP
        self.assertEqual(SCORE_MAP['VL'], 0.0)
        self.assertEqual(SCORE_MAP['L'],  0.2)
        self.assertEqual(SCORE_MAP['M'],  0.5)
        self.assertEqual(SCORE_MAP['H'],  0.7)
        self.assertEqual(SCORE_MAP['VH'], 1.0)

    def test_global_exposure_score(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        # 6 services: water=0.7, soil=0.5, rest=0.0 → avg = (0.7+0.5+0+0+0+0)/6
        expected = round((0.7 + 0.5) / 6, 3)
        self.assertAlmostEqual(data['global_exposure_score'], expected, places=3)

    def test_critical_nodes_counts_h_or_vh(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        # water=H(0.7) → this commodity×scope is critical
        self.assertEqual(data['critical_nodes'], 1)

    def test_primary_service_is_highest_avg(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        self.assertEqual(data['primary_service']['key'], 'water')
        self.assertAlmostEqual(data['primary_service']['score'], 0.7, places=3)

    def test_supply_chain_grouped_by_scope(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        scopes = [t['scope'] for t in data['supply_chain']]
        self.assertIn('direct', scopes)

    def test_supply_chain_only_shows_services_above_threshold(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        direct_tier = next(t for t in data['supply_chain'] if t['scope'] == 'direct')
        # Only water(0.7) and soil(0.5) are >= 0.2
        service_keys = [s['key'] for s in direct_tier['services']]
        self.assertIn('water', service_keys)
        self.assertIn('soil_quality', service_keys)
        self.assertNotIn('pollination', service_keys)

    def test_supply_chain_labels(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        direct_tier = next(t for t in data['supply_chain'] if t['scope'] == 'direct')
        water_svc = next(s for s in direct_tier['services'] if s['key'] == 'water')
        self.assertEqual(water_svc['label'], 'Critical')
        soil_svc = next(s for s in direct_tier['services'] if s['key'] == 'soil_quality')
        self.assertEqual(soil_svc['label'], 'High')

    def test_empty_company_returns_defaults(self):
        from .views import _get_dependencies_data
        empty = Company.objects.create(name='Empty')
        data = _get_dependencies_data(empty)
        self.assertIsNone(data['year'])
        self.assertEqual(data['global_exposure_score'], 0)
        self.assertEqual(data['critical_nodes'], 0)
        self.assertIsNone(data['primary_service'])
        self.assertEqual(data['supply_chain'], [])

    def test_revenue_segments_sorted_by_revenue_desc(self):
        from .views import _get_dependencies_data
        sector = Sector.objects.create(name='Agri')
        sub1 = SubSector.objects.create(
            name='Céréales', sector=sector,
            Water_dependency='H', Pollination_dependency='VL',
            Soil_quality_dependency='VL', Carbon_Sequestration='VL',
            Water_purification_dependency='VL', Pest_control_dependency='VL',
        )
        sub2 = SubSector.objects.create(
            name='Légumes', sector=sector,
            Water_dependency='L', Pollination_dependency='VL',
            Soil_quality_dependency='VL', Carbon_Sequestration='VL',
            Water_purification_dependency='VL', Pest_control_dependency='VL',
        )
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=sub1, year=2024, revenue=12_000_000
        )
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=sub2, year=2024, revenue=5_000_000
        )
        data = _get_dependencies_data(self.company)
        self.assertEqual(len(data['revenue_segments']), 2)
        self.assertEqual(data['revenue_segments'][0]['subsector'], 'Céréales')
        self.assertEqual(data['revenue_segments'][0]['exposure_label'], 'High')
        self.assertEqual(data['revenue_segments'][1]['subsector'], 'Légumes')
        self.assertEqual(data['revenue_segments'][1]['exposure_label'], 'Low')

    def test_uses_latest_year_only(self):
        from .views import _get_dependencies_data
        commodity2 = Commodity.objects.create(
            name='OldCom',
            dependency_water='VH',
            dependency_soil_quality='VH',
            dependency_carbon_sequestration='VH',
            dependency_water_purification='VH',
            dependency_pest_control='VH',
            dependency_pollination='VH',
        )
        # Older year — should be ignored
        Production.objects.create(
            company=self.company, commodity=commodity2, year=2020,
            production=999.0, scope='direct',
        )
        data = _get_dependencies_data(self.company)
        self.assertEqual(data['year'], 2024)
        # primary service should still reflect 2024 commodity, not 2020 VH one
        expected_score = round((0.7 + 0.5) / 6, 3)
        self.assertAlmostEqual(data['global_exposure_score'], expected_score, places=3)

    def test_productions_via_asset_included(self):
        from .views import _get_dependencies_data
        asset = Asset.objects.create(
            name='Site B', latitude=0.0, longitude=0.0,
            country=self.country, subnational_region=self.region,
        )
        Ownership.objects.create(Asset=asset, Company=self.company, ownership='100%')
        commodity_vh = Commodity.objects.create(
            name='AssetCom',
            dependency_water='VH',
            dependency_soil_quality='VH',
            dependency_carbon_sequestration='VH',
            dependency_water_purification='VH',
            dependency_pest_control='VH',
            dependency_pollination='VH',
        )
        Production.objects.create(
            asset=asset, commodity=commodity_vh, year=2024,
            production=50.0, scope='tier 1',
        )
        data = _get_dependencies_data(self.company)
        # 'tier 1' scope should appear because asset-linked production was included
        scopes = [t['scope'] for t in data['supply_chain']]
        self.assertIn('tier 1', scopes)

    def test_service_exposure_with_revenue(self):
        from .views import _get_dependencies_data
        Company_Revenue.objects.create(
            company=self.company, year=2024, revenue=10_000_000, currency='EUR'
        )
        data = _get_dependencies_data(self.company)
        se = data['service_exposure']
        self.assertEqual(se['total_revenue'], 10_000_000)
        self.assertEqual(se['currency'], 'EUR')
        water_svc = next(
            s for cat in se['categories'] for s in cat['services'] if s['key'] == 'water'
        )
        self.assertAlmostEqual(water_svc['revenue_exposure'], round(0.7 * 10_000_000), delta=1)

    def test_service_exposure_without_revenue(self):
        from .views import _get_dependencies_data
        data = _get_dependencies_data(self.company)
        se = data['service_exposure']
        self.assertIsNone(se['total_revenue'])
        water_svc = next(
            s for cat in se['categories'] for s in cat['services'] if s['key'] == 'water'
        )
        self.assertIsNone(water_svc['revenue_exposure'])
