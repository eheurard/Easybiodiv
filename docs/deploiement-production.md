# Déploiement en production — o2switch (cPanel)

La production tourne sur **SQLite**. Ce n'est pas un provisoire subi : c'est le
résultat d'un blocage vérifié côté hébergeur, décrit ci-dessous.

## 1. Pourquoi pas PostgreSQL

o2switch fournit **PostgreSQL 9.6.22**, en fin de vie depuis novembre 2021.
Django 6.0 exige **PostgreSQL 14 minimum** (`django/db/backends/postgresql/features.py`,
`minimum_database_version = (14,)`) et refuse la connexion avant toute requête :

```
django.db.utils.NotSupportedError: PostgreSQL 14 or later is required (found 9.622).
```

Aucun contournement par configuration. Les alternatives évaluées et écartées :

| Piste | Écartée parce que |
|---|---|
| MariaDB/MySQL o2switch | Migration réelle du backend, sans bénéfice sur le MVP |
| PostgreSQL managé externe (Supabase, Neon…) | Latence réseau par requête, dépendance à un tiers, coût du plan non-gratuit |
| Rétrograder Django à 3.2 | EOL avril 2024 — inacceptable en sécurité |

## 2. Configuration

**Ne pas définir `DB_NAME`.** `easybiodiv/db.py` retombe alors sur SQLite. Si la
variable est renseignée, l'application tente PostgreSQL et renvoie une 500 sur
chaque requête.

