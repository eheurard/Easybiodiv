import operator
from collections import namedtuple
from decimal import Decimal, InvalidOperation
from functools import reduce

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

UNDOCUMENTED_SCALE_HELP_TEXT = (
    'Échelle et unité non documentées à ce jour — vérifier le glossaire '
    'métier avant de saisir une valeur.'
)

KEY_HELP_TEXT = (
    'Identifiant technique repris tel quel dans les clés JSON des vues. '
    'Ne pas modifier sur un enregistrement existant sans vérifier les '
    'vues qui le consomment.'
)

THEME_HELP_TEXT = (
    'Clé d’appariement entre mesure et modèle : un inventaire d’actif '
    'est comparé aux catégories d’impact qui portent le même thème.'
)


class Country(models.Model):
    name = models.CharField(max_length=255, verbose_name='Nom')
    water_ownership = models.CharField(
        max_length=255,
        choices=[('Public','Public'),('Private','Privée'),('Public Private partnership',"Partenariat public privé")],
        verbose_name="Régime de propriété de l'eau",
    )
    land_ownership = models.CharField(
        max_length=255, verbose_name='Régime de propriété foncière à définir',
    )
    water_Governance = models.TextField(
        blank=True, verbose_name="Gouvernance de l'eau",
    )
    land_Governance = models.TextField(
        blank=True, verbose_name='Gouvernance foncière',
    )
    restoration_cost_m2 = models.FloatField(
        default=0, verbose_name='Coût de restauration (par m²)',
        help_text="En € / m² issu des études locales ou des projets de développement du pays",
    )
    restoration_cost_source = models.CharField(
        blank=True,
        choices=[('Country budget allocation','State'),('Scientific studies','Scientific')],
        verbose_name='origine de la donnée du cout de restauration'
    )
    biodiversity_loss_agriculture = models.FloatField(
        default=0, verbose_name='Perte de biodiversité — agriculture',
        help_text="En % par rapport à une unité de référence(i.e MSA agricole par rapport à état de référence)",
    )
    biodiversity_loss_urbanization = models.FloatField(
        default=0, verbose_name='Perte de biodiversité — urbanisation',
        help_text="En % par rapport à une unité de référence(i.e zone urbaine dense par rapport à état de référence)",
    )
    biodiversity_loss_mining = models.FloatField(
        default=0, verbose_name='Perte de biodiversité — extraction minière',
        help_text="En % par rapport à une unité de référence(i.e zone minière par rapport à état de référence)",
    )

    class Meta:
        verbose_name = 'Pays'
        verbose_name_plural = 'Pays'

    def __str__(self):
        return self.name


class SubnationalRegion(models.Model):
    name = models.CharField(max_length=255, verbose_name='Nom')
    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, verbose_name='Pays',
    )
    restoration_cost_m2 = models.FloatField(
        default=0, verbose_name='Coût de restauration (par m²)',
    )
    Mean_X = models.FloatField(
        default=0, verbose_name='Coordonnée X moyenne',
        help_text="Coordonnée utilisé pour la projection en carte",
    )
    Mean_Y = models.FloatField(
        default=0, verbose_name='Coordonnée Y moyenne',
        help_text='Coordonnée utilisé pour la projection en carte',
    )

    class Meta:
        verbose_name = 'Région infranationale'
        verbose_name_plural = 'Régions infranationales'

    def __str__(self):
        return self.name

# Commodités techniques lues par le code (clés JSON des vues, inventaire mesuré,
# émissions déclarées) : key -> (name, unit, theme). La migration
# 0050_seed_technical_commodities en garde une copie figée.
TECHNICAL_COMMODITIES = {
    'water': ('Eau', 'm³', 'water'),
    'energy': ('Énergie', 'MWh', 'energy'),
    'co2': ('CO₂', 'tCO₂e', 'carbon'),
    'waste': ('Déchets', 't', 'waste'),
    'surface_area': ('Surface occupée', 'm²', 'land'),
}


class CommodityQuerySet(models.QuerySet):

    def technical(self, key):
        """Commodité technique `key`, recréée si elle manque (base vidée par un
        test transactionnel, ou ligne supprimée à la main)."""
        name, unit, theme = TECHNICAL_COMMODITIES[key]
        commodity, _ = self.get_or_create(
            key=key, defaults={'name': name, 'unit': unit, 'theme': theme},
        )
        return commodity


class Commodity (models.Model):
    DEPENDENCY_CHOICES = [
        ('VL', 'Very low'),
        ('L', 'Low'),
        ('M', 'Medium'),
        ('H', 'High'),
        ('VH', 'Very High'),
    ]
    DEPENDENCY_HELP_TEXT = (
        'Niveau de dépendance à ce service écosystémique. Converti en '
        'score de calcul : très faible 0 · faible 0,2 · moyen 0,5 · '
        'fort 0,7 · très fort 1.'
    )
    name = models.CharField(max_length=255, verbose_name='Nom')
    description = models.TextField(blank=True, verbose_name='Description')
    unit = models.CharField(
        max_length=255, default="tonnes", verbose_name='Unité de mesure',
        help_text='Unité dans laquelle les productions et les échanges de cette '
                  'commodité sont exprimés (par défaut : tonnes).',
    )
    key = models.CharField(
        max_length=50, unique=True, null=True, blank=True,
        verbose_name='Clé technique', help_text=KEY_HELP_TEXT,
    )
    theme = models.CharField(
        max_length=30, blank=True, default='', verbose_name='Thème',
        help_text=THEME_HELP_TEXT,
    )

    dependency_water = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name='Dépendance — approvisionnement en eau',
        help_text=DEPENDENCY_HELP_TEXT,
    )
    dependency_pollination = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name='Dépendance — pollinisation',
        help_text=DEPENDENCY_HELP_TEXT,
    )
    dependency_soil_quality = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name='Dépendance — qualité des sols',
        help_text=DEPENDENCY_HELP_TEXT,
    )
    dependency_carbon_sequestration = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name='Dépendance — séquestration carbone',
        help_text=DEPENDENCY_HELP_TEXT,
    )
    dependency_water_purification = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name="Dépendance — épuration de l'eau",
        help_text=DEPENDENCY_HELP_TEXT,
    )
    dependency_pest_control = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name='Dépendance — contrôle des ravageurs',
        help_text=DEPENDENCY_HELP_TEXT,
    )

    biodiversity_loss_class = models.CharField(
        choices=[
            ('Agriculture', 'Agriculture'),
            ('Urbanisation', 'Urbanisation'),
            ('Mining', 'Mining'),
        ],
        default="Agriculture",
        verbose_name='Classe de perte de biodiversité pour le calcul de dette biodiversité',
        help_text='Détermine lequel des trois taux de perte du pays s’applique : '
                  'agriculture, urbanisation ou extraction minière.',
    )

    objects = CommodityQuerySet.as_manager()

    class Meta:
        verbose_name = 'Commodité'
        verbose_name_plural = 'Commodités'

    def __str__(self):
        return self.name

