# Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implémenter login, inscription, logout et reset de mot de passe dans l'app `authentication`, avec les pages d'authentification autonomes (pas de sidebar), le dashboard restant public.

**Architecture:** Django built-in auth views pour login/logout/password-reset, une FBV custom pour l'inscription. Tout est dans l'app `authentication` (forms.py, urls.py, views.py, admin.py, templates, static). Le modèle User existant est mis à jour (role=SUBSCRIBER par défaut, profile_photo optionnelle).

**Tech Stack:** Django 6.0.5, `django.contrib.auth.views`, HTML/CSS vanilla, Django TestCase.

---

## Fichiers créés / modifiés

| Fichier | Action | Rôle |
|---|---|---|
| `authentication/models.py` | Modifier | Ajouter `default=SUBSCRIBER` + `blank/null` photo |
| `authentication/migrations/0002_*.py` | Créer (via makemigrations) | Migration des changements modèle |
| `authentication/forms.py` | Créer | `RegisterForm` héritant `UserCreationForm` |
| `authentication/views.py` | Modifier | FBV `register_view` |
| `authentication/urls.py` | Créer | Routes auth + built-in views configurées |
| `authentication/admin.py` | Modifier | `UserAdmin` avec champ `role` |
| `authentication/tests/__init__.py` | Créer | Package tests |
| `authentication/tests/test_models.py` | Créer | Tests modèle |
| `authentication/tests/test_forms.py` | Créer | Tests formulaire |
| `authentication/tests/test_views.py` | Créer | Tests vues |
| `authentication/static/authentication/css/auth.css` | Créer | Styles des pages auth |
| `authentication/templates/authentication/auth_base.html` | Créer | Layout partagé (sans sidebar) |
| `authentication/templates/authentication/login.html` | Créer | Page connexion |
| `authentication/templates/authentication/register.html` | Créer | Page inscription |
| `authentication/templates/authentication/password_reset.html` | Créer | Saisie email reset |
| `authentication/templates/authentication/password_reset_done.html` | Créer | Confirmation envoi email |
| `authentication/templates/authentication/password_reset_confirm.html` | Créer | Nouveau mot de passe |
| `authentication/templates/authentication/password_reset_complete.html` | Créer | Succès reset |
| `authentication/templates/authentication/logged_out.html` | Créer | Fallback déconnexion |
| `authentication/templates/authentication/password_reset_email.html` | Créer | Corps de l'email reset |
| `authentication/templates/authentication/password_reset_subject.txt` | Créer | Sujet de l'email reset |
| `easybiodiv/settings.py` | Modifier | LOGIN_REDIRECT_URL, LOGOUT_REDIRECT_URL, EMAIL_BACKEND |
| `easybiodiv/urls.py` | Modifier | Inclure `authentication.urls` |
| `requirements.txt` | Modifier | Ajouter Pillow |

---

## Task 1 — Mise à jour du modèle User

**Files:**
- Modify: `authentication/models.py`
- Create (auto): `authentication/migrations/0002_user_optional_photo_and_default_role.py`

- [ ] **Étape 1 : Créer le répertoire de tests**

```
authentication/
└── tests/
    └── __init__.py
```

Créer `authentication/tests/__init__.py` (fichier vide).

- [ ] **Étape 2 : Écrire le test modèle (échec attendu)**

Créer `authentication/tests/test_models.py` :

```python
from django.test import TestCase
from authentication.models import User


class UserDefaultsTest(TestCase):
    def test_new_user_has_subscriber_role(self):
        user = User.objects.create_user(username='alice', password='Pass1234!')
        self.assertEqual(user.role, User.SUBSCRIBER)

    def test_profile_photo_is_optional(self):
        user = User.objects.create_user(username='bob', password='Pass1234!')
        # ImageField vide → falsy
        self.assertFalse(user.profile_photo)
```

- [ ] **Étape 3 : Lancer les tests — vérifier l'échec**

```
python manage.py test authentication.tests.test_models -v 2
```

Attendu : FAIL — `IntegrityError` ou erreur de contrainte sur `role` (pas de default).

- [ ] **Étape 4 : Mettre à jour le modèle**

Remplacer le contenu de `authentication/models.py` :

```python
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    CREATOR = 'CREATOR'
    SUBSCRIBER = 'SUBSCRIBER'

    ROLE_CHOICES = (
        (CREATOR, 'Créateur'),
        (SUBSCRIBER, 'Abonné'),
    )

    profile_photo = models.ImageField(
        verbose_name='Photo de profil',
        blank=True,
        null=True,
    )
    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default=SUBSCRIBER,
        verbose_name='Rôle',
    )
```

- [ ] **Étape 5 : Générer et appliquer la migration**

```
python manage.py makemigrations authentication --name user_optional_photo_and_default_role
python manage.py migrate
```

Attendu : `OK` sur les deux commandes.

- [ ] **Étape 6 : Lancer les tests — vérifier le succès**

