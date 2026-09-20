"""Contraintes de structure que rien d'autre ne garde.

Ces tests ne décrivent aucun comportement musical : ils protègent des
invariants d'architecture qu'un changement raisonnable à l'échelle d'un seul
fichier ferait sauter en silence.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from hardset.config import CURVE_PARAMS, CurveSpec
from hardset.engine.curves import CurveError, curve_fn

RACINE = Path(__file__).parent.parent


# --- Types de courbe : déclarés et implémentés ----------------------------
# `CURVE_PARAMS` déclare les types reconnus par la configuration, `curve_fn`
# les implémente, et aucune référence ne les lie : un type ajouté à la
# configuration sans implémentation se charge sans erreur, puis produit un 500
# à la génération. Vérifié par le comportement de `curve_fn`, jamais par
# lecture de sa source : peu importe comment elle est écrite, seul compte ce
# qu'elle accepte et refuse réellement.

@pytest.mark.parametrize("type_de_courbe", sorted(CURVE_PARAMS))
def test_chaque_type_declare_est_implemente(type_de_courbe):
    # `curve_fn` lèverait `CurveError` sur un type déclaré mais non implémenté.
    assert callable(curve_fn(CurveSpec(type_de_courbe, {})))


def test_un_type_inconnu_est_refuse():
    # Symétrique du test ci-dessus : un type que la configuration ne
    # reconnaît pas ne doit produire aucune courbe.
    assert "inexistant" not in CURVE_PARAMS
    with pytest.raises(CurveError):
        curve_fn(CurveSpec("inexistant", {}))


# --- Pureté du moteur -----------------------------------------------------
# `hardset/engine/` et `hardset/model.py` sont du Python pur : aucune E/S,
# aucun `yaml`, aucun `fastapi`. C'est cette contrainte qui a justifié de
# garder `import yaml` dans le corps de `load_config` plutôt qu'en tête de
# `hardset/config.py`, que `hardset.engine` importe pour ses dataclasses.

SONDE = (
    "import sys;"
    "import hardset.engine.sequencing;"
    "import hardset.engine.pinning;"
    "import hardset.engine.search;"
    "import hardset.model;"
    "print(sorted(m for m in ('yaml', 'fastapi', 'uvicorn', 'starlette')"
    " if m in sys.modules))"
)


def test_importer_le_moteur_ne_charge_ni_yaml_ni_fastapi():
    resultat = subprocess.run(
        [sys.executable, "-c", SONDE],
        capture_output=True,
        text=True,
        cwd=RACINE,
        check=True,
    )
    assert resultat.stdout.strip() == "[]", (
        "le moteur charge des modules interdits : " + resultat.stdout.strip()
    )
