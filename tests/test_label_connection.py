"""Tests for `connect_leader_to_label` and the strain-label font knobs."""

from __future__ import annotations

from typing import Any

import altair as alt
import pandas as pd
import pytest

import tree_annotated_plot


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
    """Required kwargs only — `connect_leader_to_label` defaults to off."""
    return dict(
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
    )


def _on_kw():
    """Required kwargs plus `connect_leader_to_label=True`."""
    return dict(_kw(), connect_leader_to_label=True)


def _references_strain(node: Any) -> bool:
    """Recursively check whether `node` has any encoding referencing the
    `"strain"` field on `x` or `y` (i.e. it's the user's chart panel)."""
    if isinstance(node, dict):
        enc = node.get("encoding")
        if isinstance(enc, dict):
            for ch in ("x", "y"):
                chdef = enc.get(ch, {})
                if isinstance(chdef, dict) and chdef.get("field") == "strain":
                    return True
        for v in node.values():
            if _references_strain(v):
                return True
    elif isinstance(node, list):
        for v in node:
            if _references_strain(v):
                return True
    return False


def _is_tree_panel(panel: dict) -> bool:
    """The tree panel is the one that does NOT reference the strain field
    on its x/y encoding (its layers encode the layout-internal x:Q / y:Q
    quantitative fields). The user's chart panel references the strain
    field somewhere on x or y."""
    return not _references_strain(panel)


def _tree_panel(out: alt.HConcatChart | alt.VConcatChart) -> dict:
    d = out.to_dict()
    panels = d.get("hconcat") or d.get("vconcat")
    assert panels, "expected hconcat or vconcat output"
    for panel in panels:
        if _is_tree_panel(panel):
            return panel
    raise AssertionError("no tree panel found")


def _chart_panel(out: alt.HConcatChart | alt.VConcatChart) -> dict:
    d = out.to_dict()
    panels = d.get("hconcat") or d.get("vconcat")
    assert panels, "expected hconcat or vconcat output"
    for panel in panels:
        if not _is_tree_panel(panel):
            return panel
    raise AssertionError("no chart panel found")


def _tree_layers(out: alt.HConcatChart | alt.VConcatChart) -> list[dict]:
    return _tree_panel(out)["layer"]


def _strain_text_layers(out: alt.HConcatChart | alt.VConcatChart) -> list[dict]:
    """Return all strain-label text layers (those whose `text` encoding
    references `name`). With `connect_leader_to_label=True` there are two:
    a white-halo shadow layer drawn first, then the visible black text."""
    out_layers = []
    for layer in _tree_layers(out):
        mark = layer.get("mark")
        if isinstance(mark, dict) and mark.get("type") == "text":
            enc = layer.get("encoding", {})
            text_def = enc.get("text", {})
            if isinstance(text_def, dict) and text_def.get("field") == "name":
                out_layers.append(layer)
    return out_layers


def _text_layer(out: alt.HConcatChart | alt.VConcatChart) -> dict | None:
    """Return the visible strain-label text layer (the second of the two
    stacked text layers, i.e. the one *without* white fill/stroke). Returns
    None if `connect_leader_to_label` is off."""
    for layer in _strain_text_layers(out):
        mark = layer["mark"]
        if mark.get("fill") != "white":
            return layer
    return None


def _halo_text_layer(out: alt.HConcatChart | alt.VConcatChart) -> dict | None:
    """Return the white-halo shadow text layer (white fill + white stroke)."""
    for layer in _strain_text_layers(out):
        mark = layer["mark"]
        if mark.get("fill") == "white" and mark.get("stroke") == "white":
            return layer
    return None


def _leader_layer(out: alt.HConcatChart | alt.VConcatChart) -> dict:
    """The dashed-rule leader layer."""
    matches = [
        layer
        for layer in _tree_layers(out)
        if isinstance(layer.get("mark"), dict)
        and layer["mark"].get("type") == "rule"
        and "strokeDash" in layer["mark"]
    ]
    assert len(matches) == 1, f"expected exactly one leader layer, got {len(matches)}"
    return matches[0]


def _resolve_dataset(out_dict: dict, layer: dict) -> list[dict]:
    """Return inline rows for `layer`'s data — either layer.data.values or
    the named dataset that altair hoists to the top-level `datasets` block."""
    data = layer.get("data") or {}
    if "values" in data and isinstance(data["values"], list):
        return data["values"]
    name = data.get("name")
    rows = out_dict.get("datasets", {}).get(name, [])
    assert isinstance(rows, list), f"dataset {name!r} not a list"
    return rows


# ---------- chart-axis suppression ----------


