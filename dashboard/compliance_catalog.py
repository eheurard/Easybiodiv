"""Catalogue réglementaire ESRS E4 (texte de référence des Disclosure Requirements).

Source de vérité unique des métadonnées (intitulé, description, référence ESRS 2).
L'état mutable (statut, justification) est stocké dans le modèle DisclosureRequirement.
"""

DR_CATALOG = {
    'E4_1': {
        'title': 'Plan de transition biodiversité',
        'description': (
            "À publier uniquement si un plan de transition existe ou a été rendu public. "
            "S'il existe, décrire l'alignement avec le Cadre mondial Kunming-Montréal "
            "(stopper et inverser la perte de biodiversité d'ici 2030). Sinon, simple "
            "déclaration d'absence."
        ),
        'reference': 'ESRS 2',
    },
    'E4_2': {
        'title': 'Politiques',
        'description': (
            "Politiques biodiversité couvrant la traçabilité des produits/matières à "
            "impact matériel et les sites proches de zones sensibles. Test clé : la "
            "politique couvre-t-elle les impacts matériels identifiés dans la DMA ?"
        ),
        'reference': 'ESRS 2 GDR-P',
    },
    'E4_3': {
        'title': 'Actions et ressources',
        'description': (
            "Actions et moyens engagés. Focus sur les compensations (offsets) et leur "
            "place dans la hiérarchie d'atténuation (éviter → réduire → restaurer → "
            "compenser). Seules les actions engagées/financées comptent."
        ),
        'reference': 'ESRS 2 GDR-A',
    },
    'E4_4': {
        'title': 'Cibles',
        'description': (
            "Cibles biodiversité : seuils écologiques et méthodo, alignement "
            "Kunming-Montréal / Stratégie UE Biodiversité 2030, usage d'offsets, portée "
            "géographique, niveau de la hiérarchie d'atténuation visé."
        ),
        'reference': 'ESRS 2 GDR-T',
    },
    'E4_5': {
        'title': "Métriques d'impact",
        'description': (
            "Métrique dure : nombre et surface (hectares) des sites situés dans/près de "
            "zones sensibles avec impacts négatifs (analyse géospatiale). Métriques "
            "additionnelles optionnelles : étendue/condition des écosystèmes, indicateurs "
            "d'espèces (IUCN/European Red List), connectivité des habitats."
        ),
        'reference': '—',
    },
    'E4_6': {
        'title': 'Effets financiers anticipés',
        'description': (
            "Effets financiers anticipés des risques et opportunités biodiversité. "
            "Supprimé dans la version amendée (déc. 2025) — présent uniquement en mode "
            "ESRS E4 original 2023."
        ),
        'reference': '—',
    },
}

APPLICABLE_DRS = {
    'AMENDED_2025': ['E4_1', 'E4_2', 'E4_3', 'E4_4', 'E4_5'],
    'ORIGINAL_2023': ['E4_1', 'E4_2', 'E4_3', 'E4_4', 'E4_5', 'E4_6'],
}
