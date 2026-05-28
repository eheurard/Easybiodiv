# Dashboard Test Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Créer une page de test minimale sur `/` dans l'app `dashboard`, avec CSS et JS vanille chargés via le système de statics Django.

**Architecture:** Les fichiers statiques vivent dans `dashboard/static/dashboard/` (convention `APP_DIRS`). La vue `index` dans `dashboard/views.py` rend `dashboard/index.html`. Le routeur principal inclut `dashboard.urls`.

**Tech Stack:** Django 6.0.5, HTML5, CSS3 vanille, JS ES6 vanille, pytest-django

---

## File Map

| Fichier | Action | Responsabilité |
|---|---|---|
| `easybiodiv/settings.py` | Modifier | Ajouter `STATIC_ROOT` |
| `easybiodiv/urls.py` | Modifier | Inclure `dashboard.urls` |
| `dashboard/urls.py` | Créer | Déclarer route `/` → `index` |
| `dashboard/views.py` | Modifier | Vue `index` |
| `dashboard/templates/dashboard/index.html` | Créer | Template HTML de test |
| `dashboard/static/dashboard/css/style.css` | Créer | Styles vanille |
| `dashboard/static/dashboard/js/main.js` | Créer | Comportement bouton |
| `dashboard/tests.py` | Modifier | Tests de la vue |

---

### Task 1 : Configurer `STATIC_ROOT` dans settings

**Files:**
- Modify: `easybiodiv/settings.py`

- [ ] **Step 1 : Ajouter `STATIC_ROOT` en fin de fichier**

Dans `easybiodiv/settings.py`, après la ligne `STATIC_URL = 'static/'`, ajouter :

```python
STATIC_ROOT = BASE_DIR / 'staticfiles'
```

- [ ] **Step 2 : Vérifier que le serveur démarre toujours**

```bash
.\venv\Scripts\python manage.py check
```

Expected output : `System check identified no issues (0 silenced).`

- [ ] **Step 3 : Commit**

```bash
git add easybiodiv/settings.py
git commit -m "feat: add STATIC_ROOT to settings"
```

---

### Task 2 : Créer `dashboard/urls.py` et brancher dans le routeur principal

**Files:**
- Create: `dashboard/urls.py`
- Modify: `easybiodiv/urls.py`

- [ ] **Step 1 : Créer `dashboard/urls.py`**

```python
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
]
```

- [ ] **Step 2 : Mettre à jour `easybiodiv/urls.py`**

Remplacer le contenu par :

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
]
```

- [ ] **Step 3 : Vérifier les URLs**

```bash
.\venv\Scripts\python manage.py check
```

Expected output : `System check identified no issues (0 silenced).`

- [ ] **Step 4 : Commit**

```bash
git add dashboard/urls.py easybiodiv/urls.py
git commit -m "feat: wire dashboard URLs into main router"
```

---

### Task 3 : Écrire le test de la vue, puis implémenter la vue

**Files:**
- Modify: `dashboard/tests.py`
- Modify: `dashboard/views.py`

- [ ] **Step 1 : Écrire les tests dans `dashboard/tests.py`**

```python
from django.test import TestCase
from django.urls import reverse


class DashboardIndexViewTests(TestCase):

    def test_index_returns_200(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)

    def test_index_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertTemplateUsed(response, 'dashboard/index.html')
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

```bash
.\venv\Scripts\python manage.py test dashboard
```

Expected : `ERROR` — `AttributeError: module 'dashboard.views' has no attribute 'index'`

- [ ] **Step 3 : Implémenter la vue dans `dashboard/views.py`**

```python
from django.shortcuts import render


def index(request):
    return render(request, 'dashboard/index.html')
```

- [ ] **Step 4 : Lancer les tests — ils doivent échouer pour une autre raison**

```bash
.\venv\Scripts\python manage.py test dashboard
```

Expected : `ERROR` — `django.template.exceptions.TemplateDoesNotExist: dashboard/index.html`
(La vue existe, mais le template n'existe pas encore — c'est attendu.)

- [ ] **Step 5 : Commit**

```bash
git add dashboard/tests.py dashboard/views.py
git commit -m "feat: add dashboard index view and tests"
```

---

### Task 4 : Créer les fichiers statiques CSS et JS

**Files:**
- Create: `dashboard/static/dashboard/css/style.css`
- Create: `dashboard/static/dashboard/js/main.js`

- [ ] **Step 1 : Créer l'arborescence statique**

```bash
mkdir dashboard\static\dashboard\css
mkdir dashboard\static\dashboard\js
```

- [ ] **Step 2 : Créer `dashboard/static/dashboard/css/style.css`**

```css
*, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: system-ui, sans-serif;
    background-color: #f5f5f5;
    color: #1a1a1a;
    display: flex;
    justify-content: center;
    padding: 4rem 1rem;
}

.container {
    max-width: 600px;
    width: 100%;
    text-align: center;
}

h1 {
    font-size: 2.5rem;
    margin-bottom: 1rem;
    color: #2d6a4f;
}

p {
    font-size: 1.1rem;
    margin-bottom: 2rem;
    color: #444;
}

.test-btn {
    display: inline-block;
    padding: 0.75rem 2rem;
    font-size: 1rem;
    font-weight: 600;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    background-color: #2d6a4f;
    color: #fff;
    transition: background-color 0.2s ease;
}

.test-btn.active {
    background-color: #74c69d;
    color: #1a1a1a;
}
```

- [ ] **Step 3 : Créer `dashboard/static/dashboard/js/main.js`**

```javascript
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('test-btn');
    btn.addEventListener('click', () => {
        btn.classList.toggle('active');
    });
});
```

- [ ] **Step 4 : Commit**

```bash
git add dashboard/static/
git commit -m "feat: add dashboard CSS and JS static files"
```

---

### Task 5 : Créer le template HTML

**Files:**
- Create: `dashboard/templates/dashboard/index.html`

- [ ] **Step 1 : Créer l'arborescence templates**

```bash
mkdir dashboard\templates\dashboard
```

- [ ] **Step 2 : Créer `dashboard/templates/dashboard/index.html`**

```html
{% load static %}
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Easybiodiv</title>
    <link rel="stylesheet" href="{% static 'dashboard/css/style.css' %}">
</head>
<body>
    <div class="container">
        <h1>Easybiodiv</h1>
        <p>Plateforme de partage et de suivi de la biodiversité.</p>
        <button id="test-btn" class="test-btn">Tester les statics</button>
    </div>
    <script src="{% static 'dashboard/js/main.js' %}"></script>
</body>
</html>
```

- [ ] **Step 3 : Lancer les tests — ils doivent maintenant passer**

```bash
.\venv\Scripts\python manage.py test dashboard
```

Expected :
```
Found 2 test(s).
..
----------------------------------------------------------------------
Ran 2 tests in 0.XXXs

OK
```

- [ ] **Step 4 : Vérifier manuellement dans le navigateur**

```bash
.\venv\Scripts\python manage.py runserver
```

Ouvrir `http://127.0.0.1:8000/` — vérifier :
- Le titre "Easybiodiv" est affiché en vert foncé
- Le clic sur le bouton change sa couleur (vert clair)
- Aucune erreur 404 dans la console du navigateur pour les fichiers statiques

- [ ] **Step 5 : Commit**

```bash
git add dashboard/templates/
git commit -m "feat: add dashboard index template with static files"
```
