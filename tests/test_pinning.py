"""Tests de l'épinglage : résolution des morceaux choisis et accord des BPM.

Le module étant pur, tous les cas se jouent sur une collection fabriquée en mémoire.
"""

import pytest

from hardset.engine.pinning import Pins, PinningError, resolve
from hardset.model import SetRequest, Track


def piste(id_: str, bpm: float, mood: int = 3) -> Track:
    return Track(
        id=id_,
        artist=f"Artiste {id_}",
        title=f"Titre {id_}",
        bpm=bpm,
        camelot="8A",
        duration_s=200,
        location=f"file://localhost/{id_}.mp3",
        genres=("Hardcore",),
        moods=(mood,),
    )


COLLECTION = [piste("a", 160.0), piste("b", 182.0), piste("c", 195.0)]


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


# --- Cas sans épinglage ---------------------------------------------------

def test_sans_epinglage_la_demande_est_rendue_intacte():
    demandee = requete()
    accordee, pins = resolve(COLLECTION, demandee)
    assert accordee == demandee
    assert pins == Pins()
    assert pins.epingles == ()


def test_sans_epinglage_la_collection_n_est_pas_parcourue():
    # Un itérateur qui lèverait s'il était lu : sans id à résoudre, `resolve`
    # n'a aucune raison de toucher à la collection.
    def explose():
        raise AssertionError("la collection ne devait pas être parcourue")
        yield   # pragma: no cover

    accordee, pins = resolve(explose(), requete())
    assert pins == Pins()
    assert accordee.bpm_min == 150.0


# --- Accord des bornes ----------------------------------------------------

def test_le_son_de_depart_impose_le_bpm_min():
    accordee, pins = resolve(COLLECTION, requete(start_track_id="b"))
    assert accordee.bpm_min == 182.0
    assert accordee.bpm_max == 200.0   # la borne sans morceau choisi ne bouge pas
    assert pins.start is not None and pins.start.id == "b"
    assert pins.end is None


def test_le_son_de_fin_impose_le_bpm_max():
    accordee, pins = resolve(COLLECTION, requete(end_track_id="b"))
    assert accordee.bpm_max == 182.0
    assert accordee.bpm_min == 150.0
    assert pins.end is not None and pins.end.id == "b"
    assert pins.start is None


def test_les_deux_bornes_sont_accordees_ensemble():
    accordee, pins = resolve(COLLECTION, requete(start_track_id="a", end_track_id="c"))
    assert (accordee.bpm_min, accordee.bpm_max) == (160.0, 195.0)
    assert pins.epingles == (pins.start, pins.end)


def test_le_reste_de_la_demande_est_intact():
    accordee, _ = resolve(COLLECTION, requete(start_track_id="a", duration_min=42))
    assert accordee.duration_min == 42
    assert accordee.profile == "montee"
    assert accordee.start_track_id == "a"


def test_resolve_est_idempotente():
    demandee = requete(start_track_id="a", end_track_id="c")
    accordee, pins = resolve(COLLECTION, demandee)
    rejouee, memes = resolve(COLLECTION, accordee)
    assert rejouee == accordee
    assert memes == pins


# --- Refus ----------------------------------------------------------------

def test_un_id_absent_de_la_collection_est_refuse():
    with pytest.raises(PinningError, match="absent de la collection"):
        resolve(COLLECTION, requete(start_track_id="inconnu"))


def test_le_meme_morceau_des_deux_cotes_est_refuse():
    with pytest.raises(PinningError, match="à la fois le son de départ et le son de fin"):
        resolve(COLLECTION, requete(start_track_id="b", end_track_id="b"))


def test_un_son_de_fin_plus_lent_que_le_depart_est_refuse():
    with pytest.raises(PinningError) as erreur:
        resolve(COLLECTION, requete(start_track_id="c", end_track_id="a"))
    # Le message nomme les deux tempos : c'est ce qui dit quoi corriger.
    assert "195" in str(erreur.value)
    assert "160" in str(erreur.value)


def test_un_son_de_depart_au_dela_du_bpm_max_demande_est_refuse():
    with pytest.raises(PinningError, match="dépasse le BPM max"):
        resolve(COLLECTION, requete(start_track_id="c", bpm_max=170.0))


def test_un_son_de_fin_en_deca_du_bpm_min_demande_est_refuse():
    with pytest.raises(PinningError, match="BPM min"):
        resolve(COLLECTION, requete(end_track_id="a", bpm_min=170.0))


def test_une_plage_reduite_a_un_seul_bpm_est_acceptee():
    # Départ et fin de même tempo : la plage est d'épaisseur nulle mais non vide.
    collection = [*COLLECTION, piste("b-bis", 182.0)]
    accordee, _ = resolve(collection, requete(start_track_id="b", end_track_id="b-bis"))
    assert accordee.bpm_min == accordee.bpm_max == 182.0
