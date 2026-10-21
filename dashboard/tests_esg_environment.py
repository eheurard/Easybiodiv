"""Onglets environnementaux de la page ESG : pollution, utilisation des
ressources, espèces exotiques envahissantes (services/esg_environment.py)."""
from django.test import TestCase
from django.urls import reverse

from dashboard.models import (
    Asset, CharacterizationFactor, Commodity, Company, Country, ImpactCategory, Ownership,
)
from dashboard.services import esg_environment
from dashboard.testing import (
    make_declared_consumption, make_inventory, make_production, make_supply,
)

EUTRO = 'impact_midpoint_ReCiPe2016_freshwater_eutrophication'
OZONE = 'impact_midpoint_ReCiPe2016_ozonedepletion'
FOSSIL = 'impact_midpoint_ReCiPe2016_resource_depletion_fossil'
MINERALS = 'impact_midpoint_ReCiPe2016_resource_depletion_minerals'


class EnvironmentTestMixin:
    def setUp(self):
        self.company = Company.objects.create(name='EnvCorp')
        self.france = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private')
        self.brazil = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private')
        self.soja = Commodity.objects.create(name='Soja', biodiversity_loss_class='Agriculture')
        self.cuivre = Commodity.objects.create(name='Cuivre', biodiversity_loss_class='Mining')

    def asset(self, name, country=None, share=1, **fields):
        asset = Asset.objects.create(
            name=name, latitude=0, longitude=0, country=country or self.france, **fields)
        Ownership.objects.create(asset=asset, company=self.company, share=share)
        return asset

    def cf(self, commodity, key, value):
        CharacterizationFactor.objects.create(
            commodity=commodity, category=ImpactCategory.objects.get(key=key), value=value)


class PollutionTests(EnvironmentTestMixin, TestCase):
    def indicator(self, data, key):
        return next(i for m in data['media'] for i in m['indicators'] if i['key'] == key)

    def test_pression_par_actif_et_par_commodite(self):
        usine = self.asset('Usine')
        ferme = self.asset('Ferme', share=0.3)
        make_production(asset=usine, commodity=self.soja, year=2024, production=10.0)
        make_production(asset=usine, commodity=self.cuivre, year=2024, production=2.0)
        make_production(asset=ferme, commodity=self.soja, year=2023, production=100.0)
        self.cf(self.soja, EUTRO, 0.5)
        self.cf(self.cuivre, EUTRO, 4.0)

        data = esg_environment.get_pollution(self.company)
        eutro = self.indicator(data, EUTRO)
        # Pas de pondération par la part de détention : Ferme = 100 × 0,5.
        self.assertEqual([(r['name'], r['value'], r['year']) for r in eutro['assets']],
                         [('Ferme', 50.0, 2023), ('Usine', 13.0, 2024)])
        self.assertEqual(eutro['total'], 63.0)
        self.assertEqual({r['name']: r['value'] for r in eutro['commodities']},
                         {'Soja': 55.0, 'Cuivre': 8.0})
        self.assertEqual(eutro['unit'], 'kg P eq')

    def test_milieux_et_indicateur_sans_facteur(self):
        usine = self.asset('Usine')
        make_production(asset=usine, commodity=self.soja, year=2024, production=10.0)
        data = esg_environment.get_pollution(self.company)
        self.assertEqual([m['key'] for m in data['media']], ['air', 'water', 'soil'])
        ozone = self.indicator(data, OZONE)
        self.assertIsNone(ozone['total'])
        self.assertEqual(ozone['assets'], [])

    def test_petites_valeurs_gardees_en_chiffres_significatifs(self):
        usine = self.asset('Usine')
        make_production(asset=usine, commodity=self.soja, year=2024, production=3.0)
        self.cf(self.soja, OZONE, 1.234567e-6)
        ozone = self.indicator(esg_environment.get_pollution(self.company), OZONE)
        self.assertEqual(ozone['total'], 3.704e-6)

    def test_entreprise_sans_actif(self):
        data = esg_environment.get_pollution(Company.objects.create(name='Vide'))
        self.assertEqual(data['asset_count'], 0)
        self.assertTrue(all(i['total'] is None
                            for m in data['media'] for i in m['indicators']))


