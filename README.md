# tree-annotated-plot

Plot a phylogenetic tree alongside an Altair / Vega-Lite chart whose
categorical axis is reordered to match the tree's tip order.

The tree dictates strain order; the chart follows. The chart's
sort is overridden so each row sits next to the matching tree tip.

## Quickstart

### Python

```python
import altair as alt
import pandas as pd
import tree_annotated_plot as tap

df = pd.DataFrame(
    [{"strain": s, "serum": "s1", "titer": v}
     for s, v in [("A", 100), ("B", 200), ("C", 400), ("D", 800)]]
)
chart = (
    alt.Chart(df)
    .mark_circle()
    .encode(x="titer:Q", y="strain:N")
    .properties(width=300, height=200)
)

out = tap.plot(
    "h3n2.auspice.json", chart,
    chart_strain_field="strain",
    tree_strain_field="name",
    branch_length="div",
)
out.save("combined.html")
```

### Command line

```bash
tree-annotated-plot \
    --tree h3n2.auspice.json \
    --chart-spec titers.json \
    --output combined.html \
    --chart-strain-field axis_label \
    --tree-strain-field derived_haplotype \
    --branch-length div
```

`--chart-spec` accepts both `*.json` and `*.html` saved by altair's
`chart.save(...)`. The output extension determines the format
(`.html` / `.json` / `.png` / `.svg` / `.pdf`).

## Documentation

The canonical reference is the docs site at
[https://jbloomlab.github.io/tree-annotated-plot/](https://jbloomlab.github.io/tree-annotated-plot/).
It's auto-deployed by GitHub Actions on every push to `main` —
[`.github/workflows/docs.yml`](.github/workflows/docs.yml) installs
the package + docs extras, runs
[`scripts/generate_docs_assets.py`](scripts/generate_docs_assets.py)
to render PNG screenshots and standalone interactive HTML for each
example, then `mkdocs build --strict`, and uploads `site/` as a
GitHub Pages artifact.

### Building locally

For day-to-day editing of the docs, use MkDocs's live-reload server
(saves go straight to your browser):

```bash
pip install -e ".[docs]"
mkdocs serve              # http://localhost:8000
```

For the strict build that matches CI (catches broken
[`mkdocstrings`](https://mkdocstrings.github.io/) refs, missing
images, unresolved cross-links):

```bash
bash scripts/build_docs.sh
```

This first runs `scripts/generate_docs_assets.py` (so the example
PNGs and interactive HTMLs exist before MkDocs reads `docs/`), then
`mkdocs build --strict`. Output lands in `site/`.

### Adding a new example

The docs follow a single template per example: a short motivation,
a code excerpt, an embedded PNG screenshot, a link to the
fully-interactive standalone HTML, and the commands to reproduce.
[`docs/examples.md`](docs/examples.md) shows the existing shape. To
add another:

1. Drop a runnable script into `examples/`. Keep helpers at module
   level (callable from outside) so the asset script can import them.
2. Add a clause to `scripts/generate_docs_assets.py` that imports
   the script and calls `tap.plot(...)` followed by saving both
   `<name>.png` (into `docs/images/`) and `<name>.html` (into
   `docs/charts/`). Both directories are gitignored — only the
   asset script writes there.
3. Add a section to `docs/examples.md` matching the template.
4. Run `bash scripts/build_docs.sh` and open `site/examples.html`
   to verify. Push when happy; the deployed site updates on the
   next CI run.

## Installation (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,docs]"
```

`pyproject.toml` is the canonical source for the supported Python
version and runtime dependencies.

## License

Released under the [MIT License](LICENSE).
