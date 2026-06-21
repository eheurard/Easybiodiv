from django import forms

from .models import Portfolio, PortfolioHolding


class PortfolioForm(forms.ModelForm):
    class Meta:
        model = Portfolio
        fields = ['name', 'size', 'currency', 'benchmark']


class PortfolioHoldingForm(forms.ModelForm):
    class Meta:
        model = PortfolioHolding
        fields = [
            'company', 'amount', 'weight', 'instrument_type',
            'maturity_date', 'coupon_rate', 'face_value',
        ]

    def clean_weight(self):
        weight = self.cleaned_data['weight']
        if weight < 0 or weight > 100:
            raise forms.ValidationError('Le poids doit être compris entre 0 et 100.')
        return weight
