# Conformité ESRS E4 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une page « Conformité CSRD / ESRS E4 » dans l'app `dashboard` qui restitue, par entreprise, le verrou de matérialité, une synthèse (KPIs, métrique E4-5, frise LEAP) et le détail des Disclosure Requirements, alimentée par de nouveaux modèles Django éditables en admin + dérivations des données existantes.

**Architecture:** Mêmes patterns que les pages existantes du dashboard — une fonction `_get_compliance_data(company)` construit un dict JSON-sérialisable, exposé via une vue page (rend un template + `initial_data`) et une vue API JSON par entreprise. Saisie via l'admin Django uniquement (page en lecture seule). Frontend vanilla (template + 1 JS + CSS dans `style.css`).

**Tech Stack:** Django (LTS), SQLite (dev), HTML/CSS/JS vanilla. Aucun `JSONField`, aucun framework JS. Tests : `django.test.TestCase` via `python manage.py test dashboard`.

**Conventions d'exécution (Windows / PowerShell):**
- Python du venv : `.\venv\Scripts\python.exe`
- Lancer les tests : `.\venv\Scripts\python.exe manage.py test dashboard -v 2`
- `manage.py` est à la racine du dépôt.

---

### Task 1: Nouveaux modèles E4 + champs zones sensibles sur Asset

**Files:**
- Modify: `dashboard/models.py` (ajouter champs sur `Asset` ~ligne 98-123 ; ajouter 2 nouvelles classes en fin de fichier)
- Test: `dashboard/tests.py` (nouvelle classe `E4ModelTests`)

- [ ] **Step 1: Écrire le test des modèles (échouera)**

Ajouter en fin de `dashboard/tests.py` :

```python
class E4ModelTests(TestCase):

    def test_assessment_str(self):
        from .models import E4Assessment
        company = Company.objects.create(name='Acme')
        a = E4Assessment.objects.create(company=company, reporting_year=2024)
        self.assertEqual(str(a), 'Acme — E4 2024')

    def test_assessment_defaults(self):
        from .models import E4Assessment
        company = Company.objects.create(name='Acme')
        a = E4Assessment.objects.create(company=company, reporting_year=2024)
        self.assertEqual(a.standard_version, 'AMENDED_2025')
        self.assertEqual(a.materiality_status, 'NOT_ASSESSED')
        self.assertEqual(a.leap_locate_status, 'TODO')

    def test_disclosure_unique_per_code(self):
        from django.db import IntegrityError, transaction
        from .models import E4Assessment, DisclosureRequirement
        company = Company.objects.create(name='Acme')
        a = E4Assessment.objects.create(company=company, reporting_year=2024)
        DisclosureRequirement.objects.create(assessment=a, code='E4_2')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DisclosureRequirement.objects.create(assessment=a, code='E4_2')

    def test_asset_sensitive_zone_fields(self):
        country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private'
        )
        asset = Asset.objects.create(
            name='Site', latitude=1.0, longitude=1.0, country=country,
            near_sensitive_zone=True, sensitive_zone_type='NATURA_2000',
            sensitive_zone_name='Camargue', sensitive_zone_area_ha=120.0,
        )
        self.assertTrue(asset.near_sensitive_zone)
        self.assertEqual(asset.sensitive_zone_area_ha, 120.0)
        self.assertEqual(asset.get_sensitive_zone_type_display(), 'Natura 2000')
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.E4ModelTests -v 2`
Expected: FAIL (ImportError / champs inexistants).

- [ ] **Step 3: Ajouter les champs zones sensibles sur `Asset`**

Dans `dashboard/models.py`, à l'intérieur de la classe `Asset` (avant la méthode `__str__`), ajouter :

```python
    class SensitiveZoneType(models.TextChoices):
        NATURA_2000 = 'NATURA_2000', 'Natura 2000'
        NATIONAL_PROTECTED = 'NATIONAL_PROTECTED', 'Aire protégée nationale'
        UNESCO = 'UNESCO', 'Site UNESCO'
        IUCN_KBA = 'IUCN_KBA', 'IUCN Key Biodiversity Area'
        OTHER = 'OTHER', 'Autre'

    near_sensitive_zone = models.BooleanField(default=False)
    sensitive_zone_type = models.CharField(
        max_length=20, choices=SensitiveZoneType.choices, blank=True
    )
    sensitive_zone_name = models.CharField(max_length=255, blank=True)
    sensitive_zone_area_ha = models.FloatField(default=0)
```

- [ ] **Step 4: Ajouter `import` settings + les deux nouvelles classes**

En haut de `dashboard/models.py`, sous `from django.db import models`, ajouter :

```python
from django.conf import settings
```

En fin de `dashboard/models.py`, ajouter :

```python
class E4Assessment(models.Model):
    """Dossier de conformité ESRS E4 d'une entreprise (verrou de matérialité + LEAP)."""

    class StandardVersion(models.TextChoices):
        AMENDED_2025 = 'AMENDED_2025', 'ESRS E4 amendé (déc. 2025) — 5 DR'
        ORIGINAL_2023 = 'ORIGINAL_2023', 'ESRS E4 original (2023) — 6 DR'

    class Materiality(models.TextChoices):
        NOT_ASSESSED = 'NOT_ASSESSED', 'Non évaluée'
        MATERIAL = 'MATERIAL', 'Matérielle'
        NOT_MATERIAL = 'NOT_MATERIAL', 'Non matérielle'

    class LeapStatus(models.TextChoices):
        TODO = 'TODO', 'À faire'
        IN_PROGRESS = 'IN_PROGRESS', 'En cours'
        DONE = 'DONE', 'Fait'

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='e4_assessments'
    )
    reporting_year = models.IntegerField(default=2024)
    standard_version = models.CharField(
        max_length=20, choices=StandardVersion.choices,
        default=StandardVersion.AMENDED_2025,
    )
    materiality_status = models.CharField(
        max_length=20, choices=Materiality.choices,
        default=Materiality.NOT_ASSESSED,
    )
    materiality_justification = models.TextField(blank=True)

    leap_locate_status = models.CharField(
        max_length=20, choices=LeapStatus.choices, default=LeapStatus.TODO
    )
    leap_evaluate_status = models.CharField(
        max_length=20, choices=LeapStatus.choices, default=LeapStatus.TODO
    )
    leap_assess_status = models.CharField(
        max_length=20, choices=LeapStatus.choices, default=LeapStatus.TODO
    )
    leap_locate_notes = models.TextField(blank=True)
    leap_evaluate_notes = models.TextField(blank=True)
    leap_assess_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f"{self.company.name} — E4 {self.reporting_year}"


class DisclosureRequirement(models.Model):
    """État de conformité d'un Disclosure Requirement pour une évaluation E4."""

    class Code(models.TextChoices):
        E4_1 = 'E4_1', 'E4-1'
        E4_2 = 'E4_2', 'E4-2'
        E4_3 = 'E4_3', 'E4-3'
        E4_4 = 'E4_4', 'E4-4'
        E4_5 = 'E4_5', 'E4-5'
        E4_6 = 'E4_6', 'E4-6'

    class Status(models.TextChoices):
        NOT_STARTED = 'NOT_STARTED', 'Non commencé'
        NON_COMPLIANT = 'NON_COMPLIANT', 'Non conforme'
        PARTIAL = 'PARTIAL', 'Partiel'
        COMPLIANT = 'COMPLIANT', 'Conforme'
        NOT_APPLICABLE = 'NOT_APPLICABLE', 'Non applicable'

    assessment = models.ForeignKey(
        E4Assessment, on_delete=models.CASCADE, related_name='disclosure_requirements'
    )
    code = models.CharField(max_length=10, choices=Code.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOT_STARTED
    )
    justification = models.TextField(blank=True)

    class Meta:
        unique_together = ('assessment', 'code')

    def __str__(self):
        return f"{self.assessment.company.name} — {self.get_code_display()}"
```

