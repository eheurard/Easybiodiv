"""Lecture des informations légales déclarées dans settings.LEGAL."""

from django.conf import settings
from django.utils.translation import gettext as _

# Toujours exigés : l'identité et le contact du responsable du traitement
# (RGPD, art. 13.1.a), y compris pour un éditeur particulier.
REQUIRED_ALWAYS = ('editor_name', 'contact_email')

# Exigés en plus d'un éditeur professionnel (LCEN, art. 6-III-1). Un particulier
# peut les taire s'il les a communiqués à l'hébergeur (art. 6-III-2).
REQUIRED_PROFESSIONAL = ('editor_address', 'editor_phone', 'publication_director')


def _legal():
    return getattr(settings, 'LEGAL', {})


def required_fields():
    """Champs obligatoires selon le statut, professionnel ou non, de l'éditeur."""
    if _legal().get('editor_professional'):
        return REQUIRED_ALWAYS + REQUIRED_PROFESSIONAL
    return REQUIRED_ALWAYS


def missing_fields():
    """Champs obligatoires de settings.LEGAL absents ou vides."""
    legal = _legal()
    return [key for key in required_fields() if not str(legal.get(key, '')).strip()]


def legal_context():
    """settings.LEGAL prêt pour les gabarits.

    Un champ obligatoire vide est remplacé par un repère visible plutôt que
    d'être omis : une mention légale manquante doit se voir sur la page.
    Les champs facultatifs vides restent vides (les gabarits les masquent).
    """
    info = dict(_legal())
    for key in missing_fields():
        info[key] = _('[à compléter]')
    return info
