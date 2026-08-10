from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class DashboardConfig(AppConfig):
    name = 'dashboard'


class EasybiodivAdminConfig(AdminConfig):
    """Remplace le site admin par defaut par celui de la console.

    ATTENTION : malgre son emplacement dans dashboard/apps.py, cette config
    configure l'app `django.contrib.admin` et non `dashboard` — elle herite
    `name = 'django.contrib.admin'` de SimpleAdminConfig. C'est la voie
    documentee par Django pour substituer un AdminSite : elle est independante
    de l'ordre des imports, contrairement a une reassignation de `admin.site`,
    qui ferait disparaitre silencieusement les modeles enregistres trop tot.

    Les deux configs de ce module sont referencees par chemin complet dans
    INSTALLED_APPS (`dashboard.apps.DashboardConfig` et
    `dashboard.apps.EasybiodivAdminConfig`). Django ne scanne donc jamais ce
    fichier a la recherche d'une config par defaut, et la question du candidat
    unique — qui imposait `default = False` ici et un import du module plutot
    que de la classe AdminConfig — ne se pose plus.
    """

    default_site = 'dashboard.admin_site.EasybiodivAdminSite'
