# Stress test climatique — probabilité de défaut d'un émetteur

> Design validé le 2026-07-31.
> Objet : ajouter une page **Stress test climatique** permettant de sélectionner un
> **scénario de référence NGFS**, d'ajuster quelques **hypothèses**, et d'obtenir la
> **probabilité de défaut (PD) stressée** de l'entreprise sélectionnée, décomposée
> par canal de risque (transition / physique).

---

## 1. Contexte

### 1.1 État actuel

L'app `dashboard` expose 11 pages suivant toutes le même patron : une vue page
(`login_required`, rend un template qui étend `base.html` avec le combobox
entreprise), un endpoint JSON `/api/company/<pk>/<page>/`, un module JS vanilla
dédié dans `dashboard/static/dashboard/js/`, et — pour les plus riches — un
fichier golden dans `dashboard/golden/`.

Aucune notion de risque de crédit n'existe aujourd'hui. Les données financières
disponibles se limitent à :

| Modèle | Donnée exploitable |
|---|---|
| `Company_Revenue` | CA consolidé par année et devise |
| `Company_Revenue_Sector` | CA par sous-secteur (→ `Sector`, code NACE) |
| `Carbon_emission` | tCO₂e par année et par scope |
| `Production.estimated_revenue` | CA estimé par actif |
| `Asset.risk_*` | 15 scores d'aléa physique ∈ [0,1] |
| `Policy_Level.vulnerability_*` | 15 coefficients de vulnérabilité |

**Il n'existe aucune donnée de bilan** : ni dette, ni EBITDA, ni notation, ni
capitalisation fiable (`services/market.py` interroge Yahoo Finance mais bascule
en mode démo dès que le ticker est absent).

### 1.2 Méthodes de référence

La littérature superviseur et industrie converge sur une chaîne unique :

```
Scénario (NGFS) → variables de risque → impact P&L de l'émetteur
                → ratios financiers → probabilité de défaut
```

Trois familles se distinguent sur la dernière étape :

1. **Structurelle (Merton)** — choc de valeur d'actif → distance au défaut → PD.
   *Battiston et al. (2017), Bouchet & Le Guenedal (2020), CRISK (Jung/Engle/
   Berner), Amundi Climate VaR.* Requiert capitalisation, dette et volatilité
   d'actif.
2. **Satellite fondamentale** — ratios stressés (levier, marge, couverture
   d'intérêts) → PD via scorecard ou logit calibré sur historique de défauts.
   *BCE Occasional Paper 281 (2021), ACPR exercice pilote 2020, UNEP FI / Oliver
   Wyman.* Requiert des états financiers complets.
3. **Transformation en espace latent (Merton-Vasicek)** — une PD de départ
   décalée par un choc systématique. Standard des stress tests bancaires
   (passage through-the-cycle → point-in-time, IFRS 9).

Deux briques de calcul d'impact font consensus, indépendamment de la famille :

- **Transition** — *coût carbone non provisionné* :
  `émissions × (prix carbone du scénario − prix déjà payé) × (1 − répercussion)`.
  Cœur du *Carbon Earnings at Risk* (Trucost/S&P) et du *Climate VaR* (MSCI).
- **Physique** — `exposition × aléa × vulnérabilité`, structure déjà implémentée
  dans `_get_physical_risk_data`.

### 1.3 Décisions de cadrage (arbitrées)

- **Famille 3 retenue.** Les familles 1 et 2 exigent des données de bilan
  absentes du modèle. La famille 3 est alimentable par les données existantes et
  reste la plus lisible pour un utilisateur non spécialiste du crédit.
- **PD₀ = table sectorielle pondérée**, surchargeable par l'utilisateur.
- **Deux canaux** : transition *et* physique. Un canal biodiversité adossé à la
  dette écologique a été écarté (aucun référentiel de scénarios établi).
- **Scénarios en base**, seedés par migration de données, éditables en admin.
- **Variables exposées à l'écran** : horizon, prix carbone, périmètre de scopes,
  taux de répercussion, marge EBITDA, PD₀. Les paramètres du modèle de crédit
  (volatilité d'EBITDA, transmission du scope 3, multiplicateur d'aléa) restent
  des constantes documentées, non éditables à l'écran.
- **Aucune persistance des exécutions.** Calcul à la volée, endpoint GET
  paramétré, cohérent avec les 11 pages existantes. Pas de modèle `StressTestRun`.

---

## 2. Modèle de calcul

### 2.1 Année de référence

`année_réf` = dernière année pour laquelle l'entreprise dispose d'un
`Company_Revenue`. Les émissions et l'exposition sont lues sur cette même année ;
à défaut, sur l'année disponible la plus proche, et un avertissement est ajouté
au payload.

### 2.2 Canal transition — coût carbone non provisionné

```
ΔP    = P(scénario, horizon) − P(scénario, année_réf)          €/tCO₂e
E     = Σ scopes 1+2  [ + Σ scope 3 × τ₃  si scope 3 activé ]  tCO₂e
Coût  = ΔP × E × (1 − pass_through)                            €
```

- `ΔP` est un **différentiel**, pas un prix absolu : l'émetteur supporte déjà le
  prix carbone courant. La trajectoire de chaque scénario porte donc une valeur
  pour l'année de référence.
- **Lecture d'une trajectoire à une année quelconque** : interpolation linéaire
  entre les deux points encadrants, valeur constante au-delà du premier et du
  dernier point (`2025` et `2050`). Règle unique, appliquée aussi bien à
  `carbon_price` qu'à `hazard_multiplier`, et testée aux trois cas (avant, entre,
  après).
