"""Tests for `strain_label_styles`: per-strain styling of the tree-panel labels."""

from __future__ import annotations

import json
import re

import altair as alt
import pandas as pd
import pytest
import vl_convert as vlc

import tree_annotated_plot
from tree_annotated_plot import _label_style

STRAINS = ["A", "B", "C", "D"]
RED = "#d62728"


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


def _chart(strain_axis: str = "y", strains: list[str] = STRAINS) -> alt.Chart:
    df = pd.DataFrame(
        {"strain": strains, "titer": [2.0**i for i in range(len(strains))]}
    )
    strain_enc = alt.Y("strain:N") if strain_axis == "y" else alt.X("strain:N")
    titer_enc = "titer:Q"
    enc = (
        {"y": strain_enc, "x": titer_enc}
        if strain_axis == "y"
        else {"x": strain_enc, "y": titer_enc}
    )
    return alt.Chart(df).mark_circle().encode(**enc).properties(width=200, height=200)


def _kw(**extra) -> dict:
    return dict(
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        connect_leader_to_label=True,
        **extra,
    )


def _checkbox(name: str = "hl", value: bool = True) -> alt.Parameter:
    return alt.param(name=name, value=value, bind=alt.binding_checkbox(name="hl "))


def _label_layers(spec: dict) -> tuple[dict, dict]:
    """Return the (halo, text) strain-label layers of the tree panel."""
    panels = spec.get("hconcat") or spec.get("vconcat")
    layers = [
        layer
        for panel in panels
        for layer in panel.get("layer", [])
        if isinstance(layer.get("mark"), dict)
        and layer["mark"].get("type") == "text"
        and layer.get("encoding", {}).get("text", {}).get("field") == "name"
    ]
    assert len(layers) == 2, f"expected halo + text label layers, got {len(layers)}"
    halo, text = layers
    assert halo["mark"]["fill"] == "white"
    return halo, text


def _rendered_labels(spec: dict) -> dict[str, dict[str, str]]:
    """Render `spec` to SVG and return each visible label's text attributes.

    The halo layer draws the same strings in white first; the visible text
    layer comes second, so later occurrences overwrite the halo's.
    """
    svg = vlc.vegalite_to_svg(spec)
    labels: dict[str, dict[str, str]] = {}
    for tag, text in re.findall(r"<text([^>]*)>([^<]*)</text>", svg):
        if text not in STRAINS or "graphics-symbol" not in tag:
            continue
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', tag))
        if attrs.get("fill") == "white":
            continue
        labels[text] = attrs
    assert set(labels) == set(STRAINS), f"labels rendered: {sorted(labels)}"
    return labels


def _bold_red(labels: dict[str, dict[str, str]]) -> list[str]:
    return sorted(
        s
        for s, a in labels.items()
        if a.get("font-weight") == "bold" and a.get("fill") == RED
    )


def _top_level_param_names(spec: dict) -> list[str]:
    return [p["name"] for p in spec.get("params", [])]


VACCINE_RULE = {"strains": ["A", "C"], "style": {"fill": RED, "fontWeight": "bold"}}


# ---------- static rules ----------


def test_static_rule_sets_expressions_on_label_layers() -> None:
    out = tree_annotated_plot.plot(
        _auspice(), _chart(), **_kw(strain_label_styles=[VACCINE_RULE])
    )
    halo, text = _label_layers(out.to_dict())
    # Visible text gets every styled property; the halo only the glyph-shape
    # one, keeping its white fill so it still masks the leader.
    assert set(text["mark"]["fill"]) == {"expr"}
    assert set(text["mark"]["fontWeight"]) == {"expr"}
    assert set(halo["mark"]["fontWeight"]) == {"expr"}
    assert halo["mark"]["fill"] == "white"
    assert text["mark"]["fontWeight"] == halo["mark"]["fontWeight"]


def test_static_rule_adds_membership_column() -> None:
    out = tree_annotated_plot.plot(
        _auspice(), _chart(), **_kw(strain_label_styles=[VACCINE_RULE])
    )
    spec = out.to_dict()
    _, text = _label_layers(spec)
    rows = spec["datasets"][text["data"]["name"]]
    column = _label_style.membership_column(0)
    assert {r["name"]: r[column] for r in rows} == {
        "A": True,
        "B": False,
        "C": True,
        "D": False,
    }


