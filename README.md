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
