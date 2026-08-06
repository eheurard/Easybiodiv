# Déploiement PostgreSQL — production o2switch (cPanel)

Deux bases **séparées** : dev local et prod. Config identique pilotée par
l'environnement (`easybiodiv/db.py`) ; seules les valeurs du `.env` diffèrent.
Si `DB_NAME` est vide, l'application retombe automatiquement sur SQLite.

## 1. Créer la base PostgreSQL dans cPanel

1. cPanel → **Bases de données PostgreSQL**.
2. Créer une **base** (cPanel préfixe : `cpaneluser_easybiodiv`).
3. Créer un **utilisateur** + mot de passe (préfixe : `cpaneluser_ebd`).
4. **Associer** l'utilisateur à la base avec **TOUS LES PRIVILÈGES**.

> Note : sur l'hébergement mutualisé, l'utilisateur n'a pas le droit
> `CREATE DATABASE`. Ce n'est pas un problème : on ne lance pas les tests en
> prod, et le schéma est créé par `migrate` dans la base existante.

## 2. Renseigner le `.env` de production

Dans le `.env` du site en prod (jamais commité) :

```
SECRET_KEY=<clé secrète de prod>
DEBUG=False
ALLOWED_HOSTS=votre-domaine.com
DB_NAME=cpaneluser_easybiodiv
DB_USER=cpaneluser_ebd
DB_PASSWORD=<mot de passe cPanel>
DB_HOST=localhost
DB_PORT=5432
```

`DB_HOST=localhost` : en prod, Django et PostgreSQL tournent sur le même
serveur o2switch. **Aucun accès distant n'est nécessaire.**

## 3. Déployer le code et charger les données (une fois)

Le fichier `dump.json` est produit **sur le poste de dev** depuis la base SQLite
d'origine (voir `docs/superpowers/plans/2026-07-27-migration-postgresql.md`,
Task 2). Sous Windows, il faut forcer l'UTF-8 pour éviter une erreur `charmap` :

```powershell
$env:PYTHONUTF8=1
python manage.py dumpdata --exclude contenttypes --exclude auth.permission --indent 2 -o dump.json
```

Transférer le code à jour **et** `dump.json` sur le serveur (gestionnaire de
fichiers cPanel ou Git).

Via **Terminal cPanel** (ou la console « Setup Python App », après activation de
l'environnement virtuel de l'application) :

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py loaddata dump.json
python manage.py collectstatic --noinput
```

`loaddata` réinitialise les séquences PostgreSQL : la première création d'objet
après import n'entrera pas en collision de clé.

Puis **supprimer `dump.json`** du serveur. Redémarrer l'application
(Setup Python App → Restart, ou toucher `tmp/restart.txt` pour Passenger).

## 4. Migrations futures

À chaque déploiement modifiant les modèles : après transfert du code, dans le
Terminal cPanel de l'application : `python manage.py migrate` puis redémarrer
l'application.

## 5. Développement local (rappel)

En local, `.env` pointe sur une base PostgreSQL **locale** (jamais la prod) :

```
DB_NAME=easybiodiv_dev
DB_USER=easybiodiv_dev
DB_PASSWORD=<mot de passe local>
DB_HOST=localhost
DB_PORT=5432
```

Les tests créent automatiquement une base `test_easybiodiv_dev` (l'utilisateur
local possède le droit `CREATEDB`). Pour revenir ponctuellement sur SQLite
(dépannage), vider `DB_NAME` dans le `.env`.

## 6. Anticipation PostGIS (cartes — hors périmètre actuel)

Avant d'investir dans les cartes, **vérifier auprès du support o2switch** :

- l'extension **PostGIS** est-elle disponible (`CREATE EXTENSION postgis;`) ?
- les bibliothèques **GDAL / GEOS / PROJ** sont-elles présentes et accessibles
  au process Python ?

Si oui, l'activation consistera à : `CREATE EXTENSION postgis;`, passer `ENGINE`
sur `django.contrib.gis.db.backends.postgis`, ajouter `django.contrib.gis` à
`INSTALLED_APPS`, installer GDAL en dev (OSGeo4W), et ajouter les champs `geom`
via une migration dédiée. Si non, les cartes nécessiteront un VPS.
