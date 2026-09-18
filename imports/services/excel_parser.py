import openpyxl
from dashboard.models import (
    Asset, AssetInventory, Carbon_emission, CharacterizationFactor, ClimateScenario,
    Commodity, Company, Company_Policy, Company_Revenue, Company_Revenue_Sector,
    Country, Currency, ESG_data, Flow, ImpactCategory, Ownership, Policy_Level,
    Policy_Subcategory, Policy_Type, Production, ScenarioVariable, Sector,
    SectorCreditProfile, SubnationalRegion, SubSector,
)
from .cells import parse_optional_year, parse_share
from .constants import (
    AT_LEAST_ONE_OF, CHOICE_FIELDS, DUPLICATE_CRITERIA, FK_FIELDS,
    MODEL_KEY_TO_SOURCE, REQUIRED_FIELDS, SHEET_COLUMNS,
)


def parse_file(source):
    """
    Parse an xlsx file (path or file-like object).
    Returns {sheet_name: [{'status': 'ok'|'duplicate'|'error', 'data': {...}, 'message': str}, …]}.
    """
    wb = openpyxl.load_workbook(source)
    file_names = _collect_file_names(wb)
    db_name_cache = _build_db_name_cache()
    context = _build_row_check_context()

    result = {}
    for sheet_name in SHEET_COLUMNS:
        if sheet_name not in wb.sheetnames:
            continue
        result[sheet_name] = _parse_sheet(
            wb[sheet_name], sheet_name, file_names, db_name_cache, context)
    return result


# ── helpers ──────────────────────────────────────────────────────────────────

def _collect_file_names(wb):
    """
    Build lookup sets of identifiers defined in the file itself, so FK fields can
    reference rows from a sibling sheet in the same upload.
    Returns {model_key: {identifier_lower, …}}.
    """
    file_names = {key: set() for key in MODEL_KEY_TO_SOURCE}
    for model_key, (sheet_name, id_column) in MODEL_KEY_TO_SOURCE.items():
        if sheet_name is None or sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        header = [c.value for c in ws[1]]
        if id_column not in header:
            continue
        id_idx = header.index(id_column)
        for row in ws.iter_rows(min_row=2):
            val = row[id_idx].value if id_idx < len(row) else None
            if val is not None:
                file_names[model_key].add(str(val).strip().lower())
    return file_names


def _build_db_name_cache():
    """
    Fetch all FK-referenced identifier sets from the DB in one go.
    Returns {model_key: {identifier_lower, …}}.
    """
    def keys(qs, field):
        return {str(v).lower() for v in qs.values_list(field, flat=True)}

    return {
        'country': keys(Country.objects, 'name'),
        'subnational_region': keys(SubnationalRegion.objects, 'name'),
        'commodity': keys(Commodity.objects, 'name'),
        'policy_type': keys(Policy_Type.objects, 'name'),
        'policy_subcategory': keys(Policy_Subcategory.objects, 'name'),
        'policy_level': keys(Policy_Level.objects, 'name'),
        'currency': keys(Currency.objects, 'code'),
        'sector': keys(Sector.objects, 'name'),
        'subsector': keys(SubSector.objects, 'name'),
        'company': keys(Company.objects, 'name'),
        'asset': keys(Asset.objects, 'name'),
        'impact_category': keys(ImpactCategory.objects, 'key'),
        'flow': keys(Flow.objects, 'key'),
        'climate_scenario': keys(ClimateScenario.objects, 'key'),
        # Les node_ref sont des poignées locales au fichier : rien à résoudre en base.
        'supply_node': set(),
    }


def _can_resolve(model_key, name, file_names, db_name_cache):
    key = name.strip().lower()
    return key in db_name_cache.get(model_key, set()) or key in file_names.get(model_key, set())


# Clé de doublon existante en base, dans l'ordre de DUPLICATE_CRITERIA.
_EXISTING_KEY_QUERIES = {
    'Country': (Country, ['name']),
    'SubnationalRegion': (SubnationalRegion, ['name', 'country__name']),
    'Commodity': (Commodity, ['name']),
    'CharacterizationFactor': (CharacterizationFactor, [
        'category__key', 'commodity__name', 'country__name', 'region__name',
    ]),
    'Policy_Type': (Policy_Type, ['name']),
    'Policy_Subcategory': (Policy_Subcategory, ['name', 'policy_type__name']),
    'Policy_Level': (Policy_Level, [
        'name', 'subcategory__name', 'subcategory__policy_type__name',
    ]),
    'Currency': (Currency, ['code']),
    'Sector': (Sector, ['name']),
    'SubSector': (SubSector, ['name', 'sector__name']),
    'SectorCreditProfile': (SectorCreditProfile, ['sector__name']),
    'Company': (Company, ['name']),
    'Asset': (Asset, ['name', 'country__name']),
    'AssetInventory': (AssetInventory, ['asset__name', 'flow__key', 'year']),
    'Production': (Production, ['asset__name', 'commodity__name', 'year']),
    'Ownership': (Ownership, ['asset__name', 'company__name', 'start_year']),
    'Company_Revenue': (Company_Revenue, ['company__name', 'year']),
    'Company_Revenue_Sector': (Company_Revenue_Sector, [
        'company__name', 'subsector__name', 'year',
    ]),
    'Company_Policy': (Company_Policy, [
        'company__name',
        'policy_level__subcategory__policy_type__name',
        'policy_level__subcategory__name',
        'policy_level__name',
    ]),
    'ESG_data': (ESG_data, ['company__name', 'year']),
    'Carbon_emission': (Carbon_emission, ['company__name', 'year', 'scope']),
    'ClimateScenario': (ClimateScenario, ['key']),
    'ScenarioVariable': (ScenarioVariable, ['scenario__key', 'year', 'key']),
    # SupplyNode / Exchange : identité locale au fichier (node_ref), donc aucune
    # clé comparable en base. L'idempotence est assurée par le get_or_create
    # de l'importeur.
}


