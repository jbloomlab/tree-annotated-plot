# Examples

Three runnable examples that span the package's API surface. Each is
shown with a static screenshot of the rendered output and a link to
the **fully interactive** Altair-rendered version, with tooltips,
selection bindings, and (for the Kikawa charts) the cohort-toggle
legend.

## 1. Synthetic 8-tip tree — minimum end-to-end

The smallest possible call to
[`tree_annotated_plot.plot`](python-api.md#tree_annotated_plot.plot):
8 tips in two clades, four titer values per tip, a flat `alt.Chart`
with `strain:N` on the y-axis. Useful when you're sanity-checking an
installation or understanding the API at minimum complexity.

The source for this example lives in
[`examples/synthetic_example.py`](https://github.com/jbloomlab/tree-annotated-plot/blob/main/examples/synthetic_example.py){target="_blank"}.
Running it produces `examples/data/synthetic_tree.json` (the Auspice
tree) and `examples/data/synthetic_chart.json` (the saved Vega-Lite
chart spec); the CLI invocation below consumes those two files.

![Synthetic combined chart](images/synthetic_example.svg)

[Open the interactive chart in a new tab →](charts/synthetic_example.html){target="_blank"}

### Reproduce — command line

```bash
python examples/synthetic_example.py
tree-annotated-plot \
    --tree examples/data/synthetic_tree.json \
    --chart examples/data/synthetic_chart.json \
    --output examples/data/synthetic_example.html \
    --chart-strain-field strain \
    --tree-strain-field name \
    --branch-length div \
    --tree-size 140
```

### Reproduce — Python API

This can also be done via the Python API using:

```python
import tree_annotated_plot

# `synthetic_auspice()` returns an Auspice JSON dict; build_chart()
# returns an alt.Chart with strain on y. Both live in
# examples/synthetic_example.py.
out = tree_annotated_plot.plot(
    synthetic_auspice(),
    build_chart(synthetic_titers()),
    chart_strain_field="strain",
    tree_strain_field="name",
    branch_length="div",
    tree_size=140,
)
```

## 2. Kikawa H3N2 — vertical layout, real Auspice tree

The realistic case: HA neutralization titers for ~50 H3N2 strains
across multiple sera cohorts, paired with the matching Nextstrain
Auspice tree from
[jbloomlab/flu-seqneut-2025to2026](https://github.com/jbloomlab/flu-seqneut-2025to2026){target="_blank"}.
You can [view the tree on Nextstrain](https://nextstrain.org/community/jbloomlab/flu-seqneut-2025to2026@main/H3N2){target="_blank"}
or download the
[raw Auspice JSON](https://raw.githubusercontent.com/jbloomlab/flu-seqneut-2025to2026/main/auspice/flu-seqneut-2025to2026_H3N2.json){target="_blank"}
that this example feeds into `tree-annotated-plot`.

The chart is a `VConcatChart` wrapping a `FacetChart` wrapping a
`LayerChart` (errorband + median-points), with a strain encoding on
each layer — `tree_annotated_plot.plot` walks all of it and rewrites
every encoding's sort to the tree's tip order in a single deepcopy.

This example also demonstrates the case the package was *designed*
for: the chart's strain values and the tree's tip identifiers come
from **different fields** but join by value. The chart encodes
`axis_label:N` (a haplotype label like `K:S96C,K207Q,V223I`); the
tree carries the same label at `node_attrs.derived_haplotype.value`.
You name them with `chart_strain_field` and `tree_strain_field`
independently.

The titer chart on its own (no tree):

![H3N2 titer chart, no tree](images/h3n2_chart_only.svg)

[Open the interactive chart in a new tab →](charts/h3n2_chart_only.html){target="_blank"}

With the tree panel added by `tree-annotated-plot`:

![H3N2 combined chart](images/h3n2_combined.svg)

[Open the interactive chart in a new tab →](charts/h3n2_combined.html){target="_blank"}

The strain axis is on `y`, so `tree_annotated_plot.plot` auto-picks
the **vertical layout** (`tree_location` defaults to `"left"` on a
y-encoded strain): result is an `HConcatChart` with the tree on the
left and a centered scale bar at the bottom of the tree panel. The
chart's natural strain-axis labels are kept exactly as the
chart-builder wrote them (fonts, ticks, axis title, and all), and the
tree's dashed leader lines stop at the tree panel's chart-facing
edge.

### Optional: connect leaders all the way to the labels

If you'd prefer the dashed leaders to run flush into the strain
labels themselves (with no break between tip and label), set
`connect_leader_to_label=True`. This involves moving the labels off
the chart's natural axis and into the tree panel, with a few
trade-offs to be aware of:

- The chart's strain-axis is replaced: any labels, ticks, title,
  or custom `axis=...` you set on that encoding are dropped, and
  replacement labels are rendered alongside the tree.
- Label widths are estimated, not measured exactly, so layout may
  need tuning. The two main knobs are `strain_label_font_size`
  (default 10) and `shift_tree_loc` (a manual pixel offset that
  moves the tree closer to the labels).

The example below turns on label connection, shrinks the labels to
9 pt, and uses `shift_tree_loc=60` to bring the tree flush against
them:

![H3N2 with label connection at 9pt font](images/h3n2_combined_label_connect.svg)

[Open the interactive chart in a new tab →](charts/h3n2_combined_label_connect.html){target="_blank"}

CLI flags: `--connect-leader-to-label --strain-label-font-size 9
--shift-tree-loc 60`. In Python:
`connect_leader_to_label=True, strain_label_font_size=9, shift_tree_loc=60`.

### Reproduce — command line

```bash
python examples/fetch_auspice_data.py
python examples/flu-seqneut-2025to2026_titer_charts.py
tree-annotated-plot \
    --tree examples/data/flu-seqneut-2025to2026_H3N2.json \
    --chart examples/data/flu-seqneut-2025to2026_H3N2_titers.json \
    --chart-strain-field axis_label \
    --tree-strain-field derived_haplotype \
    --branch-length div \
    --tree-size 140 \
    --scale-bar \
    --branch-length-units substitutions \
    --output examples/data/h3n2_combined.json
```

### Reproduce — Python API

This can also be done via the Python API using:

```python
out = tree_annotated_plot.plot(
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

## 3. Kikawa H1N1 — horizontal layout, tree below the chart

Same data shape, same `VConcat(Facet(Layer))` chart structure, but
the chart-builder encodes `axis_label` on `x` instead of `y`. The
strain labels then render at the *bottom* of the chart panel, so
`tree_annotated_plot.plot`'s default `tree_location="bottom"` puts
the tree **underneath** the chart with its tips at the top — flush
against the strain labels above. The output is a `VConcatChart`.
Branches in the tree grow upward (root at the bottom of the tree
panel, tips at the top) and the scale bar's text rotates 270° to
read parallel to the now-vertical bar.

You can [view the H1N1 tree on Nextstrain](https://nextstrain.org/community/jbloomlab/flu-seqneut-2025to2026@main/H1N1){target="_blank"}
or download the
[raw Auspice JSON](https://raw.githubusercontent.com/jbloomlab/flu-seqneut-2025to2026/main/auspice/flu-seqneut-2025to2026_H1N1.json){target="_blank"}
fed into the example.

This example demonstrates layout auto-detection: nothing about the
call differs from the H3N2 case beyond the chart itself. The package
detects which axis carries `chart_strain_field` and dispatches.

The titer chart on its own (no tree):

![H1N1 titer chart, no tree](images/h1n1_chart_only.svg)

[Open the interactive chart in a new tab →](charts/h1n1_chart_only.html){target="_blank"}

With the tree panel added by `tree-annotated-plot`:

![H1N1 combined chart](images/h1n1_combined.svg)

[Open the interactive chart in a new tab →](charts/h1n1_combined.html){target="_blank"}

The chart-builder script puts the cohort legend **above** the H1N1
faceted chart specifically so that the strain labels land on the
chart panel's bottom edge — which is where the tree's tips sit when
vconcat'd underneath. For the H3N2 case (strain labels on the left)
the legend stays below the chart panel.

### Reproduce — command line

```bash
python examples/fetch_auspice_data.py
python examples/flu-seqneut-2025to2026_titer_charts.py
tree-annotated-plot \
    --tree examples/data/flu-seqneut-2025to2026_H1N1.json \
    --chart examples/data/flu-seqneut-2025to2026_H1N1_titers.json \
    --chart-strain-field axis_label \
    --tree-strain-field derived_haplotype \
    --branch-length div \
    --tree-size 140 \
    --scale-bar \
    --branch-length-units substitutions \
    --output examples/data/h1n1_combined.json
```

### Reproduce — Python API

This can also be done via the Python API using:

```python
out = tree_annotated_plot.plot(
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

## Notes

!!! note "Input chart format: prefer `.json` over `.html`"
    This applies to the chart you **pass into** `tree-annotated-plot`
    via `--chart` / the Python `chart` argument — *not* to the output.
    The chart you feed in can be saved by altair as either a portable
    Vega-Lite JSON spec (`chart.save("titers.json")`) or an HTML page
    (`chart.save("titers.html")`). We recommend `.json` for the input:
    it's the canonical Vega-Lite exchange format and `tree-annotated-plot`
    parses it directly. The `.html` path works only with altair's default
    save template — custom `template=` arguments aren't supported, so
    JSON is the more robust choice.

    For the **output** that `tree-annotated-plot` writes via `--output`,
    `.html` is a perfectly good choice if you want a self-contained
    interactive page that opens in any browser. `.json` is smaller and
    portable across Vega-Lite hosts; pick whichever fits your downstream
    use.

!!! warning "Charts must come from altair 6+ (Vega-Lite v6)"
    The `--chart` / `chart` argument must be a Vega-Lite v6 spec.
    Re-save older charts from an altair 6+ environment with
    `chart.save(...)`. `--no-strict-version` /
    `strict_version=False` lets you proceed anyway, at the risk of
    rendering bugs from cross-version spec drift.
