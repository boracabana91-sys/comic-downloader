#!/bin/bash
# Double-click me once. Installs everything Sports Clipper needs, then creates "Open Sports Clipper.command".
cd "$(dirname "$0")" || exit 1
echo "== Sports Clipper installer =="
if ! command -v brew >/dev/null 2>&1; then
  echo
  echo "Homebrew (the Mac installer tool) is missing. Install it first:"
  echo "  1. Open https://brew.sh   2. Copy the one line shown there into Terminal and press Enter"
  echo "  3. When it finishes, double-click this file again."
  read -p "Press Enter to close." ; exit 1
fi
set -e
brew install ffmpeg python python-tk
PY="$(brew --prefix)/bin/python3"
"$PY" -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cat > "Open Sports Clipper.command" <<'EOT'
#!/bin/bash
cd "$(dirname "$0")" || exit 1
. .venv/bin/activate
python -m sportsclipper gui
EOT
chmod +x "Open Sports Clipper.command"
echo
echo "DONE. Now double-click  'Open Sports Clipper.command'  to open the program."
read -p "Press Enter to close."