- [ ] **Step 5: Créer la migration**

Run: `.\venv\Scripts\python.exe manage.py makemigrations dashboard --name e4_compliance`
Expected: crée `dashboard/migrations/0018_e4_compliance.py` (AddField x4 sur Asset, CreateModel E4Assessment, CreateModel DisclosureRequirement).

- [ ] **Step 6: Appliquer la migration et lancer le test**

Run: `.\venv\Scripts\python.exe manage.py migrate; .\venv\Scripts\python.exe manage.py test dashboard.tests.E4ModelTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add dashboard/models.py dashboard/migrations/0018_e4_compliance.py dashboard/tests.py
git commit -m "feat(compliance): modèles E4Assessment, DisclosureRequirement + zones sensibles Asset"
```

---

### Task 2: Catalogue réglementaire + helpers de conformité

**Files:**
- Create: `dashboard/compliance_catalog.py`
- Test: `dashboard/tests.py` (nouvelle classe `E4CatalogTests`)

- [ ] **Step 1: Écrire le test du catalogue (échouera)**

Ajouter en fin de `dashboard/tests.py` :

```python
class E4CatalogTests(TestCase):

    def test_applicable_drs_amended_has_five(self):
        from .compliance_catalog import APPLICABLE_DRS
        self.assertEqual(
            APPLICABLE_DRS['AMENDED_2025'], ['E4_1', 'E4_2', 'E4_3', 'E4_4', 'E4_5']
        )

    def test_applicable_drs_original_has_six_with_e4_6(self):
        from .compliance_catalog import APPLICABLE_DRS
        self.assertIn('E4_6', APPLICABLE_DRS['ORIGINAL_2023'])
        self.assertEqual(len(APPLICABLE_DRS['ORIGINAL_2023']), 6)

    def test_catalog_has_every_code(self):
        from .compliance_catalog import DR_CATALOG
        for code in ['E4_1', 'E4_2', 'E4_3', 'E4_4', 'E4_5', 'E4_6']:
            self.assertIn(code, DR_CATALOG)
            self.assertIn('title', DR_CATALOG[code])
            self.assertIn('description', DR_CATALOG[code])
            self.assertIn('reference', DR_CATALOG[code])
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.E4CatalogTests -v 2`
Expected: FAIL (ModuleNotFoundError `compliance_catalog`).

- [ ] **Step 3: Créer le catalogue**

Créer `dashboard/compliance_catalog.py` :

```python
"""Catalogue réglementaire ESRS E4 (texte de référence des Disclosure Requirements).

Source de vérité unique des métadonnées (intitulé, description, référence ESRS 2).
L'état mutable (statut, justification) est stocké dans le modèle DisclosureRequirement.
"""

DR_CATALOG = {
    'E4_1': {
        'title': 'Plan de transition biodiversité',
        'description': (
            "À publier uniquement si un plan de transition existe ou a été rendu public. "
            "S'il existe, décrire l'alignement avec le Cadre mondial Kunming-Montréal "
            "(stopper et inverser la perte de biodiversité d'ici 2030). Sinon, simple "
            "déclaration d'absence."
        ),
        'reference': 'ESRS 2',
    },
    'E4_2': {
        'title': 'Politiques',
        'description': (
            "Politiques biodiversité couvrant la traçabilité des produits/matières à "
            "impact matériel et les sites proches de zones sensibles. Test clé : la "
            "politique couvre-t-elle les impacts matériels identifiés dans la DMA ?"
        ),
        'reference': 'ESRS 2 GDR-P',
    },
    'E4_3': {
        'title': 'Actions et ressources',
        'description': (
            "Actions et moyens engagés. Focus sur les compensations (offsets) et leur "
            "place dans la hiérarchie d'atténuation (éviter → réduire → restaurer → "
            "compenser). Seules les actions engagées/financées comptent."
        ),
        'reference': 'ESRS 2 GDR-A',
    },
    'E4_4': {
        'title': 'Cibles',
        'description': (
            "Cibles biodiversité : seuils écologiques et méthodo, alignement "
            "Kunming-Montréal / Stratégie UE Biodiversité 2030, usage d'offsets, portée "
            "géographique, niveau de la hiérarchie d'atténuation visé."
        ),
        'reference': 'ESRS 2 GDR-T',
    },
    'E4_5': {
        'title': "Métriques d'impact",
        'description': (
            "Métrique dure : nombre et surface (hectares) des sites situés dans/près de "
            "zones sensibles avec impacts négatifs (analyse géospatiale). Métriques "
            "additionnelles optionnelles : étendue/condition des écosystèmes, indicateurs "
            "d'espèces (IUCN/European Red List), connectivité des habitats."
        ),
        'reference': '—',
    },
    'E4_6': {
        'title': 'Effets financiers anticipés',
        'description': (
            "Effets financiers anticipés des risques et opportunités biodiversité. "
            "Supprimé dans la version amendée (déc. 2025) — présent uniquement en mode "
            "ESRS E4 original 2023."
        ),
        'reference': '—',
    },
}

APPLICABLE_DRS = {
    'AMENDED_2025': ['E4_1', 'E4_2', 'E4_3', 'E4_4', 'E4_5'],
    'ORIGINAL_2023': ['E4_1', 'E4_2', 'E4_3', 'E4_4', 'E4_5', 'E4_6'],
}
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.E4CatalogTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/compliance_catalog.py dashboard/tests.py
git commit -m "feat(compliance): catalogue réglementaire DR_CATALOG + ensembles applicables"
```

