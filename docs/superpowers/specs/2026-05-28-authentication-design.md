# Authentication — Design Spec
*Date : 2026-05-28*

## Contexte

L'app `authentication` gère l'ensemble du cycle de vie d'un compte utilisateur dans Easybiodiv. Le dashboard est **public** (accessible sans compte) ; l'authentification permet de débloquer du contenu additionnel.

---

## Périmètre

| Flux | Inclus |
|---|---|
| Connexion | ✅ |
| Déconnexion | ✅ |
| Inscription | ✅ |
| Réinitialisation de mot de passe (email) | ✅ |
| SSO / MFA | ❌ hors périmètre MVP |
| Page profil / modification photo | ❌ hors périmètre MVP |

---

## Modèle — `authentication.User`

Deux changements sur le modèle existant, suivis d'une nouvelle migration :

| Champ | Changement |
|---|---|
| `role` | Ajouter `default=User.SUBSCRIBER` — tout nouvel inscrit est SUBSCRIBER automatiquement |
| `profile_photo` | Ajouter `blank=True, null=True` — photo optionnelle, uploadable plus tard |

Le champ `role` n'est modifiable que via le panneau admin Django (jamais exposé dans les formulaires publics).

---

## Formulaires — `authentication/forms.py`

### `RegisterForm`
- Hérite de `django.contrib.auth.forms.UserCreationForm`
- Champs exposés : `username`, `email`, `password1`, `password2`
- Surcharge `save()` pour forcer `role = SUBSCRIBER` avant création

---

## Vues & URLs

### `authentication/urls.py` (`app_name = "authentication"`)

| URL | Vue | Nom |
|---|---|---|
| `login/` | `LoginView` (built-in, template custom) | `login` |
| `logout/` | `LogoutView` (built-in) | `logout` |
| `register/` | FBV `register_view` (custom) | `register` |
| `password-reset/` | `PasswordResetView` (built-in) | `password_reset` |
| `password-reset/done/` | `PasswordResetDoneView` (built-in) | `password_reset_done` |
| `password-reset/confirm/<uidb64>/<token>/` | `PasswordResetConfirmView` (built-in) | `password_reset_confirm` |
| `password-reset/complete/` | `PasswordResetCompleteView` (built-in) | `password_reset_complete` |

### `easybiodiv/urls.py`
Ajout de `path('auth/', include('authentication.urls'))`.

### `register_view` (FBV)
- `GET` : affiche `RegisterForm` vide
- `POST` : valide le formulaire → crée l'utilisateur (role=SUBSCRIBER) → connecte → redirige vers `dashboard:index`
- En cas d'erreur : réaffiche le formulaire avec les erreurs

---

## Admin — `authentication/admin.py`

Enregistrement de `User` via un `UserAdmin` custom :
- Champ `role` visible et modifiable dans le détail d'un utilisateur
- `role` absent de tous les formulaires publics

---

## Settings

```python
LOGIN_REDIRECT_URL = 'dashboard:index'   # après connexion → dashboard
LOGOUT_REDIRECT_URL = 'dashboard:index'  # après déconnexion → dashboard
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # dev uniquement
```

Pas de `LOGIN_URL` ni de `@login_required` sur le dashboard — il reste public.

---

## Templates

Structure : `authentication/templates/authentication/<page>.html`

Toutes les pages auth partagent une **base auth autonome** (`auth_base.html`) sans sidebar ni header du dashboard, avec :
- Fond parchment `#fbf9f4` + grain CSS subtil
- Logo + nom + tagline centré au-dessus de la carte
- Carte blanche, bordure `#dac1ba`, ombre légère, `border-radius: 12px`, padding `36px 40px`
- Labels en petites majuscules (`text-transform: uppercase`, `letter-spacing: 0.05em`)
- Inputs fond `#f5f3ee`, border `#dac1ba` → focus : fond blanc + border terra cotta `#91452d`
- Bouton primaire : `background: #91452d`, blanc, `border-radius: 6px`
- Lien "Retour au dashboard" sous la carte

| Template | Contenu |
|---|---|
| `auth_base.html` | Layout partagé (fond, logo, carte wrappée dans un block) |
| `login.html` | Formulaire username + password, lien "mot de passe oublié", lien "créer un compte" |
| `register.html` | Formulaire username + email + password + confirmation, lien "déjà un compte" |
| `password_reset.html` | Formulaire email |
| `password_reset_done.html` | Confirmation d'envoi de l'email |
| `password_reset_confirm.html` | Formulaire nouveau mot de passe + confirmation |
| `password_reset_complete.html` | Message de succès + lien vers login |
| `logged_out.html` | Message de déconnexion + lien vers dashboard (fallback si LOGOUT_REDIRECT_URL n'est pas suivi) |

---

## Migration

Une migration `0002_user_optional_photo_and_default_role` :
- `profile_photo` : `blank=True, null=True`
- `role` : `default='SUBSCRIBER'`

---

## Décisions notables

- **Dashboard public** : aucune protection globale, `request.user.is_authenticated` utilisé dans les templates pour afficher le contenu additionnel.
- **Reset via email** : en dev, les emails s'affichent dans la console. En prod, configurer un vrai backend SMTP dans `settings/prod.py`.
- **Pillow** : requis pour `ImageField` — vérifier sa présence dans `requirements/base.txt`.
