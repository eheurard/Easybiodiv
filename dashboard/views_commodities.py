"""Page Commodités : liste, création et fiche (identité, sources)."""
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .decorators import creator_required
from .forms_commodities import (
    CommodityIdentityForm, CommodityModifierForm, CommoditySourceFormSet, FactorGridForm,
    ModifierEffectFormSet, format_factor, impact_category_choices,
)
from .models import (
    Commodity, CommodityModifier, Country, ImpactCategory, SubnationalRegion,
    source_codes,
)
from .services.commodity_sheet import (
    location_chips, location_key, modifier_cards, parse_location, save_factors, sheet_kpis,
)

SOURCES_PREFIX = 'sources'
NEW_MODIFIER = 'new'


def _modifier_forms(commodity, modifier, data=None, category_choices=None):
    """Formulaire et formset d'un modificateur (`modifier` sans pk = création)."""
    key = modifier.pk or NEW_MODIFIER
    form = CommodityModifierForm(commodity, data, instance=modifier, prefix=f'mod-{key}')
    formset = ModifierEffectFormSet(
        data, instance=modifier, prefix=f'effects-{key}',
        form_kwargs={'category_choices': category_choices})
    return form, formset


def _can_edit(user):
    return user.is_authenticated and user.role == 'CREATOR'


def _detail_url(commodity, request):
    """URL de la fiche, en conservant le lieu (`?lieu=`) courant."""
    url = redirect('dashboard:commodity_detail', pk=commodity.pk).url
    lieu = request.GET.get('lieu', '')
    return f'{url}?{urlencode({"lieu": lieu})}' if lieu else url


def _location_options():
    """Sélecteur « + pays ou région » : pays, puis régions groupées par pays."""
    countries = [(f'country-{c.pk}', c.name) for c in Country.objects.order_by('name')]
    groups = {}
    regions = SubnationalRegion.objects.select_related('country').order_by(
        'country__name', 'name')
    for region in regions:
        groups.setdefault(region.country.name, []).append(
            (f'region-{region.pk}', region.name))
    return countries, list(groups.items())


def _detail_context(request, commodity, *, identity_form=None, source_formset=None,
                    factor_form=None, modifier_forms=None):
    """Contexte de la fiche. `modifier_forms` : `(modificateur, form, formset)` en erreur."""
    codes = source_codes(commodity)
    sources = list(commodity.sources.all())
    for source in sources:
        source.code = codes.get(source.pk, '')
    source_formset = source_formset or CommoditySourceFormSet(
        instance=commodity, prefix=SOURCES_PREFIX)
    for form in source_formset:
        form.code = codes.get(form.instance.pk, '')
    location = parse_location(request.GET.get('lieu') or request.POST.get('lieu'))
    factor_form = factor_form or FactorGridForm(commodity, location)
    countries, region_groups = _location_options()
    can_edit = _can_edit(request.user)
    cards = modifier_cards(commodity, location)
    for card in cards:
        card['dialog_id'] = f'modifier-dialog-{card["modifier"].pk}'
        for item in card['effects']:
            percent = item['effect'].percent
            item['percent_display'] = (
                ('+' if percent > 0 else '−' if percent < 0 else '')
                + format_factor(abs(percent)))
            item['adjusted_display'] = format_factor(item['adjusted'])
            item['is_endpoint'] = item['level'] == ImpactCategory.Level.ENDPOINT
    failed = modifier_forms[0].pk if modifier_forms else None
    new_has_errors = bool(modifier_forms) and failed is None
    choices = impact_category_choices()
    new_form, new_formset = (
        modifier_forms[1:] if new_has_errors
        else _modifier_forms(commodity, CommodityModifier(commodity=commodity),
                             category_choices=choices))
    if can_edit:
        for card in cards:
            if modifier_forms and failed == card['modifier'].pk:
                card['form'], card['formset'] = modifier_forms[1:]
                card['has_errors'] = True
            else:
                card['form'], card['formset'] = _modifier_forms(
                    commodity, card['modifier'], category_choices=choices)
    factor_blocks = factor_form.bound_blocks()
    identity_form = identity_form or CommodityIdentityForm(instance=commodity)
    chips = location_chips(commodity, location)
    return {
        'kpis': sheet_kpis(commodity, factor_blocks, len(cards)),
        # Facteur résolu (propre, sinon hérité) par catégorie : aperçu de la modale.
        'resolved_factors': {
            str(row['category'].pk): (row['value'] if row['value'] is not None
                                      else row['inherited'])
            for block in factor_blocks for row in block['rows']},
        'identity_editing': identity_form.is_bound and bool(identity_form.errors),
        'sources_editing': source_formset.is_bound and not source_formset.is_valid(),
        'modifier_cards': cards,
        'new_modifier_form': new_form,
        'new_effects_formset': new_formset,
        'new_modifier_has_errors': new_has_errors,
        'commodity': commodity,
        'can_edit': can_edit,
        'lieu': request.GET.get('lieu', ''),
        'location': location,
        'location_key': location_key(location),
        'chips': chips,
        'location_label': next((c['label'] for c in chips if c['active']), _('Global')),
        'factor_form': factor_form,
        'factor_blocks': factor_blocks,
        'location_countries': countries,
        'location_region_groups': region_groups,
        'identity_form': identity_form,
        'source_formset': source_formset,
        'source_codes': codes,
        'sources': sources,
    }


