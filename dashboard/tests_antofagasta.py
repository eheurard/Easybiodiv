"""Garde-fous sur les chiffres publiés chargés par `populate_antofagasta`.

Les quantités de la commande viennent des rapports d'Antofagasta plc. Ces tests
rejouent les recoupements qui ont servi à les lire : les totaux par site doivent
retomber sur les totaux groupe publiés. Une faute de frappe dans un chiffre les
casse.
"""
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from .models import Asset, Company, Company_Revenue, Flow, FlowKind
from .services import flows as flow_service


class PopulateAntofagastaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        call_command('populate_antofagasta')
        cls.company = Company.objects.get(name='Antofagasta')
        cls.assets = {a.name: a for a in Asset.objects.owned_by(cls.company)}

    def _water_total(self, year):
        return sum(
            flow.quantity for flow in Flow.objects.filter(
                kind=FlowKind.CONSUMPTION, what__key='water', year=year,
                to_asset__in=[a.pk for a in self.assets.values()],
            )
        )

    def test_four_mines_are_owned_with_their_published_shares(self):
        shares = {
            name: asset.ownerships.get(company=self.company).share
            for name, asset in self.assets.items()
        }
        self.assertEqual(shares, {
            'Los Pelambres mine': Decimal('0.6000'),
            'Centinela mine': Decimal('0.7000'),
            'Antucoya mine': Decimal('0.7000'),
            'Zaldivar mine': Decimal('0.5000'),
        })

    def test_water_withdrawals_match_the_published_division_total(self):
        # SR24 : 81 910 ML en 2023, 102 650 ML en 2024 pour la division minière,
        # toutes origines confondues. Le total 2023 publié arrondit à 1 ML près
        # la somme de ses propres lignes (81 911 ML).
        self.assertAlmostEqual(self._water_total(2023), 81_910_000, delta=1_000)
        self.assertEqual(self._water_total(2024), 102_650_000)

    def test_copper_output_matches_the_published_group_total(self):
        # Les sites sont stockés à 100 %, dont Zaldívar ; le groupe publie sa
        # quote-part de 50 % sur cette seule mine. 704 000 t est aussi le
        # dénominateur de l'intensité 1,75 tCO₂e/tCu publiée pour 2024.
        by_asset = {
            flow.from_asset.name: flow.quantity
            for flow in flow_service.productions([a.pk for a in self.assets.values()])
            if flow.what.name == 'copper' and flow.year == 2024
        }
        self.assertEqual(sum(by_asset.values()), 704_000)
        self.assertEqual(by_asset['Zaldivar mine'], 80_200)
        attributable = sum(by_asset.values()) - by_asset['Zaldivar mine'] / 2
        self.assertAlmostEqual(attributable, 664_000, delta=200)

    def test_site_scope_1_emissions_add_up_to_the_declared_group_scope_1(self):
        # SR24 : les quatre mines plus 185 tCO₂e de bureaux font le Scope 1 de la
        # division minière déclaré pour 2024.
        sites = sum(
            flow.quantity for flow in Flow.objects.filter(
                kind=FlowKind.EMISSION, what__key='co2', year=2024,
                from_asset__in=[a.pk for a in self.assets.values()],
            )
        )
        declared = flow_service.declared_emissions(self.company)[2024]
        self.assertEqual(sites + 185, declared['Scope 1'])
        self.assertEqual(sites + 185 + declared['Scope 2'], 1_229_811)

    def test_2025_emissions_are_kept_as_an_unsplit_scope_1_2(self):
        # Le groupe ne publie pas la ventilation 2025 : resolve_scopes doit
        # rendre le total tel quel, sans le confondre avec un Scope 1.
        self.assertEqual(
            flow_service.declared_emissions(self.company)[2025],
            {'Scope 1+2': 1_319_884.0},
        )

    def test_revenue_follows_the_five_year_summary(self):
        self.assertEqual(
            dict(Company_Revenue.objects.filter(company=self.company)
                 .values_list('year', 'revenue')),
            {2023: 6_324_500_000.0, 2024: 6_613_400_000.0, 2025: 8_620_300_000.0},
        )

    def test_running_twice_does_not_duplicate_flows(self):
        before = Flow.objects.count()
        call_command('populate_antofagasta')
        self.assertEqual(Flow.objects.count(), before)
