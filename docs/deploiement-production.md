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

Variables à déclarer dans **Setup Python App → Environment variables** (ou dans
un `.env` prod — pas les deux, pour éviter toute ambiguïté sur la valeur qui
l'emporte) :

```
SECRET_KEY=<clé secrète de prod>
DEBUG=False
ALLOWED_HOSTS=votre-domaine.com
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

Le déploiement est piloté par `.cpanel.yml` (`migrate`, `collectstatic
--noinput`, puis `touch tmp/restart.txt`) : les statiques sont donc recollectées
à chaque déploiement, y compris `dashboard/css/admin-easybiodiv.css`, le fichier
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

Après transfert du code, `migrate` tourne automatiquement via `.cpanel.yml`.
Sauvegarder la base avant toute migration destructive : sur SQLite il n'y a pas
de restauration à un point dans le temps, seulement la dernière copie du cron.

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
