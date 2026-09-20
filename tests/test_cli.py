"""Tests du point d'entrée de ligne de commande."""

import pytest

from hardset.cli import main


# --- Gestion du port occupé -----------------------------------------------

def test_cli_port_occupe_affiche_message_et_retourne_1(monkeypatch, capsys):
    """
    Quand uvicorn.run() lève une OSError (port occupé), main() doit :
    - afficher un message français explicite nommant le port
    - suggérer l'option --port
    - retourner 1
    """
    def mock_uvicorn_run(*args, **kwargs):
        raise OSError("[Errno 98] Address already in use")

    monkeypatch.setattr("hardset.cli.uvicorn.run", mock_uvicorn_run)
    monkeypatch.setattr("sys.argv", ["hardset", "--no-browser"])

    code_retour = main()

    assert code_retour == 1
    sortie = capsys.readouterr().out
    assert "port" in sortie.lower()
    assert "--port" in sortie
