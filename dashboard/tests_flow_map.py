"""Tests de la carte interactive des flux."""
import datetime
import json

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.http import urlencode

from .models import (
    ENDPOINT_COMPANY, FLOW_RULES, SUPPLY_SELF_LOOP_MESSAGE, Asset, AssetGroup,
    AssetGroupMember, Commodity, CommodityModifier, Company, Country, Flow, FlowKind, Ownership,
    REVENUE_PRODUCTION_ONLY_MESSAGE, SubnationalRegion,
)
from .services.flow_map import (
    assign_columns, block_details, build_flow_map, delete_flow_years, end_ownership, endpoint_fields,
    endpoint_key, flow_key, flow_years, latest_flows, owned_assets_in_range, parse_key, unlink,
    unlink_preview,
)
from .services.flow_map import _serialize_flow
from .services.flows import perimeter_flows, perimeter_years, range_perimeter_flows
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

    def test_range_perimeter_flows_is_union_of_years(self):
        flows = [
            make_supply(what=self.soja, year=year, quantity=5,
                        origin=self.cargill, destination=asset)
            for year in (2019, 2021, 2023, 2024)
            for asset in (self.vevey, self.rotterdam)
        ]
        make_supply(what=self.soja, year=2022, quantity=5,
                    origin=self.brazil, destination=self.cargill)
        expected = sorted(
            (flow for year in range(2019, 2025) for flow in perimeter_flows(self.acme, year)),
            key=lambda flow: (flow.year, flow.pk))
        self.assertEqual(range_perimeter_flows(self.acme, 2019, 2024), expected)
        self.assertEqual(
            [(f.year, f.to_asset_id) for f in expected],
            [(2021, self.vevey.pk), (2021, self.rotterdam.pk), (2023, self.vevey.pk),
             (2023, self.rotterdam.pk), (2024, self.vevey.pk)])
        self.assertNotIn(flows[0], expected)
        self.assertEqual(
            range_perimeter_flows(self.acme, 2022, 2024,
                                  touching=('asset', self.rotterdam.pk)),
            [flows[5]])


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

    def test_bands_are_ignored(self):
        cols = assign_columns(
            ['a', 'b', 'c', 'market'],
            [('a', 'b'), ('b', 'c'), ('market', 'a'), ('c', 'market'), ('environment', 'b')])
        self.assertEqual(cols, {'a': 0, 'b': 1, 'c': 2})

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

    def test_environment_and_market_ends(self):
        water = make_inventory(asset=self.vevey, key='water', year=2024, value=1)
        self.assertEqual(endpoint_key(water, 'from'), 'environment')
        production = make_production(
            commodity=self.soja, year=2024, production=1, asset=self.vevey)
        self.assertEqual(endpoint_key(production, 'to'), 'market')
        bought = Flow.objects.create(
            kind=FlowKind.SUPPLY, what=self.soja, to_asset=self.vevey,
            year=2024, quantity=1)
        self.assertEqual(endpoint_key(bought, 'from'), 'market')

    def test_parse_key(self):
        self.assertEqual(parse_key('asset:5'), ('asset', 5))
        self.assertEqual(parse_key('group:3'), ('group', 3))
        self.assertEqual(parse_key('environment'), ('environment', None))
        self.assertEqual(parse_key('market'), (None, None))
        for bad in ('asset', 'asset:', 'asset:x', 'site:5', 'asset:-1', '', 'asset:5:6',
                    'unknown-in', 'unknown-out'):
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
        self.assertEqual(endpoint_fields('to', 'market'), {
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
        data = build_flow_map(self.acme, 2024, 2024, AnonymousUser())
        blocks = self._blocks(data)
        self.assertEqual(set(blocks), {
            f'company:{self.acme.pk}', f'asset:{self.vevey.pk}',
            f'asset:{self.rotterdam.pk}', f'company:{self.cargill.pk}'})
        self.assertEqual(len(data['flows']), 3)
        self.assertFalse(data['can_edit'])
        self.assertEqual(data['company'], {'id': self.acme.pk, 'name': 'Acme'})
        self.assertEqual((data['start'], data['end']), (2024, 2024))
        self.assertEqual(data['groups'], [])
        self.assertEqual(data['blocks'][0]['key'], f'company:{self.acme.pk}')
        self.assertEqual(blocks[f'company:{self.acme.pk}']['type'], 'company')
        self.assertEqual(blocks[f'company:{self.acme.pk}']['column'], 0)
        self.assertEqual(blocks[f'company:{self.cargill.pk}']['column'], 0)
        self.assertEqual(blocks[f'asset:{self.vevey.pk}']['column'], 1)
        self.assertTrue(blocks[f'asset:{self.vevey.pk}']['owned'])
        self.assertFalse(blocks[f'company:{self.cargill.pk}']['owned'])
        self.assertEqual(data['flows'][2]['to'], 'market')
        self.assertEqual(data['flows'][0], {
            'id': supply.pk, 'kind': 'SUPPLY', 'kind_label': 'Approvisionnement',
            'from': f'company:{self.cargill.pk}', 'to': f'asset:{self.vevey.pk}',
            'what': {'id': self.soja.pk, 'name': 'Soja', 'unit': 't'},
            'quantity': 5.0, 'year': 2024, 'tier': 0, 'scope': 'undefined',
            'source': '', 'reference': '', 'modifiers': [],
        })

    def test_market_is_a_band_not_a_block(self):
        Flow.objects.create(
            kind=FlowKind.SUPPLY, what=self.soja, to_asset=self.vevey,
            year=2024, quantity=1)
        data = build_flow_map(self.acme, 2024, 2024, AnonymousUser())
        blocks = self._blocks(data)
        self.assertNotIn('market', blocks)
        self.assertEqual(blocks[f'asset:{self.vevey.pk}']['column'], 0)
        self.assertEqual((data['flows'][0]['from'], data['flows'][0]['to']),
                         ('market', f'asset:{self.vevey.pk}'))

    def test_default_range_is_known_years_else_current(self):
        current = datetime.date.today().year
        data = build_flow_map(self.acme, None, None, AnonymousUser())
        self.assertEqual((data['start'], data['end']), (current, current))
        self.assertEqual(data['years'], [current])
        make_inventory(asset=self.vevey, key='water', year=2021, value=1)
        make_inventory(asset=self.vevey, key='water', year=2022, value=1)
        data = build_flow_map(self.acme, None, None, AnonymousUser())
        self.assertEqual((data['start'], data['end']), (2021, 2022))
        self.assertEqual(data['years'], [2021, 2022, current])
        data = build_flow_map(self.acme, 1990, 1990, AnonymousUser())
        self.assertEqual(data['years'], [1990, 2021, 2022, current])
        data = build_flow_map(self.acme, 1985, 2095, AnonymousUser())
        self.assertEqual(data['years'], [1985, 2021, 2022, current, 2095])

    def test_group_collapsed_for_layout_and_members_share_column(self):
        group = AssetGroup.objects.create(name='Usines', company=self.acme)
        group.set_members([self.vevey.pk, self.rotterdam.pk])
        make_supply(what=self.soja, year=2024, quantity=5,
                    origin=self.cargill, destination=self.vevey)
        make_supply(what=self.soja, year=2024, quantity=5,
                    origin=self.vevey, destination=self.rotterdam)
        data = build_flow_map(self.acme, 2024, 2024, AnonymousUser())
        blocks = self._blocks(data)
        group_key = f'group:{group.pk}'
        self.assertEqual(data['groups'], [{
            'key': group_key, 'id': group.pk, 'name': 'Usines',
            'members': [f'asset:{self.vevey.pk}', f'asset:{self.rotterdam.pk}'],
            'all_members': [f'asset:{self.vevey.pk}', f'asset:{self.rotterdam.pk}'],
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
        data = build_flow_map(self.acme, 2024, 2024, AnonymousUser())
        self.assertEqual([g['name'] for g in data['groups']], ['Mixte'])
        self.assertEqual(data['groups'][0]['members'], [f'asset:{self.vevey.pk}'])
        self.assertEqual(data['groups'][0]['all_members'],
                         [f'asset:{self.vevey.pk}', f'asset:{other.pk}'])
        self.assertNotIn(f'asset:{self.mine.pk}', self._blocks(data))

    def test_outside_group_is_not_owned(self):
        group = AssetGroup.objects.create(name='Mines', company=self.acme)
        group.set_members([self.mine.pk])
        make_supply(what=self.soja, year=2024, quantity=5,
                    origin=self.mine, destination=self.vevey)
        data = build_flow_map(self.acme, 2024, 2024, AnonymousUser())
        self.assertFalse(data['groups'][0]['owned'])
        self.assertFalse(self._blocks(data)[f'asset:{self.mine.pk}']['owned'])

    def test_other_company_group_is_ignored(self):
        cargill_group = AssetGroup.objects.create(name='Cargill', company=self.cargill)
        cargill_group.set_members([self.vevey.pk])
        data = build_flow_map(self.acme, 2024, 2024, AnonymousUser())
        self.assertEqual(data['groups'], [])
        self.assertIsNone(self._blocks(data)[f'asset:{self.vevey.pk}']['group'])

    def test_can_edit_for_creator(self):
        User = get_user_model()
        creator = User.objects.create_user('c', password='pw', role=User.CREATOR)
        subscriber = User.objects.create_user('s', password='pw', role=User.SUBSCRIBER)
        self.assertTrue(build_flow_map(self.acme, 2024, 2024, creator)['can_edit'])
        self.assertFalse(build_flow_map(self.acme, 2024, 2024, subscriber)['can_edit'])


class BlockDetailsTests(TestCase):
    def setUp(self):
        self.brazil = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private')
        self.mato = SubnationalRegion.objects.create(name='Mato Grosso', country=self.brazil)
        self.acme = Company.objects.create(name='Acme', isin='FR0000000001', ticker='ACM')
        self.cargill = Company.objects.create(name='Cargill')
        self.farm = Asset.objects.create(
            name='Ferme', latitude=-12.5, longitude=-55.7, country=self.brazil,
            subnational_region=self.mato)
        self.silo = Asset.objects.create(
            name='Silo', latitude=1.0, longitude=2.0, country=self.brazil)
        Ownership.objects.create(
            asset=self.farm, company=self.cargill, share='0.4', start_year=2021, end_year=None)
        Ownership.objects.create(
            asset=self.farm, company=self.acme, share='0.6', start_year=2018, end_year=2022)
        Ownership.objects.create(
            asset=self.silo, company=self.acme, share='1', start_year=None, end_year=None)

    def test_asset_has_place_coordinates_and_every_ownership(self):
        details = block_details(f'asset:{self.farm.pk}')
        self.assertEqual(details['type'], 'asset')
        self.assertEqual(details['name'], 'Ferme')
        self.assertEqual(details['country'], 'Brésil')
        self.assertEqual(details['region'], 'Mato Grosso')
        self.assertEqual((details['latitude'], details['longitude']), (-12.5, -55.7))
        self.assertEqual(details['ownerships'], [
            {'company_id': self.acme.pk, 'company': 'Acme', 'share': 0.6,
             'start_year': 2018, 'end_year': 2022},
            {'company_id': self.cargill.pk, 'company': 'Cargill', 'share': 0.4,
             'start_year': 2021, 'end_year': None},
        ])

    def test_asset_without_region(self):
        details = block_details(f'asset:{self.silo.pk}')
        self.assertIsNone(details['region'])
        self.assertEqual(details['ownerships'][0]['start_year'], None)

    def test_company_has_identifiers_and_held_assets(self):
        details = block_details(f'company:{self.acme.pk}')
        self.assertEqual((details['isin'], details['ticker']), ('FR0000000001', 'ACM'))
        self.assertEqual(details['assets'], [
            {'asset_id': self.farm.pk, 'asset': 'Ferme', 'share': 0.6,
             'start_year': 2018, 'end_year': 2022},
            {'asset_id': self.silo.pk, 'asset': 'Silo', 'share': 1.0,
             'start_year': None, 'end_year': None},
        ])
        cargill = block_details(f'company:{self.cargill.pk}')
        self.assertEqual((cargill['isin'], cargill['ticker']), ('', ''))   # défaut « 0 »

    def test_country_and_region(self):
        self.assertEqual(block_details(f'country:{self.brazil.pk}'), {
            'key': f'country:{self.brazil.pk}', 'type': 'country', 'name': 'Brésil'})
        self.assertEqual(block_details(f'region:{self.mato.pk}'), {
            'key': f'region:{self.mato.pk}', 'type': 'region', 'name': 'Mato Grosso',
            'country': 'Brésil'})

    def test_bands_groups_and_bad_keys_are_refused(self):
        for key in ('environment', 'market', 'group:1', 'nope'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                block_details(key)

    def test_missing_object_is_does_not_exist(self):
        with self.assertRaises(Asset.DoesNotExist):
            block_details('asset:999999')


class RangeFlowMapTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.cargill = Company.objects.create(name='Cargill')
        self.brazil = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private')
        self.soja = Commodity.objects.create(name='Soja', unit='t')
        self.vevey, self.mine = (
            Asset.objects.create(name=name, latitude=1.0, longitude=2.0, country=self.brazil)
            for name in ('Vevey', 'Mine')
        )
        Ownership.objects.create(
            asset=self.vevey, company=self.acme, share=1, start_year=2020, end_year=None)
        Ownership.objects.create(
            asset=self.mine, company=self.acme, share=1, start_year=2021, end_year=2022)

    def _ids(self, data):
        return [flow['id'] for flow in data['flows']]

    def test_latest_year_wins_for_same_flow(self):
        make_supply(what=self.soja, year=2021, quantity=5,
                    origin=self.cargill, destination=self.vevey)
        new = make_supply(what=self.soja, year=2023, quantity=7,
                          origin=self.cargill, destination=self.vevey)
        data = build_flow_map(self.acme, 2020, 2024, AnonymousUser())
        self.assertEqual(self._ids(data), [new.pk])
        self.assertEqual(data['flows'][0]['year'], 2023)
        self.assertEqual((data['start'], data['end']), (2020, 2024))
        self.assertNotIn('year', data)

    def test_different_scope_is_another_flow(self):
        old = make_declared_emission(company=self.acme, year=2021, scope='Scope 1', value=3)
        new = make_declared_emission(company=self.acme, year=2023, scope='Scope 2', value=4)
        data = build_flow_map(self.acme, 2020, 2024, AnonymousUser())
        self.assertEqual(self._ids(data), [old.pk, new.pk])

    def test_same_year_duplicates_are_both_kept(self):
        make_supply(what=self.soja, year=2021, quantity=1,
                    origin=self.cargill, destination=self.vevey)
        first, second = (
            make_supply(what=self.soja, year=2023, quantity=quantity,
                        origin=self.cargill, destination=self.vevey)
            for quantity in (5, 6)
        )
        data = build_flow_map(self.acme, 2020, 2024, AnonymousUser())
        self.assertEqual(self._ids(data), [first.pk, second.pk])

    def test_asset_owned_part_of_range_is_owned_block(self):
        data = build_flow_map(self.acme, 2022, 2024, AnonymousUser())
        blocks = {block['key']: block for block in data['blocks']}
        self.assertTrue(blocks[f'asset:{self.mine.pk}']['owned'])
        self.assertEqual(list(owned_assets_in_range(self.acme, 2022, 2024)),
                         [self.vevey, self.mine])
        self.assertEqual(list(owned_assets_in_range(self.acme, 2023, 2024)), [self.vevey])
        self.assertEqual(list(owned_assets_in_range(self.acme, 2018, 2019)), [])
        data = build_flow_map(self.acme, 2023, 2024, AnonymousUser())
        self.assertNotIn(f'asset:{self.mine.pk}',
                         {block['key'] for block in data['blocks']})

    def test_two_ownership_periods_exclude_flows_of_the_gap(self):
        depot = Asset.objects.create(
            name='Dépôt', latitude=1.0, longitude=2.0, country=self.brazil)
        for first, last in ((2020, 2021), (2023, 2024)):
            Ownership.objects.create(
                asset=depot, company=self.acme, share=1, start_year=first, end_year=last)
        rows = {
            year: make_supply(what=self.soja, year=year, quantity=year,
                              origin=self.cargill, destination=depot)
            for year in (2020, 2021, 2022, 2023, 2024)
        }
        # Même clé de flux sur toute la plage : la ligne de la dernière année l'emporte,
        # les années de trou sont écartées du périmètre.
        flows = range_perimeter_flows(self.acme, 2020, 2024)
        self.assertEqual(sorted(f.year for f in flows), [2020, 2021, 2023, 2024])
        data = build_flow_map(self.acme, 2020, 2024, AnonymousUser())
        self.assertEqual(self._ids(data), [rows[2024].pk])
        self.assertEqual(
            flow_years(self.acme, 2020, 2024, rows[2022]),
            [{'year': 2020, 'count': 1}, {'year': 2021, 'count': 1},
             {'year': 2023, 'count': 1}, {'year': 2024, 'count': 1}])
        self.assertEqual(self._ids(build_flow_map(self.acme, 2022, 2022, AnonymousUser())), [])

    def test_flow_of_year_asset_not_owned_is_excluded(self):
        kept = make_supply(what=self.soja, year=2022, quantity=5,
                           origin=self.cargill, destination=self.mine)
        make_supply(what=self.soja, year=2024, quantity=5,
                    origin=self.cargill, destination=self.mine)
        data = build_flow_map(self.acme, 2020, 2024, AnonymousUser())
        self.assertEqual(self._ids(data), [kept.pk])

    def test_default_range_spans_known_years(self):
        make_inventory(asset=self.vevey, key='water', year=2019, value=1)  # pas encore détenu
        make_inventory(asset=self.vevey, key='water', year=2020, value=1)
        make_declared_emission(company=self.acme, year=2022, scope='Scope 1', value=3)
        data = build_flow_map(self.acme, None, None, AnonymousUser())
        self.assertEqual((data['start'], data['end']), (2020, 2022))

    def test_single_year_range_matches_year_view(self):
        group = AssetGroup.objects.create(name='Usines', company=self.acme)
        group.set_members([self.vevey.pk, self.mine.pk])
        for year in (2021, 2022, 2023):
            make_supply(what=self.soja, year=year, quantity=5,
                        origin=self.cargill, destination=self.mine)
            make_supply(what=self.soja, year=year, quantity=5,
                        origin=self.mine, destination=self.vevey)
        make_inventory(asset=self.vevey, key='water', year=2022, value=1)
        data = build_flow_map(self.acme, 2022, 2022, AnonymousUser())
        self.assertEqual(self._ids(data),
                         [flow.pk for flow in perimeter_flows(self.acme, 2022)])
        owned = {block['key'] for block in data['blocks'] if block['owned']}
        self.assertEqual(owned, {f'company:{self.acme.pk}'} | {
            f'asset:{asset.pk}' for asset in Asset.objects.owned_by(self.acme, 2022)})
        self.assertEqual(data['groups'][0]['members'],
                         [f'asset:{self.vevey.pk}', f'asset:{self.mine.pk}'])

    def test_one_bound_missing_raises(self):
        with self.assertRaises(ValueError):
            build_flow_map(self.acme, 2020, None, AnonymousUser())
        with self.assertRaises(ValueError):
            build_flow_map(self.acme, None, 2020, AnonymousUser())
        with self.assertRaises(ValueError):
            build_flow_map(self.acme, 2024, 2020, AnonymousUser())

    def test_flow_key_and_latest_flows(self):
        old = make_supply(what=self.soja, year=2021, quantity=5,
                          origin=self.cargill, destination=self.vevey)
        new = make_supply(what=self.soja, year=2023, quantity=5,
                          origin=self.cargill, destination=self.vevey)
        other = make_supply(what=self.soja, year=2021, quantity=5,
                            origin=self.brazil, destination=self.vevey)
        self.assertEqual(flow_key(old), (
            'SUPPLY', self.soja.pk, f'company:{self.cargill.pk}', f'asset:{self.vevey.pk}',
            'undefined', ()))
        self.assertEqual(flow_key(old), flow_key(new))
        self.assertEqual(latest_flows([new, old, other]), [other, new])


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
        self.assertEqual(
            unlink_preview(self.acme, 2024, 2024, f'company:{self.cargill.pk}'),
            {'years': [{'year': 2024, 'flows': 2}], 'ownership': False,
             'ownership_year': None, 'co_owners': []})

    def test_preview_flags_owned_asset(self):
        self.assertEqual(
            unlink_preview(self.acme, 2024, 2024, f'asset:{self.vevey.pk}'),
            {'years': [{'year': 2024, 'flows': 2}], 'ownership': True,
             'ownership_year': 2024, 'co_owners': []})

    def test_unlink_external_company_keeps_company_and_other_years(self):
        unlink(self.acme, 2024, 2024, f'company:{self.cargill.pk}', years=[2024],
               ownership_year=None)
        self.assertTrue(Company.objects.filter(pk=self.cargill.pk).exists())
        self.assertEqual(Flow.objects.filter(year=2023).count(), 1)
        self.assertEqual(Flow.objects.filter(year=2024).count(), 0)

    def test_unlink_owned_asset_ends_ownership_previous_year(self):
        result = unlink(self.acme, 2024, 2024, f'asset:{self.vevey.pk}', years=[2024],
                        ownership_year=2024)
        self.assertEqual(result, {'flows': 2, 'ownership': True})
        self.ownership.refresh_from_db()
        self.assertEqual(self.ownership.end_year, 2023)
        self.assertTrue(Asset.objects.filter(pk=self.vevey.pk).exists())

    def test_preview_lists_co_owners_and_unlink_keeps_their_ownership(self):
        other = Ownership.objects.create(
            asset=self.vevey, company=self.cargill, share=0.5, start_year=2020)
        key = f'asset:{self.vevey.pk}'
        self.assertEqual(unlink_preview(self.acme, 2024, 2024, key)['co_owners'], ['Cargill'])
        self.assertEqual(unlink(self.acme, 2024, 2024, key, years=[2024], ownership_year=2024),
                         {'flows': 2, 'ownership': True})
        other.refresh_from_db()
        self.assertIsNone(other.end_year)
        self.assertEqual(
            unlink_preview(self.acme, 2024, 2024, f'company:{self.cargill.pk}')['co_owners'],
            [])

    def test_unlink_ownership_starting_that_year_is_deleted(self):
        self.ownership.start_year = 2024
        self.ownership.save()
        unlink(self.acme, 2024, 2024, f'asset:{self.vevey.pk}', years=[2024],
               ownership_year=2024)
        self.assertFalse(Ownership.objects.filter(pk=self.ownership.pk).exists())

    def test_unlink_keeps_later_ownership(self):
        self.ownership.end_year = 2022
        self.ownership.save()
        later = Ownership.objects.create(
            asset=self.vevey, company=self.acme, share=1, start_year=2025, end_year=None)
        unlink(self.acme, 2021, 2021, f'asset:{self.vevey.pk}', years=[],
               ownership_year=2021)
        self.ownership.refresh_from_db()
        later.refresh_from_db()
        self.assertEqual(self.ownership.end_year, 2020)
        self.assertEqual((later.start_year, later.end_year), (2025, None))

    def test_unlink_keeps_another_companys_ownership_starting_in_range(self):
        # Détention d'une autre entreprise débutant dans (Y, F] : elle n'est pas touchée.
        other = Ownership.objects.create(
            asset=self.vevey, company=self.cargill, share=0.3, start_year=2022, end_year=None)
        unlink(self.acme, 2021, 2024, f'asset:{self.vevey.pk}', years=[],
               ownership_year=2021)
        other.refresh_from_db()
        self.assertEqual((other.start_year, other.end_year), (2022, None))
        end_ownership(self.acme, self.vevey, 2021, 2024)
        other.refresh_from_db()
        self.assertEqual((other.start_year, other.end_year), (2022, None))

    def test_unlink_keeps_group_membership(self):
        group = AssetGroup.objects.create(name='G', company=self.acme)
        group.set_members([self.vevey.pk])
        unlink(self.acme, 2024, 2024, f'asset:{self.vevey.pk}', years=[2024],
               ownership_year=2024)
        self.assertTrue(AssetGroup.objects.filter(pk=group.pk).exists())
        self.assertEqual(group.members.count(), 1)

    def test_unlink_refuses_the_company_itself(self):
        with self.assertRaises(ValueError):
            unlink(self.acme, 2024, 2024, f'company:{self.acme.pk}', years=[2024],
                   ownership_year=None)
        self.assertEqual(Flow.objects.count(), 3)

    def test_refuses_groups_environment_and_market(self):
        for key in ('group:1', 'environment', 'market'):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    unlink_preview(self.acme, 2024, 2024, key)
                with self.assertRaises(ValueError):
                    unlink(self.acme, 2024, 2024, key, years=[2024], ownership_year=None)


class RangeDeletionTests(TestCase):
    """Suppression par années et retrait de liens sur une plage (spec §10.3)."""

    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.cargill = Company.objects.create(name='Cargill')
        self.brazil = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private')
        self.soja = Commodity.objects.create(name='Soja', unit='t')
        self.vevey, self.bale = (
            Asset.objects.create(name=name, latitude=1.0, longitude=2.0, country=self.brazil)
            for name in ('Vevey', 'Bâle')
        )
        self.ownership = Ownership.objects.create(
            asset=self.vevey, company=self.acme, share=1, start_year=2015, end_year=None)

    def _supply(self, year, origin=None):
        return make_supply(what=self.soja, year=year, quantity=5,
                           origin=origin or self.cargill, destination=self.vevey)

    def _remaining(self):
        return set(Flow.objects.values_list('pk', flat=True))

    def test_flow_years_lists_years_with_counts(self):
        old = self._supply(2021)
        new = self._supply(2023)
        self._supply(2023, origin=self.brazil)  # autre clé : autre origine
        self._supply(2019)  # hors plage
        expected = [{'year': 2021, 'count': 1}, {'year': 2023, 'count': 1}]
        self.assertEqual(flow_years(self.acme, 2020, 2024, new), expected)
        self.assertEqual(flow_years(self.acme, 2020, 2024, old), expected)

    def test_flow_years_counts_rows_of_same_year(self):
        new = self._supply(2023)
        self._supply(2023)
        self.assertEqual(flow_years(self.acme, 2020, 2024, new), [{'year': 2023, 'count': 2}])

    def test_flow_years_skip_years_outside_perimeter(self):
        self.ownership.start_year = 2022
        self.ownership.save()
        self._supply(2021)  # Vevey pas encore détenu
        new = self._supply(2023)
        self.assertEqual(flow_years(self.acme, 2020, 2024, new), [{'year': 2023, 'count': 1}])

    def test_delete_flow_years_only_checked(self):
        old = self._supply(2021)
        new = self._supply(2023)
        other = self._supply(2021, origin=self.brazil)
        before = self._supply(2019)
        self.assertEqual(delete_flow_years(self.acme, 2020, 2024, new, [2021]), 1)
        self.assertNotIn(old.pk, self._remaining())
        self.assertEqual(self._remaining(), {new.pk, other.pk, before.pk})

    def test_delete_flow_years_spares_rows_outside_perimeter(self):
        self.ownership.start_year = 2022
        self.ownership.save()
        old = self._supply(2021)  # hors périmètre : Vevey pas encore détenu
        new = self._supply(2023)
        self.assertEqual(delete_flow_years(self.acme, 2020, 2024, new, [2021, 2023]), 1)
        self.assertEqual(self._remaining(), {old.pk})

    def test_delete_flow_years_rejects_out_of_range(self):
        self._supply(2021)
        new = self._supply(2023)
        for years in ([], [2019], [2021, 2025]):
            with self.subTest(years=years):
                with self.assertRaises(ValueError):
                    delete_flow_years(self.acme, 2020, 2024, new, years)
        self.assertEqual(Flow.objects.count(), 2)

    def test_unlink_preview_range(self):
        self._supply(2021)
        self._supply(2023)
        self._supply(2023)
        self._supply(2022, origin=self.brazil)
        self._supply(2019)  # hors plage
        zeta, bunge = (Company.objects.create(name=name) for name in ('Zeta', 'Bunge'))
        Ownership.objects.create(
            asset=self.vevey, company=self.cargill, share=0.2, start_year=2010, end_year=2020)
        Ownership.objects.create(asset=self.vevey, company=zeta, share=0.2, start_year=2024)
        Ownership.objects.create(  # se termine avant la plage
            asset=self.vevey, company=bunge, share=0.2, start_year=2010, end_year=2019)
        self.assertEqual(unlink_preview(self.acme, 2020, 2024, f'asset:{self.vevey.pk}'), {
            'years': [{'year': 2021, 'flows': 1}, {'year': 2022, 'flows': 1},
                      {'year': 2023, 'flows': 2}],
            'ownership': True, 'ownership_year': 2021, 'co_owners': ['Cargill', 'Zeta'],
        })
        self.assertEqual(
            unlink_preview(self.acme, 2020, 2024, f'company:{self.cargill.pk}'), {
                'years': [{'year': 2021, 'flows': 1}, {'year': 2023, 'flows': 2}],
                'ownership': False, 'ownership_year': None, 'co_owners': [],
            })

    def test_unlink_preview_without_flows(self):
        self.assertEqual(
            unlink_preview(self.acme, 2020, 2024, f'asset:{self.vevey.pk}'),
            {'years': [], 'ownership': True, 'ownership_year': 2020, 'co_owners': []})
        self.assertEqual(
            unlink_preview(self.acme, 2020, 2024, f'asset:{self.bale.pk}'),
            {'years': [], 'ownership': False, 'ownership_year': None, 'co_owners': []})

    def test_unlink_selected_years_only(self):
        f2021 = self._supply(2021)
        self._supply(2023)
        f2019 = self._supply(2019)
        result = unlink(self.acme, 2020, 2024, f'company:{self.cargill.pk}', years=[2023],
                        ownership_year=None)
        self.assertEqual(result, {'flows': 1, 'ownership': False})
        self.assertEqual(self._remaining(), {f2021.pk, f2019.pk})

    def test_unlink_with_ownership_option(self):
        self.ownership.end_year = 2022
        self.ownership.save()
        short = Ownership.objects.create(
            asset=self.vevey, company=self.acme, share=1, start_year=2023, end_year=2023)
        later = Ownership.objects.create(
            asset=self.vevey, company=self.acme, share=1, start_year=2026, end_year=None)
        self._supply(2022)
        f2023 = self._supply(2023)
        result = unlink(self.acme, 2020, 2024, f'asset:{self.vevey.pk}', years=[2022],
                        ownership_year=2022)
        self.assertEqual(result, {'flows': 1, 'ownership': True})
        self.ownership.refresh_from_db()
        self.assertEqual((self.ownership.start_year, self.ownership.end_year), (2015, 2021))
        self.assertFalse(Ownership.objects.filter(pk=short.pk).exists())
        later.refresh_from_db()
        self.assertEqual((later.start_year, later.end_year), (2026, None))
        self.assertEqual(self._remaining(), {f2023.pk})
        self.assertTrue(Asset.objects.filter(pk=self.vevey.pk).exists())

    def test_unlink_without_ownership_option_keeps_ownership(self):
        self._supply(2022)
        self._supply(2023)
        result = unlink(self.acme, 2020, 2024, f'asset:{self.vevey.pk}', years=[2022, 2023],
                        ownership_year=None)
        self.assertEqual(result, {'flows': 2, 'ownership': False})
        self.assertEqual(Flow.objects.count(), 0)
        self.ownership.refresh_from_db()
        self.assertEqual((self.ownership.start_year, self.ownership.end_year), (2015, None))

    def test_unlink_nothing_selected_raises(self):
        self._supply(2022)
        vevey, cargill = f'asset:{self.vevey.pk}', f'company:{self.cargill.pk}'
        refused = [
            (vevey, [], None),  # rien de coché
            (vevey, [2019], None),  # année hors plage
            (vevey, [2022], 2025),  # fin de détention hors plage
            (cargill, [2022], 2022),  # pas un actif détenu
            (f'asset:{self.bale.pk}', [], 2022),  # actif non détenu sur la plage
        ]
        for key, years, ownership_year in refused:
            with self.subTest(key=key, years=years, ownership_year=ownership_year):
                with self.assertRaises(ValueError):
                    unlink(self.acme, 2020, 2024, key, years=years,
                           ownership_year=ownership_year)
        self.assertEqual(Flow.objects.count(), 1)
        self.ownership.refresh_from_db()
        self.assertIsNone(self.ownership.end_year)


class FlowWriteApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.creator = user_model.objects.create_user('createur', password='x', role='CREATOR')
        self.subscriber = user_model.objects.create_user(
            'abonne', password='x', role='SUBSCRIBER')
        self.client.force_login(self.creator)
        self.cargill = Company.objects.create(name='Cargill')
        self.brazil = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private')
        self.soja = Commodity.objects.create(name='Soja')
        self.vevey = Asset.objects.create(
            name='Vevey', latitude=1.0, longitude=2.0, country=self.brazil)
        self.other = Asset.objects.create(
            name='Autre', latitude=1.0, longitude=2.0, country=self.brazil)

    def _post(self, name, body, *args):
        return self.client.post(
            reverse(name, args=args), data=json.dumps(body), content_type='application/json')

    def _supply(self, **extra):
        body = {'kind': 'SUPPLY', 'what_id': self.soja.pk, 'quantity': 12, 'year': 2024,
                'from': f'company:{self.cargill.pk}', 'to': f'asset:{self.vevey.pk}'}
        body.update(extra)
        return body

    def test_anonymous_and_subscriber_are_refused(self):
        for user in (None, self.subscriber):
            self.client.logout()
            if user:
                self.client.force_login(user)
            r = self._post('dashboard:flow_map_flow_create', self._supply())
            self.assertEqual(r.status_code, 403)
            self.assertIn('__all__', r.json()['errors'])
        self.assertEqual(Flow.objects.count(), 0)

    def test_create_supply(self):
        r = self._post('dashboard:flow_map_flow_create', self._supply())
        self.assertEqual(r.status_code, 201)
        flow = Flow.objects.get(pk=r.json()['id'])
        self.assertEqual((flow.from_company, flow.to_asset, flow.created_by),
                         (self.cargill, self.vevey, self.creator))

    def test_create_consumption_from_environment(self):
        r = self._post('dashboard:flow_map_flow_create', self._supply(
            kind='CONSUMPTION', **{'from': 'environment'}))
        self.assertEqual(r.status_code, 201, r.content)
        flow = Flow.objects.get(pk=r.json()['id'])
        self.assertTrue(flow.from_environment)
        self.assertEqual(flow.to_asset, self.vevey)

    def test_create_production_to_market(self):
        r = self._post('dashboard:flow_map_flow_create', self._supply(
            kind='PRODUCTION', **{'from': f'asset:{self.vevey.pk}', 'to': 'market'}))
        self.assertEqual(r.status_code, 201, r.content)
        flow = Flow.objects.get(pk=r.json()['id'])
        self.assertIsNone(flow.to_asset)
        self.assertFalse(flow.to_environment)

    def test_create_supply_from_market(self):
        r = self._post('dashboard:flow_map_flow_create', self._supply(**{'from': 'market'}))
        self.assertEqual(r.status_code, 201, r.content)
        flow = Flow.objects.get(pk=r.json()['id'])
        self.assertEqual(
            (flow.from_asset, flow.from_region, flow.from_country, flow.from_company),
            (None, None, None, None))
        self.assertEqual(flow.to_asset, self.vevey)

    def test_create_supply_to_market_is_refused(self):
        r = self._post('dashboard:flow_map_flow_create', self._supply(**{'to': 'market'}))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Flow.objects.count(), 0)

    def test_create_flow_accepts_french_number(self):
        r = self._post('dashboard:flow_map_flow_create', self._supply(quantity='12 400,5'))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Flow.objects.get(pk=r.json()['id']).quantity, 12400.5)

    def test_create_rejects_bad_quantity_and_keys(self):
        for quantity in ('abc', 0, -3, None, '1_000'):
            r = self._post('dashboard:flow_map_flow_create', self._supply(quantity=quantity))
            self.assertEqual(r.status_code, 400)
            self.assertIn('quantity', r.json()['errors'])
        for key in ('nope', None, 5, 'group:1'):
            r = self._post('dashboard:flow_map_flow_create', self._supply(**{'from': key}))
            self.assertEqual(r.status_code, 400)
            self.assertIn('__all__', r.json()['errors'])
        self.assertEqual(Flow.objects.count(), 0)

    def test_create_supply_to_itself_returns_rule_message(self):
        r = self._post('dashboard:flow_map_flow_create', self._supply(
            **{'from': f'asset:{self.vevey.pk}', 'to': f'asset:{self.vevey.pk}'}))
        self.assertEqual(r.status_code, 400)
        self.assertIn(SUPPLY_SELF_LOOP_MESSAGE, r.json()['errors']['__all__'])

    def test_kind_forbidden_by_rules_returns_rule_message(self):
        r = self._post('dashboard:flow_map_flow_create', self._supply(
            kind='EMISSION', **{'from': f'country:{self.brazil.pk}', 'to': 'environment'}))
        self.assertEqual(r.status_code, 400)
        self.assertIn(FLOW_RULES['EMISSION'].message, r.json()['errors']['__all__'])

    def test_update_keeps_endpoints(self):
        flow = make_supply(what=self.soja, year=2024, quantity=1,
                           origin=self.cargill, destination=self.vevey)
        r = self._post('dashboard:flow_map_flow_update', self._supply(
            quantity=5, **{'from': f'asset:{self.other.pk}', 'to': f'asset:{self.other.pk}'}),
            flow.pk)
        self.assertEqual(r.status_code, 200, r.content)
        flow.refresh_from_db()
        self.assertEqual(flow.quantity, 5)
        self.assertEqual((flow.from_company, flow.to_asset), (self.cargill, self.vevey))

    def test_update_missing_flow_returns_404(self):
        r = self._post('dashboard:flow_map_flow_update', self._supply(), 999999)
        self.assertEqual(r.status_code, 404)
        self.assertIn('__all__', r.json()['errors'])

    def test_update_to_waste_of_priced_production_is_refused(self):
        flow = make_production(commodity=self.soja, year=2024, production=3,
                               asset=self.vevey, estimated_revenue=10.0)
        r = self._post('dashboard:flow_map_flow_update', {
            'kind': 'WASTE', 'what_id': self.soja.pk, 'quantity': 3, 'year': 2024}, flow.pk)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn(REVENUE_PRODUCTION_ONLY_MESSAGE, r.json()['errors']['__all__'])
        flow.refresh_from_db()
        self.assertEqual(flow.kind, FlowKind.PRODUCTION)

    def test_update_keeps_omitted_optional_fields(self):
        flow = make_supply(what=self.soja, year=2024, quantity=1,
                           origin=self.cargill, destination=self.vevey, tier=2)
        flow.scope = 'Scope 3'
        flow.source = 'Src'
        flow.reference = 'Ref'
        flow.save()
        r = self._post('dashboard:flow_map_flow_update', {
            'kind': 'SUPPLY', 'what_id': self.soja.pk, 'quantity': 7, 'year': 2024}, flow.pk)
        self.assertEqual(r.status_code, 200, r.content)
        flow.refresh_from_db()
        self.assertEqual((flow.quantity, flow.scope, flow.tier, flow.source, flow.reference),
                         (7, 'Scope 3', 2, 'Src', 'Ref'))

    def test_year_out_of_bounds_is_refused(self):
        r = self._post('dashboard:flow_map_flow_create', self._supply(year=20244))
        self.assertEqual(r.status_code, 400)
        self.assertIn('year', r.json()['errors'])
        self.assertEqual(Flow.objects.count(), 0)

    def _owned_flows(self, years=(2022, 2023, 2024)):
        acme = Company.objects.create(name='Acme')
        Ownership.objects.create(asset=self.vevey, company=acme, share=1, start_year=2015)
        flows = [make_supply(what=self.soja, year=year, quantity=1,
                             origin=self.cargill, destination=self.vevey) for year in years]
        return acme, flows

    def _delete(self, acme, flow, body):
        return self._post('dashboard:flow_map_flow_delete', body, acme.pk, flow.pk)

    def test_flow_years_endpoint(self):
        acme, flows = self._owned_flows()
        url = reverse('dashboard:flow_map_flow_years', args=[acme.pk, flows[2].pk])
        self.client.logout()
        r = self.client.get(url, {'start': 2023, 'end': 2025})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'years': [{'year': 2023, 'count': 1},
                                              {'year': 2024, 'count': 1}]})

    def test_flow_years_requires_valid_range(self):
        acme, flows = self._owned_flows()
        url = reverse('dashboard:flow_map_flow_years', args=[acme.pk, flows[0].pk])
        for params in ({}, {'start': 2022}, {'start': 2024, 'end': 2022},
                       {'start': 'x', 'end': 1}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(url, params).status_code, 400)
        missing = reverse('dashboard:flow_map_flow_years', args=[acme.pk, 999999])
        self.assertEqual(self.client.get(missing, {'start': 2022, 'end': 2024}).status_code, 404)

    def test_delete_flow_selected_years(self):
        acme, flows = self._owned_flows()
        r = self._delete(acme, flows[2], {'start': 2022, 'end': 2024, 'years': [2022, 2024]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'deleted': 2})
        self.assertEqual(list(Flow.objects.values_list('year', flat=True)), [2023])

    def test_delete_flow_missing_is_404(self):
        acme, flows = self._owned_flows(years=(2024,))
        body = {'start': 2024, 'end': 2024, 'years': [2024]}
        self.assertEqual(self._delete(acme, flows[0], body).json(), {'deleted': 1})
        self.assertEqual(self._delete(acme, flows[0], body).status_code, 404)

    def test_delete_flow_rejects_year_outside_range(self):
        acme, flows = self._owned_flows()
        r = self._delete(acme, flows[2], {'start': 2023, 'end': 2024, 'years': [2022, 2024]})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Flow.objects.count(), 3)

    def test_delete_flow_rejects_bad_body(self):
        acme, flows = self._owned_flows()
        bad_years = ['2024', 2024.0, True, None, [], [None], [2024.5], 'x', [2024, '2023']]
        for years in bad_years:
            with self.subTest(years=years):
                r = self._delete(acme, flows[2], {'start': 2022, 'end': 2024, 'years': years})
                self.assertEqual(r.status_code, 400)
                self.assertIn('years', r.json()['errors'])
        for start, end in (('2022', 2024), (2022, None), (2024, 2022), (1800, 2024),
                           (True, 2024)):
            with self.subTest(start=start, end=end):
                r = self._delete(acme, flows[2], {'start': start, 'end': end, 'years': [2024]})
                self.assertEqual(r.status_code, 400)
                self.assertTrue({'start', 'end'} & set(r.json()['errors']))
        self.assertEqual(Flow.objects.count(), 3)
        r = self.client.post(
            reverse('dashboard:flow_map_flow_delete', args=[acme.pk, flows[0].pk]),
            data='pas du json', content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_delete_flow_refused_for_subscriber(self):
        acme, flows = self._owned_flows()
        self.client.force_login(self.subscriber)
        r = self._delete(acme, flows[2], {'start': 2022, 'end': 2024, 'years': [2024]})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Flow.objects.count(), 3)


class FlowModifierApiTests(TestCase):
    """Modificateurs de commodité cochés sur un flux (API de la carte)."""

    def setUp(self):
        user_model = get_user_model()
        self.creator = user_model.objects.create_user('createur', password='x', role='CREATOR')
        self.client.force_login(self.creator)
        self.cargill = Company.objects.create(name='Cargill')
        self.brazil = Country.objects.create(
            name='Brésil', water_ownership='Public', land_ownership='Private')
        self.mato = SubnationalRegion.objects.create(name='Mato Grosso', country=self.brazil)
        self.soja = Commodity.objects.create(name='Soja')
        self.maize = Commodity.objects.create(name='Maïs')
        self.certified = CommodityModifier.objects.create(commodity=self.soja, name='Certifié')
        self.bio = CommodityModifier.objects.create(commodity=self.soja, name='Bio')
        self.maize_bio = CommodityModifier.objects.create(commodity=self.maize, name='Bio maïs')
        self.vevey = Asset.objects.create(
            name='Vevey', latitude=1.0, longitude=2.0, country=self.brazil)

    def _post(self, name, body, *args):
        return self.client.post(
            reverse(name, args=args), data=json.dumps(body), content_type='application/json')

    def _body(self, **extra):
        body = {'kind': 'SUPPLY', 'what_id': self.soja.pk, 'quantity': 12, 'year': 2024,
                'from': f'company:{self.cargill.pk}', 'to': f'asset:{self.vevey.pk}'}
        body.update(extra)
        return body

    def _flow(self, what=None, modifiers=()):
        flow = make_supply(what=what or self.soja, year=2024, quantity=1,
                           origin=self.cargill, destination=self.vevey)
        flow.modifiers.set(modifiers)
        return flow

    def test_create_flow_with_modifiers(self):
        r = self._post('dashboard:flow_map_flow_create', self._body(
            modifier_ids=[self.certified.pk, self.bio.pk]))
        self.assertEqual(r.status_code, 201, r.content)
        flow = Flow.objects.get(pk=r.json()['id'])
        self.assertEqual(set(flow.modifiers.all()), {self.certified, self.bio})

    def test_modifier_of_other_commodity_rejected(self):
        r = self._post('dashboard:flow_map_flow_create', self._body(
            modifier_ids=[self.maize_bio.pk]))
        self.assertEqual(r.status_code, 400)
        self.assertIn('modifiers', r.json()['errors'])
        self.assertEqual(Flow.objects.count(), 0)

    def test_update_changing_commodity_without_modifier_ids_clears_them(self):
        flow = self._flow(modifiers=[self.certified])
        r = self._post('dashboard:flow_map_flow_update',
                       self._body(what_id=self.maize.pk), flow.pk)
        self.assertEqual(r.status_code, 200, r.content)
        flow.refresh_from_db()
        self.assertEqual(flow.what, self.maize)
        self.assertEqual(flow.modifiers.count(), 0)

    def test_update_without_modifier_ids_keeps_them_when_commodity_unchanged(self):
        flow = self._flow(modifiers=[self.certified])
        r = self._post('dashboard:flow_map_flow_update', self._body(quantity=7), flow.pk)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(list(flow.modifiers.all()), [self.certified])

    def test_update_with_explicit_modifier_ids(self):
        flow = self._flow(modifiers=[self.certified])
        r = self._post('dashboard:flow_map_flow_update',
                       self._body(modifier_ids=[self.bio.pk]), flow.pk)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(list(flow.modifiers.all()), [self.bio])
        r = self._post('dashboard:flow_map_flow_update', self._body(modifier_ids=[]), flow.pk)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(flow.modifiers.count(), 0)

    def test_serialized_flow_lists_modifiers(self):
        flow = self._flow(modifiers=[self.certified, self.bio])
        self.assertEqual(_serialize_flow(flow)['modifiers'], [
            {'id': self.bio.pk, 'name': 'Bio'},
            {'id': self.certified.pk, 'name': 'Certifié'},
        ])
        self.assertEqual(_serialize_flow(self._flow())['modifiers'], [])

    def test_flow_key_distinguishes_modifier_sets(self):
        acme = Company.objects.create(name='Acme')
        Ownership.objects.create(
            asset=self.vevey, company=acme, share=1, start_year=2015, end_year=None)
        plain = make_supply(what=self.soja, year=2024, quantity=1,
                            origin=self.mato, destination=self.vevey)
        certified = make_supply(what=self.soja, year=2024, quantity=1,
                                origin=self.mato, destination=self.vevey)
        certified.modifiers.set([self.certified])
        self.assertNotEqual(flow_key(plain), flow_key(certified))
        self.assertEqual(flow_years(acme, 2020, 2024, plain), [{'year': 2024, 'count': 1}])
        self.assertEqual(delete_flow_years(acme, 2020, 2024, plain, [2024]), 1)
        self.assertEqual(set(Flow.objects.values_list('pk', flat=True)), {certified.pk})

    def test_commodity_modifiers_endpoint(self):
        self.client.logout()
        r = self.client.get(reverse('dashboard:flow_map_commodity_modifiers',
                                    args=[self.soja.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'modifiers': [
            {'id': self.bio.pk, 'name': 'Bio'},
            {'id': self.certified.pk, 'name': 'Certifié'},
        ]})
        r = self.client.get(reverse('dashboard:flow_map_commodity_modifiers', args=[999999]))
        self.assertEqual(r.status_code, 404)
        self.assertIn('__all__', r.json()['errors'])


class MapApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.creator = user_model.objects.create_user('createur2', password='x', role='CREATOR')
        self.subscriber = user_model.objects.create_user(
            'abonne2', password='x', role='SUBSCRIBER')
        self.client.force_login(self.creator)
        self.acme = Company.objects.create(name='Acme')
        self.other = Company.objects.create(name='Other')
        self.cargill = Company.objects.create(name='Cargill')
        self.suisse = Country.objects.create(
            name='Suisse', water_ownership='Public', land_ownership='Private')
        self.soja = Commodity.objects.create(name='Soja', unit='t')
        self.vevey = Asset.objects.create(
            name='Usine Vevey', latitude=1.0, longitude=2.0, country=self.suisse)
        self.bale = Asset.objects.create(
            name='Usine Bâle', latitude=1.0, longitude=2.0, country=self.suisse)

    def _post(self, name, body, *args):
        return self.client.post(
            reverse(name, args=args), data=json.dumps(body), content_type='application/json')

    def _search(self, kind, q):
        return self.client.get(reverse('dashboard:flow_map_search'), {'type': kind, 'q': q})

    def test_search_assets_by_keyword(self):
        r = self._search('asset', 'vev')
        self.assertEqual(r.json()['results'],
                         [{'id': self.vevey.pk, 'name': 'Usine Vevey', 'detail': 'Suisse'}])

    def test_search_details_and_unknown_type(self):
        self.assertEqual(self._search('commodity', 'so').json()['results'],
                         [{'id': self.soja.pk, 'name': 'Soja', 'detail': 't'}])
        self.assertEqual(self._search('company', 'cargi').json()['results'][0]['detail'], '')
        self.assertEqual(self._search('country', 'sui').json()['results'][0]['detail'], '')
        region = SubnationalRegion.objects.create(name='Vaud', country=self.suisse)
        self.assertEqual(self._search('region', 'va').json()['results'],
                         [{'id': region.pk, 'name': 'Vaud', 'detail': 'Suisse'}])
        self.assertEqual(self._search('nope', 'abc').status_code, 400)

    def test_search_short_query_returns_nothing(self):
        self.assertEqual(self._search('asset', 'u').json(), {'results': []})

    def test_create_asset(self):
        r = self._post('dashboard:flow_map_asset_create', {
            'name': 'Nouveau', 'country': self.suisse.pk, 'type': 'Mine',
            'latitude': 46.4, 'longitude': 6.8})
        self.assertEqual(r.status_code, 201, r.content)
        asset = Asset.objects.get(pk=r.json()['id'])
        self.assertEqual((asset.name, asset.type), ('Nouveau', 'Mine'))

    def test_create_asset_rejects_latitude_out_of_range(self):
        before = Asset.objects.count()
        r = self._post('dashboard:flow_map_asset_create', {
            'name': 'X', 'country': self.suisse.pk, 'type': 'Mine',
            'latitude': 95, 'longitude': 6.8})
        self.assertEqual(r.status_code, 400)
        self.assertIn('latitude', r.json()['errors'])
        self.assertEqual(Asset.objects.count(), before)

    def test_create_company_with_name_only(self):
        r = self._post('dashboard:flow_map_company_create', {'name': 'Nestlé'})
        self.assertEqual(r.status_code, 201, r.content)
        company = Company.objects.get(pk=r.json()['id'])
        self.assertEqual((company.isin, company.ticker), ('0', '0'))

    def test_create_commodity_default_unit(self):
        r = self._post('dashboard:flow_map_commodity_create', {'name': 'Cacao'})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['unit'], 'tonnes')

    def test_create_ownership_starts_at_year(self):
        r = self._post('dashboard:flow_map_ownership_create', {
            'company_id': self.acme.pk, 'asset_id': self.vevey.pk, 'share': 0.5, 'year': 2024})
        self.assertEqual(r.status_code, 201, r.content)
        ownership = Ownership.objects.get(asset=self.vevey)
        self.assertEqual((ownership.start_year, ownership.end_year, ownership.created_by),
                         (2024, None, self.creator))

    def test_ownership_without_year_is_refused(self):
        for year in (None, 'x', 3000):
            body = {'company_id': self.acme.pk, 'asset_id': self.vevey.pk, 'share': 1}
            if year is not None:
                body['year'] = year
            r = self._post('dashboard:flow_map_ownership_create', body)
            self.assertEqual(r.status_code, 400)
            self.assertIn('start_year', r.json()['errors'])
        self.assertEqual(Ownership.objects.count(), 0)

    def test_search_requires_get(self):
        r = self.client.post(reverse('dashboard:flow_map_search'), {'type': 'asset', 'q': 'ab'})
        self.assertEqual(r.status_code, 405)

    def test_group_save_is_atomic_on_duplicate_member(self):
        from unittest import mock
        with mock.patch('dashboard.models.AssetGroup.set_members',
                        side_effect=IntegrityError('dup')):
            r = self._post('dashboard:flow_map_group_create',
                           {'name': 'B', 'members': [self.vevey.pk]}, self.acme.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn('members', r.json()['errors'])
        self.assertEqual(AssetGroup.objects.count(), 0)

    def test_ownership_over_full_share_is_refused(self):
        Ownership.objects.create(
            asset=self.vevey, company=self.other, share=1, start_year=2020)
        r = self._post('dashboard:flow_map_ownership_create', {
            'company_id': self.acme.pk, 'asset_id': self.vevey.pk, 'share': 1, 'year': 2024})
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()['errors'])
        self.assertEqual(Ownership.objects.count(), 1)

    def test_group_create_update_delete(self):
        r = self._post('dashboard:flow_map_group_create',
                       {'name': 'Suisse', 'members': [self.vevey.pk]}, self.acme.pk)
        self.assertEqual(r.status_code, 201, r.content)
        group = AssetGroup.objects.get(pk=r.json()['id'])
        self.assertEqual((group.company, group.created_by), (self.acme, self.creator))
        r = self._post('dashboard:flow_map_group_update',
                       {'name': 'CH', 'members': [self.bale.pk]}, group.pk)
        self.assertEqual(r.status_code, 200, r.content)
        group.refresh_from_db()
        self.assertEqual(group.name, 'CH')
        self.assertEqual(list(group.members.values_list('asset_id', flat=True)),
                         [self.bale.pk])
        r = self._post('dashboard:flow_map_group_delete', {}, group.pk)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(AssetGroup.objects.exists())
        self.assertEqual(
            self._post('dashboard:flow_map_group_delete', {}, group.pk).status_code, 404)
        self.assertEqual(
            self._post('dashboard:flow_map_group_update',
                       {'name': 'x', 'members': []}, group.pk).status_code, 404)

    def test_group_update_keeps_members_absent_from_displayed_map(self):
        # Vevey n'est plus détenu en 2024 : hors de la carte, mais toujours membre.
        Ownership.objects.create(asset=self.vevey, company=self.acme, share=1,
                                 start_year=2020, end_year=2022)
        Ownership.objects.create(asset=self.bale, company=self.acme, share=1,
                                 start_year=2020, end_year=None)
        group = AssetGroup.objects.create(name='Suisse', company=self.acme)
        group.set_members([self.vevey.pk, self.bale.pk])
        data = build_flow_map(self.acme, 2024, 2024, self.creator)
        self.assertEqual(data['groups'][0]['members'], [f'asset:{self.bale.pk}'])
        self.assertEqual(data['groups'][0]['all_members'],
                         [f'asset:{self.vevey.pk}', f'asset:{self.bale.pk}'])
        # Le JS renvoie les cases cochées plus les membres conservés hors carte.
        r = self._post('dashboard:flow_map_group_update',
                       {'name': 'CH', 'members': [self.bale.pk, self.vevey.pk]}, group.pk)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(sorted(group.members.values_list('asset_id', flat=True)),
                         sorted([self.vevey.pk, self.bale.pk]))

    def test_group_refuses_asset_of_another_group(self):
        first = AssetGroup.objects.create(name='A', company=self.acme)
        first.set_members([self.vevey.pk])
        r = self._post('dashboard:flow_map_group_create',
                       {'name': 'B', 'members': [self.vevey.pk]}, self.acme.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn('Usine Vevey', r.json()['errors']['members'][0])
        self.assertEqual(AssetGroup.objects.count(), 1)

    def _unlink_url(self, key, start=2020, end=2025):
        base = reverse('dashboard:flow_map_unlink', args=[self.acme.pk])
        return f'{base}?start={start}&end={end}&block={key}'

    def _unlink(self, key, body, **range_):
        return self.client.post(
            self._unlink_url(key, **range_), data=json.dumps(body),
            content_type='application/json')

    def test_unlink_preview_then_unlink(self):
        Ownership.objects.create(asset=self.vevey, company=self.acme, share=1, start_year=2020)
        make_supply(what=self.soja, year=2024, quantity=5,
                    origin=self.cargill, destination=self.vevey)
        key = f'company:{self.cargill.pk}'
        r = self.client.get(self._unlink_url(key))
        self.assertEqual(r.json(), {
            'years': [{'year': 2024, 'flows': 1}], 'ownership': False,
            'ownership_year': None, 'co_owners': []})
        self.assertEqual(Flow.objects.count(), 1)
        r = self._unlink(key, {'years': [2024], 'ownership_year': None})
        self.assertEqual(r.json(), {'flows': 1, 'ownership': False})
        self.assertEqual(Flow.objects.count(), 0)

    def test_unlink_with_years_and_ownership_year(self):
        Ownership.objects.create(asset=self.vevey, company=self.acme, share=1, start_year=2020)
        for year in (2022, 2023, 2024):
            make_supply(what=self.soja, year=year, quantity=5,
                        origin=self.cargill, destination=self.vevey)
        key = f'asset:{self.vevey.pk}'
        r = self._unlink(key, {'years': [2022, 2024], 'ownership_year': 2023})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'flows': 2, 'ownership': True})
        self.assertEqual(list(Flow.objects.values_list('year', flat=True)), [2023])
        ownership = Ownership.objects.get(asset=self.vevey, company=self.acme)
        self.assertEqual(ownership.end_year, 2022)

    def test_unlink_with_nothing_selected_is_refused(self):
        Ownership.objects.create(asset=self.vevey, company=self.acme, share=1, start_year=2020)
        make_supply(what=self.soja, year=2024, quantity=5,
                    origin=self.cargill, destination=self.vevey)
        for body in ({}, {'years': [], 'ownership_year': None}):
            r = self._unlink(f'asset:{self.vevey.pk}', body)
            self.assertEqual(r.status_code, 400)
        self.assertEqual(Flow.objects.count(), 1)
        self.assertIsNone(Ownership.objects.get(asset=self.vevey).end_year)

    def test_unlink_rejects_untyped_years(self):
        make_supply(what=self.soja, year=2024, quantity=5,
                    origin=self.cargill, destination=self.vevey)
        key = f'company:{self.cargill.pk}'
        for body in ({'years': ['2024']}, {'years': [True]}, {'years': 2024},
                     {'years': [2024.5]}, {'years': [2024], 'ownership_year': '2024'},
                     {'years': [2024], 'ownership_year': 2024.0},
                     {'years': [2024], 'ownership_year': False}):
            with self.subTest(body=body):
                r = self._unlink(key, body)
                self.assertEqual(r.status_code, 400)
                self.assertTrue({'years', 'ownership_year'} & set(r.json()['errors']))
        r = self._unlink(key, {'years': [2030]})
        self.assertEqual(r.status_code, 400)
        r = self.client.post(self._unlink_url(key), data='x', content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Flow.objects.count(), 1)

    def test_unlink_bad_input(self):
        url = reverse('dashboard:flow_map_unlink', args=[self.acme.pk])
        for start, end in (('99999999999999999999', 2024), (1800, 2024), (2020, 2101),
                           ('x', 2024), (2024, 2020), (2020, None)):
            params = {'start': start, 'block': 'company:1'}
            if end is not None:
                params['end'] = end
            self.assertEqual(self.client.get(url, params).status_code, 400)
            self.assertEqual(
                self.client.post(url + '?' + urlencode(params), data='{}',
                                 content_type='application/json').status_code, 400)
        self.assertEqual(self.client.get(url, {'block': 'company:1'}).status_code, 400)
        self.assertEqual(self.client.get(
            url, {'start': 2024, 'end': 2024, 'block': 'environment'}).status_code, 400)
        self.assertEqual(self._unlink('environment', {'years': [2024]}).status_code, 400)

    def test_writes_refused_for_subscriber(self):
        self.client.force_login(self.subscriber)
        calls = [
            ('dashboard:flow_map_asset_create', ()),
            ('dashboard:flow_map_company_create', ()),
            ('dashboard:flow_map_commodity_create', ()),
            ('dashboard:flow_map_ownership_create', ()),
            ('dashboard:flow_map_group_create', (self.acme.pk,)),
            ('dashboard:flow_map_group_update', (1,)),
            ('dashboard:flow_map_group_delete', (1,)),
        ]
        for name, args in calls:
            with self.subTest(name=name):
                self.assertEqual(self._post(name, {}, *args).status_code, 403)
        url = reverse('dashboard:flow_map_unlink', args=[self.acme.pk])
        r = self.client.post(url + '?start=2024&end=2024&block=company:1', data='{}',
                             content_type='application/json')
        self.assertEqual(r.status_code, 403)


class FlowMapPageTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.cargill = Company.objects.create(name='Cargill')
        self.soja = Commodity.objects.create(name='Soja', unit='t')
        for year in (2023, 2024):
            make_supply(what=self.soja, year=year, quantity=5,
                        origin=self.cargill, destination=self.acme)

    def test_page_renders_with_initial_data(self):
        r = self.client.get(reverse('dashboard:flow_map'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="flow-rules"')
        self.assertContains(r, 'flow_map.js')
        self.assertEqual(r.context['companies'][0], {'id': self.acme.pk, 'name': 'Acme'})
        self.assertEqual(r.context['initial_data']['company']['id'], self.acme.pk)
        self.assertEqual(r.context['initial_data']['start'], 2023)
        self.assertEqual(r.context['initial_data']['end'], 2024)
        self.assertFalse(r.context['can_edit'])

    def test_page_context_rules_and_kinds(self):
        r = self.client.get(reverse('dashboard:flow_map'))
        rules = r.context['flow_rules']
        self.assertEqual(set(rules), set(FLOW_RULES))
        self.assertEqual(rules['PRODUCTION'], {
            'origins': ['asset', 'company'], 'destinations': [None]})
        self.assertIn(None, rules['CONSUMPTION']['origins'])
        json.dumps(rules)
        kinds = r.context['kinds']
        self.assertEqual([k['value'] for k in kinds], list(FlowKind.values))
        self.assertTrue(all(isinstance(k['label'], str) for k in kinds))
        self.assertContains(r, '"destinations": [null]')
        scopes = r.context['scopes']
        self.assertEqual([s['value'] for s in scopes], list(Flow.Scope.values))
        self.assertNotContains(r, 'id="flow-map-panel"')
        self.assertNotContains(r, 'id="flow-map-block-panel"')
        self.assertNotContains(r, 'data-add=')

    def test_page_can_edit_for_creator(self):
        User = get_user_model()
        self.client.force_login(User.objects.create_user('c', password='pw', role='CREATOR'))
        r = self.client.get(reverse('dashboard:flow_map'))
        self.assertTrue(r.context['can_edit'])
        self.assertContains(r, 'id="flow-map-panel"')
        self.assertContains(r, 'id="flow-map-confirm"')
        self.assertContains(r, '<option value="undefined">')
        self.assertContains(r, 'id="flow-map-block-panel"')
        self.assertContains(r, 'data-add="asset"')
        self.assertRegex(r.content.decode(), r'<option value="Factory"\s+selected>')
        self.assertContains(r, 'flow_map_blocks.js')
        self.assertIn({'value': 'Mine', 'label': 'Mine'}, r.context['asset_types'])

    def test_panel_renders_modifier_fieldset(self):
        User = get_user_model()
        self.client.force_login(User.objects.create_user('c', password='pw', role='CREATOR'))
        r = self.client.get(reverse('dashboard:flow_map'))
        self.assertContains(r, 'id="fm-modifiers"')
        self.assertContains(r, 'id="fm-modifiers-list"')
        self.assertContains(r, 'id="fm-modifiers-note"')
        self.assertContains(
            r, reverse('dashboard:flow_map_commodity_modifiers', args=[0]))

    def test_page_without_company(self):
        Flow.objects.all().delete()
        Company.objects.all().delete()
        r = self.client.get(reverse('dashboard:flow_map'))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context['initial_data'])
        self.assertEqual(r.context['companies'], [])

    def test_data_uses_range(self):
        r = self.client.get(reverse('dashboard:flow_map_data', args=[self.acme.pk]),
                            {'start': 2020, 'end': 2024})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual((data['start'], data['end']), (2020, 2024))
        self.assertEqual(data['company'], {'id': self.acme.pk, 'name': 'Acme'})
        self.assertNotIn('year', data)

    def test_data_default_range(self):
        data = self.client.get(reverse('dashboard:flow_map_data', args=[self.acme.pk])).json()
        self.assertEqual((data['start'], data['end']), (2023, 2024))

    def test_data_rejects_inverted_range(self):
        r = self.client.get(reverse('dashboard:flow_map_data', args=[self.acme.pk]),
                            {'start': 2024, 'end': 2023})
        self.assertEqual(r.status_code, 400)
        self.assertIn('end', r.json()['errors'])

    def test_data_rejects_single_bound(self):
        url = reverse('dashboard:flow_map_data', args=[self.acme.pk])
        r = self.client.get(url, {'start': 2023})
        self.assertEqual(r.status_code, 400)
        self.assertIn('end', r.json()['errors'])
        r = self.client.get(url, {'end': 2023})
        self.assertEqual(r.status_code, 400)
        self.assertIn('start', r.json()['errors'])

    def test_data_rejects_bad_bounds(self):
        url = reverse('dashboard:flow_map_data', args=[self.acme.pk])
        for params in ({'start': 'abc', 'end': 2024}, {'start': 1800, 'end': 2024},
                       {'start': 2020, 'end': '99999999999999999999'}):
            with self.subTest(params=params):
                r = self.client.get(url, params)
                self.assertEqual(r.status_code, 400)
                self.assertTrue({'start', 'end'} & set(r.json()['errors']))

    def test_block_endpoint_is_public(self):
        brazil = Country.objects.create(
            name='Pérou', water_ownership='Public', land_ownership='Private')
        self.client.logout()
        r = self.client.get(reverse('dashboard:flow_map_block'), {'key': f'country:{brazil.pk}'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['name'], 'Pérou')

    def test_block_endpoint_errors(self):
        url = reverse('dashboard:flow_map_block')
        self.assertEqual(self.client.get(url).status_code, 400)
        self.assertEqual(self.client.get(url, {'key': 'market'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'key': 'asset:999999'}).status_code, 404)

    def test_data_endpoint_unknown_company(self):
        r = self.client.get(reverse('dashboard:flow_map_data', args=[999999]))
        self.assertEqual(r.status_code, 404)

    def test_sidebar_links_to_flow_map(self):
        r = self.client.get(reverse('dashboard:index'))
        self.assertContains(r, reverse('dashboard:flow_map'))
