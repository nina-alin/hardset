"""Tests du point d'entrée de ligne de commande."""

import socket
import time

import uvicorn

from hardset.cli import main


def _port_ephemere_occupe() -> socket.socket:
    """Ouvre réellement une socket d'écoute sur un port libre du système.

    Le port choisi par l'OS (`bind` sur le port 0) est ensuite tenu occupé par
    cette socket, exactement comme le serait une autre instance de hardset déjà
    lancée. L'appelante doit fermer la socket rendue une fois le test terminé.
    """
    occupee = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupee.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupee.bind(("127.0.0.1", 0))
    occupee.listen(1)
    return occupee


# --- Gestion du port occupé -----------------------------------------------
# En conditions réelles, uvicorn intercepte lui-même l'OSError de bind : elle
# ne remonte jamais jusqu'à cli.py. Ces tests occupent donc un vrai port
# éphémère plutôt que de remplacer uvicorn.Server.run par un substitut qui
# lève une OSError qui ne se produirait jamais ainsi en pratique.

def test_cli_port_occupe_affiche_message_et_retourne_1(monkeypatch, capsys):
    """
    Quand le port demandé est déjà occupé par un autre processus, main() doit :
    - afficher un message français explicite nommant le port
    - suggérer l'option --port
    - retourner 1
    """
    occupee = _port_ephemere_occupe()
    port = occupee.getsockname()[1]
    try:
        monkeypatch.setattr("sys.argv", ["hardset", "--no-browser", "--port", str(port)])
        code_retour = main()
    finally:
        occupee.close()

    assert code_retour == 1
    sortie = capsys.readouterr().out
    assert str(port) in sortie
    assert "--port" in sortie


# --- Ouverture du navigateur ----------------------------------------------
# L'ouverture était programmée avant que uvicorn n'ait pris le port : sur un
# port occupé, l'utilisatrice voyait un onglet mort *et* le message d'erreur.

def test_le_navigateur_ne_souvre_pas_si_le_port_est_occupe(monkeypatch):
    ouvertures = []
    occupee = _port_ephemere_occupe()
    port = occupee.getsockname()[1]
    try:
        monkeypatch.setattr("hardset.cli.webbrowser.open", ouvertures.append)
        monkeypatch.setattr("sys.argv", ["hardset", "--port", str(port)])   # sans --no-browser

        assert main() == 1
    finally:
        occupee.close()
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
