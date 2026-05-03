"""Build the tree-annotated chart by introspecting and extending a user's Altair chart."""

from __future__ import annotations

import copy
import json
import math
import re
import warnings
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal

import altair as alt
import pandas as pd

from . import _tree

# Accepted chart input forms for the public `plot` function.
ChartInput = alt.TopLevelMixin | str | Path | dict

# Type for an axis hit found by _find_strain_encoding: (path, encoding_dict, channel).
# `path` is a tuple of dict keys / list indices that locates `encoding_dict`
# inside the spec, ending with ("encoding", channel).
_AxisHit = tuple[tuple, dict, str]


TreeLocation = Literal["left", "right", "top", "bottom"]


def plot(
    tree: str | Path | dict | _tree.TreeNode,
    chart: ChartInput,
    *,
    chart_strain_field: str,
    tree_strain_field: str,
    branch_length: Literal["div", "num_date"] = "div",
    tree_size: int = 100,
    tree_location: TreeLocation | None = None,
    scale_bar: bool = False,
    branch_length_units: str | None = None,
    prune_tree_to_chart: bool = False,
    strict_version: bool = True,
) -> alt.HConcatChart | alt.VConcatChart:
    """Return an Altair chart with a phylogenetic tree drawn alongside `chart`.

    The chart's strain-axis sort is overridden to match the tree's tip order
    (the headline behavior of this package).

    Parameters
    ----------
    tree
        Auspice JSON path, dict, or a pre-parsed :class:`TreeNode`. If a path
        or dict, it is parsed with the same `tree_strain_field` value.
    chart
        Either a live Altair chart (`Chart`, `LayerChart`, `FacetChart`,
        `HConcatChart`, `VConcatChart`, `ConcatChart`), a path to a saved
        Vega-Lite JSON (`*.json`) or HTML (`*.html`), or an already-parsed
        spec `dict`. Whichever form, the chart must encode `chart_strain_field`
        on `x` or `y`. Secondary encodings (color, tooltip, etc.) on the same
        field are passed through untouched.
    chart_strain_field
        Required. The data-column name the chart's strain axis encodes (e.g.
        `"strain"` or `"axis_label"`).
    tree_strain_field
        Required. Where on each tree tip to find the strain identifier. The
        literal string `"name"` selects the top-level Auspice node `name`
        field; any other value `X` selects `node_attrs[X]` (auto-unwrapping
        the Auspice `{"value": ...}` convention). Dotted paths are not
        accepted.
    branch_length
        Which Auspice node attribute supplies branch lengths. `"div"`
        (default) reads `node_attrs.div`. `"num_date"` reads
        `node_attrs.num_date.value`.
    tree_size
        Size in pixels of the tree's branch axis (the dimension perpendicular
        to the strain rows). For vertical layout (chart strain on `y`) this
        is the tree panel's *width*; for horizontal layout (chart strain on
        `x`) this is the tree panel's *height*. The tree's tip-axis
        dimension is computed from the chart's strain dimension so tips
        align row-for-row with chart rows.
    tree_location
        Where to draw the tree relative to the chart. Valid values depend
        on which axis carries the strain encoding:

        - chart strain on `y` → `"left"` (default) or `"right"`. With
          `"right"`, the tree is hconcat'd on the right of the chart and
          its branches flip so tips face left toward the chart.
        - chart strain on `x` → `"bottom"` (default) or `"top"`. With
          `"top"`, the tree is vconcat'd above the chart and its branches
          flip so tips face down toward the chart.

        Defaults match where the chart's strain-axis labels naturally
        render (left side for y-axis, bottom for x-axis), so tips align
        with the labels. Specifying `"top"`/`"bottom"` for a y-encoded
        strain (or `"left"`/`"right"` for an x-encoded strain) raises
        `ValueError`.
    scale_bar
        Off by default. When True, adds a small bar in the tree panel
        whose length corresponds to a "nice" number (largest value among
        1/2/5 × 10^k that is ≤ 25% of the branch range). Sits at the tail
        end of the tip axis, in extra pixel space added past the tree
        body so tip-row alignment with the chart is preserved.
    branch_length_units
        Used only when `scale_bar=True` and `branch_length="div"`: the
        unit string pasted after the bar's numeric length (e.g.
        `"substitutions/site"` → `"0.01 substitutions/site"`). `None`
        renders unitless. We do not auto-detect divergence units —
        Auspice has no formal field for them and magnitude heuristics
        misclassify silently. For `branch_length="num_date"` the label
        is always in `years`/`months` and this argument is ignored.
    prune_tree_to_chart
        When False (default), tree tips not present in the chart's strain
        set are a fatal error. When True, those tips (and any internal
        nodes whose subtrees become empty) are dropped before drawing,
        with single-child internals collapsed into their kept child. Chart
        strains not present in the tree are *always* fatal regardless of
        this flag — pruning would silently lose plot data.
    strict_version
        When True (default) the package raises `ValueError` if the chart
        spec's `$schema` URL identifies Vega-Lite 5 or earlier, or if the
        Auspice JSON's top-level `version` is not `v2`. With `False`, both
        cases become `warnings.warn` and parsing proceeds. The flag has no
        effect on a live `alt.Chart` (the constructing altair version is
        necessarily the running altair version).

    Returns
    -------
    altair.HConcatChart | altair.VConcatChart
        For vertical layout (chart strain on `y`), an `HConcatChart` with
        the tree on the left and the user's chart on the right. For
        horizontal layout (chart strain on `x`), a `VConcatChart` with the
        tree on top and the chart below. The orientation is fully derived
        from which axis carries `chart_strain_field`.
    """
    root = _ensure_tree(
        tree,
        tree_strain_field,
        branch_length=branch_length,
        strict_version=strict_version,
    )
    tip_list = _tree.layout(root)
    tip_names = [t.name for t in tip_list]

    _check_no_duplicate_tip_strains(tip_names, tree_strain_field=tree_strain_field)

    chart = _load_chart(chart, strict_version=strict_version)
    spec = chart.to_dict()

    axis_hits = _find_strain_encoding(spec, chart_strain_field)
    axis = axis_hits[0][2]

    location = _resolve_tree_location(tree_location, axis)

    chart_strains = _extract_chart_strains(spec, axis_hits, chart_strain_field)

    _reconcile_tips_and_strains(
        tree_strains=tip_names,
        chart_strains=chart_strains,
        chart_strain_field=chart_strain_field,
        tree_strain_field=tree_strain_field,
        prune_tree_to_chart=prune_tree_to_chart,
        chart_spec=spec,
        tree_source=tree,
    )

    if prune_tree_to_chart and (set(tip_names) - set(chart_strains)):
        root = _tree._prune_tree_to(root, set(chart_strains))
        tip_list = _tree.layout(root)
        tip_names = [t.name for t in tip_list]

    strain_dim = _coerce_dim(
        _chart_strain_dim(spec, axis_hits, axis), n_tips=len(tip_names)
    )
    tree_chart = _build_tree_chart(
        root,
        n_tips=len(tip_names),
        tree_size=tree_size,
        strain_dim=strain_dim,
        strain_axis=axis,
        tree_location=location,
        scale_bar=scale_bar,
        branch_length=branch_length,
        branch_length_units=branch_length_units,
    )

    new_chart = _apply_tree_order_to_chart_object(chart, chart_strain_field, tip_names)
    hoisted_config, hoisted_other = _pop_toplevel_only_attrs(new_chart)

    combined = _concat_for_location(
        tree_chart=tree_chart, user_chart=new_chart, location=location
    )
    _apply_combined_config(combined, hoisted_config)
    for k, v in hoisted_other.items():
        combined._kwds[k] = v
    return combined