def test_static_rule_renders_styled_labels() -> None:
    out = tree_annotated_plot.plot(
        _auspice(), _chart(), **_kw(strain_label_styles=[VACCINE_RULE])
    )
    labels = _rendered_labels(out.to_dict())
    assert _bold_red(labels) == ["A", "C"]
    for s in ("B", "D"):
        assert labels[s]["font-weight"] == "normal"
        assert labels[s]["fill"] == "black"


def test_unstyled_font_weight_follows_global_setting() -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        **_kw(
            strain_label_font_weight="bold",
            strain_label_styles=[{"strains": ["A"], "style": {"fontWeight": "normal"}}],
        ),
    )
    labels = _rendered_labels(out.to_dict())
    assert labels["A"]["font-weight"] == "normal"
    assert all(labels[s]["font-weight"] == "bold" for s in ("B", "C", "D"))


def test_no_styles_leaves_label_marks_static() -> None:
    for styles in (None, []):
        out = tree_annotated_plot.plot(
            _auspice(), _chart(), **_kw(strain_label_styles=styles)
        )
        halo, text = _label_layers(out.to_dict())
        assert text["mark"]["fontWeight"] == "normal"
        assert "fill" not in text["mark"]
        assert halo["mark"]["fontWeight"] == "normal"


def test_overlapping_rules_combine_property_by_property() -> None:
    """A strain in two rules gets both styles; where both set the same
    property, the later rule wins."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        **_kw(
            strain_label_styles=[
                {"strains": ["A", "C"], "style": {"fill": RED, "fontWeight": "bold"}},
                {"strains": ["C", "D"], "style": {"fontStyle": "italic"}},
                {"strains": ["A"], "style": {"fill": "#1f77b4"}},
            ]
        ),
    )
    labels = _rendered_labels(out.to_dict())
    assert labels["A"]["fill"] == "#1f77b4"
    assert labels["A"]["font-weight"] == "bold"
    assert labels["A"]["font-style"] == "normal"
    assert labels["C"]["fill"] == RED
    assert labels["C"]["font-weight"] == "bold"
    assert labels["C"]["font-style"] == "italic"
    assert labels["D"]["font-style"] == "italic"
    assert labels["D"]["fill"] == "black"
    assert labels["B"] == {**labels["B"], "fill": "black", "font-style": "normal"}


def test_opacity_and_numeric_font_weight_render() -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        **_kw(
            strain_label_styles=[
                {"strains": ["B"], "style": {"opacity": 0.4, "fontWeight": 700}}
            ]
        ),
    )
    labels = _rendered_labels(out.to_dict())
    assert labels["B"]["opacity"] == "0.4"
    assert labels["B"]["font-weight"] == "700"


@pytest.mark.parametrize("strain_axis", ["y", "x"])
def test_both_layouts_with_scale_bar(strain_axis: str) -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(strain_axis),
        **_kw(scale_bar=True, strain_label_styles=[VACCINE_RULE]),
    )
    assert _bold_red(_rendered_labels(out.to_dict())) == ["A", "C"]


def test_strains_accept_any_iterable_of_strings() -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        **_kw(
            strain_label_styles=[
                {"strains": pd.Series(["A", "C"]), "style": VACCINE_RULE["style"]}
            ]
        ),
    )
    assert _bold_red(_rendered_labels(out.to_dict())) == ["A", "C"]


# ---------- `when` toggles ----------


@pytest.mark.parametrize("value", [True, False])
def test_when_parameter_is_declared_once_and_toggles(value: bool) -> None:
    hl = _checkbox(value=value)
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        **_kw(strain_label_styles=[{**VACCINE_RULE, "when": hl}]),
    )
    spec = out.to_dict()
    assert _top_level_param_names(spec) == ["hl"]
    assert _bold_red(_rendered_labels(spec)) == (["A", "C"] if value else [])


def test_when_parameter_already_on_chart_is_not_redeclared() -> None:
    hl = _checkbox()
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart().add_params(hl),
        **_kw(strain_label_styles=[{**VACCINE_RULE, "when": hl}]),
    )
    spec = out.to_dict()
    assert _top_level_param_names(spec).count("hl") == 1
    assert _bold_red(_rendered_labels(spec)) == ["A", "C"]


def test_when_shared_parameter_across_rules_declared_once() -> None:
    hl = _checkbox()
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(),
        **_kw(
            strain_label_styles=[
                {"strains": ["A"], "style": {"fill": RED}, "when": hl},
                {"strains": ["C"], "style": {"fontWeight": "bold"}, "when": "hl"},
            ]
        ),
    )
    assert _top_level_param_names(out.to_dict()) == ["hl"]


def test_when_name_of_chart_param_from_json_chart(tmp_path) -> None:
    """The CLI form: the param lives in the saved chart and `when` names it."""
    path = tmp_path / "chart.json"
    _chart().add_params(_checkbox(value=False)).save(str(path))
    out = tree_annotated_plot.plot(
        _auspice(),
        path,
        **_kw(strain_label_styles=[{**VACCINE_RULE, "when": "hl"}]),
    )
    spec = out.to_dict()
    assert _top_level_param_names(spec) == ["hl"]
    assert _bold_red(_rendered_labels(spec)) == []
    spec["params"][0]["value"] = True
    assert _bold_red(_rendered_labels(spec)) == ["A", "C"]


@pytest.mark.parametrize("emphasis, expected", [("cell", ["A"]), ("egg", ["C"])])
def test_when_expressions_drive_a_radio_param(emphasis, expected) -> None:
    emph = alt.param(
        name="emph",
        value=emphasis,
        bind=alt.binding_radio(options=["none", "cell", "egg"]),
    )
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart().add_params(emph),
        **_kw(
            strain_label_styles=[
                # A string expression and an altair parameter expression.
                {
                    "strains": ["A"],
                    "style": VACCINE_RULE["style"],
                    "when": "emph == 'cell'",
                },
                {
                    "strains": ["C"],
                    "style": VACCINE_RULE["style"],
                    "when": emph == "egg",
                },
            ]
        ),
    )
    assert _bold_red(_rendered_labels(out.to_dict())) == expected


def test_renested_output_keeps_single_param_and_renders() -> None:
    """Like flu-seqneut-2026's `finalize()`: the returned chart is nested in a
    further vconcat whose other panel declares params of its own."""
    hl = _checkbox()
    slider = alt.param(name="slider", value=1, bind=alt.binding_range(min=0, max=2))
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart("x"),
        **_kw(strain_label_styles=[{**VACCINE_RULE, "when": hl}]),
    )
    readout = (
        alt.Chart(pd.DataFrame({"row": [0]}))
        .add_params(slider)
        .mark_text()
        .encode(text=alt.value("readout"))
        .properties(width=100, height=14)
    )
    spec = alt.vconcat(readout, out).to_dict()
    assert sorted(_top_level_param_names(spec)) == ["hl", "slider"]
    assert _bold_red(_rendered_labels(spec)) == ["A", "C"]


def test_when_undeclared_name_raises() -> None:
    with pytest.raises(ValueError, match="names no parameter declared"):
        tree_annotated_plot.plot(
            _auspice(),
            _chart(),
            **_kw(strain_label_styles=[{**VACCINE_RULE, "when": "nope"}]),
        )


def test_when_selection_parameter_object_raises() -> None:
    sel = alt.selection_point(name="sel", fields=["strain"])
    with pytest.raises(ValueError, match="selection parameter"):
        tree_annotated_plot.plot(
            _auspice(),
            _chart().add_params(sel),
            **_kw(strain_label_styles=[{**VACCINE_RULE, "when": sel}]),
        )


def test_when_selection_parameter_name_raises() -> None:
    sel = alt.selection_point(name="sel", fields=["strain"])
    with pytest.raises(ValueError, match="selection parameter"):
        tree_annotated_plot.plot(
            _auspice(),
            _chart().add_params(sel),
            **_kw(strain_label_styles=[{**VACCINE_RULE, "when": "sel"}]),
        )


@pytest.mark.parametrize("when", ["", "   ", 3, ["hl"]])
def test_when_bad_value_raises(when) -> None:
    with pytest.raises(ValueError, match=r'\["when"\]'):
        tree_annotated_plot.plot(
            _auspice(),
            _chart().add_params(_checkbox()),
            **_kw(strain_label_styles=[{**VACCINE_RULE, "when": when}]),
        )


# ---------- strains ----------


def test_unknown_strain_raises_with_samples() -> None:
    with pytest.raises(ValueError) as exc:
        tree_annotated_plot.plot(
            _auspice(),
            _chart(),
            **_kw(
                strain_label_styles=[{"strains": ["A", "Z"], "style": {"fill": RED}}]
            ),
        )
    msg = str(exc.value)
    assert "not tips of the tree" in msg
    assert "'Z'" in msg
    assert "Sample tree tips" in msg and "'A'" in msg


def test_strain_pruned_from_tree_is_skipped() -> None:
    """D is a tree tip but not in the chart, so `prune_tree_to_chart` drops it;
    styling it is not an error."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _chart(strains=["A", "B", "C"]),
        **_kw(
            prune_tree_to_chart=True,
            strain_label_styles=[{"strains": ["A", "D"], "style": {"fill": RED}}],
        ),
    )
    spec = out.to_dict()
    _, text = _label_layers(spec)
    rows = spec["datasets"][text["data"]["name"]]
    column = _label_style.membership_column(0)
    assert {r["name"]: r[column] for r in rows} == {"A": True, "B": False, "C": False}