class Sector(models.Model):
    name = models.CharField(max_length=255, verbose_name='Nom')
    NACE_code = models.CharField(
        max_length=255, blank=True, null=True, verbose_name='Code NACE',
    )

    class Meta:
        verbose_name = 'Secteur'
        verbose_name_plural = 'Secteurs'

    def __str__(self):
        return self.name

class SubSector(models.Model):
    DEPENDENCY_CHOICES = [
        ('VL', 'Very low'),
        ('L', 'Low'),
        ('M', 'Medium'),
        ('H', 'High'),
        ('VH', 'Very High'),
    ]
    name = models.CharField(max_length=255, verbose_name='Nom')
    sector = models.ForeignKey(
        Sector, on_delete=models.CASCADE, verbose_name='Secteur',
    )
    NACE_code = models.CharField(
        max_length=255, blank=True, null=True, verbose_name='Code NACE',
    )
    Water_dependency = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name='Dépendance — approvisionnement en eau',
        help_text=Commodity.DEPENDENCY_HELP_TEXT,
    )
    Pollination_dependency = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name='Dépendance — pollinisation',
        help_text=Commodity.DEPENDENCY_HELP_TEXT,
    )
    Soil_quality_dependency = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name='Dépendance — qualité des sols',
        help_text=Commodity.DEPENDENCY_HELP_TEXT,
    )
    Carbon_Sequestration = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name='Dépendance — séquestration carbone',
        help_text=Commodity.DEPENDENCY_HELP_TEXT,
    )
    Water_purification_dependency = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name="Dépendance — épuration de l'eau",
        help_text=Commodity.DEPENDENCY_HELP_TEXT,
    )
    Pest_control_dependency = models.CharField(
        max_length=2, choices=DEPENDENCY_CHOICES, default='VL',
        verbose_name='Dépendance — contrôle des ravageurs',
        help_text=Commodity.DEPENDENCY_HELP_TEXT,
    )

    class Meta:
        verbose_name = 'Sous-secteur'
        verbose_name_plural = 'Sous-secteurs'

    def __str__(self):
        return self.name

class AssetQuerySet(models.QuerySet):

    def owned_by(self, company, year=None):
        """Actifs détenus par `company` l'année `year` ; sans année, périmètre
        actuel (spec §3.6). Trié par pk pour un ordre stable."""
        held = Ownership.objects.valid_in(year).filter(company=company).values('asset_id')
        return self.filter(pk__in=held).order_by('pk')


class Asset(models.Model):


    name = models.CharField(max_length=255, verbose_name='Nom')
    description = models.TextField(blank=True, verbose_name='Description')
    latitude = models.FloatField(verbose_name='Latitude')
    longitude = models.FloatField(verbose_name='Longitude')
    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, verbose_name='Pays',
    )
    subnational_region = models.ForeignKey(
        SubnationalRegion, on_delete=models.CASCADE, null=True, blank=True,
        verbose_name='Région infranationale',
    )
    type = models.CharField(
        max_length=255,
        choices=[
            ('Airport', 'Airport'),
            ('Mine', 'Mine'),
            ('Aluminium', 'Aluminium'),
            ('Factory', 'Factory'),
            ('Forest', 'Forest'),
            ('Office', 'Office'),
            ('Paper', 'Paper'),
            ('Refinery', 'Refinery'),
            ('Renewable', 'Renewable'),
            ('Smelter', 'Smelter'),
        ],
        default='Factory',
        verbose_name='Type de site',
    )

    risk_water = models.FloatField(
        default=0, verbose_name='Risque — approvisionnement en eau',
        help_text='Risque eau du WRI de 0 a 5',
    )
    risk_pollination = models.FloatField(
        default=0, verbose_name='Risque — pollinisation',
        help_text='A définir',
    )
    risk_soil_quality = models.FloatField(
        default=0, verbose_name='Risque — qualité des sols',
        help_text='A définir, check WWF',
    )
    risk_carbon_sequestration = models.FloatField(
        default=0, verbose_name='Risque — séquestration carbone',
        help_text='A définir',
    )
    risk_water_purification = models.FloatField(
        default=0, verbose_name="Risque — épuration de l'eau",
        help_text='A définir',
    )
    risk_pest_control = models.FloatField(
        default=0, verbose_name='Risque — contrôle des ravageurs',
        help_text='A définir',
    )
    risk_water_stress = models.FloatField(
        default=0, verbose_name='Aléa — stress hydrique',
        help_text='WRI water stress score de 0 a 5',
    )
    risk_wildfire = models.FloatField(
        default=0, verbose_name='Aléa — feu de forêt',
        help_text='A définir',
    )
    risk_cyclone = models.FloatField(
        default=0, verbose_name='Aléa — cyclone',
        help_text='A définir',
    )
    risk_drought = models.FloatField(
        default=0, verbose_name='Aléa — sécheresse',
        help_text='WRI drought score de 0 à 5',
    )
    risk_flood = models.FloatField(
        default=0, verbose_name='Aléa — inondation',
        help_text='WRI flood score de 0 à 5',
    )
    risk_coastal_inundation = models.FloatField(
        default=0, verbose_name='Aléa — submersion côtière',
        help_text='WRI coastal inondation score de 0 à 5',
    )
    risk_heatwave = models.FloatField(
        default=0, verbose_name='Aléa — canicule',
        help_text='A définir',
    )
    risk_temperature_variation = models.FloatField(
        default=0, verbose_name='Aléa — variation de température',
        help_text='A définir',
    )
    risk_precipitation_variation = models.FloatField(
        default=0, verbose_name='Aléa — variation des précipitations',
        help_text='A définir',
    )

    class SensitiveZoneType(models.TextChoices):
        NATURA_2000 = 'NATURA_2000', 'Natura 2000'
        NATIONAL_PROTECTED = 'NATIONAL_PROTECTED', 'Aire protégée nationale'
        UNESCO = 'UNESCO', 'Site UNESCO'
        IUCN_KBA = 'IUCN_KBA', 'IUCN Key Biodiversity Area'
        OTHER = 'OTHER', 'Autre'

    SENSITIVE_ZONE_HELP_TEXT = (
        'Renseigné seulement si « Proche d’une zone sensible » est coché.'
    )

    near_sensitive_zone = models.BooleanField(
        default=False, verbose_name="Proche d'une zone sensible",
    )
    sensitive_zone_type = models.CharField(
        max_length=20, choices=SensitiveZoneType.choices, blank=True,
        verbose_name='Type de zone sensible', help_text=SENSITIVE_ZONE_HELP_TEXT,
    )
    sensitive_zone_name = models.CharField(
        max_length=255, blank=True, verbose_name='Nom de la zone sensible',
        help_text=SENSITIVE_ZONE_HELP_TEXT,
    )
    sensitive_zone_area_ha = models.FloatField(
        default=0, verbose_name='Surface de la zone sensible (ha)',
        help_text=SENSITIVE_ZONE_HELP_TEXT,
    )

    objects = AssetQuerySet.as_manager()

    class Meta:
        verbose_name = 'Actif'
        verbose_name_plural = 'Actifs'

    def __str__(self):
        return self.name

