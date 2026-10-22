# Carte interactive des flux — conception

Date : 2026-10-22
Statut : validé en brainstorming, à planifier

## 1. Intention

Aujourd'hui, les flux d'une entreprise (table `Flow`) se saisissent par la console
admin ou l'import Excel. Le plus pénible est de **voir les connexions** entre les
éléments : qui fournit quoi à quel actif, ce qui part vers le milieu, etc.

La nouvelle page affiche, pour une entreprise et une année, ses actifs, ses
partenaires et le milieu naturel sous forme de **blocs carrés reliés par des
flèches courbes**. On y lit la chaîne d'un coup d'œil et on la complète ou la corrige
directement sur le schéma, de façon ludique : on clique un petit « + » au bord d'un
bloc, puis le bloc d'arrivée, et une fiche courte enregistre le flux.

La page **complète** l'admin et l'import Excel, elle ne les remplace pas.

Maquettes validées (non versionnées) : `.superpowers/brainstorm/30-1792658953/content/`
(`carte-flux.html`, style « A — Courbe lisse » ; `fiche-flux.html`).

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- Visualiser les flux d'une entreprise sélectionnée, pour une année.
- Ajouter des blocs (actif, pays, région, entreprise, groupe d'actifs) en cherchant
  par mot-clé dans la base, ou en créant l'élément s'il n'existe pas (voir §6.2).
- Ajouter, modifier, supprimer des flux depuis la carte.
- Masquer un bloc, ou supprimer ses liens avec l'entreprise (avec confirmation).
- Regrouper des actifs dans des **groupes d'actifs enregistrés** pour rester lisible
  avec des centaines de blocs.

**Non-objectifs**
- Enregistrer la position des blocs : le rangement est recalculé à chaque visite.
- Enregistrer les blocs masqués.
- Remonter la chaîne au-delà du périmètre (voir §4.1) : un flux Brésil → Cargill
  n'apparaît pas s'il ne touche ni l'entreprise ni ses actifs.
- Historique / annulation des modifications (au-delà de la confirmation de
  suppression).
- Supprimer de la base un pays, une région, une entreprise ou un actif depuis cette page.

**Anti-objectifs** (ce qui serait un échec même si « ça marche »)
- Une carte illisible dès quelques dizaines de blocs (spaghetti de flèches).
- Une suppression qui efface plus que ce que l'utilisateur voit à l'écran.
- Pouvoir enregistrer un flux que les contraintes `FLOW_RULES` refusent, ou un message
  d'erreur cryptique à la place de la règle métier.

## 3. Contraintes

- HTML / CSS / JS vanilla (CLAUDE.md). Le graphe est dessiné en **SVG natif**, sans
  bibliothèque de graphe. La mini-carte de création d'actif utilise **MapLibre GL**,
  déjà chargé par CDN sur d'autres pages (le projet n'utilise pas Leaflet en pratique).
- Compatible SQLite et PostgreSQL.
- Lecture des flux **uniquement** via `dashboard/services/flows.py` (règle existante) :
  y ajouter les fonctions nécessaires.
- Écritures via `forms.ModelForm` / `forms.Form`, sur le modèle de `portfolio_save`
  (JSON → formulaire → `JsonResponse` avec `errors`). Les contraintes en base de `Flow`
  doivent remonter comme erreurs de formulaire lisibles (`violation_error_message`).
- Bilingue FR/EN : tout texte visible marqué (gabarits, JS via `gettext`).
- Charte `DESIGN.md` (palette Terra Insight).
- `created_by` renseigné sur les flux, détentions et groupes créés depuis la page.

## 4. Lecture : ce que montre la carte

### 4.1 Périmètre

Pour l'entreprise E et l'année A :
- **Blocs du périmètre** : E elle-même et les actifs détenus par E l'année A
  (`Asset.objects.owned_by(E, year=A)`).
- **Flux affichés** : tous les flux de l'année A dont l'origine ou la destination est
  un bloc du périmètre (`from_company`/`to_company` = E, ou `from_asset`/`to_asset`
  parmi les actifs détenus).
- **Blocs extérieurs** : l'autre extrémité de ces flux (pays, région, entreprise,
  actif non détenu).
- **Milieu** : un bandeau horizontal en haut, sur toute la largeur, extrémité de
  `*_environment`.
