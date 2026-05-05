"""Tests for `color_tree_by`: per-node attr / genotype / haplotype coloring,
Auspice-scale preference, default-palette fallback, gray-for-missing,
legend wiring."""

from __future__ import annotations

from typing import Any

import altair as alt
import pandas as pd
import pytest

import tree_annotated_plot
from tree_annotated_plot import _color, _tree


def _attr_auspice() -> dict:
    """Tiny tree with `subclade` on every node and tips A..D in two clades."""
    return {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0, "subclade": {"value": "X"}},
            "children": [
                {
                    "name": "INT_LEFT",
                    "node_attrs": {"div": 0.02, "subclade": {"value": "X"}},
                    "children": [
                        {
                            "name": "A",
                            "node_attrs": {
                                "div": 0.04,
                                "subclade": {"value": "X"},
                            },
                        },
                        {
                            "name": "B",
                            "node_attrs": {
                                "div": 0.05,
                                "subclade": {"value": "X"},
                            },
                        },
                    ],
                },
                {
                    "name": "INT_RIGHT",
                    "node_attrs": {"div": 0.03, "subclade": {"value": "Y"}},
                    "children": [
                        {
                            "name": "C",
                            "node_attrs": {
                                "div": 0.06,
                                "subclade": {"value": "Y"},
                            },
                        },
                        {
                            "name": "D",
                            "node_attrs": {
                                "div": 0.07,
                                "subclade": {"value": "Z"},
                            },
                        },
                    ],
                },
            ],
        },
    }


def _genotype_auspice(*, mutations_at_158: bool = True) -> dict:
    """Tree with HA1 mutations along selected branches.

    With `mutations_at_158=True` (default):
    - tip_A inherits N158K via its branch (state K).
    - tip_B is on a no-mutation branch (root state N).
    - INT1 carries N158D, so its descendants tip_C, tip_D are state D.

    With `mutations_at_158=False`: same topology, but no HA1:158 mutation
    anywhere — used for the invariant-site case.
    """
    site_158_mut = "N158K" if mutations_at_158 else None
    int1_mut = "N158D" if mutations_at_158 else None
    return {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [
                {
                    "name": "tip_A",
                    "node_attrs": {"div": 0.04},
                    "branch_attrs": (
                        {"mutations": {"HA1": [site_158_mut]}} if site_158_mut else {}
                    ),
                },
                {"name": "tip_B", "node_attrs": {"div": 0.05}},
                {
                    "name": "INT1",
                    "node_attrs": {"div": 0.02},
                    "branch_attrs": (
                        {"mutations": {"HA1": [int1_mut]}} if int1_mut else {}
                    ),
                    "children": [
                        {"name": "tip_C", "node_attrs": {"div": 0.06}},
                        {"name": "tip_D", "node_attrs": {"div": 0.07}},
                    ],
                },
            ],
        },
    }


def _haplotype_auspice() -> dict:
    """Tree carrying HA1 mutations at sites 158 *and* 189 along independent
    branches, so a 2-site haplotype gives several distinct categories."""
    return {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [
                {
                    "name": "tip_A",
                    "node_attrs": {"div": 0.04},
                    "branch_attrs": {"mutations": {"HA1": ["N158K"]}},
                },
                {
                    "name": "tip_B",
                    "node_attrs": {"div": 0.05},
                    "branch_attrs": {"mutations": {"HA1": ["S189T"]}},
                },
                {
                    "name": "INT1",
                    "node_attrs": {"div": 0.02},
                    "branch_attrs": {"mutations": {"HA1": ["N158K", "S189T"]}},
                    "children": [
                        {"name": "tip_C", "node_attrs": {"div": 0.06}},
                        {"name": "tip_D", "node_attrs": {"div": 0.07}},
                    ],
                },
            ],
        },
    }


def _load(d: dict) -> _tree.TreeNode:
    return _tree.load_auspice(d, tree_strain_field="name", branch_length="div")


# -----------------------------------------------------------------------------
# node_attrs path
# -----------------------------------------------------------------------------


def test_color_tree_by_node_attr_assigns_per_tip():
    root = _load(_attr_auspice())
    m = _color.compute_node_color_values(root, "subclade")
    assert m.values_by_node["A"] == "X"
    assert m.values_by_node["B"] == "X"
    assert m.values_by_node["C"] == "Y"
    assert m.values_by_node["D"] == "Z"


