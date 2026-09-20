# Refonte du modèle de données — table `Flow` unique

> Design validé le 2026-09-18. Objet : **réduire le nombre de tables** en remplaçant
> les six modèles qui décrivent ce qui entre dans un actif, ce qui en sort et ce qui
> circule entre deux lieux (`Production`, `AssetInventory`, l'ancien `Flow`,
> `SupplyNode`, `Exchange`, `Carbon_emission`) par **une seule table `Flow`** ; et
> nettoyer `Ownership` dans la foulée. Bilan : **5 tables de moins**.

---

## 1. Contexte

État actuel (`dashboard/models.py`), hérité de la refonte « edges » du 2026-07-04
(`2026-07-04-refonte-modele-donnees-edges-design.md`) :

- `Production` : ce qu'un actif produit (commodity, année, quantité, revenu estimé,
  tier). Mélange en pratique la production d'un actif et des achats de
  l'entreprise (lignes sans actif, lignes en tier 1 ou 3).
- `Flow` + `AssetInventory` : inventaire mesuré sur un actif (eau, énergie, CO₂,
  déchets, surface), avec un catalogue de flux distinct de `Commodity`.
- `SupplyNode` + `Exchange` : graphe fournisseur → consommateur, avec une table de
  nœuds intermédiaire.
- `Carbon_emission` : émissions déclarées par l'entreprise, par scope.
- `Ownership` : lien actif ↔ entreprise. La part est un **texte** aux formats mêlés
  (`'75%'`, `'0.45'`, `'1'`), les champs s'appellent `Asset` / `Company` (majuscule),
  et rien ne date la détention.

Deux défauts existants sur les scopes, corrigés par cette refonte :

- **Page ESG** : un scope agrégé (« Scope 1+2 ») s'ajoute aux scopes détaillés de la
  même année (`views.py`, `_get_esg_carbon`) → total et barres empilées gonflés.
- **Stress test** : seuls « Scope 1 », « Scope 2 » et « Scope 3 » sont lus
  (`stress_test.company_snapshot`) → une entreprise qui ne déclare que « Scope 1+2 »
  y apparaît avec zéro émission en scopes 1 et 2.

## 2. Décisions structurantes (arbitrées)

1. **Une table `Flow`** remplace les six modèles cités. Une ligne = une quantité
   d'une commodité, une année, d'une origine (`from_*`) vers une destination (`to_*`).
2. **Pas de migration des données.** Les anciennes tables sont supprimées avec leur
   contenu ; tout est re-rempli par l'import Excel. `Ownership` est vidée.
3. **`what`** (et non `commodity`) désigne la commodité : le CO₂, l'eau ou les
   déchets deviennent des lignes de `Commodity`, le mot « commodity » prêtait à
   confusion.
4. **`kind` = nature du flux** : PRODUCTION, SUPPLY, CONSUMPTION, EMISSION, WASTE.
   Le sens IN/OUT pour un actif se déduit du côté où il se trouve.
5. **Extrémités = 8 clés étrangères + 2 booléens « milieu »**, et non une table de
   nœuds ni une `GenericForeignKey`.
6. **L'entreprise peut être une extrémité** (données connues seulement au niveau de
   l'entreprise).
7. **Champ `scope`** : Scope 1, 2, 3, 1+2, 1+2+3, undefined.
8. **`Carbon_emission` est absorbée** : émissions déclarées = flux EMISSION de
   l'entreprise vers le milieu.
9. **Le « milieu » est une extrémité explicite**, des deux côtés ; « vide » veut dire
   « inconnu ».
10. **`Ownership` : nettoyage complet** (part décimale, renommages, années de
    validité, contrôles).
11. **Attribution inchangée : 100 %.** Un actif détenu entre en entier dans les
    chiffres de l'entreprise ; la part ne sert qu'à l'affichage.

## 3. Modèle de données cible

### 3.1 `Flow`

