"""Export de la base au format du classeur d'import.

Le classeur produit se réimporte tel quel : une feuille par table importable,
mêmes colonnes et mêmes vocabulaires que ceux que le parseur sait lire. Chaque
colonne est écrite comme `imports/services/importer.py` la relit.

Deux usages :

* `build_flow_export(companies)` — la seule feuille Flow, filtrable par
  entreprise (commande `export_flows`) ;
* `build_full_export()` — toutes les feuilles (bouton « Exporter toutes les
  données » de la page Imports).

Les extrémités et clés étrangères voyagent par leur nom : la base d'arrivée doit
connaître les entités citées, ou le classeur doit les déclarer lui-même — ce
que fait l'export complet, qui contient toutes les feuilles de référence.

Hors format d'import, donc hors export : utilisateurs, portefeuilles,
évaluations ESRS E4 et catalogue des catégories d'impact (seedé par migration).
"""
import io
from decimal import Decimal

import openpyxl
from django.db.models import Q

from dashboard.models import (
    ENDPOINT_ENVIRONMENT, Asset, CharacterizationFactor, ClimateScenario, Commodity,
    Company, Company_Policy, Company_Revenue, Company_Revenue_Sector, Country,
    Currency, ESG_data, Flow, Ownership, Policy_Level, Policy_Subcategory,
    Policy_Type, ScenarioVariable, Sector, SectorCreditProfile, SubnationalRegion,
    SubSector,
)

from .constants import SHEET_COLUMNS
from .excel_template import write_header

FLOW_COLUMNS = SHEET_COLUMNS['Flow']
_FLOW_RELATIONS = (
    'what', 'from_asset', 'from_region', 'from_country', 'from_company',
    'to_asset', 'to_region', 'to_country', 'to_company',
)


# ── Feuille Flow ──────────────────────────────────────────────────────────────

def flows_of(companies):
    """Flux rattachés à ces entreprises : ceux qu'elles déclarent elles-mêmes et
    ceux qui partent de leurs actifs ou y arrivent. Sans entreprise, tous."""
    queryset = Flow.objects.select_related(*_FLOW_RELATIONS).order_by('pk')
    if not companies:
        return queryset
    condition = Q()
    for company in companies:
        owned = Asset.objects.owned_by(company).values('pk')
        condition |= (
            Q(from_company=company) | Q(to_company=company)
            | Q(from_asset__in=owned) | Q(to_asset__in=owned)
        )
    return queryset.filter(condition).distinct()


def _endpoint(flow, side):
    """(type, nom) d'une extrémité, dans le vocabulaire du classeur."""
    endpoint = flow.origin_type if side == 'from' else flow.destination_type
    if endpoint is None:
        return '', ''
    if endpoint == ENDPOINT_ENVIRONMENT:
        return 'milieu', ''
    return endpoint, getattr(flow, f'{side}_{endpoint}').name


def flow_row(flow):
    from_type, from_name = _endpoint(flow, 'from')
    to_type, to_name = _endpoint(flow, 'to')
    return {
        'kind': flow.kind,
        'what': flow.what.name,
        'scope': flow.scope,
        'from_type': from_type,
        'from_name': from_name,
        'to_type': to_type,
        'to_name': to_name,
        'year': flow.year,
        'quantity': flow.quantity,
        'tier': flow.tier,
        'estimated_revenue': flow.estimated_revenue,
        'source': flow.source,
        'reference': flow.reference,
    }


# ── Autres feuilles ───────────────────────────────────────────────────────────

def _name(obj):
    """Nom d'une clé étrangère facultative, vide quand elle n'est pas renseignée."""
    return obj.name if obj is not None else ''


def _country_row(c):
    return {
        'name': c.name,
        'water_ownership': c.water_ownership,
        'land_ownership': c.land_ownership,
        'water_governance': c.water_Governance,
        'land_governance': c.land_Governance,
        'restoration_cost_m2': c.restoration_cost_m2,
        'biodiversity_loss_agriculture': c.biodiversity_loss_agriculture,
        'biodiversity_loss_urbanization': c.biodiversity_loss_urbanization,
        'biodiversity_loss_mining': c.biodiversity_loss_mining,
    }


