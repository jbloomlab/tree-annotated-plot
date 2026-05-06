"""Build the tree-annotated chart by introspecting and extending a user's Altair chart."""

from __future__ import annotations

import copy
import json
import math
import re
import warnings
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal

import altair as alt
import pandas as pd

from . import _color, _config, _tree
from ._config import PlotConfig, TreeLocation

# Vega-Lite `orient` values that anchor the legend to the chart's left or
# right edge — these are the ones whose natural layout is one entry per row.
# (The Vega-Lite schema's other corner orients, `top-left`/`top-right`/
# `bottom-left`/`bottom-right`, all anchor to the top or bottom edge, so
# they're horizontal-direction by default and don't need the smart default.)
# If a chart's config-level `legend.columns` default is set (a common
# pattern in altair theme/config setups), Vega-Lite will pack entries into
# multiple columns even with a left/right orient. We force columns=1 in
# that case so the user's choice of `orient: "left"` or `"right"` produces
# vertical stacking without requiring them to know about the `columns`
# interaction.
_VERTICAL_ORIENTS = frozenset({"left", "right"})

# Accepted chart input forms for the public `plot` function.
ChartInput = alt.TopLevelMixin | str | Path | dict

# Type for an axis hit found by _find_strain_encoding: (path, encoding_dict, channel).
# `path` is a tuple of dict keys / list indices that locates `encoding_dict`
# inside the spec, ending with ("encoding", channel).
_AxisHit = tuple[tuple, dict, str]


def plot(
    tree: str | Path | dict | _tree.TreeNode,
    chart: ChartInput,
    *,
    chart_strain_field: str,
    tree_strain_field: str,
    branch_length: Literal["div", "num_date"],
    tree_size: int = 100,
    tree_location: TreeLocation | None = None,
    tree_line_width: float = 2.0,
    tree_node_size: float = 45,
    leader_line_width: float = 1.0,
    scale_bar: bool = False,
    branch_length_units: str | None = None,
    prune_tree_to_chart: bool = False,
    strict_version: bool = True,
    connect_leader_to_label: bool = False,
    strain_label_font_size: float = 10.0,
    strain_label_font_weight: Literal["normal", "bold"] = "normal",
    shift_tree_loc: int = 0,
    color_tree_by: str | None = None,
    tree_color_scale: dict[str, str] | None = None,
    tree_color_legend_format: dict[str, Any] | None = None,
    tree_color_legend_show: bool = True,
    scale_bar_font_size: float = 10.0,
) -> alt.HConcatChart | alt.VConcatChart:
    """Return an Altair chart with a phylogenetic tree drawn alongside `chart`."""
    return _build(
        tree,
        chart,
        PlotConfig(
            chart_strain_field=chart_strain_field,
            tree_strain_field=tree_strain_field,
            branch_length=branch_length,
            tree_size=tree_size,
            tree_location=tree_location,
            tree_line_width=tree_line_width,
            tree_node_size=tree_node_size,
            leader_line_width=leader_line_width,
            scale_bar=scale_bar,
            branch_length_units=branch_length_units,
            prune_tree_to_chart=prune_tree_to_chart,
            strict_version=strict_version,
            connect_leader_to_label=connect_leader_to_label,
            strain_label_font_size=strain_label_font_size,
            strain_label_font_weight=strain_label_font_weight,
            shift_tree_loc=shift_tree_loc,
            color_tree_by=color_tree_by,
            tree_color_scale=tree_color_scale,
            tree_color_legend_format=tree_color_legend_format,
            tree_color_legend_show=tree_color_legend_show,
            scale_bar_font_size=scale_bar_font_size,
        ),
    )


# `plot.__doc__` is assembled from canonical descriptions in `_config`:
# `PlotConfig`'s `Annotated[T, "<description>"]` metadata for every styling
# / behavior knob, and `_config.{TREE,CHART}_DESCRIPTION` for the two
# data-input parameters. The CLI's `--help` text reads from the same two
# sources, so per-parameter text lives in exactly one place.
_PLOT_DOC_HEADER = (
    "Return an Altair chart with a phylogenetic tree drawn alongside `chart`.\n"
    "\n"
    "The chart's strain-axis sort is overridden to match the tree's tip order\n"
    "(the headline behavior of this package).\n"
    "\n"
    "Parameters\n"
    "----------\n"
    + _config._render_data_param("tree", _config.TREE_DESCRIPTION)
    + "\n"
    + _config._render_data_param("chart", _config.CHART_DESCRIPTION)
    + "\n"
)