- **Inconnu** : un bloc fantôme en pointillés « Destination inconnue » à droite (production,
  déchet sans destination) et « Origine inconnue » à gauche (consommation d'origine
  inconnue), affichés seulement s'ils servent.

Sélecteur d'année : liste des années ayant des flux pour ce périmètre, **plus l'année
en cours, plus une saisie libre** (pour ouvrir une année encore vide et y saisir).
Par défaut : la plus récente année où le périmètre a des flux ; à défaut (entreprise
sans aucun flux), l'année en cours. *(Choix de conception.)*

### 4.2 Rangement automatique

- Colonnes de gauche (sources) à droite (aval). Un bloc est placé selon la plus
  longue chaîne de flux qui y mène (rang topologique). Les flux avec le milieu
  n'entrent pas dans ce calcul.
- Les cycles éventuels (A fournit B qui fournit A) sont cassés pour le calcul, sans
  masquer de flèche.
- Ordre vertical dans une colonne : à la discrétion du builder, en cherchant à limiter
  les croisements.
- Avec des centaines de blocs : **zoom et déplacement** (molette / glisser sur le fond).
- On peut déplacer un bloc à la main pendant la session ; rien n'est enregistré.

### 4.3 Dessin

- Blocs carrés : type en petites capitales (PAYS, RÉGION, ENTREPRISE, ACTIF), nom en
  dessous. Les actifs détenus se distinguent légèrement des blocs extérieurs.
- **Flèches en courbe lisse** (Bézier en S, bord droit de l'origine → bord gauche de la
  destination ; courbe verticale vers / depuis le bandeau milieu). Ni ondulation ni
  animation.
- Couleur par nature (`FlowKind`), légende au-dessus de la carte.
- Épaisseur proportionnelle à la quantité (échelle bornée, min et max lisibles ;
  les unités différant entre commodités, l'épaisseur est une indication relative,
  pas une mesure).
- **Une flèche par paire de blocs et par nature** : si plusieurs flux (commodités
  différentes) relient les deux mêmes blocs avec la même nature, une seule courbe,
  étiquetée « Soja +2 » (commodité de plus forte quantité + nombre d'autres).

### 4.4 Groupes d'actifs

- Un groupe apparaît comme un bloc « pile de cartes » avec son nom et son nombre
  d'actifs. **Replié par défaut** ; un clic le déplie (les actifs membres apparaissent
  à sa place, avec leurs propres flèches) et le replie.
- Replié, ses flux sont agrégés : les flux de ses membres vers un même bloc et de même
  nature forment une seule flèche (même règle que §4.3). Les flux entre deux membres
  du même groupe ne sont pas dessinés quand il est replié.
- Un groupe peut contenir des actifs détenus ou extérieurs (ex. les mines d'un
  fournisseur).
- Pour l'année A, un groupe n'est affiché que si au moins un de ses membres est sur la
  carte (détenu en A ou extrémité d'un flux affiché) ; il ne compte alors que ces
  membres-là. Replié, il est **un seul bloc** pour le rangement en colonnes, et il prend
  le style « périmètre » s'il contient au moins un actif détenu. *(Choix de conception.)*
- Sur une flèche d'un groupe replié, pas de bouton « + Ajouter un flux » ni de « + » sur
  le bloc : on déplie le groupe pour tracer un flux depuis un actif précis. Modifier et
  supprimer restent possibles ligne par ligne. *(Choix de conception.)*

## 5. Saisie

Toutes les actions d'écriture sont réservées au rôle **Créateur**
(`User.role == CREATOR`, comme `imports.decorators.creator_required`). La lecture est
ouverte comme les autres pages du dashboard ; pour un non-Créateur, les « + », boutons
d'ajout, de masquage et de suppression ne sont pas affichés (masquer reste permis : ce
n'est qu'une vue).

### 5.1 Ajouter un flux

