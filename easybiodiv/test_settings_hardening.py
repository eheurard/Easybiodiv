"""Garde-fou sur le bloc de durcissement production de `settings.py`.

Ce bloc ne s'exécute que hors DEBUG : les tests tournent avec DEBUG=True et ne
l'atteignent donc jamais. Résultat, la configuration de sécurité de production
n'était couverte par rien — et un réglage supprimé par une version de Django
(`STATICFILES_STORAGE`, retiré en 5.1) a pu rester en place, silencieusement
ignoré, sans que rien ne le signale.

Ces tests rechargent `settings.py` dans un module jetable avec un environnement
de production simulé, et vérifient ce qui en sort.
"""

import importlib.util
import os
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

SETTINGS_PATH = Path(__file__).resolve().parent / 'settings.py'

PROD_ENV = {
    'DEBUG': 'False',
    'SECRET_KEY': 'cle-de-test-non-secrete',
    'ALLOWED_HOSTS': 'easybiodiv.fr,www.easybiodiv.fr',
}

WHITENOISE_BACKEND = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
DJANGO_STATIC_BACKEND = 'django.contrib.staticfiles.storage.StaticFilesStorage'


def load_settings(**overrides):
    """Exécute `settings.py` dans un module isolé, avec l'environnement fourni.

    `load_dotenv` n'écrase jamais une variable déjà présente : les valeurs
    passées ici priment donc sur le `.env` local.
    """
    env = dict(PROD_ENV, **overrides)
    spec = importlib.util.spec_from_file_location(
        'easybiodiv._settings_probe', SETTINGS_PATH
    )
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, env):
        spec.loader.exec_module(module)
    return module


class ProductionHardeningTests(SimpleTestCase):
    """Hors DEBUG, les protections HTTPS/cookies/en-têtes doivent être actives."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.settings_module = load_settings()

    def test_debug_is_off(self):
        self.assertFalse(self.settings_module.DEBUG)

    def test_https_is_enforced(self):
        self.assertTrue(self.settings_module.SECURE_SSL_REDIRECT)
        self.assertEqual(
            self.settings_module.SECURE_PROXY_SSL_HEADER,
            ('HTTP_X_FORWARDED_PROTO', 'https'),
        )

    def test_cookies_are_secure(self):
        self.assertTrue(self.settings_module.SESSION_COOKIE_SECURE)
        self.assertTrue(self.settings_module.CSRF_COOKIE_SECURE)

    def test_hsts_is_configured_for_a_year(self):
        self.assertEqual(self.settings_module.SECURE_HSTS_SECONDS, 31536000)
        self.assertTrue(self.settings_module.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertTrue(self.settings_module.SECURE_HSTS_PRELOAD)

    def test_browser_headers_are_locked_down(self):
        self.assertTrue(self.settings_module.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(self.settings_module.X_FRAME_OPTIONS, 'DENY')

    def test_csrf_trusted_origins_derive_from_allowed_hosts(self):
        self.assertEqual(
            self.settings_module.CSRF_TRUSTED_ORIGINS,
            ['https://easybiodiv.fr', 'https://www.easybiodiv.fr'],
        )


class StaticStorageTests(SimpleTestCase):
    """`STORAGES` doit rester le point de configuration du stockage statique.

    Régression visée : `STATICFILES_STORAGE`, supprimé par Django 5.1, laissait
    WhiteNoise inactif en production sans aucun signal.
    """

    def test_production_uses_whitenoise_compressed_manifest(self):
        settings_module = load_settings()
        self.assertEqual(
            settings_module.STORAGES['staticfiles']['BACKEND'], WHITENOISE_BACKEND
        )

    def test_removed_django_setting_is_not_reintroduced(self):
        settings_module = load_settings()
        self.assertFalse(
            hasattr(settings_module, 'STATICFILES_STORAGE'),
            "STATICFILES_STORAGE est ignoré depuis Django 5.1 : utiliser STORAGES.",
        )

    def test_debug_leaves_storages_to_django_defaults(self):
        """En dev et pendant les tests, `settings.py` ne définit pas `STORAGES`.

        Django applique alors son backend par défaut, qui ne réclame aucun
        manifeste : ni `collectstatic` ni `staticfiles/` ne sont nécessaires
        pour lancer la suite de tests.
        """
        settings_module = load_settings(DEBUG='True')
        self.assertFalse(hasattr(settings_module, 'STORAGES'))
        from django.conf import global_settings
        self.assertEqual(
            global_settings.STORAGES['staticfiles']['BACKEND'], DJANGO_STATIC_BACKEND
        )


class SecretKeyTests(SimpleTestCase):

    def test_missing_secret_key_fails_fast_in_production(self):
        with self.assertRaises(RuntimeError):
            load_settings(SECRET_KEY='')

    def test_debug_falls_back_to_a_dev_key(self):
        settings_module = load_settings(DEBUG='True', SECRET_KEY='')
        self.assertTrue(settings_module.SECRET_KEY.startswith('django-insecure-'))
