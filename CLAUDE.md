# CLAUDE.md

> Ce fichier fournit le contexte du projet à Claude Code (et à tout assistant IA) afin
> d'assurer des contributions cohérentes, sûres et alignées avec l'architecture cible.
> À lire **systématiquement** avant toute modification du code.

---

## 1. Vue d'ensemble du projet

**Easybiodiv** est une application web de **Dashboard biodiversité** permettant à des
entreprises de mesurer, suivre et reporter leur impact, leurs dépendances et leurs
risques biodiversité.

### Objectifs fonctionnels (MVP)
- Authentification + gestion d'utilisateurs (Admin / Utilisateur simple).
- CRUD des entreprises et de leurs sites d'exploitation (avec géolocalisation).
- Saisie / import (CSV, Excel) de données de pressions et impacts.
- Indicateurs de reporting **CSRD / ESRS E4**.
- Évaluation du **risque financier biodiversité** selon le framework **TNFD / LEAP**
  (Locate, Evaluate, Assess, Prepare).
- Dashboard avec graphiques (JS natif, ex. Chart.js via CDN si nécessaire).
- Carte interactive (Leaflet.js, en préparation de PostGIS).

### Hors périmètre MVP
- Multi-tenant complet (à anticiper dans les modèles mais non exposé).
- API publique REST/GraphQL (interne uniquement via vues Django).
- SSO entreprise, MFA.

---

## 2. Stack technique

| Couche             | Choix                                                                 |
|--------------------|-----------------------------------------------------------------------|
| Backend            | **Django** (LTS) — `django.contrib.auth`, vues classiques (CBV/FBV)   |
| Frontend           | **HTML5 + CSS3 + JavaScript natif** — **aucun framework JS** (pas de React/Vue/HTMX si non-strictement requis) |
| Cartographie       | **Leaflet.js** (chargé en local ou CDN)                               |
| Graphiques         | Chart.js (CDN) — sinon `<canvas>` natif                                |
| Base de données    | **SQLite** en dev → migration **PostgreSQL + PostGIS** en prod         |
| Hébergement cible  | **cPanel** (Passenger / WSGI Python)                                  |
| Dev local          | venv + `runserver`                                                    |
| Tests              | **Django TestCase + pytest-django**                                   |
| Gestion deps       | `requirements.txt` (séparer `base.txt`, `dev.txt`, `prod.txt`)         |

### Contraintes fortes
- **Pas de framework frontend externe**. Toute solution proposée doit s'appuyer sur
  HTML/CSS/JS vanilla. Une lib utilitaire isolée (Leaflet, Chart.js) est acceptable
  mais doit rester **chargée explicitement** et **documentée**.
- **Le code doit fonctionner identiquement en SQLite et PostgreSQL/PostGIS.**
  Encapsuler tout code spécifique PostGIS derrière un abstracteur ou un feature flag
  (ex. `if connection.vendor == "postgresql"`).
- **cPanel-friendly** : éviter dépendances système exotiques, processus
  long-running, websockets, build steps Node non triviaux.

---

## 3. Architecture du projet (modulaire par domaine)

```
easybiodiv/
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── config/                  # projet Django (settings, urls, wsgi)
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── core/                # utils transverses, mixins, base templates
│   ├── accounts/            # User custom, rôles, profils, login/logout
│   ├── companies/           # Entreprises (Company) + Sites (Site) géolocalisés
│   ├── biodiversity/        # Pressions, impacts, dépendances, indicateurs E4
│   ├── risks/               # Évaluations TNFD/LEAP, scoring, risque financier
│   ├── imports/             # Upload CSV/Excel, parsing, validation, mapping
│   └── dashboard/           # Vues agrégées, graphiques, KPI
├── static/
│   ├── css/
│   ├── js/
│   └── img/
├── templates/               # Templates globaux + base.html
├── media/                   # uploads utilisateur (gitignored)
├── tests/                   # tests transverses / d'intégration
└── docs/
    ├── CLAUDE.md            # ce fichier
    └── design.md            # charte UI/UX
```

Chaque app suit le squelette Django standard : `models.py`, `views.py`, `urls.py`,
`forms.py`, `admin.py`, `templates/<app>/`, `tests/`.

---

## 4. Modèle de données — principes

- `accounts.User` : User custom (hérite `AbstractUser`) **dès le départ**, même si
  on n'ajoute rien tout de suite. Champ `role` avec choices `ADMIN` / `USER`.