1. Chaque bloc porte des petits « + » en bordure : **droite** = flux sortant,
   **gauche** = flux entrant, **haut** = flux avec le milieu (actifs, entreprises,
   groupes dépliés seulement — un groupe replié n'a pas de « + »).
2. Clic sur « + » droite/gauche, puis clic sur le bloc d'arrivée, le bloc
   « inconnu » ou le fond vide (= extrémité inconnue). Échap annule.
   Le « + » du haut ouvre directement la fiche avec le milieu pour l'autre extrémité.
3. Une fiche s'ouvre dans un **panneau latéral à droite** de la carte (maquette
   `fiche-flux.html`) :
   - **Nature** : seules les natures permises par `FLOW_RULES` pour ce couple
     d'extrémités sont proposées. Avec le milieu : Consommation (milieu → bloc),
     Émission ou Déchet (bloc → milieu) — le sens découle de la nature.
   - **Commodité** : recherche par mot-clé, ou création (§6.2). Unité de la commodité
     affichée en lecture seule.
   - **Quantité**, **Année** (pré-remplie avec l'année affichée).
   - Facultatif, replié : Tier, Scope GES (proposé pour Émission seulement), Source,
     Référence. Revenu estimé : non proposé (hors besoin exprimé).
4. Enregistrer → validation serveur → la carte se redessine. Erreurs affichées dans la
   fiche.

### 5.2 Consulter, modifier, supprimer un flux

**Clic sur une flèche → le panneau latéral droit s'ouvre directement sur le détail du
flux, déjà en formulaire modifiable** (mêmes champs que la fiche de création,
pré-remplis ; origine et destination affichées en tête, non modifiables). Boutons
**Enregistrer** et **Supprimer** (confirmation). Pas d'étape intermédiaire « voir puis
modifier ».

Si la flèche regroupe plusieurs flux (§4.3, §4.4) : le panneau affiche en haut un
sélecteur compact des flux qu'elle porte (commodité · quantité · unité ; actif membre
pour un groupe replié), le plus gros sélectionné par défaut, et en dessous le formulaire
modifiable du flux sélectionné. Cliquer un autre flux de la liste charge son formulaire.
En bas : « + Ajouter un flux entre ces deux blocs » (sauf groupe replié, §4.4).

La flèche cliquée reste en surbrillance tant que le panneau est ouvert ; fermer le
panneau (✕ ou Échap) annule les modifications non enregistrées.

### 5.3 Ajouter un bloc

Barre d'outils au-dessus de la carte : « + Pays », « + Région », « + Entreprise »,
« + Actif », « + Groupe d'actifs ». Chaque bouton ouvre une recherche par mot-clé côté
serveur (la base compte beaucoup d'éléments : pas de liste complète embarquée).

Un bloc ajouté sans flux n'existe que dans la session (il ne correspond à rien en base)
**sauf** :
- un **actif** ajouté avec la case « détenu par E » cochée (cochée par défaut, part
  100 % modifiable) : crée une `Ownership` (E, actif, part, `start_year` = année
  affichée, `end_year` vide). Case décochée : bloc extérieur, rien en base tant qu'aucun
  flux n'est tracé.
- un **groupe d'actifs** : enregistré dès sa création (§6.1).

### 5.4 Retirer un bloc

Menu du bloc (clic droit ou bouton « ⋯ ») :
- **Masquer** : disparaît de la vue avec ses flèches. Une pastille « N blocs masqués »
  permet de tout réafficher. Non enregistré.
- **Supprimer les liens** (Créateur) : supprime **les liens de ce bloc avec le
  périmètre affichés à l'écran**, jamais l'élément lui-même :
  - les flux de l'année affichée entre ce bloc et le périmètre ;
  - pour un actif détenu : sa détention par E à partir de l'année affichée. La
    détention valide l'année A prend fin en A − 1 (`end_year = A − 1`), ou est
    supprimée si elle commence en A. Les années antérieures restent intactes ; une
    éventuelle détention qui commence après A n'est pas touchée (elle n'est pas à
    l'écran). Les flux des autres années restent en base.
    *(Choix de conception, pas une demande explicite.)*
  - l'appartenance de l'actif à un groupe n'est pas modifiée.
  La fenêtre de confirmation précise aussi la conséquence pour un actif détenu :
  « … l'actif ne sera plus détenu par E à partir de A ».
  La fenêtre de confirmation « Êtes-vous sûr de vouloir supprimer… ? » **énumère** ce
  qui sera effacé (« 4 flux et 1 détention »). Les nombres viennent du serveur (le bloc
  affiché peut agréger des flux masqués par le regroupement).
- Le bloc de l'entreprise E ne peut être ni masqué ni supprimé.
- Pour un **groupe** : « Supprimer le groupe » supprime le groupe seulement (ses actifs
  et leurs flux restent) ; confirmation également.

### 5.5 Gérer un groupe

- Création : nom + choix d'actifs parmi ceux affichés sur la carte (cases à cocher dans
  le panneau, avec recherche). Un actif appartient à **un seul groupe par
  entreprise** ; un actif déjà groupé est signalé et ne peut pas être coché.