```
Flow
  kind      CharField(max_length=12, choices=Kind)       # voir 3.4
  what      -> Commodity (PROTECT, related_name='flows')
  scope     CharField(max_length=12, choices=Scope, default='undefined')

  # Origine (From) : au plus une des cinq valeurs
  from_asset    -> Asset             (CASCADE, null, related_name='flows_out')
  from_region   -> SubnationalRegion (CASCADE, null, related_name='flows_out')
  from_country  -> Country           (CASCADE, null, related_name='flows_out')
  from_company  -> Company           (CASCADE, null, related_name='flows_out')
  from_environment  BooleanField(default=False)

  # Destination (Where) : au plus une des cinq valeurs
  to_asset      -> Asset             (CASCADE, null, related_name='flows_in')
  to_region     -> SubnationalRegion (CASCADE, null, related_name='flows_in')
  to_country    -> Country           (CASCADE, null, related_name='flows_in')
  to_company    -> Company           (CASCADE, null, related_name='flows_in')
  to_environment    BooleanField(default=False)

  year              IntegerField
  quantity          FloatField                   # exprimée dans what.unit
  tier              PositiveSmallIntegerField(default=0, max 3)
  estimated_revenue FloatField(null)             # PRODUCTION uniquement
  source            CharField(255, blank)
  reference         CharField(255, blank)
  created_at, updated_at
  created_by -> User (SET_NULL, null, related_name='+')
```

Choix de valeurs (`TextChoices`, codes en anglais, libellés en français) :

| `Kind` | Libellé |
|---|---|
| `PRODUCTION` | Production |
| `SUPPLY` | Approvisionnement |
| `CONSUMPTION` | Consommation |
| `EMISSION` | Émission |
| `WASTE` | Déchet |

| `Scope` (valeur stockée) | Libellé |
|---|---|
| `Scope 1`, `Scope 2`, `Scope 3`, `Scope 1+2`, `Scope 1+2+3` | identique |
| `undefined` | Non défini |

Notes :

- `from` est un mot réservé Python, d'où les préfixes `from_` / `to_`. Libellés
  d'interface : « Origine » et « Destination ».
- `what` en `PROTECT` : supprimer une commodité utilisée (ex. le CO₂) est refusé au
  lieu d'effacer toutes les lignes qui l'emploient. Les extrémités restent en
  `CASCADE`, comme les modèles actuels.
- `tier` est conservé tel quel (page Dépendances). `scope` et `tier` sont
  indépendants : le tier situe le flux dans la chaîne, le scope dans le périmètre GES.
- **Pas d'unicité en base** : SQLite traite les NULL comme distincts, une contrainte
  ne protégerait rien. Les doublons sont détectés par l'import (§6).