Variables à déclarer dans un **`.env` à la racine du dépôt** (ou dans
**Setup Python App → Environment variables** — pas les deux, pour éviter toute
ambiguïté sur la valeur qui l'emporte). Préférer le `.env` : c'est le seul que
voient aussi les tâches cron (§10).

```
SECRET_KEY=<clé secrète de prod>
DEBUG=False
ALLOWED_HOSTS=votre-domaine.com
# Emails de réinitialisation de mot de passe (§10)
EMAIL_HOST=<serveur>.o2switch.net
EMAIL_PORT=465
EMAIL_HOST_USER=contact@votre-domaine.com
EMAIL_HOST_PASSWORD=<mot de passe de la boîte>
```

Les connexions SQLite sont réglées pour l'accès multi-processus dans
`easybiodiv/db.py` (WAL, `transaction_mode=IMMEDIATE`, timeout 20 s). Passenger
lance plusieurs processus sur le même fichier ; sans ce réglage, les écritures
concurrentes produisent des `database is locked`.

## 3. Le fichier de base

Chemin : `~/repositories/Easybiodiv/db.sqlite3` (racine du dépôt).

- Il est dans `.gitignore` : **il survit aux déploiements**, git n'y touche pas.
- Corollaire : il ne survit **pas** à une suppression / re-clone du dépôt.
  Sauvegarder avant toute manipulation de ce type.
- Il doit rester hors de `public_html`. C'est le cas par défaut avec
  `repositories/` ; à revérifier si l'arborescence change, un fichier SQLite
  servi en HTTP expose toute la base.

Le mode WAL crée deux fichiers voisins (`db.sqlite3-wal`, `db.sqlite3-shm`).
Normal, ne pas les supprimer à chaud.

## 4. Sauvegardes

SQLite n'a aucune sauvegarde managée : c'est le principal renoncement de ce
choix, et il se compense par un cron. cPanel → **Tâches Cron**, quotidien :

```
0 3 * * * /usr/bin/sqlite3 /home/heel8455/repositories/Easybiodiv/db.sqlite3 ".backup '/home/heel8455/backups/easybiodiv-$(date +\%F).sqlite3'"
```

`.backup` produit une copie cohérente **base en cours d'utilisation**, contrairement
à un `cp` qui peut capturer un état intermédiaire. Le `%` doit être échappé en
`\%` dans une crontab.

Créer `~/backups` au préalable, et purger périodiquement — rien ne le fait
automatiquement.

## 5. Déployer

Le déploiement est piloté par `.cpanel.yml` (`backup_sqlite`, `migrate`,
`collectstatic --noinput`, puis `touch tmp/restart.txt`) : les statiques sont
donc recollectées à chaque déploiement, y compris
`dashboard/css/admin-easybiodiv.css`, le fichier
propre à la console de données, en supplément de ceux de
`django.contrib.admin`. Dans cPanel : **Git Version Control → Update from
Remote**.

Si cPanel affiche *« The system cannot deploy »*, le blocage est presque toujours
la seconde condition, pas le `.cpanel.yml`. Dans le Terminal cPanel :

```bash
cd ~/repositories/Easybiodiv
git status --porcelain     # chaque ligne retournée bloque le déploiement
```

- lignes ` M` → fichiers modifiés sur le serveur ; inspecter avec `git diff`,
  puis `git checkout -- <fichier>` si la modification n'a pas à être conservée
  (destructif, vérifier le diff d'abord) ;
- diff ne montrant que des `old mode 100644 / new mode 100755` → permissions
  altérées par un upload FTP : `git config core.fileMode false` ;
- lignes `??` → fichiers non suivis à supprimer ou à ajouter au `.gitignore`.

## 6. Migrations futures

Après transfert du code, `.cpanel.yml` chaîne `python manage.py backup_sqlite`
et `migrate --noinput` sur une seule ligne (`&&`) : `backup_sqlite` écrit une
copie cohérente de la base dans `db.sqlite3.pre-deploy` (API `backup` de
SQLite, sûre en mode WAL), et comme les deux commandes sont chaînées, un échec
de la sauvegarde empêche la migration de s'exécuter sur une base non protégée.
Ce fichier est écrasé à chaque déploiement : il ne protège que le dernier. Il
est ignoré par git (`*.sqlite3.pre-deploy`), il ne bloque donc pas les
déploiements suivants.

Retour arrière après une migration ratée : revenir au commit précédent, arrêter
l'application, remplacer `db.sqlite3` par `db.sqlite3.pre-deploy` et supprimer
`db.sqlite3-wal` et `db.sqlite3-shm`, puis redémarrer (`touch tmp/restart.txt`).

### Refonte de la table Flow (septembre 2026)

Le déploiement de `feat/table-flow` supprime, sans les recopier, les données de
`Production`, `AssetInventory`, `SupplyNode`, `Exchange`, `Carbon_emission` et
`Ownership` (spec `docs/superpowers/specs/2026-09-18-table-flow-unique-design.md`,
décision 2).

**Avant le déploiement**

- Vérifier qu'aucune commodité de prod ne porte déjà un des noms créés par la
  migration 0050 (`Eau`, `Énergie`, `CO₂`, `Déchets`, `Surface occupée`) : cette
  migration crée (ou met à jour) ces commodités par `key`, pas par `name`, donc
  un doublon de nom existant en base passerait inaperçu. Terminal cPanel, en
  lecture seule :
  ```bash
  sqlite3 ~/repositories/Easybiodiv/db.sqlite3 "SELECT name FROM dashboard_commodity WHERE name IN ('Eau', 'Énergie', 'CO₂', 'Déchets', 'Surface occupée');"
  ```
  Une ligne retournée : renommer ou fusionner la commodité en base avant de
  déployer.
- Préparer à l'avance le classeur Excel `Ownership` / `Flow` à réimporter
  (étape 3 ci-dessous), pour raccourcir la période de pages vides.

**Déploiement**

1. Déployer à un moment calme : Git Version Control → Update from Remote.
2. Vérifier dans le journal de déploiement la ligne `Sauvegarde écrite :`
   (`.cpanel.yml` chaîne désormais `backup_sqlite && migrate --noinput` : un
   échec de sauvegarde bloque la migration, voir §6).
3. Télécharger le nouveau modèle Excel depuis `/imports/`, remplir les feuilles
   `Ownership` et `Flow` (et `Commodity` si besoin), puis importer.

Entre les étapes 1 et 3, les pages affichent des entreprises sans production ni
émission.

**Juste après le déploiement**

Copier `db.sqlite3.pre-deploy` sous un nom durable ignoré par git,
`db-pre-flow.sqlite3` (le motif `*.sqlite3` du `.gitignore` le couvre), et le
télécharger en local : c'est la seule copie complète des anciennes données
(`Production`, `AssetInventory`, `SupplyNode`, `Exchange`, `Carbon_emission`,
`Ownership`). `db.sqlite3.pre-deploy` est écrasé dès le déploiement suivant.

**Retour arrière**

Copier `db.sqlite3.pre-deploy` de côté **avant** tout nouvel « Update from
Remote », puisque chaque déploiement l'écrase. Procédure complète de retour
arrière : §6 ci-dessus.

## 7. Développement local

Identique à la prod : `.env` sans `DB_NAME`, base `db.sqlite3` locale. Les tests
utilisent une base en mémoire.

## 8. Quand reconsidérer ce choix

SQLite convient tant que les écritures restent peu concurrentes — ce qui est le
profil d'un dashboard de reporting. Les signaux qui justifieraient une migration :

- des `database is locked` en journal malgré le WAL ;
- plusieurs utilisateurs saisissant simultanément des données de manière
  régulière ;
- un volume rendant les sauvegardes par copie de fichier impraticables.

À ce moment-là, la cible réaliste est un **PostgreSQL managé externe**, pas celui
d'o2switch. `easybiodiv/db.py` est déjà prêt : renseigner `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `DB_HOST`, `DB_PORT` suffit à basculer. Prévoir d'ajouter le SSL
(`OPTIONS: {'sslmode': 'require'}`) et `CONN_MAX_AGE`, indispensables dès que la
base n'est plus sur `localhost`.

## 9. Cartographie / PostGIS — bloqué

Hors de portée sur cet hébergement, et **le problème n'est pas la base** :
`django.contrib.gis` exige les bibliothèques natives **GEOS et GDAL** installées
sur le serveur qui exécute Python, donc sur o2switch. Passer à un PostgreSQL
externe avec PostGIS ne lèverait que la moitié du blocage.

À vérifier auprès du support o2switch avant tout investissement dans les cartes :
GEOS et GDAL sont-ils présents et accessibles au process Python ? Si non, les
cartes nécessiteront un VPS.

## 10. Conformité légale (France)

L'app `legal` publie les pages exigées pour un site édité en France :
`/mentions-legales/` (LCEN, art. 6-III), `/confidentialite/` (RGPD, art. 13),
`/cookies/` et `/cgu/`. Un pied de page y renvoie depuis chaque page, et
l'inscription exige l'acceptation des CGU (horodatée dans
`User.terms_accepted_at`).

**Éditeur.** Le dictionnaire `LEGAL` de `easybiodiv/settings.py` déclare un
éditeur particulier (`editor_professional: False`) : la LCEN (art. 6-III-2) le
dispense de publier adresse et téléphone, déjà communiqués à o2switch. Seuls le
nom et l'adresse de contact sont exigés (identité du responsable du traitement,
RGPD art. 13). L'adresse de contact n'est pas versionnée : elle se lit dans
`CONTACT_EMAIL`, à défaut `EMAIL_HOST_USER` (la boîte dédiée ci-dessous). Tant
qu'un champ obligatoire est vide, les pages affichent « [à compléter] » et
`migrate` imprime l'avertissement `legal.W001` dans le journal de déploiement.
En cas d'activité professionnelle : passer `editor_professional` à `True` et
renseigner adresse, téléphone et immatriculation. Les coordonnées d'o2switch y
sont déjà, vérifiées au registre SIRENE le 2026-10-23.

**Cookies.** Le site ne dépose que des cookies exemptés de consentement
(session, CSRF, langue) : le bandeau affiché est une simple information, pas un
recueil de consentement. Ajouter un outil de mesure d'audience non exempté
(Google Analytics…), une vidéo intégrée ou tout autre traceur tiers impose de
le remplacer par un vrai bandeau Accepter / Refuser, et de mettre à jour
`legal/templates/legal/*/cookies.html`. Même logique pour toute nouvelle
ressource tierce (CDN, police, tuiles) : la déclarer dans la politique de
confidentialité. La police Inter est auto-hébergée pour cette raison.

**Durée de conservation.** La politique de confidentialité annonce la
suppression des comptes abonnés sans connexion depuis 3 ans. La tâche cron
mensuelle est installée par le déploiement lui-même : la dernière étape de
`.cpanel.yml` lance `deploy/install_cron.sh`, qui ajoute (ou remplace, s'il
existe déjà) dans la crontab cette ligne repérée par son marqueur, sans toucher
aux autres tâches :

```
0 4 1 * * cd /home/heel8455/repositories/Easybiodiv && $VENV/python manage.py purge_inactive_accounts >> ~/logs/easybiodiv-purge.log 2>&1 # easybiodiv:purge_inactive_accounts
```

Elle est visible dans cPanel → Tâches Cron ; le journal est dans
`~/logs/easybiodiv-purge.log`. Une tâche cron ne voit pas les variables de
*Setup Python App* : elle exige un `.env` à la racine du dépôt contenant au
moins `SECRET_KEY` (le script avertit dans le journal de déploiement s'il
manque). Pour l'essayer sans rien supprimer, dans le Terminal cPanel :
`python manage.py purge_inactive_accounts --dry-run`.

**Courriels.** La réinitialisation de mot de passe passe par le SMTP d'o2switch
dès que `EMAIL_HOST` est défini (`easybiodiv/mail.py`) ; sinon les emails
partent dans la console, et `migrate` l'avertit (`authentication.W001`).

1. cPanel → **Comptes de messagerie** → créer une boîte dédiée, par exemple
   `contact@votre-domaine` : elle expédie les emails et sert d'adresse de
   contact publique (mentions légales, droits RGPD).
2. Sur cette boîte, **Connect Devices** donne le serveur sortant (de la forme
   `xxx.o2switch.net`) et le port SMTP (465 en SSL).
3. Déclarer `EMAIL_HOST`, `EMAIL_PORT=465`, `EMAIL_HOST_USER` (l'adresse
   complète) et `EMAIL_HOST_PASSWORD`, au même endroit que `SECRET_KEY`.
4. Redémarrer l'application, puis tester « Mot de passe oublié » avec un
   compte existant.

L'expéditeur est la boîte authentifiée (`Easybiodiv <EMAIL_HOST_USER>`) :
o2switch refuse ou classe en spam un expéditeur qui ne lui appartient pas.
Un échec d'envoi n'interrompt pas la page (Django l'intercepte) mais est
journalisé par le logger `django.contrib.auth`, visible dans le journal
d'erreurs de l'application.

**Modifier un texte.** Chaque page existe en `legal/templates/legal/fr/` et
`legal/templates/legal/en/` (la version française fait foi) ; mettre à jour les
deux, puis `TEXTS_UPDATED` dans `legal/views.py`.
