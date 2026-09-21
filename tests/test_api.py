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
MOODS = ("CALME", "DANSANT", "UN PEU VNR", "CARREMENT VNR", "C DU BRUIT")


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
    assert donnees["moods"][0] == {"value": 1, "label": "CALME"}
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
    assert set(premier) == {"id", "artist", "title", "bpm", "camelot", "mood", "moods", "genres"}
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


# --- Survie de l'avertissement de pénurie aux remplacements ---------------
# Le moteur préserve délibérément la pénurie de `generate` à travers les
# remplacements (`_sans_avertissements_de_remplacement`). La route de
# remplacement reconstruit le set courant : elle doit donc recalculer cet
# avertissement, et non le perdre ni le faire reporter par le navigateur.

def test_penurie_de_generate_survit_a_un_remplacement_reussi(client, collection_xml):
    genere = client.post("/api/generate", json=corps(collection_xml, duration_min=600)).json()
    assert "shortage" in [w["code"] for w in genere["warnings"]]

    # Quelques lignes supprimées dans la page : il reste des remplaçants
    # disponibles, le remplacement réussit.
    ids = [t["id"] for t in genere["tracks"]][:30]
    donnees = client.post(
        "/api/replace",
        json=corps(collection_xml, duration_min=600, track_ids=ids, position=0),
    ).json()

    assert donnees["tracks"][0]["id"] != ids[0]
    assert "shortage" in [w["code"] for w in donnees["warnings"]]


def test_penurie_de_generate_survit_a_un_remplacement_impossible(client, collection_xml):
    genere = client.post("/api/generate", json=corps(collection_xml, duration_min=600)).json()
    ids = [t["id"] for t in genere["tracks"]]

    # Sans suppression, la pénurie a consommé toute la collection : plus aucun
    # remplaçant. Les deux avertissements doivent coexister.
    donnees = client.post(
        "/api/replace",
        json=corps(collection_xml, duration_min=600, track_ids=ids, position=0),
    ).json()

    codes = [w["code"] for w in donnees["warnings"]]
    assert "shortage" in codes
    assert "replacement_shortage" in codes


def test_pas_de_penurie_inventee_par_le_remplacement(client, collection_xml):
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]]
    donnees = client.post(
        "/api/replace", json=corps(collection_xml, track_ids=ids, position=2)
    ).json()
    assert "shortage" not in [w["code"] for w in donnees["warnings"]]


# --- Recalcul des cibles (propriété du serveur) ---------------------------
# La forme de la courbe d'énergie est de la logique musicale : elle appartient
# au serveur. Après une suppression de ligne, la page redemande les cibles pour
# la nouvelle longueur au lieu de tronquer les siennes.

def test_cibles_redistribuees_sur_la_longueur_demandee(client, collection_xml):
    donnees = client.post("/api/targets", json=corps(collection_xml, count=5)).json()
    bpms = [c["bpm"] for c in donnees["targets"]]
    assert len(bpms) == 5
    assert [c["position"] for c in donnees["targets"]] == list(range(5))
    # Redistribuées, pas tronquées : la courbe couvre toujours toute la plage.
    assert bpms[0] == pytest.approx(150.0)
    assert bpms[-1] == pytest.approx(200.0)


def test_cibles_identiques_a_celles_dun_remplacement_de_meme_longueur(client, collection_xml):
    # Un seul propriétaire : ce que rend `/api/targets` après une suppression
    # doit être exactement ce que `/api/replace` imposera au coup suivant.
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]][:5]

    remplace = client.post(
        "/api/replace", json=corps(collection_xml, track_ids=ids, position=0)
    ).json()
    cibles = client.post("/api/targets", json=corps(collection_xml, count=5)).json()

    assert cibles["targets"] == remplace["targets"]


def test_cibles_pour_un_set_vide(client, collection_xml):
    donnees = client.post("/api/targets", json=corps(collection_xml, count=0)).json()
    assert donnees["targets"] == []


def test_cibles_longueur_negative_renvoie_400(client, collection_xml):
    reponse = client.post("/api/targets", json=corps(collection_xml, count=-1))
    assert reponse.status_code == 400


def test_cibles_longueur_excessive_renvoie_400(client, collection_xml):
    # `count` pilote une boucle non bornée : sans plafond, une faute de frappe
    # ou une régression du JavaScript fige le serveur (mesuré : count=2000000
    # rend un 200 en 5,7 s pour 141 Mo de réponse). Toutes les autres routes
    # sont de fait bornées par la taille de la collection ; celle-ci ne doit
    # pas rester la seule sans limite.
    reponse = client.post("/api/targets", json=corps(collection_xml, count=2_000_000))
    assert reponse.status_code == 400
    assert "count" in reponse.json()["detail"]


