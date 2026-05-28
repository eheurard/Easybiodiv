from django.test import TestCase
from authentication.models import User


class UserDefaultsTest(TestCase):
    def test_new_user_has_subscriber_role(self):
        user = User.objects.create_user(username='alice', password='Pass1234!')
        self.assertEqual(user.role, User.SUBSCRIBER)

    def test_profile_photo_is_optional(self):
        user = User.objects.create_user(username='bob', password='Pass1234!')
        fresh = User.objects.get(pk=user.pk)
        self.assertFalse(fresh.profile_photo)
