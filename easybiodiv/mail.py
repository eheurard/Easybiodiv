"""Aiguillage console ↔ SMTP pour l'envoi d'emails (réinitialisation de mot de passe).

Même principe que db.py : la configuration se lit dans l'environnement, et
l'absence de EMAIL_HOST retombe sur un réglage sûr pour le développement (la
console, qui affiche les emails au lieu de les envoyer).
"""

CONSOLE_BACKEND = 'django.core.mail.backends.console.EmailBackend'
SMTP_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'


def email_config(environ):
    """Réglages EMAIL_* de Django, déduits des variables d'environnement."""
    host = environ.get('EMAIL_HOST', '').strip()
    if not host:
        return {'EMAIL_BACKEND': CONSOLE_BACKEND}

    port = int(environ.get('EMAIL_PORT') or 465)
    user = environ.get('EMAIL_HOST_USER', '').strip()
    # L'expéditeur doit être la boîte authentifiée : un serveur mutualisé
    # (o2switch) refuse ou classe en spam un From qui ne lui appartient pas.
    default_from = f'Easybiodiv <{user}>' if user else 'webmaster@localhost'
    from_email = environ.get('DEFAULT_FROM_EMAIL', '').strip() or default_from
    return {
        'EMAIL_BACKEND': SMTP_BACKEND,
        'EMAIL_HOST': host,
        'EMAIL_PORT': port,
        'EMAIL_HOST_USER': user,
        'EMAIL_HOST_PASSWORD': environ.get('EMAIL_HOST_PASSWORD', ''),
        # 465 : SSL dès la connexion ; 587 : STARTTLS. Django refuse les deux à la fois.
        'EMAIL_USE_SSL': port == 465,
        'EMAIL_USE_TLS': port == 587,
        # Sans délai, un serveur SMTP muet bloquerait le processus Passenger.
        'EMAIL_TIMEOUT': 10,
        'DEFAULT_FROM_EMAIL': from_email,
        'SERVER_EMAIL': from_email,
    }
