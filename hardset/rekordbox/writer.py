"""Écriture du XML de playlist réimportable dans Rekordbox.

Rekordbox exige que tout morceau référencé dans une playlist figure dans le bloc
COLLECTION du même fichier. Les nœuds TRACK sont donc recopiés depuis `raw_attrs`,
sans aucune modification : l'outil n'a pas à comprendre les attributs Rekordbox pour
les restituer.

L'import est additif : supprimer la playlist importée ne laisse aucune trace.
"""

from __future__ import annotations

import io
import re
from collections.abc import Sequence
from datetime import date
from xml.etree import ElementTree

from hardset.model import SetRequest, Track, normalize_tag


def _slug(value: str) -> str:
    """Forme utilisable dans un nom de fichier : sans accent, sans espace."""
    return re.sub(r"[^a-z0-9]+", "-", normalize_tag(value)).strip("-")


def default_playlist_name(request: SetRequest, today: date | None = None) -> str:
    """Nom proposé dans le formulaire : `{genres}-{profil}-{durée}min-{date}`."""
    jour = today or date.today()
    genres = "-".join(sorted(_slug(g) for g in request.genres)) if request.genres else "tous"
    return f"{genres}-{_slug(request.profile)}-{request.duration_min}min-{jour.isoformat()}"


def build_playlist_xml(tracks: Sequence[Track], playlist_name: str) -> bytes:
    """Construit le fichier DJ_PLAYLISTS contenant la collection du set et sa playlist.

    L'ordre de jeu est porté par les références de la playlist ; COLLECTION ne
    contient chaque morceau qu'une fois.
    """
    racine = ElementTree.Element("DJ_PLAYLISTS", {"Version": "1.0.0"})
    ElementTree.SubElement(
        racine,
        "PRODUCT",
        {"Name": "rekordbox", "Version": "6.0.0", "Company": "AlphaTheta"},
    )

    # COLLECTION : les nœuds d'origine, dédoublonnés, dans l'ordre de première
    # apparition. `raw_attrs` est recopié tel quel.
    uniques: dict[str, Track] = {}
    for track in tracks:
        uniques.setdefault(track.id, track)

    collection = ElementTree.SubElement(racine, "COLLECTION", {"Entries": str(len(uniques))})
    for track in uniques.values():
        attrs = dict(track.raw_attrs) or {
            "TrackID": track.id,
            "Name": track.title,
            "Artist": track.artist,
            "AverageBpm": f"{track.bpm:.2f}",
            "TotalTime": str(track.duration_s),
            "Location": track.location,
        }
        ElementTree.SubElement(collection, "TRACK", attrs)

    playlists = ElementTree.SubElement(racine, "PLAYLISTS")
    noeud_racine = ElementTree.SubElement(
        playlists, "NODE", {"Type": "0", "Name": "ROOT", "Count": "1"}
    )
    playlist = ElementTree.SubElement(
        noeud_racine,
        "NODE",
        {"Name": playlist_name, "Type": "1", "KeyType": "0", "Entries": str(len(tracks))},
    )
    for track in tracks:
        ElementTree.SubElement(playlist, "TRACK", {"Key": track.id})

    tampon = io.BytesIO()
    ElementTree.ElementTree(racine).write(tampon, encoding="UTF-8", xml_declaration=True)
    return tampon.getvalue()
