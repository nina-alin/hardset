"""Modèle de données du générateur de sets.

Module sans dépendance : il ne connaît ni le XML Rekordbox, ni la configuration,
ni le web. Toutes les autres couches en dépendent.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum

# Bornes de l'échelle de mood. Les libellés vivent dans la configuration ;
# seule l'étendue de l'échelle est une constante du code.
MOOD_MIN = 1
MOOD_MAX = 5


def normalize_tag(value: str) -> str:
    """Forme comparable d'un tag : minuscules, sans accents, sans espaces de bordure.

    Permet de reconnaître « Vénère », « venere » et «  VÉNÈRE  » comme un seul tag.
    """
    decomposed = unicodedata.normalize("NFD", value.strip().lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class Track:
    """Un morceau de la collection, tel que lu dans l'export XML.

    `raw_attrs` porte l'intégralité des attributs du nœud TRACK d'origine : l'export
    les recopie sans les comprendre, ce qui évite toute perte d'information.
    """

    id: str
    artist: str
    title: str
    bpm: float
    camelot: str | None
    duration_s: int
    location: str
    genres: tuple[str, ...] = ()
    mood: int | None = None
    raw_attrs: dict[str, str] = field(default_factory=dict, compare=False)

    @property
    def label(self) -> str:
        return f"{self.artist} — {self.title}"


@dataclass(frozen=True)
class Target:
    """Cible visée à une position du set. `mood` n'est volontairement pas arrondi."""

    position: int
    bpm: float
    mood: float


class WarningCode(str, Enum):
    """Nature d'un avertissement, pour permettre un regroupement côté interface."""

    SHORTAGE = "shortage"                # moins de morceaux éligibles que demandé
    NO_MOOD = "no_mood"                  # morceau sans tag de mood
    MULTIPLE_MOODS = "multiple_moods"    # morceau portant plusieurs tags de mood
    NO_KEY = "no_key"                    # tonalité absente ou illisible
    NO_TRACK_ID = "no_track_id"          # morceau sans TrackID, absent de la collection


@dataclass(frozen=True)
class SetWarning:
    """Problème rencontré, à afficher sans interrompre la génération.

    Nommée `SetWarning` et non `Warning` pour ne pas masquer le type natif.
    """

    code: WarningCode
    message: str
    track_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SetRequest:
    """Le set demandé. `genres` ou `moods` vides valent « tous ».

    `seed` n'est pas exposée dans l'interface : elle ne sert qu'à rendre la
    génération reproductible dans les tests.
    """

    genres: frozenset[str]
    moods: frozenset[int]
    bpm_min: float
    bpm_max: float
    profile: str
    duration_min: int
    seconds_per_track: int = 120
    seed: int | None = None

    @property
    def track_count(self) -> int:
        """Nombre de morceaux visé, au moins 1."""
        return max(1, int(self.duration_min * 60 // self.seconds_per_track))


@dataclass
class GeneratedSet:
    """Résultat d'une génération : les morceaux dans l'ordre de jeu et leurs cibles."""

    tracks: list[Track] = field(default_factory=list)
    targets: list[Target] = field(default_factory=list)
    warnings: list[SetWarning] = field(default_factory=list)
