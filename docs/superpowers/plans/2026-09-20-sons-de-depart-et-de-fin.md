# Son de départ et son de fin choisis — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre de choisir, avant la génération, le morceau qui ouvre le set et celui qui le ferme, la plage de BPM demandée s'accordant automatiquement à leur tempo.

**Architecture:** Un module pur `hardset/engine/pinning.py` résout les morceaux épinglés et rend une `SetRequest` dont les bornes de BPM valent leur tempo ; `generate` les place en première et dernière position sans les noter. Un module pur `hardset/engine/search.py` cherche un morceau par artiste ou titre, exposé par une route `POST /api/tracks`. La page n'affiche que le résultat de ces décisions : elle recopie la borne imposée dans le champ et le verrouille, mais le serveur re-dérive toujours depuis l'id.

**Tech Stack:** Python 3.12+, FastAPI, pytest. Page unique HTML/CSS/JS sans dépendance ni outil de build.

**Spec :** `docs/superpowers/specs/2026-09-20-sons-de-depart-et-de-fin-design.md`

## Global Constraints

- **Langue :** tout le code, les commentaires, les docstrings, les messages d'erreur et les noms de tests sont en français, sauf les noms d'API publique du moteur qui restent en anglais (`resolve`, `search`, `generate`, `eligible`), comme le reste du dépôt.
- **Pureté du moteur :** `hardset/engine/` et `hardset/model.py` n'importent ni `yaml`, ni `fastapi`, ni `uvicorn`, ni `starlette`, et ne font aucune entrée/sortie. `tests/test_architecture.py::test_importer_le_moteur_ne_charge_ni_yaml_ni_fastapi` le vérifie.
- **Aucune logique musicale dans `hardset/web/`** : cette couche traduit des requêtes HTTP et sérialise des résultats.
- **Aucun test JavaScript** dans ce dépôt (hors périmètre acté du design initial) : la page se vérifie à la main, tâche 6.
- **Ne jamais écrire** qu'un XML produit par cet outil a été réimporté dans Rekordbox : ça n'a jamais été fait.
- **Commande de test :** `.venv/bin/pytest` depuis la racine. Base de départ : **317 tests passent**.
- **Commits :** un par tâche au minimum, message en français, préfixe `feat:` / `test:` / `fix:` comme dans l'historique.

---

### Task 1: `engine/pinning.py` — résoudre les épinglés et accorder les BPM

**Files:**
- Create: `hardset/engine/pinning.py`
- Modify: `hardset/model.py` (dataclass `SetRequest`)
- Test: `tests/test_pinning.py` (create)

**Interfaces:**
- Consumes: `hardset.model.SetRequest`, `hardset.model.Track`.
- Produces:
  - `SetRequest.start_track_id: str | None = None` et `SetRequest.end_track_id: str | None = None`
  - `hardset.engine.pinning.Pins` — dataclass figée, champs `start: Track | None = None`, `end: Track | None = None`, propriété `epingles: tuple[Track, ...]`
  - `hardset.engine.pinning.PinningError(Exception)`
  - `hardset.engine.pinning.resolve(tracks: Iterable[Track], request: SetRequest) -> tuple[SetRequest, Pins]`

- [ ] **Step 1: Écrire les tests, qui échouent**

Créer `tests/test_pinning.py` :

```python
"""Tests de l'épinglage : résolution des morceaux choisis et accord des BPM.

Le module étant pur, tous les cas se jouent sur une collection fabriquée en mémoire.
"""

import pytest

from hardset.engine.pinning import Pins, PinningError, resolve
from hardset.model import SetRequest, Track


def piste(id_: str, bpm: float, mood: int = 3) -> Track:
    return Track(
        id=id_,
        artist=f"Artiste {id_}",
        title=f"Titre {id_}",
        bpm=bpm,
        camelot="8A",
        duration_s=200,
        location=f"file://localhost/{id_}.mp3",
        genres=("Hardcore",),
        moods=(mood,),
    )


COLLECTION = [piste("a", 160.0), piste("b", 182.0), piste("c", 195.0)]


def requete(**kwargs) -> SetRequest:
    base = dict(
        genres=frozenset(),
        moods=frozenset(),
        bpm_min=150.0,
        bpm_max=200.0,
        profile="montee",
        duration_min=60,
        seed=1,
    )
    base.update(kwargs)
    return SetRequest(**base)


# --- Cas sans épinglage ---------------------------------------------------

def test_sans_epinglage_la_demande_est_rendue_intacte():
    demandee = requete()
    accordee, pins = resolve(COLLECTION, demandee)
    assert accordee == demandee
    assert pins == Pins()
    assert pins.epingles == ()


def test_sans_epinglage_la_collection_n_est_pas_parcourue():
    # Un itérateur qui lèverait s'il était lu : sans id à résoudre, `resolve`
    # n'a aucune raison de toucher à la collection.
    def explose():
        raise AssertionError("la collection ne devait pas être parcourue")
        yield   # pragma: no cover

    accordee, pins = resolve(explose(), requete())
    assert pins == Pins()
    assert accordee.bpm_min == 150.0


# --- Accord des bornes ----------------------------------------------------

def test_le_son_de_depart_impose_le_bpm_min():
    accordee, pins = resolve(COLLECTION, requete(start_track_id="b"))
    assert accordee.bpm_min == 182.0
    assert accordee.bpm_max == 200.0   # la borne sans morceau choisi ne bouge pas
    assert pins.start is not None and pins.start.id == "b"
    assert pins.end is None


def test_le_son_de_fin_impose_le_bpm_max():
    accordee, pins = resolve(COLLECTION, requete(end_track_id="b"))
    assert accordee.bpm_max == 182.0
    assert accordee.bpm_min == 150.0
    assert pins.end is not None and pins.end.id == "b"
    assert pins.start is None


def test_les_deux_bornes_sont_accordees_ensemble():
    accordee, pins = resolve(COLLECTION, requete(start_track_id="a", end_track_id="c"))
    assert (accordee.bpm_min, accordee.bpm_max) == (160.0, 195.0)
    assert pins.epingles == (pins.start, pins.end)


def test_le_reste_de_la_demande_est_intact():
    accordee, _ = resolve(COLLECTION, requete(start_track_id="a", duration_min=42))
    assert accordee.duration_min == 42
    assert accordee.profile == "montee"
    assert accordee.start_track_id == "a"


def test_resolve_est_idempotente():
    demandee = requete(start_track_id="a", end_track_id="c")
    accordee, pins = resolve(COLLECTION, demandee)
    rejouee, memes = resolve(COLLECTION, accordee)
    assert rejouee == accordee
    assert memes == pins


# --- Refus ----------------------------------------------------------------

def test_un_id_absent_de_la_collection_est_refuse():
    with pytest.raises(PinningError, match="absent de la collection"):
        resolve(COLLECTION, requete(start_track_id="inconnu"))


def test_le_meme_morceau_des_deux_cotes_est_refuse():
    with pytest.raises(PinningError, match="à la fois le son de départ et le son de fin"):
        resolve(COLLECTION, requete(start_track_id="b", end_track_id="b"))


def test_un_son_de_fin_plus_lent_que_le_depart_est_refuse():
    with pytest.raises(PinningError) as erreur:
        resolve(COLLECTION, requete(start_track_id="c", end_track_id="a"))
    # Le message nomme les deux tempos : c'est ce qui dit quoi corriger.
    assert "195" in str(erreur.value)
    assert "160" in str(erreur.value)


def test_un_son_de_depart_au_dela_du_bpm_max_demande_est_refuse():
    with pytest.raises(PinningError, match="dépasse le BPM max"):
        resolve(COLLECTION, requete(start_track_id="c", bpm_max=170.0))


def test_un_son_de_fin_en_deca_du_bpm_min_demande_est_refuse():
    with pytest.raises(PinningError, match="BPM min"):
        resolve(COLLECTION, requete(end_track_id="a", bpm_min=170.0))


def test_une_plage_reduite_a_un_seul_bpm_est_acceptee():
    # Départ et fin de même tempo : la plage est d'épaisseur nulle mais non vide.
    collection = [*COLLECTION, piste("b-bis", 182.0)]
    accordee, _ = resolve(collection, requete(start_track_id="b", end_track_id="b-bis"))
    assert accordee.bpm_min == accordee.bpm_max == 182.0
```

