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

    `raw_children` porte de la même façon ses nœuds enfants — beatgrid (`TEMPO`)
    et points de repère (`POSITION_MARK`) — sous forme de fragments sérialisés,
    opaques : le modèle ne les interprète pas plus qu'il n'interprète les
    attributs, il les transporte pour que l'export les restitue. Ce sont les
    données les plus coûteuses à reconstituer pour une DJ : elles se refont à la
    main, morceau par morceau.
    """

    id: str
    artist: str
    title: str
    bpm: float
    camelot: str | None
    duration_s: int
    location: str
    genres: tuple[str, ...] = ()
    moods: tuple[int, ...] = ()
    raw_attrs: dict[str, str] = field(default_factory=dict, compare=False)
    raw_children: tuple[str, ...] = field(default=(), compare=False)

    @property
    def mood(self) -> float | None:
        """Énergie du morceau : la moyenne de ses niveaux de mood.

        `None` quand le morceau n'en porte aucun — il est alors exclu de toute
        sélection, faute de savoir où le placer sur la courbe.

        La moyenne n'est pas arrondie : un morceau tagué à la fois DANSANT et
        UN PEU VNR vaut 2,5, et se place naturellement entre les deux paliers.
        C'est la même échelle continue que celle des cibles (`Target.mood`),
        qui ne sont pas arrondies non plus.

        `moods` reste la vérité pour le **filtrage** : un tel morceau appartient
        au niveau 2 comme au niveau 3, pas au niveau 2,5 qui ne désigne aucun
        libellé. Voir `hardset/engine/filtering.py`.
        """
        if not self.moods:
            return None
        return sum(self.moods) / len(self.moods)

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
    REPLACEMENT_SHORTAGE = "replacement_shortage"  # aucun remplaçant dispo pour `replace_at`


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
