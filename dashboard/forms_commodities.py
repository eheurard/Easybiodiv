from django import forms
from django.forms import inlineformset_factory

from .models import Commodity, CommoditySource

DEPENDENCY_FIELDS = (
    'dependency_water', 'dependency_pollination', 'dependency_soil_quality',
    'dependency_carbon_sequestration', 'dependency_water_purification',
    'dependency_pest_control',
)


class CommodityIdentityForm(forms.ModelForm):
    """Identité d'une commodité. La clé technique n'est jamais éditable."""

    class Meta:
        model = Commodity
        fields = ('name', 'unit', 'description', 'biodiversity_loss_class') + DEPENDENCY_FIELDS
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit'].required = False
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                'class', 'form-input')

    def clean_unit(self):
        return (self.cleaned_data.get('unit') or '').strip() or 'tonnes'

    @property
    def main_fields(self):
        return [self[name] for name in self.fields if name not in DEPENDENCY_FIELDS]

    @property
    def dependency_fields(self):
        return [self[name] for name in DEPENDENCY_FIELDS]

    @property
    def dependency_display(self):
        """Couples (libellé du champ, libellé du choix) pour la lecture seule."""
        return [(self[name].label, getattr(self.instance, f'get_{name}_display')())
                for name in DEPENDENCY_FIELDS]

    @property
    def dependency_has_errors(self):
        return any(name in self.errors for name in DEPENDENCY_FIELDS)


CommoditySourceFormSet = inlineformset_factory(
    Commodity, CommoditySource, fields=('kind', 'title', 'reference'),
    extra=1, can_delete=True,
)
