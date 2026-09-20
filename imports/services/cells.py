"""Lecture des cellules à format métier, partagée par l'analyseur et l'importeur."""
import math
from decimal import Decimal, InvalidOperation

SHARE_QUANTUM = Decimal('0.0001')


def parse_share(value):
    """Part de détention : '75%', '75 %', '0.75' ou '0,75' → Decimal('0.7500').

    Renvoie None si la valeur est vide, illisible ou hors de ]0, 1]. Sans « % »,
    une valeur supérieure à 1 est refusée (75 ou 0,75 ?) ; '1' vaut 100 %.
    """
    text = str(value if value is not None else '').strip().replace(',', '.')
    if not text:
        return None
    percent = text.endswith('%')
    if percent:
        text = text[:-1].strip()
    try:
        share = Decimal(text)
    except InvalidOperation:
        return None
    if not share.is_finite():
        return None
    if percent:
        share = share / 100
    if not 0 < share <= 1:
        return None
    return share.quantize(SHARE_QUANTUM)


def parse_optional_year(value):
    """Année facultative : '' → None ; '2024' ou '2024.0' → 2024.

    Lève ValueError si la cellule n'est pas une année lisible.
    """
    text = str(value if value is not None else '').strip()
    if not text:
        return None
    return int(float(text))


def parse_number(value):
    """Nombre : '12,5' ou '12.5' → 12.5 (virgule ou point décimal, espaces
    ignorés).

    Lève ValueError si la cellule est vide ou n'est pas un nombre fini.
    """
    text = str(value if value is not None else '').strip().replace(',', '.')
    text = ''.join(text.split())
    if not text:
        raise ValueError('valeur vide')
    result = float(text)
    if not math.isfinite(result):
        raise ValueError('valeur non finie')
    return result


def parse_int(value):
    """Entier : '2024' ou '2024.0' → 2024.

    Lève ValueError si la cellule est vide, non numérique, ou porte une partie
    décimale non nulle ('2024.5', 'FY2024').
    """
    number = parse_number(value)
    if not number.is_integer():
        raise ValueError(f"'{value}' n'est pas un entier")
    return int(number)
