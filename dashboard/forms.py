"""Formulaires du dashboard.

Toute entrée utilisateur — y compris les query params d'un endpoint GET —
passe par un formulaire, jamais par une lecture brute de `request.GET`.
"""
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import ClimateScenario, Flow, Portfolio, PortfolioHolding
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


class FlowMapFlowForm(forms.ModelForm):
    """Création / modification d'un flux depuis la carte des flux.

    Tous les champs d'extrémité figurent dans le formulaire pour que `full_clean`
    valide les `CheckConstraint` du modèle (règles par nature, boucle d'approvisionnement).
    """

    quantity = forms.CharField()

    class Meta:
        model = Flow
        fields = [
            'kind', 'what', 'scope',
            'from_asset', 'from_region', 'from_country', 'from_company', 'from_environment',
            'to_asset', 'to_region', 'to_country', 'to_company', 'to_environment',
            'year', 'quantity', 'tier', 'source', 'reference',
        ]

    def clean_quantity(self):
        raw = str(self.cleaned_data['quantity'])
        text = ''.join(raw.split()).replace(' ', '').replace(' ', '')
        try:
            value = float(text.replace(',', '.'))
        except ValueError:
            raise forms.ValidationError(_('Quantité invalide.'))
        if value != value or value in (float('inf'), float('-inf')):
            raise forms.ValidationError(_('Quantité invalide.'))
        if value <= 0:
            raise forms.ValidationError(_('La quantité doit être positive.'))
        return value
