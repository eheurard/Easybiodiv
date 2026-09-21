"""Écrit un classeur Excel ne contenant que la feuille « Flow ».

    python manage.py export_flows                      # tous les flux
    python manage.py export_flows --company "Acme Corp" --company Antofagasta
    python manage.py export_flows --output C:/tmp/flux.xlsx

Le fichier produit est celui qu'attend l'import (Imports → Charger un fichier).
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Company
from imports.services.excel_export import build_flow_export

DEFAULT_OUTPUT = Path('media') / 'exports' / 'easybiodiv_flows.xlsx'


class Command(BaseCommand):
    help = "Exporte la table Flow dans un classeur Excel réimportable"

    def add_arguments(self, parser):
        parser.add_argument(
            '--company', action='append', dest='companies', metavar='NOM',
            help="Limite l'export à cette entreprise (répétable). Par défaut, tout.",
        )
        parser.add_argument(
            '--output', default=str(DEFAULT_OUTPUT), metavar='CHEMIN',
            help=f"Fichier à écrire (défaut : {DEFAULT_OUTPUT}).",
        )

    def handle(self, *args, **options):
        companies = []
        for name in options['companies'] or []:
            company = Company.objects.filter(name__iexact=name).first()
            if company is None:
                raise CommandError(f"Entreprise introuvable : « {name} »")
            companies.append(company)

        buffer, count = build_flow_export(companies)

        output = Path(options['output'])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(buffer.getvalue())

        scope = (
            ', '.join(c.name for c in companies) if companies
            else 'toutes les entreprises'
        )
        self.stdout.write(self.style.SUCCESS(
            f"{count} flux exportés ({scope}) → {output.resolve()}"
        ))
