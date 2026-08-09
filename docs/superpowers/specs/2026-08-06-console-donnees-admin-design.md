# Console de données superuser — Design Spec
*Date : 2026-08-06*

## Contexte

Le besoin exprimé : *une page accessible seulement au superuser, permettant de naviguer et
modifier les données (interface CRUD) de manière intuitive, avec des tooltips explicatifs.*

Or un admin Django complet existe déjà : [dashboard/admin.py](../../../dashboard/admin.py)
enregistre 27 modèles avec `search_fields`, `list_filter` et `autocomplete_fields`, plus
`auth.Group` et `authentication.User`. Le CRUD lui-même n'est donc pas le manque. Les
manques réels sont ailleurs :

1. **Accès** — `/admin/` est ouvert à tout compte `is_staff`, pas aux seuls superusers.
2. **Lisibilité** — aucun `verbose_name` ni `help_text` nulle part. Les libellés affichés
   sont les noms de champs bruts : `Mean_X`, `pd_baseline`, `carbon_pass_through`,
   `dependency_pollination`. Le chrome de l'admin est en anglais (`LANGUAGE_CODE = 'en-us'`).
3. **Navigation** — l'index est une liste à plat de 27 modèles triés alphabétiquement sous
   un unique en-tête « Dashboard ».
4. **Trous de couverture** — trois modèles ne sont pas éditables du tout (voir plus bas).

**Décision : on n'écrit pas une page CRUD maison.** On transforme `/admin/` en
« Console de données Easybiodiv ». Réécrire à la main la navigation, les formulaires,
la validation, la recherche et les `autocomplete` de 30 modèles pour arriver au même
résultat fonctionnel serait un coût sans contrepartie.

---

## Périmètre

| Élément | Inclus |
|---|---|
| Restriction de `/admin/` aux superusers | ✅ |
| Regroupement de l'index par domaine de données | ✅ |
| `Meta.verbose_name` français sur tous les modèles | ✅ |
| `verbose_name` français sur tous les champs | ✅ |
| `help_text` là où le code métier est explicite | ✅ |
| Rendu des `help_text` en bulle `(?)` au lieu de texte statique | ✅ |
| Thème CSS aux couleurs Easybiodiv + chrome en français | ✅ |
| Enregistrement des 2 modèles aujourd'hui non éditables | ✅ |
| Lien d'entrée dans la sidebar du dashboard | ✅ |
| `help_text` sur les champs à sémantique métier non déductible du code | ❌ voir « Points ouverts » |
| Page CRUD maison hors `/admin/` | ❌ décision ci-dessus |
| Désactivation de `/admin/` | ❌ c'est la console elle-même |
| Journalisation des accès admin | ❌ hors périmètre, `admin.LogEntry` existe déjà nativement |

---

## Architecture

Fichiers créés :

| Fichier | Rôle |
|---|---|
| `dashboard/admin_site.py` | `EasybiodivAdminSite` + table `GROUPS` |
| `dashboard/apps.py` (modifié) | `EasybiodivAdminConfig` avec `default_site` |
| `templates/admin/base_site.html` | Branding, CSS de thème, neutralisation du mode sombre |
| `templates/admin/color_theme_toggle.html` | Vide — retire le sélecteur de thème |
| `templates/admin/app_list.html` | En-tête de groupe non cliquable |
| `templates/admin/includes/fieldset.html` | `help_text` → bulle `(?)` |
| `dashboard/static/dashboard/css/admin-easybiodiv.css` | Thème + styles de bulle |
| `dashboard/tests_admin_console.py` | Tests |

Fichiers modifiés : `dashboard/admin.py` (2 enregistrements), `dashboard/models.py`
(libellés), `easybiodiv/settings.py` (2 lignes), `templates/base.html` (lien sidebar).

`templates/` est déjà dans `TEMPLATES.DIRS`, consulté **avant** `APP_DIRS`. Les overrides
y gagnent donc sur les templates de `django.contrib.admin` sans configuration
supplémentaire.