- `τ₃` = part du scope 3 amont répercutée sur l'émetteur via le prix de ses
  intrants. **Constante documentée, défaut 0,50.** Retenir 100 % du scope 3
  reviendrait à faire payer à l'émetteur les émissions de sa chaîne de valeur
  entière, ce qui double-compte à l'échelle d'un portefeuille.
- `pass_through` = part du surcoût répercutée sur les clients. Curseur
  utilisateur, valeur par défaut issue du profil sectoriel.
- `ΔP` est borné à zéro par le bas : un prix carbone décroissant ne génère pas de
  gain.

### 2.3 Canal physique — agrégation multiplicative bornée

```
ratio_perte = 1 − Π_aléas ( 1 − min(1, risk_h × vuln_h × λ(scénario, horizon)) )
Perte       = ratio_perte × exposition_totale
```

où `exposition_totale` = somme des `estimated_revenue` des actifs détenus par
l'entreprise sur leur dernière année de production, `risk_h` le score d'aléa de
l'actif, `vuln_h` la vulnérabilité moyenne des politiques de l'entreprise, et `λ`
le multiplicateur d'aléa du scénario à l'horizon retenu.

**Divergence assumée avec la page Risque physique.** Celle-ci *somme* les
contributions des 15 aléas (`Σ hazard × expo × vuln`), ce qui peut produire une
perte supérieure à 100 % du chiffre d'affaires. Inoffensif pour un classement
d'aléas, inacceptable pour alimenter une PD. L'agrégation multiplicative est
naturellement bornée dans [0,1] et correspond à la combinaison standard de
probabilités de dommage indépendants.

**Conséquence acceptée** : les deux pages afficheront des pertes physiques
différentes. Elle sera signalée dans l'infobulle du canal physique.
L'alignement de la page Risque physique est **hors périmètre** de cette spec et
fera l'objet d'un chantier séparé (golden à ré-enregistrer, tests à reprendre).

### 2.4 Conversion en PD — décalage latent de type Merton

```
EBITDA_proxy = CA(année_réf) × marge_EBITDA
Choc         = (Coût_carbone + Perte_physique) / EBITDA_proxy    sans dimension
S            = Choc / σ                                          écarts-types
PD*          = Φ( Φ⁻¹(PD₀) + S )
```

**Justification.** `−Φ⁻¹(PD₀)` est la distance au défaut implicite de l'émetteur,
exprimée en écarts-types de sa capacité bénéficiaire ; le choc la réduit de `S`.
C'est la logique de Merton appliquée à une PD au lieu d'une valeur d'actif.

