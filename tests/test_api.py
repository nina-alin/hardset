"""Tests des routes de l'API. La page elle-même n'est pas testée (spec §12)."""

import os
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from hardset.config import load_config
from hardset.web.app import create_app

CONFIG = load_config()

# Les cinq moods de la configuration livrée, pour tagger la collection de test.
MOODS = ("calme", "dansant", "un peu vénère", "vénère", "c'est du bruit")


@pytest.fixture
def collection_xml(tmp_path: Path) -> Path:
    noeuds = "".join(
        f'<TRACK TrackID="{i}" Name="Titre {i}" Artist="Artiste {i}"'
        f' AverageBpm="{150 + i}.00" Tonality="Am" TotalTime="200"'
        f' Location="file://localhost/{i}.mp3"'
        f' Comments="/* Hardcore / {MOODS[i % 5]} */"/>'
        for i in range(40)
    )
    chemin = tmp_path / "collection.xml"
    chemin.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<DJ_PLAYLISTS Version="1.0.0">'
        '<PRODUCT Name="rekordbox" Version="6.0.0" Company="AlphaTheta"/>'
        f'<COLLECTION Entries="40">{noeuds}</COLLECTION>'
        '<PLAYLISTS/></DJ_PLAYLISTS>',
        encoding="utf-8",
    )
    return chemin


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(CONFIG))


def corps(chemin: Path, **kwargs) -> dict:
    base = {
        "path": str(chemin),
        "genres": [],
        "moods": [],
        "bpm_min": 150.0,
        "bpm_max": 200.0,
        "profile": "montee",
        "duration_min": 20,
        "seconds_per_track": 120,
    }
    base.update(kwargs)
    return base


# --- Configuration et page -----------------------------------------------

def test_page_servie(client):
    reponse = client.get("/")
    assert reponse.status_code == 200
    assert "text/html" in reponse.headers["content-type"]


def test_config_expose_profils_et_moods(client):
    donnees = client.get("/api/config").json()
    assert [p["key"] for p in donnees["profils"]] == ["montee", "warmup-long", "plateau", "vagues"]
    assert donnees["moods"][0] == {"value": 1, "label": "calme"}
    assert len(donnees["moods"]) == 5


def test_config_expose_seconds_per_track_de_la_configuration():
    # Point tranché : la valeur vient de `config.seconds_per_track`, pas d'un
    # littéral codé dans la route — une configuration différente de la
    # collection de test doit se refléter dans la réponse.
    config = replace(CONFIG, seconds_per_track=90)
    client_local = TestClient(create_app(config))
    donnees = client_local.get("/api/config").json()
    assert donnees["seconds_per_track"] == 90


# --- Lecture de collection -----------------------------------------------

def test_collection_renvoie_genres_et_plage_bpm(client, collection_xml):
    donnees = client.post("/api/collection", json={"path": str(collection_xml)}).json()
    assert donnees["track_count"] == 40
    assert donnees["genres"] == ["Hardcore"]
    assert donnees["bpm_min"] == 150.0
    assert donnees["bpm_max"] == 189.0


def test_collection_introuvable_renvoie_400(client, tmp_path):
    reponse = client.post("/api/collection", json={"path": str(tmp_path / "rien.xml")})
    assert reponse.status_code == 400
    assert "introuvable" in reponse.json()["detail"]


def test_collection_chemin_avec_octet_nul_renvoie_400(client):
    # Un octet NUL dans le chemin fait lever un `ValueError` natif de `pathlib`
    # (« embedded null byte »), pas un `OSError` : sans interception dédiée,
    # il remontait en 500 brut jusqu'à Starlette.
    reponse = client.post("/api/collection", json={"path": "foo\x00bar"})
    assert reponse.status_code == 400
    assert "chemin invalide" in reponse.json()["detail"]


def test_collection_repertoire_renvoie_400(client, tmp_path):
    # Se tromper de champ dans le formulaire et pointer vers un dossier plutôt
    # qu'un fichier est une erreur ordinaire : elle doit produire un 400 clair.
    reponse = client.post("/api/collection", json={"path": str(tmp_path)})
    assert reponse.status_code == 400


def test_collection_xml_mal_forme_renvoie_400(client, tmp_path):
    # Se tromper de fichier (un XML tronqué ou invalide) est tout aussi
    # ordinaire ; le lecteur le convertit déjà en erreur exploitable.
    chemin = tmp_path / "invalide.xml"
    chemin.write_text("<DJ_PLAYLISTS><COLLECTION>", encoding="utf-8")
    reponse = client.post("/api/collection", json={"path": str(chemin)})
    assert reponse.status_code == 400


# --- Génération ----------------------------------------------------------

