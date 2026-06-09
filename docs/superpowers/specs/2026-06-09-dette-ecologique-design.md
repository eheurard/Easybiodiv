# Dette écologique — Spécification

## Contexte

Deux changements liés :

1. **Renommage** : la page "Risque de transition" devient **"Mesure d'empreinte"**. Toutes les références internes (`transition_risk`) sont renommées en `mesure_empreinte` pour que le code reflète le domaine métier.
2. **Nouvelle page** : **"Dette écologique"** ajoutée sous "Analyse des risques" dans le sidebar. Elle affiche une carte avec des marqueurs pie chart dont la taille est proportionnelle à la dette écologique (Lbiodiv) par asset ou par région subnational.

---

## 1. Navigation & renommage

### Renommage "Risque de transition" → "Mesure d'empreinte"

| Élément | Avant | Après |
|---------|-------|-------|
| Vue Django | `transition_risk` | `mesure_empreinte` |
| Vue API Django | `transition_risk_data` | `mesure_empreinte_data` |
| Helper interne | `_get_transition_risk_data` | `_get_mesure_empreinte_data` |
| URL path | `transition-risk/` | `mesure-empreinte/` |
| URL name | `transition_risk` | `mesure_empreinte` |
| URL API name | `transition_risk_data` | `mesure_empreinte_data` |
| Template | `transition_risk.html` | `mesure_empreinte.html` |
| Nav block | `nav_transition_risk` | `nav_mesure_empreinte` |
| Titre de page | "Risque de transition — Easybiodiv" | "Mesure d'empreinte — Easybiodiv" |
| Label sidebar | "Risque de transition" | "Mesure d'empreinte" |

### Nouvelle entrée sidebar

```
Analyse des risques
├── Mesure d'empreinte
├── Risque physique
└── Dette écologique        ← nouveau
```

Bloc nav : `nav_dette_ecologique`. Nécessite un nouveau `{% block nav_dette_ecologique %}` dans `base.html`.

---

## 2. Formule de la dette écologique

Pour chaque enregistrement `Production p` lié à un `Asset` :

```
Lbiodiv(p) = biodiversity_loss_{class}(p.asset.country)
           × p.asset.subnational_region.restoration_cost_m2
           × p.production
           × p.commodity.impact_endpoint_ReCiPe2016_ecosystem_diversity
```

**Résolution de `{class}`** depuis `p.commodity.biodiversity_loss_class` :

| Valeur | Champ Country utilisé |
|--------|----------------------|
| `Agriculture` | `biodiversity_loss_agriculture` |
| `Urbanisation` | `biodiversity_loss_urbanization` |
| `Mining` | `biodiversity_loss_mining` |

**Règles d'exclusion :**
- Production sans asset (`asset=None`) → ignorée.
- Asset sans `subnational_region` → ignoré (et ses productions).

**Année de référence :** pour chaque asset, on utilise uniquement les productions de l'année la plus récente (`Max('year')` par asset).

---

## 3. Backend Django

### Nouveaux fichiers / modifications

| Fichier | Modification |
|---------|-------------|
| `dashboard/views.py` | Renommer `_get_transition_risk_data` → `_get_mesure_empreinte_data`, `transition_risk` → `mesure_empreinte`, `transition_risk_data` → `mesure_empreinte_data`. Ajouter `_get_dette_ecologique_data`, `dette_ecologique`, `dette_ecologique_data`. |
| `dashboard/urls.py` | Renommer URLs + ajouter `dette-ecologique/` et `api/company/<pk>/dette-ecologique/`. |
| `dashboard/templates/dashboard/transition_risk.html` | Renommer → `mesure_empreinte.html`, mettre à jour titre et nav block. |
| `templates/base.html` | Mettre à jour label sidebar, URL et nav block pour mesure_empreinte. Ajouter entrée "Dette écologique". |
| `dashboard/templates/dashboard/dette_ecologique.html` | Nouveau template. |

### Fonction `_get_dette_ecologique_data(company)`

**Entrées :** une instance `Company`.