- `companies.Company` : entreprise cliente (nom, secteur NACE, SIREN…).
- `companies.Site` : site d'exploitation rattaché à une `Company`.
  - Coordonnées : `latitude` / `longitude` en `FloatField` côté SQLite.
  - **Préparer** un champ `geom` (PointField PostGIS) injecté conditionnellement
    en prod via un mixin ou une migration séparée.
- `biodiversity.Pressure` / `Impact` / `Dependency` : reliés à un `Site`.
- `biodiversity.ESRSIndicator` : indicateurs E4 (catalogue + valeurs).
- `risks.LEAPAssessment` : workflow Locate → Evaluate → Assess → Prepare,
  une évaluation par `Site` (ou `Company`), avec statut et étapes.
- `imports.ImportJob` : trace chaque upload (utilisateur, fichier, statut, erreurs).

Toujours ajouter `created_at`, `updated_at`, `created_by` (FK User) sur les modèles
métier. Préférer `models.TextChoices` aux constantes brutes.

---

## 5. Conventions de code

### Python / Django
- Python **3.11+**.
- Style : **PEP 8**, lignes ≤ 100 caractères.
- Imports triés : stdlib / Django / tiers / locaux.
- Utiliser des **vues basées classes** (CBV) pour le CRUD standard ; FBV pour les
  vues simples ou très spécifiques.
- Formulaires : toujours via `forms.ModelForm` ou `forms.Form` (jamais de POST brut).
- URL : namespacing par app (`app_name = "companies"`, reverse via
  `companies:site_detail`).
- Settings : pas de secret en clair → `os.environ` + `.env` (ignoré par git).
- Migrations : **une migration = un changement logique**. Nommer explicitement
  (`makemigrations --name add_site_geom`).

### Frontend
- Un fichier CSS par grande section / page si nécessaire ; sinon `main.css`.
- BEM léger pour le nommage des classes (`.card`, `.card__title`, `.card--muted`).
- Variables CSS (`:root { --color-terra: ... }`) — voir `design.md`.
- JS organisé en petits modules dans `static/js/` ; chargement `defer`.
- **Pas de dépendance npm** sauf accord explicite (et alors documentée).
- Accessibilité : attributs ARIA, contraste AA minimum, navigation clavier.

### Git
- Branches : `feat/<sujet>`, `fix/<sujet>`, `chore/<sujet>`.
- Commits courts en français ou anglais, à l'impératif, **un commit = un sujet**.
- Pas de commit de `db.sqlite3`, `.env`, `media/`, `__pycache__/`.

---

## 6. Tests

- Framework : **pytest-django** (préféré) avec `Django TestCase` pour les cas
  nécessitant des transactions complexes.
- Organisation : un dossier `tests/` par app, miroir de la structure
  (`test_models.py`, `test_views.py`, `test_forms.py`, `test_imports.py`).
- **Fixtures** : `pytest` fixtures + `factory_boy` (à introduire dès qu'on a >2 modèles).
- Couverture cible : **≥ 70 %** sur le code métier (`apps/`).
- Exécution :
  ```bash
  pytest                       # tous les tests
  pytest apps/companies/tests  # tests d'une app
  pytest -k "site"             # filtrage par nom
  ```
- Tout nouveau modèle / vue / formulaire doit s'accompagner d'au moins **un test**
  (création nominale + un cas d'erreur).
- Tests d'import CSV/Excel : utiliser des fichiers fixtures dans
  `apps/imports/tests/fixtures/`.

---

## 7. Workflow de développement attendu (pour Claude)

Ne **jamais** :
- Introduire un framework frontend (React, Vue, Alpine, HTMX) sans validation
  explicite.
- Casser la compatibilité SQLite (ex. champ `JSONField` Postgres-only, fonctions
  PostGIS dans le code commun).
- Modifier `settings/prod.py` sans le signaler.
- Supprimer des migrations historiques.
- Ajouter une dépendance lourde sans l'inscrire dans `requirements/*.txt` et la
  justifier.


## 10. Sécurité & conformité

- `DEBUG=False` en prod, `ALLOWED_HOSTS` configuré.
- Secrets via variables d'environnement.
- CSRF activé partout, `SECURE_*` settings en prod (`SECURE_SSL_REDIRECT`,
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`).
- Données entreprises potentiellement sensibles → journaliser les accès admin,
  limiter les exports.
- Conserver une cohérence avec les exigences **CSRD** (traçabilité des données
  saisies, qui, quand).

---

## 11. Référence design

Toute décision visuelle (couleurs, typographie, espacement, composants) est
**centralisée dans `design.md`**. Ne pas introduire d'autres palettes ou polices
sans mise à jour de ce fichier.
