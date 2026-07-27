# Refonte du modèle de données — inspiration edges LCA

> Design validé le 2026-07-04. Objet : rendre le modèle capable de gérer des
> **connexions fournisseur ↔ consommateur complexes**, de **conserver la
> localisation des assets**, et d'être **plus précis sur les facteurs de
> caractérisation (CF)** du calcul d'impact — en s'inspirant de la nomenclature
> [edges](https://edges.readthedocs.io/en/latest/nomenclature.html) sans importer
> la bibliothèque.

---

## 1. Contexte

État actuel (app `dashboard`, `models.py` monolithique) :

- Les **16 facteurs de caractérisation** (11 midpoints ReCiPe2016, 3 endpoints
  ReCiPe, 2 GBS) sont des colonnes `FloatField` **figées** sur `Commodity`.
  Ils sont **globaux** (mêmes valeurs partout) et **non extensibles** (nouvelle
  méthode/catégorie = migration + colonne).
- Les **connexions** sont éclatées sur deux modèles qui se recouvrent :
  `Production` (avec un enum plat `scope`) et `Supply_chain` (dont les deux
  extrémités sont forcément des `Asset`). Impossible de chaîner plusieurs tiers
  ou de représenter un fournisseur externe non possédé.
- La **formule d'impact** (`production × CF`, et la « dette écologique »
  `biodiversity_loss × restoration_cost × production × CF`) est **dupliquée dans
  6+ fonctions de vue**. Pas de couche service.
- L'inventaire mesuré à l'échelle site vit dans `Asset_consumption` (colonnes
  figées eau/énergie/CO₂/déchets, **sans année**).

## 2. Mapping edges → Easybiodiv

| Concept edges | Cible Easybiodiv |
|---|---|
| **Flow** (produit / flux élémentaire) | `Commodity` (technosphère) et `Flow` (inventaire mesuré) |
| **Activity** (processus localisé) | `Asset` + `Production` |
| **Exchange** (supplier → consumer + CF) | `Exchange` + `SupplyNode` |
| **Characterization Factor** régionalisé avec *fallback* `IT → RER → GLO` | `CharacterizationFactor` (fallback région → pays → global) |

## 3. Décisions structurantes (arbitrées)

1. **Ambition** : reprendre les *concepts* edges dans l'ORM Django. **Pas** de
   moteur matriciel, **pas** de numpy/scipy. 100 % Django, compatible SQLite,
   cPanel-friendly.
2. **Graphe** : nœud générique à **résolution variable** — chaque extrémité d'un
   `Exchange` pointe vers un `Asset` précis *ou* vers une `(Commodity + Localisation
   pays/région)` quand le site est inconnu. Multi-tiers supporté.
3. **CF** : **agrégés par commodity** (« impact par unité »), **régionalisés**
   avec fallback région → pays → global. L'inventaire mesuré est **conservé en
   parallèle** de l'impact ACV (les deux valeurs coexistent, jamais l'une écrase
   l'autre).
4. **Périmètre archi** : on **reste dans l'app `dashboard`** ; on extrait une
   **couche service** pour dé-dupliquer les calculs. Pas de découpage en `apps/`.
5. **`tier` remplace `scope`** : `Production.scope` (enum) → `Production.tier`
   (entier), vocabulaire partagé avec `Exchange.tier`.

## 4. Principes directeurs

- **Deux chemins distincts et conservés** : (1) *impact ACV* = `production × CF
  régionalisé` ; (2) *inventaire mesuré* asset = donnée terrain qui alimente le
  **risque** et sert de comparaison.
- **Migration par étapes** : chaque colonne figée est d'abord recopiée dans la
  nouvelle table, puis les vues basculent sur le service, puis on supprime
  l'ancien. **À aucun moment l'app n'est cassée.**
- **Compatibilité de sortie** : le service renvoie **la même forme JSON**
  qu'aujourd'hui → templates et JS front **inchangés**, seul l'intérieur des vues
  change.
- **Traçabilité CSRD** (§10 CLAUDE.md) : les CF et l'inventaire portent des champs
  de provenance (`source`, `reference`).

---

## 5. Modèle de données cible

### 5.1 Catalogue des axes (remplace les colonnes figées)

