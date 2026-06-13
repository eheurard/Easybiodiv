# Page « Données ESG » — Design

> Date : 2026-06-13
> Statut : validé pour implémentation

## 1. Objectif

Ajouter une nouvelle page **Données ESG** au dashboard, insérée dans la
navigation **entre « Vue d'ensemble » et « Analyse des risques »**. La page
présente les données environnementales d'une entreprise : tendance des émissions
carbone, politiques d'entreprise (basées sur le modèle existant
`Company_Policy`), et un bloc « Market Intelligence » / « ESG News » (placeholders
en attendant une source de données externe).

Le sélecteur de thème **Environmental / Social / Governance** est présent mais
seul l'onglet **Environmental** contient des données ; Social et Governance
affichent un état vide « À venir ».

La page suit strictement les conventions du projet : `base.html`, CSS vanilla
avec les tokens existants (palette terracotta `#91452d`, Inter), JS natif par
page, vue page + vue API JSON, combobox entreprise avec `localStorage`. **Aucun
framework frontend ni Tailwind.**

## 2. Décisions de cadrage (issues du brainstorming)

| Sujet | Décision |
|---|---|
| Graphique carbone | Corriger le modèle `Carbon_emission` + ajouter des données démo. Graphique pleinement data-driven. |
| Colonne droite — Market Intelligence | Placeholder visuel complet (valeurs « démo » clairement factices), branché plus tard sur le ticker. |
| Colonne droite — ESG News | **Placeholder** avec état vide « No news yet » (à remplir juste après). |
| Onglets E/S/G | Garder les 3 onglets, seul **Environmental** rempli ; S/G → état vide « À venir ». |
| Politiques | **2 cartes en avant** = les 2 politiques au score le plus élevé ; **liste framework** = les 5 politiques. |
| Rendu graphique | **(A)** Graphique SVG construit à la main en JS vanilla (cohérent avec `dette_ecologique.js`). |
| Authentification | `@login_required` + `@require_GET` (comme la page conformité). |

## 3. Modifications backend

### 3.1 Modèle `Carbon_emission` (`dashboard/models.py`)

État actuel (à corriger) :

```python
class Carbon_emission(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    year = models.IntegerField()
    scope = models.CharField(max_length=255)
    carbon_emission = models.FloatField(default=0)

    def __str__(self):
        # BUG : self.business_activity n'existe pas
        return f"{self.company.name} - {self.year} - {self.scope} - {self.business_activity.name}"

    class Meta:
        unique_together = ('company', 'year')  # bloque plusieurs scopes / an
```

Modifications :

- `unique_together = ('company', 'year', 'scope')` — permet Scope 1/2/3 par an.
- `__str__` corrigé : `return f"{self.company.name} - {self.year} - {self.scope}"`.

### 3.2 Migration

- Nouvelle migration `dashboard/migrations/0020_alter_carbon_emission_unique_together.py`
  (générée via `makemigrations --name alter_carbon_emission_unique_together`).
- **Compatible SQLite et PostgreSQL** (changement de `unique_together` standard).
- **Ne pas** supprimer/éditer de migration historique.

### 3.3 Données de démo (`dashboard/management/commands/populate_acme.py`)

Ajouter des lignes `Carbon_emission` pour Acme Corp via `get_or_create` :

- Années ~2018 → 2024.
- Scopes : `"Scope 1"`, `"Scope 2"`, `"Scope 3"`.
- Trajectoire globale **décroissante** (cohérente avec une projection de réduction).
- Valeurs en tCO2e (ordre de grandeur réaliste, le total annuel décroît dans le temps).

### 3.4 Vues (`dashboard/views.py`)

Nouvelle fonction helper `_get_esg_data(company)` retournant un dict :

```text
{
  'company_id', 'company_name',
  'carbon': {
      'historical': [ {'year', 'total', 'scopes': {scope: value, ...}}, ... ],  # années avec données, triées
      'projection': [ {'year', 'total'}, ... ],   # extrapolation linéaire jusqu'à 2030 (incluse), dashed
      'latest_year', 'latest_total',
      'reduction_pct',     # variation total dernière année vs première année (négatif = baisse)
      'unit': 'tCO2e',
  },
  'policies': {
      'featured': [ {  # 2 politiques au score le plus élevé
          'type', 'subcategory', 'level', 'description', 'score', 'date', 'comment',
          'tags': [ ... ],   # ex. [type, level]
      }, ... ],
      'framework': [ {  # toutes les politiques
          'type', 'subcategory', 'level', 'score', 'date',
      }, ... ],
  },
  'market': {            # PLACEHOLDER démo — non câblé
      'is_demo': True,
      'isin', 'ticker',  # champs réels de Company (peuvent valoir "0")
      'price', 'currency', 'change_pct', 'market_cap', 'esg_rating',
      'relative_perf', 'sparkline': [ ... ],  # valeurs factices
  },
  'news': [],            # PLACEHOLDER vide → le template affiche « No news yet »
  'social':     {'available': False},   # onglet vide « À venir »
  'governance': {'available': False},
}
```

Détails de calcul :

- **Carbone historique** : agréger `Carbon_emission` de l'entreprise par année
  (somme des scopes) + détail par scope ; trier par année croissante.
- **Projection** : régression linéaire simple (moindres carrés) sur les totaux
  annuels historiques, extrapolée année par année jusqu'à 2030. Le premier point
  de projection se raccorde au dernier point historique (continuité visuelle).
  Si < 2 points historiques → pas de projection (`projection: []`).
- **`reduction_pct`** : `(latest_total - first_total) / first_total * 100`,
  arrondi ; `None` si pas de données.
