# tree-annotated-plot

Plot a phylogenetic tree alongside an Altair / Vega-Lite chart whose
categorical axis is reordered to match the tree's tip order.

The package's headline behavior: **the tree dictates strain order; the
chart follows.** Whatever order your chart originally had — alphabetical,
clade-grouped, sorted by some other field — gets overridden so each
chart row sits next to the matching tree tip.

## What it does

You give it two things:

1. A phylogenetic tree as an [Auspice JSON v2](https://docs.nextstrain.org/projects/augur/en/stable/usage/json_format.html) file.
2. A Vega-Lite chart whose categorical axis encodes the strain field
   (e.g. `y=alt.Y("strain:N")`), saved as a Vega-Lite spec via
   [Altair](https://altair-viz.github.io/)'s `chart.save("titers.json")`.

It produces a combined Altair chart with the tree drawn alongside the
chart, tips aligned row-for-row with the chart's strain rows. Works
with `Chart` / `LayerChart` / `FacetChart` / `HConcatChart` /
`VConcatChart` / `ConcatChart`, with the strain encoding on either
axis. The tree drops to whichever side of the chart the strain labels
sit on by default (left for y-axis, bottom for x-axis).

## Installation

Released on [PyPI](https://pypi.org/project/tree-annotated-plot/).
Requires Python 3.13+.

```bash
pip install tree-annotated-plot
```

To pin a specific version:

```bash
pip install tree-annotated-plot==0.0.1
```

To install the bleeding edge directly from the
[GitHub source](https://github.com/jbloomlab/tree-annotated-plot):

```bash
pip install git+https://github.com/jbloomlab/tree-annotated-plot.git
```

For a development checkout (contributors), see the README's
[development install](https://github.com/jbloomlab/tree-annotated-plot#installation-development).

## 30-second example

Given an Auspice tree at `h3n2.auspice.json` and a Vega-Lite chart spec
at `titers.json`:

```bash
tree-annotated-plot \
    --tree h3n2.auspice.json \
    --chart titers.json \
    --output combined.html \
    --chart-strain-field strain \
    --tree-strain-field name \
    --branch-length div
```

The output format is dispatched on `--output`'s extension: `.html`,
`.json`, `.png`, `.svg`, or `.pdf` are all accepted. We recommend
`.json` for portability and `.html` for interactivity (see the
[examples](examples.md) for the trade-off in context).

## Command line and Python

The package can be used either from the command line (above) or as a
Python function. See [Command line](cli.md) for the CLI reference and
[Python API](python-api.md) for the Python entry point. Both surfaces
accept the same parameters and produce the same output.

!!! warning "Save your chart from altair 6+ (Vega-Lite v6)"
    `tree-annotated-plot` is built against Vega-Lite v6 — the spec
    format written by altair 6 and newer. A chart saved from older
    altair (which writes Vega-Lite v5 or earlier) raises a
    `ValueError` by default. Re-save it from an altair 6+
    environment with `chart.save("titers.json")`. If you can't
    upgrade and want to proceed anyway, pass `--no-strict-version`
    (CLI) or `strict_version=False` (Python) — but spec shapes
    differ across major versions, so rendering may be wrong. Charts
    saved from a *newer* Vega-Lite than tested are accepted with a
    warning (Vega-Lite is largely backward-compatible).

## License

Released under the [MIT License](https://github.com/jbloomlab/tree-annotated-plot/blob/main/LICENSE).
