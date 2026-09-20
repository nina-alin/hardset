"""Tests du séquençage : respect de la courbe, pénurie, aléa, remplacement.

Le moteur étant pur, tous les cas se jouent sur des collections fabriquées en mémoire.
"""

import random
from dataclasses import replace

import pytest

from hardset.config import Weights, load_config
from hardset.engine.pinning import PinningError
from hardset.engine.sequencing import (
    SequencingError,
    cost,
    generate,
    replace_at,
    shortage_warnings,
)
from hardset.model import GeneratedSet, SetRequest, SetWarning, Target, Track, WarningCode

# Chargé une seule fois pour les profils de courbe (`generate`) : les tests de
# coût, eux, construisent leur propre `Weights()` pour ne pas dépendre de
# hardset.yaml (cf. tâche 8, trouvaille 6).
CONFIG = load_config()


def piste(id_: str, bpm: float, mood: int, camelot: str | None = "8A", genres=("Hardcore",)) -> Track:
    return Track(
        id=id_,
        artist=f"Artiste {id_}",
        title=f"Titre {id_}",
        bpm=bpm,
        camelot=camelot,
        duration_s=200,
        location=f"file://localhost/{id_}.mp3",
        genres=genres,
        moods=() if mood is None else (mood,),
    )


def collection_dense(camelot: str | None = "8A") -> list[Track]:
    """Un morceau par BPM entier de 150 à 200 et par mood de 1 à 5 : 255 morceaux."""
    return [
        piste(f"{bpm}-{mood}", float(bpm), mood, camelot)
        for bpm in range(150, 201)
        for mood in range(1, 6)
    ]


def requete(**kwargs) -> SetRequest:
    base = dict(
        genres=frozenset(),
        moods=frozenset(),
        bpm_min=150.0,
        bpm_max=200.0,
        profile="montee",
        duration_min=60,
        seed=1,
    )
    base.update(kwargs)
    return SetRequest(**base)


# --- Calcul du coût ------------------------------------------------------
#
# `Weights()` est construit directement ici : ces tests portent sur la formule
# de `cost`, pas sur le réglage musical du dépôt, et ne doivent pas dépendre
# de hardset.yaml (cf. tâche 8, trouvaille 6).

POIDS = Weights()


def test_cout_nul_sur_la_cible_exacte():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    assert cost(piste("x", 180.0, 4), cible, None, POIDS) == pytest.approx(0.0)


def test_ecart_bpm_divise_par_la_tolerance():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    # 5 BPM d'écart = 1 unité, pondérée par w_bpm = 1.0
    assert cost(piste("x", 185.0, 4), cible, None, POIDS) == pytest.approx(1.0)


def test_poids_bpm_pondere_lecart_de_bpm():
    # Épingle weights.bpm dans la formule, comme mood et tonalite le sont déjà :
    # sans `weights.bpm *`, ce test resterait vert avec le poids par défaut (1.0)
    # mais échoue ici puisque w_bpm = 2.0 double le terme.
    poids = Weights(bpm=2.0, mood=1.5, tonalite=0.4, bpm_tolerance=5.0, k=5)
    cible = Target(position=0, bpm=180.0, mood=4.0)
    # 5 BPM d'écart = 1 unité, pondérée par w_bpm = 2.0
    assert cost(piste("x", 185.0, 4), cible, None, poids) == pytest.approx(2.0)


def test_ecart_de_mood_pondere():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    # 1 cran de mood × w_mood = 1.5
    assert cost(piste("x", 180.0, 3), cible, None, POIDS) == pytest.approx(1.5)


def test_premiere_position_sans_penalite_harmonique():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    # previous=None à la première position : pénalité 0, et non 0,5 (clé inconnue).
    assert cost(piste("x", 180.0, 4, camelot=None), cible, None, POIDS) == pytest.approx(0.0)


def test_penalite_harmonique_appliquee_ensuite():
    cible = Target(position=1, bpm=180.0, mood=4.0)
    precedent = piste("p", 180.0, 4, camelot="8A")
    candidat = piste("c", 180.0, 4, camelot="2A")   # lointain : pénalité 2
    assert cost(candidat, cible, precedent, POIDS) == pytest.approx(0.8)  # 2 × 0.4