def _resolve_tree_location(
    tree_location: TreeLocation | None, strain_axis: str
) -> TreeLocation:
    """Pick the default tree_location matching the strain axis, or validate
    that an explicit value is compatible with the axis."""
    valid_for_y = ("left", "right")
    valid_for_x = ("top", "bottom")
    if tree_location is None:
        return "left" if strain_axis == "y" else "bottom"
    if strain_axis == "y" and tree_location not in valid_for_y:
        raise ValueError(
            f"tree_location={tree_location!r} is incompatible with a "
            "y-encoded strain (vertical layout). The chart's strain "
            "axis is on `y`, so the tree must be alongside it on the "
            f"left or right. Valid values: {valid_for_y!r}."
        )
    if strain_axis == "x" and tree_location not in valid_for_x:
        raise ValueError(
            f"tree_location={tree_location!r} is incompatible with an "
            "x-encoded strain (horizontal layout). The chart's strain "
            "axis is on `x`, so the tree must be above or below it. "
            f"Valid values: {valid_for_x!r}."
        )
    return tree_location


def _concat_for_location(
    *,
    tree_chart: alt.TopLevelMixin,
    user_chart: alt.TopLevelMixin,
    location: TreeLocation,
) -> alt.HConcatChart | alt.VConcatChart:
    """Concat tree and chart in the order implied by the tree's location."""
    if location == "left":
        return alt.hconcat(tree_chart, user_chart, spacing=0).resolve_scale(
            y="independent"
        )
    if location == "right":
        return alt.hconcat(user_chart, tree_chart, spacing=0).resolve_scale(
            y="independent"
        )
    if location == "top":
        return alt.vconcat(tree_chart, user_chart, spacing=0).resolve_scale(
            x="independent"
        )
    if location == "bottom":
        return alt.vconcat(user_chart, tree_chart, spacing=0).resolve_scale(
            x="independent"
        )
    raise ValueError(f"unreachable: tree_location={location!r}")


