"""Données de la carte interactive des flux (spec 2026-10-22 §4 et §10).

Blocs, groupes et flux d'une entreprise sur une plage d'années, rangés en colonnes.
Les flux sont lus via dashboard/services/flows.py, seul module qui filtre Flow.

Clés de blocs (contrat partagé avec le JS) : `company:<id>`, `asset:<id>`,
`country:<id>`, `region:<id>`, `group:<id>`, et les deux bandeaux `environment`
(le milieu) et `market` (le marché global : extrémité vide d'un flux, origine ou
destination non localisée).
"""
import datetime
import re
from collections import Counter

from django.db import transaction
from django.utils.translation import gettext

from dashboard.models import (
    _ENDPOINT_FIELD_SUFFIX, ENDPOINT_ASSET, ENDPOINT_COMPANY, ENDPOINT_ENVIRONMENT, Asset,
    Company, Ownership,
)
from dashboard.services.flows import (
    delete_flows, ownerships_in_range, ownerships_overlapping, perimeter_years,
    range_perimeter_flows,
)

ENVIRONMENT_KEY = ENDPOINT_ENVIRONMENT
MARKET_KEY = 'market'
BAND_KEYS = (ENVIRONMENT_KEY, MARKET_KEY)
GROUP_TYPE = 'group'

_SIDES = ('from', 'to')
_KEY_PATTERN = re.compile(
    r'(?P<type>%s):(?P<id>[1-9][0-9]*)'
    % '|'.join(list(_ENDPOINT_FIELD_SUFFIX) + [GROUP_TYPE])
)


def _check_side(side):
    if side not in _SIDES:
        raise ValueError(f'Côté de flux inconnu : {side!r}')


def endpoint_key(flow, side):
    """Clé du bloc à l'extrémité `side` ('from' ou 'to') du flux."""
    _check_side(side)
    if getattr(flow, f'{side}_environment'):
        return ENVIRONMENT_KEY
    for endpoint, suffix in _ENDPOINT_FIELD_SUFFIX.items():
        pk = getattr(flow, f'{side}_{suffix}_id')
        if pk is not None:
            return f'{endpoint}:{pk}'
    return MARKET_KEY


def parse_key(key):
    """'asset:5' → ('asset', 5) ; 'environment' → ('environment', None) ;
    'market' → (None, None). ValueError sinon."""
    if key == ENVIRONMENT_KEY:
        return ENDPOINT_ENVIRONMENT, None
    if key == MARKET_KEY:
        return None, None
    match = _KEY_PATTERN.fullmatch(key)
    if match is None:
        raise ValueError(f'Clé de bloc invalide : {key!r}')
    return match['type'], int(match['id'])


def endpoint_fields(side, key):
    """Champs de formulaire Flow du côté `side` pour le bloc `key`. Un groupe
    n'est pas une extrémité de flux : ValueError."""
    _check_side(side)
    endpoint, pk = parse_key(key)
    if endpoint == GROUP_TYPE:
        raise ValueError(f"Un groupe n'est pas une extrémité de flux : {key!r}")
    fields = {
        f'{side}_{suffix}': pk if candidate == endpoint else None
        for candidate, suffix in _ENDPOINT_FIELD_SUFFIX.items()
    }
    fields[f'{side}_environment'] = endpoint == ENDPOINT_ENVIRONMENT
    return fields


