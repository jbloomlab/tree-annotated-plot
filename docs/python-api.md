# Python API

## `tree_annotated_plot.plot`

::: tree_annotated_plot.plot
    options:
      heading_level: 3

## `PlotConfig`

The single source of truth for plot-parameter descriptions. The
`tree-annotated-plot` CLI generates its options from this dataclass
(see [Command line](cli.md)), and the `tree_annotated_plot.plot` function accepts the
same keyword arguments.

::: tree_annotated_plot.PlotConfig
    options:
      heading_level: 3
      members_order: source
      show_if_no_docstring: true

## Tree loading

::: tree_annotated_plot.load_auspice
    options:
      heading_level: 3

::: tree_annotated_plot.TreeNode
    options:
      heading_level: 3
      members:
        - name
        - x
        - y
        - children
        - is_tip