**Sorties :**
```json
{
  "company_id": 1,
  "company_name": "Acme",
  "year": 2023,
  "total_lbiodiv": 4200000.0,
  "commodities": [
    {"name": "Soja", "lbiodiv": 1800000.0, "pct": 0.4286}
  ],
  "assets": [
    {
      "id": 1,
      "name": "Asset Brésil-1",
      "latitude": -15.5,
      "longitude": -47.9,
      "total_lbiodiv": 1800000.0,
      "pct": 0.4286,
      "commodities": [
        {"name": "Soja", "lbiodiv": 1400000.0, "pct": 0.7778}
      ]
    }
  ],
  "regions": [
    {
      "id": 5,
      "name": "Mato Grosso",
      "latitude": -12.0,
      "longitude": -55.0,
      "total_lbiodiv": 2600000.0,
      "pct": 0.619,
      "commodities": [
        {"name": "Soja", "lbiodiv": 1800000.0, "pct": 0.6923}
      ]
    }
  ]
}
```

**Algorithme :**
1. Récupérer les assets de la company (via `Ownership`), exclure ceux sans `subnational_region`.
2. Pour chaque asset, calculer `max_year`.
3. Filtrer les productions : asset dans la liste, année = `max_year` de l'asset.
4. Pour chaque production valide, calculer `Lbiodiv(p)` avec la formule ci-dessus.
5. Agréger par asset (somme, détail par commodité).
6. Agréger par région subnational (somme des assets de la région, détail par commodité).
7. Calculer le total global. Normaliser les `pct`.
8. Agréger la liste globale `commodities` (somme toutes sources).

**URLs ajoutées :**
```python
path('dette-ecologique/', views.dette_ecologique, name='dette_ecologique'),
path('api/company/<int:pk>/dette-ecologique/', views.dette_ecologique_data, name='dette_ecologique_data'),
```

---

## 4. Frontend

### Template `dette_ecologique.html`

Structure :
1. **KPI row** (4 cartes) : Lbiodiv total · Année · Nb assets ou régions visibles · Top commodité
2. **Toggle pill** : `[Par asset]` / `[Par région subnational]`
3. **Carte MapLibre GL** (hauteur ~500px) avec marqueurs pie chart SVG
4. **Légende flottante** (bas-droite de la carte) : couleur + nom commodité + % du total global

### Marqueurs SVG (MapLibre `Marker` avec élément DOM)

**Rayon :**
```js
const r = MIN_R + (MAX_R - MIN_R) * Math.sqrt(point.total_lbiodiv / maxLbiodiv);
// MIN_R = 18, MAX_R = 60
```

**Dessin du pie** : arcs SVG calculés trigonométriquement (vanilla JS), un `<path>` par commodité.

**Tooltip** au survol (div positionné) :
- Nom de l'asset / région
- Lbiodiv total formaté
- Année
- Top 3 commodités avec %

### Palette de couleurs

8 couleurs CSS custom properties cycliques (`--pie-color-0` … `--pie-color-7`), définies dans la feuille de style. Assignées à chaque commodité par ordre alphabétique de nom, stables entre les deux vues (asset / région).

### Comportement du toggle

- Seules les données côté client (`assets[]` vs `regions[]`) sont utilisées.
- Basculer le toggle → détruire les marqueurs MapLibre existants, recréer avec la liste correspondante.
- Mettre à jour le KPI "Assets/Régions" en conséquence.

### Endpoint API consommé

- Chargement initial : données injectées via `{{ initial_data|json_script:"de-data" }}`
- Switch entreprise : `GET /api/company/<pk>/dette-ecologique/` → JSON

---

## 5. Tests

- `test_get_dette_ecologique_data_no_assets` → retour vide cohérent.
- `test_get_dette_ecologique_data_excludes_no_region` → asset sans région absent du résultat.
- `test_lbiodiv_formula_agriculture` → calcul correct pour `biodiversity_loss_class=Agriculture`.
- `test_lbiodiv_formula_urbanisation` → calcul correct pour `biodiversity_loss_class=Urbanisation`.
- `test_lbiodiv_formula_mining` → calcul correct pour `biodiversity_loss_class=Mining`.
- `test_region_aggregation` → somme des assets d'une même région correcte.
- `test_latest_year_only` → seule l'année la plus récente par asset est prise.
- `test_mesure_empreinte_view_status` → vue renommée répond 200.
- `test_dette_ecologique_view_status` → nouvelle vue répond 200.