def _region_row(r):
    return {
        'name': r.name, 'country_name': r.country.name,
        'restoration_cost_m2': r.restoration_cost_m2, 'Mean_X': r.Mean_X, 'Mean_Y': r.Mean_Y,
    }


def _commodity_row(c):
    return {column: getattr(c, column) for column in SHEET_COLUMNS['Commodity']}


def _cf_row(cf):
    return {
        'category_key': cf.category.key,
        'commodity_name': cf.commodity.name,
        'country_name': _name(cf.country),
        'subnational_region_name': _name(cf.region),
        'value': cf.value,
        'source': cf.source,
        'reference': cf.reference,
    }


def _policy_subcategory_row(s):
    return {'name': s.name, 'description': s.description,
            'policy_type_name': s.policy_type.name}


def _policy_level_row(level):
    row = {column: getattr(level, column) for column in SHEET_COLUMNS['Policy_Level']
           if column.startswith('vulnerability_')}
    row.update({
        'name': level.name,
        'score': level.score,
        'description': level.description,
        'subcategory_name': level.subcategory.name,
        'policy_type_name': level.subcategory.policy_type.name,
    })
    return row


def _subsector_row(s):
    row = {column: getattr(s, column) for column in SHEET_COLUMNS['SubSector']
           if column != 'sector_name'}
    row['sector_name'] = s.sector.name
    return row


def _credit_profile_row(p):
    row = {column: getattr(p, column) for column in SHEET_COLUMNS['SectorCreditProfile']
           if column != 'sector_name'}
    row['sector_name'] = p.sector.name
    return row


def _asset_row(a):
    row = {column: getattr(a, column) for column in SHEET_COLUMNS['Asset']
           if column not in ('country_name', 'subnational_region_name')}
    row['country_name'] = a.country.name
    row['subnational_region_name'] = _name(a.subnational_region)
    return row


def _ownership_row(o):
    return {
        'asset_name': o.asset.name,
        'company_name': o.company.name,
        'share': o.share,
        'start_year': o.start_year,
        'end_year': o.end_year,
        'description': o.description,
    }


def _revenue_row(r):
    return {'company_name': r.company.name, 'year': r.year,
            'revenue': r.revenue, 'currency': r.currency}


def _revenue_sector_row(r):
    return {
        'company_name': r.company.name,
        'subsector_name': r.subsector.name,
        'sector_name': r.subsector.sector.name,
        'year': r.year,
        'revenue': r.revenue,
    }


def _company_policy_row(p):
    # policy_level est nullable : une politique sans niveau sort avec des noms
    # vides, que l'aperçu d'import signalera, plutôt que d'être écartée en silence.
    level = p.policy_level
    return {
        'company_name': p.company.name,
        'policy_type_name': level.subcategory.policy_type.name if level else '',
        'policy_subcategory_name': level.subcategory.name if level else '',
        'policy_level_name': _name(level),
        # En texte : relue comme date Excel, elle reviendrait « 2024-03-15
        # 00:00:00 », que l'importeur ne sait pas découper.
        'policy_date': p.policy_date.isoformat() if p.policy_date else '',
        'comment': p.comment,
    }


def _esg_row(e):
    return {'company_name': e.company.name, 'year': e.year,
            'employees_number': e.employees_number}


def _scenario_row(s):
    return {column: getattr(s, column) for column in SHEET_COLUMNS['ClimateScenario']}


def _scenario_variable_row(v):
    return {'scenario_key': v.scenario.key, 'year': v.year, 'key': v.key, 'value': v.value}


def _plain_row(sheet_name):
    """Feuille dont chaque colonne porte le nom exact d'un champ du modèle."""
    columns = SHEET_COLUMNS[sheet_name]
    return lambda obj: {column: getattr(obj, column) for column in columns}


