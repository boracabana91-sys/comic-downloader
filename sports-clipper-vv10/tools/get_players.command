#!/bin/bash
# Double-click on a Mac. Installs what it needs into its own folder, then gets all 30 player pictures.
cd "$(dirname "$0")" || exit 1
VENV="$HOME/SportsClipper/.players-venv"
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV" || { echo "python3 is needed: install it from python.org, then double-click this again."; read -r -p "Press Enter"; exit 1; }
  "$VENV/bin/pip" install --quiet requests pillow "rembg[cpu]" onnxruntime
fi
"$VENV/bin/python" get_players.py "$@"
read -r -p "Press Enter to close"
