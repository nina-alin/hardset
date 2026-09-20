"""Tests du chargement de la configuration."""

import os

import pytest

from hardset.config import ConfigError, Weights, load_config


def _ecrit(tmp_path, nom, contenu):
    """Écrit `contenu` dans `tmp_path / nom` (UTF-8) et rend le chemin obtenu."""
    fichier = tmp_path / nom
    fichier.write_text(contenu, encoding="utf-8")
    return fichier


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
    fichier = _ecrit(
        tmp_path,
        "custom.yaml",
        "moods: [doux, fort]\n"
        "poids:\n"
        "  mood: 3.0\n"
        "profils:\n"
        "  lineaire-pur:\n"
        "    label: Test\n"
        "    bpm: {type: lineaire}\n"
        "    mood: {type: lineaire}\n",
    )
    config = load_config(fichier)
    assert config.moods == ("doux", "fort")
    assert config.mood_value("fort") == 2
    assert config.poids.mood == 3.0        # surchargé
    assert config.poids.bpm == 1.0         # valeur par défaut conservée


def test_trop_de_moods_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "trop.yaml",
        "moods: [a, b, c, d, e, f]\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="5"):
        load_config(fichier)


def test_type_de_courbe_inconnu_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "mauvais.yaml",
        "moods: [a, b]\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: exponentiel}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="exponentiel"):
        load_config(fichier)


# --- seconds_per_track ----------------------------------------------------

def test_seconds_per_track_charge_depuis_la_config_livree():
    config = load_config()
    assert config.seconds_per_track == 120