def test_cout_exige_un_mood_sans_repli_sur_la_cible():
    # `eligible` écarte les morceaux sans mood ; `cost` ne doit pas s'en
    # accommoder par un repli sur `target.mood`, qui annulerait le terme et
    # ferait d'un candidat sans mood le meilleur score possible.
    cible = Target(position=0, bpm=180.0, mood=4.0)
    candidat = Track(
        id="x", artist="A", title="T", bpm=180.0, camelot=None,
        duration_s=200, location="file://localhost/x.mp3", genres=(), moods=(),
    )
    with pytest.raises(TypeError):
        cost(candidat, cible, None, POIDS)


# --- Respect de la courbe ------------------------------------------------

def test_montee_suit_la_cible_bpm():
    resultat = generate(collection_dense(), requete(duration_min=60), CONFIG)
    assert len(resultat.tracks) == 30
    ecarts = [
        abs(track.bpm - cible.bpm)
        for track, cible in zip(resultat.tracks, resultat.targets)
    ]
    assert max(ecarts) <= CONFIG.poids.bpm_tolerance


def test_le_mood_progresse():
    resultat = generate(collection_dense(), requete(duration_min=60), CONFIG)
    moods = [t.mood for t in resultat.tracks]
    tiers = len(moods) // 3
    premier = sum(moods[:tiers]) / tiers
    dernier = sum(moods[-tiers:]) / tiers
    assert premier < dernier


def test_profil_vagues_genere_sans_erreur():
    resultat = generate(collection_dense(), requete(profile="vagues"), CONFIG)
    assert len(resultat.tracks) == 30


# --- Pénurie -------------------------------------------------------------

def test_penurie_produit_le_set_le_plus_long_possible():
    pool = [piste(str(i), 150.0 + i, (i % 5) + 1) for i in range(28)]
    resultat = generate(pool, requete(duration_min=90), CONFIG)   # 45 demandés

    assert len(resultat.tracks) == 28
    assert len(resultat.targets) == 28
    avertissement = next(w for w in resultat.warnings if w.code == WarningCode.SHORTAGE)
    assert "45" in avertissement.message and "28" in avertissement.message


def test_aucun_avertissement_de_penurie_si_assez_de_morceaux():
    resultat = generate(collection_dense(), requete(duration_min=60), CONFIG)
    assert not [w for w in resultat.warnings if w.code == WarningCode.SHORTAGE]


def test_collection_vide_donne_un_set_vide():
    resultat = generate([], requete(), CONFIG)
    assert resultat.tracks == []
    assert any(w.code == WarningCode.SHORTAGE for w in resultat.warnings)


# --- Tonalité ------------------------------------------------------------

def test_collection_sans_tonalite_genere_quand_meme():
    resultat = generate(collection_dense(camelot=None), requete(), CONFIG)
    assert len(resultat.tracks) == 30
    assert all(t.camelot is None for t in resultat.tracks)


# --- Doublons et aléa ----------------------------------------------------

def test_aucun_doublon():
    resultat = generate(collection_dense(), requete(), CONFIG)
    ids = [t.id for t in resultat.tracks]
    assert len(ids) == len(set(ids))


def test_id_duplique_en_entree_nest_place_quune_fois():
    """`Track` est comparé par valeur : un `id` répété dans l'itérable d'entrée
    (une requête HTTP mal dédupliquée, cf. tâche 10 — rien ne garantit
    aujourd'hui l'unicité comme le fait Rekordbox) ne doit pas permettre au
    même morceau d'être tiré deux fois.
    """
    a = piste("A", 180.0, 3)
    b = piste("B", 181.0, 3)
    c = piste("C", 182.0, 3)
    pool = [a, a, b, c]   # "A" apparaît deux fois

    for graine in range(20):
        resultat = generate(pool, requete(seed=graine), CONFIG)
        ids = [t.id for t in resultat.tracks]
        assert ids.count("A") <= 1, f"graine {graine} : {ids}"


def test_deux_generations_different():
    a = generate(collection_dense(), requete(seed=None), CONFIG)
    b = generate(collection_dense(), requete(seed=None), CONFIG)
    assert [t.id for t in a.tracks] != [t.id for t in b.tracks]


def test_graine_fixee_reproductible():
    a = generate(collection_dense(), requete(seed=42), CONFIG)
    b = generate(collection_dense(), requete(seed=42), CONFIG)
    assert [t.id for t in a.tracks] == [t.id for t in b.tracks]


