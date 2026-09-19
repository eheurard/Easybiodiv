"""Site admin de la console de donnees Easybiodiv.

Restreint l'acces aux superusers et regroupe l'index par domaine metier.
"""
from django.contrib import admin
from django.contrib.auth.models import Group
from django.utils.text import slugify

from authentication.models import User
from dashboard import models as m

UNGROUPED_TITLE = 'Non classé'

# Ordre d'affichage de l'index. L'ordre des modeles dans chaque groupe est
# volontairement celui de la liste, pas alphabetique : les tables parentes
# precedent leurs enfants.
GROUPS = [
    ('Référentiels géographiques', [m.Country, m.SubnationalRegion]),
    ('Référentiels sectoriels & produits', [
        m.Sector, m.SubSector, m.Commodity, m.Currency, m.SectorCreditProfile,
    ]),
    ('Entreprises & actifs', [
        m.Company, m.Asset, m.Ownership, m.Company_Revenue,
        m.Company_Revenue_Sector, m.ESG_data,
    ]),
    ('Flux', [m.Flow]),
    ('Impacts & inventaire (ACV)', [
        m.ImpactMethod, m.ImpactCategory, m.CharacterizationFactor,
    ]),
    ('Politiques & vulnérabilité', [
        m.Policy_Type, m.Policy_Subcategory, m.Policy_Level, m.Company_Policy,
    ]),
    ('Conformité CSRD / ESRS E4', [m.E4Assessment]),
    ('Scénarios climatiques', [m.ClimateScenario, m.ScenarioVariable]),
    ('Comptes', [User, Group]),
]


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

    def get_app_list(self, request, app_label=None):
        """Regroupe l'index par domaine metier.

        Ne regroupe que l'index et la nav laterale (`app_label is None`). La
        vue par-app /admin/dashboard/ passe un `app_label` et doit garder le
        comportement natif.
        """
        if app_label is not None:
            return super().get_app_list(request, app_label)

        entries = {}
        for app in self._build_app_dict(request).values():
            for entry in app['models']:
                entries[entry['model']] = entry

        app_list = []
        for titre, modeles in GROUPS:
            groupe = [entries.pop(model) for model in modeles if model in entries]
            if groupe:
                app_list.append(self._pseudo_app(titre, groupe))

        if entries:
            app_list.append(
                self._pseudo_app(UNGROUPED_TITLE, list(entries.values()))
            )
        return app_list

    @staticmethod
    def _pseudo_app(titre, modeles):
        """Groupe presente comme une app au template admin/app_list.html.

        `app_url` vide : un groupe transverse n'a pas d'URL d'app unique, et
        l'override du template rend alors le titre en texte simple.
        """
        return {
            'name': titre,
            'app_label': slugify(titre),
            'app_url': '',
            'has_module_perms': True,
            'models': modeles,
        }
