from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    CREATOR = 'CREATOR'
    SUBSCRIBER = 'SUBSCRIBER'

    ROLE_CHOICES = (
        (CREATOR, 'Créateur'),
        (SUBSCRIBER, 'Abonné'),
    )

    profile_photo = models.ImageField(
        verbose_name='Photo de profil',
        blank=True,
        null=True,
    )
    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default=SUBSCRIBER,
        verbose_name='Rôle',
    )
    # Preuve de l'acceptation des CGU à l'inscription (null : compte créé avant
    # leur mise en place, ou par un administrateur).
    terms_accepted_at = models.DateTimeField(
        verbose_name="Date d'acceptation des CGU",
        null=True,
        blank=True,
    )