class Company (models.Model):
    name = models.CharField(max_length=255, verbose_name='Nom')
    description = models.TextField(blank=True, verbose_name='Description')
    isin = models.CharField(max_length=255, default="0", verbose_name='Code ISIN')
    ticker = models.CharField(max_length=255, default="0", verbose_name='Ticker boursier')

    class Meta:
        verbose_name = 'Entreprise'
        verbose_name_plural = 'Entreprises'

    def __str__(self):
        return self.name

TIER_HELP_TEXT = (
    'Position dans la chaîne : 0 opérations directes · 1 chaîne '
    'd’approvisionnement · 2 approvisionnement amont · 3 matières '
    'premières.'
)


class Company_Revenue(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, verbose_name='Entreprise',
    )
    year = models.IntegerField(verbose_name='Exercice')
    revenue = models.FloatField(verbose_name="Chiffre d'affaires")
    evic = models.FloatField(
        default=0.0, verbose_name='EVIC',
        help_text="Enterprise Value Including Cash — dénominateur de l'impact financé.",
    )
    ebitda = models.FloatField(default=0.0, verbose_name='EBITDA')
    currency = models.CharField(max_length=255, verbose_name='Devise')

    class Meta:
        verbose_name = "Chiffre d'affaires"
        verbose_name_plural = "Chiffres d'affaires"

    def __str__(self):
        return str(self.company.name) + " - " + str(self.year)

class Company_Revenue_Sector(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, verbose_name='Entreprise',
    )
    subsector = models.ForeignKey(
        SubSector, on_delete=models.CASCADE, verbose_name='Sous-secteur',
    )
    year = models.IntegerField(verbose_name='Exercice')
    revenue = models.FloatField(verbose_name="Chiffre d'affaires")

    class Meta:
        verbose_name = 'CA par sous-secteur'
        verbose_name_plural = 'CA par sous-secteur'

    def __str__(self):
        return str(self.company.name) + " - " + str(self.subsector.sector.name) + " - " + str(self.subsector.name) + " - " + str(self.year)

class Policy_Type(models.Model):
    name = models.CharField(max_length=255, verbose_name='Nom')
    description = models.TextField(blank=True, verbose_name='Description')

    class Meta:
        verbose_name = 'Type de politique'
        verbose_name_plural = 'Types de politique'

    def __str__(self):
        return self.name

class Policy_Subcategory(models.Model):
    policy_type = models.ForeignKey(
        Policy_Type, on_delete=models.CASCADE, verbose_name='Type de politique',
    )
    name = models.CharField(max_length=255, verbose_name='Nom')
    description = models.TextField(blank=True, verbose_name='Description')

    class Meta:
        verbose_name = 'Sous-catégorie de politique'
        verbose_name_plural = 'Sous-catégories de politique'

    def __str__(self):
        return str(self.policy_type.name) + " - " + str(self.name)