_PLOT_DOC_FOOTER = """

Returns
-------
altair.HConcatChart | altair.VConcatChart
    For vertical layout (chart strain on `y`), an `HConcatChart` with the
    tree on the left and the user's chart on the right. For horizontal
    layout (chart strain on `x`), a `VConcatChart` with the tree on top
    and the chart below.
"""


plot.__doc__ = (
    _PLOT_DOC_HEADER
    + _config._render_numpy_params(_config.PARAM_DOC_EXTRAS)
    + _PLOT_DOC_FOOTER
)


def _build(
    tree: str | Path | dict | _tree.TreeNode,
    chart: ChartInput,
    config: PlotConfig,
) -> alt.HConcatChart | alt.VConcatChart:
    """Shared implementation used by both `plot()` and the CLI.

    `tree` and `chart` are the data inputs (the things you can't usefully
    set on a config object); `config` carries every styling / behavior
    knob. Both surfaces converge here so they can never disagree.
    """
    root, auspice_meta = _ensure_tree(
        tree,
        config.tree_strain_field,
        branch_length=config.branch_length,
        strict_version=config.strict_version,
    )
    tip_list = _tree.layout(root)
    tip_names = [t.name for t in tip_list]

    _check_no_duplicate_tip_strains(
        tip_names, tree_strain_field=config.tree_strain_field
    )

    chart = _load_chart(chart, strict_version=config.strict_version)
    spec = chart.to_dict()

    axis_hits = _find_strain_encoding(spec, config.chart_strain_field)
    axis = axis_hits[0][2]

    location = _resolve_tree_location(config.tree_location, axis)

    chart_strains = _extract_chart_strains(spec, axis_hits, config.chart_strain_field)

    _reconcile_tips_and_strains(
        tree_strains=tip_names,
        chart_strains=chart_strains,
        chart_strain_field=config.chart_strain_field,
        tree_strain_field=config.tree_strain_field,
        prune_tree_to_chart=config.prune_tree_to_chart,
        chart_spec=spec,
        tree_source=tree,
    )

    if config.prune_tree_to_chart and (set(tip_names) - set(chart_strains)):
        root = _tree._prune_tree_to(root, set(chart_strains))
        tip_list = _tree.layout(root)
        tip_names = [t.name for t in tip_list]

    strain_dim = _coerce_dim(
        _chart_strain_dim(spec, axis_hits, axis), n_tips=len(tip_names)
    )
    if config.color_tree_by is not None:
        color_mapping = _color.compute_node_color_values(
            root,
            config.color_tree_by,
            auspice_meta=auspice_meta,
            tree_color_scale=config.tree_color_scale,
        )
    else:
        if config.tree_color_scale is not None:
            raise ValueError(
                "tree_color_scale was supplied but color_tree_by is None; "
                "the override only applies when the tree is being colored."
            )
        color_mapping = None
    tree_chart = _build_tree_chart(
        root,
        n_tips=len(tip_names),
        tree_size=config.tree_size,
        strain_dim=strain_dim,
        strain_axis=axis,
        tree_location=location,
        tree_line_width=config.tree_line_width,
        tree_node_size=config.tree_node_size,
        leader_line_width=config.leader_line_width,
        scale_bar=config.scale_bar,
        scale_bar_font_size=config.scale_bar_font_size,
        branch_length=config.branch_length,
        branch_length_units=config.branch_length_units,
        connect_leader_to_label=config.connect_leader_to_label,
        strain_label_font_size=config.strain_label_font_size,
        strain_label_font_weight=config.strain_label_font_weight,
        shift_tree_loc=config.shift_tree_loc,
        tip_names=tip_names,
        color_mapping=color_mapping,
        legend_format=config.tree_color_legend_format,
        legend_show=config.tree_color_legend_show,
    )

    new_chart = copy.deepcopy(chart)
    suppress_axis_chrome = config.connect_leader_to_label
    n_hits = 0
    for ch in _iter_strain_axis_channels(new_chart, config.chart_strain_field):
        ch.sort = list(tip_names)
        if suppress_axis_chrome:
            ch.axis = alt.Axis(labels=False, ticks=False, domain=False, title=None)
        n_hits += 1
    _check_walker_hits("strain-axis update", n_hits, len(axis_hits), axis)
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
    """Concat tree and chart in the order implied by the tree's location.

    The strain axis is resolved independent so the tree and chart can use
    different scales on that axis (the tree's branch length vs. the chart's
    measurement value), while still sharing the orthogonal strain axis. The
    `color` scale is also resolved independent: when ``color_tree_by`` is set
    the tree panel emits a `color_value:N` color scale with a tree-specific
    domain, and Vega-Lite's default of sharing color across concat views
    would merge it with any color encoding on the user's chart, hiding
    user-chart marks whose color values aren't in the tree's domain.
    """
    if location == "left":
        return alt.hconcat(tree_chart, user_chart, spacing=0).resolve_scale(
            y="independent", color="independent"
        )
    if location == "right":
        return alt.hconcat(user_chart, tree_chart, spacing=0).resolve_scale(
            y="independent", color="independent"
        )
    if location == "top":
        return alt.vconcat(tree_chart, user_chart, spacing=0).resolve_scale(
            x="independent", color="independent"
        )
    if location == "bottom":
        return alt.vconcat(user_chart, tree_chart, spacing=0).resolve_scale(
            x="independent", color="independent"
        )
    raise ValueError(f"unreachable: tree_location={location!r}")