def _acyclic_successors(nodes, edges):
    """Successeurs de chaque nœud, sans les arêtes arrière d'un DFS qui visite
    les nœuds dans l'ordre de `nodes`, et ordre topologique du graphe restant."""
    successors = {node: {} for node in nodes}
    for origin, destination in edges:
        if origin in successors and destination in successors:
            successors[origin][destination] = None
    kept = {node: [] for node in nodes}
    on_stack, done, postorder = set(), set(), []
    for root in nodes:
        if root in done:
            continue
        on_stack.add(root)
        stack = [(root, iter(successors[root]))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                stack.pop()
                on_stack.discard(node)
                done.add(node)
                postorder.append(node)
            elif child in on_stack:
                continue  # arête arrière : retirée pour casser le cycle
            else:
                kept[node].append(child)
                if child not in done:
                    on_stack.add(child)
                    stack.append((child, iter(successors[child])))
    return kept, postorder[::-1]


def assign_columns(nodes, edges):
    """{nœud: colonne} : longueur du plus long chemin qui mène au nœud (sources
    et nœuds isolés en 0). Les arêtes touchant un bandeau (milieu, marché global)
    sont ignorées, les cycles cassés."""
    nodes = [node for node in dict.fromkeys(nodes) if node not in BAND_KEYS]
    successors, order = _acyclic_successors(nodes, edges)
    columns = dict.fromkeys(nodes, 0)
    for node in order:
        for child in successors[node]:
            columns[child] = max(columns[child], columns[node] + 1)
    return columns


def _block(key, block_type, pk, name, owned=False):
    return {
        'key': key, 'type': block_type, 'id': pk, 'name': name, 'owned': owned,
        'group': None, 'column': 0,
    }


def _endpoint_block(flow, side, key):
    """Bloc d'une extrémité extérieure au périmètre, construit depuis le flux."""
    endpoint, pk = parse_key(key)
    target = getattr(flow, f'{side}_{_ENDPOINT_FIELD_SUFFIX[endpoint]}')
    return _block(key, endpoint, pk, target.name)


def _serialize_flow(flow):
    return {
        'id': flow.pk,
        'kind': flow.kind,
        'kind_label': str(flow.get_kind_display()),
        'from': endpoint_key(flow, 'from'),
        'to': endpoint_key(flow, 'to'),
        'what': {'id': flow.what.pk, 'name': flow.what.name, 'unit': flow.what.unit},
        'quantity': flow.quantity,
        'year': flow.year,
        'tier': flow.tier,
        'scope': flow.scope,
        'source': flow.source,
        'reference': flow.reference,
        'modifiers': [{'id': m.pk, 'name': m.name} for m in flow.modifiers.all()],
    }


def flow_key(flow):
    """Identité d'un « même flux » d'une année à l'autre (spec §10.1) : nature,
    commodité, origine, destination, scope et jeu de modificateurs."""
    return (
        flow.kind, flow.what_id, endpoint_key(flow, 'from'), endpoint_key(flow, 'to'),
        flow.scope, tuple(sorted(m.pk for m in flow.modifiers.all())),
    )


def latest_flows(flows):
    """Pour chaque flow_key(), toutes les lignes de son année la plus récente,
    dans l'ordre (année, pk)."""
    latest = {}
    for flow in flows:
        key = flow_key(flow)
        latest[key] = max(latest.get(key, flow.year), flow.year)
    kept = [flow for flow in flows if flow.year == latest[flow_key(flow)]]
    return sorted(kept, key=lambda flow: (flow.year, flow.pk))


def owned_assets_in_range(company, start, end):
    """Actifs détenus par `company` au moins une année de [start, end], par pk."""
    held = ownerships_in_range(company, start, end).values('asset_id')
    return Asset.objects.filter(pk__in=held).order_by('pk')


def _perimeter_blocks(company, owned_assets, flows):
    """Blocs dans l'ordre de rangement : l'entreprise, ses actifs détenus (par
    pk), puis les autres extrémités des flux triées par type et id. Les bandeaux
    (milieu, marché global) ne sont pas des blocs."""
    perimeter = {
        f'{ENDPOINT_COMPANY}:{company.pk}': _block(
            f'{ENDPOINT_COMPANY}:{company.pk}', ENDPOINT_COMPANY, company.pk, company.name,
            owned=True),
    }
    for asset in owned_assets:
        key = f'{ENDPOINT_ASSET}:{asset.pk}'
        perimeter[key] = _block(key, ENDPOINT_ASSET, asset.pk, asset.name, owned=True)
    outside = {}
    for flow in flows:
        for side in _SIDES:
            key = endpoint_key(flow, side)
            if key not in BAND_KEYS and key not in perimeter and key not in outside:
                outside[key] = _endpoint_block(flow, side, key)
    ordered = sorted(outside.values(), key=lambda b: (b['type'], b['id']))
    return list(perimeter.values()) + ordered


def _present_groups(company, blocks):
    """Groupes de l'entreprise ayant au moins un membre parmi les blocs, avec
    ces membres (`members`) et tous les membres du groupe (`all_members`, pour
    que l'édition du groupe conserve ceux absents de la carte) ; marque le
    groupe de chaque bloc membre."""
    groups = []
    for group in company.asset_groups.prefetch_related('members').order_by('pk'):
        group_key = f'{GROUP_TYPE}:{group.pk}'
        all_members = [
            f'{ENDPOINT_ASSET}:{asset_id}'
            for asset_id in sorted(member.asset_id for member in group.members.all())
        ]
        members = [key for key in all_members if key in blocks]
        if not members:
            continue
        for key in members:
            blocks[key]['group'] = group_key
        groups.append({
            'key': group_key, 'id': group.pk, 'name': group.name, 'members': members,
            'all_members': all_members,
            'owned': any(blocks[key]['owned'] for key in members), 'column': 0,
        })
    return groups


def _layout(blocks, groups, flows):
    """Colonnes calculées groupes repliés ; un membre prend la colonne de son groupe."""
    def collapsed(key):
        block = blocks.get(key)
        return block['group'] if block and block['group'] else key

    nodes = [collapsed(key) for key in blocks]
    edges = []
    for flow in flows:
        origin = collapsed(endpoint_key(flow, 'from'))
        destination = collapsed(endpoint_key(flow, 'to'))
        if origin != destination:
            edges.append((origin, destination))
    columns = assign_columns(nodes, edges)
    for key, block in blocks.items():
        block['column'] = columns[collapsed(key)]
    for group in groups:
        group['column'] = columns[group['key']]


def build_flow_map(company, start, end, user):
    """Données de la carte des flux de `company` sur [start, end] (spec §10.1).

    `start` et `end` à None : de la première à la dernière année du périmètre
    ayant des flux, sinon l'année en cours. Un seul des deux à None, ou
    start > end : ValueError. Un même flux présent plusieurs années n'est
    dessiné que pour la plus récente."""
    if (start is None) != (end is None):
        raise ValueError('Plage incomplète : start et end vont ensemble')
    known_years = perimeter_years(company)
    current_year = datetime.date.today().year
    if start is None:
        start = known_years[0] if known_years else current_year
        end = known_years[-1] if known_years else current_year
    if start > end:
        raise ValueError(f'Plage inversée : {start} > {end}')
    flows = latest_flows(range_perimeter_flows(company, start, end))
    owned_assets = owned_assets_in_range(company, start, end)
    blocks = {
        block['key']: block for block in _perimeter_blocks(company, owned_assets, flows)
    }
    groups = _present_groups(company, blocks)
    _layout(blocks, groups, flows)
    return {
        'company': {'id': company.pk, 'name': company.name},
        'start': start,
        'end': end,
        'years': sorted(set(known_years) | {current_year, start, end}),
        'can_edit': bool(user.is_authenticated and user.role == 'CREATOR'),
        'blocks': list(blocks.values()),
        'groups': groups,
        'flows': [_serialize_flow(flow) for flow in flows],
    }


def _check_range(start, end):
    if start > end:
        raise ValueError(f'Plage inversée : {start} > {end}')


def _checked_years(start, end, years):
    """Années demandées, toutes dans [start, end] ; ValueError sinon."""
    _check_range(start, end)
    years = set(years)
    outside = sorted(year for year in years if not start <= year <= end)
    if outside:
        raise ValueError(f'Années hors de la plage {start}–{end} : {outside}')
    return years


def _flow_anchor(flow):
    """(extrémité, pk) d'un côté du flux porté par une clé étrangère, pour
    restreindre la lecture aux flux qui le touchent ; None s'il n'y en a pas."""
    for side in _SIDES:
        endpoint, pk = parse_key(endpoint_key(flow, side))
        if endpoint in _ENDPOINT_FIELD_SUFFIX:
            return endpoint, pk
    return None


def _same_flow_rows(company, start, end, flow):
    """Lignes du périmètre sur [start, end] de même flow_key() que `flow`."""
    key = flow_key(flow)
    candidates = range_perimeter_flows(company, start, end, touching=_flow_anchor(flow))
    return [row for row in candidates if flow_key(row) == key]


def flow_years(company, start, end, flow):
    """[{'year', 'count'}] croissant : années de [start, end] où le même flux que
    `flow` figure dans le périmètre, avec le nombre de lignes (spec §10.3)."""
    _check_range(start, end)
    counts = Counter(row.year for row in _same_flow_rows(company, start, end, flow))
    return [{'year': year, 'count': counts[year]} for year in sorted(counts)]


def delete_flow_years(company, start, end, flow, years):
    """Supprime les lignes du même flux que `flow` des années `years`, parmi celles
    du périmètre sur [start, end] ; renvoie le nombre supprimé. `years` vide ou
    contenant une année hors plage : ValueError, rien n'est supprimé."""
    years = _checked_years(start, end, years)
    if not years:
        raise ValueError('Aucune année à supprimer')
    with transaction.atomic():
        rows = _same_flow_rows(company, start, end, flow)
        return delete_flows([row for row in rows if row.year in years])


def _unlink_target(company, key):
    """(extrémité, pk) du bloc dont on retire les liens ; ValueError pour l'entreprise
    elle-même, un groupe, le milieu ou le marché global."""
    endpoint, pk = parse_key(key)
    if endpoint in (None, ENDPOINT_ENVIRONMENT, GROUP_TYPE):
        raise ValueError(f'Les liens de ce bloc ne peuvent pas être retirés : {key!r}')
    if endpoint == ENDPOINT_COMPANY and pk == company.pk:
        raise ValueError("Les liens de l'entreprise elle-même ne peuvent pas être retirés")
    return endpoint, pk


def _is_owned_in_range(company, start, end, endpoint, pk):
    return (
        endpoint == ENDPOINT_ASSET
        and owned_assets_in_range(company, start, end).filter(pk=pk).exists()
    )


def unlink_preview(company, start, end, key):
    """Effet d'un retrait des liens du bloc `key` sur [start, end] (spec §10.3) :
    années ayant des flux entre ce bloc et le périmètre, avec leur nombre ; si
    l'actif est détenu sur la plage ; année proposée pour la fin de détention ;
    noms des autres entreprises détentrices de l'actif sur la plage."""
    endpoint, pk = _unlink_target(company, key)
    _check_range(start, end)
    counts = Counter(
        flow.year for flow in range_perimeter_flows(company, start, end, touching=(endpoint, pk))
    )
    years = [{'year': year, 'flows': counts[year]} for year in sorted(counts)]
    ownership = _is_owned_in_range(company, start, end, endpoint, pk)
    if not ownership:
        ownership_year = None
    elif years:
        ownership_year = years[0]['year']
    else:
        ownership_year = start
    co_owners = []
    if endpoint == ENDPOINT_ASSET:
        others = ownerships_overlapping(start, end).filter(asset_id=pk).exclude(company=company)
        co_owners = list(
            Company.objects.filter(pk__in=others.values('company_id'))
            .order_by('name').values_list('name', flat=True))
    return {
        'years': years, 'ownership': ownership, 'ownership_year': ownership_year,
        'co_owners': co_owners,
    }


def end_ownership(company, asset, year, until):
    """Met fin à la détention de `asset` par `company` à partir de `year` (spec
    §10.3) : les détentions valides en `year` sont supprimées si elles commencent
    cette année-là, sinon arrêtées en `year` − 1 ; celles qui commencent après
    `year` et au plus tard en `until` sont supprimées ; les suivantes restent."""
    mine = Ownership.objects.filter(company=company, asset=asset)
    with transaction.atomic():
        for ownership in mine.valid_in(year):
            if ownership.start_year == year:
                ownership.delete()
            else:
                ownership.end_year = year - 1
                ownership.save()
        mine.filter(start_year__gt=year, start_year__lte=until).delete()


def unlink(company, start, end, key, years, ownership_year):
    """Retire les liens du bloc `key` sur [start, end] (spec §10.3) : supprime ses
    flux du périmètre des années `years` et, si `ownership_year` est donné, met fin
    à la détention de l'actif à partir de cette année. Le bloc et les groupes
    restent. ValueError, sans rien modifier : rien de demandé, année hors plage,
    ou fin de détention pour un bloc qui n'est pas un actif détenu sur la plage."""
    endpoint, pk = _unlink_target(company, key)
    years = _checked_years(start, end, years)
    if ownership_year is not None:
        _checked_years(start, end, [ownership_year])
    elif not years:
        raise ValueError('Rien à retirer : aucune année ni fin de détention')
    with transaction.atomic():
        if ownership_year is not None and not _is_owned_in_range(
                company, start, end, endpoint, pk):
            raise ValueError(f"Ce bloc n'est pas un actif détenu sur la plage : {key!r}")
        # Flux lus avant de toucher aux détentions, qui définissent le périmètre.
        flows = range_perimeter_flows(company, start, end, touching=(endpoint, pk))
        deleted = delete_flows([flow for flow in flows if flow.year in years])
        if ownership_year is not None:
            end_ownership(company, Asset.objects.get(pk=pk), ownership_year, end)
    return {'flows': deleted, 'ownership': ownership_year is not None}