- [ ] **Step 2: Lancer les tests pour les voir échouer**

Run: `.venv/bin/pytest tests/test_pinning.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hardset.engine.pinning'`

- [ ] **Step 3: Ajouter les deux champs à `SetRequest`**

Dans `hardset/model.py`, dans la dataclass `SetRequest`, insérer après `seconds_per_track: int = 120` et avant `seed: int | None = None` :

```python
    # Morceaux imposés aux extrémités du set, par leur `Track.id`. Facultatifs et
    # indépendants. Ils déplacent les bornes de BPM (`engine/pinning.resolve`) :
    # la demande porte l'intention, pas encore la conséquence.
    start_track_id: str | None = None
    end_track_id: str | None = None
```

Complété de la même façon dans la docstring de la classe, après la phrase sur `seed` :

```python
    `start_track_id` et `end_track_id` sont les morceaux choisis pour ouvrir et
    fermer le set. `engine/pinning.resolve` les résout contre une collection.
```

- [ ] **Step 4: Écrire `hardset/engine/pinning.py`**

```python
"""Morceaux imposés aux extrémités du set, et accord des BPM à leur tempo.

Module pur, comme le reste de `hardset/engine/`.

`bpm_min` et `bpm_max` portent deux rôles à la fois : ce sont les extrémités de
la courbe (`engine/curves.build_targets`) et les bornes du vivier
(`engine/filtering.eligible`). Accorder une borne au morceau épinglé la déplace
donc pour **tout le set** : un son de départ à 182 BPM écarte du vivier tout ce
qui est plus lent. C'est voulu — un set qui ouvre à 182 n'a rien à faire à 150
ensuite — et c'est la même confusion des deux rôles qui interdit les sets
descendants : la plage dérivée serait vide.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from hardset.model import SetRequest, Track


class PinningError(Exception):
    """Choix d'épinglage inexploitable : morceau introuvable, ou plage vide."""


@dataclass(frozen=True)
class Pins:
    """Morceaux imposés aux extrémités du set. `None` quand rien n'est choisi."""

    start: Track | None = None
    end: Track | None = None

    @property
    def epingles(self) -> tuple[Track, ...]:
        """Les morceaux effectivement choisis, départ d'abord."""
        return tuple(t for t in (self.start, self.end) if t is not None)


def resolve(tracks: Iterable[Track], request: SetRequest) -> tuple[SetRequest, Pins]:
    """Résout les morceaux épinglés et accorde la plage de BPM à leur tempo.

    Rend la demande accordée et les morceaux résolus. La borne qui n'a pas de
    morceau choisi est laissée telle quelle.

    Idempotente : appliquée à son propre résultat, elle rend le même couple — la
    borne dérivée est déjà celle du morceau épinglé. C'est ce qui autorise
    `generate`, `shortage_warnings` et la couche web à l'appeler chacune pour son
    compte, sans se coordonner et sans risque de dérive.
    """
    if request.start_track_id is None and request.end_track_id is None:
        return request, Pins()

    if request.start_track_id is not None and request.start_track_id == request.end_track_id:
        raise PinningError(
            "le même morceau ne peut pas être à la fois le son de départ et le son de fin"
        )

    par_id = {track.id: track for track in tracks}
    pins = Pins(
        start=_retrouve(par_id, request.start_track_id),
        end=_retrouve(par_id, request.end_track_id),
    )

    accordee = replace(
        request,
        bpm_min=pins.start.bpm if pins.start is not None else request.bpm_min,
        bpm_max=pins.end.bpm if pins.end is not None else request.bpm_max,
    )
    if accordee.bpm_min > accordee.bpm_max:
        raise PinningError(_plage_vide(pins, request))
    return accordee, pins


def _retrouve(par_id: dict[str, Track], track_id: str | None) -> Track | None:
    if track_id is None:
        return None
    try:
        return par_id[track_id]
    except KeyError as exc:
        raise PinningError(f"morceau {track_id} absent de la collection") from exc


def _plage_vide(pins: Pins, request: SetRequest) -> str:
    """Message de plage vide, nommant ce qu'il faut corriger.

    Deux morceaux épinglés en ordre inverse, ou un seul qui sort de la borne
    restée saisie : même impasse, mais ce n'est pas la même chose à corriger.
    """
    if pins.start is not None and pins.end is not None:
        return (
            f"le son de fin ({pins.end.bpm:g} BPM) est plus lent que le son de "
            f"départ ({pins.start.bpm:g} BPM)"
        )
    if pins.start is not None:
        return (
            f"le son de départ ({pins.start.bpm:g} BPM) dépasse le BPM max "
            f"demandé ({request.bpm_max:g})"
        )
    assert pins.end is not None   # un des deux au moins est résolu à ce stade
    return (
        f"le son de fin ({pins.end.bpm:g} BPM) est plus lent que le BPM min "
        f"demandé ({request.bpm_min:g})"
    )
```

- [ ] **Step 5: Lancer les tests jusqu'au vert**

Run: `.venv/bin/pytest tests/test_pinning.py -q`
Expected: PASS — 13 tests.

- [ ] **Step 6: Vérifier que rien n'a bougé ailleurs**

