#!/usr/bin/env bash
# Build a single-file `wzlcarrot` binary with PyInstaller.
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --extra binary
uv run pyinstaller --clean --noconfirm packaging/pyinstaller/wzlcarrot.spec

echo "built: dist/wzlcarrot (Windows: dist/wzlcarrot.exe)"