def test_color_tree_by_node_attr_internal_nodes():
    root = _load(_attr_auspice())
    m = _color.compute_node_color_values(root, "subclade")
    assert m.values_by_node["INT_LEFT"] == "X"
    assert m.values_by_node["INT_RIGHT"] == "Y"
    assert m.values_by_node["ROOT"] == "X"


def test_color_tree_by_node_attr_unwraps_value():
    # `node_attrs.subclade = {"value": "X"}` resolves to "X", not the dict.
    root = _load(_attr_auspice())
    m = _color.compute_node_color_values(root, "subclade")
    assert "X" in m.values_by_node.values()


def test_color_tree_by_node_attr_missing_marked_unknown():
    d = _attr_auspice()
    # Strip subclade off a single tip.
    d["tree"]["children"][0]["children"][0]["node_attrs"].pop("subclade")
    root = _load(d)
    m = _color.compute_node_color_values(root, "subclade")
    assert m.values_by_node["A"] == "unknown"
    # Domain places "unknown" last and pairs it with #888888.
    assert m.domain[-1] == "unknown"
    assert m.range_[-1] == "#888888"
    # A is a tip, so the legend must keep "unknown" visible.
    assert m.legend_values is None


def test_color_tree_by_unknown_omitted_from_legend_when_only_internal():
    """When only internal nodes lack the attribute (every tip is annotated),
    "unknown" stays in the scale (so internal segments render gray) but is
    hidden from the legend."""
    d = _attr_auspice()
    # Strip subclade off the ROOT internal node only — all tips remain
    # annotated.
    d["tree"]["node_attrs"].pop("subclade")
    root = _load(d)
    m = _color.compute_node_color_values(root, "subclade")
    assert m.values_by_node["ROOT"] == "unknown"
    # Domain still includes "unknown" so the seg_df row for ROOT renders gray.
    assert "unknown" in m.domain
    # But the legend display drops it.
    assert m.legend_values is not None
    assert "unknown" not in m.legend_values
    # And the rest of the legend matches domain-minus-unknown.
    assert m.legend_values == [c for c in m.domain if c != "unknown"]


def test_color_tree_by_unknown_absent_legend_unrestricted():
    """Fully annotated tree (no `"unknown"` anywhere) -> legend_values stays
    None, i.e. the legend uses the full domain."""
    root = _load(_attr_auspice())
    m = _color.compute_node_color_values(root, "subclade")
    assert "unknown" not in m.values_by_node.values()
    assert m.legend_values is None


def test_color_tree_by_missing_attr_raises_lists_keys():
    root = _load(_attr_auspice())
    with pytest.raises(ValueError) as exc:
        _color.compute_node_color_values(root, "nonexistent_field")
    msg = str(exc.value)
    assert "nonexistent_field" in msg
    # Observed keys appear in the message — div and subclade at minimum.
    assert "'div'" in msg
    assert "'subclade'" in msg


# -----------------------------------------------------------------------------
# genotype path: single-site
# -----------------------------------------------------------------------------


def test_color_tree_by_genotype_root_state_inference():
    root = _load(_genotype_auspice())
    m = _color.compute_node_color_values(root, "genotype:HA1:158")
    assert m.values_by_node["tip_A"] == "K158"  # branch carries N158K
    assert m.values_by_node["tip_B"] == "N158"  # root state
    assert m.values_by_node["tip_C"] == "D158"  # inherited from INT1's N158D
    assert m.values_by_node["tip_D"] == "D158"


def test_color_tree_by_genotype_multiple_mutations_along_path():
    d = {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [
                {"name": "tip_X", "node_attrs": {"div": 0.05}},
                {
                    "name": "INT1",
                    "node_attrs": {"div": 0.02},
                    "branch_attrs": {"mutations": {"HA1": ["N158K"]}},
                    "children": [
                        {
                            "name": "tip_Y",
                            "node_attrs": {"div": 0.04},
                        },
                        {
                            "name": "tip_Z",
                            "node_attrs": {"div": 0.06},
                            "branch_attrs": {"mutations": {"HA1": ["K158R"]}},
                        },
                    ],
                },
            ],
        },
    }
    root = _load(d)
    m = _color.compute_node_color_values(root, "genotype:HA1:158")
    assert m.values_by_node["tip_X"] == "N158"  # root, no muts on path
    assert m.values_by_node["tip_Y"] == "K158"  # parent N158K
    assert m.values_by_node["tip_Z"] == "R158"  # N158K then K158R