def test_on_suppresses_chart_strain_axis() -> None:
    """Setting `connect_leader_to_label=True` hides labels/ticks/domain/title
    on the chart's strain-axis encoding."""
    out = tree_annotated_plot.plot(_auspice(), _vertical_chart(), **_on_kw())
    enc = _chart_panel(out)["encoding"]["y"]
    axis = enc.get("axis")
    assert isinstance(axis, dict), f"expected an axis dict, got {axis!r}"
    assert axis.get("labels") is False
    assert axis.get("ticks") is False
    assert axis.get("domain") is False
    assert axis.get("title") is None


def test_default_off_keeps_chart_strain_axis_untouched() -> None:
    """The default (`connect_leader_to_label=False`) leaves the chart's
    strain encoding exactly as the user wrote it — no suppressed-axis
    block is injected."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _vertical_chart(),
        **_kw(),
    )
    enc = _chart_panel(out)["encoding"]["y"]
    # User's _vertical_chart() didn't pass a custom axis, so no axis dict
    # should be present at all (or at least none with our suppression keys).
    if "axis" in enc:
        axis = enc["axis"]
        assert axis.get("labels") is not False
        assert axis.get("ticks") is not False


def test_default_off_keeps_horizontal_strain_axis_untouched() -> None:
    """Same check, horizontal layout."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _horizontal_chart(),
        **_kw(),
    )
    enc = _chart_panel(out)["encoding"]["x"]
    if "axis" in enc:
        axis = enc["axis"]
        assert axis.get("labels") is not False


# ---------- tree-panel text layer ----------


def test_on_adds_text_layer_to_tree_panel() -> None:
    """When on, the tree panel gains a text layer whose `text` encoding
    is the strain name."""
    out = tree_annotated_plot.plot(_auspice(), _vertical_chart(), **_on_kw())
    text = _text_layer(out)
    assert text is not None, "expected a strain-label text layer"
    assert text["mark"]["type"] == "text"
    assert text["encoding"]["text"]["field"] == "name"


def test_default_off_does_not_add_text_layer() -> None:
    """The default (off) leaves the tree panel with no `text` mark."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _vertical_chart(),
        **_kw(),
    )
    assert _text_layer(out) is None
    # Only the three default layers (leaders + branches + tip-circles).
    assert len(_tree_layers(out)) == 3


# ---------- leader endpoint extension ----------


def test_leaders_share_chart_edge_endpoint_when_on() -> None:
    """With `connect_leader_to_label=True`, every leader extends to the
    same `chart_edge_branch` (a single shared endpoint past `branch_max`).
    A white halo around each rendered text label masks the leader behind
    each glyph — but in the underlying data every leader's `x2` is the
    same."""
    out = tree_annotated_plot.plot(_auspice(), _vertical_chart(), **_on_kw())
    leader = _leader_layer(out)
    rows = _resolve_dataset(out.to_dict(), leader)
    branch_max = 0.06
    x2_values = {row["x2"] for row in rows}
    assert len(x2_values) == 1, f"expected one shared x2 value, got {x2_values}"
    (x2,) = x2_values
    assert x2 > branch_max + 1e-9, f"expected x2 > branch_max ({branch_max}), got {x2}"


def test_default_leader_endpoint_stops_at_branch_max() -> None:
    """The default (off) leaves leaders stopping at branch_max (the prior
    behavior)."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _vertical_chart(),
        **_kw(),
    )
    leader = _leader_layer(out)
    rows = _resolve_dataset(out.to_dict(), leader)
    branch_max = 0.06
    for row in rows:
        assert row["x2"] == pytest.approx(branch_max)


# ---------- side-of-panel placement ----------


def test_vertical_left_renders_text_with_right_align() -> None:
    """Vertical layout with `connect_leader_to_label=True` and default
    `tree_location="left"`: tree on left, chart on right; labels flush
    against the chart on the panel's right (chart-facing) edge. Text
    mark uses `align="right"` and `x_label > branch_max`."""
    out = tree_annotated_plot.plot(_auspice(), _vertical_chart(), **_on_kw())
    text = _text_layer(out)
    assert text is not None
    assert text["mark"].get("align") == "right"
    rows = _resolve_dataset(out.to_dict(), text)
    branch_max = 0.06
    for row in rows:
        assert row["x_label"] > branch_max


def test_vertical_right_renders_text_with_left_align() -> None:
    """Vertical layout, `tree_location="right"`: tree on right, chart on
    left; labels are flush against the chart on the panel's left
    (chart-facing) edge. Text mark uses `align="left"`; `x_label` still
    extends past `branch_max` because the panel was widened in the
    branch-max direction; chart's natural left-side strain axis is still
    suppressed."""
    out = tree_annotated_plot.plot(
        _auspice(), _vertical_chart(), tree_location="right", **_on_kw()
    )
    text = _text_layer(out)
    assert text is not None
    assert text["mark"].get("align") == "left"
    rows = _resolve_dataset(out.to_dict(), text)
    branch_max = 0.06
    for row in rows:
        assert row["x_label"] > branch_max
    # Chart's natural left-side strain axis labels are still suppressed.
    enc = _chart_panel(out)["encoding"]["y"]
    axis = enc.get("axis")
    assert isinstance(axis, dict)
    assert axis.get("labels") is False
    assert axis.get("ticks") is False


