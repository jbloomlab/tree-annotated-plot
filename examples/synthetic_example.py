"""Generate a synthetic tree-annotated titer plot and save it to HTML and PNG.

Run from the project root:

    .venv/bin/python examples/synthetic_example.py

Outputs:
    examples/data/synthetic_example.html   (interactive Vega/Altair page)
    examples/data/synthetic_example.png    (static raster via vl-convert)
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import altair as alt
import pandas as pd

import tree_annotated_plot as tap

OUT_DIR = Path(__file__).parent / "data"


def synthetic_auspice() -> dict:
    """Two-clade tree with 8 tips: clade_A (3 tips) and clade_B (5 tips, with sub-clade)."""
    return {
        "version": "v2",
        "meta": {"title": "synthetic"},
        "tree": {
            "name": "ROOT",
            "node_attrs": {"div": 0.0},
            "children": [
                {
                    "name": "clade_A",
                    "node_attrs": {"div": 0.005},
                    "children": [
                        {"name": "a1", "node_attrs": {"div": 0.020}},
                        {"name": "a2", "node_attrs": {"div": 0.025}},
                        {"name": "a3", "node_attrs": {"div": 0.030}},
                    ],
                },
                {
                    "name": "clade_B",
                    "node_attrs": {"div": 0.008},
                    "children": [
                        {
                            "name": "clade_B1",
                            "node_attrs": {"div": 0.015},
                            "children": [
                                {"name": "b1", "node_attrs": {"div": 0.022}},
                                {"name": "b2", "node_attrs": {"div": 0.028}},
                            ],
                        },
                        {
                            "name": "clade_B2",
                            "node_attrs": {"div": 0.018},
                            "children": [
                                {"name": "b3", "node_attrs": {"div": 0.024}},
                                {"name": "b4", "node_attrs": {"div": 0.030}},
                                {"name": "b5", "node_attrs": {"div": 0.035}},
                            ],
                        },
                    ],
                },
            ],
        },
    }


def synthetic_titers() -> pd.DataFrame:
    """Plausible-looking titers: sera s1/s2 favor clade_A; s3/s4 favor clade_B."""
    rng = random.Random(0)
    strains = ["a1", "a2", "a3", "b1", "b2", "b3", "b4", "b5"]
    sera_means = {
        "s1": {
            "a1": 1024,
            "a2": 512,
            "a3": 512,
            "b1": 64,
            "b2": 32,
            "b3": 32,
            "b4": 16,
            "b5": 16,
        },
        "s2": {
            "a1": 512,
            "a2": 1024,
            "a3": 512,
            "b1": 32,
            "b2": 64,
            "b3": 16,
            "b4": 32,
            "b5": 32,
        },
        "s3": {
            "a1": 32,
            "a2": 32,
            "a3": 64,
            "b1": 256,
            "b2": 512,
            "b3": 1024,
            "b4": 512,
            "b5": 256,
        },
        "s4": {
            "a1": 16,
            "a2": 32,
            "a3": 32,
            "b1": 128,
            "b2": 256,
            "b3": 512,
            "b4": 1024,
            "b5": 512,
        },
    }
    rows = []
    for serum, by_strain in sera_means.items():
        for strain in strains:
            mean_log2 = math.log2(by_strain[strain])
            jitter = rng.gauss(0, 0.3)
            rows.append(
                {"strain": strain, "serum": serum, "titer": 2 ** (mean_log2 + jitter)}
            )
    return pd.DataFrame(rows)


def build_chart(df: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "titer:Q",
                scale=alt.Scale(type="log", base=2),
                axis=alt.Axis(title="neutralization titer (log2)"),
            ),
            y=alt.Y("strain:N", axis=alt.Axis(title=None)),
            color=alt.Color("serum:N", legend=alt.Legend(title="serum")),
        )
        .properties(width=320, height=320)
    )


def main() -> None:
    chart = build_chart(synthetic_titers())
    annotated = tap.plot(
        synthetic_auspice(),
        chart,
        chart_strain_field="strain",
        tree_strain_field="name",
        tree_size=140,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUT_DIR / "synthetic_example.html"
    png_path = OUT_DIR / "synthetic_example.png"

    annotated.save(str(html_path))
    annotated.save(str(png_path), ppi=144)

    print(f"wrote {html_path}")
    print(f"wrote {png_path}")


if __name__ == "__main__":
    main()
