"""Tests de la carte interactive des flux."""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Asset, AssetGroup, AssetGroupMember, Company, Country


class AssetGroupModelTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private')
        self.a1, self.a2, self.a3 = (
            Asset.objects.create(name=f'Site {i}', latitude=1.0, longitude=2.0, country=country)
            for i in range(3)
        )

    def test_set_members_replaces_members(self):
        group = AssetGroup.objects.create(name='Usines Europe', company=self.acme)
        group.set_members([self.a1.pk, self.a2.pk])
        group.set_members([self.a2.pk, self.a3.pk])
        self.assertEqual(
            sorted(group.members.values_list('asset_id', flat=True)),
            [self.a2.pk, self.a3.pk])

    def test_member_copies_group_company(self):
        group = AssetGroup.objects.create(name='G', company=self.acme)
        group.set_members([self.a1.pk])
        self.assertEqual(group.members.get().company_id, self.acme.pk)

    def test_asset_cannot_be_in_two_groups_of_same_company(self):
        g1 = AssetGroup.objects.create(name='G1', company=self.acme)
        g2 = AssetGroup.objects.create(name='G2', company=self.acme)
        g1.set_members([self.a1.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            g2.set_members([self.a1.pk])

    def test_asset_can_be_grouped_by_two_companies(self):
        other = Company.objects.create(name='Other')
        AssetGroup.objects.create(name='G1', company=self.acme).set_members([self.a1.pk])
        AssetGroup.objects.create(name='G2', company=other).set_members([self.a1.pk])
        self.assertEqual(AssetGroupMember.objects.filter(asset=self.a1).count(), 2)


class AssetGroupAdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client.force_login(User.objects.create_superuser('root', 'r@x.fr', 'pw'))
        self.acme = Company.objects.create(name='Acme')
        country = Country.objects.create(
            name='France', water_ownership='Public', land_ownership='Private')
        self.a1, self.a2 = (
            Asset.objects.create(name=f'Site {i}', latitude=1.0, longitude=2.0, country=country)
            for i in range(2)
        )
        self.g1 = AssetGroup.objects.create(name='G1', company=self.acme)
        self.g1.set_members([self.a1.pk])

    def _add_data(self, assets, name='G2'):
        data = {
            'name': name, 'company': self.acme.pk,
            'members-TOTAL_FORMS': len(assets), 'members-INITIAL_FORMS': 0,
            'members-MIN_NUM_FORMS': 0, 'members-MAX_NUM_FORMS': 1000,
        }
        for i, asset in enumerate(assets):
            data[f'members-{i}-asset'] = asset.pk
        return data

    def test_admin_rejects_asset_already_grouped_by_company(self):
        response = self.client.post(
            reverse('admin:dashboard_assetgroup_add'), self._add_data([self.a1]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'appartient déjà à un groupe')
        self.assertFalse(AssetGroup.objects.filter(name='G2').exists())

    def test_admin_rejects_duplicate_asset_in_same_submission(self):
        response = self.client.post(
            reverse('admin:dashboard_assetgroup_add'), self._add_data([self.a2, self.a2]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'appartient déjà à un groupe')

    def test_admin_accepts_free_asset(self):
        response = self.client.post(
            reverse('admin:dashboard_assetgroup_add'), self._add_data([self.a2]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AssetGroupMember.objects.filter(asset=self.a2).count(), 1)

    def test_company_is_readonly_when_editing(self):
        request = self.client.get(reverse('admin:index')).wsgi_request
        model_admin = admin.site._registry[AssetGroup]
        self.assertIn('company', model_admin.get_readonly_fields(request, self.g1))
        self.assertNotIn('company', model_admin.get_readonly_fields(request, None))