```
ImpactMethod
  name         CharField (unique)          # 'ReCiPe2016', 'GBS', 'LC-IMPACT'…
  version      CharField (blank)
  description  TextField (blank)

ImpactCategory                             # axe d'impact ACV
  method   -> ImpactMethod (related_name='categories')
  key      CharField                       # 'climate_change', 'water_consumption', 'ecosystem_diversity'…
  name     CharField
  unit     CharField
  level    CharField choices               # MIDPOINT | ENDPOINT
  theme    CharField (blank)               # 'water','carbon','land'… (appariement avec Flow)
  unique_together = (method, key)

Flow                                       # axe physique MESURÉ (inventaire), distinct des impacts
  key    CharField (unique)                # 'water','energy','co2','waste','surface_area'…
  name   CharField
  unit   CharField
  theme  CharField (blank)                 # même slug que ImpactCategory.theme
```

`theme` est le fil qui relie les deux chemins : une `ImpactCategory` « eau » et un
`Flow` « eau » partagent `theme='water'`, ce qui permet à l'UI d'afficher côte à
côte impact modélisé et mesure terrain — **sans les confondre** (unités et
sémantiques différentes).

### 5.2 Facteurs de caractérisation régionalisés

```
CharacterizationFactor
  category   -> ImpactCategory (related_name='factors')
  commodity  -> Commodity      (related_name='cfs')
  region     -> SubnationalRegion (null, blank)      ┐ résolution du lieu
  country    -> Country           (null, blank)      ┘ (les deux null = global)
  value      FloatField
  source     CharField (blank)             # provenance
  reference  CharField (blank)
  created_at, updated_at
  unique_together = (category, commodity, region, country)
```

Interprétation de la résolution :

- `region` renseigné → CF **niveau région** ;
- `region` null + `country` renseigné → CF **niveau pays** ;
- les deux null → CF **global**.

### 5.3 Graphe fournisseurs

```
SupplyNode                                 # sommet du graphe, résolution variable
  asset     -> Asset             (null, blank)   # site précis (possédé ou identifié)
  region    -> SubnationalRegion (null, blank)
  country   -> Country           (null, blank)
  commodity -> Commodity         (null, blank)   # ce que le nœud fournit (optionnel)
  name        CharField (blank)                  # libellé (surtout fournisseurs externes)
  is_external BooleanField (default False)
  created_at, updated_at
  # clean() : au moins un de {asset, region, country} requis.
  # propriétés dérivées :
  #   resolution        -> 'asset' | 'region' | 'country'
  #   effective_region  -> asset.subnational_region si asset, sinon self.region
  #   effective_country -> asset.country si asset, sinon self.country
  # (la localisation effective alimente le fallback CF)

Exchange                                   # arête dirigée fournisseur → consommateur
  supplier   -> SupplyNode (related_name='outgoing')
  consumer   -> SupplyNode (related_name='incoming')
  commodity  -> Commodity
  quantity   FloatField
  year       IntegerField
  tier       PositiveSmallIntegerField     # 0=direct, 1, 2, 3=matières premières
  data_confidence CharField choices        # 'asset' | 'region' | 'country' (repris de supplier_data_confidence)
  created_at, updated_at
  created_by -> User (null, blank)
```

**Multi-tiers** : un nœud `consumer` d'un `Exchange` peut être `supplier` d'un
autre → chaîne de profondeur arbitraire. La traversée se fait dans le service avec
une **garde anti-cycle** et une profondeur maximale bornée.

### 5.4 Inventaire mesuré

```
AssetInventory                             # généralise Asset_consumption
  asset  -> Asset (related_name='inventory')
  flow   -> Flow
  year   IntegerField
  value  FloatField
  source     CharField (blank)
  reference  CharField (blank)
  unique_together = (asset, flow, year)
```

### 5.5 Vocabulaire `tier` partagé

Constante unique (module `dashboard/services/impacts.py` ou `dashboard/constants.py`),
réutilisée par `Production`, `Exchange` et les vues :

```python
TIER_DIRECT, TIER_1, TIER_2, TIER_RAW = 0, 1, 2, 3
TIER_LABELS = {
    0: 'Opérations directes',
    1: "Tier 1 : Chaîne d'approvisionnement",
    2: 'Tier 2 : Approvisionnement amont',
    3: 'Matières premières',
}
```

### 5.6 Changements sur les modèles existants

- **`Production`** : ajout `tier` (PositiveSmallInteger, default 0) ; suppression
  de `scope` **après** data migration (`direct→0`, `tier 1→1`, `tier 2→2`,
  `raw material→3`). Le reste (asset/company/region/country/commodity/year/
  production/estimated_revenue) est inchangé.
