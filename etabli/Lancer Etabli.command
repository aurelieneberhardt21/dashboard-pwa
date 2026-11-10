#!/bin/bash
# Double-cliquez sur ce fichier (macOS) pour lancer Établi. Fermez la fenêtre du Terminal pour l'arrêter.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "Établi a besoin de « uv », un petit outil libre qui installe Python et les bibliothèques"
  echo "scientifiques dans ce dossier, sans toucher au reste de l'ordinateur (https://docs.astral.sh/uv/)."
  read -r -p "Installer uv maintenant ? [o/N] " reponse
  if [ "$reponse" = "o" ] || [ "$reponse" = "O" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh || { echo "Installation impossible."; read -r -p "Entrée pour fermer."; exit 1; }
    export PATH="$HOME/.local/bin:$PATH"
  else
    exit 1
  fi
fi
echo "Démarrage d'Établi (la première fois, le téléchargement des bibliothèques prend une à deux minutes)…"
uv run etabli "$@"
read -r -p "Établi s'est arrêté. Appuyez sur Entrée pour fermer cette fenêtre."
