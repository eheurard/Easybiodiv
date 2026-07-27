# Vue risque — tooltip d'inventaire mesuré Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher l'inventaire mesuré récent (eau / CO₂ / usage des sols) par asset sur la vue risque physique, sous forme d'un tooltip informatif au survol du nom — sans toucher à la formule de perte.

**Architecture:** `_get_physical_risk_data` ajoute un champ additif `inventory` par asset (flux du sous-ensemble, année d'inventaire la plus récente, valeurs non nulles). Le front (`physical_risk.js`) rend un tooltip au survol du nom d'asset, en réutilisant la mécanique CSS du tooltip de vulnérabilité existant (`pr-vuln-tooltip`).

**Tech Stack:** Django (TestCase) ; JavaScript vanilla ; CSS. Aucune dépendance nouvelle.

## Global Constraints

- Django pur, compatible SQLite, aucune dépendance nouvelle, PEP 8 ≤ 100 caractères.
- Frontend **JS vanilla** (pas de framework), chargement `defer` existant.
- Reste dans l'app `dashboard`.
- **La formule de perte** (`annual_loss` = aléa × exposition × vulnérabilité) est **inchangée**.
- Sous-ensemble de flux affichés : `('water', 'co2', 'surface_area')` ; `surface_area` libellé **« Usage des sols »**.
- `physical_risk` n'est **pas** dans `GOLDEN_VIEWS` : le champ `inventory` est additif, les tests existants restent verts.
- Commande de test : `.venv\Scripts\python.exe manage.py test dashboard` ; suite projet : `.venv\Scripts\python.exe manage.py test`. Ne redirige pas la sortie vers un fichier du repo.

---

### Task 1 : Backend — champ `inventory` sur `_get_physical_risk_data`

**Files:**
- Modify: `dashboard/views.py` (constantes près de `PHYSICAL_RISKS` ; corps de `_get_physical_risk_data`)
- Test: `dashboard/tests.py` (`PhysicalRiskDataTests`)

**Interfaces:**
- Consumes: `AssetInventory`, `Flow` (déjà importés/existants) ; `Max`, `defaultdict` (déjà importés dans views.py).
- Produces: chaque asset de la sortie a `inventory: list[{'name': str, 'value': float, 'unit': str}]` (ordre `water, co2, surface_area` ; `[]` si aucun).

- [ ] **Step 1 : Écrire les tests (dans `PhysicalRiskDataTests`)**

`PhysicalRiskDataTests.setUp` crée déjà `self.company`, `self.a1`, `self.a2` (assets détenus). Les `Flow` sont seedés (migration 0037). Ajouter :

```python
    def test_inventory_subset_latest_year_ordered(self):
        from .models import AssetInventory, Flow
        from .views import _get_physical_risk_data
        water = Flow.objects.get(key='water')
        co2 = Flow.objects.get(key='co2')
        energy = Flow.objects.get(key='energy')
        AssetInventory.objects.create(asset=self.a1, flow=water, year=2023, value=10.0)
        AssetInventory.objects.create(asset=self.a1, flow=water, year=2024, value=100.0)
        AssetInventory.objects.create(asset=self.a1, flow=co2, year=2024, value=50.0)
        AssetInventory.objects.create(asset=self.a1, flow=energy, year=2024, value=999.0)
        data = _get_physical_risk_data(self.company)
        a1 = next(a for a in data['assets'] if a['name'] == 'Site A1')
        # sous-ensemble + ordre (eau, CO2) ; énergie exclue ; année récente (100, pas 10)
        self.assertEqual([e['name'] for e in a1['inventory']],
                         ['Consommation eau', 'Émissions CO₂'])
        self.assertEqual(a1['inventory'][0]['value'], 100.0)
        self.assertEqual(a1['inventory'][0]['unit'], 'm³')

    def test_inventory_empty_when_none(self):
        from .views import _get_physical_risk_data
        data = _get_physical_risk_data(self.company)
        a2 = next(a for a in data['assets'] if a['name'] == 'Site A2')
        self.assertEqual(a2['inventory'], [])
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.PhysicalRiskDataTests`
Expected : FAIL (`KeyError: 'inventory'` ou `assertEqual` — le champ n'existe pas encore).

- [ ] **Step 3 : Ajouter les constantes**

Dans `dashboard/views.py`, juste après la liste `PHYSICAL_RISKS` (avant `def _exposure_label`), ajouter :

```python
# Inventaire mesuré affiché (informatif) sur la vue risque : sous-ensemble de flux.
_RISK_INVENTORY_KEYS = ('water', 'co2', 'surface_area')
_RISK_INVENTORY_LABELS = {
    'water': 'Consommation eau',
    'co2': 'Émissions CO₂',
    'surface_area': 'Usage des sols',
}
```

- [ ] **Step 4 : Calculer `inventory` dans la vue**

Dans `_get_physical_risk_data`, après la ligne `asset_ids = [a.pk for a in assets]` (et avant la boucle `for a in assets:` qui construit `assets_out`), ajouter :

```python
    # Inventaire mesuré (informatif) : flux du sous-ensemble, année d'inventaire la
    # plus récente de l'asset, valeurs non nulles. N'entre PAS dans la perte.
    latest_inv_years = dict(
        AssetInventory.objects.filter(
            asset_id__in=asset_ids, flow__key__in=_RISK_INVENTORY_KEYS
        ).values('asset_id').annotate(m=Max('year')).values_list('asset_id', 'm')
    )
    inv_by_asset = defaultdict(dict)
    for inv in AssetInventory.objects.filter(
        asset_id__in=asset_ids, flow__key__in=_RISK_INVENTORY_KEYS
    ).select_related('flow'):
        if inv.value and latest_inv_years.get(inv.asset_id) == inv.year:
            inv_by_asset[inv.asset_id][inv.flow.key] = {
                'name': _RISK_INVENTORY_LABELS[inv.flow.key],
                'value': round(inv.value, 2),
                'unit': inv.flow.unit,
            }

    def _inventory_for(asset_id):
        entries = inv_by_asset.get(asset_id, {})
        return [entries[k] for k in _RISK_INVENTORY_KEYS if k in entries]
```

Puis, dans le `assets_out.append({...})`, ajouter la clé `inventory` (après `'risk': ...`) :

```python
            'risk': {k: round(v, 4) for k, v in risk_vals.items()},
            'inventory': _inventory_for(a.pk),
        })
```

- [ ] **Step 5 : Lancer, vérifier le succès**

Run : `.venv\Scripts\python.exe manage.py test dashboard.tests.PhysicalRiskDataTests`
Expected : PASS (nouveaux tests + assertions existantes).
Run : `.venv\Scripts\python.exe manage.py test dashboard`
Expected : PASS (pas de régression ; physical_risk n'est pas golden).

- [ ] **Step 6 : Commit**

```bash
git add dashboard/views.py dashboard/tests.py
git commit -m "feat(risk): expose l'inventaire mesuré récent par asset (informatif)"
```

---

### Task 2 : Frontend — tooltip d'inventaire sur le nom d'asset

**Files:**
- Modify: `dashboard/static/dashboard/js/physical_risk.js` (`prRenderTable`, ~lignes 216-256)
- Modify: `dashboard/static/dashboard/css/style.css` (près des règles `.pr-vuln-tooltip`, ~ligne 2471+)

**Interfaces:**
- Consumes: le champ `a.inventory` (liste `{name, value, unit}`) fourni par Task 1 ; helper `escHtml` (déjà présent dans le fichier JS).

- [ ] **Step 1 : Porter `inventory` jusqu'à la ligne**

Dans `physical_risk.js`, dans `prRenderTable`, le `data.assets.map(a => {...})` construit un objet `r`. Ajouter `inventory` à ce `r`. Remplacer :

```javascript
  const rows = data.assets.map(a => {
    const hz = a.risk[key] || 0;
    const risk = hz * a.exposition * vuln;
    return { name: a.name, hz: hz, expo: a.exposition, risk: risk };
  }).sort((x, y) => y.risk - x.risk);
```
par :
```javascript
  const rows = data.assets.map(a => {
    const hz = a.risk[key] || 0;
    const risk = hz * a.exposition * vuln;
    return { name: a.name, hz: hz, expo: a.exposition, risk: risk,
             inventory: a.inventory || [] };
  }).sort((x, y) => y.risk - x.risk);
```

- [ ] **Step 2 : Rendre la cellule nom avec tooltip**

Toujours dans `prRenderTable`, dans le `body.innerHTML = rows.map(r => { ... })`, construire une cellule nom conditionnelle et l'utiliser dans le `<tr>`. Remplacer la ligne `<td>${escHtml(r.name)}</td>` du template par `${nameCell}`, et calculer `nameCell` en tête du callback (avant le `return`) :

```javascript
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
```

Le `<tr>` devient :
```javascript
    return `
    <tr>
      ${nameCell}
      <td class="data-tabular">${(r.hz * 100).toFixed(1)}%</td>
      <td class="data-tabular">${prFmtEuro(r.expo)}</td>
      <td class="data-tabular pr-table__vuln">${(vuln * 100).toFixed(1)}%${tooltip}</td>
      <td class="data-tabular pr-table__risk">${prFmtEuro(r.risk)}</td>
    </tr>`;
```

- [ ] **Step 3 : Ajouter le CSS**

Dans `dashboard/static/dashboard/css/style.css`, juste après le bloc `.pr-vuln-tooltip*` (après la règle `.pr-vuln-tooltip__note`, ~ligne 2545), ajouter :

```css
.pr-table__asset {
  position: relative;
  cursor: help;
}

.pr-table__asset--has-inv {
  text-decoration: underline dotted;
  text-underline-offset: 3px;
}

/* Reprend l'apparence de .pr-vuln-tooltip mais ancré à gauche (cellule nom). */
.pr-inv-tooltip {
  display: none;
  position: absolute;
  left: 0;
  top: 100%;
  z-index: 20;
  margin-top: 6px;
  padding: 10px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-outline-variant);
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, .12);
  min-width: 200px;
  text-align: left;
  white-space: normal;
  font-weight: 400;
}

.pr-table__asset:hover .pr-inv-tooltip {
  display: block;
}
```

> Vérifier que les variables CSS utilisées (`--color-surface`, `--color-outline-variant`) existent dans `style.css` (ce sont celles de la charte). Si un nom diffère, aligner sur les valeurs réellement utilisées par `.pr-vuln-tooltip` (lire son bloc à ~ligne 2476-2493 et reprendre exactement `background`/`border`/`box-shadow`/`border-radius`).

- [ ] **Step 4 : Vérifier (pas de régression + JS valide)**

Run : `.venv\Scripts\python.exe manage.py test dashboard`
Expected : PASS (les tests de page `PhysicalRiskPageViewTests` restent verts ; le tooltip est rendu côté client, donc non asservi par un test serveur).
Vérifier que `physical_risk.js` ne comporte pas d'erreur de syntaxe évidente (accolades/backticks équilibrés dans les blocs modifiés). La vérification visuelle du tooltip se fait en lançant l'app (hors boucle de test automatisée).

- [ ] **Step 5 : Commit**

```bash
git add dashboard/static/dashboard/js/physical_risk.js dashboard/static/dashboard/css/style.css
git commit -m "feat(risk): tooltip d'inventaire mesuré au survol du nom d'asset"
```

---

## Self-Review

**Couverture du spec :**
- §2.1 backend champ `inventory` (sous-ensemble water/co2/surface_area, année récente, non nuls, libellé « Usage des sols », additif, chargement en masse) → Task 1.
- §2.2 frontend tooltip au survol du nom (réutilise le pattern `pr-vuln-tooltip`) → Task 2.
- §2.3 hors périmètre (formule inchangée, pas de carte, Location différée) → respecté (aucune tâche ne touche `annual_loss`/carte/géographie).
- §3 tests → Task 1 (backend, auto). Frontend non auto-testable (rendu client) — vérification manuelle notée.

**Placeholders :** aucun. La note CSS (« vérifier les variables ») est une consigne de robustesse, pas un placeholder — le bloc CSS est fourni complet.

**Cohérence des types/noms :** `inventory: [{name, value, unit}]` produit par Task 1 == consommé par Task 2 (`e.name`/`e.value`/`e.unit`). Constantes `_RISK_INVENTORY_KEYS`/`_RISK_INVENTORY_LABELS` cohérentes entre elles. Ordre déterministe (water, co2, surface_area).

**Note :** le frontend (tooltip JS/CSS) n'a pas de test automatisé — c'est inhérent à un rendu client-side. Le backend (la donnée) est entièrement testé. La vérification visuelle du tooltip relève d'un lancement de l'app.
