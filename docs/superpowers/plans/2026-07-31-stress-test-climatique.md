# Stress test climatique — PD stressée Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une page « Stress test climatique » où l'utilisateur choisit un scénario NGFS, ajuste quelques hypothèses, et obtient la probabilité de défaut stressée de l'entreprise sélectionnée, décomposée par canal (transition / physique).

**Architecture:** Chaîne `scénario NGFS → coût carbone non provisionné + dommages physiques → choc rapporté à un proxy d'EBITDA → décalage latent de type Merton → PD*`. Les scénarios vivent en base (seedés par migration, éditables en admin). Tout le calcul est dans `dashboard/services/stress_test.py`, dont le haut de module est un noyau pur sans ORM. Les vues restent des coquilles, comme les 11 pages existantes. Aucune persistance des exécutions : endpoint GET paramétré, validé par un `forms.Form`.

**Tech Stack:** Django 6.0.5, `statistics.NormalDist` (stdlib) pour Φ et Φ⁻¹, JS vanilla, Chart.js 4.4.4 par CDN (déjà chargé par `leap_prepare.html`), SQLite en dev / PostgreSQL en prod.

**Spec:** `docs/superpowers/specs/2026-07-31-stress-test-climatique-design.md`

## Global Constraints

- Python **3.11+**, PEP 8, lignes **≤ 100 caractères**.
- **Aucune dépendance nouvelle.** `requirements.txt` n'est pas modifié. Les maths viennent de `statistics.NormalDist` (stdlib).
- **Parité SQLite / PostgreSQL** : uniquement `FloatField`, `IntegerField`, `CharField`, `TextField`, `BooleanField`, `FK`, `OneToOne`, `DateTimeField`. Pas de `JSONField`, pas de PostGIS.
- **Pas de framework frontend.** JS vanilla, `defer`. Chart.js par CDN uniquement.
- **Une migration = un changement logique**, nommée explicitement, réversible, et **auto-suffisante** (données figées dans le fichier de migration, jamais d'import d'une constante vivante du code).
- Dernière migration existante : `0041_asset_type` → les nouvelles s'enchaînent à partir de `0042`.
- Toute entrée utilisateur passe par un `forms.Form`. Jamais de lecture brute de `request.GET`.
- URLs namespacées : `dashboard:climate_stress_test`, `dashboard:climate_stress_test_data`.
- Accessibilité : ARIA, navigation clavier, contraste AA.
- Commande de test : `.venv\Scripts\python.exe manage.py test dashboard`
  Un test précis : `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test.NomDeClasse.test_nom`
- **Ne jamais rediriger la sortie des tests vers un fichier du repo.**
- Les tests de cette feature vont dans **`dashboard/tests_stress_test.py`** (nouveau module, découvert par le runner Django via le motif `test*.py`). `dashboard/tests.py` fait déjà 2446 lignes ; on ne l'alourdit pas. Seule exception : la ligne à ajouter dans `GOLDEN_VIEWS` (Task 11).

## File Structure

| Fichier | Responsabilité |
|---|---|
| `dashboard/services/stress_test.py` | **Créé.** Noyau pur (constantes + 7 fonctions sans ORM) puis couche ORM (`get_stress_test_data`). Seul endroit où vit la méthodologie. |
| `dashboard/services/hazards.py` | **Créé.** `PHYSICAL_RISKS` déplacé depuis `views.py` pour être partageable sans import circulaire. |
| `dashboard/forms.py` | **Créé.** `StressTestForm` — validation et bornage des paramètres GET. |
| `dashboard/models.py` | **Modifié.** `ClimateScenario`, `ScenarioVariable`, `SectorCreditProfile` en fin de fichier. |
| `dashboard/migrations/0042_climate_scenario_models.py` | **Créé.** Schéma des 3 modèles. |
| `dashboard/migrations/0043_seed_climate_scenarios.py` | **Créé.** Seed des 5 scénarios NGFS + trajectoires. |
| `dashboard/views.py` | **Modifié.** 2 vues fines ; `PHYSICAL_RISKS` ré-importé depuis `services/hazards.py`. |
| `dashboard/urls.py` | **Modifié.** 2 routes. |
| `dashboard/admin.py` | **Modifié.** 3 enregistrements. |
| `dashboard/templates/dashboard/climate_stress_test.html` | **Créé.** |
| `dashboard/static/dashboard/js/climate_stress_test.js` | **Créé.** |
| `dashboard/static/dashboard/css/style.css` | **Modifié.** Styles de la page en fin de fichier. |
| `templates/base.html` | **Modifié.** Sous-item de navigation. |
| `dashboard/management/commands/populate_acme.py` | **Modifié.** Profils sectoriels de démo. |
| `dashboard/tests_stress_test.py` | **Créé.** Tous les tests de la feature. |
| `dashboard/tests.py` | **Modifié.** Une ligne dans `GOLDEN_VIEWS`. |
| `dashboard/golden/climate_stress_test.json` | **Créé.** Enregistré via `GOLDEN_RECORD=1`. |

**Contrat central** — le payload de `get_stress_test_data(company, params)` :

```python
{
  'company_id': int, 'company_name': str, 'reference_year': int | None,
  'scenarios': [{'key','name','family','family_label','warming_c','narrative'}],
  'selected': {...} | None,
  'inputs': {'emissions': {'scope1','scope2','scope3','retained'},
             'revenue', 'ebitda_proxy', 'exposure', 'asset_count'} | None,
  'result': {...} | None,
  'waterfall': [{'label','pd','delta_bps'}],
  'channels': {'transition': {...}, 'physical': {...}} | None,
  'horizon_curve': [{'year','pd'}],
  'scenario_comparison': [{'key','name','pd','delta_bps'}],
  'assumptions': [{'label','value','source','reference'}],
  'warnings': [str],
}
```

Toutes les clés sont **toujours présentes**. En cas d'impossibilité de calcul, les blocs valent `None` / `[]` et `warnings` explique pourquoi. Le JS n'a donc jamais à tester l'existence d'une clé.

---

### Task 1 : Noyau pur du service

Sept fonctions sans ORM, testables isolément. C'est toute la méthodologie ; le reste du plan ne fait que l'alimenter.

**Files:**
- Create: `dashboard/services/stress_test.py`
- Test: `dashboard/tests_stress_test.py`

**Interfaces:**
- Produces:
  - `SCOPE3_TRANSMISSION: float`, `MAX_SHOCK_SIGMA: float`, `PHYSICAL_DAMAGE_FACTOR: float`, `PD_MIN`, `PD_MAX`, `HORIZONS: tuple[int, ...]`, `DEFAULT_CREDIT_PROFILE: dict[str, float]`, `RATING_BANDS: list[tuple[str, float]]`
  - `retained_emissions(scope1: float, scope2: float, scope3: float, include_scope3: bool) -> float`
  - `carbon_cost(emissions_t: float, delta_price: float, pass_through: float) -> float`
  - `hazard_severity_ratio(hazard_pairs: list[tuple[float, float]], multiplier: float) -> float`
  - `shock_to_sigma(shock_ratio: float, volatility: float) -> float`
  - `shock_to_pd(pd_baseline: float, shock_sigma: float) -> float`
  - `pd_to_rating(pd: float) -> str`
  - `interpolate_trajectory(points: dict[int, float], year: int) -> float`

- [ ] **Step 1 : Écrire les tests du noyau**

Créer `dashboard/tests_stress_test.py` :

```python
"""Tests du stress test climatique (noyau pur, service, formulaire, vues)."""
import json

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from dashboard.services.stress_test import (
    DEFAULT_CREDIT_PROFILE, MAX_SHOCK_SIGMA, SCOPE3_TRANSMISSION,
    carbon_cost, interpolate_trajectory, pd_to_rating, hazard_severity_ratio,
    retained_emissions, shock_to_pd, shock_to_sigma,
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
```

- [ ] **Step 2 : Lancer les tests, vérifier qu'ils échouent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.services.stress_test'`

- [ ] **Step 3 : Écrire le noyau**

Créer `dashboard/services/stress_test.py` :

```python
"""Stress test climatique — probabilité de défaut stressée d'un émetteur.

Chaîne de calcul :

    scénario NGFS
      → coût carbone non provisionné + dommages physiques
      → choc rapporté à un proxy d'EBITDA
      → décalage latent de type Merton
      → PD stressée

Le haut de ce module est un **noyau pur** : aucune requête ORM, aucun import
Django. Il est testable isolément et constitue la seule définition de la
méthodologie. La couche ORM vient plus bas dans le fichier.

Références : NGFS Phase V (scénarios) ; BCE Occasional Paper 281 (2021) ;
ACPR exercice pilote climatique 2020 ; Trucost CEaR et MSCI Climate VaR
(coût carbone non provisionné) ; Merton (1974).
"""
from statistics import NormalDist

_NORM = NormalDist()

# Part du scope 3 amont supportée par l'émetteur via le prix de ses intrants.
# Retenir 100 % ferait payer à l'émetteur toute sa chaîne de valeur, ce qui
# double-compte à l'échelle d'un portefeuille (cf. Trucost CEaR, MSCI CVaR).
SCOPE3_TRANSMISSION = 0.50

# Plafond du choc, en écarts-types. Au-delà, PD* vaut numériquement 1 ; le
# plafond évite qu'un proxy d'EBITDA proche de zéro ne produise un infini.
MAX_SHOCK_SIGMA = 8.0

# Coefficient de dommage : fraction du chiffre d'affaires exposé réellement
# perdue sur un an lorsque la sévérité des aléas vaut 1. Les scores `risk_*`
# sont des indices de sévérité relative, pas des taux de perte ; sans cette
# conversion, une sévérité de 0,64 signifierait « 64 % du CA perdu chaque
# année ». Fonction de dommage au sens de MSCI Climate VaR / Trucost.
PHYSICAL_DAMAGE_FACTOR = 0.10

# Bornes de sécurité appliquées à la PD avant inversion de Φ.
PD_MIN = 1e-6
PD_MAX = 0.99

# Horizons proposés à l'utilisateur.
HORIZONS = (2030, 2040, 2050)

# Profil appliqué quand l'entreprise n'a aucun mix sectoriel connu.
DEFAULT_CREDIT_PROFILE = {
    'pd_baseline': 0.015,
    'ebitda_margin': 0.12,
    'ebitda_volatility': 0.25,
    'carbon_pass_through': 0.30,
}

# Équivalent notation indicatif : (notation, PD 1 an maximale de la bande).
# Convention d'affichage, jamais une notation attribuée.
RATING_BANDS = [
    ('AAA', 0.0002),
    ('AA',  0.0006),
    ('A',   0.0015),
    ('BBB', 0.0050),
    ('BB',  0.0250),
    ('B',   0.1000),
    ('CCC', 1.0),
]


def retained_emissions(scope1, scope2, scope3, include_scope3):
    """tCO₂e retenues : scopes 1+2, plus une fraction du scope 3 si activé."""
    total = scope1 + scope2
    if include_scope3:
        total += scope3 * SCOPE3_TRANSMISSION
    return total


def carbon_cost(emissions_t, delta_price, pass_through):
    """Coût carbone non provisionné, en euros.

    `delta_price` est un **différentiel** de prix (€/tCO₂e) entre l'horizon et
    l'année de référence : l'émetteur supporte déjà le prix courant. Un
    différentiel négatif ne produit pas de gain.
    """
    if emissions_t <= 0 or delta_price <= 0:
        return 0.0
    return emissions_t * delta_price * (1.0 - pass_through)


