"""Tests des courbes de progression et du calcul des cibles."""

import pytest

from hardset.config import CurveSpec, Profile
from hardset.engine.curves import CurveError, build_targets, curve_fn
from hardset.model import MOOD_MAX, MOOD_MIN, SetRequest


def profil(bpm: CurveSpec, mood: CurveSpec | None = None) -> Profile:
    return Profile(key="test", label="Test", bpm=bpm, mood=mood or bpm)


def requete(**kwargs) -> SetRequest:
    base = dict(
        genres=frozenset(),
        moods=frozenset(),
        bpm_min=150.0,
        bpm_max=200.0,
        profile="test",
        duration_min=20,
    )
    base.update(kwargs)
    return SetRequest(**base)


# --- Types de courbe -----------------------------------------------------

def test_lineaire_par_defaut_va_de_0_a_1():
    f = curve_fn(CurveSpec("lineaire", {}))
    assert f(0.0) == pytest.approx(0.0)
    assert f(0.5) == pytest.approx(0.5)
    assert f(1.0) == pytest.approx(1.0)


def test_lineaire_avec_depart():
    f = curve_fn(CurveSpec("lineaire", {"depart": 0.7}))
    assert f(0.0) == pytest.approx(0.7)
    assert f(1.0) == pytest.approx(1.0)


def test_retarde_reste_a_zero_avant_le_palier():
    f = curve_fn(CurveSpec("retarde", {"palier": 0.4}))
    assert f(0.0) == pytest.approx(0.0)
    assert f(0.39) == pytest.approx(0.0)
    assert f(0.4) == pytest.approx(0.0)
    assert f(0.7) == pytest.approx(0.5)
    assert f(1.0) == pytest.approx(1.0)


def test_vagues_oscille_et_reste_borne():
    f = curve_fn(CurveSpec("vagues", {"amplitude": 0.15, "oscillations": 2.5}))
    valeurs = [f(i / 50) for i in range(51)]
    assert all(0.0 <= v <= 1.0 for v in valeurs)
    # Une vague, c'est au moins une redescente.
    assert any(b < a for a, b in zip(valeurs, valeurs[1:]))


def test_type_inconnu_refuse():
    with pytest.raises(CurveError):
        curve_fn(CurveSpec("exponentiel", {}))


# --- Cibles --------------------------------------------------------------

def test_cibles_encadrent_la_plage_bpm():
    cibles = build_targets(requete(), profil(CurveSpec("lineaire", {})), 10)
    assert len(cibles) == 10
    assert [c.position for c in cibles] == list(range(10))
    assert cibles[0].bpm == pytest.approx(150.0)
    assert cibles[-1].bpm == pytest.approx(200.0)


def test_mood_cible_non_arrondi():
    cibles = build_targets(requete(), profil(CurveSpec("lineaire", {})), 3)
    assert cibles[1].mood == pytest.approx(3.0)   # milieu de 1 → 5
    assert isinstance(cibles[1].mood, float)


def test_mood_cible_borne_par_les_moods_demandes():
    cibles = build_targets(requete(moods=frozenset({2, 3})), profil(CurveSpec("lineaire", {})), 5)
    assert cibles[0].mood == pytest.approx(2.0)
    assert cibles[-1].mood == pytest.approx(3.0)


def test_une_seule_position():
    cibles = build_targets(requete(), profil(CurveSpec("lineaire", {})), 1)
    assert len(cibles) == 1
    assert cibles[0].bpm == pytest.approx(150.0)   # t = 0


def test_count_nul_donne_une_liste_vide():
    assert build_targets(requete(), profil(CurveSpec("lineaire", {})), 0) == []


def test_profil_vagues_redescend():
    cibles = build_targets(
        requete(),
        profil(CurveSpec("vagues", {"amplitude": 0.15, "oscillations": 2.5}),
               CurveSpec("lineaire", {})),
        40,
    )
    bpms = [c.bpm for c in cibles]
    assert any(b < a for a, b in zip(bpms, bpms[1:]))


def test_mood_vagues_reste_dans_les_bornes():
    """Vérifier le bornage de mood à travers build_targets avec une courbe vagues.

    Avec une forte amplitude, la courbe vagues sortirait des bornes [0,1]
    sans le clamp. Vérifie que les cibles restent dans [mood_min, mood_max].
    """
    cibles = build_targets(
        requete(moods=frozenset({1, 5})),
        profil(
            CurveSpec("lineaire", {}),
            CurveSpec("vagues", {"amplitude": 0.6, "oscillations": 2})
        ),
        50,
    )
    moods = [c.mood for c in cibles]
    # Toutes les moods doivent rester dans les bornes demandées
    assert all(1.0 <= m <= 5.0 for m in moods), f"Mood hors bornes : min={min(moods)}, max={max(moods)}"