def test_generation(client, collection_xml):
    donnees = client.post("/api/generate", json=corps(collection_xml)).json()
    assert len(donnees["tracks"]) == 10
    assert len(donnees["targets"]) == 10
    premier = donnees["tracks"][0]
    assert set(premier) == {"id", "artist", "title", "bpm", "camelot", "mood", "genres"}
    assert donnees["playlist_name"].endswith("min-" + donnees["date"])
    assert isinstance(donnees["warnings"], list)


def test_generation_signale_la_penurie(client, collection_xml):
    donnees = client.post("/api/generate", json=corps(collection_xml, duration_min=600)).json()
    codes = [w["code"] for w in donnees["warnings"]]
    assert "shortage" in codes
    assert len(donnees["tracks"]) < 300


def test_profil_inconnu_renvoie_400(client, collection_xml):
    reponse = client.post("/api/generate", json=corps(collection_xml, profile="inexistant"))
    assert reponse.status_code == 400


# --- Validation de la requête (point tranché) -----------------------------
# Une requête invalide est refusée avec un 400 explicite, et ne doit jamais
# traverser silencieusement le moteur pour produire un set vide indistinguable
# d'une pénurie.

def test_mood_hors_echelle_renvoie_400(client, collection_xml):
    reponse = client.post("/api/generate", json=corps(collection_xml, moods=[7]))
    assert reponse.status_code == 400
    assert "mood" in reponse.json()["detail"]


def test_bpm_min_superieur_a_bpm_max_renvoie_400(client, collection_xml):
    reponse = client.post(
        "/api/generate", json=corps(collection_xml, bpm_min=200.0, bpm_max=150.0)
    )
    assert reponse.status_code == 400
    assert "bpm" in reponse.json()["detail"]


def test_duree_nulle_ou_negative_renvoie_400(client, collection_xml):
    reponse = client.post("/api/generate", json=corps(collection_xml, duration_min=0))
    assert reponse.status_code == 400
    assert "durée" in reponse.json()["detail"]

    reponse_negative = client.post("/api/generate", json=corps(collection_xml, duration_min=-5))
    assert reponse_negative.status_code == 400


def test_seconds_per_track_nul_ou_negatif_renvoie_400(client, collection_xml):
    reponse = client.post(
        "/api/generate", json=corps(collection_xml, seconds_per_track=0)
    )
    assert reponse.status_code == 400
    assert "seconds_per_track" in reponse.json()["detail"]

    reponse_negative = client.post(
        "/api/generate", json=corps(collection_xml, seconds_per_track=-10)
    )
    assert reponse_negative.status_code == 400


def test_requete_valide_avec_penurie_nest_pas_une_erreur(client, collection_xml):
    # Rappel : une requête valide qui manque de morceaux est une pénurie (200,
    # avertissement), jamais une erreur — à ne pas confondre avec les cas
    # ci-dessus.
    reponse = client.post("/api/generate", json=corps(collection_xml, duration_min=600))
    assert reponse.status_code == 200


# --- Remplacement --------------------------------------------------------

def test_remplacement_dune_position(client, collection_xml):
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]]

    donnees = client.post(
        "/api/replace",
        json=corps(collection_xml, track_ids=ids, position=3),
    ).json()

    nouveaux = [t["id"] for t in donnees["tracks"]]
    assert len(nouveaux) == len(ids)
    assert nouveaux[3] != ids[3]
    assert nouveaux[:3] == ids[:3]
    assert nouveaux[4:] == ids[4:]
    assert len(set(nouveaux)) == len(nouveaux)


def test_remplacement_apres_suppression_recalcule_les_cibles(client, collection_xml):
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]][:6]      # comme si 4 lignes étaient supprimées

    donnees = client.post(
        "/api/replace",
        json=corps(collection_xml, track_ids=ids, position=0),
    ).json()

    assert len(donnees["tracks"]) == 6
    assert len(donnees["targets"]) == 6


def test_remplacement_profil_inconnu_message_identique_a_la_generation(client, collection_xml):
    # Même faute (profil inexistant), même message que sur /api/generate : la
    # route de remplacement ne doit pas revalider le profil avec un message
    # moins informatif que celui du moteur.
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]]

    reponse_generation = client.post(
        "/api/generate", json=corps(collection_xml, profile="inexistant")
    )
    reponse_remplacement = client.post(
        "/api/replace",
        json=corps(collection_xml, track_ids=ids, position=0, profile="inexistant"),
    )

    assert reponse_remplacement.status_code == 400
    assert reponse_remplacement.json()["detail"] == reponse_generation.json()["detail"]
    assert "disponibles" in reponse_remplacement.json()["detail"]


def test_remplacement_position_invalide_renvoie_400(client, collection_xml):
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]]
    reponse = client.post("/api/replace", json=corps(collection_xml, track_ids=ids, position=99))
    assert reponse.status_code == 400