def hazard_severity_ratio(hazard_pairs, multiplier):
    """Sévérité moyenne des aléas d'un actif, bornée dans [0, 1].

    Ce n'est **pas** une fraction de chiffre d'affaires perdue : la conversion
    en perte économique passe par `PHYSICAL_DAMAGE_FACTOR`, appliqué par
    l'appelant.

    `hazard_pairs` : itérable de `(aléa, vulnérabilité)` pour un même actif,
    couvrant **tout le panel d'aléas**. Un aléa nul signifie « cet actif n'est
    pas exposé » et pèse dans la moyenne.

    L'agrégation est une **moyenne**, pas une composition d'événements
    indépendants. Les scores `risk_*` sont des indices de sévérité relative,
    pas des probabilités annuelles de perte totale : les composer par
    `1 − Π(1 − r·v·λ)` sature à 1 dès une dizaine d'aléas (0,82¹⁵ ≈ 0,05) et
    prive la métrique de tout pouvoir discriminant. La moyenne ne sature pas
    et ne dépend pas du nombre de colonnes d'aléas.
    """
    pairs = list(hazard_pairs)
    if not pairs:
        return 0.0
    severity = sum(
        max(0.0, hazard * vulnerability) for hazard, vulnerability in pairs
    ) / len(pairs)
    return min(1.0, severity * multiplier)


def shock_to_sigma(shock_ratio, volatility):
    """Choc relatif d'EBITDA converti en écarts-types, plancher 0, plafond."""
    if volatility <= 0:
        return MAX_SHOCK_SIGMA
    return min(MAX_SHOCK_SIGMA, max(0.0, shock_ratio / volatility))


def shock_to_pd(pd_baseline, shock_sigma):
    """PD stressée par décalage latent : ``PD* = Φ(Φ⁻¹(PD₀) + S)``.

    ``−Φ⁻¹(PD₀)`` est la distance au défaut implicite en écarts-types ; le choc
    la réduit de ``S``. Neutre exactement en ``S = 0``, monotone, et borné dans
    ``]0, 1[``.
    """
    pd0 = min(PD_MAX, max(PD_MIN, pd_baseline))
    return _NORM.cdf(_NORM.inv_cdf(pd0) + shock_sigma)


def pd_to_rating(pd):
    """Équivalent notation indicatif pour une PD 1 an."""
    for label, upper in RATING_BANDS:
        if pd <= upper:
            return label
    return RATING_BANDS[-1][0]


def interpolate_trajectory(points, year):
    """Valeur d'une trajectoire à `year`.

    `points` : `{année: valeur}`. Interpolation linéaire entre les deux points
    encadrants ; valeur constante avant le premier et après le dernier point.
    """
    if not points:
        return 0.0
    years = sorted(points)
    if year <= years[0]:
        return float(points[years[0]])
    if year >= years[-1]:
        return float(points[years[-1]])
    for low, high in zip(years, years[1:]):
        if low <= year <= high:
            weight = (year - low) / (high - low)
            return float(points[low] + (points[high] - points[low]) * weight)
    return float(points[years[-1]])
```

- [ ] **Step 4 : Lancer les tests, vérifier qu'ils passent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test`
Expected: PASS (34 tests)

- [ ] **Step 5 : Commit**

```bash
git add dashboard/services/stress_test.py dashboard/tests_stress_test.py
git commit -m "feat(service): noyau pur du stress test climatique (cout carbone, dommages, PD)"
```

---

### Task 2 : Modèles de scénario et profil de crédit

**Files:**
- Modify: `dashboard/models.py` (fin de fichier)
- Create: `dashboard/migrations/0042_climate_scenario_models.py`
- Test: `dashboard/tests_stress_test.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `ClimateScenario(key [unique], name, family, narrative, warming_c, source, reference, order)` avec `Family.ORDERLY|DISORDERLY|TOO_LITTLE|HOT_HOUSE` et `related_name='variables'`
  - `ScenarioVariable(scenario, year, key, value)` avec `Key.CARBON_PRICE='carbon_price'`, `Key.HAZARD_MULTIPLIER='hazard_multiplier'`, `unique_together=('scenario','year','key')`
  - `SectorCreditProfile(sector [OneToOne], pd_baseline, ebitda_margin, ebitda_volatility, carbon_pass_through, source, reference)` avec `related_name='credit_profile'`

- [ ] **Step 1 : Écrire les tests**

Ajouter à la fin de `dashboard/tests_stress_test.py` :

```python
from django.db import IntegrityError, transaction

from dashboard.models import (
    ClimateScenario, ScenarioVariable, Sector, SectorCreditProfile,
)


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
        self.assertEqual([s.key for s in ClimateScenario.objects.all()], ['A', 'B'])


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
```

- [ ] **Step 2 : Lancer les tests, vérifier qu'ils échouent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test`
Expected: FAIL — `ImportError: cannot import name 'ClimateScenario' from 'dashboard.models'`

- [ ] **Step 3 : Écrire les modèles**

Ajouter à la fin de `dashboard/models.py` :

```python
class ClimateScenario(models.Model):
    """Scénario climatique de référence (NGFS Phase V)."""

    class Family(models.TextChoices):
        ORDERLY = 'ORDERLY', 'Transition ordonnée'
        DISORDERLY = 'DISORDERLY', 'Transition désordonnée'
        TOO_LITTLE = 'TOO_LITTLE', 'Trop peu, trop tard'
        HOT_HOUSE = 'HOT_HOUSE', 'Monde en surchauffe'

    key = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    family = models.CharField(
        max_length=20, choices=Family.choices, default=Family.ORDERLY
    )
    narrative = models.TextField(blank=True)
    warming_c = models.FloatField(default=0.0)
    source = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=255, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('order', 'key')

    def __str__(self):
        return self.name


class ScenarioVariable(models.Model):
    """Point de trajectoire d'un scénario (prix carbone, multiplicateur d'aléa)."""

    class Key(models.TextChoices):
        CARBON_PRICE = 'carbon_price', 'Prix du carbone (€/tCO₂e)'
        HAZARD_MULTIPLIER = 'hazard_multiplier', "Multiplicateur d'aléa"

    scenario = models.ForeignKey(
        ClimateScenario, on_delete=models.CASCADE, related_name='variables'
    )
    year = models.IntegerField()
    key = models.CharField(max_length=30, choices=Key.choices)
    value = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('scenario', 'year', 'key')
        ordering = ('scenario', 'key', 'year')

    def __str__(self):
        return f'{self.scenario.key} — {self.key} {self.year}'


class SectorCreditProfile(models.Model):
    """Paramètres de crédit et de marge d'un secteur (NACE).

    Sert de valeur par défaut : l'utilisateur peut surcharger la PD initiale et
    la marge EBITDA à l'écran.
    """

    sector = models.OneToOneField(
        Sector, on_delete=models.CASCADE, related_name='credit_profile'
    )
    pd_baseline = models.FloatField(default=0.015)
    ebitda_margin = models.FloatField(default=0.12)
    ebitda_volatility = models.FloatField(default=0.25)
    carbon_pass_through = models.FloatField(default=0.30)
    source = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.sector.name} — PD {self.pd_baseline:.2%}'
```

- [ ] **Step 4 : Générer la migration**

Run: `.venv\Scripts\python.exe manage.py makemigrations dashboard --name climate_scenario_models`
Expected: crée `dashboard/migrations/0042_climate_scenario_models.py` avec les 3 `CreateModel`.

- [ ] **Step 5 : Lancer les tests, vérifier qu'ils passent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test`
Expected: PASS

- [ ] **Step 6 : Vérifier que la suite complète reste verte**

Run: `.venv\Scripts\python.exe manage.py test dashboard`
Expected: PASS — aucun modèle existant n'a été touché.

- [ ] **Step 7 : Commit**

```bash
git add dashboard/models.py dashboard/migrations/0042_climate_scenario_models.py dashboard/tests_stress_test.py
git commit -m "feat(models): ClimateScenario, ScenarioVariable, SectorCreditProfile"
```

---

### Task 3 : Seed des scénarios NGFS

**Files:**
- Create: `dashboard/migrations/0043_seed_climate_scenarios.py`
- Test: `dashboard/tests_stress_test.py`

**Interfaces:**
- Consumes: `ClimateScenario`, `ScenarioVariable` (Task 2).
- Produces: 5 scénarios en base, clés `NET_ZERO_2050`, `BELOW_2C`, `DELAYED_TRANSITION`, `FRAGMENTED_WORLD`, `CURRENT_POLICIES`, chacun avec 4 points `carbon_price` et 4 points `hazard_multiplier` (2025, 2030, 2040, 2050).

> **Avertissement sur les valeurs.** Les trajectoires ci-dessous sont des ordres de grandeur **indicatifs** cohérents avec les narratifs NGFS Phase V, pas des extractions du portail. Le champ `reference` le dit explicitement sur chaque scénario. Recaler ces valeurs sur le *NGFS Scenarios Portal* est un suivi à part entière — mais la page est fonctionnelle et méthodologiquement correcte avec ces valeurs.

- [ ] **Step 1 : Écrire les tests du seed**

Ajouter à `dashboard/tests_stress_test.py` :

```python
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
```

- [ ] **Step 2 : Lancer les tests, vérifier qu'ils échouent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test.SeedClimateScenariosTests`
Expected: FAIL — `AssertionError: 'NET_ZERO_2050' not found in set()`

- [ ] **Step 3 : Écrire la migration de seed**

Créer `dashboard/migrations/0043_seed_climate_scenarios.py` :

