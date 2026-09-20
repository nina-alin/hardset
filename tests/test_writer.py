"""Tests de l'export XML : structure DJ_PLAYLISTS et intégrité des références."""

from datetime import date
from xml.etree import ElementTree

from hardset.model import SetRequest, Track
from hardset.rekordbox.writer import build_playlist_xml, default_playlist_name


def piste(id_: str, **extra) -> Track:
    attrs = {
        "TrackID": id_,
        "Name": f"Titre {id_}",
        "Artist": f"Artiste {id_}",
        "AverageBpm": "180.00",
        "Tonality": "Am",
        "TotalTime": "200",
        "Location": f"file://localhost/{id_}.mp3",
        "Comments": "/* Hardcore / vénère */",
        "Kind": "MP3 File",
    }
    attrs.update(extra)
    return Track(
        id=id_,
        artist=attrs["Artist"],
        title=attrs["Name"],
        bpm=180.0,
        camelot="8A",
        duration_s=200,
        location=attrs["Location"],
        genres=("Hardcore",),
        mood=4,
        raw_attrs=attrs,
    )


# --- Structure du fichier -------------------------------------------------

def test_xml_bien_forme_et_structure_attendue():
    xml = build_playlist_xml([piste("1"), piste("2")], "Mon set")
    racine = ElementTree.fromstring(xml)

    assert racine.tag == "DJ_PLAYLISTS"
    assert racine.get("Version") == "1.0.0"
    assert racine.find("PRODUCT").get("Name") == "rekordbox"

    collection = racine.find("COLLECTION")
    assert collection.get("Entries") == "2"

    noeud_racine = racine.find("PLAYLISTS/NODE")
    assert noeud_racine.get("Type") == "0"
    assert noeud_racine.get("Name") == "ROOT"
    assert noeud_racine.get("Count") == "1"

    playlist = noeud_racine.find("NODE")
    assert playlist.get("Name") == "Mon set"
    assert playlist.get("Type") == "1"
    assert playlist.get("KeyType") == "0"
    assert playlist.get("Entries") == "2"


def test_declaration_xml_presente():
    xml = build_playlist_xml([piste("1")], "S")
    assert xml.startswith(b"<?xml")


def test_declaration_xml_en_guillemets_doubles():
    # `ElementTree.write(xml_declaration=True)` produit des guillemets simples ;
    # on écrit la déclaration nous-mêmes pour rester au plus près des fichiers XML
    # du monde réel (guillemets doubles), faute de pouvoir tester le parseur de
    # Rekordbox avant la tâche 12.
    xml = build_playlist_xml([piste("1")], "S")
    premiere_ligne = xml.split(b"\n", 1)[0]
    assert premiere_ligne == b'<?xml version="1.0" encoding="UTF-8"?>'


# --- Intégrité des références --------------------------------------------

def test_chaque_cle_de_playlist_existe_dans_collection():
    xml = build_playlist_xml([piste("1"), piste("2"), piste("3")], "S")
    racine = ElementTree.fromstring(xml)

    ids_collection = {t.get("TrackID") for t in racine.findall("COLLECTION/TRACK")}
    cles = [t.get("Key") for t in racine.findall("PLAYLISTS/NODE/NODE/TRACK")]

    assert cles == ["1", "2", "3"]          # l'ordre de jeu est conservé
    assert set(cles) <= ids_collection


def test_attributs_dorigine_recopies_sans_perte():
    track = piste("1", CustomAttr="valeur", Rating="255")
    xml = build_playlist_xml([track], "S")
    noeud = ElementTree.fromstring(xml).find("COLLECTION/TRACK")

    for cle, valeur in track.raw_attrs.items():
        assert noeud.get(cle) == valeur


