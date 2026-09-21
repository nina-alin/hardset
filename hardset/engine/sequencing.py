"""Séquençage du set : remplissage position par position.

Pour chaque position, tous les morceaux encore disponibles sont notés, et le retenu
est tiré uniformément parmi les `k` de coût le plus faible. C'est la seule source
d'aléa : la courbe est toujours respectée, mais deux générations diffèrent.

L'algorithme est glouton et ne revient jamais en arrière. Sur quelques centaines de
titres l'effet est inaudible, et la tracklist reste éditable.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence

from hardset.config import Config, Weights
from hardset.engine.curves import build_targets
from hardset.engine.filtering import eligible
from hardset.engine.harmony import key_penalty
from hardset.engine.pinning import Pins, resolve
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


def _vivier(
    tracks: Iterable[Track], request: SetRequest
) -> tuple[SetRequest, Pins, list[Track]]:
    """Demande accordée aux épinglés, épinglés résolus, et vivier privé d'eux.

    `tracks` est matérialisé d'abord : il peut être un itérateur, et il est
    désormais lu deux fois — une pour résoudre les épinglés, une pour filtrer.

    Les épinglés sont retirés du vivier qu'ils en fassent partie ou non. Un
    morceau épinglé qui est aussi éligible serait sinon placé deux fois : une
    fois d'autorité, une fois par tirage.
    """
    materiel = list(tracks)
    accordee, pins = resolve(materiel, request)
    exclus = {track.id for track in pins.epingles}
    vivier = [
        track
        for track in _dedoublonne_par_id(eligible(materiel, accordee))
        if track.id not in exclus
    ]
    return accordee, pins, vivier


def _placement(pins: Pins, count: int) -> dict[int, Track]:
    """Positions imposées par l'épinglage, pour un set de `count` positions.

    Quand le set n'a qu'une position et que deux morceaux sont choisis, le
    départ l'emporte : arbitraire, mais fixé et documenté, et préférable à un
    échec pour un cas qui n'arrive que par accident — une durée demandée plus
    courte que le temps de jeu d'un seul morceau.
    """
    impose: dict[int, Track] = {}
    if count <= 0:
        return impose
    if pins.start is not None:
        impose[0] = pins.start
    if pins.end is not None and (count - 1) not in impose:
        impose[count - 1] = pins.end
    return impose


def _avertissements_epinglage(
    pins: Pins, impose: dict[int, Track], request: SetRequest
) -> list[SetWarning]:
    """Avertissements propres à l'épinglage, sur une demande déjà accordée.

    Un morceau épinglé n'a traversé aucun filtre : c'est l'intention (un choix
    explicite passe avant un critère coché), et c'est précisément pour ça qu'il
    faut le dire.
    """
    avertissements: list[SetWarning] = []
    places = {track.id for track in impose.values()}

    for role, track in (("première", pins.start), ("dernière", pins.end)):
        if track is None or track.id not in places:
            continue
        # La borne de BPM a été accordée à ce morceau : seuls le mood et le
        # genre peuvent encore le faire échouer ici.
        if not eligible([track], request):
            avertissements.append(
                SetWarning(
                    code=WarningCode.PIN_OFF_FILTERS,
                    message=(
                        f"« {track.label} » est placé en {role} position bien qu'il "
                        "ne corresponde pas aux critères demandés"
                    ),
                    track_ids=(track.id,),
                )
            )

    # Seul le son de fin peut rester sur le carreau : `_placement` donne la
    # position unique au départ quand les deux sont choisis.
    if pins.end is not None and pins.end.id not in places:
        avertissements.append(
            SetWarning(
                code=WarningCode.PIN_DROPPED,
                message="le son de fin n'a pas pu être placé : le set ne compte qu'une position",
                track_ids=(pins.end.id,),
            )
        )
    return avertissements


def _placement_affiche(pins: Pins, current: Sequence[Track]) -> dict[int, Track]:
    """Comme `_placement`, mais pour les positions réellement occupées dans un
    set déjà affiché, plutôt que celles qu'une génération fraîche imposerait.

    Le set affiché est éditable à la main : l'utilisatrice a pu supprimer ou
    remplacer la ligne épinglée (revue finale, point A). La vérification se
    fait donc par identité du morceau réellement présent à chaque extrémité de
    `current`, et non par simple appartenance de son id à `pins` — un morceau
    épinglé qui n'y est plus ne doit produire aucune affirmation sur une
    position qu'il n'occupe plus.
    """
    impose: dict[int, Track] = {}
    if not current:
        return impose
    if pins.start is not None and current[0].id == pins.start.id:
        impose[0] = pins.start
    derniere = len(current) - 1
    if pins.end is not None and derniere not in impose and current[derniere].id == pins.end.id:
        impose[derniere] = pins.end
    return impose


def request_warnings(
    tracks: Iterable[Track], request: SetRequest, current: Sequence[Track] | None = None
) -> list[SetWarning]:
    """Avertissements de la demande — pénurie et épinglage — que `generate`
    produirait pour cette demande.

    Aide publique unique, pour que la couche web, qui reconstruit le set
    courant à chaque remplacement, les recalcule ici même plutôt que de les
    perdre ou de les faire reporter par le navigateur (revue finale, point A).
    `generate` s'appuie sur exactement le même calcul : avoir deux chemins qui
    le refont chacun de son côté est la cause du défaut corrigé ici, et les
    laisser distincts les ferait rediverger.

    `current`, quand fourni, est le set réellement affiché — potentiellement
    édité à la main, ligne épinglée supprimée ou remplacée comprise : les
    avertissements d'épinglage ne portent alors que sur les morceaux qui
    occupent réellement la première et la dernière position de CE set (voir
    `_placement_affiche`). Sans lui (le cas de `generate`, qui n'a encore
    produit aucun set affiché), les positions qu'une génération fraîche
    imposerait sont utilisées à la place.
    """
    accordee, pins, vivier = _vivier(tracks, request)
    disponibles = len(vivier) + len(pins.epingles)
    if current is None:
        impose = _placement(pins, min(request.track_count, disponibles))
    else:
        impose = _placement_affiche(pins, current)
    return [
        *_penurie(disponibles, request.track_count),
        *_avertissements_epinglage(pins, impose, accordee),
    ]


def shortage_warnings(tracks: Iterable[Track], request: SetRequest) -> list[SetWarning]:
    """Avertissement de pénurie que `generate` produirait pour cette demande.

    La pénurie est une propriété de la demande et de la collection, pas du set
    affiché : elle survit donc à tout remplacement
    (`_sans_avertissements_de_remplacement`). Cette aide est publique pour que
    la couche web, qui reconstruit le set courant à chaque remplacement, la
    recalcule ici même plutôt que de la perdre ou de la faire reporter par le
    navigateur.

    Les morceaux épinglés comptent dans le décompte bien qu'ils ne viennent pas
    du vivier : ils occupent une position du set. Sans ça, cette aide et
    `generate` divergeraient d'au plus deux morceaux, et l'avertissement
    reparaîtrait ou disparaîtrait au premier remplacement.
    """
    _, pins, vivier = _vivier(tracks, request)
    return _penurie(len(vivier) + len(pins.epingles), request.track_count)


def generate(tracks: Iterable[Track], request: SetRequest, config: Config) -> GeneratedSet:
    """Construit le set demandé, ou le plus long possible si les morceaux manquent.

    Les morceaux épinglés (`SetRequest.start_track_id` / `end_track_id`) ouvrent
    et ferment le set. Ils sont **placés, pas choisis** : `cost` ne les note
    jamais, et leur position peut donc s'écarter de la cible — c'est une
    contrainte imposée, pas un échec de sélection, et la courbe le montre.
    """
    profile = _profile(request, config)   # valide le profil avant toute autre chose
    materiel = list(tracks)
    # `request` est rebindée sur la demande accordée aux épinglés : tout ce qui
    # suit (cibles, filtrage, avertissements) doit voir les bornes dérivées.
    request, pins, pool = _vivier(materiel, request)

    vise = request.track_count
    disponibles = len(pool) + len(pins.epingles)
    count = min(vise, disponibles)

    targets = build_targets(request, profile, count, config.mood_max)
    impose = _placement(pins, count)
    # `request_warnings` est la même aide que `/api/replace` recalcule après un
    # remplacement (revue finale, point A) : un seul calcul pour les deux
    # chemins, pour qu'ils ne puissent plus diverger.
    avertissements = request_warnings(materiel, request)

    rng = random.Random(request.seed)
    retenus: list[Track] = []
    precedent: Track | None = None
    for target in targets:
        epingle = impose.get(target.position)
        precedent = epingle if epingle is not None else _pick(
            pool, target, precedent, config.poids, rng
        )
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

    Les positions épinglées ne sont pas protégées : l'épinglage est une
    contrainte de génération, pas un verrou d'édition, et la tracklist reste
    modifiable à la main comme le reste.
    """
    _profile(request, config)   # valide le profil avant toute autre chose
    if not 0 <= position < len(generated.tracks):
        raise SequencingError(
            f"position {position} hors du set (0 à {len(generated.tracks) - 1})"
        )

    deja_places = {track.id for track in generated.tracks}
    # La demande est accordée ici aussi : le vivier de remplacement doit tenir
    # dans la plage imposée par les sons épinglés, comme celui de `generate`.
    request, _, vivier = _vivier(tracks, request)
    pool = [track for track in vivier if track.id not in deja_places]

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
