"""Écriture des flux depuis la carte interactive (JSON, Créateurs uniquement)."""
import json

from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .decorators import creator_required_json
from .forms import FlowMapFlowForm
from .models import Flow
from .services.flow_map import endpoint_fields

ENDPOINT_FIELDS = [
    f'{side}_{suffix}'
    for side in ('from', 'to')
    for suffix in ('asset', 'region', 'country', 'company', 'environment')
]


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


def _save(form):
    if not form.is_valid():
        return JsonResponse({'errors': {
        field: [str(message) for message in messages]
        for field, messages in form.errors.items()
    }}, status=400)
    return None


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
    refused = _save(form)
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
    refused = _save(form)
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
