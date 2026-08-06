# Console de données superuser — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformer `/admin/` en « Console de données Easybiodiv » : réservée aux superusers, index regroupé par domaine métier, libellés français et `help_text` rendus en bulle `(?)`, thème aux couleurs du dashboard.

**Architecture:** On n'écrit pas de CRUD maison. Un `AdminSite` custom (`dashboard/admin_site.py`) installé via `AdminConfig.default_site` remplace le site par défaut sans toucher aux 28 `@admin.register` existants. Quatre overrides de templates dans `templates/admin/` (déjà prioritaire sur `APP_DIRS`) portent le regroupement, les bulles et le thème. Les libellés vivent dans `dashboard/models.py`, seule source de vérité.

**Tech Stack:** Django 6.0.5, SQLite, `django.test.TestCase`, CSS vanilla (aucun JS ajouté).

**Spec de référence :** [docs/superpowers/specs/2026-08-06-console-donnees-admin-design.md](../specs/2026-08-06-console-donnees-admin-design.md)

## Global Constraints

- **Runner de tests : `python manage.py test`**, classes `django.test.TestCase`. `pytest` n'est **pas** installé (absent de `requirements.txt` et de `.venv`, aucun fichier de config) malgré ce qu'annonce `CLAUDE.md`. Ne pas l'ajouter.
- **Environnement :** activer `.\.venv\Scripts\Activate.ps1` (PowerShell) avant toute commande `manage.py`.
- **Branche de travail :** `feat/console-donnees-admin`, déjà créée. Ne pas créer d'autre branche.
- **Aucune dépendance nouvelle**, aucun framework JS, aucun npm (`CLAUDE.md` §2).
- **Aucun JavaScript** ajouté : les bulles sont en CSS pur.
- **Une seule migration** pour l'ensemble des libellés, nommée explicitement (`CLAUDE.md` §5 : une migration = un changement logique).
- **Ne pas modifier** les migrations historiques, ni `easybiodiv/db.py`, ni les vues du dashboard.
- **Français** pour tout texte visible par l'utilisateur ; commits à l'impératif, sans accents dans le sujet (convention du dépôt).
- **Palette imposée** (reprise de `dashboard/static/dashboard/css/style.css`) : primaire `#91452d`, primaire-container `#af5d43`, fond `#fbf9f4`, surface-container `#f0eee9`, texte `#1b1c19`, texte-variant `#54433e`, outline `#87736d`, outline-variant `#dac1ba`, erreur `#ba1a1a`, police `'Inter', system-ui, sans-serif`.
- **Ordre des tâches imposé :** T1 installe le site admin ; tout le reste en dépend.

---

### Task 1: `EasybiodivAdminSite` et restriction superuser

**Files:**
- Create: `dashboard/admin_site.py`
- Create: `dashboard/tests_admin_console.py`
- Modify: `dashboard/apps.py`
- Modify: `easybiodiv/settings.py:51`

**Interfaces:**
- Consumes: rien.
- Produces: `dashboard.admin_site.EasybiodivAdminSite` — sous-classe `django.contrib.admin.AdminSite` avec `has_permission(request) -> bool`. Devient l'objet renvoyé par `django.contrib.admin.site` pour tout le reste du plan. `dashboard.apps.EasybiodivAdminConfig` — `AdminConfig` avec `default_site: str`.

**Contexte pour l'implémenteur :** `AdminSite.has_permission` renvoie aujourd'hui `request.user.is_active and request.user.is_staff`. Un compte `is_staff=True, is_superuser=False` accède donc à `/admin/`. C'est ce que la tâche corrige. En base de production, les deux seuls comptes `is_staff` sont déjà superusers : le durcissement ne verrouille personne.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `dashboard/tests_admin_console.py` :

```python
"""Tests de la console de donnees superuser (/admin durci et habille)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AdminAccessTests(TestCase):
    """Seul un superuser accede a la console."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='root', email='root@example.com', password='pwd-root-123',
        )
        # is_staff sans is_superuser : le cas que le durcissement doit fermer.
        cls.staff = User.objects.create_user(
            username='staff', password='pwd-staff-123', is_staff=True,
        )
        cls.creator = User.objects.create_user(
            username='creator', password='pwd-creator-123', role=User.CREATOR,
        )
        cls.subscriber = User.objects.create_user(
            username='abonne', password='pwd-abonne-123', role=User.SUBSCRIBER,
        )

    def test_superuser_accede_a_la_console(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)

    def test_staff_non_superuser_est_refuse(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)

    def test_creator_non_superuser_est_refuse(self):
        """Le role applicatif CREATOR suffit pour /imports/, pas pour la console."""
        self.client.force_login(self.creator)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)

    def test_subscriber_est_refuse(self):
        self.client.force_login(self.subscriber)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)

    def test_branding_de_la_console(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'Console de données')
```

- [ ] **Step 2: Lancer les tests et constater les échecs**

```bash
python manage.py test dashboard.tests_admin_console -v 2
```

Attendu : **2 échecs**, `test_staff_non_superuser_est_refuse` (obtient 200, attend 302) et `test_branding_de_la_console` (le header dit « Django administration »). Les trois autres passent déjà — `creator` et `abonne` ont `is_staff=False` et sont donc déjà refusés par Django. C'est normal : ils verrouillent l'intention, ils ne pilotent pas cette tâche.

- [ ] **Step 3: Créer le site admin**

`dashboard/admin_site.py` :

```python
"""Site admin de la console de donnees Easybiodiv.

Restreint l'acces aux superusers et regroupe l'index par domaine metier.
"""
from django.contrib import admin


class EasybiodivAdminSite(admin.AdminSite):
    site_header = 'Easybiodiv — Console de données'
    site_title = 'Console de données'
    index_title = 'Données de référence et données entreprises'

    def has_permission(self, request):
        """Console reservee aux superusers.

        Django autorise par defaut tout compte `is_staff`. Le role applicatif
        CREATOR, qui suffit pour /imports/, ne donne pas acces ici.
        """
        return request.user.is_active and request.user.is_superuser
```

- [ ] **Step 4: Déclarer l'`AppConfig` de l'admin**

Ajouter dans `dashboard/apps.py`, en conservant `DashboardConfig` tel quel :

```python
from django.contrib.admin.apps import AdminConfig


class EasybiodivAdminConfig(AdminConfig):
    """Remplace le site admin par defaut par celui de la console.

    ATTENTION : malgre son emplacement dans dashboard/apps.py, cette config
    configure l'app `django.contrib.admin` et non `dashboard` — elle herite
    `name = 'django.contrib.admin'` de SimpleAdminConfig. C'est la voie
    documentee par Django pour substituer un AdminSite : elle est independante
    de l'ordre des imports, contrairement a une reassignation de `admin.site`,
    qui ferait disparaitre silencieusement les modeles enregistres trop tot.
    """

    default_site = 'dashboard.admin_site.EasybiodivAdminSite'
```

- [ ] **Step 5: Brancher la config dans les settings**

Dans `easybiodiv/settings.py`, remplacer la première entrée de `INSTALLED_APPS` :

```python
INSTALLED_APPS = [
    'dashboard.apps.EasybiodivAdminConfig',  # remplace django.contrib.admin
    'django.contrib.auth',
```

- [ ] **Step 6: Lancer les tests et vérifier qu'ils passent**

```bash
python manage.py test dashboard.tests_admin_console -v 2
```

Attendu : 5 tests PASS.

- [ ] **Step 7: Vérifier qu'aucun modèle n'a été perdu**

```bash
python manage.py shell -c "from django.contrib import admin; print(type(admin.site).__name__, len(admin.site._registry))"
```

Attendu exactement : `EasybiodivAdminSite 29`. Si le nombre est inférieur, un `@admin.register` s'est enregistré sur l'ancien site — ne pas continuer.

- [ ] **Step 8: Lancer la suite complète pour vérifier l'absence de régression**

```bash
python manage.py test
```

Attendu : aucun échec nouveau par rapport à l'état de départ de la branche.

- [ ] **Step 9: Commit**

```bash
git add dashboard/admin_site.py dashboard/apps.py dashboard/tests_admin_console.py easybiodiv/settings.py
git commit -m "feat(admin): reserve la console de donnees aux superusers"
```

---

### Task 2: Enregistrer `Currency` et `ESG_data`