# --- Remplacement d'une position -----------------------------------------

def _set_minimal_pour_remplacement():
    """Sept morceaux strictement à égalité de coût (bpm et mood collés à la
    cible), dont cinq déjà placés : sans l'exclusion des morceaux en place,
    ils seraient les meilleurs candidats possibles pour n'importe quelle
    position, et un remplacement les retirerait forcément du pool restant
    (ids "6" et "7") pour reprendre l'un des cinq déjà utilisés ailleurs.

    Contrairement à un pool dense de 255 morceaux, où les concurrents des
    autres positions n'entrent presque jamais dans les `k` meilleurs de la
    cible visée, ce pool minimal force la réutilisation si l'exclusion venait
    à disparaître : le test échoue alors réellement.
    """
    pool = [piste(str(i), 180.0, 3) for i in range(1, 8)]   # ids "1" à "7"
    targets = [Target(position=i, bpm=180.0, mood=3.0) for i in range(5)]
    generated = GeneratedSet(tracks=list(pool[:5]), targets=targets, warnings=[])
    return pool, generated


def test_remplacement_change_le_morceau():
    pool, resultat = _set_minimal_pour_remplacement()

    remplace = replace_at(resultat, 2, pool, requete(), CONFIG)

    assert remplace.tracks[2].id != "3"
    assert len(remplace.tracks) == len(resultat.tracks)
    # Les autres positions ne bougent pas.
    assert [t.id for t in remplace.tracks[:2]] == [t.id for t in resultat.tracks[:2]]
    assert [t.id for t in remplace.tracks[3:]] == [t.id for t in resultat.tracks[3:]]


def test_remplacement_exclut_les_morceaux_deja_places():
    pool, resultat = _set_minimal_pour_remplacement()

    remplace = replace_at(resultat, 2, pool, requete(), CONFIG)

    deja_places_ailleurs = {resultat.tracks[i].id for i in (0, 1, 3, 4)}
    assert remplace.tracks[2].id not in deja_places_ailleurs
    assert remplace.tracks[2].id in {"6", "7"}


def test_remplacement_sans_doublon():
    pool, resultat = _set_minimal_pour_remplacement()
    remplace = replace_at(resultat, 2, pool, requete(), CONFIG)
    ids = [t.id for t in remplace.tracks]
    assert len(ids) == len(set(ids))


def test_remplacement_sans_candidat_laisse_le_set_intact():
    pool = [piste(str(i), 150.0 + i, (i % 5) + 1) for i in range(5)]
    resultat = generate(pool, requete(duration_min=10), CONFIG)   # 5 morceaux pour 5 places
    avant = [t.id for t in resultat.tracks]

    remplace = replace_at(resultat, 2, pool, requete(duration_min=10), CONFIG)

    assert [t.id for t in remplace.tracks] == avant
    assert any(w.code == WarningCode.REPLACEMENT_SHORTAGE for w in remplace.warnings)


def test_remplacements_infructueux_repetes_ne_dupliquent_pas_lavertissement():
    pool = [piste(str(i), 150.0 + i, (i % 5) + 1) for i in range(5)]
    resultat = generate(pool, requete(duration_min=10), CONFIG)   # 5 morceaux pour 5 places, sans marge

    premier = replace_at(resultat, 2, pool, requete(duration_min=10), CONFIG)
    second = replace_at(premier, 2, pool, requete(duration_min=10), CONFIG)

    penuries = [w for w in second.warnings if w.code == WarningCode.REPLACEMENT_SHORTAGE]
    assert len(penuries) == 1


def test_remplacement_reussi_nefface_pas_lavertissement_dun_remplacement_precedent():
    pool = collection_dense()
    resultat = generate(pool, requete(), CONFIG)

    # Une première tentative échoue faute de tout candidat (pool vide fourni).
    echoue = replace_at(resultat, 0, [], requete(), CONFIG)
    assert any(w.code == WarningCode.REPLACEMENT_SHORTAGE for w in echoue.warnings)

    # Une seconde tentative, ailleurs, réussit : l'avertissement de la
    # première ne doit pas être reporté, il est désormais périmé.
    reussi = replace_at(echoue, 1, pool, requete(seed=7), CONFIG)
    assert not any(w.code == WarningCode.REPLACEMENT_SHORTAGE for w in reussi.warnings)


