# Examples

Three runnable examples that span the package's API surface. Each is
shown with a static screenshot of the rendered output and a link to
the **fully interactive** Altair-rendered version, where tooltips,
selection bindings, and (for the Kikawa charts) the cohort-toggle
legend all work just like they do in a Jupyter notebook.

## 1. Synthetic 8-tip tree — minimum end-to-end

The smallest possible call to [`tap.plot`](python-api.md#tree_annotated_plot.plot):
8 tips in two clades, four titer values per tip, a flat `alt.Chart`
with `strain:N` on the y-axis. Useful when you're sanity-checking a
tap.plot installation or understanding the API at minimum complexity.

```python
import tree_annotated_plot as tap

# `synthetic_auspice()` returns an Auspice JSON dict; build_chart()
# returns an alt.Chart with strain on y. Both live in
# examples/synthetic_example.py.
out = tap.plot(
    synthetic_auspice(),
    build_chart(synthetic_titers()),
    chart_strain_field="strain",
    tree_strain_field="name",
    branch_length="div",
    tree_size=140,
)
```

![Synthetic combined chart](images/synthetic_example.png)

[Open the interactive chart in a new tab →](charts/synthetic_example.html){target="_blank"}

To reproduce locally:

```bash
python examples/synthetic_example.py
# → examples/data/synthetic_example.{html,png}
```

## 2. Kikawa H3N2 — vertical layout, real Auspice tree

The realistic case: HA neutralization titers for ~50 H3N2 strains
across multiple sera cohorts, paired with the matching nextstrain
Auspice tree from
[jbloomlab/flu-seqneut-2025to2026](https://github.com/jbloomlab/flu-seqneut-2025to2026).
The chart is a `VConcatChart` wrapping a `FacetChart` wrapping a
`LayerChart` (errorband + median-points), with a strain encoding on
each layer — `tap.plot` walks all of it and rewrites every encoding's
sort to the tree's tip order in a single deepcopy.

This example also demonstrates the case the package was *designed*
for: the chart's strain values and the tree's tip identifiers come
from **different fields** but join by value. The chart encodes
`axis_label:N` (a haplotype label like `K:S96C,K207Q,V223I`); the
tree carries the same label at `node_attrs.derived_haplotype.value`.
You name them with `chart_strain_field` and `tree_strain_field`
independently:

```python
out = tap.plot(
    "examples/data/flu-seqneut-2025to2026_H3N2.json",
    chart,                          # built by examples/flu-seqneut-2025to2026_titer_charts.py
    chart_strain_field="axis_label",
    tree_strain_field="derived_haplotype",
    branch_length="div",
    tree_size=140,
    scale_bar=True,
    branch_length_units="substitutions",
)
```

The strain axis is on `y`, so `tap.plot` auto-picks the **vertical
layout** (`tree_location` defaults to `"left"` on a y-encoded
strain): result is an `HConcatChart` with the tree on the left, tips
flush against the chart's strain labels, and a centered scale bar at
the bottom of the tree panel.

![H3N2 combined chart](images/h3n2_combined.png)

[Open the interactive chart in a new tab →](charts/h3n2_combined.html){target="_blank"}

To reproduce:

```bash
python examples/fetch_auspice_data.py
python examples/flu-seqneut-2025to2026_titer_charts.py
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

## 3. Kikawa H1N1 — horizontal layout, tree below the chart

Same data shape, same `VConcat(Facet(Layer))` chart structure, but
the chart-builder encodes `axis_label` on `x` instead of `y`. The
strain labels then render at the *bottom* of the chart panel, so
`tap.plot`'s default `tree_location="bottom"` puts the tree
**underneath** the chart with its tips at the top — flush against
the strain labels above. The output is a `VConcatChart`. Branches in
the tree grow upward (root at the bottom of the tree panel, tips at
the top) and the scale bar's text rotates 270° to read parallel to
the now-vertical bar.

This example demonstrates layout auto-detection: nothing about the
call differs from the H3N2 case beyond the chart itself. The package
detects which axis carries `chart_strain_field` and dispatches.

```python
out = tap.plot(
    "examples/data/flu-seqneut-2025to2026_H1N1.json",
    chart,                          # H1N1 chart; strain encoded on x
    chart_strain_field="axis_label",
    tree_strain_field="derived_haplotype",
    branch_length="div",
    tree_size=140,
    scale_bar=True,
    branch_length_units="substitutions",
)
```

![H1N1 combined chart](images/h1n1_combined.png)

[Open the interactive chart in a new tab →](charts/h1n1_combined.html){target="_blank"}

The chart-builder script puts the cohort legend **above** the H1N1
faceted chart specifically so that the strain labels land on the
chart panel's bottom edge — which is where the tree's tips sit when
vconcat'd underneath. For the H3N2 case (strain labels on the left)
the legend stays below the chart panel.

To reproduce: same as H3N2 above, replacing `H3N2` with `H1N1`
everywhere.