class Policy_Level(models.Model):
    subcategory = models.ForeignKey(
        Policy_Subcategory, on_delete=models.CASCADE, verbose_name='Sous-catégorie',
    )
    name = models.CharField(max_length=255, verbose_name='Nom')
    score = models.FloatField(
        null=True, blank=True, verbose_name='Score',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    description = models.TextField(blank=True, verbose_name='Description')
    vulnerability_water = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — approvisionnement en eau',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_pollination = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — pollinisation',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_soil_quality = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — qualité des sols',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_carbon_sequestration = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — séquestration carbone',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_water_purification = models.FloatField(
        default=1.0, verbose_name="Vulnérabilité — épuration de l'eau",
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_pest_control = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — contrôle des ravageurs',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_water_stress = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — stress hydrique',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_wildfire = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — feu de forêt',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_cyclone = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — cyclone',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_drought = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — sécheresse',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_flood = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — inondation',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_coastal_inundation = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — submersion côtière',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_heatwave = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — canicule',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_temperature_variation = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — variation de température',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    vulnerability_precipitation_variation = models.FloatField(
        default=1.0, verbose_name='Vulnérabilité — variation des précipitations',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )

    class Meta:
        verbose_name = 'Niveau de politique'
        verbose_name_plural = 'Niveaux de politique'

    def __str__(self):
        return str(self.subcategory.policy_type.name) + " - " + str(self.subcategory.name) + " - " + str(self.name)

class Company_Policy(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name='Entreprise')
    policy_level = models.ForeignKey(
        Policy_Level, on_delete=models.CASCADE, null=True, verbose_name='Niveau de politique',
    )
    policy_date = models.DateField(default="2026-01-01", verbose_name="Date d'adoption")
    comment = models.TextField(blank=True, verbose_name='Commentaire')
    def __str__(self):
        return str(self.company.name) + " - " +str(self.policy_level.subcategory.name) + " - " +str(self.policy_level.name)
    class Meta:
        unique_together = ('company', 'policy_level')
        verbose_name = "Politique d'entreprise"
        verbose_name_plural = "Politiques d'entreprise"


OWNERSHIP_OVERLAP_MESSAGE = (
    'Cette entreprise détient déjà cet actif sur une période qui chevauche celle-ci.'
)


def share_overflow_message(year):
    """Message d'erreur quand la somme des parts d'un actif dépasse 1."""
    when = f' en {year}' if year else ''
    return f'La somme des parts de cet actif dépasse 100 %{when}.'


def _year_bounds(start, end):
    """Période [start, end] en années ; une borne vide est ouverte."""
    return (start if start is not None else 0, end if end is not None else 9999)


def periods_overlap(first, second):
    """Deux périodes (start_year, end_year) ont-elles une année en commun ?"""
    first_start, first_end = _year_bounds(*first)
    second_start, second_end = _year_bounds(*second)
    return first_start <= second_end and second_start <= first_end


def share_overflow_year(holdings):
    """Première année où la somme des parts dépasse 1, ou None (0 si la période
    fautive n'a pas d'année de début).

    `holdings` : itérable de (share, start_year, end_year). La somme n'augmente
    qu'au début d'une période : tester ces années suffit.
    """
    bounded = [(share, *_year_bounds(start, end)) for share, start, end in holdings]
    for year in sorted({start for _, start, _ in bounded}):
        total = sum(share for share, start, end in bounded if start <= year <= end)
        if total > 1:
            return year
    return None


class OwnershipQuerySet(models.QuerySet):

    def valid_in(self, year=None):
        """Détentions valides l'année `year` ; sans année, celles en cours (sans
        `end_year`). Convention : détenteur au 31 décembre (spec §3.6)."""
        if year is None:
            return self.filter(end_year__isnull=True)
        return self.filter(
            Q(start_year__isnull=True) | Q(start_year__lte=year),
            Q(end_year__isnull=True) | Q(end_year__gte=year),
        )


OWNERSHIP_YEAR_HELP_TEXT = (
    'Le détenteur d’une année est celui du 31 décembre : pour une cession en juin '
    '2024, le vendeur finit en 2023 et l’acheteur commence en 2024. Vide = sans limite.'
)


class Ownership(models.Model):
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name='ownerships', verbose_name='Actif',
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='ownerships',
        verbose_name='Entreprise',
    )
    share = models.DecimalField(
        max_digits=5, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001')), MaxValueValidator(Decimal('1'))],
        verbose_name='Part de détention', help_text='Entre 0 et 1 : 0,75 = 75 %.',
    )
    start_year = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Année de début',
        help_text=OWNERSHIP_YEAR_HELP_TEXT,
    )
    end_year = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Année de fin',
        help_text=OWNERSHIP_YEAR_HELP_TEXT,
    )
    description = models.TextField(blank=True, verbose_name='Description')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Créé le')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Modifié le')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='Créé par',
    )

    objects = OwnershipQuerySet.as_manager()

    class Meta:
        verbose_name = 'Détention'
        verbose_name_plural = 'Détentions'
        constraints = [
            models.CheckConstraint(
                name='ownership_share_range',
                condition=Q(share__gt=0) & Q(share__lte=1),
                violation_error_message=(
                    'La part de détention doit être comprise entre 0 (exclu) et 1.'
                ),
            ),
            models.CheckConstraint(
                name='ownership_years_ordered',
                condition=(
                    Q(start_year__isnull=True) | Q(end_year__isnull=True)
                    | Q(start_year__lte=F('end_year'))
                ),
                violation_error_message="L'année de début doit précéder l'année de fin.",
            ),
        ]

    def __str__(self):
        return f'{self.asset.name} - {self.company.name}'

    def clean(self):
        """Pas de chevauchement pour un même couple actif / entreprise, et somme
        des parts d'un actif ≤ 1 chaque année (spec §3.6)."""
        super().clean()
        if self.asset_id is None or self.company_id is None:
            return
        try:
            share = Decimal(str(self.share))
        except (InvalidOperation, TypeError):
            return  # clean_fields() signale déjà la part illisible
        mine = (self.start_year, self.end_year)
        others = list(Ownership.objects.filter(asset_id=self.asset_id).exclude(pk=self.pk))
        for other in others:
            same_company = other.company_id == self.company_id
            if same_company and periods_overlap(mine, (other.start_year, other.end_year)):
                raise ValidationError(OWNERSHIP_OVERLAP_MESSAGE)
        year = share_overflow_year(
            [(share, *mine)] + [(o.share, o.start_year, o.end_year) for o in others]
        )
        if year is not None:
            raise ValidationError(share_overflow_message(year))

    @property
    def share_label(self):
        """Part au format affiché : Decimal('0.75') → '75%'."""
        return f'{(Decimal(self.share) * 100).normalize():f}%'


# ── Flux : table Flow unique (spec 2026-09-18) ────────────────────────────────

ENDPOINT_ASSET = 'asset'
ENDPOINT_REGION = 'region'
ENDPOINT_COUNTRY = 'country'
ENDPOINT_COMPANY = 'company'
ENDPOINT_ENVIRONMENT = 'environment'
# Extrémités « lieu ou entreprise ». None désigne un côté vide (inconnu).
LOCATED_ENDPOINTS = (ENDPOINT_ASSET, ENDPOINT_REGION, ENDPOINT_COUNTRY, ENDPOINT_COMPANY)
ALL_ENDPOINTS = LOCATED_ENDPOINTS + (ENDPOINT_ENVIRONMENT, None)


class FlowKind(models.TextChoices):
    PRODUCTION = 'PRODUCTION', 'Production'
    SUPPLY = 'SUPPLY', 'Approvisionnement'
    CONSUMPTION = 'CONSUMPTION', 'Consommation'
    EMISSION = 'EMISSION', 'Émission'
    WASTE = 'WASTE', 'Déchet'


class FlowScope(models.TextChoices):
    SCOPE_1 = 'Scope 1', 'Scope 1'
    SCOPE_2 = 'Scope 2', 'Scope 2'
    SCOPE_3 = 'Scope 3', 'Scope 3'
    SCOPE_1_2 = 'Scope 1+2', 'Scope 1+2'
    SCOPE_1_2_3 = 'Scope 1+2+3', 'Scope 1+2+3'
    UNDEFINED = 'undefined', 'Non défini'


FlowRule = namedtuple('FlowRule', ['origins', 'destinations', 'message'])

