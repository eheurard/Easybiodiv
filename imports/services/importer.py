from datetime import date

from django.db import transaction
from dashboard.models import (
    Asset, Asset_consumption, Carbon_emission, Commodity, Company, Company_Policy,
    Company_Revenue, Company_Revenue_Sector, Country, Currency, ESG_data, Ownership,
    Policy_Level, Policy_Subcategory, Policy_Type, Production, Sector, SubnationalRegion,
    SubSector,
)
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

def _f(val, default=0.0):
    """Parse a cell value as float, returning default on failure."""
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def _s(val, default=''):
    return val if val else default


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
        country = lookup['country'].get(d['country_name'].lower())
        if not country:
            continue
        obj = SubnationalRegion.objects.create(
            name=d['name'],
            description=_s(d.get('description')),
            country=country,
            restoration_cost_m2=_f(d.get('restoration_cost_m2')),
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
            biodiversity_loss_class=d.get('biodiversity_loss_class') or 'Agriculture',
            impact_midpoint_ReCiPe2016_water_consumption=_f(d.get('impact_midpoint_ReCiPe2016_water_consumption')),
            impact_midpoint_ReCiPe2016_climate_change=_f(d.get('impact_midpoint_ReCiPe2016_climate_change')),
            impact_midpoint_ReCiPe2016_freshwater_ecotoxicity=_f(d.get('impact_midpoint_ReCiPe2016_freshwater_ecotoxicity')),
            impact_midpoint_ReCiPe2016_freshwater_eutrophication=_f(d.get('impact_midpoint_ReCiPe2016_freshwater_eutrophication')),
            impact_midpoint_ReCiPe2016_marine_eutrophication=_f(d.get('impact_midpoint_ReCiPe2016_marine_eutrophication')),
            impact_midpoint_ReCiPe2016_terrestrial_acidification=_f(d.get('impact_midpoint_ReCiPe2016_terrestrial_acidification')),
            impact_midpoint_ReCiPe2016_soil_acidification=_f(d.get('impact_midpoint_ReCiPe2016_soil_acidification')),
            impact_midpoint_ReCiPe2016_ozonedepletion=_f(d.get('impact_midpoint_ReCiPe2016_ozonedepletion')),
            impact_midpoint_ReCiPe2016_resource_depletion_fossil=_f(d.get('impact_midpoint_ReCiPe2016_resource_depletion_fossil')),
            impact_midpoint_ReCiPe2016_resource_depletion_minerals=_f(d.get('impact_midpoint_ReCiPe2016_resource_depletion_minerals')),
            impact_midpoint_ReCiPe2016_land_use=_f(d.get('impact_midpoint_ReCiPe2016_land_use')),
            impact_endpoint_ReCiPe2016_human_health=_f(d.get('impact_endpoint_ReCiPe2016_human_health')),
            impact_endpoint_ReCiPe2016_ecosystem_diversity=_f(d.get('impact_endpoint_ReCiPe2016_ecosystem_diversity')),
            impact_endpoint_ReCiPe2016_resource_availability=_f(d.get('impact_endpoint_ReCiPe2016_resource_availability')),
            impact_endpoint_GBS_terrestrial_dynamic=_f(d.get('impact_endpoint_GBS_terrestrial_dynamic')),
            impact_endpoint_GBS_terrestrial_static=_f(d.get('impact_endpoint_GBS_terrestrial_static')),
            dependency_water=d.get('dependency_water') or 'VL',
            dependency_pollination=d.get('dependency_pollination') or 'VL',
            dependency_soil_quality=d.get('dependency_soil_quality') or 'VL',
            dependency_carbon_sequestration=d.get('dependency_carbon_sequestration') or 'VL',
            dependency_water_purification=d.get('dependency_water_purification') or 'VL',
            dependency_pest_control=d.get('dependency_pest_control') or 'VL',
        )
        lookup['commodity'][d['name'].lower()] = obj
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
        pt = lookup['policy_type'].get(d['policy_type_name'].lower())
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
        country = lookup['country'].get(d['country_name'].lower())
        if not country:
            continue
        region_name = d.get('subnational_region_name', '')
        region = lookup['subnational_region'].get(region_name.lower()) if region_name else None
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
        )
        lookup['asset'][d['name'].lower()] = obj
        created += 1
    return created


def _import_production(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        asset = lookup['asset'].get(d['asset_name'].lower())
        commodity = lookup['commodity'].get(d['commodity_name'].lower())
        if not asset or not commodity:
            continue
        try:
            year = int(d['year'])
            production = float(d['production'])
        except (ValueError, TypeError):
            continue
        Production.objects.create(
            asset=asset,
            commodity=commodity,
            year=year,
            production=production,
            estimated_revenue=_f(d.get('estimated_revenue')),
            scope=d.get('scope') or 'direct',
        )
        created += 1
    return created


def _import_company_revenue(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        company = lookup['company'].get(d['company_name'].lower())
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
        asset = lookup['asset'].get(d['asset_name'].lower())
        company = lookup['company'].get(d['company_name'].lower())
        if not asset or not company:
            continue
        Ownership.objects.create(
            Asset=asset, Company=company,
            ownership=d.get('ownership', ''),
            description=_s(d.get('description')),
        )
        created += 1
    return created


def _import_company_policy(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        company = lookup['company'].get(d['company_name'].lower())
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
            defaults={'policy_date': policy_date},
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
            description=_s(d.get('description')),
        )
        lookup['sector'][d['name'].lower()] = obj
        created += 1
    return created


def _import_subsector(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        sector = lookup['sector'].get(d['sector_name'].lower())
        if not sector:
            continue
        obj = SubSector.objects.create(
            name=d['name'],
            sector=sector,
            NACE_code=_s(d.get('NACE_code')),
            description=_s(d.get('description')),
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


def _import_company_revenue_sector(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        company = lookup['company'].get(d['company_name'].lower())
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


def _import_asset_consumption(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        asset = lookup['asset'].get(d['asset_name'].lower())
        if not asset:
            continue
        Asset_consumption.objects.create(
            asset=asset,
            surface_area=_f(d.get('surface_area')),
            water_consumption=_f(d.get('water_consumption')),
            energy_consumption=_f(d.get('energy_consumption')),
            CO2_emissions=_f(d.get('CO2_emissions')),
            waste_generated=_f(d.get('waste_generated')),
        )
        created += 1
    return created


def _import_esg_data(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        company = lookup['company'].get(d['company_name'].lower())
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
        company = lookup['company'].get(d['company_name'].lower())
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


_IMPORTERS = {
    'Country': _import_country,
    'SubnationalRegion': _import_subnational_region,
    'Commodity': _import_commodity,
    'Policy_Type': _import_policy_type,
    'Policy_Subcategory': _import_policy_subcategory,
    'Policy_Level': _import_policy_level,
    'Currency': _import_currency,
    'Sector': _import_sector,
    'SubSector': _import_subsector,
    'Company': _import_company,
    'Asset': _import_asset,
    'Production': _import_production,
    'Company_Revenue': _import_company_revenue,
    'Ownership': _import_ownership,
    'Company_Policy': _import_company_policy,
    'Company_Revenue_Sector': _import_company_revenue_sector,
    'Asset_consumption': _import_asset_consumption,
    'ESG_data': _import_esg_data,
    'Carbon_emission': _import_carbon_emission,
}


def _build_lookup():
    return {
        'country': {o.name.lower(): o for o in Country.objects.all()},
        'subnational_region': {o.name.lower(): o for o in SubnationalRegion.objects.all()},
        'commodity': {o.name.lower(): o for o in Commodity.objects.all()},
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
    }
