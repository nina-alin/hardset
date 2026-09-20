"""Courbes d'évolution : d'un profil et d'une durée vers une liste de cibles.

Trois types de courbe paramétriques, et pas de code arbitraire en configuration :
un profil décrit une intention musicale, il n'exécute rien.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from hardset.config import CurveSpec, Profile
from hardset.model import MOOD_MAX, MOOD_MIN, SetRequest, Target


class CurveError(Exception):
    """Type de courbe inconnu."""


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def curve_fn(spec: CurveSpec) -> Callable[[float], float]:
    """Traduit une courbe de configuration en fonction de progression `[0,1] → [0,1]`."""
    if spec.type == "lineaire":
        depart = spec.params.get("depart", 0.0)
        arrivee = spec.params.get("arrivee", 1.0)
        return lambda t: _clamp(depart + t * (arrivee - depart))

    if spec.type == "retarde":
        palier = min(max(spec.params.get("palier", 0.0), 0.0), 0.99)
        return lambda t: _clamp(0.0 if t <= palier else (t - palier) / (1.0 - palier))

    if spec.type == "vagues":
        amplitude = spec.params.get("amplitude", 0.15)
        oscillations = spec.params.get("oscillations", 2.0)
        return lambda t: _clamp(t + amplitude * math.sin(2 * math.pi * oscillations * t))

    raise CurveError(f"type de courbe '{spec.type}' inconnu")


def build_targets(
    request: SetRequest,
    profile: Profile,
    count: int,
    mood_max: int = MOOD_MAX,
) -> list[Target]:
    """Cible (BPM, mood) de chaque position du set.

    `mood` reste un flottant : un set peut viser « entre dansant et un peu vénère ».

    `mood_max` est le haut de l'échelle réellement configurée (`Config.mood_max`),
    que les appelants passent quand ils en disposent. Sans mood demandé, la
    courbe balaie toute l'échelle : viser `MOOD_MAX` alors que la configuration
    n'en déclare que trois reviendrait à viser un niveau qui n'existe pas.
    """
    if count <= 0:
        return []

    p_bpm = curve_fn(profile.bpm)
    p_mood = curve_fn(profile.mood)

    # Sans mood demandé, la courbe balaie toute l'échelle.
    mood_min = min(request.moods) if request.moods else MOOD_MIN
    mood_haut = max(request.moods) if request.moods else mood_max

    cibles: list[Target] = []
    for i in range(count):
        t = i / max(count - 1, 1)
        cibles.append(
            Target(
                position=i,
                bpm=request.bpm_min + p_bpm(t) * (request.bpm_max - request.bpm_min),
                mood=mood_min + p_mood(t) * (mood_haut - mood_min),
            )
        )
    return cibles