- **`Commodity`** : suppression **des 16 colonnes** `impact_midpoint_*` (11),
  `impact_endpoint_ReCiPe2016_*` (3), `impact_endpoint_GBS_*` (2) après migration
  vers `CharacterizationFactor`. **Conservés** : `name`, `description`, `unit`,
  les 6 `dependency_*`, `biodiversity_loss_class`.
- **`Country` / `SubnationalRegion`** : **inchangés** (leurs champs
  `biodiversity_loss_*` et `restoration_cost_m2` sont déjà régionalisés et
  restent la source de la dette écologique).
- **Suppressions** (étape finale, après bascule) : modèles `Supply_chain` et
  `Asset_consumption`.

---

## 6. Couche service

Nouveau paquet de fonctions, **point d'entrée unique** appelé par **toutes** les
vues (à côté de `dashboard/services/market.py` existant) :

`dashboard/services/impacts.py`
- `build_cf_index(categories, commodities)` → charge en masse (1 `SELECT`) tous
  les CF pertinents dans un dict `(commodity_id, category_id, lieu)`.
- `cf_value(commodity, category, asset, cf_index)` → applique le fallback
  région → pays → global (voir §7).
- `commodity_impact(production, category, cf_index)` = `production.production ×
  cf_value(...)`.
- `footprint(company, ...)`, `dette_ecologique(company, ...)`,
  `evaluate_impacts(company, ...)`, `comparison_totals(company, ...)` : les
  formules aujourd'hui dupliquées, centralisées ici.
- `measured_vs_modeled(asset, theme, year)` → apparie `AssetInventory` (mesuré) et
  impact ACV (`Σ production × CF`) via `theme`.

`dashboard/services/supply.py`
- `upstream_chain(node, year, max_depth)` → traversée multi-tiers du graphe
  `Exchange`/`SupplyNode`, garde anti-cycle, pour `leap_locate` et les vues de
  connexions.

## 7. Algorithme de résolution CF (fallback)

```python
def cf_value(commodity, category, asset, cf_index):
    reg = asset.subnational_region_id
    ctry = asset.country_id
    # 1. niveau région
    if reg and (commodity.id, category.id, ('region', reg)) in cf_index:
        return cf_index[(commodity.id, category.id, ('region', reg))]
    # 2. niveau pays
    if (commodity.id, category.id, ('country', ctry)) in cf_index:
        return cf_index[(commodity.id, category.id, ('country', ctry))]
    # 3. global
    return cf_index.get((commodity.id, category.id, ('global', None)), 0.0)
```

Le chargement en masse (`build_cf_index`) évite le N+1 — important au vu du travail
récent sur la performance de chargement.

## 8. Migrations par étapes (une migration = un changement logique, §5 CLAUDE.md)

1. **Catalogue** : créer `ImpactMethod`, `ImpactCategory`, `Flow` + data
   migration de seed (16 `ImpactCategory` correspondant aux colonnes actuelles ;
   `Flow` pour eau/énergie/CO₂/déchets/surface ; `theme` renseigné).
2. **CF** : créer `CharacterizationFactor` + data migration recopiant chaque
   `Commodity.impact_*` → 1 ligne CF **globale** (`region=country=null`). Les
   calculs restent identiques.
3. **Graphe** : créer `SupplyNode` + `Exchange` + data migration depuis
   `Supply_chain` ; ajouter `Production.tier`, recopier depuis `scope`, puis
   **supprimer `scope`**.
4. **Inventaire** : créer `AssetInventory` + data migration depuis
   `Asset_consumption` (1 ligne par flux non nul ; **année = production la plus
   récente du site**, sinon année de référence par défaut à confirmer).
5. **Bascule code** (aucun schéma) : service + toutes les vues + templates +
   `populate_acme` + `admin` + `tests`.
6. **Nettoyage** : supprimer les 16 colonnes `Commodity.impact_*`, les modèles
   `Supply_chain` et `Asset_consumption`. **Seulement après** bascule et tests
   verts.

## 9. Mise à jour exhaustive des pages (livrable explicite)

