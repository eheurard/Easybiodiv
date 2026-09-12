# Vue d'ensemble — modes de carte (pays, asset, risque physique, dette écologique)

> Design validé le 2026-09-12. Branche `feat/overview-modes-carte`.
> Objet : fusionner dans la page **Vue d'ensemble** (`/`) les vues cartographiques de
> **LEAP Locate**, **Risque physique** et **Dette écologique**, via 4 boutons de mode
> dans le panneau droit. Chaque mode adapte le panneau, la légende, le style des
> points et, si besoin, le tiroir bas. Les pages de référence **restent en place**.

---

## 1. Contexte

La Vue d'ensemble (`dashboard/templates/dashboard/index.html`, logique dans le bloc
« Overview page » de `dashboard/static/dashboard/js/main.js`) affiche une carte
MapLibre plein écran, un panneau droit « Exposition » à 2 onglets (par pays / par
asset classé par empreinte, avec filtre par type et tri) et un tiroir bas
« Politiques ». Les points sont colorés par type d'actif (`ASSET_TYPE_COLORS`).

Trois pages carte portent déjà les données à fusionner, chacune avec son JS :

| Page | API (existante) | Panneau droit | Points | Tiroir bas |
|---|---|---|---|---|
| LEAP Locate (`leap_locate.js`) | `leap_locate_data` — **login requis** | Liste de sites : type (classe biodiv.), détention, productions, revenu associé | Couleur + taille par revenu associé ; supply chain (courbes + flèches animées) | — |
| Risque physique (`physical_risk.js`) | `physical_risk_data` — public | 3 KPI (perte 5/10 ans) + classement des aléas (sélecteur) | Couleur par bande d'aléa, taille par risque € | « Détail par actif » |
| Dette écologique (`dette_ecologique.js`) | `dette_ecologique_data` — **login requis** | 4 KPI + bascule asset/région | Camemberts par commodité (taille ∝ √Lbiodiv) | — |

`index` et `company_data` sont publics. `pie_markers.js` expose déjà un module
partagé `window.PieMarkers` (utilisé par le portfolio ; la page dette en garde une
copie dupliquée).

**Décisions de cadrage (arbitrées) :**
- Les pages Locate, Risque physique et Dette **restent** accessibles (menu et
  parcours LEAP inchangés). Le code de rendu est **partagé** entre ces pages et la
  Vue d'ensemble pour éviter toute divergence (approche A).
- Mode asset : reprise **complète** de Locate, supply chain comprise. Le filtre par
  type d'actif et le tri sont conservés ; le tri porte sur le **revenu associé**
  (l'empreinte n'est pas dans la sortie Locate).
- Le bouton **Supply chain** est en haut à gauche de la carte et **disponible dans
  tous les modes**.
- Mode dette : **camemberts + liste d'assets au format Locate**, sans regroupement
  par région.
- Tiroir bas : **Politiques** dans les modes pays, asset et dette ; **Détail par
  actif** en mode risque physique.
- Visiteur non connecté : les modes asset et dette, ainsi que la supply chain, sont
  **affichés mais désactivés** (« Connexion requise »). Les règles d'accès des API
  ne changent pas.
- Chargement **à la demande** via les **endpoints existants** ; aucun nouvel
  endpoint.

## 2. Expérience utilisateur

### 2.1 Panneau droit

Les 2 onglets actuels sont remplacés par une grille 2×2 de boutons de mode, fixe en
tête du panneau (le contenu du mode défile dessous). Le titre du panneau reprend
celui de la page de référence.

| Clé | Bouton | Titre du panneau | Connexion requise |
|---|---|---|---|
| `pays` | Exposition pays | Exposition par pays | non |
| `asset` | Exposition asset | Sites localisés | oui |
| `risque` | Risque physique | Classement des risques | non |
| `dette` | Dette écologique | Dette écologique | oui |

