# tree-annotated-plot

Plot a phylogenetic tree alongside an Altair / Vega-Lite chart whose
categorical axis is reordered to match the tree's tip order.

The package's headline behavior: **the tree dictates strain order; the
chart follows.** Whatever order your chart originally had — alphabetical,
clade-grouped, sorted by some other field — gets overridden so each
chart row sits next to the matching tree tip.

## What it does

You give it two things:

1. A phylogenetic tree (Auspice JSON v2).
2. A Vega-Lite chart whose categorical axis encodes the strain field
   (e.g. `y=alt.Y("strain:N")`).

It produces a combined Altair chart with the tree drawn alongside the
chart, tips aligned row-for-row with the chart's strain rows. Works
with `Chart` / `LayerChart` / `FacetChart` / `HConcatChart` /
`VConcatChart` / `ConcatChart`, with the strain encoding on either
axis. The tree drops to whichever side of the chart the strain labels
sit on by default (left for y-axis, bottom for x-axis).

## 30-second example

```python
import altair as alt
import pandas as pd
import tree_annotated_plot as tap

# Your data — a chart with strain on y.
df = pd.DataFrame(
    [
        {"strain": s, "serum": serum, "titer": v}
        for s, serum, v in [("A", "s1", 100), ("B", "s1", 200),
                             ("C", "s1", 400), ("D", "s1", 800)]
    ]
)
chart = (
    alt.Chart(df)
    .mark_circle()
    .encode(x="titer:Q", y="strain:N")
    .properties(width=300, height=200)
)

# Auspice JSON tree (path or dict or pre-parsed TreeNode).
tree = "h3n2.auspice.json"

out = tap.plot(
    tree, chart,
    chart_strain_field="strain",
    tree_strain_field="name",
    branch_length="div",
)
out.save("combined.html")
```

The result is an `alt.HConcatChart` with the tree on the left and the
chart on the right, with the chart's `y` sort overridden to the tree's
depth-first tip order.

## Two surfaces, one config

The same configuration is exposed through two interfaces, both backed
by [`PlotConfig`](python-api.md#tree_annotated_plot.PlotConfig):

- **Python**: `tap.plot(tree, chart, **kwargs)` →
  [Python API](python-api.md).
- **CLI**: `tree-annotated-plot --tree ... --chart-spec ...` →
  [Command line](cli.md).

A Vega-Lite chart saved with `chart.save("foo.json")` (or `.html`) can
be fed straight into either, so you can build the chart in one process
and combine it with a tree in another.

## License

Released under the [MIT License](https://github.com/jbloomlab/tree-annotated-plot/blob/main/LICENSE).