class ResourceUseTests(EnvironmentTestMixin, TestCase):
    def test_inventaire_chaque_cle_a_sa_derniere_annee(self):
        usine = self.asset('Usine')
        make_inventory(asset=usine, key='water', year=2024, value=1000.0)
        make_inventory(asset=usine, key='water', year=2023, value=900.0)
        make_inventory(asset=usine, key='waste', year=2023, value=12.0)
        data = esg_environment.get_resource_use(self.company)
        row = data['assets'][0]
        self.assertEqual(row['water'], {'value': 1000.0, 'year': 2024})
        # Le déchet mesuré un an plus tôt que l'eau reste affiché.
        self.assertEqual(row['waste'], {'value': 12.0, 'year': 2023})
        self.assertIsNone(row['energy'])
        totals = {i['key']: i['total'] for i in data['inventory']}
        self.assertEqual(totals, {'water': 1000.0, 'energy': None, 'waste': 12.0})

    def test_consommation_declaree_au_niveau_du_groupe(self):
        self.asset('Usine')
        make_declared_consumption(company=self.company, key='energy', year=2024, value=5.0e4)
        inventory = {i['key']: i for i in
                     esg_environment.get_resource_use(self.company)['inventory']}
        self.assertEqual(inventory['energy']['declared_group'], {'value': 5.0e4, 'year': 2024})
        self.assertIsNone(inventory['energy']['total'])
        self.assertIsNone(inventory['waste']['declared_group'])
        self.assertEqual(inventory['energy']['unit'], 'MWh')

    def test_rarefaction_modelisee(self):
        mine = self.asset('Mine')
        make_production(asset=mine, commodity=self.cuivre, year=2024, production=10.0)
        self.cf(self.cuivre, MINERALS, 2.0)
        data = esg_environment.get_resource_use(self.company)
        scarcity = {s['key']: s for s in data['scarcity']}
        self.assertEqual(scarcity[MINERALS]['total'], 20.0)
        self.assertEqual(scarcity[MINERALS]['unit'], 'kg Cu eq')
        # Aucun facteur fossile : pas de zéro trompeur.
        self.assertIsNone(scarcity[FOSSIL]['total'])
        self.assertEqual(data['assets'][0]['scarcity_year'], 2024)


class InvasiveSpeciesTests(EnvironmentTestMixin, TestCase):
    def rows(self):
        data = esg_environment.get_invasive_species(self.company)
        return data, {r['name']: r for r in data['assets']}

    def test_voies_d_introduction_et_niveaux(self):
        ferme = self.asset('Ferme')
        make_production(asset=ferme, commodity=self.soja, year=2024, production=1.0)
        usine = self.asset('Usine')
        fournisseur = Asset.objects.create(
            name='Fournisseur', latitude=0, longitude=0, country=self.brazil)
        make_supply(what=self.soja, year=2024, quantity=1.0,
                    origin=fournisseur, destination=usine)
        make_production(asset=usine, commodity=self.soja, year=2024, production=1.0)
        self.asset('Bureau')

        data, rows = self.rows()
        self.assertEqual(rows['Ferme']['activity'], 'cultivation')
        self.assertFalse(rows['Ferme']['trade'])
        self.assertEqual(rows['Ferme']['level'], 'moderate')
        self.assertEqual(rows['Usine']['trade_origins'], ['Brésil'])
        self.assertEqual(rows['Usine']['level'], 'high')
        self.assertEqual(rows['Bureau']['level'], 'low')
        # Tri : exposition décroissante, puis nom.
        self.assertEqual([r['name'] for r in data['assets']], ['Usine', 'Ferme', 'Bureau'])
        self.assertEqual(data['counts'], {
            'screened': 3, 'high': 1, 'with_pathway': 2, 'sensitive': 0,
        })

    def test_zone_sensible_releve_d_un_niveau_sans_creer_d_exposition(self):
        self.asset('Mine', type='Mine', near_sensitive_zone=True,
                   sensitive_zone_type=Asset.SensitiveZoneType.NATURA_2000)
        self.asset('Bureau', near_sensitive_zone=True)
        _data, rows = self.rows()
        self.assertEqual(rows['Mine']['activity'], 'disturbance')
        self.assertEqual(rows['Mine']['level'], 'high')
        self.assertEqual(rows['Mine']['sensitive_label'], 'Natura 2000')
        self.assertEqual(rows['Bureau']['level'], 'low')

    def test_approvisionnement_du_meme_pays_et_aeroport(self):
        usine = self.asset('Usine')
        voisin = Asset.objects.create(name='Voisin', latitude=0, longitude=0, country=self.france)
        make_supply(what=self.cuivre, year=2024, quantity=1.0, origin=voisin, destination=usine)
        self.asset('Aéroport', type='Airport')
        _data, rows = self.rows()
        self.assertFalse(rows['Usine']['trade'])
        self.assertTrue(rows['Aéroport']['trade'])
        self.assertEqual(rows['Aéroport']['trade_origins'], [])


class EsgEnvironmentPageTests(TestCase):
    def test_panneaux_rendus_sans_placeholder(self):
        response = self.client.get(reverse('dashboard:esg'))
        for element_id in ('esg-pollution-media', 'esg-resource-kpis', 'esg-ias-rows'):
            self.assertContains(response, f'id="{element_id}"')
        for placeholder in ('Pollution — à venir', 'Resource use — à venir',
                            'Invasive species — à venir'):
            self.assertNotContains(response, placeholder)

    def test_api_expose_les_trois_onglets(self):
        company = Company.objects.create(name='ApiCorp')
        data = self.client.get(reverse('dashboard:esg_data', kwargs={'pk': company.pk})).json()
        for key in ('pollution', 'resource_use', 'invasive_species'):
            self.assertIn(key, data)

    def test_libelles_traduits_en_anglais(self):
        company = Company.objects.create(name='ApiCorp')
        self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        data = self.client.get(reverse('dashboard:esg_data', kwargs={'pk': company.pk})).json()
        self.assertEqual([m['name'] for m in data['pollution']['media']], ['Air', 'Water', 'Soil'])
        response = self.client.get(reverse('dashboard:esg'))
        self.assertContains(response, 'Invasive alien species')
