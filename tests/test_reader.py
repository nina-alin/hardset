"""Tests du lecteur de collection Rekordbox.

Les cas de parsing des My Tags reposent sur l'hypothèse non vérifiée de format
`/* tag / tag */` (voir la docstring de hardset/rekordbox/reader.py) : ils décrivent
le comportement du parseur pour ce format hypothétique, pas un format observé sur un
export réel. `tools/inspect_collection.py` est la sonde prévue pour confronter cette
hypothèse à un export réel dès qu'on en aura un.
"""

from pathlib import Path

import pytest

from hardset.config import load_config
from hardset.model import WarningCode
from hardset.rekordbox.reader import (
    Collection,
    CollectionError,
    _float,
    _int,
    parse_my_tags,
    read_collection,
)

FIXTURE = Path(__file__).parent / "fixtures" / "collection_extrait.xml"


# --- Extraction des My Tags ----------------------------------------------

@pytest.mark.parametrize(
    "comments, attendu",
    [
        ("/* Hardcore / vénère */", ("Hardcore", "vénère")),
        ("/* Hardcore */", ("Hardcore",)),
        ("un commentaire libre /* Frenchcore / calme */", ("Frenchcore", "calme")),
        ("/* Uptempo / c'est du bruit */ suivi de texte", ("Uptempo", "c'est du bruit")),
        ("/*Hardcore/vénère*/", ("Hardcore", "vénère")),
        ("/*  Hardcore  /  vénère  */", ("Hardcore", "vénère")),
        ("commentaire sans tag", ()),
        ("", ()),
        (None, ()),
        ("/* */", ()),
        ("/* Hardcore / / vénère */", ("Hardcore", "vénère")),
    ],
)
def test_parse_my_tags(comments, attendu):
    assert parse_my_tags(comments) == attendu


# --- Lecture d'une collection fabriquée ----------------------------------

def ecrire_xml(tmp_path: Path, tracks_xml: str) -> Path:
    chemin = tmp_path / "collection.xml"
    chemin.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<DJ_PLAYLISTS Version="1.0.0">\n'
        '  <PRODUCT Name="rekordbox" Version="6.0.0" Company="AlphaTheta"/>\n'
        f'  <COLLECTION Entries="0">{tracks_xml}</COLLECTION>\n'
        '  <PLAYLISTS/>\n'
        '</DJ_PLAYLISTS>\n',
        encoding="utf-8",
    )
    return chemin


def test_lit_un_morceau_complet(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="1" Name="Titre" Artist="Artiste" AverageBpm="180.00"'
        ' Tonality="Am" TotalTime="240" Location="file://localhost/x.mp3"'
        ' Comments="/* Hardcore / Uptempo / vénère */"/>',
    )
    collection = read_collection(chemin, load_config())
    track = collection.tracks[0]
    assert track.id == "1"
    assert track.artist == "Artiste"
    assert track.title == "Titre"
    assert track.bpm == 180.0
    assert track.camelot == "8A"
    assert track.duration_s == 240
    assert track.genres == ("Hardcore", "Uptempo")
    assert track.mood == 4
    assert track.raw_attrs["Location"] == "file://localhost/x.mp3"


def test_mood_multiple_exclu_et_signale(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="2" Name="T" Artist="A" AverageBpm="180" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore / calme / vénère */"/>',
    )
    collection = read_collection(chemin, load_config())
    assert collection.tracks[0].mood is None
    assert collection.tracks[0].genres == ("Hardcore",)
    codes = {w.code for w in collection.warnings}
    assert WarningCode.MULTIPLE_MOODS in codes
    avertissement = next(w for w in collection.warnings if w.code == WarningCode.MULTIPLE_MOODS)
    assert avertissement.track_ids == ("2",)


def test_mood_absent_signale(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="3" Name="T" Artist="A" AverageBpm="180" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore */"/>',
    )
    collection = read_collection(chemin, load_config())
    assert collection.tracks[0].mood is None
    assert WarningCode.NO_MOOD in {w.code for w in collection.warnings}


def test_tonalite_illisible_signalee(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="4" Name="T" Artist="A" AverageBpm="180" Tonality=""'
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore / vénère */"/>',
    )
    collection = read_collection(chemin, load_config())
    assert collection.tracks[0].camelot is None
    assert WarningCode.NO_KEY in {w.code for w in collection.warnings}


def test_tonalite_absente_signalee(tmp_path):
    # `Tonality=""` et l'attribut complètement omis doivent être traités de façon
    # identique : un vrai export pourrait tout aussi bien omettre l'attribut plutôt
    # que de le laisser vide.
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="4b" Name="T" Artist="A" AverageBpm="180"'
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore / vénère */"/>',
    )
    collection = read_collection(chemin, load_config())
    assert collection.tracks[0].camelot is None
    assert WarningCode.NO_KEY in {w.code for w in collection.warnings}