```python
"""Seed des scénarios climatiques de référence (NGFS Phase V).

Données figées dans le fichier : la migration ne doit jamais dépendre d'une
constante vivante du code applicatif.

Les trajectoires sont des ordres de grandeur indicatifs cohérents avec les
narratifs NGFS Phase V (novembre 2024). Elles sont marquées comme telles dans
le champ `reference` et doivent être recalées sur le NGFS Scenarios Portal.
"""
from django.db import migrations

SOURCE = 'NGFS — Climate Scenarios for Central Banks and Supervisors, Phase V (nov. 2024)'
REFERENCE = (
    'Valeurs indicatives cohérentes avec les narratifs NGFS — '
    'à recaler sur https://www.ngfs.net/ngfs-scenarios-portal/'
)

# (key, name, family, warming_c, order, narrative)
SCENARIOS = [
    (
        'NET_ZERO_2050', 'Net Zero 2050', 'ORDERLY', 1.5, 1,
        "Politiques climatiques ambitieuses et immédiates, neutralité carbone "
        "atteinte vers 2050. Risque de transition élevé mais anticipé, risque "
        "physique contenu.",
    ),
    (
        'BELOW_2C', 'Below 2 °C', 'ORDERLY', 1.7, 2,
        "Durcissement progressif des politiques, réchauffement limité sous 2 °C. "
        "Transition graduelle, risques répartis dans le temps.",
    ),
    (
        'DELAYED_TRANSITION', 'Delayed Transition', 'DISORDERLY', 1.8, 3,
        "Aucune baisse des émissions avant 2030, puis politiques abruptes pour "
        "tenir la cible. Choc de transition tardif et brutal.",
    ),
    (
        'FRAGMENTED_WORLD', 'Fragmented World', 'TOO_LITTLE', 2.3, 4,
        "Ambition climatique divergente selon les pays ; les objectifs net zéro "
        "ne sont atteints que partiellement. Risques de transition ET physiques "
        "élevés.",
    ),
    (
        'CURRENT_POLICIES', 'Current Policies', 'HOT_HOUSE', 3.0, 5,
        "Seules les politiques déjà en vigueur sont maintenues. Risque de "
        "transition faible, risque physique sévère et croissant.",
    ),
]

# key: {year: prix carbone €/tCO₂e}
CARBON_PRICE = {
    'NET_ZERO_2050':      {2025: 80.0, 2030: 190.0, 2040: 400.0, 2050: 570.0},
    'BELOW_2C':           {2025: 80.0, 2030: 110.0, 2040: 220.0, 2050: 350.0},
    'DELAYED_TRANSITION': {2025: 80.0, 2030: 85.0,  2040: 400.0, 2050: 550.0},
    'FRAGMENTED_WORLD':   {2025: 80.0, 2030: 95.0,  2040: 190.0, 2050: 280.0},
    'CURRENT_POLICIES':   {2025: 80.0, 2030: 85.0,  2040: 90.0,  2050: 95.0},
}

# key: {year: multiplicateur d'aléa physique, base 1.0 aujourd'hui}
HAZARD_MULTIPLIER = {
    'NET_ZERO_2050':      {2025: 1.0, 2030: 1.10, 2040: 1.20, 2050: 1.30},
    'BELOW_2C':           {2025: 1.0, 2030: 1.10, 2040: 1.25, 2050: 1.40},
    'DELAYED_TRANSITION': {2025: 1.0, 2030: 1.15, 2040: 1.30, 2050: 1.50},
    'FRAGMENTED_WORLD':   {2025: 1.0, 2030: 1.20, 2040: 1.50, 2050: 1.90},
    'CURRENT_POLICIES':   {2025: 1.0, 2030: 1.25, 2040: 1.70, 2050: 2.40},
}


def seed(apps, schema_editor):
    ClimateScenario = apps.get_model('dashboard', 'ClimateScenario')
    ScenarioVariable = apps.get_model('dashboard', 'ScenarioVariable')

    for key, name, family, warming, order, narrative in SCENARIOS:
        scenario, _ = ClimateScenario.objects.get_or_create(
            key=key,
            defaults={
                'name': name, 'family': family, 'warming_c': warming,
                'order': order, 'narrative': narrative,
                'source': SOURCE, 'reference': REFERENCE,
            },
        )
        for var_key, table in (
            ('carbon_price', CARBON_PRICE),
            ('hazard_multiplier', HAZARD_MULTIPLIER),
        ):
            for year, value in table[key].items():
                ScenarioVariable.objects.get_or_create(
                    scenario=scenario, year=year, key=var_key,
                    defaults={'value': value},
                )


def unseed(apps, schema_editor):
    ClimateScenario = apps.get_model('dashboard', 'ClimateScenario')
    ClimateScenario.objects.filter(key__in=[s[0] for s in SCENARIOS]).delete()


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0042_climate_scenario_models')]
    operations = [migrations.RunPython(seed, unseed)]
```

- [ ] **Step 4 : Lancer les tests, vérifier qu'ils passent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test`
Expected: PASS

- [ ] **Step 5 : Vérifier la réversibilité de la migration**

Run: `.venv\Scripts\python.exe manage.py migrate dashboard 0042` puis `.venv\Scripts\python.exe manage.py migrate dashboard`
Expected: les deux sens passent sans erreur.

- [ ] **Step 6 : Commit**

```bash
git add dashboard/migrations/0043_seed_climate_scenarios.py dashboard/tests_stress_test.py
git commit -m "feat(migration): seed des 5 scenarios NGFS Phase V et de leurs trajectoires"
```

---

### Task 4 : Lecture des trajectoires (couche ORM)

**Files:**
- Modify: `dashboard/services/stress_test.py` (ajouts en fin de fichier)
- Test: `dashboard/tests_stress_test.py`

**Interfaces:**
- Consumes: `interpolate_trajectory` (Task 1) ; `ClimateScenario`, `ScenarioVariable` (Task 2).
- Produces:
  - `scenario_trajectory(scenario: ClimateScenario, key: str) -> dict[int, float]`
  - `scenario_value(scenario: ClimateScenario, key: str, year: int) -> float`
  - `carbon_price_delta(scenario, year, reference_year, override=None) -> float`

- [ ] **Step 1 : Écrire les tests**

Ajouter à `dashboard/tests_stress_test.py` :

```python
from dashboard.services.stress_test import (
    carbon_price_delta, scenario_trajectory, scenario_value,
)


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
```

- [ ] **Step 2 : Lancer les tests, vérifier qu'ils échouent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test.ScenarioTrajectoryTests`
Expected: FAIL — `ImportError: cannot import name 'scenario_trajectory'`

- [ ] **Step 3 : Implémenter**

Ajouter à la fin de `dashboard/services/stress_test.py` :

```python
# ── Couche ORM ────────────────────────────────────────────────────────────────
#
# Tout ce qui suit touche la base. Le noyau ci-dessus reste pur.

from ..models import ScenarioVariable  # noqa: E402  (import après le noyau pur)

KEY_CARBON_PRICE = ScenarioVariable.Key.CARBON_PRICE
KEY_HAZARD_MULTIPLIER = ScenarioVariable.Key.HAZARD_MULTIPLIER


def scenario_trajectory(scenario, key):
    """`{année: valeur}` pour une variable d'un scénario."""
    return {
        variable.year: variable.value
        for variable in scenario.variables.filter(key=key)
    }


def scenario_value(scenario, key, year):
    """Valeur d'une variable de scénario à une année quelconque."""
    return interpolate_trajectory(scenario_trajectory(scenario, key), year)


def carbon_price_delta(scenario, year, reference_year, override=None):
    """Différentiel de prix carbone entre `year` et `reference_year`, ≥ 0.

    `override` remplace le prix du scénario à l'horizon (curseur utilisateur) ;
    le prix de référence, lui, reste celui du scénario.
    """
    reference = scenario_value(scenario, KEY_CARBON_PRICE, reference_year)
    price = (
        float(override) if override is not None
        else scenario_value(scenario, KEY_CARBON_PRICE, year)
    )
    return max(0.0, price - reference)
```

- [ ] **Step 4 : Lancer les tests, vérifier qu'ils passent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test`
Expected: PASS

- [ ] **Step 5 : Commit**

```bash
git add dashboard/services/stress_test.py dashboard/tests_stress_test.py
git commit -m "feat(service): lecture interpolee des trajectoires de scenario"
```

---

### Task 5 : Extraction de `PHYSICAL_RISKS` vers un module partagé

`services/stress_test.py` a besoin de la liste des 15 aléas, aujourd'hui définie dans `views.py`. L'importer depuis `views.py` créerait un cycle (`views` → `services.stress_test` → `views`). On la déplace, sans changer une virgule de son contenu.

**Files:**
- Create: `dashboard/services/hazards.py`
- Modify: `dashboard/views.py:55-76` (suppression) et `dashboard/views.py:15-18` (import)
- Test: `dashboard/tests_stress_test.py`

**Interfaces:**
- Produces: `dashboard.services.hazards.PHYSICAL_RISKS: list[dict]` — 15 entrées `{'key','name','group'}`, dans l'ordre exact d'origine.
- `dashboard.views.PHYSICAL_RISKS` reste importable et identique (ré-export).

- [ ] **Step 1 : Écrire le test de non-régression**

Ajouter à `dashboard/tests_stress_test.py` :

```python
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
```

- [ ] **Step 2 : Lancer les tests, vérifier qu'ils échouent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test.HazardCatalogTests`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.services.hazards'`

- [ ] **Step 3 : Créer le module**

Créer `dashboard/services/hazards.py` :

```python
"""Catalogue des aléas physiques.

Partagé entre la vue Risque physique et le stress test climatique. Vivait dans
`views.py` ; déplacé ici pour être importable par les services sans cycle.

Chaque `key` correspond à un champ `Asset.risk_<key>` ET à un champ
`Policy_Level.vulnerability_<key>`.
"""

PHYSICAL_RISKS = [
    {'key': 'water', 'name': 'Eau', 'group': 'Services écosystémiques'},
    {'key': 'pollination', 'name': 'Pollinisation', 'group': 'Services écosystémiques'},
    {'key': 'soil_quality', 'name': 'Qualité des sols', 'group': 'Services écosystémiques'},
    {'key': 'carbon_sequestration', 'name': 'Séquestration carbone',
     'group': 'Services écosystémiques'},
    {'key': 'water_purification', 'name': "Épuration de l'eau",
     'group': 'Services écosystémiques'},
    {'key': 'pest_control', 'name': 'Contrôle des ravageurs',
     'group': 'Services écosystémiques'},
    {'key': 'water_stress', 'name': 'Stress hydrique', 'group': 'Aléas climatiques'},
    {'key': 'wildfire', 'name': 'Incendie', 'group': 'Aléas climatiques'},
    {'key': 'cyclone', 'name': 'Cyclone', 'group': 'Aléas climatiques'},
    {'key': 'drought', 'name': 'Sécheresse', 'group': 'Aléas climatiques'},
    {'key': 'flood', 'name': 'Inondation', 'group': 'Aléas climatiques'},
    {'key': 'coastal_inundation', 'name': 'Submersion côtière', 'group': 'Aléas climatiques'},
    {'key': 'heatwave', 'name': 'Canicule', 'group': 'Aléas climatiques'},
    {'key': 'temperature_variation', 'name': 'Variation de température',
     'group': 'Aléas climatiques'},
    {'key': 'precipitation_variation', 'name': 'Variation des précipitations',
     'group': 'Aléas climatiques'},
]
```

- [ ] **Step 4 : Retirer la définition de `views.py`**

Supprimer le bloc `PHYSICAL_RISKS = [...]` de `dashboard/views.py` (lignes 55 à 76, du `PHYSICAL_RISKS = [` jusqu'au `]` inclus) et ajouter l'import à côté des autres imports de services :

```python
from .services.supply import TIER_LABELS, TIER_TO_SCOPE
from .services.hazards import PHYSICAL_RISKS
```

- [ ] **Step 5 : Lancer la suite complète**

Run: `.venv\Scripts\python.exe manage.py test dashboard`
Expected: PASS — notamment `PhysicalRiskDataTests` et `GoldenViewOutputTests`, qui prouvent que le déplacement est neutre.

- [ ] **Step 6 : Commit**

```bash
git add dashboard/services/hazards.py dashboard/views.py dashboard/tests_stress_test.py
git commit -m "refactor(services): deplace PHYSICAL_RISKS dans services/hazards (partage sans cycle)"
```

---

### Task 6 : Profils de crédit sectoriels

**Files:**
- Modify: `dashboard/services/stress_test.py` (ajout en fin de fichier)
- Modify: `dashboard/management/commands/populate_acme.py` (après le bloc « Revenus », vers la ligne 449)
- Test: `dashboard/tests_stress_test.py`

**Interfaces:**
- Consumes: `DEFAULT_CREDIT_PROFILE` (Task 1) ; `SectorCreditProfile` (Task 2).
- Produces: `resolve_credit_profile(company, year) -> tuple[dict, list[str]]` — le dict a exactement les 4 clés de `DEFAULT_CREDIT_PROFILE`, la liste contient les avertissements.

- [ ] **Step 1 : Écrire les tests**

Ajouter à `dashboard/tests_stress_test.py` :

```python
from dashboard.models import Company, Company_Revenue_Sector, SubSector
from dashboard.services.stress_test import resolve_credit_profile


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
```

- [ ] **Step 2 : Lancer les tests, vérifier qu'ils échouent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test.ResolveCreditProfileTests`
Expected: FAIL — `ImportError: cannot import name 'resolve_credit_profile'`