def _ensure_tree(
    tree: str | Path | dict | _tree.TreeNode,
    tree_strain_field: str,
    *,
    branch_length: str,
    strict_version: bool,
) -> tuple[_tree.TreeNode, dict | None]:
    """Return ``(root, auspice_meta)``.

    ``auspice_meta`` is the loaded Auspice JSON's top-level ``meta`` dict, or
    ``None`` when the caller passed a pre-built ``TreeNode`` (in which case
    we have no JSON to read ``meta.colorings`` from, and color resolution
    falls back to the default palette).
    """
    if isinstance(tree, _tree.TreeNode):
        return tree, None
    return _tree.load_auspice_with_meta(
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


_TARGET_VEGA_LITE_MAJOR = 6


def _check_chart_schema_version(spec: dict, *, strict_version: bool) -> None:
    """Inspect spec['$schema'] and react to mismatched Vega-Lite versions.

    Three regimes:
      - Vega-Lite < 6  → known incompatible. Raises under strict_version
        (the default); warns under strict_version=False.
      - Vega-Lite = 6  → the version this package was built against.
        Silent.
      - Vega-Lite > 6  → newer than tested. We don't know whether it
        works, but Vega-Lite tends to be backward-compatible so we
        proceed and warn (regardless of strict_version). The user can
        silence the warning via the `warnings` module if needed.

    Missing or unrecognized $schema URLs always warn and proceed.
    """
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
    if major < _TARGET_VEGA_LITE_MAJOR:
        msg = (
            f"chart spec was saved with Vega-Lite {major} (likely altair "
            f"{major - 1}); please re-save it from an altair "
            f"{_TARGET_VEGA_LITE_MAJOR}+ environment with `chart.save(...)`."
        )
        if strict_version:
            raise ValueError(msg)
        warnings.warn(msg, stacklevel=3)
    elif major > _TARGET_VEGA_LITE_MAJOR:
        warnings.warn(
            f"chart spec was saved with Vega-Lite {major}, newer than this "
            f"package targets (Vega-Lite {_TARGET_VEGA_LITE_MAJOR}). Most "
            "things should still work because Vega-Lite is largely "
            "backward-compatible, but if rendering looks wrong please "
            "file an issue.",
            stacklevel=3,
        )


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


def _check_walker_hits(operation: str, actual: int, expected: int, axis: str) -> None:
    """Cross-check the live-object walk's hit count against the spec walk's.

    `_find_strain_encoding` walks the chart's serialized dict form to count
    how many `x`/`y` strain encodings the chart has and to validate
    consistency (axis agreement, type=nominal/ordinal, etc.). The live
    iteration in `_build` (driven by `_iter_strain_axis_channels`) must
    visit exactly the same number of encodings — fewer would silently skip
    applying the tree's tip order (or the axis suppression) to part of the
    chart, more would mean we mutated structures the dict walker doesn't
    know about.

    The check is symmetric (`!=`) rather than one-sided (`<`) because
    either direction signals that spec-level introspection and
    live-object traversal have diverged, and continuing would render an
    unverified chart.
    """
    if actual != expected:
        raise RuntimeError(
            f"internal consistency check failed for {operation!r}: "
            f"_find_strain_encoding located {expected} strain {axis!r}-axis "
            f"encoding(s) in the chart spec, but the live-object walk "
            f"updated {actual}. Spec-level and live-object traversal have "
            "diverged, which would render the chart with a wrong tip order "
            "or leave axis chrome behind. Please file a bug at "
            "https://github.com/jbloomlab/tree-annotated-plot/issues with a "
            "minimal reproducer."
        )


def _iter_strain_axis_channels(node: Any, chart_strain_field: str) -> Iterator[Any]:
    """Yield every live x/y channel object whose field matches
    `chart_strain_field`.

    Pure read — no mutation, no count. The caller iterates and applies
    whatever mutation it needs (currently `sort` and, when
    `connect_leader_to_label=True`, an axis-suppression `alt.Axis(...)`),
    counting hits as it goes so the cross-check in `_check_walker_hits`
    can compare against the spec walker.

    Walks the live altair object tree (Chart / LayerChart / FacetChart /
    HConcatChart / VConcatChart / ConcatChart) rather than its dict form,
    because altair's to_dict / from_dict round-trip introduces internal
    annotations (e.g. params[].views) and class-dispatch issues that the
    dict approach has to fight. Modifying the object in place is robust as
    long as altair's container attribute names hold (.hconcat / .vconcat /
    .concat / .layer / .spec / .encoding), which is stable in altair 5+.
    `FacetChart.spec` is recursed into unconditionally so we descend to the
    inner LayerChart / Chart that actually carries the encoding (gating on
    `spec.encoding is not None` would skip LayerCharts, whose encodings
    live on their layers rather than at the top level).
    """
    enc = _live_attr(node, "encoding")
    if enc is not None:
        for channel in ("x", "y"):
            ch = _live_attr(enc, channel)
            if ch is not None and _channel_field(ch) == chart_strain_field:
                yield ch
    for attr in ("hconcat", "vconcat", "concat", "layer"):
        sub = _live_attr(node, attr)
        if isinstance(sub, list):
            for s in sub:
                yield from _iter_strain_axis_channels(s, chart_strain_field)
    spec = _live_attr(node, "spec")
    if spec is not None:
        yield from _iter_strain_axis_channels(spec, chart_strain_field)


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
    autosize, background, datasets, usermeta) that are non-Undefined.

    Vega-Lite forbids these properties on subspecs; altair enforces this in
    `_check_if_valid_subspec` (or in `to_dict` validation for some keys).
    We move them onto the outer HConcatChart we build. `datasets` in
    particular shows up here only when the user passed a JSON / HTML / dict
    chart — `alt.Chart.from_dict(...)` parks the data dict at the top
    level, but the outer hconcat we wrap it in won't serialize cleanly
    with `datasets` on a subspec.
    """
    config = chart._kwds.pop("config", alt.Undefined)
    other: dict = {}
    for k in ("$schema", "padding", "autosize", "background", "datasets", "usermeta"):
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

    Returns the field name when the channel references a data field (either
    via the `field=` keyword or via positional shorthand like
    `alt.Y("strain")` / `alt.Y("strain:N")` / `alt.Y("mean(titer):Q")`).
    Returns `None` when the channel has no field at all (a `value=` /
    `datum=` constant encoding). Raises `ValueError` when the channel's
    `_kwds` shape is unrecognized — silent fallthrough hid a real bug
    where untyped shorthand axes were never reordered to match the tree.

    Reads `ch._kwds` directly rather than going through `ch.to_dict()`:
    altair's `to_dict()` on a bare channel raises when the shorthand has
    no explicit type (e.g. `alt.Y("strain")`), because the `nominal` /
    `quantitative` inference needs the chart's data context. That
    exception is what the previous catch-all hid.
    """
    kwds = getattr(ch, "_kwds", None)
    if not isinstance(kwds, dict):
        raise ValueError(
            f"channel object {type(ch).__name__} has no `_kwds` mapping; "
            "this isn't a recognized altair channel encoding."
        )
    field = kwds.get("field")
    if field is not None and field is not alt.Undefined:
        # `from_dict`-roundtripped channels store the field as a
        # `FieldName(SchemaBase)` wrapper rather than a plain str; its
        # `to_dict()` returns the raw string, while `str(...)` returns the
        # repr `FieldName('x')`. Cover both.
        if isinstance(field, str):
            if field:
                return field
        elif hasattr(field, "to_dict"):
            unwrapped = field.to_dict()
            if isinstance(unwrapped, str) and unwrapped:
                return unwrapped
            raise ValueError(
                f"channel field wrapper {type(field).__name__} unwrapped "
                f"to {unwrapped!r}; expected a non-empty string."
            )
        else:
            raise ValueError(
                f"channel field has unexpected value {field!r} "
                f"(type {type(field).__name__}); expected a string."
            )
    shorthand = kwds.get("shorthand")
    if shorthand is None or shorthand is alt.Undefined:
        return None
    if not isinstance(shorthand, str) or not shorthand:
        raise ValueError(
            f"channel shorthand has unexpected value {shorthand!r}; "
            "expected a string like 'strain', 'strain:N', or "
            "'mean(strain):Q'."
        )
    # Shorthand grammar: '[<aggregate>(]<field>[)][:<type>]'.
    bare = shorthand.split(":", 1)[0]
    if "(" in bare:
        if not bare.endswith(")"):
            raise ValueError(
                f"channel shorthand {shorthand!r} has an unbalanced "
                "aggregate wrapper; expected 'aggregate(field)[:type]'."
            )
        bare = bare[bare.index("(") + 1 : -1]
    if not bare:
        raise ValueError(
            f"channel shorthand {shorthand!r} parsed to an empty field name."
        )
    return bare


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
    font_size: float = 10.0,
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
            .mark_text(fontSize=font_size, align="center", baseline="top")
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
            .mark_text(fontSize=font_size, align="center", baseline="middle", angle=270)
            .encode(y="x:Q", x="y:Q", text="label:N")
        )
    return bar + text