```
python manage.py test authentication.tests.test_models -v 2
```

Attendu : `OK` (2 tests).

- [ ] **Étape 7 : Commit**

```
git add authentication/models.py authentication/migrations/0002_user_optional_photo_and_default_role.py authentication/tests/__init__.py authentication/tests/test_models.py
git commit -m "feat: set default role SUBSCRIBER and make profile_photo optional"
```

---

## Task 2 — RegisterForm

**Files:**
- Create: `authentication/forms.py`
- Create: `authentication/tests/test_forms.py`

- [ ] **Étape 1 : Écrire les tests formulaire (échec attendu)**

Créer `authentication/tests/test_forms.py` :

```python
from django.test import TestCase
from authentication.forms import RegisterForm
from authentication.models import User


class RegisterFormTest(TestCase):
    valid_data = {
        'username': 'newuser',
        'email': 'new@example.com',
        'password1': 'TestPass123!',
        'password2': 'TestPass123!',
    }

    def test_valid_form(self):
        form = RegisterForm(self.valid_data)
        self.assertTrue(form.is_valid())

    def test_email_is_required(self):
        data = {**self.valid_data, 'email': ''}
        form = RegisterForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_passwords_must_match(self):
        data = {**self.valid_data, 'password2': 'Different!'}
        form = RegisterForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)

    def test_save_assigns_subscriber_role(self):
        form = RegisterForm(self.valid_data)
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertEqual(user.role, User.SUBSCRIBER)

    def test_save_stores_email(self):
        form = RegisterForm(self.valid_data)
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertEqual(user.email, 'new@example.com')
```

- [ ] **Étape 2 : Lancer les tests — vérifier l'échec**

```
python manage.py test authentication.tests.test_forms -v 2
```

Attendu : `ImportError` — `RegisterForm` n'existe pas encore.

- [ ] **Étape 3 : Créer `authentication/forms.py`**

```python
from django.contrib.auth.forms import UserCreationForm
from django import forms
from .models import User


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, label='Adresse email')

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = User.SUBSCRIBER
        if commit:
            user.save()
        return user
```

- [ ] **Étape 4 : Lancer les tests — vérifier le succès**

```
python manage.py test authentication.tests.test_forms -v 2
```

Attendu : `OK` (5 tests).

- [ ] **Étape 5 : Commit**

```
git add authentication/forms.py authentication/tests/test_forms.py
git commit -m "feat: add RegisterForm with SUBSCRIBER default and email field"
```

---

## Task 3 — Admin

**Files:**
- Modify: `authentication/admin.py`

- [ ] **Étape 1 : Remplacer `authentication/admin.py`**

```python
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Rôle & Profil', {'fields': ('role', 'profile_photo')}),
    )
    list_display = ('username', 'email', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
```

- [ ] **Étape 2 : Vérifier dans le navigateur**

```
python manage.py runserver
```

Ouvrir `http://127.0.0.1:8000/admin/authentication/user/`. Le champ **Rôle** doit apparaître dans la section "Rôle & Profil" du détail d'un utilisateur.

- [ ] **Étape 3 : Commit**

```
git add authentication/admin.py
git commit -m "feat: register User in admin with role and profile_photo fields"
```

---

## Task 4 — Settings & URLs

**Files:**
- Modify: `easybiodiv/settings.py`
- Create: `authentication/urls.py`
- Modify: `easybiodiv/urls.py`
- Modify: `requirements.txt`

- [ ] **Étape 1 : Mettre à jour `requirements.txt`**

Ajouter `Pillow` à la fin du fichier `requirements.txt`.

- [ ] **Étape 2 : Ajouter les settings auth**

Dans `easybiodiv/settings.py`, ajouter à la fin du fichier :

```python
# Auth redirects
LOGIN_REDIRECT_URL = 'dashboard:index'
LOGOUT_REDIRECT_URL = 'dashboard:index'

# Email (console en dev — configurer SMTP en prod)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

- [ ] **Étape 3 : Créer `authentication/urls.py`**

```python
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from . import views

app_name = 'authentication'

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(
        template_name='authentication/login.html',
        redirect_authenticated_user=True,
    ), name='login'),

    path('logout/', auth_views.LogoutView.as_view(
        next_page='dashboard:index',
    ), name='logout'),

    path('register/', views.register_view, name='register'),

    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='authentication/password_reset.html',
        email_template_name='authentication/password_reset_email.html',
        subject_template_name='authentication/password_reset_subject.txt',
        success_url=reverse_lazy('authentication:password_reset_done'),
    ), name='password_reset'),

    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='authentication/password_reset_done.html',
    ), name='password_reset_done'),

    path('password-reset/confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='authentication/password_reset_confirm.html',
        success_url=reverse_lazy('authentication:password_reset_complete'),
    ), name='password_reset_confirm'),

    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='authentication/password_reset_complete.html',
    ), name='password_reset_complete'),
]
```

- [ ] **Étape 4 : Inclure dans `easybiodiv/urls.py`**

Remplacer le contenu de `easybiodiv/urls.py` :

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('authentication.urls')),
    path('', include('dashboard.urls')),
]
```

