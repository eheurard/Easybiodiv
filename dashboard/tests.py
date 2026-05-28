from django.test import TestCase
from django.urls import reverse


class DashboardIndexViewTests(TestCase):

    def test_index_returns_200(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)

    def test_index_uses_correct_template(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertTemplateUsed(response, 'dashboard/index.html')
