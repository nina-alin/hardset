"""Tests du lecteur de collection Rekordbox.

Les cas de parsing des My Tags proviennent des valeurs de `Comments` observées
sur l'export réel (cf. tools/inspect_collection.py, tâche 1).
"""

from pathlib import Path

import pytest

from hardset.config import load_config
from hardset.model import WarningCode
from hardset.rekordbox.reader import CollectionError, parse_my_tags, read_collection

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


def test_fichier_absent(tmp_path):
    with pytest.raises(CollectionError, match="introuvable"):
        read_collection(tmp_path / "rien.xml", load_config())


def test_xml_invalide(tmp_path):
    chemin = tmp_path / "casse.xml"
    chemin.write_text("<DJ_PLAYLISTS", encoding="utf-8")
    with pytest.raises(CollectionError, match="XML"):
        read_collection(chemin, load_config())


# --- Lecture de l'extrait réel -------------------------------------------

@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture d'export réel absente")
def test_extrait_reel_est_exploitable():
    collection = read_collection(FIXTURE, load_config())
    assert len(collection.tracks) >= 8
    # Au moins un morceau complètement exploitable, sinon le format a changé.
    assert any(t.mood is not None and t.genres for t in collection.tracks)
    assert collection.genres
