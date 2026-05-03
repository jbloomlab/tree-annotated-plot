"""Real-data invariants for the Kikawa H3N2 / H1N1 example.

These tests lock down the assumptions that later phases of `tap.plot` will
depend on, so upstream drift in the Auspice JSONs or the chart-builder gets
caught before it breaks downstream code rather than after.

Tests skip cleanly when the data hasn't been fetched/built. To exercise
them locally:

    .venv/bin/python examples/fetch_auspice_data.py
    .venv/bin/python examples/flu-seqneut-2025to2026_titer_charts.py
    .venv/bin/pytest tests/test_real_data.py

The end-to-end `tap.plot(real_chart, real_tree, ...)` invocation lives in
later phases; this module validates only the data shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "examples" / "data"

# (subtype, auspice_filename, chart_json_filename, expected_tip_count)
SUBTYPES = [
    pytest.param(
        "H3N2",
        "flu-seqneut-2025to2026_H3N2.json",
        "flu-seqneut-2025to2026_H3N2_titers.json",
        54,
        id="H3N2",
    ),
    pytest.param(
        "H1N1",
        "flu-seqneut-2025to2026_H1N1.json",
        "flu-seqneut-2025to2026_H1N1_titers.json",
        31,
        id="H1N1",
    ),
]


def _load_or_skip(path: Path, hint: str) -> dict:
    if not path.exists():
        pytest.skip(f"{path.name} not present; run `{hint}` to generate it")
    with path.open() as f:
        return json.load(f)


def _walk_tip_haplotypes(node: dict) -> set[str]:
    """Collect every tip's `node_attrs.derived_haplotype.value` from an Auspice tree."""
    out: set[str] = set()

    def visit(n: dict) -> None:
        children = n.get("children")
        if children:
            for c in children:
                visit(c)
            return
        attrs = n.get("node_attrs", {})
        hap = attrs.get("derived_haplotype")
        if isinstance(hap, dict) and "value" in hap:
            out.add(hap["value"])

    visit(node)
    return out


def _find_axis_label_sort(node: Any) -> list[str] | None:
    """Find the first encoding with `field == "axis_label"` and return its sort.

    Walks dicts and lists recursively. Returns None if not found."""
    if isinstance(node, dict):
        for axis in ("y", "x"):
            enc = node.get(axis)
            if (
                isinstance(enc, dict)
                and enc.get("field") == "axis_label"
                and isinstance(enc.get("sort"), list)
            ):
                return enc["sort"]
        for v in node.values():
            r = _find_axis_label_sort(v)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = _find_axis_label_sort(v)
            if r is not None:
                return r
    return None


@pytest.mark.parametrize("subtype,auspice_name,chart_name,expected_tips", SUBTYPES)
def test_auspice_is_v2_with_derived_haplotype_on_every_tip(
    subtype: str, auspice_name: str, chart_name: str, expected_tips: int
) -> None:
    tree = _load_or_skip(
        DATA_DIR / auspice_name, "python examples/fetch_auspice_data.py"
    )

    assert tree.get("version", "").startswith(
        "v2"
    ), f"{auspice_name}: expected Auspice v2, got version={tree.get('version')!r}"

    tip_count = 0
    missing_haplotype: list[str] = []

    def visit(n: dict) -> None:
        nonlocal tip_count
        children = n.get("children")
        if children:
            for c in children:
                visit(c)
            return
        tip_count += 1
        hap = n.get("node_attrs", {}).get("derived_haplotype")
        if not (isinstance(hap, dict) and isinstance(hap.get("value"), str)):
            missing_haplotype.append(n.get("name", "<unnamed>"))

    visit(tree["tree"])

    assert missing_haplotype == [], (
        f"{auspice_name}: {len(missing_haplotype)} tips lack "
        f"node_attrs.derived_haplotype.value: {missing_haplotype[:5]}..."
    )
    assert tip_count == expected_tips, (
        f"{auspice_name}: expected {expected_tips} tips, got {tip_count}. "
        "Upstream tree may have changed; update SUBTYPES if intentional."
    )


