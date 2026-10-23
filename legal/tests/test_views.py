from django.test import TestCase, override_settings
from django.urls import reverse

LEGAL_COMPLETE = {
    'editor_name': 'Jeanne Martin',
    'editor_address': '1 rue de la Paix, 75002 Paris',
    'editor_phone': '01 23 45 67 89',
    'contact_email': 'contact@example.com',
    'publication_director': 'Jeanne Martin',
    'host_name': 'O2SWITCH',
    'host_address': 'Chemin des Pardiaux, 63000 Clermont-Ferrand, France',
}

PAGES = ('legal:notice', 'legal:privacy', 'legal:cookies', 'legal:terms')


@override_settings(LEGAL=LEGAL_COMPLETE)
class LegalPagesTest(TestCase):

    def test_pages_are_public(self):
        for name in PAGES:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_notice_shows_editor_and_host(self):
        response = self.client.get(reverse('legal:notice'))
        self.assertContains(response, 'Jeanne Martin')
        self.assertContains(response, 'O2SWITCH')
        self.assertContains(response, 'Chemin des Pardiaux')
        self.assertNotContains(response, '[à compléter]')

    def test_optional_fields_are_hidden_when_empty(self):
        response = self.client.get(reverse('legal:notice'))
        self.assertNotContains(response, 'SIREN')

    def test_english_version_is_served_in_english(self):
        self.client.cookies['django_language'] = 'en'
        response = self.client.get(reverse('legal:privacy'))
        self.assertTemplateUsed(response, 'legal/en/confidentialite.html')
        self.assertContains(response, 'Data controller')

    def test_footer_links_every_legal_page(self):
        response = self.client.get(reverse('dashboard:index'))
        for name in PAGES:
            with self.subTest(name=name):
                self.assertContains(response, f'href="{reverse(name)}"')

    def test_auth_pages_have_footer(self):
        response = self.client.get(reverse('authentication:login'))
        self.assertContains(response, f'href="{reverse("legal:notice")}"')

    def test_no_google_fonts(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertNotContains(response, 'fonts.googleapis.com')


LEGAL_PRIVATE_PERSON = {
    'editor_professional': False,
    'editor_name': 'Jeanne Martin',
    'contact_email': 'contact@example.com',
    'host_name': 'O2SWITCH',
    'host_phone': '+33 4 44 44 60 40',
}


@override_settings(LEGAL=LEGAL_PRIVATE_PERSON)
class PrivatePersonPublisherTest(TestCase):

    def test_name_and_email_are_enough(self):
        response = self.client.get(reverse('legal:notice'))
        self.assertContains(response, 'Jeanne Martin')
        self.assertContains(response, 'à titre non professionnel')
        self.assertNotContains(response, '[à compléter]')
        self.assertNotContains(response, 'Téléphone : <')

    def test_missing_contact_email_shows_placeholder(self):
        with self.settings(LEGAL={**LEGAL_PRIVATE_PERSON, 'contact_email': ''}):
            response = self.client.get(reverse('legal:privacy'))
        self.assertContains(response, '[à compléter]')


@override_settings(LEGAL={**LEGAL_COMPLETE, 'editor_professional': True, 'editor_phone': ''})
class ProfessionalPublisherTest(TestCase):

    def test_missing_phone_shows_placeholder(self):
        response = self.client.get(reverse('legal:notice'))
        self.assertContains(response, '[à compléter]')
        self.assertNotContains(response, 'à titre non professionnel')
