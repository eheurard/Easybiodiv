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
| Base de données    | **SQLite** en dev **et en prod** (o2switch, voir `docs/deploiement-production.md`) ; code gardé compatible PostgreSQL |
| Hébergement cible  | **cPanel** (Passenger / WSGI Python)                                  |
| Dev local          | venv + `runserver`                                                    |
| Tests              | **Django TestCase + pytest-django**                                   |
| Gestion deps       | un seul `requirements.txt` à la racine (runtime + tests)               |

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
├── passenger_wsgi.py        # point d'entrée WSGI cPanel
├── requirements.txt         # dépendances runtime + tests
├── pytest.ini               # DJANGO_SETTINGS_MODULE + motifs de collecte
├── CLAUDE.md                # ce fichier
├── DESIGN.md                # charte UI/UX
├── easybiodiv/              # projet Django (settings, urls, wsgi)
│   ├── settings.py          # module unique (pas de split base/dev/prod)
│   ├── db.py                # aiguillage SQLite ↔ PostgreSQL
│   ├── urls.py
│   ├── asgi.py / wsgi.py
│   └── test_db.py
├── authentication/          # User custom, rôles, login/logout
│   ├── migrations/ static/ templates/
│   └── tests/               # test_models.py, test_forms.py, test_views.py
├── dashboard/               # cœur métier : modèles, vues agrégées, LEAP, Portfolio
│   ├── services/            # logique métier extraite (market, stress_test…)
│   ├── management/ migrations/ golden/ static/ templates/
│   ├── tests.py             # gros fichier de tests historique
│   ├── tests_admin_console.py
│   └── tests_stress_test.py
├── imports/                 # Upload Excel, parsing, validation, mapping
│   ├── services/ templates/
│   └── tests/
├── templates/               # templates globaux : base.html, admin/, dashboard/
├── media/                   # uploads utilisateur (gitignored)
└── docs/
    ├── agents/              # config des agent skills (issue tracker, triage, domain)
    └── superpowers/