- [ ] **Step 3 : Implémenter la résolution**

Ajouter à la fin de `dashboard/services/stress_test.py` (et compléter l'import ORM en tête de la section ORM) :

```python
from ..models import Company_Revenue_Sector, SectorCreditProfile  # noqa: E402


def resolve_credit_profile(company, year):
    """Profil de crédit pondéré par le mix de CA sectoriel de l'année.

    Retourne `(profil, avertissements)`. Le profil a toujours les 4 clés de
    `DEFAULT_CREDIT_PROFILE`.
    """
    weights = {}
    rows = (
        Company_Revenue_Sector.objects
        .filter(company=company, year=year)
        .select_related('subsector')
    )
    for row in rows:
        if row.revenue > 0:
            sector_id = row.subsector.sector_id
            weights[sector_id] = weights.get(sector_id, 0.0) + row.revenue

    total = sum(weights.values())
    if not total:
        return dict(DEFAULT_CREDIT_PROFILE), [
            f"Aucun mix sectoriel connu pour {year} : profil de crédit de repli "
            f"appliqué."
        ]

    profiles = {
        profile.sector_id: profile
        for profile in SectorCreditProfile.objects.filter(sector_id__in=weights)
    }
    warnings = []
    missing = [sector_id for sector_id in weights if sector_id not in profiles]
    if missing:
        warnings.append(
            f"{len(missing)} secteur(s) sans profil de crédit : valeurs de repli "
            f"utilisées pour cette part du chiffre d'affaires."
        )

    resolved = {}
    for field, fallback in DEFAULT_CREDIT_PROFILE.items():
        accumulator = 0.0
        for sector_id, weight in weights.items():
            profile = profiles.get(sector_id)
            value = getattr(profile, field) if profile is not None else fallback
            accumulator += (weight / total) * value
        resolved[field] = accumulator
    return resolved, warnings
```

- [ ] **Step 4 : Ajouter les profils de démo à `populate_acme`**

Dans `dashboard/management/commands/populate_acme.py`, ajouter `SectorCreditProfile` à l'import de modèles en tête de fichier, puis insérer ce bloc **juste après** la boucle `Company_Revenue_Sector.objects.get_or_create(...)` (vers la ligne 449) :

```python
        # ── Profils de crédit sectoriels (démo) ───────────────────────────────
        #
        # PD 1 an, marge et volatilité d'EBITDA, répercussion du coût carbone.
        # Valeurs de démonstration : ordres de grandeur plausibles, à remplacer
        # par des données de marché pour un usage réel.

        for sector, pd_baseline, margin, volatility, pass_through in [
            (sector_agri, 0.0180, 0.10, 0.28, 0.20),
            (sector_food, 0.0090, 0.14, 0.22, 0.35),
        ]:
            SectorCreditProfile.objects.get_or_create(
                sector=sector,
                defaults={
                    "pd_baseline": pd_baseline,
                    "ebitda_margin": margin,
                    "ebitda_volatility": volatility,
                    "carbon_pass_through": pass_through,
                    "source": "Démonstration Easybiodiv",
                    "reference": "Ordres de grandeur, non calibrés sur données de marché",
                },
            )
```

- [ ] **Step 5 : Lancer les tests, vérifier qu'ils passent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test`
Expected: PASS

- [ ] **Step 6 : Commit**

```bash
git add dashboard/services/stress_test.py dashboard/management/commands/populate_acme.py dashboard/tests_stress_test.py
git commit -m "feat(service): profil de credit sectoriel pondere par le mix de CA"
```

---

### Task 7 : Orchestration `get_stress_test_data`

Le cœur : assemble snapshot d'entreprise, scénario et hypothèses en un payload complet.

**Files:**
- Modify: `dashboard/services/stress_test.py` (ajout en fin de fichier)
- Test: `dashboard/tests_stress_test.py`

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces:
  - `company_snapshot(company, year) -> dict` avec les clés `scope1`, `scope2`, `scope3`, `revenue`, `exposure`, `asset_count`, `assets` (liste de `{'exposure', 'hazard_pairs'}`)
  - `get_stress_test_data(company, params=None) -> dict` — le contrat complet documenté dans « File Structure ».
  - `params` accepte : `scenario` (`ClimateScenario | None`), `horizon` (`int | None`), `carbon_price` (`float | None`), `include_scope3` (`bool`), `pass_through` (`float | None`), `ebitda_margin` (`float | None`), `pd_baseline` (`float | None`).

- [ ] **Step 1 : Écrire les tests**

Ajouter à `dashboard/tests_stress_test.py` :

```python
from django.core.management import call_command

from dashboard.models import ClimateScenario
from dashboard.services.stress_test import (
    HORIZONS, company_snapshot, get_stress_test_data,
)


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
```

- [ ] **Step 2 : Lancer les tests, vérifier qu'ils échouent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test.GetStressTestDataTests`
Expected: FAIL — `ImportError: cannot import name 'get_stress_test_data'`

- [ ] **Step 3 : Implémenter**

Ajouter à la fin de `dashboard/services/stress_test.py` (compléter les imports ORM avec `Asset`, `Carbon_emission`, `ClimateScenario`, `Company_Revenue`, `Company_Policy`, `Production`, et `from django.db.models import Max`, et `from .hazards import PHYSICAL_RISKS`) :

```python
def company_snapshot(company, year):
    """Émissions, CA, exposition et couples (aléa, vulnérabilité) par actif."""
    emissions = {}
    for row in Carbon_emission.objects.filter(company=company, year=year):
        normalized = row.scope.strip().lower().replace(' ', '')
        emissions[normalized] = emissions.get(normalized, 0.0) + row.carbon_emission

    revenue_row = Company_Revenue.objects.filter(company=company, year=year).first()

    assets = list(Asset.objects.filter(ownership__Company=company).distinct())
    asset_ids = [asset.pk for asset in assets]

    latest_years = dict(
        Production.objects.filter(asset_id__in=asset_ids)
        .values('asset_id').annotate(max_year=Max('year'))
        .values_list('asset_id', 'max_year')
    )
    exposure_by_asset = {}
    for row in Production.objects.filter(asset_id__in=asset_ids).values(
        'asset_id', 'year', 'estimated_revenue'
    ):
        if latest_years.get(row['asset_id']) == row['year']:
            exposure_by_asset[row['asset_id']] = (
                exposure_by_asset.get(row['asset_id'], 0.0) + row['estimated_revenue']
            )

    levels = [
        link.policy_level
        for link in Company_Policy.objects.filter(company=company)
        .select_related('policy_level')
        if link.policy_level_id
    ]

    def _vulnerability(key):
        values = [getattr(level, f'vulnerability_{key}') for level in levels]
        return sum(values) / len(values) if values else 1.0

    vulnerabilities = {risk['key']: _vulnerability(risk['key'])
                       for risk in PHYSICAL_RISKS}

    assets_out = []
    for asset in assets:
        assets_out.append({
            'exposure': exposure_by_asset.get(asset.pk, 0.0),
            'hazard_pairs': [
                (getattr(asset, f"risk_{risk['key']}"), vulnerabilities[risk['key']])
                for risk in PHYSICAL_RISKS
            ],
        })

    return {
        'scope1': emissions.get('scope1', 0.0),
        'scope2': emissions.get('scope2', 0.0),
        'scope3': emissions.get('scope3', 0.0),
        'revenue': revenue_row.revenue if revenue_row else 0.0,
        'exposure': sum(exposure_by_asset.values()),
        'asset_count': len(assets),
        'assets': assets_out,
    }


def _evaluate(snapshot, options, delta_price, hazard_multiplier):
    """Bloc de résultat pour un jeu d'hypothèses. `None` si l'EBITDA proxy ≤ 0."""
    emissions = retained_emissions(
        snapshot['scope1'], snapshot['scope2'], snapshot['scope3'],
        options['include_scope3'],
    )
    cost = carbon_cost(emissions, delta_price, options['pass_through'])

    loss = 0.0
    for asset in snapshot['assets']:
        loss += (
            asset['exposure'] * PHYSICAL_DAMAGE_FACTOR
            * hazard_severity_ratio(asset['hazard_pairs'], hazard_multiplier)
        )
    exposure = snapshot['exposure']
    loss_ratio = (loss / exposure) if exposure > 0 else 0.0

    ebitda = snapshot['revenue'] * options['ebitda_margin']
    if ebitda <= 0:
        return None

    volatility = options['ebitda_volatility']
    sigma_transition = shock_to_sigma(cost / ebitda, volatility)
    sigma_total = shock_to_sigma((cost + loss) / ebitda, volatility)
    sigma_physical = max(0.0, sigma_total - sigma_transition)

    pd0 = options['pd_baseline']
    pd_transition = shock_to_pd(pd0, sigma_transition)
    pd_total = shock_to_pd(pd0, sigma_total)

    return {
        'pd_baseline': round(pd0, 6),
        'pd_stressed': round(pd_total, 6),
        'delta_bps': round((pd_total - pd0) * 10_000, 1),
        'multiple': round(pd_total / pd0, 2) if pd0 > 0 else None,
        'rating_baseline': pd_to_rating(pd0),
        'rating_stressed': pd_to_rating(pd_total),
        'shock_ratio': round((cost + loss) / ebitda, 4),
        'shock_sigma': round(sigma_total, 4),
        'ebitda_proxy': round(ebitda, 2),
        'emissions_retained': round(emissions, 2),
        'transition': {
            'cost_eur': round(cost, 2),
            'pct_ebitda': round(cost / ebitda, 4),
            'shock_sigma': round(sigma_transition, 4),
        },
        'physical': {
            'loss_eur': round(loss, 2),
            'loss_ratio': round(loss_ratio, 4),
            'pct_ebitda': round(loss / ebitda, 4),
            'shock_sigma': round(sigma_physical, 4),
        },
        'waterfall': [
            {'label': 'PD initiale', 'pd': round(pd0, 6), 'delta_bps': 0.0},
            {'label': 'Transition', 'pd': round(pd_transition, 6),
             'delta_bps': round((pd_transition - pd0) * 10_000, 1)},
            {'label': 'Physique', 'pd': round(pd_total, 6),
             'delta_bps': round((pd_total - pd_transition) * 10_000, 1)},
        ],
    }


def _scenario_payload(scenario):
    return {
        'key': scenario.key,
        'name': scenario.name,
        'family': scenario.family,
        'family_label': scenario.get_family_display(),
        'warming_c': scenario.warming_c,
        'narrative': scenario.narrative,
    }


def _empty_payload(company, reference_year, scenarios, warnings):
    return {
        'company_id': company.pk,
        'company_name': company.name,
        'reference_year': reference_year,
        'scenarios': [_scenario_payload(s) for s in scenarios],
        'selected': None,
        'inputs': None,
        'result': None,
        'waterfall': [],
        'channels': None,
        'horizon_curve': [],
        'scenario_comparison': [],
        'assumptions': [],
        'warnings': warnings,
    }


def _assumptions(scenario, horizon, options, carbon_price, reference_price,
                 hazard_multiplier):
    scenario_source = scenario.source
    scenario_reference = scenario.reference
    return [
        {'label': 'Scénario', 'value': scenario.name,
         'source': scenario_source, 'reference': scenario_reference},
        {'label': 'Horizon', 'value': str(horizon),
         'source': '', 'reference': ''},
        {'label': 'Prix du carbone à l’horizon',
         'value': f'{carbon_price:,.0f} €/tCO₂e'.replace(',', ' '),
         'source': scenario_source, 'reference': scenario_reference},
        {'label': 'Prix du carbone de référence',
         'value': f'{reference_price:,.0f} €/tCO₂e'.replace(',', ' '),
         'source': scenario_source, 'reference': scenario_reference},
        {'label': "Multiplicateur d'aléa physique",
         'value': f'{hazard_multiplier:.2f}',
         'source': scenario_source, 'reference': scenario_reference},
        {'label': 'Périmètre des émissions',
         'value': 'Scopes 1+2+3' if options['include_scope3'] else 'Scopes 1+2',
         'source': 'Choix utilisateur', 'reference': ''},
        {'label': 'Transmission du scope 3 amont',
         'value': f'{SCOPE3_TRANSMISSION:.0%}',
         'source': 'Constante Easybiodiv',
         'reference': 'Traitement Trucost CEaR / MSCI Climate VaR'},
        {'label': 'Coefficient de dommage physique',
         'value': f'{PHYSICAL_DAMAGE_FACTOR:.0%}',
         'source': 'Constante Easybiodiv',
         'reference': "Fonction de dommage au sens MSCI Climate VaR / Trucost ; "
                      "part du CA exposé perdue à sévérité 1"},
        {'label': 'Répercussion du coût carbone',
         'value': f"{options['pass_through']:.0%}",
         'source': 'Profil sectoriel ou choix utilisateur', 'reference': ''},
        {'label': 'Marge EBITDA',
         'value': f"{options['ebitda_margin']:.1%}",
         'source': 'Profil sectoriel ou choix utilisateur', 'reference': ''},
        {'label': "Volatilité d'EBITDA",
         'value': f"{options['ebitda_volatility']:.0%}",
         'source': 'Profil sectoriel', 'reference': ''},
        {'label': 'PD initiale',
         'value': f"{options['pd_baseline']:.2%}",
         'source': 'Profil sectoriel pondéré ou choix utilisateur',
         'reference': ''},
    ]


def get_stress_test_data(company, params=None):
    """Payload complet du stress test climatique pour une entreprise."""
    params = params or {}
    warnings = []
    scenarios = list(ClimateScenario.objects.all())

    revenue_row = (
        Company_Revenue.objects.filter(company=company).order_by('-year').first()
    )
    reference_year = revenue_row.year if revenue_row else None

    if not scenarios:
        warnings.append(
            'Aucun scénario climatique en base : appliquer les migrations.'
        )
        return _empty_payload(company, reference_year, scenarios, warnings)

    if revenue_row is None or revenue_row.revenue <= 0:
        warnings.append(
            "Aucun chiffre d'affaires connu pour cette entreprise : le stress "
            "test ne peut pas être calculé."
        )
        return _empty_payload(company, reference_year, scenarios, warnings)

    scenario = params.get('scenario') or scenarios[0]
    horizon = params.get('horizon') or HORIZONS[0]

    profile, profile_warnings = resolve_credit_profile(company, reference_year)
    warnings.extend(profile_warnings)

    options = {
        'include_scope3': bool(params.get('include_scope3', False)),
        'pass_through': _pick(params, 'pass_through',
                              profile['carbon_pass_through']),
        'ebitda_margin': _pick(params, 'ebitda_margin', profile['ebitda_margin']),
        'pd_baseline': _pick(params, 'pd_baseline', profile['pd_baseline']),
        'ebitda_volatility': profile['ebitda_volatility'],
    }

    snapshot = company_snapshot(company, reference_year)
    if snapshot['scope1'] + snapshot['scope2'] + snapshot['scope3'] == 0:
        warnings.append(
            f"Aucune donnée d'émissions pour {reference_year} : le canal "
            f"transition est nul."
        )
    if snapshot['asset_count'] == 0:
        warnings.append(
            'Aucun actif rattaché à cette entreprise : le canal physique est nul.'
        )

    reference_price = scenario_value(scenario, KEY_CARBON_PRICE, reference_year)
    carbon_price = params.get('carbon_price')
    if carbon_price is None:
        carbon_price = scenario_value(scenario, KEY_CARBON_PRICE, horizon)
    delta_price = carbon_price_delta(
        scenario, horizon, reference_year, override=params.get('carbon_price')
    )
    hazard_multiplier = scenario_value(scenario, KEY_HAZARD_MULTIPLIER, horizon)

    result = _evaluate(snapshot, options, delta_price, hazard_multiplier)
    if result is None:
        warnings.append(
            "Le proxy d'EBITDA est nul ou négatif : ajuster la marge EBITDA."
        )
        return _empty_payload(company, reference_year, scenarios, warnings)

    horizon_curve = []
    for year in HORIZONS:
        point = _evaluate(
            snapshot, options,
            carbon_price_delta(scenario, year, reference_year),
            scenario_value(scenario, KEY_HAZARD_MULTIPLIER, year),
        )
        horizon_curve.append({'year': year,
                              'pd': point['pd_stressed'] if point else None})

    comparison = []
    for other in scenarios:
        point = _evaluate(
            snapshot, options,
            carbon_price_delta(other, horizon, reference_year),
            scenario_value(other, KEY_HAZARD_MULTIPLIER, horizon),
        )
        comparison.append({
            'key': other.key,
            'name': other.name,
            'pd': point['pd_stressed'] if point else None,
            'delta_bps': point['delta_bps'] if point else None,
        })

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'reference_year': reference_year,
        'scenarios': [_scenario_payload(s) for s in scenarios],
        'selected': {
            'scenario': scenario.key,
            'horizon': horizon,
            'carbon_price': round(carbon_price, 2),
            'carbon_price_reference': round(reference_price, 2),
            'hazard_multiplier': round(hazard_multiplier, 4),
            'include_scope3': options['include_scope3'],
            'pass_through': round(options['pass_through'], 4),
            'ebitda_margin': round(options['ebitda_margin'], 4),
            'pd_baseline': round(options['pd_baseline'], 6),
            'ebitda_volatility': round(options['ebitda_volatility'], 4),
            'scope3_transmission': SCOPE3_TRANSMISSION,
        },
        'inputs': {
            'emissions': {
                'scope1': round(snapshot['scope1'], 2),
                'scope2': round(snapshot['scope2'], 2),
                'scope3': round(snapshot['scope3'], 2),
                'retained': result['emissions_retained'],
            },
            'revenue': round(snapshot['revenue'], 2),
            'ebitda_proxy': result['ebitda_proxy'],
            'exposure': round(snapshot['exposure'], 2),
            'asset_count': snapshot['asset_count'],
        },
        'result': {
            'pd_baseline': result['pd_baseline'],
            'pd_stressed': result['pd_stressed'],
            'delta_bps': result['delta_bps'],
            'multiple': result['multiple'],
            'rating_baseline': result['rating_baseline'],
            'rating_stressed': result['rating_stressed'],
            'shock_ratio': result['shock_ratio'],
            'shock_sigma': result['shock_sigma'],
        },
        'waterfall': result['waterfall'],
        'channels': {
            'transition': result['transition'],
            'physical': result['physical'],
        },
        'horizon_curve': horizon_curve,
        'scenario_comparison': comparison,
        'assumptions': _assumptions(
            scenario, horizon, options, carbon_price, reference_price,
            hazard_multiplier,
        ),
        'warnings': warnings,
    }


def _pick(params, key, fallback):
    """Valeur du paramètre si fournie et non nulle, sinon le repli."""
    value = params.get(key)
    return fallback if value is None else float(value)
```

> `_pick` est utilisée avant sa définition dans le fichier ; c'est légal en Python (résolution à l'appel). La placer en fin de module la garde à côté des autres helpers.