def test_color_tree_by_genotype_single_site_invariant_renders_no_variation():
    root = _load(_genotype_auspice(mutations_at_158=False))
    # The JSON has no mutations anywhere, so this fires the "no mutation
    # annotations" error rather than the invariant path. Add a stray
    # mutation at a different site so mutations *exist* in the tree but
    # NOT at site 158.
    d = _genotype_auspice(mutations_at_158=False)
    d["tree"]["children"][0]["branch_attrs"] = {"mutations": {"HA1": ["S145N"]}}
    root = _load(d)
    m = _color.compute_node_color_values(root, "genotype:HA1:158")
    # Every node gets the literal "<no variation>" category.
    assert set(m.values_by_node.values()) == {"<no variation>"}
    assert m.domain == ["<no variation>"]


def test_color_tree_by_genotype_no_mutations_anywhere_raises():
    d = _genotype_auspice(mutations_at_158=False)
    root = _load(d)
    with pytest.raises(ValueError) as exc:
        _color.compute_node_color_values(root, "genotype:HA1:158")
    assert "no branch_attrs.mutations annotations" in str(exc.value)


def test_color_tree_by_genotype_missing_gene_raises_lists_genes():
    root = _load(_genotype_auspice())
    with pytest.raises(ValueError) as exc:
        _color.compute_node_color_values(root, "genotype:NONEXISTENT:158")
    msg = str(exc.value)
    assert "'NONEXISTENT'" in msg
    assert "'HA1'" in msg


# -----------------------------------------------------------------------------
# genotype path: haplotype
# -----------------------------------------------------------------------------


def test_color_tree_by_haplotype_basic():
    root = _load(_haplotype_auspice())
    m = _color.compute_node_color_values(root, "genotype:HA1:158,189")
    # tip_A: branch N158K, no 189 mut -> K158/S189
    # tip_B: branch S189T, no 158 mut -> N158/T189
    # INT1's children inherit both N158K and S189T -> K158/T189
    assert m.values_by_node["tip_A"] == "K158/S189"
    assert m.values_by_node["tip_B"] == "N158/T189"
    assert m.values_by_node["tip_C"] == "K158/T189"
    assert m.values_by_node["tip_D"] == "K158/T189"


def test_color_tree_by_haplotype_drops_invariant_sites():
    # Same tree as the single-site test, but ask for a 2-site haplotype
    # where only 158 has mutations: the haplotype label collapses to just
    # the 158 locus.
    d = _genotype_auspice()  # only 158 has mutations
    root = _load(d)
    m = _color.compute_node_color_values(root, "genotype:HA1:158,189")
    # 189 is invariant in this tree -> dropped from the label.
    assert m.values_by_node["tip_A"] == "K158"
    assert m.values_by_node["tip_B"] == "N158"
    assert m.values_by_node["tip_C"] == "D158"


def test_color_tree_by_haplotype_all_invariant_renders_no_variation():
    d = _genotype_auspice(mutations_at_158=False)
    # Need mutations to exist somewhere so we don't trip the
    # "no mutations anywhere" guard. Add a HA1 mutation at a third site.
    d["tree"]["children"][0]["branch_attrs"] = {"mutations": {"HA1": ["S145N"]}}
    root = _load(d)
    m = _color.compute_node_color_values(root, "genotype:HA1:158,189")
    assert set(m.values_by_node.values()) == {"<no variation>"}
    assert m.domain == ["<no variation>"]


def test_color_tree_by_haplotype_preserves_user_site_order():
    root = _load(_haplotype_auspice())
    m = _color.compute_node_color_values(root, "genotype:HA1:189,158")
    # User wrote 189 first, so the label has 189 first.
    assert m.values_by_node["tip_A"] == "S189/K158"
    assert m.values_by_node["tip_B"] == "T189/N158"


def test_color_tree_by_haplotype_duplicate_sites_raises():
    root = _load(_haplotype_auspice())
    with pytest.raises(ValueError) as exc:
        _color.compute_node_color_values(root, "genotype:HA1:158,158")
    assert "duplicates" in str(exc.value)


def test_color_tree_by_genotype_site_int_form_required():
    root = _load(_haplotype_auspice())
    with pytest.raises(ValueError) as exc:
        _color.compute_node_color_values(root, "genotype:HA1:foo")
    assert "positive integer" in str(exc.value)


# -----------------------------------------------------------------------------
# scale resolution: Auspice meta vs default palette
# -----------------------------------------------------------------------------