# Types d'extrémité autorisés par nature de flux (spec §3.4). Source unique des
# contraintes en base et des messages d'erreur de l'import Excel.
FLOW_RULES = {
    FlowKind.PRODUCTION.value: FlowRule(
        (ENDPOINT_ASSET, ENDPOINT_COMPANY), (None,),
        "Une production part d'un actif ou d'une entreprise, sans destination.",
    ),
    FlowKind.SUPPLY.value: FlowRule(
        LOCATED_ENDPOINTS, LOCATED_ENDPOINTS,
        'Un approvisionnement va d’un actif, d’une région, d’un pays ou d’une '
        'entreprise vers un autre actif, région, pays ou entreprise.',
    ),
    FlowKind.CONSUMPTION.value: FlowRule(
        (ENDPOINT_ENVIRONMENT, None), (ENDPOINT_ASSET, ENDPOINT_COMPANY),
        'Une consommation vient du milieu ou d’une origine inconnue et va vers un '
        'actif ou une entreprise.',
    ),
    FlowKind.EMISSION.value: FlowRule(
        (ENDPOINT_ASSET, ENDPOINT_COMPANY), (ENDPOINT_ENVIRONMENT,),
        "Une émission part d'un actif ou d'une entreprise et va vers le milieu.",
    ),
    FlowKind.WASTE.value: FlowRule(
        (ENDPOINT_ASSET, ENDPOINT_COMPANY), (ENDPOINT_ENVIRONMENT, None, ENDPOINT_ASSET),
        "Un déchet part d'un actif ou d'une entreprise et va vers le milieu, un actif "
        '(site de traitement) ou une destination inconnue.',
    ),
}

SUPPLY_SELF_LOOP_MESSAGE = 'Un approvisionnement ne peut pas relier un lieu à lui-même.'
REVENUE_PRODUCTION_ONLY_MESSAGE = 'Seule une production porte un revenu estimé.'

# Suffixe du champ clé étrangère de chaque type d'extrémité : from_<suffixe>.
_ENDPOINT_FIELD_SUFFIX = {
    ENDPOINT_ASSET: 'asset',
    ENDPOINT_REGION: 'region',
    ENDPOINT_COUNTRY: 'country',
    ENDPOINT_COMPANY: 'company',
}


def endpoint_q(side, endpoint):
    """Q vrai quand le côté `side` ('from' ou 'to') vaut exactement `endpoint`."""
    condition = Q(**{f'{side}_environment': endpoint == ENDPOINT_ENVIRONMENT})
    for candidate, suffix in _ENDPOINT_FIELD_SUFFIX.items():
        condition &= Q(**{f'{side}_{suffix}__isnull': candidate != endpoint})
    return condition


def _endpoints_q(side, endpoints):
    return reduce(operator.or_, (endpoint_q(side, endpoint) for endpoint in endpoints))


def _flow_constraints():
    """Contraintes de Flow (spec §3.3 et §3.4), générées depuis FLOW_RULES."""
    distinct_ends = reduce(operator.and_, (
        ~Q(**{f'from_{suffix}': F(f'to_{suffix}')})
        for suffix in _ENDPOINT_FIELD_SUFFIX.values()
    ))
    constraints = [
        models.CheckConstraint(
            name='flow_single_origin',
            condition=_endpoints_q('from', ALL_ENDPOINTS),
            violation_error_message='Un flux a au plus une origine.',
        ),
        models.CheckConstraint(
            name='flow_single_destination',
            condition=_endpoints_q('to', ALL_ENDPOINTS),
            violation_error_message='Un flux a au plus une destination.',
        ),
        models.CheckConstraint(
            name='flow_located_end',
            condition=(
                _endpoints_q('from', LOCATED_ENDPOINTS) | _endpoints_q('to', LOCATED_ENDPOINTS)
            ),
            violation_error_message=(
                "L'origine ou la destination doit être un actif, une région, un pays ou "
                'une entreprise.'
            ),
        ),
        models.CheckConstraint(
            name='flow_environment_one_end',
            condition=~Q(from_environment=True, to_environment=True),
            violation_error_message=(
                'Le milieu ne peut pas être à la fois origine et destination.'
            ),
        ),
        models.CheckConstraint(
            name='flow_revenue_production_only',
            condition=Q(estimated_revenue__isnull=True) | Q(kind=FlowKind.PRODUCTION.value),
            violation_error_message=REVENUE_PRODUCTION_ONLY_MESSAGE,
        ),
        models.CheckConstraint(
            name='flow_supply_distinct_ends',
            condition=~Q(kind=FlowKind.SUPPLY.value) | distinct_ends,
            violation_error_message=SUPPLY_SELF_LOOP_MESSAGE,
        ),
    ]
    for kind, rule in FLOW_RULES.items():
        constraints.append(models.CheckConstraint(
            name=f'flow_rule_{kind.lower()}',
            condition=~Q(kind=kind) | (
                _endpoints_q('from', rule.origins) & _endpoints_q('to', rule.destinations)
            ),
            violation_error_message=rule.message,
        ))
    return constraints


FLOW_ENDPOINT_HELP_TEXT = (
    'Au plus un champ renseigné par côté (actif, région, pays, entreprise ou milieu). '
    'Tout vide = inconnu (acheteur ou origine non renseignés).'
)


def _flow_endpoint(model, side, label):
    """Clé étrangère d'extrémité d'un Flow (from_* ou to_*)."""
    return models.ForeignKey(
        model, on_delete=models.CASCADE, null=True, blank=True,
        related_name='flows_out' if side == 'from' else 'flows_in',
        verbose_name=f"{'Origine' if side == 'from' else 'Destination'} — {label}",
        help_text=FLOW_ENDPOINT_HELP_TEXT,
    )


