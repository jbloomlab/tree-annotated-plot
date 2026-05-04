"""Tests for `PlotConfig` and its single-source contract.

PlotConfig is the canonical home for plot-parameter descriptions. The
function `tree_annotated_plot.plot` and the CLI both consume it. These tests guard the
contract: every field has a non-empty description, and `tree_annotated_plot.plot`'s
keyword arguments stay in sync with PlotConfig's fields.
"""

from __future__ import annotations

import dataclasses
import inspect
import typing

import tree_annotated_plot
from tree_annotated_plot._config import PlotConfig


def test_every_plot_config_field_has_a_description() -> None:
    """Each PlotConfig field's type annotation must be `Annotated[T, "..."]`
    with a non-empty description string."""
    hints = typing.get_type_hints(PlotConfig, include_extras=True)
    for f in dataclasses.fields(PlotConfig):
        annotated = hints[f.name]
        assert hasattr(
            annotated, "__metadata__"
        ), f"PlotConfig.{f.name}: expected Annotated[T, '...'] type"
        meta = annotated.__metadata__
        assert len(meta) >= 1, f"PlotConfig.{f.name}: missing description"
        assert isinstance(
            meta[0], str
        ), f"PlotConfig.{f.name}: description must be a string"
        assert meta[0].strip(), f"PlotConfig.{f.name}: description is empty/whitespace"


def test_plot_signature_matches_plot_config_fields() -> None:
    """`tree_annotated_plot.plot`'s keyword arguments and PlotConfig's fields must be the
    same set. Adding a parameter to one without the other is a regression."""
    sig = inspect.signature(tree_annotated_plot.plot)
    plot_kwargs = {
        name
        for name, p in sig.parameters.items()
        if p.kind in (p.KEYWORD_ONLY, p.POSITIONAL_OR_KEYWORD)
        and name not in ("tree", "chart")
    }
    config_fields = {f.name for f in dataclasses.fields(PlotConfig)}
    assert plot_kwargs == config_fields, (
        f"plot() kwargs vs PlotConfig fields drifted:\n"
        f"  in plot but not config: {plot_kwargs - config_fields}\n"
        f"  in config but not plot: {config_fields - plot_kwargs}"
    )


def test_plot_config_field_defaults_match_plot_signature_defaults() -> None:
    """Same default values on both surfaces, so callers see identical
    behavior whether they instantiate PlotConfig directly or call plot()."""
    sig = inspect.signature(tree_annotated_plot.plot)
    fields_by_name = {f.name: f for f in dataclasses.fields(PlotConfig)}
    for name, param in sig.parameters.items():
        if name in ("tree", "chart"):
            continue
        if param.default is inspect.Parameter.empty:
            # No default in plot() → required → field also has no default.
            assert fields_by_name[name].default is dataclasses.MISSING
        else:
            assert fields_by_name[name].default == param.default, (
                f"default for {name} differs: plot()={param.default!r} vs "
                f"PlotConfig={fields_by_name[name].default!r}"
            )


def test_plot_docstring_assembles_from_plot_config() -> None:
    """`tree_annotated_plot.plot.__doc__` is built at import time from the same Annotated
    descriptions the CLI's --help reads. Every PlotConfig field's name
    and (whitespace-collapsed) description must appear, plus the
    hand-written `tree` and `chart` entries."""
    doc = tree_annotated_plot.plot.__doc__ or ""
    flattened = " ".join(doc.split())

    hints = typing.get_type_hints(PlotConfig, include_extras=True)
    for f in dataclasses.fields(PlotConfig):
        assert f.name in doc, f"field {f.name!r} missing from plot docstring"
        description = " ".join(hints[f.name].__metadata__[0].split())
        assert description in flattened, (
            f"description for {f.name!r} not found in plot docstring "
            "(textwrap may have broken a token unexpectedly)"
        )

    # Hand-written entries.
    assert "\ntree\n" in doc, "`tree` parameter missing from plot docstring"
    assert "\nchart\n" in doc, "`chart` parameter missing from plot docstring"
    assert "Returns" in doc, "Returns section missing from plot docstring"
