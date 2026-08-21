"""**Exécution** — normalisation du texte lu (§3-J.3, étape 4). 100 % déterministe.

Le modèle rend un texte « tel qu'il croit l'avoir vu ». Ce module en fait un numéro de
course ou rien du tout, par des règles fixes et testables :

1. majuscules, suppression des séparateurs et préfixes usuels (`N°`, `#`, espaces, tirets) ;
2. confusions typographiques usuelles sur du texte peint : `O/D → 0`, `I/L → 1`, `S → 5`,
   `B → 8`, `Z → 2` ;
3. suppression des caractères non numériques résiduels ;
4. **rejet** si le résultat ne correspond pas à `^[0-9]{1,3}$`.

Une confusion est un pari : « SO » devient « 50 », ce qui est correct sur une carrosserie
et catastrophique sur un logo de sponsor. On garde donc trace du **nombre de caractères
qui étaient déjà des chiffres** (`digit_purity`) : `scoring.py` s'en sert pour pénaliser
une lecture obtenue à coups de substitutions, sans jamais l'interdire.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Confusions retenues (§3-J.3, étape 4). Liste **fermée** et volontairement courte :
#: chaque entrée supplémentaire augmente le rappel et le taux de faux positifs à la fois.
CONFUSIONS: dict[str, str] = {
    "O": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "S": "5",
    "B": "8",
    "Z": "2",
}

#: Caractères purement décoratifs, retirés avant toute autre règle.
_SEPARATORS = re.compile(r"[\s\-_.,;:/\\'\"«»()\[\]{}#°º*+]")
#: Préfixe « numéro » écrit à la française ou à l'anglaise, fréquemment collé au chiffre.
_NUMBER_PREFIX = re.compile(r"^(?:N|NO|NR|NUM)(?=\d)")

#: Un numéro de course tient sur 1 à 3 chiffres (§3-J.3, étape 4).
CAR_NUMBER_RE = re.compile(r"^[0-9]{1,3}$")


@dataclass(frozen=True, slots=True)
class NormalizedText:
    """Résultat de la normalisation. `number is None` ⇒ la lecture n'est pas un numéro."""

    raw: str
    number: str | None
    #: Fraction des caractères retenus qui étaient **déjà** des chiffres avant confusion.
    #: 1.0 = lecture purement numérique ; 0.0 = intégralement reconstruite par substitution.
    digit_purity: float
    #: Nombre de substitutions typographiques appliquées — exposé pour le journal/debug.
    substitutions: int


def normalize_text(raw: str) -> NormalizedText:
    """Applique les 4 règles ci-dessus. Ne lève jamais."""
    cleaned = _SEPARATORS.sub("", raw).upper()
    cleaned = _NUMBER_PREFIX.sub("", cleaned)

    if not cleaned:
        return NormalizedText(raw=raw, number=None, digit_purity=0.0, substitutions=0)

    digits: list[str] = []
    already_digit = 0
    substitutions = 0
    for char in cleaned:
        if char.isdigit():
            digits.append(char)
            already_digit += 1
        elif char in CONFUSIONS:
            digits.append(CONFUSIONS[char])
            substitutions += 1
        # Tout autre caractère est purement et simplement abandonné (règle 3).

    candidate = "".join(digits)
    kept = len(candidate)
    purity = (already_digit / kept) if kept else 0.0

    number = candidate if CAR_NUMBER_RE.match(candidate) else None
    return NormalizedText(raw=raw, number=number, digit_purity=purity, substitutions=substitutions)


def canonical_number(number: str) -> str:
    """Forme canonique pour la comparaison à la table des engagements.

    « 07 », « 7 » et « 007 » désignent la même voiture ; la table peut porter l'une ou
    l'autre écriture selon la fédération. On compare donc des formes canoniques des deux
    côtés de la jointure, jamais des chaînes brutes. Toute valeur non numérique est rendue
    telle quelle (une table d'engagements peut, elle, contenir « 7B » — dans ce cas aucune
    lecture OCR numérique ne matchera, ce qui est le comportement voulu : on ne devine pas).
    """
    stripped = number.strip()
    if not stripped.isdigit():
        return stripped.upper()
    return str(int(stripped))