Propriétés vérifiées par les tests :

| Propriété | Vérification |
|---|---|
| Neutralité exacte | `S = 0 ⟹ PD* = PD₀` |
| Monotonie | `S₁ < S₂ ⟹ PD*(S₁) < PD*(S₂)` |
| Bornes | `0 < PD* < 1` pour tout `S` fini |
| Additivité du choc | `S_total = S_transition + S_physique` |

**La corrélation d'actif ρ n'apparaît volontairement pas.** Elle gouverne la
distribution de pertes d'un *portefeuille* de contreparties, pas la PD
conditionnelle d'un émetteur isolé. L'introduire ici serait de la fausse rigueur.
C'est aussi ce qui évite l'inconsistance connue de la transformation de Vasicek
brute, qui ne restitue pas `PD₀` en l'absence de choc.

`Φ` et `Φ⁻¹` proviennent de `statistics.NormalDist` (`.cdf()` / `.inv_cdf()`) —
**bibliothèque standard Python, aucune dépendance ajoutée**, comportement
identique sous SQLite et PostgreSQL.

**Garde-fous** : `PD₀` est bornée dans `[1e-6, 0.99]` avant inversion ; `S` est
plafonné à `MAX_SHOCK_SIGMA = 8.0` (au-delà, `PD*` est numériquement égale à 1)
pour qu'un `EBITDA_proxy` proche de zéro ne produise pas d'infini ; un
`EBITDA_proxy` nul ou négatif court-circuite le calcul et retourne un
avertissement. Une entreprise sans `Company_Revenue` retourne un payload vide
assorti d'un avertissement, sans erreur 500.

### 2.5 PD₀ et profils sectoriels

```
PD₀ = Σ_secteurs ( part_de_CA(secteur) × pd_baseline(secteur) )
```

pondérée par `Company_Revenue_Sector` de l'année de référence, remontée de
`SubSector` vers `Sector`. Même pondération pour `marge_EBITDA`, `σ` et
`pass_through`. En l'absence de mix sectoriel, un profil de repli documenté
s'applique et un avertissement est émis.

### 2.6 Équivalent notation

Table de correspondance PD → notation indicative (AAA … CCC), **constante Python**
dans le service : c'est une convention d'affichage, pas une donnée métier à
éditer. Affichée comme « équivalent indicatif », jamais comme une notation
attribuée.

---

## 3. Architecture

### 3.1 Modèles (3 nouveaux)

```python
class ClimateScenario(models.Model):
    class Family(models.TextChoices):
        ORDERLY    = 'ORDERLY',    'Transition ordonnée'
        DISORDERLY = 'DISORDERLY', 'Transition désordonnée'
        TOO_LITTLE = 'TOO_LITTLE', 'Trop peu, trop tard'
        HOT_HOUSE  = 'HOT_HOUSE',  'Monde en surchauffe'

    key, name, family, narrative, warming_c,
    source, reference, order, created_at, updated_at


class ScenarioVariable(models.Model):
    class Key(models.TextChoices):
        CARBON_PRICE      = 'carbon_price',      'Prix du carbone (€/tCO₂e)'
        HAZARD_MULTIPLIER = 'hazard_multiplier', "Multiplicateur d'aléa"

    scenario, year, key, value
    unique_together = ('scenario', 'year', 'key')


class SectorCreditProfile(models.Model):
    sector = OneToOneField(Sector)
    pd_baseline, ebitda_margin, ebitda_volatility, carbon_pass_through,
    source, reference, created_at, updated_at
```

Tous portent `source` et `reference` : exigence de traçabilité CSRD, et
cohérence avec `CharacterizationFactor` et `AssetInventory`.

### 3.2 Migrations (2, une par changement logique)

- `0042_climate_scenario_models` — schéma des 3 modèles.
- `0043_seed_climate_scenarios` — migration de données, sur le patron de
  `0026_seed_impact_catalog` et `0037_seed_flows`.

Scénarios seedés (NGFS Phase V, novembre 2024) :

