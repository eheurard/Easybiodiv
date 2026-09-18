from datetime import date

from django.db import transaction
from dashboard.models import (
    Asset, Carbon_emission, CharacterizationFactor, ClimateScenario,
    Commodity, Company, Company_Policy, Company_Revenue, Company_Revenue_Sector,
    Country, Currency, ESG_data, Exchange, ImpactCategory, Ownership,
    Policy_Level, Policy_Subcategory, Policy_Type, ScenarioVariable,
    Sector, SectorCreditProfile, SubnationalRegion, SubSector, SupplyNode,
)
from .cells import parse_optional_year, parse_share
from .constants import IMPORT_ORDER


@transaction.atomic
def save_import(parsed_data):
    """
    Save all 'ok' rows from parsed_data in topological order.
    Returns {sheet_name: count_created}.
    """
    counts = {}
    lookup = _build_lookup()

    for sheet_name in IMPORT_ORDER:
        if sheet_name not in parsed_data:
            continue
        ok_rows = [r for r in parsed_data[sheet_name] if r['status'] == 'ok']
        fn = _IMPORTERS[sheet_name]
        count = fn(ok_rows, lookup)
        counts[sheet_name] = count

    return counts


# ── helpers ───────────────────────────────────────────────────────────────────

_TRUE_VALUES = {'1', 'true', 'vrai', 'oui', 'yes', 'y', 'o', 'x'}


def _f(val, default=0.0):
    """Parse a cell value as float, returning default on failure."""
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def _i(val, default=0):
    """Parse a cell value as int, tolerating '2024.0'."""
    try:
        return int(float(val)) if val else default
    except (ValueError, TypeError):
        return default


def _b(val, default=False):
    """Parse a cell value as boolean."""
    if not val:
        return default
    return str(val).strip().lower() in _TRUE_VALUES


def _tier(val):
    """Clamp a tier cell to the model's 0–3 range."""
    return min(3, max(0, _i(val)))


def _s(val, default=''):
    return val if val else default


def _get(lookup, model_key, name):
    """Resolve a FK by its case-insensitive identifier, or None if absent."""
    return lookup[model_key].get(name.lower()) if name else None


# ── per-sheet import functions ────────────────────────────────────────────────

