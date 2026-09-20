"""Données publiées par Antofagasta plc, chargées telles quelles.

Contrairement à `populate_acme` (jeu fictif de démonstration), toutes les
quantités de ce fichier proviennent des rapports publics du groupe. Chaque flux
porte sa source dans `Flow.source` et le libellé de la ligne d'origine dans
`Flow.reference`.

Sources (consultées en septembre 2026) :

* PROD24  — Q4 2024 Production Report, 16 janvier 2025
            production et sous-produits par mine, 2023 et 2024.
* AR25    — Annual Report and Financial Statements 2025
            production 2025 par mine, revenus par segment, GES du groupe.
* SR24    — Sustainability Report 2024
            eau et GES par site 2021-2024, énergie du groupe.

Deux retraitements, signalés dans le `reference` de chaque ligne concernée :

* Zaldívar est une coentreprise 50/50 avec Barrick et le groupe ne publie que sa
  quote-part de production. Les quantités stockées ici sont celles du site (× 2),
  cohérentes avec les émissions de Zaldívar, publiées elles à 100 % : l'intensité
  de 1,99 tCO₂e/tCu publiée ne se retrouve qu'à ce périmètre.
* Les carburants sont publiés en TJ et convertis en MWh (1 TJ = 277,778 MWh),
  unité de la commodité technique « Énergie ».
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import models, transaction

from dashboard.models import (
    Asset, Commodity, Company, Company_Revenue, Company_Revenue_Sector, Country,
    Flow, FlowKind, FlowScope, Ownership, SubSector, SubnationalRegion,
)

PROD24 = "Antofagasta plc — Q4 2024 Production Report (16/01/2025)"
AR25 = "Antofagasta plc — Annual Report and Financial Statements 2025"
SR24 = "Antofagasta Minerals — Sustainability Report 2024"

TJ_TO_MWH = 1_000_000 / 3_600  # 1 TJ = 277,778 MWh


def _flow(kind, what, year, quantity, *, source, reference, created_by=None,
          revenue=None, **endpoints):
    """Écrit un flux réel.

    `reference` fait partie de la clé de recherche : c'est elle qui distingue
    deux lignes d'un même site et d'une même année, comme les quatre origines
    d'eau de Los Pelambres. Une nouvelle exécution corrige les quantités si le
    chiffre publié a été révisé.
    """
    defaults = {'quantity': float(quantity), 'source': source, 'created_by': created_by}
    if revenue is not None:
        defaults['estimated_revenue'] = float(revenue)
    Flow.objects.update_or_create(
        kind=kind, what=what, year=year, reference=reference, **endpoints,
        defaults=defaults,
    )


class Command(BaseCommand):
    help = "Charge les données publiées par Antofagasta plc (production, eau, GES)"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Chargement des données publiées par Antofagasta plc…")

        author = (
            get_user_model().objects.filter(is_superuser=True).first()
            or get_user_model().objects.first()
        )

        # ── Pays et régions ───────────────────────────────────────────────────
        #
        # Les noms des régions chiliennes ont été importés en double encodage
        # (« RegiÃ³n de Antofagasta »). Les deux régions utilisées ici sont
        # corrigées et pourvues de leur centroïde ; les autres restent en l'état.

        chile, _ = Country.objects.get_or_create(name="Chile")

        antofagasta_region = self._fix_region(
            chile, 'RegiÃ³n de Antofagasta', "Región de Antofagasta",
            mean_x=-69.50, mean_y=-23.60,
        )
        coquimbo = self._fix_region(
            chile, 'RegiÃ³n de Coquimbo', "Región de Coquimbo",
            mean_x=-71.00, mean_y=-30.60,
        )

        # ── Entreprise ────────────────────────────────────────────────────────

        anto, _ = Company.objects.update_or_create(
            name="Antofagasta",
            defaults={
                "description": (
                    "Antofagasta plc — groupe minier chilien coté à Londres, contrôlé "
                    "par le groupe Luksic. Quatre mines de cuivre au Chili (Los "
                    "Pelambres, Centinela, Antucoya, Zaldívar) et une division "
                    "transport (FCAB). 653 700 t de cuivre produites en 2025."
                ),
                "isin": "GB0000456144",
                "ticker": "ANTO",
            },
        )

        # ── Commodités ────────────────────────────────────────────────────────

        # Le cuivre existe déjà en base sous son nom anglais : on le garde pour
        # ne pas casser les imports Excel qui s'y réfèrent, et on le complète.
        copper, _ = Commodity.objects.get_or_create(name="copper")
        copper.description = (
            "Cuivre — concentrés et cathodes. Niveaux de dépendance issus du "
            "référentiel ENCORE pour l'extraction de minerais métalliques."
        )
        copper.unit = "tonnes"
        copper.dependency_water = 'VH'
        copper.dependency_water_purification = 'M'
        copper.dependency_soil_quality = 'VL'
        copper.dependency_pollination = 'VL'
        copper.dependency_carbon_sequestration = 'VL'
        copper.dependency_pest_control = 'VL'
        copper.biodiversity_loss_class = 'Mining'
        copper.save()

        gold, _ = Commodity.objects.get_or_create(
            name="Or",
            defaults={
                "description": "Sous-produit des concentrés de cuivre.",
                "unit": "onces troy",
                "dependency_water": 'VH',
                "biodiversity_loss_class": 'Mining',
            },
        )
        molybdenum, _ = Commodity.objects.get_or_create(
            name="Molybdène",
            defaults={
                "description": "Sous-produit des concentrés de cuivre.",
                "unit": "tonnes",
                "dependency_water": 'VH',
                "biodiversity_loss_class": 'Mining',
            },
        )
        silver, _ = Commodity.objects.get_or_create(
            name="Argent",
            defaults={
                "description": "Sous-produit des concentrés de cuivre.",
                "unit": "onces troy",
                "dependency_water": 'VH',
                "biodiversity_loss_class": 'Mining',
            },
        )

        water = Commodity.objects.technical('water')
        energy = Commodity.objects.technical('energy')
        co2 = Commodity.objects.technical('co2')

        # ── Actifs ────────────────────────────────────────────────────────────

        pelambres = self._update_asset(
            "Los Pelambres mine", coquimbo, (-31.7166, -70.4881),
            "Gisement de sulfures, région de Coquimbo, 240 km au nord de Santiago. "
            "Concentrés de cuivre avec sous-produits or, argent et molybdène. Usine "
            "de dessalement à pleine capacité (400 l/s) depuis mars 2024.",
            sensitive_zone={
                'near_sensitive_zone': True,
                'sensitive_zone_type': Asset.SensitiveZoneType.OTHER,
                'sensitive_zone_name': (
                    "Sanctuaires de la nature de la vallée du Choapa (Laguna Conchalí, "
                    "Palma Chilena de Monte Aranda, Quebrada Llau Llau, Cerro Santa Inés)"
                ),
                'sensitive_zone_area_ha': 27_808.0,
            },
        )
        centinela = self._update_asset(
            "Centinela mine", antofagasta_region, (-22.9736, -69.0600),
            "Sulfures et oxydes, commune de Sierra Gorda, 1 350 km au nord de "
            "Santiago. Concentrés et cathodes de cuivre. Alimentée à 100 % en eau de "
            "mer depuis 2022.",
        )
        antucoya = self._update_asset(
            "Antucoya mine", antofagasta_region, (-22.6299, -69.8766),
            "Gisement d'oxydes, 125 km au nord-est d'Antofagasta. Lixiviation en tas "
            "et électro-extraction (SX-EW), cathodes de cuivre. Eau de mer.",
        )
        zaldivar = self._update_asset(
            "Zaldivar mine", antofagasta_region, (-24.2010, -69.0655),
            "Mine à ciel ouvert d'oxydes à 3 000 m d'altitude, 175 km au sud-est "
            "d'Antofagasta. Lixiviation en tas. Coentreprise 50/50 avec Barrick, "
            "opérée par Antofagasta. Seule opération du groupe encore alimentée en "
            "eaux souterraines continentales.",
        )

        # ── Détentions (AR25, Mineral Resources and Ore Reserves) ─────────────

        for asset, share, note in [
            (pelambres, Decimal('0.60'),
             "40 % détenus par un consortium japonais (MMC / Nippon Mining)."),
            (centinela, Decimal('0.70'), "30 % détenus par Marubeni Corporation."),
            (antucoya, Decimal('0.70'), "30 % détenus par Marubeni Corporation."),
            (zaldivar, Decimal('0.50'),
             "Coentreprise 50/50 avec Barrick Mining Corporation."),
        ]:
            Ownership.objects.update_or_create(
                asset=asset, company=anto, end_year=None,
                defaults={'share': share, 'description': note, 'created_by': author},
            )

        # ── Production de cuivre par mine (kt → t) ────────────────────────────
        #
        # Base 100 % du site. Le revenu porté par la ligne cuivre est celui du
        # segment (AR25, note 5) : il couvre aussi les sous-produits de la mine.

        for asset, y23, y24, y25, rev24, rev25 in [
            (pelambres, 300.3, 319.6, 295.3, 3_326.7, 4_131.0),
            (centinela, 242.0, 223.8, 240.4, 2_359.2, 3_478.5),
            (antucoya, 77.8, 80.4, 81.2, 732.6, 837.3),
        ]:
            for year, kt, revenue in [
                (2023, y23, None), (2024, y24, rev24), (2025, y25, rev25),
            ]:
                _flow(
                    FlowKind.PRODUCTION, copper, year, kt * 1_000,
                    source=PROD24 if year < 2025 else AR25,
                    reference="Production de cuivre (base 100 % du site)",
                    created_by=author,
                    revenue=revenue * 1_000_000 if revenue else None,
                    from_asset=asset,
                )

        # Zaldívar n'est publiée qu'en quote-part : ramenée au site pour rester
        # cohérente avec ses émissions, publiées à 100 %.
        for year, attributable in [(2023, 40.5), (2024, 40.1), (2025, 36.7)]:
            _flow(
                FlowKind.PRODUCTION, copper, year, attributable * 2 * 1_000,
                source=PROD24 if year < 2025 else AR25,
                reference="Production de cuivre (quote-part 50 % publiée × 2 = site)",
                created_by=author, from_asset=zaldivar,
            )

        # ── Sous-produits ─────────────────────────────────────────────────────

        for asset, rows in [
            (pelambres, {2023: 43.3, 2024: 46.6, 2025: 54.8}),
            (centinela, {2023: 165.8, 2024: 140.3, 2025: 156.5}),
        ]:
            for year, koz in rows.items():
                _flow(
                    FlowKind.PRODUCTION, gold, year, koz * 1_000,
                    source=PROD24 if year < 2025 else AR25,
                    reference="Production d'or (sous-produit)",
                    created_by=author, from_asset=asset,
                )

        for asset, rows in [
            (pelambres, {2023: 8.1, 2024: 8.4, 2025: 12.4}),
            (centinela, {2023: 2.9, 2024: 2.4, 2025: 3.4}),
        ]:
            for year, kt in rows.items():
                _flow(
                    FlowKind.PRODUCTION, molybdenum, year, kt * 1_000,
                    source=PROD24 if year < 2025 else AR25,
                    reference="Production de molybdène (sous-produit)",
                    created_by=author, from_asset=asset,
                )

        # L'argent n'est publié qu'au niveau du groupe : flux porté par
        # l'entreprise, sans actif d'origine (autorisé par FLOW_RULES).
        for year, moz in [(2023, 3.1), (2024, 2.8), (2025, 3.4)]:
            _flow(
                FlowKind.PRODUCTION, silver, year, moz * 1_000_000,
                source=AR25, reference="Production d'argent du groupe (sous-produit)",
                created_by=author, from_company=anto,
            )

        # ── Eau prélevée par site et par origine (mégalitres → m³) ────────────
        #
        # « Operational water withdrawals » au sens ICMM. Eau de mer, de surface
        # et souterraine viennent du milieu ; l'eau achetée à des tiers n'a pas
        # d'origine renseignée.

        for asset, origin, ml_2023, ml_2024, from_environment in [
            (pelambres, "Eau de mer (dessalement)", 13_044, 24_536, True),
            (pelambres, "Eaux de surface", 15_188, 23_340, True),
            (pelambres, "Eaux souterraines", 10_568, 11_224, True),
            (pelambres, "Fournie par des tiers", 7, 7, False),
            (centinela, "Eau de mer", 28_961, 27_683, True),
            (centinela, "Eaux souterraines", 1_560, 1_416, True),
            (antucoya, "Eau de mer", 6_840, 7_621, True),
            (antucoya, "Eaux souterraines", 241, 275, True),
            (zaldivar, "Eaux souterraines", 5_502, 6_548, True),
        ]:
            for year, megalitres in [(2023, ml_2023), (2024, ml_2024)]:
                _flow(
                    FlowKind.CONSUMPTION, water, year, megalitres * 1_000,
                    source=SR24, reference=f"Prélèvement d'eau — {origin}",
                    created_by=author,
                    from_environment=from_environment, to_asset=asset,
                )

        # ── Émissions de GES par site (Scope 1, tCO₂e) ────────────────────────
        #
        # Le Scope 2 market-based des quatre mines est nul depuis avril 2022 :
        # 100 % d'électricité renouvelable sous contrat.

        for asset, t_2023, t_2024 in [
            (pelambres, 271_281, 276_630),
            (centinela, 551_766, 543_519),
            (zaldivar, 132_813, 160_011),
            (antucoya, 232_316, 248_579),
        ]:
            for year, tonnes in [(2023, t_2023), (2024, t_2024)]:
                _flow(
                    FlowKind.EMISSION, co2, year, tonnes,
                    source=SR24, reference="Émissions directes du site (Scope 1)",
                    created_by=author,
                    scope=FlowScope.SCOPE_1, from_asset=asset, to_environment=True,
                )

        # ── Émissions déclarées par le groupe (division minière) ──────────────

        for year, scope, tonnes in [
            (2021, FlowScope.SCOPE_1, 987_949), (2021, FlowScope.SCOPE_2, 968_825),
            (2022, FlowScope.SCOPE_1, 1_113_581), (2022, FlowScope.SCOPE_2, 95_236),
            (2023, FlowScope.SCOPE_1, 1_188_386), (2023, FlowScope.SCOPE_2, 16),
            (2024, FlowScope.SCOPE_1, 1_228_924), (2024, FlowScope.SCOPE_2, 887),
        ]:
            _flow(
                FlowKind.EMISSION, co2, year, tonnes,
                source=SR24,
                reference="Division minière — Scope 2 market-based",
                created_by=author,
                scope=scope, from_company=anto, to_environment=True,
            )

        _flow(
            FlowKind.EMISSION, co2, 2025, 1_319_884,
            source=AR25,
            reference="Division minière — Scope 1+2 market-based (ventilation non publiée)",
            created_by=author,
            scope=FlowScope.SCOPE_1_2, from_company=anto, to_environment=True,
        )

        # ── Énergie consommée par le groupe ───────────────────────────────────

        for year, gwh in [(2023, 3_393), (2024, 3_951)]:
            _flow(
                FlowKind.CONSUMPTION, energy, year, gwh * 1_000,
                source=SR24, reference="Électricité (100 % renouvelable sous contrat)",
                created_by=author, to_company=anto,
            )

        for year, terajoules in [(2023, 16_704), (2024, 16_649)]:
            _flow(
                FlowKind.CONSUMPTION, energy, year, terajoules * TJ_TO_MWH,
                source=SR24, reference="Carburants (publiés en TJ, convertis en MWh)",
                created_by=author, to_company=anto,
            )

        # ── Chiffre d'affaires ────────────────────────────────────────────────

        for year, millions in [(2023, 6_324.5), (2024, 6_613.4), (2025, 8_620.3)]:
            Company_Revenue.objects.update_or_create(
                company=anto, year=year,
                defaults={"revenue": millions * 1_000_000, "currency": "USD"},
            )

        mining = SubSector.objects.filter(name="Mining of metal ores").first()
        if mining is not None:
            for year, millions in [(2024, 6_418.5), (2025, 8_446.8)]:
                Company_Revenue_Sector.objects.update_or_create(
                    company=anto, subsector=mining, year=year,
                    defaults={"revenue": millions * 1_000_000},
                )

        self._report(anto)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fix_region(self, country, stored_name, real_name, mean_x, mean_y):
        """Région chilienne, avec son nom rétabli si l'import l'a mal encodé."""
        region = (
            SubnationalRegion.objects.filter(country=country, name=real_name).first()
            or SubnationalRegion.objects.filter(country=country, name=stored_name).first()
            or SubnationalRegion(country=country, name=real_name)
        )
        region.name = real_name
        region.Mean_X = mean_x
        region.Mean_Y = mean_y
        region.save()
        return region

    def _update_asset(self, name, region, coordinates, description, sensitive_zone=None):
        """Mine du groupe, créée si elle manque. Les coordonnées ne servent qu'à
        la création : celles déjà en base priment."""
        latitude, longitude = coordinates
        asset, _ = Asset.objects.get_or_create(
            name=name,
            defaults={
                'country': region.country,
                'latitude': latitude,
                'longitude': longitude,
            },
        )
        asset.description = description
        asset.subnational_region = region
        asset.country = region.country
        asset.type = 'Mine'
        for field, value in (sensitive_zone or {}).items():
            setattr(asset, field, value)
        asset.save()
        return asset

    def _report(self, company):
        assets = list(Asset.objects.owned_by(company).values_list('pk', flat=True))
        flows = Flow.objects.filter(
            models.Q(from_asset__in=assets) | models.Q(to_asset__in=assets)
            | models.Q(from_company=company) | models.Q(to_company=company)
        )
        by_kind = {kind.label: flows.filter(kind=kind).count() for kind in FlowKind}
        self.stdout.write(self.style.SUCCESS(
            "\nAntofagasta plc — données publiées chargées\n"
            f"  Mines          : {len(assets)} (Los Pelambres 60 % · Centinela 70 % · "
            "Antucoya 70 % · Zaldívar 50 %)\n"
            "  Production     : cuivre 2023-2025, or et molybdène par mine, argent groupe\n"
            "  Eau            : prélèvements par origine et par site, 2023-2024\n"
            "  GES            : Scope 1 par site 2023-2024, groupe 2021-2025\n"
            "  Chiffre d'aff. : 8 620,3 M$ (2025)\n"
            "\n  Flux rattachés à Antofagasta :\n"
            + "".join(f"    {label:<20} {count}\n" for label, count in by_kind.items())
        ))