---

## 1. Installation du site admin et restriction d'accès

### `dashboard/admin_site.py`

```python
class EasybiodivAdminSite(admin.AdminSite):
    site_header = 'Easybiodiv — Console de données'
    site_title = 'Console de données'
    index_title = 'Données de référence et données entreprises'

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser
```

`has_permission` passe de `is_active and is_staff` à `is_active and is_superuser`. Un
non-superuser authentifié est redirigé vers le formulaire de connexion de l'admin — c'est
le comportement natif de `AdminSite`, aucun code de gating à écrire.

**Vérifié en base avant de décider :** `elouan` et `loulou` sont les deux seuls comptes
`is_staff`, tous deux déjà `is_superuser`. Le durcissement ne verrouille personne.

À noter : la restriction est réelle et distincte du rôle applicatif. Le rôle `CREATOR`
suffit pour `/imports/` (via `creator_required`) mais **ne suffit pas** pour la console.

### Installation via `AppConfig`, pas par réassignation

```python
# dashboard/apps.py
class EasybiodivAdminConfig(AdminConfig):
    default_site = 'dashboard.admin_site.EasybiodivAdminSite'
```

```python
# easybiodiv/settings.py — INSTALLED_APPS
- 'django.contrib.admin',
+ 'dashboard.apps.EasybiodivAdminConfig',
```

C'est la voie documentée par Django et c'est le point structurant : tous les
enregistrements existants — 28 décorateurs `@admin.register` dans `dashboard/admin.py` et
`authentication/admin.py`, plus `auth.Group` enregistré par `django.contrib.auth`, soit 29
modèles — pointent vers `admin.site`. Remplacer le site via `default_site` les fait tous
basculer sans toucher une ligne d'enregistrement.

À l'implémentation, un détail qui surprend à la lecture : `EasybiodivAdminConfig` vit dans
`dashboard/apps.py` à côté de `DashboardConfig`, mais **configure l'app
`django.contrib.admin`**, pas `dashboard`. Il hérite son `name = 'django.contrib.admin'` de
`SimpleAdminConfig` (vérifié). Un commentaire dans le fichier doit le dire, sinon la
prochaine lecture conclura à une erreur.

**Alternative rejetée :** réassigner `admin.site = EasybiodivAdminSite()` dans un module
importé tôt. Le résultat dépend de l'ordre des imports — les `@admin.register` évalués
avant la réassignation enregistreraient sur l'ancien site et leurs modèles
disparaîtraient silencieusement de la console.

### Point d'entrée

Dans le footer de sidebar de [templates/base.html](../../../templates/base.html), sous
`{% if user.is_superuser %}`, à côté du lien Import Excel déjà conditionné par
`user.role == 'CREATOR'` :

```html
{% if user.is_superuser %}
<a href="{% url 'admin:index' %}" class="sidebar__footer-link">
  ... <span class="sidebar__footer-link-label">Console de données</span>
</a>
{% endif %}
```

---

## 2. Navigation regroupée par domaine

### Surcharge de `get_app_list`

```python
def get_app_list(self, request, app_label=None):
    if app_label is not None:
        return super().get_app_list(request, app_label)
    # ... regroupement selon GROUPS
```

**La garde `app_label is not None` est essentielle.** `get_app_list` sert à la fois
l'index (`app_label=None`) et la vue par-app `/admin/dashboard/` (`app_label='dashboard'`).
Ne regrouper que le premier cas laisse la seconde intacte.

