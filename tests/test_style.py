"""Tests for the tree-styling kwargs (line widths, node size, layer toggles)."""

from __future__ import annotations

import altair as alt
import pandas as pd
import pytest

import tree_annotated_plot


def _auspice() -> dict:
    return {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [
                {"name": "A", "node_attrs": {"div": 0.04}},
                {"name": "B", "node_attrs": {"div": 0.05}},
                {"name": "C", "node_attrs": {"div": 0.03}},
                {"name": "D", "node_attrs": {"div": 0.06}},
            ],
        },
    }


def _chart() -> alt.Chart:
    df = pd.DataFrame({"strain": ["A", "B", "C", "D"], "titer": [1.0, 2.0, 4.0, 8.0]})
    return (
        alt.Chart(df)
        .mark_circle()
        .encode(x="titer:Q", y=alt.Y("strain:N"))
        .properties(width=200, height=200)
    )


def _tree_layers(out: alt.HConcatChart) -> list[dict]:
    return out.to_dict()["hconcat"][0]["layer"]


def _layer_marks(layers: list[dict]) -> list[dict]:
    return [layer["mark"] for layer in layers if "mark" in layer]


# ---------- defaults ----------


def test_defaults_yield_three_layers() -> None:
    """With default styles (all three knobs > 0), scale_bar=False, and
    connect_leader_to_label=False, the tree has three layers: leaders,
    branches, tip-circles."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        connect_leader_to_label=False,
    )
    assert len(_tree_layers(out)) == 3


# ---------- non-default styles propagate to spec ----------


def test_tree_line_width_propagates() -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        tree_line_width=3.5,
    )
    marks = _layer_marks(_tree_layers(out))
    # The branches layer is the rule with no strokeDash and our line width.
    branch_marks = [
        m for m in marks if m.get("type") == "rule" and "strokeDash" not in m
    ]
    assert any(m.get("strokeWidth") == 3.5 for m in branch_marks)


def test_tree_node_size_propagates() -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        tree_node_size=80,
    )
    marks = _layer_marks(_tree_layers(out))
    circle_marks = [m for m in marks if m.get("type") == "circle"]
    assert any(m.get("size") == 80 for m in circle_marks)


def _circle_layer(out: alt.HConcatChart | alt.VConcatChart) -> dict:
    """Return the tip-circle layer dict from the tree panel of `out`.

    Works for both vertical (HConcatChart, tree on left) and horizontal
    (VConcatChart, tree on bottom by default for an x-encoded strain) layouts.
    """
    container = out.to_dict()
    tree_panel = (
        container["hconcat"][0] if "hconcat" in container else container["vconcat"][1]
    )
    circle_layers = [
        layer
        for layer in tree_panel["layer"]
        if layer.get("mark", {}).get("type") == "circle"
    ]
    assert (
        len(circle_layers) == 1
    ), f"expected exactly one tip-circle layer, got {len(circle_layers)}"
    return circle_layers[0]


def test_tip_circles_have_strain_tooltip_vertical() -> None:
    """Vertical layout (chart strain on y → tree on left): each tip circle
    should expose the strain name as a tooltip on hover."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
    )
    encoding = _circle_layer(out)["encoding"]
    assert "tooltip" in encoding, "tip-circle layer should encode a tooltip"
    tooltip = encoding["tooltip"]
    assert tooltip.get("field") == "name"
    assert tooltip.get("type") == "nominal"
    assert tooltip.get("title") == "strain"


def test_tip_circles_have_strain_tooltip_horizontal() -> None:
    """Horizontal layout (chart strain on x → tree on bottom): same
    tooltip should be present."""
    horizontal_chart = (
        alt.Chart(
            pd.DataFrame(
                {"strain": ["A", "B", "C", "D"], "titer": [1.0, 2.0, 4.0, 8.0]}
            )
        )
        .mark_circle()
        .encode(x=alt.X("strain:N"), y="titer:Q")
        .properties(width=200, height=200)
    )
    out = tree_annotated_plot.plot(
        _auspice(),
        horizontal_chart,
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
    )
    encoding = _circle_layer(out)["encoding"]
    assert "tooltip" in encoding, "tip-circle layer should encode a tooltip"
    tooltip = encoding["tooltip"]
    assert tooltip.get("field") == "name"
    assert tooltip.get("type") == "nominal"
    assert tooltip.get("title") == "strain"


def test_leader_line_width_propagates() -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        leader_line_width=2.0,
    )
    marks = _layer_marks(_tree_layers(out))
    leader_marks = [m for m in marks if m.get("type") == "rule" and "strokeDash" in m]
    assert any(m.get("strokeWidth") == 2.0 for m in leader_marks)


# ---------- layer-disable behavior ----------


def test_tree_node_size_zero_disables_tip_circles() -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        tree_node_size=0,
        connect_leader_to_label=False,
    )
    marks = _layer_marks(_tree_layers(out))
    assert not any(m.get("type") == "circle" for m in marks)
    # Two layers remaining: leaders + branches.
    assert len(_tree_layers(out)) == 2


def test_leader_line_width_zero_disables_leader_layer() -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        leader_line_width=0,
        connect_leader_to_label=False,
    )
    marks = _layer_marks(_tree_layers(out))
    leader_marks = [m for m in marks if m.get("type") == "rule" and "strokeDash" in m]
    assert not leader_marks
    # Two layers remaining: branches + tip-circles.
    assert len(_tree_layers(out)) == 2


def test_both_disabled_leaves_only_branches() -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        tree_node_size=0,
        leader_line_width=0,
        connect_leader_to_label=False,
    )
    assert len(_tree_layers(out)) == 1


# ---------- validation ----------


@pytest.mark.parametrize(
    "kwarg,bad",
    [
        ("tree_line_width", -0.5),
        ("tree_node_size", -1),
        ("leader_line_width", -1.0),
    ],
)
def test_negative_style_raises(kwarg: str, bad: float) -> None:
    with pytest.raises(ValueError, match=kwarg):
        tree_annotated_plot.plot(
            _auspice(),
            _chart(),
            chart_strain_field="strain",
            tree_strain_field="name",
            branch_length="div",
            **{kwarg: bad},
        )
