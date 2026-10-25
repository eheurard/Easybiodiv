from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from django.utils.formats import number_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from .models import (
    Commodity, CommodityModifier, CommoditySource, ImpactCategory, ModifierEffect,
    source_codes,
)
from .services.commodity_sheet import factor_rows

def format_factor(value):
    """Facteur en 6 chiffres significatifs, séparateur localisé, sans exposant."""
    if value is None:
        return ''
    number = Decimal(format(value, '.6g'))
    return number_format(number, use_l10n=True, force_grouping=True)


DEPENDENCY_FIELDS = (
    'dependency_water', 'dependency_pollination', 'dependency_soil_quality',
    'dependency_carbon_sequestration', 'dependency_water_purification',
    'dependency_pest_control',
)


# Libellés traduits (msgid en français) : les verbose_name du modèle sont du français brut
# et les codes de DEPENDENCY_CHOICES des mots anglais ; les codes stockés ne changent pas.
DEPENDENCY_LABELS = {
    'VL': _l('Très faible'), 'L': _l('Faible'), 'M': _l('Moyen'),
    'H': _l('Fort'), 'VH': _l('Très fort'),
}
LOSS_CLASS_LABELS = {
    'Agriculture': _l('Agriculture'),
    'Urbanisation': _l('Urbanisation'),
    'Mining': _l('Extraction minière'),
}
DEPENDENCY_FIELD_LABELS = {
    'dependency_water': _l('Dépendance — approvisionnement en eau'),
    'dependency_pollination': _l('Dépendance — pollinisation'),
    'dependency_soil_quality': _l('Dépendance — qualité des sols'),
    'dependency_carbon_sequestration': _l('Dépendance — séquestration carbone'),
    'dependency_water_purification': _l("Dépendance — épuration de l'eau"),
    'dependency_pest_control': _l('Dépendance — contrôle des ravageurs'),
}


