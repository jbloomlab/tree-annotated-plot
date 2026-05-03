#!/usr/bin/env bash
# Run pytest, ruff, and black --check against the project's .venv.
# Exits non-zero if any check fails. Run at every phase boundary.
# Eventually graduates to a GitHub Actions workflow.
set -euo pipefail

cd "$(dirname "$0")/.."

VENV_PY=".venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
    echo "scripts/check.sh: $VENV_PY not found; create the venv first" >&2
    exit 2
fi

echo "==> pytest"
.venv/bin/pytest tests/

echo "==> ruff check"
.venv/bin/ruff check .

echo "==> black --check"
.venv/bin/black --check .

echo "all checks passed"