- [ ] **Étape 5 : Ajouter un stub `register_view` pour débloquer le démarrage**

`authentication/views.py` importe `register_view` dès le chargement des URLs. Ajouter un stub temporaire (remplacé en Task 5) :

```python
from django.http import HttpResponse


def register_view(request):
    return HttpResponse('stub — implémenté en Task 5')
```

- [ ] **Étape 6 : Vérifier la configuration**

```
python manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

- [ ] **Étape 7 : Commit**

```
git add easybiodiv/settings.py authentication/urls.py easybiodiv/urls.py authentication/views.py requirements.txt
git commit -m "feat: wire authentication URLs and configure auth settings"
```

---

## Task 5 — register_view + tests de vues

**Files:**
- Modify: `authentication/views.py`
- Create: `authentication/tests/test_views.py`

- [ ] **Étape 1 : Écrire les tests de vues (échec attendu)**

Créer `authentication/tests/test_views.py` :

```python
from django.test import TestCase
from django.urls import reverse
from authentication.models import User


class RegisterViewTest(TestCase):
    valid_data = {
        'username': 'newuser',
        'email': 'new@example.com',
        'password1': 'TestPass123!',
        'password2': 'TestPass123!',
    }

    def test_get_returns_200(self):
        response = self.client.get(reverse('authentication:register'))
        self.assertEqual(response.status_code, 200)

    def test_get_uses_register_template(self):
        response = self.client.get(reverse('authentication:register'))
        self.assertTemplateUsed(response, 'authentication/register.html')

    def test_valid_post_redirects_to_dashboard(self):
        response = self.client.post(reverse('authentication:register'), self.valid_data)
        self.assertRedirects(response, reverse('dashboard:index'))

    def test_valid_post_creates_subscriber(self):
        self.client.post(reverse('authentication:register'), self.valid_data)
        user = User.objects.get(username='newuser')
        self.assertEqual(user.role, User.SUBSCRIBER)

    def test_valid_post_logs_user_in(self):
        self.client.post(reverse('authentication:register'), self.valid_data)
        response = self.client.get(reverse('dashboard:index'))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_invalid_post_returns_200_with_form(self):
        response = self.client.post(reverse('authentication:register'), {})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'authentication/register.html')
        self.assertIn('form', response.context)

    def test_authenticated_user_redirected(self):
        User.objects.create_user(username='existing', password='Pass1234!')
        self.client.login(username='existing', password='Pass1234!')
        response = self.client.get(reverse('authentication:register'))
        self.assertRedirects(response, reverse('dashboard:index'))


class LoginViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='TestPass123!')

    def test_get_returns_200(self):
        response = self.client.get(reverse('authentication:login'))
        self.assertEqual(response.status_code, 200)

    def test_get_uses_login_template(self):
        response = self.client.get(reverse('authentication:login'))
        self.assertTemplateUsed(response, 'authentication/login.html')

    def test_valid_login_redirects_to_dashboard(self):
        response = self.client.post(reverse('authentication:login'), {
            'username': 'testuser',
            'password': 'TestPass123!',
        })
        self.assertRedirects(response, reverse('dashboard:index'))


class LogoutViewTest(TestCase):
    def setUp(self):
        User.objects.create_user(username='testuser', password='TestPass123!')
        self.client.login(username='testuser', password='TestPass123!')

    def test_post_logout_redirects_to_dashboard(self):
        response = self.client.post(reverse('authentication:logout'))
        self.assertRedirects(response, reverse('dashboard:index'))
```

- [ ] **Étape 2 : Lancer les tests — vérifier l'échec**

```
python manage.py test authentication.tests.test_views -v 2
```

Attendu : `TemplateDoesNotExist` (templates pas encore créés) ou `ImportError` sur `register_view`.

- [ ] **Étape 3 : Implémenter `register_view` dans `authentication/views.py`**

```python
from django.contrib.auth import login
from django.shortcuts import render, redirect
from .forms import RegisterForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:index')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('dashboard:index')
    return render(request, 'authentication/register.html', {'form': form})
