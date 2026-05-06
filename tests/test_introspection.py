"""Tests for the chart-introspection layer (axis-finding + axis-check).

Covers `_find_strain_encoding` against both the synthetic case and the real
Kikawa H3N2 (vertical) / H1N1 (horizontal) saved-chart JSONs. Negative cases
exercise the four axis-check rules: zero hits, secondary-only hits, mixed
axes across panels, non-categorical type.
"""

from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import pandas as pd
import pytest

from tree_annotated_plot._plot import _channel_field, _find_strain_encoding

DATA_DIR = Path(__file__).resolve().parent.parent / "examples" / "data"


def _load_or_skip(path: Path, hint: str) -> dict:
    if not path.exists():
        pytest.skip(f"{path.name} not present; run `{hint}` to generate it")
    with path.open() as f:
        return json.load(f)


def _flat_chart_spec(*, axis: str = "y", typ: str = "nominal") -> dict:
    chart = (
        alt.Chart(pd.DataFrame({"strain": ["A", "B"], "titer": [1.0, 2.0]}))
        .mark_circle()
        .encode(
            **{
                axis: (
                    alt.Y(f"strain:{typ[0].upper()}")
                    if axis == "y"
                    else alt.X(f"strain:{typ[0].upper()}")
                ),
                "y" if axis == "x" else "x": "titer:Q",
            }
        )
    )
    return chart.to_dict()


def test_find_strain_encoding_flat_chart_y() -> None:
    spec = _flat_chart_spec(axis="y")
    hits = _find_strain_encoding(spec, "strain")
    assert len(hits) == 1
    path, enc, channel = hits[0]
    assert channel == "y"
    assert enc.get("field") == "strain"
    assert path[-2:] == ("encoding", "y")


def test_find_strain_encoding_secondary_hits_are_ignored() -> None:
    """A chart with `strain` on y AND on tooltip is fine — we only validate
    axis hits."""
    spec = (
        alt.Chart(pd.DataFrame({"strain": ["A", "B"], "titer": [1.0, 2.0]}))
        .mark_circle()
        .encode(
            x="titer:Q",
            y=alt.Y("strain:N"),
            tooltip=[alt.Tooltip("strain:N")],
        )
        .to_dict()
    )
    hits = _find_strain_encoding(spec, "strain")
    assert len(hits) == 1
    assert hits[0][2] == "y"


def test_find_strain_encoding_real_h3n2_chart_finds_y_in_layered_facet() -> None:
    """The H3N2 chart is VConcatChart(FacetChart(LayerChart, dummy_cohort)).
    Both layers in the LayerChart encode `axis_label` on y; the dummy_cohort
    panel doesn't reference the field at all. Both axis hits should agree on
    'y' and on type='nominal'."""
    spec = _load_or_skip(
        DATA_DIR / "flu-seqneut-2025to2026_H3N2_titers.json",
        "python examples/flu-seqneut-2025to2026_titer_charts.py",
    )
    hits = _find_strain_encoding(spec, "axis_label")
    assert len(hits) == 2, "expected one hit per layer in the LayerChart body"
    channels = {h[2] for h in hits}
    assert channels == {"y"}
    types = {h[1].get("type") for h in hits}
    assert types == {"nominal"}


def test_find_strain_encoding_real_h1n1_chart_finds_x() -> None:
    """The H1N1 chart is the same vconcat/facet/layer shape but with the
    strain axis on x (horizontal layout)."""
    spec = _load_or_skip(
        DATA_DIR / "flu-seqneut-2025to2026_H1N1_titers.json",
        "python examples/flu-seqneut-2025to2026_titer_charts.py",
    )
    hits = _find_strain_encoding(spec, "axis_label")
    assert len(hits) == 2
    channels = {h[2] for h in hits}
    assert channels == {"x"}


def test_find_strain_encoding_no_match_raises() -> None:
    spec = _flat_chart_spec()
    with pytest.raises(ValueError, match="not found in any encoding"):
        _find_strain_encoding(spec, "nonexistent_field")


