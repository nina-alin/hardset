"""Tests du lecteur de collection Rekordbox.

Le format `/* tag / tag */` des My Tags a été observé sur un export réel, dont
`tests/fixtures/collection_reelle.xml` est un extrait verbatim ; les tests qui
le lisent sont regroupés en fin de fichier. Les autres cas de parsing restent
exercés sur des XML fabriqués à la main : ils décrivent la robustesse du
parseur (bloc non fermé, séparateurs multiples, commentaire libre autour), pas
ce qu'un export réel contient.
"""

import os
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
        ("/* Hardcore / CARREMENT VNR */", ("Hardcore", "CARREMENT VNR")),
        ("/* Hardcore */", ("Hardcore",)),
        ("un commentaire libre /* Frenchcore / CALME */", ("Frenchcore", "CALME")),
        ("/* Uptempo / C DU BRUIT */ suivi de texte", ("Uptempo", "C DU BRUIT")),
        ("/*Hardcore/CARREMENT VNR*/", ("Hardcore", "CARREMENT VNR")),
        ("/*  Hardcore  /  CARREMENT VNR  */", ("Hardcore", "CARREMENT VNR")),
        ("commentaire sans tag", ()),
        ("", ()),
        (None, ()),
        ("/* */", ()),
        ("/* Hardcore / / CARREMENT VNR */", ("Hardcore", "CARREMENT VNR")),
        # Plusieurs blocs : seul le premier est extrait (regex .search, non .findall)
        ("/* Hardcore / Uptempo */ texte /* Frenchcore / CALME */", ("Hardcore", "Uptempo")),
        # Bloc non fermé : aucun tag n'est extrait (fermeture `*/` manquante)
        ("/* Hardcore sans fermeture", ()),
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
        ' Comments="/* Hardcore / Uptempo / CARREMENT VNR */"/>',
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


def test_mood_multiple_signale_mais_conserve(tmp_path):
    """Signalé, mais jouable : l'énergie retenue est la moyenne des deux moods."""
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="2" Name="T" Artist="A" AverageBpm="180" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore / CALME / CARREMENT VNR */"/>',
    )
    collection = read_collection(chemin, load_config())
    assert collection.tracks[0].moods == (1, 4)
    assert collection.tracks[0].mood == 2.5
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
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore / CARREMENT VNR */"/>',
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
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore / CARREMENT VNR */"/>',
    )
    collection = read_collection(chemin, load_config())
    assert collection.tracks[0].camelot is None
    assert WarningCode.NO_KEY in {w.code for w in collection.warnings}


def test_genres_tries_et_dedoublonnes(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="5" Name="T" Artist="A" AverageBpm="180" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* Uptempo / CARREMENT VNR */"/>'
        '<TRACK TrackID="6" Name="T" Artist="A" AverageBpm="190" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* uptempo / Hardcore / CALME */"/>',
    )
    collection = read_collection(chemin, load_config())
    # « uptempo » et « Uptempo » sont le même genre : la première casse rencontrée gagne.
    assert collection.genres == ("Hardcore", "Uptempo")
    assert collection.bpm_range == (180.0, 190.0)


def test_bpm_illisible_donne_zero(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="7" Name="T" Artist="A" AverageBpm="" Tonality="Am"'
        ' TotalTime="" Location="file://x" Comments="/* Hardcore / CARREMENT VNR */"/>',
    )
    collection = read_collection(chemin, load_config())
    assert collection.tracks[0].bpm == 0.0
    assert collection.tracks[0].duration_s == 0


def test_track_id_absent_ignore_et_signale(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK Name="Sans id" Artist="Anonyme" AverageBpm="180" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore / CARREMENT VNR */"/>'
        '<TRACK TrackID="9" Name="Avec id" Artist="B" AverageBpm="140" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* Hardcore / CALME */"/>',
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


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="test non applicable quand exécuté en root : chmod ne bloque pas la lecture",
)
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
    """La fixture est fabriquée à la main : c'est `collection_reelle.xml`, et non
    celle-ci, qui atteste du format d'un export Rekordbox. Ce test atteste
    seulement que le lecteur traite de bout en bout une collection complète
    couvrant tous les cas déjà testés unitairement (un mood, plusieurs moods,
    aucun mood, tonalité illisible, plusieurs genres, etc.) sans lever
    d'exception et en produisant des résultats cohérents.
    """
    collection = read_collection(FIXTURE, load_config())
    assert len(collection.tracks) >= 8
    assert any(t.mood is not None and t.genres for t in collection.tracks)
    assert collection.genres


# --- Enfants du nœud TRACK ------------------------------------------------

def test_enfants_du_noeud_track_conserves(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="1" Name="T" Artist="A" AverageBpm="160" Tonality="Am"'
        ' TotalTime="300" Location="file://x" Comments="/* Hardcore / CARREMENT VNR */">'
        '<TEMPO Inizio="0.025" Bpm="160.00" Metro="4/4" Battito="1"/>'
        '<POSITION_MARK Name="Drop" Type="0" Start="90.025" Num="0"/>'
        '</TRACK>',
    )
    track = read_collection(chemin, load_config()).tracks[0]
    assert len(track.raw_children) == 2
    assert "TEMPO" in track.raw_children[0]
    assert "POSITION_MARK" in track.raw_children[1]


def test_track_sans_enfant_na_pas_denfant(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="1" Name="T" Artist="A" AverageBpm="160" Tonality="Am"'
        ' TotalTime="300" Location="file://x" Comments="/* Hardcore / CARREMENT VNR */"/>',
    )
    assert read_collection(chemin, load_config()).tracks[0].raw_children == ()


