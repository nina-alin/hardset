"""Recherche d'un morceau dans la collection, par artiste ou par titre.

Sert à choisir les sons de départ et de fin. Le module vit dans le moteur et non
dans la route qui l'expose, pour la même raison que le reste : `hardset/web/`
traduit des requêtes HTTP, il ne décide de rien.

La recherche ne connaît **aucun** critère de set : un morceau sans mood, hors
plage de BPM ou hors des genres cochés reste trouvable, donc épinglable. C'est
l'intention — un choix explicite passe avant un filtre coché.
"""

from __future__ import annotations

from collections.abc import Iterable

from hardset.model import Track, normalize_tag


def search(tracks: Iterable[Track], q: str, limit: int) -> tuple[list[Track], bool]:
    """Morceaux dont « artiste titre » contient tous les mots de `q`.

    Rend au plus `limit` morceaux, dans l'ordre de la collection, et un drapeau
    disant qu'il y en avait davantage — la page invite alors à affiner plutôt
    que de laisser croire à une liste complète.

    Une requête vide ne rend rien : dérouler une collection entière n'aide
    personne à choisir.
    """
    mots = normalize_tag(q).split()
    if not mots or limit <= 0:
        return [], False

    trouves: list[Track] = []
    for track in tracks:
        foin = normalize_tag(f"{track.artist} {track.title}")
        if not all(mot in foin for mot in mots):
            continue
        trouves.append(track)
        if len(trouves) > limit:
            return trouves[:limit], True
    return trouves, False