_LABEL_PAD_PX_MIN = 4
_LABEL_PAD_RATIO = 0.4  # `LABEL_PAD_PX = max(MIN, font_size * RATIO)`
_LABEL_CHAR_PX_RATIO = 0.6  # rough proportional sans-serif glyph-width estimate
_LABEL_HALO_RATIO = 0.6  # white-halo strokeWidth as a fraction of font_size


def _build_tree_chart(
    root: _tree.TreeNode,
    *,
    n_tips: int,
    tree_size: int,
    strain_dim: int | float | alt.Step,
    strain_axis: str,
    tree_location: TreeLocation,
    tree_line_width: float = 2.0,
    tree_node_size: float = 45,
    leader_line_width: float = 1.0,
    scale_bar: bool = False,
    scale_bar_font_size: float = 10.0,
    branch_length: str = "div",
    branch_length_units: str | None = None,
    connect_leader_to_label: bool = False,
    strain_label_font_size: float = 10.0,
    strain_label_font_weight: str = "normal",
    shift_tree_loc: int = 0,
    tip_names: list[str] | None = None,
    color_mapping: _color.ColorMapping | None = None,
    legend_format: dict[str, Any] | None = None,
    legend_show: bool = True,
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
    if tree_line_width < 0:
        raise ValueError(f"tree_line_width must be >= 0, got {tree_line_width}")
    if tree_node_size < 0:
        raise ValueError(f"tree_node_size must be >= 0, got {tree_node_size}")
    if leader_line_width < 0:
        raise ValueError(f"leader_line_width must be >= 0, got {leader_line_width}")

    seg_df = _tree.segments(root)
    tips_df = pd.DataFrame(
        [{"name": t.name, "x": t.x, "y": t.y} for t in _tree.tips(root)]
    )
    branch_max = float(seg_df[["x", "x2"]].max().max())
    branch_min = float(seg_df[["x", "x2"]].min().min())

    # When color_tree_by is set, attach the per-node color category to both
    # frames. The `mark_rule` for branches (one row per `seg_df` segment) and
    # the `mark_circle` for tips share the same color encoding so Altair
    # collapses them into a single legend at the bottom.
    if color_mapping is not None:
        seg_df = seg_df.assign(
            color_value=seg_df["color_node"].map(color_mapping.values_by_node)
        )
        tips_df = tips_df.assign(
            color_value=tips_df["name"].map(color_mapping.values_by_node)
        )
        # Defaults the user can override by passing the same key in
        # `legend_format`. Title comes from the color mapping's derived
        # title (e.g. "subclade" or "HA1 site 158"); orient defaults to
        # bottom to match the docs.
        legend_kwargs: dict = {
            "title": color_mapping.legend_title,
            "orient": "bottom",
        }
        if legend_format is not None:
            legend_kwargs.update(legend_format)
        if color_mapping.legend_values is not None:
            # Restrict the legend display without touching the scale, so
            # internal-node segments still render gray when "unknown" is on
            # the tree but no tip is.
            legend_kwargs["values"] = list(color_mapping.legend_values)
        # Smart default for vertical stacking: when the (final) orient
        # places the legend on the chart's left or right edge and the user
        # has not explicitly set `columns` or `direction`, force columns=1.
        # This counteracts a chart-level config default of `legend.columns`
        # > 1 (some altair theme presets set this), which would otherwise
        # pack a side-anchored legend into multiple columns.
        if (
            legend_kwargs.get("orient") in _VERTICAL_ORIENTS
            and "columns" not in legend_kwargs
            and "direction" not in legend_kwargs
        ):
            legend_kwargs["columns"] = 1
        if not legend_show:
            legend_arg: alt.Legend | None = None
        else:
            legend_arg = alt.Legend(**legend_kwargs)
        color_enc = alt.Color(
            "color_value:N",
            scale=alt.Scale(
                domain=list(color_mapping.domain),
                range=list(color_mapping.range_),
            ),
            legend=legend_arg,
        )
    else:
        color_enc = None

    # When connect_leader_to_label is on:
    #   - All leaders extend to a single point: the panel's chart-facing edge
    #     (`chart_edge_branch`).
    #   - Each label is rendered as TWO `mark_text` layers stacked at the
    #     same position: a white "halo" layer (white fill + thick white
    #     stroke) drawn first, then the visible black text on top. The halo
    #     follows the actual rendered glyph outline — auto-sized to the
    #     text — and masks the dashed leader behind each label without any
    #     width estimation. Vega-Lite doesn't expose `paintOrder`, so the
    #     two-layer trick stands in for a single text-with-halo mark.
    #   - `shift_tree_loc` (pixels) shrinks the strip — bringing the tree
    #     visually closer to the labels — by reducing the data-units between
    #     branch_max and chart_edge_branch. The tree's tree_size-pixel
    #     allocation is unchanged.
    # When connect_leader_to_label is off, the chart's natural strain-axis
    # labels are kept and leaders stop at branch_max (the prior behavior).
    halo_px = max(2.0, strain_label_font_size * _LABEL_HALO_RATIO)
    if connect_leader_to_label:
        names = tip_names if tip_names is not None else list(tips_df["name"])
        max_name_len = max((len(n) for n in names), default=0)
        char_px = strain_label_font_size * _LABEL_CHAR_PX_RATIO
        label_pad_px = max(_LABEL_PAD_PX_MIN, strain_label_font_size * _LABEL_PAD_RATIO)
        # Strip needs to fit the longest label plus `halo_px / 2` of halo
        # extension on the leader-facing side, plus a small fixed pad.
        label_pixel_width = label_pad_px + max_name_len * char_px + halo_px / 2
        strip_pixel_width = label_pixel_width - shift_tree_loc
        if strip_pixel_width <= 0:
            raise ValueError(
                f"shift_tree_loc={shift_tree_loc} eliminates the label strip "
                f"(estimated label_pixel_width={label_pixel_width:.1f}); "
                "reduce shift_tree_loc, lower strain_label_font_size, or "
                "shorten the longest strain name."
            )
        branch_span = branch_max - branch_min
        per_pixel = branch_span / tree_size if tree_size else 0.0
        extra_branch_units = strip_pixel_width * per_pixel
        chart_edge_branch = branch_max + extra_branch_units
        tips_df = tips_df.assign(x_label=chart_edge_branch)
        leader_df = tips_df[tips_df["x"] < chart_edge_branch].assign(
            x2=chart_edge_branch
        )
        extended_tree_size = tree_size + strip_pixel_width
    else:
        chart_edge_branch = branch_max
        leader_df = tips_df[tips_df["x"] < branch_max].assign(x2=branch_max)
        extended_tree_size = tree_size

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
            font_size=scale_bar_font_size,
        )
    else:
        extra_units = 0.0
        extended_strain_dim = strain_dim
        scale_bar_layer = None

    if strain_axis == "y":
        # Vertical: branch axis on chart x; tip axis with tip 0 on top.
        # When connect_leader_to_label is on, the branch domain is extended
        # past `branch_max` to `chart_edge_branch` so the label strip has
        # data-units to occupy; tips at `branch_max` still sit at pixel
        # `tree_size` on the panel. Each label's chart-facing edge is
        # anchored at `chart_edge_branch` and aligned outward (right for
        # tree on the left, left for tree on the right).
        if tree_location == "left":
            branch_domain = [branch_min, chart_edge_branch]
            text_align = "right"
        else:
            branch_domain = [chart_edge_branch, branch_min]
            text_align = "left"
        branch_scale = alt.Scale(domain=branch_domain, nice=False, zero=False)
        # tip-axis domain[0] (at panel bottom) extends past last tip when
        # scale_bar=True; tip i still sits at the same on-screen pixel.
        tip_scale = alt.Scale(
            domain=[n_tips - 0.5 + extra_units, -0.5], nice=False, zero=False
        )
        branch_enc = alt.X("x:Q", axis=None, scale=branch_scale)
        tip_enc = alt.Y("y:Q", axis=None, scale=tip_scale)
        layers: list[alt.Chart] = []
        if leader_line_width > 0:
            layers.append(
                alt.Chart(leader_df)
                .mark_rule(
                    stroke="#888",
                    strokeWidth=leader_line_width,
                    strokeDash=[2, 2],
                )
                .encode(x=branch_enc, x2="x2:Q", y=tip_enc)
            )
        seg_enc_kwargs: dict = {
            "x": branch_enc,
            "x2": "x2:Q",
            "y": tip_enc,
            "y2": "y2:Q",
        }
        if color_enc is not None:
            seg_enc_kwargs["color"] = color_enc
        layers.append(
            alt.Chart(seg_df)
            .mark_rule(strokeWidth=tree_line_width, opacity=1.0)
            .encode(**seg_enc_kwargs)
        )
        if tree_node_size > 0:
            tip_enc_kwargs: dict = {
                "x": branch_enc,
                "y": tip_enc,
                "tooltip": alt.Tooltip("name:N", title="strain"),
            }
            tip_mark_kwargs: dict = {"size": tree_node_size, "opacity": 1.0}
            if color_enc is None:
                tip_mark_kwargs["color"] = "black"
            else:
                tip_enc_kwargs["color"] = color_enc
            layers.append(
                alt.Chart(tips_df)
                .mark_circle(**tip_mark_kwargs)
                .encode(**tip_enc_kwargs)
            )
        # Strain text label, drawn as two stacked layers: a white halo
        # (white fill + thick white stroke) under the visible text. The
        # halo auto-sizes to the rendered glyphs.
        if connect_leader_to_label:
            label_text_enc = dict(
                x=alt.X("x_label:Q", scale=branch_scale, axis=None),
                y=tip_enc,
                text="name:N",
            )
            layers.append(
                alt.Chart(tips_df)
                .mark_text(
                    align=text_align,
                    baseline="middle",
                    fontSize=strain_label_font_size,
                    fontWeight=strain_label_font_weight,
                    fill="white",
                    stroke="white",
                    strokeWidth=halo_px,
                    strokeJoin="round",
                )
                .encode(**label_text_enc)
            )
            layers.append(
                alt.Chart(tips_df)
                .mark_text(
                    align=text_align,
                    baseline="middle",
                    fontSize=strain_label_font_size,
                    fontWeight=strain_label_font_weight,
                )
                .encode(**label_text_enc)
            )
        if scale_bar_layer is not None:
            layers.append(scale_bar_layer)
        layered = alt.layer(*layers)
        layered = layered.properties(
            width=extended_tree_size, height=extended_strain_dim
        )
    elif strain_axis == "x":
        # Horizontal: branch axis on chart y (Vega-Lite default has domain[1]
        # at the top); tip axis with tip 0 on the left.
        # tree_location="top" → root at top → branch_max at bottom (label
        # strip at bottom, opposite the chart above).
        # tree_location="bottom" → root at bottom → branch_max at top (label
        # strip at top, opposite the chart below).
        # Each label's chart-facing edge is anchored at `chart_edge_branch`.
        # The text mark is rotated 270° (reads bottom-to-top), which maps
        # pre-rotation `align="right"` to a top anchor (text extends down)
        # and `align="left"` to a bottom anchor (text extends up). For tree
        # on the bottom, the chart-facing edge is the panel's top → "right".
        # For tree on the top, it's the panel's bottom → "left".
        if tree_location == "top":
            branch_domain = [chart_edge_branch, branch_min]
            text_align = "left"
        else:
            branch_domain = [branch_min, chart_edge_branch]
            text_align = "right"
        branch_scale = alt.Scale(domain=branch_domain, nice=False, zero=False)
        # tip-axis domain[1] (at panel right) extends past last tip when
        # scale_bar=True.
        tip_scale = alt.Scale(
            domain=[-0.5, n_tips - 0.5 + extra_units], nice=False, zero=False
        )
        branch_enc = alt.Y("x:Q", axis=None, scale=branch_scale)
        tip_enc = alt.X("y:Q", axis=None, scale=tip_scale)
        layers = []
        if leader_line_width > 0:
            layers.append(
                alt.Chart(leader_df)
                .mark_rule(
                    stroke="#888",
                    strokeWidth=leader_line_width,
                    strokeDash=[2, 2],
                )
                .encode(y=branch_enc, y2="x2:Q", x=tip_enc)
            )
        seg_enc_kwargs = {
            "y": branch_enc,
            "y2": "x2:Q",
            "x": tip_enc,
            "x2": "y2:Q",
        }
        if color_enc is not None:
            seg_enc_kwargs["color"] = color_enc
        layers.append(
            alt.Chart(seg_df)
            .mark_rule(strokeWidth=tree_line_width, opacity=1.0)
            .encode(**seg_enc_kwargs)
        )
        if tree_node_size > 0:
            tip_enc_kwargs = {
                "y": branch_enc,
                "x": tip_enc,
                "tooltip": alt.Tooltip("name:N", title="strain"),
            }
            tip_mark_kwargs = {"size": tree_node_size, "opacity": 1.0}
            if color_enc is None:
                tip_mark_kwargs["color"] = "black"
            else:
                tip_enc_kwargs["color"] = color_enc
            layers.append(
                alt.Chart(tips_df)
                .mark_circle(**tip_mark_kwargs)
                .encode(**tip_enc_kwargs)
            )
        # Strain text label as halo + visible text (see vertical-layout
        # comment above).
        if connect_leader_to_label:
            label_text_enc = dict(
                y=alt.Y("x_label:Q", scale=branch_scale, axis=None),
                x=tip_enc,
                text="name:N",
            )
            layers.append(
                alt.Chart(tips_df)
                .mark_text(
                    align=text_align,
                    baseline="middle",
                    angle=270,
                    fontSize=strain_label_font_size,
                    fontWeight=strain_label_font_weight,
                    fill="white",
                    stroke="white",
                    strokeWidth=halo_px,
                    strokeJoin="round",
                )
                .encode(**label_text_enc)
            )
            layers.append(
                alt.Chart(tips_df)
                .mark_text(
                    align=text_align,
                    baseline="middle",
                    angle=270,
                    fontSize=strain_label_font_size,
                    fontWeight=strain_label_font_weight,
                )
                .encode(**label_text_enc)
            )
        if scale_bar_layer is not None:
            layers.append(scale_bar_layer)
        layered = alt.layer(*layers)
        layered = layered.properties(
            width=extended_strain_dim, height=extended_tree_size
        )
    else:
        raise ValueError(f"strain_axis must be 'x' or 'y', got {strain_axis!r}")

    # Suppress the panel border on the tree itself. This is a panel-level
    # Vega-Lite `view` property, which overrides any inherited
    # `config.view.stroke` (e.g. if the user's chart was built with
    # `.configure_view(stroke="black")`, that stroke applies to the chart
    # panel but not to the tree).
    layered._kwds["view"] = alt.ViewBackground(stroke=None)
    return layered
