"""Tests for the `tree-annotated-plot` CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from tree_annotated_plot.cli import main

DATA_DIR = Path(__file__).resolve().parent.parent / "examples" / "data"


def _runner() -> CliRunner:
    return CliRunner()


def test_help_lists_data_options() -> None:
    """--help should show the three CLI-specific data options."""
    result = _runner().invoke(main, ["--help"])
    assert result.exit_code == 0
    # Trailing space distinguishes from --chart-strain-field /
    # --tree-strain-field, which contain --chart and --tree as substrings.
    assert "--tree " in result.output
    assert "--chart " in result.output
    assert "--output" in result.output


def test_help_lists_auto_generated_options() -> None:
    """A handful of PlotConfig-derived options should appear in --help."""
    result = _runner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for opt in (
        "--chart-strain-field",
        "--tree-strain-field",
        "--branch-length",
        "--tree-size",
        "--tree-location",
        "--tree-line-width",
        "--scale-bar / --no-scale-bar",
        "--strict-version / --no-strict-version",
    ):
        assert opt in result.output, f"missing option in --help: {opt}"


def test_help_lists_required_options_before_defaulted() -> None:
    """All five required options (--tree, --chart, --output,
    --chart-strain-field, --tree-strain-field) should appear in --help
    *before* any optional-with-default option."""
    result = _runner().invoke(main, ["--help"])
    assert result.exit_code == 0
    # Find the position of each required option's first occurrence.
    # Trailing space on --tree / --chart avoids matching --tree-strain-field
    # / --chart-strain-field (which appear later in --help).
    required = [
        "--tree ",
        "--chart ",
        "--output",
        "--chart-strain-field",
        "--tree-strain-field",
    ]
    # And one option with a default — must come AFTER all required ones.
    first_optional = "--branch-length "
    positions = {opt: result.output.find(opt) for opt in required + [first_optional]}
    for opt in required:
        assert positions[opt] >= 0, f"{opt!r} missing from --help"
        assert (
            positions[opt] < positions[first_optional]
        ), f"{opt!r} should appear before {first_optional!r} in --help"


def test_help_includes_descriptions_from_plot_config() -> None:
    """The --help text should carry the actual descriptions written on
    PlotConfig fields. Pin one phrase from each of two fields."""
    result = _runner().invoke(main, ["--help"])
    assert result.exit_code == 0
    # Click wraps --help output at terminal width, which can break
    # multi-word phrases across lines. Collapse whitespace before checking.
    flat = " ".join(result.output.split())
    # From PlotConfig.chart_strain_field's description:
    assert "data-column name" in flat
    # From PlotConfig.scale_bar's description:
    assert "branch-length scale" in flat


def test_missing_required_chart_strain_field_exits_nonzero(tmp_path: Path) -> None:
    """Missing --chart-strain-field should fail fast."""
    auspice = DATA_DIR / "flu-seqneut-2025to2026_H3N2.json"
    chart = DATA_DIR / "flu-seqneut-2025to2026_H3N2_titers.json"
    if not (auspice.exists() and chart.exists()):
        pytest.skip("real-data files not present")
    result = _runner().invoke(
        main,
        [
            "--tree",
            str(auspice),
            "--chart",
            str(chart),
            "--tree-strain-field",
            "derived_haplotype",
            "--branch-length",
            "div",
            "--output",
            str(tmp_path / "out.html"),
        ],
    )
    assert result.exit_code != 0
    assert "chart-strain-field" in result.output.lower()


def test_h3n2_end_to_end(tmp_path: Path) -> None:
    """Full real-data run via the CLI: H3N2 chart + tree → HTML output."""
    auspice = DATA_DIR / "flu-seqneut-2025to2026_H3N2.json"
    chart = DATA_DIR / "flu-seqneut-2025to2026_H3N2_titers.json"
    if not (auspice.exists() and chart.exists()):
        pytest.skip("real-data files not present")
    out = tmp_path / "h3n2.html"
    result = _runner().invoke(
        main,
        [
            "--tree",
            str(auspice),
            "--chart",
            str(chart),
            "--chart-strain-field",
            "axis_label",
            "--tree-strain-field",
            "derived_haplotype",
            "--branch-length",
            "div",
            "--tree-size",
            "140",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, f"CLI failed: {result.output}"
    assert out.exists()
    assert out.stat().st_size > 0


def test_h1n1_end_to_end(tmp_path: Path) -> None:
    """The horizontal-layout path through the CLI: H1N1 chart (strain on
    x) + tree → VConcat output written to disk."""
    auspice = DATA_DIR / "flu-seqneut-2025to2026_H1N1.json"
    chart = DATA_DIR / "flu-seqneut-2025to2026_H1N1_titers.json"
    if not (auspice.exists() and chart.exists()):
        pytest.skip("real-data files not present")
    out = tmp_path / "h1n1.html"
    result = _runner().invoke(
        main,
        [
            "--tree",
            str(auspice),
            "--chart",
            str(chart),
            "--chart-strain-field",
            "axis_label",
            "--tree-strain-field",
            "derived_haplotype",
            "--branch-length",
            "div",
            "--tree-size",
            "140",
            "--scale-bar",
            "--branch-length-units",
            "substitutions",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, f"CLI failed: {result.output}"
    assert out.exists()
    assert out.stat().st_size > 0


def test_dual_flag_no_strict_version_recognized(tmp_path: Path) -> None:
    """--no-strict-version is the negative side of the dual flag and
    should be a recognized option (not an error)."""
    auspice = DATA_DIR / "flu-seqneut-2025to2026_H3N2.json"
    chart = DATA_DIR / "flu-seqneut-2025to2026_H3N2_titers.json"
    if not (auspice.exists() and chart.exists()):
        pytest.skip("real-data files not present")
    out = tmp_path / "h3n2.html"
    result = _runner().invoke(
        main,
        [
            "--tree",
            str(auspice),
            "--chart",
            str(chart),
            "--chart-strain-field",
            "axis_label",
            "--tree-strain-field",
            "derived_haplotype",
            "--branch-length",
            "div",
            "--no-strict-version",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, f"CLI failed: {result.output}"