# ---------- horizontal layout ----------


def test_horizontal_bottom_uses_right_align_and_270() -> None:
    """Horizontal layout with `connect_leader_to_label=True` and default
    `tree_location="bottom"`: tree below chart; labels flush against the
    chart on the panel's top (chart-facing) edge. With `angle=270` (text
    reads bottom-to-top), `align="right"` anchors the post-rotation top
    of the text at the panel's top, so labels extend downward from the
    chart."""
    out = tree_annotated_plot.plot(_auspice(), _horizontal_chart(), **_on_kw())
    text = _text_layer(out)
    assert text is not None
    assert text["mark"].get("angle") == 270
    assert text["mark"].get("align") == "right"


def test_horizontal_top_uses_left_align_and_270() -> None:
    """Horizontal layout, `tree_location="top"`: tree above chart;
    labels are flush against the chart on the panel's bottom (chart-facing)
    edge. With `angle=270`, `align="left"` anchors the post-rotation
    bottom of the text at the panel's bottom, so labels extend upward
    from the chart."""
    out = tree_annotated_plot.plot(
        _auspice(), _horizontal_chart(), tree_location="top", **_on_kw()
    )
    text = _text_layer(out)
    assert text is not None
    assert text["mark"].get("angle") == 270
    assert text["mark"].get("align") == "left"


# ---------- font knobs ----------


def test_strain_label_font_size_and_weight_propagate() -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _vertical_chart(),
        strain_label_font_size=14,
        strain_label_font_weight="bold",
        **_on_kw(),
    )
    text = _text_layer(out)
    assert text is not None
    assert text["mark"].get("fontSize") == 14
    assert text["mark"].get("fontWeight") == "bold"


def test_strain_label_font_weight_invalid_raises() -> None:
    """`strain_label_font_weight` is a Literal["normal","bold"]; an invalid
    value should fail (in practice altair's schema-validation rejects it
    when constructing the text mark)."""
    with pytest.raises(Exception, match="(?i)fontweight|heavy"):
        tree_annotated_plot.plot(
            _auspice(),
            _vertical_chart(),
            strain_label_font_weight="heavy",  # type: ignore[arg-type]
            **_on_kw(),
        )


# ---------- multi-encoding case ----------


def test_layered_chart_suppresses_every_strain_encoding() -> None:
    """If the user's chart references the strain field on multiple
    sub-encodings (e.g. layered LayerChart), every match should be
    suppressed — same walker pattern as `_walk_and_apply_sort`."""
    df = pd.DataFrame({"strain": ["A", "B", "C", "D"], "titer": [1.0, 2.0, 4.0, 8.0]})
    base = alt.Chart(df).encode(y=alt.Y("strain:N"), x="titer:Q")
    layered = (base.mark_circle() + base.mark_line()).properties(width=200, height=200)
    out = tree_annotated_plot.plot(_auspice(), layered, **_on_kw())
    chart_panel = _chart_panel(out)
    # Each layer's y encoding should be suppressed.
    found_axes: list[Any] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            enc = node.get("encoding")
            if isinstance(enc, dict):
                y = enc.get("y")
                if isinstance(y, dict) and y.get("field") == "strain":
                    found_axes.append(y.get("axis"))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(chart_panel)
    assert found_axes, "expected at least one strain encoding in chart panel"
    for axis in found_axes:
        assert isinstance(axis, dict), f"expected suppressed axis dict, got {axis!r}"
        assert axis.get("labels") is False
        assert axis.get("ticks") is False


# ---------- white-halo shadow text layer (leader mask) ----------


def test_on_adds_halo_text_layer() -> None:
    """When on, a white-halo shadow `mark_text` (white fill + thick white
    stroke, `strokeJoin="round"` for smooth glyph corners) is drawn under
    the visible label, auto-sized to the rendered glyphs."""
    out = tree_annotated_plot.plot(_auspice(), _vertical_chart(), **_on_kw())
    halo = _halo_text_layer(out)
    assert halo is not None, "expected a halo (shadow) text layer"
    mark = halo["mark"]
    assert mark.get("fill") == "white"
    assert mark.get("stroke") == "white"
    assert mark.get("strokeJoin") == "round"
    # strokeWidth scales with font_size; default 10 pt × 0.6 ratio → 6.0.
    assert mark.get("strokeWidth") >= 5


