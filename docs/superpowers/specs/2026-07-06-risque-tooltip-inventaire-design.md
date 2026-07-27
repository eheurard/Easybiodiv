# Vue risque — tooltip d'inventaire mesuré (informatif)

> Design validé le 2026-07-06. Piste de suivi de la refonte edges (Plans A/B/C).
> Objet : rendre l'inventaire mesuré (`AssetInventory`, Plan C) visible sur la vue
> **risque physique** sous forme d'un **tooltip informatif** par asset — SANS
> modifier la formule de perte.

---

## 1. Contexte

`_get_physical_risk_data` (`dashboard/views.py`) produit, par asset, un aléa
(`asset.risk_*`), une exposition (`estimated_revenue` de l'année récente) et une
vulnérabilité (moyenne des politiques) ; la perte annuelle = `aléa × exposition ×
vulnérabilité`. La vue front (`physical_risk`) est un **tableau** (+ une carte
maplibre) : une ligne par asset (nom, aléa %, exposition €, vulnérabilité % avec
un tooltip `pr-vuln-tooltip` au survol, risque €).

Le modèle `AssetInventory` (Plan C : `asset × Flow × année × value`) est désormais
first-class mais n'est pas exploité par la vue risque. L'utilisateur veut le
**montrer** (contexte), pas l'injecter dans le calcul.

**Décisions de cadrage (arbitrées) :**
- L'inventaire entre comme **KPI informatif en tooltip** — la formule de perte
  n'est **pas** touchée.
- **Tableau uniquement** ; les popups de la carte maplibre sont hors périmètre.
- Sous-ensemble de flux affichés : **eau (`water`), CO₂ (`co2`), usage des sols
  (`surface_area`)**. Énergie et déchets exclus.
- La **hiérarchie Location** (super-régions RER/OCDE) est **différée** (YAGNI ;
  aucune donnée super-région aujourd'hui ; les 2 FK région/pays suffisent).

## 2. Design

### 2.1 Backend — `_get_physical_risk_data`

Chaque entrée d'asset dans `assets` (la sortie JSON) gagne un champ **`inventory`** :
liste de `{'name': str, 'value': float, 'unit': str}` pour les flux mesurés du
sous-ensemble `('water', 'co2', 'surface_area')`, **non nuls**, de l'**année
d'inventaire la plus récente de l'asset**. `[]` si aucun inventaire.

- Année récente par asset : `max(AssetInventory.year)` pour cet asset (indépendante
  de l'année de production ; cohérent avec le scoping de `leap_evaluate`).
- Libellés : `water` → « Consommation eau » (m³), `co2` → « Émissions CO₂ »
  (tCO₂e), `surface_area` → **« Usage des sols »** (m²). Ces libellés/unités
  proviennent du `Flow` seedé, sauf `surface_area` dont le libellé affiché est
  forcé à « Usage des sols » (le `Flow.name` seedé est « Surface »).
- Chargement en masse (un `SELECT` sur `AssetInventory.filter(asset_id__in=...,
  flow__key__in=(...)).select_related('flow')`), pas de N+1.
- Champ **additif** : `physical_risk` n'est pas dans `GOLDEN_VIEWS` ; les tests
  existants (`PhysicalRiskDataTests`) qui vérifient les champs actuels ne cassent
  pas.

### 2.2 Frontend — `physical_risk.js` (`prRenderTable`)

La cellule **nom de l'asset** reçoit un **tooltip au survol** réutilisant la
mécanique CSS existante (`pr-vuln-tooltip`) : un `<span role="tooltip">` listant
des phrases courtes `«  <value> <unit> · <name> »` (ex. « 100 m³ · Consommation
eau », « 50 tCO₂e · Émissions CO₂ », « 1 200 m² · Usage des sols »). Le nom est
souligné en pointillés (indice de survol). Si `inventory` est vide → aucun
tooltip ni soulignement.

- Le rendu se fait à partir du champ `a.inventory` fourni par le backend (le JS
  formate les lignes, comme il le fait déjà pour `vulnerability_detail`).
- CSS : réutiliser/étendre les classes de tooltip existantes (une classe
  `pr-inv-tooltip` calquée sur `pr-vuln-tooltip` si un style distinct est utile),
  dans le même fichier CSS que `pr-vuln-tooltip`.

### 2.3 Hors périmètre
- La **formule de perte** (`annual_loss`, exposition, vulnérabilité) est inchangée.
- Les **popups de la carte** maplibre.
- La **hiérarchie Location** / super-régions (différée).

## 3. Tests

- `PhysicalRiskDataTests` (Django TestCase, `dashboard/tests.py`) :
  - un asset avec `AssetInventory(flow=water, year=2024, value=100)` →
    `asset['inventory']` contient `{'name': 'Consommation eau', 'value': 100.0,
    'unit': 'm³'}` ;
  - un flux **hors sous-ensemble** (ex. `energy`) ou **nul** n'apparaît pas ;
  - deux années d'inventaire (2023, 2024) → seule l'année récente (2024) est
    reflétée ;
  - un asset **sans** inventaire → `asset['inventory'] == []`.
- Les assertions existantes de `PhysicalRiskDataTests` restent vertes (champ
  additif). Suite projet verte.

## 4. Contraintes
- Django pur, compatible SQLite, aucune dépendance nouvelle, PEP 8 ≤ 100.
- Frontend JS vanilla (pas de framework), chargement `defer` existant.
- Reste dans l'app `dashboard`.
