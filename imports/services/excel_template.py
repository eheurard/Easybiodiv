import io
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from dashboard.models import (
    Asset, ClimateScenario, Commodity, Company, Country, Currency,
    ImpactCategory, Policy_Level, Policy_Subcategory, Policy_Type, Sector,
    SubnationalRegion, SubSector,
)
from .constants import CHOICE_FIELDS, SHEET_COLUMNS

_HEADER_FILL = PatternFill(start_color='1F7A4A', end_color='1F7A4A', fill_type='solid')
_HEADER_FONT = Font(bold=True, color='FFFFFF')
_HEADER_ALIGN = Alignment(horizontal='center')

# Énumérations qui ne sont pas déjà portées par CHOICE_FIELDS, ou dont la
# formulation aide au remplissage.
_EXTRA_ENUMS = {
    'Codes de dépendance': ['VL', 'L', 'M', 'H', 'VH'],
    'Classes de perte de biodiversité': ['Agriculture', 'Urbanisation', 'Mining'],
    'Niveaux de tier': ['0 (direct)', '1', '2', '3 (matière première)'],
    'Booléens': ['TRUE', 'FALSE'],
}


def build_template():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for sheet_name, columns in SHEET_COLUMNS.items():
        ws = wb.create_sheet(sheet_name)
        for col_idx, col_name in enumerate(columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = _HEADER_FONT
            cell.fill = _HEADER_FILL
            cell.alignment = _HEADER_ALIGN
            letter = ws.cell(row=1, column=col_idx).column_letter
            ws.column_dimensions[letter].width = max(len(col_name) + 4, 15)

    _build_reference_sheet(wb)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def _write_column(ws, col_idx, title, sections):
    """Write a titled stack of (section_name, values) blocks in one column."""
    cell = ws.cell(row=1, column=col_idx, value=title)
    cell.font = _HEADER_FONT
    cell.fill = _HEADER_FILL

    row = 2
    bold = Font(bold=True)
    for section_name, values in sections:
        ws.cell(row=row, column=col_idx, value=section_name).font = bold
        row += 1
        for value in values:
            ws.cell(row=row, column=col_idx, value=value)
            row += 1
        row += 1


def _build_reference_sheet(wb):
    ws = wb.create_sheet('_Référence')

    db_sections = [
        ('Countries', Country.objects.values_list('name', flat=True)),
        ('SubnationalRegions', SubnationalRegion.objects.values_list('name', flat=True)),
        ('Commodities', Commodity.objects.values_list('name', flat=True)),
        ('ImpactCategories (category_key)',
         ImpactCategory.objects.values_list('key', flat=True)),
        ('Policy_Types', Policy_Type.objects.values_list('name', flat=True)),
        ('Policy_Subcategories', Policy_Subcategory.objects.values_list('name', flat=True)),
        ('Policy_Levels', Policy_Level.objects.values_list('name', flat=True)),
        ('Currencies', Currency.objects.values_list('code', flat=True)),
        ('Sectors', Sector.objects.values_list('name', flat=True)),
        ('SubSectors', SubSector.objects.values_list('name', flat=True)),
        ('Companies', Company.objects.values_list('name', flat=True)),
        ('Assets', Asset.objects.values_list('name', flat=True)),
        ('ClimateScenarios (scenario_key)',
         ClimateScenario.objects.values_list('key', flat=True)),
    ]

    enum_sections = [
        ("Asset — type", CHOICE_FIELDS['Asset']['type']),
        ("Asset — sensitive_zone_type", CHOICE_FIELDS['Asset']['sensitive_zone_type']),
        ("ClimateScenario — family", CHOICE_FIELDS['ClimateScenario']['family']),
        ("ScenarioVariable — key", CHOICE_FIELDS['ScenarioVariable']['key']),
    ] + list(_EXTRA_ENUMS.items())

    _write_column(ws, 1, 'Valeurs enregistrées en base', db_sections)
    _write_column(ws, 3, 'Valeurs autorisées', enum_sections)

    ws.column_dimensions['A'].width = 46
    ws.column_dimensions['C'].width = 46
