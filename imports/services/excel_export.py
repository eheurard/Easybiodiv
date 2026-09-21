"""Export de la table Flow au format de la feuille « Flow » de l'import.

Le classeur produit se réimporte tel quel : mêmes colonnes, mêmes vocabulaires
d'extrémité (`milieu`, vide = inconnu), mêmes noms de commodité et de lieu que
ceux que le parseur sait résoudre.

Les extrémités étant désignées par leur nom, la base d'arrivée doit déjà
connaître les entreprises, actifs, régions, pays et commodités cités : l'export
ne transporte que les flux.
"""
import io

import openpyxl
from django.db.models import Q

from dashboard.models import ENDPOINT_ENVIRONMENT, Asset, Flow

from .constants import SHEET_COLUMNS
from .excel_template import write_header

FLOW_COLUMNS = SHEET_COLUMNS['Flow']


def flows_of(companies):
    """Flux rattachés à ces entreprises : ceux qu'elles déclarent elles-mêmes et
    ceux qui partent de leurs actifs ou y arrivent. Sans entreprise, tous."""
    queryset = Flow.objects.select_related(
        'what', 'from_asset', 'from_region', 'from_country', 'from_company',
        'to_asset', 'to_region', 'to_country', 'to_company',
    ).order_by('pk')
    if not companies:
        return queryset
    condition = Q()
    for company in companies:
        owned = Asset.objects.owned_by(company).values('pk')
        condition |= (
            Q(from_company=company) | Q(to_company=company)
            | Q(from_asset__in=owned) | Q(to_asset__in=owned)
        )
    return queryset.filter(condition).distinct()


def _endpoint(flow, side):
    """(type, nom) d'une extrémité, dans le vocabulaire du classeur."""
    endpoint = flow.origin_type if side == 'from' else flow.destination_type
    if endpoint is None:
        return '', ''
    if endpoint == ENDPOINT_ENVIRONMENT:
        return 'milieu', ''
    return endpoint, getattr(flow, f'{side}_{endpoint}').name


def flow_row(flow):
    from_type, from_name = _endpoint(flow, 'from')
    to_type, to_name = _endpoint(flow, 'to')
    return {
        'kind': flow.kind,
        'what': flow.what.name,
        'scope': flow.scope,
        'from_type': from_type,
        'from_name': from_name,
        'to_type': to_type,
        'to_name': to_name,
        'year': flow.year,
        'quantity': flow.quantity,
        'tier': flow.tier,
        'estimated_revenue': flow.estimated_revenue,
        'source': flow.source,
        'reference': flow.reference,
    }


def build_flow_export(companies=None):
    """Classeur à une seule feuille « Flow ». Renvoie (buffer, nombre de lignes)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Flow'
    write_header(ws, FLOW_COLUMNS)

    count = 0
    for flow in flows_of(companies or []):
        row = flow_row(flow)
        ws.append([row[column] for column in FLOW_COLUMNS])
        count += 1

    ws.freeze_panes = 'A2'
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer, count
