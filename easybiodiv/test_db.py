from pathlib import Path

from django.test import SimpleTestCase

from easybiodiv.db import database_config


class DatabaseConfigTests(SimpleTestCase):
    def test_postgres_when_db_name_set(self):
        env = {'DB_NAME': 'mydb', 'DB_USER': 'u', 'DB_PASSWORD': 'p'}
        cfg = database_config(env, Path('/base'))
        self.assertEqual(cfg['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(cfg['NAME'], 'mydb')
        self.assertEqual(cfg['USER'], 'u')
        self.assertEqual(cfg['PASSWORD'], 'p')
        self.assertEqual(cfg['HOST'], 'localhost')  # défaut
        self.assertEqual(cfg['PORT'], '5432')       # défaut

    def test_postgres_respects_explicit_host_port(self):
        env = {'DB_NAME': 'd', 'DB_USER': 'u', 'DB_PASSWORD': 'p',
               'DB_HOST': 'db.example', 'DB_PORT': '6543'}
        cfg = database_config(env, Path('/base'))
        self.assertEqual(cfg['HOST'], 'db.example')
        self.assertEqual(cfg['PORT'], '6543')

    def test_sqlite_fallback_when_no_db_name(self):
        cfg = database_config({}, Path('/base'))
        self.assertEqual(cfg['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(cfg['NAME'], Path('/base') / 'db.sqlite3')
