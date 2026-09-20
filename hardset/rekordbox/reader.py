"""Lecture d'un export XML de collection Rekordbox.

Rekordbox écrit les My Tags dans l'attribut `Comments` du nœud TRACK, sous la
forme `/* tag / tag */`, éventuellement entourée d'un commentaire libre. Ce
format a été **observé** sur un export réel (rekordbox 7.2.18, 706 morceaux, le
2026-09-20), dont `tests/fixtures/collection_reelle.xml` est un extrait
verbatim. Il n'apparaît toutefois que si le réglage Rekordbox qui recopie les My
Tags dans les commentaires est actif : sans lui, `Comments` ne porte que du texte
libre et la collection paraît entièrement non taguée. `tools/
inspect_collection.py` reste la sonde pour le constater sur un export donné.

Le XML ne transporte pas la **catégorie** d'un tag. Le lecteur la déduit donc par
élimination, dans cet ordre :

1. un tag reconnu par `Config.mood_value` est un niveau de mood ;
2. un tag déclaré dans `tags_ignores` (état de préparation, jouabilité) est
   écarté ;
3. un tag qui a la forme d'une plage de BPM (`140-150`, `195+`) est écarté
   aussi : `AverageBpm` porte déjà l'information, exactement ;
4. **tout le reste est un genre.**

L'ordre compte, et le sens de la règle 4 aussi : un genre ajouté dans Rekordbox
apparaît sans qu'on touche à la configuration, qui n'a à nommer que les
catégories fermées.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from hardset.config import Config
from hardset.engine.harmony import to_camelot
from hardset.model import SetWarning, Track, WarningCode, normalize_tag

# Bloc de My Tags dans `Comments`, au format décrit dans la docstring du module.
_TAGS_RE = re.compile(r"/\*(.*?)\*/", re.DOTALL)
_TAG_SEPARATOR = "/"

# Tags de plage de BPM (`110-120`, `195+`). Reconnus à la forme et non par une
# liste : ils forment une famille ouverte, et une plage ajoutée dans Rekordbox
# ne doit pas se mettre à peupler la liste des genres. Le tag n'est pas lu comme
# un intervalle — il est seulement écarté ; `AverageBpm` est plus précis.
_PLAGE_BPM_RE = re.compile(r"^\d{2,3}\s*(?:-\s*\d{2,3}|\+)$")


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
        """Plage de BPM des morceaux à BPM renseigné, pour préremplir le formulaire.

        Tous les morceaux dont le BPM est supérieur à zéro comptent, y compris
        ceux qui seront exclus de la sélection faute de mood : le formulaire
        propose une plage, il ne présume pas de la demande.
        """
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
    """Lit l'export XML et classe les tags de chaque morceau (voir la docstring du module).

    Un morceau portant plusieurs moods est jouable : son énergie est leur
    moyenne (`Track.mood`), et il reste filtrable sur chacun d'eux
    (`Track.moods`). Il est tout de même signalé — l'information est utile pour
    repérer un tag posé par erreur.

    Un morceau sans aucun mood est **conservé** dans la collection, mais sera
    exclu de la sélection faute de savoir où le placer sur la courbe ; il est
    signalé. Un morceau sans TrackID, en revanche, ne peut pas être référencé
    dans une playlist : il est retiré de la collection elle-même (pas seulement
    de la sélection), et signalé aussi.
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
        niveaux: set[int] = set()
        for tag in parse_my_tags(attrs.get("Comments")):
            valeur = config.mood_value(tag)
            if valeur is not None:
                niveaux.add(valeur)
            elif config.tag_ignore(tag) or _PLAGE_BPM_RE.match(tag):
                continue
            else:
                genres.append(tag)

        # Trié pour que deux lectures du même morceau donnent le même tuple, et
        # dédoublonné pour qu'un tag répété (« DANSANT / dansant ») ne passe pas
        # pour deux moods.
        moods = tuple(sorted(niveaux))
        if not moods:
            sans_mood.append(identifiant)
        elif len(moods) > 1:
            moods_multiples.append(identifiant)

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
                moods=moods,
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
            "{n} morceaux portent plusieurs moods : leur énergie est la moyenne de ces moods",
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