def test_position_hors_set_refusee():
    pool = collection_dense()
    resultat = generate(pool, requete(), CONFIG)
    with pytest.raises(SequencingError, match="position"):
        replace_at(resultat, 99, pool, requete(), CONFIG)


# --- Distinction par code entre pénurie de generate et de remplacement ----

def test_avertissement_de_generate_non_filtre_meme_si_son_message_ressemble_a_celui_dun_remplacement():
    """La distinction entre la pénurie de `generate` et celle de `replace_at`
    doit reposer sur `WarningCode`, pas sur le texte du message.

    Ce test fabrique un avertissement de code `SHORTAGE` (celui de `generate`)
    dont le message se trouve, par coïncidence, commencer comme le format
    qu'utilise `replace_at` pour ses propres pénuries. Un filtrage fondé sur
    le préfixe du message le ferait disparaître à tort après un remplacement
    réussi ailleurs ; un filtrage fondé sur le code doit le conserver.
    """
    pool = collection_dense()
    resultat = generate(pool, requete(), CONFIG)

    avertissement_de_generate = SetWarning(
        code=WarningCode.SHORTAGE,
        message="aucun remplaçant disponible à la position 9 (coïncidence de formulation)",
    )
    avec_avertissement = GeneratedSet(
        tracks=resultat.tracks,
        targets=resultat.targets,
        warnings=[avertissement_de_generate],
    )

    reussi = replace_at(avec_avertissement, 0, pool, requete(seed=7), CONFIG)

    assert avertissement_de_generate in reussi.warnings


def test_avertissement_de_penurie_de_generate_survit_a_des_remplacements_reussis():
    """Un avertissement de pénurie émis par `generate` (morceaux éligibles
    insuffisants pour la durée demandée) porte sur le déficit global de la
    collection, pas sur une position précise : il doit survivre à des
    `replace_at` réussis sur les positions effectivement générées.
    """
    pool_initial = [piste(str(i), 150.0 + i, (i % 5) + 1) for i in range(10)]
    resultat = generate(pool_initial, requete(duration_min=90), CONFIG)   # 45 demandés, 10 dispo
    assert len(resultat.tracks) == 10
    avertissement_initial = next(w for w in resultat.warnings if w.code == WarningCode.SHORTAGE)

    # Un pool plus large pour permettre un remplacement réussi (les morceaux
    # déjà placés sont exclus par `replace_at`).
    pool_large = pool_initial + [piste(f"x{i}", 150.0 + i, (i % 5) + 1) for i in range(20)]

    premier = replace_at(resultat, 0, pool_large, requete(duration_min=90), CONFIG)
    assert avertissement_initial in premier.warnings

    second = replace_at(premier, 1, pool_large, requete(duration_min=90, seed=2), CONFIG)
    assert avertissement_initial in second.warnings


# --- Déduplication par id, côté replace_at --------------------------------

def test_replace_at_deduplique_les_doublons_dans_son_pool():
    """`replace_at` applique `_dedoublonne_par_id` sur son argument `tracks`,
    tout comme `generate` le fait sur le sien (cf.
    `test_id_duplique_en_entree_nest_place_quune_fois`), mais ce n'était
    jusqu'ici testé que côté `generate`.

    Ici, "6" a le coût le plus bas et apparaît 5 fois, "7" a un coût
    strictement plus élevé et apparaît une seule fois. Avec `k=2` : si le
    pool est dédoublonné, les deux id sont dans la fenêtre des `k` meilleurs
    candidats et "7" reste tirable ; sans dédoublonnage, les 5 doublons de
    "6" occupent à eux seuls toute la fenêtre et "7" n'est plus jamais
    tirable, quelle que soit la graine.
    """
    pool_place = [piste(str(i), 180.0, 3) for i in range(1, 6)]   # ids "1" à "5", déjà placés
    targets = [Target(position=i, bpm=180.0, mood=3.0) for i in range(5)]
    generated = GeneratedSet(tracks=list(pool_place), targets=targets, warnings=[])

    candidats = [piste("6", 180.0, 3)] * 5 + [piste("7", 181.0, 3)]
    config_k2 = replace(CONFIG, poids=replace(CONFIG.poids, k=2))

    # Graine choisie pour que le tirage, une fois le pool dédoublonné à
    # {"6", "7"}, retienne "7" (le second des deux candidats).
    remplace = replace_at(generated, 2, pool_place + candidats, requete(seed=0), config_k2)

    assert remplace.tracks[2].id == "7"