| clé | nom | famille |
|---|---|---|
| `NET_ZERO_2050` | Net Zero 2050 | Ordonnée |
| `BELOW_2C` | Below 2 °C | Ordonnée |
| `DELAYED_TRANSITION` | Delayed Transition | Désordonnée |
| `FRAGMENTED_WORLD` | Fragmented World | Trop peu, trop tard |
| `CURRENT_POLICIES` | Current Policies | Surchauffe |

Chacun porte `carbon_price` et `hazard_multiplier` pour **2025, 2030, 2040,
2050**. Les valeurs numériques ne sont **pas fixées par cette spec** : elles
seront relevées au moment de l'implémentation. Critère d'acceptation :
`source` renseigné pour chaque scénario (« NGFS Phase V, novembre 2024 ») et
`reference` pointant l'URL ou le tableau précis dont la valeur est tirée ; toute
valeur non sourçable est marquée comme estimation dans `reference` plutôt que
présentée comme officielle. Les trajectoires doivent être **croissantes en prix
carbone** pour les scénarios de transition et **croissantes en multiplicateur
d'aléa** pour les scénarios de surchauffe — vérifié par un test du seed.

Un jeu de profils sectoriels de démonstration est ajouté à `populate_acme` pour
que la page soit fonctionnelle sur ACME.

### 3.3 Répartition du code

`dashboard/views.py` fait déjà 1762 lignes. Le moteur n'y va pas.

**`dashboard/services/stress_test.py`** (nouveau) — deux couches nettement
séparées :

*Noyau pur, sans accès base ni ORM, testable isolément :*

```python
def carbon_cost(emissions_t, delta_price, pass_through) -> float
def physical_loss_ratio(hazard_pairs, multiplier)      -> float
def shock_to_pd(pd_baseline, shock, sigma)             -> float
def pd_to_rating(pd)                                   -> str
```

*Orchestration, seule couche qui touche l'ORM :*

```python
def get_stress_test_data(company, params) -> dict
```

