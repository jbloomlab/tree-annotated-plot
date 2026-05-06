"""Tests for `tree_color_scale`, `tree_color_legend_format`,
`tree_color_legend_show`, and `scale_bar_font_size`."""

from __future__ import annotations

import json
from typing import Any

import altair as alt
import pandas as pd
import pytest

import tree_annotated_plot
from tree_annotated_plot import _color, _tree

# -----------------------------------------------------------------------------
# Test fixtures (inlined rather than imported across test modules so this file
# stays runnable on its own — `tests/` has no __init__.py).
# -----------------------------------------------------------------------------


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


def _genotype_auspice() -> dict:
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
                {"name": "tip_B", "node_attrs": {"div": 0.05}},
                {
                    "name": "INT1",
                    "node_attrs": {"div": 0.02},
                    "branch_attrs": {"mutations": {"HA1": ["N158D"]}},
                    "children": [
                        {"name": "tip_C", "node_attrs": {"div": 0.06}},
                        {"name": "tip_D", "node_attrs": {"div": 0.07}},
                    ],
                },
            ],
        },
    }


def _haplotype_auspice() -> dict:
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
    spec = out.to_dict()
    panels = spec.get("hconcat") or spec.get("vconcat") or []
    assert panels
    tree_panel = panels[0]
    return [
        enc
        for _, enc in _find_color_encodings(tree_panel)
        if isinstance(enc, dict) and enc.get("field") == "color_value"
    ]


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
    tree_path.write_text(json.dumps(tree_dict))
    chart.save(str(chart_path))
    return tree_path, chart_path, out_path


# -----------------------------------------------------------------------------
# tree_color_scale: validation
# -----------------------------------------------------------------------------


def test_tree_color_scale_overrides_palette_in_user_order():
    root = _load(_attr_auspice())
    user_scale = {"Z": "#111111", "Y": "#222222", "X": "#333333"}
    m = _color.compute_node_color_values(root, "subclade", tree_color_scale=user_scale)
    # Domain order is the dict's insertion order — not descending frequency.
    assert m.domain == ["Z", "Y", "X"]
    assert m.range_ == ["#111111", "#222222", "#333333"]


def test_tree_color_scale_appends_unknown_when_present():
    d = _attr_auspice()
    # Strip subclade off one tip so "unknown" is a real category.
    d["tree"]["children"][0]["children"][0]["node_attrs"].pop("subclade")
    root = _load(d)
    m = _color.compute_node_color_values(
        root,
        "subclade",
        tree_color_scale={"X": "#aaaaaa", "Y": "#bbbbbb", "Z": "#cccccc"},
    )
    assert m.domain[-1] == "unknown"
    assert m.range_[-1] == "#888888"
    # User keys come before "unknown" in the domain.
    assert m.domain[:-1] == ["X", "Y", "Z"]


def test_tree_color_scale_missing_key_raises_lists_categories():
    root = _load(_attr_auspice())
    with pytest.raises(ValueError) as exc:
        _color.compute_node_color_values(
            root,
            "subclade",
            tree_color_scale={"X": "#aaaaaa", "Y": "#bbbbbb"},  # missing Z
        )
    msg = str(exc.value)
    assert "Tree categories" in msg
    assert "'X'" in msg and "'Y'" in msg and "'Z'" in msg
    assert "Missing from your scale" in msg
    assert "'Z'" in msg


def test_tree_color_scale_extra_key_raises():
    root = _load(_attr_auspice())
    with pytest.raises(ValueError) as exc:
        _color.compute_node_color_values(
            root,
            "subclade",
            tree_color_scale={
                "X": "#aaaaaa",
                "Y": "#bbbbbb",
                "Z": "#cccccc",
                "W": "#dddddd",  # not in tree
            },
        )
    msg = str(exc.value)
    assert "Unexpected in your scale" in msg
    assert "'W'" in msg


def test_tree_color_scale_unknown_key_rejected():
    root = _load(_attr_auspice())
    with pytest.raises(ValueError, match="must not contain"):
        _color.compute_node_color_values(
            root,
            "subclade",
            tree_color_scale={
                "X": "#aaaaaa",
                "Y": "#bbbbbb",
                "Z": "#cccccc",
                "unknown": "#999999",
            },
        )


def test_tree_color_scale_genotype_categories_use_letter_site():
    """User-supplied scale for a single-site genotype must use `<letter><site>`
    keys (e.g. "K158"), not bare letters. Mismatch error names the actual
    tree categories so the user can copy them."""
    root = _load(_genotype_auspice())
    with pytest.raises(ValueError) as exc:
        _color.compute_node_color_values(
            root,
            "genotype:HA1:158",
            tree_color_scale={"K": "#aaa", "N": "#bbb", "D": "#ccc"},
        )
    msg = str(exc.value)
    # The actual tree categories include the site number.
    assert "'K158'" in msg or "'N158'" in msg or "'D158'" in msg


