"""Tests for the tree-styling kwargs (line widths, node size, layer toggles)."""

from __future__ import annotations

import altair as alt
import pandas as pd
import pytest

import tree_annotated_plot as tap


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
    """With default styles (all three knobs > 0) and scale_bar=False, the
    tree has three layers: leaders, branches, tip-circles."""
    out = tap.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
    )
    assert len(_tree_layers(out)) == 3


# ---------- non-default styles propagate to spec ----------


def test_tree_line_width_propagates() -> None:
    out = tap.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        tree_line_width=3.5,
    )
    marks = _layer_marks(_tree_layers(out))
    # The branches layer is the rule with no strokeDash and our line width.
    branch_marks = [
        m for m in marks if m.get("type") == "rule" and "strokeDash" not in m
    ]
    assert any(m.get("strokeWidth") == 3.5 for m in branch_marks)


def test_tree_node_size_propagates() -> None:
    out = tap.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        tree_node_size=80,
    )
    marks = _layer_marks(_tree_layers(out))
    circle_marks = [m for m in marks if m.get("type") == "circle"]
    assert any(m.get("size") == 80 for m in circle_marks)


def test_leader_line_width_propagates() -> None:
    out = tap.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        leader_line_width=2.0,
    )
    marks = _layer_marks(_tree_layers(out))
    leader_marks = [m for m in marks if m.get("type") == "rule" and "strokeDash" in m]
    assert any(m.get("strokeWidth") == 2.0 for m in leader_marks)


# ---------- layer-disable behavior ----------


def test_tree_node_size_zero_disables_tip_circles() -> None:
    out = tap.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        tree_node_size=0,
    )
    marks = _layer_marks(_tree_layers(out))
    assert not any(m.get("type") == "circle" for m in marks)
    # Two layers remaining: leaders + branches.
    assert len(_tree_layers(out)) == 2


def test_leader_line_width_zero_disables_leader_layer() -> None:
    out = tap.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        leader_line_width=0,
    )
    marks = _layer_marks(_tree_layers(out))
    leader_marks = [m for m in marks if m.get("type") == "rule" and "strokeDash" in m]
    assert not leader_marks
    # Two layers remaining: branches + tip-circles.
    assert len(_tree_layers(out)) == 2


def test_both_disabled_leaves_only_branches() -> None:
    out = tap.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        tree_node_size=0,
        leader_line_width=0,
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
        tap.plot(
            _auspice(),
            _chart(),
            chart_strain_field="strain",
            tree_strain_field="name",
            **{kwarg: bad},
        )