**`dashboard/forms.py`** (nouveau) — `StressTestForm(forms.Form)` valide et borne
les paramètres. CLAUDE.md proscrit le POST brut ; la même exigence s'applique aux
query params. Champs : `scenario` (`ModelChoiceField` sur la clé), `horizon`
(`ChoiceField`), `carbon_price`, `pass_through` ∈ [0,1], `ebitda_margin` ∈ ]0,1],
`pd_baseline` ∈ ]0,1[, `include_scope3` (`BooleanField`). Tous optionnels : à
défaut, valeurs du scénario et du profil sectoriel.

**`dashboard/views.py`** — deux fonctions fines uniquement, `climate_stress_test`
et `climate_stress_test_data`, sur le patron exact des 10 pages existantes.

### 3.4 Endpoint

```
GET /api/company/<pk>/climate-stress-test/
    ?scenario=NET_ZERO_2050&horizon=2030&carbon_price=250
    &include_scope3=1&pass_through=0.30&ebitda_margin=0.15&pd_baseline=0.012
```

`400` sur paramètre invalide (erreurs du formulaire en JSON), `404` sur
entreprise inconnue, `login_required` comme toutes les pages du dashboard.

Réponse :

```json
{
  "company_id": 1,
  "company_name": "ACME",
  "reference_year": 2024,
  "scenarios": [{"key": "...", "name": "...", "family": "...",
                 "family_label": "...", "warming_c": 1.5, "narrative": "..."}],
  "selected": {"scenario": "...", "horizon": 2030, "carbon_price": 250.0,
               "carbon_price_reference": 80.0, "include_scope3": true,
               "pass_through": 0.30, "ebitda_margin": 0.15,
               "pd_baseline": 0.012, "ebitda_volatility": 0.25,
               "scope3_transmission": 0.50, "hazard_multiplier": 1.3},
  "inputs": {"emissions": {"scope1": 0, "scope2": 0, "scope3": 0,
                           "retained": 0},
             "revenue": 0, "ebitda_proxy": 0, "exposure": 0},
  "result": {"pd_baseline": 0.0120, "pd_stressed": 0.0287,
             "delta_bps": 167, "multiple": 2.39,
             "rating_baseline": "BBB", "rating_stressed": "BB",
             "shock_ratio": 0.0893, "shock_sigma": 0.357},
  "waterfall": [{"label": "PD initiale", "pd": 0.0120, "delta_bps": 0},
                {"label": "Transition", "pd": 0.0231, "delta_bps": 111},
                {"label": "Physique",   "pd": 0.0287, "delta_bps": 56}],
  "channels": {"transition": {"cost_eur": 0, "pct_ebitda": 0.0658,
                              "shock_sigma": 0.263},
               "physical":   {"loss_eur": 0, "pct_ebitda": 0.0235,
                              "loss_ratio": 0, "shock_sigma": 0.094}},
  "horizon_curve": [{"year": 2030, "pd": 0.0287}, {"year": 2040, "pd": 0.0}],
  "scenario_comparison": [{"key": "...", "name": "...", "pd": 0.0,
                           "delta_bps": 0}],
  "assumptions": [{"label": "...", "value": "...", "source": "...",
                   "reference": "..."}],
  "warnings": ["Aucune donnée d'émissions pour 2024 — canal transition nul"]
}
```

**Attribution du waterfall : séquentielle, transition puis physique.** Le
décalage latent étant additif en `S`, la décomposition du choc est exacte ; seule
la répartition en points de base dépend de l'ordre, par non-linéarité de `Φ`.
Documenté dans l'infobulle du graphique.

### 3.5 Interface — `/climate-stress-test/`

```
┌ Entreprise (combobox, pattern existant) ──────────────────────┐
├ Scénarios : 5 cartes radio (nom · famille · °C · prix carbone)
├ Hypothèses : horizon 2030|2040|2050 · prix carbone · scope 3 ⃞
│              pass-through ▬▬●▬▬ · marge EBITDA · PD₀   [Réinit.]
├ KPI : PD initiale │ PD stressée │ Δ bps │ BBB → BB
├ Waterfall (PD₀ → transition → physique → PD*) │ Courbe 2030/40/50
├ Comparaison des 5 scénarios à l'horizon retenu
└ Table des hypothèses + sources (traçabilité CSRD)
```

- JS vanilla dans `climate_stress_test.js`, recalcul par `fetch` avec debounce
  300 ms sur tout changement d'hypothèse, `localStorage` partagé
  `selected-company-id` comme les autres pages de risque.
- **Chart.js 4.4.4 par CDN** — déjà chargé par `leap_prepare.html`. Aucune
  dépendance nouvelle, aucun framework JS.
- Accessibilité : `role="radiogroup"` sur les cartes de scénario avec navigation
  clavier, `<label>` sur chaque champ, `aria-live="polite"` sur le bandeau KPI
  pour annoncer la PD recalculée, contraste AA.
- Navigation : sous-item « Stress test climatique » dans l'accordéon « Analyse
  des risques » de `templates/base.html`.
- États vides explicites : entreprise sans CA, sans émissions, ou sans actif
  produisent chacun un message dédié plutôt qu'un zéro silencieux.

---

## 4. Tests

| Niveau | Contenu |
|---|---|
| Noyau pur | Neutralité `S=0 ⟹ PD*=PD₀` ; monotonie ; bornes `0<PD*<1` ; `pass_through=1 ⟹ coût nul` ; `ΔP<0 ⟹ coût nul` ; ratio physique borné à 1 ; additivité `S_total` ; table PD↔rating aux frontières |
| Service | PD₀ pondérée par le mix sectoriel ; repli sans mix ; sélection de l'année de référence ; absence d'émissions → avertissement et canal transition nul ; absence de CA → payload vide sans erreur |
| Formulaire | Bornes rejetées (`pass_through=1.5`, `pd_baseline=0`, horizon inconnu) ; valeurs par défaut appliquées quand un champ est absent |
| Vues | 200 ; `Content-Type` JSON ; `login_required` ; 404 entreprise inconnue ; 400 paramètre invalide ; page rend le template avec `companies` et `initial_data` |
| Golden | `dashboard/golden/climate_stress_test.json` sur ACME, scénario et hypothèses par défaut, dans `GoldenViewOutputTests` |
| Trajectoires | Interpolation linéaire entre points ; valeur constante avant 2025 et après 2050 ; lecture exacte sur un point de la grille |
| Seed | Les 5 scénarios et leurs 4 points de trajectoire existent après migration ; monotonie des trajectoires ; `source` renseigné sur chaque scénario |

---

## 5. Fichiers

**Créés**

- `dashboard/services/stress_test.py`
- `dashboard/forms.py`
- `dashboard/templates/dashboard/climate_stress_test.html`
- `dashboard/static/dashboard/js/climate_stress_test.js`
- `dashboard/migrations/0042_climate_scenario_models.py`
- `dashboard/migrations/0043_seed_climate_scenarios.py`
- `dashboard/golden/climate_stress_test.json`

**Modifiés**

- `dashboard/models.py` — 3 modèles
- `dashboard/views.py` — 2 vues fines
- `dashboard/urls.py` — 2 routes (`climate_stress_test`, `climate_stress_test_data`)
- `dashboard/admin.py` — enregistrement des 3 modèles
- `templates/base.html` — sous-item de navigation
- `dashboard/static/dashboard/css/style.css` — styles de la page
- `dashboard/tests.py` — les niveaux du §4
- `dashboard/management/commands/populate_acme.py` — profils sectoriels de démo

---

## 6. Conformité CLAUDE.md

| Exigence | Respect |
|---|---|
| Pas de framework frontend | JS vanilla ; Chart.js déjà présent et chargé explicitement |
| Parité SQLite / PostgreSQL | Aucun `JSONField`, aucune fonction PostGIS ; maths en `statistics.NormalDist` (stdlib) |
| Pas de dépendance nouvelle | Aucune ligne ajoutée à `requirements.txt` |
| Une migration = un changement logique | Schéma et seed séparés, nommés explicitement |
| Formulaires, jamais d'entrée brute | `StressTestForm` valide tous les paramètres GET |
| Namespacing des URLs | `dashboard:climate_stress_test` |
| Traçabilité CSRD | `source` / `reference` sur les 3 modèles ; table d'hypothèses affichée |
| Accessibilité | ARIA, navigation clavier, contraste AA |
| Tests | Un test au minimum par modèle, vue et formulaire ajouté |

---

## 7. Hors périmètre

- Alignement de la page Risque physique sur l'agrégation multiplicative (§2.3).
- Persistance des exécutions (`StressTestRun`) et historique.
- Import des trajectoires NGFS depuis un export du portail (app `imports`).
- Canal biodiversité adossé à la dette écologique.
- Modèle de Merton sur données de marché (exigerait des données de bilan).
- Exposition des paramètres du modèle de crédit à l'écran (σ, τ₃, λ).

---

## 8. Références

- NGFS, *Climate Scenarios for Central Banks and Supervisors — Phase V*,
  novembre 2024 — <https://www.ngfs.net/ngfs-scenarios-portal/>
- BCE, *Economy-wide climate stress test — Methodology and results*, Occasional
  Paper Series 281, septembre 2021 —
  <https://www.ecb.europa.eu/pub/pdf/scpops/ecb.op281~05a7735b1c.en.pdf>
- ACPR, *Les principaux résultats de l'exercice pilote climatique 2020*, Analyses
  et synthèses n° 122 —
  <https://acpr.banque-france.fr/en/analysis-and-synthesis-no-122-main-results-2020-climate-pilot-exercise>
- Trucost / S&P Global, *Carbon Earnings at Risk methodology*
- MSCI, *Climate Value-at-Risk methodology* —
  <https://www.msci.com/documents/1296102/39141520/Updated_PUBLIC_CVaR_Meth+doc_EEC.pdf>
- Merton, R. C. (1974), *On the Pricing of Corporate Debt: The Risk Structure of
  Interest Rates*
- Vasicek, O. (1987), *Probability of Loss on Loan Portfolio* — et la littérature
  sur les inconsistances de la conversion TtC → PiT
- Acharya, Berner, Engle et al., *Climate Stress Testing*, Federal Reserve Bank
  of New York Staff Report 1059 —
  <https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr1059.pdf>
