import json
from django.test import TestCase
from django.urls import reverse
from .models import (
    Asset, Commodity, Company, Company_Policy, Country,
    Ownership, Policy_Level, Policy_Subcategory, Policy_Type,
    Production, SubnationalRegion,
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
    Production.objects.create(Asset=asset, commodity=commodity, year=2024, production=100.0)
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
