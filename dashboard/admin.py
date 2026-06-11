from django.contrib import admin
from .models import (
    Country, SubnationalRegion, Commodity, Sector, SubSector,
    Asset, Asset_consumption, Company, Production, Ownership,
    Company_Revenue, Company_Revenue_Sector,
    Policy_Type, Policy_Subcategory, Policy_Level, Company_Policy,
)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    list_display = ('name', 'water_ownership', 'land_ownership')
    list_filter = ('water_ownership', 'land_ownership')


@admin.register(SubnationalRegion)
class SubnationalRegionAdmin(admin.ModelAdmin):
    search_fields = ('name', 'country__name')
    list_display = ('name', 'country')
    list_filter = ('country',)
    autocomplete_fields = ('country',)


@admin.register(Commodity)
class CommodityAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    list_display = ('name', 'unit', 'biodiversity_loss_class')
    list_filter = (
        'biodiversity_loss_class',
        'dependency_water', 'dependency_pollination',
        'dependency_soil_quality',
    )


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    search_fields = ('name', 'NACE_code')
    list_display = ('name', 'NACE_code')


@admin.register(SubSector)
class SubSectorAdmin(admin.ModelAdmin):
    search_fields = ('name', 'NACE_code', 'sector__name')
    list_display = ('name', 'sector', 'NACE_code')
    list_filter = ('sector',)
    autocomplete_fields = ('sector',)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    search_fields = ('name', 'country__name', 'subnational_region__name')
    list_display = ('name', 'country', 'subnational_region', 'latitude', 'longitude')
    list_filter = ('country',)
    autocomplete_fields = ('country', 'subnational_region')


@admin.register(Asset_consumption)
class AssetConsumptionAdmin(admin.ModelAdmin):
    search_fields = ('asset__name',)
    list_display = ('asset', 'surface_area', 'water_consumption', 'energy_consumption')
    autocomplete_fields = ('asset',)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    search_fields = ('name', 'isin', 'ticker')
    list_display = ('name', 'isin', 'ticker')


@admin.register(Production)
class ProductionAdmin(admin.ModelAdmin):
    search_fields = (
        'commodity__name', 'asset__name', 'company__name',
        'subnational_region__name', 'country__name',
    )
    list_display = ('__str__', 'commodity', 'company', 'scope', 'year', 'production')
    list_filter = ('scope', 'year', 'country')
    autocomplete_fields = ('commodity', 'asset', 'company', 'subnational_region', 'country')


@admin.register(Ownership)
class OwnershipAdmin(admin.ModelAdmin):
    search_fields = ('Asset__name', 'Company__name')
    list_display = ('Asset', 'Company', 'ownership')
    autocomplete_fields = ('Asset', 'Company')


@admin.register(Company_Revenue)
class CompanyRevenueAdmin(admin.ModelAdmin):
    search_fields = ('company__name',)
    list_display = ('company', 'year', 'revenue', 'currency')
    list_filter = ('year', 'currency')
    autocomplete_fields = ('company',)


@admin.register(Company_Revenue_Sector)
class CompanyRevenueSectorAdmin(admin.ModelAdmin):
    search_fields = ('company__name', 'subsector__name', 'subsector__sector__name')
    list_display = ('company', 'subsector', 'year', 'revenue')
    list_filter = ('year',)
    autocomplete_fields = ('company', 'subsector')


@admin.register(Policy_Type)
class PolicyTypeAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    list_display = ('name',)


@admin.register(Policy_Subcategory)
class PolicySubcategoryAdmin(admin.ModelAdmin):
    search_fields = ('name', 'policy_type__name')
    list_display = ('name', 'policy_type')
    list_filter = ('policy_type',)
    autocomplete_fields = ('policy_type',)


@admin.register(Policy_Level)
class PolicyLevelAdmin(admin.ModelAdmin):
    search_fields = ('name', 'subcategory__name', 'subcategory__policy_type__name')
    list_display = ('name', 'subcategory', 'score')
    list_filter = ('subcategory__policy_type',)
    autocomplete_fields = ('subcategory',)


@admin.register(Company_Policy)
class CompanyPolicyAdmin(admin.ModelAdmin):
    search_fields = ('company__name', 'policy_level__name', 'policy_level__subcategory__name')
    list_display = ('company', 'policy_level', 'policy_date')
    list_filter = ('policy_date',)
    autocomplete_fields = ('company', 'policy_level')