Le regroupement réutilise `self._build_app_dict(request)` — qui expose la classe de modèle
sous la clé `model` — puis redistribue les entrées dans les groupes de `GROUPS`. Chaque
groupe produit un pseudo-dict d'app : `{'name': titre, 'app_label': slug, 'app_url': '',
'has_module_perms': True, 'models': [...]}`.

### Table `GROUPS`

Liste **ordonnée** de `(titre, [classes de modèles])`. L'ordre d'affichage est celui de la
table, et l'ordre des modèles dans chaque groupe est celui de la liste — pas alphabétique,
pour que les tables parentes précèdent leurs enfants.

| # | Groupe | Modèles |
|---|---|---|
| 1 | Référentiels géographiques | `Country`, `SubnationalRegion` |
| 2 | Référentiels sectoriels & produits | `Sector`, `SubSector`, `Commodity`, `Currency`\*, `SectorCreditProfile` |
| 3 | Entreprises & actifs | `Company`, `Asset`, `Ownership`, `Company_Revenue`, `Company_Revenue_Sector`, `ESG_data`\*, `Carbon_emission` |
| 4 | Chaîne d'approvisionnement | `Production`, `SupplyNode`, `Exchange` |
| 5 | Impacts & inventaire (ACV) | `ImpactMethod`, `ImpactCategory`, `CharacterizationFactor`, `Flow`, `AssetInventory` |
| 6 | Politiques & vulnérabilité | `Policy_Type`, `Policy_Subcategory`, `Policy_Level`, `Company_Policy` |
| 7 | Conformité CSRD / ESRS E4 | `E4Assessment` |
| 8 | Scénarios climatiques | `ClimateScenario`, `ScenarioVariable` |
| 9 | Comptes | `User`, `Group` |

\* Modèles à enregistrer, non éditables aujourd'hui.

Total : 31 entrées. `DisclosureRequirement` n'apparaît pas — il reste édité en
`TabularInline` sous `E4Assessment`, ce qui est plus intuitif pour un enfant d'agrégat que
comme table autonome. Le groupe 7 n'a donc qu'une entrée, c'est volontaire.

### Garde-fou « Non classé »

Tout modèle enregistré mais absent de `GROUPS` est placé dans un groupe **« Non classé »**
en fin d'index, et un test asserte que ce groupe est vide. Sans ce filet, ajouter un modèle
plus tard le rendrait invisible dans la console — un bug silencieux et difficile à relier
à sa cause. Avec, l'oubli devient un échec de test.

### Trois trous de couverture mis au jour

Inventaire fait programmatiquement (`admin.site._registry` contre `apps.get_models()`) :

| Modèle | État | Action |
|---|---|---|
| `Currency` | Absent de `admin.py`, y compris des imports | **Enregistrer** — groupe 2. Les taux `ratio_USD` sont sinon inéditables. |
| `ESG_data` | Importé dans `admin.py` mais jamais enregistré | **Enregistrer** — groupe 3. Porte `employees_number`, consommé par la page ESG. |
| `DisclosureRequirement` | Importé, utilisé en inline uniquement | **Laisser en inline**, choix assumé. |

Les deux `ModelAdmin` à ajouter suivent les conventions du fichier :
`search_fields`, `list_display`, `list_filter` sur l'année, `autocomplete_fields` sur les FK.

### Override de `admin/app_list.html`

Django rend l'en-tête de groupe en `<a href="{{ app.app_url }}">`. Deux raisons de
surcharger :

- un groupe transverse (« Comptes » = `authentication.User` + `auth.Group`) n'a pas d'URL
  d'app unique correcte ;
- `app_url` vide produit `href=""`, qui recharge la page courante — un lien qui mime un
  lien mort.

L'override rend le titre en texte simple quand `app_url` est vide, et conserve le lien
sinon. Aucune autre modification du template.

---

## 3. Libellés et tooltips

### Source unique de vérité : le modèle

`verbose_name` français sur tous les champs de [dashboard/models.py](../../../dashboard/models.py),
`help_text` là où le code métier est explicite (services de calcul, importer, tests). Aucun
dictionnaire de libellés parallèle : le jour où le glossaire métier arrive, il n'y a qu'un
endroit à remplir.

### Les noms de modèles aussi, via `Meta`

L'index de l'admin affiche `capfirst(model._meta.verbose_name_plural)` (vérifié dans
`_build_app_dict`). Sans `Meta`, les groupes afficheraient les noms dérivés des classes :
« Esg datas », « Subnational regions », « Company revenue sectors », « Sub sectors ». Chaque
modèle reçoit donc :

```python
class Meta:
    verbose_name = 'Donnée ESG'
    verbose_name_plural = 'Données ESG'
