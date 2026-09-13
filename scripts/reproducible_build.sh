#!/usr/bin/env bash
# Build sdist+wheel with a pinned SOURCE_DATE_EPOCH for a reproducible build,
# then print hashes so two runs can be compared.
set -euo pipefail
cd "$(dirname "$0")/.."

export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"
rm -rf dist
uv build
echo "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"
sha256sum dist/* 2>/dev/null || shasum -a 256 dist/*
