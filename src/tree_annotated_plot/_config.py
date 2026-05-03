"""`PlotConfig`: the single source of truth for plot-parameter descriptions.

Both `tap.plot` and the CLI consume `PlotConfig`. The `Annotated[T, str]`
metadata on each field doubles as the parameter description: it's pulled
into the function's `Args:` block at runtime (via the docstring decorator
in this module), and into each click option's `help` text by
`tree_annotated_plot.cli`. Adding a new parameter therefore takes one
edit (a new field with description), not three.
"""

from __future__ import annotations

import dataclasses
from typing import Annotated, Literal

TreeLocation = Literal["left", "right", "top", "bottom"]


@dataclasses.dataclass(frozen=True, kw_only=True)
class PlotConfig:
    """Configuration for `tap.plot`.

    Each field's type annotation is `Annotated[T, "<description>"]`. The
    description is the canonical text that appears in the function
    docstring, the click `--help`, and (later, in Phase 2j) the rendered
    docs site.
    """

    chart_strain_field: Annotated[
        str,
        "Required. The data-column name the chart's strain axis encodes "
        '(e.g. "strain" or "axis_label").',
    ]

    tree_strain_field: Annotated[
        str,
        "Required. Where on each tree tip to find the strain identifier. "
        'The literal string "name" selects the top-level Auspice node `name` '
        "field; any other value X selects node_attrs[X] (auto-unwrapping the "
        'Auspice {"value": ...} convention). Dotted paths are not accepted.',
    ]

    branch_length: Annotated[
        Literal["div", "num_date"],
        'Which Auspice node attribute supplies branch lengths. "div" '
        '(default) reads node_attrs.div. "num_date" reads '
        "node_attrs.num_date.value.",
    ] = "div"

    tree_size: Annotated[
        int,
        "Size in pixels of the tree's branch axis (the dimension "
        "perpendicular to the strain rows). For vertical layout (chart "
        "strain on `y`) this is the tree panel's *width*; for horizontal "
        "layout (chart strain on `x`) this is the tree panel's *height*. "
        "The tree's tip-axis dimension is computed from the chart's "
        "strain dimension so tips align row-for-row with chart rows.",
    ] = 100

    tree_location: Annotated[
        TreeLocation | None,
        "Where to draw the tree relative to the chart. y-encoded strain "
        'accepts "left" (default) or "right"; x-encoded strain accepts '
        '"bottom" (default) or "top". Defaults match where Vega-Lite '
        "renders strain-axis labels by default, so tips align with the "
        "labels. Specifying a value incompatible with the strain axis "
        "raises ValueError.",
    ] = None

    tree_line_width: Annotated[
        float,
        "Stroke width (px) for the tree's branch lines. Default 1.5.",
    ] = 1.5

    tree_node_size: Annotated[
        float,
        "Area (px²) of the small filled circles drawn at each tip. "
        "Default 28. Setting tree_node_size=0 disables the tip-circle "
        "layer entirely. Negative values raise.",
    ] = 28

    leader_line_width: Annotated[
        float,
        "Stroke width (px) for the dashed leader lines that connect each "
        "tip's branch endpoint to the strain row when the branch doesn't "
        "extend all the way to branch_max. Default 1.0. Setting "
        "leader_line_width=0 disables the leader-line layer entirely. "
        "Negative values raise.",
    ] = 1.0

    scale_bar: Annotated[
        bool,
        "Off by default. When on, adds a small bar in the tree panel "
        'whose length corresponds to a "nice" number (largest 1/2/5 * 10^k '
        "≤ 25% of the branch range). Sits at the tail end of the tip "
        "axis in extra pixel space, so tip-row alignment with the chart "
        "is preserved.",
    ] = False

    branch_length_units: Annotated[
        str | None,
        'Used only when scale_bar is on and branch_length="div": the unit '
        "string pasted after the bar's numeric length (e.g. "
        '"substitutions/site"). None renders unitless. We do not '
        'auto-detect divergence units. For branch_length="num_date" the '
        "label is always in years/months and this argument is ignored.",
    ] = None

    prune_tree_to_chart: Annotated[
        bool,
        "When off (default), tree tips not present in the chart's strain "
        "set are a fatal error. When on, those tips (and any internal "
        "nodes whose subtrees become empty) are dropped before drawing, "
        "with single-child internals collapsed into their kept child. "
        "Chart strains not present in the tree are *always* fatal "
        "regardless of this flag — pruning would silently lose plot data.",
    ] = False

    strict_version: Annotated[
        bool,
        "When on (default) the package raises ValueError if the chart "
        "spec's $schema URL identifies Vega-Lite 5 or earlier, or if the "
        "Auspice JSON's top-level `version` is not v2. When off, both "
        "cases become warnings and parsing proceeds. Has no effect on a "
        "live alt.Chart (the constructing altair version is necessarily "
        "the running altair version).",
    ] = True


def field_description(field_name: str) -> str:
    """Return the Annotated description of a PlotConfig field."""
    import typing

    hints = typing.get_type_hints(PlotConfig, include_extras=True)
    annotated = hints[field_name]
    return annotated.__metadata__[0]
