"""Tests de la console de donnees superuser (/admin durci et habille)."""
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from dashboard.admin_site import GROUPS, UNGROUPED_TITLE
from dashboard.models import Currency, ESG_data

User = get_user_model()


class AdminAccessTests(TestCase):
    """Seul un superuser accede a la console."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='root', email='root@example.com', password='pwd-root-123',
        )
        # is_staff sans is_superuser : le cas que le durcissement doit fermer.
        cls.staff = User.objects.create_user(
            username='staff', password='pwd-staff-123', is_staff=True,
        )
        cls.creator = User.objects.create_user(
            username='creator', password='pwd-creator-123', role=User.CREATOR,
        )
        cls.subscriber = User.objects.create_user(
            username='abonne', password='pwd-abonne-123', role=User.SUBSCRIBER,
        )

    def test_superuser_accede_a_la_console(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)

    def test_staff_non_superuser_est_refuse(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)

    def test_creator_non_superuser_est_refuse(self):
        """Le role applicatif CREATOR suffit pour /imports/, pas pour la console."""
        self.client.force_login(self.creator)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)

    def test_subscriber_est_refuse(self):
        self.client.force_login(self.subscriber)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)

    def test_branding_de_la_console(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'Console de données')


class AdminCoverageTests(TestCase):
    """Les tables editables le restent."""

    def test_currency_est_enregistre(self):
        self.assertIn(Currency, django_admin.site._registry)

    def test_esg_data_est_enregistre(self):
        self.assertIn(ESG_data, django_admin.site._registry)


class AdminGroupingTests(TestCase):
    """L'index est regroupe par domaine, sans table orpheline."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='root2', email='root2@example.com', password='pwd-root-123',
        )

    def _app_list(self):
        request = RequestFactory().get('/admin/')
        request.user = self.superuser
        return django_admin.site.get_app_list(request)

    def test_titres_de_groupes_uniques(self):
        titres = [titre for titre, _ in GROUPS]
        self.assertEqual(len(titres), len(set(titres)))

    def test_aucun_modele_dans_deux_groupes(self):
        modeles = [m for _, liste in GROUPS for m in liste]
        self.assertEqual(len(modeles), len(set(modeles)))

    def test_tous_les_modeles_enregistres_sont_classes(self):
        """Garde-fou : un modele ajoute plus tard ne doit pas disparaitre."""
        classes = {m for _, liste in GROUPS for m in liste}
        manquants = sorted(
            m._meta.label for m in django_admin.site._registry if m not in classes
        )
        self.assertEqual(manquants, [])

    def test_groupe_non_classe_absent_de_l_index(self):
        titres = [app['name'] for app in self._app_list()]
        self.assertNotIn(UNGROUPED_TITLE, titres)

    def test_index_expose_les_groupes_dans_l_ordre(self):
        attendus = [titre for titre, _ in GROUPS]
        self.assertEqual([app['name'] for app in self._app_list()], attendus)

    def test_vue_par_app_toujours_accessible(self):
        """La surcharge ne doit pas casser /admin/dashboard/."""
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:app_list', args=['dashboard']))
        self.assertEqual(response.status_code, 200)

    def test_changelist_toujours_accessible(self):
        """Toute page admin rend la nav laterale via app_list.html : une
        changelist verifie donc aussi l'override de ce template."""
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:dashboard_country_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Référentiels géographiques')

    def test_index_rend_les_titres_de_groupes(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'Référentiels géographiques')
        self.assertContains(response, 'Chaîne d&#x27;approvisionnement')


class AdminTooltipTests(TestCase):
    """Les help_text sont rendus en bulle, pas en texte statique."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='root3', email='root3@example.com', password='pwd-root-123',
        )

    def setUp(self):
        self.client.force_login(self.superuser)
        url = reverse('admin:authentication_user_change', args=[self.superuser.pk])
        self.response = self.client.get(url)

    def test_le_formulaire_repond(self):
        self.assertEqual(self.response.status_code, 200)

    def test_la_bulle_est_rendue(self):
        self.assertContains(self.response, 'eb-help')

    def test_l_icone_est_decorative(self):
        """Ni focusable ni annoncee : l'explication passe par l'aria-describedby
        que Django pose deja sur le champ. Assertion sur le markup exact, donc
        aucun tabindex ni role ne peut s'y glisser."""
        self.assertContains(
            self.response,
            '<span class="eb-help__icon" aria-hidden="true">?</span>',
        )

    def test_l_ancre_aria_describedby_est_conservee(self):
        """Django pointe aria-describedby vers cet id : il doit survivre."""
        self.assertContains(self.response, '_helptext')

    def test_le_css_de_la_console_est_charge(self):
        self.assertContains(self.response, 'admin-easybiodiv.css')


class AdminThemeTests(TestCase):
    """Console aux couleurs Easybiodiv, en francais, mono-theme."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='root4', email='root4@example.com', password='pwd-root-123',
        )

    def setUp(self):
        self.client.force_login(self.superuser)
        self.response = self.client.get(reverse('admin:index'))

    def test_le_chrome_est_en_francais(self):
        self.assertContains(self.response, 'Déconnexion')

    def test_la_langue_du_document_est_le_francais(self):
        self.assertContains(self.response, 'lang="fr-fr"')

    def test_le_mode_sombre_de_django_n_est_pas_charge(self):
        self.assertNotContains(self.response, 'dark_mode.css')

    def test_le_script_de_theme_n_est_pas_charge(self):
        self.assertNotContains(self.response, 'theme.js')

    def test_le_selecteur_de_theme_est_retire(self):
        self.assertNotContains(self.response, 'theme-toggle')
