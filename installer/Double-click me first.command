#!/bin/bash
# Cattyfied installer helper. Copies the app to Applications, removes the "downloaded from internet"
# block (Cattyfied is not Apple-signed), and opens it.

APP_NAME="Cattyfied.app"
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/$APP_NAME"
DEST="/Applications/$APP_NAME"

echo ""
echo "  🐱  Installing Cattyfied..."
echo ""

if [ ! -d "$SRC" ]; then
  echo "  😿  I can't find Cattyfied next to this file."
  echo "      Please open the Cattyfied disk image again and double-click me from there."
  echo ""
  read -n 1 -s -r -p "  Press any key to close."
  exit 1
fi

if pgrep -x "Cattyfied" >/dev/null 2>&1; then
  echo "  Closing the old Cattyfied first..."
  osascript -e 'tell application "Cattyfied" to quit' >/dev/null 2>&1
  sleep 2
fi

echo "  Copying Cattyfied to your Applications folder..."
if ! ditto "$SRC" "$DEST" 2>/dev/null; then
  echo "  Your Mac needs your password to copy into Applications (the password you use to log in)."
  echo "  (Nothing shows while you type. That's normal. Press Return when done.)"
  sudo ditto "$SRC" "$DEST" || { echo "  😿  Copy failed. Drag Cattyfied onto the Applications folder instead."; read -n 1 -s -r -p "  Press any key to close."; exit 1; }
fi

echo "  Telling your Mac that Cattyfied is safe to open..."
xattr -cr "$DEST" 2>/dev/null || sudo xattr -cr "$DEST"

echo "  Opening Cattyfied..."
open "$DEST"

echo ""
echo "  ✅  All done! You can close this window."
echo "      Next time, open Cattyfied from Launchpad or your Applications folder."
echo ""
