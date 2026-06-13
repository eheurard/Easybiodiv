from django.core.management.base import BaseCommand
from django.db import transaction

from dashboard.models import (
    Asset, Commodity, Company, Company_Policy, Company_Revenue,
    Company_Revenue_Sector, Country, DisclosureRequirement, E4Assessment,
    Ownership, Policy_Level, Policy_Subcategory, Policy_Type, Production,
    Sector, SubSector, SubnationalRegion,
)


class Command(BaseCommand):
    help = "Peuple la base avec des données artificielles pour Acme Corp (risque de transition)"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Création des données Acme Corp…")

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
                "description": "Région nord-ouest, industrie agroalimentaire dense",
                "restoration_cost_m2": 50.0,
                "Mean_X": -2.80,
                "Mean_Y": 48.10,
            },
        )

        occitanie, _ = SubnationalRegion.objects.get_or_create(
            name="Occitanie",
            country=france,
            defaults={
                "description": "Région sud, grandes cultures céréalières",
                "restoration_cost_m2": 42.0,
                "Mean_X": 2.35,
                "Mean_Y": 43.60,
            },
        )

        mato_grosso, _ = SubnationalRegion.objects.get_or_create(
            name="Mato Grosso",
            country=brazil,
            defaults={
                "description": "État de la frontière agricole du soja, Cerrado",
                "restoration_cost_m2": 30.0,
                "Mean_X": -55.00,
                "Mean_Y": -12.50,
            },
        )

        para, _ = SubnationalRegion.objects.get_or_create(
            name="Pará",
            country=brazil,
            defaults={
                "description": "État amazonien à fort risque de déforestation",
                "restoration_cost_m2": 35.0,
                "Mean_X": -51.00,
                "Mean_Y": -3.80,
            },
        )

        sumatra, _ = SubnationalRegion.objects.get_or_create(
            name="Sumatra",
            country=indonesia,
            defaults={
                "description": "Île principale de la production d'huile de palme",
                "restoration_cost_m2": 25.0,
                "Mean_X": 102.00,
                "Mean_Y": 0.50,
            },
        )

        # ── Secteurs & sous-secteurs ──────────────────────────────────────────

        sector_agri, _ = Sector.objects.get_or_create(
            name="Agriculture",
            defaults={"NACE_code": "A01", "description": "Production végétale et animale"},
        )

        sector_food, _ = Sector.objects.get_or_create(
            name="Industrie alimentaire",
            defaults={"NACE_code": "C10", "description": "Transformation des produits alimentaires"},
        )

        ss_cereales, _ = SubSector.objects.get_or_create(
            name="Grandes cultures céréalières",
            defaults={
                "sector": sector_agri,
                "NACE_code": "A01.1",
                "description": "Blé, maïs, colza",
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
                "description": "Soja, palmier à huile",
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
                "description": "Raffinage et conditionnement d'huiles",
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
                "impact_midpoint_ReCiPe2016_water_consumption": 1.21,
                "impact_midpoint_ReCiPe2016_climate_change": 0.29,
                "impact_midpoint_ReCiPe2016_freshwater_ecotoxicity": 0.008,
                "impact_midpoint_ReCiPe2016_land_use": 2.8,
                "impact_endpoint_ReCiPe2016_ecosystem_diversity": 0.0014,
                "impact_endpoint_GBS_terrestrial_dynamic": 0.42,
                "impact_endpoint_GBS_terrestrial_static": 0.38,
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
                "impact_midpoint_ReCiPe2016_water_consumption": 1.58,
                "impact_midpoint_ReCiPe2016_climate_change": 0.33,
                "impact_midpoint_ReCiPe2016_freshwater_ecotoxicity": 0.012,
                "impact_midpoint_ReCiPe2016_land_use": 3.1,
                "impact_endpoint_ReCiPe2016_ecosystem_diversity": 0.0017,
                "impact_endpoint_GBS_terrestrial_dynamic": 0.48,
                "impact_endpoint_GBS_terrestrial_static": 0.43,
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
                "impact_midpoint_ReCiPe2016_water_consumption": 2.14,
                "impact_midpoint_ReCiPe2016_climate_change": 0.72,
                "impact_midpoint_ReCiPe2016_freshwater_ecotoxicity": 0.021,
                "impact_midpoint_ReCiPe2016_land_use": 6.5,
                "impact_endpoint_ReCiPe2016_ecosystem_diversity": 0.0048,
                "impact_endpoint_GBS_terrestrial_dynamic": 1.12,
                "impact_endpoint_GBS_terrestrial_static": 0.95,
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
                "impact_midpoint_ReCiPe2016_water_consumption": 3.45,
                "impact_midpoint_ReCiPe2016_climate_change": 1.82,
                "impact_midpoint_ReCiPe2016_freshwater_ecotoxicity": 0.038,
                "impact_midpoint_ReCiPe2016_land_use": 12.0,
                "impact_endpoint_ReCiPe2016_ecosystem_diversity": 0.0095,
                "impact_endpoint_GBS_terrestrial_dynamic": 2.45,
                "impact_endpoint_GBS_terrestrial_static": 2.10,
                "dependency_water": "VH",
                "dependency_pollination": "H",
                "dependency_soil_quality": "VH",
                "dependency_carbon_sequestration": "VH",
                "dependency_water_purification": "VH",
                "dependency_pest_control": "H",
                "biodiversity_loss_class": "Agriculture",
            },
        )

        # ── Entreprise ────────────────────────────────────────────────────────

        acme, _ = Company.objects.get_or_create(
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

        # ── Propriétés ────────────────────────────────────────────────────────

        for asset, pct in [
            (a_bretagne, "100%"),
            (a_occitanie, "100%"),
            (a_mato_grosso, "75%"),
            (a_para, "100%"),
            (a_sumatra, "60%"),
        ]:
            Ownership.objects.get_or_create(Asset=asset, Company=acme, defaults={"ownership": pct})

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
            Production.objects.get_or_create(
                asset=asset,
                commodity=commodity,
                scope=scope,
                year=year,
                defaults={
                    "company": acme,
                    "production": qty,
                    "estimated_revenue": revenue,
                    "country": asset.country,
                    "subnational_region": asset.subnational_region,
                },
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

        self.stdout.write(self.style.SUCCESS(
            "\nAcme Corp — données créées avec succès !\n"
            "  Pays           : France, Brésil, Indonésie\n"
            "  Régions        : Bretagne, Occitanie, Mato Grosso, Pará, Sumatra\n"
            "  Actifs         : 5 (2 FR · 2 BR · 1 ID)\n"
            "  Commodités     : Blé, Maïs, Soja, Huile de palme\n"
            "  Productions    : 12 entrées (2023-2024)\n"
            "  Chiffre d'aff. : 452,6 M€ (2024)\n"
            "  Types politi.  : Risque Réglementaire, Risque de Marché\n"
            "  Sous-catégories: EUDR · CSRD/ESRS E4 · Taxe biodiversité · ESG · Marchés durables\n"
            "  Politiques     : 15 niveaux définis, 5 appliqués à Acme Corp\n"
            "  Profil         : exposition modérée-haute au risque de transition\n"
        ))