Run: `.venv/bin/pytest -q`
Expected: PASS — 330 tests (317 + 13).

- [ ] **Step 7: Commit**

```bash
git add hardset/engine/pinning.py hardset/model.py tests/test_pinning.py
git commit -m "feat(engine): résout les sons épinglés et accorde la plage de BPM"
```

---

### Task 2: `engine/sequencing.py` — placer les épinglés dans le set

**Files:**
- Modify: `hardset/model.py` (enum `WarningCode`)
- Modify: `hardset/engine/sequencing.py` (`generate`, `shortage_warnings`, `replace_at`)
- Test: `tests/test_sequencing.py`

**Interfaces:**
- Consumes: `hardset.engine.pinning.resolve`, `Pins`, `PinningError` (tâche 1) ; `SetRequest.start_track_id` / `end_track_id` (tâche 1).
- Produces:
  - `WarningCode.PIN_OFF_FILTERS = "pin_off_filters"`, `WarningCode.PIN_DROPPED = "pin_dropped"`
  - `generate`, `shortage_warnings` et `replace_at` gardent exactement leur signature ; toutes trois peuvent désormais lever `PinningError`.

- [ ] **Step 1: Écrire les tests, qui échouent**

Ajouter à la fin de `tests/test_sequencing.py` :

```python
# --- Sons de départ et de fin épinglés ------------------------------------
#
# `piste` et `collection_dense` sont définis en tête de ce fichier. Les
# morceaux épinglés doivent appartenir à la collection : `resolve` les y
# retrouve par leur id.

def collection_avec_extremites() -> list[Track]:
    """Trois morceaux au milieu, un lent et un rapide destinés à être épinglés."""
    return [
        piste("debut", 150.0, 3),
        piste("a", 160.0, 3),
        piste("b", 165.0, 3),
        piste("c", 170.0, 3),
        piste("fin", 200.0, 3),
    ]


def test_le_son_de_depart_ouvre_le_set():
    jeu = generate(collection_dense(), requete(start_track_id="182-3"), CONFIG)
    assert jeu.tracks[0].id == "182-3"


def test_le_son_de_fin_ferme_le_set():
    jeu = generate(collection_dense(), requete(end_track_id="182-3"), CONFIG)
    assert jeu.tracks[-1].id == "182-3"


def test_le_son_de_depart_impose_la_borne_du_vivier():
    # Conséquence assumée : la borne accordée filtre tout le reste du set.
    jeu = generate(collection_dense(), requete(start_track_id="182-3"), CONFIG)
    assert min(track.bpm for track in jeu.tracks) == 182.0


def test_un_morceau_epingle_n_est_pas_place_deux_fois():
    jeu = generate(collection_dense(), requete(start_track_id="182-3"), CONFIG)
    assert [t.id for t in jeu.tracks].count("182-3") == 1


def test_les_epingles_comptent_dans_la_longueur_du_set():
    jeu = generate(
        collection_avec_extremites(),
        requete(start_track_id="debut", end_track_id="fin"),
        CONFIG,
    )
    # Trois morceaux au vivier, plus les deux épinglés.
    assert len(jeu.tracks) == 5
    assert jeu.tracks[0].id == "debut"
    assert jeu.tracks[-1].id == "fin"


def test_la_penurie_compte_les_epingles():
    jeu = generate(
        collection_avec_extremites(),
        requete(start_track_id="debut", end_track_id="fin"),
        CONFIG,
    )
    penurie = [w for w in jeu.warnings if w.code is WarningCode.SHORTAGE]
    assert len(penurie) == 1
    assert "5 éligibles" in penurie[0].message


def test_shortage_warnings_compte_comme_generate():
    collection = collection_avec_extremites()
    demande = requete(start_track_id="debut", end_track_id="fin")
    attendus = [w for w in generate(collection, demande, CONFIG).warnings
                if w.code is WarningCode.SHORTAGE]
    assert shortage_warnings(collection, demande) == attendus


def test_un_epingle_hors_des_criteres_est_place_avec_un_avertissement():
    collection = [*collection_dense(), piste("calme", 182.0, 1)]
    jeu = generate(
        collection,
        requete(start_track_id="calme", moods=frozenset({4, 5})),
        CONFIG,
    )
    assert jeu.tracks[0].id == "calme"
    hors = [w for w in jeu.warnings if w.code is WarningCode.PIN_OFF_FILTERS]
    assert len(hors) == 1
    assert hors[0].track_ids == ("calme",)
    assert "première" in hors[0].message


def test_un_epingle_sans_aucun_mood_est_place_quand_meme():
    # Sans épinglage, `eligible` l'écarterait : on ne saurait pas où le placer.
    # Épinglé, il est placé d'autorité — et signalé.
    muet = replace(piste("muet", 200.0, 3), moods=())
    jeu = generate([*collection_dense(), muet], requete(end_track_id="muet"), CONFIG)
    assert jeu.tracks[-1].id == "muet"
    assert any(w.code is WarningCode.PIN_OFF_FILTERS for w in jeu.warnings)


def test_un_epingle_dans_les_criteres_ne_produit_aucun_avertissement():
    jeu = generate(collection_dense(), requete(start_track_id="182-3"), CONFIG)
    assert not [w for w in jeu.warnings if w.code is WarningCode.PIN_OFF_FILTERS]


def test_un_set_d_une_seule_position_garde_le_son_de_depart():
    jeu = generate(
        collection_avec_extremites(),
        requete(start_track_id="debut", end_track_id="fin", duration_min=1),
        CONFIG,
    )
    assert [t.id for t in jeu.tracks] == ["debut"]
    abandon = [w for w in jeu.warnings if w.code is WarningCode.PIN_DROPPED]
    assert len(abandon) == 1
    assert abandon[0].track_ids == ("fin",)


def test_un_set_d_une_seule_position_place_le_son_de_fin_s_il_est_seul():
    jeu = generate(
        collection_avec_extremites(),
        requete(end_track_id="fin", duration_min=1),
        CONFIG,
    )
    assert [t.id for t in jeu.tracks] == ["fin"]
    assert not [w for w in jeu.warnings if w.code is WarningCode.PIN_DROPPED]


def test_un_epingle_introuvable_fait_echouer_la_generation():
    with pytest.raises(PinningError):
        generate(collection_dense(), requete(start_track_id="inconnu"), CONFIG)


def test_le_remplacement_respecte_la_plage_accordee():
    demande = requete(start_track_id="182-3")
    jeu = generate(collection_dense(), demande, CONFIG)
    apres = replace_at(jeu, 1, collection_dense(), demande, CONFIG)
    assert apres.tracks[1].id != jeu.tracks[1].id
    assert apres.tracks[1].bpm >= 182.0


def test_la_collection_peut_etre_un_iterateur():
    # `generate` lit la collection deux fois désormais (résolution puis
    # filtrage) : un itérateur ne doit pas être consommé au premier passage.
    jeu = generate(iter(collection_dense()), requete(start_track_id="182-3"), CONFIG)
    assert jeu.tracks[0].id == "182-3"
```

