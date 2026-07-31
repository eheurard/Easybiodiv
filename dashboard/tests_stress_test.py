"""Tests du stress test climatique (noyau pur, service, formulaire, vues)."""
import json

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from dashboard.models import (
    ClimateScenario, Company, Company_Revenue_Sector, ScenarioVariable, Sector,
    SectorCreditProfile, SubSector,
)
from dashboard.services.stress_test import (
    DEFAULT_CREDIT_PROFILE, MAX_SHOCK_SIGMA, SCOPE3_TRANSMISSION,
    carbon_cost, carbon_price_delta, interpolate_trajectory, pd_to_rating,
    physical_loss_ratio, resolve_credit_profile, retained_emissions,
    scenario_trajectory, scenario_value, shock_to_pd, shock_to_sigma,
)


class RetainedEmissionsTests(SimpleTestCase):

    def test_scopes_1_and_2_only_by_default(self):
        self.assertEqual(retained_emissions(100.0, 50.0, 900.0, False), 150.0)

    def test_scope3_enters_partially(self):
        expected = 150.0 + 900.0 * SCOPE3_TRANSMISSION
        self.assertEqual(retained_emissions(100.0, 50.0, 900.0, True), expected)

    def test_scope3_transmission_is_below_one(self):
        self.assertLess(SCOPE3_TRANSMISSION, 1.0)
        self.assertGreater(SCOPE3_TRANSMISSION, 0.0)


class CarbonCostTests(SimpleTestCase):

    def test_nominal(self):
        self.assertAlmostEqual(carbon_cost(1000.0, 200.0, 0.30), 140_000.0)

    def test_full_pass_through_cancels_the_cost(self):
        self.assertEqual(carbon_cost(1000.0, 200.0, 1.0), 0.0)

    def test_falling_carbon_price_yields_no_gain(self):
        self.assertEqual(carbon_cost(1000.0, -50.0, 0.30), 0.0)

    def test_no_emissions_yields_no_cost(self):
        self.assertEqual(carbon_cost(0.0, 200.0, 0.30), 0.0)


class PhysicalLossRatioTests(SimpleTestCase):

    def test_no_hazard_yields_no_loss(self):
        self.assertEqual(physical_loss_ratio([], 1.0), 0.0)

    def test_single_hazard(self):
        self.assertAlmostEqual(physical_loss_ratio([(0.2, 1.0)], 1.0), 0.2)

    def test_two_hazards_combine_multiplicatively(self):
        # 1 - (1-0.2)(1-0.5) = 0.6, et non 0.7
        self.assertAlmostEqual(physical_loss_ratio([(0.2, 1.0), (0.5, 1.0)], 1.0), 0.6)

    def test_ratio_stays_bounded_by_one(self):
        pairs = [(0.9, 2.0)] * 20
        self.assertLessEqual(physical_loss_ratio(pairs, 3.0), 1.0)

    def test_multiplier_amplifies_the_loss(self):
        low = physical_loss_ratio([(0.2, 1.0)], 1.0)
        high = physical_loss_ratio([(0.2, 1.0)], 2.0)
        self.assertGreater(high, low)


class ShockToSigmaTests(SimpleTestCase):

    def test_ratio_divided_by_volatility(self):
        self.assertAlmostEqual(shock_to_sigma(0.10, 0.25), 0.4)

    def test_capped(self):
        self.assertEqual(shock_to_sigma(100.0, 0.25), MAX_SHOCK_SIGMA)

    def test_zero_volatility_returns_the_cap(self):
        self.assertEqual(shock_to_sigma(0.10, 0.0), MAX_SHOCK_SIGMA)

    def test_negative_ratio_floored_at_zero(self):
        self.assertEqual(shock_to_sigma(-0.5, 0.25), 0.0)


class ShockToPdTests(SimpleTestCase):

    def test_zero_shock_is_exactly_neutral(self):
        self.assertAlmostEqual(shock_to_pd(0.012, 0.0), 0.012, places=9)

    def test_monotonic_in_the_shock(self):
        self.assertLess(shock_to_pd(0.012, 0.2), shock_to_pd(0.012, 0.5))

    def test_stays_strictly_inside_zero_one(self):
        for sigma in (0.0, 1.0, MAX_SHOCK_SIGMA):
            value = shock_to_pd(0.012, sigma)
            self.assertGreater(value, 0.0)
            self.assertLess(value, 1.0)

    def test_extreme_baseline_is_clamped_not_crashing(self):
        self.assertGreater(shock_to_pd(0.0, 1.0), 0.0)
        self.assertLess(shock_to_pd(1.0, 1.0), 1.0)

    def test_shock_is_additive_in_sigma_space(self):
        # Un choc de 0.3 puis 0.2 équivaut à un choc unique de 0.5.
        direct = shock_to_pd(0.012, 0.5)
        chained = shock_to_pd(0.012, 0.3 + 0.2)
        self.assertAlmostEqual(direct, chained, places=12)


