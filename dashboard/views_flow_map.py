"""Carte interactive des flux : page en lecture, données JSON et écritures
(Créateurs uniquement)."""
import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .decorators import creator_required_json
from .forms import (
    AssetGroupForm, AssetQuickForm, CommodityQuickForm, CompanyQuickForm, FlowMapFlowForm,
    OwnershipQuickForm,
)
from .models import (
    FLOW_RULES, Asset, AssetGroup, Commodity, Company, Country, Flow, FlowKind,
    SubnationalRegion,
)
from .services.flow_map import build_flow_map, endpoint_fields, unlink, unlink_preview

ENDPOINT_FIELDS = [
    f'{side}_{suffix}'
    for side in ('from', 'to')
    for suffix in ('asset', 'region', 'country', 'company', 'environment')
]


# ── Page et données de la carte ──────────────────────────────────────────────

def _flow_rules():
    """FLOW_RULES sérialisable : {nature: {'origins': [...], 'destinations': [...]}},
    une extrémité inconnue valant None (null en JSON)."""
    return {
        kind: {'origins': list(rule.origins), 'destinations': list(rule.destinations)}
        for kind, rule in FLOW_RULES.items()
    }


@require_GET
def flow_map(request):
    """Page Carte des flux, ouverte sur la première entreprise (le JS recharge
    l'entreprise mémorisée si elle diffère)."""
    user = request.user
    companies = list(Company.objects.order_by('name').values('id', 'name'))
    initial_data = None
    if companies:
        first = Company.objects.get(pk=companies[0]['id'])
        initial_data = build_flow_map(first, None, user)
    return render(request, 'dashboard/flow_map.html', {
        'companies': companies,
        'initial_data': initial_data,
        'flow_rules': _flow_rules(),
        'kinds': [{'value': value, 'label': str(label)} for value, label in FlowKind.choices],
        'scopes': [{'value': value, 'label': str(label)} for value, label in Flow.Scope.choices],
        'asset_types': [
            {'value': value, 'label': str(label)}
            for value, label in Asset._meta.get_field('type').choices
        ],
        'can_edit': bool(user.is_authenticated and user.role == 'CREATOR'),
    })


@require_GET
def flow_map_data(request, company_pk):
    """Données de la carte pour une entreprise et `?year=` (absent : année par défaut)."""
    company = get_object_or_404(Company, pk=company_pk)
    year = request.GET.get('year')
    if year in (None, ''):
        year = None
    else:
        try:
            year = int(year)
        except ValueError:
            return JsonResponse({'errors': {'year': [_('Année invalide.')]}}, status=400)
    return JsonResponse(build_flow_map(company, year, request.user))


# ── Écriture des flux ────────────────────────────────────────────────────────

def _error(message, status=400):
    return JsonResponse({'errors': {'__all__': [str(message)]}}, status=status)


def _not_found():
    return _error(_("Ce flux n'existe plus."), status=404)