Boutons : `<button type="button" data-mode="…" aria-pressed="…">` dans un
`role="group"` (« Mode d'affichage de la carte »). Un bouton verrouillé est rendu
`disabled` par le serveur, avec `title="Connexion requise"` et une icône cadenas.

### 2.2 Contenu par mode

| Mode | Panneau droit | Points | Légende (bas gauche) | Tiroir bas |
|---|---|---|---|---|
| `pays` | Liste des pays (inchangée) ; clic → zoom pays | Couleur par type d'actif, rayon 7 (inchangé) ; popup actuel (productions, empreinte, dette) | « Type d'actif » dynamique (inchangée) | Politiques |
| `asset` | Barre d'outils (filtre par type d'actif, tri revenu ↓/↑) + liste Locate (nom, badge classe biodiv., détention, productions, revenu) ; clic → zoom asset | Couleur + taille par bande de revenu (Locate) ; popup Locate | « Revenu associé » (Faible → Très élevé) | Politiques |
| `risque` | 3 KPI (actifs à risque élevé, vulnérabilité moyenne, perte projetée + 5/10 ans) + classement des aléas cliquable | Couleur par bande de l'aléa sélectionné, taille par risque € ; popup Risque physique | « Risque physique » (Faible → Critique) | Détail par actif (aléa sélectionné) |
| `dette` | 4 KPI (Lbiodiv total, année de référence, assets, top commodité) + liste d'assets au format Locate : nom, badge part du total (%), Lbiodiv, répartition par commodité (pastille, nom, %) ; clic → zoom asset | Camemberts par commodité (taille ∝ √Lbiodiv), infobulle au survol | « Commodités » (pastille, nom, %) — 8 premières | Politiques |

Précisions :
- Le filtre par type (mode asset) porte sur `Asset.type` (Smelter, Mine…), ordonné
  comme la palette `ASSET_TYPE_COLORS` ; il filtre la **liste seulement**, comme
  aujourd'hui. Libellés du tri : « Revenu décroissant » / « Revenu croissant ».
- Mode risque : l'aléa sélectionné par défaut est le premier du classement ;
  horizon 5 ans par défaut. Aléa et horizon sont conservés quand on change de mode,
  et réinitialisés quand on change d'entreprise (comme sur la page de référence).
- Mode dette : seuls les assets ayant une dette calculable apparaissent (les assets
  sans région subnationale sont exclus, comme sur la page Dette). Liste vide :
  « Aucun asset avec une dette calculable. »
- Zoom au clic dans une liste d'assets : `zoom: 9` (valeur de Locate) ; pays :
  `zoom: 5` (inchangé).

### 2.3 Supply chain (tous modes)

- Bouton « Supply chain » dans une pastille sous le sélecteur de fond
  (`.map-stage__tl`), `aria-pressed`. Désactivé (« Connexion requise ») pour un
  visiteur non connecté.
- Au premier clic, les données Locate de l'entreprise sont chargées (ou reprises du
  cache si le mode asset les a déjà chargées).
- Courbes sous les points, flèches animées et points fournisseurs au-dessus
  (popup fournisseur de Locate). En mode dette, les camemberts (marqueurs DOM)
  restent au-dessus de tout.
- Légende « Flux fournisseurs » (pastille + commodité) empilée sous la légende du
  mode, visible uniquement quand la supply chain est active.
- État conservé au changement de mode et d'entreprise (les données sont
  rechargées pour la nouvelle entreprise).

### 2.4 Couleurs des commodités (Vue d'ensemble)

Flèches supply chain et camemberts partagent **une seule table commodité → couleur
par entreprise**, pour qu'une commodité ait la même couleur partout sur la carte :
- Palette : `PieMarkers.PALETTE`.
- Construction : d'abord les commodités de `company_data` (toujours chargé), triées
  alphabétiquement ; puis, quand Locate est chargé, les commodités des flux
  fournisseurs absentes de la table, triées alphabétiquement, ajoutées à la suite.
  Une couleur déjà attribuée ne change jamais pendant la vie de l'entreprise
  sélectionnée.
- Les pages Locate et Dette gardent leurs propres palettes (inchangées).

### 2.5 Comportements communs

- Sélecteur de fond (Classique / Gris / Satellite) et bascule jour/nuit actifs dans
  tous les modes.
- Changer d'entreprise conserve le mode actif.
- Le mode est mémorisé dans `localStorage['overview-mode']`. Si le mode mémorisé
  est verrouillé (visiteur non connecté) ou inconnu → repli sur `pays`.
- Pendant le chargement d'un mode : message « Chargement… » (`role="status"`) dans
  la vue du mode.

## 3. Architecture

### 3.1 Modules JS partagés

Même forme que `pie_markers.js` : IIFE exposant un espace de noms `window.X`, sans
dépendance autre que les utilitaires globaux de `main.js` (`escHtml`, `fmtNum`,
`fmtEuro`, `mapStyleFor`) et `maplibregl`.

