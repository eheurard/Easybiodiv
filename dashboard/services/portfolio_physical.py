"""Carte du risque physique d'un portefeuille (onglet Risque physique de
Portfolio analysis).

Agrège les actifs détenus par les entreprises du portefeuille, au format de
la page Risque physique (dashboard/js/physical_risk_view.js), en pondérant
chaque actif par son exposition financée :

  exposition financée = Σ_entreprises  revenu de l'actif × montant investi / EVIC

Le facteur d'attribution `montant / EVIC` est celui des onglets Impact et
Risque de transition. Une entreprise sans EVIC (> 0) a un facteur nul : ses
actifs restent sur la carte, sans risque financé, et elle est signalée.

Risque financé d'un actif pour un aléa = aléa × exposition financée ×
vulnérabilité. La vulnérabilité est propre à chaque entreprise (moyenne de
ses politiques, comme la page Risque physique) ; pour un actif détenu par
plusieurs entreprises du portefeuille, elle est pondérée par leurs facteurs
d'attribution, ce qui garde le risque égal à la somme des risques par
entreprise.
"""
from collections import defaultdict

from ..models import Asset, Company_Policy, Company_Revenue
from . import flows as flow_service
from .hazards import PHYSICAL_RISKS


def latest_evic(company_ids):
    """{company_id: EVIC le plus récent > 0}."""
    out = {}
    for rev in (
        Company_Revenue.objects
        .filter(company_id__in=company_ids, evic__gt=0)
        .order_by('company_id', '-year')
    ):
        out.setdefault(rev.company_id, rev.evic)
    return out


def company_vulnerabilities(company):
    """({clé d'aléa: vulnérabilité moyenne}, niveaux de politique) d'une
    entreprise ; 1,0 sans politique, comme la page Risque physique."""
    levels = [
        cp.policy_level
        for cp in Company_Policy.objects.filter(company=company).select_related('policy_level')
        if cp.policy_level_id
    ]
    vulnerabilities = {}
    for risk in PHYSICAL_RISKS:
        values = [getattr(level, f"vulnerability_{risk['key']}") for level in levels]
        vulnerabilities[risk['key']] = sum(values) / len(values) if values else 1.0
    return vulnerabilities


def physical_risk_map(holdings):
    """Payload {kpis, hazards, assets, companies_without_evic} pour la carte."""
    keys = [risk['key'] for risk in PHYSICAL_RISKS]
    evic = latest_evic([h.company_id for h in holdings])

    # Facteur d'attribution par entreprise (une entreprise peut figurer deux
    # fois dans un portefeuille mal saisi : les montants s'additionnent).
    attribution = defaultdict(float)
    companies = {}
    for h in holdings:
        companies[h.company_id] = h.company
        if evic.get(h.company_id):
            attribution[h.company_id] += (h.amount or 0.0) / evic[h.company_id]

    vulnerabilities = {pk: company_vulnerabilities(c) for pk, c in companies.items()}

    # Actifs détenus, agrégés : un actif commun à deux entreprises n'apparaît qu'une fois.
    assets = {}
    owners = defaultdict(list)
    for pk, company in companies.items():
        for asset in Asset.objects.owned_by(company).select_related('country').distinct():
            assets[asset.pk] = asset
            owners[asset.pk].append(pk)

    revenue = defaultdict(float)
    for p in flow_service.latest_productions(list(assets)):
        revenue[p.from_asset_id] += p.estimated_revenue or 0.0

    assets_out = []
    totals = {key: 0.0 for key in keys}
    for asset_pk, asset in sorted(assets.items(), key=lambda item: item[1].name):
        factor = sum(attribution[pk] for pk in owners[asset_pk])
        exposure = revenue[asset_pk] * factor
        vulnerability = {}
        for key in keys:
            if factor:
                vulnerability[key] = sum(
                    attribution[pk] * vulnerabilities[pk][key] for pk in owners[asset_pk]
                ) / factor
            else:
                vulnerability[key] = (
                    sum(vulnerabilities[pk][key] for pk in owners[asset_pk])
                    / len(owners[asset_pk])
                )
            totals[key] += getattr(asset, f'risk_{key}') * exposure * vulnerability[key]
        assets_out.append({
            'id': asset_pk,
            'name': asset.name,
            'latitude': asset.latitude,
            'longitude': asset.longitude,
            'country': asset.country.name if asset.country else '',
            'companies': ', '.join(sorted(companies[pk].name for pk in owners[asset_pk])),
            'exposition': round(exposure, 2),
            'risk': {key: round(getattr(asset, f'risk_{key}'), 4) for key in keys},
            'vulnerability': {key: round(value, 4) for key, value in vulnerability.items()},
        })

    total_exposure = sum(a['exposition'] for a in assets_out)
    n_assets = len(assets_out)
    hazards = []
    for risk in PHYSICAL_RISKS:
        key = risk['key']
        # Vulnérabilité affichée : moyenne pondérée par l'exposition financée.
        shown = (
            sum(a['vulnerability'][key] * a['exposition'] for a in assets_out) / total_exposure
            if total_exposure else
            (sum(a['vulnerability'][key] for a in assets_out) / n_assets if n_assets else 0.0)
        )
        hazards.append({
            'key': key,
            'name': risk['name'],
            'group': risk['group'],
            'vulnerability': round(shown, 4),
            'vulnerability_detail': [
                {'policy': companies[pk].name, 'value': round(vulnerabilities[pk][key], 4)}
                for pk in sorted(companies, key=lambda pk: companies[pk].name)
            ],
            'avg_risk': round(totals[key] / n_assets, 2) if n_assets else 0.0,
        })
    hazards.sort(key=lambda h: -h['avg_risk'])

    return {
        'kpis': {'annual_loss': round(sum(totals.values()), 2), 'asset_count': n_assets},
        'hazards': hazards,
        'assets': assets_out,
        'companies_without_evic': sorted(
            c.name for pk, c in companies.items() if not evic.get(pk)
        ),
    }
