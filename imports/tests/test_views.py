import io
import json
import os
import openpyxl
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from authentication.models import User

import tempfile


def _make_minimal_xlsx():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet('Country')
    ws.append(['name', 'water_ownership', 'land_ownership', 'water_Governance', 'land_Governance'])
    ws.append(['TestLand', 'pub', 'priv', '', ''])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ViewsAccessTest(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user('creator', password='pass', role='CREATOR')
        self.subscriber = User.objects.create_user('sub', password='pass', role='SUBSCRIBER')

    def test_index_anonymous_redirects(self):
        resp = self.client.get(reverse('imports:index'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login/', resp['Location'])

    def test_index_subscriber_403(self):
        self.client.login(username='sub', password='pass')
        resp = self.client.get(reverse('imports:index'))
        self.assertEqual(resp.status_code, 403)

    def test_index_creator_200(self):
        self.client.login(username='creator', password='pass')
        resp = self.client.get(reverse('imports:index'))
        self.assertEqual(resp.status_code, 200)

    def test_download_template_returns_xlsx(self):
        self.client.login(username='creator', password='pass')
        resp = self.client.get(reverse('imports:download_template'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])

    def test_upload_bad_extension_shows_error(self):
        self.client.login(username='creator', password='pass')
        f = SimpleUploadedFile('test.csv', b'name\nFrance\n', content_type='text/csv')
        resp = self.client.post(reverse('imports:upload'), {'excel_file': f})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Format invalide')

    def test_upload_valid_file_redirects_to_preview(self):
        self.client.login(username='creator', password='pass')
        xlsx_bytes = _make_minimal_xlsx()
        f = SimpleUploadedFile('data.xlsx', xlsx_bytes,
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post(reverse('imports:upload'), {'excel_file': f})
        self.assertRedirects(resp, reverse('imports:preview'), fetch_redirect_response=False)
        self.assertIn('import_key', self.client.session)

    def test_preview_renders_data_rows(self):
        self.client.login(username='creator', password='pass')
        xlsx_bytes = _make_minimal_xlsx()
        f = SimpleUploadedFile('data.xlsx', xlsx_bytes,
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.client.post(reverse('imports:upload'), {'excel_file': f})
        resp = self.client.get(reverse('imports:preview'))
        self.assertEqual(resp.status_code, 200)
        # The actual data row must be rendered, not the empty-tab notice.
        self.assertContains(resp, 'TestLand')
        self.assertContains(resp, 'badge--ok')
        self.assertNotContains(resp, 'Aucune ligne dans cet onglet')

    def test_preview_without_session_redirects(self):
        self.client.login(username='creator', password='pass')
        resp = self.client.get(reverse('imports:preview'))
        self.assertRedirects(resp, reverse('imports:index'), fetch_redirect_response=False)

    def test_full_workflow_upload_preview_confirm(self):
        self.client.login(username='creator', password='pass')
        xlsx_bytes = _make_minimal_xlsx()
        f = SimpleUploadedFile('data.xlsx', xlsx_bytes,
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.client.post(reverse('imports:upload'), {'excel_file': f})
        resp = self.client.get(reverse('imports:preview'))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post(reverse('imports:confirm'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'importé')
        from dashboard.models import Country
        self.assertTrue(Country.objects.filter(name='TestLand').exists())
