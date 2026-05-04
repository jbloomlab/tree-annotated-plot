# Command line

The `tree-annotated-plot` command pairs a saved Vega-Lite chart spec
(JSON or HTML) with an Auspice JSON tree and writes the combined plot
to disk.

The configuration options below are auto-generated from
[`PlotConfig`](python-api.md#tree_annotated_plot.PlotConfig), so
descriptions and CLI `--help` text are guaranteed to match.

## Quickstart

```bash
tree-annotated-plot \
    --tree h3n2.auspice.json \
    --chart titers.json \
    --output combined.html \
    --chart-strain-field axis_label \
    --tree-strain-field derived_haplotype \
    --branch-length div
```

The output's format is dispatched on the file extension: `.html`,
`.json`, `.png`, `.svg`, `.pdf` are all accepted.

## Reference

::: mkdocs-click
    :module: tree_annotated_plot.cli
    :command: main