```

- [ ] **Étape 4 : Créer les templates vides pour débloquer les tests**

Créer les répertoires et fichiers suivants avec un contenu minimal (les vrais templates arrivent en Task 7-8) :

`authentication/templates/authentication/login.html` :
```html
<!DOCTYPE html><html><body>login</body></html>
```

`authentication/templates/authentication/register.html` :
```html
<!DOCTYPE html><html><body>{% if form %}register{% endif %}</body></html>
```

- [ ] **Étape 5 : Lancer les tests — vérifier le succès**

```
python manage.py test authentication.tests.test_views -v 2
```

Attendu : `OK` (11 tests).

- [ ] **Étape 6 : Lancer tous les tests**

```
python manage.py test authentication -v 2
```

Attendu : `OK` (18 tests au total).

- [ ] **Étape 7 : Commit**

```
git add authentication/views.py authentication/tests/test_views.py authentication/templates/
git commit -m "feat: implement register_view with auto-login and SUBSCRIBER role"
```

---

## Task 6 — CSS des pages auth

**Files:**
- Create: `authentication/static/authentication/css/auth.css`

- [ ] **Étape 1 : Créer le répertoire static**

```
authentication/static/authentication/css/
```

- [ ] **Étape 2 : Créer `authentication/static/authentication/css/auth.css`**

```css
/* ── Auth pages — Terra Insight design system ─────────────────────────── */

*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

:root {
  --color-primary:       #91452d;
  --color-primary-dark:  #77321b;
  --color-surface:       #fbf9f4;
  --color-surface-low:   #f5f3ee;
  --color-surface-mid:   #f0eee9;
  --color-on-surface:    #1b1c19;
  --color-on-variant:    #54433e;
  --color-muted:         #87736d;
  --color-outline:       #dac1ba;
  --color-error:         #ba1a1a;
  --color-white:         #ffffff;

  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 12px;
}

body {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  background-color: var(--color-surface);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E");
  color: var(--color-on-surface);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

/* ── Brand ───────────────────────────────────────────────────────────── */
.auth-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 28px;
  text-decoration: none;
}

.auth-brand__logo {
  width: 38px;
  height: 38px;
  background: var(--color-primary);
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.auth-brand__text {
  display: flex;
  flex-direction: column;
}

.auth-brand__name {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-on-surface);
  letter-spacing: -0.01em;
  line-height: 1.2;
}

.auth-brand__tagline {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-muted);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

/* ── Card ────────────────────────────────────────────────────────────── */
.auth-card {
  background: var(--color-white);
  border: 1px solid var(--color-outline);
  border-radius: var(--radius-lg);
  padding: 36px 40px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 4px 24px rgba(115, 107, 94, 0.07);
}

.auth-card__title {
  font-size: 22px;
  font-weight: 600;
  color: var(--color-on-surface);
  letter-spacing: -0.01em;
  margin-bottom: 4px;
}

.auth-card__subtitle {
  font-size: 14px;
  color: var(--color-muted);
  margin-bottom: 28px;
}

/* ── Form elements ───────────────────────────────────────────────────── */
.auth-form__group {
  margin-bottom: 18px;
}

.auth-form__label {
  display: block;
  font-size: 11px;
  font-weight: 700;
  color: var(--color-on-variant);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.auth-form__input {
  display: block;
  width: 100%;
  padding: 10px 14px;
  font-size: 15px;
  font-family: inherit;
  color: var(--color-on-surface);
  background: var(--color-surface-low);
  border: 1px solid var(--color-outline);
  border-radius: var(--radius-md);
  outline: none;
  transition: border-color 0.15s, background-color 0.15s;
}

.auth-form__input:focus {
  border-color: var(--color-primary);
  background: var(--color-white);
}

.auth-form__input::placeholder {
  color: var(--color-muted);
  opacity: 0.7;
}

.auth-form__errors {
  list-style: none;
  margin-top: 5px;
}

.auth-form__error {
  font-size: 12px;
  color: var(--color-error);
}

/* Messages d'erreur non-field (ex: login incorrect) */
.auth-form__global-errors {
  background: #ffdad6;
  border: 1px solid #ffb4ab;
  border-radius: var(--radius-md);
  padding: 10px 14px;
  margin-bottom: 20px;
  list-style: none;
}

.auth-form__global-error {
  font-size: 13px;
  color: #93000a;
}

/* ── Forgot password link ─────────────────────────────────────────────── */
.auth-form__forgot {
  display: block;
  text-align: right;
  font-size: 13px;
  color: var(--color-primary);
  text-decoration: none;
  margin-top: -10px;
  margin-bottom: 20px;
}

.auth-form__forgot:hover {
  text-decoration: underline;
}

/* ── Primary button ──────────────────────────────────────────────────── */
.auth-btn {
  display: block;
  width: 100%;
  padding: 11px;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  letter-spacing: 0.01em;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color 0.15s;
  margin-top: 8px;
}

.auth-btn--primary {
  background: var(--color-primary);
  color: var(--color-white);
}

.auth-btn--primary:hover {
  background: var(--color-primary-dark);
}

/* ── Divider ─────────────────────────────────────────────────────────── */
.auth-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 22px 0;
  font-size: 12px;
  color: var(--color-outline);
}

.auth-divider::before,
.auth-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--color-outline);
}

/* ── Secondary link ──────────────────────────────────────────────────── */
.auth-link-row {
  text-align: center;
  font-size: 14px;
  color: var(--color-muted);
}

