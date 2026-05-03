"""End-to-end smoke test of `tree_annotated_plot.plot` on a synthetic example."""

from __future__ import annotations

import altair as alt
import pandas as pd
import pytest

import tree_annotated_plot as tap


def _synthetic_auspice() -> dict:
    """A 4-tip Auspice JSON: ((A, B), (C, D)).

    Tree shape:

        ROOT
        ├── int1
        │   ├── A (div=0.04)
        │   └── B (div=0.05)
        └── int2
            ├── C (div=0.03)
            └── D (div=0.06)
    """
    return {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [
                {
                    "name": "int1",
                    "node_attrs": {"div": 0.01},
                    "children": [
                        {"name": "A", "node_attrs": {"div": 0.04}},
                        {"name": "B", "node_attrs": {"div": 0.05}},
                    ],
                },
                {
                    "name": "int2",
                    "node_attrs": {"div": 0.02},
                    "children": [
                        {"name": "C", "node_attrs": {"div": 0.03}},
                        {"name": "D", "node_attrs": {"div": 0.06}},
                    ],
                },
            ],
        },
    }


def _synthetic_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"strain": s, "serum": serum, "titer": v}
            for s, serum, v in [
                ("A", "s1", 100),
                ("B", "s1", 200),
                ("C", "s1", 400),
                ("D", "s1", 800),
                ("A", "s2", 150),
                ("B", "s2", 250),
                ("C", "s2", 350),
                ("D", "s2", 700),
            ]
        ]
    )


def _synthetic_chart(*, height: int | None = 200) -> alt.Chart:
    """A line plot of titer vs strain across two sera."""
    chart = (
        alt.Chart(_synthetic_df())
        .mark_line(point=True)
        .encode(
            x=alt.X("titer:Q", scale=alt.Scale(type="log")),
            y=alt.Y("strain:N"),
            color="serum:N",
        )
    )
    return (
        chart.properties(width=300, height=height)
        if height is not None
        else chart.properties(width=300)
    )


def test_plot_returns_hconcat_with_two_panels():
    out = tap.plot(
        _synthetic_auspice(),
        _synthetic_chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
    )
    assert isinstance(out, alt.HConcatChart)
    assert len(out.hconcat) == 2


def test_plot_overrides_y_sort_to_tree_tip_order():
    out = tap.plot(
        _synthetic_auspice(),
        _synthetic_chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
    )
    user_panel_spec = out.hconcat[1].to_dict()
    assert user_panel_spec["encoding"]["y"]["sort"] == ["A", "B", "C", "D"]


def test_plot_strain_mismatch_raises():
    bad = _synthetic_chart()
    bad.data = bad.data.replace({"strain": {"D": "X"}})
    with pytest.raises(ValueError, match="not present in the"):
        tap.plot(
            _synthetic_auspice(),
            bad,
            chart_strain_field="strain",
            tree_strain_field="name",
            branch_length="div",
        )


def test_plot_requires_explicit_height():
    chart = _synthetic_chart(height=None)
    with pytest.raises(ValueError, match="height"):
        tap.plot(
            _synthetic_auspice(),
            chart,
            chart_strain_field="strain",
            tree_strain_field="name",
            branch_length="div",
        )


def test_plot_renders_to_html(tmp_path):
    """End-to-end: result can be saved to standalone HTML."""
    out = tap.plot(
        _synthetic_auspice(),
        _synthetic_chart(),
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
    )
    target = tmp_path / "out.html"
    out.save(str(target))
    html = target.read_text()
    # presence of vega-embed and the strain values is a sanity check
    assert "vegaEmbed" in html
    for s in ["A", "B", "C", "D"]:
        assert s in html