- Champs supprimés sans remplacement : `Production.company/region/country` (doublons
  de l'actif ou d'`Ownership`), `Exchange.data_confidence` (déductible du type
  d'origine), `SupplyNode.name/is_external` (lus par aucune vue).

### 3.2 Sémantique des extrémités

| Valeur d'un côté | Sens | Lieu retenu pour les facteurs de caractérisation |
|---|---|---|
| actif, région, pays | un lieu précis | ce lieu (actif → sa région, sinon son pays) |
| entreprise | l'entreprise, non localisée | aucun → facteur global |
| **milieu** | milieu naturel à proximité de l'autre extrémité | celui de l'autre extrémité |
| vide | inconnu (acheteur ou origine non renseignés) | aucun → facteur global |

Exemples :

| Flux | From | Where |
|---|---|---|
| CO₂ déclaré par une entreprise | l'entreprise | milieu |
| CO₂ mesuré sur une mine | la mine | milieu |
| Eau prélevée par une mine | milieu | la mine |
| Soja produit par une plantation | la plantation | vide |
| Bœuf du Brésil acheté par Acme | Brésil | Acme Corp |

Le modèle expose des propriétés dérivées : `origin_type` / `destination_type`
(`'asset' | 'region' | 'country' | 'company' | 'environment' | None`).

### 3.3 Contraintes générales (en base)

`CheckConstraint`, portables SQLite et PostgreSQL :

1. Au plus une valeur par côté (4 clés étrangères + booléen milieu).
2. Au moins un côté est un lieu ou une entreprise : « vide → vide » et
   « milieu → vide » sont refusés.
3. Jamais le milieu des deux côtés.
4. `estimated_revenue` n'est renseigné que si `kind = PRODUCTION`.

### 3.4 Règles par `kind` : `FLOW_RULES`

| Kind | From | Where | Lu par |
|---|---|---|---|
| PRODUCTION | actif ou entreprise | vide | impact ACV (quantité × CF), Dépendances, Dette écologique, CA exposé du stress test |
| SUPPLY | actif, région, pays ou entreprise | actif, région, pays ou entreprise, différent de From | carte des fournisseurs (LEAP Locate) |
| CONSUMPTION | milieu ou vide | actif ou entreprise | inventaire mesuré (eau, énergie, surface) |
| EMISSION | actif ou entreprise | milieu | From = actif : inventaire mesuré (CO₂) ; From = entreprise : émissions déclarées (page ESG, stress test) |
| WASTE | actif ou entreprise | milieu, vide, ou actif (site de traitement) | inventaire mesuré |

**Source unique.** Un dictionnaire `FLOW_RULES` dans `dashboard/models.py` associe à
chaque `kind` les types autorisés pour From et pour Where. Il génère :

- une `CheckConstraint` par `kind`, avec un `violation_error_message` lisible
  (ex. « Une émission part d'un actif ou d'une entreprise et va vers le milieu. »).
  Les contraintes s'appliquent aussi à `objects.create()`, `populate_acme` et l'admin ;
- les messages d'erreur de l'import Excel (§6), identiques.

La règle « SUPPLY : Where différent de From » s'écrit
`~Q(from_asset=F('to_asset'))` (et de même pour région, pays, entreprise) ; une
comparaison avec NULL ne fait pas échouer la contrainte.

Changer une règle = modifier `FLOW_RULES` + une migration.

**Principe de comptage : chaque calcul lit un seul `kind` ; aucune page n'additionne
deux `kind`.**

- Sorties : PRODUCTION est le total produit ; les SUPPLY qui partent du même actif en
  sont des parts (80 t produites, dont 30 t vendues à B).
- Entrées : SUPPLY (origine connue) et CONSUMPTION (milieu ou origine inconnue) sont
  disjoints. **Convention de saisie** : en CONSUMPTION, on ne met que la part d'origine
  inconnue, jamais le total.

**Non vérifié (accepté)** : la cohérence entre `kind` et `what` (rien n'interdit une
« EMISSION de blé ») et la cohérence des quantités entre lignes (SUPPLY sortants
supérieurs à la PRODUCTION).

### 3.5 `Commodity`

- Ajout de **`key`** : `CharField(max_length=50, unique=True, null=True, blank=True)`.
  Clé technique des commodités lues par le code (clés JSON des vues). `null` permet
  plusieurs commodités sans clé malgré l'unicité.
- Ajout de **`theme`** : `CharField(max_length=30, blank=True)`, même slug que
  `ImpactCategory.theme` (appariement de `measured_vs_modeled`).
- Pas de champ de type : c'est le flux qui porte sa nature.
- **Cinq commodités techniques** créées par migration (seed), reprises de l'ancien
  catalogue `Flow` :

| name | unit | key | theme |
|---|---|---|---|
| Eau | m³ | `water` | `water` |
| Énergie | MWh | `energy` | `energy` |
| CO₂ | tCO₂e | `co2` | `carbon` |
| Déchets | t | `waste` | `waste` |
| Surface occupée | m² | `surface_area` | `land` |

La surface devient une CONSUMPTION (occupation du sol, notion standard en ACV). Les
champs `dependency_*` et `biodiversity_loss_class` gardent leurs valeurs par défaut
sur ces lignes : seuls les flux PRODUCTION alimentent les calculs qui les lisent.

### 3.6 `Ownership`

```
Ownership
  asset      -> Asset   (CASCADE, related_name='ownerships')
  company    -> Company (CASCADE, related_name='ownerships')
  share      DecimalField(max_digits=5, decimal_places=4)   # 0,75 = 75 %
  start_year PositiveSmallIntegerField(null, blank)   # vide = depuis toujours
  end_year   PositiveSmallIntegerField(null, blank)   # vide = toujours détenu
  description TextField(blank)
  created_at, updated_at
  created_by -> User (SET_NULL, null, related_name='+')
```

- Renommages : `Asset` → `asset`, `Company` → `company`, `ownership` → `share`.
- **Années, pas dates** : les flux sont annuels. Convention (dans `help_text`) : le
  détenteur d'une année est celui du 31 décembre. Cession en juin 2024 → vendeur
  `end_year = 2023`, acheteur `start_year = 2024`.
- Contraintes en base : `0 < share ≤ 1` ; `start_year ≤ end_year` si les deux sont
  renseignés.
- Contrôles dans `clean()` et à l'import (non exprimables de façon portable en
  base) : pas de périodes qui se chevauchent pour un même couple actif / entreprise ;
  somme des parts d'un actif ≤ 1 pour chaque année. Pas d'unicité (actif, entreprise) :
  un couple peut avoir plusieurs périodes.