def test_genres_tries_et_dedoublonnes(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="5" Name="T" Artist="A" AverageBpm="180" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* Uptempo / vénère */"/>'
        '<TRACK TrackID="6" Name="T" Artist="A" AverageBpm="190" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* uptempo / Hardcore / calme */"/>',
    )
    collection = read_collection(chemin, load_config())
    # « uptempo » et « Uptempo » sont le même genre : la première casse rencontrée gagne.
    assert collection.genres == ("Hardcore", "Uptempo")
    assert collection.bpm_range == (180.0, 190.0)


def test_bpm_illisible_donne_zero(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="7" Name="T" Artist="A" AverageBpm="" Tonality="Am"'
        ' TotalTime="" Location="file://x" Comments="/* Hardcore / vénère */"/>',
    )
    collection = read_collection(chemin, load_config())
    assert collection.tracks[0].bpm == 0.0
    assert collection.tracks[0].duration_s == 0


def test_track_id_absent_ignore_et_signale(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK Name="Sans id" Artist="Anonyme" AverageBpm="180" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore / vénère */"/>'
        '<TRACK TrackID="9" Name="Avec id" Artist="B" AverageBpm="140" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore / calme */"/>',
    )
    collection = read_collection(chemin, load_config())
    # Le morceau sans TrackID ne peut pas être référencé en playlist : il est
    # effectivement absent de la collection, mais l'absence doit être signalée.
    assert len(collection.tracks) == 1
    assert collection.tracks[0].id == "9"
    codes = {w.code for w in collection.warnings}
    assert WarningCode.NO_TRACK_ID in codes
    avertissement = next(w for w in collection.warnings if w.code == WarningCode.NO_TRACK_ID)
    assert avertissement.track_ids == ("Anonyme — Sans id",)


def test_fichier_absent(tmp_path):
    with pytest.raises(CollectionError, match="introuvable"):
        read_collection(tmp_path / "rien.xml", load_config())


def test_xml_invalide(tmp_path):
    chemin = tmp_path / "casse.xml"
    chemin.write_text("<DJ_PLAYLISTS", encoding="utf-8")
    with pytest.raises(CollectionError, match="XML"):
        read_collection(chemin, load_config())


def test_chemin_est_un_repertoire(tmp_path):
    with pytest.raises(CollectionError, match="lire"):
        read_collection(tmp_path, load_config())


def test_fichier_sans_droit_de_lecture(tmp_path):
    chemin = tmp_path / "prive.xml"
    chemin.write_text("<DJ_PLAYLISTS/>", encoding="utf-8")
    chemin.chmod(0o000)
    try:
        with pytest.raises(CollectionError, match="lire"):
            read_collection(chemin, load_config())
    finally:
        chemin.chmod(0o644)


# --- Plage de BPM ---------------------------------------------------------

def test_bpm_range_collection_vide():
    assert Collection(tracks=()).bpm_range == (0.0, 0.0)


def test_bpm_range_tous_bpm_a_zero(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="10" Name="T" Artist="A" AverageBpm="0" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore */"/>',
    )
    collection = read_collection(chemin, load_config())
    assert collection.bpm_range == (0.0, 0.0)


# --- Conversions défensives ------------------------------------------------

@pytest.mark.parametrize("value", ["", None, "N/A"])
def test_float_valeur_non_numerique_ou_absente_donne_zero(value):
    assert _float(value) == 0.0


@pytest.mark.parametrize("value", ["", None, "N/A"])
def test_int_valeur_non_numerique_ou_absente_donne_zero(value):
    assert _int(value) == 0


# --- Lecture de bout en bout d'une fixture complète ------------------------

@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture absente")
def test_lecture_complete_de_la_fixture_couvre_tous_les_cas():
    """Ne valide PAS le format d'un export Rekordbox réel : la fixture est fabriquée
    à la main sous l'hypothèse `/* tag / tag */` (voir docstring du module), pas
    extraite d'un vrai export. Atteste seulement que le lecteur traite de bout en
    bout une collection complète couvrant tous les cas déjà testés unitairement
    (mood unique, mood multiple, mood absent, tonalité illisible, plusieurs genres,
    etc.) sans lever d'exception et en produisant des résultats cohérents.
    """
    collection = read_collection(FIXTURE, load_config())
    assert len(collection.tracks) >= 8
    assert any(t.mood is not None and t.genres for t in collection.tracks)
    assert collection.genres
