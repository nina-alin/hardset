"""Réduction de la collection aux morceaux éligibles à une demande.

Un critère vide vaut « tous » et n'est alors pas appliqué du tout : un morceau sans
aucun genre reste éligible si aucun genre n'est demandé.
"""

from __future__ import annotations

from collections.abc import Iterable

from hardset.model import SetRequest, Track, normalize_tag


def eligible(tracks: Iterable[Track], request: SetRequest) -> list[Track]:
    """Morceaux retenus pour la sélection, dans leur ordre d'origine.

    Sont écartés : les morceaux sans aucun mood, ceux dont le mood ou le BPM
    sort de la demande, et — si des genres sont demandés — ceux qui n'en
    partagent aucun.

    Le filtrage sur le mood porte sur `track.moods`, les niveaux effectivement
    tagués, et non sur `track.mood`, leur moyenne : un morceau tagué DANSANT et
    UN PEU VNR appartient aux deux niveaux, alors que sa moyenne (2,5) n'en
    désigne aucun et le ferait écarter des deux demandes où il a sa place. La
    moyenne ne sert qu'à le **placer** sur la courbe, une fois retenu.
    """
    genres_demandes = {normalize_tag(g) for g in request.genres}

    retenus: list[Track] = []
    for track in tracks:
        if not track.moods:
            continue
        if request.moods and not request.moods.intersection(track.moods):
            continue
        if not request.bpm_min <= track.bpm <= request.bpm_max:
            continue
        if genres_demandes:
            if not genres_demandes & {normalize_tag(g) for g in track.genres}:
                continue
        retenus.append(track)
    return retenus
