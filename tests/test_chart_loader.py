"""Tests for `_load_chart` and the version-compat checks.

`_load_chart` accepts a live Altair chart, a path to a saved Vega-Lite JSON
(`*.json`) or HTML (`*.html`), or a parsed spec dict. The version check
inspects the spec's `$schema` URL and (separately, in `_tree.py`) the
Auspice top-level `version` field; under `strict_version=True` (default)
non-v6 Vega-Lite or non-v2 Auspice raises, with `strict_version=False`
they warn and proceed.
"""

from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import pandas as pd
import pytest

from tree_annotated_plot import _tree
from tree_annotated_plot._plot import (
    _extract_spec_from_html,
    _load_chart,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "examples" / "data"


# ---------- _load_chart input dispatch ----------


def _flat_chart() -> alt.Chart:
    return (
        alt.Chart(pd.DataFrame({"strain": ["A", "B"], "titer": [1.0, 2.0]}))
        .mark_circle()
        .encode(x="titer:Q", y=alt.Y("strain:N"))
        .properties(width=200, height=200)
    )


def test_load_chart_passes_live_altair_through_unchanged() -> None:
    chart = _flat_chart()
    out = _load_chart(chart, strict_version=True)
    assert out is chart


def test_load_chart_dispatches_dict() -> None:
    spec = _flat_chart().to_dict()
    out = _load_chart(spec, strict_version=True)
    assert isinstance(out, alt.Chart)


def test_load_chart_dispatches_json_path(tmp_path: Path) -> None:
    chart = _flat_chart()
    target = tmp_path / "chart.json"
    chart.save(str(target))
    out = _load_chart(str(target), strict_version=True)
    assert isinstance(out, alt.Chart)


def test_load_chart_unsupported_extension_raises(tmp_path: Path) -> None:
    target = tmp_path / "chart.png"
    target.write_bytes(b"not a chart")
    with pytest.raises(ValueError, match="unsupported chart file extension"):
        _load_chart(str(target), strict_version=True)


def test_load_chart_unsupported_input_type_raises() -> None:
    with pytest.raises(TypeError, match="must be a live Altair chart"):
        _load_chart(42, strict_version=True)  # type: ignore[arg-type]


# ---------- HTML extraction ----------


def test_html_extraction_synthetic_round_trip(tmp_path: Path) -> None:
    """HTML extraction should produce a spec dict equivalent to the JSON-saved
    sibling for the same chart."""
    chart = _flat_chart()
    html_path = tmp_path / "chart.html"
    json_path = tmp_path / "chart.json"
    chart.save(str(html_path))
    chart.save(str(json_path))

    extracted = _extract_spec_from_html(html_path.read_text())
    with json_path.open() as f:
        from_json = json.load(f)

    # The two saves are independent calls to to_dict and may differ on
    # transient details (auto-generated dataset names, params name suffixes).
    # The strain encoding shape is what we care about — confirm it round-trips.
    assert extracted.get("$schema") == from_json.get("$schema")
    assert extracted["encoding"]["y"]["field"] == "strain"
    assert from_json["encoding"]["y"]["field"] == "strain"


def test_html_extraction_real_h3n2_matches_json_sibling() -> None:
    """For the real Kikawa H3N2 saved chart, the extracted spec must agree
    with the JSON sibling on the strain-axis sort. Both files are generated
    by the same chart-builder script."""
    html = DATA_DIR / "flu-seqneut-2025to2026_H3N2_titers.html"
    js = DATA_DIR / "flu-seqneut-2025to2026_H3N2_titers.json"
    if not (html.exists() and js.exists()):
        pytest.skip("run examples/flu-seqneut-2025to2026_titer_charts.py first")

    extracted = _extract_spec_from_html(html.read_text())
    with js.open() as f:
        from_json = json.load(f)

    # Same shape at the strain encoding.
    e = extracted["vconcat"][0]["spec"]["layer"][0]["encoding"]["y"]
    j = from_json["vconcat"][0]["spec"]["layer"][0]["encoding"]["y"]
    assert e["field"] == "axis_label"
    assert j["field"] == "axis_label"
    assert e["sort"] == j["sort"]


def test_html_extraction_no_var_spec_raises(tmp_path: Path) -> None:
    """Custom altair templates without `var spec = {...}` get a clear error
    pointing the user at JSON."""
    bad = tmp_path / "weird.html"
    bad.write_text(
        "<!DOCTYPE html><html><body>"
        "<script>const otherVar = 42;</script>"
        "</body></html>"
    )
    with pytest.raises(ValueError, match="non-default altair template"):
        _extract_spec_from_html(bad.read_text())


def test_html_extraction_takes_first_when_multiple_blocks(tmp_path: Path) -> None:
    """Documented limit: a page with multiple `var spec = {...}` blocks
    yields the first one. (Unusual case; users can split charts into
    separate files.)"""
    multi = (
        "<!DOCTYPE html><html><body>"
        '<script>var spec = {"a": 1};</script>'
        '<script>var spec = {"b": 2};</script>'
        "</body></html>"
    )
    extracted = _extract_spec_from_html(multi)
    assert extracted == {"a": 1}


# ---------- Vega-Lite $schema version check ----------


def _stale_schema_spec() -> dict:
    """A minimal-but-valid spec carrying a Vega-Lite v5 schema URL."""
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": [{"strain": "A", "titer": 1}]},
        "mark": "circle",
        "encoding": {
            "x": {"field": "titer", "type": "quantitative"},
            "y": {"field": "strain", "type": "nominal"},
        },
    }


