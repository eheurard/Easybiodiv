from django.urls import path
from django.utils.translation import gettext_lazy as _

from .views import LegalPageView

app_name = 'legal'

urlpatterns = [
    path('mentions-legales/', LegalPageView.as_view(
        page='mentions', title=_('Mentions légales'),
    ), name='notice'),
    path('confidentialite/', LegalPageView.as_view(
        page='confidentialite', title=_('Politique de confidentialité'),
    ), name='privacy'),
    path('cookies/', LegalPageView.as_view(
        page='cookies', title=_('Cookies et stockage local'),
    ), name='cookies'),
    path('cgu/', LegalPageView.as_view(
        page='cgu', title=_("Conditions générales d'utilisation"),
    ), name='terms'),
]