---

### Task 3: Fonction `_get_compliance_data` (cœur métier)

**Files:**
- Modify: `dashboard/views.py` (ajouter imports + constantes labels + helpers + fonction)
- Test: `dashboard/tests.py` (nouvelle classe `ComplianceDataTests`)

- [ ] **Step 1: Écrire les tests de la fonction (échoueront)**

Ajouter en fin de `dashboard/tests.py` :

```python
class ComplianceDataTests(TestCase):

    def _company_with_asset(self, near_zone=False, area=0.0):
        company = Company.objects.create(name='CompCorp')
        country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private'
        )
        asset = Asset.objects.create(
            name='Site', latitude=1.0, longitude=1.0, country=country,
            near_sensitive_zone=near_zone, sensitive_zone_area_ha=area,
            sensitive_zone_type=('NATURA_2000' if near_zone else ''),
        )
        Ownership.objects.create(Asset=asset, Company=company, ownership='100%')
        return company, asset

    def test_unconfigured_company(self):
        from .views import _get_compliance_data
        company, _ = self._company_with_asset()
        data = _get_compliance_data(company)
        self.assertFalse(data['configured'])
        self.assertEqual(data['materiality']['status'], 'NOT_ASSESSED')
        # NOT_ASSESSED → les DR restent affichés (5 en version amendée par défaut)
        self.assertEqual(len(data['disclosure_requirements']), 5)

    def test_suggestion_e4_2_when_policy_exists(self):
        from .views import _get_compliance_data
        company, _ = self._company_with_asset()
        pt = Policy_Type.objects.create(name='Bio')
        sub = Policy_Subcategory.objects.create(name='Sub', policy_type=pt)
        lvl = Policy_Level.objects.create(name='Lvl', subcategory=sub, score=0.5)
        Company_Policy.objects.create(company=company, policy_level=lvl)
        data = _get_compliance_data(company)
        dr2 = next(d for d in data['disclosure_requirements'] if d['code'] == 'E4_2')
        self.assertEqual(dr2['auto_suggestion'], 'PARTIAL')

    def test_material_amended_shows_five_drs(self):
        from .views import _get_compliance_data
        from .models import E4Assessment
        company, _ = self._company_with_asset()
        E4Assessment.objects.create(
            company=company, reporting_year=2024,
            materiality_status=E4Assessment.Materiality.MATERIAL,
        )
        data = _get_compliance_data(company)
        self.assertTrue(data['configured'])
        self.assertTrue(data['materiality']['is_material'])
        self.assertEqual(len(data['disclosure_requirements']), 5)
        e4_1 = next(d for d in data['disclosure_requirements'] if d['code'] == 'E4_1')
        self.assertTrue(e4_1['is_conditional'])

    def test_not_material_hides_drs(self):
        from .views import _get_compliance_data
        from .models import E4Assessment
        company, _ = self._company_with_asset()
        E4Assessment.objects.create(
            company=company, reporting_year=2024,
            materiality_status=E4Assessment.Materiality.NOT_MATERIAL,
            materiality_justification='Screening site par site : non matériel.',
        )
        data = _get_compliance_data(company)
        self.assertEqual(data['disclosure_requirements'], [])
        self.assertIn('non matériel', data['materiality']['justification'])

    def test_e4_5_metric_counts_sensitive_sites(self):
        from .views import _get_compliance_data
        company, _ = self._company_with_asset(near_zone=True, area=120.0)
        # second sensitive asset
        country = Country.objects.get(name='France')
        a2 = Asset.objects.create(
            name='Site2', latitude=2.0, longitude=2.0, country=country,
            near_sensitive_zone=True, sensitive_zone_area_ha=80.0,
            sensitive_zone_type='UNESCO',
        )
        Ownership.objects.create(Asset=a2, Company=company, ownership='100%')
        data = _get_compliance_data(company)
        self.assertEqual(data['e4_5_metric']['sites_count'], 2)
        self.assertAlmostEqual(data['e4_5_metric']['total_area_ha'], 200.0, places=2)

    def test_original_2023_includes_e4_1_mandatory_and_e4_6(self):
        from .views import _get_compliance_data
        from .models import E4Assessment
        company, _ = self._company_with_asset()
        E4Assessment.objects.create(
            company=company, reporting_year=2024,
            standard_version=E4Assessment.StandardVersion.ORIGINAL_2023,
            materiality_status=E4Assessment.Materiality.MATERIAL,
        )
        data = _get_compliance_data(company)
        codes = [d['code'] for d in data['disclosure_requirements']]
        self.assertEqual(len(codes), 6)
        self.assertIn('E4_6', codes)
        e4_1 = next(d for d in data['disclosure_requirements'] if d['code'] == 'E4_1')
        self.assertFalse(e4_1['is_conditional'])

    def test_latest_assessment_used(self):
        from .views import _get_compliance_data
        from .models import E4Assessment
        company, _ = self._company_with_asset()
        E4Assessment.objects.create(
            company=company, reporting_year=2022,
            materiality_status=E4Assessment.Materiality.NOT_MATERIAL,
        )
        E4Assessment.objects.create(
            company=company, reporting_year=2024,
            materiality_status=E4Assessment.Materiality.MATERIAL,
        )
        data = _get_compliance_data(company)
        self.assertEqual(data['reporting_year'], 2024)
        self.assertTrue(data['materiality']['is_material'])
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.ComplianceDataTests -v 2`
Expected: FAIL (`ImportError: cannot import name '_get_compliance_data'`).

- [ ] **Step 3: Ajouter imports + constantes en tête de `views.py`**

Dans `dashboard/views.py`, modifier la ligne d'import des modèles (ligne 10) pour ajouter les nouveaux modèles :

```python
from .models import (
    Asset, Commodity, Company, Company_Policy, Company_Revenue,
    Company_Revenue_Sector, DisclosureRequirement, E4Assessment, Ownership,
    Production,
)
```

Ajouter, juste après cette ligne d'import :

```python
from .compliance_catalog import APPLICABLE_DRS, DR_CATALOG

DR_STATUS_LABELS = {s.value: s.label for s in DisclosureRequirement.Status}
LEAP_STATUS_LABELS = {s.value: s.label for s in E4Assessment.LeapStatus}
```

- [ ] **Step 4: Ajouter les helpers + la fonction principale**

Ajouter dans `dashboard/views.py` (par ex. juste avant `def index(request):` à la ligne ~858) :

