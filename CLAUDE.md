# `tree-annotated-plot` – Claude Code Notes

- **Keep CLAUDE.md and README.md updated** when updating the code. `CLAUDE.md` describes programming principles; `README.md` describes use of package for users.
- **Single source of truth**: `pyproject.toml` is canonical for dependencies, supported Python version, build config, and tool settings. Do not restate any of these in `CLAUDE.md`, `README.md`, or other prose — refer to `pyproject.toml` instead so the docs cannot drift from the spec.
- **Fail fast**: validate inputs early and raise clear errors on unexpected data. Prefer assertions and explicit `ValueError` over silent fallbacks.
- **Pure-Python package**: managed via `pyproject.toml` and a plain `venv` (not conda). Required Python version specified in `pyproject.toml`. Develop with:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -e ".[dev]"
  ```
  The `src/` layout requires `dev-mode-dirs = ["src"]` under `[tool.hatch.build.targets.wheel]` for editable installs to work.
- **Use default `black` / `ruff` line length.** Do not add `line-length` overrides to `pyproject.toml` unless explicitly requested.
- **API shape**: the user supplies their line plot as an `altair.Chart` object (not raw data + a config). The package introspects the chart to find the strain y-encoding, overrides its sort to match the tree's tip order, and `hconcat`s a tree panel to its left. Tree dictates tip ordering; plot follows.
- **Lint and format before committing**:
  ```bash
  ruff check .
  black .
  ```