.auth-link-row a {
  color: var(--color-primary);
  text-decoration: none;
  font-weight: 500;
}

.auth-link-row a:hover {
  text-decoration: underline;
}

/* ── Back to site ────────────────────────────────────────────────────── */
.auth-back {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 22px;
  font-size: 13px;
  color: var(--color-muted);
  text-decoration: none;
  transition: color 0.15s;
}

.auth-back:hover {
  color: var(--color-primary);
}

/* ── Info block (password_reset_done, complete) ───────────────────────── */
.auth-info {
  text-align: center;
  padding: 8px 0;
}

.auth-info__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  background: #ffdbd0;
  border-radius: 50%;
  margin: 0 auto 20px;
}

.auth-info__text {
  font-size: 15px;
  color: var(--color-on-variant);
  line-height: 1.6;
  margin-bottom: 20px;
}

/* ── Responsive ──────────────────────────────────────────────────────── */
@media (max-width: 480px) {
  .auth-card {
    padding: 28px 24px;
  }
}
```

- [ ] **Étape 3 : Commit**

```
git add authentication/static/
git commit -m "feat: add auth CSS with Terra Insight design tokens"
```

---

## Task 7 — Templates : auth_base + login + register

**Files:**
- Modify: `authentication/templates/authentication/login.html`
- Modify: `authentication/templates/authentication/register.html`
- Create: `authentication/templates/authentication/auth_base.html`

- [ ] **Étape 1 : Créer `authentication/templates/authentication/auth_base.html`**

```html
{% load static %}
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Easybiodiv{% endblock %}</title>
  <link rel="stylesheet" href="{% static 'authentication/css/auth.css' %}">
</head>
<body>

  <a href="{% url 'dashboard:index' %}" class="auth-brand" aria-label="Retour à l'accueil Easybiodiv">
    <div class="auth-brand__logo" aria-hidden="true">
      <svg width="22" height="22" viewBox="0 0 32 32" fill="none">
        <path d="M16 6C10.477 6 6 10.477 6 16s4.477 10 10 10 10-4.477 10-10S21.523 6 16 6zm0 3a7 7 0 110 14A7 7 0 0116 9zm0 2a5 5 0 100 10A5 5 0 0016 11zm0 2a3 3 0 110 6 3 3 0 010-6z" fill="#fff"/>
      </svg>
    </div>
    <div class="auth-brand__text">
      <span class="auth-brand__name">Easybiodiv</span>
      <span class="auth-brand__tagline">Biodiversité &amp; CSRD</span>
    </div>
  </a>

  <div class="auth-card" role="main">
    {% block card %}{% endblock %}
  </div>

  <a href="{% url 'dashboard:index' %}" class="auth-back" aria-label="Retour au dashboard">
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M9 11L5 7l4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    Retour au dashboard
  </a>

</body>
</html>
```

- [ ] **Étape 2 : Remplacer `authentication/templates/authentication/login.html`**

```html
{% extends "authentication/auth_base.html" %}

{% block title %}Connexion — Easybiodiv{% endblock %}

{% block card %}
  <h1 class="auth-card__title">Connexion</h1>
  <p class="auth-card__subtitle">Accédez à votre espace biodiversité</p>

  {% if form.non_field_errors %}
    <ul class="auth-form__global-errors" role="alert">
      {% for error in form.non_field_errors %}
        <li class="auth-form__global-error">{{ error }}</li>
      {% endfor %}
    </ul>
  {% endif %}

  <form method="post" novalidate>
    {% csrf_token %}

    <div class="auth-form__group">
      <label class="auth-form__label" for="{{ form.username.id_for_label }}">Identifiant</label>
      <input
        class="auth-form__input"
        type="text"
        id="{{ form.username.id_for_label }}"
        name="{{ form.username.html_name }}"
        value="{{ form.username.value|default:'' }}"
        autocomplete="username"
        autofocus
        aria-describedby="{% if form.username.errors %}id_username_errors{% endif %}"
      >
      {% if form.username.errors %}
        <ul class="auth-form__errors" id="id_username_errors">
          {% for error in form.username.errors %}
            <li class="auth-form__error">{{ error }}</li>
          {% endfor %}
        </ul>
      {% endif %}
    </div>

    <div class="auth-form__group">
      <label class="auth-form__label" for="{{ form.password.id_for_label }}">Mot de passe</label>
      <input
        class="auth-form__input"
        type="password"
        id="{{ form.password.id_for_label }}"
        name="{{ form.password.html_name }}"
        autocomplete="current-password"
        aria-describedby="{% if form.password.errors %}id_password_errors{% endif %}"
      >
      {% if form.password.errors %}
        <ul class="auth-form__errors" id="id_password_errors">
          {% for error in form.password.errors %}
            <li class="auth-form__error">{{ error }}</li>
          {% endfor %}
        </ul>
      {% endif %}
    </div>

    <a href="{% url 'authentication:password_reset' %}" class="auth-form__forgot">
      Mot de passe oublié ?
    </a>

    <button class="auth-btn auth-btn--primary" type="submit">Se connecter</button>
  </form>

  <div class="auth-divider">ou</div>

  <p class="auth-link-row">
    Pas encore de compte ?
    <a href="{% url 'authentication:register' %}">Créer un compte</a>
  </p>
{% endblock %}
```

- [ ] **Étape 3 : Remplacer `authentication/templates/authentication/register.html`**

```html
{% extends "authentication/auth_base.html" %}

