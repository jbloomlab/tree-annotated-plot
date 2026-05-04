# `tree-annotated-plot`: annotate the axis of an Altair / Vega-Lite plot with a phylogenetic tree

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

This is a Python package from the [Bloom lab](https://jbloomlab.org/) that allows you to combine an Altair / Vega-Lite plot with a Nextstrain JSON of a phylogenetic tree so that the tree is aligned to annotate strains on the axis of the plot.
See [https://jbloomlab.github.io/tree-annotated-plot/](https://jbloomlab.github.io/tree-annotated-plot/) for detailed documentation.

> **Note:** charts must be saved from altair 6+ (Vega-Lite v6). Older specs raise by default; pass `--no-strict-version` (CLI) or `strict_version=False` (Python) to override at your own risk. See the [docs](https://jbloomlab.github.io/tree-annotated-plot/) for details.

## Notes for developing the package

### Installation (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,docs]"
```

[pyproject.toml](pyproject.toml) is the canonical source for the supported Python
version and runtime dependencies.

### Visual verification after code changes

This package has automated tests for chart **structure** (encodings,
sort order, tip reconciliation, scale-bar arithmetic, etc.), but
**not** for chart **appearance** — there are no image-snapshot
regression tests, because rendering is sensitive to fonts,
`vl-convert-python` versions, and platform differences in ways that
make pixel-level comparison flaky in practice.

So the discipline is manual: any time you change code that affects
rendering (`src/tree_annotated_plot/_plot.py`,
`src/tree_annotated_plot/_tree.py`, the example scripts under
`examples/`, or anything they touch), run the full check below and
**eyeball every example** before considering the change done.

```bash
bash scripts/check.sh        # lint + format + pytest (all 100+ tests)
bash scripts/build_docs.sh   # regenerates docs/images + docs/charts and runs mkdocs --strict
```

Then open `site/examples.html` in a browser and, for each example:

1. Look at the embedded SVG screenshot. Does it match what the
   feature you changed should produce? Are tip rows still aligned with
   the chart rows? Is the tree's tip-end facing the chart? Is the
   scale bar (if enabled) centered and labeled correctly?
2. Click "Open the interactive chart →". Hover tips to confirm
   tooltips fire; if there's a cohort selector (Kikawa examples),
   toggle it; pan/zoom if relevant.
3. Compare against the
   [deployed site](https://jbloomlab.github.io/tree-annotated-plot/)
   (which still reflects `main` before your change) for what "good"
   looks like.

If something visibly regresses, fix it before pushing — there's no
CI gate that will catch a visual regression for you.

### Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every
push to `main` and every pull request: it installs the package, fetches
the upstream Kikawa Auspice JSONs (so the real-data tests actually
exercise rather than skip), builds the Kikawa titer chart specs, and
runs `ruff check`, `black --check`, and `pytest tests/`. This mirrors
[`scripts/check.sh`](scripts/check.sh) — green locally should mean
green in CI.

A separate workflow,
[`.github/workflows/docs.yml`](.github/workflows/docs.yml), builds the
docs site on every push to `main` and every PR (catching broken
mkdocstrings refs / missing images / unresolved cross-links before
merge), and additionally deploys `site/` to GitHub Pages on push to
`main`.

A third workflow,
[`.github/workflows/release.yml`](.github/workflows/release.yml),
builds the sdist + wheel and publishes them to PyPI when a `v*` tag
is pushed (see "Releasing a new version" below).

### Releasing a new version

Releases are fully automated by tag push. Trusted publishing (OIDC)
means **no API token or password is stored in the repo** — PyPI
authenticates the workflow via its repo + workflow filename +
environment.

One-time setup (only needed before the first release):

1. Reserve `tree-annotated-plot` on [PyPI](https://pypi.org/) (first
   successful publish creates it; or claim it manually via
   `pip install build && python -m build && twine upload dist/*` from a
   maintainer machine).
2. On PyPI, go to the project → "Publishing" tab → "Add a new pending
   publisher". Fill in: owner `jbloomlab`, repository
   `tree-annotated-plot`, workflow filename `release.yml`, environment
   `pypi`.
3. (Optional but recommended) On GitHub, repo Settings → Environments
   → New environment → name `pypi`. Add yourself as a required
   reviewer if you want a manual approval gate before each release
   lands on PyPI.

Per-release recipe (every time):

```bash
# 1. Edit pyproject.toml and bump `version = "X.Y.Z"`.
# 2. Commit and tag (the workflow verifies they match before publishing).
git commit -am "release vX.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

The `release` workflow then builds, verifies tag ⇋ version match, and
publishes to PyPI.

### Documentation
The docs are at
[https://jbloomlab.github.io/tree-annotated-plot/](https://jbloomlab.github.io/tree-annotated-plot/).
They are auto-deployed by GitHub Actions on every push to `main` —
[`.github/workflows/docs.yml`](.github/workflows/docs.yml) installs
the package + docs extras, runs
[`scripts/generate_docs_assets.py`](scripts/generate_docs_assets.py)
to render images and standalone interactive HTML for each
example, then `mkdocs build --strict`, and uploads `site/` as a
GitHub Pages artifact.

### Building documentation locally

For day-to-day editing of the docs, use MkDocs's live-reload server
(saves go straight to your browser):

```bash
mkdocs serve              # http://localhost:8000
```

To do this on the Fred Hutch remote server, do:
```bash
mkdocs serve -a $(hostname -i | awk '{print $1}'):$(fhfreeport)
```

For the strict build that matches CI (catches broken
[`mkdocstrings`](https://mkdocstrings.github.io/) refs, missing
images, unresolved cross-links):

```bash
bash scripts/build_docs.sh
```

This first runs `scripts/generate_docs_assets.py` (so the example
SVGs and interactive HTMLs exist before MkDocs reads `docs/`), then
`mkdocs build --strict`. Output lands in `site/`.

### Adding a new example

The docs follow a single template per example: a short motivation,
an embedded SVG screenshot, a link to the fully-interactive
standalone HTML, and the commands to reproduce (CLI form first,
Python API form second). [`docs/examples.md`](docs/examples.md)
shows the existing shape. To add another:

1. Drop a runnable script into `examples/`. Keep helpers at module
   level (callable from outside) so the asset script can import them.
2. Add a clause to `scripts/generate_docs_assets.py` that imports
   the script and calls `tree_annotated_plot.plot(...)` followed by saving both
   `<name>.svg` (into `docs/images/`) and `<name>.html` (into
   `docs/charts/`). Both directories are gitignored — only the
   asset script writes there.
3. Add a section to `docs/examples.md` matching the template.
4. Run `bash scripts/build_docs.sh` and open `site/examples.html`
   to verify. Push when happy; the deployed site updates on the
   next CI run.
