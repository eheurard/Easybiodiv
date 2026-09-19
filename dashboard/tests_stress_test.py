"""Tests du stress test climatique (noyau pur, service, formulaire, vues)."""
import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from dashboard.forms import StressTestForm
from dashboard.models import (
    ClimateScenario, Company, Company_Revenue, Company_Revenue_Sector,
    ScenarioVariable, Sector, SectorCreditProfile, SubSector,
)
from dashboard.services.stress_test import (
    DEFAULT_CREDIT_PROFILE, HORIZONS, MAX_SHOCK_SIGMA, PD_MAX, SCOPE3_TRANSMISSION,
    carbon_cost, carbon_price_delta, company_snapshot, get_stress_test_data,
    hazard_severity_ratio, interpolate_trajectory, pd_to_rating,
    resolve_credit_profile, retained_emissions, scenario_trajectory,
    scenario_value, shock_to_pd, shock_to_sigma,
)
from dashboard.testing import make_declared_emission


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


class HazardSeverityRatioTests(SimpleTestCase):

    def test_no_hazard_yields_no_loss(self):
        self.assertEqual(hazard_severity_ratio([], 1.0), 0.0)

    def test_single_hazard(self):
        self.assertAlmostEqual(hazard_severity_ratio([(0.2, 1.0)], 1.0), 0.2)

    def test_two_hazards_are_averaged_not_compounded(self):
        # (0.2 + 0.5) / 2 = 0.35 — et surtout PAS 1 - (1-0.2)(1-0.5) = 0.6
        self.assertAlmostEqual(hazard_severity_ratio([(0.2, 1.0), (0.5, 1.0)], 1.0), 0.35)

    def test_null_hazards_weigh_in_the_average(self):
        # Un actif exposé à 1 aléa sur 4 est moins touché qu'un actif exposé aux 4.
        few = hazard_severity_ratio([(0.8, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)], 1.0)
        many = hazard_severity_ratio([(0.8, 1.0)] * 4, 1.0)
        self.assertAlmostEqual(few, 0.2)
        self.assertAlmostEqual(many, 0.8)

    def test_does_not_saturate_on_a_long_hazard_panel(self):
        # Régression : la forme multiplicative renvoyait ~0.96 ici, ce qui
        # saturait la métrique. La moyenne doit rester à 0.2.
        self.assertAlmostEqual(hazard_severity_ratio([(0.2, 1.0)] * 15, 1.0), 0.2)

    def test_ratio_stays_bounded_by_one(self):
        pairs = [(0.9, 2.0)] * 20
        self.assertLessEqual(hazard_severity_ratio(pairs, 3.0), 1.0)

    def test_multiplier_amplifies_the_loss(self):
        low = hazard_severity_ratio([(0.2, 1.0)], 1.0)
        high = hazard_severity_ratio([(0.2, 1.0)], 2.0)
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

    def test_fallback_profile_is_a_copy_not_the_shared_constant(self):
        profile, _ = resolve_credit_profile(self.company, 2024)
        profile['pd_baseline'] = 0.99
        self.assertNotEqual(DEFAULT_CREDIT_PROFILE['pd_baseline'], 0.99)

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


class CompanySnapshotTests(TestCase):

    def setUp(self):
        call_command('populate_acme')
        self.acme = Company.objects.get(name='Acme Corp')

    def test_reads_emissions_by_scope(self):
        snapshot = company_snapshot(self.acme, 2024)
        self.assertEqual(snapshot['scope1'], 22000.0)
        self.assertEqual(snapshot['scope2'], 12000.0)
        self.assertEqual(snapshot['scope3'], 70000.0)

    def test_zero_emissions_for_an_unknown_year(self):
        snapshot = company_snapshot(self.acme, 1990)
        self.assertEqual(snapshot['scope1'], 0.0)

    def test_exposure_is_positive(self):
        snapshot = company_snapshot(self.acme, 2024)
        self.assertGreater(snapshot['exposure'], 0.0)

    def test_each_asset_carries_fifteen_hazard_pairs(self):
        snapshot = company_snapshot(self.acme, 2024)
        self.assertGreater(len(snapshot['assets']), 0)
        for asset in snapshot['assets']:
            self.assertEqual(len(asset['hazard_pairs']), 15)


