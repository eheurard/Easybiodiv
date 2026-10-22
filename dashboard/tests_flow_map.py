"""Tests de la carte interactive des flux."""
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Asset, AssetGroupMember, AssetGroup, Company, Country


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
