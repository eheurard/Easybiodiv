"""Suppression des comptes inactifs, durée annoncée par la politique de confidentialité."""
import datetime

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from authentication.models import User

# Durée sans connexion au-delà de laquelle un compte utilisateur est supprimé
# (recommandation CNIL ; reprise par legal/templates/legal/*/confidentialite.html).
INACTIVITY = datetime.timedelta(days=3 * 365)


def inactive_accounts(now=None):
    """Comptes abonnés sans connexion depuis INACTIVITY.

    Un compte jamais connecté est jugé sur sa date d'inscription. Les comptes
    contributeurs (CREATOR), staff et superutilisateurs sont exclus : leur nom
    signe les données saisies (`created_by`), traçabilité exigée par la CSRD.
    """
    cutoff = (now or timezone.now()) - INACTIVITY
    return (
        User.objects
        .filter(role=User.SUBSCRIBER, is_staff=False, is_superuser=False)
        .annotate(last_seen=Coalesce('last_login', 'date_joined'))
        .filter(Q(last_seen__lt=cutoff))
    )


class Command(BaseCommand):
    help = (
        'Supprime les comptes abonnés sans connexion depuis 3 ans, avec leur photo de '
        'profil. À planifier en tâche cron (docs/deploiement-production.md).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Liste les comptes concernés sans rien supprimer.')

    def handle(self, *args, **options):
        accounts = list(inactive_accounts())
        if options['dry_run']:
            for user in accounts:
                self.stdout.write(
                    f'{user.username} (dernière activité {user.last_seen:%Y-%m-%d})')
            self.stdout.write(f'{len(accounts)} compte(s) seraient supprimé(s).')
            return
        for user in accounts:
            if user.profile_photo:
                user.profile_photo.delete(save=False)
            user.delete()
        self.stdout.write(f'{len(accounts)} compte(s) inactif(s) supprimé(s).')