class Flow(models.Model):
    """Quantité d'une commodité, une année, d'une origine vers une destination
    (spec 2026-09-18). Remplace Production, AssetInventory, l'ancien graphe
    fournisseurs et Carbon_emission (modèles historiques, aujourd'hui supprimés)."""

    Kind = FlowKind
    Scope = FlowScope

    kind = models.CharField(
        max_length=12, choices=FlowKind.choices, verbose_name='Nature du flux',
    )
    what = models.ForeignKey(
        Commodity, on_delete=models.PROTECT, related_name='flows',
        verbose_name='Commodité',
    )
    scope = models.CharField(
        max_length=12, choices=FlowScope.choices, default=FlowScope.UNDEFINED,
        verbose_name='Scope GES',
    )

    from_asset = _flow_endpoint(Asset, 'from', 'actif')
    from_region = _flow_endpoint(SubnationalRegion, 'from', 'région')
    from_country = _flow_endpoint(Country, 'from', 'pays')
    from_company = _flow_endpoint(Company, 'from', 'entreprise')
    from_environment = models.BooleanField(
        default=False, verbose_name='Origine — milieu',
        help_text='Prélevé dans le milieu naturel, à proximité de la destination.',
    )

    to_asset = _flow_endpoint(Asset, 'to', 'actif')
    to_region = _flow_endpoint(SubnationalRegion, 'to', 'région')
    to_country = _flow_endpoint(Country, 'to', 'pays')
    to_company = _flow_endpoint(Company, 'to', 'entreprise')
    to_environment = models.BooleanField(
        default=False, verbose_name='Destination — milieu',
        help_text='Rejeté dans le milieu naturel, à proximité de l’origine.',
    )

    year = models.IntegerField(verbose_name='Année')
    quantity = models.FloatField(
        verbose_name='Quantité', help_text="Exprimée dans l'unité de la commodité.",
    )
    tier = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(3)], verbose_name='Tier',
        help_text=TIER_HELP_TEXT,
    )
    estimated_revenue = models.FloatField(
        null=True, blank=True, verbose_name='Revenu estimé',
        help_text='Production uniquement. ' + UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    source = models.CharField(max_length=255, blank=True, verbose_name='Source')
    reference = models.CharField(max_length=255, blank=True, verbose_name='Référence')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Créé le')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Modifié le')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='Créé par',
    )

    class Meta:
        verbose_name = 'Flux'
        verbose_name_plural = 'Flux'
        constraints = _flow_constraints()

    def __str__(self):
        return f'{self.get_kind_display()} — {self.what.name} ({self.year})'

    def _endpoint_type(self, side):
        if getattr(self, f'{side}_environment'):
            return ENDPOINT_ENVIRONMENT
        for endpoint, suffix in _ENDPOINT_FIELD_SUFFIX.items():
            if getattr(self, f'{side}_{suffix}_id') is not None:
                return endpoint
        return None

    @property
    def origin_type(self):
        return self._endpoint_type('from')

    @property
    def destination_type(self):
        return self._endpoint_type('to')


class E4Assessment(models.Model):
    """Dossier de conformité ESRS E4 d'une entreprise (verrou de matérialité + LEAP)."""

    class StandardVersion(models.TextChoices):
        AMENDED_2025 = 'AMENDED_2025', 'ESRS E4 amendé (déc. 2025) — 5 DR'
        ORIGINAL_2023 = 'ORIGINAL_2023', 'ESRS E4 original (2023) — 6 DR'

    class Materiality(models.TextChoices):
        NOT_ASSESSED = 'NOT_ASSESSED', 'Non évaluée'
        MATERIAL = 'MATERIAL', 'Matérielle'
        NOT_MATERIAL = 'NOT_MATERIAL', 'Non matérielle'

    class LeapStatus(models.TextChoices):
        TODO = 'TODO', 'À faire'
        IN_PROGRESS = 'IN_PROGRESS', 'En cours'
        DONE = 'DONE', 'Fait'

    LEAP_STATUS_HELP_TEXT = (
        'La phase Prepare est hors périmètre ESRS E4 : seules Locate, '
        'Evaluate et Assess servent à la détermination de matérialité.'
    )

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='e4_assessments',
        verbose_name='Entreprise',
    )
    reporting_year = models.IntegerField(default=2024, verbose_name='Exercice de reporting')
    standard_version = models.CharField(
        max_length=20, choices=StandardVersion.choices,
        default=StandardVersion.AMENDED_2025,
        verbose_name='Version du standard',
    )
    materiality_status = models.CharField(
        max_length=20, choices=Materiality.choices,
        default=Materiality.NOT_ASSESSED,
        verbose_name='Statut de matérialité',
    )
    materiality_justification = models.TextField(
        blank=True, verbose_name='Justification de matérialité',
    )

    # Approche LEAP limitée à 3 phases (Locate/Evaluate/Assess) pour la
    # détermination de matérialité — la phase Prepare est hors périmètre E4.
    leap_locate_status = models.CharField(
        max_length=20, choices=LeapStatus.choices, default=LeapStatus.TODO,
        verbose_name='LEAP — Locate, statut', help_text=LEAP_STATUS_HELP_TEXT,
    )
    leap_evaluate_status = models.CharField(
        max_length=20, choices=LeapStatus.choices, default=LeapStatus.TODO,
        verbose_name='LEAP — Evaluate, statut', help_text=LEAP_STATUS_HELP_TEXT,
    )
    leap_assess_status = models.CharField(
        max_length=20, choices=LeapStatus.choices, default=LeapStatus.TODO,
        verbose_name='LEAP — Assess, statut', help_text=LEAP_STATUS_HELP_TEXT,
    )
    leap_locate_notes = models.TextField(blank=True, verbose_name='LEAP — Locate, notes')
    leap_evaluate_notes = models.TextField(blank=True, verbose_name='LEAP — Evaluate, notes')
    leap_assess_notes = models.TextField(blank=True, verbose_name='LEAP — Assess, notes')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Créé le')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Modifié le')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Créé par',
    )

    class Meta:
        verbose_name = 'Évaluation ESRS E4'
        verbose_name_plural = 'Évaluations ESRS E4'

    def __str__(self):
        return f"{self.company.name} — E4 {self.reporting_year}"


class DisclosureRequirement(models.Model):
    """État de conformité d'un Disclosure Requirement pour une évaluation E4."""

    class Code(models.TextChoices):
        E4_1 = 'E4_1', 'E4-1'
        E4_2 = 'E4_2', 'E4-2'
        E4_3 = 'E4_3', 'E4-3'
        E4_4 = 'E4_4', 'E4-4'
        E4_5 = 'E4_5', 'E4-5'
        E4_6 = 'E4_6', 'E4-6'

    class Status(models.TextChoices):
        NOT_STARTED = 'NOT_STARTED', 'Non commencé'
        NON_COMPLIANT = 'NON_COMPLIANT', 'Non conforme'
        PARTIAL = 'PARTIAL', 'Partiel'
        COMPLIANT = 'COMPLIANT', 'Conforme'
        NOT_APPLICABLE = 'NOT_APPLICABLE', 'Non applicable'

    assessment = models.ForeignKey(
        E4Assessment, on_delete=models.CASCADE, related_name='disclosure_requirements',
        verbose_name='Évaluation',
    )
    code = models.CharField(
        max_length=10, choices=Code.choices, verbose_name='Code du DR',
        help_text='Les DR applicables dépendent de la version du standard retenue '
                  'sur l’évaluation (5 DR pour la version amendée 2025, 6 pour '
                  'l’originale 2023).',
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOT_STARTED,
        verbose_name='Statut de conformité',
    )
    justification = models.TextField(blank=True, verbose_name='Justification')

    class Meta:
        unique_together = ('assessment', 'code')
        verbose_name = 'Disclosure Requirement'
        verbose_name_plural = 'Disclosure Requirements'

    def __str__(self):
        return f"{self.assessment.company.name} — {self.get_code_display()}"