def _ensure_tree(
    tree: str | Path | dict | _tree.TreeNode,
    tree_strain_field: str,
    *,
    branch_length: str,
    strict_version: bool,
) -> _tree.TreeNode:
    if isinstance(tree, _tree.TreeNode):
        return tree
    return _tree.load_auspice(
        tree,
        tree_strain_field=tree_strain_field,
        branch_length=branch_length,
        strict_version=strict_version,
    )


# ---------- chart loading (JSON / HTML / dict / live altair) ----------


def _load_chart(chart_input: ChartInput, *, strict_version: bool) -> alt.TopLevelMixin:
    """Convert any supported chart input into a live Altair chart.

    A live `alt.TopLevelMixin` is returned as-is — its `$schema` is
    irrelevant since the constructing altair version is necessarily the
    running altair version. For dict / JSON path / HTML path inputs we run
    the Vega-Lite version check (under `strict_version`), strip altair's
    `params[].views` round-trip annotations, and then dispatch to the right
    chart subclass via `alt.Chart.from_dict(...)`.
    """
    if isinstance(chart_input, alt.TopLevelMixin):
        return chart_input

    if isinstance(chart_input, dict):
        spec = chart_input
    elif isinstance(chart_input, (str, Path)):
        path = Path(chart_input)
        suffix = path.suffix.lower()
        if suffix == ".json":
            with path.open() as f:
                spec = json.load(f)
        elif suffix == ".html":
            spec = _extract_spec_from_html(path.read_text())
        else:
            raise ValueError(
                f"unsupported chart file extension {suffix!r} for {path}; "
                "expected .json or .html"
            )
    else:
        raise TypeError(
            "chart must be a live Altair chart, a path (str / pathlib.Path) "
            "to a .json or .html file, or a parsed spec dict; got "
            f"{type(chart_input).__name__}"
        )

    _check_chart_schema_version(spec, strict_version=strict_version)
    spec = copy.deepcopy(spec)
    _strip_params_views(spec)
    # `from_dict` with validate=True dispatches to the right subclass
    # (Chart / LayerChart / FacetChart / HConcatChart / VConcatChart /
    # ConcatChart) based on the spec's shape.
    return alt.Chart.from_dict(spec)


def _check_chart_schema_version(spec: dict, *, strict_version: bool) -> None:
    """Inspect spec['$schema']; raise / warn if it identifies Vega-Lite 5
    or earlier."""
    schema = spec.get("$schema")
    if not isinstance(schema, str) or not schema:
        warnings.warn(
            "chart spec has no $schema field; proceeding but the spec may "
            "have been saved by an older altair version with a different "
            "shape than this package expects.",
            stacklevel=3,
        )
        return
    m = re.search(r"vega-lite/v(\d+)", schema)
    if m is None:
        warnings.warn(
            f"chart $schema={schema!r} does not look like a Vega-Lite "
            "schema URL; proceeding but the spec may not be a Vega-Lite "
            "chart.",
            stacklevel=3,
        )
        return
    major = int(m.group(1))
    if major < 6:
        msg = (
            f"chart spec was saved with Vega-Lite {major} (likely altair "
            f"{major - 1}); please re-save it from an altair 6+ "
            "environment with `chart.save(...)`."
        )
        if strict_version:
            raise ValueError(msg)
        warnings.warn(msg, stacklevel=3)


def _strip_params_views(spec: Any) -> None:
    """Recursively delete `views` from every params[] entry.

    altair's `to_dict()` annotates each selection-param with the views it's
    bound to, but altair's own `from_dict()` validation rejects the field.
    Stripping is safe: the renderer rebinds params to views on its own.
    """
    if isinstance(spec, dict):
        params = spec.get("params")
        if isinstance(params, list):
            for p in params:
                if isinstance(p, dict):
                    p.pop("views", None)
        for v in spec.values():
            _strip_params_views(v)
    elif isinstance(spec, list):
        for item in spec:
            _strip_params_views(item)


