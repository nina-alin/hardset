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


def _ecrit(tmp_path, nom, contenu):
    fichier = tmp_path / nom
    fichier.write_text(contenu, encoding="utf-8")
    return fichier


def test_seconds_per_track_non_entier_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "non_entier.yaml",
        "moods: [a, b]\n"
        "seconds_per_track: 1.5\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="seconds_per_track"):
        load_config(fichier)


def test_seconds_per_track_booleen_true_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "booleen_true.yaml",
        "moods: [a, b]\n"
        "seconds_per_track: true\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="seconds_per_track"):
        load_config(fichier)


def test_seconds_per_track_booleen_false_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "booleen_false.yaml",
        "moods: [a, b]\n"
        "seconds_per_track: false\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="seconds_per_track"):
        load_config(fichier)


# --- Durcissement de la validation ---------------------------------------

def test_racine_non_mapping_refuse(tmp_path):
    fichier = _ecrit(tmp_path, "racine_liste.yaml", "- a\n- b\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(fichier)


def test_moods_chaine_unique_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "moods_chaine.yaml",
        "moods: calme\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="moods"):
        load_config(fichier)


def test_moods_non_sequence_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "moods_mapping.yaml",
        "moods: {a: 1}\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="moods"):
        load_config(fichier)


def test_profils_non_mapping_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "profils_liste.yaml",
        "moods: [a, b]\n"
        "profils: [p]\n",
    )
    with pytest.raises(ConfigError, match="profils"):
        load_config(fichier)


def test_profil_entree_non_mapping_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "profil_texte.yaml",
        "moods: [a, b]\n"
        "profils:\n"
        "  p: juste du texte\n",
    )
    with pytest.raises(ConfigError, match="profils.p"):
        load_config(fichier)


def test_poids_non_mapping_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "poids_liste.yaml",
        "moods: [a, b]\n"
        "poids: [1, 2]\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="poids"):
        load_config(fichier)


def test_poids_valeur_non_numerique_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "poids_texte.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        "  mood: pas-un-nombre\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="poids.mood"):
        load_config(fichier)


def test_poids_valeur_booleenne_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "poids_booleen.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        "  k: true\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="poids.k"):
        load_config(fichier)


def test_parametre_de_courbe_non_numerique_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "courbe_texte.yaml",
        "moods: [a, b]\n"
        "profils:\n"
        "  p:\n"
        "    label: P\n"
        "    bpm: {type: lineaire, depart: pas-un-nombre}\n"
        "    mood: {type: lineaire}\n",
    )
    with pytest.raises(ConfigError, match="profils.p.bpm.depart"):
        load_config(fichier)
