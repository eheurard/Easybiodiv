# Mise à jour du template Excel d'import — modèles récents

**Date** : 2026-08-06
**Statut** : validé

## Contexte

Le template Excel d'import (`imports/services/`) a été conçu en mai 2026
(spec `2026-05-29-excel-import-design.md`). Depuis, trois refontes ont modifié le
modèle de données sans que le template ne soit mis à jour :

| Refonte | Migrations | Effet sur le modèle |
|---|---|---|
| Plan A — CF régionalisés | 0024 → 0028 | Les 16 colonnes `Commodity.impact_*` sont supprimées, remplacées par `ImpactMethod` / `ImpactCategory` / `CharacterizationFactor` |
| Plan B — graphe fournisseurs | 0029 → 0035 | `Supply_chain` remplacé par `SupplyNode` + `Exchange` ; `Production.scope` remplacé par `Production.tier` |
| Plan C — inventaire mesuré | 0036 → 0040 | `Asset_consumption` remplacé par `Flow` + `AssetInventory` |
| Stress test climatique | 0042 → 0043 | Ajout de `ClimateScenario`, `ScenarioVariable`, `SectorCreditProfile` |

Le template contient donc aujourd'hui des colonnes qui ne correspondent plus à
aucun champ de modèle et ne survivent que grâce à des shims dans l'importeur
(`SCOPE_TO_TIER`, `LEGACY_IMPACT_COLUMNS`, mapping colonne → `Flow`). À
l'inverse, sept modèles récents ne sont pas importables du tout.

## Objectif

Aligner le template sur le modèle de données réel : **nettoyage complet**, sans
couche de compatibilité. Les fichiers déjà remplis avec l'ancien template ne
seront plus importables tels quels ; les utilisateurs doivent re-télécharger le
template. Décision explicitement validée.

## Architecture — inchangée

Le pipeline reste piloté par les tables déclaratives de
`imports/services/constants.py` :

- `SHEET_COLUMNS` → onglets et en-têtes générés par `excel_template.build_template()`
- `REQUIRED_FIELDS` / `FK_FIELDS` / `DUPLICATE_CRITERIA` → validation dans `excel_parser.parse_file()`
- `IMPORT_ORDER` + `_IMPORTERS` → écriture en base dans `importer.save_import()`

`imports/views.py` est entièrement générique (il itère sur `SHEET_COLUMNS`) :
**aucune modification**. Idem pour `preview.html` et `index.html`.

## Feuilles ajoutées

### Stress test climatique

| Feuille | Colonnes |
|---|---|
| `ClimateScenario` | `key`, `name`, `family`, `warming_c`, `narrative`, `source`, `reference`, `order` |
| `ScenarioVariable` | `scenario_key`, `year`, `key`, `value` |
| `SectorCreditProfile` | `sector_name`, `pd_baseline`, `ebitda_margin`, `ebitda_volatility`, `carbon_pass_through`, `source`, `reference` |

`ClimateScenario.family` accepte les valeurs de `ClimateScenario.Family`
(`ORDERLY`, `DISORDERLY`, `TOO_LITTLE`, `HOT_HOUSE`) ; `ScenarioVariable.key`
celles de `ScenarioVariable.Key` (`carbon_price`, `hazard_multiplier`). Une
valeur hors énumération est rejetée en erreur de ligne.

`SectorCreditProfile.sector` est un `OneToOneField` : la clé de doublon est
`sector_name` seul, et l'import utilise `get_or_create` pour ne pas violer la
contrainte.

### Impacts régionalisés, graphe fournisseurs, inventaire

| Feuille | Colonnes |
|---|---|
| `CharacterizationFactor` | `category_key`, `commodity_name`, `country_name`, `subnational_region_name`, `value`, `source`, `reference` |
| `SupplyNode` | `node_ref`, `asset_name`, `subnational_region_name`, `country_name`, `commodity_name`, `is_external` |
| `Exchange` | `supplier_ref`, `consumer_ref`, `commodity_name`, `quantity`, `year`, `tier`, `data_confidence` |
| `AssetInventory` | `asset_name`, `flow_key`, `year`, `value`, `source`, `reference` |

**Résolution du lieu d'un CF** (contrat déjà porté par le modèle) :
`subnational_region_name` renseigné → CF régional ; sinon `country_name` → CF
pays ; sinon les deux vides → CF global. Une ligne qui renseigne les deux est
acceptée mais la région prime, conformément à `build_cf_index()`.

**Identité de `SupplyNode`.** Le modèle n'a pas de clé naturelle : `name` est
`blank=True` et les nœuds créés par la migration 0033 l'ont vide. On introduit
donc `node_ref`, **poignée libre locale au fichier**, non persistée comme
identité. À l'import, le nœud est résolu par sa composition
(`asset`, `region`, `country`, `commodity`) via `get_or_create`, avec
`defaults={'name': node_ref, 'is_external': …}` — un nœud déjà en base est donc
réutilisé et non dupliqué. `Exchange.supplier_ref` / `consumer_ref` référencent
des `node_ref` **déclarés dans la même feuille `SupplyNode` du même fichier** ;
pour rattacher un échange à un nœud existant, on redéclare la ligne `SupplyNode`
(le `get_or_create` la réutilise). Aucune migration n'est nécessaire.

### Catalogues volontairement non importables