Ajouter `PinningError` à l'import en tête du fichier de test :

```python
from hardset.engine.pinning import PinningError
```

- [ ] **Step 2: Lancer les tests pour les voir échouer**

Run: `.venv/bin/pytest tests/test_sequencing.py -q`
Expected: FAIL — `AttributeError: PIN_OFF_FILTERS` et `TypeError: ... unexpected keyword argument 'start_track_id'` selon les tests, puisque `generate` ignore encore les épinglés.

- [ ] **Step 3: Ajouter les deux codes d'avertissement**

Dans `hardset/model.py`, dans l'enum `WarningCode`, après `REPLACEMENT_SHORTAGE` :

```python
    PIN_OFF_FILTERS = "pin_off_filters"   # morceau épinglé placé hors des critères
    PIN_DROPPED = "pin_dropped"           # morceau épinglé non plaçable, set trop court
```

- [ ] **Step 4: Écrire le placement dans `sequencing.py`**

Ajouter à l'import, en tête de `hardset/engine/sequencing.py` :

```python
from hardset.engine.pinning import Pins, resolve
```

Ajouter ces trois fonctions privées après `_penurie` :

```python
def _vivier(
    tracks: Iterable[Track], request: SetRequest
) -> tuple[SetRequest, Pins, list[Track]]:
    """Demande accordée aux épinglés, épinglés résolus, et vivier privé d'eux.

    `tracks` est matérialisé d'abord : il peut être un itérateur, et il est
    désormais lu deux fois — une pour résoudre les épinglés, une pour filtrer.

    Les épinglés sont retirés du vivier qu'ils en fassent partie ou non. Un
    morceau épinglé qui est aussi éligible serait sinon placé deux fois : une
    fois d'autorité, une fois par tirage.
    """
    materiel = list(tracks)
    accordee, pins = resolve(materiel, request)
    exclus = {track.id for track in pins.epingles}
    vivier = [
        track
        for track in _dedoublonne_par_id(eligible(materiel, accordee))
        if track.id not in exclus
    ]
    return accordee, pins, vivier


def _placement(pins: Pins, count: int) -> dict[int, Track]:
    """Positions imposées par l'épinglage, pour un set de `count` positions.

    Quand le set n'a qu'une position et que deux morceaux sont choisis, le
    départ l'emporte : arbitraire, mais fixé et documenté, et préférable à un
    échec pour un cas qui n'arrive que par accident — une durée demandée plus
    courte que le temps de jeu d'un seul morceau.
    """
    impose: dict[int, Track] = {}
    if count <= 0:
        return impose
    if pins.start is not None:
        impose[0] = pins.start
    if pins.end is not None and (count - 1) not in impose:
        impose[count - 1] = pins.end
    return impose


def _avertissements_epinglage(
    pins: Pins, impose: dict[int, Track], request: SetRequest
) -> list[SetWarning]:
    """Avertissements propres à l'épinglage, sur une demande déjà accordée.

    Un morceau épinglé n'a traversé aucun filtre : c'est l'intention (un choix
    explicite passe avant un critère coché), et c'est précisément pour ça qu'il
    faut le dire.
    """
    avertissements: list[SetWarning] = []
    places = {track.id for track in impose.values()}

    for role, track in (("première", pins.start), ("dernière", pins.end)):
        if track is None or track.id not in places:
            continue
        # La borne de BPM a été accordée à ce morceau : seuls le mood et le
        # genre peuvent encore le faire échouer ici.
        if not eligible([track], request):
            avertissements.append(
                SetWarning(
                    code=WarningCode.PIN_OFF_FILTERS,
                    message=(
                        f"« {track.label} » est placé en {role} position bien qu'il "
                        "ne corresponde pas aux critères demandés"
                    ),
                    track_ids=(track.id,),
                )
            )

    # Seul le son de fin peut rester sur le carreau : `_placement` donne la
    # position unique au départ quand les deux sont choisis.
    if pins.end is not None and pins.end.id not in places:
        avertissements.append(
            SetWarning(
                code=WarningCode.PIN_DROPPED,
                message="le son de fin n'a pas pu être placé : le set ne compte qu'une position",
                track_ids=(pins.end.id,),
            )
        )
    return avertissements
```

Remplacer le corps de `shortage_warnings` (la docstring est conservée telle quelle, en lui ajoutant le paragraphe ci-dessous) :

```python
    _, pins, vivier = _vivier(tracks, request)
    return _penurie(len(vivier) + len(pins.epingles), request.track_count)
```

Paragraphe à ajouter à la fin de sa docstring :

```
    Les morceaux épinglés comptent dans le décompte bien qu'ils ne viennent pas
    du vivier : ils occupent une position du set. Sans ça, cette aide et
    `generate` divergeraient d'au plus deux morceaux, et l'avertissement
    reparaîtrait ou disparaîtrait au premier remplacement.
```

Remplacer le corps de `generate` :

```python
def generate(tracks: Iterable[Track], request: SetRequest, config: Config) -> GeneratedSet:
    """Construit le set demandé, ou le plus long possible si les morceaux manquent.

    Les morceaux épinglés (`SetRequest.start_track_id` / `end_track_id`) ouvrent
    et ferment le set. Ils sont **placés, pas choisis** : `cost` ne les note
    jamais, et leur position peut donc s'écarter de la cible — c'est une
    contrainte imposée, pas un échec de sélection, et la courbe le montre.
    """
    profile = _profile(request, config)   # valide le profil avant toute autre chose
    # `request` est rebindée sur la demande accordée aux épinglés : tout ce qui
    # suit (cibles, filtrage, avertissements) doit voir les bornes dérivées.
    request, pins, pool = _vivier(tracks, request)

    vise = request.track_count
    disponibles = len(pool) + len(pins.epingles)
    count = min(vise, disponibles)

    targets = build_targets(request, profile, count, config.mood_max)
    impose = _placement(pins, count)
    avertissements = [
        *_penurie(disponibles, vise),
        *_avertissements_epinglage(pins, impose, request),
    ]

    rng = random.Random(request.seed)
    retenus: list[Track] = []
    precedent: Track | None = None
    for target in targets:
        epingle = impose.get(target.position)
        precedent = epingle if epingle is not None else _pick(
            pool, target, precedent, config.poids, rng
        )
        retenus.append(precedent)

    return GeneratedSet(tracks=retenus, targets=targets, warnings=avertissements)
```

Dans `replace_at`, remplacer le calcul du vivier :