def test_tree_color_scale_haplotype_categories_use_slash_join():
    root = _load(_haplotype_auspice())
    # Real categories are slash-joined like "K158/T189", "N158/T189", etc.
    m_default = _color.compute_node_color_values(root, "genotype:HA1:158,189")
    real_cats = [c for c in m_default.domain if c != "unknown"]
    # All real cats should contain "/" given two varying sites.
    assert all("/" in c for c in real_cats), real_cats
    user_scale = {c: "#000000" for c in real_cats}
    m = _color.compute_node_color_values(
        root, "genotype:HA1:158,189", tree_color_scale=user_scale
    )
    # Order matches the dict's insertion order.
    assert m.domain[: len(real_cats)] == list(user_scale.keys())


# -----------------------------------------------------------------------------
# tree_color_scale: end-to-end via plot()
# -----------------------------------------------------------------------------


def test_plot_tree_color_scale_propagates_to_spec():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
        tree_color_scale={"Z": "#111111", "Y": "#222222", "X": "#333333"},
    )
    encs = _tree_panel_color_encodings(out)
    assert encs
    scale = encs[0]["scale"]
    assert scale["domain"] == ["Z", "Y", "X"]
    assert scale["range"] == ["#111111", "#222222", "#333333"]


def test_plot_tree_color_scale_without_color_tree_by_raises():
    with pytest.raises(ValueError, match="color_tree_by is None"):
        tree_annotated_plot.plot(
            _attr_auspice(),
            _vertical_chart(["A", "B", "C", "D"]),
            **_kw(),
            tree_color_scale={"X": "#aaa", "Y": "#bbb", "Z": "#ccc"},
        )


# -----------------------------------------------------------------------------
# tree_color_legend_format
# -----------------------------------------------------------------------------


def test_legend_format_default_is_bottom_orient_no_overrides():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
    )
    encs = _tree_panel_color_encodings(out)
    legend = encs[0]["legend"]
    assert legend["orient"] == "bottom"
    assert "titleFontSize" not in legend
    assert "labelFontSize" not in legend
    # No smart-default columns when orient is bottom.
    assert "columns" not in legend


def test_legend_format_font_sizes_propagate():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
        tree_color_legend_format={"labelFontSize": 13, "titleFontSize": 13},
    )
    encs = _tree_panel_color_encodings(out)
    for enc in encs:
        legend = enc["legend"]
        assert legend["labelFontSize"] == 13
        assert legend["titleFontSize"] == 13
        # Default orient stays bottom because we didn't override it.
        assert legend["orient"] == "bottom"


def test_legend_format_orient_overrides_default():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
        tree_color_legend_format={"orient": "right"},
    )
    encs = _tree_panel_color_encodings(out)
    assert encs[0]["legend"]["orient"] == "right"


@pytest.mark.parametrize("orient", ["left", "right"])
def test_legend_format_smart_default_columns_for_side_orients(orient):
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
        tree_color_legend_format={"orient": orient},
    )
    legend = _tree_panel_color_encodings(out)[0]["legend"]
    assert legend["orient"] == orient
    assert legend["columns"] == 1


def test_legend_format_user_columns_beats_smart_default():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
        tree_color_legend_format={"orient": "left", "columns": 3},
    )
    legend = _tree_panel_color_encodings(out)[0]["legend"]
    assert legend["columns"] == 3


def test_legend_format_user_direction_disables_smart_default():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
        tree_color_legend_format={"orient": "left", "direction": "horizontal"},
    )
    legend = _tree_panel_color_encodings(out)[0]["legend"]
    assert legend["direction"] == "horizontal"
    assert "columns" not in legend


@pytest.mark.parametrize("orient", ["top", "bottom", "top-left", "bottom-right"])
def test_legend_format_smart_default_skipped_for_top_bottom_orients(orient):
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
        tree_color_legend_format={"orient": orient},
    )
    legend = _tree_panel_color_encodings(out)[0]["legend"]
    assert legend["orient"] == orient
    # Top/bottom anchors should not get the vertical-stack smart default.
    assert "columns" not in legend


# -----------------------------------------------------------------------------
# tree_color_legend_show
# -----------------------------------------------------------------------------


def test_legend_show_default_true():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
    )
    encs = _tree_panel_color_encodings(out)
    # Legend object is present.
    assert encs[0].get("legend")


def test_legend_show_false_hides_legend():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        color_tree_by="subclade",
        tree_color_legend_show=False,
    )
    encs = _tree_panel_color_encodings(out)
    # Color encodings are still present (tree is colored), but `legend` on
    # each is null/missing — Altair drops the property when legend=None.
    assert encs
    for enc in encs:
        assert enc.get("legend") in (None, {}) or enc.get("legend") is None


# -----------------------------------------------------------------------------
# scale_bar_font_size
# -----------------------------------------------------------------------------


def _scale_bar_text_marks(out) -> list[dict]:
    """Return every `mark_text` block on the tree panel — the scale-bar text
    is the only text mark when connect_leader_to_label is off."""
    spec = out.to_dict()
    panels = spec.get("hconcat") or spec.get("vconcat") or []
    tree_panel = panels[0]
    hits: list[dict] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            mark = o.get("mark")
            if isinstance(mark, dict) and mark.get("type") == "text":
                hits.append(mark)
            elif mark == "text":
                hits.append({"type": "text"})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(tree_panel)
    return hits


