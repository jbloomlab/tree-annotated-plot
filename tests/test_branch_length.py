"""Tests for the `branch_length` parameter ("div" vs "num_date").

The Auspice JSON parser supports two branch-length sources:

  - `branch_length="div"` (default) reads `node_attrs.div`.
  - `branch_length="num_date"` reads `node_attrs.num_date.value`.

Each tip's resolved value lands on `TreeNode.x`; layout / segments /
pruning all consume `x` directly so they're branch-source-agnostic.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import pytest

import tree_annotated_plot
from tree_annotated_plot import _tree


def _auspice_with_both_branch_sources() -> dict:
    """Two tips, both div and num_date populated."""
    return {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {
                "div": 0.0,
                "num_date": {"value": 2020.0},
            },
            "children": [
                {
                    "name": "A",
                    "node_attrs": {
                        "div": 0.04,
                        "num_date": {"value": 2024.5},
                    },
                },
                {
                    "name": "B",
                    "node_attrs": {
                        "div": 0.06,
                        "num_date": {"value": 2025.5},
                    },
                },
            ],
        },
    }


def _chart() -> alt.Chart:
    return (
        alt.Chart(pd.DataFrame({"strain": ["A", "B"], "titer": [1.0, 2.0]}))
        .mark_circle()
        .encode(x="titer:Q", y=alt.Y("strain:N"))
        .properties(width=200, height=200)
    )


# ---------- _tree.load_auspice with both branch sources ----------


def test_load_auspice_div_default() -> None:
    root = _tree.load_auspice(
        _auspice_with_both_branch_sources(), tree_strain_field="name"
    )
    by_name = {t.name: t.x for t in _tree.tips(root)}
    assert by_name["A"] == pytest.approx(0.04)
    assert by_name["B"] == pytest.approx(0.06)


def test_load_auspice_num_date() -> None:
    root = _tree.load_auspice(
        _auspice_with_both_branch_sources(),
        tree_strain_field="name",
        branch_length="num_date",
    )
    by_name = {t.name: t.x for t in _tree.tips(root)}
    assert by_name["A"] == pytest.approx(2024.5)
    assert by_name["B"] == pytest.approx(2025.5)


def test_invalid_branch_length_value_raises() -> None:
    with pytest.raises(ValueError, match="branch_length='something'"):
        _tree.load_auspice(
            _auspice_with_both_branch_sources(),
            tree_strain_field="name",
            branch_length="something",
        )


def test_missing_num_date_raises_when_requested() -> None:
    """A tree built only with div but loaded with branch_length='num_date'
    should fail with an informative message naming num_date.value."""
    div_only = {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [
                {"name": "A", "node_attrs": {"div": 0.04}},
                {"name": "B", "node_attrs": {"div": 0.06}},
            ],
        },
    }
    with pytest.raises(ValueError, match="node_attrs.num_date.value"):
        _tree.load_auspice(div_only, tree_strain_field="name", branch_length="num_date")


def test_missing_div_still_raises_with_div() -> None:
    """The pre-existing div-missing error path should still fire."""
    bad = {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"num_date": {"value": 2020.0}},  # no div
            "children": [
                {
                    "name": "A",
                    "node_attrs": {"num_date": {"value": 2024.5}},
                },
            ],
        },
    }
    with pytest.raises(ValueError, match="node_attrs.div"):
        _tree.load_auspice(bad, tree_strain_field="name")


# ---------- end-to-end through tree_annotated_plot.plot ----------


def test_tap_plot_with_num_date_succeeds() -> None:
    out = tree_annotated_plot.plot(
        _auspice_with_both_branch_sources(),
        _chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="num_date",
    )
    assert isinstance(out, alt.HConcatChart)
