"""Lance Établi : serveur local + ouverture du navigateur.

    uv run etabli                 # http://127.0.0.1:8765
    uv run etabli --port 9000 --sans-navigateur
"""
from __future__ import annotations

import argparse
import threading
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(prog="etabli", description="Établi — atelier local d'analyse quantitative")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur")
    args = parser.parse_args()

    import uvicorn

    from .projet import dossier_travail

    url = f"http://127.0.0.1:{args.port}"
    print(f"\n  Établi tourne sur {url}\n  Projets enregistrés dans : {dossier_travail()}\n"
          "  Vos données restent sur cet ordinateur (le serveur n'écoute que sur 127.0.0.1).\n"
          "  Pour arrêter : Ctrl+C dans cette fenêtre.\n")
    if not args.sans_navigateur:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # 127.0.0.1 uniquement : inaccessible depuis le réseau
    uvicorn.run("etabli.server:app", host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