def _payload(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _form_data(payload, endpoints):
    data = {
        'kind': payload.get('kind'),
        'what': payload.get('what_id'),
        'scope': payload.get('scope') or Flow.Scope.UNDEFINED,
        'year': payload.get('year'),
        'quantity': payload.get('quantity'),
        'tier': payload.get('tier') or 0,
        'source': payload.get('source') or '',
        'reference': payload.get('reference') or '',
    }
    for name, value in endpoints.items():
        if value is not None and value is not False:
            data[name] = value
    return data


def _attname(field):
    return field if field.endswith('_environment') else field + '_id'


def _get_flow(pk):
    try:
        return Flow.objects.get(pk=pk)
    except Flow.DoesNotExist:
        return None


def _form_errors(form):
    """Réponse 400 si le formulaire est invalide, sinon None."""
    if form.is_valid():
        return None
    errors = {
        field: [str(message) for message in messages]
        for field, messages in form.errors.items()
    }
    return JsonResponse({'errors': errors}, status=400)


@require_POST
@creator_required_json
def flow_map_flow_create(request):
    payload = _payload(request)
    if payload is None:
        return _error(_('JSON invalide'))
    endpoints = {}
    try:
        endpoints.update(endpoint_fields('from', payload.get('from')))
        endpoints.update(endpoint_fields('to', payload.get('to')))
    except (ValueError, TypeError):
        return _error(_('Extrémité de flux invalide.'))
    form = FlowMapFlowForm(_form_data(payload, endpoints))
    refused = _form_errors(form)
    if refused:
        return refused
    flow = form.save(commit=False)
    flow.created_by = request.user
    flow.save()
    return JsonResponse({'id': flow.pk}, status=201)


@require_POST
@creator_required_json
def flow_map_flow_update(request, pk):
    flow = _get_flow(pk)
    if flow is None:
        return _not_found()
    payload = _payload(request)
    if payload is None:
        return _error(_('JSON invalide'))
    endpoints = {name: getattr(flow, _attname(name)) for name in ENDPOINT_FIELDS}
    form = FlowMapFlowForm(_form_data(payload, endpoints), instance=flow)
    refused = _form_errors(form)
    if refused:
        return refused
    form.save()
    return JsonResponse({'id': flow.pk})


@require_POST
@creator_required_json
def flow_map_flow_delete(request, pk):
    flow = _get_flow(pk)
    if flow is None:
        return _not_found()
    flow.delete()
    return JsonResponse({'deleted': pk})


# ── Recherche, créations, détentions, groupes, retrait ───────────────────────

SEARCH_LIMIT = 20
SEARCH_MIN_LENGTH = 2
SEARCH_MODELS = {
    'asset': Asset,
    'company': Company,
    'country': Country,
    'region': SubnationalRegion,
    'commodity': Commodity,
}


def _search_detail(kind, obj):
    if kind in ('asset', 'region'):
        return obj.country.name
    if kind == 'commodity':
        return obj.unit
    return ''


def flow_map_search(request):
    kind = request.GET.get('type')
    model = SEARCH_MODELS.get(kind)
    if model is None:
        return _error(_('Type de recherche inconnu.'))
    query = request.GET.get('q', '').strip()
    if len(query) < SEARCH_MIN_LENGTH:
        return JsonResponse({'results': []})
    queryset = model.objects.filter(name__icontains=query).order_by('name', 'pk')
    if kind in ('asset', 'region'):
        queryset = queryset.select_related('country')
    results = [
        {'id': obj.pk, 'name': obj.name, 'detail': _search_detail(kind, obj)}
        for obj in queryset[:SEARCH_LIMIT]
    ]
    return JsonResponse({'results': results})


def _create(request, form_class, answer):
    """Crée un objet depuis le corps JSON ; `answer(obj)` donne la réponse 201."""
    payload = _payload(request)
    if payload is None:
        return _error(_('JSON invalide'))
    form = form_class(payload)
    refused = _form_errors(form)
    if refused:
        return refused
    return JsonResponse(answer(form.save()), status=201)


@require_POST
@creator_required_json
def flow_map_asset_create(request):
    return _create(request, AssetQuickForm, lambda a: {'id': a.pk, 'name': a.name})


@require_POST
@creator_required_json
def flow_map_company_create(request):
    return _create(request, CompanyQuickForm, lambda c: {'id': c.pk, 'name': c.name})


@require_POST
@creator_required_json
def flow_map_commodity_create(request):
    return _create(
        request, CommodityQuickForm,
        lambda c: {'id': c.pk, 'name': c.name, 'unit': c.unit})


@require_POST
@creator_required_json
def flow_map_ownership_create(request):
    payload = _payload(request)
    if payload is None:
        return _error(_('JSON invalide'))
    form = OwnershipQuickForm({
        'company': payload.get('company_id'),
        'asset': payload.get('asset_id'),
        'share': payload.get('share'),
        'start_year': payload.get('year'),
    })
    refused = _form_errors(form)
    if refused:
        return refused
    ownership = form.save(commit=False)
    ownership.created_by = request.user
    ownership.save()
    return JsonResponse({'id': ownership.pk}, status=201)


def _save_group(request, company, instance=None):
    payload = _payload(request)
    if payload is None:
        return _error(_('JSON invalide'))
    members = payload.get('members')
    form = AssetGroupForm(
        {'name': payload.get('name'), 'members': members if isinstance(members, list) else []},
        instance=instance, company=company)
    refused = _form_errors(form)
    if refused:
        return refused
    group = form.save(commit=False)
    if instance is None:
        group.company = company
        group.created_by = request.user
    group.save()
    group.set_members([asset.pk for asset in form.cleaned_data['members']])
    return JsonResponse({'id': group.pk}, status=201 if instance is None else 200)


def _get_group(pk):
    return AssetGroup.objects.filter(pk=pk).select_related('company').first()


@require_POST
@creator_required_json
def flow_map_group_create(request, company_pk):
    company = Company.objects.filter(pk=company_pk).first()
    if company is None:
        return _error(_("Cette entreprise n'existe plus."), status=404)
    return _save_group(request, company)


@require_POST
@creator_required_json
def flow_map_group_update(request, pk):
    group = _get_group(pk)
    if group is None:
        return _error(_("Ce groupe n'existe plus."), status=404)
    return _save_group(request, group.company, instance=group)


@require_POST
@creator_required_json
def flow_map_group_delete(request, pk):
    group = _get_group(pk)
    if group is None:
        return _error(_("Ce groupe n'existe plus."), status=404)
    group.delete()
    return JsonResponse({'deleted': pk})


def _run_unlink(request, action):
    """Applique `action(company, year, key)` aux paramètres `year` et `block`."""
    company = Company.objects.filter(pk=request.resolver_match.kwargs['company_pk']).first()
    if company is None:
        return _error(_("Cette entreprise n'existe plus."), status=404)
    try:
        year = int(request.GET.get('year'))
    except (TypeError, ValueError):
        return _error(_('Année invalide.'))
    try:
        return JsonResponse(action(company, year, request.GET.get('block')))
    except (ValueError, TypeError):
        return _error(_('Bloc invalide.'))


@creator_required_json
def _unlink_apply(request):
    return _run_unlink(request, unlink)


@require_http_methods(['GET', 'POST'])
def flow_map_unlink(request, company_pk):
    """GET : aperçu du retrait (ouvert) ; POST : retrait effectif (Créateur)."""
    if request.method == 'POST':
        return _unlink_apply(request)
    return _run_unlink(request, unlink_preview)