def test_scale_bar_font_size_default_is_10():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        scale_bar=True,
    )
    text_marks = _scale_bar_text_marks(out)
    # At least one text mark with fontSize=10 (the scale-bar label).
    sizes = [m.get("fontSize") for m in text_marks if "fontSize" in m]
    assert 10 in sizes or 10.0 in sizes


def test_scale_bar_font_size_propagates():
    out = tree_annotated_plot.plot(
        _attr_auspice(),
        _vertical_chart(["A", "B", "C", "D"]),
        **_kw(),
        scale_bar=True,
        scale_bar_font_size=18.0,
    )
    text_marks = _scale_bar_text_marks(out)
    sizes = [m.get("fontSize") for m in text_marks if "fontSize" in m]
    assert 18.0 in sizes or 18 in sizes


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def test_cli_tree_color_scale(tmp_path):
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
            "--tree-color-scale",
            "Z=#111111,Y=#222222,X=#333333",
        ]
    )
    assert out_path.exists()
    spec = json.loads(out_path.read_text())
    encs = [
        enc
        for _, enc in _find_color_encodings(spec.get("hconcat", [{}])[0])
        if isinstance(enc, dict) and enc.get("field") == "color_value"
    ]
    assert encs
    scale = encs[0]["scale"]
    assert scale["domain"] == ["Z", "Y", "X"]
    assert scale["range"] == ["#111111", "#222222", "#333333"]


def test_cli_tree_color_scale_invalid_format(tmp_path):
    tree_path, chart_path, out_path = _cli_setup(
        tmp_path, _attr_auspice(), _vertical_chart(["A", "B", "C", "D"])
    )
    from click.testing import CliRunner

    from tree_annotated_plot import cli as cli_module

    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
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
            "--tree-color-scale",
            "Z#111111",  # missing '='
        ],
    )
    assert result.exit_code != 0
    assert "key=color" in (result.output or "") or "key=color" in (
        str(result.exception) if result.exception else ""
    )


def test_cli_legend_format_json(tmp_path):
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
            "--tree-color-legend-format",
            '{"orient": "right", "labelFontSize": 14, "titleFontSize": 14}',
        ]
    )
    spec = json.loads(out_path.read_text())
    encs = [
        enc
        for _, enc in _find_color_encodings(spec.get("hconcat", [{}])[0])
        if isinstance(enc, dict) and enc.get("field") == "color_value"
    ]
    assert encs
    legend = encs[0]["legend"]
    assert legend["orient"] == "right"
    assert legend["titleFontSize"] == 14
    assert legend["labelFontSize"] == 14
    # Smart default fired: side-anchored orient + no user columns/direction.
    assert legend["columns"] == 1


def test_cli_legend_format_invalid_json_errors(tmp_path):
    tree_path, chart_path, out_path = _cli_setup(
        tmp_path, _attr_auspice(), _vertical_chart(["A", "B", "C", "D"])
    )
    from click.testing import CliRunner

    from tree_annotated_plot import cli as cli_module

    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
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
            "--tree-color-legend-format",
            "{not valid json",
        ],
    )
    assert result.exit_code != 0


def test_cli_legend_format_non_object_errors(tmp_path):
    tree_path, chart_path, out_path = _cli_setup(
        tmp_path, _attr_auspice(), _vertical_chart(["A", "B", "C", "D"])
    )
    from click.testing import CliRunner

    from tree_annotated_plot import cli as cli_module

    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
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
            "--tree-color-legend-format",
            '["not", "an", "object"]',
        ],
    )
    assert result.exit_code != 0


def test_cli_no_tree_color_legend_show_hides_legend(tmp_path):
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
            "--no-tree-color-legend-show",
        ]
    )
    spec = json.loads(out_path.read_text())
    encs = [
        enc
        for _, enc in _find_color_encodings(spec.get("hconcat", [{}])[0])
        if isinstance(enc, dict) and enc.get("field") == "color_value"
    ]
    assert encs
    for enc in encs:
        assert enc.get("legend") in (None, {}) or enc.get("legend") is None


def test_cli_scale_bar_font_size(tmp_path):
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
            "--scale-bar",
            "--scale-bar-font-size",
            "16",
        ]
    )
    spec = json.loads(out_path.read_text())
    panels = spec.get("hconcat", [])
    tree_panel = panels[0] if panels else {}

    def collect_text_marks(o: Any, hits: list[dict]) -> None:
        if isinstance(o, dict):
            mark = o.get("mark")
            if isinstance(mark, dict) and mark.get("type") == "text":
                hits.append(mark)
            for v in o.values():
                collect_text_marks(v, hits)
        elif isinstance(o, list):
            for v in o:
                collect_text_marks(v, hits)

    text_marks: list[dict] = []
    collect_text_marks(tree_panel, text_marks)
    sizes = [m.get("fontSize") for m in text_marks if "fontSize" in m]
    assert 16.0 in sizes or 16 in sizes