class Currency(models.Model):
    code = models.CharField(max_length=3, verbose_name='Code ISO')
    name = models.CharField(max_length=255, verbose_name='Nom')
    symbol = models.CharField(max_length=3, verbose_name='Symbole')
    ratio_USD = models.FloatField(default=1, verbose_name="Taux de conversion vers l'USD")

    class Meta:
        verbose_name = 'Devise'
        verbose_name_plural = 'Devises'

    def __str__(self):
        return self.code

class ESG_data(models.Model):
    """
    Table des données financières et opérationnelles.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name='Entreprise')
    year = models.IntegerField(verbose_name='Exercice')
    employees_number = models.IntegerField(default=0, verbose_name='Nombre de salariés')
    def __str__(self):
        return f"{self.company.name} - {self.year}"

    class Meta:
        unique_together = ('company', 'year')
        verbose_name = 'Donnée ESG'
        verbose_name_plural = 'Données ESG'

class Carbon_emission(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name='Entreprise')
    year = models.IntegerField(verbose_name='Exercice')
    scope = models.CharField(max_length=255, verbose_name='Scope')
    carbon_emission = models.FloatField(default=0, verbose_name='Émissions (tCO₂e)')

    def __str__(self):
        return f"{self.company.name} - {self.year} - {self.scope}"

    class Meta:
        unique_together = ('company', 'year', 'scope')
        verbose_name = 'Émission carbone'
        verbose_name_plural = 'Émissions carbone'


class ImpactMethod(models.Model):
    """Méthode de caractérisation LCA (ReCiPe2016, GBS, …)."""
    name = models.CharField(max_length=100, unique=True, verbose_name='Nom')
    version = models.CharField(max_length=50, blank=True, verbose_name='Version')
    description = models.TextField(blank=True, verbose_name='Description')

    class Meta:
        verbose_name = 'Méthode de caractérisation'
        verbose_name_plural = 'Méthodes de caractérisation'

    def __str__(self):
        return self.name


class ImpactCategory(models.Model):
    """Axe d'impact ACV. `key` == nom de colonne legacy (contrat de sortie)."""

    class Level(models.TextChoices):
        MIDPOINT = 'MIDPOINT', 'Midpoint'
        ENDPOINT = 'ENDPOINT', 'Endpoint'

    method = models.ForeignKey(
        ImpactMethod, on_delete=models.CASCADE, related_name='categories',
        verbose_name='Méthode',
    )
    key = models.CharField(
        max_length=100, unique=True, verbose_name='Clé technique',
        help_text=KEY_HELP_TEXT,
    )
    name = models.CharField(max_length=255, verbose_name='Nom')
    unit = models.CharField(max_length=50, blank=True, verbose_name='Unité')
    level = models.CharField(max_length=10, choices=Level.choices,
                             default=Level.MIDPOINT, verbose_name='Niveau')
    theme = models.CharField(
        max_length=30, blank=True, verbose_name='Thème', help_text=THEME_HELP_TEXT,
    )

    class Meta:
        verbose_name = "Catégorie d'impact"
        verbose_name_plural = "Catégories d'impact"

    def __str__(self):
        return f'{self.method.name} — {self.key}'


CF_LOCATION_HELP_TEXT = (
    'Laisser les deux vides pour un facteur global. La résolution suit '
    'l’ordre région → pays → global : le premier facteur trouvé gagne.'
)


class CharacterizationFactor(models.Model):
    """Facteur de caractérisation régionalisé : impact par unité de commodity.

    Résolution du lieu : region renseigné → région ; sinon country → pays ;
    sinon (les deux null) → global.
    """

    category = models.ForeignKey(
        ImpactCategory, on_delete=models.CASCADE, related_name='factors',
        verbose_name="Catégorie d'impact",
    )
    commodity = models.ForeignKey(
        Commodity, on_delete=models.CASCADE, related_name='cfs', verbose_name='Commodité',
    )
    region = models.ForeignKey(
        SubnationalRegion, on_delete=models.CASCADE, null=True, blank=True,
        verbose_name='Région infranationale', help_text=CF_LOCATION_HELP_TEXT,
    )
    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, null=True, blank=True,
        verbose_name='Pays', help_text=CF_LOCATION_HELP_TEXT,
    )
    value = models.FloatField(
        default=0.0, verbose_name='Facteur',
        help_text='Impact généré par une unité de la commodité. Multiplié par la '
                  'quantité produite pour obtenir l’impact total.',
    )
    source = models.CharField(max_length=255, blank=True, verbose_name='Source')
    reference = models.CharField(max_length=255, blank=True, verbose_name='Référence')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Créé le')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Modifié le')

    class Meta:
        # NB SQLite : les NULL sont distincts dans une contrainte unique ; l'unicité
        # du CF global (region=country=null) est garantie applicativement par
        # get_or_create côté backfill et populate_acme.
        unique_together = ('category', 'commodity', 'region', 'country')
        verbose_name = 'Facteur de caractérisation'
        verbose_name_plural = 'Facteurs de caractérisation'

    def __str__(self):
        return f'{self.commodity.name} — {self.category.key}'


class ClimateScenario(models.Model):
    """Scénario climatique de référence (NGFS Phase V)."""

    class Family(models.TextChoices):
        ORDERLY = 'ORDERLY', 'Transition ordonnée'
        DISORDERLY = 'DISORDERLY', 'Transition désordonnée'
        TOO_LITTLE = 'TOO_LITTLE', 'Trop peu, trop tard'
        HOT_HOUSE = 'HOT_HOUSE', 'Monde en surchauffe'

    key = models.CharField(max_length=50, unique=True, verbose_name='Clé technique')
    name = models.CharField(max_length=255, verbose_name='Nom')
    family = models.CharField(
        max_length=20, choices=Family.choices, default=Family.ORDERLY,
        verbose_name='Famille',
    )
    narrative = models.TextField(blank=True, verbose_name='Narratif')
    warming_c = models.FloatField(default=0.0, verbose_name='Réchauffement (°C)')
    source = models.CharField(max_length=255, blank=True, verbose_name='Source')
    reference = models.CharField(max_length=255, blank=True, verbose_name='Référence')
    order = models.PositiveSmallIntegerField(
        default=0, verbose_name="Ordre d'affichage",
        help_text='Contrôle l’ordre d’affichage des scénarios dans les écrans.',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Créé le')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Modifié le')

    class Meta:
        ordering = ('order', 'key')
        verbose_name = 'Scénario climatique'
        verbose_name_plural = 'Scénarios climatiques'

    def __str__(self):
        return self.name