- Modification : renommer, ajouter / retirer des membres depuis le panneau du groupe.

## 6. Données

### 6.1 Nouveau modèle : groupe d'actifs

`AssetGroup` dans `dashboard/models.py` : `name`, `company` (FK `Company`, cascade),
membres (actifs), `created_at`, `updated_at`, `created_by`. Visible par tous les
utilisateurs pour cette entreprise. Contrainte « un actif dans au plus un groupe par
entreprise » garantie en base (ex. table d'appartenance portant `company` + unicité
`(company, asset)`) — forme exacte laissée au builder.
Supprimer un actif ou l'entreprise supprime les appartenances. Enregistré dans l'admin
de la console de données.

Aucune autre modification de schéma.

### 6.2 Création d'éléments depuis la page

| Élément    | Création possible | Champs demandés |
|------------|-------------------|-----------------|
| Actif      | oui | nom, pays (recherche), type (`Asset.type`), position : clic sur une mini-carte MapLibre ou saisie lat/long ; région facultative |
| Entreprise | oui | nom ; ISIN, ticker facultatifs |
| Commodité  | oui | nom, unité (défaut « tonnes ») |
| Pays       | **non** | choisir dans la base |
| Région     | **non** | choisir dans la base |

Pays et régions sont des tables de référence chargées par import (nombreux champs de
risque) : choisis seulement, jamais créés ici.

## 7. Architecture (indications)

- Page : vue `dashboard` (FBV) + gabarit `dashboard/flow_map.html` + JS
  `dashboard/static/dashboard/js/flow_map.js` (module découpé si besoin : rendu SVG,
  rangement, panneau). Lien dans le pied de la barre latérale, à côté de
  « Import / export Excel ».
- API JSON interne : données de la carte (blocs, flux, groupes, années) pour (E, A) ;
  recherche par mot-clé par type d'élément ; création / modification / suppression de
  flux, détention, groupe, actif, entreprise, commodité.
- Le calcul du périmètre et l'agrégation des flux sont dans `services/` (testables sans
  navigateur). Le rangement en colonnes peut être fait côté JS ou serveur (choix du
  builder) ; s'il est en Python, le tester.
- Réalisé : seul le périmètre est calculé côté serveur ; l'agrégation des flux (par paire
  et par nature, et pour les groupes repliés) est faite côté client dans
  `FlowMapDraw.aggregateEdges`, car elle dépend de l'état déplié / masqué du client ; elle
  est couverte par les vérifications manuelles.
- Découpage des modules, noms d'URL, format JSON exact : laissés au builder.

## 8. Laissé au builder

- Ordre vertical dans les colonnes, valeurs d'épaisseur, rendu exact des blocs.
- Interaction clavier : au minimum, le panneau et les fenêtres de confirmation sont
  utilisables au clavier ; tracé de flux au clavier non exigé.
- Message quand l'entreprise n'a aucun flux ni actif (carte vide + invitation à ajouter).

## 9. Tests attendus

- Modèle `AssetGroup` : création nominale, refus d'un actif dans deux groupes de la
  même entreprise.
- Service de périmètre : flux retenus / exclus (hors périmètre, autre année, actif non
  détenu cette année-là), agrégation par paire et nature, agrégation d'un groupe replié.
- Vues d'écriture : Créateur autorisé, Abonné et anonyme refusés ; flux refusé par
  `FLOW_RULES` → erreur lisible ; « supprimer les liens » n'efface que le périmètre
  annoncé et ne supprime jamais l'élément.
- Création d'actif avec détention.

## 10. Évolution : plage d'années et légende interactive (2026-10-22)

Demandée après la première livraison. **Remplace** le sélecteur d'année de §4.1, et
précise §4.1, §5.1–§5.4 là où ils parlent de « l'année A ».

### 10.1 Plage d'années

- Deux champs **« De »** et **« À »** remplacent le sélecteur d'année (années
  proposées : celles ayant des flux pour le périmètre, plus l'année en cours, plus
  saisie libre ; contrôle De ≤ À). Par défaut : de la plus ancienne à la plus récente
  année ayant des flux pour le périmètre ; à défaut, l'année en cours seule.
  *(Choix de conception.)*
- **Périmètre sur la plage [D, F]** : E et les actifs détenus par E **à un moment
  quelconque** de la plage (une détention valide au moins une année entre D et F).
  *(Choix de conception.)*