```python
def _compliance_suggestions(company, has_sensitive_sites):
    """Suggestions de statut dérivées des données existantes (indicatives)."""
    suggestions = {}
    if Company_Policy.objects.filter(company=company).exists():
        suggestions['E4_2'] = 'PARTIAL'
    if has_sensitive_sites:
        suggestions['E4_5'] = 'PARTIAL'
    return suggestions


def _build_disclosure_requirements(version, dr_state, suggestions):
    out = []
    for code in APPLICABLE_DRS[version]:
        meta = DR_CATALOG[code]
        dr = dr_state.get(code)
        status = dr.status if dr else 'NOT_STARTED'
        out.append({
            'code': code,
            'code_label': code.replace('_', '-'),
            'title': meta['title'],
            'description': meta['description'],
            'reference': meta['reference'],
            'is_conditional': (code == 'E4_1' and version == 'AMENDED_2025'),
            'status': status,
            'status_label': DR_STATUS_LABELS[status],
            'justification': dr.justification if dr else '',
            'auto_suggestion': suggestions.get(code),
        })
    return out


def _build_leap(assessment, sensitive_sites_count, company):
    dep = _get_dependencies_data(company)
    primary = dep.get('primary_service')
    emp = _get_mesure_empreinte_data(company)
    summaries = {
        'locate': f"{sensitive_sites_count} site(s) en/près d'une zone sensible",
        'evaluate': (
            f"Dépendance principale : {primary['name']}"
            if primary else "Aucune dépendance évaluée"
        ),
        'assess': f"Empreinte écosystèmes : {emp.get('total_impact', 0)}",
    }
    phases = [
        ('locate', 'Locate', 'leap_locate_status', 'leap_locate_notes'),
        ('evaluate', 'Evaluate', 'leap_evaluate_status', 'leap_evaluate_notes'),
        ('assess', 'Assess', 'leap_assess_status', 'leap_assess_notes'),
    ]
    out = []
    for key, label, status_field, notes_field in phases:
        status = getattr(assessment, status_field) if assessment else 'TODO'
        notes = getattr(assessment, notes_field) if assessment else ''
        out.append({
            'phase': key,
            'label': label,
            'status': status,
            'status_label': LEAP_STATUS_LABELS[status],
            'notes': notes,
            'derived_summary': summaries[key],
        })
    return out


def _compliance_synthesis(drs):
    counts = {s.value: 0 for s in DisclosureRequirement.Status}
    for d in drs:
        counts[d['status']] += 1
    applicable = [d for d in drs if d['status'] != 'NOT_APPLICABLE']
    score = sum(
        1.0 if d['status'] == 'COMPLIANT' else 0.5 if d['status'] == 'PARTIAL' else 0.0
        for d in applicable
    )
    pct = round(100 * score / len(applicable)) if applicable else 0
    return {
        'compliance_pct': pct,
        'counts_by_status': counts,
        'applicable_count': len(applicable),
    }


def _get_compliance_data(company):
    assessment = (
        E4Assessment.objects
        .filter(company=company)
        .order_by('-reporting_year', '-updated_at')
        .first()
    )

    sensitive_assets = list(
        Asset.objects
        .filter(ownership__Company=company, near_sensitive_zone=True)
        .distinct()
    )
    e4_5_metric = {
        'sites_count': len(sensitive_assets),
        'total_area_ha': round(sum(a.sensitive_zone_area_ha for a in sensitive_assets), 2),
        'sites': [
            {
                'name': a.name,
                'zone_type': a.get_sensitive_zone_type_display() if a.sensitive_zone_type else '',
                'zone_name': a.sensitive_zone_name,
                'area_ha': round(a.sensitive_zone_area_ha, 2),
            }
            for a in sensitive_assets
        ],
    }

    suggestions = _compliance_suggestions(company, bool(sensitive_assets))

    if assessment is None:
        version = E4Assessment.StandardVersion.AMENDED_2025
        version_label = E4Assessment.StandardVersion.AMENDED_2025.label
        materiality_status = 'NOT_ASSESSED'
        materiality_justification = ''
        reporting_year = None
        dr_state = {}
    else:
        version = assessment.standard_version
        version_label = assessment.get_standard_version_display()
        materiality_status = assessment.materiality_status
        materiality_justification = assessment.materiality_justification
        reporting_year = assessment.reporting_year
        dr_state = {dr.code: dr for dr in assessment.disclosure_requirements.all()}

    if materiality_status == 'NOT_MATERIAL':
        drs = []
    else:
        drs = _build_disclosure_requirements(version, dr_state, suggestions)

    return {
        'company_id': company.pk,
        'company_name': company.name,
        'configured': assessment is not None,
        'standard_version': version,
        'standard_version_label': version_label,
        'reporting_year': reporting_year,
        'materiality': {
            'status': materiality_status,
            'status_label': dict(E4Assessment.Materiality.choices)[materiality_status],
            'is_material': materiality_status == 'MATERIAL',
            'justification': materiality_justification,
        },
        'leap': _build_leap(assessment, len(sensitive_assets), company),
        'disclosure_requirements': drs,
        'synthesis': _compliance_synthesis(drs),
        'e4_5_metric': e4_5_metric,
    }
```

- [ ] **Step 5: Lancer les tests pour vérifier le succès**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.ComplianceDataTests -v 2`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "feat(compliance): _get_compliance_data (matérialité, DR, LEAP, métrique E4-5)"
```

---

### Task 4: URLs + vues page & API

**Files:**
- Modify: `dashboard/views.py` (2 nouvelles vues à la fin)
- Modify: `dashboard/urls.py` (2 routes)
- Test: `dashboard/tests.py` (nouvelle classe `CompliancePageViewTests`)

- [ ] **Step 1: Écrire les tests de vues (échoueront)**

Ajouter en fin de `dashboard/tests.py` :

```python
class CompliancePageViewTests(TestCase):

    def test_page_returns_200(self):
        response = self.client.get(reverse('dashboard:compliance'))
        self.assertEqual(response.status_code, 200)

    def test_page_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:compliance'))
        self.assertTemplateUsed(response, 'dashboard/compliance.html')

    def test_companies_in_context(self):
        Company.objects.create(name='CtxComp')
        response = self.client.get(reverse('dashboard:compliance'))
        self.assertIn('companies', response.context)

    def test_initial_data_none_without_companies(self):
        response = self.client.get(reverse('dashboard:compliance'))
        self.assertIsNone(response.context['initial_data'])

    def test_initial_data_present_with_companies(self):
        Company.objects.create(name='HasComp')
        response = self.client.get(reverse('dashboard:compliance'))
        self.assertIsNotNone(response.context['initial_data'])
        self.assertIn('materiality', response.context['initial_data'])

    def test_api_returns_200(self):
        company = Company.objects.create(name='ApiComp')
        url = reverse('dashboard:compliance_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_api_content_type_is_json(self):
        company = Company.objects.create(name='JsonComp')
        url = reverse('dashboard:compliance_data', kwargs={'pk': company.pk})
        response = self.client.get(url)
        self.assertIn('application/json', response['Content-Type'])

    def test_api_404_on_missing_company(self):
        url = reverse('dashboard:compliance_data', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_api_post_not_allowed(self):
        company = Company.objects.create(name='PostComp')
        url = reverse('dashboard:compliance_data', kwargs={'pk': company.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 405)
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.CompliancePageViewTests -v 2`
Expected: FAIL (`NoReverseMatch` pour `dashboard:compliance`).

