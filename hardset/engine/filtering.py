"""Réduction de la collection aux morceaux éligibles à une demande.

Un critère vide vaut « tous » et n'est alors pas appliqué du tout : un morceau sans
aucun genre reste éligible si aucun genre n'est demandé.
"""

from __future__ import annotations

from collections.abc import Iterable

from hardset.model import SetRequest, Track, normalize_tag


def eligible(tracks: Iterable[Track], request: SetRequest) -> list[Track]:
    """Morceaux retenus pour la sélection, dans leur ordre d'origine.

    Sont écartés : les morceaux sans mood unique (mood absent ou multiple, déjà
    ramené à `None` par le lecteur), ceux dont le mood ou le BPM sort de la demande,
    et — si des genres sont demandés — ceux qui n'en partagent aucun.
    """
    genres_demandes = {normalize_tag(g) for g in request.genres}

    retenus: list[Track] = []
    for track in tracks:
        if track.mood is None:
            continue
        if request.moods and track.mood not in request.moods:
            continue
        if not request.bpm_min <= track.bpm <= request.bpm_max:
            continue
        if genres_demandes:
            if not genres_demandes & {normalize_tag(g) for g in track.genres}:
                continue
        retenus.append(track)
    return retenus
