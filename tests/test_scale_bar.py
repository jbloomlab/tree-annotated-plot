"""Tests for the `scale_bar` and `branch_length_units` parameters."""

from __future__ import annotations

import altair as alt
import pandas as pd
import pytest

import tree_annotated_plot
from tree_annotated_plot._plot import (
    _format_scale_bar_label,
    _nice_scale_bar_length,
    _SCALE_BAR_EXTRA_PIXELS,
)


def _auspice() -> dict:
    """Tree spanning div ∈ [0, 0.04]."""
    return {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [
                {"name": "A", "node_attrs": {"div": 0.02}},
                {"name": "B", "node_attrs": {"div": 0.03}},
                {"name": "C", "node_attrs": {"div": 0.04}},
                {"name": "D", "node_attrs": {"div": 0.035}},
            ],
        },
    }


def _chart(*, height: int = 200) -> alt.Chart:
    return (
        alt.Chart(
            pd.DataFrame(
                {"strain": ["A", "B", "C", "D"], "titer": [1.0, 2.0, 4.0, 8.0]}
            )
        )
        .mark_circle()
        .encode(x="titer:Q", y=alt.Y("strain:N"))
        .properties(width=200, height=height)
    )


# ---------- _nice_scale_bar_length ----------


@pytest.mark.parametrize(
    "branch_range,expected",
    [
        (0.16, 0.02),  # target=0.04 → 2*10^-2
        (0.28, 0.05),  # target=0.07 → 5*10^-2
        (4.0, 1.0),  # target=1.0 → 1*10^0
        (14.0, 2.0),  # target=3.5 → 2*10^0
        (40.0, 10.0),  # target=10 → 1*10^1 (10 is the largest nice ≤ 10)
        (200.0, 50.0),  # target=50 → 5*10^1
    ],
)
def test_nice_scale_bar_length(branch_range: float, expected: float) -> None:
    assert _nice_scale_bar_length(branch_range) == pytest.approx(expected)


def test_nice_scale_bar_length_handles_zero_and_negative() -> None:
    assert _nice_scale_bar_length(0.0) == 0.0
    assert _nice_scale_bar_length(-1.0) == 0.0


# ---------- _format_scale_bar_label ----------


def test_label_div_with_units() -> None:
    assert (
        _format_scale_bar_label(0.01, "div", "substitutions/site")
        == "0.01 substitutions/site"
    )


def test_label_div_without_units() -> None:
    assert _format_scale_bar_label(0.01, "div", None) == "0.01"


def test_label_num_date_years() -> None:
    """For num_date with length >= 1, units are always 'years' regardless
    of the user's branch_length_units argument."""
    assert _format_scale_bar_label(5.0, "num_date", "ignored") == "5 years"


def test_label_num_date_months() -> None:
    """For num_date with length < 1, units are 'months'."""
    assert _format_scale_bar_label(0.5, "num_date", None) == "6 months"
    assert _format_scale_bar_label(0.25, "num_date", None) == "3 months"


# ---------- end-to-end via tree_annotated_plot.plot ----------


def test_scale_bar_off_default_no_extra_pixels() -> None:
    """Default scale_bar=False keeps the tree's tip-axis at strain_dim
    (no extra pixel margin)."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
    )
    tree_height = out.to_dict()["hconcat"][0]["height"]
    assert tree_height == 200  # matches chart height; no scale-bar margin


def test_scale_bar_on_extends_tree_panel() -> None:
    """scale_bar=True adds _SCALE_BAR_EXTRA_PIXELS to the tree panel
    height. The chart panel is unchanged so tip alignment is preserved."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        scale_bar=True,
    )
    tree_height = out.to_dict()["hconcat"][0]["height"]
    assert tree_height == 200 + _SCALE_BAR_EXTRA_PIXELS


def test_scale_bar_layer_appears_in_tree_panel() -> None:
    """With scale_bar=True the tree's LayerChart should have one extra
    layer (scale bar = 1 layer with an inner bar+text composition)."""
    out_off = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
    )
    out_on = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        scale_bar=True,
    )
    n_off = len(out_off.to_dict()["hconcat"][0]["layer"])
    n_on = len(out_on.to_dict()["hconcat"][0]["layer"])
    assert n_on > n_off


def test_scale_bar_is_centered_on_branch_range() -> None:
    """The bar's branch-axis midpoint should sit at (branch_min + branch_max)/2,
    not at branch_min (which would push a wide text label off the panel)."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        scale_bar=True,
    )
    # Find the bar layer's data — it's the only layer with "x2" set to a
    # branch value (the rule's endpoint).
    found_bar = None
    for ds_name, ds_rows in out.to_dict().get("datasets", {}).items():
        if isinstance(ds_rows, list) and len(ds_rows) == 1:
            row = ds_rows[0]
            if isinstance(row, dict) and {"x", "x2"}.issubset(row):
                found_bar = row
                break
    assert found_bar is not None, "couldn't find scale-bar data row"
    # Tree branch range on the fixture is [0, 0.04] → midpoint 0.02.
    midpoint = (found_bar["x"] + found_bar["x2"]) / 2
    assert midpoint == pytest.approx((0.0 + 0.04) / 2, abs=1e-9)


def test_scale_bar_text_rotates_in_horizontal_layout() -> None:
    """For horizontal layout (strain on x), the bar is vertical, so the
    text should be rotated to read parallel to it."""
    df = pd.DataFrame({"strain": ["A", "B", "C", "D"], "titer": [1.0, 2.0, 4.0, 8.0]})
    horiz_chart = (
        alt.Chart(df)
        .mark_circle()
        .encode(x=alt.X("strain:N"), y="titer:Q")
        .properties(width=200, height=200)
    )
    out = tree_annotated_plot.plot(
        _auspice(),
        horiz_chart,
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        scale_bar=True,
    )
    # Walk for any text-mark layer and check its angle.
    found_angles = []

    def walk(node):
        if isinstance(node, dict):
            mark = node.get("mark")
            if isinstance(mark, dict) and mark.get("type") == "text":
                if "angle" in mark:
                    found_angles.append(mark["angle"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out.to_dict())
    assert (
        270 in found_angles
    ), f"expected at least one text mark with angle=270, got {found_angles}"


def test_scale_bar_text_not_rotated_in_vertical_layout() -> None:
    """For vertical layout the bar is horizontal so the text should be
    horizontal too (no angle attribute, or angle=0)."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        scale_bar=True,
    )
    found_angles = []

    def walk(node):
        if isinstance(node, dict):
            mark = node.get("mark")
            if isinstance(mark, dict) and mark.get("type") == "text":
                found_angles.append(mark.get("angle", 0))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out.to_dict())
    assert all(
        a in (0, None) for a in found_angles
    ), f"expected unrotated text in vertical layout, got angles={found_angles}"


def test_scale_bar_label_uses_branch_length_units_for_div() -> None:
    """The bar's text label is a one-row DataFrame altair hoists to a
    top-level `datasets` block. Grep the serialized spec for the unit
    string."""
    import json

    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        scale_bar=True,
        branch_length_units="substitutions/site",
    )
    serialized = json.dumps(out.to_dict())
    # The bar length on this fixture is 0.01 (target=0.25*0.04=0.01 → 1e-2).
    assert "0.01 substitutions/site" in serialized
