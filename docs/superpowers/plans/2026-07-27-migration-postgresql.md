# Migration PostgreSQL (dev + prod) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire passer Easybiodiv de SQLite à PostgreSQL en dev local ET en production (o2switch/cPanel), avec deux bases séparées et une configuration identique pilotée par l'environnement.

**Architecture:** Le choix du moteur de base se fait dans un petit module pur `easybiodiv/db.py` (testable sans charger les settings), consommé par `settings.py`. Si `DB_NAME` est présent dans l'environnement → PostgreSQL, sinon repli SQLite. Les données existantes sont transférées via `dumpdata`/`loaddata`. PostGIS est préparé (Postgres = socle) mais volontairement pas activé.

**Tech Stack:** Django 6.0.5, `psycopg[binary]` (psycopg 3), PostgreSQL, `python-dotenv`.

## Global Constraints

- Python **3.11+**, Django **6.0.5** (version en place — ne pas changer).
- PEP 8, lignes **≤ 100 caractères**.
- **Le code doit fonctionner identiquement en SQLite et PostgreSQL** (CLAUDE.md §2).
- **PostGIS / GeoDjango non activé** dans ce plan (différé au jour des cartes).
- Secrets et config base **uniquement via l'environnement / `.env`** (jamais en clair, jamais commité).
- **Ne pas modifier** la logique de durcissement prod de `settings.py` au-delà du bloc `DATABASES`.
- Runner de tests : **`python manage.py test`** (pytest n'est PAS installé).
- Environnement virtuel : `.venv\Scripts\Activate.ps1` (PowerShell, Windows).
- Ne pas supprimer de migrations historiques ; ne pas commiter `db.sqlite3`, `.env`, `dump.json`.

---

### Task 1: Configuration `DATABASES` pilotée par l'environnement + driver

Introduit le driver PostgreSQL et bascule `DATABASES` sur une config lue depuis l'environnement, via un module pur testable. À l'issue de cette tâche, **rien ne change en pratique** : sans `DB_NAME` dans le `.env`, l'app reste sur SQLite et la suite de tests reste verte.

**Files:**
- Create: `easybiodiv/db.py`
- Create: `easybiodiv/test_db.py`
- Modify: `easybiodiv/settings.py` (bloc `DATABASES`, lignes 94-99 ; ajout d'un import)
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `easybiodiv/db.py::database_config(env, base_dir) -> dict`
  - `env` : mapping type `os.environ` (`Mapping[str, str]`).
  - `base_dir` : `pathlib.Path` (racine projet).
  - Retourne le dict de configuration de la connexion `'default'` (les clés `ENGINE`, `NAME`, et pour Postgres `USER`/`PASSWORD`/`HOST`/`PORT`).

- [ ] **Step 1: Write the failing test**

Créer `easybiodiv/test_db.py` :

```python
from pathlib import Path

from django.test import SimpleTestCase

from easybiodiv.db import database_config


class DatabaseConfigTests(SimpleTestCase):
    def test_postgres_when_db_name_set(self):
        env = {'DB_NAME': 'mydb', 'DB_USER': 'u', 'DB_PASSWORD': 'p'}
        cfg = database_config(env, Path('/base'))
        self.assertEqual(cfg['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(cfg['NAME'], 'mydb')
        self.assertEqual(cfg['USER'], 'u')
        self.assertEqual(cfg['PASSWORD'], 'p')
        self.assertEqual(cfg['HOST'], 'localhost')  # défaut
        self.assertEqual(cfg['PORT'], '5432')       # défaut

    def test_postgres_respects_explicit_host_port(self):
        env = {'DB_NAME': 'd', 'DB_USER': 'u', 'DB_PASSWORD': 'p',
               'DB_HOST': 'db.example', 'DB_PORT': '6543'}
        cfg = database_config(env, Path('/base'))
        self.assertEqual(cfg['HOST'], 'db.example')
        self.assertEqual(cfg['PORT'], '6543')

    def test_sqlite_fallback_when_no_db_name(self):
        cfg = database_config({}, Path('/base'))
        self.assertEqual(cfg['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(cfg['NAME'], Path('/base') / 'db.sqlite3')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test easybiodiv.test_db`
Expected: FAIL — `ModuleNotFoundError: No module named 'easybiodiv.db'`

- [ ] **Step 3: Write minimal implementation**

Créer `easybiodiv/db.py` :

```python
"""Construction de la configuration DATABASES depuis l'environnement.

Isolé de settings.py pour rester testable sans importer les settings
(qui exigent SECRET_KEY hors DEBUG). PostgreSQL si DB_NAME est défini,
sinon repli SQLite.
"""


def database_config(env, base_dir):
    """Retourne le dict de config de la connexion 'default'.

    `env` : mapping type os.environ. `base_dir` : Path racine projet.
    """
    if env.get('DB_NAME'):
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env['DB_NAME'],
            'USER': env['DB_USER'],
            'PASSWORD': env['DB_PASSWORD'],
            'HOST': env.get('DB_HOST', 'localhost'),
            'PORT': env.get('DB_PORT', '5432'),
        }
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': base_dir / 'db.sqlite3',
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test easybiodiv.test_db`
Expected: PASS (3 tests OK)

- [ ] **Step 5: Brancher le module dans `settings.py`**

Dans `easybiodiv/settings.py`, ajouter l'import près des autres imports locaux (après la ligne 16 `from dotenv import load_dotenv`) :

```python
from easybiodiv.db import database_config
```

Puis remplacer le bloc `DATABASES` (lignes 94-99) par :

```python
# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
# PostgreSQL si DB_NAME est défini dans l'environnement, sinon repli SQLite.
# Le jour des cartes (PostGIS), basculer ENGINE sur
# 'django.contrib.gis.db.backends.postgis' (nécessite GDAL/GEOS + CREATE
# EXTENSION postgis) — voir docs/deploiement-postgresql.md.
DATABASES = {'default': database_config(os.environ, BASE_DIR)}
```

- [ ] **Step 6: Ajouter le driver à `requirements.txt`**

Installer puis capturer la version résolue (ne pas deviner le numéro exact) :

```powershell
.\.venv\Scripts\Activate.ps1
pip install "psycopg[binary]"
pip freeze | Select-String -Pattern '^psycopg'
```

Ajouter la (ou les) ligne(s) `psycopg...` retournée(s) par `pip freeze` dans `requirements.txt`, en respectant l'ordre alphabétique existant (ex. `psycopg[binary]==3.2.x`).

- [ ] **Step 7: Documenter les variables dans `.env.example`**

Ajouter à la fin de `.env.example` :

```
# Base de données PostgreSQL — laisser DB_NAME vide pour retomber sur SQLite (dev/CI).
# DB_HOST=localhost côté prod o2switch (Postgres local au serveur) et en dev local.
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432
```

- [ ] **Step 8: Ignorer `dump.json` dans `.gitignore`**

Ajouter sous la section `# Django` de `.gitignore` :

```
# Dump de migration de données (temporaire, jamais commité)
dump.json
```

- [ ] **Step 9: Vérifier la non-régression sur SQLite**

Le `.env` local n'a PAS encore `DB_NAME` renseigné → l'app doit rester sur SQLite.

Run: `python manage.py check`
Expected: `System check identified no issues`

Run: `python manage.py test`
Expected: toute la suite verte (≈259 tests), aucun échec — on tourne encore sur SQLite.

- [ ] **Step 10: Commit**

```powershell
git add easybiodiv/db.py easybiodiv/test_db.py easybiodiv/settings.py requirements.txt .env.example .gitignore
git commit -m "feat(db): config DATABASES pilotee par l'environnement + driver psycopg"
```

---

### Task 2: Exporter les données SQLite existantes

Produit le fichier `dump.json` à partir de la base SQLite actuelle. **À faire tant que l'app tourne encore sur SQLite** (avant de renseigner `DB_NAME`).

**Files:**
- Create (temporaire, non commité) : `dump.json`

**Interfaces:**
- Produces: fichier `dump.json` (fixtures Django, encodage UTF-8) à la racine du projet, consommé par la Task 3 (dev) et par la doc de la Task 4 (prod).

- [ ] **Step 1: Vérifier qu'on est bien sur SQLite**

Confirmer que le `.env` local ne définit PAS `DB_NAME` (sinon le dump lirait Postgres, encore vide).

Run: `python manage.py shell -c "from django.db import connection; print(connection.vendor)"`
Expected: `sqlite`

- [ ] **Step 2: Générer le dump**

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py dumpdata --exclude contenttypes --exclude auth.permission --indent 2 -o dump.json
```

Notes :
- `-o dump.json` : écriture directe par Django (évite l'encodage UTF-16 d'une redirection PowerShell).
- `--exclude contenttypes --exclude auth.permission` : ces tables sont recréées par `migrate` ; les exclure évite les collisions de clés au `loaddata`.

- [ ] **Step 3: Vérifier le dump**

Run: `python manage.py shell -c "import json; d=json.load(open('dump.json', encoding='utf-8')); print(len(d), 'objets'); print(sorted({o['model'] for o in d}))"`
Expected: un nombre d'objets > 0 et la liste des modèles métier (dont `authentication.user`, modèles `dashboard.*`, `imports.*`). Vérifier qu'aucune ligne `contenttypes.contenttype` ni `auth.permission` n'apparaît.

- [ ] **Step 4: (pas de commit)**

`dump.json` est ignoré par git (Task 1, Step 8) et ne doit pas être commité. Aucune action git ici.

---

### Task 3: Mise en service de PostgreSQL en dev local

Installe PostgreSQL en local, crée la base + l'utilisateur de dev, bascule `.env` sur Postgres, applique le schéma, charge les données, et valide la suite complète **sur Postgres**. C'est la vérification d'intégration principale du plan.

**Files:**
- Modify (local, non commité) : `.env`

**Interfaces:**
- Consumes: `dump.json` (Task 2), `database_config` (Task 1).

- [ ] **Step 1: Installer PostgreSQL (Windows)**

Installer PostgreSQL via l'installeur EnterpriseDB (https://www.postgresql.org/download/windows/). Noter le mot de passe du superutilisateur `postgres` défini à l'installation. Vérifier :

Run: `psql --version`
Expected: `psql (PostgreSQL) 1x.x`
(Si `psql` est introuvable, ajouter `C:\Program Files\PostgreSQL\<version>\bin` au PATH.)

- [ ] **Step 2: Créer la base et l'utilisateur de dev**

Dans un shell `psql` connecté en superutilisateur (`psql -U postgres`) :

```sql
CREATE USER easybiodiv_dev WITH PASSWORD 'un_mot_de_passe_local';
CREATE DATABASE easybiodiv_dev OWNER easybiodiv_dev;
```

Le propriétaire d'une base possède implicitement le droit `CREATE DATABASE` requis par Django pour créer la base de test `test_easybiodiv_dev`. Si les tests échouaient sur la création de base, exécuter : `ALTER USER easybiodiv_dev CREATEDB;`

- [ ] **Step 3: Renseigner le `.env` local**

Ajouter/renseigner dans `.env` :

```
DB_NAME=easybiodiv_dev
DB_USER=easybiodiv_dev
DB_PASSWORD=un_mot_de_passe_local
DB_HOST=localhost
DB_PORT=5432
```

- [ ] **Step 4: Vérifier la connexion et le moteur**

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py check
python manage.py shell -c "from django.db import connection; print(connection.vendor)"
```
Expected: `check` sans erreur, puis `postgresql`.

- [ ] **Step 5: Appliquer le schéma**

Run: `python manage.py migrate`
Expected: toutes les migrations `... OK` sans erreur.

- [ ] **Step 6: Charger les données**

Run: `python manage.py loaddata dump.json`
Expected: `Installed N object(s) from 1 fixture(s)` sans erreur d'intégrité.

- [ ] **Step 7: Vérifier les données chargées**

Run: `python manage.py shell -c "from django.contrib.auth import get_user_model as g; from dashboard.models import Company; print('users', g().objects.count(), 'companies', Company.objects.count())"`
Expected: des comptes cohérents avec l'ancienne base SQLite (non nuls si des données existaient).

- [ ] **Step 8: Lancer la suite complète sur Postgres**

Run: `python manage.py test`
Expected: toute la suite verte (≈259 tests) sur Postgres. Si un test échoue à cause d'un comportement spécifique SQLite, le corriger (cf. systematic-debugging) — l'objectif est la parité.

- [ ] **Step 9: Smoke test manuel du serveur**

```powershell
python manage.py runserver
```
Ouvrir l'app, se connecter, vérifier qu'une page du dashboard affiche les données. Arrêter le serveur (Ctrl+C).

- [ ] **Step 10: (pas de commit)**

Aucun fichier versionné n'a changé (`.env` et `dump.json` sont ignorés). Rien à committer.

---

### Task 4: Documentation de déploiement production (o2switch/cPanel)

Rédige la procédure de mise en production sur o2switch (création base cPanel, déploiement, chargement des données, migrations futures) et la note d'anticipation PostGIS. Livrable = document ; l'exécution sur o2switch reste à la main de l'utilisateur.

**Files:**
- Create: `docs/deploiement-postgresql.md`

**Interfaces:**
- Consumes: `dump.json` (Task 2), `requirements.txt` (Task 1).

- [ ] **Step 1: Écrire la documentation**

Créer `docs/deploiement-postgresql.md` avec le contenu suivant :

````markdown
# Déploiement PostgreSQL — production o2switch (cPanel)

Deux bases **séparées** : dev local et prod. Config identique pilotée par
l'environnement (`easybiodiv/db.py`) ; seules les valeurs du `.env` diffèrent.

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
serveur o2switch. Aucun accès distant n'est nécessaire.

## 3. Déployer le code et charger les données (une fois)

Transférer le code à jour **et** le fichier `dump.json` (issu du dump SQLite,
voir le plan de migration) sur le serveur.

Via **Terminal cPanel** (ou la console « Setup Python App », après activation
de l'environnement virtuel de l'app) :

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py loaddata dump.json
python manage.py collectstatic --noinput
```

Puis **supprimer `dump.json`** du serveur. Redémarrer l'application
(Setup Python App → Restart, ou toucher `tmp/restart.txt` pour Passenger).

## 4. Migrations futures

À chaque déploiement modifiant les modèles : après transfert du code, dans le
Terminal cPanel de l'app : `python manage.py migrate` puis redémarrer l'app.

## 5. Anticipation PostGIS (cartes — hors périmètre actuel)

Avant d'investir dans les cartes, **vérifier auprès du support o2switch** :

- l'extension **PostGIS** est-elle disponible (`CREATE EXTENSION postgis;`) ?
- les bibliothèques **GDAL / GEOS / PROJ** sont-elles présentes et accessibles
  au process Python ?

Si oui, l'activation consistera à : `CREATE EXTENSION postgis;`, passer
`ENGINE` sur `django.contrib.gis.db.backends.postgis`, ajouter
`django.contrib.gis` à `INSTALLED_APPS`, installer GDAL en dev (OSGeo4W), et
ajouter les champs `geom` via une migration dédiée. Si non, les cartes
nécessiteront un VPS.
````

- [ ] **Step 2: Vérifier la cohérence de la doc**

Relire : les noms de variables (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`) correspondent exactement à ceux lus par `easybiodiv/db.py` (Task 1). Les commandes `migrate`/`loaddata` correspondent à celles validées en dev (Task 3).

- [ ] **Step 3: Commit**

```powershell
git add docs/deploiement-postgresql.md
git commit -m "docs: procedure de deploiement PostgreSQL sur o2switch"
```

---

## Notes d'exécution

- **Ordre impératif** : Task 1 → Task 2 (dump encore sur SQLite) → Task 3 (bascule Postgres) → Task 4.
- Après la Task 3, l'app locale tourne sur Postgres. Pour revenir temporairement sur SQLite (dépannage/CI), vider `DB_NAME` dans le `.env`.
- Ne jamais commiter `.env`, `db.sqlite3` ni `dump.json`.
