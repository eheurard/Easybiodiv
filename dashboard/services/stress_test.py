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


# ── Couche ORM ────────────────────────────────────────────────────────────────
#
# Tout ce qui suit touche la base. Le noyau ci-dessus reste pur.

from django.db.models import Max  # noqa: E402

from ..models import ScenarioVariable  # noqa: E402  (import après le noyau pur)
from ..models import Company_Revenue_Sector, SectorCreditProfile  # noqa: E402
from ..models import (  # noqa: E402
    Asset, Carbon_emission, ClimateScenario, Company_Policy, Company_Revenue,
    Production,
)
from .hazards import PHYSICAL_RISKS  # noqa: E402

KEY_CARBON_PRICE = ScenarioVariable.Key.CARBON_PRICE
KEY_HAZARD_MULTIPLIER = ScenarioVariable.Key.HAZARD_MULTIPLIER


def scenario_trajectory(scenario, key, cache=None):
    """`{année: valeur}` pour une variable d'un scénario.

    `cache` : dict optionnel `{(scenario_id, key): trajectoire}` fourni par
    l'appelant (typiquement le temps d'un seul appel à `get_stress_test_data`)
    pour éviter de refaire la même requête plusieurs fois. `None` par défaut
    (comportement inchangé pour tout appelant qui ne le fournit pas).
    """
    if cache is not None:
        cache_key = (scenario.pk, key)
        if cache_key in cache:
            return cache[cache_key]
    trajectory = {
        variable.year: variable.value
        for variable in scenario.variables.filter(key=key)
    }
    if cache is not None:
        cache[cache_key] = trajectory
    return trajectory


def scenario_value(scenario, key, year, cache=None):
    """Valeur d'une variable de scénario à une année quelconque."""
    trajectory = scenario_trajectory(scenario, key, cache=cache)
    return interpolate_trajectory(trajectory, year)


def carbon_price_delta(scenario, year, reference_year, override=None, cache=None):
    """Différentiel de prix carbone entre `year` et `reference_year`, ≥ 0.

    `override` remplace le prix du scénario à l'horizon (curseur utilisateur) ;
    le prix de référence, lui, reste celui du scénario.
    """
    reference = scenario_value(scenario, KEY_CARBON_PRICE, reference_year, cache=cache)
    price = (
        float(override) if override is not None
        else scenario_value(scenario, KEY_CARBON_PRICE, year, cache=cache)
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
    # Cache local (durée de vie = cet appel) des trajectoires de scénario,
    # partagé par tous les appels à `scenario_value`/`carbon_price_delta`
    # ci-dessous : évite de relire la même trajectoire à chaque horizon et à
    # chaque scénario comparé (sinon jusqu'à ~16 requêtes redondantes).
    trajectory_cache = {}
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

    reference_price = scenario_value(
        scenario, KEY_CARBON_PRICE, reference_year, cache=trajectory_cache
    )
    carbon_price = params.get('carbon_price')
    if carbon_price is None:
        carbon_price = scenario_value(
            scenario, KEY_CARBON_PRICE, horizon, cache=trajectory_cache
        )
    delta_price = carbon_price_delta(
        scenario, horizon, reference_year, override=params.get('carbon_price'),
        cache=trajectory_cache,
    )
    hazard_multiplier = scenario_value(
        scenario, KEY_HAZARD_MULTIPLIER, horizon, cache=trajectory_cache
    )

    result = _evaluate(snapshot, options, delta_price, hazard_multiplier)
    if result is None:
        warnings.append(
            "Le proxy d'EBITDA est nul ou négatif : ajuster la marge EBITDA."
        )
        return _empty_payload(company, reference_year, scenarios, warnings)

    horizon_curve = []
    for year in HORIZONS:
        # Le prix carbone saisi par l'utilisateur est un prix ABSOLU épinglé à
        # l'horizon sélectionné : il n'a pas de sens rapporté à un autre
        # horizon (le prix pour 2030 n'est pas un prix pour 2050). Mais le
        # point que l'utilisateur regarde effectivement doit rester cohérent
        # avec le bandeau KPI juste au-dessus, donc on le propage uniquement
        # à l'entrée qui correspond à la sélection courante.
        year_override = params.get('carbon_price') if year == horizon else None
        point = _evaluate(
            snapshot, options,
            carbon_price_delta(scenario, year, reference_year,
                                override=year_override, cache=trajectory_cache),
            scenario_value(scenario, KEY_HAZARD_MULTIPLIER, year, cache=trajectory_cache),
        )
        horizon_curve.append({'year': year,
                              'pd': point['pd_stressed'] if point else None})

    comparison = []
    for other in scenarios:
        # Même raisonnement : un prix pinné par l'utilisateur pour le scénario
        # sélectionné n'est pas transposable à la trajectoire d'un autre
        # scénario ; seule la ligne du scénario réellement sélectionné doit
        # correspondre au bandeau KPI.
        other_override = params.get('carbon_price') if other.key == scenario.key else None
        point = _evaluate(
            snapshot, options,
            carbon_price_delta(other, horizon, reference_year,
                                override=other_override, cache=trajectory_cache),
            scenario_value(other, KEY_HAZARD_MULTIPLIER, horizon, cache=trajectory_cache),
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