```python
    deja_places = {track.id for track in generated.tracks}
    pool = [
        track
        for track in _dedoublonne_par_id(eligible(tracks, request))
        if track.id not in deja_places
    ]
```

par :

```python
    # La demande est accordée ici aussi : le vivier de remplacement doit tenir
    # dans la plage imposée par les sons épinglés, comme celui de `generate`.
    request, _, vivier = _vivier(tracks, request)
    pool = [track for track in vivier if track.id not in deja_places]
```

en déplaçant `deja_places = {track.id for track in generated.tracks}` juste au-dessus.

Ajouter enfin ce paragraphe à la docstring de `replace_at` :

```
    Les positions épinglées ne sont pas protégées : l'épinglage est une
    contrainte de génération, pas un verrou d'édition, et la tracklist reste
    modifiable à la main comme le reste.
```

- [ ] **Step 5: Lancer les tests jusqu'au vert**

Run: `.venv/bin/pytest tests/test_sequencing.py -q`
Expected: PASS

- [ ] **Step 6: Lancer toute la suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — 345 tests (330 + 15).

- [ ] **Step 7: Commit**

```bash
git add hardset/model.py hardset/engine/sequencing.py tests/test_sequencing.py
git commit -m "feat(engine): place les sons épinglés aux extrémités du set"
```

---

### Task 3: `engine/search.py` — trouver un morceau par artiste ou titre

**Files:**
- Create: `hardset/engine/search.py`
- Test: `tests/test_search.py` (create)