def test_halo_strokeWidth_scales_with_font_size() -> None:
    out_small = tree_annotated_plot.plot(
        _auspice(), _vertical_chart(), strain_label_font_size=8, **_on_kw()
    )
    out_large = tree_annotated_plot.plot(
        _auspice(), _vertical_chart(), strain_label_font_size=20, **_on_kw()
    )
    sw_small = _halo_text_layer(out_small)["mark"]["strokeWidth"]
    sw_large = _halo_text_layer(out_large)["mark"]["strokeWidth"]
    assert sw_large > sw_small


def test_default_off_does_not_add_halo_layer() -> None:
    out = tree_annotated_plot.plot(
        _auspice(),
        _vertical_chart(),
        **_kw(),
    )
    assert _halo_text_layer(out) is None
    assert _strain_text_layers(out) == []


def test_halo_layer_drawn_before_visible_text() -> None:
    """The halo (white-fill + white-stroke) shadow must come BEFORE the
    visible black text in the layer list, so the visible text draws on
    top of the halo."""
    out = tree_annotated_plot.plot(_auspice(), _vertical_chart(), **_on_kw())
    layers = _tree_layers(out)
    halo_idx = next(
        i
        for i, layer in enumerate(layers)
        if isinstance(layer.get("mark"), dict)
        and layer["mark"].get("type") == "text"
        and layer["mark"].get("fill") == "white"
        and layer["mark"].get("stroke") == "white"
    )
    visible_idx = next(
        i
        for i, layer in enumerate(layers)
        if isinstance(layer.get("mark"), dict)
        and layer["mark"].get("type") == "text"
        and layer["mark"].get("fill") != "white"
        and layer.get("encoding", {}).get("text", {}).get("field") == "name"
    )
    assert halo_idx < visible_idx, "halo shadow must be drawn before the visible text"


# ---------- shift_tree_loc ----------


def test_shift_tree_loc_shrinks_panel() -> None:
    """Positive `shift_tree_loc` reduces the label strip's pixel width, so
    the tree panel is narrower."""
    out_zero = tree_annotated_plot.plot(
        _auspice(), _vertical_chart(), shift_tree_loc=0, **_on_kw()
    )
    out_shift = tree_annotated_plot.plot(
        _auspice(), _vertical_chart(), shift_tree_loc=2, **_on_kw()
    )
    w_zero = _tree_panel(out_zero)["width"]
    w_shift = _tree_panel(out_shift)["width"]
    assert w_shift == pytest.approx(w_zero - 2)


def test_shift_tree_loc_too_large_raises() -> None:
    """A `shift_tree_loc` that would erase the entire label strip is a
    fail-fast error (per CLAUDE.md)."""
    with pytest.raises(ValueError, match="eliminates the label strip"):
        tree_annotated_plot.plot(
            _auspice(),
            _vertical_chart(),
            shift_tree_loc=999,
            **_on_kw(),
        )


def test_shift_tree_loc_no_effect_when_off() -> None:
    """When `connect_leader_to_label=False` (the default), `shift_tree_loc`
    is ignored — there's no label strip to shrink."""
    out = tree_annotated_plot.plot(
        _auspice(),
        _vertical_chart(),
        shift_tree_loc=50,
        **_kw(),
    )
    # tree panel width == tree_size (default 100); no strip, no shift effect.
    assert _tree_panel(out)["width"] == 100


# ---------- default (off) keeps user's chart axis ----------


def test_default_off_keeps_user_axis_labels_intact() -> None:
    """The default (`connect_leader_to_label=False`) preserves the user's
    strain-axis encoding untouched — no suppressed `axis` dict is injected.
    This is the documented contract."""
    df = pd.DataFrame({"strain": ["A", "B", "C", "D"], "titer": [1.0, 2.0, 4.0, 8.0]})
    user_axis = alt.Axis(title="Strain ID", labelFontWeight="bold")
    chart = (
        alt.Chart(df)
        .mark_circle()
        .encode(x="titer:Q", y=alt.Y("strain:N", axis=user_axis))
        .properties(width=200, height=200)
    )
    out = tree_annotated_plot.plot(
        _auspice(),
        chart,
        **_kw(),
    )
    enc = _chart_panel(out)["encoding"]["y"]
    axis = enc.get("axis")
    assert axis is not None
    # user's axis intact: title and labelFontWeight preserved; we did NOT
    # set labels=False / ticks=False / domain=False.
    assert axis.get("title") == "Strain ID"
    assert axis.get("labelFontWeight") == "bold"
    assert axis.get("labels") is not False
    assert axis.get("ticks") is not False