# --- Profil ---------------------------------------------------------------

def test_profil_inconnu_refuse():
    with pytest.raises(SequencingError, match="inexistant"):
        generate(collection_dense(), requete(profile="inexistant"), CONFIG)


# --- Déterminisme et absence d'état global --------------------------------

def test_generate_ne_mute_pas_letat_global_de_random():
    """`generate` doit tirer son aléa d'une instance locale `random.Random(...)`,
    jamais du générateur global du module `random`.

    Une implémentation qui ferait `random.seed(request.seed)` puis
    `random.choice(...)` resterait reproductible à graine fixée — et passerait
    donc `test_graine_fixee_reproductible` — tout en mutant l'état global du
    processus. C'est cette mutation-là que ce test détecte, en relevant l'état
    du générateur global avant et après l'appel.
    """
    etat_avant = random.getstate()
    generate(collection_dense(), requete(seed=123), CONFIG)
    assert random.getstate() == etat_avant


# --- Avertissement de pénurie calculé seul --------------------------------

def test_shortage_warnings_signale_le_manque():
    pool = [piste(str(i), 150.0 + i, (i % 5) + 1) for i in range(5)]
    avertissements = shortage_warnings(pool, requete(duration_min=60))
    assert [w.code for w in avertissements] == [WarningCode.SHORTAGE]
    assert "30" in avertissements[0].message and "5" in avertissements[0].message


def test_shortage_warnings_muet_quand_il_y_a_assez_de_morceaux():
    assert shortage_warnings(collection_dense(), requete(duration_min=60)) == []


def test_shortage_warnings_donne_le_meme_avertissement_que_generate():
    # C'est la garantie que la couche web recalcule exactement ce que
    # `generate` aurait produit, et non une approximation.
    pool = [piste(str(i), 150.0 + i, (i % 5) + 1) for i in range(5)]
    demande = requete(duration_min=60)
    depuis_generate = [w for w in generate(pool, demande, CONFIG).warnings
                       if w.code == WarningCode.SHORTAGE]
    assert shortage_warnings(pool, demande) == depuis_generate


# --- Échelle de mood tirée de la configuration ----------------------------

def test_les_cibles_de_mood_suivent_lechelle_de_la_configuration():
    config_courte = replace(CONFIG, moods=("calme", "dansant", "vénère"))
    resultat = generate(collection_dense(), requete(duration_min=20), config_courte)
    assert max(c.mood for c in resultat.targets) <= 3.0


# --- Sons de départ et de fin épinglés ------------------------------------
#
# `piste` et `collection_dense` sont définis en tête de ce fichier. Les
# morceaux épinglés doivent appartenir à la collection : `resolve` les y
# retrouve par leur id.

def collection_avec_extremites() -> list[Track]:
    """Trois morceaux au milieu, un lent et un rapide destinés à être épinglés."""
    return [
        piste("debut", 150.0, 3),
        piste("a", 160.0, 3),
        piste("b", 165.0, 3),
        piste("c", 170.0, 3),
        piste("fin", 200.0, 3),
    ]


def test_le_son_de_depart_ouvre_le_set():
    jeu = generate(collection_dense(), requete(start_track_id="182-3"), CONFIG)
    assert jeu.tracks[0].id == "182-3"


def test_le_son_de_fin_ferme_le_set():
    jeu = generate(collection_dense(), requete(end_track_id="182-3"), CONFIG)
    assert jeu.tracks[-1].id == "182-3"


def test_le_son_de_depart_impose_la_borne_du_vivier():
    # Conséquence assumée : la borne accordée filtre tout le reste du set.
    jeu = generate(collection_dense(), requete(start_track_id="182-3"), CONFIG)
    assert min(track.bpm for track in jeu.tracks) == 182.0


def test_un_morceau_epingle_n_est_pas_place_deux_fois():
    jeu = generate(collection_dense(), requete(start_track_id="182-3"), CONFIG)
    assert [t.id for t in jeu.tracks].count("182-3") == 1


