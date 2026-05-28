# Dashboard Test Page — Design Spec

**Date:** 2026-05-28  
**Project:** Easybiodiv (Django 6.0.5)

## Objectif

Créer une page de test minimale pour l'app `dashboard` qui valide :
- la configuration des fichiers statiques (CSS et JS vanille)
- le câblage URLs → view → template

## Architecture des fichiers statiques

Approche retenue : **statics dans l'app** (convention Django native).

```
dashboard/
├── static/
│   └── dashboard/
│       ├── css/style.css
│       └── js/main.js
├── templates/
│   └── dashboard/
│       └── index.html
├── urls.py
└── views.py
```

Aucune modification de `STATICFILES_DIRS` requise. `APP_DIRS=True` et `django.contrib.staticfiles` dans `INSTALLED_APPS` suffisent. Ajouter `STATIC_ROOT = BASE_DIR / 'staticfiles'` dans `settings.py` pour `collectstatic`.

## URL Routing

- `easybiodiv/urls.py` inclut `dashboard.urls` avec le préfixe `''`
- `dashboard/urls.py` déclare `path('', views.index, name='dashboard-index')`
- Route finale : `GET /` → vue `index`

## Vue

Fonction `index(request)` dans `dashboard/views.py` : renvoie simplement `render(request, 'dashboard/index.html')`.

## Template

Page HTML standalone (`{% load static %}`), pas d'héritage de base pour ce test.

Contenu :
- `<link>` vers `dashboard/css/style.css`
- `<script>` vers `dashboard/js/main.js`
- Titre `<h1>` : "Easybiodiv"
- Paragraphe de présentation
- Bouton "Tester les statics" — un clic bascule une classe CSS via JS

## CSS

- Reset minimal (`box-sizing`, `margin`, `padding`)
- Centrage de la page (`max-width`, `margin: auto`)
- Style du bouton (couleur de base + classe `.active` pour la couleur alternative)

## JS

- `DOMContentLoaded` : attache un `click` listener sur le bouton
- Le clic ajoute/retire la classe `active` sur le bouton

## Critère de succès

Charger `http://127.0.0.1:8000/` affiche la page, le titre est stylé par le CSS, le clic sur le bouton change sa couleur (preuve que le JS est chargé).
