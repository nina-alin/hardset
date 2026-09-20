"""Lecture d'un export XML de collection Rekordbox.

Hypothèse non vérifiée : Rekordbox écrirait les My Tags dans l'attribut `Comments`
du nœud TRACK, sous la forme `/* tag / tag */`, éventuellement entourée d'un
commentaire libre. Aucun export Rekordbox réel n'a jamais été lu par ce projet :
cette hypothèse n'a donc jamais été confrontée à un vrai fichier. `tools/
inspect_collection.py` est la sonde prévue pour trancher la question dès qu'un
export réel sera disponible ; si l'export réel la contredit, c'est ici — le motif et
le séparateur ci-dessous — qu'il faut regarder en premier. Le XML ne transporte pas
la catégorie du tag : la distinction genre / mood se fait donc par la configuration
— tout tag reconnu comme mood est le mood, **tout autre tag est un genre**.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from hardset.config import Config
from hardset.engine.harmony import to_camelot
from hardset.model import SetWarning, Track, WarningCode, normalize_tag

# Bloc de My Tags dans `Comments` : encode l'hypothèse non vérifiée décrite dans la
# docstring du module. Si un export réel la contredit, c'est cette expression et le
# séparateur qui changent en premier.
_TAGS_RE = re.compile(r"/\*(.*?)\*/", re.DOTALL)
_TAG_SEPARATOR = "/"


class CollectionError(Exception):
    """Export XML introuvable ou illisible."""


def parse_my_tags(comments: str | None) -> tuple[str, ...]:
    """Tags contenus dans `Comments`, dans leur casse d'origine.

    Les tags sont rendus non normalisés : l'interface les affiche tels que Nina les
    a écrits dans Rekordbox. La normalisation ne sert qu'aux comparaisons.
    """
    if not comments:
        return ()
    match = _TAGS_RE.search(comments)
    if not match:
        return ()
    return tuple(
        tag.strip()
        for tag in match.group(1).split(_TAG_SEPARATOR)
        if tag.strip()
    )


def _float(value: str | None) -> float:
    try:
        return float(value) if value else 0.0
    except ValueError:
        return 0.0


def _int(value: str | None) -> int:
    try:
        return int(float(value)) if value else 0
    except ValueError:
        return 0


@dataclass(frozen=True)
class Collection:
    """La collection lue, avec les avertissements relevés à la lecture."""

    tracks: tuple[Track, ...]
    warnings: tuple[SetWarning, ...] = ()

    @property
    def genres(self) -> tuple[str, ...]:
        """Genres réellement présents, triés, dédoublonnés à la normalisation."""
        vus: dict[str, str] = {}
        for track in self.tracks:
            for genre in track.genres:
                vus.setdefault(normalize_tag(genre), genre)
        return tuple(sorted(vus.values(), key=normalize_tag))

    @property
    def bpm_range(self) -> tuple[float, float]:
        """Plage de BPM des morceaux exploitables, pour préremplir le formulaire."""
        bpms = [t.bpm for t in self.tracks if t.bpm > 0]
        return (min(bpms), max(bpms)) if bpms else (0.0, 0.0)


def _enfants(noeud: ElementTree.Element) -> tuple[str, ...]:
    """Nœuds enfants d'un TRACK, sérialisés tels quels.

    Un vrai export porte sous chaque TRACK sa beatgrid (`TEMPO`) et ses points
    de repère (`POSITION_MARK`) : ils ne sont pas interprétés, seulement
    transportés jusqu'à l'export, qui doit rendre le nœud intact. La queue
    (`tail`) de chaque enfant, qui n'est que l'indentation du fichier lu, est
    écartée pour ne pas être recopiée dans le fichier produit.
    """
    fragments: list[str] = []
    for enfant in noeud:
        enfant.tail = None
        fragments.append(ElementTree.tostring(enfant, encoding="unicode"))
    return tuple(fragments)


def read_collection(path: Path, config: Config) -> Collection:
    """Lit l'export XML et classe les tags de chaque morceau en genres et mood.

    Un morceau sans mood, ou portant plusieurs moods, est **conservé** dans la
    collection avec `mood = None` : il sera exclu de la sélection, et signalé ici.
    Un morceau sans TrackID, en revanche, ne peut pas être référencé dans une
    playlist : il est retiré de la collection elle-même (pas seulement de la
    sélection), et signalé ici aussi.
    """
    chemin = Path(path).expanduser()
    try:
        racine = ElementTree.parse(chemin).getroot()
    except FileNotFoundError as exc:
        raise CollectionError(f"export introuvable : {chemin}") from exc
    except ElementTree.ParseError as exc:
        raise CollectionError(f"XML illisible dans {chemin} : {exc}") from exc
    except OSError as exc:
        # Chemin fourni par l'utilisatrice via un formulaire : un répertoire
        # (`IsADirectoryError`) ou un fichier sans droit de lecture
        # (`PermissionError`) doivent produire un message clair, pas une
        # exception brute remontée jusqu'à l'interface web.
        raise CollectionError(f"impossible de lire {chemin} : {exc}") from exc

    tracks: list[Track] = []
    sans_mood: list[str] = []
    moods_multiples: list[str] = []
    sans_cle: list[str] = []
    sans_track_id: list[str] = []

    for noeud in racine.findall("./COLLECTION/TRACK"):
        attrs = dict(noeud.attrib)
        identifiant = attrs.get("TrackID", "")
        if not identifiant:
            # Un nœud sans TrackID ne peut pas être référencé dans une playlist :
            # il est écarté de la collection elle-même. Il n'a pas de TrackID à
            # inscrire dans `track_ids` ; artiste/titre servent à le retrouver.
            sans_track_id.append(f"{attrs.get('Artist', '?')} — {attrs.get('Name', '?')}")
            continue

        genres: list[str] = []
        moods: list[int] = []
        for tag in parse_my_tags(attrs.get("Comments")):
            valeur = config.mood_value(tag)
            if valeur is None:
                genres.append(tag)
            else:
                moods.append(valeur)

        if len(moods) == 1:
            mood = moods[0]
        else:
            mood = None
            (moods_multiples if moods else sans_mood).append(identifiant)

        camelot = to_camelot(attrs.get("Tonality"))
        if camelot is None:
            sans_cle.append(identifiant)

        tracks.append(
            Track(
                id=identifiant,
                artist=attrs.get("Artist", ""),
                title=attrs.get("Name", ""),
                bpm=_float(attrs.get("AverageBpm")),
                camelot=camelot,
                duration_s=_int(attrs.get("TotalTime")),
                location=attrs.get("Location", ""),
                genres=tuple(genres),
                mood=mood,
                raw_attrs=attrs,
                raw_children=_enfants(noeud),
            )
        )

    avertissements: list[SetWarning] = []
    for code, ids, gabarit in (
        (
            WarningCode.NO_TRACK_ID,
            sans_track_id,
            "{n} morceaux sans TrackID sont ignorés (absents de la collection)",
        ),
        (
            WarningCode.MULTIPLE_MOODS,
            moods_multiples,
            "{n} morceaux portent plusieurs moods et sont exclus de la sélection (mais restent dans la collection)",
        ),
        (
            WarningCode.NO_MOOD,
            sans_mood,
            "{n} morceaux sans mood sont exclus de la sélection (mais restent dans la collection)",
        ),
        (WarningCode.NO_KEY, sans_cle, "{n} morceaux sans tonalité analysée"),
    ):
        if ids:
            avertissements.append(
                SetWarning(code=code, message=gabarit.format(n=len(ids)), track_ids=tuple(ids))
            )

    return Collection(tracks=tuple(tracks), warnings=tuple(avertissements))
