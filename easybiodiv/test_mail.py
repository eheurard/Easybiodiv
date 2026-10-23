from django.test import SimpleTestCase

from easybiodiv.mail import CONSOLE_BACKEND, SMTP_BACKEND, email_config

O2SWITCH = {
    'EMAIL_HOST': 'serveur.o2switch.net',
    'EMAIL_HOST_USER': 'contact@exemple.fr',
    'EMAIL_HOST_PASSWORD': 'secret',
}


class EmailConfigTests(SimpleTestCase):
    def test_console_without_host(self):
        self.assertEqual(email_config({}), {'EMAIL_BACKEND': CONSOLE_BACKEND})

    def test_smtp_ssl_on_465_by_default(self):
        cfg = email_config(O2SWITCH)
        self.assertEqual(cfg['EMAIL_BACKEND'], SMTP_BACKEND)
        self.assertEqual(cfg['EMAIL_PORT'], 465)
        self.assertTrue(cfg['EMAIL_USE_SSL'])
        self.assertFalse(cfg['EMAIL_USE_TLS'])
        self.assertEqual(cfg['EMAIL_HOST_PASSWORD'], 'secret')

    def test_starttls_on_587(self):
        cfg = email_config({**O2SWITCH, 'EMAIL_PORT': '587'})
        self.assertTrue(cfg['EMAIL_USE_TLS'])
        self.assertFalse(cfg['EMAIL_USE_SSL'])

    def test_sender_defaults_to_authenticated_mailbox(self):
        cfg = email_config(O2SWITCH)
        self.assertEqual(cfg['DEFAULT_FROM_EMAIL'], 'Easybiodiv <contact@exemple.fr>')

    def test_explicit_sender_wins(self):
        cfg = email_config({**O2SWITCH, 'DEFAULT_FROM_EMAIL': 'no-reply@exemple.fr'})
        self.assertEqual(cfg['DEFAULT_FROM_EMAIL'], 'no-reply@exemple.fr')
