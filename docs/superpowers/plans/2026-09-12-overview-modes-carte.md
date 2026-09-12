# Vue d'ensemble — modes de carte Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter à la Vue d'ensemble 4 modes de carte (exposition pays, exposition asset, risque physique, dette écologique) et une supply chain disponible dans tous les modes, en réutilisant les données et le rendu des pages Locate, Risque physique et Dette.

**Architecture:** Le rendu des pages de référence est extrait dans des modules partagés (IIFE `window.LocateView`, `window.SupplyChain`, `window.PhysicalRiskView`, `window.DetteView`, plus `window.PieMarkers` existant) et dans des fragments de template communs. Un nouveau `overview.js` (qui reprend la logique overview de `main.js`) pilote un registre de modes : chaque mode charge à la demande l'API existante de sa page de référence, puis rend panneau, points, légende et tiroir. Backend : seul ajout du champ `type` à la sortie Locate.

**Tech Stack:** Django 6 (TestCase), JavaScript vanilla (scripts classiques `defer`), MapLibre GL 4, CSS à jetons (`DESIGN.md`).

**Spec:** `docs/superpowers/specs/2026-09-12-overview-modes-carte-design.md`

## Global Constraints

- Django pur, compatible SQLite et PostgreSQL, aucune dépendance nouvelle, PEP 8 ≤ 100 caractères (Python).
- JS vanilla, scripts chargés en `defer`, pas de framework ni de npm. `node` (v24, déjà installé) sert **uniquement** au contrôle de syntaxe `node --check` ; aucun fichier Node n'est ajouté au repo.
- Scripts classiques = espace global partagé : deux `const` top-level de même nom dans deux scripts d'une même page provoquent une `SyntaxError`. Les modules partagés sont des IIFE qui n'exposent que `window.X` ; les noms top-level d'`overview.js` sont préfixés `ov` / `OV`, sauf `SELECTED_COMPANY_KEY` et `ASSET_TYPE_COLORS`, qui sont **retirés** de `main.js`.
- Chrome de l'interface via les jetons `--color-*`, `--scrim-*`, `--tint-*` uniquement ; palettes de données identiques dans les deux thèmes.
- Pages Locate, Risque physique et Dette : **rendu strictement identique** après extraction.
- Règles d'accès des API inchangées ; `index` reste public ; boutons verrouillés rendus `disabled` + `title="Connexion requise"` côté serveur.
- Commande de test : `venv/Scripts/python.exe manage.py test dashboard` (Git Bash ou PowerShell). Ne jamais rediriger une sortie vers un fichier du repo.
- Référence avant la tâche 0 : 438 tests, **35 erreurs**, toutes causées par `populate_acme` (voir tâche 0).
- Ne pas committer `templates/base.html` (reformatage local de l'utilisateur, hors sujet).
- Commits : un sujet par commit, message en français à l'impératif, terminé par la ligne `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Carte des fichiers

| Fichier | Rôle | Tâches |
|---|---|---|
| `dashboard/management/commands/populate_acme.py` | Jeu Acme ; retrait des `description` supprimés par 0048 | 0 |
| `dashboard/views.py` | `_get_leap_locate_data` expose `type` | 1 |
| `dashboard/golden/leap_locate.json` | Golden réenregistré (ajout de `type` seulement) | 1 |
| `dashboard/static/dashboard/js/locate_view.js` (nouveau) | `LocateView` : style par revenu, liste, popup, légende | 2 |
| `dashboard/static/dashboard/js/supply_chain.js` (nouveau) | `SupplyChain.create(map, opts)` : courbes, flèches, fournisseurs, légende | 3 |
| `dashboard/static/dashboard/js/leap_locate.js` | Amorce Locate branchée sur les deux modules | 2, 3 |
| `dashboard/templates/dashboard/leap_locate.html` | Charge les modules | 2, 3 |
| `dashboard/static/dashboard/js/physical_risk_view.js` (nouveau) | `PhysicalRiskView` : KPI, horizon, classement, tableau, geojson, popup, légende | 4 |
| `dashboard/templates/dashboard/_pr_panel.html` (nouveau) | KPI + classement des aléas | 4 |
| `dashboard/templates/dashboard/_pr_detail_drawer.html` (nouveau) | Tiroir « Détail par actif » | 4 |
| `dashboard/static/dashboard/js/physical_risk.js` | Amorce Risque physique | 4 |
| `dashboard/templates/dashboard/physical_risk.html` | Inclut les fragments, charge le module | 4 |
| `dashboard/static/dashboard/js/dette_view.js` (nouveau) | `DetteView` : KPI, légende, infobulle, liste d'assets | 5 |
| `dashboard/templates/dashboard/_de_kpis.html` (nouveau) | KPI dette | 5 |
| `dashboard/static/dashboard/js/dette_ecologique.js` | Amorce Dette (camemberts via `PieMarkers`) | 5 |
| `dashboard/templates/dashboard/dette_ecologique.html` | Inclut le fragment, charge les modules | 5 |
| `dashboard/static/dashboard/js/overview.js` (nouveau) | Contrôleur des modes de la Vue d'ensemble | 6, 7, 8 |
| `dashboard/static/dashboard/js/main.js` | Ne garde que le transverse ; correctif `activeMapStyleName` | 6 |
| `dashboard/templates/dashboard/index.html` | Boutons de mode, vues, légendes, tiroirs, scripts | 6, 7, 8 |
| `dashboard/static/dashboard/css/style.css` | `.ov-modes`, `.ov-list`, suppression des styles morts | 6 |
| `dashboard/tests.py` | Tests pages / fragments / verrouillage | 1–8 |

---

### Task 0 : Réparer `populate_acme` (prérequis du golden)

La migration 0048 a supprimé `description` de `SubnationalRegion`, `Sector` et `SubSector`, mais `populate_acme` le passe encore dans `defaults` → `FieldError`, 35 tests en erreur dont `GoldenViewOutputTests`, dont la tâche 1 a besoin.

**Files:**
- Modify: `dashboard/management/commands/populate_acme.py` (régions l. 68-121, secteurs l. 125-133, sous-secteurs l. 135-178)
- Test: existants (`PopulateAcmeE4Tests`, `PopulateAcmeCfTests`, `dashboard.tests_stress_test`, `GoldenViewOutputTests`)

**Interfaces:**
- Consumes: —
- Produces: `call_command('populate_acme')` fonctionne de nouveau (utilisé par le golden en tâche 1).

- [ ] **Step 1 : Constater l'échec**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.PopulateAcmeE4Tests dashboard.tests.GoldenViewOutputTests`
Expected : ERROR `django.core.exceptions.FieldError: Invalid field name(s) for model SubnationalRegion: 'description'.`

- [ ] **Step 2 : Retirer les 10 clés `description` des modèles concernés**

Dans `populate_acme.py`, supprimer **uniquement** ces lignes (les autres `description`, sur `Commodity`, `Asset`, `Policy_*`…, restent : ces modèles ont toujours le champ) :

Régions (`SubnationalRegion.objects.get_or_create`) — supprimer les 5 lignes :
```python
                "description": "Région nord-ouest, industrie agroalimentaire dense",
                "description": "Région sud, grandes cultures céréalières",
                "description": "État de la frontière agricole du soja, Cerrado",
                "description": "État amazonien à fort risque de déforestation",
                "description": "Île principale de la production d'huile de palme",
```

Secteurs (`Sector.objects.get_or_create`) — remplacer :
```python
            defaults={"NACE_code": "A01", "description": "Production végétale et animale"},
```
par :
```python
            defaults={"NACE_code": "A01"},
```
et :
```python
            defaults={"NACE_code": "C10", "description": "Transformation des produits alimentaires"},
```
par :
```python
            defaults={"NACE_code": "C10"},
```

Sous-secteurs (`SubSector.objects.get_or_create`) — supprimer les 3 lignes :
```python
                "description": "Blé, maïs, colza",
                "description": "Soja, palmier à huile",
                "description": "Raffinage et conditionnement d'huiles",
```

- [ ] **Step 3 : Relancer les tests en erreur**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.PopulateAcmeE4Tests dashboard.tests.PopulateAcmeCfTests dashboard.tests_stress_test dashboard.tests.GoldenViewOutputTests`
Expected : OK.
**Si `GoldenViewOutputTests` échoue** sur une différence de contenu (et non plus sur `FieldError`) : c'est une dérive antérieure des sorties. Ne PAS réenregistrer ; noter la vue et la différence affichée, et s'arrêter pour le signaler.

- [ ] **Step 4 : Commit**

```bash
git add dashboard/management/commands/populate_acme.py
git commit -m "fix(populate_acme): retire les description supprimés par la migration 0048

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 1 : Backend — `type` dans la sortie Locate

**Files:**
- Modify: `dashboard/views.py` (`_get_leap_locate_data`, dictionnaire `properties`, ~l. 582-590)
- Modify: `dashboard/golden/leap_locate.json` (réenregistré)
- Test: `dashboard/tests.py` (`LeapLocateDataTests.test_geojson_feature_properties`)

**Interfaces:**
- Consumes: `Asset.type` (CharField, défaut `'Factory'`).
- Produces: chaque feature de `geojson.features` de `leap_locate_data` porte `properties.type` (str). Utilisé par le filtre du mode asset (tâche 6).

- [ ] **Step 1 : Écrire l'assertion**

Dans `LeapLocateDataTests.test_geojson_feature_properties`, juste après `self.assertEqual(props['asset_type'], 'Agriculture')`, ajouter :
```python
        self.assertEqual(props['type'], 'Factory')  # Asset.type (défaut du modèle)
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.LeapLocateDataTests`
Expected : ERROR `KeyError: 'type'`.

- [ ] **Step 3 : Implémenter**

Dans `_get_leap_locate_data`, remplacer :
```python
                'region': a.subnational_region.name if a.subnational_region else '',
                'asset_type': ', '.join(asset_types),
```
par :
```python
                'region': a.subnational_region.name if a.subnational_region else '',
                'type': a.type,
                'asset_type': ', '.join(asset_types),
```

- [ ] **Step 4 : Vérifier le succès**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.LeapLocateDataTests`
Expected : OK.

- [ ] **Step 5 : Réenregistrer le golden**

Git Bash : `GOLDEN_RECORD=1 venv/Scripts/python.exe manage.py test dashboard.tests.GoldenViewOutputTests`
PowerShell : `$env:GOLDEN_RECORD='1'; venv\Scripts\python.exe manage.py test dashboard.tests.GoldenViewOutputTests; Remove-Item Env:GOLDEN_RECORD`

- [ ] **Step 6 : Contrôler le diff du golden**

Run : `git diff --stat dashboard/golden` puis `git diff dashboard/golden/leap_locate.json`
Expected : seul `leap_locate.json` change, et le diff ne contient que des lignes ajoutées `"type": "<Type>",`. Tout autre fichier modifié : `git checkout -- <fichier>`, puis s'arrêter et signaler.

- [ ] **Step 7 : Vérifier le golden en mode contrôle**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.GoldenViewOutputTests`
Expected : OK.

- [ ] **Step 8 : Commit**

```bash
git add dashboard/views.py dashboard/tests.py dashboard/golden/leap_locate.json
git commit -m "feat(leap-locate): expose le type d'actif dans la sortie Locate

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2 : Module `LocateView` + branchement de la page Locate

**Files:**
- Create: `dashboard/static/dashboard/js/locate_view.js`
- Modify: `dashboard/static/dashboard/js/leap_locate.js`
- Modify: `dashboard/templates/dashboard/leap_locate.html` (bloc `extra_js`)
- Test: `dashboard/tests.py` (`LeapPagesTests`)

**Interfaces:**
- Consumes: globaux de `main.js` : `escHtml(s)`, `fmtNum(n)`, `fmtEuro(n)`.
- Produces: `window.LocateView` =
  - `REVENUE_COLORS` : `{Low, Moderate, High, VeryHigh}` → hex
  - `revenueBand(ratio: number) → 'Low'|'Moderate'|'High'|'VeryHigh'`
  - `styleFeatures(features: Feature[]) → Feature[]` (copies avec `properties.color`, `properties.radius`)
  - `prodLine(prod) → string`
  - `listHtml(features: Feature[]) → string` (cartes `.ll-item.ll-item--clickable` avec `data-lng` / `data-lat`)
  - `popupHtml(props) → string` (accepte `productions` tableau ou chaîne JSON)
  - `legendHtml() → string` (titre « Revenu associé » + 4 bandes)

- [ ] **Step 1 : Écrire le test**

Dans `LeapPagesTests`, ajouter :
```python
    def test_locate_page_loads_locate_view_module(self):
        response = self.client.get(reverse('dashboard:leap_locate'))
        self.assertContains(response, 'dashboard/js/locate_view.js')
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.LeapPagesTests`
Expected : FAIL `Couldn't find 'dashboard/js/locate_view.js' in response`.

- [ ] **Step 3 : Créer `locate_view.js`**

```js
'use strict';

// Rendu partagé de la phase LEAP Locate : style des points par revenu associé,
// cartes de la liste « Sites localisés », popup d'asset et légende. Utilisé par
// la page Locate et par le mode « Exposition asset » de la Vue d'ensemble.
// Dépend des utilitaires globaux de main.js (escHtml, fmtNum, fmtEuro).
window.LocateView = (function () {
  // Échelle séquentielle (clair → foncé) utilisée pour le revenu associé.
  const REVENUE_COLORS = {
    Low:      '#dac1ba',
    Moderate: '#feb87c',
    High:     '#af5d43',
    VeryHigh: '#91452d',
  };
  const REVENUE_LABELS = {
    Low: 'Faible', Moderate: 'Modéré', High: 'Élevé', VeryHigh: 'Très élevé',
  };

  function revenueBand(ratio) {
    if (ratio >= 0.66) return 'VeryHigh';
    if (ratio >= 0.33) return 'High';
    if (ratio > 0)     return 'Moderate';
    return 'Low';
  }

  function euro(v) { return fmtEuro(Math.round(Number(v) || 0)); }

  // Sur une source GeoJSON, MapLibre sérialise les propriétés non primitives.
  function parseList(value) {
    if (typeof value === 'string') {
      try { return JSON.parse(value); } catch (_) { return []; }
    }
    return value || [];
  }

  // Marqueurs colorés et dimensionnés par revenu associé (relatif au max courant).
  function styleFeatures(features) {
    const maxRev = features.reduce((m, f) => Math.max(m, f.properties.revenue_total || 0), 0) || 1;
    return features.map(f => {
      const ratio = (f.properties.revenue_total || 0) / maxRev;
      return {
        type: 'Feature',
        geometry: f.geometry,
        properties: Object.assign({}, f.properties, {
          color: REVENUE_COLORS[revenueBand(ratio)],
          radius: 6 + 18 * ratio,
        }),
      };
    });
  }

  function prodLine(p) {
    const qty = `${fmtNum(p.quantity)} ${escHtml(p.unit)}`;
    return `<span class="ll-prod"><span class="ll-prod__name">${escHtml(p.commodity)}</span>`
      + `<span class="ll-prod__qty">${qty}</span></span>`;
  }

  // Cartes de la liste ; data-lng / data-lat servent au zoom au clic.
  function listHtml(features) {
    return features.map(f => {
      const p = f.properties;
      const [lng, lat] = f.geometry.coordinates;
      const badge = p.asset_type ? `<span class="ll-item__badge">${escHtml(p.asset_type)}</span>` : '';
      const own = p.ownership
        ? `<div class="ll-item__meta">Détention : <strong>${escHtml(p.ownership)}</strong></div>` : '';
      const prods = parseList(p.productions);
      const prodHtml = prods.length
        ? `<div class="ll-item__prods">${prods.map(prodLine).join('')}</div>` : '';
      return `
      <div class="ll-item ll-item--clickable" data-lng="${lng}" data-lat="${lat}">
        <div class="ll-item__top">
          <span class="ll-item__name">${escHtml(p.name)}</span>
          ${badge}
        </div>
        ${own}
        ${prodHtml}
        <div class="ll-item__revenue">Revenu associé&nbsp;: <strong>${euro(p.revenue_total)}</strong></div>
      </div>`;
    }).join('');
  }

  function popupHtml(p) {
    const prods = parseList(p.productions);
    const meta = [p.country, p.region].filter(Boolean).map(escHtml).join(' · ');
    const type = p.asset_type ? `<div class="ll-popup__row">Type : ${escHtml(p.asset_type)}</div>` : '';
    const own  = p.ownership ? `<div class="ll-popup__row">Détention : ${escHtml(p.ownership)}</div>` : '';
    const prodHtml = prods.length
      ? `<div class="ll-popup__prods">${prods.map(prodLine).join('')}</div>`
      : '<div class="ll-popup__row">Aucune production</div>';
    return `<div class="ll-popup"><strong>${escHtml(p.name)}</strong>` +
      `<div class="ll-popup__meta">${meta}</div>${type}${own}${prodHtml}` +
      `<div class="ll-popup__revenue">Revenu associé : ${euro(p.revenue_total)}</div></div>`;
  }

  function legendHtml() {
    const items = Object.keys(REVENUE_COLORS).map(k =>
      `<li><span class="map-legend__dot" style="background:${REVENUE_COLORS[k]}"></span>${REVENUE_LABELS[k]}</li>`
    ).join('');
    return `<p class="map-legend__title">Revenu associé</p><ul class="map-legend__list">${items}</ul>`;
  }

  return { REVENUE_COLORS, revenueBand, styleFeatures, prodLine, listHtml, popupHtml, legendHtml };
})();
```

- [ ] **Step 4 : Brancher `leap_locate.js` sur le module**

(a) Supprimer le bloc suivant (constante, bande et formatage, déplacés dans le module) :
```js
// Échelle séquentielle (clair → foncé) utilisée pour le revenu associé.
const LL_REVENUE_COLORS = {
  Low:      '#dac1ba',
  Moderate: '#feb87c',
  High:     '#af5d43',
  VeryHigh: '#91452d',
};

function llRevenueBand(ratio) {
  if (ratio >= 0.66) return 'VeryHigh';
  if (ratio >= 0.33) return 'High';
  if (ratio > 0)     return 'Moderate';
  return 'Low';
}

function llEuro(v) { return fmtEuro(Math.round(Number(v) || 0)); }

```

(b) Remplacer `llStyledFeatures` et `llProdLine` :
```js
// Marqueurs colorés et dimensionnés par revenu associé (relatif au max courant).
function llStyledFeatures() {
  const all = llFeatures();
  const maxRev = all.reduce((m, f) => Math.max(m, f.properties.revenue_total || 0), 0) || 1;
  return all.map(f => {
    const ratio = (f.properties.revenue_total || 0) / maxRev;
    return {
      type: 'Feature',
      geometry: f.geometry,
      properties: Object.assign({}, f.properties, {
        color: LL_REVENUE_COLORS[llRevenueBand(ratio)],
        radius: 6 + 18 * ratio,
      }),
    };
  });
}

function llProdLine(p) {
  const qty = `${fmtNum(p.quantity)} ${escHtml(p.unit)}`;
  return `<span class="ll-prod"><span class="ll-prod__name">${escHtml(p.commodity)}</span>`
    + `<span class="ll-prod__qty">${qty}</span></span>`;
}
```
par :
```js
// Marqueurs colorés et dimensionnés par revenu associé (relatif au max courant).
function llStyledFeatures() {
  return LocateView.styleFeatures(llFeatures());
}
```

(c) Dans `llAddSourceAndLayer`, remplacer tout le gestionnaire `map.on('click', 'll-assets-layer', (e) => { … });` (de `const p = e.features[0].properties;` jusqu'à `.addTo(map);` inclus) par :
```js
  map.on('click', 'll-assets-layer', (e) => {
    new maplibregl.Popup({ maxWidth: '280px' })
      .setLngLat(e.lngLat)
      .setHTML(LocateView.popupHtml(e.features[0].properties))
      .addTo(map);
  });
```

(d) Dans `llRenderList`, remplacer l'affectation `el.innerHTML = features.map(f => { … }).join('');` (tout le bloc qui construit les cartes `.ll-item`) par :
```js
  el.innerHTML = LocateView.listHtml(features);
```
Le `el.querySelectorAll('.ll-item--clickable').forEach(…)` qui suit reste inchangé.

- [ ] **Step 5 : Charger le module dans `leap_locate.html`**

Remplacer :
```django
<script src="{% static 'dashboard/js/leap_locate.js' %}" defer></script>
```
par :
```django
<script src="{% static 'dashboard/js/locate_view.js' %}" defer></script>
<script src="{% static 'dashboard/js/leap_locate.js' %}" defer></script>
```

- [ ] **Step 6 : Contrôles**

Run : `node --check dashboard/static/dashboard/js/locate_view.js && node --check dashboard/static/dashboard/js/leap_locate.js`
Expected : aucune sortie.
Run : `grep -n "LL_REVENUE_COLORS\|llRevenueBand\|llEuro\|llProdLine" dashboard/static/dashboard/js/leap_locate.js`
Expected : aucune ligne.
Run : `venv/Scripts/python.exe manage.py test dashboard.tests.LeapPagesTests dashboard.tests.LeapLocateDataTests`
Expected : OK.

- [ ] **Step 7 : Commit**

```bash
git add dashboard/static/dashboard/js/locate_view.js dashboard/static/dashboard/js/leap_locate.js dashboard/templates/dashboard/leap_locate.html dashboard/tests.py
git commit -m "refactor(locate): extrait le rendu Locate dans locate_view.js

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3 : Module `SupplyChain` + branchement de la page Locate

**Files:**
- Create: `dashboard/static/dashboard/js/supply_chain.js`
- Modify: `dashboard/static/dashboard/js/leap_locate.js` (réécriture complète ci-dessous)
- Modify: `dashboard/templates/dashboard/leap_locate.html` (bloc `extra_js`)
- Test: `dashboard/tests.py` (`LeapPagesTests`)

**Interfaces:**
- Consumes: `escHtml` (main.js), `maplibregl`, `LocateView` (tâche 2).
- Produces: `window.SupplyChain.create(map, opts) → instance` avec
  - `opts.colorFor?: (commodity: string) => string` — à défaut, palette Locate par ordre alphabétique
  - `opts.legend?: { box: HTMLElement, list: HTMLElement }` — légende rendue par l'instance
  - `instance.addLayers(beforeLayerId?: string)` — sources, couches, évènements, données ; idempotent (au `load` et après chaque `setStyle`)
  - `instance.setData(locateData | null)` — `locateData` = réponse de `leap_locate_data`
  - `instance.setVisible(visible: boolean)`, `instance.isVisible() → boolean`
  - `instance.stop()` / `instance.resume()` — animation des flèches (à arrêter avant `setStyle`, sinon `idle` ne se déclenche jamais)
  - `instance.colors() → {commodity: color}`
  - Identifiants MapLibre inchangés : sources `ll-supplier-lines`, `ll-supplier-arrows`, `ll-suppliers` ; couches `<source>-layer` ; images `ll-arrow`, `ll-arrow-<hex>`.

- [ ] **Step 1 : Écrire le test**

Dans `LeapPagesTests`, ajouter :
```python
    def test_locate_page_loads_supply_chain_module(self):
        response = self.client.get(reverse('dashboard:leap_locate'))
        self.assertContains(response, 'dashboard/js/supply_chain.js')
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.LeapPagesTests`
Expected : FAIL `Couldn't find 'dashboard/js/supply_chain.js' in response`.

- [ ] **Step 3 : Créer `supply_chain.js`**

Le code des courbes, flèches et fournisseurs est celui de `leap_locate.js` (section « Fournisseurs »), encapsulé par instance.

```js
'use strict';

/* ───────────────────────── Supply chain ────────────────────────────────────
 * Chaque lien fournisseur → asset est dessiné comme une courbe de Bézier
 * quadratique. De petites flèches glissent le long de la courbe (du
 * fournisseur vers l'asset) via une boucle requestAnimationFrame qui met à
 * jour une source GeoJSON de points orientés. Les fournisseurs non détenus
 * sont des points cliquables.
 *
 * Partagé entre la page LEAP Locate et la Vue d'ensemble :
 *   const supply = SupplyChain.create(map, { colorFor, legend: { box, list } });
 *   supply.addLayers('id-couche-assets'); // au 'load' puis après chaque setStyle
 *   supply.setData(locateData);            // réponse de l'API leap-locate
 *   supply.setVisible(true);
 * Dépend de escHtml (main.js) et de maplibregl.
 * ------------------------------------------------------------------------ */
window.SupplyChain = (function () {
  const DEFAULT_COLOR = '#1f6f5c'; // teal, couleur par défaut / repli

  // Palette catégorielle par défaut pour distinguer les commodités.
  const PALETTE = [
    '#1f6f5c', '#c2603f', '#e0a83c', '#4f7cac', '#8a5a9e',
    '#6b8f3d', '#cf5d8a', '#3d9fa3', '#b5793b', '#7a6cc4',
  ];

  const ARROWS_PER_LINK = 4; // nombre de flèches simultanées sur chaque courbe
  const ARROW_SPEED = 0.006; // progression de la phase par frame (boucle 0→1)
  const CURVE_BOW = 0.18;    // amplitude de la courbure (0 = ligne droite)
  const CURVE_SAMPLES = 48;  // points échantillonnés pour tracer la courbe

  const SOURCE_IDS = ['ll-supplier-lines', 'll-supplier-arrows', 'll-suppliers'];
  const LAYER_IDS = ['ll-supplier-lines-layer', 'll-supplier-arrows-layer', 'll-suppliers-layer'];

  function emptyCollection() { return { type: 'FeatureCollection', features: [] }; }

  // Nom d'image MapLibre déterministe pour une couleur donnée.
  function arrowImageName(color) { return 'll-arrow-' + color.replace('#', ''); }

  // Point de contrôle : milieu décalé perpendiculairement au segment.
  function control(p0, p1) {
    const mx = (p0[0] + p1[0]) / 2;
    const my = (p0[1] + p1[1]) / 2;
    const dx = p1[0] - p0[0];
    const dy = p1[1] - p0[1];
    // Vecteur perpendiculaire (-dy, dx) → courbure constante du même côté.
    return [mx - dy * CURVE_BOW, my + dx * CURVE_BOW];
  }

  function bez(p0, c, p1, t) {
    const u = 1 - t;
    return [
      u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
      u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1],
    ];
  }

  function bezTangent(p0, c, p1, t) {
    const u = 1 - t;
    return [
      2 * u * (c[0] - p0[0]) + 2 * t * (p1[0] - c[0]),
      2 * u * (c[1] - p0[1]) + 2 * t * (p1[1] - c[1]),
    ];
  }

  // Cap (degrés, sens horaire depuis le nord) pour orienter l'icône flèche.
  function bearing(tan, lat) {
    const dx = tan[0] * Math.cos(lat * Math.PI / 180); // compression des longitudes
    const dy = tan[1];
    return Math.atan2(dx, dy) * 180 / Math.PI;
  }

  // Icône flèche dessinée sur un canvas, pointant vers le haut (= nord).
  function arrowImage(color) {
    const size = 18;
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const ctx = c.getContext('2d');
    ctx.fillStyle = color || DEFAULT_COLOR;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
    ctx.lineWidth = 1.3;
    ctx.beginPath();
    ctx.moveTo(size / 2, 2);          // pointe (haut)
    ctx.lineTo(size - 3, size - 4);   // aile droite
    ctx.lineTo(size / 2, size - 7);   // encoche
    ctx.lineTo(3, size - 4);          // aile gauche
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    return ctx.getImageData(0, 0, size, size);
  }

  function create(map, opts) {
    const options = opts || {};
    const state = {
      data: null,       // réponse leap-locate (suppliers, supplier_links)
      visible: false,
      links: [],        // courbes mises en cache pour l'animation
      colors: {},       // commodité → couleur des liens courants
      animFrame: null,  // id requestAnimationFrame de l'animation des flèches
      animPhase: 0,
      bound: false,     // évènements déjà liés à la carte ?
    };

    function linkFeatures() {
      return (state.data && state.data.supplier_links && state.data.supplier_links.features) || [];
    }

    // Commodité → couleur, par ordre alphabétique des commodités des liens.
    function buildColors() {
      const names = Array.from(
        new Set(linkFeatures().map(f => f.properties && f.properties.commodity).filter(Boolean))
      ).sort();
      const colors = {};
      names.forEach((n, i) => {
        colors[n] = options.colorFor ? options.colorFor(n) : PALETTE[i % PALETTE.length];
      });
      return colors;
    }

    // (Ré)enregistre une icône flèche par couleur de commodité + l'icône par défaut.
    function ensureArrowImages() {
      if (!map.hasImage('ll-arrow')) map.addImage('ll-arrow', arrowImage(DEFAULT_COLOR));
      const colors = new Set(Object.values(state.colors));
      colors.add(DEFAULT_COLOR);
      colors.forEach((col) => {
        const name = arrowImageName(col);
        if (!map.hasImage(name)) map.addImage(name, arrowImage(col));
      });
    }

    // Légende des couleurs de commodités, visible uniquement avec la supply chain.
    function renderLegend() {
      const legend = options.legend;
      if (!legend || !legend.box || !legend.list) return;
      const names = Object.keys(state.colors);
      if (!names.length) { legend.box.hidden = true; legend.list.innerHTML = ''; return; }
      legend.list.innerHTML = names.map(n =>
        `<li><span class="map-legend__dot" style="background:${state.colors[n]}"></span>${escHtml(n)}</li>`
      ).join('');
      legend.box.hidden = !state.visible;
    }

    function bindEvents() {
      if (state.bound) return;
      state.bound = true;
      map.on('click', 'll-suppliers-layer', (e) => {
        const p = e.features[0].properties;
        let comms = p.commodities;
        if (typeof comms === 'string') { try { comms = JSON.parse(comms); } catch (_) { comms = []; } }
        comms = comms || [];
        const list = comms.length
          ? `<div class="ll-popup__prods">${comms.map(c =>
              `<span class="ll-prod"><span class="ll-prod__name">${escHtml(c)}</span></span>`).join('')}</div>`
          : '';
        new maplibregl.Popup({ maxWidth: '260px' })
          .setLngLat(e.lngLat)
          .setHTML(
            `<div class="ll-popup"><strong>${escHtml(p.name)}</strong>` +
            `<div class="ll-popup__meta">${escHtml(p.country || '')}</div>` +
            `<div class="ll-popup__row">Fournisseur</div>${list}</div>`
          )
          .addTo(map);
      });
      map.on('mouseenter', 'll-suppliers-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'll-suppliers-layer', () => { map.getCanvas().style.cursor = ''; });
    }

    function updateArrows(phase) {
      const src = map.getSource('ll-supplier-arrows');
      if (!src) return;
      const feats = [];
      state.links.forEach(l => {
        for (let k = 0; k < ARROWS_PER_LINK; k++) {
          const t = (phase + k / ARROWS_PER_LINK) % 1;
          const pos = bez(l.p0, l.c, l.p1, t);
          const tan = bezTangent(l.p0, l.c, l.p1, t);
          feats.push({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: pos },
            properties: { bearing: bearing(tan, pos[1]), icon: l.icon },
          });
        }
      });
      src.setData({ type: 'FeatureCollection', features: feats });
    }

    // Recalcule courbes + points fournisseurs depuis state.data.
    function sync() {
      state.colors = buildColors();
      const links = [];
      const lineFeats = [];
      linkFeatures().forEach(f => {
        const [p0, p1] = f.geometry.coordinates;
        const c = control(p0, p1);
        const commodity = f.properties && f.properties.commodity;
        const color = state.colors[commodity] || DEFAULT_COLOR;
        links.push({ p0: p0, c: c, p1: p1, icon: arrowImageName(color) });
        const pts = [];
        for (let i = 0; i <= CURVE_SAMPLES; i++) pts.push(bez(p0, c, p1, i / CURVE_SAMPLES));
        lineFeats.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: pts },
          properties: { color: color },
        });
      });
      state.links = links;
      renderLegend();

      // Couches pas encore créées (carte en chargement) : addLayers resynchronisera.
      if (!map.getSource('ll-supplier-lines')) return;
      ensureArrowImages();
      map.getSource('ll-supplier-lines').setData({ type: 'FeatureCollection', features: lineFeats });
      const supFeats = (state.data && state.data.suppliers && state.data.suppliers.features) || [];
      map.getSource('ll-suppliers').setData({ type: 'FeatureCollection', features: supFeats });
      // Si l'animation tourne mais qu'il n'y a plus de lien, la source se vide.
      if (state.visible) updateArrows(state.animPhase);
    }

    // Sources, couches et évènements. Idempotent : selon le style, setStyle peut
    // conserver (diff) ou détruire les sources custom ; on ne recrée que ce qui
    // manque. Les courbes passent sous beforeLayerId (les points d'assets),
    // flèches et fournisseurs au-dessus.
    function addLayers(beforeLayerId) {
      ensureArrowImages();
      const vis = state.visible ? 'visible' : 'none';
      SOURCE_IDS.forEach((id) => {
        if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: emptyCollection() });
      });
      const before = beforeLayerId && map.getLayer(beforeLayerId) ? beforeLayerId : undefined;
      if (!map.getLayer('ll-supplier-lines-layer')) {
        map.addLayer({
          id: 'll-supplier-lines-layer',
          type: 'line',
          source: 'll-supplier-lines',
          layout: { 'line-cap': 'round', 'line-join': 'round', visibility: vis },
          paint: {
            'line-color': ['coalesce', ['get', 'color'], DEFAULT_COLOR],
            'line-width': 1.6,
            'line-opacity': 0.4,
            'line-dasharray': [2, 2],
          },
        }, before);
      }
      if (!map.getLayer('ll-supplier-arrows-layer')) {
        map.addLayer({
          id: 'll-supplier-arrows-layer',
          type: 'symbol',
          source: 'll-supplier-arrows',
          layout: {
            'icon-image': ['coalesce', ['get', 'icon'], 'll-arrow'],
            'icon-size': 0.85,
            'icon-rotate': ['get', 'bearing'],
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
            visibility: vis,
          },
        });
      }
      if (!map.getLayer('ll-suppliers-layer')) {
        map.addLayer({
          id: 'll-suppliers-layer',
          type: 'circle',
          source: 'll-suppliers',
          layout: { visibility: vis },
          paint: {
            'circle-radius': 5.5,
            'circle-color': DEFAULT_COLOR,
            'circle-opacity': 0.9,
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#ffffff',
          },
        });
      }
      bindEvents();
      sync();
    }

    function start() {
      if (state.animFrame) return;
      const step = () => {
        state.animPhase = (state.animPhase + ARROW_SPEED) % 1;
        updateArrows(state.animPhase);
        state.animFrame = requestAnimationFrame(step);
      };
      state.animFrame = requestAnimationFrame(step);
    }

    function stop() {
      if (state.animFrame) cancelAnimationFrame(state.animFrame);
      state.animFrame = null;
    }

    return {
      addLayers: addLayers,
      setData(data) { state.data = data; sync(); },
      setVisible(visible) {
        state.visible = visible;
        const vis = visible ? 'visible' : 'none';
        LAYER_IDS.forEach(id => {
          if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis);
        });
        renderLegend();
        if (visible) start(); else stop();
      },
      isVisible() { return state.visible; },
      colors() { return state.colors; },
      stop: stop,
      resume() { if (state.visible) start(); },
    };
  }

  return { create: create, DEFAULT_COLOR: DEFAULT_COLOR, PALETTE: PALETTE };
})();
```

- [ ] **Step 4 : Réécrire `leap_locate.js`**

Remplacer tout le fichier par le contenu suivant (combobox, repli du panneau et sélecteur de fond sont repris à l'identique ; toute la section « Fournisseurs » part dans `supply_chain.js`) :

```js
const LL_COMPANY_KEY = 'selected-company-id'; // partagé entre pages risques

const LL_STATE = {
  data: null,
  map: null,
  supply: null,        // instance SupplyChain (courbes, flèches, fournisseurs)
  assetsBound: false,  // évènements de la couche assets déjà liés ?
};

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl || !document.getElementById('leap-locate-map')) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  LL_STATE.map = llInitMap();
  llInitStyleToggle();
  llInitPanelToggle();
  llInitSupplierToggle();

  const savedId = parseInt(localStorage.getItem(LL_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    llFetch(savedId).then(data => llInitCombobox(companies, data || initialData));
  } else {
    if (initialData) llRender(initialData);
    llInitCombobox(companies, initialData);
  }
});

function llFetch(id) {
  return fetch(LEAP_LOCATE_API_URL.replace('/0/', '/' + id + '/'))
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => { llRender(data); return data; })
    .catch(err => console.error('leap_locate fetch failed:', err));
}

function llInitCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');
  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData && initialData.company_name) input.value = initialData.company_name;

  function buildList(filter) {
    const q = filter.toLowerCase();
    const matched = companies.filter(c => c.name.toLowerCase().includes(q));
    listbox.innerHTML = matched.map(c =>
      `<li role="option" data-id="${c.id}" class="company-combobox__option${c.id === selected ? ' selected' : ''}">${escHtml(c.name)}</li>`
    ).join('');
  }
  function openList() {
    buildList(input.value);
    listbox.removeAttribute('hidden');
    combobox.setAttribute('aria-expanded', 'true');
    if (chevron) chevron.style.transform = 'rotate(180deg)';
  }
  function closeList() {
    listbox.setAttribute('hidden', '');
    combobox.setAttribute('aria-expanded', 'false');
    if (chevron) chevron.style.transform = '';
  }

  input.addEventListener('focus', () => openList());
  input.addEventListener('input', () => { buildList(input.value); openList(); });

  listbox.addEventListener('click', (e) => {
    const opt = e.target.closest('[role="option"]');
    if (!opt) return;
    const id = parseInt(opt.dataset.id, 10);
    selected = id;
    input.value = opt.textContent;
    closeList();
    localStorage.setItem(LL_COMPANY_KEY, id);
    llFetch(id);
  });

  document.addEventListener('click', (e) => { if (!combobox.contains(e.target)) closeList(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeList(); });
}

function llInitPanelToggle() {
  const wrap   = document.querySelector('.ll-map-wrap');
  const toggle = document.getElementById('ll-panel-toggle');
  const reopen = document.getElementById('ll-panel-reopen');
  if (!wrap || !toggle || !reopen) return;

  function setCollapsed(collapsed) {
    wrap.classList.toggle('ll-collapsed', collapsed);
    toggle.setAttribute('aria-expanded', String(!collapsed));
    reopen.setAttribute('aria-expanded', String(!collapsed));
  }

  toggle.addEventListener('click', () => setCollapsed(true));
  reopen.addEventListener('click', () => setCollapsed(false));
}

function llInitStyleToggle() {
  // Cibler uniquement les boutons de fond de carte (data-layer) : la bascule
  // "Fournisseurs" partage la classe .map-layer-btn mais ne doit PAS déclencher
  // un setStyle (qui détruirait toutes les couches).
  document.querySelectorAll('.map-layer-btn[data-layer]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.map-layer-btn[data-layer]').forEach((b) => b.classList.remove('map-layer-btn--active'));
      btn.classList.add('map-layer-btn--active');
      const map = LL_STATE.map;
      if (!map) return;
      llApplyStyle(map, mapStyleFor(btn.dataset.layer));
    });
  });
}

// Rejoue un fond de carte puis reconstruit toutes nos couches. Partage entre
// le selecteur de fond et la bascule jour/nuit.
// isStyleLoaded() n'est pas fiable juste après setStyle : pour un style chargé
// par URL (classique/gris) il renvoie encore « true » pour l'ANCIEN style.
// « idle » est le seul signal fiable (nouveau style + tuiles prêts), mais il ne
// se déclenche jamais tant que l'animation des flèches tourne : on la stoppe le
// temps du rechargement, puis on reconstruit et on relance.
function llApplyStyle(map, style) {
  const supply = LL_STATE.supply;
  if (supply) supply.stop();
  map.setStyle(style);
  map.once('idle', () => {
    llAddSourceAndLayer(map);
    llSyncMapData();           // repeupler les assets avant les fournisseurs
    if (supply) {
      supply.addLayers('ll-assets-layer');
      supply.resume();
    }
  });
}

// Le fond suit le theme : meme bouton actif, variante claire ou sombre.
document.addEventListener('themechange', () => {
  if (LL_STATE.map) llApplyStyle(LL_STATE.map, mapStyleFor(activeMapStyleName()));
});

function llFeatures() {
  return (LL_STATE.data && LL_STATE.data.geojson) ? LL_STATE.data.geojson.features : [];
}

// Marqueurs colorés et dimensionnés par revenu associé (relatif au max courant).
function llStyledFeatures() {
  return LocateView.styleFeatures(llFeatures());
}

function llAddSourceAndLayer(map) {
  // Idempotent : selon le style, setStyle peut conserver (diff) ou détruire les
  // sources custom. On ne (re)crée que ce qui manque, et on ne lie les
  // évènements qu'une seule fois.
  if (!map.getSource('ll-assets')) {
    map.addSource('ll-assets', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  }
  if (!map.getLayer('ll-assets-layer')) {
    map.addLayer({
      id: 'll-assets-layer',
      type: 'circle',
      source: 'll-assets',
      paint: {
        'circle-radius': ['get', 'radius'],
        'circle-color': ['get', 'color'],
        'circle-opacity': 0.8,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff',
      },
    });
  }
  if (LL_STATE.assetsBound) return;
  LL_STATE.assetsBound = true;
  map.on('click', 'll-assets-layer', (e) => {
    new maplibregl.Popup({ maxWidth: '280px' })
      .setLngLat(e.lngLat)
      .setHTML(LocateView.popupHtml(e.features[0].properties))
      .addTo(map);
  });
  map.on('mouseenter', 'll-assets-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'll-assets-layer', () => { map.getCanvas().style.cursor = ''; });
}

function llInitMap() {
  const container = document.getElementById('leap-locate-map');
  if (!container || typeof maplibregl === 'undefined') return null;
  const map = new maplibregl.Map({
    container: 'leap-locate-map',
    style: mapStyleFor('classic'),
    center: [0, 20],
    zoom: 1.5,
  });
  LL_STATE.supply = SupplyChain.create(map, {
    legend: {
      box: document.getElementById('ll-commodity-legend'),
      list: document.getElementById('ll-commodity-legend-list'),
    },
  });
  map.on('load', () => {
    llAddSourceAndLayer(map);
    LL_STATE.supply.addLayers('ll-assets-layer');
    if (window._llPending) { map.getSource('ll-assets').setData(window._llPending); window._llPending = null; }
    LL_STATE.supply.resume();
  });
  return map;
}

function llSyncMapData() {
  const map = LL_STATE.map;
  const geojson = { type: 'FeatureCollection', features: llStyledFeatures() };
  if (!map) return;
  // Dès que la source existe on pousse les données : map.loaded() est faux juste
  // après un setStyle (tuiles en cours), ce qui mettait les assets en attente
  // indéfiniment et vidait la carte. La source suffit pour setData().
  const src = map.getSource('ll-assets');
  if (src) {
    src.setData(geojson);
  } else {
    window._llPending = geojson;
  }
}

function llRender(data) {
  LL_STATE.data = data;
  llSyncMapData();
  if (LL_STATE.supply) LL_STATE.supply.setData(data);
  llRenderList();
}

function llRenderList() {
  const el = document.getElementById('leap-locate-list');
  if (!el) return;
  const features = llFeatures();
  if (features.length === 0) {
    el.innerHTML = '<p class="ll-empty">Aucun site.</p>';
    return;
  }
  el.innerHTML = LocateView.listHtml(features);

  el.querySelectorAll('.ll-item--clickable').forEach(item => {
    item.addEventListener('click', () => {
      const lng = parseFloat(item.dataset.lng);
      const lat = parseFloat(item.dataset.lat);
      if (LL_STATE.map && !isNaN(lng) && !isNaN(lat)) {
        LL_STATE.map.flyTo({ center: [lng, lat], zoom: 9, duration: 1200 });
      }
    });
  });
}

// Bascule « Supply chain » : l'état du bouton est géré ici, les couches et la
// légende par l'instance SupplyChain.
function llInitSupplierToggle() {
  const btn = document.getElementById('ll-supplier-toggle');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const supply = LL_STATE.supply;
    if (!supply) return;
    const visible = !supply.isVisible();
    supply.setVisible(visible);
    btn.classList.toggle('map-layer-btn--active', visible);
    btn.setAttribute('aria-pressed', String(visible));
  });
}
```

- [ ] **Step 5 : Charger le module dans `leap_locate.html`**

Remplacer :
```django
<script src="{% static 'dashboard/js/locate_view.js' %}" defer></script>
```
par :
```django
<script src="{% static 'dashboard/js/locate_view.js' %}" defer></script>
<script src="{% static 'dashboard/js/supply_chain.js' %}" defer></script>
```

- [ ] **Step 6 : Contrôles**

Run : `node --check dashboard/static/dashboard/js/supply_chain.js && node --check dashboard/static/dashboard/js/leap_locate.js`
Expected : aucune sortie.
Run : `grep -n "LL_COMMODITY_PALETTE\|llStartArrowAnim\|llSyncSupplierData\|LL_SUPPLIER_COLOR" dashboard/static/dashboard/js/leap_locate.js`
Expected : aucune ligne.
Run : `venv/Scripts/python.exe manage.py test dashboard.tests.LeapPagesTests dashboard.tests.LeapLocateDataTests`
Expected : OK.

- [ ] **Step 7 : Commit**

```bash
git add dashboard/static/dashboard/js/supply_chain.js dashboard/static/dashboard/js/leap_locate.js dashboard/templates/dashboard/leap_locate.html dashboard/tests.py
git commit -m "refactor(locate): extrait la supply chain dans supply_chain.js

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4 : Module `PhysicalRiskView` + fragments + page Risque physique

**Files:**
- Create: `dashboard/static/dashboard/js/physical_risk_view.js`
- Create: `dashboard/templates/dashboard/_pr_panel.html`
- Create: `dashboard/templates/dashboard/_pr_detail_drawer.html`
- Modify: `dashboard/static/dashboard/js/physical_risk.js` (réécriture complète)
- Modify: `dashboard/templates/dashboard/physical_risk.html`
- Test: `dashboard/tests.py` (`PhysicalRiskPageViewTests`)

**Interfaces:**
- Consumes: `escHtml` (main.js) ; identifiants des fragments : `#pr-high-risk`, `#pr-avg-vuln`, `#pr-annual-loss`, `.pr-horizon`, `#pr-ranking`, `#pr-selected-hazard`, `#pr-table-body`.
- Produces: `window.PhysicalRiskView` =
  - `BAND_COLORS`, `band(score) → 'Low'|'Moderate'|'High'|'Critical'`
  - `hazard(data, key) → hazard | null`
  - `renderKpis(data, horizon: number)`, `renderLoss(data | null, horizon: number)`
  - `bindHorizon(group: HTMLElement | null, onChange: (years: number) => void)`
  - `renderRanking(data, selectedKey, onSelect: (key: string) => void)`, `markSelected(key)`
  - `renderTable(data | null, hazardKey)`
  - `buildGeojson(data | null, hazardKey) → FeatureCollection` (propriétés `name, hazardName, hazard, exposition, risk, radius, color`)
  - `popupHtml(props) → string`, `legendHtml() → string`
- Fragments : `_pr_panel.html` (sans paramètre), `_pr_detail_drawer.html` (paramètres optionnels `section_id`, `start_hidden`).

- [ ] **Step 1 : Écrire le test**

Dans `PhysicalRiskPageViewTests`, ajouter :
```python
    def test_page_uses_shared_fragments_and_module(self):
        response = self.client.get(reverse('dashboard:physical_risk'))
        self.assertTemplateUsed(response, 'dashboard/_pr_panel.html')
        self.assertTemplateUsed(response, 'dashboard/_pr_detail_drawer.html')
        html = response.content.decode()
        for element_id in ('pr-ranking', 'pr-table-body', 'pr-annual-loss'):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('dashboard/js/physical_risk_view.js', html)
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.PhysicalRiskPageViewTests`
Expected : FAIL `Template 'dashboard/_pr_panel.html' was not a template used to render the response.`

- [ ] **Step 3 : Créer `_pr_panel.html`**

```django
{% comment %}
Panneau du risque physique : KPI (dont la perte projetée 5 / 10 ans) et
classement des aléas. Inclus par la page Risque physique et la Vue d'ensemble ;
les identifiants sont ciblés par physical_risk_view.js.
{% endcomment %}
<div class="kpi-row">
  <div class="kpi-card">
    <div class="kpi-card__value data-tabular" id="pr-high-risk">—</div>
    <div class="kpi-card__label label-caps">Actifs à risque élevé</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-card__value data-tabular" id="pr-avg-vuln">—</div>
    <div class="kpi-card__label label-caps">Vulnérabilité moyenne</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-card__value data-tabular" id="pr-annual-loss">—</div>
    <div class="kpi-card__label label-caps">Perte projetée</div>
    <div class="pr-horizon" role="group" aria-label="Horizon de projection">
      <button type="button" class="pr-horizon__btn active" data-years="5" aria-pressed="true">5 ans</button>
      <button type="button" class="pr-horizon__btn" data-years="10" aria-pressed="false">10 ans</button>
    </div>
  </div>
</div>

<div id="pr-ranking" class="pr-ranking-list">
  <p class="pr-empty">Sélectionnez une entreprise.</p>
</div>
```

- [ ] **Step 4 : Créer `_pr_detail_drawer.html`**

```django
{% comment %}
Tiroir « Détail par actif » du risque physique, piloté par
physical_risk_view.js. Paramètres d'inclusion optionnels : section_id
(identifiant de la section) et start_hidden (masqué au chargement, pour la
Vue d'ensemble hors mode risque).
{% endcomment %}
<section class="map-drawer"{% if section_id %} id="{{ section_id }}"{% endif %}{% if start_hidden %} hidden{% endif %} aria-label="Détail par actif">
  <button type="button" class="map-drawer__handle" aria-expanded="false" aria-controls="pr-drawer-body">
    <span class="label-caps">Détail par actif</span>
    <span class="pr-table-card__hazard" id="pr-selected-hazard">—</span>
    <svg class="map-drawer__chevron" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4 10l4-4 4 4" stroke="currentColor" stroke-width="1.6"
            stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </button>
  <div class="map-drawer__body" id="pr-drawer-body">
    <div class="pr-table-wrap">
      <table class="pr-table">
        <thead>
          <tr>
            <th>Actif</th>
            <th>Hazard (%)</th>
            <th>Exposition</th>
            <th>Vulnérabilité (%)</th>
            <th>Risk</th>
          </tr>
        </thead>
        <tbody id="pr-table-body"></tbody>
      </table>
    </div>
  </div>
</section>
```

- [ ] **Step 5 : Créer `physical_risk_view.js`**

Rendu repris de `physical_risk.js` (KPI, classement, tableau, geojson, popup), paramétré par les données.

```js
'use strict';

// Rendu partagé du risque physique : bandes d'aléa, KPI, horizon, classement
// des aléas, tableau « Détail par actif », geojson des points, popup et
// légende. Les fonctions de rendu ciblent les identifiants des fragments
// _pr_panel.html et _pr_detail_drawer.html, inclus par la page Risque physique
// et par la Vue d'ensemble. Dépend de escHtml (main.js).
window.PhysicalRiskView = (function () {
  const BAND_COLORS = {
    Low:      '#dac1ba',
    Moderate: '#feb87c',
    High:     '#af5d43',
    Critical: '#91452d',
  };
  const BAND_LABELS = { Low: 'Faible', Moderate: 'Modéré', High: 'Élevé', Critical: 'Critique' };

  function band(score) {
    if (score >= 0.7) return 'Critical';
    if (score >= 0.5) return 'High';
    if (score >= 0.2) return 'Moderate';
    return 'Low';
  }

  function euro(v) {
    return Math.round(v).toLocaleString('fr-FR') + ' €';
  }

  function hazard(data, key) {
    if (!data || !key) return null;
    return (data.hazards || []).find(h => h.key === key) || null;
  }

  function renderKpis(data, horizon) {
    const highRisk = document.getElementById('pr-high-risk');
    if (highRisk) highRisk.textContent = data.kpis.assets_high_risk;
    const avgVuln = document.getElementById('pr-avg-vuln');
    if (avgVuln) {
      const av = data.kpis.avg_vulnerability;
      avgVuln.textContent = av != null ? (av * 100).toFixed(1) + '%' : '—';
    }
    renderLoss(data, horizon);
  }

  function renderLoss(data, horizon) {
    const el = document.getElementById('pr-annual-loss');
    if (!el || !data) return;
    const loss = data.kpis.annual_loss;
    el.textContent = loss != null ? euro(loss * horizon) : '—';
  }

  // Boutons 5 / 10 ans : état visuel, puis onChange(années).
  function bindHorizon(group, onChange) {
    if (!group) return;
    group.addEventListener('click', (e) => {
      const btn = e.target.closest('.pr-horizon__btn');
      if (!btn) return;
      group.querySelectorAll('.pr-horizon__btn').forEach(b => {
        const active = b === btn;
        b.classList.toggle('active', active);
        b.setAttribute('aria-pressed', String(active));
      });
      onChange(parseInt(btn.dataset.years, 10));
    });
  }

  // Classement des aléas ; il sert aussi de sélecteur : onSelect(clé) au clic.
  function renderRanking(data, selectedKey, onSelect) {
    const container = document.getElementById('pr-ranking');
    if (!container) return;
    if (!data.hazards || data.hazards.length === 0) {
      container.innerHTML = '<p class="pr-empty">Aucune donnée disponible.</p>';
      return;
    }
    const maxRisk = data.hazards.reduce((m, h) => h.avg_risk > m ? h.avg_risk : m, 0) || 1;
    container.innerHTML = data.hazards.map(h => {
      const pct = (h.avg_risk / maxRisk) * 100;
      const isSel = h.key === selectedKey;
      const sel = isSel ? ' pr-rank-row--selected' : '';
      return `
      <button type="button"
        class="pr-rank-row${sel}"
        data-key="${h.key}"
        aria-pressed="${isSel}">
        <span class="pr-rank-row__name">${escHtml(h.name)}</span>
        <span class="pr-rank-row__track">
          <span class="pr-rank-row__fill" style="width:${pct.toFixed(1)}%"></span>
        </span>
        <span class="pr-rank-row__val data-tabular">${euro(h.avg_risk)}</span>
      </button>`;
    }).join('');

    container.querySelectorAll('.pr-rank-row').forEach(row => {
      row.addEventListener('click', () => onSelect(row.dataset.key));
    });
  }

  function markSelected(key) {
    const container = document.getElementById('pr-ranking');
    if (!container) return;
    container.querySelectorAll('.pr-rank-row').forEach(row => {
      const active = row.dataset.key === key;
      row.classList.toggle('pr-rank-row--selected', active);
      row.setAttribute('aria-pressed', String(active));
    });
  }

  // Tableau « Détail par actif » pour l'aléa sélectionné.
  function renderTable(data, hazardKey) {
    const body = document.getElementById('pr-table-body');
    const hazardLabel = document.getElementById('pr-selected-hazard');
    if (!body) return;

    const current = hazard(data, hazardKey);
    if (hazardLabel) hazardLabel.textContent = current ? current.name : '—';

    if (!data || !current || data.assets.length === 0) {
      body.innerHTML = '<tr><td colspan="5" class="pr-empty">Aucun actif.</td></tr>';
      return;
    }

    const key = current.key;
    const vuln = current.vulnerability != null ? current.vulnerability : 0;
    const rows = data.assets.map(a => {
      const hz = a.risk[key] || 0;
      const risk = hz * a.exposition * vuln;
      return { name: a.name, hz: hz, expo: a.exposition, risk: risk,
               inventory: a.inventory || [] };
    }).sort((x, y) => y.risk - x.risk);

    const detail = current.vulnerability_detail || [];
    const detailRows = detail.length
      ? detail.map(d =>
          `<span class="pr-vuln-tooltip__row">
            <span class="pr-vuln-tooltip__policy">${escHtml(d.policy)}</span>
            <span class="pr-vuln-tooltip__val">${(d.value * 100).toFixed(1)}%</span>
          </span>`
        ).join('')
      : '<span class="pr-vuln-tooltip__note">Aucune politique renseignée</span>';

    body.innerHTML = rows.map(r => {
      const tooltip = `
        <span class="pr-vuln-tooltip" role="tooltip">
          <span class="pr-vuln-tooltip__title">Détail de la vulnérabilité</span>
          ${detailRows}
          <span class="pr-vuln-tooltip__result">Moyenne : ${(vuln * 100).toFixed(1)}%</span>
        </span>`;
      const invRows = r.inventory.map(e =>
        `<span class="pr-vuln-tooltip__row">
          <span class="pr-vuln-tooltip__policy">${escHtml(e.name)}</span>
          <span class="pr-vuln-tooltip__val">${e.value.toLocaleString('fr-FR')} ${escHtml(e.unit)}</span>
        </span>`).join('');
      const nameCell = r.inventory.length
        ? `<td class="pr-table__asset pr-table__asset--has-inv">${escHtml(r.name)}
            <span class="pr-inv-tooltip" role="tooltip">
              <span class="pr-vuln-tooltip__title">Inventaire mesuré</span>
              ${invRows}
            </span></td>`
        : `<td>${escHtml(r.name)}</td>`;
      return `
      <tr>
        ${nameCell}
        <td class="data-tabular">${(r.hz * 100).toFixed(1)}%</td>
        <td class="data-tabular">${euro(r.expo)}</td>
        <td class="data-tabular pr-table__vuln">${(vuln * 100).toFixed(1)}%${tooltip}</td>
        <td class="data-tabular pr-table__risk">${euro(r.risk)}</td>
      </tr>`;
    }).join('');
  }

  // Points : couleur par bande d'aléa, rayon proportionnel au risque en €.
  function buildGeojson(data, hazardKey) {
    const current = hazard(data, hazardKey);
    if (!data || !current) return { type: 'FeatureCollection', features: [] };

    const key = current.key;
    const vuln = current.vulnerability;
    const risks = data.assets.map(a => (a.risk[key] || 0) * a.exposition * vuln);
    const maxRisk = risks.reduce((m, v) => v > m ? v : m, 0) || 1;

    const features = data.assets.map((a, i) => {
      const hz = a.risk[key] || 0;
      const risk = risks[i];
      return {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [a.longitude, a.latitude] },
        properties: {
          name: a.name,
          hazardName: current.name,
          hazard: hz,
          exposition: a.exposition,
          risk: risk,
          radius: 6 + 18 * (risk / maxRisk),
          color: BAND_COLORS[band(hz)],
        },
      };
    });
    return { type: 'FeatureCollection', features: features };
  }

  function popupHtml(p) {
    return `<strong>${escHtml(p.name)}</strong><br>` +
      `${escHtml(p.hazardName)} : ${(Number(p.hazard) * 100).toFixed(1)}%<br>` +
      `Exposition : ${euro(Number(p.exposition))}<br>` +
      `Risk : ${euro(Number(p.risk))}`;
  }

  function legendHtml() {
    const items = Object.keys(BAND_COLORS).map(k =>
      `<li><span class="map-legend__dot" style="background:${BAND_COLORS[k]}"></span>${BAND_LABELS[k]}</li>`
    ).join('');
    return `<p class="map-legend__title">Risque physique</p><ul class="map-legend__list">${items}</ul>`;
  }

  return {
    BAND_COLORS, band, hazard, renderKpis, renderLoss, bindHorizon, renderRanking,
    markSelected, renderTable, buildGeojson, popupHtml, legendHtml,
  };
})();
```

- [ ] **Step 6 : Réécrire `physical_risk.js`**

Remplacer tout le fichier par :

```js
const PR_COMPANY_KEY = 'selected-company-id'; // shared localStorage slot across risk pages

const PR_STATE = {
  data: null,
  selectedKey: null,
  horizon: 5,
  map: null,
};

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl || !document.getElementById('pr-map')) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  PR_STATE.map = prInitMap();
  prInitHorizon();

  const savedId = parseInt(localStorage.getItem(PR_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    fetch(PHYSICAL_RISK_API_URL.replace('/0/', '/' + savedId + '/'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(data => { prRender(data); prInitCombobox(companies, data); })
      .catch(err => console.error('physical_risk fetch failed:', err));
  } else {
    if (initialData) prRender(initialData);
    prInitCombobox(companies, initialData);
  }
});


// ── Combobox (mirrors transition_risk.js) ──────────────────────────────────
function prInitCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');
  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData) input.value = initialData.company_name;

  function buildList(filter) {
    const q = filter.toLowerCase();
    const matched = companies.filter(c => c.name.toLowerCase().includes(q));
    listbox.innerHTML = matched.map(c =>
      `<li role="option" data-id="${c.id}" class="company-combobox__option${c.id === selected ? ' selected' : ''}">${escHtml(c.name)}</li>`
    ).join('');
  }
  function openList() {
    buildList(input.value);
    listbox.removeAttribute('hidden');
    combobox.setAttribute('aria-expanded', 'true');
    if (chevron) chevron.style.transform = 'rotate(180deg)';
  }
  function closeList() {
    listbox.setAttribute('hidden', '');
    combobox.setAttribute('aria-expanded', 'false');
    if (chevron) chevron.style.transform = '';
  }

  input.addEventListener('focus', () => openList());
  input.addEventListener('input', () => { buildList(input.value); openList(); });

  listbox.addEventListener('click', (e) => {
    const opt = e.target.closest('[role="option"]');
    if (!opt) return;
    const id = parseInt(opt.dataset.id, 10);
    selected = id;
    input.value = opt.textContent;
    closeList();
    localStorage.setItem(PR_COMPANY_KEY, id);
    fetch(PHYSICAL_RISK_API_URL.replace('/0/', '/' + id + '/'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(data => prRender(data))
      .catch(err => console.error('physical_risk fetch failed:', err));
  });

  document.addEventListener('click', (e) => {
    if (!combobox.contains(e.target)) closeList();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeList();
  });
}


// ── Horizon toggle (5 / 10 years) ──────────────────────────────────────────
function prInitHorizon() {
  PhysicalRiskView.bindHorizon(document.querySelector('.pr-horizon'), (years) => {
    PR_STATE.horizon = years;
    PhysicalRiskView.renderLoss(PR_STATE.data, PR_STATE.horizon);
  });
}


// ── Top-level render ───────────────────────────────────────────────────────
// KPI, classement, tableau, geojson et popup vivent dans physical_risk_view.js,
// partagé avec la Vue d'ensemble.
function prRender(data) {
  PR_STATE.data = data;
  PR_STATE.selectedKey = data.hazards && data.hazards.length ? data.hazards[0].key : null;
  PhysicalRiskView.renderKpis(data, PR_STATE.horizon);
  PhysicalRiskView.renderRanking(data, PR_STATE.selectedKey, prSelectHazard);
  prSyncMapData();
  PhysicalRiskView.renderTable(data, PR_STATE.selectedKey);
}

// Le classement sert de sélecteur d'aléa : carte et tableau suivent.
function prSelectHazard(key) {
  PR_STATE.selectedKey = key;
  PhysicalRiskView.markSelected(key);
  prSyncMapData();
  PhysicalRiskView.renderTable(PR_STATE.data, key);
}


// ── Map ────────────────────────────────────────────────────────────────────
function prInitMap() {
  const container = document.getElementById('pr-map');
  if (!container || typeof maplibregl === 'undefined') return null;

  const map = new maplibregl.Map({
    container: 'pr-map',
    style: mapStyleFor('classic'),
    center: [0, 20],
    zoom: 1.5,
  });

  map.on('load', () => {
    prAddSourceAndLayer(map);

    map.on('click', 'pr-assets-layer', (e) => {
      new maplibregl.Popup()
        .setLngLat(e.lngLat)
        .setHTML(PhysicalRiskView.popupHtml(e.features[0].properties))
        .addTo(map);
    });
    map.on('mouseenter', 'pr-assets-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'pr-assets-layer', () => { map.getCanvas().style.cursor = ''; });

    if (window._prPendingGeojson) {
      map.getSource('pr-assets').setData(window._prPendingGeojson);
      window._prPendingGeojson = null;
    }
  });

  return map;
}


// Source et couche des actifs. Idempotent : appele au chargement, puis apres
// chaque setStyle, qui les detruit. Les ecouteurs de clic/survol sont poses
// une seule fois dans prInitMap et survivent au changement de style.
function prAddSourceAndLayer(map) {
  if (!map.getSource('pr-assets')) {
    map.addSource('pr-assets', { type: 'geojson', data: prBuildGeojson() });
  }
  if (!map.getLayer('pr-assets-layer')) {
    map.addLayer({
      id: 'pr-assets-layer',
      type: 'circle',
      source: 'pr-assets',
      paint: {
        'circle-radius': ['get', 'radius'],
        'circle-color': ['get', 'color'],
        'circle-opacity': 0.75,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff',
      },
    });
  }
}


// Le fond suit le theme. « idle » est le seul signal fiable apres setStyle
// pour reconstruire la source et la couche, puis y repousser les donnees.
document.addEventListener('themechange', () => {
  const map = PR_STATE.map;
  if (!map) return;
  map.setStyle(mapStyleFor('classic'));
  map.once('idle', () => {
    prAddSourceAndLayer(map);
    // Repousser explicitement : au « idle » qui suit un setStyle, map.loaded()
    // peut encore etre faux, et prSyncMapData mettrait les donnees en attente
    // dans _prPendingGeojson sans que rien ne les reprenne.
    const src = map.getSource('pr-assets');
    if (src) src.setData(prBuildGeojson());
  });
});

function prBuildGeojson() {
  return PhysicalRiskView.buildGeojson(PR_STATE.data, PR_STATE.selectedKey);
}

function prSyncMapData() {
  const map = PR_STATE.map;
  const geojson = prBuildGeojson();
  if (!map) return;
  if (map.loaded() && map.getSource('pr-assets')) {
    map.getSource('pr-assets').setData(geojson);
  } else {
    window._prPendingGeojson = geojson;
  }
}
```

- [ ] **Step 7 : Brancher `physical_risk.html` sur les fragments**

(a) Dans `.map-panel__body`, remplacer tout le bloc `<div class="kpi-row"> … </div>` (3 KPI + horizon) **et** le `<div id="pr-ranking" class="pr-ranking-list">…</div>` qui le suit par :
```django
      {% include "dashboard/_pr_panel.html" %}
```

(b) Remplacer toute la `<section class="map-drawer" aria-label="Détail par actif"> … </section>` par :
```django
  {% include "dashboard/_pr_detail_drawer.html" %}
```

(c) Dans `extra_js`, remplacer :
```django
<script src="{% static 'dashboard/js/physical_risk.js' %}" defer></script>
```
par :
```django
<script src="{% static 'dashboard/js/physical_risk_view.js' %}" defer></script>
<script src="{% static 'dashboard/js/physical_risk.js' %}" defer></script>
```

- [ ] **Step 8 : Contrôles**

Run : `node --check dashboard/static/dashboard/js/physical_risk_view.js && node --check dashboard/static/dashboard/js/physical_risk.js`
Expected : aucune sortie.
Run : `grep -n "prFmtEuro\|PR_BAND_COLORS\|prRenderTable\|prRenderRanking" dashboard/static/dashboard/js/physical_risk.js`
Expected : aucune ligne.
Run : `venv/Scripts/python.exe manage.py test dashboard.tests.PhysicalRiskPageViewTests dashboard.tests.PhysicalRiskDataTests`
Expected : OK.

- [ ] **Step 9 : Commit**

```bash
git add dashboard/static/dashboard/js/physical_risk_view.js dashboard/static/dashboard/js/physical_risk.js dashboard/templates/dashboard/_pr_panel.html dashboard/templates/dashboard/_pr_detail_drawer.html dashboard/templates/dashboard/physical_risk.html dashboard/tests.py
git commit -m "refactor(risque-physique): extrait le rendu dans physical_risk_view.js et des fragments

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5 : Module `DetteView` + fragment KPI + page Dette sur `PieMarkers`

**Files:**
- Create: `dashboard/static/dashboard/js/dette_view.js`
- Create: `dashboard/templates/dashboard/_de_kpis.html`
- Modify: `dashboard/static/dashboard/js/dette_ecologique.js` (réécriture complète)
- Modify: `dashboard/templates/dashboard/dette_ecologique.html`
- Test: `dashboard/tests.py` (`DetteEcologiqueViewTests`)

**Interfaces:**
- Consumes: `escHtml` (main.js) ; `window.PieMarkers` (existant : `PALETTE`, `colorMap(commodities)`, `render(map, points, colors, handlers) → Marker[]`) ; identifiants du fragment `#de-total-lbiodiv`, `#de-year`, `#de-point-count`, `#de-point-count-label`, `#de-top-commodity`.
- Produces: `window.DetteView` =
  - `fmtLbiodiv(val: number) → string`
  - `renderKpis(data, mode: 'asset'|'region')`, `renderPointCount(data, mode)`
  - `legendItemsHtml(commodities, colors) → string` (8 premières, `<li class="de-legend__item">`)
  - `tooltipHandlers(tipEl, mapEl, colors) → { onEnter(point, e), onMove(e), onLeave() }` (format attendu par `PieMarkers.render`)
  - `assetListHtml(assets, colors) → string` (cartes `.ll-item.ll-item--clickable`, `data-lng` / `data-lat`)

- [ ] **Step 1 : Écrire le test**

Dans `DetteEcologiqueViewTests`, ajouter :
```python
    def test_dette_page_uses_kpi_fragment_and_modules(self):
        response = self.client.get(reverse('dashboard:dette_ecologique'))
        self.assertTemplateUsed(response, 'dashboard/_de_kpis.html')
        html = response.content.decode()
        self.assertIn('id="de-total-lbiodiv"', html)
        self.assertIn('dashboard/js/pie_markers.js', html)
        self.assertIn('dashboard/js/dette_view.js', html)
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.DetteEcologiqueViewTests`
Expected : FAIL `Template 'dashboard/_de_kpis.html' was not a template used to render the response.`

- [ ] **Step 3 : Créer `_de_kpis.html`**

```django
{% comment %}
KPI de la dette écologique. Inclus par la page Dette écologique et la Vue
d'ensemble ; les identifiants sont ciblés par dette_view.js.
{% endcomment %}
<div class="kpi-row">
  <div class="kpi-card">
    <div class="kpi-card__value data-tabular" id="de-total-lbiodiv">—</div>
    <div class="kpi-card__label label-caps">Lbiodiv total</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-card__value data-tabular" id="de-year">—</div>
    <div class="kpi-card__label label-caps">Année de référence</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-card__value data-tabular" id="de-point-count">—</div>
    <div class="kpi-card__label label-caps" id="de-point-count-label">Assets</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-card__value data-tabular" id="de-top-commodity">—</div>
    <div class="kpi-card__label label-caps">Top commodité</div>
  </div>
</div>
```

- [ ] **Step 4 : Créer `dette_view.js`**

```js
'use strict';

// Rendu partagé de la dette écologique : KPI (fragment _de_kpis.html), légende
// des commodités, infobulle des camemberts et liste d'assets au format Locate.
// Utilisé par la page Dette écologique et par le mode « Dette écologique » de
// la Vue d'ensemble. Les camemberts sont dessinés par PieMarkers.
// Dépend de escHtml (main.js).
window.DetteView = (function () {
  function fmtLbiodiv(val) {
    if (val >= 1e9) return '$' + (val / 1e9).toFixed(2) + ' G';
    if (val >= 1e6) return '$' + (val / 1e6).toFixed(2) + ' M';
    if (val >= 1e3) return '$' + (val / 1e3).toFixed(2) + ' k';
    return '$' + val.toFixed(2);
  }

  function fmtPct(v) { return (v * 100).toFixed(1) + '%'; }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function renderKpis(data, mode) {
    setText('de-total-lbiodiv', data.total_lbiodiv ? fmtLbiodiv(data.total_lbiodiv) : '—');
    setText('de-year', data.year != null ? data.year : '—');
    setText('de-top-commodity', data.commodities.length ? data.commodities[0].name : '—');
    renderPointCount(data, mode);
  }

  // Nombre de points affichés : assets ou régions selon le regroupement.
  function renderPointCount(data, mode) {
    const points = mode === 'asset' ? data.assets : data.regions;
    setText('de-point-count', points.length || '—');
    setText('de-point-count-label', mode === 'asset' ? 'Assets' : 'Régions');
  }

  function legendItemsHtml(commodities, colors) {
    return commodities.slice(0, 8).map(c => {
      const color = colors[c.name] || '#ccc';
      return (
        '<li class="de-legend__item">' +
        '<span class="de-legend__swatch" style="background:' + color + '"></span>' +
        '<span class="de-legend__name">' + escHtml(c.name) + '</span>' +
        '<span class="de-legend__pct">' + fmtPct(c.pct) + '</span>' +
        '</li>'
      );
    }).join('');
  }

  // Gestionnaires de survol pour PieMarkers.render : infobulle positionnée dans
  // le repère de mapEl (le canevas remplit la scène carte).
  function tooltipHandlers(tipEl, mapEl, colors) {
    function move(e) {
      if (!tipEl || !mapEl) return;
      const rect = mapEl.getBoundingClientRect();
      tipEl.style.left = (e.clientX - rect.left + 14) + 'px';
      tipEl.style.top  = (e.clientY - rect.top  + 14) + 'px';
    }
    return {
      onEnter(point, e) {
        if (!tipEl) return;
        const top3 = point.commodities.slice(0, 3);
        tipEl.innerHTML =
          '<strong>' + escHtml(point.name) + '</strong><br>' +
          'Lbiodiv : ' + fmtLbiodiv(point.total_lbiodiv) + '<br>' +
          top3.map(c =>
            '<span class="de-tooltip__swatch" style="background:' + (colors[c.name] || '#ccc') + '"></span>' +
            escHtml(c.name) + ' : ' + fmtPct(c.pct)
          ).join('<br>');
        tipEl.hidden = false;
        move(e);
      },
      onMove: move,
      onLeave() { if (tipEl) tipEl.hidden = true; },
    };
  }

  // Liste d'assets au format Locate : part du total, répartition par commodité
  // (pastilles aux couleurs des camemberts), Lbiodiv.
  function assetListHtml(assets, colors) {
    return assets.map(a => {
      const comms = a.commodities.map(c =>
        `<span class="ll-prod"><span class="ll-prod__name">` +
        `<span class="de-tooltip__swatch" style="background:${colors[c.name] || '#ccc'}"></span>` +
        `${escHtml(c.name)}</span><span class="ll-prod__qty">${fmtPct(c.pct)}</span></span>`
      ).join('');
      return `
      <div class="ll-item ll-item--clickable" data-lng="${a.longitude}" data-lat="${a.latitude}">
        <div class="ll-item__top">
          <span class="ll-item__name">${escHtml(a.name)}</span>
          <span class="ll-item__badge">${fmtPct(a.pct)} du total</span>
        </div>
        <div class="ll-item__prods">${comms}</div>
        <div class="ll-item__revenue">Lbiodiv&nbsp;: <strong>${fmtLbiodiv(a.total_lbiodiv)}</strong></div>
      </div>`;
    }).join('');
  }

  return { fmtLbiodiv, renderKpis, renderPointCount, legendItemsHtml, tooltipHandlers, assetListHtml };
})();
```

- [ ] **Step 5 : Réécrire `dette_ecologique.js`**

`PieMarkers.colorMap` et `PieMarkers.render` produisent exactement la même table de couleurs (même palette, tri `localeCompare`) et le même SVG (rayons 8–30 px ∝ √Lbiodiv) que les fonctions locales supprimées. Remplacer tout le fichier par :

```js
'use strict';

const DE_COMPANY_KEY = 'selected-company-id';

const DE_STATE = {
  data: null,
  mode: 'asset',
  map: null,
  markers: [],
  colorMap: {},
};

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('de-companies');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('de-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  DE_STATE.map = deInitMap();
  deInitToggle();

  const savedId = parseInt(localStorage.getItem(DE_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  DE_STATE.map.on('load', () => {
    if (savedExists && initialData && savedId !== initialData.company_id) {
      fetch(DE_API_URL.replace('/0/', '/' + savedId + '/'))
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(data => { deRender(data); deInitCombobox(companies, data); })
        .catch(err => { console.error('dette_ecologique fetch failed:', err); deInitCombobox(companies, initialData); });
    } else {
      if (initialData) deRender(initialData);
      deInitCombobox(companies, initialData);
    }
  });
});


function deInitMap() {
  return new maplibregl.Map({
    container: 'de-map',
    style: mapStyleFor('classic'),
    center: [0, 20],
    zoom: 1.5,
  });
}


// Les points sont des marqueurs DOM (maplibregl.Marker) : ils survivent a un
// setStyle, il suffit donc de rejouer le fond.
document.addEventListener('themechange', () => {
  if (DE_STATE.map) DE_STATE.map.setStyle(mapStyleFor('classic'));
});


function deInitToggle() {
  document.querySelectorAll('.de-toggle__btn').forEach(btn => {
    btn.addEventListener('click', () => {
      DE_STATE.mode = btn.dataset.mode;
      document.querySelectorAll('.de-toggle__btn').forEach(b => {
        const active = b === btn;
        b.classList.toggle('de-toggle__btn--active', active);
        b.setAttribute('aria-pressed', String(active));
      });
      if (DE_STATE.data) {
        deRenderMarkers(DE_STATE.data);
        DetteView.renderPointCount(DE_STATE.data, DE_STATE.mode);
      }
    });
  });
}


// KPI, légende et infobulle : dette_view.js ; camemberts : pie_markers.js.
function deRender(data) {
  DE_STATE.data = data;
  DE_STATE.colorMap = PieMarkers.colorMap(data.commodities);
  DetteView.renderKpis(data, DE_STATE.mode);
  const list = document.getElementById('de-legend-list');
  if (list) list.innerHTML = DetteView.legendItemsHtml(data.commodities, DE_STATE.colorMap);
  deRenderMarkers(data);
}


function deRenderMarkers(data) {
  DE_STATE.markers.forEach(m => m.remove());
  const points = DE_STATE.mode === 'asset' ? data.assets : data.regions;
  const handlers = DetteView.tooltipHandlers(
    document.getElementById('de-tooltip'), document.getElementById('de-map'), DE_STATE.colorMap
  );
  DE_STATE.markers = PieMarkers.render(DE_STATE.map, points, DE_STATE.colorMap, handlers);
}


function deInitCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');
  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData) input.value = initialData.company_name;

  function buildList(filter) {
    const q = filter.toLowerCase();
    listbox.innerHTML = companies
      .filter(c => c.name.toLowerCase().includes(q))
      .map(c =>
        '<li role="option" data-id="' + c.id + '" class="company-combobox__option' +
        (c.id === selected ? ' selected' : '') + '">' + escHtml(c.name) + '</li>'
      ).join('');
  }

  function openList() {
    buildList(input.value);
    listbox.removeAttribute('hidden');
    combobox.setAttribute('aria-expanded', 'true');
    if (chevron) chevron.style.transform = 'rotate(180deg)';
  }

  function closeList() {
    listbox.setAttribute('hidden', '');
    combobox.setAttribute('aria-expanded', 'false');
    if (chevron) chevron.style.transform = '';
  }

  input.addEventListener('focus', () => openList());
  input.addEventListener('input', () => { buildList(input.value); openList(); });

  listbox.addEventListener('click', e => {
    const opt = e.target.closest('[role="option"]');
    if (!opt) return;
    const id = parseInt(opt.dataset.id, 10);
    selected = id;
    input.value = opt.textContent;
    closeList();
    localStorage.setItem(DE_COMPANY_KEY, id);
    fetch(DE_API_URL.replace('/0/', '/' + id + '/'))
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => deRender(data))
      .catch(err => console.error('dette_ecologique fetch failed:', err));
  });

  document.addEventListener('click', e => {
    if (!combobox.contains(e.target)) closeList();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeList();
  });
}
```

- [ ] **Step 6 : Brancher `dette_ecologique.html`**

(a) Dans `.map-panel__body`, remplacer tout le bloc `<div class="kpi-row"> … </div>` (4 KPI) par :
```django
      {% include "dashboard/_de_kpis.html" %}
```
La `.de-toggle-row` qui suit reste inchangée.

(b) Dans `extra_js`, remplacer :
```django
<script src="{% static 'dashboard/js/dette_ecologique.js' %}" defer></script>
```
par :
```django
<script src="{% static 'dashboard/js/pie_markers.js' %}" defer></script>
<script src="{% static 'dashboard/js/dette_view.js' %}" defer></script>
<script src="{% static 'dashboard/js/dette_ecologique.js' %}" defer></script>
```

- [ ] **Step 7 : Contrôles**

Run : `node --check dashboard/static/dashboard/js/dette_view.js && node --check dashboard/static/dashboard/js/dette_ecologique.js`
Expected : aucune sortie.
Run : `grep -n "DE_PIE_COLORS\|deBuildPieEl\|deShowTooltip\|deFmtLbiodiv" dashboard/static/dashboard/js/dette_ecologique.js`
Expected : aucune ligne.
Run : `venv/Scripts/python.exe manage.py test dashboard.tests.DetteEcologiqueViewTests dashboard.tests.DetteEcologiqueDataTests`
Expected : OK.

- [ ] **Step 8 : Commit**

```bash
git add dashboard/static/dashboard/js/dette_view.js dashboard/static/dashboard/js/dette_ecologique.js dashboard/templates/dashboard/_de_kpis.html dashboard/templates/dashboard/dette_ecologique.html dashboard/tests.py
git commit -m "refactor(dette): extrait le rendu dans dette_view.js et passe par PieMarkers

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6 : Vue d'ensemble — contrôleur de modes, modes pays et asset

**Files:**
- Create: `dashboard/static/dashboard/js/overview.js`
- Modify: `dashboard/static/dashboard/js/main.js` (réécriture : ne garde que le transverse)
- Modify: `dashboard/templates/dashboard/index.html` (réécriture)
- Modify: `dashboard/static/dashboard/css/style.css`
- Test: `dashboard/tests.py` (import `re` + nouvelle classe `OverviewModesPageTests` en fin de fichier)

**Interfaces:**
- Consumes: `LocateView` (tâche 2) ; `properties.type` de Locate (tâche 1) ; globaux `main.js` : `escHtml`, `fmtNum`, `fmtEuro`, `fmtFootprint`, `mapStyleFor`, `activeMapStyleName`.
- Produces (utilisés par les tâches 7 et 8) :
  - globaux : `OV` (état), `OV_MODES` (registre `{title, source, drawer, renderPanel(data), mapFeatures(data) → Feature[], legendHtml(data) → string, popupHtml(props) → string | null}`), `OVERVIEW_API` (objet d'URL avec `/0/`, défini dans le template)
  - `ovLoad(source) → Promise<data>` (cache + dédoublonnage ; rejette avec `err.kind` `'stale'` ou `'session'`)
  - `ovCompanyReady() → Promise<companyData>` (données entreprise chargées **et** appliquées)
  - `ovApplyCompany(data)`, `ovSelectCompany(id, initialData | null)`, `ovRenderMode()`, `ovApplyMode(mode, data)`, `ovClearModeDisplay()`
  - `ovSetMapFeatures(features)`, `ovAddAssetsLayer()`, `ovApplyStyle(styleName)`, `ovStyled(feature, style) → Feature`, `ovFeatureList(geojson) → Feature[]`
  - `ovInitMap()`, `ovInitControls()`, `ovSetDrawer(kind: 'policy'|'risque'|null)`
  - Couche MapLibre `ov-assets-layer` (source `ov-assets`) ; propriétés lues : `color`, `radius`, `opacity`, `stroke`.
  - DOM : `.ov-mode-btn[data-mode]`, `[data-view="<mode>"]`, `#ov-panel-title`, `#ov-status`, `#ov-mode-legend`, `.ov-list`, `#policy-section`.

- [ ] **Step 1 : Écrire les tests**

En tête de `dashboard/tests.py`, ajouter `import re` sous `import json`. Puis, **à la fin du fichier**, ajouter :

```python
class OverviewModesPageTests(TestCase):
    """Vue d'ensemble : boutons de mode, verrouillage sans connexion, modules."""

    def setUp(self):
        self.company, *_ = _make_world()
        self.url = reverse('dashboard:index')

    def _login(self):
        user = get_user_model().objects.create_user(username='ovuser', password='pass')
        self.client.force_login(user)

    def _html(self):
        return self.client.get(self.url).content.decode()

    def _button(self, html, marker):
        """Balise ouvrante du <button> qui contient `marker` (ex. 'data-mode="asset"')."""
        match = re.search(r'<button\b[^>]*%s[^>]*>' % re.escape(marker), html)
        self.assertIsNotNone(match, f'bouton {marker} absent')
        return match.group(0)

    @staticmethod
    def _disabled(tag):
        return re.search(r'\sdisabled(?=[\s>=])', tag) is not None

    def test_page_stays_public(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_pays_open_and_asset_locked_for_anonymous(self):
        html = self._html()
        self.assertFalse(self._disabled(self._button(html, 'data-mode="pays"')))
        asset = self._button(html, 'data-mode="asset"')
        self.assertTrue(self._disabled(asset))
        self.assertIn('title="Connexion requise"', asset)

    def test_asset_enabled_when_authenticated(self):
        self._login()
        self.assertFalse(self._disabled(self._button(self._html(), 'data-mode="asset"')))

    def test_exposes_api_urls_and_modules(self):
        html = self._html()
        for name in ('dashboard:company_data', 'dashboard:leap_locate_data'):
            self.assertIn('"%s"' % reverse(name, kwargs={'pk': 0}), html)
        for script in ('locate_view.js', 'overview.js'):
            self.assertIn(f'dashboard/js/{script}', html)
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.OverviewModesPageTests`
Expected : FAIL `bouton data-mode="pays" absent` (et échecs similaires).

- [ ] **Step 3 : Réécrire `main.js`**

Tout ce qui est propre à la Vue d'ensemble part dans `overview.js` (step 5). `SELECTED_COMPANY_KEY` et `ASSET_TYPE_COLORS` **doivent** disparaître d'ici : `overview.js` les redéclare en `const` (voir Global Constraints). Remplacer tout le fichier par :

```js
// ── Écran de chargement ─────────────────────────────────────────────────────
// Masque le loader une fois la page entièrement chargée. Fallback à 4 s pour
// ne jamais bloquer l'affichage si une ressource externe (carte, police) traîne.
(function () {
  function hideLoader() {
    const loader = document.getElementById('page-loader');
    if (loader) loader.classList.add('is-hidden');
  }
  if (document.readyState === 'complete') {
    hideLoader();
  } else {
    window.addEventListener('load', hideLoader);
    setTimeout(hideLoader, 4000);
  }
  // Retour via le cache bfcache (bouton précédent) : le loader doit rester masqué.
  window.addEventListener('pageshow', (e) => { if (e.persisted) hideLoader(); });
})();

const SATELLITE_STYLE = {
  version: 8,
  sources: {
    satellite: {
      type: 'raster',
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 256,
      attribution: 'Tiles © Esri',
    },
  },
  layers: [{ id: 'satellite-bg', type: 'raster', source: 'satellite' }],
};

// Chaque fond a une variante par theme. « fiord » est le pendant sombre de
// « liberty » (style detaille), « dark » celui de « positron » (style gris).
// Le satellite ne change pas : l'imagerie est deja sombre.
const MAP_STYLES = {
  classic: {
    light: 'https://tiles.openfreemap.org/styles/liberty',
    dark: 'https://tiles.openfreemap.org/styles/fiord',
  },
  grayscale: {
    light: 'https://tiles.openfreemap.org/styles/positron',
    dark: 'https://tiles.openfreemap.org/styles/dark',
  },
  satellite: { light: SATELLITE_STYLE, dark: SATELLITE_STYLE },
};

function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

// Resout un nom de fond vers l'URL (ou l'objet) correspondant au theme actif.
// C'est le seul point d'entree : aucune page ne doit lire MAP_STYLES en direct.
function mapStyleFor(name) {
  const entry = MAP_STYLES[name] || MAP_STYLES.classic;
  return entry[currentTheme()];
}

// Nom du fond actuellement selectionne sur la page (bouton actif), ou
// « classic » quand la page n'expose pas de selecteur. Seuls les boutons de
// fond portent data-layer : la bascule supply chain partage .map-layer-btn.
function activeMapStyleName() {
  const btn = document.querySelector('.map-layer-btn--active[data-layer]');
  return (btn && btn.dataset.layer) || 'classic';
}

document.addEventListener('DOMContentLoaded', () => {

  // ── Sidebar toggle ──────────────────────────────────────────────────────
  const layout = document.getElementById('app-layout');
  const toggleBtn = document.getElementById('sidebar-toggle');

  if (layout && toggleBtn) {
    const STORAGE_KEY = 'sidebar-collapsed';
    const isCollapsed = localStorage.getItem(STORAGE_KEY) === '1';

    if (isCollapsed) applyCollapsed(true, false);

    toggleBtn.addEventListener('click', () => {
      const collapsed = layout.classList.toggle('sidebar-collapsed');
      localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
      toggleBtn.setAttribute('aria-expanded', String(!collapsed));
      toggleBtn.setAttribute('aria-label', collapsed ? 'Développer le menu' : 'Réduire le menu');
      if (collapsed) {
        document.querySelectorAll('.sidebar__nav-details').forEach(d => d.removeAttribute('open'));
      }
    });

    function applyCollapsed(collapsed, animate) {
      if (!animate) layout.style.transition = 'none';
      layout.classList.toggle('sidebar-collapsed', collapsed);
      toggleBtn.setAttribute('aria-expanded', String(!collapsed));
      toggleBtn.setAttribute('aria-label', collapsed ? 'Développer le menu' : 'Réduire le menu');
      if (collapsed) {
        document.querySelectorAll('.sidebar__nav-details').forEach(d => d.removeAttribute('open'));
      }
      if (!animate) requestAnimationFrame(() => { layout.style.transition = ''; });
    }
  }

  // ── Bascule jour / nuit ─────────────────────────────────────────────────
  // Le theme est deja pose par le script inline du <head> ; ici on ne gere
  // que le clic, la memorisation, et la diffusion aux cartes.
  const themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) {
    const syncBtn = () => {
      const dark = currentTheme() === 'dark';
      themeBtn.setAttribute('aria-pressed', String(dark));
      themeBtn.setAttribute('aria-label', dark ? 'Passer en mode jour' : 'Passer en mode nuit');
    };
    syncBtn();

    themeBtn.addEventListener('click', () => {
      const next = currentTheme() === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) { /* stockage indisponible */ }
      syncBtn();
      // Les cartes ecoutent cet evenement pour rejouer leur fond.
      document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: next } }));
    });
  }

  // ── Legacy test button ──────────────────────────────────────────────────
  const testBtn = document.getElementById('test-btn');
  if (testBtn) {
    testBtn.addEventListener('click', () => {
      const isActive = testBtn.classList.toggle('active');
      testBtn.setAttribute('aria-pressed', String(isActive));
    });
  }

  // ── User menu dropdown ──────────────────────────────────────────────────
  const userMenuBtn = document.getElementById('user-menu-btn');
  const userDropdown = document.getElementById('user-dropdown');

  if (userMenuBtn && userDropdown) {
    function openMenu() {
      userDropdown.removeAttribute('hidden');
      userMenuBtn.setAttribute('aria-expanded', 'true');
    }
    function closeMenu() {
      userDropdown.setAttribute('hidden', '');
      userMenuBtn.setAttribute('aria-expanded', 'false');
    }

    userMenuBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      userDropdown.hasAttribute('hidden') ? openMenu() : closeMenu();
    });

    document.addEventListener('click', closeMenu);
    userDropdown.addEventListener('click', (e) => e.stopPropagation());
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closeMenu(); userMenuBtn.focus(); }
    });
  }

});


function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtNum(n) {
  return Number(n).toLocaleString('fr-FR', { maximumFractionDigits: 0 });
}

function fmtEuro(n) {
  if (n >= 1e6) return `${(n / 1e6).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} M€`;
  if (n >= 1e3) return `${(n / 1e3).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} k€`;
  return `${n.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} €`;
}

function fmtFootprint(n) {
  if (n === 0) return '—';
  if (n >= 1e3) return `${(n / 1e3).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} k`;
  if (n >= 1) return n.toLocaleString('fr-FR', { maximumFractionDigits: 3 });
  const exp = Math.floor(Math.log10(Math.abs(n)));
  const mantissa = (n / Math.pow(10, exp)).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
  return `${mantissa}×10<sup>${exp}</sup>`;
}
```

- [ ] **Step 4 : Réécrire `index.html`**

Les modes risque et dette (tâche 7) et la supply chain (tâche 8) s'y ajouteront. Remplacer tout le fichier par :

```django
{% extends "base.html" %}
{% load static %}

{% block title %}Vue d'ensemble — Easybiodiv{% endblock %}

{% block layout_class %}map-page{% endblock %}

{% block nav_overview %}active{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css">
{% endblock %}

{% block header_left %}
<div class="company-combobox" id="company-combobox" role="combobox" aria-expanded="false" aria-haspopup="listbox"
  aria-owns="company-listbox">
  <span class="company-combobox__label label-caps">Entreprise</span>
  <div class="company-combobox__input-wrap">
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <circle cx="6" cy="6" r="4.5" stroke="currentColor" stroke-width="1.3" />
      <path d="M10 10l2.5 2.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" />
    </svg>
    <input type="text" id="company-search" class="company-combobox__input" placeholder="Rechercher une entreprise…"
      autocomplete="off" aria-autocomplete="list" aria-controls="company-listbox"
      aria-label="Sélectionner une entreprise">
    <svg class="company-combobox__chevron" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M3 5l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
    </svg>
  </div>
  <ul id="company-listbox" class="company-combobox__listbox" role="listbox" hidden></ul>
</div>
{% endblock header_left %}

{% block content %}
<div class="map-stage">
  <div class="map-stage__canvas" id="overview-map" aria-label="Carte des actifs"></div>

  <div class="map-stage__tl">
    <div class="map-layer-toggle" role="group" aria-label="Style de carte">
      <button class="map-layer-btn map-layer-btn--active" data-layer="classic">Classique</button>
      <button class="map-layer-btn" data-layer="grayscale">Gris</button>
      <button class="map-layer-btn" data-layer="satellite">Satellite</button>
    </div>
  </div>

  <div class="map-stage__bl">
    <div class="map-legend" id="ov-mode-legend" hidden aria-label="Légende de la carte"></div>
  </div>

  <aside class="map-panel" id="overview-panel" aria-label="Panneau de la carte">
    <div class="map-panel__header">
      <span class="label-caps map-panel__title" id="ov-panel-title">Exposition par pays</span>
      <button type="button" class="map-panel__toggle" aria-expanded="true"
              aria-controls="overview-panel" aria-label="Réduire le panneau">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M6 3l5 5-5 5" stroke="currentColor" stroke-width="1.6"
                stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
    </div>

    <div class="ov-modes" role="group" aria-label="Mode d'affichage de la carte">
      <button type="button" class="ov-mode-btn ov-mode-btn--active" data-mode="pays" aria-pressed="true">Exposition pays</button>
      <button type="button" class="ov-mode-btn" data-mode="asset" aria-pressed="false"{% if not user.is_authenticated %} disabled title="Connexion requise"{% endif %}>
        Exposition asset
        {% if not user.is_authenticated %}
        <svg class="ov-mode-btn__lock" width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <rect x="2.5" y="5.5" width="7" height="5" rx="1" stroke="currentColor" stroke-width="1.2" />
          <path d="M4 5.5V4a2 2 0 014 0v1.5" stroke="currentColor" stroke-width="1.2" />
        </svg>
        {% endif %}
      </button>
    </div>

    <div class="map-panel__body">
      <p class="country-panel__empty" id="ov-status" role="status" hidden></p>
      <div class="country-panel">
        <div class="country-panel__view country-panel__view--active" data-view="pays">
          <div class="country-panel__list" id="country-list">
            <p class="country-panel__empty">Sélectionnez une entreprise pour afficher l'exposition.</p>
          </div>
        </div>
        <div class="country-panel__view" data-view="asset">
          <div class="asset-list__toolbar" id="asset-list-toolbar" hidden>
            <select id="asset-type-filter" class="form-input asset-list__filter" aria-label="Filtrer par type d'actif">
              <option value="">Tous les types</option>
            </select>
            <button type="button" id="asset-sort-btn" class="asset-list__sort-btn" aria-pressed="false">
              <span id="asset-sort-label">Revenu décroissant</span>
              <svg class="asset-list__sort-icon" width="10" height="10" viewBox="0 0 14 14" fill="none"
                aria-hidden="true">
                <path d="M3 5l4 4 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"
                  stroke-linejoin="round" />
              </svg>
            </button>
          </div>
          <div class="ov-list" id="ov-asset-list"></div>
        </div>
      </div>
    </div>
  </aside>

  <button type="button" class="map-panel__reopen" aria-expanded="true" aria-controls="overview-panel"
          aria-label="Afficher le panneau de la carte">
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M3 4.5h12M3 9h12M3 13.5h12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
    </svg>
  </button>

  <section class="map-drawer" id="policy-section" hidden aria-label="Politiques">
    <button type="button" class="map-drawer__handle" aria-expanded="false" aria-controls="policy-drawer-body">
      <span class="label-caps">Politiques</span>
      <svg class="map-drawer__chevron" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path d="M4 10l4-4 4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"
              stroke-linejoin="round" />
      </svg>
    </button>
    <div class="map-drawer__body" id="policy-drawer-body">
      <div class="policy-types-row" id="policy-types-row"></div>
    </div>
  </section>
</div>
{% endblock %}

{% block extra_js %}
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js" defer></script>
{{ companies|json_script:"companies-data" }}
{{ initial_data|json_script:"initial-data" }}
<script>
  var OVERVIEW_API = {
    company: "{% url 'dashboard:company_data' pk=0 %}",
    locate: "{% url 'dashboard:leap_locate_data' pk=0 %}"
  };
</script>
<script src="{% static 'dashboard/js/map_layout.js' %}" defer></script>
<script src="{% static 'dashboard/js/locate_view.js' %}" defer></script>
<script src="{% static 'dashboard/js/overview.js' %}" defer></script>
{% endblock %}
```

- [ ] **Step 5 : Créer `overview.js`**

Reprend du `main.js` d'origine : palette `ASSET_TYPE_COLORS`, légende des types, popup d'asset, liste des pays, politiques et `scoreColor`, combobox (renommés avec le préfixe `ov`). Nouveau : registre de modes, chargement à la demande avec cache, couche unique `ov-assets-layer`. Contenu complet du fichier :

```js
'use strict';

// ── Vue d'ensemble : carte multi-modes ──────────────────────────────────────
// Les boutons du panneau droit basculent la carte entre plusieurs modes. Chaque
// mode charge à la demande les données de sa page de référence (API existantes,
// URL dans OVERVIEW_API), puis rend son panneau, ses points, sa légende et son
// tiroir bas via les modules partagés. Les réponses sont gardées en cache pour
// l'entreprise courante ; changer d'entreprise vide le cache.

const SELECTED_COMPANY_KEY = 'selected-company-id'; // partagé entre pages
const OV_MODE_KEY = 'overview-mode';

// Palette catégorielle par type d'asset — teintes fixes dérivées de la charte
// Terra Insight, validées (bande de clarté OKLCH, plancher de chroma, séparation
// daltonisme protan/deutan sur toutes les paires, contraste). Ordre figé : ne pas
// réordonner ni cycler ces teintes.
const ASSET_TYPE_COLORS = {
  Smelter: '#a32c33',
  Mine: '#cf6228',
  Factory: '#d0901e',
  Paper: '#3e6200',
  Forest: '#47a566',
  Renewable: '#007149',
  Airport: '#28a0c7',
  Refinery: '#374b99',
  Aluminium: '#8d6cc2',
  Office: '#873e79',
};
const ASSET_TYPE_FALLBACK_COLOR = ASSET_TYPE_COLORS.Factory;

const OV = {
  map: null,
  companyId: null,
  mode: 'pays',
  cache: {},           // source ('company', 'locate'…) → réponse de l'API
  pending: {},         // source → requête en cours (évite les doublons)
  companyReady: null,  // promesse : données entreprise chargées et appliquées
  features: [],        // points du mode actif (source 'ov-assets')
  countryCoords: {},   // pays → somme des coordonnées de ses actifs (zoom)
  assetFilter: '',     // mode asset : type d'actif filtré ('' = tous)
  assetSortDir: 'desc',
};

// Registre des modes. source : clé de OVERVIEW_API ; drawer : tiroir bas
// ('policy' ou 'risque') ; popupHtml : null si le mode n'a pas de popup.
const OV_MODES = {
  pays: {
    title: 'Exposition par pays',
    source: 'company',
    drawer: 'policy',
    renderPanel: ovRenderCountries,
    mapFeatures: ovPaysFeatures,
    legendHtml: ovPaysLegendHtml,
    popupHtml: ovPaysPopupHtml,
  },
  asset: {
    title: 'Sites localisés',
    source: 'locate',
    drawer: 'policy',
    renderPanel: ovRenderAssetPanel,
    mapFeatures: ovAssetFeatures,
    legendHtml: () => LocateView.legendHtml(),
    popupHtml: (p) => LocateView.popupHtml(p),
  },
};

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl || !document.getElementById('overview-map')) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  ovInitMap();
  ovInitControls();

  let storedMode = null;
  try { storedMode = localStorage.getItem(OV_MODE_KEY); } catch (e) { /* stockage indisponible */ }
  OV.mode = ovValidMode(storedMode);
  ovSyncModeUi();

  const savedId = parseInt(localStorage.getItem(SELECTED_COMPANY_KEY), 10);
  const saved = savedId ? companies.find((c) => c.id === savedId) : null;

  if (saved && initialData && savedId !== initialData.company_id) {
    ovInitCombobox(companies, { company_name: saved.name });
    ovSelectCompany(savedId, null);
  } else if (initialData) {
    ovInitCombobox(companies, initialData);
    ovSelectCompany(initialData.company_id, initialData);
  } else {
    ovInitCombobox(companies, null);
    ovRenderMode();
  }
});


// ── Carte ──────────────────────────────────────────────────────────────────

function ovInitMap() {
  const map = new maplibregl.Map({
    container: 'overview-map',
    style: mapStyleFor('classic'),
    center: [0, 20],
    zoom: 1.5,
  });
  OV.map = map;

  map.on('load', () => {
    ovAddAssetsLayer();
    // Écouteurs délégués à la couche : posés une fois, ils survivent aux setStyle.
    map.on('click', 'ov-assets-layer', (e) => {
      const popupHtml = OV_MODES[OV.mode].popupHtml;
      if (!popupHtml) return;
      new maplibregl.Popup({ maxWidth: '300px' })
        .setLngLat(e.lngLat)
        .setHTML(popupHtml(e.features[0].properties))
        .addTo(map);
    });
    map.on('mouseenter', 'ov-assets-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'ov-assets-layer', () => { map.getCanvas().style.cursor = ''; });
  });
}

// Source et couche des points. Idempotent : appelé au chargement puis après
// chaque setStyle, qui peut les détruire. Couleur, rayon, opacité et contour
// sont lus dans les propriétés calculées par le mode actif.
function ovAddAssetsLayer() {
  const map = OV.map;
  if (!map.getSource('ov-assets')) {
    map.addSource('ov-assets', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: OV.features },
    });
  }
  if (!map.getLayer('ov-assets-layer')) {
    map.addLayer({
      id: 'ov-assets-layer',
      type: 'circle',
      source: 'ov-assets',
      paint: {
        'circle-radius': ['get', 'radius'],
        'circle-color': ['get', 'color'],
        'circle-opacity': ['coalesce', ['get', 'opacity'], 1],
        'circle-stroke-width': ['coalesce', ['get', 'stroke'], 1.5],
        'circle-stroke-color': '#ffffff',
      },
    });
  }
}

function ovSetMapFeatures(features) {
  OV.features = features;
  const src = OV.map && OV.map.getSource('ov-assets');
  if (src) src.setData({ type: 'FeatureCollection', features: features });
}

// Rejoue un fond (sélecteur ou bascule jour/nuit) puis reconstruit nos couches.
// « idle » est le seul signal fiable après setStyle (voir leap_locate.js).
function ovApplyStyle(styleName) {
  const map = OV.map;
  if (!map) return;
  map.setStyle(mapStyleFor(styleName));
  map.once('idle', () => {
    ovAddAssetsLayer();
  });
}

// Le fond suit le theme : meme bouton actif, variante claire ou sombre.
document.addEventListener('themechange', () => {
  if (OV.map) ovApplyStyle(activeMapStyleName());
});


// ── Contrôles ──────────────────────────────────────────────────────────────

function ovInitControls() {
  document.querySelectorAll('.ov-mode-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      // Un clic sur le mode déjà actif ne relance le chargement qu'après une erreur.
      const status = document.getElementById('ov-status');
      if (btn.dataset.mode === OV.mode && status && status.hidden) return;
      ovSetMode(btn.dataset.mode);
    });
  });

  // Fonds de carte : seulement les boutons [data-layer] (pas la supply chain).
  document.querySelectorAll('.map-layer-btn[data-layer]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.map-layer-btn[data-layer]')
        .forEach((b) => b.classList.remove('map-layer-btn--active'));
      btn.classList.add('map-layer-btn--active');
      ovApplyStyle(btn.dataset.layer);
    });
  });

  // Pays → zoom sur le barycentre de ses actifs.
  const countryList = document.getElementById('country-list');
  if (countryList) {
    countryList.addEventListener('click', (e) => {
      const item = e.target.closest('[data-country]');
      if (!item || !OV.map) return;
      const coords = OV.countryCoords[item.dataset.country];
      if (!coords) return;
      OV.map.flyTo({
        center: [coords.sumLng / coords.n, coords.sumLat / coords.n],
        zoom: 5,
        duration: 1200,
      });
    });
  }

  // Listes d'assets (modes asset et dette) → zoom sur l'asset.
  document.querySelectorAll('.ov-list').forEach((list) => {
    list.addEventListener('click', (e) => {
      const item = e.target.closest('[data-lng]');
      if (!item || !OV.map) return;
      const lng = parseFloat(item.dataset.lng);
      const lat = parseFloat(item.dataset.lat);
      if (isNaN(lng) || isNaN(lat)) return;
      OV.map.flyTo({ center: [lng, lat], zoom: 9, duration: 1200 });
    });
  });

  // Mode asset : filtre par type d'actif + tri par revenu associé.
  const filter = document.getElementById('asset-type-filter');
  if (filter) {
    filter.addEventListener('change', () => {
      OV.assetFilter = filter.value;
      ovRenderAssetList();
    });
  }
  const sortBtn = document.getElementById('asset-sort-btn');
  if (sortBtn) {
    sortBtn.addEventListener('click', () => {
      OV.assetSortDir = OV.assetSortDir === 'desc' ? 'asc' : 'desc';
      const asc = OV.assetSortDir === 'asc';
      sortBtn.setAttribute('aria-pressed', String(asc));
      document.getElementById('asset-sort-label').textContent =
        asc ? 'Revenu croissant' : 'Revenu décroissant';
      ovRenderAssetList();
    });
  }
}


// ── Modes ──────────────────────────────────────────────────────────────────

// Mode demandé s'il existe et n'est pas verrouillé, sinon « pays ».
function ovValidMode(mode) {
  if (!Object.prototype.hasOwnProperty.call(OV_MODES, mode)) return 'pays';
  const btn = document.querySelector(`.ov-mode-btn[data-mode="${mode}"]`);
  return btn && !btn.disabled ? mode : 'pays';
}

function ovSetMode(mode) {
  OV.mode = ovValidMode(mode);
  try { localStorage.setItem(OV_MODE_KEY, OV.mode); } catch (e) { /* stockage indisponible */ }
  ovSyncModeUi();
  ovRenderMode();
}

function ovSyncModeUi() {
  document.querySelectorAll('.ov-mode-btn').forEach((b) => {
    const active = b.dataset.mode === OV.mode;
    b.classList.toggle('ov-mode-btn--active', active);
    b.setAttribute('aria-pressed', String(active));
  });
  const title = document.getElementById('ov-panel-title');
  if (title) title.textContent = OV_MODES[OV.mode].title;
}

// Rend le mode actif : données (cache ou réseau), puis panneau, carte, légende
// et tiroir. Un rendu devenu obsolète (mode ou entreprise changés) est ignoré.
function ovRenderMode() {
  const mode = OV.mode;
  const cfg = OV_MODES[mode];
  if (OV.companyId == null) {
    ovShowView(mode);
    return;
  }
  if (!OV.cache.company || !OV.cache[cfg.source]) {
    ovClearModeDisplay();
    ovShowStatus('Chargement…');
  }
  Promise.all([ovCompanyReady(), ovLoad(cfg.source)])
    .then(([, data]) => { if (OV.mode === mode) ovApplyMode(mode, data); })
    .catch((err) => {
      if (err && err.kind === 'stale') return;
      console.error(`overview : chargement du mode « ${mode} » impossible`, err);
      if (OV.mode !== mode) return;
      ovShowStatus(err && err.kind === 'session'
        ? 'Session expirée — reconnectez-vous.'
        : 'Impossible de charger les données.');
    });
}

function ovApplyMode(mode, data) {
  const cfg = OV_MODES[mode];
  ovShowStatus('');
  ovShowView(mode);
  cfg.renderPanel(data);
  ovSetMapFeatures(cfg.mapFeatures(data));
  ovSetLegend(cfg.legendHtml(data));
  ovSetDrawer(cfg.drawer);
}

// Vide la carte, la légende et les tiroirs le temps d'un chargement.
function ovClearModeDisplay() {
  ovSetMapFeatures([]);
  ovSetLegend('');
  ovSetDrawer(null);
}

function ovShowStatus(message) {
  const el = document.getElementById('ov-status');
  if (!el) return;
  el.textContent = message;
  el.hidden = !message;
  if (message) {
    document.querySelectorAll('[data-view]')
      .forEach((v) => v.classList.remove('country-panel__view--active'));
  }
}

function ovShowView(mode) {
  document.querySelectorAll('[data-view]').forEach((v) => {
    v.classList.toggle('country-panel__view--active', v.dataset.view === mode);
  });
}

function ovSetLegend(html) {
  const el = document.getElementById('ov-mode-legend');
  if (!el) return;
  el.innerHTML = html;
  el.hidden = !html;
}

// Tiroir bas : « Politiques » (si l'entreprise en a) ou « Détail par actif ».
function ovSetDrawer(kind) {
  const policy = document.getElementById('policy-section');
  const detail = document.getElementById('pr-detail-section');
  const company = OV.cache.company;
  const hasPolicies = !!(company && company.policies && company.policies.length);
  if (policy) policy.hidden = !(kind === 'policy' && hasPolicies);
  if (detail) detail.hidden = kind !== 'risque';
}


// ── Données ────────────────────────────────────────────────────────────────

function ovSelectCompany(id, initialData) {
  OV.companyId = id;
  OV.cache = initialData ? { company: initialData } : {};
  OV.pending = {};
  OV.companyReady = null;
  ovRenderMode();
}

function ovError(kind) {
  const err = new Error(kind);
  err.kind = kind;
  return err;
}

// Réponse de l'API `source` pour l'entreprise courante, depuis le cache ou le
// réseau. Rejette avec kind 'stale' si l'entreprise a changé entre-temps, et
// 'session' si la réponse n'est pas du JSON (redirection vers la connexion).
function ovLoad(source) {
  if (OV.cache[source]) return Promise.resolve(OV.cache[source]);
  if (OV.pending[source]) return OV.pending[source];
  const companyId = OV.companyId;
  const url = OVERVIEW_API[source].replace('/0/', `/${companyId}/`);
  const request = fetch(url, { headers: { Accept: 'application/json' } })
    .then((r) => {
      if (r.redirected) throw ovError('session');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      if (!(r.headers.get('Content-Type') || '').includes('application/json')) {
        throw ovError('session');
      }
      return r.json();
    })
    .then((data) => {
      if (companyId !== OV.companyId) throw ovError('stale');
      OV.cache[source] = data;
      return data;
    })
    .catch((err) => {
      throw companyId !== OV.companyId ? ovError('stale') : err;
    })
    .finally(() => {
      if (OV.pending[source] === request) delete OV.pending[source];
    });
  OV.pending[source] = request;
  return request;
}

// Données entreprise chargées puis appliquées (barycentres, politiques…), une
// fois par entreprise. En cas d'échec, la promesse est oubliée : un nouveau
// rendu réessaiera.
function ovCompanyReady() {
  if (OV.companyReady) return OV.companyReady;
  const ready = ovLoad('company').then((data) => {
    ovApplyCompany(data);
    return data;
  });
  OV.companyReady = ready;
  ready.catch(() => { if (OV.companyReady === ready) OV.companyReady = null; });
  return ready;
}

function ovApplyCompany(data) {
  OV.countryCoords = {};
  ovFeatureList(data.geojson).forEach((f) => {
    const country = f.properties.country;
    const [lng, lat] = f.geometry.coordinates;
    if (!OV.countryCoords[country]) OV.countryCoords[country] = { sumLat: 0, sumLng: 0, n: 0 };
    OV.countryCoords[country].sumLat += lat;
    OV.countryCoords[country].sumLng += lng;
    OV.countryCoords[country].n += 1;
  });
  ovRenderPolicies(data);
}

function ovFeatureList(geojson) {
  return geojson && geojson.features ? geojson.features : [];
}

// Copie d'un point avec les propriétés de style lues par ov-assets-layer.
function ovStyled(feature, style) {
  return {
    type: 'Feature',
    geometry: feature.geometry,
    properties: Object.assign({}, feature.properties, style),
  };
}


// ── Mode « Exposition pays » ───────────────────────────────────────────────

function ovRenderCountries(data) {
  const list = document.getElementById('country-list');
  if (!list) return;
  if (data.countries.length === 0) {
    list.innerHTML = '<p class="country-panel__empty">Aucun actif pour cette entreprise.</p>';
    return;
  }
  list.innerHTML = data.countries
    .map((c) => {
      const hasCoords = !!OV.countryCoords[c.name];
      const tags = c.commodities
        .map((cm, i) =>
          `<span class="country-item__tag${i === 0 ? ' country-item__tag--primary' : ''}">${escHtml(cm.name)} ×${cm.count}</span>`
        )
        .join('');
      return `
        <div class="country-item${hasCoords ? ' country-item--clickable' : ''}" data-country="${escHtml(c.name)}">
          <div class="country-item__top">
            <span class="country-item__name">${escHtml(c.name)}</span>
            <span class="country-item__count">${c.asset_count} actif${c.asset_count > 1 ? 's' : ''}</span>
          </div>
          <div class="country-item__tags">${tags}</div>
        </div>`;
    })
    .join('');
}

function ovPaysFeatures(data) {
  return ovFeatureList(data.geojson).map((f) => ovStyled(f, {
    color: ASSET_TYPE_COLORS[f.properties.type] || ASSET_TYPE_FALLBACK_COLOR,
    radius: 7,
    opacity: 1,
    stroke: 2,
  }));
}

// Légende dynamique : ne liste que les types réellement présents dans les
// données affichées, dans l'ordre fixe de la palette (jamais alphabétique).
function ovPaysLegendHtml(data) {
  const present = new Set(ovFeatureList(data.geojson).map((f) => f.properties.type).filter(Boolean));
  const items = Object.keys(ASSET_TYPE_COLORS).filter((t) => present.has(t));
  if (items.length === 0) return '';
  return `
    <p class="map-legend__title">Type d'actif</p>
    <ul class="map-legend__list">
      ${items.map((t) => `
        <li>
          <span class="map-legend__dot" style="background:${ASSET_TYPE_COLORS[t]}"></span>
          <span>${escHtml(t)}</span>
        </li>
      `).join('')}
    </ul>
  `;
}

function ovPaysPopupHtml(p) {
  // Sur une source GeoJSON, MapLibre sérialise les propriétés non primitives.
  let productions = p.productions;
  if (typeof productions === 'string') {
    try { productions = JSON.parse(productions); } catch (_) { productions = []; }
  }
  productions = productions || [];

  const metaParts = [p.country, p.region].filter(Boolean);
  const yearLabel = p.year ? ` — ${p.year}` : '';

  const prodsHtml = productions.length > 0
    ? productions.map((prod) =>
        `<div class="asset-popup__prod-row">
          <span class="asset-popup__prod-dot"></span>
          <span class="asset-popup__prod-name">${escHtml(prod.commodity)}</span>
          <span class="asset-popup__prod-qty">${fmtNum(prod.quantity)}&nbsp;${escHtml(prod.unit)}</span>
        </div>`
      ).join('')
    : '<p class="asset-popup__no-data">Aucune production enregistrée</p>';

  const footprintVal = (typeof p.footprint === 'number' && p.footprint > 0)
    ? fmtFootprint(p.footprint)
    : '—';

  const detteVal = (typeof p.dette_eco === 'number' && p.dette_eco > 0)
    ? fmtEuro(p.dette_eco)
    : '—';

  return `
    <div class="asset-popup">
      <div class="asset-popup__header">
        <div class="asset-popup__name">${escHtml(p.name)}</div>
        <div class="asset-popup__meta">${metaParts.map(escHtml).join(' · ')}</div>
      </div>
      <div class="asset-popup__body">
        <div class="asset-popup__section-title">Productions${yearLabel}</div>
        ${prodsHtml}
        <div class="asset-popup__divider"></div>
        <div class="asset-popup__metrics">
          <div class="asset-popup__metric">
            <div class="asset-popup__metric-value">${footprintVal}</div>
            <div class="asset-popup__metric-label">Empreinte biodiversité</div>
          </div>
          <div class="asset-popup__metric asset-popup__metric--risk">
            <div class="asset-popup__metric-value">${detteVal}</div>
            <div class="asset-popup__metric-label">Dette écologique</div>
          </div>
        </div>
      </div>
    </div>`;
}


// ── Mode « Exposition asset » ──────────────────────────────────────────────

function ovAssetFeatures(data) {
  return LocateView.styleFeatures(ovFeatureList(data.geojson))
    .map((f) => ovStyled(f, { opacity: 0.8, stroke: 1.5 }));
}

function ovRenderAssetPanel(data) {
  ovPopulateTypeFilter(ovFeatureList(data.geojson));
  ovRenderAssetList();
}

// Types présents : d'abord dans l'ordre de la palette, puis ceux hors palette.
function ovPopulateTypeFilter(features) {
  const toolbar = document.getElementById('asset-list-toolbar');
  const select = document.getElementById('asset-type-filter');
  if (!toolbar || !select) return;
  toolbar.hidden = features.length === 0;
  if (features.length === 0) return;

  const present = new Set(features.map((f) => f.properties.type).filter(Boolean));
  const types = Object.keys(ASSET_TYPE_COLORS).filter((t) => present.has(t));
  present.forEach((t) => { if (!types.includes(t)) types.push(t); });

  if (OV.assetFilter && !present.has(OV.assetFilter)) OV.assetFilter = '';
  select.innerHTML = '<option value="">Tous les types</option>' +
    types.map((t) => `<option value="${escHtml(t)}">${escHtml(t)}</option>`).join('');
  select.value = OV.assetFilter;
}

function ovRenderAssetList() {
  const el = document.getElementById('ov-asset-list');
  const data = OV.cache.locate;
  if (!el || !data) return;

  const all = ovFeatureList(data.geojson);
  if (all.length === 0) {
    el.innerHTML = '<p class="ll-empty">Aucun site.</p>';
    return;
  }
  const features = OV.assetFilter
    ? all.filter((f) => f.properties.type === OV.assetFilter)
    : all;
  if (features.length === 0) {
    el.innerHTML = '<p class="ll-empty">Aucun actif pour ce type.</p>';
    return;
  }
  const dir = OV.assetSortDir === 'asc' ? 1 : -1;
  const sorted = [...features].sort(
    (a, b) => dir * ((a.properties.revenue_total || 0) - (b.properties.revenue_total || 0))
  );
  el.innerHTML = LocateView.listHtml(sorted);
}


// ── Politiques (tiroir bas) ────────────────────────────────────────────────

function ovScoreColor(score) {
  const s = Math.max(0, Math.min(100, score));
  const red    = [185,  28,  28];  // #b91c1c — rouge, proche de la couleur erreur du design
  const orange = [201, 106,  16];  // #c96a10 — ambre chaud, harmonieux avec le secondaire #865220
  const green  = [ 61, 107,  79];  // #3d6b4f — vert forêt terreux
  let from, to, t;
  if (s <= 50) { from = red;    to = orange; t = s / 50; }
  else         { from = orange; to = green;  t = (s - 50) / 50; }
  const r = Math.round(from[0] + t * (to[0] - from[0]));
  const g = Math.round(from[1] + t * (to[1] - from[1]));
  const b = Math.round(from[2] + t * (to[2] - from[2]));
  return `rgb(${r},${g},${b})`;
}

// Contenu du tiroir « Politiques » ; sa visibilité est gérée par ovSetDrawer.
function ovRenderPolicies(data) {
  const row = document.getElementById('policy-types-row');
  if (!row) return;
  row.innerHTML = (data.policies || [])
    .map((pt) => {
      const avgDisplay = pt.avg_score !== null ? pt.avg_score.toFixed(2) : '—';
      const avgColor = pt.avg_score !== null ? ovScoreColor(pt.avg_score) : null;
      const rows = pt.entries
        .map((e) => {
          const sc = e.score !== null ? Number(e.score) : null;
          const levelStyle = sc !== null
            ? ` style="background:${ovScoreColor(sc)};color:#fff;border-color:transparent"`
            : '';
          return `
          <tr>
            <td>${escHtml(e.subcategory)}</td>
            <td><span class="policy-level"${levelStyle}>${escHtml(e.level)}</span></td>
            <td class="policy-score">${sc !== null ? sc.toFixed(2) : '—'}</td>
          </tr>`;
        })
        .join('');
      return `
        <div class="policy-accordion-item">
          <button class="policy-accordion-header" aria-expanded="false">
            <span class="policy-type-card__name">${escHtml(pt.type)}</span>
            <div class="policy-accordion-header__right">
              <span class="policy-type-card__avg"${avgColor ? ` style="background:${avgColor}"` : ''}>∅ ${escHtml(avgDisplay)}</span>
              <svg class="policy-accordion-chevron" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
          </button>
          <div class="policy-accordion-body" hidden>
            <table class="policy-table">
              <thead><tr><th>Sous-catégorie</th><th>Niveau</th><th>Score</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>`;
    })
    .join('');

  row.querySelectorAll('.policy-accordion-header').forEach((btn) => {
    btn.addEventListener('click', () => {
      const item = btn.closest('.policy-accordion-item');
      const body = item.querySelector('.policy-accordion-body');
      const expanded = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', String(!expanded));
      body.hidden = expanded;
      item.classList.toggle('policy-accordion-item--open', !expanded);
    });
  });
}


// ── Combobox entreprise ────────────────────────────────────────────────────

function ovInitCombobox(companies, initialData) {
  const input = document.getElementById('company-search');
  const listbox = document.getElementById('company-listbox');
  const combobox = document.getElementById('company-combobox');
  if (!input || !listbox || !combobox) return;

  function renderOptions(query) {
    const q = query.toLowerCase();
    const filtered = companies.filter((c) => c.name.toLowerCase().includes(q));
    listbox.innerHTML = filtered
      .map(
        (c) =>
          `<li class="company-combobox__option" role="option" data-id="${c.id}" tabindex="-1">${escHtml(c.name)}</li>`
      )
      .join('');
    const open = filtered.length > 0;
    listbox.hidden = !open;
    combobox.setAttribute('aria-expanded', String(open));
  }

  function selectCompany(id, name) {
    input.value = name;
    listbox.hidden = true;
    combobox.setAttribute('aria-expanded', 'false');
    localStorage.setItem(SELECTED_COMPANY_KEY, id);
    ovSelectCompany(id, null);
  }

  input.addEventListener('input', () => renderOptions(input.value));
  input.addEventListener('focus', () => renderOptions(input.value));

  listbox.addEventListener('click', (e) => {
    const opt = e.target.closest('[data-id]');
    if (opt) selectCompany(Number(opt.dataset.id), opt.textContent.trim());
  });

  document.addEventListener('click', (e) => {
    if (!combobox.contains(e.target)) {
      listbox.hidden = true;
      combobox.setAttribute('aria-expanded', 'false');
    }
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      listbox.hidden = true;
      combobox.setAttribute('aria-expanded', 'false');
    }
    if (e.key === 'ArrowDown') {
      const first = listbox.querySelector('[data-id]');
      if (first) { e.preventDefault(); first.focus(); }
    }
  });

  listbox.addEventListener('keydown', (e) => {
    const opts = [...listbox.querySelectorAll('[data-id]')];
    const idx = opts.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' && idx < opts.length - 1) {
      e.preventDefault(); opts[idx + 1].focus();
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (idx > 0) opts[idx - 1].focus(); else input.focus();
    }
    if (e.key === 'Enter' && idx >= 0) {
      selectCompany(Number(opts[idx].dataset.id), opts[idx].textContent.trim());
    }
    if (e.key === 'Escape') {
      listbox.hidden = true;
      combobox.setAttribute('aria-expanded', 'false');
      input.focus();
    }
  });

  if (initialData && companies.length > 0) {
    input.value = initialData.company_name;
  }
}
```

- [ ] **Step 6 : CSS (`style.css`)**

(a) Supprimer les styles des anciens onglets, devenus morts : les règles `.country-panel__tabs`, `.country-panel__tab-indicator`, `.country-panel__tab`, `.country-panel__tab:hover`, `.country-panel__tab--active`, `.country-panel__tab--active:hover` (bloc « Country panel », l. 1014-1070 à la rédaction). Garder `.country-panel`, `.country-panel__view*`, les `@keyframes panelEnter/panelLeave`, `.country-panel__empty` et `.country-item*`.

(b) Supprimer tout le bloc `/* ─── Asset exposure cards ─── */` : règles `.asset-card`, `.asset-card__rank`, `__body`, `__top`, `__name`, `__footprint`, `__commodities`, `__comm-tag`, `.asset-card--clickable` et `:hover` (l. 1250-1328 à la rédaction). Garder le bloc `.asset-list__*` qui le précède.

(c) Remplacer :
```css
/* Liste potentiellement longue : limiter la hauteur et défiler. */
.ll-commodity-legend .map-legend__list,
#asset-type-legend .map-legend__list {
```
par :
```css
/* Liste potentiellement longue : limiter la hauteur et défiler. */
.ll-commodity-legend .map-legend__list,
#ov-mode-legend .map-legend__list,
#ov-supply-legend .map-legend__list {
```

(d) Remplacer :
```css
.map-stage .ll-commodity-legend .map-legend__list,
.map-stage #asset-type-legend .map-legend__list {
  max-height: 30vh;
}
```
par :
```css
.map-stage .ll-commodity-legend .map-legend__list,
.map-stage #ov-mode-legend .map-legend__list,
.map-stage #ov-supply-legend .map-legend__list {
  max-height: 30vh;
}
```

(e) Remplacer :
```css
/* Onglets du panneau « Exposition » (Vue d'ensemble) : ils doivent rester
   visibles pendant que la liste défile. */
.map-panel .country-panel__tabs {
  flex-shrink: 0;
  margin-bottom: 12px;
}

/* C'est .map-panel__body qui defile : les vues internes ne doivent pas
   creer un second conteneur de defilement. */
.map-panel .country-panel__view {
  overflow: visible;
}

/* Les libelles complets ne tiennent pas sur une ligne dans un panneau de
   320px : on les laisse passer a la ligne plutot que de les raccourcir. */
.map-panel .country-panel__tab {
  white-space: normal;
  padding: 6px 8px;
  letter-spacing: 0.02em;
}
```
par :
```css
/* C'est .map-panel__body qui defile : les vues internes ne doivent pas
   creer un second conteneur de defilement. */
.map-panel .country-panel__view {
  overflow: visible;
}
```

(f) Juste après la règle :
```css
/* Le tableau « Détail par actif » défile horizontalement dans le tiroir. */
.map-drawer .pr-table-wrap {
  overflow-x: auto;
}
```
insérer :
```css

/* ── Modes de la Vue d'ensemble ────────────────────────────────────────────
   Grille 2×2 fixe entre l'en-tête du panneau et son contenu défilant. */
.ov-modes {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-outline-variant);
  flex-shrink: 0;
}

.ov-mode-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 34px;
  padding: 6px 8px;
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-md);
  background: var(--color-surface-container-lowest);
  color: var(--color-on-surface-variant);
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.25;
  text-align: center;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.ov-mode-btn:hover:not(:disabled) {
  border-color: var(--color-outline);
  background: var(--color-surface-container-low);
  color: var(--color-on-surface);
}

.ov-mode-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* L'état actif l'emporte sur le survol (même spécificité, déclaré après). */
.ov-mode-btn.ov-mode-btn--active,
.ov-mode-btn.ov-mode-btn--active:hover {
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: var(--color-on-primary);
}

.ov-mode-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.ov-mode-btn__lock {
  flex-shrink: 0;
}

/* Listes de sites du panneau : c'est .map-panel__body qui défile. */
.ov-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Bascule verrouillée (supply chain sans connexion). */
.map-layer-btn:disabled,
.map-layer-btn:disabled:hover {
  background: transparent;
  opacity: 0.55;
  cursor: not-allowed;
}
```

- [ ] **Step 7 : Contrôles**

Run : `node --check dashboard/static/dashboard/js/overview.js && node --check dashboard/static/dashboard/js/main.js`
Expected : aucune sortie.
Run : `grep -rn "country-panel__tab\|asset-card\|asset-type-legend\|COMPANY_API_URL\|_overviewMap\|renderAssetTypeLegend" dashboard/static dashboard/templates templates`
Expected : aucune ligne.
Run : `grep -n "^const \|^let " dashboard/static/dashboard/js/main.js dashboard/static/dashboard/js/overview.js`
Expected : aucun nom en double entre les deux fichiers (`main.js` : `SATELLITE_STYLE`, `MAP_STYLES` ; `overview.js` : `SELECTED_COMPANY_KEY`, `OV_MODE_KEY`, `ASSET_TYPE_COLORS`, `ASSET_TYPE_FALLBACK_COLOR`, `OV`, `OV_MODES`).
Run : `venv/Scripts/python.exe manage.py test dashboard.tests.OverviewModesPageTests dashboard.tests.DashboardIndexViewTests dashboard.tests.CompanyDataViewTests`
Expected : OK.

- [ ] **Step 8 : Commit**

```bash
git add dashboard/static/dashboard/js/overview.js dashboard/static/dashboard/js/main.js dashboard/templates/dashboard/index.html dashboard/static/dashboard/css/style.css dashboard/tests.py
git commit -m "feat(overview): contrôleur de modes de carte, modes pays et asset

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7 : Vue d'ensemble — modes risque physique et dette écologique

**Files:**
- Modify: `dashboard/templates/dashboard/index.html`
- Modify: `dashboard/static/dashboard/js/overview.js`
- Test: `dashboard/tests.py` (`OverviewModesPageTests`)

**Interfaces:**
- Consumes: tâche 6 (`OV`, `OV_MODES`, `ovApplyMode`, `ovClearModeDisplay`, `ovSelectCompany`, `ovApplyCompany`, `ovInitControls`, `ovSetMapFeatures`, `ovStyled`) ; `PhysicalRiskView` (tâche 4) ; `DetteView` (tâche 5) ; `PieMarkers` ; fragments `_pr_panel.html`, `_pr_detail_drawer.html`, `_de_kpis.html`.
- Produces (utilisés par la tâche 8) : `ovColor(name) → color` (table commodité → couleur stable pour l'entreprise courante, palette `PieMarkers.PALETTE`) ; `OV.colors: Map`.

- [ ] **Step 1 : Écrire les tests**

Dans `OverviewModesPageTests`, ajouter :
```python
    def test_risque_open_and_dette_locked_for_anonymous(self):
        html = self._html()
        self.assertFalse(self._disabled(self._button(html, 'data-mode="risque"')))
        dette = self._button(html, 'data-mode="dette"')
        self.assertTrue(self._disabled(dette))
        self.assertIn('title="Connexion requise"', dette)

    def test_dette_enabled_when_authenticated(self):
        self._login()
        self.assertFalse(self._disabled(self._button(self._html(), 'data-mode="dette"')))

    def test_includes_shared_fragments(self):
        response = self.client.get(self.url)
        for template in ('dashboard/_pr_panel.html', 'dashboard/_pr_detail_drawer.html',
                         'dashboard/_de_kpis.html'):
            self.assertTemplateUsed(response, template)
        html = response.content.decode()
        self.assertRegex(html, r'<section[^>]*id="pr-detail-section"[^>]*\shidden')
        for element_id in ('pr-ranking', 'pr-table-body', 'de-total-lbiodiv',
                           'ov-dette-list', 'de-tooltip'):
            self.assertIn(f'id="{element_id}"', html)

    def test_exposes_risque_and_dette_api_and_modules(self):
        html = self._html()
        for name in ('dashboard:physical_risk_data', 'dashboard:dette_ecologique_data'):
            self.assertIn('"%s"' % reverse(name, kwargs={'pk': 0}), html)
        for script in ('pie_markers.js', 'physical_risk_view.js', 'dette_view.js'):
            self.assertIn(f'dashboard/js/{script}', html)
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.OverviewModesPageTests`
Expected : FAIL `bouton data-mode="risque" absent` (et échecs similaires).

- [ ] **Step 3 : Template — boutons**

Dans `index.html`, juste avant la fermeture `</div>` de `.ov-modes` (après le bouton `data-mode="asset"`), ajouter :
```django
      <button type="button" class="ov-mode-btn" data-mode="risque" aria-pressed="false">Risque physique</button>
      <button type="button" class="ov-mode-btn" data-mode="dette" aria-pressed="false"{% if not user.is_authenticated %} disabled title="Connexion requise"{% endif %}>
        Dette écologique
        {% if not user.is_authenticated %}
        <svg class="ov-mode-btn__lock" width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <rect x="2.5" y="5.5" width="7" height="5" rx="1" stroke="currentColor" stroke-width="1.2" />
          <path d="M4 5.5V4a2 2 0 014 0v1.5" stroke="currentColor" stroke-width="1.2" />
        </svg>
        {% endif %}
      </button>
```

- [ ] **Step 4 : Template — vues, tiroir, infobulle, API, scripts**

(a) Dans `.country-panel`, après la vue `data-view="asset"` (après son `</div>` fermant), ajouter :
```django
        <div class="country-panel__view" data-view="risque">
          {% include "dashboard/_pr_panel.html" %}
        </div>
        <div class="country-panel__view" data-view="dette">
          {% include "dashboard/_de_kpis.html" %}
          <div class="ov-list" id="ov-dette-list"></div>
        </div>
```

(b) Juste après la `</section>` de `#policy-section`, ajouter :
```django

  {% include "dashboard/_pr_detail_drawer.html" with section_id="pr-detail-section" start_hidden=True %}

  <div class="de-tooltip" id="de-tooltip" hidden></div>
```

(c) Remplacer :
```django
  var OVERVIEW_API = {
    company: "{% url 'dashboard:company_data' pk=0 %}",
    locate: "{% url 'dashboard:leap_locate_data' pk=0 %}"
  };
```
par :
```django
  var OVERVIEW_API = {
    company: "{% url 'dashboard:company_data' pk=0 %}",
    locate: "{% url 'dashboard:leap_locate_data' pk=0 %}",
    risque: "{% url 'dashboard:physical_risk_data' pk=0 %}",
    dette: "{% url 'dashboard:dette_ecologique_data' pk=0 %}"
  };
```

(d) Remplacer :
```django
<script src="{% static 'dashboard/js/locate_view.js' %}" defer></script>
<script src="{% static 'dashboard/js/overview.js' %}" defer></script>
```
par :
```django
<script src="{% static 'dashboard/js/pie_markers.js' %}" defer></script>
<script src="{% static 'dashboard/js/locate_view.js' %}" defer></script>
<script src="{% static 'dashboard/js/physical_risk_view.js' %}" defer></script>
<script src="{% static 'dashboard/js/dette_view.js' %}" defer></script>
<script src="{% static 'dashboard/js/overview.js' %}" defer></script>
```

- [ ] **Step 5 : `overview.js` — état et registre**

(a) Dans `OV`, remplacer :
```js
  assetFilter: '',     // mode asset : type d'actif filtré ('' = tous)
  assetSortDir: 'desc',
};
```
par :
```js
  assetFilter: '',     // mode asset : type d'actif filtré ('' = tous)
  assetSortDir: 'desc',
  prHazard: null,      // mode risque : aléa sélectionné (premier par défaut)
  prHorizon: 5,        // mode risque : horizon de la perte projetée (années)
  pies: [],            // mode dette : marqueurs camembert
  colors: new Map(),   // commodité → couleur, stable pour l'entreprise courante
};
```

(b) Dans `OV_MODES`, remplacer :
```js
    legendHtml: () => LocateView.legendHtml(),
    popupHtml: (p) => LocateView.popupHtml(p),
  },
};
```
par :
```js
    legendHtml: () => LocateView.legendHtml(),
    popupHtml: (p) => LocateView.popupHtml(p),
  },
  risque: {
    title: 'Classement des risques',
    source: 'risque',
    drawer: 'risque',
    renderPanel: ovRenderRisquePanel,
    mapFeatures: ovRisqueFeatures,
    legendHtml: () => PhysicalRiskView.legendHtml(),
    popupHtml: (p) => PhysicalRiskView.popupHtml(p),
  },
  dette: {
    title: 'Dette écologique',
    source: 'dette',
    drawer: 'policy',
    pies: true,          // camemberts (marqueurs DOM) au lieu des cercles
    renderPanel: ovRenderDettePanel,
    mapFeatures: () => [],
    legendHtml: ovDetteLegendHtml,
    popupHtml: null,
  },
};
```

- [ ] **Step 6 : `overview.js` — branchements**

(a) À la fin de `ovInitControls` (après le bloc du bouton de tri, avant l'accolade fermante de la fonction), ajouter :
```js

  // Mode risque : horizon 5 / 10 ans de la perte projetée.
  PhysicalRiskView.bindHorizon(document.querySelector('[data-view="risque"] .pr-horizon'), (years) => {
    OV.prHorizon = years;
    PhysicalRiskView.renderLoss(OV.cache.risque, OV.prHorizon);
  });
```

(b) Dans `ovApplyMode`, remplacer :
```js
  ovSetMapFeatures(cfg.mapFeatures(data));
  ovSetLegend(cfg.legendHtml(data));
```
par :
```js
  ovSetMapFeatures(cfg.mapFeatures(data));
  if (cfg.pies) ovRenderPies(data); else ovClearPies();
  ovSetLegend(cfg.legendHtml(data));
```

(c) Dans `ovClearModeDisplay`, remplacer :
```js
  ovSetMapFeatures([]);
  ovSetLegend('');
```
par :
```js
  ovSetMapFeatures([]);
  ovClearPies();
  ovSetLegend('');
```

(d) Dans `ovSelectCompany`, remplacer :
```js
  OV.companyReady = null;
  ovRenderMode();
```
par :
```js
  OV.companyReady = null;
  OV.prHazard = null;  // l'horizon, lui, est conservé (comme sur la page Risque physique)
  ovRenderMode();
```

(e) Dans `ovApplyCompany`, remplacer :
```js
    OV.countryCoords[country].n += 1;
  });
  ovRenderPolicies(data);
```
par :
```js
    OV.countryCoords[country].n += 1;
  });

  // Couleurs des commodités : d'abord celles de l'entreprise, par ordre
  // alphabétique ; les commodités propres aux flux fournisseurs viendront à la
  // suite, sans jamais décaler celles déjà attribuées.
  OV.colors = new Map();
  const names = new Set();
  (data.countries || []).forEach((c) => c.commodities.forEach((cm) => names.add(cm.name)));
  [...names].sort((a, b) => a.localeCompare(b)).forEach(ovColor);

  ovRenderPolicies(data);
```

- [ ] **Step 7 : `overview.js` — nouvelles sections**

Insérer, juste avant la ligne `// ── Politiques (tiroir bas) ───…`, les deux sections suivantes :
```js
// ── Mode « Risque physique » ───────────────────────────────────────────────

// Aléa sélectionné : conservé entre les modes, réinitialisé au changement
// d'entreprise (premier du classement par défaut).
function ovCurrentHazard(data) {
  if (!PhysicalRiskView.hazard(data, OV.prHazard)) {
    OV.prHazard = data.hazards && data.hazards.length ? data.hazards[0].key : null;
  }
  return OV.prHazard;
}

function ovRenderRisquePanel(data) {
  const key = ovCurrentHazard(data);
  PhysicalRiskView.renderKpis(data, OV.prHorizon);
  PhysicalRiskView.renderRanking(data, key, ovSelectHazard);
  PhysicalRiskView.renderTable(data, key);
}

function ovRisqueFeatures(data) {
  return PhysicalRiskView.buildGeojson(data, ovCurrentHazard(data)).features
    .map((f) => ovStyled(f, { opacity: 0.75, stroke: 1.5 }));
}

// Le classement sert de sélecteur : points et tableau suivent l'aléa choisi.
function ovSelectHazard(key) {
  const data = OV.cache.risque;
  if (!data) return;
  OV.prHazard = key;
  PhysicalRiskView.markSelected(key);
  ovSetMapFeatures(ovRisqueFeatures(data));
  PhysicalRiskView.renderTable(data, key);
}


// ── Mode « Dette écologique » ──────────────────────────────────────────────

// Couleur stable d'une commodité pour l'entreprise courante : attribuée à la
// première demande, dans l'ordre de la palette, puis jamais modifiée. Partagée
// par les camemberts et les flèches de la supply chain.
function ovColor(name) {
  if (!OV.colors.has(name)) {
    const palette = PieMarkers.PALETTE;
    OV.colors.set(name, palette[OV.colors.size % palette.length]);
  }
  return OV.colors.get(name);
}

function ovColorMap(names) {
  const colors = {};
  names.forEach((n) => { colors[n] = ovColor(n); });
  return colors;
}

function ovDetteColors(data) {
  return ovColorMap(data.commodities.map((c) => c.name));
}

function ovRenderDettePanel(data) {
  DetteView.renderKpis(data, 'asset');
  const list = document.getElementById('ov-dette-list');
  if (!list) return;
  list.innerHTML = data.assets.length
    ? DetteView.assetListHtml(data.assets, ovDetteColors(data))
    : '<p class="ll-empty">Aucun asset avec une dette calculable.</p>';
}

function ovDetteLegendHtml(data) {
  if (!data.commodities.length) return '';
  return '<p class="map-legend__title">Commodités</p>' +
    `<ul class="map-legend__list">${DetteView.legendItemsHtml(data.commodities, ovDetteColors(data))}</ul>`;
}

// Camemberts : marqueurs DOM, ils survivent aux setStyle et passent au-dessus
// de toutes les couches (supply chain comprise).
function ovRenderPies(data) {
  ovClearPies();
  const colors = ovDetteColors(data);
  const handlers = DetteView.tooltipHandlers(
    document.getElementById('de-tooltip'), document.getElementById('overview-map'), colors
  );
  OV.pies = PieMarkers.render(OV.map, data.assets, colors, handlers);
}

function ovClearPies() {
  OV.pies.forEach((m) => m.remove());
  OV.pies = [];
  const tip = document.getElementById('de-tooltip');
  if (tip) tip.hidden = true;
}


```

- [ ] **Step 8 : Contrôles**

Run : `node --check dashboard/static/dashboard/js/overview.js`
Expected : aucune sortie.
Run : `venv/Scripts/python.exe manage.py test dashboard.tests.OverviewModesPageTests dashboard.tests.DashboardIndexViewTests dashboard.tests.PhysicalRiskPageViewTests dashboard.tests.DetteEcologiqueViewTests`
Expected : OK.

- [ ] **Step 9 : Commit**

```bash
git add dashboard/templates/dashboard/index.html dashboard/static/dashboard/js/overview.js dashboard/tests.py
git commit -m "feat(overview): modes risque physique et dette écologique

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8 : Vue d'ensemble — supply chain dans tous les modes

**Files:**
- Modify: `dashboard/templates/dashboard/index.html`
- Modify: `dashboard/static/dashboard/js/overview.js`
- Test: `dashboard/tests.py` (`OverviewModesPageTests`)

**Interfaces:**
- Consumes: `SupplyChain.create` (tâche 3) ; `ovColor` (tâche 7) ; `ovLoad`, `ovCompanyReady`, `ovInitMap`, `ovApplyStyle`, `ovSelectCompany`, `ovInitControls` (tâche 6).
- Produces: `OV.supply` (instance `SupplyChain`), `ovSetSupplyVisible(visible)`, `ovLoadSupply()` ; DOM `#ov-supply-toggle`, `#ov-supply-legend`, `#ov-supply-legend-list`.

- [ ] **Step 1 : Écrire les tests**

Dans `OverviewModesPageTests`, ajouter :
```python
    def test_supply_toggle_locked_for_anonymous(self):
        tag = self._button(self._html(), 'id="ov-supply-toggle"')
        self.assertTrue(self._disabled(tag))
        self.assertIn('title="Connexion requise"', tag)

    def test_supply_toggle_enabled_when_authenticated(self):
        self._login()
        html = self._html()
        self.assertFalse(self._disabled(self._button(html, 'id="ov-supply-toggle"')))
        self.assertIn('id="ov-supply-legend"', html)
        self.assertIn('dashboard/js/supply_chain.js', html)
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `venv/Scripts/python.exe manage.py test dashboard.tests.OverviewModesPageTests`
Expected : FAIL `bouton id="ov-supply-toggle" absent`.

- [ ] **Step 3 : Template**

(a) Dans `.map-stage__tl`, après le `<div class="map-layer-toggle" role="group" aria-label="Style de carte">…</div>`, ajouter :
```django
    <div class="map-layer-toggle" role="group" aria-label="Fournisseurs">
      <button type="button" class="map-layer-btn" id="ov-supply-toggle" aria-pressed="false"{% if not user.is_authenticated %} disabled title="Connexion requise"{% endif %}>Supply chain</button>
    </div>
```

(b) Dans `.map-stage__bl`, après `#ov-mode-legend` (la légende du mode reste au-dessus), ajouter :
```django
    <div class="map-legend" id="ov-supply-legend" hidden aria-label="Légende des flux fournisseurs">
      <p class="map-legend__title">Flux fournisseurs</p>
      <ul class="map-legend__list" id="ov-supply-legend-list"></ul>
    </div>
```

(c) Remplacer :
```django
<script src="{% static 'dashboard/js/locate_view.js' %}" defer></script>
<script src="{% static 'dashboard/js/physical_risk_view.js' %}" defer></script>
```
par :
```django
<script src="{% static 'dashboard/js/locate_view.js' %}" defer></script>
<script src="{% static 'dashboard/js/supply_chain.js' %}" defer></script>
<script src="{% static 'dashboard/js/physical_risk_view.js' %}" defer></script>
```

- [ ] **Step 4 : `overview.js` — état, carte, fond**

(a) Dans `OV`, remplacer :
```js
  colors: new Map(),   // commodité → couleur, stable pour l'entreprise courante
};
```
par :
```js
  colors: new Map(),   // commodité → couleur, stable pour l'entreprise courante
  supply: null,        // instance SupplyChain, disponible dans tous les modes
};
```

(b) Dans `ovInitMap`, remplacer :
```js
  OV.map = map;

  map.on('load', () => {
    ovAddAssetsLayer();
```
par :
```js
  OV.map = map;
  // Flèches et camemberts partagent la table de couleurs de l'entreprise.
  OV.supply = SupplyChain.create(map, {
    colorFor: ovColor,
    legend: {
      box: document.getElementById('ov-supply-legend'),
      list: document.getElementById('ov-supply-legend-list'),
    },
  });

  map.on('load', () => {
    ovAddAssetsLayer();
    OV.supply.addLayers('ov-assets-layer');
    OV.supply.resume();
```

(c) Remplacer tout `ovApplyStyle` :
```js
function ovApplyStyle(styleName) {
  const map = OV.map;
  if (!map) return;
  map.setStyle(mapStyleFor(styleName));
  map.once('idle', () => {
    ovAddAssetsLayer();
  });
}
```
par :
```js
function ovApplyStyle(styleName) {
  const map = OV.map;
  if (!map) return;
  // « idle » ne se déclenche pas tant que l'animation des flèches tourne.
  OV.supply.stop();
  map.setStyle(mapStyleFor(styleName));
  map.once('idle', () => {
    ovAddAssetsLayer();
    OV.supply.addLayers('ov-assets-layer');
    OV.supply.resume();
  });
}
```

- [ ] **Step 5 : `overview.js` — entreprise et bouton**

(a) Dans `ovSelectCompany`, remplacer :
```js
  OV.prHazard = null;  // l'horizon, lui, est conservé (comme sur la page Risque physique)
  ovRenderMode();
```
par :
```js
  OV.prHazard = null;  // l'horizon, lui, est conservé (comme sur la page Risque physique)
  // Les flux de l'entreprise précédente disparaissent tout de suite.
  OV.supply.setData(null);
  if (OV.supply.isVisible()) ovLoadSupply();
  ovRenderMode();
```

(b) À la fin de `ovInitControls` (après le branchement de l'horizon), ajouter :
```js

  // Supply chain : disponible dans tous les modes (connexion requise).
  const supplyBtn = document.getElementById('ov-supply-toggle');
  if (supplyBtn && !supplyBtn.disabled) {
    supplyBtn.addEventListener('click', () => {
      const visible = !OV.supply.isVisible();
      ovSetSupplyVisible(visible);
      if (visible) ovLoadSupply();
    });
  }
```

(c) Insérer, juste avant la ligne `// ── Politiques (tiroir bas) ───…`, la section :
```js
// ── Supply chain (tous modes) ──────────────────────────────────────────────

function ovSetSupplyVisible(visible) {
  const btn = document.getElementById('ov-supply-toggle');
  if (btn) {
    btn.classList.toggle('map-layer-btn--active', visible);
    btn.setAttribute('aria-pressed', String(visible));
  }
  OV.supply.setVisible(visible);
}

// Données Locate (partagées avec le mode asset) poussées dans la supply chain,
// après les données entreprise pour que leurs couleurs gardent la priorité.
function ovLoadSupply() {
  if (OV.companyId == null) return;
  Promise.all([ovCompanyReady(), ovLoad('locate')])
    .then(([, data]) => OV.supply.setData(data))
    .catch((err) => {
      if (err && err.kind === 'stale') return;
      console.error('overview : chargement de la supply chain impossible', err);
      ovSetSupplyVisible(false);
    });
}


```

- [ ] **Step 6 : Contrôles**

Run : `node --check dashboard/static/dashboard/js/overview.js`
Expected : aucune sortie.
Run : `venv/Scripts/python.exe manage.py test dashboard.tests.OverviewModesPageTests dashboard.tests.LeapPagesTests`
Expected : OK.

- [ ] **Step 7 : Commit**

```bash
git add dashboard/templates/dashboard/index.html dashboard/static/dashboard/js/overview.js dashboard/tests.py
git commit -m "feat(overview): supply chain disponible dans tous les modes

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9 : Vérification finale

Aucun code applicatif. Le script de fumée est jetable : `<scratchpad>` désigne le répertoire temporaire de la session (ou tout dossier hors du repo), jamais le repo. `<sessionid>` est la valeur affichée au step 3.

**Files:**
- Create (hors repo) : `<scratchpad>/smoke.mjs`

**Interfaces:**
- Consumes: tout ce qui précède ; globaux de page `OV` (overview.js).
- Produces: un compte rendu (tests, erreurs JS, état des modes) pour l'utilisateur.

- [ ] **Step 1 : Suite complète**

Run : `venv/Scripts/python.exe manage.py test`
Expected : OK, 0 erreur (contre 35 avant la tâche 0). Rapporter le nombre de tests.

- [ ] **Step 2 : Syntaxe de tous les scripts touchés**

Run : `for f in main overview locate_view supply_chain physical_risk_view dette_view leap_locate physical_risk dette_ecologique; do node --check dashboard/static/dashboard/js/$f.js || echo "ECHEC $f"; done`
Expected : aucune ligne `ECHEC`.

- [ ] **Step 3 : Serveur de dev et session de test**

Lancer en arrière-plan : `DEBUG=True venv/Scripts/python.exe manage.py runserver 127.0.0.1:8765 --noreload`

Créer une session pour le premier utilisateur actif (aucune donnée métier modifiée ; la session est supprimée au step 6) :
```bash
venv/Scripts/python.exe manage.py shell -c "
from django.contrib.auth import get_user_model, SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
u = get_user_model().objects.filter(is_active=True).order_by('pk').first()
s = SessionStore()
s[SESSION_KEY] = str(u.pk)
s[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'
s[HASH_SESSION_KEY] = u.get_session_auth_hash()
s.create()
print(s.session_key)"
```
S'il n'existe aucun utilisateur, sauter les steps 4-5 et le signaler (la checklist manuelle du step 7 reste due).

- [ ] **Step 4 : Écrire `<scratchpad>/smoke.mjs`**

```js
// Parcours des pages carte dans Edge headless : remonte les erreurs JS
// (exceptions, console.error) puis l'état de chaque mode de la Vue d'ensemble.
// Usage : node smoke.mjs http://127.0.0.1:8765 <sessionid>
import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [base, sessionid] = process.argv.slice(2);
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const PORT = 9333;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const edge = spawn(EDGE, [
  '--headless=new', `--remote-debugging-port=${PORT}`, '--window-size=1440,900',
  '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
  `--user-data-dir=${mkdtempSync(join(tmpdir(), 'smoke-'))}`, 'about:blank',
]);

async function pageSocketUrl() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === 'page');
      if (page) return page.webSocketDebuggerUrl;
    } catch (_) { /* Edge démarre */ }
    await sleep(200);
  }
  throw new Error('Edge injoignable');
}

const ws = new WebSocket(await pageSocketUrl());
await new Promise((r) => ws.addEventListener('open', r));
let seq = 0;
const waiting = new Map();
const errors = [];
ws.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && waiting.has(msg.id)) { waiting.get(msg.id)(msg); waiting.delete(msg.id); return; }
  if (msg.method === 'Runtime.exceptionThrown') {
    const d = msg.params.exceptionDetails;
    errors.push((d.exception && d.exception.description) || d.text);
  }
  if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
    errors.push(msg.params.args.map((a) => a.value ?? a.description).join(' '));
  }
});
const send = (method, params = {}) => new Promise((r) => {
  const id = ++seq;
  waiting.set(id, r);
  ws.send(JSON.stringify({ id, method, params }));
});

