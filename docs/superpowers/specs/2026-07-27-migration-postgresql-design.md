# Migration SQLite → PostgreSQL (dev + prod)

> Design validé le 2026-07-27.
> Objet : faire passer Easybiodiv de SQLite à **PostgreSQL** en **dev local** ET en
> **production** (o2switch/cPanel), avec deux bases **séparées** mais une config
> **identique pilotée par l'environnement** (parité totale : voir les changements
> en dev avant la prod). **PostGIS est préparé mais volontairement pas activé**
> maintenant (cf. CLAUDE.md §2, §4).

---

## 1. Contexte

État actuel (`easybiodiv/settings.py`) :
- Django 6.0.5, `DATABASES` **en dur** sur SQLite (`django.db.backends.sqlite3`,
  `BASE_DIR / 'db.sqlite3'`).
- Variables déjà lues depuis un `.env` via `python-dotenv` (`SECRET_KEY`, `DEBUG`,
  `ALLOWED_HOSTS`). Durcissement prod déjà présent (Passenger/o2switch).
- Dépendances (`requirements.txt`) : Django, whitenoise, python-dotenv, openpyxl,
  Pillow… **pas de driver PostgreSQL**.
- Custom user model `authentication.User`. Apps métier : `dashboard`, `imports`.
- Données existantes dans SQLite **à conserver**.

**Décisions de cadrage (arbitrées avec l'utilisateur) :**
- **Deux bases séparées** dev/prod (pas de base partagée) — le plus sûr.
- **Postgres en dev ET en prod** (l'utilisateur veut la parité et prépare les
  cartes → PostGIS futur).
- **PostGIS différé** : on migre vers Postgres « simple » maintenant. GeoDjango
  (`django.contrib.gis`, backend `postgis`, GDAL/GEOS) n'est **pas** activé ; il le
  sera le jour des cartes, une fois la disponibilité PostGIS+GDAL **confirmée sur
  o2switch**. Conforme à CLAUDE.md (« encapsuler tout code spécifique PostGIS »).
- **Accès distant Postgres non requis** : le dev ne se connecte jamais à la prod.
- Accès serveur o2switch : **cPanel uniquement** (pas de SSH) → Terminal cPanel /
  console « Setup Python App ».

## 2. Design

### 2.1 Dépendance — `requirements.txt`

Ajouter le driver `psycopg[binary]` (psycopg 3, supporté nativement par Django 6.0 ;
la variante `[binary]` embarque les binaires → **aucune compilation** requise sur
Windows ni sur cPanel).

### 2.2 `settings.py` — `DATABASES` piloté par l'environnement

Remplacer le bloc SQLite en dur par une config lue depuis l'environnement :

```python
if os.environ.get('DB_NAME'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ['DB_NAME'],
            'USER': os.environ['DB_USER'],
            'PASSWORD': os.environ['DB_PASSWORD'],
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
```

- **Une seule ligne de code identique** dev/prod ; seules les **valeurs** du `.env`
  diffèrent.
- **Repli SQLite** conservé si `DB_NAME` est absent (dépannage / CI éventuelle).
- Un **commentaire** documente le futur passage au backend PostGIS
  (`django.contrib.gis.db.backends.postgis`) le jour des cartes.

### 2.3 `.env.example`

Documenter les nouvelles variables (à côté des existantes) :

```
# Base de données PostgreSQL (laisser vide pour retomber sur SQLite)
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432
```

### 2.4 Postgres en local (dev, Windows)

Procédure documentée (dans la doc de déploiement, cf. §2.7) :
1. Installer PostgreSQL (installeur EnterpriseDB pour Windows).
2. Créer une base + un utilisateur de dev (l'utilisateur local possède le droit
   `CREATE DATABASE` → nécessaire pour les tests, cf. §2.6).
3. Renseigner `.env` local avec les `DB_*` correspondants.
4. *(PostGIS : l'extension est fournie par l'installeur Windows / Stack Builder ;
   `CREATE EXTENSION postgis` pourra être exécuté le moment venu, sans réinstaller.)*

### 2.5 Postgres en prod (o2switch, cPanel)

Procédure documentée :
1. cPanel → « Bases de données PostgreSQL » : créer la base, l'utilisateur, le mot
   de passe (cPanel préfixe automatiquement : `cpaneluser_...`).
2. Associer utilisateur ↔ base avec **tous les privilèges**.
3. Renseigner le `.env` de prod (`DB_HOST=localhost`, port par défaut).

### 2.6 Transfert des données existantes (SQLite → chaque base Postgres)

Le dump est généré **une fois** depuis SQLite, puis chargé dans **chacune** des deux
bases (dev locale, puis prod).

1. **Dump** (avec SQLite encore actif, c.-à-d. sans `DB_NAME`) :
   ```
   python manage.py dumpdata --exclude contenttypes --exclude auth.permission --indent 2 -o dump.json
   ```
   - `-o dump.json` : écriture directe (évite les soucis d'encodage UTF-16 de la
     redirection PowerShell).
   - `--exclude contenttypes --exclude auth.permission` : évite les collisions de
     clés lors du `loaddata` (ces tables sont recréées par `migrate`).
2. **Dev** : basculer `.env` sur Postgres → `migrate` → `loaddata dump.json`.
3. **Prod** : déployer le code + `dump.json` sur o2switch, renseigner le `.env` prod,
   puis via **Terminal cPanel / console Setup Python App** :
   `pip install -r requirements.txt` → `migrate` → `loaddata dump.json`.
4. `dump.json` est **temporaire** et **non commité** (à ajouter au `.gitignore` s'il
   n'est pas déjà couvert).

### 2.7 Documentation de déploiement

Consigner la procédure (installation Postgres local, création base cPanel, transfert
des données, futures migrations via Terminal cPanel) dans un fichier de doc
(`docs/` — emplacement/format à préciser dans le plan).

### 2.8 PostGIS — vérification anticipée (hors périmètre de cette migration)

À lever tôt auprès d'o2switch, **sans bloquer** cette migration : l'**extension
PostGIS** et les bibliothèques **GDAL/GEOS/PROJ** sont-elles disponibles sur le
mutualisé ? Si non, les futures cartes imposeront un VPS. Aucune action code ici.

## 3. Tests

- `pytest` s'exécutera désormais sur **Postgres local** (Django crée automatiquement
  une base `test_<DB_NAME>` ; l'utilisateur de dev local a le droit `CREATE
  DATABASE`). Bénéfice : parité réelle avec la prod, détection des différences
  Postgres.
- **Critère de non-régression** : les 259 tests existants doivent rester **verts**
  sur Postgres. Tout test dépendant d'un comportement spécifique SQLite sera corrigé
  (aucun attendu à ce stade).
- Aucun test ne tourne contre la base de prod (bases séparées).

## 4. Fichiers touchés

- `requirements.txt` — ajout `psycopg[binary]`.
- `easybiodiv/settings.py` — bloc `DATABASES` piloté par l'environnement.
- `.env.example` — variables `DB_*` documentées.
- `.gitignore` — s'assurer que `dump.json` est ignoré.
- Doc de déploiement (nouveau fichier `docs/`).

## 5. Hors périmètre

- Activation de GeoDjango / PostGIS / GDAL (différée au jour des cartes).
- Accès Postgres distant depuis le dev.
- Migration automatisée type `pgloader` (le couple `dumpdata`/`loaddata` suffit au
  volume actuel).
- Modification de `settings` prod au-delà du bloc `DATABASES`.