def test_la_fixture_porte_un_morceau_avec_beatgrid_et_reperes():
    collection = read_collection(FIXTURE, load_config())
    track = next(t for t in collection.tracks if t.id == "11")
    assert sum("TEMPO" in enfant for enfant in track.raw_children) == 2
    assert sum("POSITION_MARK" in enfant for enfant in track.raw_children) == 2


# --- Classement des tags en genres, moods, plages de BPM et tags ignorés ---
#
# Le XML ne transporte pas la catégorie d'un My Tag. Le lecteur la déduit donc
# par élimination : ce qui est un mood est un mood, ce qui est déclaré ignoré
# dans la configuration est ignoré, ce qui a la forme d'une plage de BPM est
# ignoré aussi — et **tout le reste est un genre**. Un genre ajouté dans
# Rekordbox apparaît ainsi sans toucher à la configuration.

REELLE = Path(__file__).parent / "fixtures" / "collection_reelle.xml"


def lire_reelle() -> dict[str, object]:
    collection = read_collection(REELLE, load_config())
    return {track.id: track for track in collection.tracks}


def test_plage_de_bpm_nest_pas_un_genre(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="1" Name="T" Artist="A" AverageBpm="175" Tonality="Am"'
        ' TotalTime="200" Location="file://x"'
        ' Comments="/* GABBER / 170-180 / 195+ / UN PEU VNR */"/>',
    )
    track = read_collection(chemin, load_config()).tracks[0]
    assert track.genres == ("GABBER",)


def test_tag_detat_nest_pas_un_genre(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="1" Name="T" Artist="A" AverageBpm="175" Tonality="Am"'
        ' TotalTime="200" Location="file://x"'
        ' Comments="/* GABBER / BEAT GRID CHECKED / OPENER / UN PEU VNR */"/>',
    )
    track = read_collection(chemin, load_config()).tracks[0]
    assert track.genres == ("GABBER",)


def test_un_nombre_seul_reste_un_genre(tmp_path):
    """Seule la *forme* d'une plage (`140-150`, `195+`) est écartée.

    Un tag numérique qui n'est pas une plage n'a aucune raison d'être traité
    comme un reliquat de la catégorie BPM.
    """
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="1" Name="T" Artist="A" AverageBpm="175" Tonality="Am"'
        ' TotalTime="200" Location="file://x" Comments="/* 2000 / UN PEU VNR */"/>',
    )
    assert read_collection(chemin, load_config()).tracks[0].genres == ("2000",)


def test_moods_multiples_moyennes_et_conserves(tmp_path):
    """Un morceau à deux moods reste jouable : son énergie est leur moyenne."""
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="1" Name="T" Artist="A" AverageBpm="175" Tonality="Am"'
        ' TotalTime="200" Location="file://x"'
        ' Comments="/* GABBER / DANSANT / UN PEU VNR */"/>',
    )
    collection = read_collection(chemin, load_config())
    track = collection.tracks[0]
    assert track.moods == (2, 3)
    assert track.mood == 2.5
    # Toujours signalé — ce n'est plus une exclusion, c'est une information.
    assert WarningCode.MULTIPLE_MOODS in {w.code for w in collection.warnings}


def test_mood_en_double_compte_une_fois(tmp_path):
    chemin = ecrire_xml(
        tmp_path,
        '<TRACK TrackID="1" Name="T" Artist="A" AverageBpm="175" Tonality="Am"'
        ' TotalTime="200" Location="file://x"'
        ' Comments="/* GABBER / DANSANT / DANSANT */"/>',
    )
    collection = read_collection(chemin, load_config())
    assert collection.tracks[0].moods == (2,)
    assert WarningCode.MULTIPLE_MOODS not in {w.code for w in collection.warnings}


# --- Lecture d'un extrait d'export réel -----------------------------------

def test_extrait_reel_mood_unique():
    track = lire_reelle()["238609622"]
    assert track.moods == (3,)
    assert track.mood == 3.0
    assert track.genres == ("FRAPCORE", "MELODIC HARDCORE", "EXPERIMENTAL HARDCORE")


def test_extrait_reel_mood_double():
    track = lire_reelle()["195918841"]
    assert track.moods == (2, 3)
    assert track.mood == 2.5
    assert track.genres == ("AMBIENT TECHNO", "TRANCE", "HARDTRANCE")


def test_extrait_reel_mood_triple():
    track = lire_reelle()["61643345"]
    assert track.moods == (2, 3, 4)
    assert track.mood == 3.0
    assert track.genres == ("FRAPCORE", "NEW HARDCORE")


def test_extrait_reel_tags_detat_et_plages_ecartes():
    pistes = lire_reelle()
    assert pistes["114701038"].genres == (
        "NEW HARDCORE", "EXPERIMENTAL HARDCORE", "DRUM AND BASS",
    )
    assert pistes["68056539"].genres == ("NEW HARDCORE",)
    assert pistes["63684875"].genres == ("FRAPCORE", "EXPERIMENTAL HARDCORE")


def test_extrait_reel_morceau_sans_genre_garde_son_mood():
    track = lire_reelle()["261205190"]
    assert track.genres == ()
    assert track.moods == (3,)


def test_extrait_reel_morceau_sans_aucun_tag():
    track = lire_reelle()["228493434"]
    assert track.genres == ()
    assert track.moods == ()
    assert track.mood is None


def test_extrait_reel_genres_de_la_collection():
    """La liste des genres ne contient aucune plage de BPM ni tag d'état."""
    genres = read_collection(REELLE, load_config()).genres
    assert "170-180" not in genres
    assert "BEAT GRID CHECKED" not in genres
    assert "OPENER" not in genres
    assert "UN PEU VNR" not in genres
    assert "FRAPCORE" in genres
