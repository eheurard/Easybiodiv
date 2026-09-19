"""Sauvegarde SQLite lancée par .cpanel.yml avant migrate (spec 2026-09-18 §9)."""
import io
import sqlite3
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase


class BackupSqliteCommandTests(SimpleTestCase):

    def test_copies_the_database_next_to_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'db.sqlite3'
            connection = sqlite3.connect(source)
            connection.execute('CREATE TABLE t (x INTEGER)')
            connection.execute('INSERT INTO t VALUES (42)')
            connection.commit()
            connection.close()

            call_command('backup_sqlite', source=str(source), stdout=io.StringIO())

            backup = sqlite3.connect(Path(tmp) / 'db.sqlite3.pre-deploy')
            value = backup.execute('SELECT x FROM t').fetchone()[0]
            backup.close()
            self.assertEqual(value, 42)

    def test_a_missing_database_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            call_command('backup_sqlite', source=str(Path(tmp) / 'absente.sqlite3'), stdout=out)
            self.assertIn('aucune sauvegarde', out.getvalue())
            self.assertEqual(list(Path(tmp).iterdir()), [])
