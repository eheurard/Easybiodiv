from django.test import TestCase
from authentication.forms import RegisterForm
from authentication.models import User


class RegisterFormTest(TestCase):
    valid_data = {
        'username': 'newuser',
        'email': 'new@example.com',
        'password1': 'TestPass123!',
        'password2': 'TestPass123!',
    }

    def test_valid_form(self):
        form = RegisterForm(self.valid_data)
        self.assertTrue(form.is_valid())

    def test_email_is_required(self):
        data = {**self.valid_data, 'email': ''}
        form = RegisterForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_passwords_must_match(self):
        data = {**self.valid_data, 'password2': 'Different!'}
        form = RegisterForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)

    def test_save_assigns_subscriber_role(self):
        form = RegisterForm(self.valid_data)
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertEqual(user.role, User.SUBSCRIBER)

    def test_save_stores_email(self):
        form = RegisterForm(self.valid_data)
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertEqual(user.email, 'new@example.com')