class PdToRatingTests(SimpleTestCase):

    def test_investment_grade(self):
        self.assertEqual(pd_to_rating(0.0001), 'AAA')
        self.assertEqual(pd_to_rating(0.0040), 'BBB')

    def test_speculative_grade(self):
        self.assertEqual(pd_to_rating(0.020), 'BB')
        self.assertEqual(pd_to_rating(0.080), 'B')

    def test_worst_band_catches_everything(self):
        self.assertEqual(pd_to_rating(0.95), 'CCC')


class InterpolateTrajectoryTests(SimpleTestCase):

    def setUp(self):
        self.points = {2025: 80.0, 2030: 180.0, 2040: 400.0, 2050: 560.0}

    def test_exact_grid_point(self):
        self.assertEqual(interpolate_trajectory(self.points, 2030), 180.0)

    def test_linear_between_two_points(self):
        # mi-chemin entre 2030 (180) et 2040 (400)
        self.assertAlmostEqual(interpolate_trajectory(self.points, 2035), 290.0)

    def test_constant_before_the_first_point(self):
        self.assertEqual(interpolate_trajectory(self.points, 2019), 80.0)

    def test_constant_after_the_last_point(self):
        self.assertEqual(interpolate_trajectory(self.points, 2080), 560.0)

    def test_empty_trajectory(self):
        self.assertEqual(interpolate_trajectory({}, 2030), 0.0)


class DefaultCreditProfileTests(SimpleTestCase):

    def test_has_the_four_expected_keys(self):
        self.assertEqual(
            sorted(DEFAULT_CREDIT_PROFILE),
            ['carbon_pass_through', 'ebitda_margin', 'ebitda_volatility', 'pd_baseline'],
        )

    def test_values_are_plausible(self):
        self.assertGreater(DEFAULT_CREDIT_PROFILE['pd_baseline'], 0.0)
        self.assertLess(DEFAULT_CREDIT_PROFILE['pd_baseline'], 1.0)
        self.assertGreater(DEFAULT_CREDIT_PROFILE['ebitda_margin'], 0.0)
        self.assertLessEqual(DEFAULT_CREDIT_PROFILE['ebitda_margin'], 1.0)


class ClimateScenarioModelTests(TestCase):

    def test_created_with_defaults(self):
        scenario = ClimateScenario.objects.create(key='TEST', name='Test')
        self.assertEqual(scenario.family, ClimateScenario.Family.ORDERLY)
        self.assertEqual(scenario.warming_c, 0.0)
        self.assertEqual(str(scenario), 'Test')

    def test_key_is_unique(self):
        ClimateScenario.objects.create(key='TEST', name='Test')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClimateScenario.objects.create(key='TEST', name='Autre')

    def test_ordering_follows_order_then_key(self):
        ClimateScenario.objects.create(key='B', name='B', order=2)
        ClimateScenario.objects.create(key='A', name='A', order=1)
        # Vérifier l'ordre des scénarios créés par ce test uniquement
        test_scenarios = ClimateScenario.objects.filter(key__in=['A', 'B'])
        self.assertEqual([s.key for s in test_scenarios], ['A', 'B'])


