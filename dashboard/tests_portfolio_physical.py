"""Carte du risque physique d'un portefeuille (services/portfolio_physical.py) :
actifs agrégés, pondérés par l'exposition financée (montant / EVIC)."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from dashboard.models import (
    Asset, Commodity, Company, Company_Policy, Company_Revenue, Country, Currency,
    Ownership, Policy_Level, Policy_Subcategory, Policy_Type, Portfolio, PortfolioHolding,
)
from dashboard.services.portfolio_physical import physical_risk_map
from dashboard.testing import make_production


class PortfolioPhysicalMapTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='pf', password='x')
        self.eur = Currency.objects.create(code='EUR', name='Euro', symbol='€')
        self.france = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private')
        self.soja = Commodity.objects.create(name='Soja')

        # Alpha : EVIC 1 000, investi 100 → attribution 0,1 ; vulnérabilité crue 1,5.
        self.alpha = Company.objects.create(name='Alpha')
        Company_Revenue.objects.create(
            company=self.alpha, year=2024, revenue=1, evic=1000.0, currency='EUR')
        # Beta : EVIC 2 000, investi 100 → attribution 0,05 ; vulnérabilité 1,0 (défaut).
        self.beta = Company.objects.create(name='Beta')
        Company_Revenue.objects.create(
            company=self.beta, year=2024, revenue=1, evic=2000.0, currency='EUR')
        policy_type = Policy_Type.objects.create(name='Climat')
        sub = Policy_Subcategory.objects.create(name='Adaptation', policy_type=policy_type)
        level = Policy_Level.objects.create(name='N1', subcategory=sub, vulnerability_flood=1.5)
        Company_Policy.objects.create(company=self.alpha, policy_level=level)

        # Site A (Alpha seule) : revenu 1 000, crue 0,8.
        self.site_a = self.asset('Site A', revenue=1000.0, risk_flood=0.8)
        Ownership.objects.create(asset=self.site_a, company=self.alpha, share=1)
        # Site commun (Alpha et Beta) : revenu 400, crue 0,5.
        self.shared = self.asset('Site commun', revenue=400.0, risk_flood=0.5)
        Ownership.objects.create(asset=self.shared, company=self.alpha, share=0.5)
        Ownership.objects.create(asset=self.shared, company=self.beta, share=0.5)

        self.portfolio = Portfolio.objects.create(
            name='Fonds', size=200, currency=self.eur, created_by=self.user)
        PortfolioHolding.objects.create(
            portfolio=self.portfolio, company=self.alpha, amount=100, weight=50)
        PortfolioHolding.objects.create(
            portfolio=self.portfolio, company=self.beta, amount=100, weight=50)

    def asset(self, name, revenue, **risks):
        asset = Asset.objects.create(
            name=name, latitude=45.0, longitude=3.0, country=self.france, **risks)
        make_production(asset=asset, commodity=self.soja, year=2024, production=1.0,
                        estimated_revenue=revenue)
        return asset

    def data(self):
        holdings = list(self.portfolio.holdings.select_related('company'))
        return physical_risk_map(holdings)

    def test_exposition_financee_et_actif_commun_agrege(self):
        data = self.data()
        assets = {a['name']: a for a in data['assets']}
        self.assertEqual(len(data['assets']), 2)
        # 1 000 × 0,1
        self.assertAlmostEqual(assets['Site A']['exposition'], 100.0)
        # 400 × (0,1 + 0,05), une seule ligne pour les deux détentrices.
        self.assertAlmostEqual(assets['Site commun']['exposition'], 60.0)
        self.assertEqual(assets['Site commun']['companies'], 'Alpha, Beta')
        # Vulnérabilité pondérée par l'attribution : (0,1 × 1,5 + 0,05 × 1,0) / 0,15.
        self.assertAlmostEqual(assets['Site commun']['vulnerability']['flood'], 4 / 3, places=4)

    def test_perte_annuelle_et_classement(self):
        data = self.data()
        # Crue : 0,8 × 100 × 1,5 + 0,5 × 60 × 4/3 = 120 + 40 = 160.
        flood = next(h for h in data['hazards'] if h['key'] == 'flood')
        self.assertAlmostEqual(flood['avg_risk'], 80.0)   # 160 / 2 actifs
        self.assertEqual(data['hazards'][0]['key'], 'flood')
        self.assertAlmostEqual(data['kpis']['annual_loss'], 160.0)
        self.assertEqual(
            [d['policy'] for d in flood['vulnerability_detail']], ['Alpha', 'Beta'])

    def test_entreprise_sans_evic(self):
        gamma = Company.objects.create(name='Gamma')
        site = self.asset('Site G', revenue=500.0, risk_flood=0.9)
        Ownership.objects.create(asset=site, company=gamma, share=1)
        PortfolioHolding.objects.create(
            portfolio=self.portfolio, company=gamma, amount=100, weight=0)
        data = self.data()
        site_g = next(a for a in data['assets'] if a['name'] == 'Site G')
        self.assertEqual(site_g['exposition'], 0.0)
        self.assertEqual(data['companies_without_evic'], ['Gamma'])
        self.assertAlmostEqual(data['kpis']['annual_loss'], 160.0)

    def test_portefeuille_vide(self):
        data = physical_risk_map([])
        self.assertEqual(data['assets'], [])
        self.assertEqual(data['kpis']['annual_loss'], 0.0)

    def test_api_et_page(self):
        self.client.force_login(self.user)
        url = reverse('dashboard:portfolio_physical_risk', kwargs={'pk': self.portfolio.pk})
        payload = json.loads(self.client.get(url).content)
        self.assertIn('map', payload)
        self.assertIn('portfolio', payload)   # radar inchangé
        page = self.client.get(reverse('dashboard:portfolio_analysis')).content.decode()
        self.assertIn('id="pf-phys-map"', page)
        self.assertIn('id="pr-ranking"', page)
        self.assertNotIn('pf-phys-heatmap', page)
        self.assertLess(page.index('js/physical_risk_view.js'), page.index('js/portfolio.js'))