**Interfaces:**
- Consumes: `hardset.model.Track`, `hardset.model.normalize_tag`.
- Produces: `hardset.engine.search.search(tracks: Iterable[Track], q: str, limit: int) -> tuple[list[Track], bool]` — les morceaux trouvés (au plus `limit`, dans l'ordre de la collection) et un drapeau disant qu'il y en avait davantage.

- [ ] **Step 1: Écrire les tests, qui échouent**

Créer `tests/test_search.py` :

```python
"""Tests de la recherche de morceaux, qui sert à choisir les sons épinglés."""

from hardset.engine.search import search
from hardset.model import Track


def piste(id_: str, artist: str, title: str, moods=(3,)) -> Track:
    return Track(
        id=id_,
        artist=artist,
        title=title,
        bpm=180.0,
        camelot="8A",
        duration_s=200,
        location=f"file://localhost/{id_}.mp3",
        genres=("Hardcore",),
        moods=moods,
    )


COLLECTION = [
    piste("1", "Angerfist", "Raise Your Fist"),
    piste("2", "Angerfist", "Pennywise"),
    piste("3", "Nosferatu", "Raise The Dead"),
    piste("4", "Sefa", "Vérité"),
    piste("5", "DJ Paul Elstak", "Rainbow In The Sky", moods=()),
]


def ids(resultat) -> list[str]:
    trouves, _ = resultat
    return [track.id for track in trouves]


def test_cherche_dans_le_titre():
    assert ids(search(COLLECTION, "pennywise", 20)) == ["2"]


def test_cherche_dans_l_artiste():
    assert ids(search(COLLECTION, "angerfist", 20)) == ["1", "2"]


def test_tous_les_mots_doivent_figurer_dans_n_importe_quel_ordre():
    # « fist » vient de l'artiste et du titre, « raise » du titre seul.
    assert ids(search(COLLECTION, "raise angerfist", 20)) == ["1"]
    assert ids(search(COLLECTION, "angerfist raise", 20)) == ["1"]


def test_la_casse_et_les_accents_sont_ignores():
    assert ids(search(COLLECTION, "VERITE", 20)) == ["4"]
    assert ids(search(COLLECTION, "vérité", 20)) == ["4"]


def test_une_recherche_vide_ne_rend_rien():
    # La page invite à taper plutôt que de dérouler la collection entière.
    assert search(COLLECTION, "", 20) == ([], False)
    assert search(COLLECTION, "   ", 20) == ([], False)


def test_aucun_resultat():
    assert search(COLLECTION, "zzzz", 20) == ([], False)


def test_l_ordre_de_la_collection_est_conserve():
    assert ids(search(COLLECTION, "raise", 20)) == ["1", "3"]


def test_le_plafond_tronque_et_le_signale():
    trouves, tronque = search(COLLECTION, "a", 2)
    assert len(trouves) == 2
    assert tronque is True


def test_sans_troncature_le_drapeau_est_faux():
    trouves, tronque = search(COLLECTION, "angerfist", 2)
    assert len(trouves) == 2
    assert tronque is False


def test_un_plafond_nul_ne_rend_rien():
    assert search(COLLECTION, "angerfist", 0) == ([], False)


def test_un_morceau_sans_mood_reste_trouvable():
    # La recherche ne connaît aucun critère de set : c'est ce qui rend
    # épinglable un morceau que `eligible` écarterait.
    assert ids(search(COLLECTION, "rainbow", 20)) == ["5"]
```

- [ ] **Step 2: Lancer les tests pour les voir échouer**

Run: `.venv/bin/pytest tests/test_search.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hardset.engine.search'`

- [ ] **Step 3: Écrire `hardset/engine/search.py`**

```python
"""Recherche d'un morceau dans la collection, par artiste ou par titre.

Sert à choisir les sons de départ et de fin. Le module vit dans le moteur et non
dans la route qui l'expose, pour la même raison que le reste : `hardset/web/`
traduit des requêtes HTTP, il ne décide de rien.

La recherche ne connaît **aucun** critère de set : un morceau sans mood, hors
plage de BPM ou hors des genres cochés reste trouvable, donc épinglable. C'est
l'intention — un choix explicite passe avant un filtre coché.
"""

from __future__ import annotations

from collections.abc import Iterable

from hardset.model import Track, normalize_tag


def search(tracks: Iterable[Track], q: str, limit: int) -> tuple[list[Track], bool]:
    """Morceaux dont « artiste titre » contient tous les mots de `q`.

    Rend au plus `limit` morceaux, dans l'ordre de la collection, et un drapeau
    disant qu'il y en avait davantage — la page invite alors à affiner plutôt
    que de laisser croire à une liste complète.

    Une requête vide ne rend rien : dérouler une collection entière n'aide
    personne à choisir.
    """
    mots = normalize_tag(q).split()
    if not mots or limit <= 0:
        return [], False

    trouves: list[Track] = []
    for track in tracks:
        foin = normalize_tag(f"{track.artist} {track.title}")
        if not all(mot in foin for mot in mots):
            continue
        trouves.append(track)
        if len(trouves) > limit:
            return trouves[:limit], True
    return trouves, False
```

- [ ] **Step 4: Lancer les tests jusqu'au vert**

Run: `.venv/bin/pytest tests/test_search.py -q`
Expected: PASS — 11 tests.

- [ ] **Step 5: Lancer toute la suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — 356 tests (345 + 11).

- [ ] **Step 6: Commit**

```bash
git add hardset/engine/search.py tests/test_search.py
git commit -m "feat(engine): cherche un morceau par artiste ou par titre"
```

---

### Task 4: `web/app.py` — exposer la recherche et transporter les épinglés

**Files:**
- Modify: `hardset/web/app.py`
- Test: `tests/test_api.py`, `tests/test_bout_en_bout.py`

**Interfaces:**
- Consumes: `search` (tâche 3), `resolve` / `PinningError` (tâche 1), `generate` / `replace_at` / `shortage_warnings` accordés (tâche 2).
- Produces (contrat HTTP dont dépend la tâche 6) :
  - `POST /api/tracks` ← `{path, q, limit}` → `{"tracks": [<track_payload>], "truncated": bool}`
  - `SetRequestPayload` (donc `/api/generate`, `/api/replace`, `/api/targets`) accepte `start_track_id: str | null` et `end_track_id: str | null`, tous deux facultatifs.
  - Toute `PinningError` sort en HTTP 400 dont le `detail` est le message français du moteur.

- [ ] **Step 1: Écrire les tests, qui échouent**

Ajouter à la fin de `tests/test_api.py`. Rappel de la fixture `collection_xml` : 40 morceaux, `TrackID` de `"0"` à `"39"`, BPM `150 + i`, artiste `Artiste i`, titre `Titre i`, genre `Hardcore`, mood `MOODS[i % 5]`. Le morceau `"10"` fait donc 160 BPM et le morceau `"30"` en fait 180 ; tous deux sont `CALME` (mood 1).

```python
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
```

Ajouter à `tests/test_bout_en_bout.py` :

```python
def test_un_morceau_sans_mood_est_trouvable_donc_epinglable(client):
    # « Industrial Corridor » (Mira Cast) est le morceau sans mood de la
    # fixture, celui que `eligible` écarte toujours. La recherche, elle, doit
    # le rendre — sans quoi il serait impossible de l'épingler, alors que c'est
    # justement l'intérêt d'un choix explicite.
    donnees = client.post(
        "/api/tracks", json={"path": str(FIXTURE), "q": "industrial corridor"}
    ).json()
    assert [t["title"] for t in donnees["tracks"]] == ["Industrial Corridor"]
    assert donnees["tracks"][0]["moods"] == []
```

> La recherche porte sur l'artiste et le titre, **pas** sur les genres : ici
> « Industrial » est trouvé parce qu'il est dans le titre, et le fait que ce
> soit aussi son genre n'y est pour rien.

- [ ] **Step 2: Lancer les tests pour les voir échouer**

Run: `.venv/bin/pytest tests/test_api.py tests/test_bout_en_bout.py -q`
Expected: FAIL — 404 sur `/api/tracks`, et les épinglés ignorés par `/api/generate` (les champs inconnus d'un modèle Pydantic sont silencieusement ignorés).

- [ ] **Step 3: Déclarer la route de recherche**

Dans `hardset/web/app.py`, ajouter aux imports :

```python
from hardset.engine.pinning import PinningError, resolve
from hardset.engine.search import search
```

Ajouter la constante, sous `TARGETS_COUNT_MAX` :

```python
# Plafond de `limit` sur `/api/tracks`. La page en demande 20 : une liste de
# choix plus longue ne se lit pas. Le plafond protège d'une réponse énorme sur
# une requête d'un seul caractère, sans interdire à une autre cliente d'en
# demander davantage.
TRACKS_LIMIT_MAX = 100
```

Ajouter le modèle, après `CollectionPayload` :

```python
class SearchPayload(CollectionPayload):
    """Recherche d'un morceau à épingler, par artiste ou par titre."""

    q: str = ""
    limit: int = 20
```

Ajouter la route, juste après `/api/collection` :

```python
    @app.post("/api/tracks")
    def chercher(payload: SearchPayload) -> dict:
        """Morceaux de la collection correspondant à la recherche.

        Aucun critère du set n'est appliqué : c'est ce qui permet d'épingler un
        morceau que la génération écarterait (`engine/search.py`).
        """
        lue = charger(payload.path)
        limite = max(1, min(payload.limit, TRACKS_LIMIT_MAX))
        trouves, tronque = search(lue.tracks, payload.q, limite)
        return {
            "tracks": [_track_payload(track) for track in trouves],
            "truncated": tronque,
        }
```

- [ ] **Step 4: Transporter les épinglés dans les trois routes de génération**

Dans `SetRequestPayload`, ajouter après `seconds_per_track` :

```python
    # Morceaux imposés aux extrémités. Non validés ici : c'est `resolve` qui le
    # fait, contre la collection, et lui seul sait ce qu'ils impliquent.
    start_track_id: str | None = None
    end_track_id: str | None = None
```

et les recopier dans le `SetRequest` rendu par `to_request` :

```python
            start_track_id=self.start_track_id,
            end_track_id=self.end_track_id,
```

Dans `/api/generate`, élargir la capture :

```python
        try:
            resultat = generate(lue.tracks, requete, config)
        except (SequencingError, PinningError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
```

Dans `/api/replace`, remplacer le corps après `profil = profil_demande(requete)` :

```python
        try:
            # Les cibles du set courant doivent être celles de la demande
            # accordée aux sons épinglés, sinon la courbe affichée cesse de
            # correspondre à celle que le remplacement vise.
            accordee, _ = resolve(lue.tracks, requete)
            courant = GeneratedSet(
                tracks=tracks,
                targets=build_targets(accordee, profil, len(tracks), config.mood_max),
                warnings=shortage_warnings(lue.tracks, requete),
            )
            resultat = replace_at(courant, payload.position, lue.tracks, requete, config)
        except (SequencingError, PinningError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _set_payload(resultat, lue, requete)
```

Dans `/api/targets`, insérer avant le `return`, après les deux gardes sur `count` :

```python
        # La collection n'est ouverte que s'il y a un son épinglé : sans
        # épinglage les cibles n'en dépendent pas, et la route garde la
        # propriété que défend sa docstring. Le cache rend ce chargement
        # gratuit en pratique — la page vient de lire la collection.
        if requete.start_track_id is not None or requete.end_track_id is not None:
            try:
                requete, _ = resolve(charger(payload.path).tracks, requete)
            except PinningError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
```

et compléter la docstring de la route d'une phrase :

```
        Elle n'ouvre la collection que pour résoudre un son épinglé, dont elle a
        besoin de connaître le tempo.
```

- [ ] **Step 5: Lancer les tests jusqu'au vert**

Run: `.venv/bin/pytest tests/test_api.py tests/test_bout_en_bout.py -q`
Expected: PASS

- [ ] **Step 6: Lancer toute la suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — 375 tests (356 + 19).

- [ ] **Step 7: Commit**

```bash
git add hardset/web/app.py tests/test_api.py tests/test_bout_en_bout.py
git commit -m "feat(web): expose la recherche et transporte les sons épinglés"
```

---

### Task 5: La page — choisir les sons et verrouiller les bornes

**Files:**
- Modify: `hardset/web/static/index.html`
- Modify: `hardset/web/static/style.css`
- Modify: `hardset/web/static/app.js`

**Interfaces:**
- Consumes: `POST /api/tracks` et les champs `start_track_id` / `end_track_id` (tâche 4).
- Produces: rien dont une autre tâche dépende. La vérification est manuelle (tâche 6).

Aucun test automatisé : ce dépôt n'en a pas pour le JavaScript (contrainte globale). Chaque étape se vérifie à l'œil, et la tâche 6 reprend le tout.

- [ ] **Step 1: Ajouter le bloc de choix dans `index.html`**

Dans les deux `<span>` de la ligne BPM, ajouter la mention de verrouillage :

```html
        <div class="ligne">
          <span>
            <label for="bpm-min">BPM min</label>
            <input type="number" id="bpm-min" value="150" step="1">
            <span id="note-bpm-min" class="discret" hidden>imposé par le son de départ</span>
          </span>
          <span>
            <label for="bpm-max">BPM max</label>
            <input type="number" id="bpm-max" value="200" step="1">
            <span id="note-bpm-max" class="discret" hidden>imposé par le son de fin</span>
          </span>
        </div>
```

Puis, juste après la `<div class="colonnes">` fermante et avant la ligne des boutons `generer` / `regenerer` :

```html
    <fieldset id="epinglage">
      <legend>Début et fin du set (facultatif)</legend>
      <div class="deux-colonnes">
        <div class="recherche">
          <label for="recherche-start">Son de départ</label>
          <input type="search" id="recherche-start" placeholder="artiste ou titre…"
                 autocomplete="off" disabled>
          <ul id="resultats-start" class="resultats" hidden></ul>
          <div id="choix-start" class="choix" hidden></div>
        </div>
        <div class="recherche">
          <label for="recherche-end">Son de fin</label>
          <input type="search" id="recherche-end" placeholder="artiste ou titre…"
                 autocomplete="off" disabled>
          <ul id="resultats-end" class="resultats" hidden></ul>
          <div id="choix-end" class="choix" hidden></div>
        </div>
      </div>
    </fieldset>
```

- [ ] **Step 2: Habiller le bloc dans `style.css`**

Ajouter après la règle `.colonnes` :

```css
.deux-colonnes { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; }
```

et à la fin du fichier, avant `.export` :

```css
.recherche input[type="search"] { width: 100%; }

.resultats {
  list-style: none;
  margin: 0.35rem 0 0;
  padding: 0;
  max-height: 12rem;
  overflow-y: auto;
  border: 1px solid var(--trait);
  border-radius: 6px;
  background: #24282f;
}
.resultats li { border-bottom: 1px solid var(--trait); }
.resultats li:last-child { border-bottom: 0; }
.resultats li.discret { padding: 0.4rem 0.6rem; }
.resultats button {
  width: 100%;
  text-align: left;
  border: 0;
  border-radius: 0;
  background: none;
}
.resultats button:hover { background: #2c313a; }

.choix { display: flex; gap: 0.5rem; align-items: center; margin-top: 0.35rem; }
.choix .epingle { flex: 1; }

/* Une borne imposée par un son choisi se voit : elle n'est plus modifiable. */
input:read-only { opacity: 0.55; }
```

- [ ] **Step 3: Tenir les deux choix dans l'état de la page**

Dans `hardset/web/static/app.js`, ajouter le champ à l'état initial :

```js
const state = {
  config: null,
  collection: null,
  set: null,
  path: '',
  // Sons imposés aux extrémités, tels que /api/tracks les a rendus (ou null).
  pins: { start: null, end: null },
};
```

Ajouter dans `requete()`, avant le `...extra` :

```js
    start_track_id: state.pins.start ? state.pins.start.id : null,
    end_track_id: state.pins.end ? state.pins.end.id : null,
```

- [ ] **Step 4: Écrire le widget de choix**

Ajouter cette section dans `app.js`, entre « Rendu » et « Actions » :

```js
// --- Sons de départ et de fin ---------------------------------------------
//
// Un son choisi impose la borne de BPM correspondante. La page écrit la valeur
// dans le champ et le verrouille, mais ce n'est que de l'affichage : le serveur
// re-dérive toujours la borne depuis l'id envoyé et ne lit jamais ce que le
// champ a transmis (hardset/engine/pinning.py).

const PINS = {
  start: { bpm: 'bpm-min', note: 'note-bpm-min', borne: (b) => b.min },
  end:   { bpm: 'bpm-max', note: 'note-bpm-max', borne: (b) => b.max },
};

const minuteries = { start: null, end: null };

// Bornes de BPM de la collection chargée, celles que le champ retrouve quand on
// retire un son choisi. Sans collection, les valeurs par défaut du formulaire.
function bornesCollection() {
  const lue = state.collection;
  if (!lue || !(lue.bpm_max > 0)) return { min: 150, max: 200 };
  return { min: Math.floor(lue.bpm_min), max: Math.ceil(lue.bpm_max) };
}

function appliquerPin(role) {
  const pin = state.pins[role];
  const { bpm, note, borne } = PINS[role];
  const champ = $(`recherche-${role}`);
  const choix = $(`choix-${role}`);

  $(`resultats-${role}`).replaceChildren();
  $(`resultats-${role}`).hidden = true;
  choix.replaceChildren();
  choix.hidden = !pin;
  champ.hidden = Boolean(pin);

  if (pin) {
    choix.append(
      el('span', {
        className: 'epingle',
        textContent: `📌 ${pin.artist} — ${pin.title} · ${pin.bpm.toFixed(1)} BPM`,
      }),
      el('button', {
        type: 'button', textContent: '✕', title: 'retirer ce choix',
        onclick: () => { state.pins[role] = null; appliquerPin(role); },
      }),
    );
    $(bpm).value = pin.bpm;
  } else {
    champ.value = '';
    $(bpm).value = borne(bornesCollection());
  }
  $(bpm).readOnly = Boolean(pin);
  $(note).hidden = !pin;
}

function choisirPin(role, track) {
  const autre = role === 'start' ? 'end' : 'start';
  if (state.pins[autre] && state.pins[autre].id === track.id) {
    // Le serveur le refuserait aussi ; le dire tout de suite évite un
    // aller-retour pour une erreur visible d'ici.
    renderAvertissements([{
      message: 'le même morceau ne peut pas être à la fois le son de départ et le son de fin',
    }]);
    return;
  }
  state.pins[role] = track;
  appliquerPin(role);
}

async function rechercher(role) {
  const q = $(`recherche-${role}`).value.trim();
  const liste = $(`resultats-${role}`);
  if (!q) {
    liste.replaceChildren();
    liste.hidden = true;
    return;
  }
  try {
    const reponse = await api('/api/tracks', { path: state.path, q, limit: 20 });
    const donnees = await reponse.json();
    liste.replaceChildren(...donnees.tracks.map((track) => el('li', {}, [
      el('button', {
        type: 'button',
        textContent: `${track.artist} — ${track.title} · ${track.bpm.toFixed(1)} BPM · ${track.camelot ?? '—'}`,
        onclick: () => choisirPin(role, track),
      }),
    ])));
    if (!donnees.tracks.length) {
      liste.append(el('li', { className: 'discret', textContent: 'aucun morceau trouvé' }));
    } else if (donnees.truncated) {
      liste.append(el('li', {
        className: 'discret', textContent: 'affinez : d’autres morceaux correspondent',
      }));
    }
    liste.hidden = false;
  } catch (erreur) {
    renderAvertissements([{ message: erreur.message }]);
  }
}

// Une frappe ne déclenche pas un appel : la temporisation évite une requête par
// caractère sur une collection de plusieurs centaines de morceaux.
function brancherRecherche(role) {
  const champ = $(`recherche-${role}`);
  champ.oninput = () => {
    clearTimeout(minuteries[role]);
    minuteries[role] = setTimeout(() => rechercher(role), 200);
  };
  champ.onkeydown = (evenement) => {
    if (evenement.key === 'Escape') $(`resultats-${role}`).hidden = true;
  };
}
```

- [ ] **Step 5: Brancher le widget au chargement et au rendu**

Dans `chargerCollection`, remplacer le bloc :

```js
    if (donnees.bpm_max > 0) {
      $('bpm-min').value = Math.floor(donnees.bpm_min);
      $('bpm-max').value = Math.ceil(donnees.bpm_max);
    }
```

par :

```js
    // Les sons choisis n'appartiennent plus à cette collection-ci, comme le set.
    // `appliquerPin` remet du même coup les bornes de BPM de la collection lue.
    state.pins = { start: null, end: null };
    for (const role of ['start', 'end']) {
      $(`recherche-${role}`).disabled = false;
      appliquerPin(role);
    }
```

Dans `render()`, remplacer la cellule du numéro de ligne :

```js
      el('td', { textContent: String(index + 1) }),
```

par :

```js
      el('td', celluleNumero(track, index)),
```

et ajouter cette fonction juste au-dessus de `render()` :

```js
// Le repère suit le morceau épinglé s'il est déplacé : il est posé par
// comparaison d'id, jamais par position. Les boutons de la ligne restent
// actifs — l'épinglage contraint la génération, il ne verrouille pas l'édition.
function celluleNumero(track, index) {
  const epingle = [state.pins.start, state.pins.end].some((p) => p && p.id === track.id);
  return epingle
    ? { textContent: `${index + 1} 📌`, title: 'son choisi avant la génération' }
    : { textContent: String(index + 1) };
}
```

Dans `init()`, avant les branchements de boutons :

```js
  for (const role of ['start', 'end']) brancherRecherche(role);
```

Et pour qu'un clic ailleurs referme une liste ouverte, à la fin de `init()` :

```js
  document.addEventListener('click', (evenement) => {
    if (evenement.target.closest('.recherche')) return;
    for (const role of ['start', 'end']) $(`resultats-${role}`).hidden = true;
  });
```

- [ ] **Step 6: Vérifier que la suite Python est toujours verte**

Les fichiers statiques sont servis tels quels ; aucun test ne les lit, mais la page doit rester servie.

Run: `.venv/bin/pytest -q`
Expected: PASS — 375 tests.

- [ ] **Step 7: Commit**

```bash
git add hardset/web/static/index.html hardset/web/static/style.css hardset/web/static/app.js
git commit -m "feat(web): choisit le son de départ et le son de fin dans la page"
```

---

### Task 6: Vérification dans le navigateur

**Files:**
- Modify: aucun, sauf correction d'un défaut constaté.

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces: la preuve que la page fait ce que la spec décrit.

Le JavaScript n'a pas de tests dans ce dépôt : cette tâche est la seule vérification de la page, et elle ne peut pas être sautée.

- [ ] **Step 1: Lancer l'outil sur un export réel**

```bash
.venv/bin/hardset --no-browser
```

Ouvrir `http://127.0.0.1:8765`, saisir le chemin d'un export Rekordbox, cliquer sur **Charger**.

- [ ] **Step 2: Dérouler la liste de contrôle**

Chaque ligne se coche à l'œil dans la page :

1. avant chargement, les deux champs de recherche sont grisés ;
2. après chargement, ils s'activent, et **BPM min / BPM max** portent les bornes de la collection ;
3. taper trois lettres dans **Son de départ** affiche une liste de morceaux avec leur BPM et leur clé ;
4. cliquer sur l'un d'eux le remplace par `📌 Artiste — Titre · 182.0 BPM ✕`, **BPM min** passe à 182, devient grisé et non modifiable, et la mention `imposé par le son de départ` apparaît ;
5. **Générer** produit un set dont la première ligne est ce morceau, marquée `1 📌`, et dont aucun morceau n'est plus lent que lui ;
6. choisir un **Son de fin** plus rapide et régénérer : la dernière ligne est ce morceau, marquée 📌 ;
7. supprimer une ligne du milieu : la courbe se redistribue, et les deux extrémités restent en place ;
8. déplacer la ligne épinglée avec ↑ : le 📌 la suit ;
9. choisir un son de fin **plus lent** que le son de départ, puis **Générer** : un avertissement nomme les deux tempos, et le set affiché n'est pas remplacé ;
10. le ✕ d'un choix rend la main au champ BPM, qui retrouve la borne de la collection ;
11. recharger une autre collection : les deux choix disparaissent et les champs redeviennent modifiables ;
12. choisir un morceau dont le mood n'est pas coché : il est bien placé, et l'avertissement `ne correspond pas aux critères demandés` s'affiche ;
13. la console du navigateur ne montre aucune erreur.

- [ ] **Step 3: Corriger ce qui cloche, puis commiter**

Toute correction est commitée séparément, avec le défaut constaté dans le message :

```bash
git add -A
git commit -m "fix(web): <ce qui n'allait pas, tel que constaté dans la page>"
```

- [ ] **Step 4: Rendre compte**

Dire ce qui a été vérifié et sur quel export, et rappeler ce qui ne l'est toujours pas : **aucun XML produit par cet outil n'a jamais été réimporté dans Rekordbox.**
