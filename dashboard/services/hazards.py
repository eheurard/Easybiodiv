"""Catalogue des aléas physiques.

Partagé entre la vue Risque physique et le stress test climatique. Vivait dans
`views.py` ; déplacé ici pour être importable par les services sans cycle.

Chaque `key` correspond à un champ `Asset.risk_<key>` ET à un champ
`Policy_Level.vulnerability_<key>`.
"""

PHYSICAL_RISKS = [
    {'key': 'water', 'name': 'Eau', 'group': 'Services écosystémiques'},
    {'key': 'pollination', 'name': 'Pollinisation', 'group': 'Services écosystémiques'},
    {'key': 'soil_quality', 'name': 'Qualité des sols', 'group': 'Services écosystémiques'},
    {'key': 'carbon_sequestration', 'name': 'Séquestration carbone',
     'group': 'Services écosystémiques'},
    {'key': 'water_purification', 'name': "Épuration de l'eau",
     'group': 'Services écosystémiques'},
    {'key': 'pest_control', 'name': 'Contrôle des ravageurs',
     'group': 'Services écosystémiques'},
    {'key': 'water_stress', 'name': 'Stress hydrique', 'group': 'Aléas climatiques'},
    {'key': 'wildfire', 'name': 'Incendie', 'group': 'Aléas climatiques'},
    {'key': 'cyclone', 'name': 'Cyclone', 'group': 'Aléas climatiques'},
    {'key': 'drought', 'name': 'Sécheresse', 'group': 'Aléas climatiques'},
    {'key': 'flood', 'name': 'Inondation', 'group': 'Aléas climatiques'},
    {'key': 'coastal_inundation', 'name': 'Submersion côtière', 'group': 'Aléas climatiques'},
    {'key': 'heatwave', 'name': 'Canicule', 'group': 'Aléas climatiques'},
    {'key': 'temperature_variation', 'name': 'Variation de température',
     'group': 'Aléas climatiques'},
    {'key': 'precipitation_variation', 'name': 'Variation des précipitations',
     'group': 'Aléas climatiques'},
]
