"""Connection order on `mark_line` / `mark_trail` / `mark_area` follows tip order.

Regression: when the user chart had `mark_line` with strain on a discrete
axis, lines connected points in tip order most of the time — but adding an
explicit categorical color-scale `domain` shifted Vega-Lite's default
connection-order heuristic away from the strain-axis `sort`, causing lines
to crisscross. The package now sets the `order` channel to a per-row
tip-rank field on these marks (unless the user has set their own `order`),
pinning rule 1 of the Vega-Lite fallback chain.

The tip-rank is computed via a `calculate` transform that runs `indexof`
against the tip-names list — Vega-Lite's `order` channel `sort` only
accepts ascending/descending, so a derived quantitative field is the
direct way to express custom ordering.
"""

from __future__ import annotations

from typing import Any

import altair as alt
import pandas as pd
import pytest

import tree_annotated_plot
from tree_annotated_plot._plot import _TIP_ORDER_RANK_FIELD


def _synthetic_auspice() -> dict:
    """4-tip Auspice tree; tip layout order is [A, B, C, D]."""
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


TIP_ORDER = ["A", "B", "C", "D"]


def _df() -> pd.DataFrame:
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


def _plot_user_panel(chart: alt.TopLevelMixin) -> dict:
    """Run plot() with default settings and return the user-panel spec dict."""
    out = tree_annotated_plot.plot(
        _synthetic_auspice(),
        chart,
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
    )
    # Default tree_location for y-axis strain is "left" — user panel is hconcat[1].
    return out.to_dict()["hconcat"][1]


def _find_order_encodings(spec: Any) -> list[dict]:
    """Walk a spec dict and return every `encoding.order` dict found."""
    found: list[dict] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            enc = node.get("encoding")
            if isinstance(enc, dict) and "order" in enc:
                found.append(enc["order"])
            for k, v in node.items():
                if k != "encoding":
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return found


def _find_tip_rank_transforms(spec: Any) -> list[dict]:
    """Walk a spec dict and return every calculate transform that computes
    the package's tip-rank derived field."""
    found: list[dict] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            transforms = node.get("transform")
            if isinstance(transforms, list):
                for t in transforms:
                    if isinstance(t, dict) and t.get("as") == _TIP_ORDER_RANK_FIELD:
                        found.append(t)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return found


def _assert_tip_rank_wired(spec: dict) -> None:
    """Spec contains both an order-channel pointing at the tip-rank field
    and a calculate transform that derives that field from the tip names."""
    orders = _find_order_encodings(spec)
    assert len(orders) == 1, f"expected one order encoding, got {orders}"
    assert orders[0]["field"] == _TIP_ORDER_RANK_FIELD
    assert orders[0]["type"] == "quantitative"
    transforms = _find_tip_rank_transforms(spec)
    assert len(transforms) == 1, f"expected one tip-rank transform, got {transforms}"
    expr = transforms[0]["calculate"]
    assert "indexof" in expr
    # The expression embeds the tip names list verbatim.
    for tip in TIP_ORDER:
        assert f'"{tip}"' in expr, f"tip {tip!r} not in calculate expression {expr!r}"


def test_mark_line_with_color_domain_gets_order_in_tip_order():
    """The original bug: explicit color-scale `domain` no longer crisscrosses lines."""
    chart = (
        alt.Chart(_df())
        .mark_line(point=True)
        .encode(
            x=alt.X("titer:Q", scale=alt.Scale(type="log")),
            y=alt.Y("strain:N"),
            color=alt.Color(
                "serum:N",
                scale=alt.Scale(domain=["s1", "s2"], range=["red", "blue"]),
            ),
        )
        .properties(width=300, height=200)
    )
    _assert_tip_rank_wired(_plot_user_panel(chart))


def test_user_supplied_order_is_preserved():
    """User-supplied `order` always wins; the package never overwrites it."""
    chart = (
        alt.Chart(_df())
        .mark_line()
        .encode(
            x=alt.X("titer:Q"),
            y=alt.Y("strain:N"),
            color="serum:N",
            order=alt.Order("titer:Q", sort="ascending"),
        )
        .properties(width=300, height=200)
    )
    spec = _plot_user_panel(chart)
    orders = _find_order_encodings(spec)
    assert len(orders) == 1
    assert orders[0]["field"] == "titer"
    # The package did not attach its tip-rank transform either.
    assert _find_tip_rank_transforms(spec) == []


@pytest.mark.parametrize("mark_method", ["mark_line", "mark_area", "mark_trail"])
def test_connection_order_marks_get_order_in_tip_order(mark_method: str):
    """All three connection-order marks (line / area / trail) get `order` injected."""
    base = alt.Chart(_df()).encode(
        x=alt.X("titer:Q"),
        y=alt.Y("strain:N"),
        color="serum:N",
    )
    chart = getattr(base, mark_method)().properties(width=300, height=200)
    _assert_tip_rank_wired(_plot_user_panel(chart))


def test_layered_chart_only_line_layer_gets_order():
    """Mixed-mark layers: line layer gets `order`, circle layer is untouched."""
    base = alt.Chart(_df()).encode(
        x=alt.X("titer:Q"),
        y=alt.Y("strain:N"),
        color="serum:N",
    )
    layered = (base.mark_line() + base.mark_circle()).properties(width=300, height=200)
    _assert_tip_rank_wired(_plot_user_panel(layered))


def test_no_connection_order_marks_means_no_order_injected():
    """A chart with only point/circle/etc. marks is a no-op for the walker."""
    chart = (
        alt.Chart(_df())
        .mark_circle()
        .encode(
            x=alt.X("titer:Q"),
            y=alt.Y("strain:N"),
            color="serum:N",
        )
        .properties(width=300, height=200)
    )
    spec = _plot_user_panel(chart)
    assert _find_order_encodings(spec) == []
    assert _find_tip_rank_transforms(spec) == []


def test_faceted_chart_gets_order_injection():
    """The walker descends into the inner spec of a faceted chart."""
    df_facet = pd.DataFrame(
        [
            {"strain": s, "serum": serum, "panel": p, "titer": v}
            for s, serum, p, v in [
                ("A", "s1", "P1", 100),
                ("B", "s1", "P1", 200),
                ("C", "s1", "P1", 400),
                ("D", "s1", "P1", 800),
                ("A", "s1", "P2", 150),
                ("B", "s1", "P2", 250),
                ("C", "s1", "P2", 350),
                ("D", "s1", "P2", 700),
            ]
        ]
    )
    base = (
        alt.Chart(df_facet)
        .mark_line()
        .encode(
            x=alt.X("titer:Q"),
            y=alt.Y("strain:N"),
            color="serum:N",
        )
        .properties(width=300, height=200)
    )
    faceted = base.facet(facet="panel:N", columns=2)
    _assert_tip_rank_wired(_plot_user_panel(faceted))