- **Politiques** : réutiliser `Company_Policy.objects.filter(company=...)
  .select_related('policy_level__subcategory__policy_type')`.
  `featured` = tri décroissant par `policy_level.score` (None traité comme 0),
  les 2 premiers. `framework` = toutes, triées par type puis sous-catégorie.
- **Market** : valeurs démo statiques (déterministes, peu importe la source) ;
  `isin`/`ticker` lus sur `Company`. `is_demo: True` pour afficher un badge « Démo ».

Nouvelles vues (pattern identique aux pages existantes) :

```python
@login_required
@require_GET
def esg(request):
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = _get_esg_data(first)
    return render(request, 'dashboard/esg.html', {
        'companies': companies,
        'initial_data': initial_data,
    })

@login_required
@require_GET
def esg_data(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return JsonResponse(_get_esg_data(company))
```

### 3.5 URLs (`dashboard/urls.py`)

```python
path('esg-data/', views.esg, name='esg'),
path('api/company/<int:pk>/esg-data/', views.esg_data, name='esg_data'),
```

## 4. Modifications frontend

### 4.1 Navigation (`templates/base.html`)

Insérer un nouvel élément de menu **entre** « Vue d'ensemble » et le groupe
« Analyse des risques » :

```html
<li>
  <a href="{% url 'dashboard:esg' %}" class="sidebar__nav-link {% block nav_esg %}{% endblock %}" aria-label="Données ESG">
    <svg class="sidebar__nav-icon" ...> <!-- icône analytics/barres --> </svg>
    <span class="sidebar__nav-label">Données ESG</span>
  </a>
</li>
```

### 4.2 Template (`dashboard/templates/dashboard/esg.html`)

- `{% extends "base.html" %}`, `{% block nav_esg %}active{% endblock %}`.
- `header_left` : combobox entreprise (identique aux autres pages).
- Sélecteur de thème : 3 boutons (Environmental actif, Social, Governance).
- **Onglet Environmental** (visible par défaut) :
  - Colonne gauche : carte « Carbon Emissions Trend » (conteneur SVG + légende
    Historique / Projection) ; 2 cartes politiques « en avant » ; carte liste
    « Corporate Policy Framework ».
  - Colonne droite : carte « Market Intelligence » (placeholder + badge Démo) ;
    carte « Latest ESG News » (état vide « No news yet ») ; panneau décoratif
    (dégradé CSS, **pas d'image externe**).
- **Onglets Social / Governance** : conteneurs cachés avec état vide « À venir —
  aucune donnée disponible ».
- `extra_js` : `{{ companies|json_script:"esg-companies" }}`,
  `{{ initial_data|json_script:"esg-data" }}`, définition de `ESG_API_URL`,
  inclusion de `esg.js`.

### 4.3 JS (`dashboard/static/dashboard/js/esg.js`)

Calqué sur `dette_ecologique.js` :

- Lecture `esg-companies` / `esg-data`, `localStorage` clé `selected-company-id`
  (partagée avec les autres pages).
- Combobox (`deInitCombobox` équivalent) → `fetch(ESG_API_URL)` au changement.
- `esgRender(data)` : KPIs carbone, graphique SVG, cartes politiques, liste
  framework, bloc market.
- **Graphique SVG** : axes simples, ligne pleine (historique) + ligne pointillée
  (`stroke-dasharray`) pour la projection, points/labels d'années, échelle Y
  auto. Construit en `document.createElementNS` (pattern existant).
- Switch d'onglets E/S/G : affiche/masque les conteneurs, met à jour l'état
  `aria-pressed` (visuel + accessibilité).
- Helper `escHtml` (réutiliser le pattern existant).

### 4.4 CSS (`dashboard/static/dashboard/css/style.css`)

Ajouter en fin de fichier un bloc `/* ESG page */` avec classes BEM `esg-*`
utilisant exclusivement les tokens existants (`--color-primary`,
`--color-surface-container-*`, etc.). Composants : `esg-theme-tabs`,
`esg-grid` (12 colonnes : 8 / 4), `esg-chart`, `esg-policy-card`,
`esg-framework`, `esg-market`, `esg-news`, `esg-empty`.

## 5. Tests

Conformément au `CLAUDE.md` (un test nominal + un cas limite minimum) :

- `_get_esg_data` : entreprise avec données carbone + politiques → structure
  correcte, projection calculée, `featured` = 2 politiques top-score.
- `_get_esg_data` : entreprise **sans** donnée carbone → `historical: []`,
  `projection: []`, pas d'erreur.
- Vue `esg` : `@login_required` (302 si anonyme, 200 si connecté).
- Vue `esg_data` : JSON 200 pour un pk valide, 404 sinon.
- Migration : `Carbon_emission` accepte désormais plusieurs scopes pour une même
  (company, year) et rejette les doublons (company, year, scope).

## 6. Hors périmètre

- Câblage réel du bloc Market Intelligence à une API externe.
- Contenu réel de la section ESG News.
- Données et contenu des onglets Social / Governance.
- Toute fonctionnalité PostGIS (la page n'utilise pas de carte).

## 7. Fichiers touchés

- `dashboard/models.py` (modèle `Carbon_emission`)
- `dashboard/migrations/0020_*.py` (nouvelle)
- `dashboard/management/commands/populate_acme.py` (données démo carbone)
- `dashboard/views.py` (`_get_esg_data`, `esg`, `esg_data`)
- `dashboard/urls.py` (2 routes)
- `templates/base.html` (item de nav)
- `dashboard/templates/dashboard/esg.html` (nouveau)
- `dashboard/static/dashboard/js/esg.js` (nouveau)
- `dashboard/static/dashboard/css/style.css` (styles ESG)
- `dashboard/tests.py` (tests des vues/helper, module unique existant)