await send('Runtime.enable');
await send('Network.enable');
await send('Network.setCookie', { name: 'sessionid', value: sessionid, url: base });

for (const path of ['/leap/locate/', '/physical-risk/', '/dette-ecologique/', '/portfolio/', '/']) {
  errors.length = 0;
  await send('Page.navigate', { url: base + path });
  await sleep(6000);
  console.log(`${path} → ${errors.length ? 'ERREURS\n  ' + errors.join('\n  ') : 'ok'}`);
}

// Sur la Vue d'ensemble (dernière page chargée) : chaque mode, puis supply
// chain et changement de fond.
errors.length = 0;
const res = await send('Runtime.evaluate', {
  awaitPromise: true,
  returnByValue: true,
  expression: `(async () => {
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const out = {};
    for (const mode of ['pays', 'asset', 'risque', 'dette']) {
      document.querySelector('.ov-mode-btn[data-mode="' + mode + '"]').click();
      await wait(3000);
      const status = document.getElementById('ov-status');
      out[mode] = {
        title: document.getElementById('ov-panel-title').textContent,
        status: status.hidden ? '' : status.textContent,
        view: document.querySelector('[data-view="' + mode + '"]').classList.contains('country-panel__view--active'),
        legend: !document.getElementById('ov-mode-legend').hidden,
        points: OV.features.length,
        pies: OV.pies.length,
        drawers: ['policy-section', 'pr-detail-section'].filter((id) => !document.getElementById(id).hidden),
      };
    }
    document.getElementById('ov-supply-toggle').click();
    await wait(3000);
    out.supply = { visible: OV.supply.isVisible(), commodities: Object.keys(OV.supply.colors()).length };
    document.querySelector('.map-layer-btn[data-layer="grayscale"]').click();
    await wait(6000);
    out.afterStyle = {
      points: !!OV.map.getLayer('ov-assets-layer'),
      supply: !!OV.map.getLayer('ll-supplier-lines-layer'),
    };
    return out;
  })()`,
});
console.log(JSON.stringify(res.result && res.result.result && res.result.result.value, null, 2));
console.log(errors.length ? 'ERREURS overview :\n  ' + errors.join('\n  ') : 'overview : aucune erreur JS');
ws.close();
edge.kill();
```

- [ ] **Step 5 : Lancer le test de fumée**

Run : `node <scratchpad>/smoke.mjs http://127.0.0.1:8765 <sessionid>`
Expected :
- chaque page : `ok`. Les erreurs réseau des tuiles (`AJAXError`, `Failed to fetch` vers openfreemap/arcgis) sont du bruit d'environnement sans réseau ; toute `ReferenceError`, `TypeError` ou `SyntaxError` est un défaut à corriger ;
- overview : pour chaque mode, `status` vide, `view: true`, `legend: true` ; `points > 0` pour pays, asset et risque ; `pies > 0` pour dette ; `drawers` vaut `["pr-detail-section"]` en risque, et `["policy-section"]` ou `[]` (entreprise sans politique) ailleurs ;
- `supply.visible: true` ; `afterStyle.points` et `afterStyle.supply` à `true` (si le style n'a pas pu se charger faute de réseau, `idle` peut ne pas venir : le signaler sans conclure).

- [ ] **Step 6 : Nettoyage**

Arrêter le serveur de dev, puis supprimer la session :
`venv/Scripts/python.exe manage.py shell -c "from django.contrib.sessions.models import Session; Session.objects.filter(session_key='<sessionid>').delete()"`

- [ ] **Step 7 : Checklist navigateur pour l'utilisateur**

Transmettre telle quelle, en précisant ce que le test de fumée a déjà couvert :
- Vue d'ensemble, connecté : chaque mode × changement d'entreprise, de fond (Classique / Gris / Satellite) et de thème jour/nuit, supply chain active ou non.
- Mode asset : filtre par type, tri revenu ↑↓, clic dans la liste → zoom, popup Locate.
- Mode risque : horizon 5/10 ans, sélection d'un aléa → couleurs des points et tiroir « Détail par actif » mis à jour, infobulles du tableau.
- Mode dette : camemberts, infobulle au survol, liste (parts, Lbiodiv), même couleur pour une commodité sur les camemberts et sur les flèches de la supply chain.
- Rechargement de la page : mode et entreprise restaurés.
- Déconnecté : boutons asset, dette et supply chain grisés avec « Connexion requise » ; un mode verrouillé mémorisé revient sur « pays ».
- Non-régression : Locate (liste, couleurs revenu, supply chain, fond/thème), Risque physique (classement, tiroir, horizon, thème), Dette (camemberts, infobulle, bascule asset/région, thème), Portfolio (camemberts).