- [ ] **Step 4 : Lancer les tests, vérifier qu'ils passent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test`
Expected: PASS

- [ ] **Step 5 : Commit**

```bash
git add dashboard/services/stress_test.py dashboard/tests_stress_test.py
git commit -m "feat(service): orchestration get_stress_test_data (payload complet)"
```

---

### Task 8 : Formulaire de validation

**Files:**
- Create: `dashboard/forms.py`
- Test: `dashboard/tests_stress_test.py`

**Interfaces:**
- Consumes: `HORIZONS` (Task 1) ; `ClimateScenario` (Task 2).
- Produces: `StressTestForm(forms.Form)` — tous les champs optionnels ; `to_params() -> dict` renvoie le dict attendu par `get_stress_test_data`.

- [ ] **Step 1 : Écrire les tests**

Ajouter à `dashboard/tests_stress_test.py` :

```python
from dashboard.forms import StressTestForm


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
```

- [ ] **Step 2 : Lancer les tests, vérifier qu'ils échouent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test.StressTestFormTests`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.forms'`

- [ ] **Step 3 : Implémenter**

Créer `dashboard/forms.py` :

```python
"""Formulaires du dashboard.

Toute entrée utilisateur — y compris les query params d'un endpoint GET —
passe par un formulaire, jamais par une lecture brute de `request.GET`.
"""
from django import forms

from .models import ClimateScenario
from .services.stress_test import HORIZONS


class StressTestForm(forms.Form):
    """Hypothèses du stress test climatique.

    Tous les champs sont optionnels : un champ absent signifie « valeur par
    défaut du scénario ou du profil sectoriel ».
    """

    scenario = forms.CharField(required=False)
    horizon = forms.TypedChoiceField(
        required=False, coerce=int, empty_value=None,
        choices=[(str(year), str(year)) for year in HORIZONS],
    )
    carbon_price = forms.FloatField(required=False, min_value=0.0)
    include_scope3 = forms.BooleanField(required=False)
    pass_through = forms.FloatField(required=False, min_value=0.0, max_value=1.0)
    ebitda_margin = forms.FloatField(required=False, min_value=0.001, max_value=1.0)
    pd_baseline = forms.FloatField(required=False, min_value=1e-6, max_value=0.999)

    def clean_scenario(self):
        key = (self.cleaned_data.get('scenario') or '').strip()
        if not key:
            return None
        try:
            return ClimateScenario.objects.get(key=key)
        except ClimateScenario.DoesNotExist:
            raise forms.ValidationError('Scénario inconnu.')

    def to_params(self):
        """Dict d'hypothèses consommable par `get_stress_test_data`."""
        data = self.cleaned_data
        return {
            'scenario': data.get('scenario'),
            'horizon': data.get('horizon'),
            'carbon_price': data.get('carbon_price'),
            'include_scope3': bool(data.get('include_scope3')),
            'pass_through': data.get('pass_through'),
            'ebitda_margin': data.get('ebitda_margin'),
            'pd_baseline': data.get('pd_baseline'),
        }
```

- [ ] **Step 4 : Lancer les tests, vérifier qu'ils passent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test`
Expected: PASS

- [ ] **Step 5 : Commit**

```bash
git add dashboard/forms.py dashboard/tests_stress_test.py
git commit -m "feat(forms): StressTestForm valide et borne les hypotheses GET"
```

---