**Files:**
- Modify: `dashboard/admin.py:2-11` (imports) et fin de fichier
- Modify: `dashboard/tests_admin_console.py`

**Interfaces:**
- Consumes: `EasybiodivAdminSite` de T1 (via `admin.site`).
- Produces: `CurrencyAdmin` et `ESGDataAdmin` enregistrés ; `admin.site._registry` passe à 31 modèles. T3 les référence dans `GROUPS`.

**Contexte :** inventaire fait en comparant `admin.site._registry` à `apps.get_models()`. `Currency` (avec ses taux `ratio_USD`) n'est même pas importé dans `admin.py`. `ESG_data` est importé mais jamais enregistré, alors qu'il porte `employees_number`, consommé par la page ESG. Ces deux tables sont aujourd'hui inéditables. `DisclosureRequirement` est le troisième non-enregistré : il reste volontairement en `TabularInline` sous `E4Assessment`, ne pas y toucher.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter dans `dashboard/tests_admin_console.py` :

```python
from django.contrib import admin as django_admin

from dashboard.models import Currency, ESG_data


class AdminCoverageTests(TestCase):
    """Les tables editables le restent."""

    def test_currency_est_enregistre(self):
        self.assertIn(Currency, django_admin.site._registry)

    def test_esg_data_est_enregistre(self):
        self.assertIn(ESG_data, django_admin.site._registry)
```

- [ ] **Step 2: Lancer les tests et constater l'échec**

```bash
python manage.py test dashboard.tests_admin_console.AdminCoverageTests -v 2
```

Attendu : 2 FAIL, les deux modèles sont absents du registre.

- [ ] **Step 3: Ajouter les imports**

Dans `dashboard/admin.py`, compléter le bloc d'import depuis `.models` avec `Currency` et en conservant `ESG_data` déjà présent :

```python
from .models import (
    Country, SubnationalRegion, Commodity, Sector, SubSector,
    Asset, Company, Production, Ownership,
    Company_Revenue, Company_Revenue_Sector,
    Policy_Type, Policy_Subcategory, Policy_Level, Company_Policy,
    DisclosureRequirement, E4Assessment, ESG_data, Carbon_emission,
    Currency,
    ImpactMethod, ImpactCategory, CharacterizationFactor,
    SupplyNode, Exchange, Flow, AssetInventory,
    ClimateScenario, ScenarioVariable, SectorCreditProfile,
)
```

- [ ] **Step 4: Écrire les deux `ModelAdmin`**

Ajouter à la fin de `dashboard/admin.py`, en suivant les conventions du fichier :

```python
@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    search_fields = ('code', 'name')
    list_display = ('code', 'name', 'symbol', 'ratio_USD')


@admin.register(ESG_data)
class ESGDataAdmin(admin.ModelAdmin):
    search_fields = ('company__name',)
    list_display = ('company', 'year', 'employees_number')
    list_filter = ('year',)
    autocomplete_fields = ('company',)
```

- [ ] **Step 5: Lancer les tests et vérifier qu'ils passent**

```bash
python manage.py test dashboard.tests_admin_console -v 2
```

Attendu : 7 tests PASS.

- [ ] **Step 6: Vérifier le décompte du registre**

```bash
python manage.py shell -c "from django.contrib import admin; print(len(admin.site._registry))"
```

Attendu exactement : `31`.

- [ ] **Step 7: Commit**

```bash
git add dashboard/admin.py dashboard/tests_admin_console.py
git commit -m "feat(admin): rend Currency et ESG_data editables"
```

---

### Task 3: Regroupement de l'index par domaine

**Files:**
- Modify: `dashboard/admin_site.py`
- Create: `templates/admin/app_list.html`
- Modify: `dashboard/tests_admin_console.py`

**Interfaces:**
- Consumes: `EasybiodivAdminSite` (T1), `Currency` et `ESG_data` enregistrés (T2).
- Produces: `dashboard.admin_site.GROUPS` — `list[tuple[str, list[type[models.Model]]]]`, ordonnée. `dashboard.admin_site.UNGROUPED_TITLE` — `str`, vaut `'Non classé'`. `EasybiodivAdminSite.get_app_list(request, app_label=None) -> list[dict]`.

**Contexte :** `get_app_list` sert **deux** usages — l'index et la nav latérale (`app_label=None`), et la vue par-app `/admin/dashboard/` (`app_label='dashboard'`). Ne regrouper que le premier cas, sinon la seconde casse. `self._build_app_dict(request)` renvoie un dict par app dont chaque entrée de `models` contient la clé `model` (la classe), vérifié dans Django 6.0.5.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter dans `dashboard/tests_admin_console.py` :

```python
from django.test import RequestFactory

from dashboard.admin_site import GROUPS, UNGROUPED_TITLE


class AdminGroupingTests(TestCase):
    """L'index est regroupe par domaine, sans table orpheline."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='root2', email='root2@example.com', password='pwd-root-123',
        )

    def _app_list(self):
        request = RequestFactory().get('/admin/')
        request.user = self.superuser
        return django_admin.site.get_app_list(request)

    def test_titres_de_groupes_uniques(self):
        titres = [titre for titre, _ in GROUPS]
        self.assertEqual(len(titres), len(set(titres)))

    def test_aucun_modele_dans_deux_groupes(self):
        modeles = [m for _, liste in GROUPS for m in liste]
        self.assertEqual(len(modeles), len(set(modeles)))

    def test_tous_les_modeles_enregistres_sont_classes(self):
        """Garde-fou : un modele ajoute plus tard ne doit pas disparaitre."""
        classes = {m for _, liste in GROUPS for m in liste}
        manquants = sorted(
            m._meta.label for m in django_admin.site._registry if m not in classes
        )
        self.assertEqual(manquants, [])

    def test_groupe_non_classe_absent_de_l_index(self):
        titres = [app['name'] for app in self._app_list()]
        self.assertNotIn(UNGROUPED_TITLE, titres)

    def test_index_expose_les_groupes_dans_l_ordre(self):
        attendus = [titre for titre, _ in GROUPS]
        self.assertEqual([app['name'] for app in self._app_list()], attendus)

    def test_vue_par_app_toujours_accessible(self):
        """La surcharge ne doit pas casser /admin/dashboard/."""
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:app_list', args=['dashboard']))
        self.assertEqual(response.status_code, 200)

    def test_changelist_toujours_accessible(self):
        """Toute page admin rend la nav laterale via app_list.html : une
        changelist verifie donc aussi l'override de ce template."""
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:dashboard_country_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Référentiels géographiques')

    def test_index_rend_les_titres_de_groupes(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'Référentiels géographiques')
        self.assertContains(response, 'Chaîne d&#x27;approvisionnement')
```

- [ ] **Step 2: Lancer les tests et constater les échecs**

```bash
python manage.py test dashboard.tests_admin_console.AdminGroupingTests -v 2
```

Attendu : erreur d'import (`GROUPS` n'existe pas) — tous les tests de la classe échouent.

- [ ] **Step 3: Écrire `GROUPS` et la surcharge**

Ajouter dans `dashboard/admin_site.py`, au-dessus de la classe :

```python
from django.contrib.auth.models import Group

from authentication.models import User
from dashboard import models as m

UNGROUPED_TITLE = 'Non classé'

# Ordre d'affichage de l'index. L'ordre des modeles dans chaque groupe est
# volontairement celui de la liste, pas alphabetique : les tables parentes
# precedent leurs enfants.
GROUPS = [
    ('Référentiels géographiques', [m.Country, m.SubnationalRegion]),
    ('Référentiels sectoriels & produits', [
        m.Sector, m.SubSector, m.Commodity, m.Currency, m.SectorCreditProfile,
    ]),
    ('Entreprises & actifs', [
        m.Company, m.Asset, m.Ownership, m.Company_Revenue,
        m.Company_Revenue_Sector, m.ESG_data, m.Carbon_emission,
    ]),
    ("Chaîne d'approvisionnement", [m.Production, m.SupplyNode, m.Exchange]),
    ('Impacts & inventaire (ACV)', [
        m.ImpactMethod, m.ImpactCategory, m.CharacterizationFactor,
        m.Flow, m.AssetInventory,
    ]),
    ('Politiques & vulnérabilité', [
        m.Policy_Type, m.Policy_Subcategory, m.Policy_Level, m.Company_Policy,
    ]),
    ('Conformité CSRD / ESRS E4', [m.E4Assessment]),
    ('Scénarios climatiques', [m.ClimateScenario, m.ScenarioVariable]),
    ('Comptes', [User, Group]),
]
```

