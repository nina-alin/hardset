"""Tonalités : normalisation en Camelot et pénalité d'enchaînement.

Rekordbox écrit `Tonality` en notation classique, en Camelot ou en Open Key selon
les préférences de l'utilisateur. Tout est ramené en Camelot (1A–12B), qui rend la
proximité harmonique lisible comme une distance sur une roue.

La pénalité ne porte que sur la transition immédiate : on favorise des
enchaînements deux à deux, on ne cherche pas à tenir une tonalité sur la durée.
"""

from __future__ import annotations

import re

# Camelot de chaque note, en majeur (lettre B) puis en mineur (lettre A).
_MAJOR: dict[str, int] = {
    "c": 8, "g": 9, "d": 10, "a": 11, "e": 12, "b": 1,
    "f#": 2, "gb": 2, "db": 3, "c#": 3, "ab": 4, "g#": 4,
    "eb": 5, "d#": 5, "bb": 6, "a#": 6, "f": 7,
}
_MINOR: dict[str, int] = {
    "a": 8, "e": 9, "b": 10, "f#": 11, "gb": 11, "c#": 12, "db": 12,
    "g#": 1, "ab": 1, "d#": 2, "eb": 2, "bb": 3, "a#": 3,
    "f": 4, "c": 5, "g": 6, "d": 7,
}

_MINOR_SUFFIXES = {"m", "min", "minor", "mi"}
_MAJOR_SUFFIXES = {"", "maj", "major", "ma"}

_CAMELOT_RE = re.compile(r"^(\d{1,2})([ab])$")
_OPEN_KEY_RE = re.compile(r"^(\d{1,2})([dm])$")
_CLASSIC_RE = re.compile(r"^([a-g][#b]?)(.*)$")


def to_camelot(tonality: str | None) -> str | None:
    """Ramène une tonalité en Camelot (`"1A"`–`"12B"`), ou `None` si illisible.

    Une valeur illisible n'écarte pas le morceau : elle lui donne simplement une
    pénalité neutre au moment du séquençage.
    """
    if not tonality:
        return None
    brut = tonality.strip().lower().replace(" ", "")
    if not brut:
        return None

    # Déjà en Camelot (« 8A »). Testé avant Open Key : « 8a » n'est pas ambigu.
    match = _CAMELOT_RE.match(brut)
    if match:
        numero, lettre = int(match.group(1)), match.group(2).upper()
        return f"{numero}{lettre}" if 1 <= numero <= 12 else None

    # Open Key (« 1m », « 6d ») : le numéro est décalé de 7 crans vers Camelot.
    match = _OPEN_KEY_RE.match(brut)
    if match:
        numero, mode = int(match.group(1)), match.group(2)
        if not 1 <= numero <= 12:
            return None
        camelot = ((numero + 6) % 12) + 1
        return f"{camelot}{'A' if mode == 'm' else 'B'}"

    # Notation classique (« Am », « F#m », « Bb », « Cmaj »).
    match = _CLASSIC_RE.match(brut)
    if match:
        note, suffixe = match.group(1), match.group(2)
        if suffixe in _MINOR_SUFFIXES and note in _MINOR:
            return f"{_MINOR[note]}A"
        if suffixe in _MAJOR_SUFFIXES and note in _MAJOR:
            return f"{_MAJOR[note]}B"
    return None


def _split(camelot: str) -> tuple[int, str]:
    return int(camelot[:-1]), camelot[-1]


def key_penalty(previous: str | None, candidate: str | None) -> float:
    """Coût harmonique de l'enchaînement `previous` → `candidate`.

    Une clé inconnue vaut 0,5 : ni récompense, ni exclusion.
    """
    if previous is None or candidate is None:
        return 0.5

    numero_avant, lettre_avant = _split(previous)
    numero_apres, lettre_apres = _split(candidate)

    if lettre_avant != lettre_apres:
        # Relatif majeur / mineur : même chiffre, autre lettre.
        return 0 if numero_avant == numero_apres else 2

    ecart = (numero_apres - numero_avant) % 12
    distance = min(ecart, 12 - ecart)
    if distance <= 1:      # même clé ou voisin immédiat
        return 0
    if distance == 2:
        return 1
    return 2