{% block title %}Créer un compte — Easybiodiv{% endblock %}

{% block card %}
  <h1 class="auth-card__title">Créer un compte</h1>
  <p class="auth-card__subtitle">Rejoignez Easybiodiv gratuitement</p>

  <form method="post" novalidate>
    {% csrf_token %}

    <div class="auth-form__group">
      <label class="auth-form__label" for="{{ form.username.id_for_label }}">Identifiant</label>
      <input
        class="auth-form__input"
        type="text"
        id="{{ form.username.id_for_label }}"
        name="{{ form.username.html_name }}"
        value="{{ form.username.value|default:'' }}"
        autocomplete="username"
        autofocus
        aria-describedby="{% if form.username.errors %}id_reg_username_errors{% endif %}"
      >
      {% if form.username.errors %}
        <ul class="auth-form__errors" id="id_reg_username_errors">
          {% for error in form.username.errors %}
            <li class="auth-form__error">{{ error }}</li>
          {% endfor %}
        </ul>
      {% endif %}
    </div>

    <div class="auth-form__group">
      <label class="auth-form__label" for="{{ form.email.id_for_label }}">Adresse email</label>
      <input
        class="auth-form__input"
        type="email"
        id="{{ form.email.id_for_label }}"
        name="{{ form.email.html_name }}"
        value="{{ form.email.value|default:'' }}"
        autocomplete="email"
        aria-describedby="{% if form.email.errors %}id_email_errors{% endif %}"
      >
      {% if form.email.errors %}
        <ul class="auth-form__errors" id="id_email_errors">
          {% for error in form.email.errors %}
            <li class="auth-form__error">{{ error }}</li>
          {% endfor %}
        </ul>
      {% endif %}
    </div>

    <div class="auth-form__group">
      <label class="auth-form__label" for="{{ form.password1.id_for_label }}">Mot de passe</label>
      <input
        class="auth-form__input"
        type="password"
        id="{{ form.password1.id_for_label }}"
        name="{{ form.password1.html_name }}"
        autocomplete="new-password"
        aria-describedby="{% if form.password1.errors %}id_pwd1_errors{% endif %}"
      >
      {% if form.password1.errors %}
        <ul class="auth-form__errors" id="id_pwd1_errors">
          {% for error in form.password1.errors %}
            <li class="auth-form__error">{{ error }}</li>
          {% endfor %}
        </ul>
      {% endif %}
    </div>

    <div class="auth-form__group">
      <label class="auth-form__label" for="{{ form.password2.id_for_label }}">Confirmer le mot de passe</label>
      <input
        class="auth-form__input"
        type="password"
        id="{{ form.password2.id_for_label }}"
        name="{{ form.password2.html_name }}"
        autocomplete="new-password"
        aria-describedby="{% if form.password2.errors %}id_pwd2_errors{% endif %}"
      >
      {% if form.password2.errors %}
        <ul class="auth-form__errors" id="id_pwd2_errors">
          {% for error in form.password2.errors %}
            <li class="auth-form__error">{{ error }}</li>
          {% endfor %}
        </ul>
      {% endif %}
    </div>

    <button class="auth-btn auth-btn--primary" type="submit">Créer mon compte</button>
  </form>

  <div class="auth-divider">ou</div>

  <p class="auth-link-row">
    Déjà un compte ?
    <a href="{% url 'authentication:login' %}">Se connecter</a>
  </p>
{% endblock %}
```

- [ ] **Étape 4 : Lancer tous les tests**

```
python manage.py test authentication -v 2
```

Attendu : `OK` (18 tests).

- [ ] **Étape 5 : Vérifier visuellement dans le navigateur**

```
python manage.py runserver
```

- `http://127.0.0.1:8000/auth/login/` → carte centrée avec formulaire login
- `http://127.0.0.1:8000/auth/register/` → formulaire inscription
- Vérifier : fond parchment, inputs stylés, bouton terra cotta, lien retour dashboard

- [ ] **Étape 6 : Commit**

```
git add authentication/templates/ authentication/static/
git commit -m "feat: add auth templates (base, login, register) with Terra Insight design"
```

---

## Task 8 — Templates password reset + email