| Fichier | Espace de noms | Contenu | Utilisé par |
|---|---|---|---|
| `locate_view.js` | `LocateView` | `REVENUE_COLORS`, `revenueBand`, `styleFeatures(features)` (couleur/rayon par revenu), `prodLine`, `listHtml(features)` (cartes `.ll-item` avec `data-lng`/`data-lat`), `popupHtml(props)` | Locate, Vue d'ensemble |
| `supply_chain.js` | `SupplyChain` | `SupplyChain.create(map, opts)` → instance à état encapsulé : `setData(locateData)`, `addLayers(beforeLayerId)`, `setVisible(bool)`, `isVisible()`, `stop()` / `resume()` de l'animation, `renderLegend(box, list)`, `colors()`. `opts.colorFor(commodity)` optionnel ; à défaut, table alphabétique sur la palette Locate actuelle. Liaison des évènements (popup fournisseur, curseur) une seule fois par instance. | Locate, Vue d'ensemble |
| `physical_risk_view.js` | `PhysicalRiskView` | `BAND_COLORS`, `band`, `fmtEuro`, `buildGeojson(data, hazardKey)`, `renderKpis(data, horizon)`, `renderRanking(data, selectedKey, onSelect)`, `renderTable(data, hazardKey)`, `popupHtml(props)` — ciblent les identifiants des fragments partagés (§ 3.3) | Risque physique, Vue d'ensemble |
| `dette_view.js` | `DetteView` | `fmtLbiodiv`, `renderKpis(data, mode)`, `renderLegend(listEl, commodities, colors)`, `showTooltip` / `moveTooltip` / `hideTooltip(tipEl, mapEl, …)`, `assetListHtml(assets, colors)` (nouveau, format Locate) | Dette, Vue d'ensemble |
| `pie_markers.js` (existant) | `PieMarkers` | inchangé | Dette (**nouveau**), portfolio, Vue d'ensemble |

Les pages de référence deviennent des amorces qui appellent ces modules :
- `leap_locate.js` : garde combobox, repli du panneau, sélecteur de fond,
  initialisation de la carte ; délègue liste/style/popup à `LocateView` et toute la
  supply chain à une instance `SupplyChain`. Rendu identique (palette Locate).
- `physical_risk.js` : garde combobox, bascule d'horizon, carte ; délègue KPI,
  classement, tableau, geojson et popup à `PhysicalRiskView`.
- `dette_ecologique.js` : garde combobox, bascule asset/région, carte ; délègue KPI,
  légende, infobulle à `DetteView` et les camemberts à `PieMarkers.render` (la copie
  locale `deBuildPieEl` est supprimée — sortie SVG identique). `dette_ecologique.html`
  charge `pie_markers.js`.

### 3.2 `overview.js` et `main.js`

- **`overview.js`** (nouveau) reprend toute la logique de la Vue d'ensemble
  actuellement dans `main.js` (bloc « Overview page » et fonctions associées :
  `ASSET_TYPE_COLORS`, légende des types, couche et popup des assets, combobox,
  liste des pays, politiques, `scoreColor`…) et ajoute le contrôleur de modes.
- Registre `MODES` : pour chaque clé → titre, URL d'API, connexion requise,
  `renderPanel`, `mapFeatures`, `renderLegend`, `popupHtml`, tiroir.
- État : entreprise courante, mode courant, cache
  `{ company, locate, risque, dette }` pour l'entreprise courante, aléa et horizon
  du mode risque, filtre/tri du mode asset, instance `SupplyChain`, marqueurs
  camembert, table des couleurs de commodités.
- **`main.js`** ne garde que le transverse : écran de chargement, fonds de carte
  (`MAP_STYLES`, `mapStyleFor`, `currentTheme`, `activeMapStyleName`), sidebar,
  thème, menu utilisateur, utilitaires de formatage. Correctif associé :
  `activeMapStyleName()` cible `.map-layer-btn--active[data-layer]` (le bouton
  supply chain porte aussi `.map-layer-btn`).
- Le sélecteur de fond de la Vue d'ensemble ne lie que les boutons `[data-layer]`
  (comme Locate), pour que la supply chain ne déclenche pas de `setStyle`.

