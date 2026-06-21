# Portfolio Analysis — Design

> Date : 2026-06-21
> Statut : validé (brainstorming) — prêt pour planification d'implémentation

## 1. Objectif

Ajouter une page **Portfolio analysis** permettant de créer un portefeuille (fonds)
en sélectionnant des entreprises de la base, puis de naviguer entre plusieurs onglets
d'analyse. Cette itération livre **l'onglet Création** complet et la **coquille de
navigation à onglets**, les autres onglets étant des placeholders « à venir ».

Onglets prévus : `Création` · `Impact` · `Risque physique` · `Risque de transition` ·
`Risque composite` · `Scénario`.

## 2. Décisions de cadrage

| Sujet | Décision |
|-------|----------|
| Persistance | Nouveaux modèles Django en base. |
| Emplacement du code | Dans l'app existante **`dashboard`**. |
| Mécanique des onglets | **Une URL** `/portfolio/` + onglets JS in-page (pattern ESG). |
| Benchmark | Un autre `Portfolio` marqué `is_benchmark=True` (auto-référence). |
| Pondération | Montant **et** poids % stockés, **synchronisés** côté front. |
| Pop-up financière | Type Equity/Bond + champs obligataires **conditionnels** (maturité, coupon, valeur nominale). |
| Portée de l'itération | Onglet Création complet + 5 onglets placeholder. |

## 3. Modèle de données

Trois modèles ajoutés à `dashboard/models.py`, suivant les conventions du projet
(`created_at`/`updated_at`/`created_by`, `TextChoices`, compatibilité SQLite/Postgres).

```python
class Portfolio(models.Model):
    name = models.CharField(max_length=255)
    size = models.FloatField(default=0)                 # taille du fonds (devise)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    benchmark = models.ForeignKey('self', on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='benchmarked_by')
    is_benchmark = models.BooleanField(default=False)   # peut servir de benchmark
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.SET_NULL, null=True, blank=True)


class PortfolioHolding(models.Model):
    class Instrument(models.TextChoices):
        EQUITY = 'EQUITY', 'Action (Equity)'
        BOND   = 'BOND',   'Obligation (Bond)'

    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE,
                                  related_name='holdings')
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    amount = models.FloatField(default=0)               # montant investi (devise du fonds)
    weight = models.FloatField(default=0)               # poids en % (0–100)
    instrument_type = models.CharField(max_length=10, choices=Instrument.choices,
                                       default=Instrument.EQUITY)
    # champs obligataires (utilisés seulement si instrument_type == BOND)
    maturity_date = models.DateField(null=True, blank=True)
    coupon_rate = models.FloatField(null=True, blank=True)   # %
    face_value = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ('portfolio', 'company')
```

Notes :
- `benchmark` est une auto-référence ; la liste des benchmarks proposés à l'UI est
  filtrée sur `is_benchmark=True`.
- `amount` et `weight` sont tous deux persistés (saisie synchronisée), pour éviter
  les recalculs et gérer le cas où la somme des montants ≠ taille du fonds.
- Champs obligataires `null=True` : présents mais inertes pour les actions ;
  pas de JSONField ni de type Postgres-only → compatible SQLite.
- Migration : `makemigrations dashboard --name add_portfolio_models`.

## 4. URLs, vues et flux de sauvegarde

Ajouts dans `dashboard/urls.py` (namespace `dashboard`) :

```python
path('portfolio/', views.portfolio_analysis, name='portfolio_analysis'),
path('api/portfolio/save/', views.portfolio_save, name='portfolio_save'),
path('api/portfolio/<int:pk>/', views.portfolio_detail, name='portfolio_detail'),
```

Toutes les vues sous `@login_required`.

### `portfolio_analysis` (GET)
Rend la coquille à onglets. Passe au template via `json_script` (pattern ESG) :
- `companies` : `[{id, name, isin, ticker}]` (recherche/ajout d'entreprise) ;
- `currencies` : `[{id, code, symbol}]` (menu devise) ;
- `benchmarks` : portefeuilles `is_benchmark=True` → `[{id, name}]` ;
- `portfolios` : portefeuilles existants de l'utilisateur → `[{id, name}]` (combobox header).

### `portfolio_save` (POST, JSON)
Reçoit :
```json
{
  "id": 0,
  "name": "...", "size": 0, "currency_id": 0,
  "benchmark_id": null, "is_benchmark": false,
  "holdings": [
    {"company_id": 0, "amount": 0, "weight": 0,
     "instrument_type": "EQUITY|BOND",
     "maturity_date": null, "coupon_rate": null, "face_value": null}
  ]
}
```
- Validation **côté serveur via Django Forms** (règle CLAUDE.md « jamais de POST brut ») :
  - `PortfolioForm` (ModelForm) pour les champs d'en-tête ;
  - validation des lignes holdings via un `HoldingForm` léger (ou validation explicite),
    bornes du poids (0–100), cohérence des champs obligataires.
- Création/mise à jour du `Portfolio` dans une **transaction** ; les `holdings` sont
  remplacés intégralement.
- `created_by = request.user` à la création.
- Réponse : `{id, ...}` en succès, `{errors: {...}}` (HTTP 400) en cas d'erreur.

### `portfolio_detail` (GET, JSON)
Renvoie un portefeuille + ses holdings pour réhydrater le formulaire lors de la
sélection d'un portefeuille existant. 404 si inexistant.

### Sécurité
- CSRF : le POST `fetch` envoie l'en-tête `X-CSRFToken` (token via `{% csrf_token %}`).
- Pas de PostGIS / JSONField → compatible SQLite et Postgres.

## 5. Onglet Création — UI

Fichiers :
- `dashboard/templates/dashboard/portfolio.html`
- `dashboard/static/dashboard/js/portfolio.js`
- styles ajoutés à `dashboard/static/dashboard/css/style.css` (réutilise `card`,
  `form-input`, `label-caps`, motifs combobox existants).

### En-tête de page
Combobox de sélection d'un portefeuille existant (réutilise le pattern
`company-combobox`) + bouton **« Nouveau portefeuille »** (réinitialise le formulaire).