@pytest.mark.parametrize(
    "strains, match",
    [
        ("A", "must be a list of strain names"),
        ({"A": 1}, "must be a list of strain names"),
        ([], "is empty"),
        (["A", 3], "must contain strings"),
    ],
)
def test_bad_strains_raise(strains, match) -> None:
    with pytest.raises(ValueError, match=match):
        tree_annotated_plot.plot(
            _auspice(),
            _chart(),
            **_kw(strain_label_styles=[{"strains": strains, "style": {"fill": RED}}]),
        )


# ---------- style ----------


@pytest.mark.parametrize(
    "style, match",
    [
        ({}, "non-empty dict"),
        ("bold", "non-empty dict"),
        ({"color": RED}, 'use "fill"'),
        ({"fontSize": 12}, "strain_label_font_size"),
        ({"strokeWidth": 2}, "unsupported key"),
        ({"fill": ""}, "non-empty color string"),
        ({"opacity": 1.5}, "number from 0 to 1"),
        ({"opacity": True}, "number from 0 to 1"),
        ({"fontWeight": "heavy"}, "fontWeight"),
        ({"fontWeight": 750}, "fontWeight"),
        ({"fontStyle": "oblique"}, "fontStyle"),
    ],
)
def test_bad_style_raises(style, match) -> None:
    with pytest.raises(ValueError, match=match):
        tree_annotated_plot.plot(
            _auspice(),
            _chart(),
            **_kw(strain_label_styles=[{"strains": ["A"], "style": style}]),
        )


