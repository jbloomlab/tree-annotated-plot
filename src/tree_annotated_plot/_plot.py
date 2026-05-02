"""Build the tree-annotated chart by introspecting and extending a user's Altair chart."""

from __future__ import annotations

import copy
from pathlib import Path

import altair as alt
import pandas as pd

from . import _tree


def plot(
    tree: str | Path | dict | _tree.TreeNode,
    chart: alt.Chart,
    *,
    tree_width: int = 100,
) -> alt.HConcatChart:
    """Return an Altair chart with a phylogenetic tree drawn alongside `chart`.

    Parameters
    ----------
    tree
        Auspice JSON path, dict, or a pre-parsed :class:`TreeNode`.
    chart
        An :class:`altair.Chart` whose y-encoding's `field` column lists the
        same set of strain names as the tree's tips. The y-encoding's sort
        order is overridden to match the tree's tip order.
    tree_width
        Width in pixels of the tree panel.

    Returns
    -------
    altair.HConcatChart
        Tree on the left, user's chart on the right.
    """
    root = _ensure_tree(tree)
    tip_list = _tree.layout(root)
    tip_names = [t.name for t in tip_list]

    y_field = _y_field(chart)
    chart_strains = _chart_y_values(chart, y_field)
    _check_strain_match(tip_names, chart_strains)

    height = _chart_height(chart)
    user_chart = _set_y_sort(chart, tip_names)
    tree_chart = _build_tree_chart(
        root, n_tips=len(tip_names), width=tree_width, height=height
    )

    return (
        alt.hconcat(tree_chart, user_chart, spacing=0)
        .resolve_scale(y="independent")
        .configure_view(stroke=None)
    )


def _ensure_tree(tree):
    if isinstance(tree, _tree.TreeNode):
        return tree
    return _tree.load_auspice(tree)


def _y_field(chart: alt.Chart) -> str:
    spec = chart.to_dict()
    enc = spec.get("encoding", {})
    if "y" not in enc:
        raise ValueError("chart must have a 'y' encoding")
    field = enc["y"].get("field")
    if not field:
        raise ValueError("chart's y-encoding must have a 'field'")
    return field


def _chart_y_values(chart: alt.Chart, field: str) -> list:
    data = chart.data
    if not isinstance(data, pd.DataFrame):
        raise ValueError(
            f"chart's data must be a pandas DataFrame (got {type(data).__name__})"
        )
    if field not in data.columns:
        raise ValueError(f"chart's y-field {field!r} not found in chart data columns")
    return list(data[field].unique())


def _check_strain_match(tip_names, chart_strains) -> None:
    tip_set = set(tip_names)
    chart_set = set(chart_strains)
    missing_in_chart = tip_set - chart_set
    missing_in_tree = chart_set - tip_set
    if missing_in_chart or missing_in_tree:
        raise ValueError(
            "strain set mismatch between tree tips and chart data:\n"
            f"  tips not in chart: {sorted(missing_in_chart)}\n"
            f"  chart strains not in tree: {sorted(missing_in_tree)}"
        )


def _chart_height(chart: alt.Chart) -> int:
    h = chart.to_dict().get("height")
    if isinstance(h, (int, float)):
        return int(h)
    raise ValueError(
        "chart must have an explicit `height` set (e.g. chart.properties(height=400)) "
        "so the tree panel can be sized to match"
    )


def _set_y_sort(chart: alt.Chart, sort_order: list[str]) -> alt.Chart:
    """Return a deep copy of `chart` with its y-encoding sort set to `sort_order`."""
    new = copy.deepcopy(chart)
    y = new.encoding.y
    if isinstance(y, str) or y is alt.Undefined:
        # shouldn't get here because _y_field already validated
        raise ValueError("chart's y-encoding could not be modified")
    y.sort = list(sort_order)
    return new


def _build_tree_chart(
    root: _tree.TreeNode, *, n_tips: int, width: int, height: int
) -> alt.Chart:
    seg_df = _tree.segments(root)
    tips_df = pd.DataFrame(
        [{"name": t.name, "x": t.x, "y": t.y} for t in _tree.tips(root)]
    )
    x_max = tips_df["x"].max()
    leader_df = tips_df[tips_df["x"] < x_max].assign(x2=x_max)

    x_min_seg = float(seg_df[["x", "x2"]].min().min())
    x_max_seg = float(seg_df[["x", "x2"]].max().max())
    x_scale = alt.Scale(domain=[x_min_seg, x_max_seg], nice=False, zero=False)
    y_scale = alt.Scale(domain=[n_tips - 0.5, -0.5], nice=False, zero=False)
    y_enc = alt.Y("y:Q", axis=None, scale=y_scale)
    x_enc = alt.X("x:Q", axis=None, scale=x_scale)

    leaders = (
        alt.Chart(leader_df)
        .mark_rule(stroke="#888", strokeWidth=1.0, strokeDash=[2, 2])
        .encode(x=x_enc, x2="x2:Q", y=y_enc)
    )
    branches = (
        alt.Chart(seg_df)
        .mark_rule(strokeWidth=1.5)
        .encode(x=x_enc, x2="x2:Q", y=y_enc, y2="y2:Q")
    )
    tip_marks = (
        alt.Chart(tips_df).mark_circle(size=28, color="black").encode(x=x_enc, y=y_enc)
    )

    return (leaders + branches + tip_marks).properties(width=width, height=height)
