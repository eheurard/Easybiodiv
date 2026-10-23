from django.conf import settings
from django.core.checks import Warning, register

from easybiodiv.mail import CONSOLE_BACKEND


@register()
def check_email_backend(app_configs, **kwargs):
    """Avertit, hors DEBUG, si les emails partent dans la console.

    La réinitialisation de mot de passe semble alors réussir sans que rien ne
    soit envoyé. `migrate` exécute les checks : l'avertissement apparaît dans
    le journal de déploiement cPanel.
    """
    if settings.DEBUG or settings.EMAIL_BACKEND != CONSOLE_BACKEND:
        return []
    return [Warning(
        'Aucun serveur SMTP : les emails de réinitialisation de mot de passe '
        "ne sont pas envoyés.",
        hint='Définir EMAIL_HOST, EMAIL_HOST_USER et EMAIL_HOST_PASSWORD (easybiodiv/mail.py).',
        id='authentication.W001',
    )]
