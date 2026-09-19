"""Sauvegarde cohérente de la base SQLite avant une migration (spec 2026-09-18 §9)."""
import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = (
        "Copie la base SQLite dans <fichier>.pre-deploy avec l'API backup de sqlite3 "
        '(cohérente en mode WAL, contrairement à une copie de fichier). Écrase la '
        'sauvegarde précédente. Lancée par .cpanel.yml avant migrate.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--source', help='Fichier SQLite à sauvegarder (défaut : base Django).')

    def handle(self, *args, **options):
        source = options['source']
        if source is None:
            if connection.vendor != 'sqlite':
                self.stdout.write('Base non SQLite : aucune sauvegarde.')
                return
            source = connection.settings_dict['NAME']
        source = Path(source)
        if not source.is_file():
            self.stdout.write(f'{source} introuvable : aucune sauvegarde.')
            return
        target = source.with_name(f'{source.name}.pre-deploy')
        src = sqlite3.connect(source)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        self.stdout.write(f'Sauvegarde écrite : {target}')