`ImpactMethod`, `ImpactCategory` et `Flow` sont des catalogues structurels dont
dépend le code de calcul par leur `key` (`LEGACY_IMPACT_COLUMNS`,
`measured_vs_modeled`, `Flow.theme`). Ils restent en lecture seule : exposés
dans l'onglet `_Référence`, référençables par clé, mais non créables depuis
Excel.

## Feuilles modifiées

| Feuille | Changement |
|---|---|
| `Commodity` | Suppression des 16 colonnes `impact_*` (champs disparus en migration 0028) |
| `Production` | `scope` → `tier` (entier 0–3) |
| `Asset` | Ajout de `type`, `near_sensitive_zone`, `sensitive_zone_type`, `sensitive_zone_name`, `sensitive_zone_area_ha` |
| `SubnationalRegion` | Ajout de `Mean_X`, `Mean_Y` |
| `Company_Policy` | Ajout de `comment` |
| `Asset_consumption` | **Supprimée** — remplacée par `AssetInventory` |

Retirer la création des CF depuis `_import_commodity` est **neutre côté calcul** :
ces CF globaux valaient 0.0, et `impacts.cf_value()` retombe déjà sur `0.0` en
l'absence de facteur.

## Corrections de bugs sur le chemin modifié

La refonte de la résolution des FK (nécessaire pour référencer par `key` et non
par `name`) corrige deux défauts existants :

1. `subsector` n'a aucune entrée dans `_build_db_name_cache()` ni dans
   `MODEL_KEY_TO_SHEET` : **toute ligne `Company_Revenue_Sector` est aujourd'hui
   rejetée** avec « Valeur introuvable pour 'subsector_name' ».
2. `sector` n'est pas dans `_build_db_name_cache()` : un secteur déjà en base ne
   peut pas être référencé, il faut le redéclarer dans le fichier.

**Correction.** `MODEL_KEY_TO_SHEET` devient
`MODEL_KEY_TO_SOURCE = {model_key: (feuille | None, colonne_identifiante)}` :

```python
MODEL_KEY_TO_SOURCE = {
    'country':            ('Country', 'name'),
    'subnational_region': ('SubnationalRegion', 'name'),
    'commodity':          ('Commodity', 'name'),
    'policy_type':        ('Policy_Type', 'name'),
    'policy_subcategory': ('Policy_Subcategory', 'name'),
    'policy_level':       ('Policy_Level', 'name'),
    'currency':           ('Currency', 'code'),
    'sector':             ('Sector', 'name'),
    'subsector':          ('SubSector', 'name'),
    'company':            ('Company', 'name'),
    'asset':              ('Asset', 'name'),
    'impact_category':    (None, 'key'),
    'flow':               (None, 'key'),
    'climate_scenario':   ('ClimateScenario', 'key'),
    'supply_node':        ('SupplyNode', 'node_ref'),
}
```

`_build_db_name_cache()` est étendu symétriquement (`sector`, `subsector`,
`impact_category`, `flow`, `climate_scenario`). `supply_node` a un cache DB
**vide** : les `node_ref` sont locaux au fichier, la résolution est donc
purement intra-fichier.

`_existing_keys()` est complété pour les nouvelles feuilles ainsi que pour
`Company_Revenue_Sector`, `ESG_data` et `Carbon_emission`, qui ne bénéficiaient
d'aucune détection de doublon côté base. `SupplyNode` et `Exchange` renvoient un
ensemble vide (identité locale au fichier) ; leur idempotence est assurée par le
`get_or_create` de l'importeur.

## Ordre d'import

`IMPORT_ORDER` respecte les dépendances :

```
Country → SubnationalRegion → Commodity → CharacterizationFactor
Policy_Type → Policy_Subcategory → Policy_Level
Currency, Sector → SubSector, SectorCreditProfile
Company, Asset → AssetInventory, Production, SupplyNode → Exchange
Ownership, Company_Revenue, Company_Revenue_Sector, Company_Policy,
ESG_data, Carbon_emission
ClimateScenario → ScenarioVariable
```

L'ordre des onglets dans le classeur (`SHEET_COLUMNS`) suit le même
enchaînement, pour que l'utilisateur remplisse le fichier de gauche à droite.

## Onglet `_Référence`

Sections ajoutées : catégories d'impact (clés), flux (clés), scénarios
climatiques (clés) et leurs familles, clés de variable de scénario, types
d'actif, types de zone sensible, codes de dépendance `VL/L/M/H/VH`, niveaux de
`tier` (0–3), valeurs de `data_confidence`.

## Tests

- `test_excel_template.py` se met à jour seul : il est piloté par `SHEET_COLUMNS`.
- `test_excel_parser.py` : résolution des FK par `key` (`flow_key`,
  `category_key`, `scenario_key`), résolution intra-fichier des `node_ref`,
  doublons des nouvelles feuilles, et non-régression des deux bugs corrigés
  (`sector` / `subsector` résolus depuis la base).
- `test_importer.py` : une fonction d'import par nouvelle feuille (cas nominal +
  FK non résolue), réutilisation d'un `SupplyNode` existant, résolution
  région/pays/global d'un CF.
- Le golden du stress test (`dashboard/golden/`) n'est pas touché : aucune
  logique de calcul n'est modifiée.

## Hors périmètre

- Toute migration de modèle.
- Import de `ImpactMethod`, `ImpactCategory`, `Flow`, `E4Assessment`,
  `DisclosureRequirement`.
- Couche de compatibilité pour les anciens fichiers (décision explicite).
