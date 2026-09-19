from collections import defaultdict

import openpyxl
from dashboard.models import (
    Asset, CharacterizationFactor, ClimateScenario,
    Commodity, Company, Company_Policy, Company_Revenue, Company_Revenue_Sector,
    Country, Currency, ENDPOINT_ENVIRONMENT, ESG_data, FLOW_RULES, Flow, FlowKind,
    ImpactCategory, OWNERSHIP_OVERLAP_MESSAGE, Ownership, Policy_Level,
    Policy_Subcategory, Policy_Type, REVENUE_PRODUCTION_ONLY_MESSAGE,
    ScenarioVariable, Sector, SectorCreditProfile, SubnationalRegion, SubSector,
    SUPPLY_SELF_LOOP_MESSAGE, periods_overlap, share_overflow_message, share_overflow_year,
)
from .cells import parse_int, parse_number, parse_optional_year, parse_share
from .constants import (
    AT_LEAST_ONE_OF, CHOICE_FIELDS, DUPLICATE_CRITERIA, ENDPOINT_TYPE_MODEL_KEYS,
    FK_FIELDS, MODEL_KEY_TO_SOURCE, REMOVED_SHEETS, REQUIRED_FIELDS, SHEET_COLUMNS,
)


def parse_file(source):
    """
    Parse an xlsx file (path or file-like object).
    Returns {sheet_name: [{'status': 'ok'|'duplicate'|'error', 'data': {...}, 'message': str}, …]}.
    """
    wb = openpyxl.load_workbook(source)
    file_names = _collect_file_names(wb)
    db_name_cache = _build_db_name_cache()
    context = _build_row_check_context(wb, file_names, db_name_cache)

    result = {}
    for sheet_name in REMOVED_SHEETS:
        if sheet_name in wb.sheetnames:
            result[sheet_name] = [{
                'status': 'error',
                'message': (
                    f"La feuille {sheet_name} n'existe plus : utilisez la feuille Flow."
                ),
                'data': {},
            }]
    for sheet_name in SHEET_COLUMNS:
        if sheet_name not in wb.sheetnames:
            continue
        rows = _parse_sheet(wb[sheet_name], sheet_name, file_names, db_name_cache, context)
        sheet_check = _SHEET_CHECKS.get(sheet_name)
        if sheet_check:
            sheet_check(rows)
        result[sheet_name] = rows
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
        'climate_scenario': keys(ClimateScenario.objects, 'key'),
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
    'ClimateScenario': (ClimateScenario, ['key']),
    'ScenarioVariable': (ScenarioVariable, ['scenario__key', 'year', 'key']),
}


def _existing_keys(sheet_name):
    """Return the set of existing duplicate-key tuples from the DB."""
    if sheet_name in _DUPLICATE_KEYS:
        return _DUPLICATE_KEYS[sheet_name][1]()
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


def _sheet_values(wb, sheet_name, columns):
    """Valeurs texte des colonnes demandées d'une feuille, une tuple par ligne."""
    if sheet_name not in wb.sheetnames:
        return []
    ws = wb[sheet_name]
    header = [c.value for c in ws[1]]
    indexes = [header.index(c) if c in header else None for c in columns]
    values = []
    for row in ws.iter_rows(min_row=2):
        values.append(tuple(
            str(row[i].value).strip()
            if i is not None and i < len(row) and row[i].value is not None else ''
            for i in indexes
        ))
    return values


