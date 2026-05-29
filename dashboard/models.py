from django.db import models

class Country(models.Model):
    name = models.CharField(max_length=255)
    water_ownership = models.CharField(max_length=255)
    land_ownership = models.CharField(max_length=255)
    water_Governance=models.TextField(blank=True)
    land_Governance=models.TextField(blank=True)
    def __str__(self):
        return self.name

class SubnationalRegion(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    def __str__(self):
        return self.name

class Commodity (models.Model):
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
    impact_endpoint_ReCiPe2016_human_health = models.FloatField(default=0)
    impact_endpoint_ReCiPe2016_ecosystem_diversity = models.FloatField(default=0)
    impact_endpoint_ReCiPe2016_resource_availability = models.FloatField(default=0)
    
    def __str__(self):
        return self.name

class Asset(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    subnational_region = models.ForeignKey(SubnationalRegion, on_delete=models.CASCADE)
    def __str__(self):
        return self.name

class Production(models.Model):
    Asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE)
    year = models.IntegerField()
    production = models.FloatField()
    def __str__(self):
        return str(self.Asset.name) + " - " + str(self.commodity.name) + " - " + str(self.year)

class Company (models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    def __str__(self):
        return self.name

class Company_Revenue(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    year = models.IntegerField()
    revenue = models.FloatField()
    currency = models.CharField(max_length=255)
    def __str__(self):
        return str(self.company.name) + " - " + str(self.year)

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