def test_find_strain_encoding_only_on_tooltip_raises() -> None:
    spec = (
        alt.Chart(pd.DataFrame({"strain": ["A"], "titer": [1.0]}))
        .mark_circle()
        .encode(
            x="titer:Q",
            y=alt.Y("titer:Q"),
            tooltip=[alt.Tooltip("strain:N")],
        )
        .to_dict()
    )
    with pytest.raises(ValueError, match="encoded on .*tooltip"):
        _find_strain_encoding(spec, "strain")


def test_find_strain_encoding_mixed_x_and_y_raises() -> None:
    """A LayerChart whose two layers put the same field on different axes
    is ambiguous — we refuse to align."""
    df = pd.DataFrame({"strain": ["A", "B"], "titer": [1.0, 2.0]})
    chart_y = alt.Chart(df).mark_circle().encode(x="titer:Q", y="strain:N")
    chart_x = alt.Chart(df).mark_line().encode(x="strain:N", y="titer:Q")
    layered = (chart_y + chart_x).to_dict()
    with pytest.raises(ValueError, match="encoded on both"):
        _find_strain_encoding(layered, "strain")


def test_find_strain_encoding_quantitative_type_raises() -> None:
    spec = _flat_chart_spec(typ="quantitative")
    with pytest.raises(ValueError, match="type='quantitative'"):
        _find_strain_encoding(spec, "strain")


# ---------- _channel_field: covers the "untyped shorthand" silent-skip bug.


def test_channel_field_typed_shorthand() -> None:
    """`alt.Y('strain:N')` — the form every existing test uses."""
    ch = alt.Y("strain:N")
    assert _channel_field(ch) == "strain"


def test_channel_field_untyped_shorthand() -> None:
    """`alt.Y('strain')` without a type — the form that triggered the
    original silent-skip bug. `to_dict()` on this channel raises because
    type inference needs the chart's data, but we can still recover the
    field from `_kwds['shorthand']`."""
    ch = alt.Y("strain")
    assert _channel_field(ch) == "strain"


def test_channel_field_explicit_field_kwarg() -> None:
    """`alt.Y(field='strain', type='nominal')` — the explicit form."""
    ch = alt.Y(field="strain", type="nominal")
    assert _channel_field(ch) == "strain"


def test_channel_field_after_from_dict_roundtrip() -> None:
    """After `alt.Chart.from_dict(...)` (used by the CLI / JSON / HTML
    chart loaders), the field is stored as a `FieldName(SchemaBase)`
    wrapper, not a plain `str`. The helper must unwrap it."""
    df = pd.DataFrame({"strain": ["A", "B"], "titer": [1.0, 2.0]})
    chart = alt.Chart(df).mark_circle().encode(x="titer:Q", y=alt.Y("strain:N"))
    roundtripped = alt.Chart.from_dict(chart.to_dict())
    assert _channel_field(roundtripped.encoding.y) == "strain"


def test_channel_field_aggregate_shorthand() -> None:
    """`alt.X('mean(titer):Q')` aggregate-wrapped shorthand."""
    ch = alt.X("mean(titer):Q")
    assert _channel_field(ch) == "titer"


def test_channel_field_value_only_returns_none() -> None:
    """A `value=` constant encoding has no field — legitimate None,
    not an error."""
    ch = alt.Y(value=5)
    assert _channel_field(ch) is None


def test_channel_field_unbalanced_aggregate_raises() -> None:
    """A shorthand string we can't parse must raise rather than silently
    return None — silent fallthrough is what hid the original bug."""
    ch = alt.Y("strain")
    ch._kwds["shorthand"] = "mean(titer:Q"
    with pytest.raises(ValueError, match="unbalanced aggregate"):
        _channel_field(ch)


def test_channel_field_non_kwds_object_raises() -> None:
    """A non-altair object accidentally passed in must raise, not return
    None — same fail-fast principle."""

    class NotAChannel:
        pass

    with pytest.raises(ValueError, match="no `_kwds` mapping"):
        _channel_field(NotAChannel())