def _render_detail(request, commodity, **forms):
    return render(request, 'dashboard/commodity_detail.html',
                  _detail_context(request, commodity, **forms))


@login_required
@require_GET
def commodity_list(request):
    query = request.GET.get('q', '').strip()
    commodities = Commodity.objects.order_by('name').annotate(
        factor_count=Count('cfs', distinct=True),
        modifier_count=Count('modifiers', distinct=True),
    )
    if query:
        commodities = commodities.filter(name__icontains=query)
    rows = [{'commodity': c, 'factor_count': c.factor_count,
             'modifier_count': c.modifier_count} for c in commodities]
    return render(request, 'dashboard/commodity_list.html', {
        'rows': rows, 'q': query, 'can_edit': _can_edit(request.user),
    })


@creator_required
@require_http_methods(['GET', 'POST'])
def commodity_create(request):
    form = CommodityIdentityForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        commodity = form.save()
        return redirect('dashboard:commodity_detail', pk=commodity.pk)
    return render(request, 'dashboard/commodity_form.html', {'form': form})


@login_required
@require_GET
def commodity_detail(request, pk):
    return _render_detail(request, get_object_or_404(Commodity, pk=pk))


@creator_required
@require_POST
def commodity_identity(request, pk):
    commodity = get_object_or_404(Commodity, pk=pk)
    form = CommodityIdentityForm(request.POST, instance=commodity)
    if form.is_valid():
        form.save()
        return redirect(_detail_url(commodity, request))
    # L'instance du formulaire invalide a été modifiée en mémoire : on repart de la base.
    return _render_detail(request, Commodity.objects.get(pk=pk), identity_form=form)


@creator_required
@require_POST
def commodity_sources(request, pk):
    commodity = get_object_or_404(Commodity, pk=pk)
    formset = CommoditySourceFormSet(request.POST, instance=commodity, prefix=SOURCES_PREFIX)
    if formset.is_valid():
        for source in formset.save(commit=False):
            if source.pk is None:
                source.created_by = request.user
            source.save()
        for source in formset.deleted_objects:
            source.delete()
        return redirect(_detail_url(commodity, request))
    return _render_detail(request, commodity, source_formset=formset)


@creator_required
@require_POST
def commodity_factors(request, pk):
    commodity = get_object_or_404(Commodity, pk=pk)
    location = parse_location(request.POST.get('lieu'))
    form = FactorGridForm(commodity, location, request.POST)
    if form.is_valid():
        save_factors(commodity, location, form.cleaned_data['factors'], request.user)
        url = redirect('dashboard:commodity_detail', pk=commodity.pk).url
        key = location_key(location)
        return redirect(f'{url}?{urlencode({"lieu": key})}' if key != 'global' else url)
    return _render_detail(request, commodity, factor_form=form)


def _modifier_submit(request, commodity, modifier):
    form, formset = _modifier_forms(commodity, modifier, request.POST)
    if form.is_valid() and formset.is_valid():
        was_new = modifier.pk is None
        try:
            with transaction.atomic():
                if was_new:
                    modifier.created_by = request.user
                modifier = form.save()
                formset.instance = modifier
                changed = formset.save(commit=False)
                # Suppressions d'abord : (modificateur, catégorie) est unique.
                for effect in formset.deleted_objects:
                    effect.delete()
                for effect in changed:
                    if effect.pk is None:
                        effect.created_by = request.user
                    effect.save()
            return redirect(_detail_url(commodity, request))
        except IntegrityError:
            if was_new:
                modifier.pk = None
            form.add_error(None, _(
                "Deux effets ne peuvent pas porter sur la même catégorie d'impact."))
    # Les instances invalides ont été modifiées en mémoire : on repart de la base.
    fresh = Commodity.objects.get(pk=commodity.pk)
    return _render_detail(request, fresh, modifier_forms=(modifier, form, formset))


@creator_required
@require_POST
def commodity_modifier_create(request, pk):
    commodity = get_object_or_404(Commodity, pk=pk)
    return _modifier_submit(request, commodity, CommodityModifier(commodity=commodity))


@creator_required
@require_POST
def commodity_modifier_update(request, pk, mpk):
    commodity = get_object_or_404(Commodity, pk=pk)
    modifier = get_object_or_404(CommodityModifier, pk=mpk, commodity=commodity)
    return _modifier_submit(request, commodity, modifier)


@creator_required
@require_POST
def commodity_modifier_delete(request, pk, mpk):
    commodity = get_object_or_404(Commodity, pk=pk)
    get_object_or_404(CommodityModifier, pk=mpk, commodity=commodity).delete()
    return redirect(_detail_url(commodity, request))