def test_remplacement_avec_id_inconnu_renvoie_400(client, collection_xml):
    # Rappel : un identifiant inconnu doit produire un 400 clair, pas une
    # `KeyError` remontée en 500.
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]]
    ids[0] = "9999"
    reponse = client.post("/api/replace", json=corps(collection_xml, track_ids=ids, position=1))
    assert reponse.status_code == 400


# --- Export --------------------------------------------------------------

def test_export_renvoie_un_xml_telechargeable(client, collection_xml):
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]]

    reponse = client.post(
        "/api/export",
        json={"path": str(collection_xml), "track_ids": ids, "playlist_name": "Mon set"},
    )

    assert reponse.status_code == 200
    assert reponse.headers["content-type"].startswith("application/xml")
    # Deux noms annoncés : un `filename` ASCII assaini et le nom complet en
    # UTF-8 percent-encodé (RFC 5987), cf. `_content_disposition`.
    disposition = reponse.headers["content-disposition"]
    assert 'filename="mon-set.xml"' in disposition
    assert "filename*=UTF-8''Mon%20set.xml" in disposition

    racine = ElementTree.fromstring(reponse.content)
    cles = [t.get("Key") for t in racine.findall("PLAYLISTS/NODE/NODE/TRACK")]
    assert cles == ids
    ids_collection = {t.get("TrackID") for t in racine.findall("COLLECTION/TRACK")}
    assert set(cles) <= ids_collection


def test_export_dun_id_inconnu_renvoie_400(client, collection_xml):
    reponse = client.post(
        "/api/export",
        json={"path": str(collection_xml), "track_ids": ["9999"], "playlist_name": "S"},
    )
    assert reponse.status_code == 400


# --- En-tête de téléchargement de l'export -------------------------------
# Starlette encode les en-têtes HTTP en latin-1 : un nom de playlist contenant
# un caractère hors de cette table (« œ », « € », un emoji) faisait lever une
# `UnicodeEncodeError` non interceptée, donc un 500, sur un nom français
# ordinaire (cœur, sœur, nœud). Le nom de fichier réellement vu par
# l'utilisatrice vient de l'attribut `download` du lien, côté JavaScript.

@pytest.mark.parametrize("nom", ["cœur", "Set 100€", "set 🔥"])
def test_export_avec_un_nom_hors_latin_1(client, collection_xml, nom):
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]]

    reponse = client.post(
        "/api/export",
        json={"path": str(collection_xml), "track_ids": ids, "playlist_name": nom},
    )

    assert reponse.status_code == 200
    disposition = reponse.headers["content-disposition"]
    disposition.encode("latin-1")            # échouerait avant la correction
    assert "filename*=UTF-8''" in disposition
    # Le nom complet reste transporté, percent-encodé selon la RFC 5987.
    assert quote(f"{nom}.xml", safe="") in disposition


def test_export_avec_un_nom_contenant_un_saut_de_ligne(client, collection_xml):
    # Un saut de ligne dans un en-tête est rejeté par le serveur HTTP réel
    # (découpage d'en-tête) : il ne doit jamais s'y retrouver tel quel.
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]]

    reponse = client.post(
        "/api/export",
        json={"path": str(collection_xml), "track_ids": ids, "playlist_name": "set\nmalin"},
    )

    assert reponse.status_code == 200
    disposition = reponse.headers["content-disposition"]
    assert "\n" not in disposition and "\r" not in disposition
    assert ElementTree.fromstring(reponse.content).find("PLAYLISTS/NODE/NODE").get("Name") == (
        "set\nmalin"
    )


def test_export_dun_nom_entierement_non_ascii_garde_un_filename_utilisable(
    client, collection_xml
):
    # « 🔥 » ne laisse aucun caractère ASCII : le `filename` de repli ne doit pas
    # être vide, sans quoi l'en-tête annoncerait un fichier sans nom.
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]]
    reponse = client.post(
        "/api/export",
        json={"path": str(collection_xml), "track_ids": ids, "playlist_name": "🔥"},
    )
    assert 'filename="set.xml"' in reponse.headers["content-disposition"]


# --- Message d'erreur de lecture -----------------------------------------

@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="test non applicable en root : chmod ne bloque pas la traversée",
)
def test_collection_sans_droit_daces_ne_dit_pas_introuvable(client, tmp_path):
    # `stat()` sur un fichier logé dans un répertoire non traversable lève une
    # `PermissionError` : le lecteur distingue déjà ce cas de l'absence, la
    # route doit le distinguer aussi.
    dossier = tmp_path / "prive"
    dossier.mkdir()
    chemin = dossier / "collection.xml"
    chemin.write_text("<DJ_PLAYLISTS/>", encoding="utf-8")
    dossier.chmod(0o000)
    try:
        reponse = client.post("/api/collection", json={"path": str(chemin)})
    finally:
        dossier.chmod(0o755)

    assert reponse.status_code == 400
    detail = reponse.json()["detail"]
    assert "introuvable" not in detail
    assert "lire" in detail
