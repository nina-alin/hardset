"""Tests du séquençage : respect de la courbe, pénurie, aléa, remplacement.

Le moteur étant pur, tous les cas se jouent sur des collections fabriquées en mémoire.
"""

import pytest

from hardset.config import load_config
from hardset.engine.sequencing import SequencingError, cost, generate, replace_at
from hardset.model import SetRequest, Target, Track, WarningCode

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
        mood=mood,
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

def test_cout_nul_sur_la_cible_exacte():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    assert cost(piste("x", 180.0, 4), cible, None, CONFIG.poids) == pytest.approx(0.0)


def test_ecart_bpm_divise_par_la_tolerance():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    # 5 BPM d'écart = 1 unité, pondérée par w_bpm = 1.0
    assert cost(piste("x", 185.0, 4), cible, None, CONFIG.poids) == pytest.approx(1.0)


def test_ecart_de_mood_pondere():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    # 1 cran de mood × w_mood = 1.5
    assert cost(piste("x", 180.0, 3), cible, None, CONFIG.poids) == pytest.approx(1.5)


def test_premiere_position_sans_penalite_harmonique():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    # previous=None à la première position : pénalité 0, et non 0,5 (clé inconnue).
    assert cost(piste("x", 180.0, 4, camelot=None), cible, None, CONFIG.poids) == pytest.approx(0.0)


def test_penalite_harmonique_appliquee_ensuite():
    cible = Target(position=1, bpm=180.0, mood=4.0)
    precedent = piste("p", 180.0, 4, camelot="8A")
    candidat = piste("c", 180.0, 4, camelot="2A")   # lointain : pénalité 2
    assert cost(candidat, cible, precedent, CONFIG.poids) == pytest.approx(0.8)  # 2 × 0.4


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


def test_deux_generations_different():
    a = generate(collection_dense(), requete(seed=None), CONFIG)
    b = generate(collection_dense(), requete(seed=None), CONFIG)
    assert [t.id for t in a.tracks] != [t.id for t in b.tracks]


def test_graine_fixee_reproductible():
    a = generate(collection_dense(), requete(seed=42), CONFIG)
    b = generate(collection_dense(), requete(seed=42), CONFIG)
    assert [t.id for t in a.tracks] == [t.id for t in b.tracks]


# --- Remplacement d'une position -----------------------------------------

def test_remplacement_change_le_morceau():
    pool = collection_dense()
    resultat = generate(pool, requete(), CONFIG)
    avant = resultat.tracks[5].id

    remplace = replace_at(resultat, 5, pool, requete(seed=7), CONFIG)

    assert remplace.tracks[5].id != avant
    assert len(remplace.tracks) == len(resultat.tracks)
    # Les autres positions ne bougent pas.
    assert [t.id for t in remplace.tracks[:5]] == [t.id for t in resultat.tracks[:5]]
    assert [t.id for t in remplace.tracks[6:]] == [t.id for t in resultat.tracks[6:]]


def test_remplacement_sans_doublon():
    pool = collection_dense()
    resultat = generate(pool, requete(), CONFIG)
    remplace = replace_at(resultat, 0, pool, requete(seed=7), CONFIG)
    ids = [t.id for t in remplace.tracks]
    assert len(ids) == len(set(ids))


def test_remplacement_sans_candidat_laisse_le_set_intact():
    pool = [piste(str(i), 150.0 + i, (i % 5) + 1) for i in range(5)]
    resultat = generate(pool, requete(duration_min=10), CONFIG)   # 5 morceaux pour 5 places
    avant = [t.id for t in resultat.tracks]

    remplace = replace_at(resultat, 2, pool, requete(duration_min=10), CONFIG)

    assert [t.id for t in remplace.tracks] == avant
    assert any(w.code == WarningCode.SHORTAGE for w in remplace.warnings)


def test_position_hors_set_refusee():
    pool = collection_dense()
    resultat = generate(pool, requete(), CONFIG)
    with pytest.raises(SequencingError, match="position"):
        replace_at(resultat, 99, pool, requete(), CONFIG)


# --- Profil ---------------------------------------------------------------

def test_profil_inconnu_refuse():
    with pytest.raises(SequencingError, match="inexistant"):
        generate(collection_dense(), requete(profile="inexistant"), CONFIG)


# --- Déterminisme et absence d'état global --------------------------------

def test_generation_reproductible_bout_en_bout():
    """À graine et requête identiques, deux générations produisent le même set,
    y compris ses cibles et l'absence d'avertissement — pas seulement les ids.

    Garantit aussi l'absence d'état global partagé : la mutation de l'état
    aléatoire d'une génération à l'autre (via le module `random` directement,
    plutôt qu'une instance locale `random.Random`) romprait cette égalité dès
    la seconde exécution du processus de test.
    """
    a = generate(collection_dense(), requete(seed=123), CONFIG)
    b = generate(collection_dense(), requete(seed=123), CONFIG)
    assert [t.id for t in a.tracks] == [t.id for t in b.tracks]
    assert a.targets == b.targets
    assert a.warnings == b.warnings
