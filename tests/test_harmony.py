"""Tests de la normalisation des tonalités et de la pénalité de transition.

Les valeurs de référence : Camelot 8B = Do majeur, 8A = La mineur ;
Open Key 1d = Do majeur, 1m = La mineur.
"""

import pytest

from hardset.engine.harmony import key_penalty, to_camelot


# --- Normalisation Camelot -----------------------------------------------

@pytest.mark.parametrize(
    "brut, attendu",
    [
        # Notation classique, mineur
        ("Am", "8A"),
        ("A min", "8A"),
        ("Aminor", "8A"),
        ("F#m", "11A"),
        ("Gbm", "11A"),
        ("Dm", "7A"),
        ("Ebm", "2A"),
        # Notation classique, majeur
        ("C", "8B"),
        ("Cmaj", "8B"),
        ("A", "11B"),
        ("F#", "2B"),
        ("Bb", "6B"),
        # Déjà en Camelot
        ("8A", "8A"),
        ("12B", "12B"),
        ("8a", "8A"),
        # Open Key
        ("1m", "8A"),
        ("1d", "8B"),
        ("6d", "1B"),
        ("12m", "7A"),
        # Illisible ou absent
        ("", None),
        ("   ", None),
        (None, None),
        ("13A", None),
        ("0B", None),
        ("H#", None),
        ("inconnu", None),
    ],
)
def test_to_camelot(brut, attendu):
    assert to_camelot(brut) == attendu


def test_espaces_et_casse_tolerees():
    assert to_camelot("  am  ") == "8A"


# --- Pénalité de transition (tableau du spec §7) -------------------------

def test_meme_cle():
    assert key_penalty("8A", "8A") == 0


@pytest.mark.parametrize("voisin", ["9A", "7A"])
def test_voisin_sur_la_roue(voisin):
    assert key_penalty("8A", voisin) == 0


def test_voisin_traverse_le_zero():
    assert key_penalty("12A", "1A") == 0


def test_relatif_majeur_mineur():
    assert key_penalty("8A", "8B") == 0


@pytest.mark.parametrize("deux_crans", ["10A", "6A"])
def test_deux_crans_sur_la_roue(deux_crans):
    assert key_penalty("8A", deux_crans) == 1


@pytest.mark.parametrize("lointain", ["2A", "5A", "3B", "11B"])
def test_tout_autre_cas(lointain):
    assert key_penalty("8A", lointain) == 2


@pytest.mark.parametrize(
    "avant, apres",
    [("8A", None), (None, "8A"), (None, None)],
)
def test_cle_inconnue(avant, apres):
    assert key_penalty(avant, apres) == 0.5