Puis, dans `EasybiodivAdminSite` :

```python
    def get_app_list(self, request, app_label=None):
        """Regroupe l'index par domaine metier.

        Ne regroupe que l'index et la nav laterale (`app_label is None`). La
        vue par-app /admin/dashboard/ passe un `app_label` et doit garder le
        comportement natif.
        """
        if app_label is not None:
            return super().get_app_list(request, app_label)

        entries = {}
        for app in self._build_app_dict(request).values():
            for entry in app['models']:
                entries[entry['model']] = entry

        app_list = []
        for titre, modeles in GROUPS:
            groupe = [entries.pop(model) for model in modeles if model in entries]
            if groupe:
                app_list.append(self._pseudo_app(titre, groupe))

        if entries:
            app_list.append(
                self._pseudo_app(UNGROUPED_TITLE, list(entries.values()))
            )
        return app_list

    @staticmethod
    def _pseudo_app(titre, modeles):
        """Groupe presente comme une app au template admin/app_list.html.

        `app_url` vide : un groupe transverse n'a pas d'URL d'app unique, et
        l'override du template rend alors le titre en texte simple.
        """
        return {
            'name': titre,
            'app_label': slugify(titre),
            'app_url': '',
            'has_module_perms': True,
            'models': modeles,
        }
```

Ajouter l'import `from django.utils.text import slugify` en tête de fichier.

- [ ] **Step 4: Surcharger `admin/app_list.html`**

Créer `templates/admin/app_list.html` en copiant intégralement le fichier de Django puis en remplaçant le seul bloc `<caption>`. Récupérer l'original :

```bash
python -c "import django.contrib.admin,os,shutil; shutil.copy(os.path.join(os.path.dirname(django.contrib.admin.__file__),'templates','admin','app_list.html'),'templates/admin/app_list.html')"
```

Puis remplacer :

```django
        <caption>
          <a href="{{ app.app_url }}" class="section" title="{% blocktranslate with name=app.name %}Models in the {{ name }} application{% endblocktranslate %}">{{ app.name }}</a>
        </caption>
```

par :

```django
        <caption>
          {% if app.app_url %}
            <a href="{{ app.app_url }}" class="section" title="{% blocktranslate with name=app.name %}Models in the {{ name }} application{% endblocktranslate %}">{{ app.name }}</a>
          {% else %}
            {# Groupe de domaine : pas d'URL d'app unique, donc pas de lien mort. #}
            <span class="section">{{ app.name }}</span>
          {% endif %}
        </caption>
```

Ne rien changer d'autre dans le fichier.

- [ ] **Step 5: Lancer les tests et vérifier qu'ils passent**

```bash
python manage.py test dashboard.tests_admin_console -v 2
```

Attendu : 15 tests PASS. Si `test_index_rend_les_titres_de_groupes` échoue sur l'apostrophe, vérifier l'échappement réel avec `python manage.py test ... -v 2` et ajuster l'assertion sur la chaîne exacte rendue (Django échappe `'` en `&#x27;`).

- [ ] **Step 6: Vérifier visuellement l'index**

```bash
python manage.py runserver
```

Ouvrir `http://127.0.0.1:8000/admin/` connecté en superuser. Vérifier : 9 titres de groupes dans l'ordre de `GROUPS`, aucun groupe « Non classé », titres non cliquables, liens de modèles fonctionnels, nav latérale gauche également regroupée.

- [ ] **Step 7: Commit**

```bash
git add dashboard/admin_site.py dashboard/tests_admin_console.py templates/admin/app_list.html
git commit -m "feat(admin): regroupe l'index de la console par domaine metier"
```

---

### Task 4: Rendu des `help_text` en bulle `(?)`

**Files:**
- Create: `templates/admin/includes/fieldset.html`
- Create: `dashboard/static/dashboard/css/admin-easybiodiv.css`
- Create: `templates/admin/base_site.html`
- Modify: `dashboard/tests_admin_console.py`

**Interfaces:**
- Consumes: `EasybiodivAdminSite` (T1).
- Produces: la classe CSS `eb-help` et le fichier `dashboard/static/dashboard/css/admin-easybiodiv.css`, que T5 complètera avec le thème. `templates/admin/base_site.html`, que T5 complètera aussi.

**Contexte :** le test s'appuie sur `authentication.User`, dont les champs héritent des `help_text` d'`AbstractUser` (`username`, `is_staff`, `groups`…). Aucune dépendance à la tâche des libellés, qui vient plus tard.

**Les deux contraintes d'accessibilité à respecter :**
1. L'icône est **décorative** (`aria-hidden="true"`, non focusable). La rendre focusable ajouterait une trentaine d'arrêts de tabulation sur un formulaire comme `Policy_Level` (15 champs).
2. La bulle se masque en `opacity` + `visibility`, **jamais en `display: none`**. Django pose automatiquement `aria-describedby` sur le widget vers l'id `_helptext` ; `display: none` sortirait la cible de l'arbre d'accessibilité.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter dans `dashboard/tests_admin_console.py` :

```python
class AdminTooltipTests(TestCase):
    """Les help_text sont rendus en bulle, pas en texte statique."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='root3', email='root3@example.com', password='pwd-root-123',
        )

    def setUp(self):
        self.client.force_login(self.superuser)
        url = reverse('admin:authentication_user_change', args=[self.superuser.pk])
        self.response = self.client.get(url)

    def test_le_formulaire_repond(self):
        self.assertEqual(self.response.status_code, 200)

    def test_la_bulle_est_rendue(self):
        self.assertContains(self.response, 'eb-help')

    def test_l_icone_est_decorative(self):
        """Non focusable : pas d'arret de tabulation supplementaire par champ."""
        self.assertContains(self.response, 'eb-help__icon')
        self.assertNotContains(self.response, 'eb-help__icon" tabindex')

    def test_l_ancre_aria_describedby_est_conservee(self):
        """Django pointe aria-describedby vers cet id : il doit survivre."""
        self.assertContains(self.response, '_helptext')

    def test_le_css_de_la_console_est_charge(self):
        self.assertContains(self.response, 'admin-easybiodiv.css')
```

- [ ] **Step 2: Lancer les tests et constater les échecs**

```bash
python manage.py test dashboard.tests_admin_console.AdminTooltipTests -v 2
```

