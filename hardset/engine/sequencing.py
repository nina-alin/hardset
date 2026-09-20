"""Séquençage du set : remplissage position par position.

Pour chaque position, tous les morceaux encore disponibles sont notés, et le retenu
est tiré uniformément parmi les `k` de coût le plus faible. C'est la seule source
d'aléa : la courbe est toujours respectée, mais deux générations diffèrent.

L'algorithme est glouton et ne revient jamais en arrière. Sur quelques centaines de
titres l'effet est inaudible, et la tracklist reste éditable.
"""

from __future__ import annotations

import random
from collections.abc import Iterable

from hardset.config import Config, Weights
from hardset.engine.curves import build_targets
from hardset.engine.filtering import eligible
from hardset.engine.harmony import key_penalty
from hardset.model import GeneratedSet, SetRequest, SetWarning, Target, Track, WarningCode


class SequencingError(Exception):
    """Demande inexploitable : profil inconnu, position hors du set."""


def cost(candidate: Track, target: Target, previous: Track | None, weights: Weights) -> float:
    """Coût d'un candidat à une position donnée. Plus bas, mieux c'est.

    La première position n'a pas de prédécesseur : la pénalité harmonique y vaut 0,
    et non 0,5 — l'absence de voisin n'est pas une tonalité inconnue.
    """
    tolerance = weights.bpm_tolerance if weights.bpm_tolerance > 0 else 1.0
    penalite = 0.0 if previous is None else key_penalty(previous.camelot, candidate.camelot)
    mood = candidate.mood if candidate.mood is not None else target.mood
    return (
        weights.bpm * abs(candidate.bpm - target.bpm) / tolerance
        + weights.mood * abs(mood - target.mood)
        + weights.tonalite * penalite
    )


def _pick(
    pool: list[Track],
    target: Target,
    previous: Track | None,
    weights: Weights,
    rng: random.Random,
) -> Track:
    """Tire un morceau parmi les `k` moins coûteux et le retire du pool.

    Le tri secondaire par `id` rend le résultat reproductible à graine fixée, sans
    dépendre de l'ordre d'itération du pool.
    """
    notes = sorted(
        pool,
        key=lambda track: (cost(track, target, previous, weights), track.id),
    )
    choisi = rng.choice(notes[: max(1, weights.k)])
    pool.remove(choisi)
    return choisi


def _profile(request: SetRequest, config: Config):
    try:
        return config.profils[request.profile]
    except KeyError as exc:
        connus = ", ".join(sorted(config.profils))
        raise SequencingError(
            f"profil '{request.profile}' inexistant (disponibles : {connus})"
        ) from exc


def generate(tracks: Iterable[Track], request: SetRequest, config: Config) -> GeneratedSet:
    """Construit le set demandé, ou le plus long possible si les morceaux manquent."""
    profile = _profile(request, config)
    pool = eligible(tracks, request)

    vise = request.track_count
    count = min(vise, len(pool))

    avertissements: list[SetWarning] = []
    if count < vise:
        avertissements.append(
            SetWarning(
                code=WarningCode.SHORTAGE,
                message=f"{vise} morceaux demandés, {len(pool)} éligibles",
            )
        )

    targets = build_targets(request, profile, count)
    rng = random.Random(request.seed)

    retenus: list[Track] = []
    precedent: Track | None = None
    for target in targets:
        precedent = _pick(pool, target, precedent, config.poids, rng)
        retenus.append(precedent)

    return GeneratedSet(tracks=retenus, targets=targets, warnings=avertissements)


def replace_at(
    generated: GeneratedSet,
    position: int,
    tracks: Iterable[Track],
    request: SetRequest,
    config: Config,
) -> GeneratedSet:
    """Rejoue le tirage pour une seule position, en excluant le set en place.

    Le voisin précédent est le morceau effectivement en place à `position - 1`.
    Sans candidat disponible, le set est rendu intact avec un avertissement.
    """
    _profile(request, config)   # valide le profil avant toute autre chose
    if not 0 <= position < len(generated.tracks):
        raise SequencingError(
            f"position {position} hors du set (0 à {len(generated.tracks) - 1})"
        )

    deja_places = {track.id for track in generated.tracks}
    pool = [track for track in eligible(tracks, request) if track.id not in deja_places]

    target = generated.targets[position]
    precedent = generated.tracks[position - 1] if position > 0 else None

    if not pool:
        return GeneratedSet(
            tracks=list(generated.tracks),
            targets=list(generated.targets),
            warnings=[
                *generated.warnings,
                SetWarning(
                    code=WarningCode.SHORTAGE,
                    message=f"aucun remplaçant disponible à la position {position + 1}",
                ),
            ],
        )

    rng = random.Random(request.seed)
    remplacant = _pick(pool, target, precedent, config.poids, rng)

    nouveaux = list(generated.tracks)
    nouveaux[position] = remplacant
    return GeneratedSet(
        tracks=nouveaux,
        targets=list(generated.targets),
        warnings=list(generated.warnings),
    )
