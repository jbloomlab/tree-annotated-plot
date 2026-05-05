"""`PlotConfig`: the single source of truth for plot-parameter descriptions.

Both `tree_annotated_plot.plot` and the CLI consume `PlotConfig`. Each
field's `Annotated[T, str]` metadata is the canonical description: it
is pulled into the function's docstring at import time (via
`_render_numpy_params`, called from `_plot.py`), and into each click
option's `help` text by `tree_annotated_plot.cli`. Adding or editing a
parameter description therefore takes one edit, not two.

For the rare case where the Python docstring needs more prose than the
CLI `--help` (e.g. cross-references to Python-only concepts), add an
entry to `PARAM_DOC_EXTRAS` keyed by the field name; the extra prose
is appended to that field's description in the docstring only.
"""

from __future__ import annotations

import dataclasses
import textwrap
import typing
from typing import Annotated, Literal

TreeLocation = Literal["left", "right", "top", "bottom"]


@dataclasses.dataclass(frozen=True, kw_only=True)
class PlotConfig:
    """Configuration for `tree_annotated_plot.plot`.

    Each field's type annotation is `Annotated[T, "<description>"]`. The
    description is the canonical text that appears in the function's
    docstring, the click `--help` text, and the rendered Python API page.
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
        "Required. Which Auspice node attribute supplies branch lengths. "
        '"div" means divergence branch lengths; "num_date" means calendar '
        "dates.",
    ]

    tree_size: Annotated[
        int,
        "Size in pixels of tree depth. For vertical layout (chart strain on "
        "`y`) this is the tree panel's *width*; for horizontal layout (chart "
        "strain on `x`) this is the tree panel's *height*.",
    ] = 100

    tree_location: Annotated[
        TreeLocation | None,
        "Which side of the chart to draw the tree on. Defaults to the side "
        'with the strain-axis labels ("left" for y-encoded strain, "bottom" '
        'for x-encoded). Other valid values: "right" (y-encoded), "top" '
        "(x-encoded).",
    ] = None

    tree_line_width: Annotated[
        float,
        "Stroke width (px) for the tree's branch lines. Default 1.5.",
    ] = 1.5

    tree_node_size: Annotated[
        float,
        "Area (px²) of the small filled circles drawn at each tip. "
        "Default 28. Setting tree_node_size=0 disables the tip-circle "
        "layer entirely.",
    ] = 28

    leader_line_width: Annotated[
        float,
        "Stroke width (px) for the dashed leader lines that connect each "
        "tip's branch endpoint to the strain row when the branch doesn't "
        "extend all the way to branch_max. Default 1.0. Setting "
        "leader_line_width=0 disables the leader-line layer entirely.",
    ] = 1.0

    scale_bar: Annotated[
        bool,
        "Off by default. When on, adds a small bar in the tree panel "
        "showing the branch-length scale. Tip-row alignment with the "
        "chart is preserved.",
    ] = False

    branch_length_units: Annotated[
        str | None,
        'Used only when scale_bar is on and branch_length="div": the unit '
        "string pasted after the bar's numeric length (e.g. "
        '"substitutions/site"). None renders unitless. For '
        'branch_length="num_date" the label is always in years/months '
        "and this argument is ignored.",
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
        "When on (default), known-stale specs raise: Vega-Lite 5 or "
        "earlier, and Auspice JSON whose `version` is not v2. When off, "
        "those become warnings and parsing proceeds.",
    ] = True

    connect_leader_to_label: Annotated[
        bool,
        "Off (default): the chart's strain-axis labels are kept as the "
        "user wrote them and dashed leader lines stop at the tree "
        "panel's chart-facing edge. On: leaders extend all the way to "
        "the labels — which requires moving the labels off the chart's "
        "strain axis and into the tree panel, so the chart's "
        "strain-axis labels, ticks, axis line, and title are SUPPRESSED "
        "(any user-supplied `axis=...` is overridden) and replacement "
        "labels are rendered alongside the tree. Label widths are "
        "estimated; for crowded charts tune `strain_label_font_size` or "
        "`shift_tree_loc`.",
    ] = False

    strain_label_font_size: Annotated[
        float,
        "Font size (px) for the strain text labels rendered in the tree "
        "panel when `connect_leader_to_label` is on.",
    ] = 10.0

    strain_label_font_weight: Annotated[
        Literal["normal", "bold"],
        "Font weight for the strain text labels rendered in the tree panel "
        "when `connect_leader_to_label` is on.",
    ] = "normal"

    shift_tree_loc: Annotated[
        int,
        "Pixels by which to shift the tree toward (positive) or away from "
        "(negative) the chart. Default 0. Has no effect when "
        "connect_leader_to_label is off.",
    ] = 0


# Sidecar for Python-docstring-only prose, keyed by PlotConfig field name.
# Empty by default — add an entry when a field's docstring entry needs more
# than the CLI `--help` text covers. The extras are appended to the field's
# description in `tree_annotated_plot.plot.__doc__`, never in CLI --help.
PARAM_DOC_EXTRAS: dict[str, str] = {}


# Descriptions for the three data-input parameters. These can't live on
# PlotConfig because their *types* differ between surfaces (Python accepts
# live objects; the CLI accepts only file paths), but their descriptions
# can — and should — be single-sourced. The CLI reads these for its --help
# text; the Python docstring header in `_plot.py` interpolates them too.
TREE_DESCRIPTION = (
    "Phylogenetic tree in Auspice JSON v2 format. The CLI accepts a file "
    "path; the Python API additionally accepts a parsed dict or a "
    "pre-built `tree_annotated_plot.TreeNode`."
)

CHART_DESCRIPTION = (
    "Vega-Lite chart whose strain axis the tree will annotate. The CLI "
    "accepts a saved spec on disk — either *.json (canonical) or *.html "
    "(extracted from altair's default save template). The Python API "
    "additionally accepts a live `altair.Chart`-or-subclass object or a "
    "parsed spec dict. Must encode `chart_strain_field` on `x` or `y`."
)

OUTPUT_DESCRIPTION = (
    "Where to save the combined plot. Format inferred from extension: "
    ".html, .json, .png, .svg, .pdf."
)


def field_description(field_name: str) -> str:
    """Return the Annotated description of a PlotConfig field."""
    hints = typing.get_type_hints(PlotConfig, include_extras=True)
    annotated = hints[field_name]
    return annotated.__metadata__[0]


def _render_data_param(name: str, description: str, width: int = 75) -> str:
    """Render one NumPy-style parameter block for a non-PlotConfig data input.

    Used by `_plot.py` to fold the `tree` and `chart` descriptions
    (`TREE_DESCRIPTION`, `CHART_DESCRIPTION`) into `plot.__doc__` in the same
    NumPy shape as the PlotConfig-derived parameters rendered by
    `_render_numpy_params`.
    """
    body = textwrap.fill(
        description,
        width=width,
        initial_indent="    ",
        subsequent_indent="    ",
        break_on_hyphens=False,
    )
    return f"{name}\n{body}"


def _render_numpy_params(
    extras: dict[str, str] | None = None,
    width: int = 75,
) -> str:
    """Render PlotConfig fields as the body of a NumPy `Parameters` block.

    Returns the per-field entries only — callers prepend the
    `Parameters\\n----------` section header. Each entry is the field
    name on its own line, followed by the field's `Annotated` description
    (and any matching `extras` prose) indented by four spaces and word-wrapped
    to `width`.
    """
    extras = extras or {}
    hints = typing.get_type_hints(PlotConfig, include_extras=True)
    chunks: list[str] = []
    for field in dataclasses.fields(PlotConfig):
        name = field.name
        description = hints[name].__metadata__[0]
        chunks.append(name)
        chunks.append(
            textwrap.fill(
                description,
                width=width,
                initial_indent="    ",
                subsequent_indent="    ",
                break_on_hyphens=False,
            )
        )
        if name in extras:
            chunks.append("")
            chunks.append(
                textwrap.fill(
                    extras[name],
                    width=width,
                    initial_indent="    ",
                    subsequent_indent="    ",
                    break_on_hyphens=False,
                )
            )
    return "\n".join(chunks)