| Vue / élément | Dépendance actuelle | Bascule vers |
|---|---|---|
| `index` / `company_data` (`_get_company_data`) | col `ecosystem_diversity` (footprint, dette_eco) | service impacts (CF régionalisé) |
| `mesure_empreinte` (`_get_mesure_empreinte_data`) | col `ecosystem_diversity` | service impacts |
| `leap_evaluate` (`_get_leap_evaluate_data`) | 11 midpoints + `Asset_consumption` | service impacts + `AssetInventory` |
| `leap_prepare` (`_get_leap_prepare_data`) | col `ecosystem_diversity` | service impacts |
| `dette_ecologique` (`_get_dette_ecologique_data`) | `ecosystem_diversity` + biodiv_loss + restoration | service impacts |
| `compare` (`_get_comparison_data` + `METRICS`) | 16 cols impact + deps + dette | service impacts |
| `leap_locate` (`_get_leap_locate_data`) | `Supply_chain` | `Exchange`/`SupplyNode` + `services/supply.py` |
| `dependencies` (`_get_dependencies_data`) | `Production.scope`, `_SCOPE_LABELS`, `_SCOPE_ORDER` | `Production.tier` + `TIER_LABELS` |
| `physical_risk` (`_get_physical_risk_data`) | `asset.risk_*` | inchangé maintenant ; `AssetInventory` rendu disponible |
| `populate_acme` (management command) | crée cols impact, `Supply_chain`, `Asset_consumption`, `Production.scope` | crée CF, `Exchange`/`SupplyNode`, `AssetInventory`, `Production.tier` |
| `admin.py` | modèles actuels | enregistrer nouveaux modèles, retirer champs supprimés |
| `tests.py` | tests actuels | mettre à jour + ajouter (voir §11) |

Les modules `_IMPACT_FIELDS`, `_EVALUATE_IMPACT_FIELDS`, `_DEPENDENCY_FIELDS`,
`_BIODIV_LOSS_FIELDS`, `SCORE_MAP` de `views.py` sont revus pour pointer sur le
catalogue (`ImpactCategory`) plutôt que sur des noms de colonnes.

## 10. Compatibilité SQLite / cPanel

- Uniquement `FloatField` / `FK` / `CharField` / `IntegerField` / `BooleanField`.
  Aucun PostGIS, aucun `JSONField` Postgres-only, aucun numpy/scipy.
- Contrainte « ≥ 1 localisation » de `SupplyNode` validée dans `clean()`
  (portable SQLite), pas en `CHECK` DB.
- Pas de processus long-running ni de build Node.

## 11. Stratégie de tests (§6 CLAUDE.md, couverture ≥ 70 %)

- **Tests de caractérisation (golden)** — filet de sécurité principal : capturer
  la sortie JSON de chaque fonction `_get_*_data` sur le jeu `acme` **avant**
  refonte, la figer en fixture, puis assert **identique** après refonte. Garantit
  que « toutes les pages » sont correctement migrées.
- **Fallback CF** : 3 lignes CF (région / pays / global) → vérifier la résolution
  et la valeur retenue à chaque niveau, plus le cas « aucune CF → 0.0 ».
- **Graphe** : traversée multi-tiers `upstream_chain`, y compris garde anti-cycle.
- **Data migrations** : `Commodity.impact_* == CF global` correspondant ;
  `Asset_consumption` → `AssetInventory` avec année affectée ; `scope → tier`.
- Chaque nouveau modèle : au moins un test (création nominale + un cas d'erreur,
  ex. `SupplyNode.clean()` sans localisation).

## 12. Hors périmètre / différé

- **Refonte de la formule de risque** pour consommer `AssetInventory` : la donnée
  est rendue first-class et disponible, mais le calcul de risque reste inchangé
  pour l'instant.
- **Chemin LCA inventaire + caractérisation** (flux élémentaires par commodity) :
  écarté au profit des CF agrégés régionalisés. La structure (`Flow`, `theme`)
  reste compatible avec une extension future.
- **Modèle `Location` hiérarchique** (super-régions type RER/OCDE/UE) : différé ;
  les deux FK nullable + fallback 3 niveaux couvrent le besoin actuel.
- **CF temporels/scénarisés** (année/scénario sur les CF) : différés ; les CF sont
  statiques dans ce périmètre.

## 13. Points ouverts (à confirmer en implémentation)

- Année de référence par défaut pour la migration d'inventaire quand un site n'a
  aucune `Production` (constante configurable ? année max de la base ?).
- `surface_area` modélisée comme `Flow` (`key='surface_area'`) plutôt que comme
  attribut d'asset — à confirmer.
- Granularité exacte des champs de provenance `source` / `reference`.
