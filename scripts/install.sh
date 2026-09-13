#!/usr/bin/env bash
# One-command install of wzlcarrot-cli via uv / pipx / pip.
set -euo pipefail

PKG="wzlcarrot-cli"

if command -v uv >/dev/null 2>&1; then
  echo "Installing with uv tool…"
  uv tool install "$PKG"
elif command -v pipx >/dev/null 2>&1; then
  echo "Installing with pipx…"
  pipx install "$PKG"
else
  echo "Installing with pip --user…"
  python3 -m pip install --user --upgrade "$PKG"
fi

echo
echo "Done. Run:  wzlcarrot version"
echo "(the legacy alias 'zhihu' is installed too)"
