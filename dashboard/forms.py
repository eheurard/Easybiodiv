"""Formulaires du dashboard.

Toute entrée utilisateur — y compris les query params d'un endpoint GET —
passe par un formulaire, jamais par une lecture brute de `request.GET`.
"""
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import (
    REVENUE_PRODUCTION_ONLY_MESSAGE, Asset, AssetGroup, AssetGroupMember, ClimateScenario,
    Commodity, CommodityModifier, Company, Flow, Ownership, Portfolio, PortfolioHolding,
    invalid_modifiers,
)
from .services.stress_test import HORIZONS, PD_MAX


class StressTestForm(forms.Form):
    """Hypothèses du stress test climatique.

    Tous les champs sont optionnels : un champ absent signifie « valeur par
    défaut du scénario ou du profil sectoriel ».
    """

    scenario = forms.CharField(required=False)
    horizon = forms.TypedChoiceField(
        required=False, coerce=int, empty_value=None,
        choices=[(str(year), str(year)) for year in HORIZONS],
    )
    carbon_price = forms.FloatField(required=False, min_value=0.0)
    include_scope3 = forms.BooleanField(required=False)
    pass_through = forms.FloatField(required=False, min_value=0.0, max_value=1.0)
    ebitda_margin = forms.FloatField(required=False, min_value=0.001, max_value=1.0)
    pd_baseline = forms.FloatField(required=False, min_value=1e-6, max_value=PD_MAX)

    def clean_scenario(self):
        key = (self.cleaned_data.get('scenario') or '').strip()
        if not key:
            return None
        try:
            return ClimateScenario.objects.get(key=key)
        except ClimateScenario.DoesNotExist:
            raise forms.ValidationError(_('Scénario inconnu.'))

    def to_params(self):
        """Dict d'hypothèses consommable par `get_stress_test_data`."""
        data = self.cleaned_data
        return {
            'scenario': data.get('scenario'),
            'horizon': data.get('horizon'),
            'carbon_price': data.get('carbon_price'),
            'include_scope3': bool(data.get('include_scope3')),
            'pass_through': data.get('pass_through'),
            'ebitda_margin': data.get('ebitda_margin'),
            'pd_baseline': data.get('pd_baseline'),
        }


class PortfolioForm(forms.ModelForm):
    """En-tête d'un portefeuille. `is_benchmark` géré à part côté vue."""

    class Meta:
        model = Portfolio
        fields = ['name', 'size', 'currency', 'benchmark']


class PortfolioHoldingForm(forms.ModelForm):
    """Validation d'une ligne de position (bornes du poids, champs obligataires)."""

    class Meta:
        model = PortfolioHolding
        fields = [
            'company', 'amount', 'weight', 'instrument_type',
            'maturity_date', 'coupon_rate', 'face_value',
        ]

    def clean_weight(self):
        weight = self.cleaned_data['weight']
        if weight < 0 or weight > 100:
            raise forms.ValidationError(_('Le poids doit être compris entre 0 et 100.'))
        return weight


YEAR_MIN, YEAR_MAX = 1900, 2100


class FlowMapFlowForm(forms.ModelForm):
    """Création / modification d'un flux depuis la carte des flux.

    Tous les champs d'extrémité figurent dans le formulaire pour que `full_clean`
    valide les `CheckConstraint` du modèle (règles par nature, boucle d'approvisionnement).
    """

    quantity = forms.CharField()
    year = forms.IntegerField(min_value=YEAR_MIN, max_value=YEAR_MAX)
    modifiers = forms.ModelMultipleChoiceField(
        queryset=CommodityModifier.objects.all(), required=False)

    class Meta:
        model = Flow
        fields = [
            'kind', 'what', 'scope', 'modifiers',
            'from_asset', 'from_region', 'from_country', 'from_company', 'from_environment',
            'to_asset', 'to_region', 'to_country', 'to_company', 'to_environment',
            'year', 'quantity', 'tier', 'source', 'reference',
        ]

    def clean_quantity(self):
        raw = str(self.cleaned_data['quantity'])
        text = ''.join(raw.split())
        try:
            if '_' in text:
                raise ValueError(text)
            value = float(text.replace(',', '.'))
        except ValueError:
            raise forms.ValidationError(_('Quantité invalide.'))
        if value != value or value in (float('inf'), float('-inf')):
            raise forms.ValidationError(_('Quantité invalide.'))
        if value <= 0:
            raise forms.ValidationError(_('La quantité doit être positive.'))
        return value

    def clean(self):
        cleaned = super().clean()
        if (self.instance.pk and self.instance.estimated_revenue is not None
                and cleaned.get('kind') != Flow.Kind.PRODUCTION):
            raise forms.ValidationError(REVENUE_PRODUCTION_ONLY_MESSAGE)
        what, modifiers = cleaned.get('what'), cleaned.get('modifiers')
        if what is not None and modifiers and invalid_modifiers(what, modifiers):
            self.add_error('modifiers', _("Ce modificateur n'appartient pas à cette commodité."))
        return cleaned


