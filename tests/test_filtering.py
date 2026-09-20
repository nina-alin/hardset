"""Tests de l'éligibilité d'un morceau à une demande de set."""

from hardset.engine.filtering import eligible
from hardset.model import SetRequest, Track


def piste(**kwargs) -> Track:
    base = dict(
        id="1",
        artist="A",
        title="T",
        bpm=180.0,
        camelot="8A",
        duration_s=200,
        location="file://x",
        genres=("Hardcore",),
        mood=4,
    )
    base.update(kwargs)
    return Track(**base)


def requete(**kwargs) -> SetRequest:
    base = dict(
        genres=frozenset(),
        moods=frozenset(),
        bpm_min=170.0,
        bpm_max=190.0,
        profile="montee",
        duration_min=20,
    )
    base.update(kwargs)
    return SetRequest(**base)


# --- Mood ----------------------------------------------------------------

def test_mood_absent_exclu():
    assert eligible([piste(mood=None)], requete()) == []


def test_mood_hors_demande_exclu():
    assert eligible([piste(mood=1)], requete(moods=frozenset({4, 5}))) == []


def test_mood_demande_retenu():
    assert len(eligible([piste(mood=4)], requete(moods=frozenset({4, 5})))) == 1


# --- Genre ---------------------------------------------------------------

def test_sans_genre_demande_un_morceau_sans_genre_reste_eligible():
    assert len(eligible([piste(genres=())], requete())) == 1


def test_genre_demande_exclut_un_morceau_sans_genre():
    assert eligible([piste(genres=())], requete(genres=frozenset({"Hardcore"}))) == []


def test_un_seul_genre_commun_suffit():
    track = piste(genres=("Uptempo", "Frenchcore"))
    assert len(eligible([track], requete(genres=frozenset({"Hardcore", "Frenchcore"})))) == 1


def test_comparaison_de_genre_insensible_casse_accents():
    track = piste(genres=("Vénère Core",))
    assert len(eligible([track], requete(genres=frozenset({"venere core"})))) == 1


# --- BPM -----------------------------------------------------------------

def test_bornes_bpm_inclusives():
    assert len(eligible([piste(bpm=170.0), piste(bpm=190.0)], requete())) == 2


def test_hors_plage_bpm_exclu():
    assert eligible([piste(bpm=169.9), piste(bpm=190.1)], requete()) == []


# --- Combinaison ---------------------------------------------------------

def test_ordre_preserve():
    tracks = [piste(id="1"), piste(id="2"), piste(id="3")]
    assert [t.id for t in eligible(tracks, requete())] == ["1", "2", "3"]
