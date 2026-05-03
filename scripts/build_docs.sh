#!/usr/bin/env bash
# Build the documentation site with mkdocs --strict so any broken
# reference (typo'd identifier in mkdocstrings, missing CLI module,
# unresolved cross-link) fails the build instead of slipping through.
#
# Run at every phase boundary alongside scripts/check.sh while the
# project is pre-CI. Eventually graduates to .github/workflows/docs.yml.
set -euo pipefail

cd "$(dirname "$0")/.."

VENV_MKDOCS=".venv/bin/mkdocs"
VENV_PYTHON=".venv/bin/python"
if [[ ! -x "$VENV_MKDOCS" || ! -x "$VENV_PYTHON" ]]; then
    echo "scripts/build_docs.sh: $VENV_MKDOCS or $VENV_PYTHON not found." >&2
    echo "Install docs deps: .venv/bin/pip install -e '.[docs]'" >&2
    exit 2
fi

# Render the chart assets (docs/images/*.png + docs/charts/*.html) the
# docs pages embed. Both directories are gitignored; this script is the
# only thing that should write to them.
echo "==> generate_docs_assets.py"
"$VENV_PYTHON" scripts/generate_docs_assets.py

echo "==> mkdocs build --strict"
"$VENV_MKDOCS" build --strict

echo "docs built into ./site"