def test_color_tree_by_uses_auspice_scale_when_present():
    root = _load(_attr_auspice())
    meta = {
        "colorings": [
            {
                "key": "subclade",
                "type": "categorical",
                "scale": [["X", "#ff0000"], ["Y", "#00ff00"], ["Z", "#0000ff"]],
            },
        ],
    }
    m = _color.compute_node_color_values(root, "subclade", auspice_meta=meta)
    color_for = dict(zip(m.domain, m.range_))
    assert color_for["X"] == "#ff0000"
    assert color_for["Y"] == "#00ff00"
    assert color_for["Z"] == "#0000ff"


def test_color_tree_by_falls_back_to_default_palette_for_unmapped():
    """Auspice scale only covers X and Z; Y must take the first slot of the
    Auspice fallback palette sized to the unmapped count (1 here, so
    `_AUSPICE_PALETTE[1][0]`). Auspice-mapped slots don't consume
    fallback-palette indices."""
    root = _load(_attr_auspice())
    meta = {
        "colorings": [
            {
                "key": "subclade",
                "type": "categorical",
                "scale": [["X", "#ff0000"], ["Z", "#0000ff"]],
            },
        ],
    }
    m = _color.compute_node_color_values(root, "subclade", auspice_meta=meta)
    color_for = dict(zip(m.domain, m.range_))
    assert color_for["X"] == "#ff0000"
    assert color_for["Z"] == "#0000ff"
    # 1 unmapped category (Y) -> _AUSPICE_PALETTE[1] -> single color.
    assert color_for["Y"] == _color._AUSPICE_PALETTE[1][0]


def test_color_tree_by_legend_title_uses_auspice_meta_title():
    root = _load(_attr_auspice())
    meta = {
        "colorings": [{"key": "subclade", "type": "categorical", "title": "Subclade"}]
    }
    m = _color.compute_node_color_values(root, "subclade", auspice_meta=meta)
    assert m.legend_title == "Subclade"


def test_color_tree_by_genotype_ignores_auspice_scale():
    """Even if meta.colorings happens to have a 'genotype' entry, the
    genotype path doesn't consult it — colors come from `_AUSPICE_PALETTE`
    sized to the category count."""
    root = _load(_genotype_auspice())
    meta = {
        "colorings": [
            {
                "key": "genotype",
                "type": "categorical",
                "scale": [["K158", "#ff0000"]],
            },
        ],
    }
    m = _color.compute_node_color_values(root, "genotype:HA1:158", auspice_meta=meta)
    color_for = dict(zip(m.domain, m.range_))
    # K158 should NOT pick up the Auspice color; it gets a palette slot.
    assert color_for["K158"] != "#ff0000"
    n_real = sum(1 for c in m.domain if c != "unknown")
    assert color_for["K158"] in _color._AUSPICE_PALETTE[n_real]


def test_color_tree_by_no_auspice_meta_uses_default_palette():
    """No `auspice_meta` and a node-attr spec -> all real categories come
    from `_AUSPICE_PALETTE[N]` where N is the number of real categories."""
    root = _load(_attr_auspice())
    m = _color.compute_node_color_values(root, "subclade", auspice_meta=None)
    n_real = sum(1 for c in m.domain if c != "unknown")
    palette_n = _color._AUSPICE_PALETTE[n_real]
    for cat, col in zip(m.domain, m.range_):
        if cat == "unknown":
            assert col == "#888888"
        else:
            assert col in palette_n


def test_color_tree_by_categories_sorted_by_descending_frequency():
    """Categories should be ordered by descending count so the most common
    one ends up at index 0 (where Auspice's per-N palette puts its
    deepest-blue start)."""
    # Build a tree where subclade frequencies are X=4 (ROOT, INT_LEFT, A, B),
    # Y=2 (INT_RIGHT, C), Z=1 (D). After sorting by descending count we
    # expect domain[:3] == ["X", "Y", "Z"].
    root = _load(_attr_auspice())
    m = _color.compute_node_color_values(root, "subclade")
    real = [c for c in m.domain if c != "unknown"]
    assert real == ["X", "Y", "Z"]