### Task 9 : Vues, routes et admin

**Files:**
- Modify: `dashboard/views.py` (fin de fichier + imports)
- Modify: `dashboard/urls.py`
- Modify: `dashboard/admin.py`
- Test: `dashboard/tests_stress_test.py`

**Interfaces:**
- Consumes: `get_stress_test_data` (Task 7), `StressTestForm` (Task 8).
- Produces: `dashboard:climate_stress_test` (`/climate-stress-test/`) et `dashboard:climate_stress_test_data` (`/api/company/<pk>/climate-stress-test/`).

- [ ] **Step 1 : Écrire les tests**

Ajouter à `dashboard/tests_stress_test.py` :

```python
from django.contrib.auth import get_user_model


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

    def test_page_requires_login(self):
        response = self.client.get(self.page_url)
        self.assertEqual(response.status_code, 302)

    def test_api_requires_login(self):
        response = self.client.get(self.api_url)
        self.assertEqual(response.status_code, 302)

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
```

- [ ] **Step 2 : Lancer les tests, vérifier qu'ils échouent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test.ClimateStressTestViewTests`
Expected: FAIL — `NoReverseMatch: 'climate_stress_test' is not a valid view function or pattern name`

- [ ] **Step 3 : Ajouter les vues**

Ajouter l'import en tête de `dashboard/views.py` :

```python
from .forms import StressTestForm
from .services.stress_test import get_stress_test_data
```

Ajouter à la fin de `dashboard/views.py` :

```python
@login_required
@require_GET
def climate_stress_test(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = get_stress_test_data(first)
    return render(request, 'dashboard/climate_stress_test.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@login_required
@require_GET
def climate_stress_test_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    form = StressTestForm(data=request.GET)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    return JsonResponse(get_stress_test_data(company, form.to_params()))
```

- [ ] **Step 4 : Ajouter les routes**

Dans `dashboard/urls.py`, ajouter avant le `]` final :

```python
    path('climate-stress-test/', views.climate_stress_test,
         name='climate_stress_test'),
    path('api/company/<int:pk>/climate-stress-test/',
         views.climate_stress_test_data, name='climate_stress_test_data'),
```

- [ ] **Step 5 : Enregistrer les modèles dans l'admin**

Dans `dashboard/admin.py`, ajouter `ClimateScenario, ScenarioVariable, SectorCreditProfile` à l'import de modèles, puis en fin de fichier :

```python
class ScenarioVariableInline(admin.TabularInline):
    model = ScenarioVariable
    extra = 0


@admin.register(ClimateScenario)
class ClimateScenarioAdmin(admin.ModelAdmin):
    search_fields = ('key', 'name')
    list_display = ('name', 'key', 'family', 'warming_c', 'order')
    list_filter = ('family',)
    ordering = ('order', 'key')
    inlines = (ScenarioVariableInline,)


@admin.register(ScenarioVariable)
class ScenarioVariableAdmin(admin.ModelAdmin):
    search_fields = ('scenario__key', 'scenario__name')
    list_display = ('scenario', 'key', 'year', 'value')
    list_filter = ('key', 'year', 'scenario')
    autocomplete_fields = ('scenario',)


@admin.register(SectorCreditProfile)
class SectorCreditProfileAdmin(admin.ModelAdmin):
    search_fields = ('sector__name', 'sector__NACE_code')
    list_display = ('sector', 'pd_baseline', 'ebitda_margin',
                    'ebitda_volatility', 'carbon_pass_through')
    autocomplete_fields = ('sector',)
```

- [ ] **Step 6 : Créer le squelette de template**

La vue rend un template qui n'existe pas encore. Créer
`dashboard/templates/dashboard/climate_stress_test.html` avec ce contenu minimal,
qui sera intégralement remplacé en Task 10 :

```html
{% extends "base.html" %}

{% block title %}Stress test climatique — Easybiodiv{% endblock %}

{% block content %}
<div class="cst-page"></div>
{{ companies|json_script:"companies-data" }}
{{ initial_data|json_script:"initial-data" }}
{% endblock content %}
```

- [ ] **Step 7 : Lancer les tests, vérifier qu'ils passent**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests_stress_test`
Expected: PASS

- [ ] **Step 8 : Vérifier la suite complète**

Run: `.venv\Scripts\python.exe manage.py test dashboard`
Expected: PASS

- [ ] **Step 9 : Commit**

```bash
git add dashboard/views.py dashboard/urls.py dashboard/admin.py dashboard/templates/dashboard/climate_stress_test.html dashboard/tests_stress_test.py
git commit -m "feat(views): page et endpoint stress test climatique + admin des scenarios"
```

---

### Task 10 : Interface

**Files:**
- Modify: `dashboard/templates/dashboard/climate_stress_test.html` (remplace le squelette de la Task 9)
- Create: `dashboard/static/dashboard/js/climate_stress_test.js`
- Modify: `dashboard/static/dashboard/css/style.css` (fin de fichier)
- Modify: `templates/base.html` (sous-item de navigation, après le `<li>` « Dette écologique », ligne 120)

**Interfaces:**
- Consumes: le payload de `get_stress_test_data` (Task 7) et les routes de la Task 9.
- Produces: rien pour les tâches suivantes.

- [ ] **Step 1 : Ajouter le sous-item de navigation**

Dans `templates/base.html`, après le `<li>` contenant le lien « Dette écologique » (se termine ligne 120) et avant le `</ul>` de `sidebar__nav-sub` :

```html
                <li>
                  <a href="{% url 'dashboard:climate_stress_test' %}"
                     class="sidebar__nav-sublink {% block nav_climate_stress_test %}{% endblock %}"
                     aria-label="Stress test climatique">
                    Stress test climatique
                  </a>
                </li>
```

- [ ] **Step 2 : Écrire le template**

Remplacer intégralement `dashboard/templates/dashboard/climate_stress_test.html` :

```html
{% extends "base.html" %}
{% load static %}

{% block title %}Stress test climatique — Easybiodiv{% endblock %}

{% block nav_risks_open %}open{% endblock %}
{% block nav_climate_stress_test %}active{% endblock %}

{% block header_left %}
<div class="company-combobox" id="company-combobox" role="combobox"
     aria-expanded="false" aria-haspopup="listbox" aria-owns="company-listbox">
  <span class="company-combobox__label label-caps">Entreprise</span>
  <div class="company-combobox__input-wrap">
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <circle cx="6" cy="6" r="4.5" stroke="currentColor" stroke-width="1.3"/>
      <path d="M10 10l2.5 2.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
    </svg>
    <input type="text" id="company-search" class="company-combobox__input"
           placeholder="Rechercher une entreprise…"
           autocomplete="off" aria-autocomplete="list"
           aria-controls="company-listbox" aria-label="Sélectionner une entreprise">
    <svg class="company-combobox__chevron" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M3 5l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
  </div>
  <ul id="company-listbox" class="company-combobox__listbox" role="listbox" hidden></ul>
</div>
{% endblock header_left %}

{% block content %}
<div class="cst-page">

  <p class="cst-warnings" id="cst-warnings" role="status" aria-live="polite" hidden></p>

  <!-- Scénarios -->
  <section class="card cst-scenarios" aria-labelledby="cst-scenarios-title">
    <h2 class="label-caps cst-section-title" id="cst-scenarios-title">
      Scénario de référence
    </h2>
    <div class="cst-scenario-grid" id="cst-scenarios"
         role="radiogroup" aria-labelledby="cst-scenarios-title"></div>
  </section>

  <!-- Hypothèses -->
  <section class="card cst-assumptions" aria-labelledby="cst-hypotheses-title">
    <div class="cst-assumptions__head">
      <h2 class="label-caps cst-section-title" id="cst-hypotheses-title">Hypothèses</h2>
      <button type="button" class="cst-reset" id="cst-reset">
        Réinitialiser aux valeurs du scénario
      </button>
    </div>

    <div class="cst-fields">
      <div class="cst-field">
        <span class="cst-field__label" id="cst-horizon-label">Horizon</span>
        <div class="cst-segmented" role="radiogroup" aria-labelledby="cst-horizon-label"
             id="cst-horizon"></div>
      </div>

      <div class="cst-field">
        <label class="cst-field__label" for="cst-carbon-price">
          Prix du carbone (€/tCO₂e)
        </label>
        <input type="number" id="cst-carbon-price" class="form-input"
               min="0" step="5" inputmode="numeric">
      </div>

      <div class="cst-field">
        <label class="cst-field__label" for="cst-pass-through">
          Répercussion au client — <output id="cst-pass-through-value">30 %</output>
        </label>
        <input type="range" id="cst-pass-through" min="0" max="100" step="5" value="30">
      </div>

      <div class="cst-field">
        <label class="cst-field__label" for="cst-ebitda-margin">
          Marge EBITDA (%)
        </label>
        <input type="number" id="cst-ebitda-margin" class="form-input"
               min="0.1" max="100" step="0.5" inputmode="decimal">
      </div>

      <div class="cst-field">
        <label class="cst-field__label" for="cst-pd-baseline">
          PD initiale (%)
        </label>
        <input type="number" id="cst-pd-baseline" class="form-input"
               min="0.001" max="99" step="0.05" inputmode="decimal">
      </div>

      <div class="cst-field cst-field--check">
        <input type="checkbox" id="cst-scope3">
        <label for="cst-scope3">
          Inclure le scope 3 amont
          <span class="cst-hint" id="cst-scope3-hint"></span>
        </label>
      </div>
    </div>
  </section>

  <!-- KPI -->
  <div class="kpi-row" id="cst-kpis" role="status" aria-live="polite">
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="cst-pd-baseline-kpi">—</div>
      <div class="kpi-card__label label-caps">PD initiale</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="cst-pd-stressed-kpi">—</div>
      <div class="kpi-card__label label-caps">PD stressée</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="cst-delta-kpi">—</div>
      <div class="kpi-card__label label-caps">Écart</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="cst-rating-kpi">—</div>
      <div class="kpi-card__label label-caps">Équivalent notation</div>
    </div>
  </div>

  <!-- Graphiques -->
  <div class="cst-charts">
    <div class="card cst-chart-card">
      <h2 class="label-caps cst-section-title">
        Décomposition du choc
        <span class="cst-tooltip" tabindex="0"
              aria-label="Attribution séquentielle : le canal transition est appliqué avant le canal physique. Le choc total est additif en écarts-types ; seule la répartition en points de base dépend de l'ordre.">ⓘ</span>
      </h2>
      <canvas id="cst-waterfall" height="220"
              aria-label="Décomposition de la probabilité de défaut par canal"></canvas>
    </div>
    <div class="card cst-chart-card">
      <h2 class="label-caps cst-section-title">PD par horizon</h2>
      <canvas id="cst-horizon-chart" height="220"
              aria-label="Probabilité de défaut stressée par horizon"></canvas>
    </div>
  </div>

  <div class="card cst-chart-card">
    <h2 class="label-caps cst-section-title">Comparaison des scénarios</h2>
    <canvas id="cst-comparison" height="200"
            aria-label="Probabilité de défaut stressée par scénario"></canvas>
  </div>

  <!-- Canaux + hypothèses -->
  <div class="cst-bottom">
    <div class="card cst-channels-card">
      <h2 class="label-caps cst-section-title">
        Canaux de risque
        <span class="cst-tooltip" tabindex="0"
              aria-label="La perte physique est la sévérité moyenne des aléas de chaque actif, bornée par son exposition. Elle diffère volontairement du chiffre de la page Risque physique, qui somme les aléas.">ⓘ</span>
      </h2>
      <table class="cst-table">
        <thead>
          <tr><th scope="col">Canal</th><th scope="col">Montant</th>
              <th scope="col">% EBITDA</th><th scope="col">Choc (σ)</th></tr>
        </thead>
        <tbody id="cst-channels"></tbody>
      </table>
    </div>

    <div class="card cst-assumptions-card">
      <h2 class="label-caps cst-section-title">Hypothèses retenues</h2>
      <table class="cst-table">
        <thead>
          <tr><th scope="col">Hypothèse</th><th scope="col">Valeur</th>
              <th scope="col">Source</th></tr>
        </thead>
        <tbody id="cst-assumptions"></tbody>
      </table>
    </div>
  </div>

</div>

{{ companies|json_script:"companies-data" }}
{{ initial_data|json_script:"initial-data" }}
{% endblock content %}

{% block extra_js %}
<script>var CLIMATE_STRESS_TEST_API_URL = "{% url 'dashboard:climate_stress_test_data' pk=0 %}";</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js" defer></script>
<script src="{% static 'dashboard/js/climate_stress_test.js' %}" defer></script>
{% endblock %}
```

