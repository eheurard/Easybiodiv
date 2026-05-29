# Excel Import — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow CREATOR users to download an Excel template, fill it, and import all dashboard data models via a preview → confirm workflow.

**Architecture:** New `imports` Django app with a `services/` layer (template generator, parser, importer). Upload parses the file immediately, stores result as a JSON temp file, keyed by UUID in the session. Preview reads from JSON; confirm saves to DB and deletes the JSON.

**Tech Stack:** Django 6, openpyxl (xlsx read/write), Django sessions (UUID key), Django TestCase.

---

## File Map

| Action | Path |
|--------|------|
| Create | `imports/__init__.py` |
| Create | `imports/apps.py` |
| Create | `imports/urls.py` |
| Create | `imports/views.py` |
| Create | `imports/decorators.py` |
| Create | `imports/services/__init__.py` |
| Create | `imports/services/constants.py` |
| Create | `imports/services/excel_template.py` |
| Create | `imports/services/excel_parser.py` |
| Create | `imports/services/importer.py` |
| Create | `imports/templates/imports/index.html` |
| Create | `imports/templates/imports/preview.html` |
| Create | `imports/tests/__init__.py` |
| Create | `imports/tests/test_excel_template.py` |
| Create | `imports/tests/test_excel_parser.py` |
| Create | `imports/tests/test_views.py` |
| Modify | `requirements.txt` |
| Modify | `easybiodiv/settings.py` |
| Modify | `easybiodiv/urls.py` |
| Modify | `templates/base.html` |

---

### Task 1: Setup — app skeleton, requirements, settings, URLs

**Files:**
- Create: `imports/__init__.py`
- Create: `imports/apps.py`
- Create: `imports/urls.py`
- Create: `imports/tests/__init__.py`
- Create: `imports/services/__init__.py`
- Modify: `requirements.txt`
- Modify: `easybiodiv/settings.py`
- Modify: `easybiodiv/urls.py`

- [ ] **Step 1: Add openpyxl to requirements.txt**

Append `openpyxl` as a new line at the end of `requirements.txt`.

Run: `pip install openpyxl`

- [ ] **Step 2: Create app skeleton files**

Create `imports/__init__.py` — empty file.

Create `imports/services/__init__.py` — empty file.

Create `imports/tests/__init__.py` — empty file.

Create `imports/apps.py`:
```python
from django.apps import AppConfig

class ImportsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'imports'
```

Create `imports/urls.py`:
```python
from django.urls import path
from . import views

app_name = 'imports'

urlpatterns = [
    path('', views.index, name='index'),
    path('template/', views.download_template, name='download_template'),
    path('upload/', views.upload, name='upload'),
    path('preview/', views.preview, name='preview'),
    path('confirm/', views.confirm, name='confirm'),
]
```

- [ ] **Step 3: Register app and add MEDIA_ROOT + LOGIN_URL to settings**

In `easybiodiv/settings.py`, change:
```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'authentication',
    'dashboard',]
```
to:
```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'authentication',
    'dashboard',
    'imports',
]
```

At the bottom of `easybiodiv/settings.py`, add:
```python
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_URL = '/auth/login/'
```

- [ ] **Step 4: Wire imports URLs into main urls.py**

In `easybiodiv/urls.py`, change:
```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('authentication.urls')),
    path('', include('dashboard.urls')),
]
```
to:
```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('authentication.urls')),
    path('imports/', include('imports.urls')),
    path('', include('dashboard.urls')),
]
```

- [ ] **Step 5: Create a placeholder views.py so the server starts**

Create `imports/views.py`:
```python
from django.http import HttpResponse

def index(request):
    return HttpResponse('imports index — WIP')

def download_template(request):
    return HttpResponse('download_template — WIP')

def upload(request):
    return HttpResponse('upload — WIP')

def preview(request):
    return HttpResponse('preview — WIP')

def confirm(request):
    return HttpResponse('confirm — WIP')
```

- [ ] **Step 6: Verify server starts**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 7: Commit**

```bash
git add imports/ easybiodiv/settings.py easybiodiv/urls.py requirements.txt
git commit -m "feat(imports): scaffold imports app with placeholder views"
```

---

### Task 2: `@creator_required` decorator

**Files:**
- Create: `imports/decorators.py`
- Create: `imports/tests/test_decorators.py`

- [ ] **Step 1: Write failing tests**

Create `imports/tests/test_decorators.py`:
```python
from django.test import TestCase, RequestFactory
from django.http import HttpResponse, HttpResponseForbidden
from authentication.models import User
from imports.decorators import creator_required


def _dummy_view(request):
    return HttpResponse('ok')


class CreatorRequiredTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.creator = User.objects.create_user('creator', password='pass', role='CREATOR')
        self.subscriber = User.objects.create_user('sub', password='pass', role='SUBSCRIBER')

    def test_anonymous_redirects_to_login(self):
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.get('/imports/')
        request.user = AnonymousUser()
        wrapped = creator_required(_dummy_view)
        response = wrapped(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response['Location'])

    def test_subscriber_gets_403(self):
        request = self.factory.get('/imports/')
        request.user = self.subscriber
        wrapped = creator_required(_dummy_view)
        response = wrapped(request)
        self.assertEqual(response.status_code, 403)

    def test_creator_passes_through(self):
        request = self.factory.get('/imports/')
        request.user = self.creator
        wrapped = creator_required(_dummy_view)
        response = wrapped(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'ok')
```