```

C'est indispensable, pas cosmétique : c'est le seul texte visible sur l'écran d'accueil de
la console. Attention aux modèles qui ont **déjà** un `Meta` (`Company_Policy`,
`DisclosureRequirement`, `ESG_data`, `Carbon_emission`, `CharacterizationFactor`,
`AssetInventory`, `ClimateScenario`, `ScenarioVariable`) : y ajouter les attributs sans
écraser `unique_together` ni `ordering`.

### Override de `admin/includes/fieldset.html`

Le template Django rend le `help_text` ainsi :

```html
<div class="help" id="{{ field.field.id_for_label }}_helptext">
  <div>{{ field.field.help_text|safe }}</div>
</div>
```

L'override remplace ce bloc par une icône `?` décorative plus une bulle. Il réutilise
`icon-unknown.svg`, livré par `django.contrib.admin`. **L'id `_helptext` est conservé
tel quel** : Django pose automatiquement `aria-describedby` sur le widget vers cet id, et
c'est ce qui donne le texte complet aux lecteurs d'écran.

### Déclenchement : `:hover` et `:focus-within` sur la ligne, pas sur l'icône

Deux contraintes se contredisent. Rendre l'icône focusable la met dans l'ordre de
tabulation : sur un formulaire comme `Policy_Level` (15 champs), cela ajoute une trentaine
d'arrêts clavier. Mais l'explication doit rester atteignable au clavier.

Résolution retenue :

- l'icône est **décorative** — `aria-hidden="true"`, non focusable ;
- la bulle se révèle sur `.form-row:hover` **et** `.form-row:focus-within`, donc dès que le
  champ lui-même prend le focus ;
- les lecteurs d'écran reçoivent le texte via l'`aria-describedby` du champ, indépendamment
  de tout affichage visuel.

Aucun JavaScript.

**Masquage : `opacity` + `visibility`, pour l'animation — pas pour l'accessibilité.**
`display` ne se transitionne pas, c'est là toute la raison du choix.

Une version antérieure de cette spec justifiait ce choix par l'accessibilité, en affirmant
que `display: none` sortirait la bulle de l'arbre d'accessibilité et laisserait
l'`aria-describedby` pointer dans le vide. **C'est faux**, et la correction vaut d'être
retenue : `visibility: hidden` retire l'élément de l'arbre exactement comme `display: none`.
Mais l'algorithme accname prévoit une exception explicite pour les nœuds *directement
référencés* — étape 2.1 *Hidden Not Referenced* : un nœud masqué ne renvoie la chaîne vide
que s'il n'est **pas** la cible d'un `aria-labelledby`/`aria-describedby`, et les user
agents « MUST include all nodes in the subtree […] when the node referenced by
`aria-labelledby` or `aria-describedby` is hidden ».

La description parvient donc aux lecteurs d'écran quelle que soit la technique de masquage.
Ce qui reste réellement obligatoire, c'est de **conserver l'`id` `_helptext`** sur la bulle :
c'est lui que Django cible.

---

## 4. Thème et langue

### `templates/admin/base_site.html`

Branding « Easybiodiv — Console de données » et chargement de
`dashboard/static/dashboard/css/admin-easybiodiv.css` après les feuilles de Django, via
`{% block extrastyle %}`.

### Le thème est une redéfinition de variables CSS

Le bloc `:root` de `base.css` de Django 6 expose 49 variables qui pilotent tout l'admin
(`--primary`, `--body-bg`, `--header-bg`, `--link-fg`, `--hairline-color`…). En réécrire une
quinzaine suffit : terre cuite `#91452d`, fond parchemin `#fbf9f4`, `Inter`, en reprenant
les valeurs de [style.css](../../../dashboard/static/dashboard/css/style.css). Une
quarantaine de lignes, au lieu de centaines de surcharges de sélecteurs.

