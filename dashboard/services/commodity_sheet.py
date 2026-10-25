"""Fiche commodité : facteurs de caractérisation par lieu (global, pays, région)."""
from django.db import transaction
from django.utils.translation import gettext as _

from ..models import (
    CharacterizationFactor, Country, ImpactCategory, SubnationalRegion,
)

GLOBAL = 'global'
COUNTRY = 'country'
REGION = 'region'


def parse_location(value):
    """`'global'`, `'country-<pk>'`, `'region-<pk>'` → `(type, pk)` ; sinon global."""
    if isinstance(value, str):
        kind, _sep, raw = value.partition('-')
        if kind in (COUNTRY, REGION) and raw.isdigit() and int(raw) > 0:
            return kind, int(raw)
    return GLOBAL, None


def location_key(location):
    kind, pk = location
    return GLOBAL if kind == GLOBAL else f'{kind}-{pk}'


def _scope(location):
    """Filtre ORM sur `CharacterizationFactor` pour un lieu `(type, pk)`.

    Un CF régional est lu dès que `region` est renseigné (comme `build_cf_index`).
    """
    kind, pk = location
    if kind == REGION:
        return {'region_id': pk}
    if kind == COUNTRY:
        return {'region__isnull': True, 'country_id': pk}
    return {'region__isnull': True, 'country__isnull': True}


def _label(location):
    kind, pk = location
    if kind == GLOBAL:
        return _('Global')
    if kind == COUNTRY:
        return Country.objects.filter(pk=pk).values_list('name', flat=True).first() or ''
    region = SubnationalRegion.objects.select_related('country').filter(pk=pk).first()
    if region is None:
        return ''
    return f'{region.country.name} › {region.name}' if region.country_id else region.name


def location_chips(commodity, current):
    """Pastilles de lieux : Global, puis les lieux ayant un CF (tri par libellé)."""
    if isinstance(current, str):
        current = parse_location(current)
    current = tuple(current)
    found = set()
    cfs = CharacterizationFactor.objects.filter(commodity=commodity)
    for region_id, country_id in cfs.values_list('region_id', 'country_id').distinct():
        if region_id:
            found.add((REGION, region_id))
        elif country_id:
            found.add((COUNTRY, country_id))
    if current != (GLOBAL, None):
        found.add(current)
    labelled = sorted((_label(loc), loc) for loc in found)
    chips = [{'key': GLOBAL, 'label': _('Global'), 'active': current == (GLOBAL, None)}]
    chips += [{'key': location_key(loc), 'label': label, 'active': loc == current}
              for label, loc in labelled]
    return chips


def _parents(location):
    """Lieux parents, du plus proche au plus lointain : `[(lieu, libellé), …]`."""
    kind, pk = location
    chain = []
    if kind == REGION:
        region = SubnationalRegion.objects.select_related('country').filter(pk=pk).first()
        if region is not None and region.country_id:
            chain.append(((COUNTRY, region.country_id), region.country.name))
    if kind in (REGION, COUNTRY):
        chain.append(((GLOBAL, None), _('Global')))
    return chain


def factor_rows(commodity, location, level):
    """Une ligne par catégorie du niveau, avec la valeur du lieu et l'héritage."""
    if isinstance(location, str):
        location = parse_location(location)
    location = tuple(location)
    categories = list(ImpactCategory.objects.filter(level=level).order_by('pk'))
    cat_ids = [c.pk for c in categories]

    def values(loc):
        qs = CharacterizationFactor.objects.filter(
            commodity=commodity, category_id__in=cat_ids, **_scope(loc))
        return {cf.category_id: cf for cf in qs}

    own = values(location)
    parents = [(label, values(loc)) for loc, label in _parents(location)]
    rows = []
    for category in categories:
        cf = own.get(category.pk)
        inherited = inherited_from = None
        for label, parent_values in parents:
            if category.pk in parent_values:
                inherited = parent_values[category.pk].value
                inherited_from = label
                break
        rows.append({
            'category': category,
            'value': cf.value if cf else None,
            'source_id': cf.commodity_source_id if cf else None,
            'inherited': inherited,
            'inherited_from': inherited_from,
        })
    return rows


@transaction.atomic
def save_factors(commodity, location, values, user):
    """`values` : `{category_pk: (valeur|None, source_pk|None)}`.

    `None` supprime le CF du lieu ; `0.0` est un vrai facteur. `user` est accepté pour la
    cohérence des services (le CF ne porte pas de `created_by`).
    """
    if isinstance(location, str):
        location = parse_location(location)
    kind, pk = tuple(location)
    for category_id, (value, source_id) in values.items():
        existing = CharacterizationFactor.objects.filter(
            commodity=commodity, category_id=category_id, **_scope((kind, pk)))
        if value is None:
            existing.delete()
            continue
        cf = existing.first() or CharacterizationFactor(
            commodity=commodity, category_id=category_id,
            region_id=pk if kind == REGION else None,
            country_id=pk if kind == COUNTRY else None,
        )
        cf.value = value
        cf.commodity_source_id = source_id
        cf.save()