class CommodityIdentityForm(forms.ModelForm):
    """Identité d'une commodité. La clé technique n'est jamais éditable."""

    class Meta:
        model = Commodity
        fields = ('name', 'unit', 'description', 'biodiversity_loss_class') + DEPENDENCY_FIELDS
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}
        labels = {
            'name': _l('Nom'),
            'unit': _l('Unité de mesure'),
            'description': _l('Description'),
            'biodiversity_loss_class': _l(
                'Classe de perte de biodiversité pour le calcul de dette biodiversité'),
            **DEPENDENCY_FIELD_LABELS,
        }
        help_texts = {
            'unit': _l(
                'Unité dans laquelle les productions et les échanges de cette '
                'commodité sont exprimés (par défaut : tonnes).'),
            'biodiversity_loss_class': _l(
                'Détermine lequel des trois taux de perte du pays s’applique : '
                'agriculture, urbanisation ou extraction minière.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit'].required = False
        for name in DEPENDENCY_FIELDS:
            self.fields[name].choices = list(DEPENDENCY_LABELS.items())
        self.fields['biodiversity_loss_class'].choices = list(LOSS_CLASS_LABELS.items())
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
        return [(self[name].label,
                 DEPENDENCY_LABELS.get(getattr(self.instance, name), getattr(self.instance, name)))
                for name in DEPENDENCY_FIELDS]

    @property
    def biodiversity_loss_display(self):
        value = self.instance.biodiversity_loss_class
        return LOSS_CLASS_LABELS.get(value, value)

    @property
    def dependency_has_errors(self):
        return any(name in self.errors for name in DEPENDENCY_FIELDS)


CommoditySourceFormSet = inlineformset_factory(
    Commodity, CommoditySource, fields=('kind', 'title', 'reference'),
    extra=1, can_delete=True,
)


class FactorGridForm(forms.Form):
    """Grille de facteurs d'un lieu : `value_<cat>` et `source_<cat>` par catégorie."""

    def __init__(self, commodity, location, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commodity = commodity
        self.location = location
        self.blocks = []
        self.codes = source_codes(commodity)
        sources = [('', '—')] + [(str(pk), code) for pk, code in self.codes.items()]
        for level in (ImpactCategory.Level.MIDPOINT, ImpactCategory.Level.ENDPOINT):
            rows = factor_rows(commodity, location, level)
            for row in rows:
                pk = row['category'].pk
                self.fields[f'value_{pk}'] = forms.CharField(
                    required=False, label=row['category'].name,
                    widget=forms.TextInput(attrs={
                        'class': 'form-input', 'inputmode': 'decimal'}))
                self.fields[f'source_{pk}'] = forms.ChoiceField(
                    required=False, choices=sources, label=_('Source'),
                    widget=forms.Select(attrs={'class': 'form-input'}))
                self.initial[f'value_{pk}'] = (
                    '' if row['value'] is None else format(row['value'], '.12g'))
                self.initial[f'source_{pk}'] = str(row['source_id'] or '')
            self.blocks.append({'level': level, 'rows': rows})

    def bound_blocks(self):
        """Blocs (midpoint, endpoint) avec les champs liés de chaque ligne."""
        return [{
            'level': block['level'],
            'is_endpoint': block['level'] == ImpactCategory.Level.ENDPOINT,
            'title': ImpactCategory.Level(block['level']).label,
            'rows': [dict(row, value_display=format_factor(row['value']),
                          inherited_display=format_factor(row['inherited']),
                          value_field=self[f'value_{row["category"].pk}'],
                          source_field=self[f'source_{row["category"].pk}'],
                          source_code=self.codes.get(row['source_id'], ''))
                     for row in block['rows']],
        } for block in self.blocks]

    @staticmethod
    def _parse_number(raw):
        text = ''.join(str(raw or '').split())
        if not text:
            return None
        try:
            if '_' in text:
                raise ValueError(text)
            value = float(text.replace(',', '.'))
        except ValueError:
            raise forms.ValidationError(_('Facteur invalide.'))
        if value != value or value in (float('inf'), float('-inf')):
            raise forms.ValidationError(_('Facteur invalide.'))
        return value

    def clean(self):
        cleaned = super().clean()
        factors = {}
        for name in list(self.fields):
            if not name.startswith('value_'):
                continue
            pk = int(name.split('_', 1)[1])
            try:
                value = self._parse_number(self.data.get(self.add_prefix(name)))
            except forms.ValidationError as error:
                self.add_error(name, error)
                continue
            source = cleaned.get(f'source_{pk}') or None
            factors[pk] = (value, int(source) if source else None)
        cleaned['factors'] = factors
        return cleaned


class CommodityModifierForm(forms.ModelForm):
    """Nom, description et source d'un modificateur ; la commodité est fixée par la vue."""

    class Meta:
        model = CommodityModifier
        fields = ('name', 'description', 'source')
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, commodity, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.commodity = commodity
        self.fields['source'].queryset = CommoditySource.objects.filter(commodity=commodity)
        self.fields['source'].empty_label = '—'
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-input')

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        duplicates = CommodityModifier.objects.filter(
            commodity=self.instance.commodity, name=name).exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError(
                _('Un modificateur porte déjà ce nom pour cette commodité.'))
        return name


def impact_category_choices():
    """Choix de catégorie d'impact, groupés par niveau, sans lire la méthode."""
    groups = {}
    for pk, name, level in ImpactCategory.objects.order_by('level', 'pk').values_list(
            'pk', 'name', 'level'):
        groups.setdefault(level, []).append((pk, name))
    return [('', '---------')] + [
        (str(ImpactCategory.Level(level).label), options)
        for level, options in groups.items()]


class ModifierEffectForm(forms.ModelForm):
    """Effet en % ; `percent` accepte la virgule décimale et les espaces."""

    percent = forms.CharField(label=_('Variation (%)'), widget=forms.TextInput(
        attrs={'class': 'form-input commodity-table__num', 'inputmode': 'decimal'}))

    class Meta:
        model = ModifierEffect
        fields = ('category', 'percent')

    def __init__(self, *args, category_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields['category']
        field.widget.attrs.setdefault('class', 'form-input')
        # Choix calculés une fois par page (`category_choices`) : sinon chaque ligne
        # d'effet relirait les catégories et leur méthode.
        field.queryset = ImpactCategory.objects.order_by('level', 'pk')
        field.choices = category_choices if category_choices is not None else (
            impact_category_choices())

    def validate_unique(self):
        # L'unicité (modificateur, catégorie) est vérifiée par le formset, qui ignore les
        # lignes supprimées ; ici, la ligne à supprimer existe encore en base.
        pass

    def validate_constraints(self):
        pass

    def clean_percent(self):
        try:
            value = FactorGridForm._parse_number(self.cleaned_data['percent'])
        except forms.ValidationError:
            raise forms.ValidationError(_('Nombre invalide.'))
        if value is None:
            raise forms.ValidationError(self.fields['percent'].error_messages['required'])
        return value


ModifierEffectFormSet = inlineformset_factory(
    CommodityModifier, ModifierEffect, form=ModifierEffectForm,
    fields=('category', 'percent'), extra=1, can_delete=True,
)