def _existing_keys(sheet_name):
    """Return the set of existing duplicate-key tuples from the DB."""
    entry = _EXISTING_KEY_QUERIES.get(sheet_name)
    if entry is None:
        return set()
    model, fields = entry
    return {
        tuple('' if v is None else str(v).lower() for v in row)
        for row in model.objects.values_list(*fields)
    }


def _choice_error(sheet_name, data):
    """Return an error message if a choice column holds an out-of-range value."""
    for col, allowed in CHOICE_FIELDS.get(sheet_name, {}).items():
        val = data.get(col, '')
        if val and val.lower() not in {a.lower() for a in allowed}:
            return f"Valeur invalide pour '{col}' : '{val}' (attendu : {', '.join(allowed)})"
    return None


def _build_row_check_context():
    """État partagé par les contrôles propres à une feuille (voir _ROW_CHECKS)
    pendant toute l'analyse d'un classeur."""
    return {
        'commodity_key_owner': {
            key.lower(): name.lower()
            for name, key in Commodity.objects.exclude(key=None).values_list('name', 'key')
        },
        'file_commodity_key_owner': {},
    }


def _commodity_row_error(data, context):
    """Commodity.key est unique : une clé déjà prise par une autre commodité, en
    base ou plus haut dans le fichier, ferait échouer tout l'import."""
    key = data.get('key', '').strip().lower()
    if not key:
        return None
    name = data['name'].strip().lower()
    for owners in (context['commodity_key_owner'], context['file_commodity_key_owner']):
        owner = owners.get(key)
        if owner is not None and owner != name:
            return f"Clé déjà utilisée par une autre commodité : '{data['key']}'"
    context['file_commodity_key_owner'].setdefault(key, name)
    return None


def _ownership_row_error(data, context):
    """Part lisible dans ]0, 1] et années cohérentes (spec §6.2)."""
    if parse_share(data.get('share')) is None:
        return (
            f"Part invalide pour 'share' : '{data.get('share')}' "
            "(attendu : 0.75 ou 75%, au plus 1)"
        )
    years = {}
    for column in ('start_year', 'end_year'):
        try:
            years[column] = parse_optional_year(data.get(column))
        except ValueError:
            return f"Année invalide pour '{column}' : '{data.get(column)}'"
    start, end = years['start_year'], years['end_year']
    if start is not None and end is not None and start > end:
        return "L'année de début ('start_year') doit précéder l'année de fin ('end_year')"
    return None


# Contrôles propres à une feuille, appliqués ligne par ligne après les
# énumérations et avant la détection des doublons.
_ROW_CHECKS = {
    'Commodity': _commodity_row_error,
    'Ownership': _ownership_row_error,
}


def _parse_sheet(ws, sheet_name, file_names, db_name_cache, context):
    columns = SHEET_COLUMNS[sheet_name]
    required = REQUIRED_FIELDS[sheet_name]
    fk_fields = FK_FIELDS.get(sheet_name, {})
    dup_criteria = DUPLICATE_CRITERIA[sheet_name]

    existing = _existing_keys(sheet_name)
    seen = set()
    rows_out = []

    header = [c.value for c in ws[1]]
    header_map = {name: idx for idx, name in enumerate(header) if name is not None}

    for ws_row in ws.iter_rows(min_row=2):
        data = {}
        for col_name in columns:
            col_idx = header_map.get(col_name)
            if col_idx is not None and col_idx < len(ws_row):
                cell_val = ws_row[col_idx].value
            else:
                cell_val = None
            data[col_name] = str(cell_val).strip() if cell_val is not None else ''

        if all(v == '' for v in data.values()):
            continue

        # Required fields
        missing = [f for f in required if not data.get(f, '')]
        if missing:
            rows_out.append({
                'status': 'error',
                'message': f"Champs obligatoires manquants : {', '.join(missing)}",
                'data': data,
            })
            continue

        # At-least-one-of groups
        group = AT_LEAST_ONE_OF.get(sheet_name)
        if group and not any(data.get(f, '') for f in group):
            rows_out.append({
                'status': 'error',
                'message': f"Renseignez au moins l'un de : {', '.join(group)}",
                'data': data,
            })
            continue

        # FK resolution
        fk_error = None
        for fk_col, model_key in fk_fields.items():
            val = data.get(fk_col, '')
            if val and not _can_resolve(model_key, val, file_names, db_name_cache):
                fk_error = f"Valeur introuvable pour '{fk_col}' : '{val}'"
                break
        if fk_error:
            rows_out.append({'status': 'error', 'message': fk_error, 'data': data})
            continue

        # Enumerations
        choice_error = _choice_error(sheet_name, data)
        if choice_error:
            rows_out.append({'status': 'error', 'message': choice_error, 'data': data})
            continue

        # Contrôles propres à la feuille
        row_check = _ROW_CHECKS.get(sheet_name)
        row_error = row_check(data, context) if row_check else None
        if row_error:
            rows_out.append({'status': 'error', 'message': row_error, 'data': data})
            continue

        # Duplicate check
        key = tuple(data.get(f, '').strip().lower() for f in dup_criteria)
        if key in existing or key in seen:
            rows_out.append({'status': 'duplicate', 'data': data})
        else:
            seen.add(key)
            rows_out.append({'status': 'ok', 'data': data})

    return rows_out
