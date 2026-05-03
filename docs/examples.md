# Examples

## Synthetic example

A tiny end-to-end runnable in seconds, with an 8-tip tree and a
matching 4-strain titer table. See
[`examples/synthetic_example.py`](https://github.com/jbloomlab/tree-annotated-plot/blob/main/examples/synthetic_example.py).

```bash
python examples/synthetic_example.py
```

Outputs `examples/data/synthetic_example.html` (interactive) and
`.png` (static raster).

## Kikawa et al. (2026) flu seqneut

The realistic case: HA neutralization titers for ~50 H3N2 (or H1N1)
strains across multiple sera cohorts, paired with the matching Auspice
tree. The chart-builder lives in
[`examples/flu-seqneut-2025to2026_titer_charts.py`](https://github.com/jbloomlab/tree-annotated-plot/blob/main/examples/flu-seqneut-2025to2026_titer_charts.py)
and produces the saved Vega-Lite JSONs / HTMLs that the CLI then
consumes alongside the Auspice JSONs.

### Fetch the trees

```bash
python examples/fetch_auspice_data.py
```

Downloads to `examples/data/`:

- `flu-seqneut-2025to2026_H3N2.json` — vertical layout (strain on `y`).
- `flu-seqneut-2025to2026_H1N1.json` — horizontal layout (strain on `x`).

### Build the saved chart specs

```bash
python examples/flu-seqneut-2025to2026_titer_charts.py
```

Writes `flu-seqneut-2025to2026_{H3N2,H1N1}_titers.{html,json}` into
`examples/data/`.

### Combine

H3N2 (vertical, tree on the left, scale bar at the bottom):

```bash
tree-annotated-plot \
    --tree examples/data/flu-seqneut-2025to2026_H3N2.json \
    --chart-spec examples/data/flu-seqneut-2025to2026_H3N2_titers.json \
    --chart-strain-field axis_label \
    --tree-strain-field derived_haplotype \
    --branch-length div \
    --tree-size 140 \
    --scale-bar \
    --branch-length-units substitutions \
    --output examples/data/h3n2_combined.html
```

H1N1 (horizontal, tree below the chart; the `--tree-location bottom`
default puts the tree under the chart's strain labels):

```bash
tree-annotated-plot \
    --tree examples/data/flu-seqneut-2025to2026_H1N1.json \
    --chart-spec examples/data/flu-seqneut-2025to2026_H1N1_titers.json \
    --chart-strain-field axis_label \
    --tree-strain-field derived_haplotype \
    --branch-length div \
    --tree-size 140 \
    --scale-bar \
    --branch-length-units substitutions \
    --output examples/data/h1n1_combined.html
```

The chart-builder script puts the cohort legend *above* the H1N1
faceted chart specifically so the strain labels land at the bottom
edge of the chart panel — which is where the tree's tips sit when
vconcat'd underneath. For H3N2 (strain labels on the left) the legend
stays below.
