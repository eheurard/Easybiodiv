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


def physical_loss_ratio(hazard_pairs, multiplier):
    """Part de l'exposition perdue, bornée dans [0, 1].

    `hazard_pairs` : itérable de `(aléa, vulnérabilité)` pour un même actif.
    L'agrégation est multiplicative (dommages indépendants), donc bornée —
    contrairement à la somme utilisée par la vue Risque physique, qui peut
    dépasser 100 % du chiffre d'affaires.
    """
    survival = 1.0
    for hazard, vulnerability in hazard_pairs:
        damage = min(1.0, max(0.0, hazard * vulnerability * multiplier))
        survival *= (1.0 - damage)
    return 1.0 - survival


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


# ── Couche ORM ────────────────────────────────────────────────────────────────
#
# Tout ce qui suit touche la base. Le noyau ci-dessus reste pur.

from ..models import ScenarioVariable  # noqa: E402  (import après le noyau pur)
from ..models import Company_Revenue_Sector, SectorCreditProfile  # noqa: E402

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