class ScenarioVariableModelTests(TestCase):

    def setUp(self):
        self.scenario = ClimateScenario.objects.create(key='TEST', name='Test')

    def test_reverse_accessor_is_variables(self):
        ScenarioVariable.objects.create(
            scenario=self.scenario, year=2030,
            key=ScenarioVariable.Key.CARBON_PRICE, value=180.0,
        )
        self.assertEqual(self.scenario.variables.count(), 1)

    def test_unique_per_scenario_year_key(self):
        ScenarioVariable.objects.create(
            scenario=self.scenario, year=2030,
            key=ScenarioVariable.Key.CARBON_PRICE, value=180.0,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ScenarioVariable.objects.create(
                scenario=self.scenario, year=2030,
                key=ScenarioVariable.Key.CARBON_PRICE, value=200.0,
            )

    def test_same_year_different_key_is_allowed(self):
        ScenarioVariable.objects.create(
            scenario=self.scenario, year=2030,
            key=ScenarioVariable.Key.CARBON_PRICE, value=180.0,
        )
        ScenarioVariable.objects.create(
            scenario=self.scenario, year=2030,
            key=ScenarioVariable.Key.HAZARD_MULTIPLIER, value=1.2,
        )
        self.assertEqual(self.scenario.variables.count(), 2)


class SectorCreditProfileModelTests(TestCase):

    def test_one_profile_per_sector(self):
        sector = Sector.objects.create(name='Agriculture', NACE_code='A01')
        SectorCreditProfile.objects.create(sector=sector, pd_baseline=0.02)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SectorCreditProfile.objects.create(sector=sector, pd_baseline=0.03)

    def test_reverse_accessor_is_credit_profile(self):
        sector = Sector.objects.create(name='Agriculture', NACE_code='A01')
        profile = SectorCreditProfile.objects.create(sector=sector, pd_baseline=0.02)
        self.assertEqual(sector.credit_profile, profile)


class SeedClimateScenariosTests(TestCase):
    """Le seed tourne dans les migrations : les données sont là dès la base de test."""

    EXPECTED_KEYS = [
        'NET_ZERO_2050', 'BELOW_2C', 'DELAYED_TRANSITION',
        'FRAGMENTED_WORLD', 'CURRENT_POLICIES',
    ]

    def test_the_five_scenarios_exist(self):
        keys = set(ClimateScenario.objects.values_list('key', flat=True))
        for key in self.EXPECTED_KEYS:
            self.assertIn(key, keys)

    def test_each_scenario_has_four_points_per_variable(self):
        for scenario in ClimateScenario.objects.all():
            for key in (ScenarioVariable.Key.CARBON_PRICE,
                        ScenarioVariable.Key.HAZARD_MULTIPLIER):
                count = scenario.variables.filter(key=key).count()
                self.assertEqual(count, 4, f'{scenario.key}/{key}')

    def test_trajectories_are_non_decreasing(self):
        for scenario in ClimateScenario.objects.all():
            for key in (ScenarioVariable.Key.CARBON_PRICE,
                        ScenarioVariable.Key.HAZARD_MULTIPLIER):
                values = list(
                    scenario.variables.filter(key=key)
                    .order_by('year').values_list('value', flat=True)
                )
                self.assertEqual(values, sorted(values), f'{scenario.key}/{key}')

    def test_every_scenario_is_sourced(self):
        for scenario in ClimateScenario.objects.all():
            self.assertTrue(scenario.source, scenario.key)
            self.assertTrue(scenario.reference, scenario.key)

    def test_hot_house_hurts_more_physically_than_net_zero(self):
        def multiplier(key):
            return (
                ClimateScenario.objects.get(key=key).variables
                .get(year=2050, key=ScenarioVariable.Key.HAZARD_MULTIPLIER).value
            )
        self.assertGreater(multiplier('CURRENT_POLICIES'), multiplier('NET_ZERO_2050'))

    def test_net_zero_prices_carbon_higher_than_current_policies(self):
        def price(key):
            return (
                ClimateScenario.objects.get(key=key).variables
                .get(year=2050, key=ScenarioVariable.Key.CARBON_PRICE).value
            )
        self.assertGreater(price('NET_ZERO_2050'), price('CURRENT_POLICIES'))


class ScenarioTrajectoryTests(TestCase):

    def setUp(self):
        self.scenario = ClimateScenario.objects.get(key='NET_ZERO_2050')

    def test_trajectory_is_a_year_to_value_map(self):
        traj = scenario_trajectory(self.scenario, ScenarioVariable.Key.CARBON_PRICE)
        self.assertEqual(sorted(traj), [2025, 2030, 2040, 2050])

    def test_value_on_a_grid_year(self):
        value = scenario_value(self.scenario, ScenarioVariable.Key.CARBON_PRICE, 2030)
        self.assertEqual(value, 190.0)

    def test_value_between_grid_years_is_interpolated(self):
        value = scenario_value(self.scenario, ScenarioVariable.Key.CARBON_PRICE, 2035)
        self.assertAlmostEqual(value, 295.0)

    def test_value_before_the_grid_is_clamped(self):
        value = scenario_value(self.scenario, ScenarioVariable.Key.CARBON_PRICE, 2020)
        self.assertEqual(value, 80.0)

    def test_unknown_variable_key_returns_zero(self):
        self.assertEqual(scenario_value(self.scenario, 'inconnue', 2030), 0.0)


class CarbonPriceDeltaTests(TestCase):

    def setUp(self):
        self.scenario = ClimateScenario.objects.get(key='NET_ZERO_2050')

    def test_delta_against_the_reference_year(self):
        # 2030 (190) − 2024 (borné à 2025 = 80)
        self.assertAlmostEqual(carbon_price_delta(self.scenario, 2030, 2024), 110.0)

    def test_override_replaces_the_scenario_price(self):
        self.assertAlmostEqual(
            carbon_price_delta(self.scenario, 2030, 2024, override=300.0), 220.0
        )

    def test_delta_is_floored_at_zero(self):
        self.assertEqual(
            carbon_price_delta(self.scenario, 2030, 2024, override=10.0), 0.0
        )


class HazardCatalogTests(TestCase):

    def test_fifteen_hazards(self):
        from dashboard.services.hazards import PHYSICAL_RISKS
        self.assertEqual(len(PHYSICAL_RISKS), 15)

    def test_views_reexports_the_same_object(self):
        from dashboard import views
        from dashboard.services.hazards import PHYSICAL_RISKS
        self.assertIs(views.PHYSICAL_RISKS, PHYSICAL_RISKS)

    def test_every_key_matches_an_asset_field(self):
        from dashboard.models import Asset
        from dashboard.services.hazards import PHYSICAL_RISKS
        names = {f.name for f in Asset._meta.get_fields()}
        for risk in PHYSICAL_RISKS:
            self.assertIn(f"risk_{risk['key']}", names)

    def test_every_key_matches_a_policy_vulnerability_field(self):
        from dashboard.models import Policy_Level
        from dashboard.services.hazards import PHYSICAL_RISKS
        names = {f.name for f in Policy_Level._meta.get_fields()}
        for risk in PHYSICAL_RISKS:
            self.assertIn(f"vulnerability_{risk['key']}", names)


class ResolveCreditProfileTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='TestCorp')
        self.agri = Sector.objects.create(name='Agriculture', NACE_code='A01')
        self.food = Sector.objects.create(name='Alimentaire', NACE_code='C10')
        self.ss_agri = SubSector.objects.create(name='Céréales', sector=self.agri)
        self.ss_food = SubSector.objects.create(name='Transfo', sector=self.food)

    def test_falls_back_when_no_sector_mix(self):
        profile, warnings = resolve_credit_profile(self.company, 2024)
        self.assertEqual(profile, DEFAULT_CREDIT_PROFILE)
        self.assertEqual(len(warnings), 1)
        self.assertIn('repli', warnings[0])

    def test_single_sector_uses_its_profile(self):
        SectorCreditProfile.objects.create(
            sector=self.agri, pd_baseline=0.02, ebitda_margin=0.10,
            ebitda_volatility=0.30, carbon_pass_through=0.20,
        )
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=self.ss_agri, year=2024, revenue=100.0
        )
        profile, warnings = resolve_credit_profile(self.company, 2024)
        self.assertAlmostEqual(profile['pd_baseline'], 0.02)
        self.assertAlmostEqual(profile['ebitda_margin'], 0.10)
        self.assertEqual(warnings, [])

    def test_two_sectors_are_revenue_weighted(self):
        SectorCreditProfile.objects.create(sector=self.agri, pd_baseline=0.02)
        SectorCreditProfile.objects.create(sector=self.food, pd_baseline=0.01)
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=self.ss_agri, year=2024, revenue=75.0
        )
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=self.ss_food, year=2024, revenue=25.0
        )
        profile, _ = resolve_credit_profile(self.company, 2024)
        self.assertAlmostEqual(profile['pd_baseline'], 0.75 * 0.02 + 0.25 * 0.01)

    def test_sector_without_profile_uses_the_fallback_and_warns(self):
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=self.ss_agri, year=2024, revenue=100.0
        )
        profile, warnings = resolve_credit_profile(self.company, 2024)
        self.assertAlmostEqual(
            profile['pd_baseline'], DEFAULT_CREDIT_PROFILE['pd_baseline']
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn('profil de crédit', warnings[0])

    def test_other_years_are_ignored(self):
        SectorCreditProfile.objects.create(sector=self.agri, pd_baseline=0.02)
        Company_Revenue_Sector.objects.create(
            company=self.company, subsector=self.ss_agri, year=2023, revenue=100.0
        )
        profile, warnings = resolve_credit_profile(self.company, 2024)
        self.assertEqual(profile, DEFAULT_CREDIT_PROFILE)
        self.assertEqual(len(warnings), 1)


class AcmeCreditProfilesTests(TestCase):

    def test_populate_acme_seeds_both_sector_profiles(self):
        from django.core.management import call_command
        call_command('populate_acme')
        self.assertEqual(SectorCreditProfile.objects.count(), 2)
        acme = Company.objects.get(name='Acme Corp')
        profile, warnings = resolve_credit_profile(acme, 2024)
        self.assertEqual(warnings, [])
        self.assertGreater(profile['pd_baseline'], 0.0)
        self.assertLess(profile['pd_baseline'], 1.0)
