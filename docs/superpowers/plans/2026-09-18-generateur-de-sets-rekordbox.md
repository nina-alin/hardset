# Générateur de sets Rekordbox — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produire, à partir d'un export XML de collection Rekordbox et de ses My Tags, une playlist ordonnée selon une courbe d'énergie choisie, éditable dans une interface web locale, puis réexportée en XML réimportable.

**Architecture :** Quatre couches avec une frontière stricte : `model.py` et `engine/` sont du Python pur (aucune E/S, aucun état global) et portent toute la logique musicale ; `rekordbox/` isole le format XML en lecture et en écriture ; `web/` n'ajoute aucune logique musicale, il expose le moteur en HTTP et sert une page unique. La configuration YAML tient les moods, les profils de courbe et les poids de scoring, si bien qu'ajouter un profil ne demande aucune modification de code.

**Tech Stack :** Python 3.12+, FastAPI + uvicorn, PyYAML, pytest. Front-end HTML + JavaScript vanilla servi par FastAPI, sans étape de build ni dépendance CDN. Courbe BPM en SVG dessiné en JavaScript.

**Spec de référence :** `docs/superpowers/specs/2026-09-18-generateur-de-sets-rekordbox-design.md`

**État de vérification du plan (2026-09-18) :** tous les blocs de code Python de ce plan
ont été extraits et exécutés ensemble hors du dépôt. Résultat : **144 tests passent,
1 est sauté** — `test_extrait_reel_est_exploitable`, qui attend la fixture d'export réel
produite en tâche 1. Les compteurs annoncés à chaque tâche sont donc des valeurs
observées, pas des estimations. Cela ne dispense de rien : la vérification bloquante du
format My Tags (tâche 1) et l'import réel dans Rekordbox (tâche 12) restent à faire, et
ce sont les deux seules choses que ce plan ne peut pas prouver seul.

## Global Constraints

- Python `>=3.12`. Dépendances runtime limitées à `fastapi`, `uvicorn`, `pyyaml` ; `pytest` et `httpx` en dev uniquement. Aucune dépendance front-end, aucun CDN.
- `hardset/model.py` et `hardset/engine/` : Python pur — aucune lecture ou écriture de fichier, aucun réseau, aucun état global, aucun `import` de `rekordbox/`, `web/` ou `yaml`.
- L'outil n'écrit **jamais** dans la base Rekordbox (`master.db`). La seule sortie est un fichier XML à importer.
- Un morceau porte **un seul** mood et **zéro ou plusieurs** genres. Mood absent ou multiple : morceau conservé dans la collection, exclu de la sélection, signalé en avertissement.
- Échelle de mood ordinale fermée 1→5, définie en configuration et non dans le code : `calme`, `dansant`, `un peu vénère`, `vénère`, `c'est du bruit`.
- Tout tag reconnu dans la liste des moods est le mood ; **tout autre tag est un genre**. Aucune liste de genres n'est maintenue.
- Comparaison des tags insensible à la casse, aux accents et aux espaces de bordure.
- Poids par défaut, en configuration : `bpm: 1.0`, `mood: 1.5`, `tonalite: 0.4`, `bpm_tolerance: 5.0`, `k: 5`. Temps de jeu par morceau par défaut : `120` s.
- Pénurie de morceaux éligibles : ce n'est **pas une erreur**. L'outil produit le set le plus long possible et émet un avertissement.
- Style du code, aligné sur `~/Projects/Personal/xdj-az-watch` : docstrings et commentaires en français, `from __future__ import annotations` en tête de module, `dataclass` et `Enum` plutôt que des dictionnaires, commentaires de section `# --- Titre ---` dans les tests.
- L'interface web n'est pas testée automatiquement (les routes de l'API le sont, la page ne l'est pas).

## Structure de fichiers

| Fichier | Responsabilité |
|---|---|
| `pyproject.toml` | Métadonnées, dépendances, `testpaths`, script `hardset` |
| `hardset.yaml` | Configuration livrée : moods, 4 profils, poids, chemin XML par défaut |
| `hardset/model.py` | `Track`, `Target`, `SetRequest`, `GeneratedSet`, `SetWarning`, `WarningCode`, `normalize_tag` |
| `hardset/config.py` | Chargement YAML → `Config`, `Profile`, `CurveSpec`, `Weights` |
| `hardset/rekordbox/reader.py` | Parsing du XML de collection, extraction des My Tags → `Collection` |
| `hardset/rekordbox/writer.py` | Écriture du XML `DJ_PLAYLISTS` de la playlist |
| `hardset/engine/harmony.py` | Normalisation Camelot, pénalité de transition |
| `hardset/engine/curves.py` | Types de courbe paramétriques, profil + durée → cibles |
| `hardset/engine/filtering.py` | Réduction de la collection aux morceaux éligibles |
| `hardset/engine/sequencing.py` | Coût, remplissage position par position, remplacement |
| `hardset/web/app.py` | Application FastAPI : routes API + service de la page |
| `hardset/web/static/index.html` | Page unique : formulaire, tracklist, avertissements, export |
| `hardset/web/static/app.js` | Appels API, rendu de la tracklist, actions de ligne |
| `hardset/web/static/curve.js` | Courbe BPM cible / obtenu en SVG |
| `hardset/web/static/style.css` | Mise en forme de la page |
| `hardset/cli.py` | Point d'entrée : lance uvicorn et ouvre le navigateur |
| `tools/inspect_collection.py` | Sonde de diagnostic du format d'export (tâche 1) |
| `tests/` | Un fichier de test par module du moteur, plus `test_api.py` |

**Écart assumé au spec :** le spec nomme la dataclasse d'avertissement `Warning`. Le plan la nomme `SetWarning` pour ne pas masquer le `Warning` natif de Python. Renommage cosmétique, sans effet sur le design.

---

### Task 1 : Amorce du projet et vérification bloquante du format My Tags

Le spec marque cette vérification comme bloquante : si les My Tags ne sont pas lisibles
dans l'export XML, seul `rekordbox/reader.py` change, mais il faut le savoir avant de
l'écrire. Aucun export Rekordbox n'existe sur la machine au moment de la rédaction de ce
plan : **cette tâche exige une action de Nina** (exporter la collection depuis Rekordbox).

