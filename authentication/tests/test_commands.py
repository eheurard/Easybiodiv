import datetime
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from authentication.models import User


def _user(username, *, last_login=None, joined_days_ago=0, **extra):
    user = User.objects.create_user(username=username, password='x', **extra)
    User.objects.filter(pk=user.pk).update(
        last_login=last_login,
        date_joined=timezone.now() - datetime.timedelta(days=joined_days_ago),
    )
    return user


class PurgeInactiveAccountsTest(TestCase):
    long_ago = timezone.now() - datetime.timedelta(days=4 * 365)

    def run_command(self, *args):
        out = StringIO()
        call_command('purge_inactive_accounts', *args, stdout=out)
        return out.getvalue()

    def test_deletes_subscriber_inactive_for_three_years(self):
        _user('dormant', last_login=self.long_ago, joined_days_ago=5 * 365)
        self.run_command()
        self.assertFalse(User.objects.filter(username='dormant').exists())

    def test_never_logged_in_is_judged_on_sign_up_date(self):
        _user('ghost', joined_days_ago=4 * 365)
        _user('newcomer', joined_days_ago=10)
        self.run_command()
        self.assertFalse(User.objects.filter(username='ghost').exists())
        self.assertTrue(User.objects.filter(username='newcomer').exists())

    def test_keeps_recently_active_subscriber(self):
        _user('active', last_login=timezone.now(), joined_days_ago=5 * 365)
        self.run_command()
        self.assertTrue(User.objects.filter(username='active').exists())

    def test_keeps_creators_and_staff(self):
        _user('author', last_login=self.long_ago, role=User.CREATOR)
        _user('admin', last_login=self.long_ago, is_staff=True)
        self.run_command()
        self.assertEqual(User.objects.filter(username__in=['author', 'admin']).count(), 2)

    def test_dry_run_deletes_nothing(self):
        _user('dormant', last_login=self.long_ago)
        out = self.run_command('--dry-run')
        self.assertIn('dormant', out)
        self.assertTrue(User.objects.filter(username='dormant').exists())
