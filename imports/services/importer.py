from django.db import transaction
from dashboard.models import (
    Asset, Commodity, Company, Company_Policy, Company_Revenue,
    Country, Ownership, Policy_Level, Policy_Subcategory, Policy_Type,
    Production, SubnationalRegion,
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


# ── per-sheet import functions ────────────────────────────────────────────────

def _import_country(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        obj = Country.objects.create(
            name=d['name'],
            water_ownership=d.get('water_ownership', ''),
            land_ownership=d.get('land_ownership', ''),
            water_Governance=d.get('water_Governance', ''),
            land_Governance=d.get('land_Governance', ''),
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
            description=d.get('description', ''),
            country=country,
        )
        lookup['subnational_region'][d['name'].lower()] = obj
        created += 1
    return created


def _import_commodity(rows, lookup):
    def _f(val, default=0.0):
        try:
            return float(val) if val else default
        except (ValueError, TypeError):
            return default

    created = 0
    for r in rows:
        d = r['data']
        obj = Commodity.objects.create(
            name=d['name'],
            description=d.get('description', ''),
            unit=d.get('unit', 'tonnes'),
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
            impact_endpoint_ReCiPe2016_human_health=_f(d.get('impact_endpoint_ReCiPe2016_human_health')),
            impact_endpoint_ReCiPe2016_ecosystem_diversity=_f(d.get('impact_endpoint_ReCiPe2016_ecosystem_diversity')),
            impact_endpoint_ReCiPe2016_resource_availability=_f(d.get('impact_endpoint_ReCiPe2016_resource_availability')),
        )
        lookup['commodity'][d['name'].lower()] = obj
        created += 1
    return created


def _import_policy_type(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        obj = Policy_Type.objects.create(name=d['name'], description=d.get('description', ''))
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
            description=d.get('description', ''),
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
            description=d.get('description', ''),
            subcategory=sub,
        )
        level_key = f"{d['policy_type_name'].lower()}|{d['subcategory_name'].lower()}|{d['name'].lower()}"
        lookup['policy_level'][level_key] = obj
        created += 1
    return created


def _import_company(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        obj = Company.objects.create(name=d['name'], description=d.get('description', ''))
        lookup['company'][d['name'].lower()] = obj
        created += 1
    return created


def _import_asset(rows, lookup):
    created = 0
    for r in rows:
        d = r['data']
        country = lookup['country'].get(d['country_name'].lower())
        region = lookup['subnational_region'].get(d['subnational_region_name'].lower())
        if not country or not region:
            continue
        try:
            lat = float(d['latitude'])
            lon = float(d['longitude'])
        except (ValueError, TypeError):
            continue
        obj = Asset.objects.create(
            name=d['name'],
            description=d.get('description', ''),
            latitude=lat,
            longitude=lon,
            country=country,
            subnational_region=region,
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
        Production.objects.create(Asset=asset, commodity=commodity, year=year, production=production)
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
            description=d.get('description', ''),
        )
        created += 1
    return created


def _import_company_policy(rows, lookup):
    from datetime import date
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
        Company_Policy.objects.get_or_create(
            company=company,
            policy_level=policy_level,
            defaults={'policy_date': policy_date},
        )
        created += 1
    return created


_IMPORTERS = {
    'Country': _import_country,
    'SubnationalRegion': _import_subnational_region,
    'Commodity': _import_commodity,
    'Policy_Type': _import_policy_type,
    'Policy_Subcategory': _import_policy_subcategory,
    'Policy_Level': _import_policy_level,
    'Company': _import_company,
    'Asset': _import_asset,
    'Production': _import_production,
    'Company_Revenue': _import_company_revenue,
    'Ownership': _import_ownership,
    'Company_Policy': _import_company_policy,
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
        'company': {o.name.lower(): o for o in Company.objects.all()},
        'asset': {o.name.lower(): o for o in Asset.objects.all()},
    }
