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

Full API reference + CLI reference + worked examples:

```bash
.venv/bin/pip install -e ".[docs]"
.venv/bin/mkdocs serve
```

See `docs/` for the source.

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