def test_raw_attrs_vide_utilise_le_repli_construit_depuis_track():
    # Quand `raw_attrs` est vide, le TRACK est reconstruit depuis les champs
    # typés de `Track` (pas de Tonality, Comments ou autre attribut d'origine :
    # ils n'existent pas en dehors de `raw_attrs`).
    track = Track(
        id="1",
        artist="Art",
        title="Tit",
        bpm=180.0,
        camelot="8A",
        duration_s=200,
        location="file://x.mp3",
        genres=("Hardcore",),
        mood=4,
        raw_attrs={},
    )
    xml = build_playlist_xml([track], "S")
    noeud = ElementTree.fromstring(xml).find("COLLECTION/TRACK")

    assert noeud.attrib == {
        "TrackID": "1",
        "Name": "Tit",
        "Artist": "Art",
        "AverageBpm": "180.00",
        "TotalTime": "200",
        "Location": "file://x.mp3",
    }


def test_un_morceau_place_deux_fois_napparait_quune_fois_dans_collection():
    # Ne doit pas arriver (le séquençage l'interdit), mais le fichier doit rester valide.
    track = piste("1")
    racine = ElementTree.fromstring(build_playlist_xml([track, track], "S"))
    assert len(racine.findall("COLLECTION/TRACK")) == 1
    assert racine.find("COLLECTION").get("Entries") == "1"
    assert len(racine.findall("PLAYLISTS/NODE/NODE/TRACK")) == 2
    assert racine.find("PLAYLISTS/NODE/NODE").get("Entries") == "2"


def test_set_vide():
    racine = ElementTree.fromstring(build_playlist_xml([], "S"))
    assert racine.find("COLLECTION").get("Entries") == "0"
    assert racine.findall("PLAYLISTS/NODE/NODE/TRACK") == []


def test_caracteres_speciaux_echappes():
    xml = build_playlist_xml([piste("1", Name='Titre "AT&T" <x>')], 'Set & "co"')
    racine = ElementTree.fromstring(xml)   # échouerait si l'échappement était absent
    assert racine.find("PLAYLISTS/NODE/NODE").get("Name") == 'Set & "co"'
    assert racine.find("COLLECTION/TRACK").get("Name") == 'Titre "AT&T" <x>'


# --- Nom de playlist par défaut ------------------------------------------

def requete(**kwargs) -> SetRequest:
    base = dict(
        genres=frozenset(),
        moods=frozenset(),
        bpm_min=150.0,
        bpm_max=200.0,
        profile="montee",
        duration_min=90,
    )
    base.update(kwargs)
    return SetRequest(**base)


def test_nom_par_defaut_avec_genres():
    nom = default_playlist_name(
        requete(genres=frozenset({"Uptempo", "Hardcore"})), date(2026, 9, 18)
    )
    assert nom == "hardcore-uptempo-montee-90min-2026-09-18"


def test_nom_par_defaut_sans_genre():
    assert default_playlist_name(requete(), date(2026, 9, 18)) == "tous-montee-90min-2026-09-18"


def test_nom_par_defaut_assainit_les_genres():
    nom = default_playlist_name(requete(genres=frozenset({"Vénère Core"})), date(2026, 9, 18))
    assert nom == "venere-core-montee-90min-2026-09-18"


def test_nom_par_defaut_avec_une_longue_liste_de_genres():
    nom = default_playlist_name(
        requete(
            genres=frozenset(
                {"Hardcore", "Uptempo", "Rawstyle", "Frenchcore", "Speedcore"}
            )
        ),
        date(2026, 9, 18),
    )
    assert nom == "frenchcore-hardcore-rawstyle-speedcore-uptempo-montee-90min-2026-09-18"


def test_nom_par_defaut_avec_un_genre_vide():
    # Observé : une chaîne de genre vide s'assainit en chaîne vide, ce qui laisse
    # un tiret de tête dans le nom produit — comportement actuel, pas un choix
    # délibéré, mais rien n'indique qu'il soit faux : ce cas ne devrait pas se
    # présenter en pratique (le formulaire ne propose pas de genre vide).
    nom = default_playlist_name(requete(genres=frozenset({""})), date(2026, 9, 18))
    assert nom == "-montee-90min-2026-09-18"


def test_nom_par_defaut_sans_date_utilise_la_date_du_jour():
    nom = default_playlist_name(requete())
    assert nom == f"tous-montee-90min-{date.today().isoformat()}"