def test_strict_version_rejects_vega_lite_v5_chart() -> None:
    with pytest.raises(ValueError, match="Vega-Lite 5"):
        _load_chart(_stale_schema_spec(), strict_version=True)


def test_loose_version_warns_on_vega_lite_v5_chart() -> None:
    with pytest.warns(UserWarning, match="Vega-Lite 5"):
        out = _load_chart(_stale_schema_spec(), strict_version=False)
    assert isinstance(out, alt.Chart)


def test_missing_chart_schema_warns() -> None:
    spec = {
        "data": {"values": [{"strain": "A", "titer": 1}]},
        "mark": "circle",
        "encoding": {
            "x": {"field": "titer", "type": "quantitative"},
            "y": {"field": "strain", "type": "nominal"},
        },
    }
    with pytest.warns(UserWarning, match="no \\$schema"):
        _load_chart(spec, strict_version=True)


def test_vega_lite_newer_than_target_always_warns() -> None:
    """Vega-Lite > 6 (a hypothetical future schema) is untested but
    probably backward-compatible. We warn but never raise — strict_version
    has no effect on this case (the flag controls known-stale, not
    newer-than-tested)."""
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v9.json",
        "data": {"values": [{"strain": "A", "titer": 1}]},
        "mark": "circle",
        "encoding": {
            "x": {"field": "titer", "type": "quantitative"},
            "y": {"field": "strain", "type": "nominal"},
        },
    }
    # Default strict_version=True still warns rather than raising.
    with pytest.warns(UserWarning, match="newer than this package"):
        out = _load_chart(spec, strict_version=True)
    assert isinstance(out, alt.Chart)
    # And strict_version=False also just warns.
    with pytest.warns(UserWarning, match="newer than this package"):
        _load_chart(spec, strict_version=False)


def test_unrecognized_chart_schema_warns() -> None:
    spec = {
        "$schema": "https://example.com/not-a-vega-schema.json",
        "data": {"values": [{"strain": "A", "titer": 1}]},
        "mark": "circle",
        "encoding": {
            "x": {"field": "titer", "type": "quantitative"},
            "y": {"field": "strain", "type": "nominal"},
        },
    }
    with pytest.warns(UserWarning, match="does not look like a Vega-Lite"):
        _load_chart(spec, strict_version=True)


# ---------- Auspice tree version check ----------


def _stale_auspice_dict() -> dict:
    """A minimal Auspice-shaped JSON whose version field is v1 (the Auspice
    pre-v2 format we no longer support)."""
    return {
        "version": "v1",
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [
                {"name": "A", "node_attrs": {"div": 0.01}},
                {"name": "B", "node_attrs": {"div": 0.02}},
            ],
        },
    }


def test_strict_version_rejects_auspice_v1() -> None:
    with pytest.raises(ValueError, match="version='v1'"):
        _tree.load_auspice(
            _stale_auspice_dict(),
            tree_strain_field="name",
            strict_version=True,
        )


def test_loose_version_warns_on_auspice_v1() -> None:
    with pytest.warns(UserWarning, match="version='v1'"):
        root = _tree.load_auspice(
            _stale_auspice_dict(),
            tree_strain_field="name",
            strict_version=False,
        )
    assert root.name == "ROOT"


def test_missing_auspice_version_warns() -> None:
    no_version = {
        "meta": {},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [{"name": "A", "node_attrs": {"div": 0.01}}],
        },
    }
    with pytest.warns(UserWarning, match="no top-level 'version'"):
        _tree.load_auspice(no_version, tree_strain_field="name", strict_version=True)