**Files:**
- Create: `authentication/templates/authentication/password_reset.html`
- Create: `authentication/templates/authentication/password_reset_done.html`
- Create: `authentication/templates/authentication/password_reset_confirm.html`
- Create: `authentication/templates/authentication/password_reset_complete.html`
- Create: `authentication/templates/authentication/password_reset_email.html`
- Create: `authentication/templates/authentication/password_reset_subject.txt`

- [ ] **Étape 1 : Créer `authentication/templates/authentication/password_reset.html`**

```html
{% extends "authentication/auth_base.html" %}

{% block title %}Réinitialiser le mot de passe — Easybiodiv{% endblock %}

{% block card %}
  <h1 class="auth-card__title">Mot de passe oublié ?</h1>
  <p class="auth-card__subtitle">
    Entrez votre adresse email et nous vous enverrons un lien de réinitialisation.
  </p>

  <form method="post" novalidate>
    {% csrf_token %}

    <div class="auth-form__group">
      <label class="auth-form__label" for="{{ form.email.id_for_label }}">Adresse email</label>
      <input
        class="auth-form__input"
        type="email"
        id="{{ form.email.id_for_label }}"
        name="{{ form.email.html_name }}"
        value="{{ form.email.value|default:'' }}"
        autocomplete="email"
        autofocus
      >
      {% if form.email.errors %}
        <ul class="auth-form__errors">
          {% for error in form.email.errors %}
            <li class="auth-form__error">{{ error }}</li>
          {% endfor %}
        </ul>
      {% endif %}
    </div>

    <button class="auth-btn auth-btn--primary" type="submit">Envoyer le lien</button>
  </form>

  <div class="auth-divider">ou</div>

  <p class="auth-link-row">
    <a href="{% url 'authentication:login' %}">Retour à la connexion</a>
  </p>
{% endblock %}
```

- [ ] **Étape 2 : Créer `authentication/templates/authentication/password_reset_done.html`**

```html
{% extends "authentication/auth_base.html" %}

{% block title %}Email envoyé — Easybiodiv{% endblock %}

{% block card %}
  <div class="auth-info">
    <div class="auth-info__icon" aria-hidden="true">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <path d="M3 8l9 6 9-6M3 8v10a1 1 0 001 1h16a1 1 0 001-1V8M3 8l1-1h16l1 1" stroke="#91452d" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <h1 class="auth-card__title">Email envoyé</h1>
    <p class="auth-info__text">
      Si un compte est associé à cette adresse, vous recevrez un email avec un lien
      valable <strong>24 heures</strong> pour réinitialiser votre mot de passe.
    </p>
    <p class="auth-link-row">
      <a href="{% url 'authentication:login' %}">Retour à la connexion</a>
    </p>
  </div>
{% endblock %}
```

- [ ] **Étape 3 : Créer `authentication/templates/authentication/password_reset_confirm.html`**

```html
{% extends "authentication/auth_base.html" %}

{% block title %}Nouveau mot de passe — Easybiodiv{% endblock %}

{% block card %}
  <h1 class="auth-card__title">Nouveau mot de passe</h1>
  <p class="auth-card__subtitle">Choisissez un mot de passe sécurisé.</p>

  {% if validlink %}
    <form method="post" novalidate>
      {% csrf_token %}

      <div class="auth-form__group">
        <label class="auth-form__label" for="{{ form.new_password1.id_for_label }}">
          Nouveau mot de passe
        </label>
        <input
          class="auth-form__input"
          type="password"
          id="{{ form.new_password1.id_for_label }}"
          name="{{ form.new_password1.html_name }}"
          autocomplete="new-password"
          autofocus
        >
        {% if form.new_password1.errors %}
          <ul class="auth-form__errors">
            {% for error in form.new_password1.errors %}
              <li class="auth-form__error">{{ error }}</li>
            {% endfor %}
          </ul>
        {% endif %}
      </div>

      <div class="auth-form__group">
        <label class="auth-form__label" for="{{ form.new_password2.id_for_label }}">
          Confirmer le mot de passe
        </label>
        <input
          class="auth-form__input"
          type="password"
          id="{{ form.new_password2.id_for_label }}"
          name="{{ form.new_password2.html_name }}"
          autocomplete="new-password"
        >
        {% if form.new_password2.errors %}
          <ul class="auth-form__errors">
            {% for error in form.new_password2.errors %}
              <li class="auth-form__error">{{ error }}</li>
            {% endfor %}
          </ul>
        {% endif %}
      </div>

      <button class="auth-btn auth-btn--primary" type="submit">Enregistrer</button>
    </form>
  {% else %}
    <div class="auth-form__global-errors" role="alert">
      <p class="auth-form__global-error">
        Ce lien est invalide ou a expiré.
        <a href="{% url 'authentication:password_reset' %}">Faire une nouvelle demande</a>.
      </p>
    </div>
  {% endif %}
{% endblock %}
```

- [ ] **Étape 4 : Créer `authentication/templates/authentication/password_reset_complete.html`**

