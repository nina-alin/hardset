"""Tests du chargement de la configuration."""

import pytest

from hardset.config import ConfigError, load_config


# --- Configuration livrée ------------------------------------------------

def test_charge_la_config_livree():
    config = load_config()
    assert config.moods[0] == "calme"
    assert len(config.moods) == 5
    assert set(config.profils) == {"montee", "warmup-long", "plateau", "vagues"}
    assert config.poids.mood == 1.5
    assert config.poids.k == 5


def test_profil_vagues_porte_ses_parametres():
    profil = load_config().profils["vagues"]
    assert profil.label == "Vagues"
    assert profil.bpm.type == "vagues"
    assert profil.bpm.params["amplitude"] == 0.15
    assert profil.bpm.params["oscillations"] == 2.5
    assert profil.mood.type == "lineaire"


# --- Résolution d'un tag de mood -----------------------------------------

@pytest.mark.parametrize(
    "tag, attendu",
    [
        ("calme", 1),
        ("Dansant", 2),
        ("un peu vénère", 3),
        ("VÉNÈRE", 4),
        ("c'est du bruit", 5),
        ("hardcore", None),
        ("", None),
    ],
)
def test_mood_value(tag, attendu):
    assert load_config().mood_value(tag) == attendu


# --- Surcharge par fichier -----------------------------------------------

def test_surcharge_partielle(tmp_path):
    fichier = tmp_path / "custom.yaml"
    fichier.write_text(
        "moods: [doux, fort]\n"
        "poids:\n"
        "  mood: 3.0\n"
        "profils:\n"
        "  lineaire-pur:\n"
        "    label: Test\n"
        "    bpm: {type: lineaire}\n"
        "    mood: {type: lineaire}\n",
        encoding="utf-8",
    )
    config = load_config(fichier)
    assert config.moods == ("doux", "fort")
    assert config.mood_value("fort") == 2
    assert config.poids.mood == 3.0        # surchargé
    assert config.poids.bpm == 1.0         # valeur par défaut conservée


def test_trop_de_moods_refuse(tmp_path):
    fichier = tmp_path / "trop.yaml"
    fichier.write_text(
        "moods: [a, b, c, d, e, f]\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="5"):
        load_config(fichier)


def test_type_de_courbe_inconnu_refuse(tmp_path):
    fichier = tmp_path / "mauvais.yaml"
    fichier.write_text(
        "moods: [a, b]\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: exponentiel}, mood: {type: lineaire}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="exponentiel"):
        load_config(fichier)


# --- seconds_per_track ----------------------------------------------------

def test_seconds_per_track_charge_depuis_la_config_livree():
    config = load_config()
    assert config.seconds_per_track == 120


def test_seconds_per_track_invalide_refuse(tmp_path):
    fichier = tmp_path / "invalide.yaml"
    fichier.write_text(
        "moods: [a, b]\n"
        "seconds_per_track: -10\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="seconds_per_track"):
        load_config(fichier)
