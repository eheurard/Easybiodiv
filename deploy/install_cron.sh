#!/bin/bash
# Installe ou met à jour la tâche cron mensuelle de purge des comptes inactifs
# (durée annoncée par la politique de confidentialité) dans la crontab de
# l'utilisateur cPanel. Lancé par .cpanel.yml à chaque déploiement.
#
# Idempotent : seule la ligne portant MARKER est remplacée ; les autres tâches
# (sauvegarde SQLite de docs/deploiement-production.md §4…) sont conservées.
#
# Usage : deploy/install_cron.sh <dossier bin du virtualenv>
set -eu

VENV_BIN="$1"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$HOME/logs"
MARKER='# easybiodiv:purge_inactive_accounts'
# Le 1er de chaque mois à 4 h. Journal hors du dépôt : un fichier non suivi
# dans le dépôt bloquerait les déploiements cPanel suivants.
LINE="0 4 1 * * cd $REPO && $VENV_BIN/python manage.py purge_inactive_accounts"
LINE="$LINE >> $LOG_DIR/easybiodiv-purge.log 2>&1 $MARKER"

mkdir -p "$LOG_DIR"
# Lue entièrement avant réécriture : lire et réinstaller dans un même pipeline
# risquerait de tronquer la crontab avant sa lecture.
CURRENT="$(crontab -l 2>/dev/null || true)"
{
    if [ -n "$CURRENT" ]; then printf '%s
' "$CURRENT" | grep -vF "$MARKER" || true; fi
    echo "$LINE"
} | crontab -
echo "Tâche cron installée : $LINE"

# Une tâche cron ne reçoit pas les variables de « Setup Python App » : sans
# .env, settings.py s'arrête faute de SECRET_KEY.
if [ ! -f "$REPO/.env" ]; then
    echo "ATTENTION : $REPO/.env absent, la tâche cron échouera (SECRET_KEY introuvable)."
fi
