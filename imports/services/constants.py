# ---------------------------------------------------------------------------
# Column definitions — hardcoded for stability, decoupled from model fields
#
# Les valeurs d'énumération ci-dessous sont volontairement écrites en dur plutôt
# qu'importées depuis dashboard.models : le contrat du fichier Excel doit rester
# stable même si le modèle bouge. test_constants.py garde les deux alignés.
# ---------------------------------------------------------------------------

SHEET_COLUMNS = {
    # ── Référentiels géographiques et matières ────────────────────────────────
    'Country': [
        'name', 'water_ownership', 'land_ownership',
        'water_governance', 'land_governance',
        'restoration_cost_m2',
        'biodiversity_loss_agriculture', 'biodiversity_loss_urbanization', 'biodiversity_loss_mining',
    ],
    'SubnationalRegion': [
        'name', 'country_name', 'restoration_cost_m2', 'Mean_X', 'Mean_Y',
    ],
    'Commodity': [
        'name', 'description', 'unit', 'key', 'theme', 'biodiversity_loss_class',
        'dependency_water', 'dependency_pollination', 'dependency_soil_quality',
        'dependency_carbon_sequestration', 'dependency_water_purification', 'dependency_pest_control',
    ],
    # Facteurs de caractérisation ACV, régionalisables.
    # region renseignée → CF régional ; sinon country → CF pays ; sinon → CF global.
    'CharacterizationFactor': [
        'category_key', 'commodity_name', 'country_name', 'subnational_region_name',
        'value', 'source', 'reference',
    ],

    # ── Politiques ────────────────────────────────────────────────────────────
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

    # ── Secteurs et devises ───────────────────────────────────────────────────
    'Currency': ['code', 'name', 'symbol', 'ratio_USD'],
    'Sector': ['name', 'NACE_code'],
    'SubSector': [
        'name', 'sector_name', 'NACE_code',
        'Water_dependency', 'Pollination_dependency', 'Soil_quality_dependency',
        'Carbon_Sequestration', 'Water_purification_dependency', 'Pest_control_dependency',
    ],
    'SectorCreditProfile': [
        'sector_name', 'pd_baseline', 'ebitda_margin', 'ebitda_volatility',
        'carbon_pass_through', 'source', 'reference',
    ],

    # ── Entreprises et actifs ─────────────────────────────────────────────────
    'Company': ['name', 'description', 'isin', 'ticker'],
    'Asset': [
        'name', 'description', 'latitude', 'longitude', 'country_name', 'subnational_region_name',
        'type',
        'risk_water', 'risk_pollination', 'risk_soil_quality', 'risk_carbon_sequestration',
        'risk_water_purification', 'risk_pest_control', 'risk_water_stress', 'risk_wildfire',
        'risk_cyclone', 'risk_drought', 'risk_flood', 'risk_coastal_inundation',
        'risk_heatwave', 'risk_temperature_variation', 'risk_precipitation_variation',
        'near_sensitive_zone', 'sensitive_zone_type', 'sensitive_zone_name',
        'sensitive_zone_area_ha',
    ],
    # ── Graphe d'approvisionnement ────────────────────────────────────────────
    # node_ref est une poignée libre, locale au fichier : elle sert uniquement à
    # relier les lignes Exchange aux lignes SupplyNode du même classeur.
    'SupplyNode': [
        'node_ref', 'asset_name', 'subnational_region_name', 'country_name',
        'commodity_name', 'is_external',
    ],
    'Exchange': [
        'supplier_ref', 'consumer_ref', 'commodity_name', 'quantity', 'year',
        'tier', 'data_confidence',
    ],

    # ── Données d'entreprise ──────────────────────────────────────────────────
    'Ownership': ['asset_name', 'company_name', 'share', 'start_year', 'end_year', 'description'],
    'Company_Revenue': ['company_name', 'year', 'revenue', 'currency'],
    'Company_Revenue_Sector': ['company_name', 'subsector_name', 'sector_name', 'year', 'revenue'],
    'Company_Policy': [
        'company_name', 'policy_type_name', 'policy_subcategory_name', 'policy_level_name',
        'policy_date', 'comment',
    ],
    'ESG_data': ['company_name', 'year', 'employees_number'],
    'Carbon_emission': ['company_name', 'year', 'scope', 'carbon_emission'],

    # ── Stress test climatique ────────────────────────────────────────────────
    'ClimateScenario': [
        'key', 'name', 'family', 'warming_c', 'narrative', 'source', 'reference', 'order',
    ],
    'ScenarioVariable': ['scenario_key', 'year', 'key', 'value'],
}