Ordre de chargement dans `index.html` (tous `defer`, ordre d'exécution garanti) :
MapLibre, `map_layout.js`, `pie_markers.js`, `locate_view.js`, `supply_chain.js`,
`physical_risk_view.js`, `dette_view.js`, `overview.js`. Les URL d'API sont passées
dans un objet unique `OVERVIEW_API = { company, locate, risque, dette }` construit
avec `{% url … pk=0 %}` ; le JS remplace `/0/` par `/<id>/`.

### 3.3 Templates

Fragments partagés (dans `dashboard/templates/dashboard/`), inclus par la page de
référence **et** par `index.html`, avec les mêmes identifiants :
- `_pr_panel.html` : rangée de KPI (`#pr-high-risk`, `#pr-avg-vuln`,
  `#pr-annual-loss` + boutons d'horizon) et `#pr-ranking`.
- `_pr_detail_drawer.html` : tiroir « Détail par actif » (`#pr-selected-hazard`,
  `#pr-table-body`). Paramètres d'inclusion : identifiant de section et état masqué
  initial (masqué dans la Vue d'ensemble hors mode risque).
- `_de_kpis.html` : rangée de KPI dette (`#de-total-lbiodiv`, `#de-year`,
  `#de-point-count`, `#de-point-count-label`, `#de-top-commodity`).

`index.html` contient : la grille des 4 boutons de mode, 4 vues de panneau (une
seule visible), la pastille supply chain, les conteneurs de légende
(`#ov-mode-legend`, `#ov-supply-legend`), l'infobulle dette (`#de-tooltip`) et deux
tiroirs (Politiques, Détail par actif). Les états `disabled` des boutons verrouillés
sont posés côté serveur via `user.is_authenticated`.

### 3.4 Backend

Seul changement : `_get_leap_locate_data` ajoute `'type': a.type` aux propriétés de
chaque feature (nécessaire au filtre par type du mode asset). Champ additif.
`leap_locate` fait partie de `GOLDEN_VIEWS` → réenregistrer le golden et ne
conserver que la modification de `dashboard/golden/leap_locate.json` (ajout de
`type` uniquement) ; les autres fichiers golden doivent rester identiques.

Aucune vue, URL ni règle d'authentification ne change. `index` reste public.

### 3.5 CSS (`style.css`)

- Nouveau bloc `.ov-modes` / `.ov-mode-btn` (grille 2×2, état actif en
  `--color-primary` / `--color-on-primary`, état désactivé atténué + cadenas),
  jetons de `DESIGN.md` uniquement (aucun hexadécimal pour le chrome).
- Suppression des styles devenus morts, utilisés seulement par l'ancienne Vue
  d'ensemble : `.country-panel__tabs`, `.country-panel__tab-indicator`,
  `.country-panel__tab*` (et leurs surcharges `.map-panel …`), `.asset-card*`.
  `.country-panel`, `.country-panel__view*`, `.country-panel__empty`,
  `.country-item*` et `.asset-list__*` restent utilisés.
- La règle `max-height: 30vh` des listes de légende vise les nouveaux conteneurs
  de légende.

## 4. Flux de données et cycle de vie de la carte

### 4.1 Chargement et cache

```
Ouverture         → company_data injecté par le serveur (inchangé) ; entreprise
                    mémorisée rechargée si différente (inchangé) ; mode mémorisé
                    restauré (repli pays)
Changement        → cache vidé → company_data (toujours : mode pays + Politiques)
d'entreprise        + API du mode actif + Locate si supply chain active
Changement de mode→ données en cache ? rendu immédiat : requête puis rendu
```

- Le mode asset et la supply chain partagent la même réponse Locate (une requête).
- **Courses** : chaque requête retient l'identifiant de l'entreprise demandée ; une
  réponse arrivée après un changement d'entreprise est ignorée. Une réponse arrivée
  après un changement de mode est mise en cache sans être rendue.

### 4.2 Carte

- Une source `ov-assets` et une couche cercle `ov-assets-layer` dont la couleur,
  le rayon, l'opacité et l'épaisseur du contour sont lus dans les propriétés
  (`['get', …]`) calculées par le mode actif (`pays` : type / 7 px ; `asset` :
  `LocateView.styleFeatures` ; `risque` : `PhysicalRiskView.buildGeojson`).
- Mode `dette` : la source est vidée et les camemberts sont créés par
  `PieMarkers.render` avec la table de couleurs commune ; ils sont retirés en
  quittant le mode ou en changeant d'entreprise.
- Un seul écouteur de clic sur `ov-assets-layer` affiche le popup du mode actif.
- Supply chain : `supply.addLayers('ov-assets-layer')` place les courbes sous les
  points.
- Changement de fond ou de thème : arrêt de l'animation → `setStyle(mapStyleFor(…))`
  → `once('idle')` → recréer source et couche, repousser les données du mode,
  `supply.addLayers` + données, relancer l'animation si active. (Remplace le
  `styledata` actuel de la Vue d'ensemble ; « idle » ne se déclenche pas tant que
  l'animation tourne, d'où l'arrêt préalable — schéma éprouvé sur Locate.) Les
  camemberts, marqueurs DOM, survivent au `setStyle`.

### 4.3 Erreurs

| Cas | Comportement |
|---|---|
| Erreur réseau / HTTP ≥ 400 | La vue du mode affiche « Impossible de charger les données. » ; carte et légende du mode vides ; rien n'est mis en cache → un nouveau clic sur le mode relance la requête ; `console.error` conservé |
| Session expirée (réponse redirigée ou non JSON) | Message « Session expirée — reconnectez-vous. » |
| Entreprise sans données | Messages vides des pages de référence (« Aucun site. », « Aucune donnée disponible. », « Aucun actif. »…) |
| Échec du chargement supply chain | Le bouton revient à l'état inactif ; `console.error` |

## 5. Hors périmètre

- Suppression ou redirection des pages Locate, Risque physique, Dette.
- Regroupement par région subnationale en mode dette.
- Nouvel endpoint (combiné ou autre) ; changement des règles d'accès des API.
- Filtre par type appliqué aux points de la carte (liste seulement, comme
  aujourd'hui).
- Lien profond `?mode=…`.
- Tests JS automatisés (pas d'outillage npm dans le projet).

## 6. Tests

Suite Django (`python manage.py test dashboard`), `dashboard/tests.py` :
- `LeapLocateDataTests.test_geojson_feature_properties` : vérifie `props['type']`.
- Nouvelle classe de tests de la page Vue d'ensemble :
  - visiteur anonyme : `GET /` → 200 ; boutons `data-mode="asset"`,
    `data-mode="dette"` et le bouton supply chain rendus `disabled` ;
    `data-mode="pays"` et `data-mode="risque"` actifs ;
  - utilisateur connecté : aucun bouton de mode ni supply chain `disabled` ; les 4
    URL d'API et les scripts `overview.js`, `locate_view.js`, `supply_chain.js`,
    `physical_risk_view.js`, `dette_view.js`, `pie_markers.js` sont présents.
- Fragments partagés : `id="pr-ranking"` et `id="pr-table-body"` présents dans
  `/` et `/physical-risk/` ; `id="de-total-lbiodiv"` présent dans `/` et
  `/dette-ecologique/` (connecté) ; `dette_ecologique.html` charge
  `pie_markers.js`.
- Golden : seul `leap_locate.json` change (ajout de `type`).
- Suite existante entièrement verte.

Vérification navigateur (checklist) :
- Vue d'ensemble : chaque mode × changement d'entreprise, de fond, de thème,
  supply chain active/inactive ; popups, légendes, clic dans les listes, filtre et
  tri (asset), horizon 5/10 ans et sélection d'aléa (carte + tiroir), bascule
  Politiques ↔ Détail par actif, boutons verrouillés en anonyme, restauration du
  mode mémorisé, couleurs de commodités cohérentes entre flèches et camemberts.
- Non-régression : Locate (liste, couleurs revenu, supply chain, fond/thème),
  Risque physique (classement, tiroir, horizon, thème), Dette (camemberts,
  infobulle, bascule asset/région, thème), Portfolio (camemberts).

## 7. Contraintes

- Django pur, compatible SQLite et PostgreSQL, aucune dépendance nouvelle,
  PEP 8 ≤ 100.
- JS vanilla, modules chargés en `defer`, pas de framework ni de npm.
- Chrome de l'interface exclusivement via les jetons `--color-*`, `--scrim-*`,
  `--tint-*` (`DESIGN.md`) ; palettes de données identiques dans les deux thèmes.
- Accessibilité : boutons natifs, `aria-pressed`, `disabled` + `title` explicites,
  message de chargement en `role="status"`.
- Reste dans l'app `dashboard`.