> La ligne `CLIMATE_STRESS_TEST_API_URL` reprend exactement le patron de
> `physical_risk.html:108` : l'URL est générée avec `pk=0`, et le JS remplace
> `/0/` par l'identifiant réel. Ne pas construire l'URL à la main côté JS.

- [ ] **Step 3 : Écrire le JS**

Créer `dashboard/static/dashboard/js/climate_stress_test.js` :

```javascript
const CST_COMPANY_KEY = 'selected-company-id'; // partagé avec les pages de risque
const CST_DEBOUNCE_MS = 300;

const CST_COLORS = {
  baseline: '#dac1ba',
  transition: '#af5d43',
  physical: '#91452d',
  accent: '#feb87c',
};

const CST_STATE = {
  companyId: null,
  data: null,
  overrides: {},   // hypothèses surchargées par l'utilisateur
  charts: {},
  timer: null,
};

function cstPct(value, digits) {
  if (value === null || value === undefined) return '—';
  return (value * 100).toFixed(digits === undefined ? 2 : digits) + ' %';
}

function cstEuro(value) {
  if (value === null || value === undefined) return '—';
  return Math.round(value).toLocaleString('fr-FR') + ' €';
}

function cstBps(value) {
  if (value === null || value === undefined) return '—';
  const sign = value > 0 ? '+' : '';
  return sign + Math.round(value).toLocaleString('fr-FR') + ' pb';
}

/* ── Rendu ─────────────────────────────────────────────────────────────── */

function cstRenderScenarios(data) {
  const host = document.getElementById('cst-scenarios');
  host.innerHTML = '';
  const selected = data.selected ? data.selected.scenario : null;

  data.scenarios.forEach((scenario) => {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'cst-scenario' + (scenario.key === selected ? ' is-active' : '');
    card.setAttribute('role', 'radio');
    card.setAttribute('aria-checked', scenario.key === selected ? 'true' : 'false');
    card.dataset.key = scenario.key;
    card.innerHTML =
      '<span class="cst-scenario__name">' + scenario.name + '</span>' +
      '<span class="cst-scenario__family">' + scenario.family_label + '</span>' +
      '<span class="cst-scenario__warming">' +
      scenario.warming_c.toFixed(1).replace('.', ',') + ' °C</span>';
    card.title = scenario.narrative;
    card.addEventListener('click', () => {
      CST_STATE.overrides = { scenario: scenario.key };  // le scénario réinitialise
      cstRefresh();
    });
    host.appendChild(card);
  });
}

function cstRenderHorizons(data) {
  const host = document.getElementById('cst-horizon');
  if (host.children.length) {
    Array.from(host.children).forEach((button) => {
      const active = data.selected && String(data.selected.horizon) === button.dataset.year;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-checked', active ? 'true' : 'false');
    });
    return;
  }
  data.horizon_curve.forEach((point) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'cst-segmented__btn';
    button.setAttribute('role', 'radio');
    button.dataset.year = String(point.year);
    button.textContent = String(point.year);
    button.addEventListener('click', () => {
      CST_STATE.overrides.horizon = point.year;
      delete CST_STATE.overrides.carbon_price; // le prix suit le nouvel horizon
      cstRefresh();
    });
    host.appendChild(button);
  });
  cstRenderHorizons(data);
}

function cstRenderFields(data) {
  if (!data.selected) return;
  const selected = data.selected;

  document.getElementById('cst-carbon-price').value = Math.round(selected.carbon_price);
  document.getElementById('cst-ebitda-margin').value =
    (selected.ebitda_margin * 100).toFixed(1);
  document.getElementById('cst-pd-baseline').value =
    (selected.pd_baseline * 100).toFixed(3);

  const slider = document.getElementById('cst-pass-through');
  slider.value = Math.round(selected.pass_through * 100);
  document.getElementById('cst-pass-through-value').textContent =
    Math.round(selected.pass_through * 100) + ' %';

  document.getElementById('cst-scope3').checked = selected.include_scope3;
  document.getElementById('cst-scope3-hint').textContent =
    '(' + Math.round(selected.scope3_transmission * 100) + ' % du scope 3 amont retenu)';
}

function cstRenderKpis(data) {
  const result = data.result;
  document.getElementById('cst-pd-baseline-kpi').textContent =
    result ? cstPct(result.pd_baseline) : '—';
  document.getElementById('cst-pd-stressed-kpi').textContent =
    result ? cstPct(result.pd_stressed) : '—';
  document.getElementById('cst-delta-kpi').textContent =
    result ? cstBps(result.delta_bps) + ' (×' + result.multiple + ')' : '—';
  document.getElementById('cst-rating-kpi').textContent =
    result ? result.rating_baseline + ' → ' + result.rating_stressed : '—';
}

function cstRenderChannels(data) {
  const body = document.getElementById('cst-channels');
  body.innerHTML = '';
  if (!data.channels) return;

  const rows = [
    ['Transition (coût carbone)', data.channels.transition.cost_eur,
     data.channels.transition.pct_ebitda, data.channels.transition.shock_sigma],
    ['Physique (dommages)', data.channels.physical.loss_eur,
     data.channels.physical.pct_ebitda, data.channels.physical.shock_sigma],
  ];
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<th scope="row">' + row[0] + '</th>' +
      '<td class="data-tabular">' + cstEuro(row[1]) + '</td>' +
      '<td class="data-tabular">' + cstPct(row[2], 1) + '</td>' +
      '<td class="data-tabular">' + row[3].toFixed(3) + '</td>';
    body.appendChild(tr);
  });
}

function cstRenderAssumptions(data) {
  const body = document.getElementById('cst-assumptions');
  body.innerHTML = '';
  data.assumptions.forEach((row) => {
    const tr = document.createElement('tr');
    const source = row.reference
      ? row.source + ' — ' + row.reference
      : row.source;
    tr.innerHTML =
      '<th scope="row">' + row.label + '</th>' +
      '<td class="data-tabular">' + row.value + '</td>' +
      '<td class="cst-source">' + (source || '—') + '</td>';
    body.appendChild(tr);
  });
}

function cstRenderWarnings(data) {
  const host = document.getElementById('cst-warnings');
  if (!data.warnings.length) {
    host.hidden = true;
    return;
  }
  host.hidden = false;
  host.textContent = data.warnings.join(' · ');
}

/* ── Graphiques ────────────────────────────────────────────────────────── */

function cstDestroy(name) {
  if (CST_STATE.charts[name]) {
    CST_STATE.charts[name].destroy();
    delete CST_STATE.charts[name];
  }
}

function cstRenderWaterfall(data) {
  cstDestroy('waterfall');
  if (!data.waterfall.length) return;
  const labels = data.waterfall.map((step) => step.label);
  const values = data.waterfall.map((step) => step.pd * 100);
  CST_STATE.charts.waterfall = new Chart(
    document.getElementById('cst-waterfall'),
    {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'PD (%)',
          data: values,
          backgroundColor: [CST_COLORS.baseline, CST_COLORS.transition,
                            CST_COLORS.physical],
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, title: { display: true, text: 'PD (%)' } } },
      },
    }
  );
}

function cstRenderHorizonChart(data) {
  cstDestroy('horizon');
  if (!data.horizon_curve.length) return;
  CST_STATE.charts.horizon = new Chart(
    document.getElementById('cst-horizon-chart'),
    {
      type: 'line',
      data: {
        labels: data.horizon_curve.map((point) => point.year),
        datasets: [{
          label: 'PD stressée (%)',
          data: data.horizon_curve.map(
            (point) => (point.pd === null ? null : point.pd * 100)
          ),
          borderColor: CST_COLORS.physical,
          backgroundColor: CST_COLORS.accent,
          tension: 0.25,
          fill: false,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, title: { display: true, text: 'PD (%)' } } },
      },
    }
  );
}

function cstRenderComparison(data) {
  cstDestroy('comparison');
  if (!data.scenario_comparison.length) return;
  const selected = data.selected ? data.selected.scenario : null;
  CST_STATE.charts.comparison = new Chart(
    document.getElementById('cst-comparison'),
    {
      type: 'bar',
      data: {
        labels: data.scenario_comparison.map((row) => row.name),
        datasets: [{
          label: 'PD stressée (%)',
          data: data.scenario_comparison.map(
            (row) => (row.pd === null ? null : row.pd * 100)
          ),
          backgroundColor: data.scenario_comparison.map(
            (row) => (row.key === selected ? CST_COLORS.physical : CST_COLORS.baseline)
          ),
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, title: { display: true, text: 'PD (%)' } } },
      },
    }
  );
}

function cstRender(data) {
  CST_STATE.data = data;
  cstRenderWarnings(data);
  cstRenderScenarios(data);
  cstRenderHorizons(data);
  cstRenderFields(data);
  cstRenderKpis(data);
  cstRenderChannels(data);
  cstRenderAssumptions(data);
  cstRenderWaterfall(data);
  cstRenderHorizonChart(data);
  cstRenderComparison(data);
}

/* ── Chargement ────────────────────────────────────────────────────────── */

function cstQueryString() {
  const params = new URLSearchParams();
  const overrides = CST_STATE.overrides;
  Object.keys(overrides).forEach((key) => {
    const value = overrides[key];
    if (value === null || value === undefined || value === false) return;
    params.set(key, value === true ? '1' : String(value));
  });
  const query = params.toString();
  return query ? '?' + query : '';
}

function cstApiUrl(companyId) {
  // Le template expose CLIMATE_STRESS_TEST_API_URL avec pk=0 ; même patron que
  // physical_risk.js.
  return CLIMATE_STRESS_TEST_API_URL.replace('/0/', '/' + companyId + '/')
    + cstQueryString();
}

function cstFetch() {
  if (!CST_STATE.companyId) return;
  fetch(cstApiUrl(CST_STATE.companyId))
    .then((response) => {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    })
    .then(cstRender)
    .catch(() => {
      const host = document.getElementById('cst-warnings');
      host.hidden = false;
      host.textContent = 'Le calcul a échoué. Vérifiez les hypothèses saisies.';
    });
}

function cstRefresh() {
  window.clearTimeout(CST_STATE.timer);
  CST_STATE.timer = window.setTimeout(cstFetch, CST_DEBOUNCE_MS);
}

function cstBindInputs() {
  document.getElementById('cst-carbon-price').addEventListener('input', (event) => {
    CST_STATE.overrides.carbon_price = event.target.value;
    cstRefresh();
  });
  document.getElementById('cst-ebitda-margin').addEventListener('input', (event) => {
    CST_STATE.overrides.ebitda_margin = Number(event.target.value) / 100;
    cstRefresh();
  });
  document.getElementById('cst-pd-baseline').addEventListener('input', (event) => {
    CST_STATE.overrides.pd_baseline = Number(event.target.value) / 100;
    cstRefresh();
  });
  const slider = document.getElementById('cst-pass-through');
  slider.addEventListener('input', (event) => {
    document.getElementById('cst-pass-through-value').textContent =
      event.target.value + ' %';
    CST_STATE.overrides.pass_through = Number(event.target.value) / 100;
    cstRefresh();
  });
  document.getElementById('cst-scope3').addEventListener('change', (event) => {
    CST_STATE.overrides.include_scope3 = event.target.checked;
    cstRefresh();
  });
  document.getElementById('cst-reset').addEventListener('click', () => {
    const scenario = CST_STATE.overrides.scenario;
    const horizon = CST_STATE.overrides.horizon;
    CST_STATE.overrides = {};
    if (scenario) CST_STATE.overrides.scenario = scenario;
    if (horizon) CST_STATE.overrides.horizon = horizon;
    cstRefresh();
  });
}

/* ── Combobox entreprise (même mécanisme que physical_risk.js) ─────────── */

function cstInitCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input = document.getElementById('company-search');
  const listbox = document.getElementById('company-listbox');
  const chevron = combobox && combobox.querySelector('.company-combobox__chevron');
  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData) input.value = initialData.company_name;

  function buildList(filter) {
    const query = filter.toLowerCase();
    listbox.innerHTML = companies
      .filter((c) => c.name.toLowerCase().includes(query))
      .map((c) =>
        '<li role="option" data-id="' + c.id + '" class="company-combobox__option'
        + (c.id === selected ? ' selected' : '') + '">' + escHtml(c.name) + '</li>')
      .join('');
  }
  function openList() {
    buildList(input.value);
    listbox.removeAttribute('hidden');
    combobox.setAttribute('aria-expanded', 'true');
    if (chevron) chevron.style.transform = 'rotate(180deg)';
  }
  function closeList() {
    listbox.setAttribute('hidden', '');
    combobox.setAttribute('aria-expanded', 'false');
    if (chevron) chevron.style.transform = '';
  }

  input.addEventListener('focus', openList);
  input.addEventListener('input', () => { buildList(input.value); openList(); });

  listbox.addEventListener('click', (event) => {
    const option = event.target.closest('[role="option"]');
    if (!option) return;
    selected = parseInt(option.dataset.id, 10);
    input.value = option.textContent;
    closeList();
    localStorage.setItem(CST_COMPANY_KEY, selected);
    CST_STATE.companyId = selected;
    CST_STATE.overrides = {};   // changer d'entreprise repart des valeurs par défaut
    cstFetch();
  });

  document.addEventListener('click', (event) => {
    if (!combobox.contains(event.target)) closeList();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeList();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialEl = document.getElementById('initial-data');
  const initialData = initialEl ? JSON.parse(initialEl.textContent) : null;

  cstBindInputs();

  const savedId = parseInt(localStorage.getItem(CST_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some((c) => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    CST_STATE.companyId = savedId;
    fetch(cstApiUrl(savedId))
      .then((response) => {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then((data) => { cstRender(data); cstInitCombobox(companies, data); })
      .catch(() => cstInitCombobox(companies, initialData));
  } else {
    if (initialData) {
      CST_STATE.companyId = initialData.company_id;
      cstRender(initialData);
    }
    cstInitCombobox(companies, initialData);
  }
});
```

