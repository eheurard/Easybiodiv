from django.test import SimpleTestCase, override_settings

from authentication.checks import check_email_backend
from easybiodiv.mail import CONSOLE_BACKEND, SMTP_BACKEND


class CheckEmailBackendTest(SimpleTestCase):

    @override_settings(DEBUG=False, EMAIL_BACKEND=CONSOLE_BACKEND)
    def test_warns_in_production_without_smtp(self):
        self.assertEqual([w.id for w in check_email_backend(None)], ['authentication.W001'])

    @override_settings(DEBUG=False, EMAIL_BACKEND=SMTP_BACKEND)
    def test_silent_with_smtp(self):
        self.assertEqual(check_email_backend(None), [])

    @override_settings(DEBUG=True, EMAIL_BACKEND=CONSOLE_BACKEND)
    def test_silent_in_debug(self):
        self.assertEqual(check_email_backend(None), [])
