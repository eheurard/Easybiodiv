from django.apps import AppConfig
# Import du module (pas de la classe) : `from ... import AdminConfig` lierait
# `AdminConfig` comme nom de classe dans l'espace de noms de ce module. Django
# scanne dashboard/apps.py pour resoudre l'entree `'dashboard'` (nom nu, plus
# bas dans INSTALLED_APPS) et exige un candidat AppConfig par defaut unique.
# Avec la classe importee directement, il en trouve deux (`AdminConfig` et
# `EasybiodivAdminConfig`, qui herite `default = True`) et leve RuntimeError.
from django.contrib.admin import apps as admin_apps


class DashboardConfig(AppConfig):
    name = 'dashboard'


class EasybiodivAdminConfig(admin_apps.AdminConfig):
    """Remplace le site admin par defaut par celui de la console.

    ATTENTION : malgre son emplacement dans dashboard/apps.py, cette config
    configure l'app `django.contrib.admin` et non `dashboard` — elle herite
    `name = 'django.contrib.admin'` de SimpleAdminConfig. C'est la voie
    documentee par Django pour substituer un AdminSite : elle est independante
    de l'ordre des imports, contrairement a une reassignation de `admin.site`,
    qui ferait disparaitre silencieusement les modeles enregistres trop tot.

    `default = False` exclut ce candidat de la resolution automatique de
    l'entree nue `'dashboard'` dans INSTALLED_APPS (qui doit rester
    `DashboardConfig`). Cette config est utilisee via son chemin complet
    `dashboard.apps.EasybiodivAdminConfig` dans INSTALLED_APPS, ce qui
    contourne entierement cette detection automatique.
    """

    default = False
    default_site = 'dashboard.admin_site.EasybiodivAdminSite'