class AssetQuickForm(forms.ModelForm):
    """Création rapide d'un actif depuis la carte des flux."""

    class Meta:
        model = Asset
        fields = ['name', 'country', 'subnational_region', 'type', 'latitude', 'longitude']

    def clean_latitude(self):
        value = self.cleaned_data['latitude']
        if not -90 <= value <= 90:
            raise forms.ValidationError(_('La latitude doit être comprise entre -90 et 90.'))
        return value

    def clean_longitude(self):
        value = self.cleaned_data['longitude']
        if not -180 <= value <= 180:
            raise forms.ValidationError(
                _('La longitude doit être comprise entre -180 et 180.'))
        return value


class CompanyQuickForm(forms.ModelForm):
    """Création rapide d'une entreprise : ISIN et ticker facultatifs (défaut du modèle)."""

    isin = forms.CharField(required=False, max_length=255)
    ticker = forms.CharField(required=False, max_length=255)

    class Meta:
        model = Company
        fields = ['name', 'isin', 'ticker']

    def clean_isin(self):
        return self.cleaned_data['isin'].strip() or '0'

    def clean_ticker(self):
        return self.cleaned_data['ticker'].strip() or '0'


class CommodityQuickForm(forms.ModelForm):
    """Création rapide d'une commodité : unité facultative (défaut « tonnes »)."""

    unit = forms.CharField(required=False, max_length=255)

    class Meta:
        model = Commodity
        fields = ['name', 'unit']

    def clean_unit(self):
        return self.cleaned_data['unit'].strip() or 'tonnes'


class OwnershipQuickForm(forms.ModelForm):
    """Détention créée depuis la carte : débute à `start_year`, sans année de fin.

    `Ownership.clean` (chevauchement, somme des parts) est appelé par le ModelForm.
    """

    start_year = forms.IntegerField(min_value=YEAR_MIN, max_value=YEAR_MAX)

    class Meta:
        model = Ownership
        fields = ['company', 'asset', 'share', 'start_year']


class StrictYearField(forms.Field):
    """Année donnée comme un vrai entier JSON (ni chaîne, ni décimal, ni booléen)
    entre YEAR_MIN et YEAR_MAX."""

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise forms.ValidationError(_('Année invalide.'), code='invalid')
        if not YEAR_MIN <= value <= YEAR_MAX:
            raise forms.ValidationError(_('Année invalide.'), code='invalid')
        return value


class YearListField(forms.Field):
    """Liste d'années (entiers stricts) ; une valeur absente donne une liste vide."""

    def to_python(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise forms.ValidationError(_('Année invalide.'), code='invalid')
        year_field = StrictYearField(required=True)
        return [year_field.clean(year) for year in value]

    def validate(self, value):
        if self.required and not value:
            raise forms.ValidationError(_('Choisissez au moins une année.'), code='required')


class FlowYearsDeleteForm(forms.Form):
    """Corps de la suppression d'un flux : plage de la carte et années cochées."""

    start = StrictYearField()
    end = StrictYearField()
    years = YearListField()

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('start'), cleaned.get('end')
        if start is not None and end is not None and start > end:
            self.add_error('end', _('La fin de la plage doit suivre son début.'))
        return cleaned


class UnlinkForm(forms.Form):
    """Corps du retrait des liens d'un bloc : années de flux et fin de détention."""

    years = YearListField(required=False)
    ownership_year = StrictYearField(required=False)


class AssetGroupForm(forms.ModelForm):
    """Groupe d'actifs d'une entreprise ; un actif n'est membre que d'un groupe."""

    members = forms.ModelMultipleChoiceField(queryset=Asset.objects.all(), required=False)

    class Meta:
        model = AssetGroup
        fields = ['name']

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company

    def clean_members(self):
        assets = self.cleaned_data['members']
        taken = AssetGroupMember.objects.filter(
            company=self.company, asset__in=assets,
        ).exclude(group=self.instance.pk).select_related('group', 'asset')
        for member in taken:
            raise forms.ValidationError(
                _('« %(asset)s » appartient déjà au groupe « %(group)s ».'),
                params={'asset': member.asset.name, 'group': member.group.name},
            )
        return assets
