"""Tests de la carte interactive des flux."""
import datetime

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import (
    ENDPOINT_COMPANY, Asset, AssetGroup, AssetGroupMember, Commodity, Company, Country, Flow,
    FlowKind, Ownership, SubnationalRegion,
)
from .services.flow_map import (
    assign_columns, build_flow_map, endpoint_fields, endpoint_key, parse_key, unlink,
    unlink_preview,
)
from .services.flows import perimeter_flows, perimeter_years
from .testing import make_declared_emission, make_inventory, make_production, make_supply


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


class PerimeterFlowsTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.cargill = Company.objects.create(name='Cargill')
        self.brazil = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private')
        self.soja = Commodity.objects.create(name='Soja')
        self.vevey, self.rotterdam = (
            Asset.objects.create(name=name, latitude=1.0, longitude=2.0, country=self.brazil)
            for name in ('Vevey', 'Rotterdam')
        )
        Ownership.objects.create(
            asset=self.vevey, company=self.acme, share=1, start_year=2020, end_year=None)
        Ownership.objects.create(
            asset=self.rotterdam, company=self.acme, share=1, start_year=2020, end_year=2023)

    def test_includes_flows_touching_company_or_owned_assets(self):
        f1 = make_supply(what=self.soja, year=2024, quantity=5,
                         origin=self.cargill, destination=self.vevey)
        f2 = make_declared_emission(company=self.acme, year=2024, scope='Scope 1', value=3)
        self.assertEqual(list(perimeter_flows(self.acme, 2024)), [f1, f2])

    def test_excludes_other_year_and_outside_flows(self):
        make_supply(what=self.soja, year=2023, quantity=5,
                    origin=self.cargill, destination=self.vevey)
        make_supply(what=self.soja, year=2024, quantity=5,
                    origin=self.brazil, destination=self.cargill)
        self.assertEqual(list(perimeter_flows(self.acme, 2024)), [])

    def test_excludes_asset_no_longer_owned(self):
        make_inventory(asset=self.rotterdam, key='water', year=2024, value=1)
        self.assertEqual(list(perimeter_flows(self.acme, 2024)), [])

    def test_touching_filters_on_one_block(self):
        f1 = make_supply(what=self.soja, year=2024, quantity=5,
                         origin=self.cargill, destination=self.vevey)
        make_inventory(asset=self.vevey, key='water', year=2024, value=1)
        self.assertEqual(
            list(perimeter_flows(self.acme, 2024, touching=(ENDPOINT_COMPANY, self.cargill.pk))),
            [f1])

    def test_perimeter_years(self):
        make_inventory(asset=self.vevey, key='water', year=2022, value=1)
        make_inventory(asset=self.rotterdam, key='water', year=2021, value=1)
        make_inventory(asset=self.rotterdam, key='water', year=2024, value=1)  # plus détenu
        self.assertEqual(perimeter_years(self.acme), [2021, 2022])


class AssignColumnsTests(SimpleTestCase):
    def test_chain_left_to_right(self):
        cols = assign_columns(['a', 'b', 'c'], [('a', 'b'), ('b', 'c')])
        self.assertEqual(cols, {'a': 0, 'b': 1, 'c': 2})

    def test_longest_path_wins(self):
        cols = assign_columns(['a', 'b', 'c'], [('a', 'b'), ('b', 'c'), ('a', 'c')])
        self.assertEqual(cols['c'], 2)

    def test_cycle_does_not_loop(self):
        cols = assign_columns(['a', 'b'], [('a', 'b'), ('b', 'a')])
        self.assertEqual(cols, {'a': 0, 'b': 1})

    def test_environment_ignored_and_unknown_out_last(self):
        cols = assign_columns(
            ['a', 'b', 'c', 'unknown-out'],
            [('a', 'b'), ('b', 'c'), ('a', 'unknown-out'), ('environment', 'b')])
        self.assertEqual(cols['unknown-out'], 3)
        self.assertNotIn('environment', cols)

    def test_isolated_node_is_in_first_column(self):
        self.assertEqual(assign_columns(['a', 'b'], []), {'a': 0, 'b': 0})


class EndpointKeyTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.brazil = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private')
        self.mato = SubnationalRegion.objects.create(name='Mato Grosso', country=self.brazil)
        self.soja = Commodity.objects.create(name='Soja')
        self.vevey = Asset.objects.create(
            name='Vevey', latitude=1.0, longitude=2.0, country=self.brazil)

    def test_located_ends(self):
        supply = make_supply(what=self.soja, year=2024, quantity=1,
                             origin=self.mato, destination=self.vevey)
        self.assertEqual(endpoint_key(supply, 'from'), f'region:{self.mato.pk}')
        self.assertEqual(endpoint_key(supply, 'to'), f'asset:{self.vevey.pk}')
        other = make_supply(what=self.soja, year=2024, quantity=1,
                            origin=self.brazil, destination=self.acme)
        self.assertEqual(endpoint_key(other, 'from'), f'country:{self.brazil.pk}')
        self.assertEqual(endpoint_key(other, 'to'), f'company:{self.acme.pk}')

    def test_environment_and_unknown_ends(self):
        water = make_inventory(asset=self.vevey, key='water', year=2024, value=1)
        self.assertEqual(endpoint_key(water, 'from'), 'environment')
        production = make_production(
            commodity=self.soja, year=2024, production=1, asset=self.vevey)
        self.assertEqual(endpoint_key(production, 'to'), 'unknown-out')
        unknown_origin = Flow.objects.create(
            kind=FlowKind.CONSUMPTION, what=self.soja, to_asset=self.vevey,
            year=2024, quantity=1)
        self.assertEqual(endpoint_key(unknown_origin, 'from'), 'unknown-in')

    def test_parse_key(self):
        self.assertEqual(parse_key('asset:5'), ('asset', 5))
        self.assertEqual(parse_key('group:3'), ('group', 3))
        self.assertEqual(parse_key('environment'), ('environment', None))
        self.assertEqual(parse_key('unknown-in'), (None, None))
        self.assertEqual(parse_key('unknown-out'), (None, None))
        for bad in ('asset', 'asset:', 'asset:x', 'site:5', 'asset:-1', '', 'asset:5:6'):
            with self.subTest(key=bad), self.assertRaises(ValueError):
                parse_key(bad)

    def test_endpoint_fields(self):
        self.assertEqual(endpoint_fields('from', 'asset:5'), {
            'from_asset': 5, 'from_region': None, 'from_country': None,
            'from_company': None, 'from_environment': False,
        })
        self.assertEqual(endpoint_fields('to', 'environment'), {
            'to_asset': None, 'to_region': None, 'to_country': None,
            'to_company': None, 'to_environment': True,
        })
        self.assertEqual(endpoint_fields('to', 'unknown-out'), {
            'to_asset': None, 'to_region': None, 'to_country': None,
            'to_company': None, 'to_environment': False,
        })
        self.assertEqual(endpoint_fields('from', 'country:2')['from_country'], 2)

    def test_endpoint_fields_rejects_group_and_bad_side(self):
        with self.assertRaises(ValueError):
            endpoint_fields('from', 'group:1')
        with self.assertRaises(ValueError):
            endpoint_fields('middle', 'asset:1')


class BuildFlowMapTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.cargill = Company.objects.create(name='Cargill')
        self.brazil = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private')
        self.soja = Commodity.objects.create(name='Soja', unit='t')
        self.vevey, self.rotterdam, self.mine = (
            Asset.objects.create(name=name, latitude=1.0, longitude=2.0, country=self.brazil)
            for name in ('Vevey', 'Rotterdam', 'Mine')
        )
        for asset in (self.vevey, self.rotterdam):
            Ownership.objects.create(
                asset=asset, company=self.acme, share=1, start_year=2020, end_year=None)

    def _blocks(self, data):
        return {block['key']: block for block in data['blocks']}

    def test_blocks_and_flows(self):
        supply = make_supply(what=self.soja, year=2024, quantity=5,
                             origin=self.cargill, destination=self.vevey)
        make_inventory(asset=self.vevey, key='water', year=2024, value=2)
        make_production(commodity=self.soja, year=2024, production=4, asset=self.vevey)
        data = build_flow_map(self.acme, 2024, AnonymousUser())
        blocks = self._blocks(data)
        self.assertEqual(set(blocks), {
            f'company:{self.acme.pk}', f'asset:{self.vevey.pk}',
            f'asset:{self.rotterdam.pk}', f'company:{self.cargill.pk}', 'unknown-out'})
        self.assertEqual(len(data['flows']), 3)
        self.assertFalse(data['can_edit'])
        self.assertEqual(data['company'], {'id': self.acme.pk, 'name': 'Acme'})
        self.assertEqual(data['year'], 2024)
        self.assertEqual(data['groups'], [])
        self.assertEqual(data['blocks'][0]['key'], f'company:{self.acme.pk}')
        self.assertEqual(blocks[f'company:{self.acme.pk}']['type'], 'company')
        self.assertEqual(blocks[f'company:{self.acme.pk}']['column'], 0)
        self.assertEqual(blocks[f'company:{self.cargill.pk}']['column'], 0)
        self.assertEqual(blocks[f'asset:{self.vevey.pk}']['column'], 1)
        self.assertEqual(blocks['unknown-out']['column'], 2)
        self.assertTrue(blocks[f'asset:{self.vevey.pk}']['owned'])
        self.assertFalse(blocks[f'company:{self.cargill.pk}']['owned'])
        self.assertEqual(blocks['unknown-out']['type'], 'unknown')
        self.assertIsNone(blocks['unknown-out']['id'])
        self.assertEqual(data['flows'][0], {
            'id': supply.pk, 'kind': 'SUPPLY', 'kind_label': 'Approvisionnement',
            'from': f'company:{self.cargill.pk}', 'to': f'asset:{self.vevey.pk}',
            'what': {'id': self.soja.pk, 'name': 'Soja', 'unit': 't'},
            'quantity': 5.0, 'year': 2024, 'tier': 0, 'scope': 'undefined',
            'source': '', 'reference': '',
        })

    def test_unknown_origin_block(self):
        Flow.objects.create(
            kind=FlowKind.CONSUMPTION, what=self.soja, to_asset=self.vevey,
            year=2024, quantity=1)
        blocks = self._blocks(build_flow_map(self.acme, 2024, AnonymousUser()))
        self.assertEqual(blocks['unknown-in']['column'], 0)
        self.assertEqual(blocks['unknown-in']['name'], 'Origine inconnue')
        self.assertEqual(blocks[f'asset:{self.vevey.pk}']['column'], 1)
        self.assertNotIn('unknown-out', blocks)

    def test_default_year_is_latest_with_flows_else_current(self):
        current = datetime.date.today().year
        data = build_flow_map(self.acme, None, AnonymousUser())
        self.assertEqual(data['year'], current)
        self.assertEqual(data['years'], [current])
        make_inventory(asset=self.vevey, key='water', year=2021, value=1)
        make_inventory(asset=self.vevey, key='water', year=2022, value=1)
        data = build_flow_map(self.acme, None, AnonymousUser())
        self.assertEqual(data['year'], 2022)
        self.assertEqual(data['years'], [2021, 2022, current])
        data = build_flow_map(self.acme, 1990, AnonymousUser())
        self.assertEqual(data['years'], [1990, 2021, 2022, current])

    def test_group_collapsed_for_layout_and_members_share_column(self):
        group = AssetGroup.objects.create(name='Usines', company=self.acme)
        group.set_members([self.vevey.pk, self.rotterdam.pk])
        make_supply(what=self.soja, year=2024, quantity=5,
                    origin=self.cargill, destination=self.vevey)
        make_supply(what=self.soja, year=2024, quantity=5,
                    origin=self.vevey, destination=self.rotterdam)
        data = build_flow_map(self.acme, 2024, AnonymousUser())
        blocks = self._blocks(data)
        group_key = f'group:{group.pk}'
        self.assertEqual(data['groups'], [{
            'key': group_key, 'id': group.pk, 'name': 'Usines',
            'members': [f'asset:{self.vevey.pk}', f'asset:{self.rotterdam.pk}'],
            'owned': True, 'column': 1,
        }])
        self.assertEqual(blocks[f'company:{self.cargill.pk}']['column'], 0)
        for asset in (self.vevey, self.rotterdam):
            self.assertEqual(blocks[f'asset:{asset.pk}']['column'], 1)
            self.assertEqual(blocks[f'asset:{asset.pk}']['group'], group_key)
        self.assertIsNone(blocks[f'company:{self.cargill.pk}']['group'])

    def test_group_without_present_member_is_omitted(self):
        AssetGroup.objects.create(name='Mines', company=self.acme).set_members([self.mine.pk])
        partial = AssetGroup.objects.create(name='Mixte', company=self.acme)
        other = Asset.objects.create(
            name='Autre', latitude=1.0, longitude=2.0, country=self.brazil)
        partial.set_members([self.vevey.pk, other.pk])
        data = build_flow_map(self.acme, 2024, AnonymousUser())
        self.assertEqual([g['name'] for g in data['groups']], ['Mixte'])
        self.assertEqual(data['groups'][0]['members'], [f'asset:{self.vevey.pk}'])
        self.assertNotIn(f'asset:{self.mine.pk}', self._blocks(data))

    def test_outside_group_is_not_owned(self):
        group = AssetGroup.objects.create(name='Mines', company=self.acme)
        group.set_members([self.mine.pk])
        make_supply(what=self.soja, year=2024, quantity=5,
                    origin=self.mine, destination=self.vevey)
        data = build_flow_map(self.acme, 2024, AnonymousUser())
        self.assertFalse(data['groups'][0]['owned'])
        self.assertFalse(self._blocks(data)[f'asset:{self.mine.pk}']['owned'])

    def test_other_company_group_is_ignored(self):
        cargill_group = AssetGroup.objects.create(name='Cargill', company=self.cargill)
        cargill_group.set_members([self.vevey.pk])
        data = build_flow_map(self.acme, 2024, AnonymousUser())
        self.assertEqual(data['groups'], [])
        self.assertIsNone(self._blocks(data)[f'asset:{self.vevey.pk}']['group'])

    def test_can_edit_for_creator(self):
        User = get_user_model()
        creator = User.objects.create_user('c', password='pw', role=User.CREATOR)
        subscriber = User.objects.create_user('s', password='pw', role=User.SUBSCRIBER)
        self.assertTrue(build_flow_map(self.acme, 2024, creator)['can_edit'])
        self.assertFalse(build_flow_map(self.acme, 2024, subscriber)['can_edit'])


class UnlinkTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.cargill = Company.objects.create(name='Cargill')
        self.brazil = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private')
        self.soja = Commodity.objects.create(name='Soja', unit='t')
        self.vevey = Asset.objects.create(
            name='Vevey', latitude=1.0, longitude=2.0, country=self.brazil)
        self.ownership = Ownership.objects.create(
            asset=self.vevey, company=self.acme, share=1, start_year=2020, end_year=None)
        for year in (2023, 2024):
            for _ in range(2 if year == 2024 else 1):
                make_supply(what=self.soja, year=year, quantity=5,
                            origin=self.cargill, destination=self.vevey)

    def test_preview_counts_only_displayed_year(self):
        self.assertEqual(unlink_preview(self.acme, 2024, f'company:{self.cargill.pk}'),
                         {'flows': 2, 'ownership': False})

    def test_preview_flags_owned_asset(self):
        self.assertEqual(unlink_preview(self.acme, 2024, f'asset:{self.vevey.pk}'),
                         {'flows': 2, 'ownership': True})

    def test_unlink_external_company_keeps_company_and_other_years(self):
        unlink(self.acme, 2024, f'company:{self.cargill.pk}')
        self.assertTrue(Company.objects.filter(pk=self.cargill.pk).exists())
        self.assertEqual(Flow.objects.filter(year=2023).count(), 1)
        self.assertEqual(Flow.objects.filter(year=2024).count(), 0)

    def test_unlink_owned_asset_ends_ownership_previous_year(self):
        result = unlink(self.acme, 2024, f'asset:{self.vevey.pk}')
        self.assertEqual(result, {'flows': 2, 'ownership': True})
        self.ownership.refresh_from_db()
        self.assertEqual(self.ownership.end_year, 2023)
        self.assertTrue(Asset.objects.filter(pk=self.vevey.pk).exists())

    def test_unlink_ownership_starting_that_year_is_deleted(self):
        self.ownership.start_year = 2024
        self.ownership.save()
        unlink(self.acme, 2024, f'asset:{self.vevey.pk}')
        self.assertFalse(Ownership.objects.filter(pk=self.ownership.pk).exists())

    def test_unlink_keeps_later_ownership(self):
        self.ownership.end_year = 2022
        self.ownership.save()
        later = Ownership.objects.create(
            asset=self.vevey, company=self.acme, share=1, start_year=2025, end_year=None)
        unlink(self.acme, 2021, f'asset:{self.vevey.pk}')
        self.ownership.refresh_from_db()
        later.refresh_from_db()
        self.assertEqual(self.ownership.end_year, 2020)
        self.assertEqual((later.start_year, later.end_year), (2025, None))

    def test_unlink_keeps_group_membership(self):
        group = AssetGroup.objects.create(name='G', company=self.acme)
        group.set_members([self.vevey.pk])
        unlink(self.acme, 2024, f'asset:{self.vevey.pk}')
        self.assertTrue(AssetGroup.objects.filter(pk=group.pk).exists())
        self.assertEqual(group.members.count(), 1)

    def test_unlink_refuses_the_company_itself(self):
        with self.assertRaises(ValueError):
            unlink(self.acme, 2024, f'company:{self.acme.pk}')

    def test_refuses_groups_environment_and_unknown(self):
        for key in ('group:1', 'environment', 'unknown-in', 'unknown-out'):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    unlink_preview(self.acme, 2024, key)
                with self.assertRaises(ValueError):
                    unlink(self.acme, 2024, key)