Attendu : `test_le_formulaire_repond` et `test_l_ancre_aria_describedby_est_conservee` passent ; les 3 autres échouent (`eb-help` et le CSS n'existent pas).

- [ ] **Step 3: Surcharger `admin/includes/fieldset.html`**

Copier l'original puis modifier :

```bash
mkdir -p templates/admin/includes
python -c "import django.contrib.admin,os,shutil; shutil.copy(os.path.join(os.path.dirname(django.contrib.admin.__file__),'templates','admin','includes','fieldset.html'),'templates/admin/includes/fieldset.html')"
```

Dans le fichier copié, remplacer le bloc :

```django
                    {% if field.field.help_text %}
                        <div class="help{% if field.field.is_hidden %} hidden{% endif %}"{% if field.field.id_for_label %} id="{{ field.field.id_for_label }}_helptext"{% endif %}>
                            <div>{{ field.field.help_text|safe }}</div>
                        </div>
                    {% endif %}
```

par :

```django
                    {% if field.field.help_text %}
                        {# Bulle explicative. L'icone est decorative : l'ouverture se
                           fait au survol ET au focus du champ (.form-row:focus-within),
                           ce qui evite un arret de tabulation par champ. Le texte reste
                           dans l'arbre d'accessibilite (opacity/visibility, jamais
                           display:none) car Django y pointe via aria-describedby. #}
                        <span class="eb-help{% if field.field.is_hidden %} hidden{% endif %}">
                            <span class="eb-help__icon" aria-hidden="true">?</span>
                            <span class="eb-help__bubble"{% if field.field.id_for_label %} id="{{ field.field.id_for_label }}_helptext"{% endif %}>{{ field.field.help_text|safe }}</span>
                        </span>
                    {% endif %}
```

Ne rien changer d'autre dans le fichier.

- [ ] **Step 4: Écrire le CSS des bulles**

Créer `dashboard/static/dashboard/css/admin-easybiodiv.css` :

```css
/* Console de donnees Easybiodiv — surcouche de django.contrib.admin.
   Le theme (variables) est ajoute par une tache ulterieure. */

/* ── Bulles explicatives (help_text) ──────────────────────────────────── */

.eb-help {
  position: relative;
  display: inline-flex;
  margin-left: 6px;
  vertical-align: middle;
}

.eb-help__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1px solid #87736d;
  background: #f0eee9;
  color: #54433e;
  font: 600 11px/1 'Inter', system-ui, sans-serif;
  cursor: help;
}

/* Masquage par opacity/visibility et JAMAIS display:none : la bulle est la
   cible de l'aria-describedby que Django pose sur le champ. */
.eb-help__bubble {
  position: absolute;
  bottom: calc(100% + 8px);
  left: -8px;
  z-index: 20;
  width: max-content;
  max-width: 320px;
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid #dac1ba;
  background: #ffffff;
  box-shadow: 0 4px 16px rgba(27, 28, 25, .14);
  color: #1b1c19;
  font: 400 12px/1.45 'Inter', system-ui, sans-serif;
  text-align: left;
  white-space: normal;
  opacity: 0;
  visibility: hidden;
  transition: opacity .13s ease, visibility .13s ease;
}

/* Ouverture au survol de l'icone, et au focus du champ lui-meme. */
.eb-help:hover .eb-help__bubble,
.form-row:focus-within .eb-help__bubble {
  opacity: 1;
  visibility: visible;
}

@media (prefers-reduced-motion: reduce) {
  .eb-help__bubble { transition: none; }
}
```

- [ ] **Step 5: Créer `base_site.html` pour charger le CSS**

Créer `templates/admin/base_site.html` :

```django
{% extends "admin/base.html" %}
{% load static %}

{% block title %}{{ title }} | Console de données Easybiodiv{% endblock %}

{% block branding %}
  <div id="site-name">
    <a href="{% url 'admin:index' %}">Easybiodiv — Console de données</a>
  </div>
{% endblock %}

{% block extrastyle %}
  {{ block.super }}
  <link rel="stylesheet" href="{% static 'dashboard/css/admin-easybiodiv.css' %}">
{% endblock %}
```

- [ ] **Step 6: Lancer les tests et vérifier qu'ils passent**

```bash
python manage.py test dashboard.tests_admin_console -v 2
```

Attendu : 20 tests PASS.

- [ ] **Step 7: Vérifier au navigateur, souris et clavier**

`python manage.py runserver`, puis ouvrir `http://127.0.0.1:8000/admin/authentication/user/1/change/`. Vérifier :
- survol du `?` → la bulle s'ouvre, lisible, sans être coupée par le bord de l'écran ;
- **tabulation seule** jusqu'au champ « Staff status » → la bulle s'ouvre sans que le `?` ait pris le focus ;
- le nombre d'arrêts de tabulation n'a pas augmenté par rapport à avant la tâche.

- [ ] **Step 8: Commit**

```bash
git add templates/admin/base_site.html templates/admin/includes/fieldset.html dashboard/static/dashboard/css/admin-easybiodiv.css dashboard/tests_admin_console.py
git commit -m "feat(admin): rend les help_text en bulle explicative accessible"
```

---

### Task 5: Thème Easybiodiv et chrome en français

**Files:**
- Modify: `dashboard/static/dashboard/css/admin-easybiodiv.css`
- Modify: `templates/admin/base_site.html`
- Create: `templates/admin/color_theme_toggle.html`
- Modify: `easybiodiv/settings.py:126`
- Modify: `docs/deploiement-production.md`
- Modify: `dashboard/tests_admin_console.py`

**Interfaces:**
- Consumes: `admin-easybiodiv.css` et `base_site.html` créés en T4.
- Produces: rien de consommé par les tâches suivantes.

**Contexte — pourquoi couper le mode sombre plutôt que le surcharger :** `dark_mode.css` déclare sa palette dans `@media (prefers-color-scheme: dark) { :root {…} }` **et** dans `html[data-theme="dark"] {…}`, dont la spécificité de 0,1,1 battrait un `:root` quel que soit l'ordre de chargement. `admin/base.html` charge cette feuille et `theme.js` dans un bloc dédié `{% block dark-mode-vars %}` : le neutraliser supprime le conflit au lieu d'essayer de le gagner. Le dashboard n'a aucun mode sombre, la console suit.

**Sur la locale :** vérifié avant d'écrire cette tâche — les `FloatField` de l'admin utilisent des widgets `type="number"`, non localisés. En `fr-fr` comme en `en-us`, `0.65` est accepté et `0,65` refusé. Les dates passent en `31/01/2026` tout en continuant d'accepter l'ISO. Aucune régression de saisie.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter dans `dashboard/tests_admin_console.py` :

```python
class AdminThemeTests(TestCase):
    """Console aux couleurs Easybiodiv, en francais, mono-theme."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='root4', email='root4@example.com', password='pwd-root-123',
        )

    def setUp(self):
        self.client.force_login(self.superuser)
        self.response = self.client.get(reverse('admin:index'))

    def test_le_chrome_est_en_francais(self):
        self.assertContains(self.response, 'Déconnexion')

    def test_la_langue_du_document_est_le_francais(self):
        self.assertContains(self.response, 'lang="fr-fr"')

    def test_le_mode_sombre_de_django_n_est_pas_charge(self):
        self.assertNotContains(self.response, 'dark_mode.css')

    def test_le_script_de_theme_n_est_pas_charge(self):
        self.assertNotContains(self.response, 'theme.js')

    def test_le_selecteur_de_theme_est_retire(self):
        self.assertNotContains(self.response, 'theme-toggle')
```

- [ ] **Step 2: Lancer les tests et constater les échecs**

```bash
python manage.py test dashboard.tests_admin_console.AdminThemeTests -v 2
```

Attendu : les 5 tests échouent.

- [ ] **Step 3: Passer la locale en français**

Dans `easybiodiv/settings.py` :

```python
LANGUAGE_CODE = 'fr-fr'
```

- [ ] **Step 4: Neutraliser le mode sombre dans `base_site.html`**

Ajouter ce bloc à `templates/admin/base_site.html` :

```django
{# Console mono-theme, comme le dashboard qui n'a pas de mode sombre. Ce bloc
   charge dark_mode.css et theme.js chez Django ; le vider supprime le conflit
   de specificite avec html[data-theme="dark"] au lieu d'avoir a le gagner. #}
{% block dark-mode-vars %}{% endblock %}
```

- [ ] **Step 5: Retirer le sélecteur de thème**

Créer `templates/admin/color_theme_toggle.html` contenant uniquement ce commentaire :

```django
{# Volontairement vide : la console est mono-theme, un selecteur sans effet
   vaudrait moins qu'aucun selecteur. Voir templates/admin/base_site.html. #}
```

- [ ] **Step 6: Écrire le thème**

Ajouter en **tête** de `dashboard/static/dashboard/css/admin-easybiodiv.css`, avant le bloc des bulles :

```css
/* ── Theme : redefinition des variables de base.css de Django ─────────────
   Les 49 variables du bloc :root de admin/css/base.css pilotent tout le
   chrome. Un simple :root suffit ici parce que base_site.html ne charge pas
   dark_mode.css — sinon html[data-theme="dark"] l'emporterait.
   Valeurs reprises de dashboard/static/dashboard/css/style.css. */

:root {
  --primary: #91452d;
  --secondary: #91452d;
  --accent: #af5d43;
  --primary-fg: #ffffff;

  --body-fg: #1b1c19;
  --body-bg: #fbf9f4;
  --body-quiet-color: #54433e;
  --body-medium-color: #54433e;
  --body-loud-color: #1b1c19;

  --header-color: #ffffff;
  --header-branding-color: #ffffff;
  --header-bg: #91452d;
  --header-link-color: #ffffff;

  --breadcrumbs-fg: #fffaf9;
  --breadcrumbs-link-fg: #ffffff;
  --breadcrumbs-bg: #af5d43;

  --link-fg: #91452d;
  --link-hover-color: #af5d43;
  --link-selected-fg: #91452d;

  --hairline-color: #e4e2dd;
  --border-color: #dac1ba;

  --error-fg: #ba1a1a;

  --darkened-bg: #f0eee9;
  --selected-bg: #eae8e3;
  --selected-row: #f5f3ee;

  --font-family-primary: 'Inter', system-ui, sans-serif;
}
```

- [ ] **Step 7: Documenter l'étape de déploiement**

Ajouter dans `docs/deploiement-production.md`, à la section des étapes de mise en production :

```markdown
- `python manage.py collectstatic --noinput` — obligatoire à chaque déploiement
  touchant les statiques. `STATICFILES_STORAGE` est
  `CompressedManifestStaticFilesStorage` : un fichier absent du manifeste fait
  lever une erreur à `{% static %}`, et non un simple 404. La console de données
  charge `dashboard/css/admin-easybiodiv.css`.
```

- [ ] **Step 8: Lancer les tests et vérifier qu'ils passent**

```bash
python manage.py test dashboard.tests_admin_console -v 2
```

Attendu : 25 tests PASS.

- [ ] **Step 9: Vérifier l'absence de régression sur toute la suite**

```bash
python manage.py test
```

Attendu : aucun échec nouveau. La bascule de locale est le changement le plus susceptible d'en provoquer — si un test existant casse sur un format de date ou de nombre, le signaler dans le rapport de tâche plutôt que de modifier le test à la légère.

- [ ] **Step 10: Vérifier au navigateur, y compris en thème sombre système**

`python manage.py runserver`, ouvrir `/admin/`. Vérifier : header terre cuite `#91452d`, fond parchemin, Inter, chrome en français, pas de sélecteur de thème. Puis **basculer l'OS en thème sombre** et recharger : l'apparence doit être identique, pas de bleu-gris Django.

- [ ] **Step 11: Commit**

```bash
git add dashboard/static/dashboard/css/admin-easybiodiv.css templates/admin/base_site.html templates/admin/color_theme_toggle.html easybiodiv/settings.py docs/deploiement-production.md dashboard/tests_admin_console.py
git commit -m "feat(admin): habille la console aux couleurs Easybiodiv en francais"
```

---

### Task 6: Lien d'entrée dans la sidebar du dashboard

**Files:**
- Modify: `templates/base.html:164-172`
- Modify: `dashboard/tests_admin_console.py`

**Interfaces:**
- Consumes: `admin:index` (T1).
- Produces: rien.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter dans `dashboard/tests_admin_console.py` :

```python
class SidebarEntryTests(TestCase):
    """Le lien vers la console n'apparait que pour un superuser."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='root5', email='root5@example.com', password='pwd-root-123',
        )
        cls.creator = User.objects.create_user(
            username='creator5', password='pwd-creator-123', role=User.CREATOR,
        )

    def test_le_superuser_voit_le_lien(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('dashboard:index'))
        self.assertContains(response, 'Console de données')

    def test_le_creator_ne_voit_pas_le_lien(self):
        self.client.force_login(self.creator)
        response = self.client.get(reverse('dashboard:index'))
        self.assertNotContains(response, 'Console de données')

    def test_l_anonyme_ne_voit_pas_le_lien(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertNotContains(response, 'Console de données')
```

- [ ] **Step 2: Lancer les tests et constater l'échec**

```bash
python manage.py test dashboard.tests_admin_console.SidebarEntryTests -v 2
```

Attendu : `test_le_superuser_voit_le_lien` FAIL ; les deux autres passent déjà (le lien n'existe nulle part).

- [ ] **Step 3: Ajouter le lien**

Dans `templates/base.html`, à l'intérieur de `<div class="sidebar__footer">`, juste après le bloc `{% if user.is_authenticated and user.role == 'CREATOR' %}…{% endif %}` de l'import Excel :

```django
        {% if user.is_superuser %}
        <a href="{% url 'admin:index' %}" class="sidebar__footer-link" aria-label="Console de données">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <ellipse cx="8" cy="3.5" rx="5" ry="2" stroke="currentColor" stroke-width="1.5"/>
            <path d="M3 3.5v9c0 1.1 2.24 2 5 2s5-.9 5-2v-9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M3 8c0 1.1 2.24 2 5 2s5-.9 5-2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <span class="sidebar__footer-link-label">Console de données</span>
        </a>
        {% endif %}
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

```bash
python manage.py test dashboard.tests_admin_console -v 2
```

Attendu : 28 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/base.html dashboard/tests_admin_console.py
git commit -m "feat(dashboard): ajoute le lien vers la console pour les superusers"
```

---

### Task 7: Libellés français et `help_text` code-explicites

**Files:**
- Modify: `dashboard/models.py` (tous les modèles)
- Create: `dashboard/migrations/00XX_libelles_metier_console.py` (généré)
- Modify: `dashboard/tests_admin_console.py`

**Interfaces:**
- Consumes: `GROUPS` (T3) pour la liste des modèles à couvrir.
- Produces: rien.

**Contexte — deux niveaux de libellés, et pourquoi les deux sont nécessaires :**
- `Meta.verbose_name` / `verbose_name_plural` : l'index affiche `capfirst(model._meta.verbose_name_plural)` (vérifié dans `_build_app_dict`). Sans `Meta`, l'écran d'accueil dirait « Esg datas », « Subnational regions », « Company revenue sectors ».
- `verbose_name` de champ : le libellé dans les formulaires et les en-têtes de liste.

**Règle sur les `help_text` :** n'écrire un `help_text` que là où le code établit la sémantique. Une définition inventée sur un champ de paramétrage est pire que pas de définition — elle sera crue. Les champs listés dans la section « Points ouverts » de la spec restent **sans** `help_text`, en attendant le glossaire métier : `Country.restoration_cost_m2`, `Country.biodiversity_loss_*`, `SubnationalRegion.Mean_X`/`Mean_Y`, `Asset.risk_*`, `Policy_Level.vulnerability_*`, `Policy_Level.score`, `SectorCreditProfile.carbon_pass_through`, `SectorCreditProfile.ebitda_volatility`, `Production.estimated_revenue`.

**Attention aux `Meta` existants** — `Company_Policy`, `DisclosureRequirement`, `ESG_data`, `Carbon_emission`, `CharacterizationFactor`, `AssetInventory`, `ClimateScenario`, `ScenarioVariable` ont déjà un `Meta` avec `unique_together` ou `ordering`. Ajouter les attributs dedans, sans écraser l'existant.

- [ ] **Step 1: Écrire le test de couverture qui échoue**

Ajouter dans `dashboard/tests_admin_console.py` :

```python
from django.apps import apps


class ModelLabelTests(TestCase):
    """Aucune table n'affiche un libelle derive du nom de classe."""

    def test_tous_les_modeles_ont_un_verbose_name_explicite(self):
        """Sinon l'accueil de la console dit « Esg datas »."""
        manquants = []
        for model in apps.get_app_config('dashboard').get_models():
            defaut = model.__name__.replace('_', ' ').lower()
            if str(model._meta.verbose_name).lower() == defaut:
                manquants.append(model.__name__)
        self.assertEqual(sorted(manquants), [])

    def test_tous_les_champs_ont_un_verbose_name_explicite(self):
        manquants = []
        for model in apps.get_app_config('dashboard').get_models():
            for field in model._meta.get_fields():
                if not hasattr(field, 'verbose_name') or field.auto_created:
                    continue
                defaut = field.name.replace('_', ' ').lower()
                if str(field.verbose_name).lower() == defaut:
                    manquants.append(f'{model.__name__}.{field.name}')
        self.assertEqual(sorted(manquants), [])
```

- [ ] **Step 2: Lancer les tests et constater les échecs**

```bash
python manage.py test dashboard.tests_admin_console.ModelLabelTests -v 2
```

Attendu : 2 FAIL. Le second liste ~200 champs — **conserver cette liste**, elle sert de checklist pour les étapes suivantes.

- [ ] **Step 3: Libeller les référentiels (`Country` → `SectorCreditProfile`)**

Dans `dashboard/models.py`. Modèle du patron à appliquer, pour `Country` :

```python
class Country(models.Model):
    name = models.CharField(max_length=255, verbose_name='Nom')
    water_ownership = models.CharField(
        max_length=255, verbose_name="Régime de propriété de l'eau",
    )
    land_ownership = models.CharField(
        max_length=255, verbose_name='Régime de propriété foncière',
    )
    water_Governance = models.TextField(
        blank=True, verbose_name="Gouvernance de l'eau",
    )
    land_Governance = models.TextField(
        blank=True, verbose_name='Gouvernance foncière',
    )
    restoration_cost_m2 = models.FloatField(
        default=0, verbose_name='Coût de restauration (par m²)',
    )
    biodiversity_loss_agriculture = models.FloatField(
        default=0, verbose_name='Perte de biodiversité — agriculture',
    )
    biodiversity_loss_urbanization = models.FloatField(
        default=0, verbose_name='Perte de biodiversité — urbanisation',
    )
    biodiversity_loss_mining = models.FloatField(
        default=0, verbose_name='Perte de biodiversité — extraction minière',
    )

    class Meta:
        verbose_name = 'Pays'
        verbose_name_plural = 'Pays'

    def __str__(self):
        return self.name
```

Libellés à appliquer pour les autres modèles du groupe :

| Modèle | `Meta` singulier / pluriel |
|---|---|
| `SubnationalRegion` | Région infranationale / Régions infranationales |
| `Sector` | Secteur / Secteurs |
| `SubSector` | Sous-secteur / Sous-secteurs |
| `Commodity` | Commodité / Commodités |
| `Currency` | Devise / Devises |
| `SectorCreditProfile` | Profil crédit sectoriel / Profils crédit sectoriels |

| Champ | `verbose_name` |
|---|---|
| `SubnationalRegion.name` | Nom |
| `SubnationalRegion.description` | Description |
| `SubnationalRegion.country` | Pays |
| `SubnationalRegion.restoration_cost_m2` | Coût de restauration (par m²) |
| `SubnationalRegion.Mean_X` | Coordonnée X moyenne |
| `SubnationalRegion.Mean_Y` | Coordonnée Y moyenne |
| `Sector.name` | Nom |
| `Sector.NACE_code` | Code NACE |
| `Sector.description` | Description |
| `SubSector.name` | Nom |
| `SubSector.sector` | Secteur |
| `SubSector.NACE_code` | Code NACE |
| `SubSector.description` | Description |
| `SubSector.Water_dependency` | Dépendance — approvisionnement en eau |
| `SubSector.Pollination_dependency` | Dépendance — pollinisation |
| `SubSector.Soil_quality_dependency` | Dépendance — qualité des sols |
| `SubSector.Carbon_Sequestration` | Dépendance — séquestration carbone |
| `SubSector.Water_purification_dependency` | Dépendance — épuration de l'eau |
| `SubSector.Pest_control_dependency` | Dépendance — contrôle des ravageurs |
| `Commodity.name` | Nom |
| `Commodity.description` | Description |
| `Commodity.unit` | Unité de mesure |
| `Commodity.dependency_water` | Dépendance — approvisionnement en eau |
| `Commodity.dependency_pollination` | Dépendance — pollinisation |
| `Commodity.dependency_soil_quality` | Dépendance — qualité des sols |
| `Commodity.dependency_carbon_sequestration` | Dépendance — séquestration carbone |
| `Commodity.dependency_water_purification` | Dépendance — épuration de l'eau |
| `Commodity.dependency_pest_control` | Dépendance — contrôle des ravageurs |
| `Commodity.biodiversity_loss_class` | Classe de perte de biodiversité |
| `Currency.code` | Code ISO |
| `Currency.name` | Nom |
| `Currency.symbol` | Symbole |
| `Currency.ratio_USD` | Taux de conversion vers l'USD |
| `SectorCreditProfile.sector` | Secteur |
| `SectorCreditProfile.pd_baseline` | Probabilité de défaut de référence |
| `SectorCreditProfile.ebitda_margin` | Marge d'EBITDA |
| `SectorCreditProfile.ebitda_volatility` | Volatilité de l'EBITDA |
| `SectorCreditProfile.carbon_pass_through` | Répercussion du coût carbone |
| `SectorCreditProfile.source` | Source |
| `SectorCreditProfile.reference` | Référence |
| `SectorCreditProfile.created_at` | Créé le |
| `SectorCreditProfile.updated_at` | Modifié le |

`help_text` de ce groupe — uniquement ceux que le code établit :

```python
# Commodity.unit  (default="tonnes", multiplie les CF dans services/impacts.py)
help_text='Unité dans laquelle les productions et les échanges de cette '
          'commodité sont exprimés (par défaut : tonnes).'

# Les 6 Commodity.dependency_* et les 6 SubSector.*_dependency
# (SCORE_MAP dans dashboard/views.py)
help_text='Niveau de dépendance à ce service écosystémique. Converti en '
          'score de calcul : très faible 0 · faible 0,2 · moyen 0,5 · '
          'fort 0,7 · très fort 1.'

# Commodity.biodiversity_loss_class
# (aiguille vers Country.biodiversity_loss_agriculture/urbanization/mining)
help_text='Détermine lequel des trois taux de perte du pays s’applique : '
          'agriculture, urbanisation ou extraction minière.'

# SectorCreditProfile.pd_baseline et ebitda_margin
# (docstring du modele : « valeur par defaut, surchargeable a l'ecran »)
help_text='Valeur par défaut du secteur. L’utilisateur peut la surcharger '
          'dans l’écran de stress test climatique.'
```

- [ ] **Step 4: Lancer les tests et commiter le premier lot**

```bash
python manage.py test dashboard.tests_admin_console -v 2
```

Attendu : `test_tous_les_champs_ont_un_verbose_name_explicite` échoue encore, mais la liste des manquants ne contient plus aucun champ des 7 modèles traités. Vérifier ce point précis avant de commiter.

```bash
git add dashboard/models.py
git commit -m "feat(models): libelle les referentiels geographiques et sectoriels"
```

- [ ] **Step 5: Libeller les entreprises et actifs**

| Modèle | `Meta` singulier / pluriel |
|---|---|
| `Company` | Entreprise / Entreprises |
| `Asset` | Actif / Actifs |
| `Ownership` | Détention / Détentions |
| `Company_Revenue` | Chiffre d'affaires / Chiffres d'affaires |
| `Company_Revenue_Sector` | CA par sous-secteur / CA par sous-secteur |
| `ESG_data` | Donnée ESG / Données ESG |
| `Carbon_emission` | Émission carbone / Émissions carbone |

| Champ | `verbose_name` |
|---|---|
| `Company.name` | Nom |
| `Company.description` | Description |
| `Company.isin` | Code ISIN |
| `Company.ticker` | Ticker boursier |
| `Asset.name` | Nom |
| `Asset.description` | Description |
| `Asset.latitude` | Latitude |
| `Asset.longitude` | Longitude |
| `Asset.country` | Pays |
| `Asset.subnational_region` | Région infranationale |
| `Asset.type` | Type de site |
| `Asset.risk_water` | Risque — approvisionnement en eau |
| `Asset.risk_pollination` | Risque — pollinisation |
| `Asset.risk_soil_quality` | Risque — qualité des sols |
| `Asset.risk_carbon_sequestration` | Risque — séquestration carbone |
| `Asset.risk_water_purification` | Risque — épuration de l'eau |
| `Asset.risk_pest_control` | Risque — contrôle des ravageurs |
| `Asset.risk_water_stress` | Aléa — stress hydrique |
| `Asset.risk_wildfire` | Aléa — feu de forêt |
| `Asset.risk_cyclone` | Aléa — cyclone |
| `Asset.risk_drought` | Aléa — sécheresse |
| `Asset.risk_flood` | Aléa — inondation |
| `Asset.risk_coastal_inundation` | Aléa — submersion côtière |
| `Asset.risk_heatwave` | Aléa — canicule |
| `Asset.risk_temperature_variation` | Aléa — variation de température |
| `Asset.risk_precipitation_variation` | Aléa — variation des précipitations |
| `Asset.near_sensitive_zone` | Proche d'une zone sensible |
| `Asset.sensitive_zone_type` | Type de zone sensible |
| `Asset.sensitive_zone_name` | Nom de la zone sensible |
| `Asset.sensitive_zone_area_ha` | Surface de la zone sensible (ha) |
| `Ownership.Asset` | Actif |
| `Ownership.Company` | Entreprise |
| `Ownership.ownership` | Part de détention |
| `Ownership.description` | Description |
| `Company_Revenue.company` | Entreprise |
| `Company_Revenue.year` | Exercice |
| `Company_Revenue.revenue` | Chiffre d'affaires |
| `Company_Revenue.currency` | Devise |
| `Company_Revenue_Sector.company` | Entreprise |
| `Company_Revenue_Sector.subsector` | Sous-secteur |
| `Company_Revenue_Sector.year` | Exercice |
| `Company_Revenue_Sector.revenue` | Chiffre d'affaires |
| `ESG_data.company` | Entreprise |
| `ESG_data.year` | Exercice |
| `ESG_data.employees_number` | Nombre de salariés |
| `Carbon_emission.company` | Entreprise |
| `Carbon_emission.year` | Exercice |
| `Carbon_emission.scope` | Scope |
| `Carbon_emission.carbon_emission` | Émissions (tCO₂e) |

`help_text` de ce groupe :

```python
# Asset.sensitive_zone_type / sensitive_zone_name / sensitive_zone_area_ha
help_text='Renseigné seulement si « Proche d’une zone sensible » est coché.'
```

- [ ] **Step 6: Lancer les tests et commiter le deuxième lot**

```bash
python manage.py test dashboard.tests_admin_console -v 2
git add dashboard/models.py
git commit -m "feat(models): libelle les entreprises et les actifs"
```

- [ ] **Step 7: Libeller la chaîne d'approvisionnement et l'ACV**

| Modèle | `Meta` singulier / pluriel |
|---|---|
| `Production` | Production / Productions |
| `SupplyNode` | Nœud d'approvisionnement / Nœuds d'approvisionnement |
| `Exchange` | Échange / Échanges |
| `ImpactMethod` | Méthode de caractérisation / Méthodes de caractérisation |
| `ImpactCategory` | Catégorie d'impact / Catégories d'impact |
| `CharacterizationFactor` | Facteur de caractérisation / Facteurs de caractérisation |
| `Flow` | Flux / Flux |
| `AssetInventory` | Inventaire d'actif / Inventaires d'actifs |

| Champ | `verbose_name` |
|---|---|
| `Production.commodity` | Commodité |
| `Production.asset` | Actif |
| `Production.company` | Entreprise |
| `Production.subnational_region` | Région infranationale |
| `Production.country` | Pays |
| `Production.tier` | Tier |
| `Production.year` | Année |
| `Production.production` | Quantité produite |
| `Production.estimated_revenue` | Revenu estimé |
| `SupplyNode.asset` | Actif |
| `SupplyNode.region` | Région infranationale |
| `SupplyNode.country` | Pays |
| `SupplyNode.commodity` | Commodité |
| `SupplyNode.name` | Nom |
| `SupplyNode.is_external` | Fournisseur externe |
| `SupplyNode.created_at` | Créé le |
| `SupplyNode.updated_at` | Modifié le |
| `Exchange.supplier` | Fournisseur |
| `Exchange.consumer` | Consommateur |
| `Exchange.commodity` | Commodité |
| `Exchange.quantity` | Quantité échangée |
| `Exchange.year` | Année |
| `Exchange.tier` | Tier |
| `Exchange.data_confidence` | Résolution de la donnée |
| `Exchange.created_at` | Créé le |
| `Exchange.updated_at` | Modifié le |
| `Exchange.created_by` | Créé par |
| `ImpactMethod.name` | Nom |
| `ImpactMethod.version` | Version |
| `ImpactMethod.description` | Description |
| `ImpactCategory.method` | Méthode |
| `ImpactCategory.key` | Clé technique |
| `ImpactCategory.name` | Nom |
| `ImpactCategory.unit` | Unité |
| `ImpactCategory.level` | Niveau |
| `ImpactCategory.theme` | Thème |
| `CharacterizationFactor.category` | Catégorie d'impact |
| `CharacterizationFactor.commodity` | Commodité |
| `CharacterizationFactor.region` | Région infranationale |
| `CharacterizationFactor.country` | Pays |
| `CharacterizationFactor.value` | Facteur |
| `CharacterizationFactor.source` | Source |
| `CharacterizationFactor.reference` | Référence |
| `CharacterizationFactor.created_at` | Créé le |
| `CharacterizationFactor.updated_at` | Modifié le |
| `Flow.key` | Clé technique |
| `Flow.name` | Nom |
| `Flow.unit` | Unité |
| `Flow.theme` | Thème |
| `AssetInventory.asset` | Actif |
| `AssetInventory.flow` | Flux |
| `AssetInventory.year` | Année |
| `AssetInventory.value` | Valeur mesurée |
| `AssetInventory.source` | Source |
| `AssetInventory.reference` | Référence |

`help_text` de ce groupe — c'est le lot où le code en établit le plus :

```python
# Production.tier et Exchange.tier  (TIER_LABELS dans services/supply.py)
help_text='Position dans la chaîne : 0 opérations directes · 1 chaîne '
          'd’approvisionnement · 2 approvisionnement amont · 3 matières '
          'premières.'

# SupplyNode.asset / region / country  (methode clean() du modele)
help_text='Un nœud requiert au moins un actif, une région ou un pays. Le plus '
          'précis des trois détermine sa résolution.'

# Exchange.data_confidence
help_text='Précision de la localisation d’où provient cette donnée : relevée '
          'sur l’actif, estimée à la région, ou estimée au pays.'

# ImpactCategory.key et Flow.key
help_text='Identifiant technique repris tel quel dans les clés JSON des vues. '
          'Ne pas modifier sur un enregistrement existant sans vérifier les '
          'vues qui le consomment.'

# ImpactCategory.theme et Flow.theme  (measured_vs_modeled dans services/impacts.py)
help_text='Clé d’appariement entre mesure et modèle : un inventaire d’actif '
          'est comparé aux catégories d’impact qui portent le même thème.'

# CharacterizationFactor.value  (production x CF dans services/impacts.py)
help_text='Impact généré par une unité de la commodité. Multiplié par la '
          'quantité produite pour obtenir l’impact total.'

# CharacterizationFactor.region et country  (cf_value dans services/impacts.py)
help_text='Laisser les deux vides pour un facteur global. La résolution suit '
          'l’ordre région → pays → global : le premier facteur trouvé gagne.'

# AssetInventory.value
help_text='Valeur relevée sur le terrain, dans l’unité du flux sélectionné.'
```

- [ ] **Step 8: Lancer les tests et commiter le troisième lot**

```bash
python manage.py test dashboard.tests_admin_console -v 2
git add dashboard/models.py
git commit -m "feat(models): libelle la chaine d'appro et le chemin ACV"
```

- [ ] **Step 9: Libeller les politiques, la conformité E4 et les scénarios**

| Modèle | `Meta` singulier / pluriel |
|---|---|
| `Policy_Type` | Type de politique / Types de politique |
| `Policy_Subcategory` | Sous-catégorie de politique / Sous-catégories de politique |
| `Policy_Level` | Niveau de politique / Niveaux de politique |
| `Company_Policy` | Politique d'entreprise / Politiques d'entreprise |
| `E4Assessment` | Évaluation ESRS E4 / Évaluations ESRS E4 |
| `DisclosureRequirement` | Disclosure Requirement / Disclosure Requirements |
| `ClimateScenario` | Scénario climatique / Scénarios climatiques |
| `ScenarioVariable` | Variable de scénario / Variables de scénario |

| Champ | `verbose_name` |
|---|---|
| `Policy_Type.name` | Nom |
| `Policy_Type.description` | Description |
| `Policy_Subcategory.policy_type` | Type de politique |
| `Policy_Subcategory.name` | Nom |
| `Policy_Subcategory.description` | Description |
| `Policy_Level.subcategory` | Sous-catégorie |
| `Policy_Level.name` | Nom |
| `Policy_Level.score` | Score |
| `Policy_Level.description` | Description |
| `Policy_Level.vulnerability_water` | Vulnérabilité — approvisionnement en eau |
| `Policy_Level.vulnerability_pollination` | Vulnérabilité — pollinisation |
| `Policy_Level.vulnerability_soil_quality` | Vulnérabilité — qualité des sols |
| `Policy_Level.vulnerability_carbon_sequestration` | Vulnérabilité — séquestration carbone |
| `Policy_Level.vulnerability_water_purification` | Vulnérabilité — épuration de l'eau |
| `Policy_Level.vulnerability_pest_control` | Vulnérabilité — contrôle des ravageurs |
| `Policy_Level.vulnerability_water_stress` | Vulnérabilité — stress hydrique |
| `Policy_Level.vulnerability_wildfire` | Vulnérabilité — feu de forêt |
| `Policy_Level.vulnerability_cyclone` | Vulnérabilité — cyclone |
| `Policy_Level.vulnerability_drought` | Vulnérabilité — sécheresse |
| `Policy_Level.vulnerability_flood` | Vulnérabilité — inondation |
| `Policy_Level.vulnerability_coastal_inundation` | Vulnérabilité — submersion côtière |
| `Policy_Level.vulnerability_heatwave` | Vulnérabilité — canicule |
| `Policy_Level.vulnerability_temperature_variation` | Vulnérabilité — variation de température |
| `Policy_Level.vulnerability_precipitation_variation` | Vulnérabilité — variation des précipitations |
| `Company_Policy.company` | Entreprise |
| `Company_Policy.policy_level` | Niveau de politique |
| `Company_Policy.policy_date` | Date d'adoption |
| `Company_Policy.comment` | Commentaire |
| `E4Assessment.company` | Entreprise |
| `E4Assessment.reporting_year` | Exercice de reporting |
| `E4Assessment.standard_version` | Version du standard |
| `E4Assessment.materiality_status` | Statut de matérialité |
| `E4Assessment.materiality_justification` | Justification de matérialité |
| `E4Assessment.leap_locate_status` | LEAP — Locate, statut |
| `E4Assessment.leap_evaluate_status` | LEAP — Evaluate, statut |
| `E4Assessment.leap_assess_status` | LEAP — Assess, statut |
| `E4Assessment.leap_locate_notes` | LEAP — Locate, notes |
| `E4Assessment.leap_evaluate_notes` | LEAP — Evaluate, notes |
| `E4Assessment.leap_assess_notes` | LEAP — Assess, notes |
| `E4Assessment.created_at` | Créé le |
| `E4Assessment.updated_at` | Modifié le |
| `E4Assessment.created_by` | Créé par |
| `DisclosureRequirement.assessment` | Évaluation |
| `DisclosureRequirement.code` | Code du DR |
| `DisclosureRequirement.status` | Statut de conformité |
| `DisclosureRequirement.justification` | Justification |
| `ClimateScenario.key` | Clé technique |
| `ClimateScenario.name` | Nom |
| `ClimateScenario.family` | Famille |
| `ClimateScenario.narrative` | Narratif |
| `ClimateScenario.warming_c` | Réchauffement (°C) |
| `ClimateScenario.source` | Source |
| `ClimateScenario.reference` | Référence |
| `ClimateScenario.order` | Ordre d'affichage |
| `ClimateScenario.created_at` | Créé le |
| `ClimateScenario.updated_at` | Modifié le |
| `ScenarioVariable.scenario` | Scénario |
| `ScenarioVariable.year` | Année |
| `ScenarioVariable.key` | Variable |
| `ScenarioVariable.value` | Valeur |

`help_text` de ce groupe :

```python
# E4Assessment.leap_*_status  (commentaire du modele : Prepare hors perimetre E4)
help_text='La phase Prepare est hors périmètre ESRS E4 : seules Locate, '
          'Evaluate et Assess servent à la détermination de matérialité.'

# DisclosureRequirement.code  (APPLICABLE_DRS dans compliance_catalog.py)
help_text='Les DR applicables dépendent de la version du standard retenue '
          'sur l’évaluation (5 DR pour la version amendée 2025, 6 pour '
          'l’originale 2023).'

# ScenarioVariable.value
help_text='L’unité dépend de la variable choisie : €/tCO₂e pour un prix du '
          'carbone, facteur sans unité pour un multiplicateur d’aléa.'

# ClimateScenario.order
help_text='Contrôle l’ordre d’affichage des scénarios dans les écrans.'
```

- [ ] **Step 10: Lancer les tests de libellés et vérifier qu'ils passent tous**

```bash
python manage.py test dashboard.tests_admin_console.ModelLabelTests -v 2
```

Attendu : 2 PASS. Si des champs restent listés, les traiter avant de continuer — ne pas assouplir le test.

- [ ] **Step 11: Générer la migration unique**

```bash
python manage.py makemigrations dashboard --name libelles_metier_console
```

Attendu : une seule migration, ne contenant que des opérations `AlterField` et `AlterModelOptions`. **Ouvrir le fichier et le vérifier** : la présence de `AddField`, `RemoveField`, `CreateModel` ou `AlterUniqueTogether` signale qu'un `Meta` existant a été écrasé — corriger `models.py` et régénérer.

- [ ] **Step 12: Vérifier que la migration n'émet aucun SQL**

```bash
python manage.py sqlmigrate dashboard 00XX_libelles_metier_console
```

(en remplaçant `00XX` par le numéro réel). Attendu : sortie vide ou uniquement des commentaires. `help_text` et `verbose_name` sont dans `Field.non_db_attrs`, et `AlterModelOptions` est une opération d'état pur — aucune reconstruction de table SQLite ne doit apparaître. Si du `CREATE TABLE`/`INSERT INTO` apparaît, un vrai changement de schéma s'est glissé dans le lot : ne pas continuer.

- [ ] **Step 13: Appliquer la migration et lancer toute la suite**

```bash
python manage.py migrate
python manage.py test
```

Attendu : migration appliquée instantanément, aucun échec nouveau.

- [ ] **Step 14: Vérifier au navigateur**

`python manage.py runserver`. Sur `/admin/` : les 9 groupes affichent des noms français, aucun « Esg datas ». Ouvrir `/admin/dashboard/commodity/` puis un enregistrement : libellés français, bulles `(?)` sur les champs de dépendance avec l'échelle de conversion. Ouvrir un `CharacterizationFactor` : vérifier la bulle expliquant la résolution région → pays → global.

- [ ] **Step 15: Commit**

```bash
git add dashboard/models.py dashboard/migrations/ dashboard/tests_admin_console.py
git commit -m "feat(models): libelle les politiques, la conformite E4 et les scenarios"
```

---

### Task 8: Vérification finale de la branche

**Files:**
- Modify: aucun, sauf correctif révélé par la vérification.

- [ ] **Step 1: Suite complète**

```bash
python manage.py test
```

Attendu : tout passe. Noter le total de tests.

- [ ] **Step 2: Vérifier qu'aucune migration ne manque**

```bash
python manage.py makemigrations --check --dry-run
```

Attendu : « No changes detected ». Sinon, un libellé a été modifié après la génération de la migration.

- [ ] **Step 3: Vérifier la santé du projet**

```bash
python manage.py check
python manage.py collectstatic --noinput --dry-run
```

Attendu : `System check identified no issues`, et le CSS de la console listé parmi les statiques collectés.

- [ ] **Step 4: Relire le diff complet**

```bash
git diff main...HEAD --stat
```

Vérifier qu'aucun fichier hors périmètre n'a été touché — en particulier ni `easybiodiv/db.py`, ni les vues du dashboard, ni les migrations historiques.

- [ ] **Step 5: Rapport**

Résumer : nombre de tests, décompte final de `admin.site._registry` (doit être 31), liste des champs restés sans `help_text` faute de glossaire métier (section « Points ouverts » de la spec).

---

## Notes de reprise

Ce qui reste volontairement à faire après ce plan, documenté dans la section « Points
ouverts » de la spec : les `help_text` des champs dont l'unité ou l'échelle n'est pas
établie par le code — `Asset.risk_*` (15 champs), `Policy_Level.vulnerability_*`
(15 champs), `Mean_X`/`Mean_Y`, `restoration_cost_m2`, `biodiversity_loss_*`,
`carbon_pass_through`, `ebitda_volatility`, `Policy_Level.score`,
`Production.estimated_revenue`.

Ce sont précisément les champs où une mauvaise valeur casse les calculs en silence. Le
travail consiste à récupérer les définitions métier puis à ajouter les `help_text` dans
`dashboard/models.py` — l'infrastructure d'affichage est déjà en place, il n'y a qu'un
endroit à remplir et une migration de libellés à régénérer.
