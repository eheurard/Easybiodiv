"""Page Commodités : liste, création et fiche (identité, sources)."""
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .decorators import creator_required
from .forms_commodities import (
    CommodityIdentityForm, CommoditySourceFormSet, FactorGridForm,
)
from .models import Commodity, Country, SubnationalRegion, source_codes
from .services.commodity_sheet import (
    location_chips, location_key, parse_location, save_factors,
)

SOURCES_PREFIX = 'sources'


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
                    factor_form=None):
    """Contexte de la fiche ; la tâche suivante y ajoute les modificateurs."""
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
    return {
        'commodity': commodity,
        'can_edit': _can_edit(request.user),
        'lieu': request.GET.get('lieu', ''),
        'location': location,
        'location_key': location_key(location),
        'chips': location_chips(commodity, location),
        'factor_form': factor_form,
        'factor_blocks': factor_form.bound_blocks(),
        'location_countries': countries,
        'location_region_groups': region_groups,
        'identity_form': identity_form or CommodityIdentityForm(instance=commodity),
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
