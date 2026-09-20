"""Tests de la recherche de morceaux, qui sert à choisir les sons épinglés."""

from hardset.engine.search import search
from hardset.model import Track


def piste(id_: str, artist: str, title: str, moods=(3,)) -> Track:
    return Track(
        id=id_,
        artist=artist,
        title=title,
        bpm=180.0,
        camelot="8A",
        duration_s=200,
        location=f"file://localhost/{id_}.mp3",
        genres=("Hardcore",),
        moods=moods,
    )


COLLECTION = [
    piste("1", "Angerfist", "Raise Your Fist"),
    piste("2", "Angerfist", "Pennywise"),
    piste("3", "Nosferatu", "Raise The Dead"),
    piste("4", "Sefa", "Vérité"),
    piste("5", "DJ Paul Elstak", "Rainbow In The Sky", moods=()),
]


def ids(resultat) -> list[str]:
    trouves, _ = resultat
    return [track.id for track in trouves]


def test_cherche_dans_le_titre():
    assert ids(search(COLLECTION, "pennywise", 20)) == ["2"]


def test_cherche_dans_l_artiste():
    assert ids(search(COLLECTION, "angerfist", 20)) == ["1", "2"]


def test_tous_les_mots_doivent_figurer_dans_n_importe_quel_ordre():
    # « fist » vient de l'artiste et du titre, « raise » du titre seul.
    assert ids(search(COLLECTION, "raise angerfist", 20)) == ["1"]
    assert ids(search(COLLECTION, "angerfist raise", 20)) == ["1"]


def test_la_casse_et_les_accents_sont_ignores():
    assert ids(search(COLLECTION, "VERITE", 20)) == ["4"]
    assert ids(search(COLLECTION, "vérité", 20)) == ["4"]


def test_une_recherche_vide_ne_rend_rien():
    # La page invite à taper plutôt que de dérouler la collection entière.
    assert search(COLLECTION, "", 20) == ([], False)
    assert search(COLLECTION, "   ", 20) == ([], False)


def test_aucun_resultat():
    assert search(COLLECTION, "zzzz", 20) == ([], False)


def test_l_ordre_de_la_collection_est_conserve():
    assert ids(search(COLLECTION, "raise", 20)) == ["1", "3"]


def test_le_plafond_tronque_et_le_signale():
    trouves, tronque = search(COLLECTION, "a", 2)
    assert len(trouves) == 2
    assert tronque is True


def test_sans_troncature_le_drapeau_est_faux():
    trouves, tronque = search(COLLECTION, "angerfist", 2)
    assert len(trouves) == 2
    assert tronque is False


def test_un_plafond_nul_ne_rend_rien():
    assert search(COLLECTION, "angerfist", 0) == ([], False)


def test_un_morceau_sans_mood_reste_trouvable():
    # La recherche ne connaît aucun critère de set : c'est ce qui rend
    # épinglable un morceau que `eligible` écarterait.
    assert ids(search(COLLECTION, "rainbow", 20)) == ["5"]
