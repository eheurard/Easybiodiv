"""Construction de la configuration DATABASES depuis l'environnement.

Isolé de settings.py pour rester testable sans importer les settings
(qui exigent SECRET_KEY hors DEBUG). PostgreSQL si DB_NAME est défini,
sinon repli SQLite.
"""


def database_config(env, base_dir):
    """Retourne le dict de config de la connexion 'default'.

    `env` : mapping type os.environ. `base_dir` : Path racine projet.
    """
    if env.get('DB_NAME'):
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env['DB_NAME'],
            'USER': env['DB_USER'],
            'PASSWORD': env['DB_PASSWORD'],
            'HOST': env.get('DB_HOST', 'localhost'),
            'PORT': env.get('DB_PORT', '5432'),
        }
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': base_dir / 'db.sqlite3',
    }