- [ ] **Step 3: Ajouter les deux vues en fin de `views.py`**

Ajouter en fin de `dashboard/views.py` :

```python
@require_GET
def compliance(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_compliance_data(first)
    return render(request, 'dashboard/compliance.html', {
        'companies': companies,
        'initial_data': initial_data,
    })


@require_GET
def compliance_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_compliance_data(company))
```

- [ ] **Step 4: Ajouter les routes dans `urls.py`**

Dans `dashboard/urls.py`, ajouter avant la ligne `]` finale :

```python
    path('compliance/', views.compliance, name='compliance'),
    path('api/company/<int:pk>/compliance/', views.compliance_data, name='compliance_data'),
```

- [ ] **Step 5: Créer un template minimal pour passer les tests**

Créer `dashboard/templates/dashboard/compliance.html` (version minimale, étoffée en Task 6) :

```html
{% extends "base.html" %}
{% load static %}
{% block title %}Conformité ESRS E4 — Easybiodiv{% endblock %}
{% block nav_compliance %}active{% endblock %}
{% block content %}<div class="comp-page" id="comp-page"></div>{% endblock %}
```

- [ ] **Step 6: Lancer les tests pour vérifier le succès**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.CompliancePageViewTests -v 2`
Expected: PASS (9 tests).

- [ ] **Step 7: Commit**

```bash
git add dashboard/views.py dashboard/urls.py dashboard/templates/dashboard/compliance.html dashboard/tests.py
git commit -m "feat(compliance): routes + vues page & API conformité E4"
```

---

### Task 5: Admin Django (saisie de la conformité)

**Files:**
- Modify: `dashboard/admin.py`
- Test: `dashboard/tests.py` (nouvelle classe `E4AdminTests`)

- [ ] **Step 1: Écrire le test admin (échouera)**

Ajouter en fin de `dashboard/tests.py` :

```python
class E4AdminTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username='boss', password='pass', email='b@b.fr'
        )
        self.client.force_login(self.admin)

    def test_assessment_changelist_loads(self):
        response = self.client.get('/admin/dashboard/e4assessment/')
        self.assertEqual(response.status_code, 200)

    def test_assessment_add_form_loads(self):
        response = self.client.get('/admin/dashboard/e4assessment/add/')
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.E4AdminTests -v 2`
Expected: FAIL (404 — modèle non enregistré dans l'admin).

- [ ] **Step 3: Enregistrer les modèles dans l'admin**

Dans `dashboard/admin.py`, modifier l'import des modèles (lignes 2-7) pour ajouter `DisclosureRequirement, E4Assessment` :

```python
from .models import (
    Country, SubnationalRegion, Commodity, Sector, SubSector,
    Asset, Asset_consumption, Company, Production, Ownership,
    Company_Revenue, Company_Revenue_Sector,
    Policy_Type, Policy_Subcategory, Policy_Level, Company_Policy,
    DisclosureRequirement, E4Assessment,
)
```

Modifier `AssetAdmin` (lignes 50-55) pour exposer les flags zones sensibles :

```python
@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    search_fields = ('name', 'country__name', 'subnational_region__name')
    list_display = (
        'name', 'country', 'subnational_region',
        'near_sensitive_zone', 'sensitive_zone_type',
    )
    list_filter = ('country', 'near_sensitive_zone', 'sensitive_zone_type')
    autocomplete_fields = ('country', 'subnational_region')
```

Ajouter en fin de `dashboard/admin.py` :

```python
class DisclosureRequirementInline(admin.TabularInline):
    model = DisclosureRequirement
    extra = 0
    fields = ('code', 'status', 'justification')


@admin.register(E4Assessment)
class E4AssessmentAdmin(admin.ModelAdmin):
    search_fields = ('company__name',)
    list_display = (
        'company', 'reporting_year', 'standard_version', 'materiality_status',
    )
    list_filter = ('standard_version', 'materiality_status', 'reporting_year')
    autocomplete_fields = ('company',)
    inlines = (DisclosureRequirementInline,)
    fieldsets = (
        (None, {
            'fields': (
                'company', 'reporting_year', 'standard_version',
                'materiality_status', 'materiality_justification', 'created_by',
            )
        }),
        ('Approche LEAP', {
            'fields': (
                ('leap_locate_status', 'leap_locate_notes'),
                ('leap_evaluate_status', 'leap_evaluate_notes'),
                ('leap_assess_status', 'leap_assess_notes'),
            )
        }),
    )
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.E4AdminTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/admin.py dashboard/tests.py
git commit -m "feat(compliance): admin E4Assessment + DR inline + flags zones sensibles Asset"
```

---

### Task 6: Activation nav + template complet

**Files:**
- Modify: `templates/base.html` (ligne 109 : lien nav)
- Modify: `dashboard/templates/dashboard/compliance.html` (template complet)

- [ ] **Step 1: Activer le lien de navigation**

Dans `templates/base.html`, remplacer la ligne 109 :

```html
            <a href="#" class="sidebar__nav-link {% block nav_compliance %}{% endblock %}" aria-label="Conformité CSRD">
```

par :

```html
            <a href="{% url 'dashboard:compliance' %}" class="sidebar__nav-link {% block nav_compliance %}{% endblock %}" aria-label="Conformité CSRD">
```

- [ ] **Step 2: Écrire le template complet**

Remplacer entièrement `dashboard/templates/dashboard/compliance.html` par :

```html
{% extends "base.html" %}
{% load static %}

{% block title %}Conformité ESRS E4 — Easybiodiv{% endblock %}

{% block nav_compliance %}active{% endblock %}

{% block header_left %}
<div class="comp-company-picker">
  <label for="comp-company-select" class="label-caps">Entreprise</label>
  <select id="comp-company-select" class="form-input comp-company-select"
          aria-label="Sélectionner une entreprise">
    {% for c in companies %}
      <option value="{{ c.id }}">{{ c.name }}</option>
    {% endfor %}
  </select>
