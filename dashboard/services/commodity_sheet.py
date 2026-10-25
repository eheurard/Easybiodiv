"""Fiche commodité : facteurs de caractérisation par lieu (global, pays, région)."""
from django.db import transaction
from django.db.models import Count
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from ..models import (
    CharacterizationFactor, Country, ImpactCategory, SubnationalRegion, source_codes,
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


def factor_locations(commodity):
    """Lieux régionalisés (pays ou région) ayant au moins un CF propre."""
    found = set()
    cfs = CharacterizationFactor.objects.filter(commodity=commodity)
    for region_id, country_id in cfs.values_list('region_id', 'country_id').distinct():
        if region_id:
            found.add((REGION, region_id))
        elif country_id:
            found.add((COUNTRY, country_id))
    return found


def location_chips(commodity, current):
    """Pastilles de lieux : Global, puis les lieux ayant un CF (tri par libellé)."""
    if isinstance(current, str):
        current = parse_location(current)
    current = tuple(current)
    found = factor_locations(commodity)
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


def modifier_cards(commodity, location):
    """Cartes des modificateurs d'une commodité pour le lieu courant.

    `adjusted` = facteur résolu du lieu (propre, sinon hérité) × max(0, 1 + percent/100),
    `None` quand aucun facteur n'existe pour la catégorie.
    """
    if isinstance(location, str):
        location = parse_location(location)
    resolved = {}
    for level in ImpactCategory.Level.values:
        for row in factor_rows(commodity, location, level):
            value = row['value'] if row['value'] is not None else row['inherited']
            resolved[row['category'].pk] = value
    codes = source_codes(commodity)
    modifiers = (commodity.modifiers.select_related('source')
                 .prefetch_related('effects__category')
                 .annotate(flow_count=Count('flows', distinct=True)))
    cards = []
    for modifier in modifiers:
        effects = []
        for effect in sorted(modifier.effects.all(), key=lambda e: e.category_id):
            base = resolved.get(effect.category_id)
            effects.append({
                'effect': effect,
                'level': ImpactCategory.Level(effect.category.level),
                'adjusted': (None if base is None
                             else base * max(0.0, 1 + effect.percent / 100)),
            })
        confirm = ngettext(
            "Supprimer « %(name)s » ? Il est coché sur %(n)s flux, dont les impacts "
            "seront recalculés.",
            "Supprimer « %(name)s » ? Il est coché sur %(n)s flux, dont les impacts "
            "seront recalculés.",
            modifier.flow_count) % {'name': modifier.name, 'n': modifier.flow_count}
        cards.append({
            'modifier': modifier, 'flow_count': modifier.flow_count, 'effects': effects,
            'source_code': codes.get(modifier.source_id, ''), 'confirm': confirm,
        })
    return cards


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
