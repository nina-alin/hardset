"""Chaîne complète sur la fixture la plus riche du dépôt.

`tests/fixtures/collection_extrait.xml` porte les cas tordus que les autres
tests n'exercent qu'un par un et sur des collections synthétiques : commentaire
libre en plus des tags, quatre notations de tonalité, morceau sans mood, morceau
à deux moods, beatgrid et points de repère. Elle n'était lue que par le lecteur.
Ici elle traverse tout : lecture → filtrage → séquençage → écriture du XML.

Rappel : cette fixture est fabriquée à la main (voir le commentaire en tête du
fichier). Rien ici n'atteste du format d'un export Rekordbox réel, ni qu'un
fichier produit se réimporte.
"""

from pathlib import Path
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from hardset.config import load_config
from hardset.web.app import create_app

CONFIG = load_config()
FIXTURE = Path(__file__).parent / "fixtures" / "collection_extrait.xml"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(CONFIG))


def corps(**kwargs) -> dict:
    base = {
        "path": str(FIXTURE),
        "genres": [],
        "moods": [],
        "bpm_min": 100.0,
        "bpm_max": 200.0,
        "profile": "montee",
        "duration_min": 10,
        "seconds_per_track": 120,
    }
    base.update(kwargs)
    return base


# --- Lecture de la fixture par l'API --------------------------------------

def test_la_collection_lue_signale_ses_cas_tordus(client):
    donnees = client.post("/api/collection", json={"path": str(FIXTURE)}).json()
    codes = {w["code"] for w in donnees["warnings"]}
    # Le morceau sans mood (Techno / Industrial), celui qui en porte deux
    # (dansant + vénère) et celui sans tonalité analysée.
    assert {"no_mood", "multiple_moods", "no_key"} <= codes
    assert donnees["bpm_min"] == 110.0
    assert donnees["bpm_max"] == 175.0
    assert "Hardcore" in donnees["genres"]


# --- Chaîne complète jusqu'au XML -----------------------------------------

def test_de_la_fixture_au_xml_produit(client):
    genere = client.post("/api/generate", json=corps()).json()
    ids = [t["id"] for t in genere["tracks"]]
    assert ids, "la fixture doit fournir au moins un morceau éligible"

    # Les morceaux sans mood unique n'arrivent jamais jusqu'au set.
    assert "2" not in ids and "3" not in ids

    reponse = client.post(
        "/api/export",
        json={"path": str(FIXTURE), "track_ids": ids, "playlist_name": "Set d'essai"},
    )
    assert reponse.status_code == 200

    racine = ElementTree.fromstring(reponse.content)
    assert [t.get("Key") for t in racine.findall("PLAYLISTS/NODE/NODE/TRACK")] == ids
    assert {t.get("TrackID") for t in racine.findall("COLLECTION/TRACK")} == set(ids)

    # Les attributs d'origine traversent la chaîne sans être réécrits : ils sont
    # comparés à ceux du fichier de départ, nœud par nœud.
    origine = {
        t.get("TrackID"): t.attrib
        for t in ElementTree.parse(FIXTURE).getroot().findall("./COLLECTION/TRACK")
    }
    for noeud in racine.findall("COLLECTION/TRACK"):
        assert noeud.attrib == origine[noeud.get("TrackID")]


def test_beatgrid_et_points_de_repere_traversent_toute_la_chaine(client):
    # « Hardcore » + mood « vénère » ne laisse que deux morceaux éligibles, dont
    # celui qui porte une beatgrid et des points de repère.
    demande = corps(genres=["Hardcore"], moods=[4], duration_min=4)
    genere = client.post("/api/generate", json=demande).json()
    ids = [t["id"] for t in genere["tracks"]]
    assert "11" in ids

    reponse = client.post(
        "/api/export",
        json={"path": str(FIXTURE), "track_ids": ids, "playlist_name": "Beatgrid"},
    )
    noeud = next(
        t
        for t in ElementTree.fromstring(reponse.content).findall("COLLECTION/TRACK")
        if t.get("TrackID") == "11"
    )

    attendu = next(
        t
        for t in ElementTree.parse(FIXTURE).getroot().findall("./COLLECTION/TRACK")
        if t.get("TrackID") == "11"
    )
    assert [e.tag for e in noeud] == [e.tag for e in attendu]
    assert [e.attrib for e in noeud] == [e.attrib for e in attendu]