def test_cibles_profil_inconnu_message_identique_a_la_generation(client, collection_xml):
    reponse_generation = client.post(
        "/api/generate", json=corps(collection_xml, profile="inexistant")
    )
    reponse_cibles = client.post(
        "/api/targets", json=corps(collection_xml, count=5, profile="inexistant")
    )
    assert reponse_cibles.status_code == 400
    assert reponse_cibles.json()["detail"] == reponse_generation.json()["detail"]


# --- Échelle de mood bornée sur la configuration --------------------------
# `load_config` accepte une échelle plus courte que la constante `MOOD_MAX` :
# avec trois moods configurés, `mood=5` n'existe pas. L'accepter rendait un set
# vide indistinguable d'une pénurie — exactement ce que la validation ajoutée
# en tâche 10 voulait empêcher.

CONFIG_TROIS_MOODS = replace(CONFIG, moods=("calme", "dansant", "vénère"))


@pytest.fixture
def client_trois_moods() -> TestClient:
    return TestClient(create_app(CONFIG_TROIS_MOODS))


def test_mood_hors_de_lechelle_configuree_renvoie_400(client_trois_moods, collection_xml):
    reponse = client_trois_moods.post("/api/generate", json=corps(collection_xml, moods=[5]))
    assert reponse.status_code == 400
    assert "mood" in reponse.json()["detail"]
    assert "3" in reponse.json()["detail"]


def test_dernier_mood_de_lechelle_configuree_accepte(client_trois_moods, collection_xml):
    reponse = client_trois_moods.post("/api/generate", json=corps(collection_xml, moods=[3]))
    assert reponse.status_code == 200


def test_cible_de_mood_ne_vise_pas_un_niveau_inexistant(client_trois_moods, collection_xml):
    # Sans mood demandé, la courbe balaie toute l'échelle : celle qui est
    # configurée, pas celle de la constante.
    donnees = client_trois_moods.post("/api/generate", json=corps(collection_xml)).json()
    assert max(c["mood"] for c in donnees["targets"]) <= 3.0


def test_cibles_de_mood_bornees_aussi_sur_la_route_des_cibles(
    client_trois_moods, collection_xml
):
    donnees = client_trois_moods.post(
        "/api/targets", json=corps(collection_xml, count=6)
    ).json()
    assert max(c["mood"] for c in donnees["targets"]) <= 3.0


# --- Recherche de morceaux ------------------------------------------------

def test_recherche_par_titre(client, collection_xml):
    # « 7 » est cherché comme un fragment, pas comme un mot entier : 17, 27 et
    # 37 en contiennent un aussi, et l'ordre est celui de la collection.
    donnees = client.post(
        "/api/tracks", json={"path": str(collection_xml), "q": "titre 7"}
    ).json()
    assert [t["id"] for t in donnees["tracks"]] == ["7", "17", "27", "37"]
    assert donnees["truncated"] is False


def test_recherche_sur_plusieurs_mots(client, collection_xml):
    donnees = client.post(
        "/api/tracks", json={"path": str(collection_xml), "q": "artiste 12"}
    ).json()
    assert [t["id"] for t in donnees["tracks"]] == ["12"]


def test_recherche_vide_ne_rend_rien(client, collection_xml):
    donnees = client.post("/api/tracks", json={"path": str(collection_xml), "q": ""}).json()
    assert donnees == {"tracks": [], "truncated": False}


def test_recherche_plafonnee_et_signalee(client, collection_xml):
    donnees = client.post(
        "/api/tracks", json={"path": str(collection_xml), "q": "titre", "limit": 5}
    ).json()
    assert len(donnees["tracks"]) == 5
    assert donnees["truncated"] is True


def test_le_plafond_de_recherche_est_borne(client, collection_xml):
    # 1000 demandés, 100 au maximum servis — et la fixture n'en a que 40.
    donnees = client.post(
        "/api/tracks", json={"path": str(collection_xml), "q": "titre", "limit": 1000}
    ).json()
    assert len(donnees["tracks"]) == 40


def test_la_recherche_rend_de_quoi_afficher_le_morceau(client, collection_xml):
    donnees = client.post(
        "/api/tracks", json={"path": str(collection_xml), "q": "titre 10"}
    ).json()
    assert donnees["tracks"][0]["bpm"] == 160.0
    assert donnees["tracks"][0]["camelot"] == "8A"


def test_la_recherche_signale_une_collection_illisible(client, tmp_path):
    reponse = client.post(
        "/api/tracks", json={"path": str(tmp_path / "absent.xml"), "q": "titre"}
    )
    assert reponse.status_code == 400