@pytest.mark.parametrize("subtype,auspice_name,chart_name,expected_tips", SUBTYPES)
def test_chart_axis_label_sort_matches_tree_haplotypes(
    subtype: str, auspice_name: str, chart_name: str, expected_tips: int
) -> None:
    tree = _load_or_skip(
        DATA_DIR / auspice_name, "python examples/fetch_auspice_data.py"
    )
    chart = _load_or_skip(
        DATA_DIR / chart_name,
        "python examples/flu-seqneut-2025to2026_titer_charts.py",
    )

    sort = _find_axis_label_sort(chart)
    assert (
        sort is not None
    ), f"{chart_name}: no encoding with field='axis_label' and a sort list found"

    chart_strains = set(sort)
    tree_strains = _walk_tip_haplotypes(tree["tree"])

    assert chart_strains == tree_strains, (
        f"{subtype}: chart axis_label set != tree derived_haplotype set. "
        f"only-in-chart={sorted(chart_strains - tree_strains)[:5]}, "
        f"only-in-tree={sorted(tree_strains - chart_strains)[:5]}"
    )
    assert len(chart_strains) == expected_tips


def _build_subtype_chart(subtype: str, chart_type: str):
    """Construct an in-process Kikawa chart by importing the example builder.

    Skips the test if the upstream CSVs aren't reachable (network failure /
    repo move) so a missing network doesn't take the suite down.
    """
    import importlib.util

    builder_path = (
        Path(__file__).resolve().parent.parent
        / "examples"
        / "flu-seqneut-2025to2026_titer_charts.py"
    )
    spec = importlib.util.spec_from_file_location("builder", builder_path)
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(builder)
        titers, viruses, sera = builder.load_data()
    except Exception as exc:
        pytest.skip(f"could not load Kikawa CSVs (network?): {exc}")

    metadata = builder.build_metadata(sera)
    all_cohorts = ["All"] + sorted(sera["cohort"].unique())
    return builder.make_chart(
        subtype=subtype,
        chart_type=chart_type,
        titers=titers,
        viruses=viruses,
        metadata=metadata,
        all_cohorts=all_cohorts,
    )


def test_h3n2_end_to_end_via_tap_plot() -> None:
    """tap.plot against the real H3N2 chart + Auspice tree.

    The H3N2 chart is vertical (strain on y) → output is HConcatChart with
    the tree on the left and the chart on the right. The chart panel's
    strain sort is rewritten to the tree's tip order.
    """
    import altair as alt

    import tree_annotated_plot as tap

    auspice = DATA_DIR / "flu-seqneut-2025to2026_H3N2.json"
    if not auspice.exists():
        pytest.skip(
            "examples/data/flu-seqneut-2025to2026_H3N2.json not present; "
            "run `python examples/fetch_auspice_data.py`"
        )

    chart = _build_subtype_chart("H3N2", "iqr")
    out = tap.plot(
        str(auspice),
        chart,
        chart_strain_field="axis_label",
        tree_strain_field="derived_haplotype",
        tree_width=140,
    )

    assert isinstance(out, alt.HConcatChart)
    assert len(out.hconcat) == 2

    # The chart panel (right) should carry a sort that matches the tree's
    # tip order at every encoding referencing axis_label.
    out_dict = out.to_dict()
    inner = out_dict["hconcat"][1]
    found_sort = _find_axis_label_sort(inner)
    assert found_sort is not None
    assert len(found_sort) == 54

    # The new order should match the depth-first tip order of the loaded tree.
    with auspice.open() as f:
        tree_json = json.load(f)
    tree_tip_order = _depth_first_haplotypes(tree_json["tree"])
    assert found_sort == tree_tip_order, (
        "chart sort does not match tree tip order; "
        f"first 5 expected={tree_tip_order[:5]}, got={found_sort[:5]}"
    )


def test_h1n1_horizontal_layout_currently_unsupported() -> None:
    """The H1N1 chart has the strain on x (horizontal layout, tree on top).
    Phase 2g implements that path; until then we expect NotImplementedError."""
    import tree_annotated_plot as tap

    auspice = DATA_DIR / "flu-seqneut-2025to2026_H1N1.json"
    if not auspice.exists():
        pytest.skip(
            "examples/data/flu-seqneut-2025to2026_H1N1.json not present; "
            "run `python examples/fetch_auspice_data.py`"
        )

    chart = _build_subtype_chart("H1N1", "lines")
    with pytest.raises(NotImplementedError, match="(?i)horizontal layout"):
        tap.plot(
            str(auspice),
            chart,
            chart_strain_field="axis_label",
            tree_strain_field="derived_haplotype",
            tree_width=140,
        )


def _depth_first_haplotypes(node: dict) -> list[str]:
    """Yield tip derived_haplotype.value strings in depth-first order."""
    out: list[str] = []

    def visit(n: dict) -> None:
        children = n.get("children")
        if children:
            for c in children:
                visit(c)
            return
        v = n.get("node_attrs", {}).get("derived_haplotype", {}).get("value")
        if isinstance(v, str):
            out.append(v)

    visit(node)
    return out