```html
{% extends "authentication/auth_base.html" %}

{% block title %}Mot de passe réinitialisé — Easybiodiv{% endblock %}

{% block card %}
  <div class="auth-info">
    <div class="auth-info__icon" aria-hidden="true">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <path d="M20 6L9 17l-5-5" stroke="#91452d" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <h1 class="auth-card__title">Mot de passe modifié</h1>
    <p class="auth-info__text">
      Votre mot de passe a bien été réinitialisé. Vous pouvez maintenant vous connecter.
    </p>
    <a href="{% url 'authentication:login' %}" class="auth-btn auth-btn--primary" style="text-decoration:none;display:block;text-align:center;">
      Se connecter
    </a>
  </div>
{% endblock %}
```

- [ ] **Étape 5 : Créer `authentication/templates/authentication/password_reset_subject.txt`**

```
Réinitialisation de votre mot de passe Easybiodiv
```

*(Pas de saut de ligne en fin de fichier — Django exige un sujet sur une seule ligne.)*

- [ ] **Étape 6 : Créer `authentication/templates/authentication/password_reset_email.html`**

```html
Bonjour {{ user.get_username }},

Vous recevez cet email car vous (ou quelqu'un d'autre) avez demandé la réinitialisation
du mot de passe de votre compte Easybiodiv.

Cliquez sur le lien ci-dessous pour choisir un nouveau mot de passe :

{{ protocol }}://{{ domain }}{% url 'authentication:password_reset_confirm' uidb64=uid token=token %}

Ce lien est valable 24 heures. Si vous n'avez pas fait cette demande, ignorez cet email.

— L'équipe Easybiodiv
```

- [ ] **Étape 7 : Vérifier le flux dans le navigateur**

```
python manage.py runserver
```

- `http://127.0.0.1:8000/auth/password-reset/` → formulaire email
- Soumettre un email → Django affiche l'email dans la console (EMAIL_BACKEND console)
- Copier le lien de l'email → `http://127.0.0.1:8000/auth/password-reset/confirm/.../` → formulaire nouveau MDP
- Valider → `http://127.0.0.1:8000/auth/password-reset/complete/` → message succès

- [ ] **Étape 8 : Commit**

```
git add authentication/templates/authentication/
git commit -m "feat: add password reset templates and email template"
```

---

## Task 9 — Template logged_out + nettoyage

**Files:**
- Create: `authentication/templates/authentication/logged_out.html`
- Delete or empty: `authentication/tests.py` (remplacé par `authentication/tests/`)

- [ ] **Étape 1 : Créer `authentication/templates/authentication/logged_out.html`**

Ce template est un fallback — avec `LOGOUT_REDIRECT_URL` configuré, il n'est normalement pas affiché. Il sert si le redirect échoue.

```html
{% extends "authentication/auth_base.html" %}

{% block title %}Déconnecté — Easybiodiv{% endblock %}

{% block card %}
  <div class="auth-info">
    <h1 class="auth-card__title">Vous êtes déconnecté</h1>
    <p class="auth-info__text">
      À bientôt sur Easybiodiv.
    </p>
    <p class="auth-link-row">
      <a href="{% url 'dashboard:index' %}">Retour au dashboard</a>
      &nbsp;·&nbsp;
      <a href="{% url 'authentication:login' %}">Se reconnecter</a>
    </p>
  </div>
{% endblock %}
```

- [ ] **Étape 2 : Vider `authentication/tests.py`**

Le fichier `authentication/tests.py` est vide et peut coexister avec le répertoire `authentication/tests/`. Pour éviter toute confusion, vider son contenu :

```python
# Tests déplacés dans authentication/tests/
```

- [ ] **Étape 3 : Lancer la suite de tests complète**

```
python manage.py test authentication -v 2
```

Attendu : `OK` (18 tests).

- [ ] **Étape 4 : Vérification manuelle finale**

```
python manage.py runserver
```

Parcourir le flux complet :
1. `http://127.0.0.1:8000/` → dashboard visible sans connexion ✓
2. `http://127.0.0.1:8000/auth/register/` → s'inscrire → redirige vers dashboard ✓
3. `http://127.0.0.1:8000/auth/login/` → se connecter → redirige vers dashboard ✓
4. Logout via POST (voir note ci-dessous) → redirige vers dashboard ✓
5. `http://127.0.0.1:8000/auth/password-reset/` → flux reset complet ✓

> **Note logout :** En Django 5+, `LogoutView` n'accepte que les requêtes POST (protection CSRF).
> Tout lien de déconnexion dans les templates du dashboard doit donc être un `<form>` :
> ```html
> <form method="post" action="{% url 'authentication:logout' %}">
>   {% csrf_token %}
>   <button type="submit">Se déconnecter</button>
> </form>
> ```

- [ ] **Étape 5 : Commit final**

```
git add authentication/templates/authentication/logged_out.html authentication/tests.py
git commit -m "feat: complete authentication flow — login, register, logout, password reset"
```
