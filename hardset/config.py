"""Chargement de la configuration YAML : moods, profils de courbe, poids.

La configuration porte tout ce qui relève du goût musical, pour qu'ajouter un
profil ou renommer un mood ne demande pas de toucher au code.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from hardset.model import MOOD_MAX, normalize_tag

DEFAULT_CONFIG_PATH = Path("hardset.yaml")

# Exemplaire livré avec le paquet, à côté du code. Sert de repli quand le
# répertoire courant ne contient pas de `hardset.yaml` : la commande `hardset`
# se lance depuis n'importe où, et « configuration introuvable » au premier
# lancement depuis ailleurs que le dépôt n'aide personne. `--config` reste le
# moyen de désigner explicitement un autre fichier.
_CONFIG_LIVREE = Path(__file__).resolve().parent.parent / "hardset.yaml"


def _chemin_par_defaut() -> Path:
    """`hardset.yaml` du répertoire courant, sinon celui livré avec le paquet.

    Le fichier du répertoire courant garde la priorité : c'est là que se
    trouvent les réglages de la personne qui lance l'outil. Si le paquet est
    installé sans ses sources, `_CONFIG_LIVREE` n'existe pas et le message
    d'erreur nomme `hardset.yaml`, comme avant.
    """
    if DEFAULT_CONFIG_PATH.exists() or not _CONFIG_LIVREE.exists():
        return DEFAULT_CONFIG_PATH
    return _CONFIG_LIVREE

# Types de courbe reconnus, et paramètres admis pour chacun (cf. tâche 6).
CURVE_PARAMS: dict[str, set[str]] = {
    "lineaire": {"depart", "arrivee"},
    "retarde": {"palier"},
    "vagues": {"amplitude", "oscillations"},
}


class ConfigError(Exception):
    """Configuration illisible ou incohérente."""


# Formulation partagée par tous les refus de type, pour que le même problème
# (un booléen là où un nombre est attendu) produise toujours le même message,
# quel que soit le champ concerné.
MESSAGE_BOOLEEN = "un booléen n'est pas une valeur numérique valide"


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


# Noms de champs réels de `Weights`, pour valider `poids.<champ>` sans passer
# par `hasattr` : `hasattr(poids, "__class__")` ou `hasattr(poids, "__init__")`
# répondrait `True` (ce sont des attributs de tout objet Python), ce qui
# laisserait passer une clé de configuration invalide jusqu'à
# `dataclasses.replace`, où elle ferait remonter une `TypeError` brute.
_CHAMPS_POIDS = frozenset(champ.name for champ in fields(Weights))

# Clés admises à la racine du fichier, et dans le corps d'un profil. Une
# liste blanche fermée, sur le modèle de `_CHAMPS_POIDS` : `hardset.yaml`
# est édité à la main, et une faute de frappe (`seconds_per_tracks`,
# `labell`) ne doit jamais se charger en silence.
_CHAMPS_RACINE = frozenset({"moods", "profils", "poids", "seconds_per_track", "collection_xml"})
_CHAMPS_PROFIL = frozenset({"label", "bpm", "mood"})


@dataclass(frozen=True)
class Config:
    moods: tuple[str, ...]
    profils: dict[str, Profile]
    poids: Weights = Weights()
    collection_xml: str | None = None
    seconds_per_track: int = 120

    @property
    def mood_max(self) -> int:
        """Plus haut niveau de l'échelle configurée.

        L'échelle est ordinale et 1-based : `moods` peut être plus courte que
        `MOOD_MAX`, qui n'en borne que l'étendue maximale. C'est cette
        longueur-là, et pas la constante, qui dit jusqu'où une demande et une
        courbe de mood ont le droit d'aller.
        """
        return len(self.moods)

    def mood_value(self, tag: str) -> int | None:
        """Position 1-based du tag dans l'échelle, ou `None` si ce n'est pas un mood."""
        cible = normalize_tag(tag)
        if not cible:
            return None
        for index, mood in enumerate(self.moods, start=1):
            if normalize_tag(mood) == cible:
                return index
        return None


def _nombre(valeur: Any, chemin: str) -> float:
    """Convertit `valeur` en `float` ou lève une `ConfigError` explicite.

    Un booléen est explicitement refusé : `bool` est une sous-classe d'`int` en
    Python, donc `float(False)` réussirait silencieusement.
    """
    if isinstance(valeur, bool):
        raise ConfigError(f"{chemin} : {MESSAGE_BOOLEEN}")
    try:
        return float(valeur)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{chemin} : valeur numérique attendue, reçu {valeur!r}") from exc


def _entier(valeur: Any, chemin: str) -> int:
    """Convertit `valeur` en entier strict, sans arrondi silencieux.

    Comme `_nombre`, un booléen est refusé. Un flottant qui n'est pas une
    valeur entière (`5.5`) est également refusé plutôt que tronqué par
    `int()`, qui l'aurait accepté sans le dire.
    """
    if isinstance(valeur, bool):
        raise ConfigError(f"{chemin} : {MESSAGE_BOOLEEN}")
    if isinstance(valeur, float) and not valeur.is_integer():
        raise ConfigError(f"{chemin} : valeur entière attendue, reçu {valeur!r}")
    try:
        return int(valeur)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{chemin} : valeur entière attendue, reçu {valeur!r}") from exc


def _curve(raw: Any, chemin: str) -> CurveSpec:
    if not isinstance(raw, dict) or "type" not in raw:
        raise ConfigError(f"{chemin} : une courbe doit être un objet avec un 'type'")
    type_ = str(raw["type"])
    if type_ not in CURVE_PARAMS:
        connus = ", ".join(sorted(CURVE_PARAMS))
        raise ConfigError(f"{chemin} : type de courbe '{type_}' inconnu (attendu : {connus})")
    for cle in raw:
        if cle != "type" and not isinstance(cle, str):
            raise ConfigError(
                f"{chemin} : les clés de paramètres doivent être des chaînes, reçu {cle!r}"
            )
    params = {
        cle: _nombre(valeur, f"{chemin}.{cle}")
        for cle, valeur in raw.items()
        if cle != "type"
    }
    # `inconnus` peut mélanger des types si des clés inattendues coexistent ;
    # la vérification ci-dessus les a déjà rejetées, donc `sorted(...)` ne
    # verra plus jamais que des chaînes ici (sinon `sorted` lèverait une
    # `TypeError` brute en comparant par exemple un `int` et une chaîne).
    inconnus = set(params) - CURVE_PARAMS[type_]
    if inconnus:
        raise ConfigError(f"{chemin} : paramètres inconnus pour '{type_}' : {sorted(inconnus)}")
    return CurveSpec(type=type_, params=params)


def load_config(path: Path | None = None) -> Config:
    """Charge la configuration. Les poids absents gardent leur valeur par défaut."""
    # Importé ici et non en tête de module : `hardset.engine` importe `hardset.config`
    # pour ses dataclasses sans avoir le droit de charger `yaml` transitivement.
    import yaml

    chemin = Path(path) if path is not None else _chemin_par_defaut()
    try:
        # Lu puis normalisé, et non `... or {}` : un fichier ne contenant que
        # `0` ou `false` est un mapping absent au sens YAML (`None`), pas une
        # valeur fausse à confondre avec lui après coup. L'idiome `or {}`
        # aurait laissé passer un tel fichier jusqu'au message de `moods`
        # (« au moins un mood »), qui ne nomme pas la vraie clé fautive : la
        # racine elle-même.
        raw = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        if raw is None:
            raw = {}
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration introuvable : {chemin}") from exc
    except (IsADirectoryError, NotADirectoryError, PermissionError) as exc:
        raise ConfigError(f"configuration illisible : {chemin} ({exc})") from exc
    except UnicodeDecodeError as exc:
        # Hérite de `ValueError`, pas d'`OSError` : un `except OSError` ne
        # l'attraperait pas. Cas réaliste avec les accents français du
        # fichier livré, si un éditeur mal réglé l'enregistre en latin-1.
        raise ConfigError(
            f"configuration illisible : {chemin} n'est pas de l'UTF-8 valide ({exc})"
        ) from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML illisible dans {chemin} : {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            f"la racine de {chemin} doit être un mapping (clé: valeur), pas {type(raw).__name__}"
        )

    # Liste blanche fermée : une clé mal orthographiée (`seconds_per_tracks`)
    # doit être signalée, pas silencieusement ignorée. `cle` peut être de
    # n'importe quel type YAML (un entier, par exemple) ; `_CHAMPS_RACINE` ne
    # contenant que des chaînes, le test d'appartenance rejette aussi ce cas
    # sans traitement particulier.
    for cle in raw:
        if cle not in _CHAMPS_RACINE:
            raise ConfigError(f"clé de configuration inconnue à la racine : {cle!r}")

    # `.get(cle, defaut)` et non `.get(cle) or defaut` : `moods: 0` est une
    # valeur fausse au sens Python, et l'idiome `or` la ferait passer pour
    # une absence de clé au lieu d'être rejetée pour mauvais type juste après.
    # `moods:` laissé nul (`None`) est en revanche traité comme absent, comme
    # `poids:` : le message qui en résulterait sinon (« pas une valeur
    # unique ») décrirait mal la situation d'une clé simplement vide.
    moods_raw = raw.get("moods", ())
    if moods_raw is None:
        moods_raw = ()
    if isinstance(moods_raw, str) or not isinstance(moods_raw, (list, tuple)):
        raise ConfigError("moods doit être une liste de chaînes, pas une valeur unique")
    for element in moods_raw:
        if not isinstance(element, str):
            raise ConfigError(f"moods : chaque élément doit être une chaîne, reçu {element!r}")
    moods = tuple(moods_raw)
    if not moods:
        raise ConfigError("la configuration doit définir au moins un mood")
    if len(moods) > MOOD_MAX:
        raise ConfigError(f"l'échelle de mood est limitée à {MOOD_MAX} valeurs, {len(moods)} fournies")
    # Un doublon rend un niveau de l'échelle ordinale inaccessible :
    # `mood_value` rend toujours l'index du premier tag rencontré. Comparaison
    # via `normalize_tag` pour que `Calme` et `calme` comptent comme un même
    # doublon.
    vus: set[str] = set()
    for mood in moods:
        normalise = normalize_tag(mood)
        if normalise in vus:
            raise ConfigError(f"moods : doublon détecté pour {mood!r}")
        vus.add(normalise)

    # Même remarque que pour `moods` : `.get(cle, defaut)`, pas `or defaut`,
    # et `None` traité comme absent pour la même raison.
    profils_raw = raw.get("profils", {})
    if profils_raw is None:
        profils_raw = {}
    if not isinstance(profils_raw, dict):
        raise ConfigError("profils doit être un mapping (clé: profil)")
    if not profils_raw:
        raise ConfigError("la configuration doit définir au moins un profil")
    profils: dict[str, Profile] = {}
    for cle, corps in profils_raw.items():
        if not isinstance(cle, str):
            raise ConfigError(f"profils : les clés doivent être des chaînes, reçu {cle!r}")
        if not isinstance(corps, dict):
            raise ConfigError(f"profils.{cle} doit être un mapping avec 'label', 'bpm' et 'mood'")
        for champ in corps:
            if champ not in _CHAMPS_PROFIL:
                raise ConfigError(f"profils.{cle} : clé inconnue {champ!r}")
        label_brut = corps.get("label", cle)
        if not isinstance(label_brut, str):
            raise ConfigError(f"profils.{cle}.label : chaîne attendue, reçu {label_brut!r}")
        profils[cle] = Profile(
            key=cle,
            label=label_brut,
            bpm=_curve(corps.get("bpm"), f"profils.{cle}.bpm"),
            mood=_curve(corps.get("mood"), f"profils.{cle}.mood"),
        )

    # Même remarque que pour `moods`/`profils` : `.get(cle, defaut)`, pas
    # `or defaut` — `poids: 0` ne doit pas passer pour « aucune surcharge ».
    # `poids:` laissé nul (`None`) reste en revanche « aucune surcharge » :
    # commenter tous les poids sous `poids:` est une manipulation défendable
    # sur un fichier édité à la main, et `Weights()` porte déjà des défauts.
    poids_raw = raw.get("poids", {})
    if poids_raw is None:
        poids_raw = {}
    if not isinstance(poids_raw, dict):
        raise ConfigError("poids doit être un mapping (clé: valeur)")
    poids = Weights()
    for champ, valeur in poids_raw.items():
        if not isinstance(champ, str):
            raise ConfigError(f"poids : les clés doivent être des chaînes, reçu {champ!r}")
        if champ not in _CHAMPS_POIDS:
            raise ConfigError(f"poids.{champ} : poids inconnu")
        if champ == "k":
            k = _entier(valeur, f"poids.{champ}")
            if k < 1:
                raise ConfigError(f"poids.{champ} : doit être au moins 1")
            poids = replace(poids, k=k)
        elif champ == "bpm_tolerance":
            bpm_tolerance = _nombre(valeur, f"poids.{champ}")
            if bpm_tolerance <= 0:
                raise ConfigError(f"poids.{champ} : doit être strictement positif")
            poids = replace(poids, bpm_tolerance=bpm_tolerance)
        else:
            # `bpm`, `mood`, `tonalite` : des poids négatifs inverseraient le
            # sens du coût qu'ils pondèrent dans le moteur.
            nombre = _nombre(valeur, f"poids.{champ}")
            if nombre < 0:
                raise ConfigError(f"poids.{champ} : doit être positif ou nul")
            poids = replace(poids, **{champ: nombre})

    # Passe par `_entier`, comme `poids.k` : même comportement (refus des
    # booléens, acceptation d'un flottant exactement entier comme `120.0`)
    # plutôt qu'une validation manuelle divergente.
    seconds_per_track = _entier(raw.get("seconds_per_track", 120), "seconds_per_track")
    if seconds_per_track <= 0:
        raise ConfigError("seconds_per_track : doit être strictement positif")

    collection = raw.get("collection_xml")
    if collection is not None and not isinstance(collection, str):
        raise ConfigError(f"collection_xml : chaîne attendue, reçu {collection!r}")

    return Config(
        moods=moods,
        profils=profils,
        poids=poids,
        collection_xml=collection if collection else None,
        seconds_per_track=seconds_per_track,
    )
