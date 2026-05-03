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
if [[ ! -x "$VENV_MKDOCS" ]]; then
    echo "scripts/build_docs.sh: $VENV_MKDOCS not found." >&2
    echo "Install docs deps: .venv/bin/pip install -e '.[docs]'" >&2
    exit 2
fi

echo "==> mkdocs build --strict"
"$VENV_MKDOCS" build --strict

echo "docs built into ./site"