# --- Sons épinglés --------------------------------------------------------

def test_le_son_de_depart_ouvre_le_set_et_impose_la_borne(client, collection_xml):
    donnees = client.post(
        "/api/generate", json=corps(collection_xml, start_track_id="10")
    ).json()
    assert donnees["tracks"][0]["id"] == "10"
    assert min(t["bpm"] for t in donnees["tracks"]) == 160.0


def test_le_son_de_fin_ferme_le_set_et_impose_la_borne(client, collection_xml):
    donnees = client.post(
        "/api/generate", json=corps(collection_xml, end_track_id="30")
    ).json()
    assert donnees["tracks"][-1]["id"] == "30"
    assert max(t["bpm"] for t in donnees["tracks"]) == 180.0


def test_un_epingle_hors_criteres_est_signale(client, collection_xml):
    # Le morceau 10 est CALME (mood 1) ; le set ne demande que le mood 5.
    donnees = client.post(
        "/api/generate", json=corps(collection_xml, start_track_id="10", moods=[5])
    ).json()
    assert donnees["tracks"][0]["id"] == "10"
    assert "pin_off_filters" in {w["code"] for w in donnees["warnings"]}


def test_un_epingle_inconnu_est_refuse(client, collection_xml):
    reponse = client.post(
        "/api/generate", json=corps(collection_xml, start_track_id="999")
    )
    assert reponse.status_code == 400
    assert "absent de la collection" in reponse.json()["detail"]


def test_le_meme_morceau_des_deux_cotes_est_refuse(client, collection_xml):
    reponse = client.post(
        "/api/generate", json=corps(collection_xml, start_track_id="10", end_track_id="10")
    )
    assert reponse.status_code == 400
    assert "à la fois" in reponse.json()["detail"]


def test_un_set_descendant_est_refuse(client, collection_xml):
    reponse = client.post(
        "/api/generate", json=corps(collection_xml, start_track_id="30", end_track_id="10")
    )
    assert reponse.status_code == 400
    detail = reponse.json()["detail"]
    assert "plus lent" in detail and "180" in detail and "160" in detail


def test_un_depart_au_dela_du_bpm_max_demande_est_refuse(client, collection_xml):
    reponse = client.post(
        "/api/generate", json=corps(collection_xml, start_track_id="30", bpm_max=170.0)
    )
    assert reponse.status_code == 400
    assert "dépasse le BPM max" in reponse.json()["detail"]


def test_les_cibles_suivent_la_borne_imposee(client, collection_xml):
    donnees = client.post(
        "/api/targets", json=corps(collection_xml, count=5, start_track_id="10")
    ).json()
    assert donnees["targets"][0]["bpm"] == 160.0


def test_les_cibles_sans_epinglage_n_ouvrent_pas_la_collection(client, tmp_path):
    # Propriété que la docstring de la route défend : sans épinglage, les cibles
    # ne dépendent pas de la collection, et un chemin illisible n'empêche rien.
    donnees = client.post(
        "/api/targets", json=corps(tmp_path / "absent.xml", count=3)
    ).json()
    assert len(donnees["targets"]) == 3


def test_les_cibles_avec_un_epingle_introuvable_sont_refusees(client, collection_xml):
    reponse = client.post(
        "/api/targets", json=corps(collection_xml, count=3, start_track_id="999")
    )
    assert reponse.status_code == 400


def test_le_remplacement_respecte_la_borne_imposee(client, collection_xml):
    jeu = client.post(
        "/api/generate", json=corps(collection_xml, start_track_id="10")
    ).json()
    ids = [t["id"] for t in jeu["tracks"]]
    donnees = client.post(
        "/api/replace",
        json=corps(collection_xml, start_track_id="10", track_ids=ids, position=1),
    ).json()
    assert donnees["tracks"][1]["bpm"] >= 160.0


def test_les_cibles_du_remplacement_suivent_la_borne_imposee(client, collection_xml):
    # Contrairement au test précédent (plancher venant du filtrage du vivier
    # par `replace_at`), celui-ci porte sur la courbe elle-même : les cibles
    # rendues par `/api/replace` doivent être celles de la demande accordée au
    # son épinglé, pas de la demande brute — sans quoi la courbe affichée
    # cesserait de correspondre à celle que le remplacement vise.
    jeu = client.post(
        "/api/generate", json=corps(collection_xml, start_track_id="10")
    ).json()
    ids = [t["id"] for t in jeu["tracks"]]
    donnees = client.post(
        "/api/replace",
        json=corps(collection_xml, start_track_id="10", track_ids=ids, position=1),
    ).json()
    assert donnees["targets"][0]["bpm"] == 160.0
