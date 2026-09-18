"""Détention actif ↔ entreprise (spec 2026-09-18 §3.6)."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from .models import Asset, Company, Country, Ownership, periods_overlap, share_overflow_year


def _country():
    return Country.objects.create(
        name='France', water_ownership='Public', land_ownership='Private')


def _asset(name, country):
    return Asset.objects.create(name=name, latitude=1.0, longitude=2.0, country=country)


class OwnershipModelTests(TestCase):

    def setUp(self):
        self.asset = _asset('Site', _country())
        self.company = Company.objects.create(name='Acme')

    def test_share_is_stored_as_decimal(self):
        o = Ownership.objects.create(asset=self.asset, company=self.company, share='0.75')
        o.refresh_from_db()
        self.assertEqual(o.share, Decimal('0.7500'))

    def test_share_label_matches_the_legacy_display(self):
        cases = [('1', '100%'), ('0.75', '75%'), ('0.6', '60%'), ('0.3333', '33.33%')]
        for share, label in cases:
            with self.subTest(share=share):
                o = Ownership(asset=self.asset, company=self.company, share=Decimal(share))
                self.assertEqual(o.share_label, label)

    def test_share_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ownership.objects.create(asset=self.asset, company=self.company, share=0)

    def test_share_cannot_exceed_one(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ownership.objects.create(asset=self.asset, company=self.company, share='1.5')

    def test_start_year_cannot_follow_end_year(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ownership.objects.create(
                asset=self.asset, company=self.company, share=1,
                start_year=2025, end_year=2024,
            )

    def test_str(self):
        o = Ownership.objects.create(asset=self.asset, company=self.company, share=1)
        self.assertEqual(str(o), 'Site - Acme')


class OwnedByTests(TestCase):

    def setUp(self):
        self.country = _country()
        self.company = Company.objects.create(name='Acme')

    def _held(self, name, **years):
        asset = _asset(name, self.country)
        Ownership.objects.create(asset=asset, company=self.company, share=1, **years)
        return asset

    def test_without_year_returns_current_holdings(self):
        current = self._held('Actuel')
        self._held('Cédé', end_year=2023)
        self.assertEqual(list(Asset.objects.owned_by(self.company)), [current])

    def test_with_year_applies_the_validity_period(self):
        always = self._held('Toujours')
        sold = self._held('Cédé', end_year=2023)
        bought = self._held('Acquis', start_year=2024)
        self.assertEqual(list(Asset.objects.owned_by(self.company, 2023)), [always, sold])
        self.assertEqual(list(Asset.objects.owned_by(self.company, 2024)), [always, bought])

    def test_other_companies_are_ignored(self):
        other = Company.objects.create(name='Autre')
        Ownership.objects.create(asset=_asset('Voisin', self.country), company=other, share=1)
        self.assertEqual(list(Asset.objects.owned_by(self.company)), [])

    def test_two_periods_do_not_duplicate_the_asset(self):
        asset = _asset('Deux périodes', self.country)
        Ownership.objects.create(asset=asset, company=self.company, share='0.5', end_year=2022)
        Ownership.objects.create(
            asset=asset, company=self.company, share='0.75', start_year=2023)
        self.assertEqual(list(Asset.objects.owned_by(self.company, 2024)), [asset])
        self.assertEqual(list(Asset.objects.owned_by(self.company)), [asset])


class OwnershipPeriodHelpersTests(SimpleTestCase):

    def test_periods_overlap(self):
        self.assertTrue(periods_overlap((None, 2023), (2023, None)))
        self.assertFalse(periods_overlap((None, 2023), (2024, None)))
        self.assertTrue(periods_overlap((None, None), (2010, 2012)))

    def test_share_overflow_year(self):
        half = Decimal('0.5')
        self.assertIsNone(share_overflow_year([(half, None, None), (half, None, None)]))
        self.assertEqual(
            share_overflow_year([(Decimal('0.6'), 2020, None), (half, 2022, 2025)]), 2022)


class OwnershipCleanTests(TestCase):

    def setUp(self):
        self.asset = _asset('Site', _country())
        self.acme = Company.objects.create(name='Acme')
        self.other = Company.objects.create(name='Autre')

    def _clean(self, **fields):
        Ownership(asset=self.asset, **fields).full_clean()

    def test_overlapping_periods_for_the_same_company_are_rejected(self):
        Ownership.objects.create(
            asset=self.asset, company=self.acme, share='0.5', end_year=2023)
        with self.assertRaisesMessage(ValidationError, 'chevauche'):
            self._clean(company=self.acme, share='0.5', start_year=2023)

    def test_consecutive_periods_are_accepted(self):
        Ownership.objects.create(
            asset=self.asset, company=self.acme, share='0.5', end_year=2023)
        self._clean(company=self.acme, share='0.75', start_year=2024)

    def test_total_share_above_one_is_rejected_with_its_year(self):
        Ownership.objects.create(
            asset=self.asset, company=self.acme, share='0.6', start_year=2020)
        with self.assertRaisesMessage(ValidationError, 'dépasse 100 % en 2022'):
            self._clean(company=self.other, share='0.5', start_year=2022)

    def test_total_share_of_exactly_one_is_accepted(self):
        Ownership.objects.create(asset=self.asset, company=self.acme, share='0.6')
        self._clean(company=self.other, share='0.4')

    def test_sale_then_purchase_does_not_add_up(self):
        Ownership.objects.create(asset=self.asset, company=self.acme, share=1, end_year=2023)
        self._clean(company=self.other, share=1, start_year=2024)