class ScenarioVariable(models.Model):
    """Point de trajectoire d'un scénario (prix carbone, multiplicateur d'aléa)."""

    class Key(models.TextChoices):
        CARBON_PRICE = 'carbon_price', 'Prix du carbone (€/tCO₂e)'
        HAZARD_MULTIPLIER = 'hazard_multiplier', "Multiplicateur d'aléa"

    scenario = models.ForeignKey(
        ClimateScenario, on_delete=models.CASCADE, related_name='variables',
        verbose_name='Scénario',
    )
    year = models.IntegerField(verbose_name='Année')
    key = models.CharField(max_length=30, choices=Key.choices, verbose_name='Variable')
    value = models.FloatField(
        default=0.0, verbose_name='Valeur',
        help_text='L’unité dépend de la variable choisie : €/tCO₂e pour un prix du '
                  'carbone, facteur sans unité pour un multiplicateur d’aléa.',
    )

    class Meta:
        unique_together = ('scenario', 'year', 'key')
        ordering = ('scenario', 'key', 'year')
        verbose_name = 'Variable de scénario'
        verbose_name_plural = 'Variables de scénario'

    def __str__(self):
        return f'{self.scenario.key} — {self.key} {self.year}'


class SectorCreditProfile(models.Model):
    """Paramètres de crédit et de marge d'un secteur (NACE).

    Sert de valeur par défaut : l'utilisateur peut surcharger la PD initiale et
    la marge EBITDA à l'écran.
    """

    sector = models.OneToOneField(
        Sector, on_delete=models.CASCADE, related_name='credit_profile',
        verbose_name='Secteur',
    )
    pd_baseline = models.FloatField(
        default=0.015, verbose_name='Probabilité de défaut de référence',
        help_text='Valeur par défaut du secteur. L’utilisateur peut la surcharger '
                  'dans l’écran de stress test climatique.',
    )
    ebitda_margin = models.FloatField(
        default=0.12, verbose_name="Marge d'EBITDA",
        help_text='Valeur par défaut du secteur. L’utilisateur peut la surcharger '
                  'dans l’écran de stress test climatique.',
    )
    ebitda_volatility = models.FloatField(
        default=0.25, verbose_name="Volatilité de l'EBITDA",
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    carbon_pass_through = models.FloatField(
        default=0.30, verbose_name='Répercussion du coût carbone',
        help_text=UNDOCUMENTED_SCALE_HELP_TEXT,
    )
    source = models.CharField(max_length=255, blank=True, verbose_name='Source')
    reference = models.CharField(max_length=255, blank=True, verbose_name='Référence')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Créé le')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Modifié le')

    class Meta:
        verbose_name = 'Profil crédit sectoriel'
        verbose_name_plural = 'Profils crédit sectoriels'

    def __str__(self):
        return f'{self.sector.name} — PD {self.pd_baseline:.2%}'


class PortfolioQuerySet(models.QuerySet):
    """Règles de visibilité et d'édition des portefeuilles."""

    def visible_to(self, user):
        """Portefeuilles de l'utilisateur, plus les portefeuilles communs."""
        return self.filter(models.Q(created_by=user) | models.Q(is_shared=True))

    def editable_by(self, user):
        """Portefeuilles que l'utilisateur peut modifier. Le staff peut tout."""
        if getattr(user, 'is_staff', False):
            return self
        return self.filter(created_by=user)


class Portfolio(models.Model):
    """Portefeuille (fonds) : ensemble d'entreprises pondérées à analyser."""
    name = models.CharField(max_length=255, verbose_name='Nom du fonds')
    size = models.FloatField(default=0, verbose_name='Taille du fonds')
    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, verbose_name='Devise',
    )
    benchmark = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='benchmarked_by', verbose_name='Benchmark',
    )
    is_benchmark = models.BooleanField(
        default=False, verbose_name='Utiliser comme benchmark',
    )
    is_shared = models.BooleanField(
        default=False, verbose_name='Portefeuille commun',
        help_text='Visible en lecture par tous les utilisateurs. Réservé au staff.',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Créé le')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Modifié le')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Créé par',
    )

    objects = PortfolioQuerySet.as_manager()

    class Meta:
        verbose_name = 'Portefeuille'
        verbose_name_plural = 'Portefeuilles'

    def __str__(self):
        return self.name

    def can_be_edited_by(self, user):
        return bool(
            getattr(user, 'is_staff', False)
            or (self.created_by_id and self.created_by_id == getattr(user, 'pk', None))
        )


class PortfolioHolding(models.Model):
    """Position d'un portefeuille : une entreprise, un montant, un poids."""
    class Instrument(models.TextChoices):
        EQUITY = 'EQUITY', 'Action (Equity)'
        BOND = 'BOND', 'Obligation (Bond)'

    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name='holdings',
        verbose_name='Portefeuille',
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, verbose_name='Entreprise',
    )
    amount = models.FloatField(default=0, verbose_name='Montant investi')
    weight = models.FloatField(default=0, verbose_name='Poids (%)')
    instrument_type = models.CharField(
        max_length=10, choices=Instrument.choices, default=Instrument.EQUITY,
        verbose_name="Type d'instrument",
    )
    maturity_date = models.DateField(
        null=True, blank=True, verbose_name='Maturité',
    )
    coupon_rate = models.FloatField(
        null=True, blank=True, verbose_name='Taux de coupon (%)',
    )
    face_value = models.FloatField(
        null=True, blank=True, verbose_name='Valeur nominale',
    )

    class Meta:
        unique_together = ('portfolio', 'company')
        verbose_name = 'Position de portefeuille'
        verbose_name_plural = 'Positions de portefeuille'

    def __str__(self):
        return f'{self.portfolio.name} — {self.company.name}'