# ---------- rule shape ----------


@pytest.mark.parametrize(
    "styles, match",
    [
        ({"strains": ["A"], "style": {"fill": RED}}, "must be a list of rule dicts"),
        (["A"], r"strain_label_styles\[0\] must be a dict"),
        ([{"style": {"fill": RED}}], "missing the required 'strains'"),
        ([{"strains": ["A"]}], "missing the required 'style'"),
        ([{"strains": ["A"], "style": {"fill": RED}, "param": "hl"}], "unknown key"),
    ],
)
def test_bad_rule_shape_raises(styles, match) -> None:
    with pytest.raises(ValueError, match=match):
        tree_annotated_plot.plot(
            _auspice(), _chart(), **_kw(strain_label_styles=styles)
        )


def test_requires_connect_leader_to_label() -> None:
    kw = _kw(strain_label_styles=[VACCINE_RULE])
    kw["connect_leader_to_label"] = False
    with pytest.raises(ValueError, match="connect_leader_to_label=True"):
        tree_annotated_plot.plot(_auspice(), _chart(), **kw)


# ---------- CLI ----------


def _cli(tmp_path, chart: alt.Chart, styles_arg: str):
    from click.testing import CliRunner

    from tree_annotated_plot import cli as cli_module

    tree_path = tmp_path / "tree.json"
    chart_path = tmp_path / "chart.json"
    out_path = tmp_path / "out.json"
    tree_path.write_text(json.dumps(_auspice()))
    chart.save(str(chart_path))
    result = CliRunner().invoke(
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
            "--connect-leader-to-label",
            "--strain-label-styles",
            styles_arg,
        ],
    )
    return result, out_path


def test_cli_strain_label_styles_with_chart_param(tmp_path) -> None:
    rule = {**VACCINE_RULE, "when": "hl"}
    result, out_path = _cli(
        tmp_path, _chart().add_params(_checkbox()), json.dumps([rule])
    )
    assert result.exit_code == 0, result.output
    spec = json.loads(out_path.read_text())
    assert _top_level_param_names(spec) == ["hl"]
    assert _bold_red(_rendered_labels(spec)) == ["A", "C"]


@pytest.mark.parametrize(
    "arg, match",
    [
        ("[{not json", "invalid JSON"),
        (json.dumps(VACCINE_RULE), "expected a JSON array of objects"),
        ('["A"]', "element 0 is str"),
    ],
)
def test_cli_strain_label_styles_bad_json(tmp_path, arg, match) -> None:
    result, _ = _cli(tmp_path, _chart(), arg)
    assert result.exit_code != 0
    assert match in result.output
