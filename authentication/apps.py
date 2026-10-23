from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    name = 'authentication'

    def ready(self):
        from . import checks  # noqa: F401 — enregistre les system checks
