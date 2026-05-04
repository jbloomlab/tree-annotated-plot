"""Render the chart assets the docs site embeds.

For each example we ship two artifacts:

  - `docs/images/<name>.svg` — embedded inline on the docs page so the
    chart is visible without the user clicking anything.
  - `docs/charts/<name>.html` — full interactive Altair-rendered chart
    that the docs page links to ("Open the interactive chart →").

Both are gitignored. This script regenerates them from the example
modules. Run before `mkdocs build`; both `scripts/build_docs.sh` and
`.github/workflows/docs.yml` invoke it.

Idempotent and safe to re-run. If `examples/data/` is missing the two
upstream Auspice JSONs, the script invokes
`examples/fetch_auspice_data.py`'s `main()` to download them first.

Adding a new example: add a clause to `_render_examples()`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import tree_annotated_plot

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = REPO / "examples"
DATA_DIR = EXAMPLES / "data"
DOCS_IMAGES = REPO / "docs" / "images"
DOCS_CHARTS = REPO / "docs" / "charts"


def _import_path(name: str, path: Path) -> ModuleType:
    """Import a Python file by path. Used for the hyphenated-filename
    chart-builder module; same trick `tests/test_real_data.py` uses."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _save_pair(chart, basename: str) -> None:
    """Save `chart` as both SVG (inline thumbnail) and HTML (interactive)."""
    DOCS_IMAGES.mkdir(parents=True, exist_ok=True)
    DOCS_CHARTS.mkdir(parents=True, exist_ok=True)
    svg_path = DOCS_IMAGES / f"{basename}.svg"
    html_path = DOCS_CHARTS / f"{basename}.html"
    chart.save(str(svg_path))
    chart.save(str(html_path))
    print(f"wrote {svg_path.relative_to(REPO)} ({svg_path.stat().st_size:,} B)")
    print(f"wrote {html_path.relative_to(REPO)} ({html_path.stat().st_size:,} B)")


def _render_synthetic() -> None:
    """The 8-tip synthetic example: minimum end-to-end."""
    syn = _import_path("syn_example", EXAMPLES / "synthetic_example.py")
    chart = syn.build_chart(syn.synthetic_titers())
    out = tree_annotated_plot.plot(
        syn.synthetic_auspice(),
        chart,
        chart_strain_field="strain",
        tree_strain_field="name",
        branch_length="div",
        tree_size=140,
    )
    _save_pair(out, "synthetic_example")


def _ensure_kikawa_auspice() -> None:
    """Download the H3N2 / H1N1 Auspice JSONs into examples/data/ if absent."""
    needed = [
        DATA_DIR / "flu-seqneut-2025to2026_H3N2.json",
        DATA_DIR / "flu-seqneut-2025to2026_H1N1.json",
    ]
    if all(p.exists() for p in needed):
        return
    fetcher = _import_path("fetcher", EXAMPLES / "fetch_auspice_data.py")
    fetcher.main()


def _render_kikawa() -> None:
    """The Kikawa flu-seqneut H3N2 (vertical) and H1N1 (horizontal)
    end-to-ends — real Auspice JSON, real chart with VConcat(Facet(Layer))
    structure, scale bar enabled."""
    _ensure_kikawa_auspice()
    builder = _import_path(
        "kikawa_builder", EXAMPLES / "flu-seqneut-2025to2026_titer_charts.py"
    )
    titers, viruses, sera = builder.load_data()
    metadata = builder.build_metadata(sera)
    all_cohorts = ["All"] + sorted(sera["cohort"].unique())

    for subtype, chart_type, basename in [
        ("H3N2", "iqr", "h3n2"),
        ("H1N1", "lines", "h1n1"),
    ]:
        chart = builder.make_chart(
            subtype=subtype,
            chart_type=chart_type,
            titers=titers,
            viruses=viruses,
            metadata=metadata,
            all_cohorts=all_cohorts,
        )
        # Render the bare chart (no tree) so the docs page can show what
        # the chart looks like before tree-annotated-plot wraps it.
        _save_pair(chart, f"{basename}_chart_only")
        out = tree_annotated_plot.plot(
            DATA_DIR / f"flu-seqneut-2025to2026_{subtype}.json",
            chart,
            chart_strain_field="axis_label",
            tree_strain_field="derived_haplotype",
            branch_length="div",
            tree_size=140,
            scale_bar=True,
            branch_length_units="substitutions",
        )
        _save_pair(out, f"{basename}_combined")


def main() -> None:
    """Render every example to SVG + interactive HTML under `docs/`."""
    _render_synthetic()
    _render_kikawa()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"asset generation failed: {exc}", file=sys.stderr)
        raise