- [ ] **Step 2: Run to confirm failure**

Run: `python manage.py test imports.tests.test_decorators`
Expected: `ImportError` — `cannot import name 'creator_required'`

- [ ] **Step 3: Implement the decorator**

Create `imports/decorators.py`:
```python
from functools import wraps
from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def creator_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if request.user.role != 'CREATOR':
            return HttpResponseForbidden('Accès réservé aux créateurs.')
        return view_func(request, *args, **kwargs)
    return wrapper
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `python manage.py test imports.tests.test_decorators`
Expected: `OK` — 3 tests passed

- [ ] **Step 5: Commit**

```bash
git add imports/decorators.py imports/tests/test_decorators.py
git commit -m "feat(imports): add creator_required decorator with tests"
```

---

### Task 3: Constants

**Files:**
- Create: `imports/services/constants.py`

No tests needed — pure data, validated implicitly by later tasks.

- [ ] **Step 1: Create constants.py**

Create `imports/services/constants.py`:
```python
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
```

- [ ] **Step 2: Commit**

```bash
git add imports/services/constants.py
git commit -m "feat(imports): add service constants (sheet columns, FK maps, import order)"
```

---

### Task 4: Excel template generator

**Files:**
- Create: `imports/services/excel_template.py`
- Create: `imports/tests/test_excel_template.py`

- [ ] **Step 1: Write failing tests**

Create `imports/tests/test_excel_template.py`:
```python
import io
import openpyxl
from django.test import TestCase
from imports.services.constants import SHEET_COLUMNS
from imports.services.excel_template import build_template


class BuildTemplateTest(TestCase):
    def setUp(self):
        self.buffer = build_template()
        self.wb = openpyxl.load_workbook(self.buffer)

    def test_all_data_sheets_present(self):
        for sheet_name in SHEET_COLUMNS:
            self.assertIn(sheet_name, self.wb.sheetnames, f'Missing sheet: {sheet_name}')

    def test_reference_sheet_present(self):
        self.assertIn('_Référence', self.wb.sheetnames)

    def test_sheet_headers_match_constants(self):
        for sheet_name, expected_cols in SHEET_COLUMNS.items():
            ws = self.wb[sheet_name]
            actual_headers = [ws.cell(1, i + 1).value for i in range(len(expected_cols))]
            self.assertEqual(actual_headers, expected_cols, f'Wrong headers in {sheet_name}')

    def test_returns_bytes_buffer(self):
        buf = build_template()
        self.assertIsInstance(buf, io.BytesIO)
        self.assertGreater(len(buf.getvalue()), 0)
```

- [ ] **Step 2: Run to confirm failure**

Run: `python manage.py test imports.tests.test_excel_template`
Expected: `ImportError` — `cannot import name 'build_template'`

- [ ] **Step 3: Implement excel_template.py**

Create `imports/services/excel_template.py`:
```python
import io
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from dashboard.models import (
    Asset, Commodity, Company, Country, Policy_Level, Policy_Subcategory,
    Policy_Type, SubnationalRegion,
)
from .constants import SHEET_COLUMNS

_HEADER_FILL = PatternFill(start_color='1F7A4A', end_color='1F7A4A', fill_type='solid')
_HEADER_FONT = Font(bold=True, color='FFFFFF')
_HEADER_ALIGN = Alignment(horizontal='center')


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


def _build_reference_sheet(wb):
    ws = wb.create_sheet('_Référence')
    bold = Font(bold=True)
    sections = [
        ('Countries', Country.objects.values_list('name', flat=True)),
        ('SubnationalRegions', SubnationalRegion.objects.values_list('name', flat=True)),
        ('Commodities', Commodity.objects.values_list('name', flat=True)),
        ('Policy_Types', Policy_Type.objects.values_list('name', flat=True)),
        ('Policy_Subcategories', Policy_Subcategory.objects.values_list('name', flat=True)),
        ('Policy_Levels', Policy_Level.objects.values_list('name', flat=True)),
        ('Companies', Company.objects.values_list('name', flat=True)),
        ('Assets', Asset.objects.values_list('name', flat=True)),
    ]
    row = 1
    for section_name, qs in sections:
        ws.cell(row=row, column=1, value=section_name).font = bold
        row += 1
        for name in qs:
            ws.cell(row=row, column=1, value=name)
            row += 1
        row += 1
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `python manage.py test imports.tests.test_excel_template`
Expected: `OK` — 4 tests passed

- [ ] **Step 5: Commit**

```bash
git add imports/services/excel_template.py imports/tests/test_excel_template.py
git commit -m "feat(imports): implement Excel template generator with tests"
```

---

### Task 5: Excel parser

**Files:**
- Create: `imports/services/excel_parser.py`
- Create: `imports/tests/test_excel_parser.py`

- [ ] **Step 1: Write failing tests**