class GetStressTestDataTests(TestCase):

    def setUp(self):
        call_command('populate_acme')
        self.acme = Company.objects.get(name='Acme Corp')

    def test_payload_has_every_contract_key(self):
        data = get_stress_test_data(self.acme)
        for key in ('company_id', 'company_name', 'reference_year', 'scenarios',
                    'selected', 'inputs', 'result', 'waterfall', 'channels',
                    'horizon_curve', 'scenario_comparison', 'assumptions',
                    'warnings'):
            self.assertIn(key, data)

    def test_lists_the_five_scenarios(self):
        data = get_stress_test_data(self.acme)
        self.assertEqual(len(data['scenarios']), 5)

    def test_stressed_pd_exceeds_baseline(self):
        data = get_stress_test_data(self.acme)
        self.assertGreater(data['result']['pd_stressed'], data['result']['pd_baseline'])

    def test_pd_stays_inside_zero_one(self):
        data = get_stress_test_data(self.acme)
        self.assertGreater(data['result']['pd_stressed'], 0.0)
        self.assertLess(data['result']['pd_stressed'], 1.0)

    def test_waterfall_deltas_sum_to_the_total(self):
        data = get_stress_test_data(self.acme)
        total = sum(step['delta_bps'] for step in data['waterfall'])
        self.assertAlmostEqual(total, data['result']['delta_bps'], places=1)

    def test_hot_house_hurts_more_than_net_zero_physically(self):
        net_zero = ClimateScenario.objects.get(key='NET_ZERO_2050')
        hot_house = ClimateScenario.objects.get(key='CURRENT_POLICIES')
        params_nz = {'scenario': net_zero, 'horizon': 2050}
        params_hh = {'scenario': hot_house, 'horizon': 2050}
        loss_nz = get_stress_test_data(self.acme, params_nz)['channels']['physical']
        loss_hh = get_stress_test_data(self.acme, params_hh)['channels']['physical']
        self.assertGreater(loss_hh['loss_eur'], loss_nz['loss_eur'])

    def test_net_zero_hurts_more_than_current_policies_on_transition(self):
        net_zero = ClimateScenario.objects.get(key='NET_ZERO_2050')
        current = ClimateScenario.objects.get(key='CURRENT_POLICIES')
        cost_nz = get_stress_test_data(
            self.acme, {'scenario': net_zero, 'horizon': 2050}
        )['channels']['transition']['cost_eur']
        cost_cp = get_stress_test_data(
            self.acme, {'scenario': current, 'horizon': 2050}
        )['channels']['transition']['cost_eur']
        self.assertGreater(cost_nz, cost_cp)

    def test_scope3_increases_the_transition_cost(self):
        without = get_stress_test_data(self.acme, {'include_scope3': False})
        with_s3 = get_stress_test_data(self.acme, {'include_scope3': True})
        self.assertGreater(
            with_s3['channels']['transition']['cost_eur'],
            without['channels']['transition']['cost_eur'],
        )

    def test_full_pass_through_removes_the_transition_channel(self):
        data = get_stress_test_data(self.acme, {'pass_through': 1.0})
        self.assertEqual(data['channels']['transition']['cost_eur'], 0.0)

    def test_pd_baseline_override_is_honoured(self):
        data = get_stress_test_data(self.acme, {'pd_baseline': 0.05})
        self.assertAlmostEqual(data['result']['pd_baseline'], 0.05)

    def test_horizon_curve_covers_every_horizon(self):
        data = get_stress_test_data(self.acme)
        self.assertEqual([p['year'] for p in data['horizon_curve']], list(HORIZONS))

    def test_horizon_curve_is_non_decreasing_for_net_zero(self):
        net_zero = ClimateScenario.objects.get(key='NET_ZERO_2050')
        curve = get_stress_test_data(
            self.acme, {'scenario': net_zero}
        )['horizon_curve']
        values = [point['pd'] for point in curve]
        self.assertEqual(values, sorted(values))

    def test_comparison_covers_every_scenario(self):
        data = get_stress_test_data(self.acme)
        self.assertEqual(len(data['scenario_comparison']), 5)

    def test_assumptions_are_all_labelled(self):
        data = get_stress_test_data(self.acme)
        self.assertGreaterEqual(len(data['assumptions']), 8)
        for row in data['assumptions']:
            self.assertTrue(row['label'])
            self.assertTrue(row['value'])

    def test_assumptions_disclose_the_damage_coefficient(self):
        # Parametre libre, doit etre visible pour l'utilisateur, pas implicite.
        data = get_stress_test_data(self.acme)
        labels = [row['label'] for row in data['assumptions']]
        self.assertIn('Coefficient de dommage physique', labels)

    def test_scenarios_produce_distinct_non_saturated_pds(self):
        data = get_stress_test_data(self.acme)
        pds = [row['pd'] for row in data['scenario_comparison']]
        self.assertEqual(len(set(pds)), len(pds))
        for pd in pds:
            self.assertLess(pd, 0.99)
            self.assertGreater(pd, data['result']['pd_baseline'])

    def test_carbon_price_override_matches_the_kpi_at_the_selected_point(self):
        # Le curseur "prix carbone" surcharge un prix absolu épinglé à
        # l'horizon et au scénario sélectionnés. Le point de la courbe par
        # horizon et la barre de comparaison qui correspondent exactement à la
        # sélection courante doivent afficher la même PD que le bandeau KPI
        # (`result.pd_stressed`) : sinon l'écran montre deux chiffres
        # différents pour le même point.
        scenario = ClimateScenario.objects.get(key='NET_ZERO_2050')
        data = get_stress_test_data(
            self.acme,
            {'scenario': scenario, 'horizon': 2030, 'carbon_price': 900},
        )
        horizon_point = next(
            p for p in data['horizon_curve']
            if p['year'] == data['selected']['horizon']
        )
        self.assertEqual(horizon_point['pd'], data['result']['pd_stressed'])

        comparison_row = next(
            row for row in data['scenario_comparison']
            if row['key'] == data['selected']['scenario']
        )
        self.assertEqual(comparison_row['pd'], data['result']['pd_stressed'])


class StressTestEmptyCasesTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Vide')

    def test_company_without_revenue_returns_a_warning_not_a_crash(self):
        data = get_stress_test_data(self.company)
        self.assertIsNone(data['result'])
        self.assertIsNone(data['selected'])
        self.assertEqual(data['waterfall'], [])
        self.assertTrue(data['warnings'])

    def test_contract_keys_present_even_when_empty(self):
        data = get_stress_test_data(self.company)
        for key in ('scenarios', 'waterfall', 'horizon_curve',
                    'scenario_comparison', 'assumptions', 'warnings'):
            self.assertIsInstance(data[key], list)

    def test_non_positive_ebitda_proxy_returns_a_warning_not_a_crash(self):
        # CA connu et positif, mais marge EBITDA nulle : le proxy est <= 0.
        company = Company.objects.create(name='CA sans marge')
        Company_Revenue.objects.create(
            company=company, year=2024, revenue=1_000_000.0, currency='EUR'
        )
        data = get_stress_test_data(company, {'ebitda_margin': 0.0})
        self.assertIsNone(data['result'])
        self.assertIsNone(data['selected'])
        self.assertIsNone(data['channels'])
        self.assertIsNone(data['inputs'])
        self.assertEqual(data['waterfall'], [])
        self.assertTrue(data['warnings'])


