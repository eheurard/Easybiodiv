# ---------------------------------------------------------------------------
# Column definitions — hardcoded for stability, decoupled from model fields
# ---------------------------------------------------------------------------

SHEET_COLUMNS = {
    'Country': [
        'name', 'water_ownership', 'land_ownership',
        'water_governance', 'land_governance',
        'restoration_cost_m2',
        'biodiversity_loss_agriculture', 'biodiversity_loss_urbanization', 'biodiversity_loss_mining',
    ],
    'SubnationalRegion': [
        'name', 'description', 'country_name', 'restoration_cost_m2',
    ],
    'Commodity': [
        'name', 'description', 'unit', 'biodiversity_loss_class',
        'impact_midpoint_ReCiPe2016_water_consumption',
        'impact_midpoint_ReCiPe2016_climate_change',
        'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity',
        'impact_midpoint_ReCiPe2016_freshwater_eutrophication',
        'impact_midpoint_ReCiPe2016_marine_eutrophication',
        'impact_midpoint_ReCiPe2016_terrestrial_acidification',
        'impact_midpoint_ReCiPe2016_soil_acidification',
        'impact_midpoint_ReCiPe2016_ozonedepletion',
        'impact_midpoint_ReCiPe2016_resource_depletion_fossil',
        'impact_midpoint_ReCiPe2016_resource_depletion_minerals',
        'impact_midpoint_ReCiPe2016_land_use',
        'impact_endpoint_ReCiPe2016_human_health',
        'impact_endpoint_ReCiPe2016_ecosystem_diversity',
        'impact_endpoint_ReCiPe2016_resource_availability',
        'impact_endpoint_GBS_terrestrial_dynamic',
        'impact_endpoint_GBS_terrestrial_static',
        'dependency_water', 'dependency_pollination', 'dependency_soil_quality',
        'dependency_carbon_sequestration', 'dependency_water_purification', 'dependency_pest_control',
    ],
    'Policy_Type': ['name', 'description'],
    'Policy_Subcategory': ['name', 'description', 'policy_type_name'],
    'Policy_Level': [
        'name', 'score', 'description', 'subcategory_name', 'policy_type_name',
        'vulnerability_water', 'vulnerability_pollination', 'vulnerability_soil_quality',
        'vulnerability_carbon_sequestration', 'vulnerability_water_purification',
        'vulnerability_pest_control', 'vulnerability_water_stress', 'vulnerability_wildfire',
        'vulnerability_cyclone', 'vulnerability_drought', 'vulnerability_flood',
        'vulnerability_coastal_inundation', 'vulnerability_heatwave',
        'vulnerability_temperature_variation', 'vulnerability_precipitation_variation',
    ],
    'Currency': ['code', 'name', 'symbol', 'ratio_USD'],
    'Sector': ['name', 'NACE_code', 'description'],
    'SubSector': [
        'name', 'sector_name', 'NACE_code', 'description',
        'Water_dependency', 'Pollination_dependency', 'Soil_quality_dependency',
        'Carbon_Sequestration', 'Water_purification_dependency', 'Pest_control_dependency',
    ],
    'Company': ['name', 'description', 'isin', 'ticker'],
    'Asset': [
        'name', 'description', 'latitude', 'longitude', 'country_name', 'subnational_region_name',
        'risk_water', 'risk_pollination', 'risk_soil_quality', 'risk_carbon_sequestration',
        'risk_water_purification', 'risk_pest_control', 'risk_water_stress', 'risk_wildfire',
        'risk_cyclone', 'risk_drought', 'risk_flood', 'risk_coastal_inundation',
        'risk_heatwave', 'risk_temperature_variation', 'risk_precipitation_variation',
    ],
    'Production': [
        'asset_name', 'commodity_name', 'company_name', 'subnational_region_name', 'country_name',
        'scope', 'year', 'production', 'estimated_revenue',
    ],
    'Company_Revenue': ['company_name', 'year', 'revenue', 'currency'],
    'Ownership': ['asset_name', 'company_name', 'ownership', 'description'],
    'Company_Policy': [
        'company_name', 'policy_type_name', 'policy_subcategory_name', 'policy_level_name', 'policy_date',
    ],
    'Company_Revenue_Sector': ['company_name', 'subsector_name', 'sector_name', 'year', 'revenue'],
    'Asset_consumption': [
        'asset_name', 'surface_area', 'water_consumption', 'energy_consumption',
        'CO2_emissions', 'waste_generated',
    ],
    'ESG_data': ['company_name', 'year', 'employees_number'],
    'Carbon_emission': ['company_name', 'year', 'scope', 'carbon_emission'],
}

