"""Point d'entrée : lance le serveur local et ouvre le navigateur."""

from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from hardset.config import ConfigError, DEFAULT_CONFIG_PATH, load_config
from hardset.web.app import create_app


def _erreur_si_port_occupe(host: str, port: int) -> OSError | None:
    """Tente de lier une socket sur `host`:`port`, renvoie l'erreur le cas échéant.

    Vérifié nous-mêmes *avant* d'appeler `uvicorn.run()` : en pratique, uvicorn
    intercepte lui-même l'`OSError` de bind, la journalise en anglais sur
    `stderr` et quitte via `sys.exit(3)` depuis son propre code — elle ne
    remonte jamais jusqu'à un `except OSError` posé autour de `serveur.run()`.
    """
    essai = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR comme le fait uvicorn (via asyncio) pour lier son propre
    # port : sans ça, un port juste relâché (état TIME_WAIT) serait signalé
    # occupé ici alors qu'uvicorn saurait s'y lier sans problème.
    essai.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        essai.bind((host, port))
    except OSError as exc:
        return exc
    finally:
        essai.close()
    return None


def _ouvrir_quand_pret(
    serveur: uvicorn.Server, url: str, fini: threading.Event, delai: float = 10.0
) -> None:
    """Ouvre le navigateur une fois le serveur réellement en écoute.

    Programmée avant que uvicorn n'ait pris le port, l'ouverture montrait un
    onglet mort en même temps que le message d'erreur quand le port était déjà
    occupé. Le drapeau `started` d'uvicorn dit quand le serveur répond ;
    `fini` est levé dès que `run()` rend la main, échec compris, pour que ce
    veilleur s'arrête au lieu d'ouvrir un onglet vers rien.
    """
    limite = time.monotonic() + delai
    while not fini.is_set() and time.monotonic() < limite:
        if serveur.started:
            webbrowser.open(url)
            return
        fini.wait(0.05)


def main() -> int:
    parseur = argparse.ArgumentParser(
        prog="hardset",
        description="Générateur de sets DJ à partir des My Tags Rekordbox",
    )
    # Sans `--config`, `load_config` choisit elle-même : le `hardset.yaml` du
    # répertoire courant, sinon celui livré avec le paquet.
    parseur.add_argument("--config", type=Path, default=None,
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

    erreur_port = _erreur_si_port_occupe(args.host, args.port)
    if erreur_port is not None:
        # Cas ordinaire : relancer l'outil alors qu'une instance tourne déjà sur
        # ce port. L'utilisatrice doit voir une phrase qui lui dit quoi faire,
        # pas une trace Python — et surtout pas celle, en anglais, d'uvicorn.
        print(
            f"Impossible d'écouter sur le port {args.port} : {erreur_port}. "
            "Une autre instance de hardset tourne peut-être déjà sur ce port : "
            "relancez avec --port pour en choisir un autre."
        )
        return 1

    url = f"http://{args.host}:{args.port}/"
    serveur = uvicorn.Server(
        uvicorn.Config(
            create_app(config), host=args.host, port=args.port, log_level="warning"
        )
    )
    fini = threading.Event()
    if not args.no_browser:
        # Le navigateur s'ouvre quand le serveur écoute vraiment, jamais avant
        # ni s'il n'a pas démarré.
        threading.Thread(
            target=_ouvrir_quand_pret, args=(serveur, url, fini), daemon=True
        ).start()

    print(f"hardset écoute sur {url}")
    try:
        serveur.run()
    finally:
        fini.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
