"""Écriture du XML de playlist destinée à être réimportée dans Rekordbox.

D'après la documentation du format, Rekordbox exige que tout morceau référencé
dans une playlist figure dans le bloc COLLECTION du même fichier. Les nœuds TRACK
sont donc recopiés depuis `raw_attrs` et `raw_children`, sans aucune
modification : attributs, beatgrid (`TEMPO`) et points de repère
(`POSITION_MARK`) sont restitués tels qu'ils ont été lus, sans que l'outil ait à
les comprendre. Les seuls nœuds TRACK reconstruits sont ceux dont `raw_attrs`
est vide, c'est-à-dire ceux qui ne viennent pas d'un export lu.

Hypothèse non vérifiée, elle aussi tirée de la documentation du format : l'import
serait additif, et supprimer ensuite la playlist importée ne laisserait aucune
trace dans la collection Rekordbox. Aucun fichier produit par ce module n'a jamais
été réimporté dans Rekordbox : cette hypothèse n'a donc jamais été confrontée à un
import réel, à aucune étape du projet. La vérifier demande un vrai Rekordbox et
reste entièrement à faire.
"""

from __future__ import annotations

import io
import re
from collections.abc import Sequence
from datetime import date
from xml.etree import ElementTree

from hardset.model import SetRequest, Track, normalize_tag


def slug(value: str) -> str:
    """Forme utilisable dans un nom de fichier : ASCII, sans accent, sans espace.

    Publique : la couche web s'en sert aussi pour bâtir le `filename` ASCII de
    l'en-tête `content-disposition` de l'export, qui ne tolère rien d'autre.
    """
    return re.sub(r"[^a-z0-9]+", "-", normalize_tag(value)).strip("-")


def default_playlist_name(request: SetRequest, today: date | None = None) -> str:
    """Nom proposé dans le formulaire : `{genres}-{profil}-{durée}min-{date}`."""
    jour = today or date.today()
    genres = "-".join(sorted(slug(g) for g in request.genres)) if request.genres else "tous"
    return f"{genres}-{slug(request.profile)}-{request.duration_min}min-{jour.isoformat()}"


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
    # apparition. `raw_attrs` et `raw_children` sont recopiés tels quels.
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
        noeud = ElementTree.SubElement(collection, "TRACK", attrs)
        # Beatgrid et points de repère du nœud d'origine : réinjectés dans
        # l'ordre, sans être relus ni corrigés.
        for enfant in track.raw_children:
            noeud.append(ElementTree.fromstring(enfant))

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

    # Déclaration écrite à la main, en guillemets doubles : celle que produit
    # `ElementTree` (xml_declaration=True) utilise des guillemets simples, valides
    # mais inhabituels dans les fichiers XML réels. Le parseur de Rekordbox nous est
    # inconnu et n'a été éprouvé à aucune étape du projet : autant coller à la forme
    # la plus courante, à coût nul.
    tampon = io.BytesIO()
    ElementTree.ElementTree(racine).write(tampon, encoding="UTF-8", xml_declaration=False)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tampon.getvalue()
