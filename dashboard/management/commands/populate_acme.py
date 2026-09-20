from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from dashboard.models import (
    Asset, CharacterizationFactor, Commodity, Company, Company_Policy,
    Company_Revenue, Company_Revenue_Sector, Country, Currency,
    DisclosureRequirement, E4Assessment, ESG_data, Flow, FlowKind, FlowScope,
    ImpactCategory, Ownership, Policy_Level, Policy_Subcategory, Policy_Type,
    Portfolio, PortfolioHolding, Sector, SectorCreditProfile, SubSector,
    SubnationalRegion,
)
from dashboard.services.impacts import legacy_cf_rows
from dashboard.services.supply import SCOPE_TO_TIER


DEMO_SOURCE = "Démonstration Easybiodiv"


def _demo_flow(kind, what, year, quantity, reference, created_by, **endpoints):
    """Crée un flux de démonstration s'il n'existe pas déjà.

    `endpoints` porte les extrémités (from_*/to_*), le scope et le tier : ils
    font partie de la recherche, deux flux ne différant que par leur origine
    étant deux flux distincts.
    """
    Flow.objects.get_or_create(
        kind=kind, what=what, year=year, **endpoints,
        defaults={
            'quantity': float(quantity),
            'source': DEMO_SOURCE,
            'reference': reference,
            'created_by': created_by,
        },
    )


