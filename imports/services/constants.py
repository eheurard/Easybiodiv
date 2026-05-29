SHEET_COLUMNS = {
    'Country': [
        'name', 'water_ownership', 'land_ownership', 'water_Governance', 'land_Governance',
    ],
    'SubnationalRegion': ['name', 'description', 'country_name'],
    'Commodity': [
        'name', 'description', 'unit',
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
        'impact_endpoint_ReCiPe2016_human_health',
        'impact_endpoint_ReCiPe2016_ecosystem_diversity',
        'impact_endpoint_ReCiPe2016_resource_availability',
    ],
    'Policy_Type': ['name', 'description'],
    'Policy_Subcategory': ['name', 'description', 'policy_type_name'],
    'Policy_Level': ['name', 'score', 'description', 'subcategory_name', 'policy_type_name'],
    'Company': ['name', 'description'],
    'Asset': [
        'name', 'description', 'latitude', 'longitude',
        'country_name', 'subnational_region_name',
    ],
    'Production': ['asset_name', 'commodity_name', 'year', 'production'],
    'Company_Revenue': ['company_name', 'year', 'revenue', 'currency'],
    'Ownership': ['asset_name', 'company_name', 'ownership', 'description'],
    'Company_Policy': [
        'company_name', 'policy_type_name', 'policy_subcategory_name',
        'policy_level_name', 'policy_date',
    ],
}

# Required (non-empty) fields per sheet
REQUIRED_FIELDS = {
    'Country': ['name', 'water_ownership', 'land_ownership'],
    'SubnationalRegion': ['name', 'country_name'],
    'Commodity': ['name', 'unit'],
    'Policy_Type': ['name'],
    'Policy_Subcategory': ['name', 'policy_type_name'],
    'Policy_Level': ['name', 'subcategory_name', 'policy_type_name'],
    'Company': ['name'],
    'Asset': ['name', 'latitude', 'longitude', 'country_name', 'subnational_region_name'],
    'Production': ['asset_name', 'commodity_name', 'year', 'production'],
    'Company_Revenue': ['company_name', 'year', 'revenue', 'currency'],
    'Ownership': ['asset_name', 'company_name', 'ownership'],
    'Company_Policy': [
        'company_name', 'policy_type_name', 'policy_subcategory_name',
        'policy_level_name', 'policy_date',
    ],
}

# FK fields: col_name -> model_key used for resolution lookup
FK_FIELDS = {
    'SubnationalRegion': {'country_name': 'country'},
    'Asset': {'country_name': 'country', 'subnational_region_name': 'subnational_region'},
    'Production': {'asset_name': 'asset', 'commodity_name': 'commodity'},
    'Company_Revenue': {'company_name': 'company'},
    'Ownership': {'asset_name': 'asset', 'company_name': 'company'},
    'Policy_Subcategory': {'policy_type_name': 'policy_type'},
    'Policy_Level': {'policy_type_name': 'policy_type', 'subcategory_name': 'policy_subcategory'},
    'Company_Policy': {
        'company_name': 'company',
        'policy_type_name': 'policy_type',
        'policy_subcategory_name': 'policy_subcategory',
        'policy_level_name': 'policy_level',
    },
}

# Fields used to detect duplicates (within-file and DB)
DUPLICATE_CRITERIA = {
    'Country': ['name'],
    'SubnationalRegion': ['name', 'country_name'],
    'Commodity': ['name'],
    'Policy_Type': ['name'],
    'Policy_Subcategory': ['name', 'policy_type_name'],
    'Policy_Level': ['name', 'subcategory_name', 'policy_type_name'],
    'Company': ['name'],
    'Asset': ['name', 'country_name'],
    'Production': ['asset_name', 'commodity_name', 'year'],
    'Company_Revenue': ['company_name', 'year'],
    'Ownership': ['asset_name', 'company_name'],
    'Company_Policy': [
        'company_name', 'policy_type_name', 'policy_subcategory_name', 'policy_level_name',
    ],
}

# Save order respects FK dependencies
IMPORT_ORDER = [
    'Country', 'SubnationalRegion', 'Commodity',
    'Policy_Type', 'Policy_Subcategory', 'Policy_Level',
    'Company', 'Asset', 'Production', 'Company_Revenue', 'Ownership', 'Company_Policy',
]

# model_key -> sheet name (for _collect_file_names)
MODEL_KEY_TO_SHEET = {
    'country': 'Country',
    'subnational_region': 'SubnationalRegion',
    'commodity': 'Commodity',
    'policy_type': 'Policy_Type',
    'policy_subcategory': 'Policy_Subcategory',
    'policy_level': 'Policy_Level',
    'company': 'Company',
    'asset': 'Asset',
}
