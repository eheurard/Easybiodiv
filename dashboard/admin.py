from django.contrib import admin
from .models import (
    Country, SubnationalRegion, Commodity, Sector, SubSector,
    Asset, Company, Ownership,
    Company_Revenue, Company_Revenue_Sector,
    Policy_Type, Policy_Subcategory, Policy_Level, Company_Policy,
    DisclosureRequirement, E4Assessment, ESG_data, Carbon_emission,
    Currency,
    ImpactMethod, ImpactCategory, CharacterizationFactor,
    Flow,
    ClimateScenario, ScenarioVariable, SectorCreditProfile,
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
    search_fields = ('name', 'key')
    list_display = ('name', 'key', 'unit', 'theme', 'biodiversity_loss_class')
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
    list_display = (
        'name', 'country', 'subnational_region',
        'near_sensitive_zone', 'sensitive_zone_type',
    )
    list_filter = ('country', 'near_sensitive_zone', 'sensitive_zone_type')
    autocomplete_fields = ('country', 'subnational_region')


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    search_fields = ('name', 'isin', 'ticker')
    list_display = ('name', 'isin', 'ticker')


@admin.register(Ownership)
class OwnershipAdmin(admin.ModelAdmin):
    search_fields = ('asset__name', 'company__name')
    list_display = ('asset', 'company', 'share_percent', 'start_year', 'end_year')
    list_filter = ('company',)
    autocomplete_fields = ('asset', 'company')

    @admin.display(description='Part de détention')
    def share_percent(self, obj):
        return obj.share_label


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


class DisclosureRequirementInline(admin.TabularInline):
    model = DisclosureRequirement
    extra = 0
    fields = ('code', 'status', 'justification')


@admin.register(E4Assessment)
class E4AssessmentAdmin(admin.ModelAdmin):
    search_fields = ('company__name',)
    list_display = (
        'company', 'reporting_year', 'standard_version', 'materiality_status',
    )
    list_filter = ('standard_version', 'materiality_status', 'reporting_year')
    autocomplete_fields = ('company',)
    inlines = (DisclosureRequirementInline,)
    fieldsets = (
        (None, {
            'fields': (
                'company', 'reporting_year', 'standard_version',
                'materiality_status', 'materiality_justification', 'created_by',
            )
        }),
        ('Approche LEAP', {
            'fields': (
                ('leap_locate_status', 'leap_locate_notes'),
                ('leap_evaluate_status', 'leap_evaluate_notes'),
                ('leap_assess_status', 'leap_assess_notes'),
            )
        }),
    )

@admin.register(Carbon_emission)
class CarbonEmissionAdmin(admin.ModelAdmin):
    search_fields = ('company__name',)
    list_display = ('company', 'year','scope', 'carbon_emission')
    list_filter = ('year',)
    autocomplete_fields = ('company',)


@admin.register(ImpactMethod)
class ImpactMethodAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    list_display = ('name', 'version')


@admin.register(ImpactCategory)
class ImpactCategoryAdmin(admin.ModelAdmin):
    search_fields = ('key', 'name')
    list_display = ('key', 'method', 'level', 'theme')
    list_filter = ('method', 'level')
    autocomplete_fields = ('method',)


@admin.register(CharacterizationFactor)
class CharacterizationFactorAdmin(admin.ModelAdmin):
    search_fields = ('commodity__name', 'category__key')
    list_display = ('commodity', 'category', 'region', 'country', 'value')
    list_filter = ('category__method', 'category__level')
    autocomplete_fields = ('category', 'commodity', 'region', 'country')


def _endpoint_label(flow, side):
    """Libellé d'une extrémité : lieu ou entreprise, « Milieu », ou « — » si vide."""
    if getattr(flow, f'{side}_environment'):
        return 'Milieu'
    for suffix in ('asset', 'region', 'country', 'company'):
        target = getattr(flow, f'{side}_{suffix}')
        if target is not None:
            return str(target)
    return '—'


@admin.register(Flow)
class FlowAdmin(admin.ModelAdmin):
    search_fields = (
        'what__name', 'from_asset__name', 'from_company__name',
        'to_asset__name', 'to_company__name',
    )
    list_display = ('kind', 'what', 'scope', 'origin', 'destination', 'year', 'quantity')
    list_filter = ('kind', 'scope', 'year', 'tier')
    autocomplete_fields = (
        'what', 'from_asset', 'from_region', 'from_country', 'from_company',
        'to_asset', 'to_region', 'to_country', 'to_company',
    )
    fieldsets = (
        (None, {'fields': (
            'kind', 'what', 'scope', 'year', 'quantity', 'tier', 'estimated_revenue',
            'source', 'reference',
        )}),
        ('Origine', {'fields': (
            'from_asset', 'from_region', 'from_country', 'from_company', 'from_environment',
        )}),
        ('Destination', {'fields': (
            'to_asset', 'to_region', 'to_country', 'to_company', 'to_environment',
        )}),
    )

    @admin.display(description='Origine')
    def origin(self, obj):
        return _endpoint_label(obj, 'from')

    @admin.display(description='Destination')
    def destination(self, obj):
        return _endpoint_label(obj, 'to')

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class ScenarioVariableInline(admin.TabularInline):
    model = ScenarioVariable
    extra = 0


@admin.register(ClimateScenario)
class ClimateScenarioAdmin(admin.ModelAdmin):
    search_fields = ('key', 'name')
    list_display = ('name', 'key', 'family', 'warming_c', 'order')
    list_filter = ('family',)
    ordering = ('order', 'key')
    inlines = (ScenarioVariableInline,)


@admin.register(ScenarioVariable)
class ScenarioVariableAdmin(admin.ModelAdmin):
    search_fields = ('scenario__key', 'scenario__name')
    list_display = ('scenario', 'key', 'year', 'value')
    list_filter = ('key', 'year', 'scenario')
    autocomplete_fields = ('scenario',)


@admin.register(SectorCreditProfile)
class SectorCreditProfileAdmin(admin.ModelAdmin):
    search_fields = ('sector__name', 'sector__NACE_code')
    list_display = ('sector', 'pd_baseline', 'ebitda_margin',
                    'ebitda_volatility', 'carbon_pass_through')
    autocomplete_fields = ('sector',)


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    search_fields = ('code', 'name')
    list_display = ('code', 'name', 'symbol', 'ratio_USD')


@admin.register(ESG_data)
class ESGDataAdmin(admin.ModelAdmin):
    search_fields = ('company__name',)
    list_display = ('company', 'year', 'employees_number')
    list_filter = ('year',)
    autocomplete_fields = ('company',)
