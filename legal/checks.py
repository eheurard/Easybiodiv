from django.conf import settings
from django.core.checks import Warning, register

from .info import missing_fields


@register()
def check_legal_info(app_configs, **kwargs):
    """Avertit, hors DEBUG, si les mentions légales sont incomplètes.

    `migrate` exécute les checks : l'avertissement apparaît donc dans le
    journal de déploiement cPanel (.cpanel.yml).
    """
    if settings.DEBUG:
        return []
    missing = missing_fields()
    if not missing:
        return []
    return [Warning(
        'Mentions légales incomplètes : settings.LEGAL ne renseigne pas %s.'
        % ', '.join(missing),
        hint=(
            'Compléter le dictionnaire LEGAL de easybiodiv/settings.py ; '
            "contact_email se lit dans CONTACT_EMAIL ou EMAIL_HOST_USER (environnement)."
        ),
        id='legal.W001',
    )]
