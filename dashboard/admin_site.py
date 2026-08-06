"""Site admin de la console de donnees Easybiodiv.

Restreint l'acces aux superusers et regroupe l'index par domaine metier.
"""
from django.contrib import admin


class EasybiodivAdminSite(admin.AdminSite):
    site_header = 'Easybiodiv — Console de données'
    site_title = 'Console de données'
    index_title = 'Données de référence et données entreprises'

    def has_permission(self, request):
        """Console reservee aux superusers.

        Django autorise par defaut tout compte `is_staff`. Le role applicatif
        CREATOR, qui suffit pour /imports/, ne donne pas acces ici.
        """
        return request.user.is_active and request.user.is_superuser
