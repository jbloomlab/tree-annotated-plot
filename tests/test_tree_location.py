"""Tests for the `tree_location` parameter.

Defaults:
  - chart strain on y → "left" (tree on the left of an hconcat)
  - chart strain on x → "bottom" (tree below the chart in a vconcat)

These match where Vega-Lite renders strain-axis labels by default, so the
tree's tip end always lies adjacent to the labels.

Validation:
  - y-encoded strain + "top"/"bottom" → ValueError
  - x-encoded strain + "left"/"right" → ValueError
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import pytest

import tree_annotated_plot


def _auspice_4_tip() -> dict:
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


def _vertical_chart() -> alt.Chart:
    df = pd.DataFrame({"strain": ["A", "B", "C", "D"], "titer": [1.0, 2.0, 4.0, 8.0]})
    return (
        alt.Chart(df)
        .mark_circle()
        .encode(x="titer:Q", y=alt.Y("strain:N"))
        .properties(width=200, height=200)
    )


def _horizontal_chart() -> alt.Chart:
    df = pd.DataFrame({"strain": ["A", "B", "C", "D"], "titer": [1.0, 2.0, 4.0, 8.0]})
    return (
        alt.Chart(df)
        .mark_circle()
        .encode(x=alt.X("strain:N"), y="titer:Q")
        .properties(width=200, height=200)
    )


def _kw():
    return dict(
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
    )


# ---------- defaults ----------


def test_default_for_y_strain_is_left() -> None:
    """tree_location=None on a y-encoded chart → tree on the left → tree
    is the first panel of the HConcatChart."""
    out = tree_annotated_plot.plot(_auspice_4_tip(), _vertical_chart(), **_kw())
    assert isinstance(out, alt.HConcatChart)
    d = out.to_dict()
    # Tree is the panel that has `width` set explicitly to our default
    # tree_size (100); chart panel's width comes from .properties(200).
    assert d["hconcat"][0]["width"] == 100
    assert d["hconcat"][1]["width"] == 200


def test_default_for_x_strain_is_bottom() -> None:
    """tree_location=None on an x-encoded chart → tree below → tree is
    vconcat[1] (chart at vconcat[0])."""
    out = tree_annotated_plot.plot(_auspice_4_tip(), _horizontal_chart(), **_kw())
    assert isinstance(out, alt.VConcatChart)
    d = out.to_dict()
    # Tree panel's height = our default tree_size (100); chart panel's
    # height = .properties(height=200).
    assert d["vconcat"][0]["height"] == 200  # chart on top
    assert d["vconcat"][1]["height"] == 100  # tree on bottom


# ---------- explicit non-default ----------


def test_explicit_right_puts_tree_on_right_of_hconcat() -> None:
    out = tree_annotated_plot.plot(
        _auspice_4_tip(), _vertical_chart(), tree_location="right", **_kw()
    )
    assert isinstance(out, alt.HConcatChart)
    d = out.to_dict()
    assert d["hconcat"][0]["width"] == 200  # chart on left
    assert d["hconcat"][1]["width"] == 100  # tree on right


def test_explicit_top_puts_tree_above_vconcat() -> None:
    out = tree_annotated_plot.plot(
        _auspice_4_tip(), _horizontal_chart(), tree_location="top", **_kw()
    )
    assert isinstance(out, alt.VConcatChart)
    d = out.to_dict()
    assert d["vconcat"][0]["height"] == 100  # tree on top
    assert d["vconcat"][1]["height"] == 200  # chart on bottom


def test_right_flips_tree_branch_direction() -> None:
    """tree_location=right inverts the branch_scale domain so tips face
    left (toward the chart that's on the left). The encoded x scale's
    domain order is the visible signal."""
    out = tree_annotated_plot.plot(
        _auspice_4_tip(), _vertical_chart(), tree_location="right", **_kw()
    )
    tree_panel = out.to_dict()["hconcat"][1]
    # Find the branch x-scale on the tree panel. It lives on a layer
    # encoding's x.scale.domain.
    layer = tree_panel["layer"][1]  # branches layer
    x_dom = layer["encoding"]["x"]["scale"]["domain"]
    # branch_min < branch_max in this fixture; for "right" the domain is
    # inverted (branch_max first).
    assert x_dom[0] > x_dom[1]


def test_top_keeps_branch_growing_downward() -> None:
    """tree_location=top: root at top, tips at bottom. On Vega-Lite y the
    domain order [max, min] places domain[0] at bottom and domain[1] at
    top, so root (small div) ends up at the top."""
    out = tree_annotated_plot.plot(
        _auspice_4_tip(), _horizontal_chart(), tree_location="top", **_kw()
    )
    tree_panel = out.to_dict()["vconcat"][0]
    layer = tree_panel["layer"][1]
    y_dom = layer["encoding"]["y"]["scale"]["domain"]
    # branch_max first → tips at bottom, root at top.
    assert y_dom[0] > y_dom[1]


# ---------- validation errors ----------


def test_top_with_y_encoded_strain_raises() -> None:
    with pytest.raises(ValueError, match="incompatible with a y-encoded"):
        tree_annotated_plot.plot(
            _auspice_4_tip(), _vertical_chart(), tree_location="top", **_kw()
        )


def test_bottom_with_y_encoded_strain_raises() -> None:
    with pytest.raises(ValueError, match="incompatible with a y-encoded"):
        tree_annotated_plot.plot(
            _auspice_4_tip(), _vertical_chart(), tree_location="bottom", **_kw()
        )


def test_left_with_x_encoded_strain_raises() -> None:
    with pytest.raises(ValueError, match="incompatible with an x-encoded"):
        tree_annotated_plot.plot(
            _auspice_4_tip(), _horizontal_chart(), tree_location="left", **_kw()
        )


def test_right_with_x_encoded_strain_raises() -> None:
    with pytest.raises(ValueError, match="incompatible with an x-encoded"):
        tree_annotated_plot.plot(
            _auspice_4_tip(), _horizontal_chart(), tree_location="right", **_kw()
        )
