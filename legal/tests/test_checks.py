from django.test import SimpleTestCase, override_settings

from legal.checks import check_legal_info

from .test_views import LEGAL_COMPLETE


class CheckLegalInfoTest(SimpleTestCase):

    @override_settings(DEBUG=False, LEGAL={**LEGAL_COMPLETE, 'contact_email': ''})
    def test_warns_in_production_when_field_missing(self):
        warnings = check_legal_info(None)
        self.assertEqual([w.id for w in warnings], ['legal.W001'])
        self.assertIn('contact_email', warnings[0].msg)

    @override_settings(DEBUG=False, LEGAL={**LEGAL_COMPLETE, 'editor_professional': True,
                                           'editor_address': ''})
    def test_professional_publisher_needs_address(self):
        warnings = check_legal_info(None)
        self.assertIn('editor_address', warnings[0].msg)

    @override_settings(DEBUG=False, LEGAL={'editor_name': 'J. Martin', 'contact_email': 'a@b.fr'})
    def test_private_person_needs_only_name_and_email(self):
        self.assertEqual(check_legal_info(None), [])

    @override_settings(DEBUG=False, LEGAL=LEGAL_COMPLETE)
    def test_silent_when_complete(self):
        self.assertEqual(check_legal_info(None), [])

    @override_settings(DEBUG=True, LEGAL={})
    def test_silent_in_debug(self):
        self.assertEqual(check_legal_info(None), [])
