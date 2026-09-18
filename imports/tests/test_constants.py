"""Cohérence interne des tables déclaratives d'import.

`constants.py` écrit les énumérations en dur pour que le contrat du fichier
Excel reste stable ; ces tests garantissent qu'elles ne divergent pas du modèle
et que les tables restent mutuellement cohérentes.
"""
from django.apps import apps
from django.test import SimpleTestCase, TestCase

from dashboard.models import Asset, ClimateScenario, ScenarioVariable
from imports.services.constants import (
    AT_LEAST_ONE_OF, CHOICE_FIELDS, DUPLICATE_CRITERIA, FK_FIELDS, IMPORT_ORDER,
    MODEL_KEY_TO_SOURCE, REQUIRED_FIELDS, SHEET_COLUMNS,
)
from imports.services.excel_parser import _EXISTING_KEY_QUERIES
from imports.services.importer import _IMPORTERS


def _model_choice_values(model, field_name):
    return [c[0] for c in model._meta.get_field(field_name).choices]


class ChoiceFieldsMatchModelTest(SimpleTestCase):
    def test_asset_type(self):
        self.assertEqual(
            CHOICE_FIELDS['Asset']['type'], _model_choice_values(Asset, 'type'))

    def test_asset_sensitive_zone_type(self):
        self.assertEqual(
            CHOICE_FIELDS['Asset']['sensitive_zone_type'],
            _model_choice_values(Asset, 'sensitive_zone_type'))

    def test_climate_scenario_family(self):
        self.assertEqual(
            CHOICE_FIELDS['ClimateScenario']['family'],
            _model_choice_values(ClimateScenario, 'family'))

    def test_scenario_variable_key(self):
        self.assertEqual(
            CHOICE_FIELDS['ScenarioVariable']['key'],
            _model_choice_values(ScenarioVariable, 'key'))


class SheetColumnsMatchModelTest(SimpleTestCase):
    """Une colonne sans champ correspondant fait planter l'import au premier
    objects.create() : c'est ce qui est arrivé quand la migration 0048 a retiré
    `description` de SubnationalRegion, Sector et SubSector."""

    FILE_LOCAL_COLUMNS = {}

    def test_every_column_maps_to_a_model_field(self):
        for sheet_name, columns in SHEET_COLUMNS.items():
            model = apps.get_model('dashboard', sheet_name)
            # Comparaison sans la casse : la colonne water_governance alimente
            # le champ water_Governance.
            fields = {f.name.lower() for f in model._meta.get_fields()}
            skipped = (
                set(FK_FIELDS.get(sheet_name, {}))
                | self.FILE_LOCAL_COLUMNS.get(sheet_name, set())
            )
            for column in columns:
                if column in skipped:
                    continue
                with self.subTest(sheet=sheet_name, column=column):
                    self.assertIn(column.lower(), fields)


class TablesAreConsistentTest(SimpleTestCase):
    def test_every_sheet_has_required_fields(self):
        self.assertEqual(set(REQUIRED_FIELDS), set(SHEET_COLUMNS))

    def test_every_sheet_has_duplicate_criteria(self):
        self.assertEqual(set(DUPLICATE_CRITERIA), set(SHEET_COLUMNS))

    def test_every_sheet_has_an_importer(self):
        self.assertEqual(set(_IMPORTERS), set(SHEET_COLUMNS))

    def test_import_order_covers_every_sheet(self):
        self.assertEqual(set(IMPORT_ORDER), set(SHEET_COLUMNS))
        self.assertEqual(len(IMPORT_ORDER), len(SHEET_COLUMNS))

    def test_declared_columns_exist_in_their_sheet(self):
        tables = {
            'REQUIRED_FIELDS': REQUIRED_FIELDS,
            'DUPLICATE_CRITERIA': DUPLICATE_CRITERIA,
            'FK_FIELDS': FK_FIELDS,
            'CHOICE_FIELDS': CHOICE_FIELDS,
            'AT_LEAST_ONE_OF': AT_LEAST_ONE_OF,
        }
        for table_name, table in tables.items():
            for sheet_name, entry in table.items():
                for column in entry:
                    self.assertIn(
                        column, SHEET_COLUMNS[sheet_name],
                        f'{table_name}[{sheet_name}] référence une colonne absente : {column}')

    def test_fk_model_keys_are_declared(self):
        for sheet_name, mapping in FK_FIELDS.items():
            for column, model_key in mapping.items():
                self.assertIn(
                    model_key, MODEL_KEY_TO_SOURCE,
                    f'{sheet_name}.{column} pointe vers un model_key inconnu : {model_key}')

    def test_model_key_sources_point_to_real_columns(self):
        for model_key, (sheet_name, id_column) in MODEL_KEY_TO_SOURCE.items():
            if sheet_name is None:
                continue
            self.assertIn(sheet_name, SHEET_COLUMNS, model_key)
            self.assertIn(id_column, SHEET_COLUMNS[sheet_name], model_key)

    def test_import_order_respects_fk_dependencies(self):
        position = {name: idx for idx, name in enumerate(IMPORT_ORDER)}
        for sheet_name, mapping in FK_FIELDS.items():
            for column, model_key in mapping.items():
                source_sheet = MODEL_KEY_TO_SOURCE[model_key][0]
                if source_sheet is None or source_sheet == sheet_name:
                    continue
                self.assertLess(
                    position[source_sheet], position[sheet_name],
                    f'{sheet_name} dépend de {source_sheet}, qui doit être importé avant')


class ExistingKeyQueriesTest(TestCase):
    def test_query_fields_match_duplicate_criteria_arity(self):
        for sheet_name, (_model, fields) in _EXISTING_KEY_QUERIES.items():
            self.assertEqual(
                len(fields), len(DUPLICATE_CRITERIA[sheet_name]),
                f'{sheet_name} : la clé en base et la clé du fichier diffèrent en longueur')

    def test_query_fields_are_valid_lookups(self):
        for sheet_name, (model, fields) in _EXISTING_KEY_QUERIES.items():
            with self.subTest(sheet=sheet_name):
                list(model.objects.values_list(*fields)[:1])
