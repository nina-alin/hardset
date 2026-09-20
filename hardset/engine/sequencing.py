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

    Précondition : `candidate.mood` n'est pas `None`. C'est `eligible` qui
    l'assure, en écartant en amont les morceaux sans mood. Un appelant qui
    violerait cette précondition échoue immédiatement (`TypeError` sur la
    soustraction) plutôt que d'obtenir silencieusement le meilleur score
    possible : un repli sur `target.mood` annulerait ce terme, ce qui ferait
    d'un morceau sans mood un candidat imbattable — l'inverse de l'intention.

    La première position n'a pas de prédécesseur : la pénalité harmonique y vaut 0,
    et non 0,5 — l'absence de voisin n'est pas une tonalité inconnue.
    """
    tolerance = weights.bpm_tolerance if weights.bpm_tolerance > 0 else 1.0
    penalite = 0.0 if previous is None else key_penalty(previous.camelot, candidate.camelot)
    return (
        weights.bpm * abs(candidate.bpm - target.bpm) / tolerance
        + weights.mood * abs(candidate.mood - target.mood)
        + weights.tonalite * penalite
    )


def _dedoublonne_par_id(tracks: list[Track]) -> list[Track]:
    """Ne garde que la première occurrence de chaque `id`, en préservant l'ordre.

    `Track` est une dataclass figée, comparée par valeur : deux occurrences du
    même morceau (même `id`, un doublon d'entrée non filtré par `eligible`)
    sont égales, et `list.remove` retirerait la première occurrence égale
    plutôt que l'objet effectivement tiré. Sans cette étape, le second
    exemplaire resterait disponible et pourrait être placé une seconde fois.
    """
    vus: set[str] = set()
    retenus: list[Track] = []
    for track in tracks:
        if track.id in vus:
            continue
        vus.add(track.id)
        retenus.append(track)
    return retenus


def _pick(
    pool: list[Track],
    target: Target,
    previous: Track | None,
    weights: Weights,
    rng: random.Random,
) -> Track:
    """Tire un morceau parmi les `k` moins coûteux et le retire du pool.

    Le tri secondaire par `id` rend le résultat reproductible à graine fixée, sans
    dépendre de l'ordre d'itération du pool. Le retrait se fait par `id`, et non
    par égalité de valeur : `pool` est déjà dédoublonné par `id` à l'entrée de
    `generate`/`replace_at`, donc au plus un morceau correspond.
    """
    notes = sorted(
        pool,
        key=lambda track: (cost(track, target, previous, weights), track.id),
    )
    choisi = rng.choice(notes[: max(1, weights.k)])
    for index, track in enumerate(pool):
        if track.id == choisi.id:
            del pool[index]
            break
    return choisi


def _profile(request: SetRequest, config: Config):
    try:
        return config.profils[request.profile]
    except KeyError as exc:
        connus = ", ".join(sorted(config.profils))
        raise SequencingError(
            f"profil '{request.profile}' inexistant (disponibles : {connus})"
        ) from exc


def _penurie(disponibles: int, vise: int) -> list[SetWarning]:
    """Avertissement de pénurie, ou rien du tout si le compte y est."""
    if disponibles >= vise:
        return []
    return [
        SetWarning(
            code=WarningCode.SHORTAGE,
            message=f"{vise} morceaux demandés, {disponibles} éligibles",
        )
    ]


def shortage_warnings(tracks: Iterable[Track], request: SetRequest) -> list[SetWarning]:
    """Avertissement de pénurie que `generate` produirait pour cette demande.

    La pénurie est une propriété de la demande et de la collection, pas du set
    affiché : elle survit donc à tout remplacement
    (`_sans_avertissements_de_remplacement`). Cette aide est publique pour que
    la couche web, qui reconstruit le set courant à chaque remplacement, la
    recalcule ici même plutôt que de la perdre ou de la faire reporter par le
    navigateur.
    """
    return _penurie(len(_dedoublonne_par_id(eligible(tracks, request))), request.track_count)


def generate(tracks: Iterable[Track], request: SetRequest, config: Config) -> GeneratedSet:
    """Construit le set demandé, ou le plus long possible si les morceaux manquent."""
    profile = _profile(request, config)
    pool = _dedoublonne_par_id(eligible(tracks, request))

    vise = request.track_count
    count = min(vise, len(pool))

    avertissements = _penurie(len(pool), vise)

    targets = build_targets(request, profile, count)
    rng = random.Random(request.seed)

    retenus: list[Track] = []
    precedent: Track | None = None
    for target in targets:
        precedent = _pick(pool, target, precedent, config.poids, rng)
        retenus.append(precedent)

    return GeneratedSet(tracks=retenus, targets=targets, warnings=avertissements)


_PREFIXE_AVERTISSEMENT_REMPLACEMENT = "aucun remplaçant disponible à la position"


def _sans_avertissements_de_remplacement(warnings: list[SetWarning]) -> list[SetWarning]:
    """Écarte les avertissements de pénurie produits par un `replace_at` antérieur.

    Ils sont propres à cette tentative-là : soit elle vient d'être remplacée par
    un remplacement réussi (le manque n'existe plus), soit un nouvel
    avertissement à jour est ajouté juste après pour celle en cours. Sans ce
    filtre, des tentatives infructueuses répétées s'accumuleraient à l'identique,
    et un remplacement réussi recopierait des avertissements déjà périmés.

    La distinction avec une pénurie de `generate` (qui doit, elle, survivre à
    tout remplacement) repose sur `WarningCode.REPLACEMENT_SHORTAGE`, un code
    dédié — et non sur le texte du message. Les deux codes partageaient
    auparavant `WarningCode.SHORTAGE`, et seule la non-collision, non garantie,
    des deux formats de message rendait le filtrage fiable.
    """
    return [w for w in warnings if w.code != WarningCode.REPLACEMENT_SHORTAGE]


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
    pool = [
        track
        for track in _dedoublonne_par_id(eligible(tracks, request))
        if track.id not in deja_places
    ]

    target = generated.targets[position]
    precedent = generated.tracks[position - 1] if position > 0 else None
    base_warnings = _sans_avertissements_de_remplacement(generated.warnings)

    if not pool:
        return GeneratedSet(
            tracks=list(generated.tracks),
            targets=list(generated.targets),
            warnings=[
                *base_warnings,
                SetWarning(
                    code=WarningCode.REPLACEMENT_SHORTAGE,
                    message=f"{_PREFIXE_AVERTISSEMENT_REMPLACEMENT} {position + 1}",
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
        warnings=base_warnings,
    )
