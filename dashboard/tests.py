import json
from django.test import TestCase
from django.urls import reverse
from .models import (
    Asset, Commodity, Company, Company_Policy, Company_Revenue,
    Company_Revenue_Sector, Country, Ownership, Policy_Level,
    Policy_Subcategory, Policy_Type, Production, Sector, SubnationalRegion,
    SubSector,
)
from .views import _get_dette_ecologique_data


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


class MesureEmpreinteDataViewTests(TestCase):

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
        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_content_type_is_json(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertIn('application/json', response['Content-Type'])

    def test_total_impact_equals_production_times_factor(self):
        company, *_ = self._setup_company(impact_factor=3.0, production_qty=50.0)
        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        self.assertAlmostEqual(data['total_impact'], 150.0, places=2)

    def test_single_commodity_pct_is_one(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': company.pk})
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
        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        # 100 * 2.0 = 200, not 10 * 2.0 = 20
        self.assertAlmostEqual(data['total_impact'], 200.0, places=2)
        self.assertEqual(data['year'], 2024)
        # 220 = 10×2 + 100×2 — would appear if both years were summed
        self.assertNotAlmostEqual(data['total_impact'], 220.0, places=2)

    def test_sankey_links_commodity_to_asset(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        sources = [lk['source'] for lk in data['sankey_links']]
        self.assertTrue(any(s.startswith('commodity:') for s in sources))

    def test_sankey_links_asset_to_country(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        sources = [lk['source'] for lk in data['sankey_links']]
        self.assertTrue(any(s.startswith('asset:') for s in sources))

    def test_sankey_links_country_to_company(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)
        sources = [lk['source'] for lk in data['sankey_links']]
        self.assertTrue(any(s.startswith('country:') for s in sources))

    def test_empty_company_returns_zero_impact(self):
        empty = Company.objects.create(name='EmptyRisk')
        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': empty.pk})
        data = json.loads(self.client.get(url).content)
        self.assertEqual(data['total_impact'], 0)
        self.assertEqual(data['commodities'], [])
        self.assertEqual(data['sankey_links'], [])

    def test_not_found_returns_404(self):
        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_post_not_allowed(self):
        company, *_ = self._setup_company()
        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': company.pk})
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

        url = reverse('dashboard:mesure_empreinte_data', kwargs={'pk': company.pk})
        data = json.loads(self.client.get(url).content)

        pct_sum = sum(c['pct'] for c in data['commodities'])
        self.assertAlmostEqual(pct_sum, 1.0, places=3)
        # Blé has 3x impact → sorted first
        self.assertEqual(data['commodities'][0]['name'], 'Blé')


class MesureEmpreintePageViewTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='pageuser', password='testpass')
        self.client.force_login(self.user)

    def test_returns_200(self):
        response = self.client.get(reverse('dashboard:mesure_empreinte'))
        self.assertEqual(response.status_code, 200)

    def test_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:mesure_empreinte'))
        self.assertTemplateUsed(response, 'dashboard/mesure_empreinte.html')

    def test_companies_in_context(self):
        Company.objects.create(name='ZetaRisk')
        response = self.client.get(reverse('dashboard:mesure_empreinte'))
        self.assertIn('companies', response.context)

    def test_initial_data_none_without_companies(self):
        response = self.client.get(reverse('dashboard:mesure_empreinte'))
        self.assertIsNone(response.context['initial_data'])

    def test_initial_data_present_with_companies(self):
        company, *_ = _make_world()
        response = self.client.get(reverse('dashboard:mesure_empreinte'))
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
        sector_a = Sector.objects.create(name='Agriculture')
        sector_b = Sector.objects.create(name='Énergie')
        # sub1 in Agriculture with Water=H: dep_score = 0.7/6
        sub1 = SubSector.objects.create(
            name='Céréales', sector=sector_a,
            Water_dependency='H', Pollination_dependency='VL',
            Soil_quality_dependency='VL', Carbon_Sequestration='VL',
            Water_purification_dependency='VL', Pest_control_dependency='VL',
        )
        # sub2 in Agriculture with Water=L: dep_score = 0.2/6
        sub2 = SubSector.objects.create(
            name='Légumes', sector=sector_a,
            Water_dependency='L', Pollination_dependency='VL',
            Soil_quality_dependency='VL', Carbon_Sequestration='VL',
            Water_purification_dependency='VL', Pest_control_dependency='VL',
        )
        # sub3 in Énergie with Water=M: dep_score = 0.5/6
        sub3 = SubSector.objects.create(
            name='Pétrole', sector=sector_b,
            Water_dependency='M', Pollination_dependency='VL',
            Soil_quality_dependency='VL', Carbon_Sequestration='VL',
            Water_purification_dependency='VL', Pest_control_dependency='VL',
        )
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=sub1, year=2024, revenue=12_000_000
        )
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=sub2, year=2024, revenue=5_000_000
        )
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=sub3, year=2024, revenue=4_000_000
        )
        data = _get_dependencies_data(self.company)

        # Two sectors: Agriculture (17M) sorted before Énergie (4M)
        self.assertEqual(len(data['revenue_segments']), 2)
        agri = data['revenue_segments'][0]
        energy = data['revenue_segments'][1]

        self.assertEqual(agri['sector'], 'Agriculture')
        self.assertEqual(agri['revenue'], 17_000_000)
        # dep_score for Agriculture = avg of sub1 (0.7/6) and sub2 (0.2/6)
        sub1_dep = round(0.7 / 6, 3)
        sub2_dep = round(0.2 / 6, 3)
        expected_agri_dep = round((sub1_dep + sub2_dep) / 2, 3)
        self.assertAlmostEqual(agri['dep_score'], expected_agri_dep, places=2)
        self.assertAlmostEqual(
            agri['revenue_at_risk'], round(expected_agri_dep * 17_000_000), delta=5000
        )

        # Subsectors within Agriculture sorted by revenue desc
        self.assertEqual(len(agri['subsectors']), 2)
        self.assertEqual(agri['subsectors'][0]['subsector'], 'Céréales')
        self.assertEqual(agri['subsectors'][1]['subsector'], 'Légumes')

        # Each subsector has services list with 6 entries
        self.assertEqual(len(agri['subsectors'][0]['services']), 6)
        water_svc = next(s for s in agri['subsectors'][0]['services'] if s['key'] == 'water')
        self.assertAlmostEqual(water_svc['score'], 0.7, places=3)
        self.assertEqual(water_svc['label'], 'Critical')

        # revenue_at_risk on subsector
        self.assertAlmostEqual(
            agri['subsectors'][0]['revenue_at_risk'],
            round(sub1_dep * 12_000_000),
            delta=5000
        )

        self.assertEqual(energy['sector'], 'Énergie')
        self.assertEqual(energy['revenue'], 4_000_000)

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


class DependenciesPageViewTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='deppage', password='testpass')
        self.client.force_login(self.user)

    def test_redirects_anonymous(self):
        self.client.logout()
        response = self.client.get('/dependencies/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_returns_200_authenticated(self):
        response = self.client.get('/dependencies/')
        self.assertEqual(response.status_code, 200)

    def test_uses_correct_template(self):
        response = self.client.get('/dependencies/')
        self.assertTemplateUsed(response, 'dashboard/dependencies.html')

    def test_companies_in_context(self):
        Company.objects.create(name='CtxCorp')
        response = self.client.get('/dependencies/')
        self.assertIn('companies', response.context)

    def test_initial_data_none_without_companies(self):
        response = self.client.get('/dependencies/')
        self.assertIsNone(response.context['initial_data'])

    def test_api_returns_200(self):
        company = Company.objects.create(name='ApiCorp')
        url = reverse('dashboard:dependencies_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_api_content_type_is_json(self):
        company = Company.objects.create(name='JsonCorp')
        url = reverse('dashboard:dependencies_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertIn('application/json', response['Content-Type'])

    def test_api_404_on_missing_company(self):
        url = reverse('dashboard:dependencies_data', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_api_post_not_allowed(self):
        company = Company.objects.create(name='PostCorp')
        url = reverse('dashboard:dependencies_data', kwargs={'pk': company.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 405)


class PhysicalRiskDataTests(TestCase):

    def setUp(self):
        from .models import Ownership
        self.company = Company.objects.create(name='PhysCorp')
        self.country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private'
        )
        self.region = SubnationalRegion.objects.create(name='IDF', country=self.country)
        self.commodity = Commodity.objects.create(name='Soja')

        # Asset A1: flood=0.8 (high risk), drought=0.5, rest 0
        self.a1 = Asset.objects.create(
            name='Site A1', latitude=48.0, longitude=2.0,
            country=self.country, subnational_region=self.region,
            risk_flood=0.8, risk_drought=0.5,
        )
        # Asset A2: flood=0.2, rest 0 (not high risk)
        self.a2 = Asset.objects.create(
            name='Site A2', latitude=43.0, longitude=5.0,
            country=self.country, subnational_region=self.region,
            risk_flood=0.2,
        )
        Ownership.objects.create(Asset=self.a1, Company=self.company, ownership='100%')
        Ownership.objects.create(Asset=self.a2, Company=self.company, ownership='100%')

        # Exposition: A1 latest year 2024 = 1000 (older 2022 ignored); A2 2024 = 500
        Production.objects.create(
            asset=self.a1, commodity=self.commodity, year=2022,
            production=1.0, estimated_revenue=9999.0,
        )
        Production.objects.create(
            asset=self.a1, commodity=self.commodity, year=2024,
            production=1.0, estimated_revenue=1000.0,
        )
        Production.objects.create(
            asset=self.a2, commodity=self.commodity, year=2024,
            production=1.0, estimated_revenue=500.0,
        )

        # Policies: two levels with vulnerability_flood 1.0 and 1.5 -> mean 1.25
        pt = Policy_Type.objects.create(name='Climat')
        sub = Policy_Subcategory.objects.create(name='Adaptation', policy_type=pt)
        lvl1 = Policy_Level.objects.create(
            name='Niveau 1', subcategory=sub, vulnerability_flood=1.0
        )
        lvl2 = Policy_Level.objects.create(
            name='Niveau 2', subcategory=sub, vulnerability_flood=1.5
        )
        Company_Policy.objects.create(company=self.company, policy_level=lvl1)
        Company_Policy.objects.create(company=self.company, policy_level=lvl2)

    def test_exposition_uses_latest_year_only(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        a1 = next(a for a in data['assets'] if a['name'] == 'Site A1')
        self.assertAlmostEqual(a1['exposition'], 1000.0, places=2)

    def test_vulnerability_is_mean_across_policies(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        flood = next(h for h in data['hazards'] if h['key'] == 'flood')
        self.assertAlmostEqual(flood['vulnerability'], 1.25, places=3)

    def test_assets_high_risk_count(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        # only A1 has a hazard >= 0.7 (flood 0.8)
        self.assertEqual(data['kpis']['assets_high_risk'], 1)

    def test_annual_loss(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        # A1: flood 0.8*1000*1.25=1000 + drought 0.5*1000*1.0=500 = 1500
        # A2: flood 0.2*500*1.25=125 = 125  -> total 1625
        self.assertAlmostEqual(data['kpis']['annual_loss'], 1625.0, places=2)

    def test_avg_vulnerability(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        # 14 hazards at 1.0 + flood 1.25, over 15
        self.assertAlmostEqual(data['kpis']['avg_vulnerability'], (14 + 1.25) / 15, places=4)

    def test_ranking_sorted_flood_first(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        # flood avg_risk = (1000+125)/2 = 562.5 ; drought = (500+0)/2 = 250
        self.assertEqual(data['hazards'][0]['key'], 'flood')
        self.assertAlmostEqual(data['hazards'][0]['avg_risk'], 562.5, places=2)
        drought = next(h for h in data['hazards'] if h['key'] == 'drought')
        self.assertAlmostEqual(drought['avg_risk'], 250.0, places=2)

    def test_assets_carry_all_15_risk_keys(self):
        from .views import _get_physical_risk_data, PHYSICAL_RISKS
        data = _get_physical_risk_data(self.company)
        a1 = next(a for a in data['assets'] if a['name'] == 'Site A1')
        self.assertEqual(set(a1['risk'].keys()), {r['key'] for r in PHYSICAL_RISKS})
        self.assertEqual(len(PHYSICAL_RISKS), 15)

    def test_empty_company_defaults(self):
        from .views import _get_physical_risk_data
        empty = Company.objects.create(name='EmptyPhys')
        data = _get_physical_risk_data(empty)
        self.assertEqual(data['assets'], [])
        self.assertEqual(data['kpis']['assets_high_risk'], 0)
        self.assertAlmostEqual(data['kpis']['annual_loss'], 0.0, places=2)
        # no policies -> every vulnerability defaults to 1.0
        self.assertAlmostEqual(data['kpis']['avg_vulnerability'], 1.0, places=4)
        self.assertTrue(all(h['avg_risk'] == 0.0 for h in data['hazards']))

    def test_assets_without_policies_use_default_vulnerability(self):
        from .views import _get_physical_risk_data
        from .models import Ownership
        company = Company.objects.create(name='NoPolicyPhys')
        asset = Asset.objects.create(
            name='Solo', latitude=1.0, longitude=1.0,
            country=self.country, subnational_region=self.region,
            risk_flood=0.5,
        )
        Ownership.objects.create(Asset=asset, Company=company, ownership='100%')
        Production.objects.create(
            asset=asset, commodity=self.commodity, year=2024,
            production=1.0, estimated_revenue=200.0,
        )
        data = _get_physical_risk_data(company)
        flood = next(h for h in data['hazards'] if h['key'] == 'flood')
        self.assertAlmostEqual(flood['vulnerability'], 1.0, places=4)
        # annual_loss = 0.5 * 200 * 1.0 = 100 (only flood non-zero)
        self.assertAlmostEqual(data['kpis']['annual_loss'], 100.0, places=2)


class PhysicalRiskPageViewTests(TestCase):

    def test_page_returns_200_without_login(self):
        response = self.client.get(reverse('dashboard:physical_risk'))
        self.assertEqual(response.status_code, 200)

    def test_page_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:physical_risk'))
        self.assertTemplateUsed(response, 'dashboard/physical_risk.html')

    def test_companies_in_context(self):
        Company.objects.create(name='CtxPhys')
        response = self.client.get(reverse('dashboard:physical_risk'))
        self.assertIn('companies', response.context)

    def test_initial_data_none_without_companies(self):
        response = self.client.get(reverse('dashboard:physical_risk'))
        self.assertIsNone(response.context['initial_data'])

    def test_initial_data_present_with_companies(self):
        Company.objects.create(name='HasDataPhys')
        response = self.client.get(reverse('dashboard:physical_risk'))
        self.assertIsNotNone(response.context['initial_data'])
        self.assertIn('kpis', response.context['initial_data'])

    def test_api_returns_200_without_login(self):
        company = Company.objects.create(name='ApiPhys')
        url = reverse('dashboard:physical_risk_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_api_content_type_is_json(self):
        company = Company.objects.create(name='JsonPhys')
        url = reverse('dashboard:physical_risk_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertIn('application/json', response['Content-Type'])

    def test_api_404_on_missing_company(self):
        url = reverse('dashboard:physical_risk_data', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_api_post_not_allowed(self):
        company = Company.objects.create(name='PostPhys')
        url = reverse('dashboard:physical_risk_data', kwargs={'pk': company.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 405)


class DetteEcologiqueDataTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='TestCorp')
        self.country = Country.objects.create(
            name='France',
            water_ownership='Public',
            land_ownership='Private',
            biodiversity_loss_agriculture=2.0,
            biodiversity_loss_urbanization=3.0,
            biodiversity_loss_mining=1.5,
        )
        self.region = SubnationalRegion.objects.create(
            name='IDF', country=self.country,
            restoration_cost_m2=10.0,
            Mean_X=2.3, Mean_Y=48.8,
        )
        self.commodity_agri = Commodity.objects.create(
            name='Soja',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
            biodiversity_loss_class='Agriculture',
        )
        self.asset = Asset.objects.create(
            name='Site A', latitude=48.8, longitude=2.3,
            country=self.country, subnational_region=self.region,
        )
        Ownership.objects.create(Asset=self.asset, Company=self.company, ownership='100%')

    def test_no_assets_returns_empty(self):
        other = Company.objects.create(name='Empty')
        result = _get_dette_ecologique_data(other)
        self.assertEqual(result['total_lbiodiv'], 0)
        self.assertEqual(result['assets'], [])
        self.assertEqual(result['regions'], [])

    def test_excludes_asset_without_region(self):
        asset_no_region = Asset.objects.create(
            name='No Region', latitude=0.0, longitude=0.0,
            country=self.country, subnational_region=None,
        )
        Ownership.objects.create(Asset=asset_no_region, Company=self.company, ownership='100%')
        Production.objects.create(
            asset=asset_no_region, commodity=self.commodity_agri, year=2024, production=100.0,
        )
        result = _get_dette_ecologique_data(self.company)
        asset_ids = [a['id'] for a in result['assets']]
        self.assertNotIn(asset_no_region.pk, asset_ids)

    def test_lbiodiv_formula_agriculture(self):
        # 2.0 * 10.0 * 100.0 * 0.5 = 1000.0
        Production.objects.create(
            asset=self.asset, commodity=self.commodity_agri, year=2024, production=100.0,
        )
        result = _get_dette_ecologique_data(self.company)
        self.assertAlmostEqual(result['total_lbiodiv'], 1000.0, places=2)

    def test_lbiodiv_formula_urbanisation(self):
        # biodiversity_loss_urbanization=3.0 → 3.0 * 10.0 * 100.0 * 0.5 = 1500.0
        commodity_urb = Commodity.objects.create(
            name='Béton',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
            biodiversity_loss_class='Urbanisation',
        )
        Production.objects.create(
            asset=self.asset, commodity=commodity_urb, year=2024, production=100.0,
        )
        result = _get_dette_ecologique_data(self.company)
        self.assertAlmostEqual(result['total_lbiodiv'], 1500.0, places=2)

    def test_lbiodiv_formula_mining(self):
        # biodiversity_loss_mining=1.5 → 1.5 * 10.0 * 100.0 * 0.5 = 750.0
        commodity_min = Commodity.objects.create(
            name='Lithium',
            impact_endpoint_ReCiPe2016_ecosystem_diversity=0.5,
            biodiversity_loss_class='Mining',
        )
        Production.objects.create(
            asset=self.asset, commodity=commodity_min, year=2024, production=100.0,
        )
        result = _get_dette_ecologique_data(self.company)
        self.assertAlmostEqual(result['total_lbiodiv'], 750.0, places=2)

    def test_latest_year_only(self):
        Production.objects.create(
            asset=self.asset, commodity=self.commodity_agri, year=2022, production=999.0,
        )
        Production.objects.create(
            asset=self.asset, commodity=self.commodity_agri, year=2024, production=100.0,
        )
        # Only 2024 : 2.0 * 10.0 * 100.0 * 0.5 = 1000.0
        result = _get_dette_ecologique_data(self.company)
        self.assertAlmostEqual(result['total_lbiodiv'], 1000.0, places=2)

    def test_region_aggregation(self):
        asset2 = Asset.objects.create(
            name='Site B', latitude=48.9, longitude=2.4,
            country=self.country, subnational_region=self.region,
        )
        Ownership.objects.create(Asset=asset2, Company=self.company, ownership='100%')
        Production.objects.create(
            asset=self.asset, commodity=self.commodity_agri, year=2024, production=100.0,
        )
        Production.objects.create(
            asset=asset2, commodity=self.commodity_agri, year=2024, production=50.0,
        )
        result = _get_dette_ecologique_data(self.company)
        self.assertEqual(len(result['regions']), 1)
        # 2.0*10.0*100.0*0.5 + 2.0*10.0*50.0*0.5 = 1000 + 500 = 1500
        self.assertAlmostEqual(result['regions'][0]['total_lbiodiv'], 1500.0, places=2)


from django.contrib.auth import get_user_model


class DetteEcologiqueViewTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='tester', password='pass')
        self.client.login(username='tester', password='pass')

    def test_mesure_empreinte_returns_200(self):
        response = self.client.get(reverse('dashboard:mesure_empreinte'))
        self.assertEqual(response.status_code, 200)

    def test_dette_ecologique_returns_200(self):
        response = self.client.get(reverse('dashboard:dette_ecologique'))
        self.assertEqual(response.status_code, 200)