</div>
{% endblock header_left %}

{% block content %}
<div class="comp-page">

  <!-- Verrou de matérialité -->
  <section class="comp-gate" id="comp-materiality" aria-live="polite">
    <div class="comp-gate__main">
      <span class="comp-gate__label label-caps">Matérialité (DMA)</span>
      <span class="comp-gate__status" id="comp-materiality-status">—</span>
      <span class="comp-gate__version" id="comp-version">—</span>
    </div>
    <p class="comp-gate__justif" id="comp-materiality-justif"></p>
  </section>

  <!-- KPIs de synthèse -->
  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="comp-kpi-pct">—</div>
      <div class="kpi-card__label label-caps">Conformité globale</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="comp-kpi-compliant">—</div>
      <div class="kpi-card__label label-caps">DR conformes</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="comp-kpi-sites">—</div>
      <div class="kpi-card__label label-caps">Sites zone sensible (E4-5)</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value data-tabular" id="comp-kpi-ha">—</div>
      <div class="kpi-card__label label-caps">Surface sensible (ha)</div>
    </div>
  </div>

  <!-- Frise LEAP -->
  <section class="card comp-leap-card">
    <h2 class="comp-section-title">Approche LEAP</h2>
    <div class="comp-leap" id="comp-leap"></div>
  </section>

  <!-- Encart non-matérialité (affiché si NOT_MATERIAL) -->
  <section class="card comp-not-material" id="comp-not-material" hidden>
    <h2 class="comp-section-title">Conclusion de non-matérialité</h2>
    <p class="comp-not-material__text" id="comp-not-material-text"></p>
  </section>

  <!-- Détail des Disclosure Requirements -->
  <section class="comp-drs" id="comp-drs" aria-label="Exigences de publication"></section>

</div>
{% endblock %}

{% block extra_js %}
{{ initial_data|json_script:"comp-data" }}
{{ companies|json_script:"comp-companies" }}
<script>var COMP_API_URL = "{% url 'dashboard:compliance_data' pk=0 %}";</script>
<script src="{% static 'dashboard/js/compliance.js' %}" defer></script>
{% endblock %}
```

- [ ] **Step 3: Vérifier que la page se charge toujours**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.CompliancePageViewTests -v 2`
Expected: PASS (9 tests — le template enrichi reste valide).

- [ ] **Step 4: Commit**

```bash
git add templates/base.html dashboard/templates/dashboard/compliance.html
git commit -m "feat(compliance): template page + activation lien nav Conformité CSRD"
```

---

### Task 7: JavaScript de rendu (compliance.js)

**Files:**
- Create: `dashboard/static/dashboard/js/compliance.js`

- [ ] **Step 1: Écrire le script**

Créer `dashboard/static/dashboard/js/compliance.js` :

```javascript
'use strict';

const COMP_COMPANY_KEY = 'selected-company-id';

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('comp-companies');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('comp-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  const select = document.getElementById('comp-company-select');
  if (select) {
    select.addEventListener('change', () => {
      const id = parseInt(select.value, 10);
      localStorage.setItem(COMP_COMPANY_KEY, String(id));
      compFetch(id);
    });
  }

  const savedId = parseInt(localStorage.getItem(COMP_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && (!initialData || savedId !== initialData.company_id)) {
    if (select) select.value = String(savedId);
    compFetch(savedId);
  } else {
    if (select && initialData) select.value = String(initialData.company_id);
    if (initialData) compRender(initialData);
  }
});

function compFetch(id) {
  fetch(COMP_API_URL.replace('/0/', '/' + id + '/'))
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(compRender)
    .catch(err => console.error('compliance fetch failed:', err));
}

function compEsc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function compRender(data) {
  // — Verrou de matérialité —
  const gate = document.getElementById('comp-materiality');
  gate.className = 'comp-gate comp-gate--' + data.materiality.status.toLowerCase();
  document.getElementById('comp-materiality-status').textContent =
    data.materiality.status_label;
  document.getElementById('comp-materiality-justif').textContent =
    data.materiality.justification || '';
  document.getElementById('comp-version').textContent = data.standard_version_label;

  // — KPIs —
  document.getElementById('comp-kpi-pct').textContent =
    data.synthesis.compliance_pct + ' %';
  const compliant = data.synthesis.counts_by_status.COMPLIANT || 0;
  document.getElementById('comp-kpi-compliant').textContent =
    compliant + ' / ' + data.synthesis.applicable_count;
  document.getElementById('comp-kpi-sites').textContent =
    data.e4_5_metric.sites_count;
  document.getElementById('comp-kpi-ha').textContent =
    data.e4_5_metric.total_area_ha;

  // — Frise LEAP —
  const leapEl = document.getElementById('comp-leap');
  leapEl.innerHTML = '';
  data.leap.forEach(p => {
    const item = document.createElement('div');
    item.className = 'comp-leap__item comp-leap__item--' + p.status.toLowerCase();
    item.innerHTML =
      '<div class="comp-leap__head">' +
        '<span class="comp-leap__phase">' + compEsc(p.label) + '</span>' +
        '<span class="comp-leap__status">' + compEsc(p.status_label) + '</span>' +
      '</div>' +
      '<p class="comp-leap__summary">' + compEsc(p.derived_summary) + '</p>' +
      (p.notes ? '<p class="comp-leap__notes">' + compEsc(p.notes) + '</p>' : '');
    leapEl.appendChild(item);
  });

  // — Non-matérialité vs détail DR —
  const notMat = document.getElementById('comp-not-material');
  const drEl = document.getElementById('comp-drs');
  if (data.materiality.status === 'NOT_MATERIAL') {
    document.getElementById('comp-not-material-text').textContent =
      data.materiality.justification ||
      'Aucune justification de non-matérialité saisie.';
    notMat.hidden = false;
    drEl.hidden = true;
    drEl.innerHTML = '';
    return;
  }
  notMat.hidden = true;
  drEl.hidden = false;

  // — Cartes DR —
  drEl.innerHTML = '';
  data.disclosure_requirements.forEach(dr => {
    const card = document.createElement('article');
    card.className = 'comp-dr';
    const cond = dr.is_conditional
      ? '<span class="comp-dr__cond">Conditionnel</span>' : '';
    const sugg = (dr.auto_suggestion && dr.auto_suggestion !== dr.status)
      ? '<p class="comp-dr__suggestion">Suggestion auto : ' +
        compEsc(dr.auto_suggestion) + '</p>'
      : '';
    const justif = dr.justification
      ? compEsc(dr.justification)
      : '<em>Aucune justification saisie</em>';
    card.innerHTML =
      '<header class="comp-dr__head">' +
        '<span class="comp-dr__code">' + compEsc(dr.code_label) + '</span>' +
        '<span class="comp-badge comp-badge--' + dr.status.toLowerCase() + '">' +
          compEsc(dr.status_label) + '</span>' +
        cond +
      '</header>' +
      '<h3 class="comp-dr__title">' + compEsc(dr.title) + '</h3>' +
      '<p class="comp-dr__desc">' + compEsc(dr.description) + '</p>' +
      '<p class="comp-dr__ref">Référence : ' + compEsc(dr.reference) + '</p>' +
      '<p class="comp-dr__justif">' + justif + '</p>' +
      sugg;
    drEl.appendChild(card);
  });
}
```