Create `imports/tests/test_excel_parser.py`:
```python
import io
import openpyxl
from django.test import TestCase
from dashboard.models import Country, SubnationalRegion, Policy_Type, Policy_Subcategory
from imports.services.excel_parser import parse_file


def _make_xlsx(sheet_data):
    """Build an in-memory .xlsx from {sheet_name: [[header…], [row…], …]}."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sheet_name, rows in sheet_data.items():
        ws = wb.create_sheet(sheet_name)
        for r_idx, row in enumerate(rows, 1):
            for c_idx, val in enumerate(row, 1):
                ws.cell(r_idx, c_idx, val)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class ParserCountryTest(TestCase):
    def test_valid_row_is_ok(self):
        buf = _make_xlsx({'Country': [
            ['name', 'water_ownership', 'land_ownership', 'water_Governance', 'land_Governance'],
            ['France', 'public', 'private', '', ''],
        ]})
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'ok')
        self.assertEqual(result['Country'][0]['data']['name'], 'France')

    def test_missing_required_field_is_error(self):
        buf = _make_xlsx({'Country': [
            ['name', 'water_ownership', 'land_ownership', 'water_Governance', 'land_Governance'],
            ['', 'public', 'private', '', ''],
        ]})
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'error')
        self.assertIn('name', result['Country'][0]['message'])

    def test_existing_db_record_is_duplicate(self):
        Country.objects.create(name='France', water_ownership='pub', land_ownership='priv')
        buf = _make_xlsx({'Country': [
            ['name', 'water_ownership', 'land_ownership', 'water_Governance', 'land_Governance'],
            ['France', 'public', 'private', '', ''],
        ]})
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'duplicate')

    def test_case_insensitive_duplicate_detection(self):
        Country.objects.create(name='France', water_ownership='pub', land_ownership='priv')
        buf = _make_xlsx({'Country': [
            ['name', 'water_ownership', 'land_ownership', 'water_Governance', 'land_Governance'],
            ['FRANCE', 'public', 'private', '', ''],
        ]})
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'duplicate')

    def test_within_file_duplicate_is_duplicate(self):
        buf = _make_xlsx({'Country': [
            ['name', 'water_ownership', 'land_ownership', 'water_Governance', 'land_Governance'],
            ['France', 'public', 'private', '', ''],
            ['France', 'public', 'private', '', ''],
        ]})
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'ok')
        self.assertEqual(result['Country'][1]['status'], 'duplicate')

    def test_empty_rows_are_skipped(self):
        buf = _make_xlsx({'Country': [
            ['name', 'water_ownership', 'land_ownership', 'water_Governance', 'land_Governance'],
            ['', '', '', '', ''],
        ]})
        result = parse_file(buf)
        self.assertEqual(result['Country'], [])


class ParserFKTest(TestCase):
    def test_invalid_fk_is_error(self):
        buf = _make_xlsx({'SubnationalRegion': [
            ['name', 'description', 'country_name'],
            ['Bretagne', '', 'NonExistent'],
        ]})
        result = parse_file(buf)
        self.assertEqual(result['SubnationalRegion'][0]['status'], 'error')
        self.assertIn('country_name', result['SubnationalRegion'][0]['message'])

    def test_valid_fk_from_db_is_ok(self):
        Country.objects.create(name='France', water_ownership='pub', land_ownership='priv')
        buf = _make_xlsx({'SubnationalRegion': [
            ['name', 'description', 'country_name'],
            ['Bretagne', '', 'France'],
        ]})
        result = parse_file(buf)
        self.assertEqual(result['SubnationalRegion'][0]['status'], 'ok')

    def test_fk_resolved_from_same_file(self):
        """SubnationalRegion can reference a Country defined in the same file."""
        buf = _make_xlsx({
            'Country': [
                ['name', 'water_ownership', 'land_ownership', 'water_Governance', 'land_Governance'],
                ['NewCountry', 'pub', 'priv', '', ''],
            ],
            'SubnationalRegion': [
                ['name', 'description', 'country_name'],
                ['NewRegion', '', 'NewCountry'],
            ],
        })
        result = parse_file(buf)
        self.assertEqual(result['Country'][0]['status'], 'ok')
        self.assertEqual(result['SubnationalRegion'][0]['status'], 'ok')

    def test_policy_level_subcategory_fk(self):
        pt = Policy_Type.objects.create(name='TypeA')
        Policy_Subcategory.objects.create(name='SubA', policy_type=pt)
        buf = _make_xlsx({'Policy_Level': [
            ['name', 'score', 'description', 'subcategory_name', 'policy_type_name'],
            ['Level1', '3.0', '', 'SubA', 'TypeA'],
        ]})
        result = parse_file(buf)
        self.assertEqual(result['Policy_Level'][0]['status'], 'ok')
```

- [ ] **Step 2: Run to confirm failure**

Run: `python manage.py test imports.tests.test_excel_parser`
Expected: `ImportError` — `cannot import name 'parse_file'`

- [ ] **Step 3: Implement excel_parser.py**

