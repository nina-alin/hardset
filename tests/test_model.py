"""Tests du modèle : normalisation des tags et nombre de morceaux visé."""

import pytest

from hardset.model import SetRequest, normalize_tag


# --- Normalisation des tags ----------------------------------------------

@pytest.mark.parametrize(
    "brut, attendu",
    [
        ("Vénère", "venere"),
        ("  vénère  ", "venere"),
        ("VENERE", "venere"),
        ("C'est du bruit", "c'est du bruit"),
        ("un peu vénère", "un peu venere"),
        ("Hardcore", "hardcore"),
    ],
)
def test_normalize_tag(brut, attendu):
    assert normalize_tag(brut) == attendu


# --- Nombre de morceaux visé ---------------------------------------------

def make_request(**kwargs) -> SetRequest:
    base = dict(
        genres=frozenset(),
        moods=frozenset(),
        bpm_min=150.0,
        bpm_max=200.0,
        profile="montee",
        duration_min=90,
    )
    base.update(kwargs)
    return SetRequest(**base)


def test_track_count_90min_120s():
    assert make_request(duration_min=90).track_count == 45


def test_track_count_arrondi_inferieur():
    # 50 min à 180 s = 16,67 morceaux : on n'en vise pas 17.
    assert make_request(duration_min=50, seconds_per_track=180).track_count == 16


def test_track_count_minimum_un():
    assert make_request(duration_min=1, seconds_per_track=120).track_count == 1
