# Page commodités et modificateurs de pratiques

> Design du 2026-10-24. Objet : une **page dédiée** pour créer et modifier les
> commodités (identité, sources, facteurs midpoint / endpoint régionalisés) et
> introduire des **modificateurs** propres à chaque commodité (« certifié »,
> « agriculture biologique », « circuit court »…) que l'on coche sur les flux et qui
> ajustent les facteurs d'impact en pourcentage.

Les passages marqués **[choix de conception]** sont des décisions prises par
l'auteur du design faute d'indication de l'utilisateur ; elles peuvent être
remises en cause en relecture. Tout le reste a été tranché par l'utilisateur.

---

## 1. Intention

Le site ne sait pas distinguer les **pratiques de production** d'une même
commodité. Un soja certifié et un soja conventionnel ont le même facteur d'impact,
alors que c'est précisément ce qui fait bouger l'impact réel d'une entreprise.

Cas d'usage de référence : pour **Acme Corp**, le flux de soja *Mato Grosso →
usine de transformation* doit pouvoir être scindé entre du soja **certifié** et du
soja **classique** (deux lignes de flux, même année, mêmes extrémités, quantités
qui somment au total réel).

Aujourd'hui :

- Une commodité se crée dans l'admin Django ou en mode rapide depuis la carte des
  flux (nom + unité, `CommodityQuickForm`).
- Ses facteurs (`CharacterizationFactor`) se saisissent un par un dans l'admin :
  16 catégories (`ImpactCategory`), 11 midpoint et 5 endpoint (ReCiPe 2016, GBS),
  régionalisés (région → pays → global), avec une source en texte libre.
- Aucune notion de variante ni de modificateur.

Qui remplit : un **Créateur** (rôle `CREATOR`), à partir d'une fiche Agribalyse,
d'un jeu de données Ecoinvent, d'un article scientifique ou d'un rapport de
certification.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**

1. Une page dédiée, hors admin Django, pour créer et modifier une commodité : nom,
   unité, sources, facteurs midpoint et endpoint **présentés dans deux blocs
   séparés**, régionalisation.
2. Des **modificateurs propres à chaque commodité**, chacun avec des effets en %
   par catégorie d'impact.
3. Dans la carte des flux, après le choix de la commodité, **cocher les
   modificateurs** applicables au flux.
4. Les modificateurs cochés sur un **flux de production d'un actif détenu** sont
   pris en compte dans **tous** les calculs d'impact du site.

**Non-objectifs (premier temps)**

- Pas d'objet « variante » nommé et réutilisable : une variante **est** la
  combinaison de modificateurs cochée sur un flux.
- Pas de ventilation des résultats par variante : les écrans qui ventilent par
  commodité (ex. ESG environnement `by_commodity`) gardent « Soja » sur une seule
  ligne. Les modificateurs ne sont visibles **que dans le détail des flux**.
- Les flux d'approvisionnement n'entrent toujours pas dans les calculs d'impact
  (impact amont non modélisé). Les modificateurs y sont des labels.
- Pas de modificateurs régionalisés : l'effet d'un modificateur est le même quel
  que soit le lieu du flux. **[choix de conception]**
- Pas de figement des valeurs déjà publiées (voir § 5.4).

**Anti-objectifs**

- Un modificateur **partagé entre commodités**. « Bio » sur le soja et « bio » sur
  le café sont deux modificateurs distincts aux effets distincts.
- Un tableau de bord dont les chiffres ne collent pas avec les modificateurs cochés
  (un écran oublié dans le recalcul).
- Un flux sans modificateur dont l'impact change : les données existantes doivent
  donner exactement les mêmes chiffres qu'avant.

## 3. Contraintes

Celles de `CLAUDE.md` s'appliquent : Django, HTML/CSS/JS natif sans framework,
compatible SQLite **et** PostgreSQL, cPanel, i18n FR (source) / EN, `.mo` commités,
une migration par changement logique, tests pour tout nouveau modèle / vue /
formulaire, charte `DESIGN.md` (tokens `--color-*`, thèmes clair / sombre).

## 4. Données

### 4.1 Nouveaux modèles

Noms indicatifs ; `created_at` / `updated_at` / `created_by` sur chacun (règle des
nouveaux modèles métier, traçabilité CSRD).

**`CommoditySource`** — source documentaire d'une commodité.