# Feuille → (lignes à exporter, conversion d'une ligne). Dans l'ordre du
# classeur, qui est aussi celui de SHEET_COLUMNS.
_SHEETS = {
    'Country': (lambda: Country.objects.order_by('pk'), _country_row),
    'SubnationalRegion': (
        lambda: SubnationalRegion.objects.select_related('country').order_by('pk'),
        _region_row),
    'Commodity': (lambda: Commodity.objects.order_by('pk'), _commodity_row),
    'CharacterizationFactor': (
        lambda: CharacterizationFactor.objects.select_related(
            'category', 'commodity', 'country', 'region').order_by('pk'),
        _cf_row),
    'Policy_Type': (lambda: Policy_Type.objects.order_by('pk'), _plain_row('Policy_Type')),
    'Policy_Subcategory': (
        lambda: Policy_Subcategory.objects.select_related('policy_type').order_by('pk'),
        _policy_subcategory_row),
    'Policy_Level': (
        lambda: Policy_Level.objects.select_related(
            'subcategory__policy_type').order_by('pk'),
        _policy_level_row),
    'Currency': (lambda: Currency.objects.order_by('pk'), _plain_row('Currency')),
    'Sector': (lambda: Sector.objects.order_by('pk'), _plain_row('Sector')),
    'SubSector': (lambda: SubSector.objects.select_related('sector').order_by('pk'),
                  _subsector_row),
    'SectorCreditProfile': (
        lambda: SectorCreditProfile.objects.select_related('sector').order_by('pk'),
        _credit_profile_row),
    'Company': (lambda: Company.objects.order_by('pk'), _plain_row('Company')),
    'Asset': (
        lambda: Asset.objects.select_related('country', 'subnational_region').order_by('pk'),
        _asset_row),
    'Flow': (lambda: flows_of([]), flow_row),
    'Ownership': (
        lambda: Ownership.objects.select_related('asset', 'company').order_by('pk'),
        _ownership_row),
    'Company_Revenue': (
        lambda: Company_Revenue.objects.select_related('company').order_by('pk'),
        _revenue_row),
    'Company_Revenue_Sector': (
        lambda: Company_Revenue_Sector.objects.select_related(
            'company', 'subsector__sector').order_by('pk'),
        _revenue_sector_row),
    'Company_Policy': (
        lambda: Company_Policy.objects.select_related(
            'company', 'policy_level__subcategory__policy_type').order_by('pk'),
        _company_policy_row),
    'ESG_data': (lambda: ESG_data.objects.select_related('company').order_by('pk'),
                 _esg_row),
    'ClimateScenario': (lambda: ClimateScenario.objects.order_by('pk'), _scenario_row),
    'ScenarioVariable': (
        lambda: ScenarioVariable.objects.select_related('scenario').order_by('pk'),
        _scenario_variable_row),
}


def _cell(value):
    """Valeur écrite dans une cellule : vide pour None, texte pour une part
    décimale (garde ses quatre décimales), telle quelle sinon."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return value


def _write_sheet(wb, sheet_name, rows, to_row):
    ws = wb.create_sheet(sheet_name)
    columns = SHEET_COLUMNS[sheet_name]
    write_header(ws, columns)
    count = 0
    for obj in rows:
        row = to_row(obj)
        ws.append([_cell(row.get(column)) for column in columns])
        count += 1
    ws.freeze_panes = 'A2'
    return count


def _save(wb):
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def build_flow_export(companies=None):
    """Classeur à une seule feuille « Flow ». Renvoie (buffer, nombre de lignes)."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    count = _write_sheet(wb, 'Flow', flows_of(companies or []), flow_row)
    return _save(wb), count


def build_full_export():
    """Classeur complet, une feuille par table importable.

    Renvoie (buffer, {feuille: nombre de lignes}).
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    counts = {}
    for sheet_name in SHEET_COLUMNS:
        rows, to_row = _SHEETS[sheet_name]
        counts[sheet_name] = _write_sheet(wb, sheet_name, rows(), to_row)
    return _save(wb), counts
