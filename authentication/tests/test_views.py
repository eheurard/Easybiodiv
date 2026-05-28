from django.test import TestCase
from django.urls import reverse
from authentication.models import User


class RegisterViewTest(TestCase):
    valid_data = {
        'username': 'newuser',
        'email': 'new@example.com',
        'password1': 'TestPass123!',
        'password2': 'TestPass123!',
    }

    def test_get_returns_200(self):
        response = self.client.get(reverse('authentication:register'))
        self.assertEqual(response.status_code, 200)

    def test_get_uses_register_template(self):
        response = self.client.get(reverse('authentication:register'))
        self.assertTemplateUsed(response, 'authentication/register.html')

    def test_valid_post_redirects_to_dashboard(self):
        response = self.client.post(reverse('authentication:register'), self.valid_data)
        self.assertRedirects(response, reverse('dashboard:index'))

    def test_valid_post_creates_subscriber(self):
        self.client.post(reverse('authentication:register'), self.valid_data)
        user = User.objects.get(username='newuser')
        self.assertEqual(user.role, User.SUBSCRIBER)

    def test_valid_post_logs_user_in(self):
        self.client.post(reverse('authentication:register'), self.valid_data)
        response = self.client.get(reverse('dashboard:index'))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_invalid_post_returns_200_with_form(self):
        response = self.client.post(reverse('authentication:register'), {})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'authentication/register.html')
        self.assertIn('form', response.context)

    def test_authenticated_user_redirected(self):
        User.objects.create_user(username='existing', password='Pass1234!')
        self.client.login(username='existing', password='Pass1234!')
        response = self.client.get(reverse('authentication:register'))
        self.assertRedirects(response, reverse('dashboard:index'))


class LoginViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='TestPass123!')

    def test_get_returns_200(self):
        response = self.client.get(reverse('authentication:login'))
        self.assertEqual(response.status_code, 200)

    def test_get_uses_login_template(self):
        response = self.client.get(reverse('authentication:login'))
        self.assertTemplateUsed(response, 'authentication/login.html')

    def test_valid_login_redirects_to_dashboard(self):
        response = self.client.post(reverse('authentication:login'), {
            'username': 'testuser',
            'password': 'TestPass123!',
        })
        self.assertRedirects(response, reverse('dashboard:index'))


class LogoutViewTest(TestCase):
    def setUp(self):
        User.objects.create_user(username='testuser', password='TestPass123!')
        self.client.login(username='testuser', password='TestPass123!')

    def test_post_logout_redirects_to_dashboard(self):
        response = self.client.post(reverse('authentication:logout'))
        self.assertRedirects(response, reverse('dashboard:index'))
