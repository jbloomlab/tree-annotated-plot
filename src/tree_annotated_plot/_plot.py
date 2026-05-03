"""Build the tree-annotated chart by introspecting and extending a user's Altair chart."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd

from . import _tree

# Type for an axis hit found by _find_strain_encoding: (path, encoding_dict, channel).
# `path` is a tuple of dict keys / list indices that locates `encoding_dict`
# inside the spec, ending with ("encoding", channel).
_AxisHit = tuple[tuple, dict, str]


def plot(
    tree: str | Path | dict | _tree.TreeNode,
    chart: alt.TopLevelMixin,
    *,
    chart_strain_field: str,
    tree_strain_field: str,
    tree_width: int = 100,
) -> alt.HConcatChart:
    """Return an Altair chart with a phylogenetic tree drawn alongside `chart`.

    The chart's strain-axis sort is overridden to match the tree's tip order
    (the headline behavior of this package).

    Parameters
    ----------
    tree
        Auspice JSON path, dict, or a pre-parsed :class:`TreeNode`. If a path
        or dict, it is parsed with the same `tree_strain_field` value.
    chart
        An Altair chart whose strain encoding (on `x` or `y`) references
        `chart_strain_field`. May be a `Chart`, `LayerChart`, `FacetChart`,
        `HConcatChart`, `VConcatChart`, or `ConcatChart`. The strain encoding
        may also appear on secondary channels (color, tooltip, etc.) — those
        are passed through untouched.
    chart_strain_field
        Required. The data-column name the chart's strain axis encodes (e.g.
        `"strain"` or `"axis_label"`).
    tree_strain_field
        Required. Where on each tree tip to find the strain identifier. The
        literal string `"name"` selects the top-level Auspice node `name`
        field; any other value `X` selects `node_attrs[X]` (auto-unwrapping
        the Auspice `{"value": ...}` convention). Dotted paths are not
        accepted.
    tree_width
        Width in pixels of the tree panel.

    Returns
    -------
    altair.HConcatChart
        Tree on the left, user's chart on the right (vertical strain layout).
        Horizontal layout (strain on x → tree on top) is added in a later
        phase.
    """
    root = _ensure_tree(tree, tree_strain_field)
    tip_list = _tree.layout(root)
    tip_names = [t.name for t in tip_list]

    spec = chart.to_dict() if isinstance(chart, alt.TopLevelMixin) else dict(chart)

    axis_hits = _find_strain_encoding(spec, chart_strain_field)
    axis = axis_hits[0][2]

    if axis != "y":
        raise NotImplementedError(
            f"chart_strain_field={chart_strain_field!r} is encoded on the "
            f"{axis!r} channel; only 'y' (vertical strain layout, tree on the "
            "left) is supported in this version. Horizontal layout (strain on "
            "x → tree on top) is coming in a later phase."
        )

    chart_strains = _extract_chart_strains(spec, axis_hits, chart_strain_field)
    _check_strain_match(tip_names, chart_strains)

    height = _coerce_dim(_chart_strain_dim(spec, axis_hits, axis))
    tree_chart = _build_tree_chart(
        root, n_tips=len(tip_names), width=tree_width, height=height
    )

    new_chart = _apply_tree_order_to_chart_object(chart, chart_strain_field, tip_names)
    hoisted_config, hoisted_other = _pop_toplevel_only_attrs(new_chart)

    combined = alt.hconcat(tree_chart, new_chart, spacing=0).resolve_scale(
        y="independent"
    )
    _apply_combined_config(combined, hoisted_config)
    for k, v in hoisted_other.items():
        combined._kwds[k] = v
    return combined


def _ensure_tree(
    tree: str | Path | dict | _tree.TreeNode,
    tree_strain_field: str,
) -> _tree.TreeNode:
    if isinstance(tree, _tree.TreeNode):
        return tree
    return _tree.load_auspice(tree, tree_strain_field=tree_strain_field)


# ---------- chart spec introspection ----------


def _walk_strain_encodings(spec: Any, chart_strain_field: str) -> list[_AxisHit]:
    """Return every encoding referencing `chart_strain_field` in the spec.

    Walks vconcat/hconcat/concat/facet.spec/layer recursively. Each hit is
    (path, encoding_dict, channel). Path is a tuple of dict keys and list
    indices ending with ("encoding", channel) so the same path on the deepcopy
    locates the same encoding for in-place modification.
    """
    hits: list[_AxisHit] = []

    def walk(node: Any, path: tuple) -> None:
        if isinstance(node, dict):
            enc = node.get("encoding")
            if isinstance(enc, dict):
                for channel, enc_def in enc.items():
                    if (
                        isinstance(enc_def, dict)
                        and enc_def.get("field") == chart_strain_field
                    ):
                        hits.append((path + ("encoding", channel), enc_def, channel))
                    elif isinstance(enc_def, list):
                        # Some channels (notably `tooltip`) carry a list of
                        # field definitions. Walk each.
                        for i, item in enumerate(enc_def):
                            if (
                                isinstance(item, dict)
                                and item.get("field") == chart_strain_field
                            ):
                                hits.append(
                                    (path + ("encoding", channel, i), item, channel)
                                )
            for k, v in node.items():
                # `encoding` already inspected; `data`/`datasets`/`config`
                # don't contain encodings.
                if k in ("encoding", "data", "datasets", "config"):
                    continue
                walk(v, path + (k,))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, path + (i,))

    walk(spec, ())
    return hits


def _find_strain_encoding(spec: dict, chart_strain_field: str) -> list[_AxisHit]:
    """Walk the spec, validate, and return only the axis (x/y) hits.

    Validates:
      1. At least one axis hit exists.
      2. All axis hits agree on the same channel ('x' or 'y').
      3. Each axis hit's encoding type is 'nominal' or 'ordinal'.
    Secondary hits (color, tooltip, detail, etc.) are allowed and ignored.
    """
    all_hits = _walk_strain_encodings(spec, chart_strain_field)

    axis_hits = [h for h in all_hits if h[2] in ("x", "y")]
    secondary_hits = [h for h in all_hits if h[2] not in ("x", "y")]

    if not axis_hits:
        if secondary_hits:
            channels = sorted({h[2] for h in secondary_hits})
            raise ValueError(
                f"chart_strain_field={chart_strain_field!r} is encoded on "
                f"{channels} but not on 'x' or 'y'; tree alignment requires "
                "the strain to be on an axis channel."
            )
        raise ValueError(
            f"chart_strain_field={chart_strain_field!r} not found in any "
            "encoding of the chart spec. Confirm the field name and that the "
            "chart has an 'x' or 'y' encoding referencing it."
        )

    axes = {h[2] for h in axis_hits}
    if len(axes) > 1:
        raise ValueError(
            f"chart_strain_field={chart_strain_field!r} is encoded on both "
            f"{sorted(axes)} channels (across layers/panels). The alignment "
            "axis is ambiguous; the chart must encode the strain on exactly "
            "one of x or y."
        )

    for _, enc, channel in axis_hits:
        t = enc.get("type")
        if t not in ("nominal", "ordinal"):
            raise ValueError(
                f"chart_strain_field={chart_strain_field!r} on the {channel!r} "
                f"channel has type={t!r}; expected 'nominal' or 'ordinal' so "
                "each strain value collapses onto exactly one axis row."
            )

    return axis_hits


def _extract_chart_strains(
    spec: dict, axis_hits: list[_AxisHit], chart_strain_field: str
) -> list[str]:
    """Return the chart's distinct strain values.

    Prefers an explicit `sort` on the first axis hit. Falls back to walking
    the spec's data (inline values or named datasets). Refuses URL data.
    """
    for _, enc, _ in axis_hits:
        sort = enc.get("sort")
        if isinstance(sort, list) and sort:
            return list(sort)

    return _extract_field_values_from_spec_data(spec, chart_strain_field)


def _extract_field_values_from_spec_data(spec: dict, field: str) -> list[str]:
    """Walk spec for inline / named data and return distinct values of `field`.

    Refuses URL data with a clear message: synchronous fetches at plot time
    are out of scope.
    """
    datasets = spec.get("datasets", {}) if isinstance(spec, dict) else {}
    seen: list[Any] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            data = node.get("data")
            if isinstance(data, dict):
                if "url" in data:
                    raise ValueError(
                        f"chart references data via URL ({data['url']!r}); "
                        "URL data is not supported. Materialize the data inline "
                        "(via alt.Chart(df) with a pandas DataFrame) before "
                        "saving the chart."
                    )
                if "values" in data and isinstance(data["values"], list):
                    for row in data["values"]:
                        if isinstance(row, dict) and field in row:
                            seen.append(row[field])
                elif "name" in data:
                    name = data["name"]
                    rows = datasets.get(name)
                    if isinstance(rows, list):
                        for row in rows:
                            if isinstance(row, dict) and field in row:
                                seen.append(row[field])
            for k, v in node.items():
                if k in ("data", "datasets"):
                    continue
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return list(dict.fromkeys(seen))


def _check_strain_match(tip_names: list[str], chart_strains: list[str]) -> None:
    tip_set = set(tip_names)
    chart_set = set(chart_strains)
    missing_in_chart = tip_set - chart_set
    missing_in_tree = chart_set - tip_set
    if missing_in_chart or missing_in_tree:
        raise ValueError(
            "strain set mismatch between tree tips and chart strains:\n"
            f"  tips not in chart ({len(missing_in_chart)}): "
            f"{sorted(missing_in_chart)[:10]}\n"
            f"  chart strains not in tree ({len(missing_in_tree)}): "
            f"{sorted(missing_in_tree)[:10]}"
        )


def _apply_tree_order_to_chart_object(
    chart: alt.TopLevelMixin, chart_strain_field: str, sort_order: list[str]
) -> alt.TopLevelMixin:
    """Return a deepcopy of the user's chart with `sort=sort_order` applied
    to every axis encoding that references `chart_strain_field`.

    Walks the live altair object tree (Chart / LayerChart / FacetChart /
    HConcatChart / VConcatChart / ConcatChart) rather than its dict form,
    because altair's to_dict / from_dict round-trip introduces internal
    annotations (e.g. params[].views) and class-dispatch issues that the
    dict approach has to fight. Modifying the object in place is robust as
    long as altair's container attribute names hold (.hconcat / .vconcat /
    .concat / .layer / .spec / .encoding), which is stable in altair 5+.
    """
    new_chart = copy.deepcopy(chart)
    _walk_and_apply_sort(new_chart, chart_strain_field, sort_order)
    return new_chart


def _walk_and_apply_sort(
    node: Any, chart_strain_field: str, sort_order: list[str]
) -> None:
    """Recursively set sort on every encoding whose field == chart_strain_field
    on a live altair chart object."""
    enc = _live_attr(node, "encoding")
    if enc is not None:
        for channel in ("x", "y"):
            ch = _live_attr(enc, channel)
            if ch is not None and _channel_field(ch) == chart_strain_field:
                ch.sort = list(sort_order)
    for attr in ("hconcat", "vconcat", "concat", "layer"):
        sub = _live_attr(node, attr)
        if isinstance(sub, list):
            for s in sub:
                _walk_and_apply_sort(s, chart_strain_field, sort_order)
    # FacetChart.spec is the chart being faceted; recurse unconditionally so
    # we descend into the inner LayerChart / Chart that actually carries the
    # encoding. Gating on `spec.encoding is not None` was wrong because a
    # LayerChart has no top-level encoding — its encodings live on its layers.
    spec = _live_attr(node, "spec")
    if spec is not None:
        _walk_and_apply_sort(spec, chart_strain_field, sort_order)


def _live_attr(obj: Any, name: str) -> Any:
    """Return obj.name unless it's missing or altair's Undefined sentinel."""
    v = getattr(obj, name, None)
    if v is None:
        return None
    if v is alt.Undefined:
        return None
    return v


def _pop_toplevel_only_attrs(
    chart: alt.TopLevelMixin,
) -> tuple[Any, dict]:
    """Pop top-level-only attrs off chart._kwds so altair lets us nest it.

    Returns (config, other) where `config` is the popped Config (or Undefined)
    and `other` is a dict of any other popped attrs ($schema, padding,
    autosize, background) that are non-Undefined.

    Vega-Lite forbids these properties on subspecs; altair enforces this in
    `_check_if_valid_subspec`. We move them onto the outer HConcatChart we
    build, where they belong.
    """
    config = chart._kwds.pop("config", alt.Undefined)
    other: dict = {}
    for k in ("$schema", "padding", "autosize", "background"):
        v = chart._kwds.pop(k, alt.Undefined)
        if v is not alt.Undefined:
            other[k] = v
    return config, other


def _apply_combined_config(combined: alt.HConcatChart, hoisted_config: Any) -> None:
    """Set the combined chart's config = (user's config) ∪ {view.stroke=None}.

    `view.stroke=None` removes the panel borders that altair would otherwise
    draw around each subspec. The user's config (if any) takes precedence on
    everything else; we only add `view.stroke=None` if not already set.
    """
    if hoisted_config is alt.Undefined:
        config_dict: dict = {}
    elif hasattr(hoisted_config, "to_dict"):
        config_dict = hoisted_config.to_dict()
    else:
        config_dict = dict(hoisted_config)
    view = dict(config_dict.get("view") or {})
    view.setdefault("stroke", None)
    config_dict["view"] = view
    combined._kwds["config"] = alt.Config.from_dict(config_dict)


def _channel_field(ch: Any) -> str | None:
    """Read the underlying `field` string from an altair channel object.

    `ch.field` returns altair's `_PropertySetter` (used for fluent chaining),
    not the stored field name. The stored value is reachable via `to_dict()`.
    """
    to_dict = getattr(ch, "to_dict", None)
    if not callable(to_dict):
        return None
    try:
        d = to_dict()
    except Exception:
        return None
    if isinstance(d, dict):
        f = d.get("field")
        if isinstance(f, str):
            return f
    return None


def _chart_strain_dim(
    spec: dict, axis_hits: list[_AxisHit], axis: str
) -> int | float | dict:
    """Return the dim value (height for axis=y, width for axis=x) on the
    panel containing the first axis hit.

    Walks the prefix of the hit's path from longest to shortest, returning
    the value of the dim key on the nearest enclosing dict that has it.
    Raises if no enclosing dict has it.
    """
    dim_key = "height" if axis == "y" else "width"
    path = axis_hits[0][0]
    for prefix_len in range(len(path), -1, -1):
        node = _get_at_path(spec, path[:prefix_len])
        if isinstance(node, dict) and dim_key in node:
            return node[dim_key]
    raise ValueError(
        "the chart panel containing chart_strain_field has no explicit "
        f"{dim_key!r} property; set the chart's {dim_key} explicitly so the "
        f"tree panel can be sized to match (e.g. .properties({dim_key}="
        f"alt.Step(11)) for one row per strain, or .properties({dim_key}=300) "
        "for fixed pixels)."
    )


def _get_at_path(spec: Any, path: tuple) -> Any:
    cur = spec
    for p in path:
        cur = cur[p]
    return cur


def _coerce_dim(v: int | float | dict) -> int | float | alt.Step:
    """Turn a spec dim value into something Altair `properties()` accepts."""
    if isinstance(v, dict) and "step" in v:
        return alt.Step(v["step"])
    if isinstance(v, (int, float)):
        return v
    raise ValueError(
        f"unsupported chart-strain dim value {v!r}; expected an int/float "
        "(fixed pixels) or {'step': N} (alt.Step)."
    )


# ---------- tree panel construction (unchanged from Phase 1) ----------


def _build_tree_chart(
    root: _tree.TreeNode,
    *,
    n_tips: int,
    width: int,
    height: int | float | alt.Step,
) -> alt.Chart:
    seg_df = _tree.segments(root)
    tips_df = pd.DataFrame(
        [{"name": t.name, "x": t.x, "y": t.y} for t in _tree.tips(root)]
    )
    x_max = tips_df["x"].max()
    leader_df = tips_df[tips_df["x"] < x_max].assign(x2=x_max)

    x_min_seg = float(seg_df[["x", "x2"]].min().min())
    x_max_seg = float(seg_df[["x", "x2"]].max().max())
    x_scale = alt.Scale(domain=[x_min_seg, x_max_seg], nice=False, zero=False)
    y_scale = alt.Scale(domain=[n_tips - 0.5, -0.5], nice=False, zero=False)
    y_enc = alt.Y("y:Q", axis=None, scale=y_scale)
    x_enc = alt.X("x:Q", axis=None, scale=x_scale)

    leaders = (
        alt.Chart(leader_df)
        .mark_rule(stroke="#888", strokeWidth=1.0, strokeDash=[2, 2])
        .encode(x=x_enc, x2="x2:Q", y=y_enc)
    )
    branches = (
        alt.Chart(seg_df)
        .mark_rule(strokeWidth=1.5)
        .encode(x=x_enc, x2="x2:Q", y=y_enc, y2="y2:Q")
    )
    tip_marks = (
        alt.Chart(tips_df).mark_circle(size=28, color="black").encode(x=x_enc, y=y_enc)
    )

    return (leaders + branches + tip_marks).properties(width=width, height=height)