FK_FIELDS = {
    'SubnationalRegion': {'country_name': 'country'},
    'CharacterizationFactor': {
        'category_key': 'impact_category',
        'commodity_name': 'commodity',
        'country_name': 'country',
        'subnational_region_name': 'subnational_region',
    },
    'Policy_Subcategory': {'policy_type_name': 'policy_type'},
    'Policy_Level': {'subcategory_name': 'policy_subcategory', 'policy_type_name': 'policy_type'},
    'SubSector': {'sector_name': 'sector'},
    'SectorCreditProfile': {'sector_name': 'sector'},
    'Asset': {'country_name': 'country', 'subnational_region_name': 'subnational_region'},
    'SupplyNode': {
        'asset_name': 'asset', 'subnational_region_name': 'subnational_region',
        'country_name': 'country', 'commodity_name': 'commodity',
    },
    'Exchange': {
        'supplier_ref': 'supply_node', 'consumer_ref': 'supply_node',
        'commodity_name': 'commodity',
    },
    'Ownership': {'asset_name': 'asset', 'company_name': 'company'},
    'Company_Revenue': {'company_name': 'company'},
    'Company_Revenue_Sector': {'company_name': 'company', 'subsector_name': 'subsector', 'sector_name': 'sector'},
    'Company_Policy': {
        'company_name': 'company',
        'policy_type_name': 'policy_type',
        'policy_subcategory_name': 'policy_subcategory',
        'policy_level_name': 'policy_level',
    },
    'ESG_data': {'company_name': 'company'},
    'Carbon_emission': {'company_name': 'company'},
    'ScenarioVariable': {'scenario_key': 'climate_scenario'},
}

REQUIRED_FIELDS = {
    'Country': ['name', 'water_ownership', 'land_ownership'],
    'SubnationalRegion': ['name', 'country_name'],
    'Commodity': ['name', 'unit'],
    'CharacterizationFactor': ['category_key', 'commodity_name', 'value'],
    'Policy_Type': ['name'],
    'Policy_Subcategory': ['name', 'policy_type_name'],
    'Policy_Level': ['name', 'subcategory_name', 'policy_type_name'],
    'Currency': ['code', 'name', 'symbol'],
    'Sector': ['name'],
    'SubSector': ['name', 'sector_name'],
    'SectorCreditProfile': ['sector_name'],
    'Company': ['name'],
    'Asset': ['name', 'latitude', 'longitude', 'country_name'],
    'SupplyNode': ['node_ref'],
    'Exchange': ['supplier_ref', 'consumer_ref', 'commodity_name', 'quantity', 'year'],
    'Ownership': ['asset_name', 'company_name', 'share'],
    'Company_Revenue': ['company_name', 'year', 'revenue', 'currency'],
    'Company_Revenue_Sector': ['company_name', 'subsector_name', 'sector_name', 'year', 'revenue'],
    'Company_Policy': [
        'company_name', 'policy_type_name', 'policy_subcategory_name',
        'policy_level_name', 'policy_date',
    ],
    'ESG_data': ['company_name', 'year'],
    'Carbon_emission': ['company_name', 'year', 'scope', 'carbon_emission'],
    'ClimateScenario': ['key', 'name'],
    'ScenarioVariable': ['scenario_key', 'year', 'key', 'value'],
}

