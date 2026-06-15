import os
import sys

BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

# Passenger/cPanel ne charge pas .env automatiquement : on lit le fichier ici,
# avant l'initialisation de Django, pour peupler os.environ (SECRET_KEY, DEBUG,
# ALLOWED_HOSTS, SMTP…). Les variables déjà définies dans l'environnement
# (ex. configurées dans l'interface cPanel) ont la priorité (setdefault).
_env_path = os.path.join(BASE_DIR, '.env')
if os.path.exists(_env_path):
    with open(_env_path, encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith('#') or '=' not in _line:
                continue
            _key, _, _val = _line.partition('=')
            os.environ.setdefault(_key.strip(), _val.strip())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'easybiodiv.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