> `escHtml` est une fonction globale définie dans `main.js` (ligne 223), chargé avant ce script par `base.html`. Ne pas la redéfinir.

- [ ] **Step 4 : Ajouter les styles**

Ajouter à la fin de `dashboard/static/dashboard/css/style.css` :

```css
/* ── Stress test climatique ──────────────────────────────────────────── */

.cst-page { display: flex; flex-direction: column; gap: 20px; }

.cst-warnings {
  margin: 0; padding: 10px 14px; border-radius: 8px;
  background: #fdf1e6; color: #7a4324; font-size: 13px;
  border: 1px solid #f0d3bb;
}

.cst-section-title { margin: 0 0 12px; display: flex; align-items: center; gap: 6px; }

.cst-scenario-grid {
  display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
}

.cst-scenario {
  display: flex; flex-direction: column; gap: 3px; padding: 12px;
  border: 1.5px solid var(--color-border, #e4e2dd); border-radius: 10px;
  background: #fff; cursor: pointer; text-align: left; font: inherit;
  transition: border-color .15s ease, background .15s ease;
}
.cst-scenario:hover { border-color: #c9a99f; }
.cst-scenario:focus-visible { outline: 2px solid #91452d; outline-offset: 2px; }
.cst-scenario.is-active { border-color: #91452d; background: #fdf6f3; }

.cst-scenario__name { font-weight: 600; font-size: 14px; color: #2f2622; }
.cst-scenario__family { font-size: 12px; color: #7c6a63; }
.cst-scenario__warming { font-size: 12px; color: #91452d; font-weight: 600; }

.cst-assumptions__head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.cst-reset {
  border: 1px solid #e4e2dd; background: #fff; border-radius: 6px;
  padding: 5px 10px; font-size: 12px; color: #54433e; cursor: pointer;
}
.cst-reset:hover { background: #faf7f4; }

.cst-fields {
  display: grid; gap: 14px; margin-top: 12px;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
}
.cst-field { display: flex; flex-direction: column; gap: 5px; }
.cst-field__label { font-size: 12px; color: #54433e; font-weight: 500; }
.cst-field--check { flex-direction: row; align-items: flex-start; gap: 8px; }
.cst-hint { display: block; font-size: 11px; color: #8a7a73; }

.cst-segmented { display: inline-flex; gap: 4px; }
.cst-segmented__btn {
  border: 1px solid #e4e2dd; background: #fff; border-radius: 6px;
  padding: 5px 12px; font-size: 13px; cursor: pointer; color: #54433e;
}
.cst-segmented__btn.is-active {
  background: #91452d; border-color: #91452d; color: #fff;
}
.cst-segmented__btn:focus-visible { outline: 2px solid #91452d; outline-offset: 2px; }

.cst-charts {
  display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}
.cst-chart-card { padding: 16px; }

.cst-bottom {
  display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}

.cst-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.cst-table th, .cst-table td {
  padding: 7px 8px; text-align: left; border-bottom: 1px solid #f0ede8;
}
.cst-table thead th { font-size: 11px; text-transform: uppercase; color: #8a7a73; }
.cst-table td.data-tabular { text-align: right; font-variant-numeric: tabular-nums; }
.cst-source { color: #8a7a73; font-size: 11px; }

.cst-tooltip { cursor: help; color: #8a7a73; font-size: 13px; }
.cst-tooltip:focus-visible { outline: 2px solid #91452d; outline-offset: 2px; }
```

- [ ] **Step 5 : Lancer la suite complète**

Run: `.venv\Scripts\python.exe manage.py test dashboard`
Expected: PASS

- [ ] **Step 6 : Vérifier la page dans un navigateur**

Run: `.venv\Scripts\python.exe manage.py runserver`
Ouvrir `http://127.0.0.1:8000/climate-stress-test/`, se connecter, puis vérifier :
- les 5 cartes de scénario s'affichent et se sélectionnent au clic ET au clavier ;
- changer d'horizon met à jour le prix carbone et les KPI ;
- le curseur de répercussion à 100 % annule la ligne « Transition » ;
- cocher le scope 3 augmente le coût de transition ;
- « Réinitialiser » restaure les valeurs du scénario ;
- les trois graphiques se redessinent sans empiler d'instances Chart.js ;
- aucune erreur dans la console.

- [ ] **Step 7 : Commit**

```bash
git add dashboard/templates/dashboard/climate_stress_test.html dashboard/static/dashboard/js/climate_stress_test.js dashboard/static/dashboard/css/style.css templates/base.html
git commit -m "feat(front): page stress test climatique (scenarios, hypotheses, waterfall)"
```

---

### Task 11 : Golden

**Files:**
- Modify: `dashboard/tests.py` (liste `GOLDEN_VIEWS`, vers la ligne 1956)
- Create: `dashboard/golden/climate_stress_test.json`

**Interfaces:**
- Consumes: `dashboard:climate_stress_test_data` (Task 9).
- Produces: un snapshot figé de la sortie JSON sur `populate_acme`.

- [ ] **Step 1 : Ajouter la vue à `GOLDEN_VIEWS`**

Dans `dashboard/tests.py`, ajouter à la fin de la liste `GOLDEN_VIEWS` :

```python
    ('climate_stress_test', 'dashboard:climate_stress_test_data'),
```

- [ ] **Step 2 : Lancer le test, vérifier qu'il échoue**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests.GoldenViewOutputTests`
Expected: FAIL — `AssertionError: ... Golden manquant : .../climate_stress_test.json (lancer GOLDEN_RECORD=1)`

- [ ] **Step 3 : Enregistrer le golden**

Run (PowerShell) :
```powershell
$env:GOLDEN_RECORD = '1'
.venv\Scripts\python.exe manage.py test dashboard.tests.GoldenViewOutputTests
Remove-Item Env:\GOLDEN_RECORD
```
Expected: crée `dashboard/golden/climate_stress_test.json`.

- [ ] **Step 4 : Inspecter le golden avant de le figer**

Ouvrir `dashboard/golden/climate_stress_test.json` et vérifier à la main :
- `result.pd_stressed` est strictement supérieur à `result.pd_baseline` et reste dans `]0, 1[` ;
- `channels.transition.cost_eur` et `channels.physical.loss_eur` sont positifs ;
- `channels.physical.loss_ratio` est ≤ 1 ;
- `selected.scenario` vaut `NET_ZERO_2050` (premier par `order`) et `selected.horizon` vaut 2030 ;
- `warnings` est vide (ACME a du CA, des émissions, des actifs et deux profils sectoriels).

Si l'une de ces conditions est fausse, **ne pas figer** : c'est un bug à corriger dans les tâches précédentes.

- [ ] **Step 5 : Relancer en mode vérification**

Run: `.venv\Scripts\python.exe manage.py test dashboard.tests.GoldenViewOutputTests`
Expected: PASS

- [ ] **Step 6 : Lancer la suite complète**

Run: `.venv\Scripts\python.exe manage.py test`
Expected: PASS — toutes les apps.

- [ ] **Step 7 : Commit**

```bash
git add dashboard/tests.py dashboard/golden/climate_stress_test.json
git commit -m "test(golden): fige la sortie JSON du stress test climatique"
```

---

## Vérification finale

- [ ] `.venv\Scripts\python.exe manage.py test` — suite complète verte
- [ ] `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` — aucune migration manquante
- [ ] `git diff main --stat` — aucun fichier hors du périmètre de « File Structure »
- [ ] `requirements.txt` inchangé
- [ ] La page répond sur `/climate-stress-test/` et les trois graphiques se redessinent