DUPLICATE_CRITERIA = {
    'Country': ['name'],
    'SubnationalRegion': ['name', 'country_name'],
    'Commodity': ['name'],
    'CharacterizationFactor': [
        'category_key', 'commodity_name', 'country_name', 'subnational_region_name',
    ],
    'Policy_Type': ['name'],
    'Policy_Subcategory': ['name', 'policy_type_name'],
    'Policy_Level': ['name', 'subcategory_name', 'policy_type_name'],
    'Currency': ['code'],
    'Sector': ['name'],
    'SubSector': ['name', 'sector_name'],
    'SectorCreditProfile': ['sector_name'],
    'Company': ['name'],
    'Asset': ['name', 'country_name'],
    'SupplyNode': ['node_ref'],
    'Exchange': ['supplier_ref', 'consumer_ref', 'commodity_name', 'year'],
    'Ownership': ['asset_name', 'company_name', 'start_year'],
    'Company_Revenue': ['company_name', 'year'],
    'Company_Revenue_Sector': ['company_name', 'subsector_name', 'year'],
    'Company_Policy': [
        'company_name', 'policy_type_name', 'policy_subcategory_name', 'policy_level_name',
    ],
    'ESG_data': ['company_name', 'year'],
    'Carbon_emission': ['company_name', 'year', 'scope'],
    'ClimateScenario': ['key'],
    'ScenarioVariable': ['scenario_key', 'year', 'key'],
}

# Colonnes dont au moins une doit être renseignée. Reflète les contraintes que
# le modèle porte dans clean() — non appelé par objects.create().
AT_LEAST_ONE_OF = {
    # SupplyNode.clean() : un sommet exige asset, region ou country.
    'SupplyNode': ['asset_name', 'subnational_region_name', 'country_name'],
}

# Colonnes dont la valeur doit appartenir à une énumération. Comparaison
# insensible à la casse ; une cellule vide est toujours acceptée (défaut modèle).
CHOICE_FIELDS = {
    'Asset': {
        'type': [
            'Airport', 'Mine', 'Aluminium', 'Factory', 'Forest', 'Office',
            'Paper', 'Refinery', 'Renewable', 'Smelter',
        ],
        'sensitive_zone_type': [
            'NATURA_2000', 'NATIONAL_PROTECTED', 'UNESCO', 'IUCN_KBA', 'OTHER',
        ],
    },
    'Exchange': {'data_confidence': ['asset', 'region', 'country']},
    'ClimateScenario': {
        'family': ['ORDERLY', 'DISORDERLY', 'TOO_LITTLE', 'HOT_HOUSE'],
    },
    'ScenarioVariable': {'key': ['carbon_price', 'hazard_multiplier']},
}

IMPORT_ORDER = [
    'Country', 'SubnationalRegion', 'Commodity', 'CharacterizationFactor',
    'Policy_Type', 'Policy_Subcategory', 'Policy_Level',
    'Currency', 'Sector', 'SubSector', 'SectorCreditProfile',
    'Company', 'Asset',
    'SupplyNode', 'Exchange',
    'Ownership', 'Company_Revenue', 'Company_Revenue_Sector', 'Company_Policy',
    'ESG_data', 'Carbon_emission',
    'ClimateScenario', 'ScenarioVariable',
]

# model_key → (feuille du classeur qui déclare ces valeurs | None, colonne identifiante).
# La feuille à None désigne un catalogue en lecture seule : il n'est pas
# importable, ses clés sont uniquement résolues depuis la base.
MODEL_KEY_TO_SOURCE = {
    'country': ('Country', 'name'),
    'subnational_region': ('SubnationalRegion', 'name'),
    'commodity': ('Commodity', 'name'),
    'policy_type': ('Policy_Type', 'name'),
    'policy_subcategory': ('Policy_Subcategory', 'name'),
    'policy_level': ('Policy_Level', 'name'),
    'currency': ('Currency', 'code'),
    'sector': ('Sector', 'name'),
    'subsector': ('SubSector', 'name'),
    'company': ('Company', 'name'),
    'asset': ('Asset', 'name'),
    'impact_category': (None, 'key'),
    'climate_scenario': ('ClimateScenario', 'key'),
    # node_ref n'a pas d'équivalent stable en base : résolution intra-fichier.
    'supply_node': ('SupplyNode', 'node_ref'),
}