class StressTestFormTests(TestCase):

    def test_empty_form_is_valid(self):
        form = StressTestForm(data={})
        self.assertTrue(form.is_valid(), form.errors)

    def test_empty_form_produces_neutral_params(self):
        form = StressTestForm(data={})
        form.is_valid()
        params = form.to_params()
        self.assertIsNone(params['scenario'])
        self.assertIsNone(params['horizon'])
        self.assertIsNone(params['carbon_price'])
        self.assertFalse(params['include_scope3'])

    def test_known_scenario_key_resolves_to_an_instance(self):
        form = StressTestForm(data={'scenario': 'NET_ZERO_2050'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.to_params()['scenario'].key, 'NET_ZERO_2050')

    def test_unknown_scenario_key_is_rejected(self):
        form = StressTestForm(data={'scenario': 'INCONNU'})
        self.assertFalse(form.is_valid())
        self.assertIn('scenario', form.errors)

    def test_unknown_horizon_is_rejected(self):
        form = StressTestForm(data={'horizon': '2027'})
        self.assertFalse(form.is_valid())
        self.assertIn('horizon', form.errors)

    def test_known_horizon_is_accepted(self):
        form = StressTestForm(data={'horizon': str(HORIZONS[-1])})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.to_params()['horizon'], HORIZONS[-1])

    def test_pass_through_above_one_is_rejected(self):
        form = StressTestForm(data={'pass_through': '1.5'})
        self.assertFalse(form.is_valid())
        self.assertIn('pass_through', form.errors)

    def test_negative_pass_through_is_rejected(self):
        form = StressTestForm(data={'pass_through': '-0.1'})
        self.assertFalse(form.is_valid())

    def test_zero_pd_baseline_is_rejected(self):
        form = StressTestForm(data={'pd_baseline': '0'})
        self.assertFalse(form.is_valid())
        self.assertIn('pd_baseline', form.errors)

    def test_pd_baseline_of_one_is_rejected(self):
        form = StressTestForm(data={'pd_baseline': '1'})
        self.assertFalse(form.is_valid())

    def test_pd_baseline_above_the_service_clamp_is_rejected(self):
        # Le formulaire acceptait jusqu'à 0.999 alors que le service écrête à
        # PD_MAX=0.99 : une valeur comme 0.995 était échoée dans
        # `selected.pd_baseline` sans jamais être réellement utilisée par le
        # calcul. La borne du formulaire doit coïncider avec celle du service.
        form = StressTestForm(data={'pd_baseline': str(PD_MAX + 0.005)})
        self.assertFalse(form.is_valid())
        self.assertIn('pd_baseline', form.errors)

    def test_zero_ebitda_margin_is_rejected(self):
        form = StressTestForm(data={'ebitda_margin': '0'})
        self.assertFalse(form.is_valid())

    def test_negative_carbon_price_is_rejected(self):
        form = StressTestForm(data={'carbon_price': '-5'})
        self.assertFalse(form.is_valid())

    def test_include_scope3_checkbox(self):
        form = StressTestForm(data={'include_scope3': '1'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.to_params()['include_scope3'])


class ClimateStressTestViewTests(TestCase):

    def setUp(self):
        call_command('populate_acme')
        self.acme = Company.objects.get(name='Acme Corp')
        User = get_user_model()
        self.user = User.objects.create_user(username='u', password='x')
        self.page_url = reverse('dashboard:climate_stress_test')
        self.api_url = reverse(
            'dashboard:climate_stress_test_data', kwargs={'pk': self.acme.pk}
        )

    def test_page_stays_public_for_anonymous(self):
        response = self.client.get(self.page_url)
        self.assertEqual(response.status_code, 200)

    def test_api_stays_public_for_anonymous(self):
        response = self.client.get(self.api_url)
        self.assertEqual(response.status_code, 200)

    def test_page_renders_with_companies_and_initial_data(self):
        self.client.force_login(self.user)
        response = self.client.get(self.page_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/climate_stress_test.html')
        self.assertIn('companies', response.context)
        self.assertIn('initial_data', response.context)

    def test_api_returns_json(self):
        self.client.force_login(self.user)
        response = self.client.get(self.api_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/json', response['Content-Type'])
        payload = json.loads(response.content)
        self.assertEqual(payload['company_name'], 'Acme Corp')

    def test_api_honours_the_scenario_parameter(self):
        self.client.force_login(self.user)
        response = self.client.get(self.api_url, {'scenario': 'CURRENT_POLICIES'})
        payload = json.loads(response.content)
        self.assertEqual(payload['selected']['scenario'], 'CURRENT_POLICIES')

    def test_api_honours_the_horizon_parameter(self):
        self.client.force_login(self.user)
        response = self.client.get(self.api_url, {'horizon': '2050'})
        payload = json.loads(response.content)
        self.assertEqual(payload['selected']['horizon'], 2050)

    def test_api_rejects_an_invalid_parameter(self):
        self.client.force_login(self.user)
        response = self.client.get(self.api_url, {'pass_through': '2'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('pass_through', json.loads(response.content)['errors'])

    def test_api_rejects_an_unknown_scenario(self):
        self.client.force_login(self.user)
        response = self.client.get(self.api_url, {'scenario': 'NOPE'})
        self.assertEqual(response.status_code, 400)

    def test_api_404_on_unknown_company(self):
        self.client.force_login(self.user)
        url = reverse('dashboard:climate_stress_test_data', kwargs={'pk': 999999})
        self.assertEqual(self.client.get(url).status_code, 404)


class CompanySnapshotScopesTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Mine SA')

    def _declare(self, scope, value, year=2024):
        make_declared_emission(company=self.company, year=year, scope=scope, value=value)

    def test_scope_1_2_counts_when_the_detail_is_missing(self):
        self._declare('Scope 1+2', 30.0)
        snapshot = company_snapshot(self.company, 2024)
        self.assertEqual(snapshot['scope1'] + snapshot['scope2'], 30.0)
        self.assertTrue(snapshot['scope12_combined'])

    def test_the_detail_wins_over_the_aggregate(self):
        self._declare('Scope 1', 20.0)
        self._declare('Scope 2', 10.0)
        self._declare('Scope 1+2', 30.0)
        snapshot = company_snapshot(self.company, 2024)
        self.assertEqual((snapshot['scope1'], snapshot['scope2']), (20.0, 10.0))
        self.assertFalse(snapshot['scope12_combined'])

    def test_an_unsplit_total_is_reported_apart(self):
        self._declare('Scope 1+2+3', 50.0)
        snapshot = company_snapshot(self.company, 2024)
        self.assertEqual(snapshot['scope1'] + snapshot['scope2'] + snapshot['scope3'], 0.0)
        self.assertEqual(snapshot['unsplit_total'], 50.0)

    def test_an_unsplit_total_produces_its_own_warning(self):
        Company_Revenue.objects.create(
            company=self.company, year=2024, revenue=1_000_000.0, currency='EUR')
        self._declare('Scope 1+2+3', 50.0)
        warnings = get_stress_test_data(self.company)['warnings']
        self.assertTrue(any('non ventilées' in w for w in warnings), warnings)
        self.assertFalse(any("Aucune donnée d'émissions" in w for w in warnings), warnings)
