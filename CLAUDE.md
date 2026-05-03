# `tree-annotated-plot` – Claude Code Notes

- **Keep CLAUDE.md, README.md, and the docs site updated** when changing the
  code. `CLAUDE.md` describes programming conventions; `README.md` describes
  basic use; `docs/` is the user-facing reference. Don't let them drift.
- **Single source of truth — `pyproject.toml`**: canonical for dependencies,
  supported Python version, build config, tool settings. Don't restate any of
  these in prose; refer to `pyproject.toml`.
- **Single source of truth — `PlotConfig`**: every plot-parameter description
  lives in `_config.py` as `Annotated[T, "<description>"]`. `tap.plot`'s
  docstring, the click `--help` text, and the rendered docs all pull from
  there. Adding a parameter = one edit (a new field), not three.
- **Fail fast**: validate inputs early and raise clear `ValueError` on
  unexpected data. Prefer assertions and explicit error messages over silent
  fallbacks. Tip-set reconciliation errors should include sample values from
  both sides plus candidate-field hints when possible.
- **Pure-Python package**: managed via `pyproject.toml` and a plain `venv`
  (not conda). Required Python version specified in `pyproject.toml`. Develop
  with:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -e ".[dev,docs]"
  ```
  The `src/` layout requires `dev-mode-dirs = ["src"]` under
  `[tool.hatch.build.targets.wheel]` for editable installs to work.
- **Use default `black` / `ruff` line length.** Do not add `line-length`
  overrides to `pyproject.toml` unless explicitly requested.
- **API shape**: the user supplies their plot as a Vega-Lite chart (an
  `altair.Chart`-or-subclass object, a JSON path, an HTML path, or a parsed
  spec dict). The package introspects the chart to find the strain encoding
  on `x` or `y`, overrides its sort to match the tree's tip order, and
  hconcat's or vconcat's a tree panel on the matching side. Tree dictates
  tip ordering; plot follows.
- **Two surfaces, one config**: `tap.plot()` and the `tree-annotated-plot`
  CLI both accept the same parameters via `PlotConfig`. They converge on
  `_build(tree, chart, config)` so they can never disagree.
- **Tests must remain green at every commit on `main`.** Single-developer
  workflow with no PRs (yet) — discipline replaces review. Lint + format +
  pytest before committing:
  ```bash
  scripts/check.sh
  ```
- **Build docs alongside checks** when changing public API surface:
  ```bash
  scripts/build_docs.sh
  ```
  `--strict` mode catches broken mkdocstrings references and missing
  cross-links.