- **Point d'entrée unique** : `AssetQuerySet.owned_by(company, year=None)`, exposé
  par `Asset.objects`.
  - avec `year` : détentions valides cette année-là
    (`start_year` vide ou ≤ `year`, `end_year` vide ou ≥ `year`) ;
  - sans `year` : périmètre actuel (détentions sans `end_year`).
  - Remplace les ~17 `Asset.objects.filter(ownership__Company=company)` des vues, de
    la conformité et du stress test. Le stress test passe son année ; les autres pages
    utilisent le périmètre actuel (équivalent au comportement d'aujourd'hui).
- **Affichage** : LEAP Locate formate la part en `"75%"` (`f"{share * 100:g}%"`),
  exactement comme aujourd'hui → `locate_view.js` et le golden inchangés.

## 4. Couche service : `dashboard/services/flows.py`

Seul module qui filtre `Flow`. Aucune vue n'écrit de requête `Flow` directe.

| Fonction | Renvoie | Remplace |
|---|---|---|
| `productions(asset_ids)` | flux PRODUCTION de ces actifs, **toutes années**, triés par `pk`, `select_related` sur `what` et l'actif | `production_set`, `Production.objects.filter(asset_id__in=…)` |
| `latest_productions(asset_ids)` | idem, en ne gardant que l'année la plus récente **de chaque actif** | le motif « max year par actif » recopié ~10 fois dans `views.py` |
| `company_productions(company)` | PRODUCTION `from_company = company` + PRODUCTION des actifs `owned_by(company)` | `Q(company=…) \| Q(asset__ownership__Company=…)` |
| `latest_inventory(asset_ids, keys)` | par actif et par clé : valeur sommée et unité, pour l'année d'inventaire la plus récente de l'actif | `AssetInventory` + max year |
| `supplies_to(asset_ids, company=None)` | SUPPLY vers ces actifs (et vers l'entreprise si fournie), dernière année par destination | `Exchange` / `SupplyNode` |
| `declared_emissions(company)` | `{année: {libellé de scope: tCO₂e}}` après résolution des scopes | `Carbon_emission` |

Précisions :

- **Tri par `pk`** : `productions` et `latest_productions` gardent l'ordre de
  création (déterminisme SQLite/PostgreSQL, requis par le sankey de Mesure
  d'empreinte, `views.py:449`).
- **Lignes d'inventaire** = CONSUMPTION vers l'actif + EMISSION et WASTE depuis
  l'actif, `what.key` renseignée. L'« année la plus récente » est calculée sur ces
  seules lignes : une PRODUCTION plus récente ne décale pas l'inventaire.
- **Résolution des scopes** (`declared_emissions`), année par année, sur les seuls
  flux EMISSION `from_company = company`, `what.key = 'co2'` (jamais le CO₂ mesuré
  sur un actif) :
  1. Scopes 1 et 2 détaillés s'ils existent, sinon Scope 1+2 ;
  2. plus le Scope 3 s'il existe ;
  3. Scope 1+2+3 ou `undefined` seulement si l'année n'a aucune autre valeur
     (totaux non ventilables).

Services existants :

- `impacts.measured_vs_modeled(asset, theme, year)` : porté sur `Flow` (inventaire via
  `what.theme`, modélisé via PRODUCTION × CF), même contrat de sortie.
- `supply.upstream_chain` : **supprimé** avec son test. Aucune page ne l'appelle ; le
  réécrire pour des extrémités de cinq types coûte plus que le recréer quand une page
  en aura besoin. `TIER_LABELS`, `SCOPE_TO_TIER`, `TIER_TO_SCOPE` restent.

## 5. Pages

| Vue ou fonction | Aujourd'hui | Demain |
|---|---|---|
| `_get_dependencies_data` | `Production` (entreprise ou actifs détenus) | `company_productions` |
| `_get_company_data` | `production_set` (toutes années + dernière année) | `productions`, `latest_productions` |
| `_get_mesure_empreinte_data`, `_get_leap_prepare_data`, `_get_dette_ecologique_data`, `_get_comparison_data` | `Production` / `production_set` + max year | `latest_productions` |
| `_company_endpoint_impacts`, `_company_physical_risks`, `_company_ecological_debt` (portefeuilles) | `Production` + max year | `latest_productions` |
| `_get_leap_evaluate_data` | `AssetInventory` (eau, CO₂, déchets) + `Production` | `latest_inventory` + `latest_productions` |
| `_get_physical_risk_data` | `AssetInventory` (eau, CO₂, surface) + `Production` | `latest_inventory` + `latest_productions` |
| `_get_leap_locate_data` | `production_set` + `Ownership` + `Exchange` | `latest_productions` + `Ownership.share` + `supplies_to` |
| `_get_compliance_data` | `ownership__Company` | `owned_by` |
| `_get_esg_carbon` | `Carbon_emission` | `declared_emissions` |
| `stress_test.company_snapshot` | `Carbon_emission` + `Production` | `declared_emissions` + `latest_productions`, `owned_by(company, year)` |

Toutes les vues listées remplacent `Asset.objects.filter(ownership__Company=company)`
par `Asset.objects.owned_by(company)`. Renommages mécaniques dans les vues :
`p.production` → `f.quantity`, `p.commodity` → `f.what`, `p.asset` → `f.from_asset`.

**Stress test** : les émissions retenues utilisent Scope 1 + Scope 2, ou Scope 1+2
quand le détail manque. Une année qui n'a qu'un total non ventilable (1+2+3 ou
`undefined`) produit l'avertissement « émissions non ventilées par scope » et un canal
transition nul — comme aujourd'hui en l'absence de données (`stress_test.py:509`).

**Page ESG** : plus de double comptage (total et barres empilées). `esg.js` accepte
déjà n'importe quel libellé de scope.

**LEAP Locate (carte)** : fournisseur placé aux coordonnées de l'actif, ou au point
moyen de la région ; un pays ou une entreprise d'origine n'a pas de coordonnées →
ignoré (comme aujourd'hui pour un pays). Un SUPPLY dont la destination est
l'entreprise affiche le point fournisseur **sans trait**. L'identifiant du
fournisseur dans le JSON devient `"asset-63"` / `"region-4"` (plus de `SupplyNode`) ;
le JavaScript ne le lit pas.

**Sorties JSON** : les 9 fichiers de référence (`dashboard/golden/`) doivent rester
**strictement identiques** — le jeu `populate_acme` ne contient ni fournisseur ni
scope agrégé. Les corrections de scopes et les identifiants de fournisseurs sont
couverts par des tests dédiés (§8).

## 6. Import Excel et admin

### 6.1 Feuille `Flow`

Remplace les feuilles `Production`, `AssetInventory`, `SupplyNode`, `Exchange` et
`Carbon_emission`. Colonnes :

`kind, what, scope, from_type, from_name, to_type, to_name, year, quantity, tier,
estimated_revenue, source, reference`

| kind | what | scope | from_type | from_name | to_type | to_name | year | quantity |
|---|---|---|---|---|---|---|---|---|
| PRODUCTION | Soja | | asset | Plantation Pará | | | 2024 | 800 |
| SUPPLY | Bœuf | | country | Brésil | company | Acme Corp | 2026 | 1000 |
| CONSUMPTION | water | | milieu | | asset | Centinela mine | 2025 | 30520 |
| EMISSION | co2 | Scope 1 | company | Acme Corp | milieu | | 2024 | 12000 |

Validation ligne par ligne :

- Obligatoires : `kind`, `what`, `year`, `quantity`.
- Listes fermées (`CHOICE_FIELDS`) : `kind`, `scope`, `from_type` et `to_type`
  (`asset`, `region`, `country`, `company`, `milieu`).
- `what` : résolu par **nom ou `key`** de la commodité, sans casse (`co2` au lieu de
  « CO₂ »).
- `from_name` / `to_name` : résolus selon le type (lookup `asset`, `subnational_region`,
  `country` ou `company`, fichier + base). Obligatoires pour un type lieu ou
  entreprise, **vides** pour `milieu`. Extension de l'analyseur : résolution de clé
  étrangère dépendante d'une colonne de type.
- Règles `FLOW_RULES` : même message que la contrainte en base, préfixé du numéro de
  ligne.
- Doublon : mêmes `kind`, `what`, `scope`, origine, destination et année qu'une ligne
  du fichier ou de la base.

**Anciens classeurs** : aujourd'hui l'analyseur ignore sans erreur les feuilles
inconnues (`excel_parser.py:25`). Les cinq noms de feuilles supprimés déclenchent
désormais une erreur explicite : « La feuille Production n'existe plus : utilisez la
feuille Flow. »

`IMPORT_ORDER` : `Flow` prend la place de `Production` (après `Company`, `Asset`).

### 6.2 Autres feuilles

- `Commodity` : colonnes facultatives `key` et `theme`.
- `Ownership` : `asset_name, company_name, share, start_year, end_year, description`.
  - `share` accepte `0.75` ou `75%` ; stocké 0,75. Une valeur > 1 sans « % » est
    refusée ; `1` = 100 %. Une cellule Excel au format pourcentage vaut déjà 0,75.
  - Doublon : (`asset_name`, `company_name`, `start_year`).
  - Seconde passe sur la feuille entière (fichier + base) : chevauchement de périodes
    et somme des parts ≤ 1 par actif et par année.
- Feuille `_Référence` du modèle : commodités listées avec unité et clé
  (« CO₂ — tCO₂e — co2 ») ; nouvelles listes fermées (`kind`, `scope`, types
  d'extrémité) ; suppression des sections « Flows (flow_key) » et
  « Exchange — data_confidence ». `MODEL_KEY_TO_SOURCE` perd `flow` et `supply_node`.

### 6.3 Admin

- Suppression des `ModelAdmin` de `Production`, `Carbon_emission`, `SupplyNode`,
  `Exchange`, ancien `Flow`, `AssetInventory`.
- `FlowAdmin` : `list_display` (kind, what, scope, origine, destination, année,
  quantité) ; `list_filter` (kind, scope, year, tier) ; `fieldsets` « Origine » et
  « Destination » ; `autocomplete_fields` sur `what` et les 8 extrémités. Les
  contraintes étant validées par le formulaire (`full_clean` → `validate_constraints`,
  Django ≥ 4.1), une violation affiche son `violation_error_message` au lieu d'une
  erreur 500.
- `OwnershipAdmin` : part en pourcentage, `start_year`, `end_year`.
- `CommodityAdmin` : ajout de `key` et `theme`.
- Console d'administration (`admin_site.py`) : le groupe « Chaîne
  d'approvisionnement » devient « Flux » (`Flow` seul) ; `Carbon_emission`, l'ancien
  `Flow` et `AssetInventory` sortent de leurs groupes.

## 7. Migrations

Une migration = un changement logique, nommée explicitement :

| # | Nom | Contenu |
|---|---|---|
| 0049 | `delete_legacy_flow_models` | `DeleteModel` : `Exchange`, `SupplyNode`, `AssetInventory`, `Flow` (ancien), `Production`, `Carbon_emission` |
| 0050 | `commodity_key_theme` | `Commodity.key`, `Commodity.theme` |
| 0051 | `seed_technical_commodities` | `RunPython` : 5 commodités du §3.5 (inverse : suppression) |
| 0052 | `flow` | `CreateModel` `Flow` + contraintes générées depuis `FLOW_RULES` |
| 0053 | `clear_ownership` | `RunPython` : suppression des lignes d'`Ownership` (inverse : rien) |
| 0054 | `ownership_cleanup` | renommages, `share`, `start_year`, `end_year`, horodatage, contraintes |

- Génération **en deux temps** : retirer les anciens modèles de `models.py` →
  `makemigrations` (0049) ; puis ajouter le nouveau `Flow` (0052). Sinon Django
  interprète l'ancien `Flow` comme modifié au lieu de supprimé puis recréé.
- Les migrations historiques passent par `apps.get_model` : elles ne sont pas
  touchées et ne sont pas supprimées.
- Ce tableau décrit l'**état final**. Le plan d'implémentation fixe l'ordre des
  tâches et peut ajouter des étapes intermédiaires (par exemple renommer
  temporairement l'ancien `Flow` pour faire cohabiter les deux modèles) afin que la
  suite de tests reste verte à la fin de chaque tâche.

## 8. Tests

Framework et conventions : CLAUDE.md §6. Nouveaux tests écrits avant le code (TDD).

**Filet de sécurité** : `GoldenViewOutputTests` (9 vues). `populate_acme` est réécrit
à données égales — 12 productions → PRODUCTION (même ordre de création), 21
émissions → EMISSION de l'entreprise vers le milieu, parts `"75%"` → décimaux. Les
fichiers golden doivent rester strictement identiques.

Nouveaux tests :

- **`FLOW_RULES`** : pour chaque `kind`, une ligne valide et une ligne par type
  d'extrémité interdit (`IntegrityError`) ; contraintes générales (milieu des deux
  côtés, côtés vides, plusieurs valeurs d'un côté) ; `estimated_revenue` hors
  PRODUCTION ; SUPPLY d'un actif vers lui-même.
- **Admin** : une violation de règle affiche le message dans le formulaire.
- **`services/flows.py`** : `productions` trié par `pk` ; `latest_productions` par
  actif ; `company_productions` (entreprise + actifs détenus) ; `latest_inventory` non
  décalé par une PRODUCTION plus récente ; `supplies_to` avec destination entreprise ;
  `declared_emissions` (détail prioritaire sur l'agrégat, total seul, CO₂ d'actif
  exclu).
- **Stress test** : année avec seulement Scope 1+2 → émissions non nulles ; année avec
  seulement un total → avertissement.
- **Page ESG** : scopes détaillés + agrégat la même année → pas de double comptage.
- **LEAP Locate** : point fournisseur sans trait ; identifiant `"asset-…"` /
  `"region-…"`.
- **`Ownership`** : contraintes de part et d'années ; chevauchement et somme des parts
  (`clean()`) ; `owned_by(company, year)` avec périodes ouvertes et fermées ;
  formatage `"75%"`.
- **Import** : feuille `Flow` pour chaque `kind` ; `what` par `key` ; nom renseigné
  avec `milieu` refusé ; violation de règle ; erreur sur feuille supprimée ; lecture
  de `share` (`0.75`, `75%`, `1`, `1.5` refusé) ; contrôles de la seconde passe
  `Ownership` ; feuille `_Référence`.

Tests supprimés : modèles disparus (`SupplyNode`, `Exchange`, `AssetInventory`,
`Production`, `Carbon_emission`), `upstream_chain`, utilitaires des anciennes
migrations de données (`tests.py:2447`), feuilles d'import supprimées. Fichiers de
`imports/tests/fixtures/` régénérés.

Fin : suite complète verte, couverture ≥ 70 % (`pytest --cov`).

## 9. Déploiement

La production cPanel tourne sur **SQLite**. `.cpanel.yml` lance `migrate --noinput`
**automatiquement** à chaque « Update from Remote » : récupérer le code supprime
immédiatement les six tables.

**Modification de `.cpanel.yml`** (configuration de production, signalée) : une étape
de sauvegarde avant `migrate`, via l'API `backup` du module `sqlite3` de Python (une
copie de fichier brute peut manquer des écritures encore dans le journal WAL, activé
dans `easybiodiv/db.py`). Elle écrase à chaque déploiement un fichier unique
`db.sqlite3.pre-deploy` : protège tous les déploiements futurs sans remplir le disque.

Procédure :

1. Fusionner `feat/table-flow`, puis « Update from Remote » dans cPanel →
   sauvegarde, `migrate`, `collectstatic`, redémarrage.
2. Télécharger le nouveau modèle Excel depuis l'application, le remplir, l'importer
   (`Commodity` si besoin, `Ownership`, `Flow`).
3. Entre 1 et 2, les pages affichent des entreprises sans production ni émission :
   déployer à un moment calme.
4. Retour arrière : revenir au commit précédent et restaurer `db.sqlite3.pre-deploy`.

## 10. Documentation (même branche)

- `CLAUDE.md` §4 : liste des modèles (`Flow` remplace `Production`,
  `Flow`+`AssetInventory`, `SupplyNode`+`Exchange`, `Carbon_emission`), `Ownership`,
  conventions d'horodatage.
- `CLAUDE.md` §2 : la production tourne sur SQLite.
- `docs/deploiement-production.md` : sauvegarde avant migration, réimport après la
  refonte.

## 11. Hors périmètre

- **Attribution au prorata** de la part de détention (changerait les chiffres de
  toutes les pages).
- **Traversée multi-tiers** du graphe d'approvisionnement (`upstream_chain`), à
  recréer quand une page en aura besoin.
- **Type sur `Commodity`** pour contrôler la cohérence `kind` / `what`.
- **Cohérence des quantités** entre lignes (SUPPLY sortants vs PRODUCTION).
- **Migration des données existantes** (re-remplissage par import).
- **Unicité des flux en base** (assurée par l'import).
- **Détention à la date près** (années seulement).