### Panneau Création — deux blocs

**Bloc 1 — Paramètres du fonds** (carte) :
`Nom du fonds` (texte) · `Taille du fonds` (nombre) · `Devise` (select ← `currencies`)
· `Benchmark` (select ← `benchmarks`, option « Aucun ») · case **« Utiliser comme
benchmark »** (`is_benchmark`).

**Bloc 2 — Composition** (carte) :
- **Barre d'ajout** : combobox de recherche d'entreprise (← `companies`) → ajoute une ligne.
- **Tableau** des positions, une ligne par entreprise :
  `Entreprise | Montant (devise) | Poids (%) | [⚙ détails] | [🗑 supprimer]`.
- **Synchronisation montant ⟷ %** : modifier le montant recalcule le poids
  (= montant / taille × 100) et inversement.
- **Pied de tableau** : total des poids avec indicateur visuel (vert si ≈ 100 %,
  ambre sinon) + total des montants.
- Bouton **« Enregistrer le portefeuille »** → POST `portfolio_save`.

### Pop-up financière (modale)
Ouverte par le bouton ⚙ d'une ligne :
- `<dialog>` natif HTML (vanilla, accessible, fermeture Échap), aucune dépendance ajoutée ;
- **Type d'instrument** : `Action` / `Obligation` ;
- champs **obligataires** (`Maturité` date, `Taux de coupon` %, `Valeur nominale`)
  **masqués** tant que le type ≠ Obligation (affichage conditionnel JS) ;
- boutons **Valider** (stocke les valeurs sur l'objet ligne en mémoire JS) / **Annuler**.
- Les détails restent en mémoire JS par ligne et sont envoyés à l'enregistrement.
- Pastille sur le bouton ⚙ signalant qu'une ligne a des détails obligataires renseignés.

Accessibilité : `<dialog>`, labels liés, navigation clavier, contraste AA.

## 6. Coquille à onglets + navigation

- **Barre d'onglets** (pattern `data-tab` / `data-tab-panel` comme `esg-theme-tabs`),
  6 onglets ; **Création** actif par défaut.
- 5 autres onglets : placeholders réutilisant le motif
  `<div class="card esg-coming"><p class="esg-empty">… — à venir</p></div>`.
- Bascule purement JS (afficher/masquer), `role="tab"` / `aria-selected`.
- **Sidebar** (`templates/base.html`) : nouvelle entrée `Portfolio analysis`
  (lien `dashboard:portfolio_analysis`, `{% block nav_portfolio %}`), placée après
  « Comparaison ». Le template définit `{% block nav_portfolio %}active{% endblock %}`.

## 7. Tests

`dashboard/tests.py` (≥ 1 cas nominal + 1 cas d'erreur par élément, cf. CLAUDE.md) :
- **Modèles** : création nominale `Portfolio`/`PortfolioHolding` ; `unique_together`
  (company dupliquée → erreur) ; auto-référence benchmark.
- **`portfolio_save`** : POST JSON valide → portefeuille + holdings créés ; POST
  invalide (devise manquante / poids hors bornes) → erreurs JSON, rien créé.
- **`portfolio_detail`** : réhydratation correcte ; 404 si inexistant.
- **`portfolio_analysis` (GET)** : 200, contexte (companies/currencies/benchmarks)
  présent ; `@login_required` redirige l'anonyme.

## 8. Hors périmètre (itérations ultérieures)

- Contenu réel des onglets Impact, Risque physique, Risque de transition, Risque
  composite, Scénario.
- Calculs de benchmark (comparaison portefeuille vs benchmark).
- Champs actions étendus (nombre d'actions, dividende) et métadonnées de position
  (ISIN par position, date d'acquisition, commentaire).