def test_les_epingles_comptent_dans_la_longueur_du_set():
    jeu = generate(
        collection_avec_extremites(),
        requete(start_track_id="debut", end_track_id="fin"),
        CONFIG,
    )
    # Trois morceaux au vivier, plus les deux épinglés.
    assert len(jeu.tracks) == 5
    assert jeu.tracks[0].id == "debut"
    assert jeu.tracks[-1].id == "fin"


def test_la_penurie_compte_les_epingles():
    jeu = generate(
        collection_avec_extremites(),
        requete(start_track_id="debut", end_track_id="fin"),
        CONFIG,
    )
    penurie = [w for w in jeu.warnings if w.code is WarningCode.SHORTAGE]
    assert len(penurie) == 1
    assert "5 éligibles" in penurie[0].message


def test_shortage_warnings_compte_comme_generate():
    collection = collection_avec_extremites()
    demande = requete(start_track_id="debut", end_track_id="fin")
    attendus = [w for w in generate(collection, demande, CONFIG).warnings
                if w.code is WarningCode.SHORTAGE]
    assert shortage_warnings(collection, demande) == attendus


def test_un_epingle_hors_des_criteres_est_place_avec_un_avertissement():
    collection = [*collection_dense(), piste("calme", 182.0, 1)]
    jeu = generate(
        collection,
        requete(start_track_id="calme", moods=frozenset({4, 5})),
        CONFIG,
    )
    assert jeu.tracks[0].id == "calme"
    hors = [w for w in jeu.warnings if w.code is WarningCode.PIN_OFF_FILTERS]
    assert len(hors) == 1
    assert hors[0].track_ids == ("calme",)
    assert "première" in hors[0].message


def test_un_epingle_sans_aucun_mood_est_place_quand_meme():
    # Sans épinglage, `eligible` l'écarterait : on ne saurait pas où le placer.
    # Épinglé, il est placé d'autorité — et signalé.
    muet = replace(piste("muet", 200.0, 3), moods=())
    jeu = generate([*collection_dense(), muet], requete(end_track_id="muet"), CONFIG)
    assert jeu.tracks[-1].id == "muet"
    assert any(w.code is WarningCode.PIN_OFF_FILTERS for w in jeu.warnings)


def test_un_epingle_dans_les_criteres_ne_produit_aucun_avertissement():
    jeu = generate(collection_dense(), requete(start_track_id="182-3"), CONFIG)
    assert not [w for w in jeu.warnings if w.code is WarningCode.PIN_OFF_FILTERS]


def test_un_set_d_une_seule_position_garde_le_son_de_depart():
    jeu = generate(
        collection_avec_extremites(),
        requete(start_track_id="debut", end_track_id="fin", duration_min=1),
        CONFIG,
    )
    assert [t.id for t in jeu.tracks] == ["debut"]
    abandon = [w for w in jeu.warnings if w.code is WarningCode.PIN_DROPPED]
    assert len(abandon) == 1
    assert abandon[0].track_ids == ("fin",)


def test_un_set_d_une_seule_position_place_le_son_de_fin_s_il_est_seul():
    jeu = generate(
        collection_avec_extremites(),
        requete(end_track_id="fin", duration_min=1),
        CONFIG,
    )
    assert [t.id for t in jeu.tracks] == ["fin"]
    assert not [w for w in jeu.warnings if w.code is WarningCode.PIN_DROPPED]


def test_un_epingle_introuvable_fait_echouer_la_generation():
    with pytest.raises(PinningError):
        generate(collection_dense(), requete(start_track_id="inconnu"), CONFIG)


def test_le_remplacement_respecte_la_plage_accordee():
    demande = requete(start_track_id="182-3")
    jeu = generate(collection_dense(), demande, CONFIG)
    apres = replace_at(jeu, 1, collection_dense(), demande, CONFIG)
    assert apres.tracks[1].id != jeu.tracks[1].id
    assert apres.tracks[1].bpm >= 182.0


def test_la_collection_peut_etre_un_iterateur():
    # `generate` lit la collection deux fois désormais (résolution puis
    # filtrage) : un itérateur ne doit pas être consommé au premier passage.
    jeu = generate(iter(collection_dense()), requete(start_track_id="182-3"), CONFIG)
    assert jeu.tracks[0].id == "182-3"