class _ScriptCollector(HTMLParser):
    """Collect the text content of every <script> tag in an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "script":
            self._in_script = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.scripts.append(data)


def _extract_spec_from_html(html: str) -> dict:
    """Pull the Vega-Lite spec dict out of an altair-saved HTML page.

    altair's default `to_html()` template emits a `var spec = {...};` line
    inside a `<script>` tag whose value is a json.dumps of the spec. We
    locate that line via stdlib `html.parser` (no regex on the document)
    and use `json.JSONDecoder.raw_decode` to do brace-balancing on the
    JSON literal (no regex on the JSON either).

    Limits: works on the default altair template. If the user passed
    `chart.save(template=...)` with a custom template, this raises with a
    remediation message pointing at JSON. A page with multiple `var spec`
    blocks: we return the first one and document this as a known limit.
    """
    parser = _ScriptCollector()
    parser.feed(html)
    decoder = json.JSONDecoder()
    for script in parser.scripts:
        i = script.find("var spec")
        if i == -1:
            continue
        brace = script.index("{", i)
        spec, _ = decoder.raw_decode(script, brace)
        return spec
    raise ValueError(
        "no `var spec = {...}` block found in the HTML; this is likely a "
        "non-default altair template. Re-save the chart as JSON: "
        "chart.save('foo.json')."
    )


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


def _check_no_duplicate_tip_strains(
    tip_names: list[str], *, tree_strain_field: str
) -> None:
    """Tip identifiers must be unique under the chosen `tree_strain_field`."""
    if len(set(tip_names)) == len(tip_names):
        return
    from collections import Counter

    dups = sorted(s for s, c in Counter(tip_names).items() if c > 1)
    raise ValueError(
        f"tree_strain_field={tree_strain_field!r} resolves to duplicate "
        f"values across tips: {dups[:10]}. Each tip must have a unique "
        "strain identifier; either pick a different tree_strain_field or "
        "fix the underlying tree."
    )


def _reconcile_tips_and_strains(
    *,
    tree_strains: list[str],
    chart_strains: list[str],
    chart_strain_field: str,
    tree_strain_field: str,
    prune_tree_to_chart: bool,
    chart_spec: dict,
    tree_source: Any,
) -> None:
    """Verify tree strains and chart strains are reconcilable.

    Three asymmetries:
      - chart strains not in tree → always fatal.
      - tree tips not in chart → fatal unless `prune_tree_to_chart=True`.
      - (duplicate tree_strain_field values across tips → handled by the
        separate `_check_no_duplicate_tip_strains`.)

    On any fatal asymmetry, raises `ValueError` with a multi-line message
    that includes sample values from both sides and any candidate-field
    suggestions whose values overlap heavily with the other side.
    """
    tree_set = set(tree_strains)
    chart_set = set(chart_strains)
    chart_minus_tree = chart_set - tree_set
    tree_minus_chart = tree_set - chart_set

    if not chart_minus_tree and (not tree_minus_chart or prune_tree_to_chart):
        return

    hints = _candidate_field_hints(
        chart_spec=chart_spec,
        chart_strain_field=chart_strain_field,
        tree_strains=tree_strains,
        tree_source=tree_source,
        tree_strain_field=tree_strain_field,
        chart_strains=chart_strains,
    )
    raise ValueError(
        _format_strain_mismatch(
            chart_strain_field=chart_strain_field,
            tree_strain_field=tree_strain_field,
            chart_strains=chart_strains,
            tree_strains=tree_strains,
            chart_minus_tree=chart_minus_tree,
            tree_minus_chart=tree_minus_chart,
            prune_tree_to_chart=prune_tree_to_chart,
            hints=hints,
        )
    )


def _format_strain_mismatch(
    *,
    chart_strain_field: str,
    tree_strain_field: str,
    chart_strains: list[str],
    tree_strains: list[str],
    chart_minus_tree: set[str],
    tree_minus_chart: set[str],
    prune_tree_to_chart: bool,
    hints: list[str],
) -> str:
    parts: list[str] = []
    if chart_minus_tree:
        parts.append(
            f"{len(chart_minus_tree)} chart strain(s) are not present in the "
            "tree (these would be silently dropped if we pruned, so this is "
            "always fatal)."
        )
    if tree_minus_chart and not prune_tree_to_chart:
        parts.append(
            f"{len(tree_minus_chart)} tree tip(s) are not present in the "
            "chart. Pass `prune_tree_to_chart=True` to drop them automatically."
        )
    parts.append("")
    parts.append(
        f"Tried: chart_strain_field={chart_strain_field!r}, "
        f"tree_strain_field={tree_strain_field!r}"
    )
    parts.append("Sample chart_strain_field values: " f"{sorted(chart_strains)[:5]}")
    parts.append("Sample tree_strain_field values:  " f"{sorted(tree_strains)[:5]}")
    if chart_minus_tree:
        parts.append(f"Sample chart-only values: {sorted(chart_minus_tree)[:5]}")
    if tree_minus_chart and not prune_tree_to_chart:
        parts.append(f"Sample tree-only values:  {sorted(tree_minus_chart)[:5]}")
    if hints:
        parts.append("")
        parts.append("Possible alternatives:")
        for h in hints:
            parts.append(f"  - {h}")
    return "\n".join(parts)


def _candidate_field_hints(
    *,
    chart_spec: dict,
    chart_strain_field: str,
    tree_strains: list[str],
    tree_source: Any,
    tree_strain_field: str,
    chart_strains: list[str],
) -> list[str]:
    """Return human-readable hints suggesting alternative strain fields.

    Scans:
      - chart side: every column appearing in inline / named data of the
        spec. For each, fraction of values that are in tree_strains.
      - tree side: every node_attrs key on tips, plus the literal "name"
        (top-level Auspice tip ID). For each, fraction of values that are
        in chart_strains. Skipped if `tree_source` is a parsed TreeNode
        rather than a path/dict (we'd have no original Auspice JSON to
        introspect).

    Threshold: 50% overlap. Tunable; lower threshold trades fewer
    false-negatives for more false-positives in the hint.
    """
    OVERLAP_THRESHOLD = 0.5
    hints: list[str] = []
    tree_set = set(tree_strains)
    chart_set = set(chart_strains)

    if tree_set:
        for field_name, values in _enumerate_chart_data_columns(chart_spec):
            if field_name == chart_strain_field:
                continue
            distinct = set(values)
            if not distinct:
                continue
            overlap = len(distinct & tree_set)
            if overlap / len(tree_set) >= OVERLAP_THRESHOLD:
                hints.append(
                    f"the chart has a field {field_name!r} whose values "
                    f"match {overlap}/{len(tree_set)} tree strains — did "
                    f"you mean chart_strain_field={field_name!r}?"
                )

    tree_dict = _tree_source_as_dict(tree_source)
    if chart_set and tree_dict is not None and "tree" in tree_dict:
        for attr, values in _enumerate_tree_tip_attrs(tree_dict["tree"]):
            if attr == tree_strain_field:
                continue
            distinct = set(values)
            if not distinct:
                continue
            overlap = len(distinct & chart_set)
            if overlap / len(chart_set) >= OVERLAP_THRESHOLD:
                hint_lhs = (
                    "the tree has node `name` field"
                    if attr == "name"
                    else f"the tree has node_attrs[{attr!r}]"
                )
                hints.append(
                    f"{hint_lhs} whose values match {overlap}/"
                    f"{len(chart_set)} chart strains — did you mean "
                    f"tree_strain_field={attr!r}?"
                )

    return hints


def _enumerate_chart_data_columns(spec: Any) -> list[tuple[str, list]]:
    """Walk the spec for every column appearing in inline / named data.

    Returns `[(field_name, values), ...]` where `values` is the list of
    raw values seen for that field across all data rows visited (with
    duplicates).
    """
    datasets = spec.get("datasets", {}) if isinstance(spec, dict) else {}
    by_field: dict[str, list] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            data = node.get("data")
            if isinstance(data, dict):
                rows: list | None = None
                if "values" in data and isinstance(data["values"], list):
                    rows = data["values"]
                elif "name" in data:
                    name = data["name"]
                    if isinstance(datasets.get(name), list):
                        rows = datasets[name]
                if rows:
                    for row in rows:
                        if isinstance(row, dict):
                            for k, v in row.items():
                                by_field.setdefault(k, []).append(v)
            for k, v in node.items():
                if k in ("data", "datasets"):
                    continue
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return list(by_field.items())


def _tree_source_as_dict(tree_source: Any) -> dict | None:
    """Return the original Auspice JSON dict if available, else None.

    We use this for the candidate-field hint on the tree side. If the user
    passed a pre-parsed `TreeNode`, we can't introspect the original
    `node_attrs` keys and skip the tree-side hint.
    """
    if isinstance(tree_source, dict):
        return tree_source
    if isinstance(tree_source, (str, Path)):
        try:
            with open(tree_source) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
    return None


def _enumerate_tree_tip_attrs(
    tree_root_dict: dict,
) -> list[tuple[str, list]]:
    """Walk an Auspice JSON tree dict and yield (attr, values) per tip-attr.

    Includes a synthetic `"name"` entry for the top-level node `name` field
    (the canonical Auspice tip identifier, used by `tree_strain_field="name"`).
    Auspice's `{value: ...}` convention is auto-unwrapped.
    """
    by_attr: dict[str, list] = {}
    names: list = []

    def walk(n: dict) -> None:
        children = n.get("children")
        if children:
            for c in children:
                walk(c)
            return
        nm = n.get("name")
        if nm is not None:
            names.append(nm)
        for k, v in n.get("node_attrs", {}).items():
            if isinstance(v, dict) and "value" in v:
                v = v["value"]
            by_attr.setdefault(k, []).append(v)

    walk(tree_root_dict)

    out: list[tuple[str, list]] = []
    if names:
        out.append(("name", names))
    out.extend(by_attr.items())
    return out


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
    """Apply the user chart's hoisted top-level config to the combined chart.

    The user's config drives the chart panel's appearance unchanged
    (including `view.stroke` if the user set one via `.configure_view(...)`);
    the tree panel handles its own border at the panel level (see
    `_build_tree_chart`'s `view = ViewBackground(stroke=None)`). If the user
    had no config, we don't add one — the chart panel gets Vega-Lite's
    defaults and the tree's panel-level view still wins.
    """
    if hoisted_config is alt.Undefined:
        return
    if hasattr(hoisted_config, "to_dict"):
        combined._kwds["config"] = alt.Config.from_dict(hoisted_config.to_dict())
    else:
        combined._kwds["config"] = alt.Config.from_dict(dict(hoisted_config))


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


def _coerce_dim(v: int | float | dict, *, n_tips: int) -> int | float:
    """Turn the chart's strain-axis dim into a pixel height for the tree.

    `Step(N)` on the chart means the chart's strain-axis body is `N * n_tips`
    pixels wide/tall (a Vega-Lite point/band scale with the default
    `paddingOuter=0.5` puts the first/last items half a step inside the
    panel). We can't pass `Step(N)` straight through to the tree because the
    tree's tip-axis is *quantitative* — Vega-Lite ignores `Step` on
    quantitative axes and falls back to a default height. So we convert to
    fixed pixels here. The tree's y-domain is set to `[-0.5, n_tips - 0.5]`,
    which positions tip i exactly where row i sits on the chart's point/band
    scale.

    For an int/float dim the chart used a fixed pixel height; we propagate
    it directly.
    """
    if isinstance(v, dict) and "step" in v:
        return v["step"] * n_tips
    if isinstance(v, (int, float)):
        return v
    raise ValueError(
        f"unsupported chart-strain dim value {v!r}; expected an int/float "
        "(fixed pixels) or {'step': N} (alt.Step)."
    )


# ---------- tree panel construction (unchanged from Phase 1) ----------


_SCALE_BAR_EXTRA_PIXELS = 35


def _nice_scale_bar_length(branch_range: float) -> float:
    """Return the largest 1/2/5 × 10^k value ≤ 25% of `branch_range`.

    Examples (target = 0.25 * branch_range):
        target=0.04 → 0.02 (m=2, k=-2)
        target=0.07 → 0.05 (m=5, k=-2)
        target=1.0  → 1.0  (m=1, k=0)
        target=3.5  → 2.0  (m=2, k=0)
    """
    target = branch_range * 0.25
    if target <= 0:
        return 0.0
    k = math.floor(math.log10(target))
    base = 10.0**k
    for m in (5, 2, 1):
        if m * base <= target:
            return m * base
    return base  # unreachable; m=1 always fits since base ≤ target


def _format_scale_bar_label(
    length: float, branch_length: str, units: str | None
) -> str:
    """Format the scale-bar text per `branch_length`.

    For `"div"` the user-supplied `units` (or no unit) is appended.
    For `"num_date"` the unit is automatic: `years` if `length >= 1`,
    otherwise `months` (rounded). `units` is ignored in the num_date case.
    """
    if branch_length == "num_date":
        if length >= 1:
            return f"{length:g} years"
        months = round(length * 12)
        return f"{months} months"
    if units:
        return f"{length:g} {units}"
    return f"{length:g}"


def _build_scale_bar_layer(
    *,
    branch_min: float,
    branch_max: float,
    bar_length: float,
    n_tips: int,
    extra_units: float,
    strain_axis: str,
    label: str,
) -> alt.LayerChart:
    """Build a 2-layer (bar rule + text) chart for the scale bar.

    The bar lives in the extra tip-axis strip past the last tip, parallel
    to the branch axis, and is **centered on the branch range** so the
    text label (which is typically wider than the bar) doesn't overflow
    the tree panel's edge.

    For vertical layouts (strain on y) the text is horizontal, placed
    just below the bar. For horizontal layouts (strain on x) the bar is
    vertical and the text is rotated 270° so it reads bottom-to-top,
    parallel to the bar.

    The bar/text data uses the same column names as `_tree.segments`
    ("x" for branch values, "y" for tip values) so it shares scales with
    the rest of the tree's layers.
    """
    # Positions inside the extra tip-axis strip. Tightened from the
    # earlier 0.35 / 0.78 split: text now sits ~7 px below the bar in
    # vertical mode (or ~7 px past it in horizontal mode).
    bar_tip_pos = n_tips - 0.5 + extra_units * 0.20
    text_tip_pos = n_tips - 0.5 + extra_units * 0.45

    # Center the bar on the branch range (was anchored at branch_min,
    # which left long text labels hanging past the panel edge).
    branch_mid = (branch_min + branch_max) / 2
    bar_b_start = branch_mid - bar_length / 2
    bar_b_end = branch_mid + bar_length / 2

    bar_df = pd.DataFrame([{"x": bar_b_start, "x2": bar_b_end, "y": bar_tip_pos}])
    text_df = pd.DataFrame([{"x": branch_mid, "y": text_tip_pos, "label": label}])

    if strain_axis == "y":
        # Bar horizontal across the branch axis; text horizontal below it.
        bar = (
            alt.Chart(bar_df)
            .mark_rule(strokeWidth=2.0, color="black")
            .encode(x="x:Q", x2="x2:Q", y="y:Q")
        )
        text = (
            alt.Chart(text_df)
            .mark_text(fontSize=10, align="center", baseline="top")
            .encode(x="x:Q", y="y:Q", text="label:N")
        )
    else:
        # Bar vertical along the branch axis; text rotated to read
        # parallel to the bar (270° = bottom-to-top), centered on its
        # anchor so it sits next to the bar without overlapping.
        bar = (
            alt.Chart(bar_df)
            .mark_rule(strokeWidth=2.0, color="black")
            .encode(y="x:Q", y2="x2:Q", x="y:Q")
        )
        text = (
            alt.Chart(text_df)
            .mark_text(fontSize=10, align="center", baseline="middle", angle=270)
            .encode(y="x:Q", x="y:Q", text="label:N")
        )
    return bar + text


def _build_tree_chart(
    root: _tree.TreeNode,
    *,
    n_tips: int,
    tree_size: int,
    strain_dim: int | float | alt.Step,
    strain_axis: str,
    tree_location: TreeLocation,
    scale_bar: bool = False,
    branch_length: str = "div",
    branch_length_units: str | None = None,
) -> alt.Chart:
    """Build the tree panel.

    `_tree.segments(root)` returns a dataframe with columns x, x2 (branch-axis
    values from the root's div) and y, y2 (tip-axis index). For each layout
    we bind those columns to chart x or chart y differently, and the
    branch_scale domain orientation depends on which side of the chart the
    tree sits on (so the tip-end of every branch always faces the chart):

    - `tree_location="left"` (strain on y). Branch axis on chart x; root on
      the left, tips on the right (toward the chart). domain = [min, max].
    - `tree_location="right"` (strain on y). Branch axis on chart x; root on
      the right, tips on the left (toward the chart). domain = [max, min].
    - `tree_location="top"` (strain on x). Branch axis on chart y; root at
      the top, tips at the bottom (toward the chart). Vega-Lite y has
      domain[1] at the top, so root-on-top means domain = [max, min].
    - `tree_location="bottom"` (strain on x). Branch axis on chart y; root
      at the bottom, tips at the top (toward the chart). domain = [min, max].

    Tip-axis scale and the leader_df are layout-direction-agnostic: tips at
    distance `tip.x < branch_max` get a leader from `tip.x` to `branch_max`
    in branch-coordinate, and the scale handles the pixel mapping.
    """
    seg_df = _tree.segments(root)
    tips_df = pd.DataFrame(
        [{"name": t.name, "x": t.x, "y": t.y} for t in _tree.tips(root)]
    )
    branch_max = float(seg_df[["x", "x2"]].max().max())
    branch_min = float(seg_df[["x", "x2"]].min().min())
    leader_df = tips_df[tips_df["x"] < branch_max].assign(x2=branch_max)

    # When scale_bar is on, extend the tip-axis past the last tip by
    # `_SCALE_BAR_EXTRA_PIXELS` and matching extra data units. Per-row pixel
    # allocation (`step_px`) stays constant, so tips 0..n-1 keep the exact
    # same on-screen positions they had before — only the panel is taller
    # (vertical) or wider (horizontal). Tip-row alignment with the chart
    # is therefore preserved; the scale bar extends beyond the chart's
    # panel edge, which the default top/left-aligned hconcat/vconcat
    # absorbs without disturbing alignment.
    if scale_bar:
        if not isinstance(strain_dim, (int, float)):
            raise ValueError(
                "scale_bar requires a numeric strain dimension; got "
                f"{type(strain_dim).__name__}"
            )
        step_px = strain_dim / n_tips
        extra_units = _SCALE_BAR_EXTRA_PIXELS / step_px
        extended_strain_dim = strain_dim + _SCALE_BAR_EXTRA_PIXELS
        bar_length = _nice_scale_bar_length(branch_max - branch_min)
        bar_label = _format_scale_bar_label(
            bar_length, branch_length, branch_length_units
        )
        scale_bar_layer = _build_scale_bar_layer(
            branch_min=branch_min,
            branch_max=branch_max,
            bar_length=bar_length,
            n_tips=n_tips,
            extra_units=extra_units,
            strain_axis=strain_axis,
            label=bar_label,
        )
    else:
        extra_units = 0.0
        extended_strain_dim = strain_dim
        scale_bar_layer = None

    if strain_axis == "y":
        # Vertical: branch axis on chart x; tip axis with tip 0 on top.
        # tree_location flips the branch domain so tips face the chart side.
        branch_domain = (
            [branch_min, branch_max]
            if tree_location == "left"
            else [branch_max, branch_min]
        )
        branch_scale = alt.Scale(domain=branch_domain, nice=False, zero=False)
        # tip-axis domain[0] (at panel bottom) extends past last tip when
        # scale_bar=True; tip i still sits at the same on-screen pixel.
        tip_scale = alt.Scale(
            domain=[n_tips - 0.5 + extra_units, -0.5], nice=False, zero=False
        )
        branch_enc = alt.X("x:Q", axis=None, scale=branch_scale)
        tip_enc = alt.Y("y:Q", axis=None, scale=tip_scale)
        leaders = (
            alt.Chart(leader_df)
            .mark_rule(stroke="#888", strokeWidth=1.0, strokeDash=[2, 2])
            .encode(x=branch_enc, x2="x2:Q", y=tip_enc)
        )
        branches = (
            alt.Chart(seg_df)
            .mark_rule(strokeWidth=1.5)
            .encode(x=branch_enc, x2="x2:Q", y=tip_enc, y2="y2:Q")
        )
        tip_marks = (
            alt.Chart(tips_df)
            .mark_circle(size=28, color="black")
            .encode(x=branch_enc, y=tip_enc)
        )
        layered = leaders + branches + tip_marks
        if scale_bar_layer is not None:
            layered = layered + scale_bar_layer
        layered = layered.properties(width=tree_size, height=extended_strain_dim)
    elif strain_axis == "x":
        # Horizontal: branch axis on chart y (Vega-Lite default has domain[1]
        # at the top); tip axis with tip 0 on the left.
        # tree_location="top" → root at top → branch_max at bottom.
        # tree_location="bottom" → root at bottom → branch_max at top.
        branch_domain = (
            [branch_max, branch_min]
            if tree_location == "top"
            else [branch_min, branch_max]
        )
        branch_scale = alt.Scale(domain=branch_domain, nice=False, zero=False)
        # tip-axis domain[1] (at panel right) extends past last tip when
        # scale_bar=True.
        tip_scale = alt.Scale(
            domain=[-0.5, n_tips - 0.5 + extra_units], nice=False, zero=False
        )
        branch_enc = alt.Y("x:Q", axis=None, scale=branch_scale)
        tip_enc = alt.X("y:Q", axis=None, scale=tip_scale)
        leaders = (
            alt.Chart(leader_df)
            .mark_rule(stroke="#888", strokeWidth=1.0, strokeDash=[2, 2])
            .encode(y=branch_enc, y2="x2:Q", x=tip_enc)
        )
        branches = (
            alt.Chart(seg_df)
            .mark_rule(strokeWidth=1.5)
            .encode(y=branch_enc, y2="x2:Q", x=tip_enc, x2="y2:Q")
        )
        tip_marks = (
            alt.Chart(tips_df)
            .mark_circle(size=28, color="black")
            .encode(y=branch_enc, x=tip_enc)
        )
        layered = leaders + branches + tip_marks
        if scale_bar_layer is not None:
            layered = layered + scale_bar_layer
        layered = layered.properties(width=extended_strain_dim, height=tree_size)
    else:
        raise ValueError(f"strain_axis must be 'x' or 'y', got {strain_axis!r}")

    # Suppress the panel border on the tree itself. This is a panel-level
    # Vega-Lite `view` property, which overrides any inherited
    # `config.view.stroke` (e.g. if the user's chart was built with
    # `.configure_view(stroke="black")`, that stroke applies to the chart
    # panel but not to the tree).
    layered._kwds["view"] = alt.ViewBackground(stroke=None)
    return layered