- **Flux retenus** : les flux d'une année entre D et F dont une extrémité est E ou un
  actif du périmètre **détenu cette année-là** (même règle qu'en §4.1, appliquée année
  par année).
- **« Même flux »** : même nature, même commodité, même origine, même destination et
  même scope. Quand un même flux existe pour plusieurs années de la plage, **seule la
  ligne de l'année la plus récente est affichée** ; les lignes plus anciennes restent
  en base et ne sont pas dessinées. Deux lignes de même clé **la même année** sont
  toutes deux affichées (pas de dédoublonnage intra-année). Tier, source, référence et
  quantité ne font pas partie de la clé. *(Définition : choix de conception.)*
- **Année visible** : chaque flux affiché porte son année, et le panneau l'affiche.
  L'étiquette de la flèche indique l'année quand **tous** ses flux ont la même année et
  qu'elle diffère de F (ex. « Soja · 2021 ») ; années mélangées → pas d'année sur
  l'étiquette, le détail est dans le panneau. *(Choix de conception.)*
- Les parts de détention ne sont ni affichées ni agrégées sur la plage : seule compte la
  présence d'une détention.
- La plage est mémorisée dans la session comme l'était l'année (pas en base).

### 10.2 Saisie dans une plage

- **Nouveau flux** : année pré-remplie avec F, modifiable.
- **Modifier un flux** : modifie la ligne affichée (la plus récente). Si l'année est
  changée vers une année déjà occupée par le même flux, la règle d'affichage s'applique
  simplement après rechargement (pas de fusion).
- **Ajouter un actif « détenu »** : la détention commence en F (champ année modifiable
  dans la fiche, pré-rempli à F).

### 10.3 Suppression : choix des années

- **Supprimer un flux** (panneau) : la confirmation **liste les années de la plage où
  ce même flux existe dans le périmètre** (années où il serait retenu par §10.1, même si
  une ligne plus récente le masque), chacune avec une case **cochée par défaut** ;
  l'utilisateur peut décocher des années. Seules les lignes des années cochées sont
  supprimées. Rien hors de la plage ni hors du périmètre n'est proposé ni supprimé.
  *(Liste limitée au périmètre : choix de conception, pour ne jamais effacer plus que
  ce que la carte représente.)*
- **Supprimer les liens d'un bloc** : même principe. La confirmation liste les années
  de la plage où des flux relient ce bloc au périmètre, avec le nombre de flux par
  année, toutes cochées par défaut ; on supprime les flux des années cochées.
- **Détention d'un actif détenu** (retrait de liens) : option **séparée** dans la même
  confirmation, « Mettre fin à la détention par E à partir de [année] », cochée par
  défaut, l'année pré-remplie avec la plus ancienne année cochée et modifiable parmi
  les années de la plage. Effet, pour l'année choisie Y : chaque détention de E sur cet
  actif valide en Y prend fin en Y − 1 (supprimée si elle commence en Y) ; une
  détention qui commence après Y et **avant ou pendant F** est supprimée ; celles qui
  commencent après F ne sont pas touchées. Décochée : la détention n'est pas modifiée.
  *(Choix de conception : découpler les années de flux et la fin de détention évite
  qu'une année décochée disparaisse de la carte sans avoir été demandée.)*
- Les copropriétaires éventuels restent mentionnés dans la confirmation.
- Aucune année cochée et option de détention décochée → bouton de confirmation
  désactivé.

### 10.4 Légende interactive

- Un clic sur une entrée de la légende (nature de flux) **masque ou réaffiche** toutes
  les flèches de cette nature ; l'entrée masquée est visiblement estompée et annoncée
  (`aria-pressed`). Activable au clavier. État de session seulement, comme le masquage
  des blocs. Les blocs qui n'ont plus aucune flèche visible restent affichés.
  *(Dernier point : choix de conception.)*

### 10.5 Tests attendus en plus

- Périmètre sur une plage : actif détenu une partie de la plage inclus ; flux d'une année
  où l'actif n'était pas détenu exclu.
- « Même flux » : deux années → seule la plus récente renvoyée ; scopes différents →
  deux flux.
- Suppression par années : seules les années cochées sont effacées, rien hors plage ;
  retrait de liens avec l'option de détention (fin en Y − 1, détention démarrant entre
  Y et F supprimée, détention après F intacte) et sans elle (détention inchangée).
