"""Formulaires du dashboard.

Toute entrée utilisateur — y compris les query params d'un endpoint GET —
passe par un formulaire, jamais par une lecture brute de `request.GET`.
"""
from django import forms

from .models import ClimateScenario
from .services.stress_test import HORIZONS


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
    pd_baseline = forms.FloatField(required=False, min_value=1e-6, max_value=0.999)

    def clean_scenario(self):
        key = (self.cleaned_data.get('scenario') or '').strip()
        if not key:
            return None
        try:
            return ClimateScenario.objects.get(key=key)
        except ClimateScenario.DoesNotExist:
            raise forms.ValidationError('Scénario inconnu.')

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
