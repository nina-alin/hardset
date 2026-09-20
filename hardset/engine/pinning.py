"""Morceaux imposés aux extrémités du set, et accord des BPM à leur tempo.

Module pur, comme le reste de `hardset/engine/`.

`bpm_min` et `bpm_max` portent deux rôles à la fois : ce sont les extrémités de
la courbe (`engine/curves.build_targets`) et les bornes du vivier
(`engine/filtering.eligible`). Accorder une borne au morceau épinglé la déplace
donc pour **tout le set** : un son de départ à 182 BPM écarte du vivier tout ce
qui est plus lent. C'est voulu — un set qui ouvre à 182 n'a rien à faire à 150
ensuite — et c'est la même confusion des deux rôles qui interdit les sets
descendants : la plage dérivée serait vide.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from hardset.model import SetRequest, Track


class PinningError(Exception):
    """Choix d'épinglage inexploitable : morceau introuvable, ou plage vide."""


@dataclass(frozen=True)
class Pins:
    """Morceaux imposés aux extrémités du set. `None` quand rien n'est choisi."""

    start: Track | None = None
    end: Track | None = None

    @property
    def epingles(self) -> tuple[Track, ...]:
        """Les morceaux effectivement choisis, départ d'abord."""
        return tuple(t for t in (self.start, self.end) if t is not None)


def resolve(tracks: Iterable[Track], request: SetRequest) -> tuple[SetRequest, Pins]:
    """Résout les morceaux épinglés et accorde la plage de BPM à leur tempo.

    Rend la demande accordée et les morceaux résolus. La borne qui n'a pas de
    morceau choisi est laissée telle quelle.

    Idempotente : appliquée à son propre résultat, elle rend le même couple — la
    borne dérivée est déjà celle du morceau épinglé. C'est ce qui autorise
    `generate`, `shortage_warnings` et la couche web à l'appeler chacune pour son
    compte, sans se coordonner et sans risque de dérive.
    """
    if request.start_track_id is None and request.end_track_id is None:
        return request, Pins()

    if request.start_track_id is not None and request.start_track_id == request.end_track_id:
        raise PinningError(
            "le même morceau ne peut pas être à la fois le son de départ et le son de fin"
        )

    par_id = {track.id: track for track in tracks}
    pins = Pins(
        start=_retrouve(par_id, request.start_track_id),
        end=_retrouve(par_id, request.end_track_id),
    )

    accordee = replace(
        request,
        bpm_min=pins.start.bpm if pins.start is not None else request.bpm_min,
        bpm_max=pins.end.bpm if pins.end is not None else request.bpm_max,
    )
    if accordee.bpm_min > accordee.bpm_max:
        raise PinningError(_plage_vide(pins, request))
    return accordee, pins


def _retrouve(par_id: dict[str, Track], track_id: str | None) -> Track | None:
    if track_id is None:
        return None
    try:
        return par_id[track_id]
    except KeyError as exc:
        raise PinningError(f"morceau {track_id} absent de la collection") from exc


def _plage_vide(pins: Pins, request: SetRequest) -> str:
    """Message de plage vide, nommant ce qu'il faut corriger.

    Deux morceaux épinglés en ordre inverse, ou un seul qui sort de la borne
    restée saisie : même impasse, mais ce n'est pas la même chose à corriger.
    """
    if pins.start is not None and pins.end is not None:
        return (
            f"le son de fin ({pins.end.bpm:g} BPM) est plus lent que le son de "
            f"départ ({pins.start.bpm:g} BPM)"
        )
    if pins.start is not None:
        return (
            f"le son de départ ({pins.start.bpm:g} BPM) dépasse le BPM max "
            f"demandé ({request.bpm_max:g})"
        )
    assert pins.end is not None   # un des deux au moins est résolu à ce stade
    return (
        f"le son de fin ({pins.end.bpm:g} BPM) est plus lent que le BPM min "
        f"demandé ({request.bpm_min:g})"
    )