```

**Cette arborescence est plate, pas en `apps/`.** Les trois applications Django sont
`authentication`, `dashboard` et `imports`, à la racine. Il n'y a ni paquet `apps/`,
ni paquet `config/`, ni dossier `static/` ou `tests/` racine : le statique et les
tests vivent dans chaque app.

Chaque app suit le squelette Django standard : `models.py`, `views.py`, `urls.py`,
`forms.py`, `admin.py`, `templates/<app>/`, et ses tests (`tests/` pour
`authentication` et `imports`, fichiers `tests*.py` pour `dashboard`).

l'environnement python est ./venv/scripts/activate.ps1
---

## 4. Modèle de données — principes

Tous les modèles métier vivent dans **`dashboard/models.py`** (~28 modèles).
`authentication` ne porte que `User` ; **`imports` n'a aucun modèle** (parsing et
vues uniquement, sans trace d'import persistée).

### Identité et périmètre

- `authentication.User` : User custom (hérite `AbstractUser`), avec `profile_photo`
  et `role` — choices **`CREATOR` / `SUBSCRIBER`** (et non `ADMIN` / `USER`).
- `Company` : entreprise analysée. Volontairement minimale — `name`, `description`,
  `isin`, `ticker`. Pas de SIREN ni de code NACE porté directement ; le rattachement
  sectoriel passe par `Company_Revenue_Sector` → `SubSector` → `Sector`.
- `Asset` : **l'entité géolocalisée** (c'est elle, et non une « Site »), avec
  `latitude` / `longitude` en `FloatField`, rattachée à `Country` et
  `SubnationalRegion`. Le lien Asset ↔ Company passe par `Ownership` : part décimale
  (`share`, entre 0 et 1) et années de validité (`start_year`, `end_year`). Lire le
  périmètre d'une entreprise avec `Asset.objects.owned_by(company, year=None)`.
- `Country`, `SubnationalRegion`, `Commodity`, `Sector`, `SubSector`, `Currency` :
  tables de référence.

### Activité et finance

- `Flow` : table unique des flux (spec
  `docs/superpowers/specs/2026-09-18-table-flow-unique-design.md`). Une ligne = une
  quantité d'une commodité (`what`), une année, d'une origine (`from_*`) vers une
  destination (`to_*`) : actif, région, pays, entreprise, milieu
  (`*_environment`) ou vide (inconnu). `kind` : PRODUCTION, SUPPLY, CONSUMPTION,
  EMISSION, WASTE ; les extrémités autorisées par nature sont dans `FLOW_RULES`,
  qui génère les contraintes en base. Lecture **uniquement** via
  `dashboard/services/flows.py`.
- `Company_Revenue` / `Company_Revenue_Sector` : chiffre d'affaires, global et
  ventilé par `SubSector`.
- `Policy_Type` → `Policy_Subcategory` → `Policy_Level`, appliqués via
  `Company_Policy` : cadre réglementaire (EUDR, CSRD/ESRS E4, taxe biodiversité…).
- `ESG_data` : indicateurs extra-financiers par entreprise. Les émissions déclarées
  sont des flux EMISSION de l'entreprise vers le milieu, avec leur `scope`.

### Impacts (chaîne ACV)

- `ImpactMethod` → `ImpactCategory` → `CharacterizationFactor` : facteurs de
  caractérisation régionalisés (impact par unité de `Commodity`).
- Inventaire mesuré (eau, énergie, CO₂, déchets, surface) et approvisionnement :
  flux `Flow` (CONSUMPTION, EMISSION, WASTE, SUPPLY). Les commodités techniques
  lues par le code ont une `Commodity.key` (`TECHNICAL_COMMODITIES`).

### Conformité et risque

- `E4Assessment` + `DisclosureRequirement` : dossier de conformité **ESRS E4**
  (verrou de matérialité + workflow LEAP). C'est ici que vit le LEAP, pas dans une
  app `risks`.
- `ClimateScenario` + `ScenarioVariable` : scénarios climatiques NGFS Phase V
  (prix carbone, multiplicateurs d'aléa), consommés par le stress test.
- `SectorCreditProfile` : paramètres de crédit et de marge par secteur (OneToOne).
- `Portfolio` + `PortfolioHolding` : portefeuilles pondérés d'entreprises.
  `PortfolioQuerySet` porte les règles de visibilité et d'édition. **Seule zone de
  l'application restée derrière `@login_required`.**

### Conventions

- `created_at` / `updated_at` ne sont présents que sur les modèles récents
  (`E4Assessment`, `CharacterizationFactor`, `Flow`, `Ownership`,
  `ClimateScenario`, `SectorCreditProfile`, `Portfolio`) ; `created_by` sur
  `E4Assessment`, `Flow`, `Ownership` et `Portfolio`. Les tables de référence
  historiques n'en ont pas — les ajouter sur **tout nouveau modèle métier**, sans
  rétrofit massif de l'existant.
- Aucun champ `geom` PostGIS n'existe aujourd'hui : la géo passe par
  `latitude` / `longitude` sur `Asset`.
- Nommage historique inconsistant (`Company_Revenue`, `ESG_data`, `Policy_Level`).
  Ne pas propager ce style : **nouveau code en `snake_case`** pour les
  champs et `CamelCase` sans underscore pour les classes.
- Préférer `models.TextChoices` aux constantes brutes.

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
- Organisation : un dossier `tests/` par app pour `authentication` et `imports`
  (`test_models.py`, `test_views.py`, `test_forms.py`…). `dashboard` utilise encore
  des fichiers plats à la racine de l'app (`tests.py`, `tests_admin_console.py`,
  `tests_stress_test.py`) — d'où le `python_files` élargi dans `pytest.ini`.
- La config de collecte vit dans `pytest.ini`. Elle exclut volontairement le motif
  `*_test.py`, qui ramasserait `dashboard/services/stress_test.py` (code de production).
- **Fixtures** : `pytest` fixtures + `factory_boy` (installé ; aucune factory écrite
  pour l'instant — en ajouter au fil des nouveaux tests plutôt qu'en masse).
- Couverture cible : **≥ 70 %** sur le code métier. Périmètre et exclusions
  (migrations, tests, wsgi/asgi) dans `.coveragerc`.
- Exécution :
  ```bash
  pytest                       # tous les tests (~570, ~4 min)
  pytest dashboard             # tests d'une app
  pytest -k "leap"             # filtrage par nom
  pytest --cov                 # avec rapport de couverture
  ```
- Tout nouveau modèle / vue / formulaire doit s'accompagner d'au moins **un test**
  (création nominale + un cas d'erreur).
- Tests d'import Excel : fichiers fixtures dans `imports/tests/fixtures/`.

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

---

## Agent skills

### Issue tracker

Les issues vivent dans GitHub Issues (`eheurard/Easybiodiv`), pilotées via la CLI `gh`.
Voir `docs/agents/issue-tracker.md`.

### Triage labels

Vocabulaire canonique par défaut : `needs-triage`, `needs-info`, `ready-for-agent`,
`ready-for-human`, `wontfix`. Voir `docs/agents/triage-labels.md`.

### Domain docs

Repo mono-contexte : un `CONTEXT.md` + `docs/adr/` à la racine.
Voir `docs/agents/domain.md`.
