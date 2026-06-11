from django.db import models
from django.conf import settings

class Country(models.Model):
    name = models.CharField(max_length=255)
    water_ownership = models.CharField(max_length=255)
    land_ownership = models.CharField(max_length=255)
    water_Governance=models.TextField(blank=True)
    land_Governance=models.TextField(blank=True)
    restoration_cost_m2 = models.FloatField(default=0)
    biodiversity_loss_agriculture=models.FloatField(default=0)
    biodiversity_loss_urbanization=models.FloatField(default=0)
    biodiversity_loss_mining=models.FloatField(default=0)
    
    def __str__(self):
        return self.name    


class SubnationalRegion(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    restoration_cost_m2 = models.FloatField(default=0)
    Mean_X=models.FloatField(default=0)
    Mean_Y=models.FloatField(default=0)
    def __str__(self):
        return self.name

class Commodity (models.Model):
    DEPENDENCY_CHOICES = [
        ('VL', 'Very low'),
        ('L', 'Low'),
        ('M', 'Medium'),
        ('H', 'High'),
        ('VH', 'Very High'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=255, default="tonnes")
    impact_midpoint_ReCiPe2016_water_consumption = models.FloatField(default=0)
    impact_midpoint_ReCiPe2016_climate_change = models.FloatField(default=0)
    impact_midpoint_ReCiPe2016_freshwater_ecotoxicity = models.FloatField(default=0)
    impact_midpoint_ReCiPe2016_freshwater_eutrophication = models.FloatField(default=0)
    impact_midpoint_ReCiPe2016_marine_eutrophication = models.FloatField(default=0)
    impact_midpoint_ReCiPe2016_terrestrial_acidification = models.FloatField(default=0)
    impact_midpoint_ReCiPe2016_soil_acidification = models.FloatField(default=0)
    impact_midpoint_ReCiPe2016_ozonedepletion = models.FloatField(default=0)
    impact_midpoint_ReCiPe2016_resource_depletion_fossil = models.FloatField(default=0)
    impact_midpoint_ReCiPe2016_resource_depletion_minerals = models.FloatField(default=0)
    impact_midpoint_ReCiPe2016_land_use=models.FloatField(default=0)
    impact_endpoint_ReCiPe2016_human_health = models.FloatField(default=0)
    impact_endpoint_ReCiPe2016_ecosystem_diversity = models.FloatField(default=0)
    impact_endpoint_ReCiPe2016_resource_availability = models.FloatField(default=0)

    impact_endpoint_GBS_terrestrial_dynamic = models.FloatField(default=0)
    impact_endpoint_GBS_terrestrial_static = models.FloatField(default=0)
    
    dependency_water = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')
    dependency_pollination = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')
    dependency_soil_quality = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')
    dependency_carbon_sequestration = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')
    dependency_water_purification = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')
    dependency_pest_control = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')

    biodiversity_loss_class = models.CharField(choices=[('Agriculture','Agriculture'),('Urbanisation','Urbanisation'),('Mining','Mining')],default="Agriculture")

    def __str__(self):
        return self.name

class Sector(models.Model):
    name = models.CharField(max_length=255)
    NACE_code = models.CharField(max_length=255, blank=True,null=True)
    description = models.TextField(blank=True,null=True)
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
    name = models.CharField(max_length=255)
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE)
    NACE_code = models.CharField(max_length=255, blank=True,null=True)
    description = models.TextField(blank=True,null=True)
    Water_dependency = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')
    Pollination_dependency = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')
    Soil_quality_dependency = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')
    Carbon_Sequestration = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')
    Water_purification_dependency = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')
    Pest_control_dependency = models.CharField(max_length=2, choices=DEPENDENCY_CHOICES, default='VL')

    def __str__(self):
        return self.name

class Asset(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    subnational_region = models.ForeignKey(SubnationalRegion, on_delete=models.CASCADE,null=True,blank=True)

    risk_water = models.FloatField(default=0)
    risk_pollination = models.FloatField(default=0)
    risk_soil_quality = models.FloatField(default=0)
    risk_carbon_sequestration = models.FloatField(default=0)
    risk_water_purification = models.FloatField(default=0)
    risk_pest_control = models.FloatField(default=0)
    risk_water_stress = models.FloatField(default=0)
    risk_wildfire = models.FloatField(default=0)
    risk_cyclone = models.FloatField(default=0)
    risk_drought = models.FloatField(default=0)
    risk_flood = models.FloatField(default=0)
    risk_coastal_inundation = models.FloatField(default=0)
    risk_heatwave = models.FloatField(default=0)
    risk_temperature_variation = models.FloatField(default=0)
    risk_precipitation_variation = models.FloatField(default=0)

    class SensitiveZoneType(models.TextChoices):
        NATURA_2000 = 'NATURA_2000', 'Natura 2000'
        NATIONAL_PROTECTED = 'NATIONAL_PROTECTED', 'Aire protégée nationale'
        UNESCO = 'UNESCO', 'Site UNESCO'
        IUCN_KBA = 'IUCN_KBA', 'IUCN Key Biodiversity Area'
        OTHER = 'OTHER', 'Autre'

    near_sensitive_zone = models.BooleanField(default=False)
    sensitive_zone_type = models.CharField(
        max_length=20, choices=SensitiveZoneType.choices, blank=True
    )
    sensitive_zone_name = models.CharField(max_length=255, blank=True)
    sensitive_zone_area_ha = models.FloatField(default=0)

    def __str__(self):
        return self.name

class Company (models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    isin = models.CharField(max_length=255, default="0")
    ticker = models.CharField(max_length=255, default="0")
    def __str__(self):
        return self.name

class Production(models.Model):
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, null=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    subnational_region = models.ForeignKey(SubnationalRegion, on_delete=models.CASCADE, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, null=True, blank=True)
    scope = models.CharField(max_length=15, choices=[('direct', 'direct'), ('tier 1', 'tier 1'), ('tier 2', 'tier 2'), ('raw material', 'raw material')], default='direct')
    year = models.IntegerField()
    production = models.FloatField()
    estimated_revenue = models.FloatField(default = 0.0)
    def __str__(self):
        asset_name = self.asset.name if self.asset else "no asset"
        return f"{asset_name} - {self.commodity.name} - {self.year}"

class Asset_consumption(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, null=True, blank=True)
    surface_area = models.FloatField(default=0)
    water_consumption = models.FloatField(default=0)
    energy_consumption = models.FloatField(default=0)
    CO2_emissions = models.FloatField(default=0)
    waste_generated = models.FloatField(default=0)
    def __str__(self):
        asset_name = self.asset.name if self.asset else "no asset"
        return f"{asset_name}"


class Company_Revenue(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    year = models.IntegerField()
    revenue = models.FloatField()
    currency = models.CharField(max_length=255)
    def __str__(self):
        return str(self.company.name) + " - " + str(self.year)

class Company_Revenue_Sector(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    subsector = models.ForeignKey(SubSector, on_delete=models.CASCADE)
    year = models.IntegerField()
    revenue = models.FloatField()
    def __str__(self):
        return str(self.company.name) + " - " + str(self.subsector.sector.name) + " - " + str(self.subsector.name) + " - " + str(self.year)

class Policy_Type(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    def __str__(self):
        return self.name

class Policy_Subcategory(models.Model):
    policy_type = models.ForeignKey(Policy_Type, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    def __str__(self):
        return str(self.policy_type.name) + " - " + str(self.name)

class Policy_Level(models.Model):
    subcategory = models.ForeignKey(Policy_Subcategory, on_delete=models.CASCADE)
    name = models.CharField(max_length=255) 
    score = models.FloatField(null=True,blank=True)
    description = models.TextField(blank=True)
    vulnerability_water = models.FloatField(default=1.0)
    vulnerability_pollination = models.FloatField(default=1.0)
    vulnerability_soil_quality = models.FloatField(default=1.0)
    vulnerability_carbon_sequestration = models.FloatField(default=1.0)
    vulnerability_water_purification = models.FloatField(default=1.0)
    vulnerability_pest_control = models.FloatField(default=1.0)
    vulnerability_water_stress = models.FloatField(default=1.0)
    vulnerability_wildfire = models.FloatField(default=1.0)
    vulnerability_cyclone = models.FloatField(default=1.0)
    vulnerability_drought = models.FloatField(default=1.0)
    vulnerability_flood = models.FloatField(default=1.0)
    vulnerability_coastal_inundation = models.FloatField(default=1.0)
    vulnerability_heatwave = models.FloatField(default=1.0)
    vulnerability_temperature_variation = models.FloatField(default=1.0)
    vulnerability_precipitation_variation = models.FloatField(default=1.0)
    def __str__(self):
        return str(self.subcategory.policy_type.name) + " - " + str(self.subcategory.name) + " - " + str(self.name)
    
class Company_Policy(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    policy_level = models.ForeignKey(Policy_Level, on_delete=models.CASCADE,null=True)
    policy_date = models.DateField(default="2026-01-01")  
    def __str__(self):
        return str(self.company.name) + " - " +str(self.policy_level.subcategory.name) + " - " +str(self.policy_level.name)
    class Meta:
        unique_together = ('company', 'policy_level')  


class Ownership(models.Model):
    Asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    Company = models.ForeignKey(Company, on_delete=models.CASCADE)
    ownership = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    def __str__(self):
        return str(self.Asset.name) + " - " + str(self.Company.name)


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

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='e4_assessments'
    )
    reporting_year = models.IntegerField(default=2024)
    standard_version = models.CharField(
        max_length=20, choices=StandardVersion.choices,
        default=StandardVersion.AMENDED_2025,
    )
    materiality_status = models.CharField(
        max_length=20, choices=Materiality.choices,
        default=Materiality.NOT_ASSESSED,
    )
    materiality_justification = models.TextField(blank=True)

    leap_locate_status = models.CharField(
        max_length=20, choices=LeapStatus.choices, default=LeapStatus.TODO
    )
    leap_evaluate_status = models.CharField(
        max_length=20, choices=LeapStatus.choices, default=LeapStatus.TODO
    )
    leap_assess_status = models.CharField(
        max_length=20, choices=LeapStatus.choices, default=LeapStatus.TODO
    )
    leap_locate_notes = models.TextField(blank=True)
    leap_evaluate_notes = models.TextField(blank=True)
    leap_assess_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

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
        E4Assessment, on_delete=models.CASCADE, related_name='disclosure_requirements'
    )
    code = models.CharField(max_length=10, choices=Code.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOT_STARTED
    )
    justification = models.TextField(blank=True)

    class Meta:
        unique_together = ('assessment', 'code')

    def __str__(self):
        return f"{self.assessment.company.name} — {self.get_code_display()}"