Create `imports/services/excel_parser.py`:
```python
import openpyxl
from dashboard.models import (
    Asset, Commodity, Company, Country, Policy_Level, Policy_Subcategory,
    Policy_Type, Production, Company_Revenue, Ownership, Company_Policy,
    SubnationalRegion,
)
from .constants import (
    DUPLICATE_CRITERIA, FK_FIELDS, MODEL_KEY_TO_SHEET,
    REQUIRED_FIELDS, SHEET_COLUMNS,
)


def parse_file(source):
    """
    Parse an xlsx file (path or file-like object).
    Returns {sheet_name: [{'status': 'ok'|'duplicate'|'error', 'data': {...}, 'message': str}, …]}.
    """
    wb = openpyxl.load_workbook(source)
    file_names = _collect_file_names(wb)

    result = {}
    for sheet_name in SHEET_COLUMNS:
        if sheet_name not in wb.sheetnames:
            continue
        result[sheet_name] = _parse_sheet(wb[sheet_name], sheet_name, file_names)
    return result


# ── helpers ──────────────────────────────────────────────────────────────────

def _collect_file_names(wb):
    """
    Build lookup sets of names defined in the file itself, so FK fields can
    reference rows from a sibling sheet in the same upload.
    Returns {model_key: {name_lower, …}}.
    """
    file_names = {key: set() for key in MODEL_KEY_TO_SHEET}
    for model_key, sheet_name in MODEL_KEY_TO_SHEET.items():
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        header = [c.value for c in ws[1]]
        if 'name' not in header:
            continue
        name_col = header.index('name')
        for row in ws.iter_rows(min_row=2):
            val = row[name_col].value if name_col < len(row) else None
            if val is not None:
                file_names[model_key].add(str(val).strip().lower())
    return file_names


def _db_names(model_key):
    model_map = {
        'country': Country,
        'subnational_region': SubnationalRegion,
        'commodity': Commodity,
        'policy_type': Policy_Type,
        'policy_subcategory': Policy_Subcategory,
        'policy_level': Policy_Level,
        'company': Company,
        'asset': Asset,
    }
    return {n.lower() for n in model_map[model_key].objects.values_list('name', flat=True)}


def _can_resolve(model_key, name, file_names):
    key = name.strip().lower()
    return key in _db_names(model_key) or key in file_names.get(model_key, set())


def _existing_keys(sheet_name):
    """Return the set of existing duplicate-key tuples from the DB."""
    if sheet_name == 'Country':
        return {(n.lower(),) for n in Country.objects.values_list('name', flat=True)}
    if sheet_name == 'SubnationalRegion':
        return {(n.lower(), c.lower()) for n, c in
                SubnationalRegion.objects.values_list('name', 'country__name')}
    if sheet_name == 'Commodity':
        return {(n.lower(),) for n in Commodity.objects.values_list('name', flat=True)}
    if sheet_name == 'Policy_Type':
        return {(n.lower(),) for n in Policy_Type.objects.values_list('name', flat=True)}
    if sheet_name == 'Policy_Subcategory':
        return {(n.lower(), p.lower()) for n, p in
                Policy_Subcategory.objects.values_list('name', 'policy_type__name')}
    if sheet_name == 'Policy_Level':
        return {(n.lower(), s.lower(), p.lower()) for n, s, p in
                Policy_Level.objects.values_list(
                    'name', 'subcategory__name', 'subcategory__policy_type__name')}
    if sheet_name == 'Company':
        return {(n.lower(),) for n in Company.objects.values_list('name', flat=True)}
    if sheet_name == 'Asset':
        return {(n.lower(), c.lower()) for n, c in
                Asset.objects.values_list('name', 'country__name')}
    if sheet_name == 'Production':
        return {(a.lower(), c.lower(), str(y)) for a, c, y in
                Production.objects.values_list('Asset__name', 'commodity__name', 'year')}
    if sheet_name == 'Company_Revenue':
        return {(c.lower(), str(y)) for c, y in
                Company_Revenue.objects.values_list('company__name', 'year')}
    if sheet_name == 'Ownership':
        return {(a.lower(), c.lower()) for a, c in
                Ownership.objects.values_list('Asset__name', 'Company__name')}
    if sheet_name == 'Company_Policy':
        return {(co.lower(), pt.lower(), ps.lower(), pl.lower()) for co, pt, ps, pl in
                Company_Policy.objects.values_list(
                    'company__name',
                    'policy_level__subcategory__policy_type__name',
                    'policy_level__subcategory__name',
                    'policy_level__name',
                )}
    return set()


def _parse_sheet(ws, sheet_name, file_names):
    columns = SHEET_COLUMNS[sheet_name]
    required = REQUIRED_FIELDS[sheet_name]
    fk_fields = FK_FIELDS.get(sheet_name, {})
    dup_criteria = DUPLICATE_CRITERIA[sheet_name]

    existing = _existing_keys(sheet_name)
    seen = set()
    rows_out = []

    header = [c.value for c in ws[1]]

    for ws_row in ws.iter_rows(min_row=2):
        data = {}
        for col_idx, col_name in enumerate(columns):
            cell_val = None
            if col_idx < len(header) and header[col_idx] == col_name:
                cell_val = ws_row[col_idx].value if col_idx < len(ws_row) else None
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

        # FK resolution
        fk_error = None
        for fk_col, model_key in fk_fields.items():
            val = data.get(fk_col, '')
            if val and not _can_resolve(model_key, val, file_names):
                fk_error = f"Valeur introuvable pour '{fk_col}' : '{val}'"
                break
        if fk_error:
            rows_out.append({'status': 'error', 'message': fk_error, 'data': data})
            continue

        # Duplicate check
        key = tuple(data.get(f, '').strip().lower() for f in dup_criteria)
        if key in existing or key in seen:
            rows_out.append({'status': 'duplicate', 'data': data})
        else:
            seen.add(key)
            rows_out.append({'status': 'ok', 'data': data})

    return rows_out
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `python manage.py test imports.tests.test_excel_parser`
Expected: `OK` — 9 tests passed

- [ ] **Step 5: Commit**

```bash
git add imports/services/excel_parser.py imports/tests/test_excel_parser.py
git commit -m "feat(imports): implement Excel parser with FK resolution and duplicate detection"
```

---

### Task 6: Importer

**Files:**
- Create: `imports/services/importer.py`
- Create: `imports/tests/test_importer.py`

- [ ] **Step 1: Write failing tests**

Create `imports/tests/test_importer.py`:
```python
from django.test import TestCase
from dashboard.models import (
    Country, SubnationalRegion, Commodity, Policy_Type, Policy_Subcategory,
    Policy_Level, Company, Asset, Production, Company_Revenue, Ownership, Company_Policy,
)
from imports.services.importer import save_import


