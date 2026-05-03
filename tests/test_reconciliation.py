"""Tip-set reconciliation + `prune_tree_to_chart` against synthetic fixtures.

The Kikawa real data is in perfect symmetry (every chart strain matches a
tree tip and vice versa) so it doesn't exercise the prune path or the
mismatch-error-message paths. This module builds tiny synthetic Auspice +
chart fixtures that produce specific asymmetries and asserts the
behaviors the plan locks in.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import pytest

import tree_annotated_plot as tap
from tree_annotated_plot import _tree

# ---------- fixtures ----------


def _auspice_two_clades() -> dict:
    """Auspice JSON with 5 tips in 2 clades:

    ROOT (div=0)
    ├── int_A  (div=0.01)
    │   ├── A1 (div=0.05)
    │   ├── A2 (div=0.06)
    │   └── A3 (div=0.07)
    └── int_B  (div=0.02)
        ├── B1 (div=0.08)
        └── B2 (div=0.09)
    """
    return {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [
                {
                    "name": "int_A",
                    "node_attrs": {"div": 0.01},
                    "children": [
                        {"name": "A1", "node_attrs": {"div": 0.05}},
                        {"name": "A2", "node_attrs": {"div": 0.06}},
                        {"name": "A3", "node_attrs": {"div": 0.07}},
                    ],
                },
                {
                    "name": "int_B",
                    "node_attrs": {"div": 0.02},
                    "children": [
                        {"name": "B1", "node_attrs": {"div": 0.08}},
                        {"name": "B2", "node_attrs": {"div": 0.09}},
                    ],
                },
            ],
        },
    }


def _chart_for_strains(strains: list[str], *, height: int = 200) -> alt.Chart:
    rows = [
        {"strain": s, "serum": "s1", "titer": float(i + 1)}
        for i, s in enumerate(strains)
    ]
    return (
        alt.Chart(pd.DataFrame(rows))
        .mark_circle()
        .encode(x="titer:Q", y=alt.Y("strain:N"), color="serum:N")
        .properties(width=200, height=height)
    )


# ---------- chart-not-in-tree (always fatal) ----------


def test_chart_strain_not_in_tree_is_fatal_default() -> None:
    """Chart has a strain X that the tree doesn't — fatal even though
    the tree has all 5 chart-shared strains too."""
    chart = _chart_for_strains(["A1", "A2", "A3", "B1", "B2", "X"])
    with pytest.raises(ValueError, match="not present in the tree"):
        tap.plot(
            _auspice_two_clades(),
            chart,
            chart_strain_field="strain",
            tree_strain_field="name",
        )


def test_chart_strain_not_in_tree_is_fatal_even_with_prune() -> None:
    """`prune_tree_to_chart=True` only drops *tree* tips. A chart strain
    not in the tree still raises — pruning would silently lose plot data."""
    chart = _chart_for_strains(["A1", "A2", "X"])
    with pytest.raises(ValueError, match="not present in the tree"):
        tap.plot(
            _auspice_two_clades(),
            chart,
            chart_strain_field="strain",
            tree_strain_field="name",
            prune_tree_to_chart=True,
        )


# ---------- tree-not-in-chart (fatal unless prune) ----------


def test_tree_tip_not_in_chart_is_fatal_default() -> None:
    """Tree has 5 tips; chart has 3. Default raises with a message that
    suggests `prune_tree_to_chart=True`."""
    chart = _chart_for_strains(["A1", "A2", "A3"])
    with pytest.raises(ValueError, match="prune_tree_to_chart=True"):
        tap.plot(
            _auspice_two_clades(),
            chart,
            chart_strain_field="strain",
            tree_strain_field="name",
        )


def test_tree_tip_not_in_chart_succeeds_with_prune() -> None:
    """With `prune_tree_to_chart=True`, dropped tips are removed from the
    tree and drawing succeeds."""
    chart = _chart_for_strains(["A1", "A2", "A3"])
    out = tap.plot(
        _auspice_two_clades(),
        chart,
        chart_strain_field="strain",
        tree_strain_field="name",
        prune_tree_to_chart=True,
    )
    assert isinstance(out, alt.HConcatChart)
    assert len(out.hconcat) == 2


# ---------- pruning behavior on the live tree object ----------


def test_prune_drops_specified_tips_and_keeps_topology() -> None:
    root = _tree.load_auspice(_auspice_two_clades(), tree_strain_field="name")
    pruned = _tree._prune_tree_to(root, {"A1", "A2", "A3"})
    # All B-clade tips dropped; A-clade subtree preserved.
    tip_names = [t.name for t in _tree.tips(pruned)]
    assert sorted(tip_names) == ["A1", "A2", "A3"]


def test_prune_collapses_single_child_internals_and_lca_reroots() -> None:
    """When all kept tips are inside one subtree, the original root's other
    branch vanishes, the original root collapses (single surviving child),
    and the LCA of kept tips becomes the new root."""
    root = _tree.load_auspice(_auspice_two_clades(), tree_strain_field="name")
    pruned = _tree._prune_tree_to(root, {"A1", "A2", "A3"})
    # New root is `int_A` (LCA of A1/A2/A3), with x = 0.01.
    assert pruned.name == "int_A"
    assert pruned.x == pytest.approx(0.01)
    assert len(pruned.children) == 3


def test_prune_preserves_root_to_tip_distances() -> None:
    """For `div`, each TreeNode.x is absolute. Pruning must not shift x —
    the distance from the new root to each tip equals (tip.x - root.x)
    along the new tree, which equals the original (tip.x - LCA.x)."""
    root = _tree.load_auspice(_auspice_two_clades(), tree_strain_field="name")
    pruned = _tree._prune_tree_to(root, {"A1", "A2", "A3"})
    # int_A (the new root) is at x=0.01; A1 at 0.05, A2 at 0.06, A3 at 0.07.
    by_name = {t.name: t for t in _tree.tips(pruned)}
    assert by_name["A1"].x == pytest.approx(0.05)
    assert by_name["A2"].x == pytest.approx(0.06)
    assert by_name["A3"].x == pytest.approx(0.07)
    # New-root-to-tip distance is the same as original LCA-to-tip distance.
    for tip_name, expected_delta in [
        ("A1", 0.05 - 0.01),
        ("A2", 0.06 - 0.01),
        ("A3", 0.07 - 0.01),
    ]:
        assert by_name[tip_name].x - pruned.x == pytest.approx(expected_delta)


def test_prune_keeps_original_root_when_kept_tips_span_both_branches() -> None:
    """If kept tips span ≥2 of the original root's child branches, the
    LCA *is* the original root and pruning preserves it."""
    root = _tree.load_auspice(_auspice_two_clades(), tree_strain_field="name")
    pruned = _tree._prune_tree_to(root, {"A1", "B1"})
    assert pruned.name == "ROOT"
    assert pruned.x == pytest.approx(0.0)
    # Both surviving paths got their single-child internals collapsed.
    # int_A's only kept child is A1 → A1 sits directly under ROOT.
    # int_B's only kept child is B1 → B1 sits directly under ROOT.
    assert sorted(c.name for c in pruned.children) == ["A1", "B1"]


def test_prune_no_overlap_raises() -> None:
    """If keep_strains has no overlap with the tree's tips, the pruned
    result would be empty — raise rather than silently return None."""
    root = _tree.load_auspice(_auspice_two_clades(), tree_strain_field="name")
    with pytest.raises(ValueError, match="no tips remain"):
        _tree._prune_tree_to(root, {"nonexistent"})


# ---------- duplicate tree_strain_field values ----------


def test_duplicate_tree_strain_field_values_are_fatal() -> None:
    """Two tips share the same `name` → fatal."""
    bad_tree = {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [
                {"name": "DUP", "node_attrs": {"div": 0.01}},
                {"name": "DUP", "node_attrs": {"div": 0.02}},  # duplicate!
                {"name": "OK", "node_attrs": {"div": 0.03}},
            ],
        },
    }
    chart = _chart_for_strains(["DUP", "OK"])
    with pytest.raises(ValueError, match="duplicate values across tips"):
        tap.plot(
            bad_tree,
            chart,
            chart_strain_field="strain",
            tree_strain_field="name",
        )


# ---------- error message content ----------


def test_error_message_contains_sample_values_and_candidate_hint() -> None:
    """A deliberate wrong-field choice should produce an error mentioning
    sample values from each side AND at least one candidate-field
    suggestion (the chart's `strain` column or the tree's `name`)."""
    # Tree tips have name=A1/A2/...; chart axis encodes `cohort` (which has
    # only one distinct value, "s1", i.e. 0% overlap). Meanwhile the chart's
    # `strain` column has values matching the tree's `name`. The candidate
    # hint should suggest chart_strain_field='strain'.
    rows = [
        {"strain": s, "cohort": "s1", "titer": float(i)}
        for i, s in enumerate(["A1", "A2", "A3", "B1", "B2"])
    ]
    chart = (
        alt.Chart(pd.DataFrame(rows))
        .mark_circle()
        .encode(x="titer:Q", y=alt.Y("cohort:N"))
        .properties(width=200, height=200)
    )
    with pytest.raises(ValueError) as excinfo:
        tap.plot(
            _auspice_two_clades(),
            chart,
            chart_strain_field="cohort",  # wrong choice on chart side
            tree_strain_field="name",
        )
    msg = str(excinfo.value)
    # Includes sample values from both sides:
    assert "Sample chart_strain_field values:" in msg
    assert "Sample tree_strain_field values:" in msg
    # And the candidate hint suggests chart_strain_field='strain':
    assert "chart_strain_field='strain'" in msg
