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
    try:
        uvicorn.run(create_app(config), host=args.host, port=args.port, log_level="warning")
    except OSError as exc:
        # Cas ordinaire : relancer l'outil alors qu'une instance tourne déjà sur
        # ce port. L'utilisatrice doit voir une phrase qui lui dit quoi faire,
        # pas une trace Python.
        print(
            f"Impossible d'écouter sur le port {args.port} : {exc}. "
            "Une autre instance de hardset tourne peut-être déjà sur ce port : "
            "relancez avec --port pour en choisir un autre."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