FK_FIELDS = {
    'SubnationalRegion': {'country_name': 'country'},
    'Policy_Subcategory': {'policy_type_name': 'policy_type'},
    'Policy_Level': {'subcategory_name': 'policy_subcategory', 'policy_type_name': 'policy_type'},
    'SubSector': {'sector_name': 'sector'},
    'Asset': {'country_name': 'country', 'subnational_region_name': 'subnational_region'},
    'Production': {
        'asset_name': 'asset', 'commodity_name': 'commodity', 'company_name': 'company',
        'subnational_region_name': 'subnational_region', 'country_name': 'country',
    },
    'Company_Revenue': {'company_name': 'company'},
    'Ownership': {'asset_name': 'asset', 'company_name': 'company'},
    'Company_Policy': {
        'company_name': 'company',
        'policy_type_name': 'policy_type',
        'policy_subcategory_name': 'policy_subcategory',
        'policy_level_name': 'policy_level',
    },
    'Company_Revenue_Sector': {'company_name': 'company', 'subsector_name': 'subsector', 'sector_name': 'sector'},
    'Asset_consumption': {'asset_name': 'asset'},
    'ESG_data': {'company_name': 'company'},
    'Carbon_emission': {'company_name': 'company'},
}

REQUIRED_FIELDS = {
    'Country': ['name', 'water_ownership', 'land_ownership'],
    'SubnationalRegion': ['name', 'country_name'],
    'Commodity': ['name', 'unit'],
    'Policy_Type': ['name'],
    'Policy_Subcategory': ['name', 'policy_type_name'],
    'Policy_Level': ['name', 'subcategory_name', 'policy_type_name'],
    'Currency': ['code', 'name', 'symbol'],
    'Sector': ['name'],
    'SubSector': ['name', 'sector_name'],
    'Company': ['name'],
    'Asset': ['name', 'latitude', 'longitude', 'country_name'],
    'Production': ['asset_name', 'commodity_name', 'year', 'production'],
    'Company_Revenue': ['company_name', 'year', 'revenue', 'currency'],
    'Ownership': ['asset_name', 'company_name', 'ownership'],
    'Company_Policy': [
        'company_name', 'policy_type_name', 'policy_subcategory_name',
        'policy_level_name', 'policy_date',
    ],
    'Company_Revenue_Sector': ['company_name', 'subsector_name', 'sector_name', 'year', 'revenue'],
    'Asset_consumption': ['asset_name'],
    'ESG_data': ['company_name', 'year'],
    'Carbon_emission': ['company_name', 'year', 'scope', 'carbon_emission'],
}

DUPLICATE_CRITERIA = {
    'Country': ['name'],
    'SubnationalRegion': ['name', 'country_name'],
    'Commodity': ['name'],
    'Policy_Type': ['name'],
    'Policy_Subcategory': ['name', 'policy_type_name'],
    'Policy_Level': ['name', 'subcategory_name', 'policy_type_name'],
    'Currency': ['code'],
    'Sector': ['name'],
    'SubSector': ['name', 'sector_name'],
    'Company': ['name'],
    'Asset': ['name', 'country_name'],
    'Production': ['asset_name', 'commodity_name', 'year'],
    'Company_Revenue': ['company_name', 'year'],
    'Ownership': ['asset_name', 'company_name'],
    'Company_Policy': [
        'company_name', 'policy_type_name', 'policy_subcategory_name', 'policy_level_name',
    ],
    'Company_Revenue_Sector': ['company_name', 'subsector_name', 'year'],
    'Asset_consumption': ['asset_name'],
    'ESG_data': ['company_name', 'year'],
    'Carbon_emission': ['company_name', 'year', 'scope'],
}

IMPORT_ORDER = [
    'Country', 'SubnationalRegion', 'Commodity',
    'Policy_Type', 'Policy_Subcategory', 'Policy_Level',
    'Currency', 'Sector', 'SubSector',
    'Company', 'Asset', 'Production', 'Company_Revenue', 'Ownership', 'Company_Policy',
    'Company_Revenue_Sector', 'Asset_consumption', 'ESG_data', 'Carbon_emission',
]

MODEL_KEY_TO_SHEET = {
    'country': 'Country',
    'subnational_region': 'SubnationalRegion',
    'commodity': 'Commodity',
    'policy_type': 'Policy_Type',
    'policy_subcategory': 'Policy_Subcategory',
    'policy_level': 'Policy_Level',
    'currency': 'Currency',
    'sector': 'Sector',
    'subsector': 'SubSector',
    'company': 'Company',
    'asset': 'Asset',
}