def test_color_tree_by_default_palette_matches_auspice_for_six_categories():
    """For a 6-category attribute, the resolved range must equal Auspice's
    `colors[6]` exactly. Pins the visual match against Nextstrain."""
    # Build a synthetic tree with 6 categories at distinct frequencies so
    # ordering is unambiguous.
    d = {
        "version": "v2",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0, "clade": {"value": "C1"}},
            "children": [
                {
                    "name": f"tip_{i}",
                    "node_attrs": {"div": 0.01 * i, "clade": {"value": v}},
                }
                # Frequencies: C1=6, C2=5, C3=4, C4=3, C5=2, C6=1 -> total 21
                for i, v in enumerate(
                    ["C1"] * 5  # plus the one on ROOT, total C1=6
                    + ["C2"] * 5
                    + ["C3"] * 4
                    + ["C4"] * 3
                    + ["C5"] * 2
                    + ["C6"]
                )
            ],
        },
    }
    root = _load(d)
    m = _color.compute_node_color_values(root, "clade")
    assert m.domain == ["C1", "C2", "C3", "C4", "C5", "C6"]
    assert tuple(m.range_) == _color._AUSPICE_PALETTE[6]


def test_color_tree_by_gray_reserved_for_unknown():
    """For a tree with non-missing categories plus 'unknown', gray (#888888)
    must appear *only* at the 'unknown' slot — never inside the per-N
    Auspice palette so a fallback-mapped category cannot collide with it."""
    d = _attr_auspice()
    # Drop subclade off one tip so "unknown" enters the legend.
    d["tree"]["children"][0]["children"][0]["node_attrs"].pop("subclade")
    root = _load(d)
    m = _color.compute_node_color_values(root, "subclade")
    gray_positions = [i for i, c in enumerate(m.range_) if c == "#888888"]
    assert len(gray_positions) == 1
    assert m.domain[gray_positions[0]] == "unknown"
    # And gray is not anywhere in the Auspice palette.
    for entry in _color._AUSPICE_PALETTE:
        assert "#888888" not in entry
        assert "#7f7f7f" not in entry


# -----------------------------------------------------------------------------
# plot()-level: encoding placement, legend orient, default-none
# -----------------------------------------------------------------------------


def _vertical_chart(strains: list[str]) -> alt.Chart:
    df = pd.DataFrame({"strain": strains, "titer": [1.0, 2.0, 4.0, 8.0]})
    return (
        alt.Chart(df)
        .mark_circle()
        .encode(x="titer:Q", y=alt.Y("strain:N"))
        .properties(width=200, height=200)
    )


def _kw():
    return dict(
        chart_strain_field="strain", tree_strain_field="name", branch_length="div"
    )


def _find_color_encodings(node: Any) -> list[tuple[str, dict]]:
    """Recursively find every encoding-block 'color' on the spec, returning
    (json-pointer-ish path, encoding dict)."""
    hits: list[tuple[str, dict]] = []

    def walk(o: Any, path: str) -> None:
        if isinstance(o, dict):
            enc = o.get("encoding")
            if isinstance(enc, dict) and "color" in enc:
                hits.append((path, enc["color"]))
            for k, v in o.items():
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")

    walk(node, "")
    return hits


def _tree_panel_color_encodings(out) -> list[dict]:
    """Color encodings on the tree panel only (which is hconcat[0] for our
    'left'-default vertical layout). Filtered to those backed by the
    'color_value' field — pre-existing chart colors are not."""
    spec = out.to_dict()
    panels = spec.get("hconcat") or spec.get("vconcat") or []
    assert panels
    tree_panel = panels[0]
    return [
        enc
        for _, enc in _find_color_encodings(tree_panel)
        if isinstance(enc, dict) and enc.get("field") == "color_value"
    ]


def test_color_tree_by_default_none_no_color_encoding():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
    )
    encs = _tree_panel_color_encodings(out)
    assert encs == []


def test_color_tree_by_legend_orient_bottom():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
    )
    encs = _tree_panel_color_encodings(out)
    assert len(encs) >= 1
    for enc in encs:
        legend = enc.get("legend") or {}
        assert legend.get("orient") == "bottom"


def test_color_tree_by_legend_title_is_spec_string():
    # No auspice_meta.colorings.title -> falls back to the literal spec.
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
    )
    encs = _tree_panel_color_encodings(out)
    assert encs[0]["legend"]["title"] == "subclade"


def test_color_tree_by_branches_and_tips_share_field():
    """The mark_rule (branches) and mark_circle (tips) both reference the
    same `color_value:N` field, so Altair collapses them into one legend."""
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
    )
    encs = _tree_panel_color_encodings(out)
    # Two encodings: one on the seg_df rule, one on the tips_df circle.
    assert len(encs) == 2
    fields = {enc["field"] for enc in encs}
    assert fields == {"color_value"}