def _ok(data):
    return {'status': 'ok', 'data': data}

def _dup(data):
    return {'status': 'duplicate', 'data': data}

def _err(data, msg='err'):
    return {'status': 'error', 'message': msg, 'data': data}


class ImporterCountryTest(TestCase):
    def test_creates_country(self):
        counts = save_import({'Country': [
            _ok({'name': 'France', 'water_ownership': 'pub',
                 'land_ownership': 'priv', 'water_Governance': '', 'land_Governance': ''}),
        ]})
        self.assertEqual(counts['Country'], 1)
        self.assertTrue(Country.objects.filter(name='France').exists())

    def test_skips_duplicate_and_error_rows(self):
        counts = save_import({'Country': [
            _ok({'name': 'France', 'water_ownership': 'pub',
                 'land_ownership': 'priv', 'water_Governance': '', 'land_Governance': ''}),
            _dup({'name': 'Germany', 'water_ownership': 'pub',
                  'land_ownership': 'priv', 'water_Governance': '', 'land_Governance': ''}),
            _err({'name': 'Bad', 'water_ownership': '', 'land_ownership': '',
                  'water_Governance': '', 'land_Governance': ''}),
        ]})
        self.assertEqual(counts['Country'], 1)
        self.assertFalse(Country.objects.filter(name='Germany').exists())

    def test_topological_order_subnational_references_country(self):
        counts = save_import({
            'Country': [
                _ok({'name': 'France', 'water_ownership': 'pub',
                     'land_ownership': 'priv', 'water_Governance': '', 'land_Governance': ''}),
            ],
            'SubnationalRegion': [
                _ok({'name': 'Bretagne', 'description': '', 'country_name': 'France'}),
            ],
        })
        self.assertEqual(counts['Country'], 1)
        self.assertEqual(counts['SubnationalRegion'], 1)
        self.assertTrue(SubnationalRegion.objects.filter(name='Bretagne').exists())

    def test_returns_zero_for_missing_sheet(self):
        counts = save_import({})
        self.assertEqual(counts, {})

    def test_transaction_rollback_does_not_partial_import(self):
        """If an unexpected error occurs mid-import, nothing is saved."""
        from unittest.mock import patch
        with patch('dashboard.models.Country.objects.create', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                save_import({'Country': [
                    _ok({'name': 'France', 'water_ownership': 'pub',
                         'land_ownership': 'priv', 'water_Governance': '', 'land_Governance': ''}),
                ]})
        self.assertFalse(Country.objects.filter(name='France').exists())
```

- [ ] **Step 2: Run to confirm failure**

Run: `python manage.py test imports.tests.test_importer`
Expected: `ImportError` — `cannot import name 'save_import'`

- [ ] **Step 3: Implement importer.py**

Create `imports/services/importer.py`:
```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `python manage.py test imports.tests.test_importer`
Expected: `OK` — 5 tests passed

- [ ] **Step 5: Commit**

```bash
git add imports/services/importer.py imports/tests/test_importer.py
git commit -m "feat(imports): implement importer with topological save order and tests"
```

---

### Task 7: Views

**Files:**
- Modify: `imports/views.py`
- Create: `imports/tests/test_views.py`

- [ ] **Step 1: Write failing tests**

Create `imports/tests/test_views.py`:
```python
import io
import json
import os
import openpyxl
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from authentication.models import User
from imports.services.constants import SHEET_COLUMNS

import tempfile


def _make_minimal_xlsx():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet('Country')
    ws.append(['name', 'water_ownership', 'land_ownership', 'water_Governance', 'land_Governance'])
    ws.append(['TestLand', 'pub', 'priv', '', ''])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ViewsAccessTest(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user('creator', password='pass', role='CREATOR')
        self.subscriber = User.objects.create_user('sub', password='pass', role='SUBSCRIBER')

    def test_index_anonymous_redirects(self):
        resp = self.client.get(reverse('imports:index'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login/', resp['Location'])

    def test_index_subscriber_403(self):
        self.client.login(username='sub', password='pass')
        resp = self.client.get(reverse('imports:index'))
        self.assertEqual(resp.status_code, 403)

    def test_index_creator_200(self):
        self.client.login(username='creator', password='pass')
        resp = self.client.get(reverse('imports:index'))
        self.assertEqual(resp.status_code, 200)

    def test_download_template_returns_xlsx(self):
        self.client.login(username='creator', password='pass')
        resp = self.client.get(reverse('imports:download_template'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])

    def test_upload_bad_extension_shows_error(self):
        self.client.login(username='creator', password='pass')
        f = SimpleUploadedFile('test.csv', b'name\nFrance\n', content_type='text/csv')
        resp = self.client.post(reverse('imports:upload'), {'excel_file': f})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Format invalide')

    def test_upload_valid_file_redirects_to_preview(self):
        self.client.login(username='creator', password='pass')
        xlsx_bytes = _make_minimal_xlsx()
        f = SimpleUploadedFile('data.xlsx', xlsx_bytes,
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post(reverse('imports:upload'), {'excel_file': f})
        self.assertRedirects(resp, reverse('imports:preview'), fetch_redirect_response=False)
        self.assertIn('import_key', self.client.session)

    def test_preview_without_session_redirects(self):
        self.client.login(username='creator', password='pass')
        resp = self.client.get(reverse('imports:preview'))
        self.assertRedirects(resp, reverse('imports:index'), fetch_redirect_response=False)

    def test_full_workflow_upload_preview_confirm(self):
        self.client.login(username='creator', password='pass')
        xlsx_bytes = _make_minimal_xlsx()
        f = SimpleUploadedFile('data.xlsx', xlsx_bytes,
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.client.post(reverse('imports:upload'), {'excel_file': f})
        resp = self.client.get(reverse('imports:preview'))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post(reverse('imports:confirm'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'importés avec succès')
        from dashboard.models import Country
        self.assertTrue(Country.objects.filter(name='TestLand').exists())
```

- [ ] **Step 2: Run to confirm failure**

Run: `python manage.py test imports.tests.test_views`
Expected: failures because views.py is still placeholder

- [ ] **Step 3: Implement views.py**

Replace `imports/views.py` with:
```python
import json
import os
import uuid

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .decorators import creator_required
from .services.excel_parser import parse_file
from .services.excel_template import build_template
from .services.importer import save_import


@creator_required
def index(request):
    return render(request, 'imports/index.html')


@creator_required
@require_http_methods(['GET'])
def download_template(request):
    buffer = build_template()
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="easybiodiv_template.xlsx"'
    return response


@creator_required
@require_http_methods(['POST'])
def upload(request):
    if 'excel_file' not in request.FILES:
        return render(request, 'imports/index.html', {'error': 'Aucun fichier fourni.'})

    f = request.FILES['excel_file']
    if not f.name.lower().endswith('.xlsx'):
        return render(request, 'imports/index.html', {
            'error': 'Format invalide. Utilisez un fichier .xlsx.',
        })

    parsed = parse_file(f)

    tmp_dir = os.path.join(settings.MEDIA_ROOT, 'imports', 'tmp')
    os.makedirs(tmp_dir, exist_ok=True)
    import_key = str(uuid.uuid4())
    json_path = os.path.join(tmp_dir, f'{import_key}.json')
    with open(json_path, 'w', encoding='utf-8') as fp:
        json.dump({'sheets': parsed}, fp, ensure_ascii=False)

    request.session['import_key'] = import_key
    return redirect('imports:preview')


@creator_required
@require_http_methods(['GET'])
def preview(request):
    import_key = request.session.get('import_key')
    if not import_key:
        return redirect('imports:index')

    json_path = os.path.join(settings.MEDIA_ROOT, 'imports', 'tmp', f'{import_key}.json')
    if not os.path.exists(json_path):
        return redirect('imports:index')

    with open(json_path, encoding='utf-8') as fp:
        data = json.load(fp)

    sheet_summaries = {}
    for sheet_name, rows in data['sheets'].items():
        sheet_summaries[sheet_name] = {
            'rows': rows,
            'ok_count': sum(1 for r in rows if r['status'] == 'ok'),
            'duplicate_count': sum(1 for r in rows if r['status'] == 'duplicate'),
            'error_count': sum(1 for r in rows if r['status'] == 'error'),
        }

    has_importable = any(s['ok_count'] > 0 for s in sheet_summaries.values())
    return render(request, 'imports/preview.html', {
        'sheets': sheet_summaries,
        'has_importable': has_importable,
    })


@creator_required
@require_http_methods(['POST'])
def confirm(request):
    import_key = request.session.get('import_key')
    if not import_key:
        return redirect('imports:index')

    json_path = os.path.join(settings.MEDIA_ROOT, 'imports', 'tmp', f'{import_key}.json')
    if not os.path.exists(json_path):
        return redirect('imports:index')

    with open(json_path, encoding='utf-8') as fp:
        data = json.load(fp)

    counts = save_import(data['sheets'])

    os.unlink(json_path)
    del request.session['import_key']

    total = sum(counts.values())
    return render(request, 'imports/index.html', {
        'success': f"{total} enregistrement(s) importé(s) avec succès.",
        'counts': counts,
    })
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `python manage.py test imports.tests.test_views`
Expected: `OK` — 9 tests passed

- [ ] **Step 5: Commit**

```bash
git add imports/views.py imports/tests/test_views.py
git commit -m "feat(imports): implement all import views with tests"
```

---

### Task 8: Templates

**Files:**
- Create: `imports/templates/imports/index.html`
- Create: `imports/templates/imports/preview.html`

No tests — templates are validated by the view tests in Task 7.

- [ ] **Step 1: Create imports/templates/imports/ directory**

```bash
mkdir -p imports/templates/imports
```

- [ ] **Step 2: Create index.html**

Create `imports/templates/imports/index.html`:
```html
{% extends "base.html" %}
{% load static %}

{% block title %}Import Excel — Easybiodiv{% endblock %}
{% block nav_overview %}{% endblock %}

{% block content %}
<div class="page-header">
  <div>
    <h1 class="page-title">Import Excel</h1>
    <p class="page-subtitle">Téléchargez le template, remplissez-le, puis importez vos données.</p>
  </div>
</div>

{% if success %}
<div class="alert alert--success" role="alert">
  <strong>Succès !</strong> {{ success }}
  {% if counts %}
  <ul class="alert__list">
    {% for sheet, count in counts.items %}
      {% if count > 0 %}<li>{{ sheet }} : {{ count }} ligne(s)</li>{% endif %}
    {% endfor %}
  </ul>
  {% endif %}
</div>
{% endif %}

{% if error %}
<div class="alert alert--error" role="alert">{{ error }}</div>
{% endif %}

<div class="import-cards">

  <div class="card">
    <div class="card__header">
      <h2 class="card__title">1. Télécharger le template</h2>
    </div>
    <div class="card__body">
      <p>Le fichier Excel contient un onglet par tableau et un onglet <em>_Référence</em> listant les valeurs acceptées.</p>
      <a href="{% url 'imports:download_template' %}" class="btn btn--primary">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M8 2v8M5 7l3 3 3-3M3 13h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        Télécharger le template
      </a>
    </div>
  </div>

  <div class="card">
    <div class="card__header">
      <h2 class="card__title">2. Importer un fichier rempli</h2>
    </div>
    <div class="card__body">
      <p>Sélectionnez votre fichier <code>.xlsx</code>. Vous pourrez vérifier les données avant confirmation.</p>
      <form method="post" action="{% url 'imports:upload' %}" enctype="multipart/form-data">
        {% csrf_token %}
        <div class="form-group">
          <label for="excel_file" class="form-label">Fichier Excel (.xlsx)</label>
          <input type="file" id="excel_file" name="excel_file" accept=".xlsx"
                 class="form-input" required>
        </div>
        <button type="submit" class="btn btn--primary">
          Analyser et prévisualiser
        </button>
      </form>
    </div>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 3: Create preview.html**

Create `imports/templates/imports/preview.html`:
```html
{% extends "base.html" %}
{% load static %}

{% block title %}Aperçu de l'import — Easybiodiv{% endblock %}

{% block content %}
<div class="page-header">
  <div>
    <h1 class="page-title">Aperçu de l'import</h1>
    <p class="page-subtitle">Vérifiez les données avant de confirmer l'import.</p>
  </div>
</div>

<div class="preview-tabs" id="preview-tabs">
  <div class="preview-tabs__nav" role="tablist">
    {% for sheet_name, sheet in sheets.items %}
    <button class="preview-tabs__tab {% if forloop.first %}preview-tabs__tab--active{% endif %}"
            role="tab"
            data-tab="{{ sheet_name }}"
            aria-selected="{% if forloop.first %}true{% else %}false{% endif %}">
      {{ sheet_name }}
      {% if sheet.error_count > 0 %}
      <span class="badge badge--error">{{ sheet.error_count }}</span>
      {% endif %}
      {% if sheet.ok_count > 0 %}
      <span class="badge badge--ok">{{ sheet.ok_count }}</span>
      {% endif %}
    </button>
    {% endfor %}
  </div>

  {% for sheet_name, sheet in sheets.items %}
  <div class="preview-tabs__panel {% if forloop.first %}preview-tabs__panel--active{% endif %}"
       id="tab-{{ sheet_name }}" role="tabpanel">

    <div class="preview-summary">
      <span class="preview-summary__item preview-summary__item--ok">
        ✓ {{ sheet.ok_count }} à importer
      </span>
      <span class="preview-summary__item preview-summary__item--dup">
        ⊘ {{ sheet.duplicate_count }} doublon(s)
      </span>
      <span class="preview-summary__item preview-summary__item--err">
        ✗ {{ sheet.error_count }} erreur(s)
      </span>
    </div>

    {% if sheet.rows %}
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th>Statut</th>
            {% for col in sheet.rows.0.data.keys %}
            <th>{{ col }}</th>
            {% endfor %}
          </tr>
        </thead>
        <tbody>
          {% for row in sheet.rows %}
          <tr class="row--{{ row.status }}">
            <td>
              {% if row.status == 'ok' %}
                <span class="badge badge--ok">À importer</span>
              {% elif row.status == 'duplicate' %}
                <span class="badge badge--dup">Doublon</span>
              {% else %}
                <span class="badge badge--error" title="{{ row.message }}">Erreur</span>
              {% endif %}
            </td>
            {% for val in row.data.values %}
            <td>{{ val }}</td>
            {% endfor %}
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <p class="empty-state">Aucune ligne dans cet onglet.</p>
    {% endif %}
  </div>
  {% endfor %}
</div>

<div class="preview-actions">
  <a href="{% url 'imports:index' %}" class="btn btn--secondary">Annuler</a>
  <form method="post" action="{% url 'imports:confirm' %}">
    {% csrf_token %}
    <button type="submit" class="btn btn--primary" {% if not has_importable %}disabled{% endif %}>
      Confirmer l'import
    </button>
  </form>
</div>

<style>
.preview-tabs__nav { display: flex; gap: .5rem; flex-wrap: wrap; border-bottom: 2px solid var(--color-border, #e5e7eb); margin-bottom: 1rem; }
.preview-tabs__tab { padding: .5rem 1rem; border: none; background: none; cursor: pointer; font-size: .875rem; border-bottom: 2px solid transparent; margin-bottom: -2px; }
.preview-tabs__tab--active { border-bottom-color: var(--color-primary, #1F7A4A); color: var(--color-primary, #1F7A4A); font-weight: 600; }
.preview-tabs__panel { display: none; }
.preview-tabs__panel--active { display: block; }
.preview-summary { display: flex; gap: 1.5rem; margin-bottom: 1rem; font-size: .875rem; }
.preview-summary__item--ok { color: #15803d; }
.preview-summary__item--dup { color: #b45309; }
.preview-summary__item--err { color: #dc2626; }
.table-scroll { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: .8125rem; }
.data-table th, .data-table td { padding: .5rem .75rem; border: 1px solid var(--color-border, #e5e7eb); text-align: left; white-space: nowrap; }
.data-table th { background: var(--color-surface, #f9fafb); font-weight: 600; }
tr.row--ok { background: #f0fdf4; }
tr.row--duplicate { background: #fffbeb; }
tr.row--error { background: #fef2f2; }
.badge { display: inline-block; padding: .125rem .5rem; border-radius: 9999px; font-size: .75rem; font-weight: 600; }
.badge--ok { background: #dcfce7; color: #15803d; }
.badge--dup { background: #fef3c7; color: #b45309; }
.badge--error { background: #fee2e2; color: #dc2626; }
.preview-actions { display: flex; gap: 1rem; margin-top: 1.5rem; justify-content: flex-end; }
.import-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; margin-top: 1.5rem; }
.alert { padding: 1rem 1.25rem; border-radius: .5rem; margin-bottom: 1rem; }
.alert--success { background: #f0fdf4; border: 1px solid #86efac; color: #15803d; }
.alert--error { background: #fef2f2; border: 1px solid #fca5a5; color: #dc2626; }
.alert__list { margin: .5rem 0 0 1.25rem; }
.btn { display: inline-flex; align-items: center; gap: .5rem; padding: .5rem 1.25rem; border-radius: .375rem; font-size: .875rem; font-weight: 500; cursor: pointer; border: none; text-decoration: none; }
.btn--primary { background: var(--color-primary, #1F7A4A); color: #fff; }
.btn--primary:disabled { opacity: .5; cursor: not-allowed; }
.btn--secondary { background: var(--color-surface, #f3f4f6); color: var(--color-text, #111); border: 1px solid var(--color-border, #d1d5db); }
.empty-state { color: var(--color-muted, #6b7280); font-style: italic; }
</style>

<script>
document.querySelectorAll('.preview-tabs__tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.preview-tabs__tab').forEach(b => {
      b.classList.remove('preview-tabs__tab--active');
      b.setAttribute('aria-selected', 'false');
    });
    document.querySelectorAll('.preview-tabs__panel').forEach(p => {
      p.classList.remove('preview-tabs__panel--active');
    });
    btn.classList.add('preview-tabs__tab--active');
    btn.setAttribute('aria-selected', 'true');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('preview-tabs__panel--active');
  });
});
</script>
{% endblock %}
```

- [ ] **Step 4: Start the dev server and verify visually**

Run: `python manage.py runserver`

Log in as a CREATOR user, go to `/imports/`, download the template, re-upload it, verify the preview page shows tabs and correct row statuses, then confirm.

- [ ] **Step 5: Commit**

```bash
git add imports/templates/
git commit -m "feat(imports): add index and preview templates"
```

---

### Task 9: Sidebar link

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Add Import Excel link in base.html sidebar footer**

In `templates/base.html`, find the sidebar footer section:
```html
      <div class="sidebar__footer">
        <a href="#" class="sidebar__footer-link" aria-label="Exporter un rapport">
```

Add the Import Excel link **before** the `sidebar__footer-actions` div:
```html
      <div class="sidebar__footer">
        {% if user.is_authenticated and user.role == 'CREATOR' %}
        <a href="{% url 'imports:index' %}" class="sidebar__footer-link" aria-label="Import Excel">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M8 14V6M5 9l3-3 3 3M3 14h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span class="sidebar__footer-link-label">Import Excel</span>
        </a>
        {% endif %}
        <a href="#" class="sidebar__footer-link" aria-label="Exporter un rapport">
```

- [ ] **Step 2: Verify the link appears only for CREATOR users**

Run: `python manage.py runserver`

- Log in as SUBSCRIBER → sidebar footer should NOT show "Import Excel".
- Log in as CREATOR → sidebar footer should show "Import Excel" linking to `/imports/`.

- [ ] **Step 3: Run the full test suite**

Run: `python manage.py test imports`
Expected: All tests pass with no errors.

- [ ] **Step 4: Commit**

```bash
git add templates/base.html
git commit -m "feat(imports): show Import Excel link in sidebar for CREATOR users"
```
