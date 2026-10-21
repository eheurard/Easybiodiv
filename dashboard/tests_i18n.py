"""Interface bilingue FR / EN : bascule par drapeau, rendu serveur, catalogue JS.

Le français est la langue source (msgid) et la langue par défaut ; seul un
catalogue anglais existe (locale/en/). Ces tests vérifient aussi que les .mo
compilés et commités sont bien chargés.
"""
import json

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from dashboard.models import DisclosureRequirement, FlowKind
from dashboard.services.hazards import PHYSICAL_RISKS


class LanguageSwitchTests(TestCase):
    def switch_to(self, language, next_url='/'):
        return self.client.post(
            reverse('set_language'), {'language': language, 'next': next_url},
        )

    def test_francais_par_defaut(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertContains(response, '<html lang="fr">')
        self.assertContains(response, "Vue d'ensemble")
        # Le drapeau propose la langue cible : l'anglais.
        self.assertContains(response, 'aria-label="Switch to English"')
        self.assertContains(response, 'name="language" value="en"')

    def test_bascule_en_anglais_puis_retour(self):
        response = self.switch_to('en', reverse('dashboard:compare'))
        self.assertRedirects(response, reverse('dashboard:compare'),
                             fetch_redirect_response=False)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'en')

        response = self.client.get(reverse('dashboard:index'))
        self.assertContains(response, '<html lang="en">')
        self.assertContains(response, 'Overview')
        self.assertContains(response, 'aria-label="Passer en français"')
        self.assertNotContains(response, "Vue d'ensemble")

        self.switch_to('fr')
        response = self.client.get(reverse('dashboard:index'))
        self.assertContains(response, '<html lang="fr">')

    def test_langue_non_proposee_ignoree(self):
        self.switch_to('de')
        response = self.client.get(reverse('dashboard:index'))
        self.assertContains(response, '<html lang="fr">')

    def test_en_tete_accept_language_respecte_sans_choix_explicite(self):
        response = self.client.get(reverse('dashboard:index'), HTTP_ACCEPT_LANGUAGE='en-US,en')
        self.assertContains(response, '<html lang="en">')

    def test_pages_d_authentification_bilingues(self):
        self.switch_to('en')
        response = self.client.get(reverse('authentication:login'))
        self.assertContains(response, 'Forgot your password?')
        self.assertContains(response, 'lang-switch')


class ServerSideTranslationTests(TestCase):
    def test_libelles_python_paresseux(self):
        hazard = next(r for r in PHYSICAL_RISKS if r['key'] == 'drought')
        with translation.override('en'):
            self.assertEqual(str(hazard['name']), 'Drought')
            self.assertEqual(str(FlowKind.WASTE.label), 'Waste')
            self.assertEqual(str(DisclosureRequirement.Status.COMPLIANT.label), 'Compliant')
        with translation.override('fr'):
            self.assertEqual(str(hazard['name']), 'Sécheresse')

    def test_json_script_en_anglais(self):
        self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        response = self.client.get(reverse('dashboard:compare'))
        self.assertContains(response, 'Number of assets')
        self.assertNotContains(response, 'Nombre d')

    def test_pourcentages_echappes_dans_les_gabarits(self):
        # {% translate %} double les % dans le msgid : la traduction doit les rétablir.
        self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        response = self.client.get(reverse('dashboard:climate_stress_test'))
        self.assertContains(response, 'EBITDA margin (%)')
        self.assertNotContains(response, '%%')


class JavaScriptCatalogTests(TestCase):
    def test_catalogue_js_anglais(self):
        self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        response = self.client.get(reverse('javascript-catalog'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(json.dumps('Erreur de chargement')[1:-1], body)
        self.assertIn('Loading error', body)

    def test_catalogue_js_francais_vide(self):
        # Les msgid sont en français : aucune traduction à servir.
        response = self.client.get(reverse('javascript-catalog'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Loading error', response.content.decode())