class Command(BaseCommand):
    help = "Peuple la base avec des données artificielles pour Acme Corp (risque de transition)"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Création des données Acme Corp…")

        # Auteur des données de démonstration : premier compte disponible, pour
        # renseigner les champs `created_by` des modèles récents.
        demo_user = (
            get_user_model().objects.filter(is_superuser=True).first()
            or get_user_model().objects.first()
        )

        # ── Pays ──────────────────────────────────────────────────────────────

        france, _ = Country.objects.get_or_create(
            name="France",
            defaults={
                "water_ownership": "Public",
                "land_ownership": "Privé",
                "water_Governance": "Eau publique gérée par les agences de bassin",
                "land_Governance": "Code rural et forestier, droit privé",
                "restoration_cost_m2": 45.0,
                "biodiversity_loss_agriculture": 0.35,
                "biodiversity_loss_urbanization": 0.65,
                "biodiversity_loss_mining": 0.50,
            },
        )

        brazil, _ = Country.objects.get_or_create(
            name="Brésil",
            defaults={
                "water_ownership": "Concession publique",
                "land_ownership": "Titre foncier (CAR)",
                "water_Governance": "Política Nacional de Recursos Hídricos (loi 9.433/97)",
                "land_Governance": "Code forestier brésilien, cadastre rural (CAR)",
                "restoration_cost_m2": 28.0,
                "biodiversity_loss_agriculture": 0.72,
                "biodiversity_loss_urbanization": 0.58,
                "biodiversity_loss_mining": 0.65,
            },
        )

        indonesia, _ = Country.objects.get_or_create(
            name="Indonésie",
            defaults={
                "water_ownership": "Étatique",
                "land_ownership": "Concession (HGU)",
                "water_Governance": "Loi sur les ressources en eau (UU No. 17/2019)",
                "land_Governance": "Loi agraire de base (UUPA), concessions gouvernementales",
                "restoration_cost_m2": 22.0,
                "biodiversity_loss_agriculture": 0.81,
                "biodiversity_loss_urbanization": 0.62,
                "biodiversity_loss_mining": 0.73,
            },
        )

        # ── Régions ───────────────────────────────────────────────────────────

        bretagne, _ = SubnationalRegion.objects.get_or_create(
            name="Bretagne",
            country=france,
            defaults={
                "restoration_cost_m2": 50.0,
                "Mean_X": -2.80,
                "Mean_Y": 48.10,
            },
        )

        occitanie, _ = SubnationalRegion.objects.get_or_create(
            name="Occitanie",
            country=france,
            defaults={
                "restoration_cost_m2": 42.0,
                "Mean_X": 2.35,
                "Mean_Y": 43.60,
            },
        )

        mato_grosso, _ = SubnationalRegion.objects.get_or_create(
            name="Mato Grosso",
            country=brazil,
            defaults={
                "restoration_cost_m2": 30.0,
                "Mean_X": -55.00,
                "Mean_Y": -12.50,
            },
        )

        para, _ = SubnationalRegion.objects.get_or_create(
            name="Pará",
            country=brazil,
            defaults={
                "restoration_cost_m2": 35.0,
                "Mean_X": -51.00,
                "Mean_Y": -3.80,
            },
        )

        sumatra, _ = SubnationalRegion.objects.get_or_create(
            name="Sumatra",
            country=indonesia,
            defaults={
                "restoration_cost_m2": 25.0,
                "Mean_X": 102.00,
                "Mean_Y": 0.50,
            },
        )

        # ── Secteurs & sous-secteurs ──────────────────────────────────────────

        sector_agri, _ = Sector.objects.get_or_create(
            name="Agriculture",
            defaults={"NACE_code": "A01"},
        )

        sector_food, _ = Sector.objects.get_or_create(
            name="Industrie alimentaire",
            defaults={"NACE_code": "C10"},
        )

        ss_cereales, _ = SubSector.objects.get_or_create(
            name="Grandes cultures céréalières",
            defaults={
                "sector": sector_agri,
                "NACE_code": "A01.1",
                "Water_dependency": "H",
                "Pollination_dependency": "M",
                "Soil_quality_dependency": "VH",
                "Carbon_Sequestration": "M",
                "Water_purification_dependency": "H",
                "Pest_control_dependency": "H",
            },
        )

        ss_oleagineux, _ = SubSector.objects.get_or_create(
            name="Oléagineux tropicaux",
            defaults={
                "sector": sector_agri,
                "NACE_code": "A01.2",
                "Water_dependency": "VH",
                "Pollination_dependency": "H",
                "Soil_quality_dependency": "VH",
                "Carbon_Sequestration": "VH",
                "Water_purification_dependency": "VH",
                "Pest_control_dependency": "H",
            },
        )

        ss_transfo, _ = SubSector.objects.get_or_create(
            name="Transformation huiles végétales",
            defaults={
                "sector": sector_food,
                "NACE_code": "C10.4",
                "Water_dependency": "M",
                "Pollination_dependency": "VL",
                "Soil_quality_dependency": "L",
                "Carbon_Sequestration": "L",
                "Water_purification_dependency": "M",
                "Pest_control_dependency": "L",
            },
        )

        # ── Commodités ────────────────────────────────────────────────────────

        ble, _ = Commodity.objects.get_or_create(
            name="Blé",
            defaults={
                "description": "Triticum aestivum — céréale tempérée",
                "unit": "tonnes",
                "dependency_water": "H",
                "dependency_pollination": "L",
                "dependency_soil_quality": "VH",
                "dependency_carbon_sequestration": "M",
                "dependency_water_purification": "H",
                "dependency_pest_control": "H",
                "biodiversity_loss_class": "Agriculture",
            },
        )

        mais, _ = Commodity.objects.get_or_create(
            name="Maïs",
            defaults={
                "description": "Zea mays — céréale à haut rendement",
                "unit": "tonnes",
                "dependency_water": "VH",
                "dependency_pollination": "M",
                "dependency_soil_quality": "VH",
                "dependency_carbon_sequestration": "M",
                "dependency_water_purification": "H",
                "dependency_pest_control": "H",
                "biodiversity_loss_class": "Agriculture",
            },
        )

        soja, _ = Commodity.objects.get_or_create(
            name="Soja",
            defaults={
                "description": "Glycine max — légumineuse à haute valeur protéique",
                "unit": "tonnes",
                "dependency_water": "VH",
                "dependency_pollination": "H",
                "dependency_soil_quality": "VH",
                "dependency_carbon_sequestration": "VH",
                "dependency_water_purification": "VH",
                "dependency_pest_control": "H",
                "biodiversity_loss_class": "Agriculture",
            },
        )

        palme, _ = Commodity.objects.get_or_create(
            name="Huile de palme",
            defaults={
                "description": "Elaeis guineensis — huile végétale tropicale",
                "unit": "tonnes",
                "dependency_water": "VH",
                "dependency_pollination": "H",
                "dependency_soil_quality": "VH",
                "dependency_carbon_sequestration": "VH",
                "dependency_water_purification": "VH",
                "dependency_pest_control": "H",
                "biodiversity_loss_class": "Agriculture",
            },
        )

        # ── Facteurs de caractérisation globaux ────────────────────────────────
        _cf_values = {
            ble: {
                'impact_midpoint_ReCiPe2016_water_consumption': 1.21,
                'impact_midpoint_ReCiPe2016_climate_change': 0.29,
                'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity': 0.008,
                'impact_midpoint_ReCiPe2016_land_use': 2.8,
                'impact_endpoint_ReCiPe2016_ecosystem_diversity': 0.0014,
                'impact_endpoint_GBS_terrestrial_dynamic': 0.42,
                'impact_endpoint_GBS_terrestrial_static': 0.38,
            },
            mais: {
                'impact_midpoint_ReCiPe2016_water_consumption': 1.58,
                'impact_midpoint_ReCiPe2016_climate_change': 0.33,
                'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity': 0.012,
                'impact_midpoint_ReCiPe2016_land_use': 3.1,
                'impact_endpoint_ReCiPe2016_ecosystem_diversity': 0.0017,
                'impact_endpoint_GBS_terrestrial_dynamic': 0.48,
                'impact_endpoint_GBS_terrestrial_static': 0.43,
            },
            soja: {
                'impact_midpoint_ReCiPe2016_water_consumption': 2.14,
                'impact_midpoint_ReCiPe2016_climate_change': 0.72,
                'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity': 0.021,
                'impact_midpoint_ReCiPe2016_land_use': 6.5,
                'impact_endpoint_ReCiPe2016_ecosystem_diversity': 0.0048,
                'impact_endpoint_GBS_terrestrial_dynamic': 1.12,
                'impact_endpoint_GBS_terrestrial_static': 0.95,
            },
            palme: {
                'impact_midpoint_ReCiPe2016_water_consumption': 3.45,
                'impact_midpoint_ReCiPe2016_climate_change': 1.82,
                'impact_midpoint_ReCiPe2016_freshwater_ecotoxicity': 0.038,
                'impact_midpoint_ReCiPe2016_land_use': 12.0,
                'impact_endpoint_ReCiPe2016_ecosystem_diversity': 0.0095,
                'impact_endpoint_GBS_terrestrial_dynamic': 2.45,
                'impact_endpoint_GBS_terrestrial_static': 2.10,
            },
        }
        _categories = {c.key: c for c in ImpactCategory.objects.all()}
        for commodity, values in _cf_values.items():
            for col, val in legacy_cf_rows(values):
                CharacterizationFactor.objects.get_or_create(
                    commodity=commodity, category=_categories[col],
                    region=None, country=None, defaults={'value': val},
                )

        # ── Entreprise ────────────────────────────────────────────────────────

        acme, _ = Company.objects.update_or_create(
            name="Acme Corp",
            defaults={
                "description": (
                    "Groupe agro-industriel international spécialisé dans la production "
                    "et la transformation de matières premières agricoles tropicales et tempérées."
                ),
                "isin": "FR0000000001",
                "ticker": "ACME",
            },
        )

        # ── Actifs ────────────────────────────────────────────────────────────

        a_bretagne, _ = Asset.objects.get_or_create(
            name="Usine de transformation Bretagne",
            defaults={
                "description": "Unité de raffinage d'huile végétale — Saint-Brieuc",
                "latitude": 48.51,
                "longitude": -2.76,
                "country": france,
                "subnational_region": bretagne,
                "risk_water": 0.15, "risk_pollination": 0.10, "risk_soil_quality": 0.12,
                "risk_carbon_sequestration": 0.10, "risk_water_purification": 0.15,
                "risk_pest_control": 0.10, "risk_water_stress": 0.20, "risk_wildfire": 0.05,
                "risk_cyclone": 0.02, "risk_drought": 0.25, "risk_flood": 0.30,
                "risk_coastal_inundation": 0.20, "risk_heatwave": 0.35,
                "risk_temperature_variation": 0.30, "risk_precipitation_variation": 0.28,
            },
        )

        a_occitanie, _ = Asset.objects.get_or_create(
            name="Silo céréalier Occitanie",
            defaults={
                "description": "Silo de stockage de céréales — Montauban",
                "latitude": 44.02,
                "longitude": 1.35,
                "country": france,
                "subnational_region": occitanie,
                "risk_water": 0.25, "risk_pollination": 0.20, "risk_soil_quality": 0.30,
                "risk_carbon_sequestration": 0.15, "risk_water_purification": 0.20,
                "risk_pest_control": 0.25, "risk_water_stress": 0.55, "risk_wildfire": 0.40,
                "risk_cyclone": 0.05, "risk_drought": 0.60, "risk_flood": 0.35,
                "risk_coastal_inundation": 0.10, "risk_heatwave": 0.65,
                "risk_temperature_variation": 0.50, "risk_precipitation_variation": 0.45,
            },
        )

        a_mato_grosso, _ = Asset.objects.get_or_create(
            name="Plantation soja Mato Grosso",
            defaults={
                "description": "Exploitation intensive de soja — Nova Mutum (Cerrado)",
                "latitude": -13.83,
                "longitude": -56.08,
                "country": brazil,
                "subnational_region": mato_grosso,
                "risk_water": 0.60, "risk_pollination": 0.55, "risk_soil_quality": 0.65,
                "risk_carbon_sequestration": 0.80, "risk_water_purification": 0.60,
                "risk_pest_control": 0.50, "risk_water_stress": 0.45, "risk_wildfire": 0.70,
                "risk_cyclone": 0.20, "risk_drought": 0.55, "risk_flood": 0.30,
                "risk_coastal_inundation": 0.05, "risk_heatwave": 0.65,
                "risk_temperature_variation": 0.55, "risk_precipitation_variation": 0.60,
            },
        )

        a_para, _ = Asset.objects.get_or_create(
            name="Plantation soja Pará",
            defaults={
                "description": "Exploitation à la frontière de la déforestation amazonienne — Paragominas",
                "latitude": -2.98,
                "longitude": -47.35,
                "country": brazil,
                "subnational_region": para,
                "risk_water": 0.70, "risk_pollination": 0.75, "risk_soil_quality": 0.80,
                "risk_carbon_sequestration": 0.95, "risk_water_purification": 0.75,
                "risk_pest_control": 0.60, "risk_water_stress": 0.40, "risk_wildfire": 0.85,
                "risk_cyclone": 0.25, "risk_drought": 0.65, "risk_flood": 0.50,
                "risk_coastal_inundation": 0.15, "risk_heatwave": 0.75,
                "risk_temperature_variation": 0.65, "risk_precipitation_variation": 0.70,
            },
        )

        a_sumatra, _ = Asset.objects.get_or_create(
            name="Palmeraie Sumatra",
            defaults={
                "description": "Plantation de palmiers à huile certifiée RSPO (partielle) — Riau",
                "latitude": 0.75,
                "longitude": 102.10,
                "country": indonesia,
                "subnational_region": sumatra,
                "risk_water": 0.65, "risk_pollination": 0.70, "risk_soil_quality": 0.75,
                "risk_carbon_sequestration": 0.90, "risk_water_purification": 0.70,
                "risk_pest_control": 0.55, "risk_water_stress": 0.30, "risk_wildfire": 0.80,
                "risk_cyclone": 0.50, "risk_drought": 0.45, "risk_flood": 0.55,
                "risk_coastal_inundation": 0.35, "risk_heatwave": 0.70,
                "risk_temperature_variation": 0.55, "risk_precipitation_variation": 0.65,
            },
        )

        a_valorisation, _ = Asset.objects.get_or_create(
            name="Unité de valorisation des coproduits Bretagne",
            defaults={
                "description": "Méthanisation et valorisation des coproduits — Lamballe",
                "latitude": 48.47,
                "longitude": -2.51,
                "country": france,
                "subnational_region": bretagne,
                "type": "Factory",
                "risk_water": 0.15, "risk_pollination": 0.10, "risk_soil_quality": 0.12,
                "risk_carbon_sequestration": 0.10, "risk_water_purification": 0.15,
                "risk_pest_control": 0.10, "risk_water_stress": 0.20, "risk_wildfire": 0.05,
                "risk_cyclone": 0.02, "risk_drought": 0.25, "risk_flood": 0.25,
                "risk_coastal_inundation": 0.15, "risk_heatwave": 0.35,
                "risk_temperature_variation": 0.30, "risk_precipitation_variation": 0.28,
            },
        )

        # ── Détentions ────────────────────────────────────────────────────────
        #
        # Part décimale et années de validité (spec §3.6) : le détenteur d'une
        # année est celui du 31 décembre. Sumatra illustre une montée au capital.

        for asset, share, start_year, note in [
            (a_bretagne, Decimal('1'), 2015, "Site historique du groupe."),
            (a_occitanie, Decimal('1'), 2017, "Acquis au rachat du groupe céréalier Midi."),
            (a_valorisation, Decimal('1'), 2022, "Construit en propre, adossé à la raffinerie."),
            (a_mato_grosso, Decimal('0.75'), 2019, "Coentreprise avec un partenaire local (25 %)."),
            (a_para, Decimal('1'), 2020, "Rachat intégral de l'exploitation."),
            (a_sumatra, Decimal('0.6'), 2021, "Participation portée de 40 % à 60 % en 2021."),
        ]:
            Ownership.objects.get_or_create(
                asset=asset, company=acme, end_year=None,
                defaults={
                    'share': share, 'start_year': start_year,
                    'description': note, 'created_by': demo_user,
                },
            )

        Ownership.objects.get_or_create(
            asset=a_sumatra, company=acme, end_year=2020,
            defaults={
                'share': Decimal('0.4'), 'start_year': 2016,
                'description': "Participation initiale, portée à 60 % en 2021.",
                'created_by': demo_user,
            },
        )

        # ── Productions 2023-2024 ─────────────────────────────────────────────

        productions = [
            (a_bretagne,    palme, "direct",      2023, 85_000,  68_000_000),
            (a_bretagne,    palme, "direct",      2024, 88_000,  72_000_000),
            (a_occitanie,   ble,   "direct",      2023, 42_000,   8_400_000),
            (a_occitanie,   ble,   "direct",      2024, 45_000,   9_000_000),
            (a_occitanie,   mais,  "direct",      2023, 28_000,   5_040_000),
            (a_occitanie,   mais,  "direct",      2024, 30_000,   5_400_000),
            (a_mato_grosso, soja,  "tier 1",      2023, 180_000, 108_000_000),
            (a_mato_grosso, soja,  "tier 1",      2024, 195_000, 117_000_000),
            (a_para,        soja,  "tier 1",      2023,  95_000,  57_000_000),
            (a_para,        soja,  "tier 1",      2024, 102_000,  61_200_000),
            (a_sumatra,     palme, "tier 1",      2023, 220_000, 176_000_000),
            (a_sumatra,     palme, "tier 1",      2024, 235_000, 188_000_000),
        ]

        for asset, commodity, scope, year, qty, revenue in productions:
            Flow.objects.get_or_create(
                kind=FlowKind.PRODUCTION,
                what=commodity,
                from_asset=asset,
                tier=SCOPE_TO_TIER[scope],
                year=year,
                defaults={'quantity': qty, 'estimated_revenue': revenue},
            )

        # ── Inventaire mesuré des sites ───────────────────────────────────────
        #
        # Commodités techniques (Commodity.key) : ce sont elles que lisent les
        # vues via dashboard/services/flows.py. Une consommation entre dans
        # l'actif, une émission et un déchet en sortent (FLOW_RULES).

        water = Commodity.objects.technical('water')
        energy = Commodity.objects.technical('energy')
        co2 = Commodity.objects.technical('co2')
        waste = Commodity.objects.technical('waste')
        surface = Commodity.objects.technical('surface_area')

        # Prélevé dans le milieu : eau (m³) et surface occupée (m²).
        for asset, commodity, qty_2023, qty_2024 in [
            (a_bretagne,     water,   1_250_000,   1_180_000),
            (a_occitanie,    water,      85_000,      92_000),
            (a_valorisation, water,     140_000,     155_000),
            (a_mato_grosso,  water,   4_200_000,   4_550_000),
            (a_para,         water,   2_300_000,   2_480_000),
            (a_sumatra,      water,   6_800_000,   7_100_000),
            (a_bretagne,     surface,   120_000,     120_000),
            (a_occitanie,    surface,    45_000,      45_000),
            (a_valorisation, surface,    18_000,      18_000),
            (a_mato_grosso,  surface, 62_000_000,  64_500_000),
            (a_para,         surface, 31_000_000,  33_200_000),
            (a_sumatra,      surface, 48_000_000,  48_000_000),
        ]:
            for year, qty in [(2023, qty_2023), (2024, qty_2024)]:
                _demo_flow(
                    FlowKind.CONSUMPTION, commodity, year, qty,
                    "Relevés de site (données fictives)", demo_user,
                    from_environment=True, to_asset=asset,
                )

        # Énergie : origine non renseignée (réseau), destination l'actif — ou le
        # siège social, qui n'est pas un actif géolocalisé.
        for asset, mwh_2023, mwh_2024 in [
            (a_bretagne,     42_000, 40_500),
            (a_occitanie,     3_200,  3_400),
            (a_valorisation,  5_600,  6_100),
            (a_mato_grosso,  12_500, 13_400),
            (a_para,          6_800,  7_300),
            (a_sumatra,      18_000, 19_200),
        ]:
            for year, qty in [(2023, mwh_2023), (2024, mwh_2024)]:
                _demo_flow(
                    FlowKind.CONSUMPTION, energy, year, qty,
                    "Factures d'électricité (données fictives)", demo_user,
                    to_asset=asset,
                )

        for year, qty in [(2023, 1_450), (2024, 1_380)]:
            _demo_flow(
                FlowKind.CONSUMPTION, energy, year, qty,
                "Siège social et flotte — hors périmètre des sites", demo_user,
                to_company=acme,
            )

        # Émissions mesurées sur site (Scope 1) : actif → milieu. Distinctes des
        # émissions déclarées par l'entreprise, créées plus bas.
        for asset, t_2023, t_2024 in [
            (a_bretagne,     9_000, 7_600),
            (a_occitanie,    1_200, 1_300),
            (a_valorisation,  1_000, 1_000),
            (a_mato_grosso,  5_400, 5_200),
            (a_para,         3_100, 3_000),
            (a_sumatra,      4_800, 4_900),
        ]:
            for year, qty in [(2023, t_2023), (2024, t_2024)]:
                _demo_flow(
                    FlowKind.EMISSION, co2, year, qty,
                    "Bilan carbone site (données fictives)", demo_user,
                    scope=FlowScope.SCOPE_1, from_asset=asset, to_environment=True,
                )

        # Déchets : les trois destinations autorisées sont illustrées — le milieu,
        # un actif de traitement, ou une destination inconnue.
        for asset, t_2023, t_2024, endpoints, reference in [
            (a_bretagne, 3_200, 3_050, {'to_asset': a_valorisation},
             "Coproduits de raffinage envoyés à l'unité de valorisation"),
            (a_occitanie, 450, 480, {'to_asset': a_valorisation},
             "Issues de silo envoyées à l'unité de valorisation"),
            (a_mato_grosso, 1_800, 1_950, {'to_environment': True},
             "Résidus de culture laissés au champ"),
            (a_para, 950, 1_020, {},
             "Collecte par un prestataire local, destination non tracée"),
            (a_sumatra, 5_400, 5_700, {'to_environment': True},
             "Rafles et effluents d'huilerie épandus sur la plantation"),
        ]:
            for year, qty in [(2023, t_2023), (2024, t_2024)]:
                _demo_flow(
                    FlowKind.WASTE, waste, year, qty, reference, demo_user,
                    from_asset=asset, **endpoints,
                )

        # ── Approvisionnements ────────────────────────────────────────────────
        #
        # Un SUPPLY relie deux lieux ou entreprises. Le tier situe le maillon :
        # 0 opérations directes, 1 fournisseur direct, 2 amont, 3 matière première.
        # Origine actif ou région → tracé sur la carte ; origine pays ou
        # destination entreprise → pas de coordonnées, donc pas de trait.

        for what, origin, destination, tier, qty_2023, qty_2024, reference in [
            (palme, {'from_asset': a_sumatra}, {'to_asset': a_bretagne}, 1,
             180_000, 195_000, "Huile brute expédiée vers la raffinerie"),
            (soja, {'from_asset': a_mato_grosso}, {'to_asset': a_bretagne}, 1,
             165_000, 172_000, "Soja du Mato Grosso trituré en Bretagne"),
            (soja, {'from_asset': a_para}, {'to_company': acme}, 1,
             88_000, 94_000, "Soja du Pará vendu depuis le négoce groupe"),
            (soja, {'from_region': mato_grosso}, {'to_asset': a_bretagne}, 2,
             40_000, 45_000, "Achats auprès de producteurs tiers de la région"),
            (palme, {'from_region': sumatra}, {'to_asset': a_bretagne}, 2,
             55_000, 60_000, "Achats auprès de petits planteurs de Riau"),
            (ble, {'from_country': france}, {'to_asset': a_occitanie}, 3,
             15_000, 16_000, "Collecte nationale, exploitations non tracées"),
            (mais, {'from_country': brazil}, {'to_company': acme}, 3,
             22_000, 24_000, "Maïs importé, origine régionale non tracée"),
            (palme, {'from_company': acme}, {'to_country': france}, 0,
             52_000, 55_000, "Huile raffinée livrée sur le marché français"),
        ]:
            for year, qty in [(2023, qty_2023), (2024, qty_2024)]:
                _demo_flow(
                    FlowKind.SUPPLY, what, year, qty, reference, demo_user,
                    tier=tier, **origin, **destination,
                )

        # ── Revenus ───────────────────────────────────────────────────────────

        Company_Revenue.objects.get_or_create(
            company=acme, year=2023, defaults={"revenue": 422_440_000, "currency": "EUR"}
        )
        Company_Revenue.objects.get_or_create(
            company=acme, year=2024, defaults={"revenue": 452_600_000, "currency": "EUR"}
        )

        for subsector, year, rev in [
            (ss_cereales,   2024,  45_000_000),
            (ss_oleagineux, 2024, 250_000_000),
            (ss_transfo,    2024, 157_600_000),
        ]:
            Company_Revenue_Sector.objects.get_or_create(
                company=acme, subsector=subsector, year=year, defaults={"revenue": rev}
            )

        # ── Profils de crédit sectoriels (démo) ───────────────────────────────
        #
        # PD 1 an, marge et volatilité d'EBITDA, répercussion du coût carbone.
        # Valeurs de démonstration : ordres de grandeur plausibles, à remplacer
        # par des données de marché pour un usage réel.

        for sector, pd_baseline, margin, volatility, pass_through in [
            (sector_agri, 0.0180, 0.10, 0.28, 0.20),
            (sector_food, 0.0090, 0.14, 0.22, 0.35),
        ]:
            SectorCreditProfile.objects.get_or_create(
                sector=sector,
                defaults={
                    "pd_baseline": pd_baseline,
                    "ebitda_margin": margin,
                    "ebitda_volatility": volatility,
                    "carbon_pass_through": pass_through,
                    "source": "Démonstration Easybiodiv",
                    "reference": "Ordres de grandeur, non calibrés sur données de marché",
                },
            )

        # ── Catalogue des politiques de transition ────────────────────────────
        #
        # Modélisation du risque de transition TNFD :
        #   - vulnerability > 1  → la politique amplifie l'exposition au risque physique
        #   - vulnerability < 1  → la politique réduit l'exposition (mesures d'adaptation)

        pt_reg, _ = Policy_Type.objects.get_or_create(
            name="Risque Réglementaire",
            defaults={"description": "Nouvelles réglementations biodiversité et environnement"},
        )

        pt_mkt, _ = Policy_Type.objects.get_or_create(
            name="Risque de Marché",
            defaults={"description": "Évolution des marchés et attentes des parties prenantes"},
        )

        # -- EUDR -------------------------------------------------------
        ps_eudr, _ = Policy_Subcategory.objects.get_or_create(
            name="EUDR — Règlement sur la déforestation",
            defaults={
                "policy_type": pt_reg,
                "description": "Règlement (UE) 2023/1115 : traçabilité sans déforestation",
            },
        )

        Policy_Level.objects.get_or_create(
            subcategory=ps_eudr, name="Conforme",
            defaults={
                "score": 0.20,
                "description": "Traçabilité complète, due diligence opérationnelle",
                "vulnerability_water": 0.8, "vulnerability_pollination": 0.8,
                "vulnerability_soil_quality": 0.8, "vulnerability_carbon_sequestration": 0.7,
                "vulnerability_water_purification": 0.8, "vulnerability_pest_control": 0.9,
                "vulnerability_water_stress": 0.9, "vulnerability_wildfire": 0.8,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 0.9,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 0.9, "vulnerability_temperature_variation": 0.9,
                "vulnerability_precipitation_variation": 0.9,
            },
        )

        pl_eudr_partiel, _ = Policy_Level.objects.get_or_create(
            subcategory=ps_eudr, name="Partiellement conforme",
            defaults={
                "score": 0.60,
                "description": "Due diligence en cours, certaines filières non tracées",
                "vulnerability_water": 1.2, "vulnerability_pollination": 1.3,
                "vulnerability_soil_quality": 1.4, "vulnerability_carbon_sequestration": 1.6,
                "vulnerability_water_purification": 1.2, "vulnerability_pest_control": 1.1,
                "vulnerability_water_stress": 1.1, "vulnerability_wildfire": 1.4,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.2,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.1, "vulnerability_temperature_variation": 1.1,
                "vulnerability_precipitation_variation": 1.2,
            },
        )

        Policy_Level.objects.get_or_create(
            subcategory=ps_eudr, name="Non conforme",
            defaults={
                "score": 1.00,
                "description": "Pas de traçabilité, risque de sanctions et d'exclusion du marché UE",
                "vulnerability_water": 1.5, "vulnerability_pollination": 1.6,
                "vulnerability_soil_quality": 1.8, "vulnerability_carbon_sequestration": 2.0,
                "vulnerability_water_purification": 1.5, "vulnerability_pest_control": 1.3,
                "vulnerability_water_stress": 1.2, "vulnerability_wildfire": 1.7,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.4,
                "vulnerability_flood": 1.1, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.3, "vulnerability_temperature_variation": 1.2,
                "vulnerability_precipitation_variation": 1.3,
            },
        )

        # -- CSRD / ESRS E4 ---------------------------------------------
        ps_csrd, _ = Policy_Subcategory.objects.get_or_create(
            name="CSRD / ESRS E4",
            defaults={
                "policy_type": pt_reg,
                "description": "Reporting de durabilité — norme biodiversité ESRS E4",
            },
        )

        Policy_Level.objects.get_or_create(
            subcategory=ps_csrd, name="Reporting intégré",
            defaults={
                "score": 0.20,
                "description": "Indicateurs ESRS E4 publiés, objectifs chiffrés, plan de transition",
                "vulnerability_water": 0.9, "vulnerability_pollination": 0.9,
                "vulnerability_soil_quality": 0.9, "vulnerability_carbon_sequestration": 0.8,
                "vulnerability_water_purification": 0.9, "vulnerability_pest_control": 0.9,
                "vulnerability_water_stress": 0.9, "vulnerability_wildfire": 0.9,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 0.9,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 0.9, "vulnerability_temperature_variation": 0.9,
                "vulnerability_precipitation_variation": 0.9,
            },
        )

        pl_csrd_transition, _ = Policy_Level.objects.get_or_create(
            subcategory=ps_csrd, name="En cours de conformité",
            defaults={
                "score": 0.50,
                "description": "Reporting partiel, lacunes quantitatives, pas de plan de transition",
                "vulnerability_water": 1.1, "vulnerability_pollination": 1.1,
                "vulnerability_soil_quality": 1.2, "vulnerability_carbon_sequestration": 1.2,
                "vulnerability_water_purification": 1.1, "vulnerability_pest_control": 1.1,
                "vulnerability_water_stress": 1.1, "vulnerability_wildfire": 1.1,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.1,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.1, "vulnerability_temperature_variation": 1.1,
                "vulnerability_precipitation_variation": 1.1,
            },
        )

        Policy_Level.objects.get_or_create(
            subcategory=ps_csrd, name="Non conforme",
            defaults={
                "score": 0.90,
                "description": "Aucun reporting biodiversité, risque de sanction et perte de confiance",
                "vulnerability_water": 1.3, "vulnerability_pollination": 1.3,
                "vulnerability_soil_quality": 1.4, "vulnerability_carbon_sequestration": 1.4,
                "vulnerability_water_purification": 1.3, "vulnerability_pest_control": 1.2,
                "vulnerability_water_stress": 1.2, "vulnerability_wildfire": 1.3,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.2,
                "vulnerability_flood": 1.1, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.2, "vulnerability_temperature_variation": 1.2,
                "vulnerability_precipitation_variation": 1.2,
            },
        )

        # -- Taxe biodiversité / PSE ------------------------------------
        ps_taxe, _ = Policy_Subcategory.objects.get_or_create(
            name="Taxe biodiversité / Paiement pour services écosystémiques",
            defaults={
                "policy_type": pt_reg,
                "description": "Mécanismes fiscaux liés à la perte de biodiversité",
            },
        )

        Policy_Level.objects.get_or_create(
            subcategory=ps_taxe, name="Exposition faible",
            defaults={
                "score": 0.20,
                "description": "Peu exposé aux écotaxes, secteur/localisation hors périmètre",
                "vulnerability_water": 0.9, "vulnerability_pollination": 0.9,
                "vulnerability_soil_quality": 0.9, "vulnerability_carbon_sequestration": 0.9,
                "vulnerability_water_purification": 0.9, "vulnerability_pest_control": 0.9,
                "vulnerability_water_stress": 1.0, "vulnerability_wildfire": 1.0,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.0,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.0, "vulnerability_temperature_variation": 1.0,
                "vulnerability_precipitation_variation": 1.0,
            },
        )

        pl_taxe_mod, _ = Policy_Level.objects.get_or_create(
            subcategory=ps_taxe, name="Exposition modérée",
            defaults={
                "score": 0.55,
                "description": "Exposition à certaines taxes sur l'utilisation des terres ou l'eau",
                "vulnerability_water": 1.2, "vulnerability_pollination": 1.1,
                "vulnerability_soil_quality": 1.3, "vulnerability_carbon_sequestration": 1.2,
                "vulnerability_water_purification": 1.2, "vulnerability_pest_control": 1.1,
                "vulnerability_water_stress": 1.1, "vulnerability_wildfire": 1.1,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.1,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.1, "vulnerability_temperature_variation": 1.0,
                "vulnerability_precipitation_variation": 1.0,
            },
        )

        Policy_Level.objects.get_or_create(
            subcategory=ps_taxe, name="Forte exposition",
            defaults={
                "score": 0.85,
                "description": "Secteur et localisation très exposés aux nouvelles taxes biodiversité",
                "vulnerability_water": 1.4, "vulnerability_pollination": 1.3,
                "vulnerability_soil_quality": 1.5, "vulnerability_carbon_sequestration": 1.5,
                "vulnerability_water_purification": 1.4, "vulnerability_pest_control": 1.2,
                "vulnerability_water_stress": 1.2, "vulnerability_wildfire": 1.2,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.3,
                "vulnerability_flood": 1.1, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.2, "vulnerability_temperature_variation": 1.1,
                "vulnerability_precipitation_variation": 1.1,
            },
        )

        # -- Pression investisseurs ESG ---------------------------------
        ps_esg, _ = Policy_Subcategory.objects.get_or_create(
            name="Pression investisseurs ESG",
            defaults={
                "policy_type": pt_mkt,
                "description": "Exigences des fonds ESG sur la biodiversité",
            },
        )

        Policy_Level.objects.get_or_create(
            subcategory=ps_esg, name="Fort engagement ESG",
            defaults={
                "score": 0.15,
                "description": "Politique biodiversité robuste, notation AAA, accès aux capitaux verts",
                "vulnerability_water": 0.8, "vulnerability_pollination": 0.8,
                "vulnerability_soil_quality": 0.8, "vulnerability_carbon_sequestration": 0.8,
                "vulnerability_water_purification": 0.8, "vulnerability_pest_control": 0.8,
                "vulnerability_water_stress": 0.9, "vulnerability_wildfire": 0.9,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 0.9,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 0.9, "vulnerability_temperature_variation": 0.9,
                "vulnerability_precipitation_variation": 0.9,
            },
        )

        pl_esg_limite, _ = Policy_Level.objects.get_or_create(
            subcategory=ps_esg, name="Engagement limité",
            defaults={
                "score": 0.60,
                "description": "Initiatives ESG superficielles, risque de désinvestissement",
                "vulnerability_water": 1.2, "vulnerability_pollination": 1.2,
                "vulnerability_soil_quality": 1.2, "vulnerability_carbon_sequestration": 1.3,
                "vulnerability_water_purification": 1.2, "vulnerability_pest_control": 1.1,
                "vulnerability_water_stress": 1.1, "vulnerability_wildfire": 1.1,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.1,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.1, "vulnerability_temperature_variation": 1.1,
                "vulnerability_precipitation_variation": 1.1,
            },
        )

        Policy_Level.objects.get_or_create(
            subcategory=ps_esg, name="Pas d'engagement ESG",
            defaults={
                "score": 1.00,
                "description": "Aucune politique ESG biodiversité, risque élevé de désinvestissement",
                "vulnerability_water": 1.4, "vulnerability_pollination": 1.4,
                "vulnerability_soil_quality": 1.4, "vulnerability_carbon_sequestration": 1.5,
                "vulnerability_water_purification": 1.4, "vulnerability_pest_control": 1.3,
                "vulnerability_water_stress": 1.2, "vulnerability_wildfire": 1.2,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.2,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.2, "vulnerability_temperature_variation": 1.2,
                "vulnerability_precipitation_variation": 1.2,
            },
        )

        # -- Demande marchés durables -----------------------------------
        ps_mkt_durable, _ = Policy_Subcategory.objects.get_or_create(
            name="Demande marchés durables",
            defaults={
                "policy_type": pt_mkt,
                "description": "Évolution des préférences consommateurs vers des produits à faible impact",
            },
        )

        Policy_Level.objects.get_or_create(
            subcategory=ps_mkt_durable, name="Offre adaptée",
            defaults={
                "score": 0.20,
                "description": "Gamme de produits durables certifiés, premium accepté par le marché",
                "vulnerability_water": 0.85, "vulnerability_pollination": 0.85,
                "vulnerability_soil_quality": 0.85, "vulnerability_carbon_sequestration": 0.80,
                "vulnerability_water_purification": 0.85, "vulnerability_pest_control": 0.9,
                "vulnerability_water_stress": 1.0, "vulnerability_wildfire": 1.0,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.0,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.0, "vulnerability_temperature_variation": 1.0,
                "vulnerability_precipitation_variation": 1.0,
            },
        )

        pl_mkt_cours, _ = Policy_Level.objects.get_or_create(
            subcategory=ps_mkt_durable, name="Transition en cours",
            defaults={
                "score": 0.50,
                "description": "Reconversion partielle, certifications en cours, risque de perte de parts de marché",
                "vulnerability_water": 1.1, "vulnerability_pollination": 1.1,
                "vulnerability_soil_quality": 1.1, "vulnerability_carbon_sequestration": 1.2,
                "vulnerability_water_purification": 1.1, "vulnerability_pest_control": 1.1,
                "vulnerability_water_stress": 1.0, "vulnerability_wildfire": 1.0,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.0,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.0, "vulnerability_temperature_variation": 1.0,
                "vulnerability_precipitation_variation": 1.0,
            },
        )

        Policy_Level.objects.get_or_create(
            subcategory=ps_mkt_durable, name="En retard",
            defaults={
                "score": 0.80,
                "description": "Produits conventionnels uniquement, risque de déréférencement",
                "vulnerability_water": 1.3, "vulnerability_pollination": 1.3,
                "vulnerability_soil_quality": 1.3, "vulnerability_carbon_sequestration": 1.4,
                "vulnerability_water_purification": 1.3, "vulnerability_pest_control": 1.2,
                "vulnerability_water_stress": 1.0, "vulnerability_wildfire": 1.0,
                "vulnerability_cyclone": 1.0, "vulnerability_drought": 1.0,
                "vulnerability_flood": 1.0, "vulnerability_coastal_inundation": 1.0,
                "vulnerability_heatwave": 1.0, "vulnerability_temperature_variation": 1.0,
                "vulnerability_precipitation_variation": 1.0,
            },
        )

        # ── Profil de risque de transition d'Acme Corp ────────────────────────
        #
        # Acme Corp = exposition modérée-haute :
        #   EUDR partiellement conforme, CSRD en cours, taxe modérée,
        #   ESG engagement limité, marché en transition

        for policy_level, date_str in [
            (pl_eudr_partiel,   "2024-03-15"),
            (pl_csrd_transition,"2024-06-01"),
            (pl_taxe_mod,       "2024-01-01"),
            (pl_esg_limite,     "2023-12-01"),
            (pl_mkt_cours,      "2024-02-01"),
        ]:
            Company_Policy.objects.get_or_create(
                company=acme,
                policy_level=policy_level,
                defaults={"policy_date": date_str},
            )

        # ── Émissions carbone (démo, tCO2e) ───────────────────────────────────
        carbon_rows = [
            (2018, 'Scope 1', 32000), (2018, 'Scope 2', 18000), (2018, 'Scope 3', 95000),
            (2019, 'Scope 1', 31000), (2019, 'Scope 2', 17500), (2019, 'Scope 3', 92000),
            (2020, 'Scope 1', 28000), (2020, 'Scope 2', 16000), (2020, 'Scope 3', 85000),
            (2021, 'Scope 1', 27000), (2021, 'Scope 2', 15500), (2021, 'Scope 3', 82000),
            (2022, 'Scope 1', 25000), (2022, 'Scope 2', 14000), (2022, 'Scope 3', 78000),
            (2023, 'Scope 1', 23500), (2023, 'Scope 2', 13000), (2023, 'Scope 3', 74000),
            (2024, 'Scope 1', 22000), (2024, 'Scope 2', 12000), (2024, 'Scope 3', 70000),
        ]
        for yr, scope, val in carbon_rows:
            Flow.objects.get_or_create(
                kind=FlowKind.EMISSION, what=co2, from_company=acme,
                to_environment=True, scope=scope, year=yr,
                defaults={'quantity': float(val)},
            )

        # ── Conformité ESRS E4 (démo) ─────────────────────────────────────────

        a_para.near_sensitive_zone = True
        a_para.sensitive_zone_type = Asset.SensitiveZoneType.IUCN_KBA
        a_para.sensitive_zone_name = "Amazonie orientale — Key Biodiversity Area"
        a_para.sensitive_zone_area_ha = 1850.0
        a_para.save()

        a_sumatra.near_sensitive_zone = True
        a_sumatra.sensitive_zone_type = Asset.SensitiveZoneType.NATIONAL_PROTECTED
        a_sumatra.sensitive_zone_name = "Parc national de Tesso Nilo"
        a_sumatra.sensitive_zone_area_ha = 1230.0
        a_sumatra.save()

        assessment, _ = E4Assessment.objects.get_or_create(
            company=acme,
            reporting_year=2024,
            defaults={
                "created_by": demo_user,
                "standard_version": E4Assessment.StandardVersion.AMENDED_2025,
                "materiality_status": E4Assessment.Materiality.MATERIAL,
                "materiality_justification": (
                    "Biodiversité jugée matérielle : exposition forte (soja Cerrado, "
                    "palme Sumatra) à proximité de zones sensibles, dépendances "
                    "écosystémiques élevées sur les filières oléagineuses."
                ),
                "leap_locate_status": E4Assessment.LeapStatus.DONE,
                "leap_evaluate_status": E4Assessment.LeapStatus.IN_PROGRESS,
                "leap_assess_status": E4Assessment.LeapStatus.IN_PROGRESS,
                "leap_locate_notes": (
                    "2 sites identifiés en/près de zones sensibles (Pará, Sumatra)."
                ),
                "leap_evaluate_notes": (
                    "Dépendances eau et qualité des sols évaluées ; pollinisation en cours."
                ),
                "leap_assess_notes": (
                    "Impacts matériels confirmés sur la déforestation ; risques en cours "
                    "de chiffrage."
                ),
            },
        )

        e4_demo = [
            ("E4_1", DisclosureRequirement.Status.PARTIAL,
             "Plan de transition en cours de rédaction, alignement Kunming-Montréal visé "
             "pour 2027 ; objectifs intermédiaires non encore publiés."),
            ("E4_2", DisclosureRequirement.Status.COMPLIANT,
             "Politique biodiversité couvrant la traçabilité soja/palme et les sites "
             "proches de zones sensibles (RSPO, EUDR)."),
            ("E4_3", DisclosureRequirement.Status.PARTIAL,
             "Actions de restauration financées sur 2 sites ; hiérarchie d'atténuation "
             "appliquée hors compensation, offsets non encore engagés."),
            ("E4_4", DisclosureRequirement.Status.NON_COMPLIANT,
             "Cibles chiffrées absentes : seuils écologiques et portée géographique non "
             "définis à ce jour."),
            ("E4_5", DisclosureRequirement.Status.COMPLIANT,
             "Métrique géospatiale publiée : 2 sites en zone sensible, 3 080 ha au total, "
             "avec impacts négatifs documentés."),
        ]
        for code, status, justif in e4_demo:
            DisclosureRequirement.objects.get_or_create(
                assessment=assessment,
                code=code,
                defaults={"status": status, "justification": justif},
            )

        # ── Données ESG & portefeuille de démonstration ───────────────────────

        for year, employees in [(2022, 1_850), (2023, 1_920), (2024, 1_980)]:
            ESG_data.objects.get_or_create(
                company=acme, year=year, defaults={"employees_number": employees},
            )

        eur, _ = Currency.objects.get_or_create(
            code="EUR", defaults={"name": "Euro", "symbol": "€", "ratio_USD": 1.08},
        )

        # Le portefeuille appartient à un utilisateur : sans compte en base, on le
        # saute plutôt que de créer un fonds orphelin.
        if demo_user is not None:
            portfolio, _ = Portfolio.objects.get_or_create(
                name="Fonds démo Easybiodiv",
                defaults={
                    "size": 20_000_000,
                    "currency": eur,
                    "is_shared": True,
                    "created_by": demo_user,
                },
            )
            PortfolioHolding.objects.get_or_create(
                portfolio=portfolio, company=acme,
                defaults={
                    "amount": 12_000_000,
                    "weight": 60.0,
                    "instrument_type": PortfolioHolding.Instrument.EQUITY,
                },
            )

        # ── Résumé ────────────────────────────────────────────────────────────

        owned = Asset.objects.owned_by(acme)
        flows_by_kind = {
            kind.label: Flow.objects.filter(kind=kind).count() for kind in FlowKind
        }
        self.stdout.write(self.style.SUCCESS(
            "\nAcme Corp — données créées avec succès !\n"
            "  Pays           : France, Brésil, Indonésie\n"
            "  Régions        : Bretagne, Occitanie, Mato Grosso, Pará, Sumatra\n"
            f"  Actifs détenus : {owned.count()} (3 FR · 2 BR · 1 ID)\n"
            "  Commodités     : Blé, Maïs, Soja, Huile de palme + 5 techniques\n"
            "  Chiffre d'aff. : 452,6 M€ (2024)\n"
            "  Politiques     : 15 niveaux définis, 5 appliqués à Acme Corp\n"
            "  Conformité     : E4Assessment 2024 + 5 exigences de publication\n"
            "  Profil         : exposition modérée-haute au risque de transition\n"
            "\n  Flux (table Flow, toutes entreprises) :\n"
            + "".join(f"    {label:<20} {count}\n" for label, count in flows_by_kind.items())
        ))
