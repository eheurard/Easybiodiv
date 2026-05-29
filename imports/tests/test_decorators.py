from django.test import TestCase, RequestFactory
from django.http import HttpResponse, HttpResponseForbidden
from authentication.models import User
from imports.decorators import creator_required


def _dummy_view(request):
    return HttpResponse('ok')


class CreatorRequiredTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.creator = User.objects.create_user('creator', password='pass', role='CREATOR')
        self.subscriber = User.objects.create_user('sub', password='pass', role='SUBSCRIBER')

    def test_anonymous_redirects_to_login(self):
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.get('/imports/')
        request.user = AnonymousUser()
        wrapped = creator_required(_dummy_view)
        response = wrapped(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response['Location'])

    def test_subscriber_gets_403(self):
        request = self.factory.get('/imports/')
        request.user = self.subscriber
        wrapped = creator_required(_dummy_view)
        response = wrapped(request)
        self.assertEqual(response.status_code, 403)

    def test_creator_passes_through(self):
        request = self.factory.get('/imports/')
        request.user = self.creator
        wrapped = creator_required(_dummy_view)
        response = wrapped(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'ok')
