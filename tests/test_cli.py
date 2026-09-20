"""Tests du point d'entrée de ligne de commande."""

import time

import uvicorn

from hardset.cli import main


# --- Gestion du port occupé -----------------------------------------------

def test_cli_port_occupe_affiche_message_et_retourne_1(monkeypatch, capsys):
    """
    Quand uvicorn.run() lève une OSError (port occupé), main() doit :
    - afficher un message français explicite nommant le port
    - suggérer l'option --port
    - retourner 1
    """
    def run_qui_echoue(self):
        raise OSError("[Errno 98] Address already in use")

    monkeypatch.setattr(uvicorn.Server, "run", run_qui_echoue)
    monkeypatch.setattr("sys.argv", ["hardset", "--no-browser"])

    code_retour = main()

    assert code_retour == 1
    sortie = capsys.readouterr().out
    assert "port" in sortie.lower()
    assert "--port" in sortie


# --- Ouverture du navigateur ----------------------------------------------
# L'ouverture était programmée avant que uvicorn n'ait pris le port : sur un
# port occupé, l'utilisatrice voyait un onglet mort *et* le message d'erreur.

def test_le_navigateur_ne_souvre_pas_si_le_serveur_na_pas_demarre(monkeypatch):
    ouvertures = []

    def run_qui_echoue(self):
        raise OSError("[Errno 98] Address already in use")

    monkeypatch.setattr("hardset.cli.webbrowser.open", ouvertures.append)
    monkeypatch.setattr(uvicorn.Server, "run", run_qui_echoue)
    monkeypatch.setattr("sys.argv", ["hardset"])       # sans --no-browser

    assert main() == 1
    assert ouvertures == []


def test_le_navigateur_souvre_une_fois_le_serveur_en_ecoute(monkeypatch):
    ouvertures = []

    def run_qui_demarre(self):
        self.started = True
        time.sleep(0.5)       # laisse le veilleur voir le drapeau

    monkeypatch.setattr("hardset.cli.webbrowser.open", ouvertures.append)
    monkeypatch.setattr(uvicorn.Server, "run", run_qui_demarre)
    monkeypatch.setattr("sys.argv", ["hardset", "--port", "8123"])

    assert main() == 0
    assert ouvertures == ["http://127.0.0.1:8123/"]


def test_option_no_browser_respectee(monkeypatch):
    ouvertures = []

    def run_qui_demarre(self):
        self.started = True
        time.sleep(0.2)

    monkeypatch.setattr("hardset.cli.webbrowser.open", ouvertures.append)
    monkeypatch.setattr(uvicorn.Server, "run", run_qui_demarre)
    monkeypatch.setattr("sys.argv", ["hardset", "--no-browser"])

    assert main() == 0
    assert ouvertures == []
