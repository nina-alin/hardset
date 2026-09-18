"""Chargement de la configuration YAML : moods, profils de courbe, poids.

La configuration porte tout ce qui relève du goût musical, pour qu'ajouter un
profil ou renommer un mood ne demande pas de toucher au code.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from hardset.model import MOOD_MAX, normalize_tag

DEFAULT_CONFIG_PATH = Path("hardset.yaml")

# Types de courbe reconnus, et paramètres admis pour chacun (cf. tâche 6).
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
    seconds_per_track: int = 120

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
    # Importé ici et non en tête de module : `hardset.engine` importe `hardset.config`
    # pour ses dataclasses sans avoir le droit de charger `yaml` transitivement.
    import yaml

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

    seconds_per_track_brut = raw.get("seconds_per_track", 120)
    if not isinstance(seconds_per_track_brut, int) or isinstance(seconds_per_track_brut, bool):
        raise ConfigError("seconds_per_track doit être un nombre entier strictement positif")
    if seconds_per_track_brut <= 0:
        raise ConfigError("seconds_per_track doit être strictement positif")

    collection = raw.get("collection_xml")
    return Config(
        moods=moods,
        profils=profils,
        poids=poids,
        collection_xml=str(collection) if collection else None,
        seconds_per_track=seconds_per_track_brut,
    )