def _build_row_check_context(wb, file_names, db_name_cache):
    """État partagé par les contrôles propres à une feuille (voir _ROW_CHECKS)
    pendant toute l'analyse d'un classeur."""
    commodity_names = {}  # nom ou clé, en minuscules -> nom de la commodité
    for name, key in Commodity.objects.values_list('name', 'key'):
        commodity_names[name.lower()] = name.lower()
        if key:
            commodity_names[key.lower()] = name.lower()
    for name, key in _sheet_values(wb, 'Commodity', ('name', 'key')):
        if name:
            commodity_names.setdefault(name.lower(), name.lower())
            if key:
                commodity_names.setdefault(key.lower(), name.lower())
    return {
        'file_names': file_names,
        'db_name_cache': db_name_cache,
        'commodity_names': commodity_names,
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


def _sheet_endpoint(value):
    """Type d'extrémité du classeur → type du modèle ('milieu' → environment,
    vide → None)."""
    value = (value or '').strip().lower()
    if not value:
        return None
    return ENDPOINT_ENVIRONMENT if value == 'milieu' else value


# Champs numériques de la feuille Flow : lecteur et facultatif ou non (spec F1).
_FLOW_NUMBER_FIELDS = (
    ('year', parse_int, False),
    ('quantity', parse_number, False),
    ('tier', parse_int, True),
    ('estimated_revenue', parse_number, True),
)


def _flow_number_error(data):
    """Premier champ numérique illisible de la ligne, ou None si tous le sont."""
    for field, parser, optional in _FLOW_NUMBER_FIELDS:
        value = data.get(field, '')
        if optional and not value:
            continue
        try:
            parser(value)
        except ValueError:
            return f"Nombre invalide pour '{field}' : '{value}'"
    return None


def _flow_row_error(data, context):
    """Contrôles de la feuille Flow (spec §6.1) : commodité, nombres, extrémités,
    puis règles FLOW_RULES avec le message même de la contrainte en base."""
    if data['what'].strip().lower() not in context['commodity_names']:
        return f"Commodité introuvable pour 'what' : '{data['what']}' (nom ou clé)"
    number_error = _flow_number_error(data)
    if number_error:
        return number_error
    for side in ('from', 'to'):
        endpoint_type = data.get(f'{side}_type', '').strip().lower()
        name = data.get(f'{side}_name', '').strip()
        if endpoint_type in ('', 'milieu'):
            if name:
                shown = endpoint_type or 'vide'
                return f"'{side}_name' doit rester vide quand '{side}_type' vaut « {shown} »"
            continue
        if not name:
            return f"'{side}_name' est obligatoire quand '{side}_type' vaut « {endpoint_type} »"
        model_key = ENDPOINT_TYPE_MODEL_KEYS[endpoint_type]
        if not _can_resolve(model_key, name, context['file_names'], context['db_name_cache']):
            return f"Valeur introuvable pour '{side}_name' : '{name}'"
    kind = data['kind'].strip().upper()
    rule = FLOW_RULES[kind]
    origin = _sheet_endpoint(data.get('from_type'))
    destination = _sheet_endpoint(data.get('to_type'))
    if origin not in rule.origins or destination not in rule.destinations:
        return rule.message
    same_place = (
        origin is not None and origin == destination
        and data['from_name'].strip().lower() == data['to_name'].strip().lower()
    )
    if kind == FlowKind.SUPPLY.value and same_place:
        return SUPPLY_SELF_LOOP_MESSAGE
    if data.get('estimated_revenue') and kind != FlowKind.PRODUCTION.value:
        return REVENUE_PRODUCTION_ONLY_MESSAGE
    return None


def _flow_duplicate_key(data, context):
    """Clé de doublon normalisée : `what` ramené au nom de la commodité, scope
    vide = 'undefined'."""
    what = data['what'].strip().lower()
    return (
        data['kind'].strip().lower(),
        context['commodity_names'].get(what, what),
        (data.get('scope') or 'undefined').strip().lower(),
        data.get('from_type', '').strip().lower(),
        data.get('from_name', '').strip().lower(),
        data.get('to_type', '').strip().lower(),
        data.get('to_name', '').strip().lower(),
        data.get('year', '').strip(),
    )


def _flow_end(flow, side):
    """(type du classeur, nom en minuscules) d'une extrémité d'un Flow en base."""
    endpoint = flow.origin_type if side == 'from' else flow.destination_type
    if endpoint is None:
        return '', ''
    if endpoint == ENDPOINT_ENVIRONMENT:
        return 'milieu', ''
    return endpoint, getattr(flow, f'{side}_{endpoint}').name.lower()


def _existing_flow_keys():
    keys = set()
    rows = Flow.objects.select_related(
        'what', 'from_asset', 'from_region', 'from_country', 'from_company',
        'to_asset', 'to_region', 'to_country', 'to_company',
    )
    for flow in rows:
        keys.add((
            flow.kind.lower(), flow.what.name.lower(), flow.scope.lower(),
            *_flow_end(flow, 'from'), *_flow_end(flow, 'to'), str(flow.year),
        ))
    return keys


# Contrôles propres à une feuille, appliqués ligne par ligne après les
# énumérations et avant la détection des doublons.
_ROW_CHECKS = {
    'Commodity': _commodity_row_error,
    'Ownership': _ownership_row_error,
    'Flow': _flow_row_error,
}

# Feuilles dont la clé de doublon demande une normalisation : (clé du fichier,
# clés existantes en base).
_DUPLICATE_KEYS = {
    'Flow': (_flow_duplicate_key, _existing_flow_keys),
}


def _mark_error(row, message):
    row['status'] = 'error'
    row['message'] = message


def _ownership_sheet_check(rows):
    """Seconde passe sur la feuille Ownership (spec §6.2) : chaque ligne 'ok' est
    confrontée à la base et aux lignes 'ok' qui la précèdent dans le fichier."""
    holdings = defaultdict(list)  # nom d'actif -> [(entreprise, part, début, fin, ligne)]
    for o in Ownership.objects.select_related('asset', 'company'):
        holdings[o.asset.name.lower()].append(
            (o.company.name.lower(), o.share, o.start_year, o.end_year, None))
    for row in rows:
        if row['status'] != 'ok':
            continue
        d = row['data']
        holdings[d['asset_name'].strip().lower()].append((
            d['company_name'].strip().lower(),
            parse_share(d['share']),
            parse_optional_year(d.get('start_year')),
            parse_optional_year(d.get('end_year')),
            row,
        ))
    for entries in holdings.values():
        for index, (company, share, start, end, row) in enumerate(entries):
            if row is None:
                continue
            kept = [e for e in entries[:index] if e[4] is None or e[4]['status'] == 'ok']
            if any(c == company and periods_overlap((start, end), (s, f))
                   for c, _, s, f, _ in kept):
                _mark_error(row, OWNERSHIP_OVERLAP_MESSAGE)
                continue
            year = share_overflow_year(
                [(sh, s, f) for _, sh, s, f, _ in kept] + [(share, start, end)])
            if year is not None:
                _mark_error(row, share_overflow_message(year))


# Contrôles portant sur toute une feuille, après l'analyse ligne par ligne.
_SHEET_CHECKS = {
    'Ownership': _ownership_sheet_check,
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
        if sheet_name in _DUPLICATE_KEYS:
            key = _DUPLICATE_KEYS[sheet_name][0](data, context)
        else:
            key = tuple(data.get(f, '').strip().lower() for f in dup_criteria)
        if key in existing or key in seen:
            rows_out.append({'status': 'duplicate', 'data': data})
        else:
            seen.add(key)
            rows_out.append({'status': 'ok', 'data': data})

    return rows_out
