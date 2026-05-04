# `tree-annotated-plot` – Claude Code Notes

- **Keep CLAUDE.md, README.md, and the docs site updated** when changing the
  code. `CLAUDE.md` describes programming conventions; `README.md` describes
  basic use; `docs/` is the user-facing reference. Don't let them drift.
- **Single source of truth — `pyproject.toml`**: canonical for dependencies,
  supported Python version, build config, tool settings. Don't restate any of
  these in prose; refer to `pyproject.toml`.
- **Single source of truth — `PlotConfig` and `_config.py`**: every plot-parameter
  description lives in `_config.py`. For styling/behavior knobs, the source is
  the field's `Annotated[T, "<description>"]` metadata on `PlotConfig`; the
  click `--help` text reads it directly, and `tree_annotated_plot.plot.__doc__`
  is assembled at import time by `_config._render_numpy_params`, so the
  REPL / mkdocstrings rendering pulls from the same string. Add Python-only
  prose for a field by setting `_config.PARAM_DOC_EXTRAS[field_name] = "..."`.
  Adding a parameter = a new `PlotConfig` field + a kwarg in
  `tree_annotated_plot.plot`'s signature with the same default. The three
  data-input parameters (`tree`, `chart`, `output`) can't sit on `PlotConfig`
  because their *types* differ between surfaces (the Python API accepts live
  `altair.Chart` / `dict` / `TreeNode`; the CLI only accepts file paths), but
  their descriptions are still single-sourced as
  `_config.{TREE,CHART,OUTPUT}_DESCRIPTION` constants — both the CLI's
  `--help` and `_plot.py`'s `_PLOT_DOC_HEADER` interpolate them.
- **Docstring style**: NumPy (Parameters / Returns sections with the
  `----------` underline), matching `mkdocs.yml`'s
  `docstring_style: numpy`. Don't mix Google-style `Args:` blocks in;
  mkdocstrings won't render them consistently.
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
- **Two surfaces, one config**: `tree_annotated_plot.plot()` and the `tree-annotated-plot`
  CLI both accept the same parameters via `PlotConfig`. They converge on
  `_build(tree, chart, config)` so they can never disagree.
- **Tests must remain green at every commit on `main`.** Single-developer
  workflow with no PRs (yet) — discipline replaces review. Lint + format +
  pytest before committing:
  ```bash
  scripts/check.sh
  ```
  The same three checks run in CI via
  [`.github/workflows/ci.yml`](.github/workflows/ci.yml) on push to
  `main` and on PRs (CI also fetches the upstream Kikawa Auspice JSONs
  so real-data tests run rather than skip). Local green ≈ CI green.
- **Build docs alongside checks** when changing public API surface:
  ```bash
  scripts/build_docs.sh
  ```
  `--strict` mode catches broken mkdocstrings references and missing
  cross-links. The script first calls
  `scripts/generate_docs_assets.py` to render `docs/images/*.svg`
  and `docs/charts/*.html` from the example modules; both
  directories are **gitignored** — never commit anything into them.
  The same asset script runs in CI before `mkdocs build`.
- **Eyeball examples after any rendering change.** There are no
  image-snapshot regression tests (vl-convert/font/platform variance
  makes them flaky), so visual regressions only get caught by
  looking. After any change to `_plot.py`, `_tree.py`, the example
  scripts, or anything they touch: run `scripts/build_docs.sh`, open
  `site/examples.html`, and click through each example — both the
  embedded SVG and the interactive HTML link. Confirm tip-row
  alignment, tree orientation, scale bar (if applicable),
  tooltips, and any selection/cohort bindings still work. The full
  recipe is in `README.md` under "Visual verification after code
  changes". When telling the user a rendering-affecting task is
  done, also report whether you ran this check (and that you
  cannot, from a non-interactive shell, actually verify the rendered
  output yourself — they need to look).
- **Docs are auto-deployed**. The
  [`.github/workflows/docs.yml`](.github/workflows/docs.yml)
  workflow runs on every push to `main`, generates assets, builds
  with `mkdocs build --strict`, and deploys to GitHub Pages
  (https://jbloomlab.github.io/tree-annotated-plot/). Pages source
  must be set to "GitHub Actions" in repo Settings; the workflow's
  `permissions:` block already declares `pages: write` and
  `id-token: write` so no further config is needed.
- **Releases are tag-driven**. Push a `vX.Y.Z` tag (after bumping
  `pyproject.toml`'s `version`) and
  [`.github/workflows/release.yml`](.github/workflows/release.yml)
  builds wheel + sdist and publishes to PyPI via trusted publishing
  (OIDC — no token in the repo). The build job verifies the tag and
  `pyproject.toml` version match before publishing. Per-release recipe
  and one-time PyPI configuration steps are in `README.md` under
  "Releasing a new version".
- **Adding a new example** (full recipe in `README.md`):
  1. Self-contained module under `examples/` with module-level
     helpers (callable from outside).
  2. New clause in `scripts/generate_docs_assets.py` that produces a
     `.svg` (into `docs/images/`) + `.html` (into `docs/charts/`).
  3. New section in `docs/examples.md` matching the existing
     three-section template (motivation → embedded SVG +
     interactive link → reproduce: CLI first, Python second).
  4. `scripts/build_docs.sh` confirms the page renders.
- **Iterating on docs**: prefer `mkdocs serve` (live-reload local
  server) for content/layout changes — much faster than
  `build_docs.sh` and shows the actual rendered page in your
  browser. Use `build_docs.sh` for the strict pre-commit
  verification.