### Mode sombre : console mono-thème assumée

Le dashboard Easybiodiv n'a aucun mode sombre (zéro occurrence de `prefers-color-scheme` ou
`data-theme` dans `style.css`). La console suit, sinon un superuser dont l'OS est en thème
sombre verrait l'admin bleu-gris de Django au lieu de la console Easybiodiv.

`dark_mode.css` déclare sa palette dans `@media (prefers-color-scheme: dark) { :root {…} }`
**et** dans `html[data-theme="dark"] {…}`, dont la spécificité de 0,1,1 battrait un simple
`:root` quel que soit l'ordre de chargement. Plutôt que de dupliquer les variables sous les
trois sélecteurs pour gagner cette bataille, on coupe à la racine — `admin/base.html` charge
la feuille et son script dans un bloc dédié :

```django
{% block dark-mode-vars %}{% endblock %}
```

Ni `dark_mode.css` ni `theme.js` ne sont alors chargés : aucun conflit de spécificité, et
`admin-easybiodiv.css` n'a qu'un bloc `:root` à écrire.

Le sélecteur de thème devient sans objet. Il vit dans son propre template
`admin/color_theme_toggle.html`, inclus par `base.html` — un override **vide** le fait
disparaître, ce qui vaut mieux qu'un `display: none` sur un contrôle qui ne fait plus rien.

### `LANGUAGE_CODE = 'fr-fr'`