- [ ] **Step 2: Vérifier la syntaxe JS (lecture + chargement de page)**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.CompliancePageViewTests.test_page_returns_200 -v 2`
Expected: PASS. (Validation visuelle complète en Task 10.)

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/dashboard/js/compliance.js
git commit -m "feat(compliance): rendu JS vanilla (matérialité, KPIs, LEAP, cartes DR)"
```

---

### Task 8: Styles CSS

**Files:**
- Modify: `dashboard/static/dashboard/css/style.css` (ajout en fin de fichier)

- [ ] **Step 1: Ajouter les styles des composants conformité**

Ajouter en fin de `dashboard/static/dashboard/css/style.css` :

```css
/* ── Conformité ESRS E4 ──────────────────────────────────────────── */

.comp-page { display: flex; flex-direction: column; gap: 20px; }

.comp-company-picker { display: flex; align-items: center; gap: 8px; }
.comp-company-select { min-width: 220px; }

.comp-section-title { font-size: 1rem; margin: 0 0 12px; }

/* Verrou de matérialité */
.comp-gate {
  border-radius: 12px; padding: 16px 20px;
  border-left: 5px solid #9ca3af; background: #f3f4f6;
}
.comp-gate__main { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
.comp-gate__status { font-size: 1.15rem; font-weight: 700; }
.comp-gate__version { font-size: .8rem; color: #6b7280; margin-left: auto; }
.comp-gate__justif { margin: 8px 0 0; font-size: .9rem; color: #374151; }
.comp-gate--material { background: #ecfdf5; border-left-color: #059669; }
.comp-gate--not_material { background: #fffbeb; border-left-color: #d97706; }
.comp-gate--not_assessed { background: #f3f4f6; border-left-color: #9ca3af; }

/* Frise LEAP */
.comp-leap { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.comp-leap__item {
  border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px;
  border-top: 4px solid #9ca3af;
}
.comp-leap__item--done { border-top-color: #059669; }
.comp-leap__item--in_progress { border-top-color: #2563eb; }
.comp-leap__item--todo { border-top-color: #9ca3af; }
.comp-leap__head { display: flex; justify-content: space-between; align-items: center; }
.comp-leap__phase { font-weight: 700; }
.comp-leap__status { font-size: .75rem; text-transform: uppercase; color: #6b7280; }
.comp-leap__summary { margin: 8px 0 0; font-size: .85rem; color: #374151; }
.comp-leap__notes { margin: 6px 0 0; font-size: .8rem; color: #6b7280; font-style: italic; }

/* Cartes DR */
.comp-drs { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.comp-dr {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
  padding: 16px; display: flex; flex-direction: column; gap: 6px;
}
.comp-dr__head { display: flex; align-items: center; gap: 8px; }
.comp-dr__code { font-weight: 700; font-size: .9rem; }
.comp-dr__cond {
  font-size: .7rem; text-transform: uppercase; letter-spacing: .03em;
  background: #ede9fe; color: #6d28d9; padding: 2px 7px; border-radius: 999px;
}
.comp-dr__title { font-size: 1rem; margin: 4px 0 0; }
.comp-dr__desc { font-size: .85rem; color: #4b5563; margin: 0; }
.comp-dr__ref { font-size: .75rem; color: #9ca3af; margin: 0; }
.comp-dr__justif { font-size: .85rem; color: #374151; margin: 6px 0 0; }
.comp-dr__suggestion {
  font-size: .78rem; color: #92400e; background: #fef3c7;
  padding: 4px 8px; border-radius: 6px; margin: 4px 0 0;
}

/* Badges de statut */
.comp-badge {
  font-size: .72rem; font-weight: 600; padding: 3px 9px; border-radius: 999px;
  margin-left: auto; white-space: nowrap;
}
.comp-badge--compliant { background: #d1fae5; color: #065f46; }
.comp-badge--partial { background: #fef3c7; color: #92400e; }
.comp-badge--non_compliant { background: #fee2e2; color: #991b1b; }
.comp-badge--not_started { background: #f3f4f6; color: #6b7280; }
.comp-badge--not_applicable { background: #e5e7eb; color: #4b5563; }

@media (max-width: 720px) {
  .comp-leap { grid-template-columns: 1fr; }
}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/static/dashboard/css/style.css
git commit -m "feat(compliance): styles page conformité E4 (gate, LEAP, cartes DR, badges)"
```

---

### Task 9: Données de démo Acme

**Files:**
- Modify: `dashboard/management/commands/populate_acme.py`
- Test: `dashboard/tests.py` (nouvelle classe `PopulateAcmeE4Tests`)

- [ ] **Step 1: Écrire le test de la commande (échouera)**

Ajouter en fin de `dashboard/tests.py` :

```python
class PopulateAcmeE4Tests(TestCase):

    def test_populate_creates_e4_assessment(self):
        from django.core.management import call_command
        from .models import E4Assessment, DisclosureRequirement, Asset
        call_command('populate_acme')
        assessment = E4Assessment.objects.get(company__name='Acme Corp')
        self.assertEqual(assessment.materiality_status, 'MATERIAL')
        self.assertEqual(assessment.disclosure_requirements.count(), 5)
        statuses = set(
            assessment.disclosure_requirements.values_list('status', flat=True)
        )
        self.assertIn('COMPLIANT', statuses)
        self.assertIn('NON_COMPLIANT', statuses)
        self.assertTrue(Asset.objects.filter(near_sensitive_zone=True).exists())

    def test_populate_is_idempotent(self):
        from django.core.management import call_command
        from .models import E4Assessment
        call_command('populate_acme')
        call_command('populate_acme')
        self.assertEqual(
            E4Assessment.objects.filter(company__name='Acme Corp').count(), 1
        )
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.PopulateAcmeE4Tests -v 2`
Expected: FAIL (`E4Assessment.DoesNotExist`).

- [ ] **Step 3: Étendre la commande**

