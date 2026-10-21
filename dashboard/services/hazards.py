"""Catalogue des aléas physiques.

Partagé entre la vue Risque physique et le stress test climatique. Vivait dans
`views.py` ; déplacé ici pour être importable par les services sans cycle.

Chaque `key` correspond à un champ `Asset.risk_<key>` ET à un champ
`Policy_Level.vulnerability_<key>`.
"""
from django.utils.translation import gettext_lazy as _

PHYSICAL_RISKS = [
    {'key': 'water', 'name': _('Eau'), 'group': _('Services écosystémiques')},
    {'key': 'pollination', 'name': _('Pollinisation'), 'group': _('Services écosystémiques')},
    {'key': 'soil_quality', 'name': _('Qualité des sols'),
     'group': _('Services écosystémiques')},
    {'key': 'carbon_sequestration', 'name': _('Séquestration carbone'),
     'group': _('Services écosystémiques')},
    {'key': 'water_purification', 'name': _("Épuration de l'eau"),
     'group': _('Services écosystémiques')},
    {'key': 'pest_control', 'name': _('Contrôle des ravageurs'),
     'group': _('Services écosystémiques')},
    {'key': 'water_stress', 'name': _('Stress hydrique'), 'group': _('Aléas climatiques')},
    {'key': 'wildfire', 'name': _('Incendie'), 'group': _('Aléas climatiques')},
    {'key': 'cyclone', 'name': _('Cyclone'), 'group': _('Aléas climatiques')},
    {'key': 'drought', 'name': _('Sécheresse'), 'group': _('Aléas climatiques')},
    {'key': 'flood', 'name': _('Inondation'), 'group': _('Aléas climatiques')},
    {'key': 'coastal_inundation', 'name': _('Submersion côtière'),
     'group': _('Aléas climatiques')},
    {'key': 'heatwave', 'name': _('Canicule'), 'group': _('Aléas climatiques')},
    {'key': 'temperature_variation', 'name': _('Variation de température'),
     'group': _('Aléas climatiques')},
    {'key': 'precipitation_variation', 'name': _('Variation des précipitations'),
     'group': _('Aléas climatiques')},
]