Traduit l'intégralité du chrome de l'admin (boutons, filtres, messages, pagination,
libellés d'actions). Testé plutôt que supposé, sur les deux types de champ à risque :

| Locale | `0.65` | `0,65` | Rendu date | `31/01/2026` accepté |
|---|---|---|---|---|
| `en-us` | valide | refusé | `2026-01-31` | non |
| `fr-fr` | valide | refusé | `31/01/2026` | oui |

Les `FloatField` de l'admin utilisent des widgets `type="number"`, non localisés : la
saisie décimale est identique dans les deux locales. Les dates passent au format français
tout en continuant d'accepter l'ISO. Aucune régression.

### Déploiement

`STATICFILES_STORAGE` est `whitenoise.storage.CompressedManifestStaticFilesStorage`. Le
nouveau fichier CSS impose un `collectstatic` au déploiement : sans lui, `{% static %}`
lève une erreur sur un fichier absent du manifeste. À ajouter aux étapes de
[docs/deploiement-production.md](../../deploiement-production.md).

---

## 5. Migration

Modifier `verbose_name` et `help_text` **génère** une migration — Django détecte ces
attributs. Elle contiendra deux sortes d'opérations :

- des `AlterField` pour les libellés de champs. `Field.non_db_attrs` contient `help_text` et
  `verbose_name` (vérifié), donc `_field_should_be_altered` renvoie `False` et **aucun SQL
  n'est émis** : pas de reconstruction de table SQLite.
- des `AlterModelOptions` pour les `Meta.verbose_name`, opération d'état pur, sans SQL par
  construction.

L'application en production est donc instantanée et sans risque sur les données.

Une migration unique, nommée explicitement conformément à la règle « une migration = un
changement logique » de [CLAUDE.md](../../../CLAUDE.md) :

```bash
python manage.py makemigrations dashboard --name libelles_metier_console
```

---

## 6. Tests — `dashboard/tests_admin_console.py`

Nouveau fichier, suivant la convention à plat du projet (`tests.py`,
`tests_stress_test.py`).

**Runner :** `django.test.TestCase` et `python manage.py test`. À noter, contrairement à ce
qu'annonce [CLAUDE.md](../../../CLAUDE.md) : `pytest` n'est ni dans `requirements.txt` ni
installé dans `.venv`, et aucun fichier de configuration pytest n'existe. Les tests
existants sont tous en `TestCase`. On suit l'existant plutôt que d'ajouter une dépendance.

| Test | Ce qu'il protège |
|---|---|
| `SUBSCRIBER` non-superuser sur `/admin/` → redirigé | La restriction demandée |
| `CREATOR` non-superuser sur `/admin/` → redirigé | Que le rôle applicatif ne suffit pas |
| superuser sur `/admin/` → 200 | Qu'on ne s'est pas verrouillé soi-même |
| groupe « Non classé » vide | Un modèle ajouté plus tard reste visible |
| aucun modèle dans deux groupes, titres uniques | Cohérence interne de `GROUPS` |
| tout modèle `dashboard` a un `Meta.verbose_name` explicite | Qu'aucune table n'affiche « Esg datas » sur l'accueil |
| `Currency` et `ESG_data` sont enregistrés | Que les trous comblés le restent |
| `/admin/dashboard/` → 200 | Que la surcharge `get_app_list` n'a pas cassé la vue par-app |
| changelist + formulaire d'un modèle → 200, markup de bulle présent | Que l'override de `fieldset.html` rend bien |

Le dernier est le filet le plus important : un override de template `django.contrib.admin`
est exactement le genre de chose qui casse silencieusement à la prochaine montée de version
de Django.

---

## Points ouverts

Un `help_text` n'est écrit que là où le code permet de le déduire sans risque d'écrire une
définition fausse. Les champs suivants ont une sémantique — unité, échelle, convention de
signe — que le code n'établit pas, et resteront sans `help_text` en attendant le glossaire
métier :

| Champ | Ce qui manque |
|---|---|
| `Country.restoration_cost_m2` | Unité monétaire, et par m² de quoi |
| `Country.biodiversity_loss_*` | Échelle et unité (MSA.m² ? fraction ?) |
| `SubnationalRegion.Mean_X` / `Mean_Y` | Longitude/latitude, ou coordonnées projetées, et dans quel CRS |
| `Asset.risk_*` (15 champs) | Bornes de l'échelle (0–1 ou 0–100) et sens (0 = pas de risque ?) |
| `Policy_Level.vulnerability_*` (15 champs) | Multiplicateur appliqué à quoi ; sens d'un `1.0` |
| `Policy_Level.score` | Bornes et convention |
| `SectorCreditProfile.carbon_pass_through` | Fraction du coût carbone répercutée sur les prix ? |
| `SectorCreditProfile.ebitda_volatility` | Écart-type annualisé ? sur quelle période ? |
| `Production.estimated_revenue` | Devise, et méthode d'estimation |
| `Exchange.data_confidence` | Ce que « asset / region / country » qualifie exactement |

Ces champs sont ceux dont une mauvaise valeur casse les calculs en silence — ce sont
précisément ceux où un tooltip a le plus de valeur. La liste est donc à traiter comme la
suite naturelle de ce chantier, pas comme un reste optionnel.

---

## Décisions notables

- **Pas de page CRUD maison.** L'admin Django fournit déjà navigation, formulaires,
  validation, recherche et autocomplete sur 29 modèles. Le manque était la lisibilité et
  l'accès, pas le CRUD.
- **`default_site` plutôt que réassignation de `admin.site`.** Indépendant de l'ordre des
  imports ; les 28 `@admin.register` du projet restent inchangés.
- **`get_app_list` gardé sur `app_label is None`.** Sinon la vue `/admin/dashboard/` casse.
- **Groupe « Non classé » plutôt qu'une liste blanche silencieuse.** Un oubli devient un
  échec de test, pas une table invisible.
- **Icône de tooltip décorative.** Évite ~30 arrêts de tabulation par formulaire ;
  l'accessibilité passe par l'`aria-describedby` que Django pose déjà.
- **Console mono-thème, par neutralisation du bloc `dark-mode-vars`** plutôt que par
  duplication des variables sous `html[data-theme]`. Supprime le conflit au lieu de le
  gagner.
- **`DisclosureRequirement` reste en inline.** C'est un enfant d'agrégat, pas un
  référentiel.