| Champ | Type | Note |
|---|---|---|
| `commodity` | FK `Commodity`, CASCADE, `related_name='sources'` | |
| `kind` | `TextChoices` | `AGRIBALYSE`, `ECOINVENT`, `ARTICLE`, `CERTIFICATION`, `OTHER` |
| `title` | Char 255 | obligatoire |
| `reference` | Char 500, blank | URL, DOI, version de base, page… |

Affichée sur la page sous un code court `S1`, `S2`… (ordre de création, calculé à
l'affichage, non stocké). **[choix de conception]**

**`CommodityModifier`** — pratique de production propre à une commodité.

| Champ | Type | Note |
|---|---|---|
| `commodity` | FK `Commodity`, CASCADE, `related_name='modifiers'` | |
| `name` | Char 100 | unique par commodité |
| `description` | Text, blank | |
| `source` | FK `CommoditySource`, SET_NULL, null | doit appartenir à la même commodité |

**`ModifierEffect`** — effet d'un modificateur sur une catégorie.

| Champ | Type | Note |
|---|---|---|
| `modifier` | FK `CommodityModifier`, CASCADE, `related_name='effects'` | |
| `category` | FK `ImpactCategory`, CASCADE | midpoint ou endpoint |
| `percent` | Float | ex. `-10.0` pour −10 %. Validation : `≥ -100`. Pas de borne haute. |

Contrainte unique (`modifier`, `category`). Une catégorie sans `ModifierEffect` est
inchangée par ce modificateur. Un effet peut être **positif** (le bio peut
augmenter l'usage des sols). **[choix de conception]**

### 4.2 Modèles existants modifiés

- **`Flow.modifiers`** : `ManyToManyField(CommodityModifier, blank=True,
  related_name='flows')`. Validation (formulaire et import) : chaque modificateur
  appartient à `flow.what`. Changer la commodité d'un flux **vide** ses
  modificateurs. Autorisé sur **toutes les natures** de flux (production,
  approvisionnement, consommation, émission, déchet), du moment que la commodité
  en définit.
- **`CharacterizationFactor.source_ref`** (nom à arbitrer) : FK nullable vers
  `CommoditySource`, SET_NULL. Les champs texte `source` / `reference` existants
  sont conservés (lecture, import Excel historique) ; la page écrit `source_ref`.
  **[choix de conception]**

### 4.3 Migration des données existantes

Migration de données : pour chaque couple distinct (`commodity`, `source`,
`reference`) non vide des CF existants, créer une `CommoditySource` de type
`OTHER` et la rattacher aux CF correspondants. Aucune valeur de facteur ne change.
**[choix de conception]**

## 5. Calcul

### 5.1 Règle

Pour un flux, une catégorie `c` et le facteur `F` résolu comme aujourd'hui
(région → pays → global → 0) :

```
facteur_ajusté = F × max(0, 1 + Σ percent(m, c) / 100)
```

où la somme porte sur les modificateurs `m` cochés sur le flux qui ont un effet sur
`c`. Les effets **s'additionnent** (−10 % et −5 % → −15 %, et non 0,90 × 0,95).
Si la somme dépasse −100 %, le facteur est **plafonné à 0**, jamais négatif.

### 5.2 Où elle s'applique

- **Flux de production des actifs détenus** (`flow_service.productions`,
  `latest_productions`, `company_productions`) : la règle s'applique dans
  **chaque** calcul `quantité × facteur`. Inventaire des appels au moment du
  design : `dashboard/views.py` (≈ 10 sites : overview, empreinte, dette
  écologique, compare, compliance, dépendances…),
  `dashboard/services/esg_environment.py`, `dashboard/services/impacts.py`
  (`measured_vs_modeled`). Le builder refait l'inventaire
  (`grep cf_value`) : **aucun ne doit être oublié**.
- **Hors périmètre, car sans facteur d'impact** : le stress test
  (`services/stress_test.py`), le risque physique portefeuille
  (`services/portfolio_physical.py`) et les vues pondérées par le revenu
  (`views.py` ≈ l. 532 et 1997). Ils lisent les productions pour leur
  `estimated_revenue`, jamais pour un facteur ; un modificateur n'y change rien.
  Créer un lien impact biodiversité → risque de crédit serait un autre projet.
- **Tous les autres flux** : modificateurs stockés et affichés, sans effet sur
  aucun chiffre.

**Cas particulier : LEAP Prepare** (`_get_leap_prepare_data`, `leap_prepare.js`).
Le serveur envoie un `impact_factor` **par commodité** et additionne les
quantités par (actif, commodité) ; le navigateur calcule `qty × impact_factor` et
applique un levier « impact » par commodité. Conformément au regroupement par
commodité (§ 2), les lignes restent par (actif, commodité), mais chaque ligne
porte son propre facteur : la **moyenne pondérée par les quantités** des facteurs
ajustés de ses flux. Le JS utilise le facteur de la ligne ; le levier par
commodité s'applique par-dessus. C'est le seul écran dont la forme JSON change.
Ce facteur reste global (non régionalisé) comme aujourd'hui : régionaliser LEAP
Prepare est hors périmètre. **[choix de conception]**

### 5.3 Mise en œuvre attendue

Centraliser dans `dashboard/services/impacts.py` : un helper qui, à partir d'un
flux (modificateurs préchargés), renvoie le multiplicateur par catégorie, et une
variante de `cf_value` qui l'applique. Les vues n'implémentent pas la formule
elles-mêmes. Les requêtes de productions préchargent `modifiers__effects`
(`prefetch_related`) pour éviter le N+1. La forme de sortie des vues ne change pas
(les tests « golden » existants doivent passer à l'identique sur des données sans
modificateur).

### 5.4 Modification et suppression

Les calculs sont faits à la volée : modifier un effet (−10 % → −12 %) **recalcule
tout**, années passées comprises, comme c'est déjà le cas quand on change un
facteur. **Supprimer** un modificateur est autorisé même s'il est utilisé : il est
retiré des flux qui le portaient (CASCADE sur la table de liaison) et les impacts
sont recalculés. La page affiche avant suppression le nombre de flux concernés
dans la confirmation. **[choix de conception pour la confirmation]**

## 6. Page commodités

### 6.1 Accès et navigation

- **Liste** `/commodites/` : nom, unité, nombre de facteurs renseignés, nombre de
  modificateurs, recherche par nom. Bouton « Nouvelle commodité » pour les
  Créateurs.
- **Fiche** `/commodites/<pk>/` : lecture pour tout utilisateur connecté,
  édition pour les Créateurs. **[choix de conception : lecture réservée aux
  utilisateurs connectés]** (voir § 9, licences).
- Entrée dans la navigation latérale, à côté de la carte des flux.
- L'admin Django et la création rapide depuis la carte des flux restent en place.

### 6.2 Contenu de la fiche (maquette validée)

Dans l'ordre :

1. **Identité** : nom, unité, description, classe de perte de biodiversité. Les 6
   dépendances aux services écosystémiques sont dans un bloc replié. La `key` des
   commodités techniques (`TECHNICAL_COMMODITIES`) est affichée en lecture seule.
2. **Sources** : tableau `S1…` (type, titre, référence / lien), ajout,
   modification, suppression.
3. **Sélecteur de lieu** (option B validée) : pastilles `Global`, puis chaque pays
   ou `Pays › Région` ayant au moins un facteur, et « + pays ou région ». Le lieu
   choisi pilote les deux blocs suivants.
4. **Facteurs midpoint** (catégories `level=MIDPOINT`) puis **facteurs endpoint**
   (`level=ENDPOINT`), deux blocs visuellement distincts. Une ligne par catégorie :
   libellé, facteur, unité de la catégorie, source (liste des `S…`).
   - Champ vide = pas de facteur à ce lieu : la valeur **héritée** s'affiche en
     gris avec son origine (« 2 400 ← Brésil », « 42 ← Global »).
   - Saisir une valeur crée le CF de ce lieu ; vider le champ le supprime.
5. **Modificateurs** : un bloc par modificateur (nom, description, source), avec
   la liste de ses effets : catégorie (badge mid / end), effet en %, **facteur
   ajusté** pour le lieu sélectionné (aperçu). « + Effet sur une catégorie »,
   « + Nouveau modificateur », suppression avec confirmation (§ 5.4).

Ajouter un modificateur, une source ou un lieu ne recharge pas forcément la page :
le builder choisit entre formulaires classiques (formsets) et petits appels JSON,
en JS natif. Les nombres acceptent la virgule décimale comme dans la carte des
flux (`FlowMapFlowForm.clean_quantity`).

## 7. Carte des flux

- Panneau de flux (`_flow_map_panel.html`, `flow_map_panel.js`) : sous le choix de
  la commodité, une liste de cases à cocher « Modificateurs » avec ceux de la
  commodité choisie. Rien si la commodité n'en a pas. Changer de commodité vide la
  sélection.
- Pour un flux qui n'est pas une production d'actif détenu, une mention discrète
  indique que les modificateurs sont des labels et ne changent pas les calculs.
- Endpoints JSON création / modification : acceptent `modifier_ids` ;
  `_serialize_flow` renvoie `modifiers: [{id, name}]`. La recherche de commodités
  renvoie les modificateurs de chacune (ou un endpoint dédié, au choix du builder).
- **Identité d'un flux** : `flow_key()` inclut l'ensemble trié des modificateurs.
  Le soja certifié et le soja classique sont donc deux flux distincts pour
  `latest_flows`, `flow_years` et la suppression par années : supprimer la ligne
  certifiée ne supprime pas la ligne classique. **[choix de conception]**
- Dessin : les deux lignes restent sous **une même flèche** (même nature, même
  commodité, mêmes extrémités) ; le panneau de la flèche liste chaque ligne avec
  ses modificateurs (« Soja · Certifié RTRS — 40 000 t »).

## 8. Import / export Excel

- Feuille des flux : nouvelle colonne `modifiers`, noms de modificateurs séparés
  par `;`. À l'import, un nom inconnu pour la commodité de la ligne est une erreur
  de validation de la ligne (pas de création implicite). **[choix de conception]**
- Feuille `CharacterizationFactor` : l'import applique la même règle que la
  migration (§ 4.3) — il retrouve ou crée la `CommoditySource` `OTHER`
  correspondant au couple (`source`, `reference`) et remplit `source_ref`. Un CF
  importé apparaît donc toujours avec son `S…` sur la page. **[choix de
  conception]**
- Pas de feuille pour les sources, modificateurs et effets dans ce premier temps :
  ils se saisissent sur la page. **[choix de conception]**
- `imports/services/constants.py` et son test d'alignement sont mis à jour ;
  l'aller-retour export → import conserve les modificateurs.

## 9. Laissé au builder

- Noms exacts des modèles, champs, URL et fichiers JS / CSS.
- Mécanique d'édition de la fiche (formsets ou JSON) et de bascule des pastilles
  de lieu (paramètre GET ou JS).
- Gestion du jeu de démonstration `populate_acme` : ajouter au soja d'Acme un
  modificateur « Certifié RTRS » et scinder le flux Mato Grosso → usine, pour que
  la fonctionnalité soit visible en démo.
- Point à signaler à l'utilisateur, pas à résoudre : la licence Ecoinvent limite
  la redistribution des données ; afficher des facteurs Ecoinvent sur une page
  consultable relève de sa responsabilité.

## 10. Tests attendus

- Modèles : création nominale de chaque modèle ; `percent < -100` refusé ;
  unicité (`modifier`, `category`) et (`commodity`, `name`) ; modificateur d'une
  autre commodité refusé sur un flux ; source d'une autre commodité refusée sur un
  modificateur.
- Calcul : aucun modificateur → valeur inchangée ; un modificateur ; deux
  modificateurs qui s'additionnent ; somme < −100 % → 0 ; effet positif ; catégorie
  sans effet inchangée ; facteur régional + modificateur.
- Périmètre du calcul : un modificateur sur un flux SUPPLY ne change aucun
  chiffre ; sur une PRODUCTION d'actif détenu, il change les écrans concernés (au
  moins overview, ESG environnement, LEAP Prepare), et ne change pas le stress
  test.
- Suppression d'un modificateur utilisé : retiré des flux, impact recalculé.
- Vues : liste et fiche (lecture connecté, édition Créateur, 403 / redirection
  Abonné et anonyme) ; création d'une commodité avec facteurs midpoint, endpoint
  et un CF régional.
- Carte des flux : création / modification avec `modifier_ids` ; changement de
  commodité qui vide les modificateurs ; `flow_key` distinguant deux lignes.
- Import / export : colonne `modifiers` en aller-retour ; nom inconnu refusé.
- Migration de données des sources : CF existants rattachés, valeurs inchangées.