Dans `dashboard/management/commands/populate_acme.py`, modifier l'import des modèles (lignes 4-9) pour ajouter `DisclosureRequirement, E4Assessment` :

```python
from dashboard.models import (
    Asset, Commodity, Company, Company_Policy, Company_Revenue,
    Company_Revenue_Sector, Country, DisclosureRequirement, E4Assessment,
    Ownership, Policy_Level, Policy_Subcategory, Policy_Type, Production,
    Sector, SubSector, SubnationalRegion,
)
```

Ajouter, juste avant le bloc final `self.stdout.write(self.style.SUCCESS(...))` (ligne ~749) :

```python
        # ── Conformité ESRS E4 (démo) ─────────────────────────────────────────

        a_para.near_sensitive_zone = True
        a_para.sensitive_zone_type = Asset.SensitiveZoneType.IUCN_KBA
        a_para.sensitive_zone_name = "Amazonie orientale — Key Biodiversity Area"
        a_para.sensitive_zone_area_ha = 1850.0
        a_para.save()

        a_sumatra.near_sensitive_zone = True
        a_sumatra.sensitive_zone_type = Asset.SensitiveZoneType.NATIONAL_PROTECTED
        a_sumatra.sensitive_zone_name = "Parc national de Tesso Nilo"
        a_sumatra.sensitive_zone_area_ha = 1230.0
        a_sumatra.save()

        assessment, _ = E4Assessment.objects.get_or_create(
            company=acme,
            reporting_year=2024,
            defaults={
                "standard_version": E4Assessment.StandardVersion.AMENDED_2025,
                "materiality_status": E4Assessment.Materiality.MATERIAL,
                "materiality_justification": (
                    "Biodiversité jugée matérielle : exposition forte (soja Cerrado, "
                    "palme Sumatra) à proximité de zones sensibles, dépendances "
                    "écosystémiques élevées sur les filières oléagineuses."
                ),
                "leap_locate_status": E4Assessment.LeapStatus.DONE,
                "leap_evaluate_status": E4Assessment.LeapStatus.IN_PROGRESS,
                "leap_assess_status": E4Assessment.LeapStatus.IN_PROGRESS,
                "leap_locate_notes": (
                    "2 sites identifiés en/près de zones sensibles (Pará, Sumatra)."
                ),
                "leap_evaluate_notes": (
                    "Dépendances eau et qualité des sols évaluées ; pollinisation en cours."
                ),
                "leap_assess_notes": (
                    "Impacts matériels confirmés sur la déforestation ; risques en cours "
                    "de chiffrage."
                ),
            },
        )

        e4_demo = [
            ("E4_1", DisclosureRequirement.Status.PARTIAL,
             "Plan de transition en cours de rédaction, alignement Kunming-Montréal visé "
             "pour 2027 ; objectifs intermédiaires non encore publiés."),
            ("E4_2", DisclosureRequirement.Status.COMPLIANT,
             "Politique biodiversité couvrant la traçabilité soja/palme et les sites "
             "proches de zones sensibles (RSPO, EUDR)."),
            ("E4_3", DisclosureRequirement.Status.PARTIAL,
             "Actions de restauration financées sur 2 sites ; hiérarchie d'atténuation "
             "appliquée hors compensation, offsets non encore engagés."),
            ("E4_4", DisclosureRequirement.Status.NON_COMPLIANT,
             "Cibles chiffrées absentes : seuils écologiques et portée géographique non "
             "définis à ce jour."),
            ("E4_5", DisclosureRequirement.Status.COMPLIANT,
             "Métrique géospatiale publiée : 2 sites en zone sensible, 3 080 ha au total, "
             "avec impacts négatifs documentés."),
        ]
        for code, status, justif in e4_demo:
            DisclosureRequirement.objects.get_or_create(
                assessment=assessment,
                code=code,
                defaults={"status": status, "justification": justif},
            )
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `.\venv\Scripts\python.exe manage.py test dashboard.tests.PopulateAcmeE4Tests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/management/commands/populate_acme.py dashboard/tests.py
git commit -m "feat(compliance): données de démo E4 pour Acme Corp"
```

---

### Task 10: Vérification finale

**Files:** aucun (validation).

- [ ] **Step 1: Vérifier qu'aucune migration n'est manquante**

Run: `.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run`
Expected: "No changes detected" (sinon, créer la migration manquante et committer).

- [ ] **Step 2: Lancer toute la suite de tests du dashboard**

Run: `.\venv\Scripts\python.exe manage.py test dashboard -v 2`
Expected: tous les tests PASS (les classes existantes + `E4ModelTests`, `E4CatalogTests`, `ComplianceDataTests`, `CompliancePageViewTests`, `E4AdminTests`, `PopulateAcmeE4Tests`).

- [ ] **Step 3: Peupler la démo et lancer le serveur**

Run:
```
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py populate_acme
.\venv\Scripts\python.exe manage.py runserver
```
Ouvrir `http://127.0.0.1:8000/compliance/`. Vérifier :
- bandeau de matérialité vert « Matérielle » pour Acme Corp ;
- KPIs renseignés (% conformité, DR conformes, 2 sites E4-5, 3080 ha) ;
- frise LEAP (Locate=Fait, Evaluate/Assess=En cours) ;
- 5 cartes DR avec badges colorés (E4-2 et E4-5 « Conforme », E4-4 « Non conforme ») ;
- lien nav « Conformité CSRD » actif.

Arrêter le serveur (Ctrl+C) une fois la vérification faite.

- [ ] **Step 4: Commit final éventuel** (si une migration manquante a été générée à l'étape 1)

```bash
git add dashboard/migrations/
git commit -m "chore(compliance): migration manquante détectée à la vérification"
```

---

## Notes d'implémentation

- **Compatibilité SQLite/PostgreSQL :** tous les nouveaux champs sont `Float/Char/Bool/Text/TextChoices`. Aucun `JSONField`. RAS côté PostGIS.
- **Sécurité XSS :** le rendu JS échappe systématiquement les valeurs via `compEsc()` (même les données admin), `innerHTML` ne reçoit que du markup contrôlé.
- **Page publique :** `compliance` n'est pas protégée par `@login_required` (cohérent avec `index` et `physical_risk`), ce qui simplifie la vérification. La saisie reste protégée derrière l'admin Django.
- **Sélecteur d'entreprise :** `<select>` natif (plus simple et accessible) plutôt que le combobox riche des autres pages — choix assumé pour ce premier jet.
- **Dérivations LEAP :** réutilisent `_get_dependencies_data` et `_get_mesure_empreinte_data` existants ; aucune logique métier dupliquée.