def test_seconds_per_track_invalide_refuse(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "invalide.yaml",
        "moods: [a, b]\n"
        "seconds_per_track: -10\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="seconds_per_track"):
        load_config(fichier)


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


# --- Seconde revue : trouvailles restantes --------------------------------

def test_poids_cle_non_chaine_refuse(tmp_path):
    """Une clé non-chaîne sous `poids:` (faute de frappe plausible) ne doit
    pas faire lever de `TypeError` brute par `hasattr`."""
    fichier = _ecrit(
        tmp_path,
        "poids_cle_int.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        "  5: 1.0\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="poids : les clés doivent être des chaînes"):
        load_config(fichier)


def test_profils_cle_non_chaine_refuse(tmp_path):
    """Même défaut, de même nature, du côté des clés de `profils:`."""
    fichier = _ecrit(
        tmp_path,
        "profils_cle_int.yaml",
        "moods: [a, b]\n"
        "profils:\n"
        "  5: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="profils : les clés doivent être des chaînes"):
        load_config(fichier)


def test_poids_k_flottant_non_entier_refuse(tmp_path):
    """`k` est une largeur de tirage entière : un flottant non entier ne doit
    pas être arrondi en douce par `int(...)`."""
    fichier = _ecrit(
        tmp_path,
        "poids_k_flottant.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        "  k: 5.5\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="poids.k"):
        load_config(fichier)


def test_poids_k_flottant_entier_accepte(tmp_path):
    """Un flottant qui représente exactement un entier (5.0) n'est pas un
    arrondi : il reste accepté et converti en `int`."""
    fichier = _ecrit(
        tmp_path,
        "poids_k_flottant_entier.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        "  k: 5.0\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    config = load_config(fichier)
    assert config.poids.k == 5


def test_collection_xml_liste_refuse(tmp_path):
    """`collection_xml` doit rester une chaîne, pas une liste ou un mapping
    transformés en texte absurde par `str(...)`."""
    fichier = _ecrit(
        tmp_path,
        "collection_liste.yaml",
        "moods: [a, b]\n"
        "collection_xml: [un, deux]\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="collection_xml"):
        load_config(fichier)


def test_collection_xml_absente_reste_none(tmp_path):
    """La clé absente reste évidemment valide : `collection_xml` vaut alors
    `None`."""
    fichier = _ecrit(
        tmp_path,
        "collection_absente.yaml",
        "moods: [a, b]\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    config = load_config(fichier)
    assert config.collection_xml is None


def test_collection_xml_nulle_reste_none(tmp_path):
    fichier = _ecrit(
        tmp_path,
        "collection_nulle.yaml",
        "moods: [a, b]\n"
        "collection_xml:\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    config = load_config(fichier)
    assert config.collection_xml is None


def test_chemin_est_un_repertoire_refuse(tmp_path):
    """Un chemin de configuration qui désigne un répertoire ne doit pas faire
    remonter d'`IsADirectoryError` brute."""
    repertoire = tmp_path / "config_dir"
    repertoire.mkdir()
    with pytest.raises(ConfigError, match="illisible"):
        load_config(repertoire)


def test_fichier_sans_droit_de_lecture_refuse(tmp_path):
    """Un fichier sans droit de lecture ne doit pas faire remonter de
    `PermissionError` brute (root ignore les permissions, donc non testable
    sous cet utilisateur)."""
    if os.name != "posix" or os.getuid() == 0:
        pytest.skip("test de permissions non pertinent (root ou non POSIX)")
    fichier = _ecrit(tmp_path, "prive.yaml", "moods: [a, b]\n")
    fichier.chmod(0o000)
    try:
        with pytest.raises(ConfigError, match="illisible"):
            load_config(fichier)
    finally:
        fichier.chmod(0o644)


def test_messages_de_refus_de_type_harmonises(tmp_path):
    """Le refus d'un booléen là où un nombre est attendu doit être formulé à
    l'identique, que ce soit sous `poids:` ou pour `seconds_per_track`."""
    fichier_poids = _ecrit(
        tmp_path,
        "poids_bool.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        "  mood: true\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    fichier_seconds = _ecrit(
        tmp_path,
        "seconds_bool.yaml",
        "moods: [a, b]\n"
        "seconds_per_track: true\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError) as erreur_poids:
        load_config(fichier_poids)
    with pytest.raises(ConfigError) as erreur_seconds:
        load_config(fichier_seconds)

    phrase_poids = str(erreur_poids.value).split(" : ", 1)[1]
    phrase_seconds = str(erreur_seconds.value).split(" : ", 1)[1]
    assert phrase_poids == phrase_seconds


# --- Troisième revue : balayage exhaustif ---------------------------------

def test_fichier_avec_segment_non_repertoire_refuse(tmp_path):
    """Un chemin dont un segment intermédiaire est un fichier (et non un
    répertoire) ne doit pas faire remonter de `NotADirectoryError` brute."""
    segment_fichier = tmp_path / "pas_un_dossier"
    segment_fichier.write_text("x", encoding="utf-8")
    chemin_impossible = segment_fichier / "hardset.yaml"
    with pytest.raises(ConfigError, match="illisible"):
        load_config(chemin_impossible)


def test_fichier_non_utf8_refuse(tmp_path):
    """Un fichier enregistré en latin-1 (accents français mal encodés) ne
    doit pas faire remonter d'`UnicodeDecodeError` brute : elle hérite de
    `ValueError`, pas d'`OSError`, donc un `except OSError` ne l'attraperait
    pas."""
    fichier = tmp_path / "latin1.yaml"
    contenu = (
        "moods: [calme, dansant, \"un peu vénère\"]\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n"
    )
    fichier.write_bytes(contenu.encode("latin-1"))
    with pytest.raises(ConfigError, match="illisible"):
        load_config(fichier)


@pytest.mark.parametrize(
    "yaml_element",
    ["null", "true", "5", "{x: 1}", "[1, 2]"],
)
def test_moods_element_non_chaine_refuse(tmp_path, yaml_element):
    """Un élément non scalaire ou non textuel dans `moods` ne doit pas être
    coercé en douce par `str(...)` (même défaut que `collection_xml`)."""
    fichier = _ecrit(
        tmp_path,
        "moods_element.yaml",
        f"moods: [calme, {yaml_element}]\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="moods"):
        load_config(fichier)


def test_label_non_scalaire_refuse(tmp_path):
    """`label` doit rester une chaîne, pas un mapping transformé en texte
    absurde par `str(...)` (même défaut que `collection_xml` et `moods`)."""
    fichier = _ecrit(
        tmp_path,
        "label_mapping.yaml",
        "moods: [a, b]\n"
        "profils:\n"
        "  p:\n"
        "    label: {x: 1}\n"
        "    bpm: {type: lineaire}\n"
        "    mood: {type: lineaire}\n",
    )
    with pytest.raises(ConfigError, match="profils.p.label"):
        load_config(fichier)


def test_moods_falsy_refuse(tmp_path):
    """`moods: 0` est une valeur fausse au sens Python : l'idiome `... or ()`
    la ferait passer pour une absence de clé au lieu d'être rejetée pour
    mauvais type."""
    fichier = _ecrit(
        tmp_path,
        "moods_falsy.yaml",
        "moods: 0\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="moods"):
        load_config(fichier)


def test_profils_falsy_refuse(tmp_path):
    """Même défaut que `moods`/`poids` pour `profils: 0`."""
    fichier = _ecrit(
        tmp_path,
        "profils_falsy.yaml",
        "moods: [a, b]\nprofils: 0\n",
    )
    with pytest.raises(ConfigError, match="profils"):
        load_config(fichier)


def test_poids_falsy_refuse(tmp_path):
    """`poids: 0` est une valeur fausse au sens Python : l'idiome `... or {}`
    la ferait passer pour « aucune surcharge » au lieu d'être rejetée pour
    mauvais type."""
    fichier = _ecrit(
        tmp_path,
        "poids_falsy.yaml",
        "moods: [a, b]\n"
        "poids: 0\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="poids doit être un mapping"):
        load_config(fichier)


def test_seconds_per_track_flottant_entier_accepte(tmp_path):
    """`seconds_per_track` doit passer par `_entier`, qui accepte un flottant
    exactement entier (`120.0`), comme `poids.k` le fait déjà. L'ancienne
    validation manuelle rejetait ce cas alors que `_entier` l'accepte : c'est
    la divergence de comportement que la factorisation doit éliminer."""
    fichier = _ecrit(
        tmp_path,
        "seconds_flottant_entier.yaml",
        "moods: [a, b]\n"
        "seconds_per_track: 120.0\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    config = load_config(fichier)
    assert config.seconds_per_track == 120


def test_courbe_parametre_cle_non_chaine_refuse(tmp_path):
    """Des clés de paramètres de courbe de types incompatibles entre eux
    (un entier et une chaîne, par exemple) ne doivent pas faire remonter de
    `TypeError` brute depuis `sorted(...)` lors du calcul des paramètres
    inconnus."""
    fichier = _ecrit(
        tmp_path,
        "courbe_cle_mixte.yaml",
        "moods: [a, b]\n"
        "profils:\n"
        "  p:\n"
        "    label: P\n"
        "    bpm: {type: lineaire, depart: 1, 5: 2, autre: 3}\n"
        "    mood: {type: lineaire}\n",
    )
    with pytest.raises(ConfigError, match="profils.p.bpm"):
        load_config(fichier)


@pytest.mark.parametrize("champ_special", ["__class__", "__init__", "__dict__"])
def test_poids_champ_special_python_refuse(tmp_path, champ_special):
    """Un nom de champ correspondant à un attribut spécial de Python
    (`__class__`, `__init__`, `__dict__`) existe forcément sur toute
    instance : `hasattr(poids, champ)` le laisserait passer, et
    `dataclasses.replace(...)` planterait ensuite avec une `TypeError` brute
    au lieu d'une `ConfigError` nommant le champ inconnu."""
    fichier = _ecrit(
        tmp_path,
        f"poids_special_{champ_special.strip('_')}.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        f"  {champ_special}: 5\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match=f"poids.{champ_special} : poids inconnu"):
        load_config(fichier)


# --- Corrections de clôture : validation du nom des clés -------------------

def test_racine_cle_inconnue_refuse(tmp_path):
    """Une clé racine mal orthographiée (`seconds_per_tracks`, au pluriel) ne
    doit pas se charger en silence : elle ferait sinon dériver la durée du
    set sans qu'aucun message ne le signale."""
    fichier = _ecrit(
        tmp_path,
        "racine_typo.yaml",
        "moods: [a, b]\n"
        "seconds_per_tracks: 90\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="seconds_per_tracks"):
        load_config(fichier)


def test_profil_cle_inconnue_refuse(tmp_path):
    """Même défaut dans le corps d'un profil : `labell` (au lieu de `label`)
    ferait prendre la clé du profil comme libellé sans le dire."""
    fichier = _ecrit(
        tmp_path,
        "profil_typo.yaml",
        "moods: [a, b]\n"
        "profils:\n"
        "  p:\n"
        "    labell: Montée\n"
        "    bpm: {type: lineaire}\n"
        "    mood: {type: lineaire}\n",
    )
    with pytest.raises(ConfigError, match="labell"):
        load_config(fichier)


# --- Corrections de clôture : gardes non couvertes par un test -------------

def test_courbe_parametre_inconnu_nomme_refuse(tmp_path):
    """Une vraie faute de frappe sur un paramètre de courbe (`amplitud` au
    lieu d'`amplitude`) doit être nommée par le message, sans être masquée
    par la garde de type de clé (qui ne se déclenche pas ici : `amplitud`
    est bien une chaîne)."""
    fichier = _ecrit(
        tmp_path,
        "courbe_typo.yaml",
        "moods: [a, b]\n"
        "profils:\n"
        "  p:\n"
        "    label: P\n"
        "    bpm: {type: vagues, amplitud: 0.15}\n"
        "    mood: {type: lineaire}\n",
    )
    with pytest.raises(ConfigError, match="amplitud"):
        load_config(fichier)


def test_moods_vide_refuse(tmp_path):
    """`moods: []` : une liste vide reste une liste valide, mais ne définit
    aucun mood."""
    fichier = _ecrit(
        tmp_path,
        "moods_vide.yaml",
        "moods: []\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="au moins un mood"):
        load_config(fichier)


def test_profils_vide_refuse(tmp_path):
    """`profils: {}` : un mapping vide reste un mapping valide, mais ne
    définit aucun profil."""
    fichier = _ecrit(tmp_path, "profils_vide.yaml", "moods: [a, b]\nprofils: {}\n")
    with pytest.raises(ConfigError, match="au moins un profil"):
        load_config(fichier)


def test_poids_champ_inconnu_plausible_refuse(tmp_path):
    """Une faute de frappe plausible sous `poids:` (`moodd` au lieu de
    `mood`), et non seulement les cas `__dunder__` déjà couverts."""
    fichier = _ecrit(
        tmp_path,
        "poids_typo.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        "  moodd: 1.5\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="poids.moodd"):
        load_config(fichier)


# --- Corrections de clôture : `poids:` vide et messages de clé nulle -------

def test_poids_nul_reste_sans_surcharge(tmp_path):
    """Commenter tous les poids sous `poids:` (donc `poids:` sans enfant,
    lu `None` par YAML) doit rester équivalent à une clé absente : « aucune
    surcharge », pas une `ConfigError`."""
    fichier = _ecrit(
        tmp_path,
        "poids_nul.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    config = load_config(fichier)
    assert config.poids == Weights()


def test_moods_nul_message_adequat(tmp_path):
    """`moods:` laissé nul doit être décrit comme l'absence d'au moins un
    mood, pas comme « pas une valeur unique » (un message qui décrirait mal
    la situation d'une clé simplement vide)."""
    fichier = _ecrit(
        tmp_path,
        "moods_nul.yaml",
        "moods:\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="au moins un mood"):
        load_config(fichier)


def test_profils_nul_message_adequat(tmp_path):
    """Même raisonnement que pour `moods:` nul, côté `profils:`."""
    fichier = _ecrit(tmp_path, "profils_nul.yaml", "moods: [a, b]\nprofils:\n")
    with pytest.raises(ConfigError, match="au moins un profil"):
        load_config(fichier)


# --- Corrections de clôture : bornes sur les valeurs de `poids` ------------

def test_poids_k_zero_refuse(tmp_path):
    """`k` est une largeur de tirage : `0` (ou moins) partirait en
    comportement absurde dans le moteur, loin de `load_config()`."""
    fichier = _ecrit(
        tmp_path,
        "poids_k_zero.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        "  k: 0\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="poids.k"):
        load_config(fichier)


def test_poids_bpm_tolerance_zero_refuse(tmp_path):
    """`bpm_tolerance` est un diviseur : `0` partirait en
    `ZeroDivisionError` dans le moteur."""
    fichier = _ecrit(
        tmp_path,
        "poids_bpm_tolerance_zero.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        "  bpm_tolerance: 0\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="poids.bpm_tolerance"):
        load_config(fichier)


def test_poids_bpm_negatif_refuse(tmp_path):
    """Les poids (`bpm`, `mood`, `tonalite`) doivent rester positifs ou
    nuls : un poids négatif inverserait le sens du coût qu'il pondère."""
    fichier = _ecrit(
        tmp_path,
        "poids_bpm_negatif.yaml",
        "moods: [a, b]\n"
        "poids:\n"
        "  bpm: -1.0\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="poids.bpm"):
        load_config(fichier)


# --- Corrections de clôture : doublons dans `moods` -------------------------

def test_moods_doublon_refuse(tmp_path):
    """Un doublon rend un niveau de l'échelle ordinale inatteignable :
    `mood_value` rend toujours l'index du premier tag rencontré."""
    fichier = _ecrit(
        tmp_path,
        "moods_doublon.yaml",
        "moods: [calme, calme, vénère]\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="doublon"):
        load_config(fichier)


def test_moods_doublon_normalise_refuse(tmp_path):
    """Le doublon se détecte aussi entre deux graphies du même tag
    (`Calme` / `calme`), via `normalize_tag`, comme `mood_value` le fait
    déjà."""
    fichier = _ecrit(
        tmp_path,
        "moods_doublon_normalise.yaml",
        "moods: [Calme, calme]\n"
        "profils:\n"
        "  p: {label: P, bpm: {type: lineaire}, mood: {type: lineaire}}\n",
    )
    with pytest.raises(ConfigError, match="doublon"):
        load_config(fichier)


# --- Chemin de configuration par défaut -----------------------------------
# La commande `hardset` s'utilise depuis n'importe où : sans `hardset.yaml`
# dans le répertoire courant, elle retombe sur l'exemplaire livré avec le
# paquet plutôt que d'échouer sur « configuration introuvable ».

def test_sans_fichier_dans_le_repertoire_courant_on_prend_celui_du_paquet(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert config.moods
    assert config.profils


def test_le_fichier_du_repertoire_courant_a_la_priorite(monkeypatch, tmp_path):
    (tmp_path / "hardset.yaml").write_text(
        "moods: [calme]\n"
        "profils:\n"
        "  simple:\n"
        "    bpm: {type: lineaire}\n"
        "    mood: {type: lineaire}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert config.moods == ("calme",)
    assert list(config.profils) == ["simple"]


def test_un_chemin_explicite_reste_prioritaire(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="introuvable"):
        load_config(tmp_path / "absent.yaml")
