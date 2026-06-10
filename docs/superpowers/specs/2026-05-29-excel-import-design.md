# Import Excel — Spécification

## Contexte

Permettre aux utilisateurs avec le rôle `CREATOR` de télécharger un template Excel,
de le remplir avec des données, et de les importer dans la base via un workflow
aperçu → confirmation.

---

## Architecture

Nouvel app Django `imports`, ajoutée à `INSTALLED_APPS`. URLs sous `/imports/`.

### Composants

| Fichier | Rôle |
|---------|------|
| `imports/apps.py` | Déclaration de l'app |
| `imports/urls.py` | Routes de l'app |
| `imports/views.py` | 4 vues : index, upload, preview, confirm |
| `imports/services/excel_template.py` | Génère le `.xlsx` template |
| `imports/services/excel_parser.py` | Parse le fichier uploadé, résout FK, produit rapport |
| `imports/services/importer.py` | Sauvegarde les lignes valides en base |
| `imports/decorators.py` | `@creator_required` — redirige vers 403 si rôle != CREATOR |
| `imports/templates/imports/index.html` | Page upload + bouton télécharger template |
| `imports/templates/imports/preview.html` | Aperçu tabulaire par onglet avec statuts |

**Dépendance Python :** `openpyxl` (à ajouter dans `requirements.txt`).

---

## Contrôle d'accès

Décorateur `@creator_required` appliqué sur toutes les vues de l'app.

```python
def creator_required(view_func):
    # si non connecté : redirect vers login
    # si connecté mais role != 'CREATOR' : HTTP 403
```

Le bouton d'accès dans la sidebar n'est rendu que si `user.role == 'CREATOR'` via
un `{% if user.role == 'CREATOR' %}` dans `base.html`.

---

## Workflow

```
GET  /imports/          → page index (bouton template + formulaire upload)
POST /imports/upload/   → parse Excel → sauve JSON tmp → redirect aperçu
GET  /imports/preview/  → lit JSON tmp → affiche aperçu
POST /imports/confirm/  → lit JSON tmp → sauvegarde → supprime tmp → succès
```

---

## Structure du fichier Excel template

### Onglets référentiel (remplir en premier)

| Onglet | Colonnes |
|--------|----------|
| `Country` | name, water_ownership, land_ownership, water_Governance, land_Governance |
| `SubnationalRegion` | name, description, country_name |
| `Commodity` | name, description, unit, impact_midpoint_ReCiPe2016_water_consumption, impact_midpoint_ReCiPe2016_climate_change, impact_midpoint_ReCiPe2016_freshwater_ecotoxicity, impact_midpoint_ReCiPe2016_freshwater_eutrophication, impact_midpoint_ReCiPe2016_marine_eutrophication, impact_midpoint_ReCiPe2016_terrestrial_acidification, impact_midpoint_ReCiPe2016_soil_acidification, impact_midpoint_ReCiPe2016_ozonedepletion, impact_midpoint_ReCiPe2016_resource_depletion_fossil, impact_midpoint_ReCiPe2016_resource_depletion_minerals, impact_endpoint_ReCiPe2016_human_health, impact_endpoint_ReCiPe2016_ecosystem_diversity, impact_endpoint_ReCiPe2016_resource_availability |
| `Policy_Type` | name, description |
| `Policy_Subcategory` | name, description, policy_type_name |
| `Policy_Level` | name, score, description, subcategory_name, policy_type_name |

### Onglets données terrain

| Onglet | Colonnes |
|--------|----------|
| `Company` | name, description |
| `Asset` | name, description, latitude, longitude, country_name, subnational_region_name |
| `Production` | asset_name, commodity_name, year, production |
| `Company_Revenue` | company_name, year, revenue, currency |
| `Ownership` | asset_name, company_name, ownership, description |
| `Company_Policy` | company_name, policy_type_name, policy_subcategory_name, policy_level_name, policy_date |

### Onglet `_Référence`

Généré automatiquement à partir des données en base. Liste les valeurs acceptées
pour chaque champ FK (Country, SubnationalRegion, Commodity, etc.) en lecture seule.

---

## Résolution des clés étrangères

- Correspondance **insensible à la casse**, avec **trim des espaces**.
- Résolution dans cet ordre : d'abord la base de données existante, puis les
  lignes des autres onglets du même fichier (pour permettre l'import de nouvelles
  données référentielles en même temps que les données terrain).
- Si une FK ne peut pas être résolue : la ligne est marquée en **erreur rouge**.

---

## Aperçu (`preview.html`)

Un onglet HTML par sheet Excel. Pour chaque onglet :

- Compteurs : `X à importer / Y ignorées (doublons) / Z erreurs`
- Tableau de toutes les lignes avec statut coloré :
  - **Vert** — sera importée
  - **Jaune** — doublon, sera ignorée
  - **Rouge** — erreur, sera ignorée
- Bouton "Confirmer l'import" en bas (désactivé si 0 lignes vertes)
- Bouton "Annuler" pour revenir à la page index

---

## Fichier temporaire

- Chemin : `MEDIA_ROOT/imports/tmp/<uuid>.json`
- Clé UUID stockée dans `request.session['import_key']`
- Supprimé après confirmation réussie
- Structure JSON :
```json
{
  "sheets": {
    "Country": {
      "rows": [
        {"status": "ok", "data": {...}},
        {"status": "duplicate", "data": {...}},
        {"status": "error", "message": "...", "data": {...}}
      ]
    }
  }
}
```

---

## Ordre d'import (topologique)

1. Country
2. SubnationalRegion
3. Commodity
4. Policy_Type
5. Policy_Subcategory
6. Policy_Level
7. Company
8. Asset
9. Production
10. Company_Revenue
11. Ownership
12. Company_Policy

---

## Détection des doublons

Règles par modèle (champs utilisés pour déterminer l'unicité) :

| Modèle | Critère doublon |
|--------|----------------|
| Country | name |
| SubnationalRegion | name + country |
| Commodity | name |
| Policy_Type | name |
| Policy_Subcategory | name + policy_type |
| Policy_Level | name + subcategory |
| Company | name |
| Asset | name + country |
| Production | asset + commodity + year |
| Company_Revenue | company + year |
| Ownership | asset + company |
| Company_Policy | company + policy_level (unique_together existant) |

---

## Sidebar

Dans `base.html`, ajout d'un lien "Import Excel" dans le footer de la sidebar,
visible uniquement si `user.is_authenticated and user.role == 'CREATOR'` :

```html
{% if user.is_authenticated and user.role == 'CREATOR' %}
  <a href="{% url 'imports:index' %}" class="sidebar__footer-link">
    <!-- icône upload -->
    <span class="sidebar__footer-link-label">Import Excel</span>
  </a>
{% endif %}
```

---

## Tests

- `imports/tests/test_excel_template.py` — vérifie que le template contient tous les onglets attendus
- `imports/tests/test_excel_parser.py` — cas nominal, FK invalide, doublon, champ manquant
- `imports/tests/test_views.py` — accès refusé (SUBSCRIBER), upload, preview, confirm
