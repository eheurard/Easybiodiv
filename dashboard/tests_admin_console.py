"""Tests de la console de donnees superuser (/admin durci et habille)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