def test_color_tree_by_legend_hides_internal_only_unknown():
    """When only an internal node lacks the attribute, the rendered spec's
    legend.values must be set and must not contain 'unknown'. Internal-node
    branches still render gray via the unchanged scale."""
    d = _attr_auspice()
    d["tree"]["node_attrs"].pop("subclade")  # drop subclade off ROOT only
    out = tree_annotated_plot.plot(
        d,
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
    )
    encs = _tree_panel_color_encodings(out)
    assert len(encs) >= 1
    for enc in encs:
        legend = enc.get("legend") or {}
        assert "values" in legend
        assert "unknown" not in legend["values"]
        # Scale still carries "unknown" so the gray rendering works.
        assert "unknown" in enc["scale"]["domain"]


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def _write_chart_json(path, chart: alt.Chart) -> None:
    chart.save(str(path))


def _write_tree_json(path, tree: dict) -> None:
    import json

    path.write_text(json.dumps(tree))


def _run_cli(args, expect_success: bool = True):
    from click.testing import CliRunner

    from tree_annotated_plot import cli as cli_module

    runner = CliRunner()
    result = runner.invoke(cli_module.main, args, catch_exceptions=False)
    if expect_success and result.exit_code != 0:
        raise AssertionError(f"CLI exit {result.exit_code}\n{result.output}")
    return result


def _cli_setup(tmp_path, tree_dict: dict, chart: alt.Chart):
    tree_path = tmp_path / "tree.json"
    chart_path = tmp_path / "chart.json"
    out_path = tmp_path / "out.json"
    _write_tree_json(tree_path, tree_dict)
    _write_chart_json(chart_path, chart)
    return tree_path, chart_path, out_path


def test_cli_color_tree_by_subclade(tmp_path):
    tree_path, chart_path, out_path = _cli_setup(
        tmp_path, _attr_auspice(), _vertical_chart(["A", "B", "C", "D"])
    )
    _run_cli(
        [
            "--tree",
            str(tree_path),
            "--chart",
            str(chart_path),
            "--output",
            str(out_path),
            "--chart-strain-field",
            "strain",
            "--tree-strain-field",
            "name",
            "--branch-length",
            "div",
            "--color-tree-by",
            "subclade",
        ]
    )
    assert out_path.exists()
    import json

    spec = json.loads(out_path.read_text())
    encs = [
        enc
        for _, enc in _find_color_encodings(spec.get("hconcat", [{}])[0])
        if isinstance(enc, dict) and enc.get("field") == "color_value"
    ]
    assert encs


def test_cli_color_tree_by_genotype(tmp_path):
    tree_path, chart_path, out_path = _cli_setup(
        tmp_path,
        _genotype_auspice(),
        _vertical_chart(["tip_A", "tip_B", "tip_C", "tip_D"]),
    )
    _run_cli(
        [
            "--tree",
            str(tree_path),
            "--chart",
            str(chart_path),
            "--output",
            str(out_path),
            "--chart-strain-field",
            "strain",
            "--tree-strain-field",
            "name",
            "--branch-length",
            "div",
            "--color-tree-by",
            "genotype:HA1:158",
        ]
    )
    assert out_path.exists()


def test_cli_color_tree_by_haplotype(tmp_path):
    """Comma in `genotype:HA1:158,189` must survive click's argument parsing."""
    tree_path, chart_path, out_path = _cli_setup(
        tmp_path,
        _haplotype_auspice(),
        _vertical_chart(["tip_A", "tip_B", "tip_C", "tip_D"]),
    )
    _run_cli(
        [
            "--tree",
            str(tree_path),
            "--chart",
            str(chart_path),
            "--output",
            str(out_path),
            "--chart-strain-field",
            "strain",
            "--tree-strain-field",
            "name",
            "--branch-length",
            "div",
            "--color-tree-by",
            "genotype:HA1:158,189",
        ]
    )
    assert out_path.exists()
    import json

    spec = json.loads(out_path.read_text())
    encs = [
        enc
        for _, enc in _find_color_encodings(spec.get("hconcat", [{}])[0])
        if isinstance(enc, dict) and enc.get("field") == "color_value"
    ]
    assert encs
    # Domain should contain at least one slash-joined haplotype label.
    domain = encs[0].get("scale", {}).get("domain", [])
    assert any("/" in cat for cat in domain)