def _import_country(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        obj = Country.objects.create(
            name=d['name'],
            water_ownership=d.get('water_ownership', ''),
            land_ownership=d.get('land_ownership', ''),
            water_Governance=d.get('water_governance', ''),
            land_Governance=d.get('land_governance', ''),
            restoration_cost_m2=_f(d.get('restoration_cost_m2')),
            biodiversity_loss_agriculture=_f(d.get('biodiversity_loss_agriculture')),
            biodiversity_loss_urbanization=_f(d.get('biodiversity_loss_urbanization')),
            biodiversity_loss_mining=_f(d.get('biodiversity_loss_mining')),
        )
        lookup['country'][d['name'].lower()] = obj
        created += 1
    return created


def _import_subnational_region(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        country = _get(lookup, 'country', d['country_name'])
        if not country:
            continue
        obj = SubnationalRegion.objects.create(
            name=d['name'],
            country=country,
            restoration_cost_m2=_f(d.get('restoration_cost_m2')),
            Mean_X=_f(d.get('Mean_X')),
            Mean_Y=_f(d.get('Mean_Y')),
        )
        lookup['subnational_region'][d['name'].lower()] = obj
        created += 1
    return created


def _import_commodity(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        obj = Commodity.objects.create(
            name=d['name'],
            description=_s(d.get('description')),
            unit=d.get('unit') or 'tonnes',
            key=(d.get('key') or '').strip().lower() or None,
            theme=_s(d.get('theme')),
            biodiversity_loss_class=d.get('biodiversity_loss_class') or 'Agriculture',
            dependency_water=d.get('dependency_water') or 'VL',
            dependency_pollination=d.get('dependency_pollination') or 'VL',
            dependency_soil_quality=d.get('dependency_soil_quality') or 'VL',
            dependency_carbon_sequestration=d.get('dependency_carbon_sequestration') or 'VL',
            dependency_water_purification=d.get('dependency_water_purification') or 'VL',
            dependency_pest_control=d.get('dependency_pest_control') or 'VL',
        )
        lookup['commodity'][d['name'].lower()] = obj
        if obj.key:
            lookup['commodity_key'][obj.key] = obj
        created += 1
    return created


def _import_characterization_factor(rows, lookup):
    """Facteur de caractérisation ACV. Le lieu suit la résolution du modèle :
    region renseignée → régional ; sinon country → pays ; sinon → global."""
    created = 0
    for r in rows:
        d = r['data']
        category = _get(lookup, 'impact_category', d['category_key'])
        commodity = _get(lookup, 'commodity', d['commodity_name'])
        if not category or not commodity:
            continue
        _, was_created = CharacterizationFactor.objects.get_or_create(
            category=category,
            commodity=commodity,
            region=_get(lookup, 'subnational_region', d.get('subnational_region_name', '')),
            country=_get(lookup, 'country', d.get('country_name', '')),
            defaults={
                'value': _f(d.get('value')),
                'source': _s(d.get('source')),
                'reference': _s(d.get('reference')),
            },
        )
        if was_created:
            created += 1
    return created


def _import_policy_type(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        obj = Policy_Type.objects.create(name=d['name'], description=_s(d.get('description')))
        lookup['policy_type'][d['name'].lower()] = obj
        created += 1
    return created


def _import_policy_subcategory(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        pt = _get(lookup, 'policy_type', d['policy_type_name'])
        if not pt:
            continue
        obj = Policy_Subcategory.objects.create(
            name=d['name'],
            description=_s(d.get('description')),
            policy_type=pt,
        )
        lookup['policy_subcategory'][f"{d['policy_type_name'].lower()}|{d['name'].lower()}"] = obj
        created += 1
    return created


def _import_policy_level(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        sub_key = f"{d['policy_type_name'].lower()}|{d['subcategory_name'].lower()}"
        sub = lookup['policy_subcategory'].get(sub_key)
        if not sub:
            continue
        score = None
        if d.get('score'):
            try:
                score = float(d['score'])
            except (ValueError, TypeError):
                score = None
        obj = Policy_Level.objects.create(
            name=d['name'],
            score=score,
            description=_s(d.get('description')),
            subcategory=sub,
            vulnerability_water=_f(d.get('vulnerability_water'), 1.0),
            vulnerability_pollination=_f(d.get('vulnerability_pollination'), 1.0),
            vulnerability_soil_quality=_f(d.get('vulnerability_soil_quality'), 1.0),
            vulnerability_carbon_sequestration=_f(d.get('vulnerability_carbon_sequestration'), 1.0),
            vulnerability_water_purification=_f(d.get('vulnerability_water_purification'), 1.0),
            vulnerability_pest_control=_f(d.get('vulnerability_pest_control'), 1.0),
            vulnerability_water_stress=_f(d.get('vulnerability_water_stress'), 1.0),
            vulnerability_wildfire=_f(d.get('vulnerability_wildfire'), 1.0),
            vulnerability_cyclone=_f(d.get('vulnerability_cyclone'), 1.0),
            vulnerability_drought=_f(d.get('vulnerability_drought'), 1.0),
            vulnerability_flood=_f(d.get('vulnerability_flood'), 1.0),
            vulnerability_coastal_inundation=_f(d.get('vulnerability_coastal_inundation'), 1.0),
            vulnerability_heatwave=_f(d.get('vulnerability_heatwave'), 1.0),
            vulnerability_temperature_variation=_f(d.get('vulnerability_temperature_variation'), 1.0),
            vulnerability_precipitation_variation=_f(d.get('vulnerability_precipitation_variation'), 1.0),
        )
        level_key = f"{d['policy_type_name'].lower()}|{d['subcategory_name'].lower()}|{d['name'].lower()}"
        lookup['policy_level'][level_key] = obj
        created += 1
    return created


def _import_company(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        obj = Company.objects.create(
            name=d['name'],
            description=_s(d.get('description')),
            isin=d.get('isin') or '0',
            ticker=d.get('ticker') or '0',
        )
        lookup['company'][d['name'].lower()] = obj
        created += 1
    return created


def _import_asset(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        country = _get(lookup, 'country', d['country_name'])
        if not country:
            continue
        region = _get(lookup, 'subnational_region', d.get('subnational_region_name', ''))
        try:
            lat = float(d['latitude'])
            lon = float(d['longitude'])
        except (ValueError, TypeError):
            continue
        obj = Asset.objects.create(
            name=d['name'],
            description=_s(d.get('description')),
            latitude=lat,
            longitude=lon,
            country=country,
            subnational_region=region,
            type=d.get('type') or 'Factory',
            risk_water=_f(d.get('risk_water')),
            risk_pollination=_f(d.get('risk_pollination')),
            risk_soil_quality=_f(d.get('risk_soil_quality')),
            risk_carbon_sequestration=_f(d.get('risk_carbon_sequestration')),
            risk_water_purification=_f(d.get('risk_water_purification')),
            risk_pest_control=_f(d.get('risk_pest_control')),
            risk_water_stress=_f(d.get('risk_water_stress')),
            risk_wildfire=_f(d.get('risk_wildfire')),
            risk_cyclone=_f(d.get('risk_cyclone')),
            risk_drought=_f(d.get('risk_drought')),
            risk_flood=_f(d.get('risk_flood')),
            risk_coastal_inundation=_f(d.get('risk_coastal_inundation')),
            risk_heatwave=_f(d.get('risk_heatwave')),
            risk_temperature_variation=_f(d.get('risk_temperature_variation')),
            risk_precipitation_variation=_f(d.get('risk_precipitation_variation')),
            near_sensitive_zone=_b(d.get('near_sensitive_zone')),
            sensitive_zone_type=_s(d.get('sensitive_zone_type')),
            sensitive_zone_name=_s(d.get('sensitive_zone_name')),
            sensitive_zone_area_ha=_f(d.get('sensitive_zone_area_ha')),
        )
        lookup['asset'][d['name'].lower()] = obj
        created += 1
    return created


def _import_supply_node(rows, lookup):
    """Crée ou réutilise un sommet du graphe. `node_ref` est une poignée locale
    au fichier ; l'identité en base reste la composition asset/region/country/
    commodity, si bien qu'un nœud déjà présent est réutilisé, pas dupliqué."""
    created = 0
    for r in rows:
        d = r['data']
        obj, was_created = SupplyNode.objects.get_or_create(
            asset=_get(lookup, 'asset', d.get('asset_name', '')),
            region=_get(lookup, 'subnational_region', d.get('subnational_region_name', '')),
            country=_get(lookup, 'country', d.get('country_name', '')),
            commodity=_get(lookup, 'commodity', d.get('commodity_name', '')),
            defaults={
                'name': d['node_ref'],
                'is_external': _b(d.get('is_external')),
            },
        )
        lookup['supply_node'][d['node_ref'].lower()] = obj
        if was_created:
            created += 1
    return created


def _import_exchange(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        supplier = _get(lookup, 'supply_node', d['supplier_ref'])
        consumer = _get(lookup, 'supply_node', d['consumer_ref'])
        commodity = _get(lookup, 'commodity', d['commodity_name'])
        if not supplier or not consumer or not commodity:
            continue
        _, was_created = Exchange.objects.get_or_create(
            supplier=supplier,
            consumer=consumer,
            commodity=commodity,
            year=_i(d.get('year')),
            defaults={
                'quantity': _f(d.get('quantity')),
                'tier': _tier(d.get('tier')),
                # À défaut de valeur explicite, la confiance suit la résolution
                # du nœud fournisseur (asset > region > country).
                'data_confidence': d.get('data_confidence') or supplier.resolution,
            },
        )
        if was_created:
            created += 1
    return created


def _import_company_revenue(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        company = _get(lookup, 'company', d['company_name'])
        if not company:
            continue
        try:
            year = int(d['year'])
            revenue = float(d['revenue'])
        except (ValueError, TypeError):
            continue
        Company_Revenue.objects.create(
            company=company, year=year, revenue=revenue,
            currency=d.get('currency', ''),
        )
        created += 1
    return created


def _import_ownership(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        asset = _get(lookup, 'asset', d['asset_name'])
        company = _get(lookup, 'company', d['company_name'])
        share = parse_share(d.get('share'))
        if not asset or not company or share is None:
            continue
        Ownership.objects.create(
            asset=asset, company=company, share=share,
            start_year=parse_optional_year(d.get('start_year')),
            end_year=parse_optional_year(d.get('end_year')),
            description=_s(d.get('description')),
        )
        created += 1
    return created


def _import_company_policy(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        company = _get(lookup, 'company', d['company_name'])
        level_key = (
            f"{d['policy_type_name'].lower()}|"
            f"{d['policy_subcategory_name'].lower()}|"
            f"{d['policy_level_name'].lower()}"
        )
        policy_level = lookup['policy_level'].get(level_key)
        if not company or not policy_level:
            continue
        try:
            parts = d['policy_date'].split('-')
            policy_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError, AttributeError):
            policy_date = date(2026, 1, 1)
        _, was_created = Company_Policy.objects.get_or_create(
            company=company,
            policy_level=policy_level,
            defaults={'policy_date': policy_date, 'comment': _s(d.get('comment'))},
        )
        if was_created:
            created += 1
    return created


def _import_currency(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        obj, was_created = Currency.objects.get_or_create(
            code=d['code'],
            defaults={
                'name': d.get('name', ''),
                'symbol': d.get('symbol', ''),
                'ratio_USD': _f(d.get('ratio_USD'), 1.0),
            },
        )
        lookup['currency'][d['code'].lower()] = obj
        if was_created:
            created += 1
    return created


def _import_sector(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        obj = Sector.objects.create(
            name=d['name'],
            NACE_code=_s(d.get('NACE_code')),
        )
        lookup['sector'][d['name'].lower()] = obj
        created += 1
    return created


def _import_subsector(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        sector = _get(lookup, 'sector', d['sector_name'])
        if not sector:
            continue
        obj = SubSector.objects.create(
            name=d['name'],
            sector=sector,
            NACE_code=_s(d.get('NACE_code')),
            Water_dependency=d.get('Water_dependency') or 'VL',
            Pollination_dependency=d.get('Pollination_dependency') or 'VL',
            Soil_quality_dependency=d.get('Soil_quality_dependency') or 'VL',
            Carbon_Sequestration=d.get('Carbon_Sequestration') or 'VL',
            Water_purification_dependency=d.get('Water_purification_dependency') or 'VL',
            Pest_control_dependency=d.get('Pest_control_dependency') or 'VL',
        )
        lookup['subsector'][f"{d['sector_name'].lower()}|{d['name'].lower()}"] = obj
        created += 1
    return created


def _import_sector_credit_profile(rows, lookup):
    """Sector est un OneToOneField : get_or_create pour ne pas violer l'unicité."""
    created = 0
    for r in rows:
        d = r['data']
        sector = _get(lookup, 'sector', d['sector_name'])
        if not sector:
            continue
        _, was_created = SectorCreditProfile.objects.get_or_create(
            sector=sector,
            defaults={
                'pd_baseline': _f(d.get('pd_baseline'), 0.015),
                'ebitda_margin': _f(d.get('ebitda_margin'), 0.12),
                'ebitda_volatility': _f(d.get('ebitda_volatility'), 0.25),
                'carbon_pass_through': _f(d.get('carbon_pass_through'), 0.30),
                'source': _s(d.get('source')),
                'reference': _s(d.get('reference')),
            },
        )
        if was_created:
            created += 1
    return created


def _import_company_revenue_sector(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        company = _get(lookup, 'company', d['company_name'])
        subsector_key = f"{d['sector_name'].lower()}|{d['subsector_name'].lower()}"
        subsector = lookup['subsector'].get(subsector_key)
        if not company or not subsector:
            continue
        try:
            year = int(d['year'])
            revenue = float(d['revenue'])
        except (ValueError, TypeError):
            continue
        Company_Revenue_Sector.objects.create(
            company=company, subsector=subsector, year=year, revenue=revenue,
        )
        created += 1
    return created


def _import_esg_data(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        company = _get(lookup, 'company', d['company_name'])
        if not company:
            continue
        try:
            year = int(d['year'])
            employees = int(d.get('employees_number') or 0)
        except (ValueError, TypeError):
            continue
        _, was_created = ESG_data.objects.get_or_create(
            company=company, year=year,
            defaults={'employees_number': employees},
        )
        if was_created:
            created += 1
    return created


def _import_carbon_emission(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        company = _get(lookup, 'company', d['company_name'])
        if not company:
            continue
        try:
            year = int(d['year'])
            emission = float(d['carbon_emission'])
        except (ValueError, TypeError):
            continue
        scope = _s(d.get('scope'))
        _, was_created = Carbon_emission.objects.get_or_create(
            company=company, year=year, scope=scope,
            defaults={'carbon_emission': emission},
        )
        if was_created:
            created += 1
    return created


def _import_climate_scenario(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        obj, was_created = ClimateScenario.objects.get_or_create(
            key=d['key'],
            defaults={
                'name': d['name'],
                'family': d.get('family') or ClimateScenario.Family.ORDERLY,
                'warming_c': _f(d.get('warming_c')),
                'narrative': _s(d.get('narrative')),
                'source': _s(d.get('source')),
                'reference': _s(d.get('reference')),
                'order': _i(d.get('order')),
            },
        )
        lookup['climate_scenario'][d['key'].lower()] = obj
        if was_created:
            created += 1
    return created


def _import_scenario_variable(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        scenario = _get(lookup, 'climate_scenario', d['scenario_key'])
        if not scenario:
            continue
        _, was_created = ScenarioVariable.objects.get_or_create(
            scenario=scenario,
            year=_i(d.get('year')),
            key=d['key'],
            defaults={'value': _f(d.get('value'))},
        )
        if was_created:
            created += 1
    return created


_IMPORTERS = {
    'Country': _import_country,
    'SubnationalRegion': _import_subnational_region,
    'Commodity': _import_commodity,
    'CharacterizationFactor': _import_characterization_factor,
    'Policy_Type': _import_policy_type,
    'Policy_Subcategory': _import_policy_subcategory,
    'Policy_Level': _import_policy_level,
    'Currency': _import_currency,
    'Sector': _import_sector,
    'SubSector': _import_subsector,
    'SectorCreditProfile': _import_sector_credit_profile,
    'Company': _import_company,
    'Asset': _import_asset,
    'SupplyNode': _import_supply_node,
    'Exchange': _import_exchange,
    'Ownership': _import_ownership,
    'Company_Revenue': _import_company_revenue,
    'Company_Revenue_Sector': _import_company_revenue_sector,
    'Company_Policy': _import_company_policy,
    'ESG_data': _import_esg_data,
    'Carbon_emission': _import_carbon_emission,
    'ClimateScenario': _import_climate_scenario,
    'ScenarioVariable': _import_scenario_variable,
}


def _build_lookup():
    return {
        'country': {o.name.lower(): o for o in Country.objects.all()},
        'subnational_region': {o.name.lower(): o for o in SubnationalRegion.objects.all()},
        'commodity': {o.name.lower(): o for o in Commodity.objects.all()},
        'commodity_key': {o.key.lower(): o for o in Commodity.objects.exclude(key=None)},
        'impact_category': {o.key.lower(): o for o in ImpactCategory.objects.all()},
        'policy_type': {o.name.lower(): o for o in Policy_Type.objects.all()},
        'policy_subcategory': {
            f"{o.policy_type.name.lower()}|{o.name.lower()}": o
            for o in Policy_Subcategory.objects.select_related('policy_type').all()
        },
        'policy_level': {
            f"{o.subcategory.policy_type.name.lower()}|{o.subcategory.name.lower()}|{o.name.lower()}": o
            for o in Policy_Level.objects.select_related('subcategory__policy_type').all()
        },
        'currency': {o.code.lower(): o for o in Currency.objects.all()},
        'sector': {o.name.lower(): o for o in Sector.objects.all()},
        'subsector': {
            f"{o.sector.name.lower()}|{o.name.lower()}": o
            for o in SubSector.objects.select_related('sector').all()
        },
        'company': {o.name.lower(): o for o in Company.objects.all()},
        'asset': {o.name.lower(): o for o in Asset.objects.all()},
        'climate_scenario': {o.key.lower(): o for o in ClimateScenario.objects.all()},
        # Poignées locales au fichier, remplies par _import_supply_node.
        'supply_node': {},
    }