**Files:**
- Create: `pyproject.toml`
- Create: `hardset/__init__.py`, `hardset/rekordbox/__init__.py`, `hardset/engine/__init__.py`, `hardset/web/__init__.py`
- Create: `tests/__init__.py`
- Create: `tools/inspect_collection.py`
- Create: `tests/fixtures/collection_extrait.xml` (extrait de l'export réel)

**Interfaces:**
- Consumes: rien.
- Produces: un environnement virtuel `.venv` avec `pytest` installé ; la fixture
  `tests/fixtures/collection_extrait.xml`, utilisée par les tâches 4 et 9 ; la réponse à
  la question « les My Tags sont-ils dans `Comments` sous la forme `/* a / b / c */` ? ».

- [ ] **Step 1: Écrire `pyproject.toml`**

```toml
[project]
name = "hardset"
version = "0.1.0"
description = "Générateur de sets DJ à partir des My Tags Rekordbox"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]

[project.scripts]
hardset = "hardset.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["hardset*"]

[tool.setuptools.package-data]
"hardset.web" = ["static/*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Créer l'arborescence des paquets et l'environnement**

```bash
cd ~/Projects/Personal/hardset
mkdir -p hardset/rekordbox hardset/engine hardset/web/static tools tests/fixtures
touch hardset/__init__.py hardset/rekordbox/__init__.py hardset/engine/__init__.py \
      hardset/web/__init__.py tests/__init__.py
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Attendu : `Successfully installed ... hardset-0.1.0 ...`. Toutes les commandes de test de
ce plan s'écrivent ensuite `.venv/bin/pytest ...`.

- [ ] **Step 3: Écrire la sonde de diagnostic**

`tools/inspect_collection.py` — script jetable mais complet, il ne sert qu'à répondre à la
question bloquante :

```python
"""Sonde de diagnostic d'un export XML Rekordbox.

Ne fait partie ni du paquet ni des tests : sert une seule fois, à vérifier que les
My Tags sont exploitables depuis le XML avant d'écrire le lecteur.

Usage : python3 tools/inspect_collection.py ~/rekordbox.xml
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

TAGS_RE = re.compile(r"/\*(.+?)\*/", re.DOTALL)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    path = Path(sys.argv[1]).expanduser()
    root = ElementTree.parse(path).getroot()
    tracks = root.findall(".//COLLECTION/TRACK")
    print(f"Fichier      : {path}")
    print(f"Morceaux     : {len(tracks)}")

    with_comments = [t for t in tracks if (t.get("Comments") or "").strip()]
    with_tags = [t for t in with_comments if TAGS_RE.search(t.get("Comments", ""))]
    print(f"Comments non vides : {len(with_comments)}")
    print(f"Comments avec /* ... */ : {len(with_tags)}")

    print("\n--- 10 valeurs brutes de Comments ---")
    for track in with_comments[:10]:
        print(f"  {track.get('Comments')!r}")

    tags: Counter[str] = Counter()
    for track in with_tags:
        inner = TAGS_RE.search(track.get("Comments", "")).group(1)
        for tag in inner.split("/"):
            if tag.strip():
                tags[tag.strip()] += 1
    print(f"\n--- Tags distincts : {len(tags)} ---")
    for tag, count in tags.most_common():
        print(f"  {count:5d}  {tag!r}")

    print("\n--- Formats de Tonality ---")
    tonalities = Counter((t.get("Tonality") or "").strip() for t in tracks)
    for value, count in tonalities.most_common(25):
        print(f"  {count:5d}  {value!r}")

    print("\n--- Attributs présents sur le premier TRACK ---")
    if tracks:
        for key, value in sorted(tracks[0].attrib.items()):
            print(f"  {key} = {value!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Obtenir l'export réel — point de synchronisation avec Nina**

Dans Rekordbox : `Fichier > Bibliothèque > Exporter la bibliothèque au format xml`
(rekordbox 6/7 : `File > Export Collection in xml format`), puis noter le chemin obtenu.

**Ne pas poursuivre sans ce fichier.** Il n'y a pas de contournement : le format exact des
My Tags à l'export n'est pas documenté de façon fiable, et tout le lecteur en dépend.

- [ ] **Step 5: Lancer la sonde et lire le verdict**

Run: `python3 tools/inspect_collection.py <chemin de l'export>`

Trois cas, un seul à retenir :

| Observation | Décision |
|---|---|
| `Comments avec /* ... */` proche du nombre de morceaux tagués, et les tags listés contiennent les 5 moods | **Nominal.** Continuer le plan tel quel. |
| `Comments` non vides mais sans `/* ... */`, ou séparateur différent | Adapter uniquement `TAGS_RE` et le séparateur dans la tâche 4. Le reste du plan est inchangé. |
| Aucun tag dans `Comments` | **Repli du spec §6 :** lire `master.db` via `pyrekordbox`. Seul `rekordbox/reader.py` est réécrit (tâche 4), en conservant la signature `read_collection(path, config) -> Collection`. Ajouter `pyrekordbox` aux dépendances. Les tâches 2, 3, 5 à 12 sont inchangées. |

Relever aussi les formats de `Tonality` réellement présents (classique, Camelot ou Open
Key) : la tâche 5 doit couvrir ceux-là en priorité.

- [ ] **Step 6: Fabriquer la fixture de test**

Extraire de l'export réel un fichier `tests/fixtures/collection_extrait.xml` contenant le
squelette `DJ_PLAYLISTS` complet et **8 à 12 nœuds `TRACK`** représentatifs, choisis pour
couvrir : un morceau à un seul mood et plusieurs genres, un à deux moods, un sans mood, un
sans `Tonality`, un dont `Comments` porte un commentaire libre **en plus** des tags, et
chaque format de `Tonality` observé. Remplacer les chemins `Location` par des chemins
fictifs, garder tous les autres attributs intacts.

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/Personal/hardset
cat >> .gitignore <<'EOF'
.venv/
*.egg-info/
EOF
git add pyproject.toml .gitignore hardset tools tests
git commit -m "chore: amorce du projet et sonde de format d'export Rekordbox"
```

---

### Task 2 : Modèle de données

**Files:**
- Create: `hardset/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes: rien (module sans dépendance, contrainte du spec §4).
- Produces:
  - `MOOD_MIN = 1`, `MOOD_MAX = 5`
  - `normalize_tag(value: str) -> str` — minuscules, accents retirés, espaces de bordure retirés
  - `Track(id, artist, title, bpm, camelot, duration_s, location, genres, mood, raw_attrs)`
    où `genres: tuple[str, ...]`, `mood: int | None`, `camelot: str | None`,
    `raw_attrs: dict[str, str]`
  - `Target(position: int, bpm: float, mood: float)`
  - `WarningCode` : `SHORTAGE`, `NO_MOOD`, `MULTIPLE_MOODS`, `NO_KEY`
  - `SetWarning(code: WarningCode, message: str, track_ids: tuple[str, ...] = ())`
  - `SetRequest(genres, moods, bpm_min, bpm_max, profile, duration_min, seconds_per_track=120, seed=None)`
    avec la propriété `track_count -> int`
  - `GeneratedSet(tracks: list[Track], targets: list[Target], warnings: list[SetWarning])`

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_model.py` :

```python
"""Tests du modèle : normalisation des tags et nombre de morceaux visé."""

import pytest

from hardset.model import SetRequest, normalize_tag


# --- Normalisation des tags ----------------------------------------------

@pytest.mark.parametrize(
    "brut, attendu",
    [
        ("Vénère", "venere"),
        ("  vénère  ", "venere"),
        ("VENERE", "venere"),
        ("C'est du bruit", "c'est du bruit"),
        ("un peu vénère", "un peu venere"),
        ("Hardcore", "hardcore"),
    ],
)
def test_normalize_tag(brut, attendu):
    assert normalize_tag(brut) == attendu


# --- Nombre de morceaux visé ---------------------------------------------

def make_request(**kwargs) -> SetRequest:
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


def test_track_count_90min_120s():
    assert make_request(duration_min=90).track_count == 45


def test_track_count_arrondi_inferieur():
    # 50 min à 180 s = 16,67 morceaux : on n'en vise pas 17.
    assert make_request(duration_min=50, seconds_per_track=180).track_count == 16


def test_track_count_minimum_un():
    assert make_request(duration_min=1, seconds_per_track=120).track_count == 1
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_model.py -v`
Attendu : FAIL — `ModuleNotFoundError: No module named 'hardset.model'`

- [ ] **Step 3: Écrire `hardset/model.py`**

```python
"""Modèle de données du générateur de sets.

Module sans dépendance : il ne connaît ni le XML Rekordbox, ni la configuration,
ni le web. Toutes les autres couches en dépendent.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum

# Bornes de l'échelle de mood. Les libellés vivent dans la configuration ;
# seule l'étendue de l'échelle est une constante du code.
MOOD_MIN = 1
MOOD_MAX = 5


def normalize_tag(value: str) -> str:
    """Forme comparable d'un tag : minuscules, sans accents, sans espaces de bordure.

    Permet de reconnaître « Vénère », « venere » et «  VÉNÈRE  » comme un seul tag.
    """
    decomposed = unicodedata.normalize("NFD", value.strip().lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class Track:
    """Un morceau de la collection, tel que lu dans l'export XML.

    `raw_attrs` porte l'intégralité des attributs du nœud TRACK d'origine : l'export
    les recopie sans les comprendre, ce qui évite toute perte d'information.
    """

    id: str
    artist: str
    title: str
    bpm: float
    camelot: str | None
    duration_s: int
    location: str
    genres: tuple[str, ...] = ()
    mood: int | None = None
    raw_attrs: dict[str, str] = field(default_factory=dict, compare=False)

    @property
    def label(self) -> str:
        return f"{self.artist} — {self.title}"


@dataclass(frozen=True)
class Target:
    """Cible visée à une position du set. `mood` n'est volontairement pas arrondi."""

    position: int
    bpm: float
    mood: float


class WarningCode(str, Enum):
    """Nature d'un avertissement, pour permettre un regroupement côté interface."""

    SHORTAGE = "shortage"                # moins de morceaux éligibles que demandé
    NO_MOOD = "no_mood"                  # morceau sans tag de mood
    MULTIPLE_MOODS = "multiple_moods"    # morceau portant plusieurs tags de mood
    NO_KEY = "no_key"                    # tonalité absente ou illisible


@dataclass(frozen=True)
class SetWarning:
    """Problème rencontré, à afficher sans interrompre la génération.

    Nommée `SetWarning` et non `Warning` pour ne pas masquer le type natif.
    """

    code: WarningCode
    message: str
    track_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SetRequest:
    """Le set demandé. `genres` ou `moods` vides valent « tous ».

    `seed` n'est pas exposée dans l'interface : elle ne sert qu'à rendre la
    génération reproductible dans les tests.
    """

    genres: frozenset[str]
    moods: frozenset[int]
    bpm_min: float
    bpm_max: float
    profile: str
    duration_min: int
    seconds_per_track: int = 120
    seed: int | None = None

    @property
    def track_count(self) -> int:
        """Nombre de morceaux visé, au moins 1."""
        return max(1, int(self.duration_min * 60 // self.seconds_per_track))


@dataclass
class GeneratedSet:
    """Résultat d'une génération : les morceaux dans l'ordre de jeu et leurs cibles."""

    tracks: list[Track] = field(default_factory=list)
    targets: list[Target] = field(default_factory=list)
    warnings: list[SetWarning] = field(default_factory=list)
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_model.py -v`
Attendu : PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add hardset/model.py tests/test_model.py
git commit -m "feat: modèle de données du générateur de sets"
```

---

### Task 3 : Configuration YAML

**Files:**
- Create: `hardset/config.py`
- Create: `hardset.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `hardset.model.MOOD_MAX`, `normalize_tag`.
- Produces:
  - `CurveSpec(type: str, params: dict[str, float])`
  - `Profile(key: str, label: str, bpm: CurveSpec, mood: CurveSpec)`
  - `Weights(bpm=1.0, mood=1.5, tonalite=0.4, bpm_tolerance=5.0, k=5)`
  - `Config(moods: tuple[str, ...], profils: dict[str, Profile], poids: Weights, collection_xml: str | None)`
    avec `Config.mood_value(tag: str) -> int | None` (1-based, comparaison normalisée)
  - `DEFAULT_CONFIG_PATH = Path("hardset.yaml")`
  - `load_config(path: Path | None = None) -> Config`
  - `ConfigError(Exception)`

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_config.py` :

```python
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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_config.py -v`
Attendu : FAIL — `ModuleNotFoundError: No module named 'hardset.config'`

- [ ] **Step 3: Écrire `hardset.yaml`**

```yaml
# Configuration du générateur de sets. Ajouter un profil ne demande aucune
# modification de code.

# Chemin de l'export XML proposé par défaut dans le formulaire.
collection_xml: ~/rekordbox.xml

# L'ordre définit l'échelle ordinale 1 → 5.
moods:
  - calme
  - dansant
  - un peu vénère
  - vénère
  - c'est du bruit

poids:
  bpm: 1.0
  mood: 1.5
  tonalite: 0.4
  bpm_tolerance: 5.0   # un écart de 5 BPM coûte 1 unité avant pondération
  k: 5                 # largeur du tirage aléatoire

profils:
  montee:
    label: "Montée"
    bpm:  {type: lineaire}
    mood: {type: lineaire}
  warmup-long:
    label: "Warm-up long"
    bpm:  {type: retarde, palier: 0.4}
    mood: {type: retarde, palier: 0.4}
  plateau:
    label: "Plateau"
    bpm:  {type: lineaire, depart: 0.7}
    mood: {type: lineaire, depart: 0.7}
  vagues:
    label: "Vagues"
    bpm:  {type: vagues, amplitude: 0.15, oscillations: 2.5}
    mood: {type: lineaire}
```

- [ ] **Step 4: Écrire `hardset/config.py`**

```python
"""Chargement de la configuration YAML : moods, profils de courbe, poids.

La configuration porte tout ce qui relève du goût musical, pour qu'ajouter un
profil ou renommer un mood ne demande pas de toucher au code.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from hardset.model import MOOD_MAX, normalize_tag

DEFAULT_CONFIG_PATH = Path("hardset.yaml")

# Types de courbe reconnus, et paramètres admis pour chacun (cf. tâche 5).
CURVE_PARAMS: dict[str, set[str]] = {
    "lineaire": {"depart", "arrivee"},
    "retarde": {"palier"},
    "vagues": {"amplitude", "oscillations"},
}


class ConfigError(Exception):
    """Configuration illisible ou incohérente."""


@dataclass(frozen=True)
class CurveSpec:
    """Une courbe de progression : un type et ses paramètres."""

    type: str
    params: dict[str, float]


@dataclass(frozen=True)
class Profile:
    """Un profil d'évolution : une courbe pour le BPM, une pour le mood."""

    key: str
    label: str
    bpm: CurveSpec
    mood: CurveSpec


@dataclass(frozen=True)
class Weights:
    """Poids du calcul de coût et largeur du tirage."""

    bpm: float = 1.0
    mood: float = 1.5
    tonalite: float = 0.4
    bpm_tolerance: float = 5.0
    k: int = 5


@dataclass(frozen=True)
class Config:
    moods: tuple[str, ...]
    profils: dict[str, Profile]
    poids: Weights = Weights()
    collection_xml: str | None = None

    def mood_value(self, tag: str) -> int | None:
        """Position 1-based du tag dans l'échelle, ou `None` si ce n'est pas un mood."""
        cible = normalize_tag(tag)
        if not cible:
            return None
        for index, mood in enumerate(self.moods, start=1):
            if normalize_tag(mood) == cible:
                return index
        return None


def _curve(raw: Any, chemin: str) -> CurveSpec:
    if not isinstance(raw, dict) or "type" not in raw:
        raise ConfigError(f"{chemin} : une courbe doit être un objet avec un 'type'")
    type_ = str(raw["type"])
    if type_ not in CURVE_PARAMS:
        connus = ", ".join(sorted(CURVE_PARAMS))
        raise ConfigError(f"{chemin} : type de courbe '{type_}' inconnu (attendu : {connus})")
    params = {k: float(v) for k, v in raw.items() if k != "type"}
    inconnus = set(params) - CURVE_PARAMS[type_]
    if inconnus:
        raise ConfigError(f"{chemin} : paramètres inconnus pour '{type_}' : {sorted(inconnus)}")
    return CurveSpec(type=type_, params=params)


def load_config(path: Path | None = None) -> Config:
    """Charge la configuration. Les poids absents gardent leur valeur par défaut."""
    chemin = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration introuvable : {chemin}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML illisible dans {chemin} : {exc}") from exc

    moods = tuple(str(m) for m in raw.get("moods") or ())
    if not moods:
        raise ConfigError("la configuration doit définir au moins un mood")
    if len(moods) > MOOD_MAX:
        raise ConfigError(f"l'échelle de mood est limitée à {MOOD_MAX} valeurs, {len(moods)} fournies")

    profils_raw = raw.get("profils") or {}
    if not profils_raw:
        raise ConfigError("la configuration doit définir au moins un profil")
    profils = {
        cle: Profile(
            key=cle,
            label=str(corps.get("label", cle)),
            bpm=_curve(corps.get("bpm"), f"profils.{cle}.bpm"),
            mood=_curve(corps.get("mood"), f"profils.{cle}.mood"),
        )
        for cle, corps in profils_raw.items()
    }

    poids = Weights()
    for champ, valeur in (raw.get("poids") or {}).items():
        if not hasattr(poids, champ):
            raise ConfigError(f"poids.{champ} : poids inconnu")
        poids = replace(poids, **{champ: int(valeur) if champ == "k" else float(valeur)})

    collection = raw.get("collection_xml")
    return Config(
        moods=moods,
        profils=profils,
        poids=poids,
        collection_xml=str(collection) if collection else None,
    )
```

- [ ] **Step 5: Lancer les tests pour vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_config.py -v`
Attendu : PASS, 12 tests. Les tests qui appellent `load_config()` sans argument lisent
`hardset.yaml` à la racine : lancer `pytest` depuis la racine du dépôt.

- [ ] **Step 6: Commit**

```bash
git add hardset/config.py hardset.yaml tests/test_config.py
git commit -m "feat: chargement de la configuration YAML (moods, profils, poids)"
```

---

### Task 4 : Tonalité — normalisation Camelot et pénalité de transition

**Écart assumé à l'ordre du spec §13 :** harmonie avant lecteur. `Track.camelot` est
stocké normalisé, donc `reader.py` appelle `to_camelot()` : la dépendance impose cet ordre.

**Convention de position, valable pour tout le plan :** `Target.position`, l'index dans
`GeneratedSet.tracks` et les positions échangées avec l'API sont **0-based**. Seule
l'interface affiche `position + 1`.

**Files:**
- Create: `hardset/engine/harmony.py`
- Test: `tests/test_harmony.py`

**Interfaces:**
- Consumes: rien du projet (Python pur, stdlib seulement).
- Produces:
  - `to_camelot(tonality: str | None) -> str | None` — rend `"1A"`…`"12B"` ou `None`
  - `key_penalty(previous: str | None, candidate: str | None) -> float` — 0, 0.5, 1 ou 2

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_harmony.py` :

```python
"""Tests de la normalisation des tonalités et de la pénalité de transition.

Les valeurs de référence : Camelot 8B = Do majeur, 8A = La mineur ;
Open Key 1d = Do majeur, 1m = La mineur.
"""

import pytest

from hardset.engine.harmony import key_penalty, to_camelot


# --- Normalisation Camelot -----------------------------------------------

@pytest.mark.parametrize(
    "brut, attendu",
    [
        # Notation classique, mineur
        ("Am", "8A"),
        ("A min", "8A"),
        ("Aminor", "8A"),
        ("F#m", "11A"),
        ("Gbm", "11A"),
        ("Dm", "7A"),
        ("Ebm", "2A"),
        # Notation classique, majeur
        ("C", "8B"),
        ("Cmaj", "8B"),
        ("A", "11B"),
        ("F#", "2B"),
        ("Bb", "6B"),
        # Déjà en Camelot
        ("8A", "8A"),
        ("12B", "12B"),
        ("8a", "8A"),
        # Open Key
        ("1m", "8A"),
        ("1d", "8B"),
        ("6d", "1B"),
        ("12m", "7A"),
        # Illisible ou absent
        ("", None),
        ("   ", None),
        (None, None),
        ("13A", None),
        ("0B", None),
        ("H#", None),
        ("inconnu", None),
    ],
)
def test_to_camelot(brut, attendu):
    assert to_camelot(brut) == attendu


def test_espaces_et_casse_tolerees():
    assert to_camelot("  am  ") == "8A"


# --- Pénalité de transition (tableau du spec §7) -------------------------

def test_meme_cle():
    assert key_penalty("8A", "8A") == 0


@pytest.mark.parametrize("voisin", ["9A", "7A"])
def test_voisin_sur_la_roue(voisin):
    assert key_penalty("8A", voisin) == 0


def test_voisin_traverse_le_zero():
    assert key_penalty("12A", "1A") == 0


def test_relatif_majeur_mineur():
    assert key_penalty("8A", "8B") == 0


@pytest.mark.parametrize("deux_crans", ["10A", "6A"])
def test_deux_crans_sur_la_roue(deux_crans):
    assert key_penalty("8A", deux_crans) == 1


@pytest.mark.parametrize("lointain", ["2A", "5A", "3B", "11B"])
def test_tout_autre_cas(lointain):
    assert key_penalty("8A", lointain) == 2


@pytest.mark.parametrize(
    "avant, apres",
    [("8A", None), (None, "8A"), (None, None)],
)
def test_cle_inconnue(avant, apres):
    assert key_penalty(avant, apres) == 0.5
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_harmony.py -v`
Attendu : FAIL — `ModuleNotFoundError: No module named 'hardset.engine.harmony'`

- [ ] **Step 3: Écrire `hardset/engine/harmony.py`**

```python
"""Tonalités : normalisation en Camelot et pénalité d'enchaînement.

Rekordbox écrit `Tonality` en notation classique, en Camelot ou en Open Key selon
les préférences de l'utilisateur. Tout est ramené en Camelot (1A–12B), qui rend la
proximité harmonique lisible comme une distance sur une roue.

La pénalité ne porte que sur la transition immédiate : on favorise des
enchaînements deux à deux, on ne cherche pas à tenir une tonalité sur la durée.
"""

from __future__ import annotations

import re

# Camelot de chaque note, en majeur (lettre B) puis en mineur (lettre A).
_MAJOR: dict[str, int] = {
    "c": 8, "g": 9, "d": 10, "a": 11, "e": 12, "b": 1,
    "f#": 2, "gb": 2, "db": 3, "c#": 3, "ab": 4, "g#": 4,
    "eb": 5, "d#": 5, "bb": 6, "a#": 6, "f": 7,
}
_MINOR: dict[str, int] = {
    "a": 8, "e": 9, "b": 10, "f#": 11, "gb": 11, "c#": 12, "db": 12,
    "g#": 1, "ab": 1, "d#": 2, "eb": 2, "bb": 3, "a#": 3,
    "f": 4, "c": 5, "g": 6, "d": 7,
}

_MINOR_SUFFIXES = {"m", "min", "minor", "mi"}
_MAJOR_SUFFIXES = {"", "maj", "major", "ma"}

_CAMELOT_RE = re.compile(r"^(\d{1,2})([ab])$")
_OPEN_KEY_RE = re.compile(r"^(\d{1,2})([dm])$")
_CLASSIC_RE = re.compile(r"^([a-g][#b]?)(.*)$")


def to_camelot(tonality: str | None) -> str | None:
    """Ramène une tonalité en Camelot (`"1A"`–`"12B"`), ou `None` si illisible.

    Une valeur illisible n'écarte pas le morceau : elle lui donne simplement une
    pénalité neutre au moment du séquençage.
    """
    if not tonality:
        return None
    brut = tonality.strip().lower().replace(" ", "")
    if not brut:
        return None

    # Déjà en Camelot (« 8A »). Testé avant Open Key : « 8a » n'est pas ambigu.
    match = _CAMELOT_RE.match(brut)
    if match:
        numero, lettre = int(match.group(1)), match.group(2).upper()
        return f"{numero}{lettre}" if 1 <= numero <= 12 else None

    # Open Key (« 1m », « 6d ») : le numéro est décalé de 7 crans vers Camelot.
    match = _OPEN_KEY_RE.match(brut)
    if match:
        numero, mode = int(match.group(1)), match.group(2)
        if not 1 <= numero <= 12:
            return None
        camelot = ((numero + 6) % 12) + 1
        return f"{camelot}{'A' if mode == 'm' else 'B'}"

    # Notation classique (« Am », « F#m », « Bb », « Cmaj »).
    match = _CLASSIC_RE.match(brut)
    if match:
        note, suffixe = match.group(1), match.group(2)
        if suffixe in _MINOR_SUFFIXES and note in _MINOR:
            return f"{_MINOR[note]}A"
        if suffixe in _MAJOR_SUFFIXES and note in _MAJOR:
            return f"{_MAJOR[note]}B"
    return None


def _split(camelot: str) -> tuple[int, str]:
    return int(camelot[:-1]), camelot[-1]


def key_penalty(previous: str | None, candidate: str | None) -> float:
    """Coût harmonique de l'enchaînement `previous` → `candidate`.

    Une clé inconnue vaut 0,5 : ni récompense, ni exclusion.
    """
    if previous is None or candidate is None:
        return 0.5

    numero_avant, lettre_avant = _split(previous)
    numero_apres, lettre_apres = _split(candidate)

    if lettre_avant != lettre_apres:
        # Relatif majeur / mineur : même chiffre, autre lettre.
        return 0 if numero_avant == numero_apres else 2

    ecart = (numero_apres - numero_avant) % 12
    distance = min(ecart, 12 - ecart)
    if distance <= 1:      # même clé ou voisin immédiat
        return 0
    if distance == 2:
        return 1
    return 2
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_harmony.py -v`
Attendu : PASS, 41 tests.

- [ ] **Step 5: Commit**

```bash
git add hardset/engine/harmony.py tests/test_harmony.py
git commit -m "feat: normalisation Camelot et pénalité de transition harmonique"
```

---

### Task 5 : Lecture du XML de collection et des My Tags

**Files:**
- Create: `hardset/rekordbox/reader.py`
- Test: `tests/test_reader.py`
- Use: `tests/fixtures/collection_extrait.xml` (tâche 1)

**Interfaces:**
- Consumes: `Track`, `SetWarning`, `WarningCode`, `normalize_tag` (tâche 2) ;
  `Config.mood_value` (tâche 3) ; `to_camelot` (tâche 4).
- Produces:
  - `parse_my_tags(comments: str | None) -> tuple[str, ...]` — tags dans leur casse d'origine
  - `Collection(tracks: tuple[Track, ...], warnings: tuple[SetWarning, ...])` avec
    `genres -> tuple[str, ...]` (tri alphabétique, casse d'origine) et
    `bpm_range -> tuple[float, float]`
  - `read_collection(path: Path, config: Config) -> Collection`
  - `CollectionError(Exception)`

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_reader.py`. Les deux premiers blocs ne dépendent pas de la fixture ; le
dernier la lit et **doit être ajusté aux valeurs réelles** de l'extrait produit en tâche 1.

```python
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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_reader.py -v`
Attendu : FAIL — `ModuleNotFoundError: No module named 'hardset.rekordbox.reader'`

- [ ] **Step 3: Écrire `hardset/rekordbox/reader.py`**

```python
"""Lecture d'un export XML de collection Rekordbox.

Rekordbox écrit les My Tags dans l'attribut `Comments` du nœud TRACK, sous la forme
`/* tag / tag */`, éventuellement entourée d'un commentaire libre. Le XML ne
transporte pas la catégorie du tag : la distinction genre / mood se fait donc par la
configuration — tout tag reconnu comme mood est le mood, **tout autre tag est un genre**.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from hardset.config import Config
from hardset.engine.harmony import to_camelot
from hardset.model import SetWarning, Track, WarningCode, normalize_tag

# Bloc de My Tags dans `Comments`. Le format exact est vérifié en tâche 1 ; si
# l'export réel diffère, c'est cette expression et le séparateur qui changent.
_TAGS_RE = re.compile(r"/\*(.*?)\*/", re.DOTALL)
_TAG_SEPARATOR = "/"


class CollectionError(Exception):
    """Export XML introuvable ou illisible."""


def parse_my_tags(comments: str | None) -> tuple[str, ...]:
    """Tags contenus dans `Comments`, dans leur casse d'origine.

    Les tags sont rendus non normalisés : l'interface les affiche tels que Nina les
    a écrits dans Rekordbox. La normalisation ne sert qu'aux comparaisons.
    """
    if not comments:
        return ()
    match = _TAGS_RE.search(comments)
    if not match:
        return ()
    return tuple(
        tag.strip()
        for tag in match.group(1).split(_TAG_SEPARATOR)
        if tag.strip()
    )


def _float(value: str | None) -> float:
    try:
        return float(value) if value else 0.0
    except ValueError:
        return 0.0


def _int(value: str | None) -> int:
    try:
        return int(float(value)) if value else 0
    except ValueError:
        return 0


@dataclass(frozen=True)
class Collection:
    """La collection lue, avec les avertissements relevés à la lecture."""

    tracks: tuple[Track, ...]
    warnings: tuple[SetWarning, ...] = ()

    @property
    def genres(self) -> tuple[str, ...]:
        """Genres réellement présents, triés, dédoublonnés à la normalisation."""
        vus: dict[str, str] = {}
        for track in self.tracks:
            for genre in track.genres:
                vus.setdefault(normalize_tag(genre), genre)
        return tuple(sorted(vus.values(), key=normalize_tag))

    @property
    def bpm_range(self) -> tuple[float, float]:
        """Plage de BPM des morceaux exploitables, pour préremplir le formulaire."""
        bpms = [t.bpm for t in self.tracks if t.bpm > 0]
        return (min(bpms), max(bpms)) if bpms else (0.0, 0.0)


def read_collection(path: Path, config: Config) -> Collection:
    """Lit l'export XML et classe les tags de chaque morceau en genres et mood.

    Un morceau sans mood, ou portant plusieurs moods, est **conservé** dans la
    collection avec `mood = None` : il sera écarté à la sélection, et signalé ici.
    """
    chemin = Path(path).expanduser()
    try:
        racine = ElementTree.parse(chemin).getroot()
    except FileNotFoundError as exc:
        raise CollectionError(f"export introuvable : {chemin}") from exc
    except ElementTree.ParseError as exc:
        raise CollectionError(f"XML illisible dans {chemin} : {exc}") from exc

    tracks: list[Track] = []
    sans_mood: list[str] = []
    moods_multiples: list[str] = []
    sans_cle: list[str] = []

    for noeud in racine.findall("./COLLECTION/TRACK"):
        attrs = dict(noeud.attrib)
        identifiant = attrs.get("TrackID", "")
        if not identifiant:
            continue  # un nœud sans TrackID ne peut pas être référencé en playlist

        genres: list[str] = []
        moods: list[int] = []
        for tag in parse_my_tags(attrs.get("Comments")):
            valeur = config.mood_value(tag)
            if valeur is None:
                genres.append(tag)
            else:
                moods.append(valeur)

        if len(moods) == 1:
            mood = moods[0]
        else:
            mood = None
            (moods_multiples if moods else sans_mood).append(identifiant)

        camelot = to_camelot(attrs.get("Tonality"))
        if camelot is None:
            sans_cle.append(identifiant)

        tracks.append(
            Track(
                id=identifiant,
                artist=attrs.get("Artist", ""),
                title=attrs.get("Name", ""),
                bpm=_float(attrs.get("AverageBpm")),
                camelot=camelot,
                duration_s=_int(attrs.get("TotalTime")),
                location=attrs.get("Location", ""),
                genres=tuple(genres),
                mood=mood,
                raw_attrs=attrs,
            )
        )

    avertissements: list[SetWarning] = []
    for code, ids, gabarit in (
        (WarningCode.MULTIPLE_MOODS, moods_multiples, "{n} morceaux portent plusieurs moods et sont écartés"),
        (WarningCode.NO_MOOD, sans_mood, "{n} morceaux sans mood sont écartés"),
        (WarningCode.NO_KEY, sans_cle, "{n} morceaux sans tonalité analysée"),
    ):
        if ids:
            avertissements.append(
                SetWarning(code=code, message=gabarit.format(n=len(ids)), track_ids=tuple(ids))
            )

    return Collection(tracks=tuple(tracks), warnings=tuple(avertissements))
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_reader.py -v`
Attendu : PASS. Le test `test_extrait_reel_est_exploitable` doit passer, **pas être
sauté** : s'il est sauté, la fixture de la tâche 1 manque et la vérification bloquante
n'a pas eu lieu.

- [ ] **Step 5: Commit**

```bash
git add hardset/rekordbox/reader.py tests/test_reader.py tests/fixtures/collection_extrait.xml
git commit -m "feat: lecture du XML de collection et des My Tags Rekordbox"
```

---

### Task 6 : Courbes et cibles

**Files:**
- Create: `hardset/engine/curves.py`
- Test: `tests/test_curves.py`

**Interfaces:**
- Consumes: `CurveSpec`, `Profile` (tâche 3) ; `SetRequest`, `Target`, `MOOD_MIN`, `MOOD_MAX` (tâche 2).
- Produces:
  - `curve_fn(spec: CurveSpec) -> Callable[[float], float]` — rend une progression `[0,1] → [0,1]`
  - `build_targets(request: SetRequest, profile: Profile, count: int) -> list[Target]`
  - `CurveError(Exception)`

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_curves.py` :

```python
"""Tests des courbes de progression et du calcul des cibles."""

import pytest

from hardset.config import CurveSpec, Profile
from hardset.engine.curves import build_targets, curve_fn
from hardset.model import SetRequest


def profil(bpm: CurveSpec, mood: CurveSpec | None = None) -> Profile:
    return Profile(key="test", label="Test", bpm=bpm, mood=mood or bpm)


def requete(**kwargs) -> SetRequest:
    base = dict(
        genres=frozenset(),
        moods=frozenset(),
        bpm_min=150.0,
        bpm_max=200.0,
        profile="test",
        duration_min=20,
    )
    base.update(kwargs)
    return SetRequest(**base)


# --- Types de courbe -----------------------------------------------------

def test_lineaire_par_defaut_va_de_0_a_1():
    f = curve_fn(CurveSpec("lineaire", {}))
    assert f(0.0) == pytest.approx(0.0)
    assert f(0.5) == pytest.approx(0.5)
    assert f(1.0) == pytest.approx(1.0)


def test_lineaire_avec_depart():
    f = curve_fn(CurveSpec("lineaire", {"depart": 0.7}))
    assert f(0.0) == pytest.approx(0.7)
    assert f(1.0) == pytest.approx(1.0)


def test_retarde_reste_a_zero_avant_le_palier():
    f = curve_fn(CurveSpec("retarde", {"palier": 0.4}))
    assert f(0.0) == pytest.approx(0.0)
    assert f(0.39) == pytest.approx(0.0)
    assert f(0.4) == pytest.approx(0.0)
    assert f(0.7) == pytest.approx(0.5)
    assert f(1.0) == pytest.approx(1.0)


def test_vagues_oscille_et_reste_borne():
    f = curve_fn(CurveSpec("vagues", {"amplitude": 0.15, "oscillations": 2.5}))
    valeurs = [f(i / 50) for i in range(51)]
    assert all(0.0 <= v <= 1.0 for v in valeurs)
    # Une vague, c'est au moins une redescente.
    assert any(b < a for a, b in zip(valeurs, valeurs[1:]))


def test_type_inconnu_refuse():
    with pytest.raises(Exception):
        curve_fn(CurveSpec("exponentiel", {}))


# --- Cibles --------------------------------------------------------------

def test_cibles_encadrent_la_plage_bpm():
    cibles = build_targets(requete(), profil(CurveSpec("lineaire", {})), 10)
    assert len(cibles) == 10
    assert [c.position for c in cibles] == list(range(10))
    assert cibles[0].bpm == pytest.approx(150.0)
    assert cibles[-1].bpm == pytest.approx(200.0)


def test_mood_cible_non_arrondi():
    cibles = build_targets(requete(), profil(CurveSpec("lineaire", {})), 3)
    assert cibles[1].mood == pytest.approx(3.0)   # milieu de 1 → 5
    assert isinstance(cibles[1].mood, float)


def test_mood_cible_borne_par_les_moods_demandes():
    cibles = build_targets(requete(moods=frozenset({2, 3})), profil(CurveSpec("lineaire", {})), 5)
    assert cibles[0].mood == pytest.approx(2.0)
    assert cibles[-1].mood == pytest.approx(3.0)


def test_une_seule_position():
    cibles = build_targets(requete(), profil(CurveSpec("lineaire", {})), 1)
    assert len(cibles) == 1
    assert cibles[0].bpm == pytest.approx(150.0)   # t = 0


def test_count_nul_donne_une_liste_vide():
    assert build_targets(requete(), profil(CurveSpec("lineaire", {})), 0) == []


def test_profil_vagues_redescend():
    cibles = build_targets(
        requete(),
        profil(CurveSpec("vagues", {"amplitude": 0.15, "oscillations": 2.5}),
               CurveSpec("lineaire", {})),
        40,
    )
    bpms = [c.bpm for c in cibles]
    assert any(b < a for a, b in zip(bpms, bpms[1:]))
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_curves.py -v`
Attendu : FAIL — `ModuleNotFoundError: No module named 'hardset.engine.curves'`

- [ ] **Step 3: Écrire `hardset/engine/curves.py`**

```python
"""Courbes d'évolution : d'un profil et d'une durée vers une liste de cibles.

Trois types de courbe paramétriques, et pas de code arbitraire en configuration :
un profil décrit une intention musicale, il n'exécute rien.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from hardset.config import CurveSpec, Profile
from hardset.model import MOOD_MAX, MOOD_MIN, SetRequest, Target


class CurveError(Exception):
    """Type de courbe inconnu."""


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def curve_fn(spec: CurveSpec) -> Callable[[float], float]:
    """Traduit une courbe de configuration en fonction de progression `[0,1] → [0,1]`."""
    if spec.type == "lineaire":
        depart = spec.params.get("depart", 0.0)
        arrivee = spec.params.get("arrivee", 1.0)
        return lambda t: _clamp(depart + t * (arrivee - depart))

    if spec.type == "retarde":
        palier = min(max(spec.params.get("palier", 0.0), 0.0), 0.99)
        return lambda t: _clamp(0.0 if t <= palier else (t - palier) / (1.0 - palier))

    if spec.type == "vagues":
        amplitude = spec.params.get("amplitude", 0.15)
        oscillations = spec.params.get("oscillations", 2.0)
        return lambda t: _clamp(t + amplitude * math.sin(2 * math.pi * oscillations * t))

    raise CurveError(f"type de courbe '{spec.type}' inconnu")


def build_targets(request: SetRequest, profile: Profile, count: int) -> list[Target]:
    """Cible (BPM, mood) de chaque position du set.

    `mood` reste un flottant : un set peut viser « entre dansant et un peu vénère ».
    """
    if count <= 0:
        return []

    p_bpm = curve_fn(profile.bpm)
    p_mood = curve_fn(profile.mood)

    # Sans mood demandé, la courbe balaie toute l'échelle.
    mood_min = min(request.moods) if request.moods else MOOD_MIN
    mood_max = max(request.moods) if request.moods else MOOD_MAX

    cibles: list[Target] = []
    for i in range(count):
        t = i / max(count - 1, 1)
        cibles.append(
            Target(
                position=i,
                bpm=request.bpm_min + p_bpm(t) * (request.bpm_max - request.bpm_min),
                mood=mood_min + p_mood(t) * (mood_max - mood_min),
            )
        )
    return cibles
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_curves.py -v`
Attendu : PASS, 11 tests.

- [ ] **Step 5: Commit**

```bash
git add hardset/engine/curves.py tests/test_curves.py
git commit -m "feat: courbes de progression et calcul des cibles du set"
```

---

### Task 7 : Filtrage des morceaux éligibles

**Files:**
- Create: `hardset/engine/filtering.py`
- Test: `tests/test_filtering.py`

**Interfaces:**
- Consumes: `Track`, `SetRequest`, `normalize_tag` (tâche 2).
- Produces: `eligible(tracks: Iterable[Track], request: SetRequest) -> list[Track]`

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_filtering.py` :

```python
"""Tests de l'éligibilité d'un morceau à une demande de set."""

from hardset.engine.filtering import eligible
from hardset.model import SetRequest, Track


def piste(**kwargs) -> Track:
    base = dict(
        id="1",
        artist="A",
        title="T",
        bpm=180.0,
        camelot="8A",
        duration_s=200,
        location="file://x",
        genres=("Hardcore",),
        mood=4,
    )
    base.update(kwargs)
    return Track(**base)


def requete(**kwargs) -> SetRequest:
    base = dict(
        genres=frozenset(),
        moods=frozenset(),
        bpm_min=170.0,
        bpm_max=190.0,
        profile="montee",
        duration_min=20,
    )
    base.update(kwargs)
    return SetRequest(**base)


# --- Mood ----------------------------------------------------------------

def test_mood_absent_exclu():
    assert eligible([piste(mood=None)], requete()) == []


def test_mood_hors_demande_exclu():
    assert eligible([piste(mood=1)], requete(moods=frozenset({4, 5}))) == []


def test_mood_demande_retenu():
    assert len(eligible([piste(mood=4)], requete(moods=frozenset({4, 5})))) == 1


# --- Genre ---------------------------------------------------------------

def test_sans_genre_demande_un_morceau_sans_genre_reste_eligible():
    assert len(eligible([piste(genres=())], requete())) == 1


def test_genre_demande_exclut_un_morceau_sans_genre():
    assert eligible([piste(genres=())], requete(genres=frozenset({"Hardcore"}))) == []


def test_un_seul_genre_commun_suffit():
    track = piste(genres=("Uptempo", "Frenchcore"))
    assert len(eligible([track], requete(genres=frozenset({"Hardcore", "Frenchcore"})))) == 1


def test_comparaison_de_genre_insensible_casse_accents():
    track = piste(genres=("Vénère Core",))
    assert len(eligible([track], requete(genres=frozenset({"venere core"})))) == 1


# --- BPM -----------------------------------------------------------------

def test_bornes_bpm_inclusives():
    assert len(eligible([piste(bpm=170.0), piste(bpm=190.0)], requete())) == 2


def test_hors_plage_bpm_exclu():
    assert eligible([piste(bpm=169.9), piste(bpm=190.1)], requete()) == []


# --- Combinaison ---------------------------------------------------------

def test_ordre_preserve():
    tracks = [piste(id="1"), piste(id="2"), piste(id="3")]
    assert [t.id for t in eligible(tracks, requete())] == ["1", "2", "3"]
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_filtering.py -v`
Attendu : FAIL — `ModuleNotFoundError: No module named 'hardset.engine.filtering'`

- [ ] **Step 3: Écrire `hardset/engine/filtering.py`**

```python
"""Réduction de la collection aux morceaux éligibles à une demande.

Un critère vide vaut « tous » et n'est alors pas appliqué du tout : un morceau sans
aucun genre reste éligible si aucun genre n'est demandé.
"""

from __future__ import annotations

from collections.abc import Iterable

from hardset.model import SetRequest, Track, normalize_tag


def eligible(tracks: Iterable[Track], request: SetRequest) -> list[Track]:
    """Morceaux retenus pour la sélection, dans leur ordre d'origine.

    Sont écartés : les morceaux sans mood unique (mood absent ou multiple, déjà
    ramené à `None` par le lecteur), ceux dont le mood ou le BPM sort de la demande,
    et — si des genres sont demandés — ceux qui n'en partagent aucun.
    """
    genres_demandes = {normalize_tag(g) for g in request.genres}

    retenus: list[Track] = []
    for track in tracks:
        if track.mood is None:
            continue
        if request.moods and track.mood not in request.moods:
            continue
        if not request.bpm_min <= track.bpm <= request.bpm_max:
            continue
        if genres_demandes:
            if not genres_demandes & {normalize_tag(g) for g in track.genres}:
                continue
        retenus.append(track)
    return retenus
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_filtering.py -v`
Attendu : PASS, 10 tests.

- [ ] **Step 5: Commit**

```bash
git add hardset/engine/filtering.py tests/test_filtering.py
git commit -m "feat: filtrage des morceaux éligibles (mood, genre, BPM)"
```

---

### Task 8 : Séquençage — coût, remplissage, remplacement

C'est le cœur musical de l'outil. Algorithme glouton, sans retour arrière : il peut
consommer tôt un morceau qui aurait mieux servi plus tard, et c'est accepté (spec §8).

**Files:**
- Create: `hardset/engine/sequencing.py`
- Test: `tests/test_sequencing.py`

**Interfaces:**
- Consumes: `Track`, `Target`, `SetRequest`, `GeneratedSet`, `SetWarning`, `WarningCode` (tâche 2) ;
  `Config`, `Weights` (tâche 3) ; `key_penalty` (tâche 4) ; `build_targets` (tâche 6) ;
  `eligible` (tâche 7).
- Produces:
  - `cost(candidate: Track, target: Target, previous: Track | None, weights: Weights) -> float`
  - `generate(tracks: Iterable[Track], request: SetRequest, config: Config) -> GeneratedSet`
  - `replace_at(generated: GeneratedSet, position: int, tracks: Iterable[Track], request: SetRequest, config: Config) -> GeneratedSet`
  - `SequencingError(Exception)` — profil inconnu ou position hors set

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_sequencing.py` :

```python
"""Tests du séquençage : respect de la courbe, pénurie, aléa, remplacement.

Le moteur étant pur, tous les cas se jouent sur des collections fabriquées en mémoire.
"""

import pytest

from hardset.config import load_config
from hardset.engine.sequencing import SequencingError, cost, generate, replace_at
from hardset.model import SetRequest, Target, Track, WarningCode

CONFIG = load_config()


def piste(id_: str, bpm: float, mood: int, camelot: str | None = "8A", genres=("Hardcore",)) -> Track:
    return Track(
        id=id_,
        artist=f"Artiste {id_}",
        title=f"Titre {id_}",
        bpm=bpm,
        camelot=camelot,
        duration_s=200,
        location=f"file://localhost/{id_}.mp3",
        genres=genres,
        mood=mood,
    )


def collection_dense(camelot: str | None = "8A") -> list[Track]:
    """Un morceau par BPM entier de 150 à 200 et par mood de 1 à 5 : 255 morceaux."""
    return [
        piste(f"{bpm}-{mood}", float(bpm), mood, camelot)
        for bpm in range(150, 201)
        for mood in range(1, 6)
    ]


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


# --- Calcul du coût ------------------------------------------------------

def test_cout_nul_sur_la_cible_exacte():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    assert cost(piste("x", 180.0, 4), cible, None, CONFIG.poids) == pytest.approx(0.0)


def test_ecart_bpm_divise_par_la_tolerance():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    # 5 BPM d'écart = 1 unité, pondérée par w_bpm = 1.0
    assert cost(piste("x", 185.0, 4), cible, None, CONFIG.poids) == pytest.approx(1.0)


def test_ecart_de_mood_pondere():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    # 1 cran de mood × w_mood = 1.5
    assert cost(piste("x", 180.0, 3), cible, None, CONFIG.poids) == pytest.approx(1.5)


def test_premiere_position_sans_penalite_harmonique():
    cible = Target(position=0, bpm=180.0, mood=4.0)
    # previous=None à la première position : pénalité 0, et non 0,5 (clé inconnue).
    assert cost(piste("x", 180.0, 4, camelot=None), cible, None, CONFIG.poids) == pytest.approx(0.0)


def test_penalite_harmonique_appliquee_ensuite():
    cible = Target(position=1, bpm=180.0, mood=4.0)
    precedent = piste("p", 180.0, 4, camelot="8A")
    candidat = piste("c", 180.0, 4, camelot="2A")   # lointain : pénalité 2
    assert cost(candidat, cible, precedent, CONFIG.poids) == pytest.approx(0.8)  # 2 × 0.4


# --- Respect de la courbe ------------------------------------------------

def test_montee_suit_la_cible_bpm():
    resultat = generate(collection_dense(), requete(duration_min=60), CONFIG)
    assert len(resultat.tracks) == 30
    ecarts = [
        abs(track.bpm - cible.bpm)
        for track, cible in zip(resultat.tracks, resultat.targets)
    ]
    assert max(ecarts) <= CONFIG.poids.bpm_tolerance


def test_le_mood_progresse():
    resultat = generate(collection_dense(), requete(duration_min=60), CONFIG)
    moods = [t.mood for t in resultat.tracks]
    tiers = len(moods) // 3
    premier = sum(moods[:tiers]) / tiers
    dernier = sum(moods[-tiers:]) / tiers
    assert premier < dernier


def test_profil_vagues_genere_sans_erreur():
    resultat = generate(collection_dense(), requete(profile="vagues"), CONFIG)
    assert len(resultat.tracks) == 30


# --- Pénurie -------------------------------------------------------------

def test_penurie_produit_le_set_le_plus_long_possible():
    pool = [piste(str(i), 150.0 + i, (i % 5) + 1) for i in range(28)]
    resultat = generate(pool, requete(duration_min=90), CONFIG)   # 45 demandés

    assert len(resultat.tracks) == 28
    assert len(resultat.targets) == 28
    avertissement = next(w for w in resultat.warnings if w.code == WarningCode.SHORTAGE)
    assert "45" in avertissement.message and "28" in avertissement.message


def test_aucun_avertissement_de_penurie_si_assez_de_morceaux():
    resultat = generate(collection_dense(), requete(duration_min=60), CONFIG)
    assert not [w for w in resultat.warnings if w.code == WarningCode.SHORTAGE]


def test_collection_vide_donne_un_set_vide():
    resultat = generate([], requete(), CONFIG)
    assert resultat.tracks == []
    assert any(w.code == WarningCode.SHORTAGE for w in resultat.warnings)


# --- Tonalité ------------------------------------------------------------

def test_collection_sans_tonalite_genere_quand_meme():
    resultat = generate(collection_dense(camelot=None), requete(), CONFIG)
    assert len(resultat.tracks) == 30
    assert all(t.camelot is None for t in resultat.tracks)


# --- Doublons et aléa ----------------------------------------------------

def test_aucun_doublon():
    resultat = generate(collection_dense(), requete(), CONFIG)
    ids = [t.id for t in resultat.tracks]
    assert len(ids) == len(set(ids))


def test_deux_generations_different():
    a = generate(collection_dense(), requete(seed=None), CONFIG)
    b = generate(collection_dense(), requete(seed=None), CONFIG)
    assert [t.id for t in a.tracks] != [t.id for t in b.tracks]


def test_graine_fixee_reproductible():
    a = generate(collection_dense(), requete(seed=42), CONFIG)
    b = generate(collection_dense(), requete(seed=42), CONFIG)
    assert [t.id for t in a.tracks] == [t.id for t in b.tracks]


# --- Remplacement d'une position -----------------------------------------

def test_remplacement_change_le_morceau():
    pool = collection_dense()
    resultat = generate(pool, requete(), CONFIG)
    avant = resultat.tracks[5].id

    remplace = replace_at(resultat, 5, pool, requete(seed=7), CONFIG)

    assert remplace.tracks[5].id != avant
    assert len(remplace.tracks) == len(resultat.tracks)
    # Les autres positions ne bougent pas.
    assert [t.id for t in remplace.tracks[:5]] == [t.id for t in resultat.tracks[:5]]
    assert [t.id for t in remplace.tracks[6:]] == [t.id for t in resultat.tracks[6:]]


def test_remplacement_sans_doublon():
    pool = collection_dense()
    resultat = generate(pool, requete(), CONFIG)
    remplace = replace_at(resultat, 0, pool, requete(seed=7), CONFIG)
    ids = [t.id for t in remplace.tracks]
    assert len(ids) == len(set(ids))


def test_remplacement_sans_candidat_laisse_le_set_intact():
    pool = [piste(str(i), 150.0 + i, (i % 5) + 1) for i in range(5)]
    resultat = generate(pool, requete(duration_min=10), CONFIG)   # 5 morceaux pour 5 places
    avant = [t.id for t in resultat.tracks]

    remplace = replace_at(resultat, 2, pool, requete(duration_min=10), CONFIG)

    assert [t.id for t in remplace.tracks] == avant
    assert any(w.code == WarningCode.SHORTAGE for w in remplace.warnings)


def test_position_hors_set_refusee():
    pool = collection_dense()
    resultat = generate(pool, requete(), CONFIG)
    with pytest.raises(SequencingError, match="position"):
        replace_at(resultat, 99, pool, requete(), CONFIG)


# --- Profil ---------------------------------------------------------------

def test_profil_inconnu_refuse():
    with pytest.raises(SequencingError, match="inexistant"):
        generate(collection_dense(), requete(profile="inexistant"), CONFIG)
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_sequencing.py -v`
Attendu : FAIL — `ModuleNotFoundError: No module named 'hardset.engine.sequencing'`

- [ ] **Step 3: Écrire `hardset/engine/sequencing.py`**

```python
"""Séquençage du set : remplissage position par position.

Pour chaque position, tous les morceaux encore disponibles sont notés, et le retenu
est tiré uniformément parmi les `k` de coût le plus faible. C'est la seule source
d'aléa : la courbe est toujours respectée, mais deux générations diffèrent.

L'algorithme est glouton et ne revient jamais en arrière. Sur quelques centaines de
titres l'effet est inaudible, et la tracklist reste éditable.
"""

from __future__ import annotations

import random
from collections.abc import Iterable

from hardset.config import Config, Weights
from hardset.engine.curves import build_targets
from hardset.engine.filtering import eligible
from hardset.engine.harmony import key_penalty
from hardset.model import GeneratedSet, SetRequest, SetWarning, Target, Track, WarningCode


class SequencingError(Exception):
    """Demande inexploitable : profil inconnu, position hors du set."""


def cost(candidate: Track, target: Target, previous: Track | None, weights: Weights) -> float:
    """Coût d'un candidat à une position donnée. Plus bas, mieux c'est.

    La première position n'a pas de prédécesseur : la pénalité harmonique y vaut 0,
    et non 0,5 — l'absence de voisin n'est pas une tonalité inconnue.
    """
    tolerance = weights.bpm_tolerance if weights.bpm_tolerance > 0 else 1.0
    penalite = 0.0 if previous is None else key_penalty(previous.camelot, candidate.camelot)
    mood = candidate.mood if candidate.mood is not None else target.mood
    return (
        weights.bpm * abs(candidate.bpm - target.bpm) / tolerance
        + weights.mood * abs(mood - target.mood)
        + weights.tonalite * penalite
    )


def _pick(
    pool: list[Track],
    target: Target,
    previous: Track | None,
    weights: Weights,
    rng: random.Random,
) -> Track:
    """Tire un morceau parmi les `k` moins coûteux et le retire du pool.

    Le tri secondaire par `id` rend le résultat reproductible à graine fixée, sans
    dépendre de l'ordre d'itération du pool.
    """
    notes = sorted(
        pool,
        key=lambda track: (cost(track, target, previous, weights), track.id),
    )
    choisi = rng.choice(notes[: max(1, weights.k)])
    pool.remove(choisi)
    return choisi


def _profile(request: SetRequest, config: Config):
    try:
        return config.profils[request.profile]
    except KeyError as exc:
        connus = ", ".join(sorted(config.profils))
        raise SequencingError(
            f"profil '{request.profile}' inexistant (disponibles : {connus})"
        ) from exc


def generate(tracks: Iterable[Track], request: SetRequest, config: Config) -> GeneratedSet:
    """Construit le set demandé, ou le plus long possible si les morceaux manquent."""
    profile = _profile(request, config)
    pool = eligible(tracks, request)

    vise = request.track_count
    count = min(vise, len(pool))

    avertissements: list[SetWarning] = []
    if count < vise:
        avertissements.append(
            SetWarning(
                code=WarningCode.SHORTAGE,
                message=f"{vise} morceaux demandés, {len(pool)} éligibles",
            )
        )

    targets = build_targets(request, profile, count)
    rng = random.Random(request.seed)

    retenus: list[Track] = []
    precedent: Track | None = None
    for target in targets:
        precedent = _pick(pool, target, precedent, config.poids, rng)
        retenus.append(precedent)

    return GeneratedSet(tracks=retenus, targets=targets, warnings=avertissements)


def replace_at(
    generated: GeneratedSet,
    position: int,
    tracks: Iterable[Track],
    request: SetRequest,
    config: Config,
) -> GeneratedSet:
    """Rejoue le tirage pour une seule position, en excluant le set en place.

    Le voisin précédent est le morceau effectivement en place à `position - 1`.
    Sans candidat disponible, le set est rendu intact avec un avertissement.
    """
    _profile(request, config)   # valide le profil avant toute autre chose
    if not 0 <= position < len(generated.tracks):
        raise SequencingError(
            f"position {position} hors du set (0 à {len(generated.tracks) - 1})"
        )

    deja_places = {track.id for track in generated.tracks}
    pool = [track for track in eligible(tracks, request) if track.id not in deja_places]

    target = generated.targets[position]
    precedent = generated.tracks[position - 1] if position > 0 else None

    if not pool:
        return GeneratedSet(
            tracks=list(generated.tracks),
            targets=list(generated.targets),
            warnings=[
                *generated.warnings,
                SetWarning(
                    code=WarningCode.SHORTAGE,
                    message=f"aucun remplaçant disponible à la position {position + 1}",
                ),
            ],
        )

    rng = random.Random(request.seed)
    remplacant = _pick(pool, target, precedent, config.poids, rng)

    nouveaux = list(generated.tracks)
    nouveaux[position] = remplacant
    return GeneratedSet(
        tracks=nouveaux,
        targets=list(generated.targets),
        warnings=list(generated.warnings),
    )
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_sequencing.py -v`
Attendu : PASS, 20 tests.

Si `test_deux_generations_different` échoue, c'est que le tirage n'est pas aléatoire :
vérifier que `rng.choice` porte bien sur les `k` premiers et non sur le seul minimum.

- [ ] **Step 5: Lancer toute la suite**

Run: `.venv/bin/pytest -v`
Attendu : PASS. À ce stade le moteur musical est complet et vérifié.

- [ ] **Step 6: Commit**

```bash
git add hardset/engine/sequencing.py tests/test_sequencing.py
git commit -m "feat: séquençage du set par coût, tirage parmi les k meilleurs"
```

---

### Task 9 : Export du XML de playlist

**Files:**
- Create: `hardset/rekordbox/writer.py`
- Test: `tests/test_writer.py`

**Interfaces:**
- Consumes: `Track`, `SetRequest` (tâche 2).
- Produces:
  - `build_playlist_xml(tracks: Sequence[Track], playlist_name: str) -> bytes`
  - `default_playlist_name(request: SetRequest, today: date | None = None) -> str`

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_writer.py` :

```python
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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_writer.py -v`
Attendu : FAIL — `ModuleNotFoundError: No module named 'hardset.rekordbox.writer'`

- [ ] **Step 3: Écrire `hardset/rekordbox/writer.py`**

```python
"""Écriture du XML de playlist réimportable dans Rekordbox.

Rekordbox exige que tout morceau référencé dans une playlist figure dans le bloc
COLLECTION du même fichier. Les nœuds TRACK sont donc recopiés depuis `raw_attrs`,
sans aucune modification : l'outil n'a pas à comprendre les attributs Rekordbox pour
les restituer.

L'import est additif : supprimer la playlist importée ne laisse aucune trace.
"""

from __future__ import annotations

import io
import re
from collections.abc import Sequence
from datetime import date
from xml.etree import ElementTree

from hardset.model import SetRequest, Track, normalize_tag


def _slug(value: str) -> str:
    """Forme utilisable dans un nom de fichier : sans accent, sans espace."""
    return re.sub(r"[^a-z0-9]+", "-", normalize_tag(value)).strip("-")


def default_playlist_name(request: SetRequest, today: date | None = None) -> str:
    """Nom proposé dans le formulaire : `{genres}-{profil}-{durée}min-{date}`."""
    jour = today or date.today()
    genres = "-".join(sorted(_slug(g) for g in request.genres)) if request.genres else "tous"
    return f"{genres}-{_slug(request.profile)}-{request.duration_min}min-{jour.isoformat()}"


def build_playlist_xml(tracks: Sequence[Track], playlist_name: str) -> bytes:
    """Construit le fichier DJ_PLAYLISTS contenant la collection du set et sa playlist.

    L'ordre de jeu est porté par les références de la playlist ; COLLECTION ne
    contient chaque morceau qu'une fois.
    """
    racine = ElementTree.Element("DJ_PLAYLISTS", {"Version": "1.0.0"})
    ElementTree.SubElement(
        racine,
        "PRODUCT",
        {"Name": "rekordbox", "Version": "6.0.0", "Company": "AlphaTheta"},
    )

    # COLLECTION : les nœuds d'origine, dédoublonnés, dans l'ordre de première
    # apparition. `raw_attrs` est recopié tel quel.
    uniques: dict[str, Track] = {}
    for track in tracks:
        uniques.setdefault(track.id, track)

    collection = ElementTree.SubElement(racine, "COLLECTION", {"Entries": str(len(uniques))})
    for track in uniques.values():
        attrs = dict(track.raw_attrs) or {
            "TrackID": track.id,
            "Name": track.title,
            "Artist": track.artist,
            "AverageBpm": f"{track.bpm:.2f}",
            "TotalTime": str(track.duration_s),
            "Location": track.location,
        }
        ElementTree.SubElement(collection, "TRACK", attrs)

    playlists = ElementTree.SubElement(racine, "PLAYLISTS")
    noeud_racine = ElementTree.SubElement(
        playlists, "NODE", {"Type": "0", "Name": "ROOT", "Count": "1"}
    )
    playlist = ElementTree.SubElement(
        noeud_racine,
        "NODE",
        {"Name": playlist_name, "Type": "1", "KeyType": "0", "Entries": str(len(tracks))},
    )
    for track in tracks:
        ElementTree.SubElement(playlist, "TRACK", {"Key": track.id})

    tampon = io.BytesIO()
    ElementTree.ElementTree(racine).write(tampon, encoding="UTF-8", xml_declaration=True)
    return tampon.getvalue()
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_writer.py -v`
Attendu : PASS, 10 tests.

- [ ] **Step 5: Vérifier l'import dans Rekordbox — point de synchronisation avec Nina**

Générer un fichier depuis un `python3 -c` d'une ligne n'a pas d'intérêt ici : l'export
sera exercé de bout en bout à la tâche 10. Noter simplement que **le premier import réel
dans Rekordbox doit être fait par Nina** avant de considérer la tâche 12 terminée
(`Fichier > Importer > Importer une playlist`), et qu'un import raté se supprime sans
laisser de trace.

- [ ] **Step 6: Commit**

```bash
git add hardset/rekordbox/writer.py tests/test_writer.py
git commit -m "feat: export du XML de playlist réimportable dans Rekordbox"
```

---

### Task 10 : API web et point d'entrée

**Choix d'architecture :** l'API est sans état côté set. Le client détient la tracklist
courante (il en supprime et en déplace des lignes) et renvoie la liste ordonnée des
`track_ids` pour un remplacement ou un export ; le serveur recalcule les cibles pour la
longueur reçue. Seule la collection lue est mise en cache, par chemin et date de
modification, pour ne pas reparser un gros XML à chaque clic.

**Files:**
- Create: `hardset/web/app.py`
- Create: `hardset/cli.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: tout ce qui précède — `load_config`, `read_collection`, `Collection`,
  `generate`, `replace_at`, `build_targets`, `build_playlist_xml`, `default_playlist_name`.
- Produces:
  - `create_app(config: Config) -> FastAPI`
  - Routes : `GET /`, `GET /api/config`, `POST /api/collection`, `POST /api/generate`,
    `POST /api/replace`, `POST /api/export`
  - `main() -> int` dans `cli.py`, exposé comme commande `hardset`

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_api.py` :

```python
"""Tests des routes de l'API. La page elle-même n'est pas testée (spec §12)."""

from pathlib import Path
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


def test_remplacement_position_invalide_renvoie_400(client, collection_xml):
    genere = client.post("/api/generate", json=corps(collection_xml)).json()
    ids = [t["id"] for t in genere["tracks"]]
    reponse = client.post("/api/replace", json=corps(collection_xml, track_ids=ids, position=99))
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
    assert "Mon set.xml" in reponse.headers["content-disposition"]

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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_api.py -v`
Attendu : FAIL — `ModuleNotFoundError: No module named 'hardset.web.app'`

- [ ] **Step 3: Écrire `hardset/web/app.py`**

```python
"""API locale et service de la page unique.

Cette couche n'ajoute aucune logique musicale : elle traduit des requêtes HTTP en
appels au moteur, et sérialise le résultat. Le set courant vit dans le navigateur ;
le serveur ne garde en mémoire que les collections lues.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hardset.config import Config
from hardset.engine.curves import build_targets
from hardset.engine.sequencing import SequencingError, generate, replace_at
from hardset.model import GeneratedSet, SetRequest, Track
from hardset.rekordbox.reader import Collection, CollectionError, read_collection
from hardset.rekordbox.writer import build_playlist_xml, default_playlist_name

STATIC = Path(__file__).parent / "static"


class CollectionPayload(BaseModel):
    path: str


class SetRequestPayload(CollectionPayload):
    genres: list[str] = Field(default_factory=list)
    moods: list[int] = Field(default_factory=list)
    bpm_min: float
    bpm_max: float
    profile: str
    duration_min: int
    seconds_per_track: int = 120

    def to_request(self) -> SetRequest:
        return SetRequest(
            genres=frozenset(self.genres),
            moods=frozenset(self.moods),
            bpm_min=self.bpm_min,
            bpm_max=self.bpm_max,
            profile=self.profile,
            duration_min=self.duration_min,
            seconds_per_track=self.seconds_per_track,
        )


class ReplacePayload(SetRequestPayload):
    track_ids: list[str]
    position: int


class ExportPayload(CollectionPayload):
    track_ids: list[str]
    playlist_name: str


def _track_payload(track: Track) -> dict:
    return {
        "id": track.id,
        "artist": track.artist,
        "title": track.title,
        "bpm": track.bpm,
        "camelot": track.camelot,
        "mood": track.mood,
        "genres": list(track.genres),
    }


def _set_payload(generated: GeneratedSet, collection: Collection, request: SetRequest) -> dict:
    aujourdhui = date.today()
    return {
        "tracks": [_track_payload(t) for t in generated.tracks],
        "targets": [
            {"position": c.position, "bpm": c.bpm, "mood": c.mood} for c in generated.targets
        ],
        "warnings": [
            {"code": w.code.value, "message": w.message, "track_ids": list(w.track_ids)}
            for w in (*collection.warnings, *generated.warnings)
        ],
        "playlist_name": default_playlist_name(request, aujourdhui),
        "date": aujourdhui.isoformat(),
    }


def create_app(config: Config) -> FastAPI:
    app = FastAPI(title="hardset", docs_url=None, redoc_url=None)

    # Collections lues, par chemin résolu et date de modification : rouvrir un gros
    # export à chaque clic serait inutilement lent, et le relire dès qu'il change
    # évite de servir des données périmées.
    cache: dict[tuple[str, float], Collection] = {}

    def charger(chemin_brut: str) -> Collection:
        chemin = Path(chemin_brut).expanduser()
        try:
            cle = (str(chemin.resolve()), chemin.stat().st_mtime)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"export introuvable : {chemin}") from exc
        if cle not in cache:
            try:
                cache.clear()   # une seule collection à la fois suffit
                cache[cle] = read_collection(chemin, config)
            except CollectionError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return cache[cle]

    def resoudre(collection: Collection, track_ids: list[str]) -> list[Track]:
        par_id = {track.id: track for track in collection.tracks}
        try:
            return [par_id[identifiant] for identifiant in track_ids]
        except KeyError as exc:
            raise HTTPException(
                status_code=400, detail=f"morceau {exc.args[0]} absent de la collection"
            ) from exc

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/config")
    def configuration() -> dict:
        return {
            "profils": [
                {"key": p.key, "label": p.label} for p in config.profils.values()
            ],
            "moods": [
                {"value": i, "label": label} for i, label in enumerate(config.moods, start=1)
            ],
            "collection_xml": config.collection_xml,
            "seconds_per_track": 120,
        }

    @app.post("/api/collection")
    def collection(payload: CollectionPayload) -> dict:
        lue = charger(payload.path)
        bpm_min, bpm_max = lue.bpm_range
        return {
            "path": payload.path,
            "track_count": len(lue.tracks),
            "genres": list(lue.genres),
            "bpm_min": bpm_min,
            "bpm_max": bpm_max,
            "warnings": [
                {"code": w.code.value, "message": w.message, "track_ids": list(w.track_ids)}
                for w in lue.warnings
            ],
        }

    @app.post("/api/generate")
    def generer(payload: SetRequestPayload) -> dict:
        lue = charger(payload.path)
        requete = payload.to_request()
        try:
            resultat = generate(lue.tracks, requete, config)
        except SequencingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _set_payload(resultat, lue, requete)

    @app.post("/api/replace")
    def remplacer(payload: ReplacePayload) -> dict:
        lue = charger(payload.path)
        requete = payload.to_request()
        tracks = resoudre(lue, payload.track_ids)
        try:
            profil = config.profils[requete.profile]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"profil '{requete.profile}' inexistant") from exc

        # Les cibles sont recalculées pour la longueur reçue : après une suppression,
        # la courbe se redistribue sur les positions restantes.
        courant = GeneratedSet(
            tracks=tracks,
            targets=build_targets(requete, profil, len(tracks)),
            warnings=[],
        )
        try:
            resultat = replace_at(courant, payload.position, lue.tracks, requete, config)
        except SequencingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _set_payload(resultat, lue, requete)

    @app.post("/api/export")
    def exporter(payload: ExportPayload) -> Response:
        lue = charger(payload.path)
        tracks = resoudre(lue, payload.track_ids)
        nom = payload.playlist_name.strip() or "set"
        return Response(
            content=build_playlist_xml(tracks, nom),
            media_type="application/xml",
            headers={"content-disposition": f'attachment; filename="{nom}.xml"'},
        )

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
```

- [ ] **Step 4: Créer un `index.html` minimal pour que la route `/` réponde**

La page complète est l'objet de la tâche 11 ; ce fichier n'existe ici que pour rendre
`GET /` testable. Écrire `hardset/web/static/index.html` :

```html
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><title>hardset</title></head>
<body><h1>hardset</h1></body>
</html>
```

- [ ] **Step 5: Lancer les tests pour vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_api.py -v`
Attendu : PASS, 12 tests.

- [ ] **Step 6: Écrire `hardset/cli.py`**

```python
"""Point d'entrée : lance le serveur local et ouvre le navigateur."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn

from hardset.config import ConfigError, DEFAULT_CONFIG_PATH, load_config
from hardset.web.app import create_app


def main() -> int:
    parseur = argparse.ArgumentParser(
        prog="hardset",
        description="Générateur de sets DJ à partir des My Tags Rekordbox",
    )
    parseur.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                         help=f"fichier de configuration (défaut : {DEFAULT_CONFIG_PATH})")
    parseur.add_argument("--host", default="127.0.0.1", help="interface d'écoute")
    parseur.add_argument("--port", type=int, default=8765, help="port d'écoute")
    parseur.add_argument("--no-browser", action="store_true",
                         help="ne pas ouvrir le navigateur au lancement")
    args = parseur.parse_args()

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration illisible : {exc}")
        return 1

    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        # Le navigateur s'ouvre une fois le serveur prêt à répondre.
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    print(f"hardset écoute sur {url}")
    uvicorn.run(create_app(config), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: Vérifier le lancement réel**

```bash
.venv/bin/hardset --no-browser --port 8765 &
sleep 2
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/
curl -s http://127.0.0.1:8765/api/config | head -c 200
kill %1
```

Attendu : `200`, puis un JSON contenant `"profils"` et `"moods"`.

- [ ] **Step 8: Commit**

```bash
git add hardset/web/app.py hardset/web/static/index.html hardset/cli.py tests/test_api.py
git commit -m "feat: API locale du générateur et commande hardset"
```

---

### Task 11 : Page unique — formulaire, tracklist, avertissements, export

Conformément au spec §12, l'interface n'est pas testée automatiquement : la vérification
est manuelle, dans le navigateur, et décrite à l'étape finale de la tâche.

**Files:**
- Modify: `hardset/web/static/index.html` (remplace le fichier minimal de la tâche 10)
- Create: `hardset/web/static/style.css`
- Create: `hardset/web/static/app.js`

**Interfaces:**
- Consumes: les routes de la tâche 10.
- Produces: `window.state` (`{config, collection, set, path}`) et la fonction
  `render()`, sur lesquelles la tâche 12 se branche.

- [ ] **Step 1: Écrire `hardset/web/static/index.html`**

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>hardset — générateur de sets</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <h1>hardset</h1>

  <section id="form" class="carte">
    <div class="ligne">
      <label for="path">Export XML de la collection</label>
      <input type="text" id="path" placeholder="~/rekordbox.xml">
      <button id="charger" type="button">Charger</button>
      <span id="etat-collection" class="discret"></span>
    </div>

    <div class="colonnes">
      <fieldset>
        <legend>Genres</legend>
        <div id="genres" class="cases discret">Charger une collection pour voir les genres.</div>
      </fieldset>

      <fieldset>
        <legend>Moods</legend>
        <div id="moods" class="cases"></div>
      </fieldset>

      <fieldset>
        <legend>Set</legend>
        <label for="profile">Profil d'évolution</label>
        <select id="profile"></select>

        <label for="duration">Durée (minutes)</label>
        <input type="number" id="duration" value="90" min="1" step="5">

        <label for="seconds">Temps de jeu par morceau (s)</label>
        <input type="number" id="seconds" value="120" min="10" step="10">

        <div class="ligne">
          <span>
            <label for="bpm-min">BPM min</label>
            <input type="number" id="bpm-min" value="150" step="1">
          </span>
          <span>
            <label for="bpm-max">BPM max</label>
            <input type="number" id="bpm-max" value="200" step="1">
          </span>
        </div>
      </fieldset>
    </div>

    <div class="ligne">
      <button id="generer" type="button" class="primaire" disabled>Générer le set</button>
      <button id="regenerer" type="button" hidden>Régénérer</button>
    </div>
  </section>

  <section id="avertissements" hidden></section>

  <section id="courbe" class="carte" hidden>
    <h2>Courbe BPM</h2>
    <div id="courbe-svg"></div>
  </section>

  <section id="resultat" class="carte" hidden>
    <h2>Tracklist <span id="compteur" class="discret"></span></h2>
    <table id="tracklist">
      <thead>
        <tr>
          <th>#</th><th>Artiste</th><th>Titre</th><th>BPM</th>
          <th>Clé</th><th>Mood</th><th>Genres</th><th></th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>

    <div class="ligne export">
      <label for="nom-playlist">Nom de la playlist</label>
      <input type="text" id="nom-playlist">
      <button id="exporter" type="button" class="primaire">Exporter en XML</button>
    </div>
  </section>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Écrire `hardset/web/static/style.css`**

```css
:root {
  --fond: #14161a;
  --carte: #1d2026;
  --trait: #2c313a;
  --texte: #e8eaed;
  --discret: #9aa1ab;
  --accent: #ff5c35;
  --alerte: #3a2a14;
}

* { box-sizing: border-box; }

body {
  margin: 0 auto;
  padding: 1.5rem;
  max-width: 1100px;
  background: var(--fond);
  color: var(--texte);
  font: 15px/1.5 system-ui, sans-serif;
}

h1 { font-size: 1.4rem; letter-spacing: 0.02em; }
h2 { font-size: 1.05rem; margin: 0 0 0.75rem; }

.carte {
  background: var(--carte);
  border: 1px solid var(--trait);
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
}

.ligne { display: flex; gap: 0.75rem; align-items: flex-end; flex-wrap: wrap; }
.ligne > label { align-self: center; }
.colonnes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 1rem 0; }

fieldset { border: 1px solid var(--trait); border-radius: 6px; }
legend { color: var(--discret); padding: 0 0.4rem; }

label { display: block; color: var(--discret); font-size: 0.85rem; margin-top: 0.5rem; }

input, select, button {
  font: inherit;
  color: var(--texte);
  background: #24282f;
  border: 1px solid var(--trait);
  border-radius: 5px;
  padding: 0.4rem 0.6rem;
}

input[type="text"] { flex: 1; min-width: 14rem; }
button { cursor: pointer; }
button:hover:not(:disabled) { border-color: var(--accent); }
button:disabled { opacity: 0.45; cursor: default; }
button.primaire { background: var(--accent); border-color: var(--accent); color: #14161a; font-weight: 600; }

.cases { display: flex; flex-direction: column; gap: 0.25rem; max-height: 14rem; overflow-y: auto; }
.cases label { display: flex; gap: 0.4rem; align-items: center; color: var(--texte); margin: 0; }

.discret { color: var(--discret); font-size: 0.85rem; }

#avertissements { padding: 0; }
.avertissement {
  background: var(--alerte);
  border: 1px solid #5a4420;
  border-radius: 6px;
  padding: 0.6rem 0.8rem;
  margin-bottom: 0.5rem;
}

table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--trait); }
th { color: var(--discret); font-weight: 500; font-size: 0.8rem; text-transform: uppercase; }
td.actions { text-align: right; white-space: nowrap; }
td.actions button { padding: 0.15rem 0.45rem; margin-left: 0.2rem; }
tr.occupe { opacity: 0.4; }

.export { margin-top: 1rem; }
```

- [ ] **Step 3: Écrire `hardset/web/static/app.js`**

```javascript
'use strict';

// État de la page. Le set courant vit ici : le serveur n'en garde pas de copie.
const state = {
  config: null,
  collection: null,
  set: null,
  path: '',
};
window.state = state;

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, enfants = []) {
  const noeud = Object.assign(document.createElement(tag), props);
  for (const enfant of enfants) noeud.append(enfant);
  return noeud;
}

async function api(route, corps) {
  const reponse = await fetch(route, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(corps),
  });
  if (!reponse.ok) {
    const donnees = await reponse.json().catch(() => ({ detail: reponse.statusText }));
    throw new Error(donnees.detail || 'erreur inattendue');
  }
  return reponse;
}

// --- Lecture du formulaire ------------------------------------------------

function cochees(conteneur) {
  return [...conteneur.querySelectorAll('input:checked')].map((c) => c.value);
}

function requete(extra = {}) {
  return {
    path: state.path,
    genres: cochees($('genres')),
    moods: cochees($('moods')).map(Number),
    bpm_min: Number($('bpm-min').value),
    bpm_max: Number($('bpm-max').value),
    profile: $('profile').value,
    duration_min: Number($('duration').value),
    seconds_per_track: Number($('seconds').value),
    ...extra,
  };
}

// --- Rendu ----------------------------------------------------------------

function renderAvertissements(avertissements) {
  const zone = $('avertissements');
  zone.replaceChildren();
  zone.hidden = !avertissements.length;
  for (const a of avertissements) {
    zone.append(el('div', { className: 'avertissement', textContent: a.message }));
  }
}

function moodLabel(valeur) {
  const mood = state.config.moods.find((m) => m.value === valeur);
  return mood ? `${valeur} ${mood.label}` : String(valeur ?? '—');
}

function render() {
  const jeu = state.set;
  $('resultat').hidden = !jeu;
  $('regenerer').hidden = !jeu;
  if (!jeu) return;

  $('compteur').textContent = `${jeu.tracks.length} morceaux`;

  const corps = $('tracklist').querySelector('tbody');
  corps.replaceChildren();

  jeu.tracks.forEach((track, index) => {
    const actions = el('td', { className: 'actions' }, [
      el('button', {
        type: 'button', textContent: '↑', title: 'monter',
        disabled: index === 0,
        onclick: () => deplacer(index, -1),
      }),
      el('button', {
        type: 'button', textContent: '↓', title: 'descendre',
        disabled: index === jeu.tracks.length - 1,
        onclick: () => deplacer(index, 1),
      }),
      el('button', {
        type: 'button', textContent: '⟳', title: 'remplacer',
        onclick: () => remplacer(index),
      }),
      el('button', {
        type: 'button', textContent: '✕', title: 'supprimer',
        onclick: () => supprimer(index),
      }),
    ]);

    corps.append(el('tr', {}, [
      el('td', { textContent: String(index + 1) }),
      el('td', { textContent: track.artist }),
      el('td', { textContent: track.title }),
      el('td', { textContent: track.bpm.toFixed(1) }),
      el('td', { textContent: track.camelot ?? '—' }),
      el('td', { textContent: moodLabel(track.mood) }),
      el('td', { textContent: track.genres.join(', ') }),
      actions,
    ]));
  });

  renderAvertissements(jeu.warnings);
}

// --- Actions --------------------------------------------------------------

async function chargerCollection() {
  const bouton = $('charger');
  bouton.disabled = true;
  $('etat-collection').textContent = 'lecture…';
  try {
    const reponse = await api('/api/collection', { path: $('path').value });
    const donnees = await reponse.json();
    state.collection = donnees;
    state.path = donnees.path;

    $('etat-collection').textContent = `${donnees.track_count} morceaux, ${donnees.genres.length} genres`;

    const zone = $('genres');
    zone.replaceChildren();
    zone.classList.remove('discret');
    for (const genre of donnees.genres) {
      zone.append(el('label', {}, [
        el('input', { type: 'checkbox', value: genre }),
        document.createTextNode(genre),
      ]));
    }

    if (donnees.bpm_max > 0) {
      $('bpm-min').value = Math.floor(donnees.bpm_min);
      $('bpm-max').value = Math.ceil(donnees.bpm_max);
    }

    $('generer').disabled = false;
    renderAvertissements(donnees.warnings);
  } catch (erreur) {
    $('etat-collection').textContent = '';
    renderAvertissements([{ message: erreur.message }]);
  } finally {
    bouton.disabled = false;
  }
}

async function generer() {
  const bouton = $('generer');
  bouton.disabled = true;
  try {
    const reponse = await api('/api/generate', requete());
    state.set = await reponse.json();
    $('nom-playlist').value = state.set.playlist_name;
    render();
  } catch (erreur) {
    renderAvertissements([{ message: erreur.message }]);
  } finally {
    bouton.disabled = false;
  }
}

async function remplacer(index) {
  const ids = state.set.tracks.map((t) => t.id);
  try {
    const reponse = await api('/api/replace', requete({ track_ids: ids, position: index }));
    state.set = await reponse.json();
    render();
  } catch (erreur) {
    renderAvertissements([{ message: erreur.message }]);
  }
}

function supprimer(index) {
  state.set.tracks.splice(index, 1);
  state.set.targets = state.set.targets.slice(0, state.set.tracks.length);
  render();
}

function deplacer(index, delta) {
  const tracks = state.set.tracks;
  const cible = index + delta;
  [tracks[index], tracks[cible]] = [tracks[cible], tracks[index]];
  render();
}

async function exporter() {
  try {
    const reponse = await api('/api/export', {
      path: state.path,
      track_ids: state.set.tracks.map((t) => t.id),
      playlist_name: $('nom-playlist').value,
    });
    const blob = await reponse.blob();
    const lien = el('a', {
      href: URL.createObjectURL(blob),
      download: `${$('nom-playlist').value || 'set'}.xml`,
    });
    document.body.append(lien);
    lien.click();
    lien.remove();
    URL.revokeObjectURL(lien.href);
  } catch (erreur) {
    renderAvertissements([{ message: erreur.message }]);
  }
}

// --- Démarrage ------------------------------------------------------------

async function init() {
  state.config = await (await fetch('/api/config')).json();

  $('profile').replaceChildren(
    ...state.config.profils.map((p) => el('option', { value: p.key, textContent: p.label })),
  );

  $('moods').replaceChildren(
    ...state.config.moods.map((m) => el('label', {}, [
      el('input', { type: 'checkbox', value: String(m.value) }),
      document.createTextNode(`${m.value} — ${m.label}`),
    ])),
  );

  $('seconds').value = state.config.seconds_per_track;
  if (state.config.collection_xml) $('path').value = state.config.collection_xml;

  $('charger').onclick = chargerCollection;
  $('generer').onclick = generer;
  $('regenerer').onclick = generer;
  $('exporter').onclick = exporter;
}

init();
```

- [ ] **Step 4: Vérifier que l'API répond toujours**

Run: `.venv/bin/pytest tests/test_api.py -v`
Attendu : PASS, 12 tests (la page a changé, pas les routes).

- [ ] **Step 5: Vérification manuelle dans le navigateur**

```bash
.venv/bin/hardset --port 8765
```

Dérouler, dans l'ordre, avec l'export réel de Nina :

1. le champ de chemin est prérempli depuis `collection_xml` ;
2. `Charger` affiche le nombre de morceaux, coche la liste réelle des genres, et
   préremplit la plage de BPM ;
3. les avertissements de lecture (moods multiples, sans mood, sans tonalité) s'affichent ;
4. `Générer le set` produit une tracklist du bon nombre de lignes ;
5. `↑` / `↓` déplacent une ligne, `✕` la supprime, `⟳` change le morceau sans créer de doublon ;
6. `Régénérer` donne un set différent ;
7. le nom de playlist est prérempli au format `{genres}-{profil}-{durée}min-{date}` ;
8. `Exporter en XML` télécharge le fichier.

- [ ] **Step 6: Commit**

```bash
git add hardset/web/static/
git commit -m "feat: page unique du générateur (formulaire, tracklist, export)"
```

---

### Task 12 : Courbe BPM en SVG

**Files:**
- Create: `hardset/web/static/curve.js`
- Modify: `hardset/web/static/index.html` (ajout du script)
- Modify: `hardset/web/static/app.js` (appel depuis `render()`)

**Interfaces:**
- Consumes: `state.set.targets` et `state.set.tracks` (tâche 11).
- Produces: `window.renderCurve(targets, tracks)` — dessine dans `#courbe-svg`.

- [ ] **Step 1: Écrire `hardset/web/static/curve.js`**

```javascript
'use strict';

// Courbe BPM : cible contre obtenu, position par position. Le but est de voir
// immédiatement si la collection a imposé un creux ou un palier subi.

const SVG_NS = 'http://www.w3.org/2000/svg';
const LARGEUR = 900;
const HAUTEUR = 260;
const MARGE = { haut: 16, droite: 16, bas: 28, gauche: 44 };

function noeud(tag, attrs) {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [cle, valeur] of Object.entries(attrs)) element.setAttribute(cle, valeur);
  return element;
}

function renderCurve(targets, tracks) {
  const conteneur = document.getElementById('courbe-svg');
  const section = document.getElementById('courbe');
  conteneur.replaceChildren();

  if (!targets || targets.length < 2) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const bpms = [...targets.map((c) => c.bpm), ...tracks.map((t) => t.bpm)];
  const basse = Math.floor(Math.min(...bpms) - 2);
  const haute = Math.ceil(Math.max(...bpms) + 2);

  const x = (i) => MARGE.gauche
    + (i / (targets.length - 1)) * (LARGEUR - MARGE.gauche - MARGE.droite);
  const y = (bpm) => HAUTEUR - MARGE.bas
    - ((bpm - basse) / (haute - basse || 1)) * (HAUTEUR - MARGE.haut - MARGE.bas);

  const svg = noeud('svg', {
    viewBox: `0 0 ${LARGEUR} ${HAUTEUR}`,
    width: '100%',
    height: HAUTEUR,
    role: 'img',
    'aria-label': 'BPM cible et BPM obtenu par position',
  });

  // Graduations horizontales, tous les 10 BPM.
  for (let bpm = Math.ceil(basse / 10) * 10; bpm <= haute; bpm += 10) {
    svg.append(noeud('line', {
      x1: MARGE.gauche, x2: LARGEUR - MARGE.droite,
      y1: y(bpm), y2: y(bpm),
      stroke: '#2c313a', 'stroke-width': 1,
    }));
    const etiquette = noeud('text', {
      x: MARGE.gauche - 8, y: y(bpm) + 4,
      fill: '#9aa1ab', 'font-size': 11, 'text-anchor': 'end',
    });
    etiquette.textContent = String(bpm);
    svg.append(etiquette);
  }

  const chemin = (valeurs) => valeurs
    .map((bpm, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(bpm).toFixed(1)}`)
    .join(' ');

  // Cible en pointillé, obtenu en plein : l'écart entre les deux est l'information.
  svg.append(noeud('path', {
    d: chemin(targets.map((c) => c.bpm)),
    fill: 'none', stroke: '#9aa1ab', 'stroke-width': 1.5, 'stroke-dasharray': '5 4',
  }));
  svg.append(noeud('path', {
    d: chemin(tracks.map((t) => t.bpm)),
    fill: 'none', stroke: '#ff5c35', 'stroke-width': 2,
  }));

  tracks.forEach((track, i) => {
    const point = noeud('circle', { cx: x(i), cy: y(track.bpm), r: 3, fill: '#ff5c35' });
    const titre = noeud('title', {});
    titre.textContent = `${i + 1}. ${track.artist} — ${track.title} (${track.bpm.toFixed(1)} BPM)`;
    point.append(titre);
    svg.append(point);
  });

  const legende = noeud('text', {
    x: MARGE.gauche, y: HAUTEUR - 6, fill: '#9aa1ab', 'font-size': 11,
  });
  legende.textContent = '— — cible      ——— obtenu';
  svg.append(legende);

  conteneur.append(svg);
}

window.renderCurve = renderCurve;
```

- [ ] **Step 2: Charger le script dans la page**

Dans `hardset/web/static/index.html`, remplacer :

```html
  <script src="/static/app.js"></script>
```

par :

```html
  <script src="/static/curve.js"></script>
  <script src="/static/app.js"></script>
```

- [ ] **Step 3: Appeler la courbe depuis `render()`**

Dans `hardset/web/static/app.js`, à la fin de `render()`, remplacer :

```javascript
  renderAvertissements(jeu.warnings);
}
```

par :

```javascript
  renderAvertissements(jeu.warnings);
  window.renderCurve(jeu.targets, jeu.tracks);
}
```

- [ ] **Step 4: Vérification manuelle**

```bash
.venv/bin/hardset --port 8765
```

1. après génération, la courbe apparaît, cible en pointillé et obtenu en plein ;
2. survoler un point affiche artiste, titre et BPM ;
3. avec le profil `vagues`, la cible redescend visiblement au moins une fois ;
4. avec le profil `warmup-long`, la cible reste plate sur les 40 % du début ;
5. supprimer une ligne redessine la courbe avec une position en moins.

- [ ] **Step 5: Lancer toute la suite et vérifier le compte**

Run: `.venv/bin/pytest -v`
Attendu : PASS, 145 tests, aucun `skipped`.

Un test `skipped` signifie que la fixture d'export réel manque : la vérification
bloquante de la tâche 1 n'a pas été faite.

- [ ] **Step 6: Vérifier l'import dans Rekordbox — dernier point de synchronisation**

Générer un set, l'exporter, puis dans Rekordbox : `Fichier > Importer > Importer une
playlist`, choisir le XML. Vérifier que la playlist apparaît, que les morceaux sont liés
aux fichiers d'origine, et que l'ordre de jeu est celui de la tracklist. L'import est
additif : supprimer la playlist ne laisse aucune trace.

**C'est la seule vérification qui prouve que la chaîne complète fonctionne.**

- [ ] **Step 7: Commit**

```bash
git add hardset/web/static/curve.js hardset/web/static/index.html hardset/web/static/app.js
git commit -m "feat: courbe BPM cible contre obtenu en SVG"
```

---

## Couverture du spec

Table de contrôle : chaque exigence du spec a une tâche qui la porte.

| Spec | Tâche |
|---|---|
| §4 Architecture en quatre couches, moteur pur | Structure de fichiers + contraintes globales |
| §5 `Track`, `Mood`, `SetRequest`, `GeneratedSet`, `Warning` | 2 |
| §5 `raw_attrs` recopié sans perte | 2 (stockage), 9 (restitution) |
| §5 Mood unique, mood multiple ou absent écarté et signalé | 5 (détection), 7 (exclusion) |
| §6 Lecture des My Tags dans `Comments` | 1 (vérification), 5 (implémentation) |
| §6 Tout tag non-mood est un genre, aucune liste de genres | 3 (`mood_value`), 5 |
| §6 Comparaison insensible casse / accents / espaces | 2 (`normalize_tag`) |
| §6 Risque à lever en premier, repli `master.db` | 1, étape 5 |
| §7 Normalisation Camelot, classique / Camelot / Open Key | 4 |
| §7 Tableau des pénalités de transition | 4 |
| §8 Étape 1 filtrage | 7 |
| §8 Pénurie : set le plus long possible + avertissement | 8 |
| §8 Étape 2 cibles, mood non arrondi | 6 |
| §8 Étape 3 coût, tirage parmi les `k` meilleurs | 8 |
| §8 Première position sans pénalité harmonique | 8 |
| §8 Remplacement d'un morceau | 8 (moteur), 10 (route), 11 (bouton) |
| §9 Trois types de courbe, quatre profils, zéro code | 3 (config), 6 (courbes) |
| §10 Formulaire, chemin lu côté serveur | 10, 11 |
| §10 Courbe BPM cible contre obtenu | 12 |
| §10 Tracklist, supprimer / remplacer / déplacer, régénérer | 11 |
| §10 Bandeau d'avertissements | 11 |
| §10 Export, nom prérempli | 9 (nom), 10 (route), 11 (bouton) |
| §11 Structure `DJ_PLAYLISTS`, `COLLECTION` complète | 9 |
| §12 Les 13 tests du tableau | 4, 5, 6, 8, 9 |
| §12 Interface non testée automatiquement | 11, 12 (vérifications manuelles) |
| §13 Ordre de construction | Tâches 1 à 12, avec l'inversion harmonie / lecteur justifiée en tâche 4 |

## Hors périmètre, à ne pas implémenter

Rappel du spec §2, pour qu'aucune tâche ne dérive : pas d'écriture dans `master.db`, pas
d'historique des sets joués, pas d'analyse audio, pas d'ordonnancement optimal global, pas
de gestion du demi / double tempo, pas de tests automatisés de l'interface web.
