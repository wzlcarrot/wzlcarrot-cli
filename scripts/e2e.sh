#!/usr/bin/env bash
# End-to-end smoke of the CLI (uses the installed binary if present, else uv run).
set -euo pipefail
cd "$(dirname "$0")/.."

export ZHIHU_CLI_NO_UPDATE_CHECK=1

if command -v wzlcarrot >/dev/null 2>&1; then
  WC="wzlcarrot"; ZH="zhihu"
else
  WC="uv run wzlcarrot"; ZH="uv run zhihu"
fi

$WC version
$WC --help >/dev/null
$WC plugins >/dev/null
$WC hooks >/dev/null
$WC connect --list >/dev/null
$WC license status >/dev/null
$WC doctor --offline >/dev/null
$WC zhihu --help >/dev/null
$ZH version >/dev/null

echo "e2e: all CLI smoke checks passed"
