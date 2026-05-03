"""Generate H3N2 IQR and H1N1 individual-sera titer plots from Kikawa et al (2026).

Reads three CSVs published in the jbloomlab/flu-seqneut-2025to2026 repo and
writes 4 files (two charts x HTML+JSON) to ./examples/data/.

Run from the project root:

    .venv/bin/python examples/flu-seqneut-2025to2026_titer_charts.py

Adapted/simplified from notebooks/plot_titer_summaries.py in
jbloomlab/flu-seqneut-2025to2026: drops the haplotype-coloring labels, the
subclade legend selection, and the fraction-below-cutoff chart. Keeps the
transform_lookup pipeline so the embedded data stays small.
"""

from pathlib import Path

import altair as alt
import pandas as pd

alt.data_transformers.disable_max_rows()

REPO_RAW = "https://raw.githubusercontent.com/jbloomlab/flu-seqneut-2025to2026/main"
TITERS_URL = f"{REPO_RAW}/results/final_titer_data/human_titers.csv"
VIRUSES_URL = f"{REPO_RAW}/results/final_titer_data/human_viruses.csv"
SERA_URL = f"{REPO_RAW}/results/final_titer_data/human_sera.csv"

# `recent_vaccine_strains` from config.yml in jbloomlab/flu-seqneut-2025to2026
RECENT_VACCINE_STRAINS = [
    "A/Sydney/1359/2024_H3N2",
    "A/DistrictOfColumbia/27/2023_H3N2",
    "A/Missouri/11/2025_H1N1",
    "A/Wisconsin/67/2022_H1N1",
]

CIRCULATING_STRAIN_TYPE = "circulating_2025to2026"
PLOT_STRAIN_TYPES = [CIRCULATING_STRAIN_TYPE, "recent_vaccine"]

# from `plot_titer_summaries_params` in config.yml
TITER_LOWER_LIMIT = 40
FACET_SIZE = 150

OUT_DIR = Path(__file__).parent / "data"


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    titers = pd.read_csv(TITERS_URL)
    viruses = pd.read_csv(VIRUSES_URL)
    sera = pd.read_csv(SERA_URL)

    required_cols = {
        "titers": ({"serum", "virus", "titer"}, titers),
        "viruses": (
            {"virus", "subtype", "strain_type", "subclade", "derived_haplotype"},
            viruses,
        ),
        "sera": (
            {"serum", "cohort", "age", "age_numeric", "sex", "serum_collection_date"},
            sera,
        ),
    }
    for name, (cols, df) in required_cols.items():
        missing = cols - set(df.columns)
        if missing:
            raise ValueError(f"{name} missing required columns: {missing}")

    if sera["serum"].duplicated().any():
        raise ValueError("sera CSV must have one row per serum")

    if set(titers["serum"]) != set(sera["serum"]):
        raise ValueError(
            f"serum mismatch: only-in-titers={set(titers['serum']) - set(sera['serum'])}, "
            f"only-in-sera={set(sera['serum']) - set(titers['serum'])}"
        )

    dups = titers.groupby(["serum", "virus"]).size()
    dups = dups[dups > 1]
    if len(dups):
        raise ValueError(f"found {len(dups)} duplicate serum-virus pairs in titers")

    missing_vaccines = set(RECENT_VACCINE_STRAINS) - set(viruses["virus"])
    if missing_vaccines:
        raise ValueError(f"recent_vaccine_strains not in viruses: {missing_vaccines}")

    viruses = viruses.copy()
    viruses["strain_type"] = viruses["strain_type"].where(
        ~viruses["virus"].isin(RECENT_VACCINE_STRAINS), "recent_vaccine"
    )

    # Build the axis label (derived_haplotype if present, else strain name with
    # the trailing _H1N1/_H3N2 suffix stripped) and use this as the actual axis
    # encoding. Verified unique within each subtype's plotted strains so it
    # doesn't collapse rows.
    viruses["axis_label"] = viruses["derived_haplotype"].where(
        viruses["derived_haplotype"].notna(),
        viruses["virus"].str.rsplit("_", n=1).str[0],
    )

    # The chart encodes the strain axis on `axis_label`, so it must be unique
    # within each plotted (subtype, strain_type) group — otherwise two distinct
    # strains would collapse onto one axis row.
    plotted = viruses[viruses["strain_type"].isin(PLOT_STRAIN_TYPES)]
    for subtype, sub_df in plotted.groupby("subtype"):
        dups = sub_df.groupby("axis_label")["virus"].apply(list)
        dups = dups[dups.str.len() > 1]
        if len(dups):
            raise ValueError(
                f"non-unique axis_label values within subtype {subtype!r}: "
                f"{dups.to_dict()}"
            )

    return titers, viruses, sera


def build_metadata(sera: pd.DataFrame) -> pd.DataFrame:
    """Per-serum metadata with each serum tagged as belonging to its real cohort
    plus the synthetic 'All' cohort. Stored as a list column so the lookup stays
    one row per serum; the chart later flattens this list to one row per
    (serum, cohort) pair."""
    meta = sera.copy()
    meta["cohorts"] = meta["cohort"].apply(lambda c: [c, "All"])
    return meta.drop(columns=["cohort"])


def strain_plot_order(viruses_subset: pd.DataFrame) -> list[str]:
    """Sort by (subclade, virus); NaN subclade (vaccine strains) sorts last."""
    sorted_df = viruses_subset.sort_values(
        by=["subclade", "virus"],
        key=lambda col: col.fillna("zzz") if col.name == "subclade" else col,
    )
    return sorted_df["virus"].tolist()


def make_chart(
    subtype: str,
    chart_type: str,
    titers: pd.DataFrame,
    viruses: pd.DataFrame,
    metadata: pd.DataFrame,
    all_cohorts: list[str],
) -> alt.TopLevelMixin:
    if chart_type not in {"iqr", "lines"}:
        raise ValueError(f"chart_type must be 'iqr' or 'lines', got {chart_type!r}")

    keep = viruses[
        (viruses["subtype"] == subtype) & viruses["strain_type"].isin(PLOT_STRAIN_TYPES)
    ]
    plot_order = strain_plot_order(keep)

    # Axis is encoded on axis_label (derived_haplotype with strain-name
    # fallback). Translate the (subclade, virus)-sorted strain plot order into
    # the corresponding axis_label sort order.
    virus_to_label = dict(zip(keep["virus"], keep["axis_label"]))
    label_sort = [virus_to_label[v] for v in plot_order]

    # iqr  -> strains on Y, titer on X, cohorts as columns
    # lines -> strains on X, titer on Y, cohorts as rows
    vertical = chart_type == "iqr"
    strain_axis = "y" if vertical else "x"
    titer_axis = "x" if vertical else "y"
    facet_dim = "column" if vertical else "row"
    strain_sort = list(reversed(label_sort)) if vertical else label_sort

    virus_selection = alt.selection_point(
        fields=["virus"], on="mouseover", empty=False, clear="mouseout", nearest=False
    )
    serum_selection = alt.selection_point(
        fields=["serum"], on="mouseover", empty=False, clear="mouseout", nearest=False
    )
    cohort_selection = alt.selection_point(
        fields=["cohort"], bind="legend", empty="all", toggle="true", clear=False
    )

    max_age = 5 * int(metadata["age_numeric"].max() // 5) + 5
    min_age_slider = alt.param(
        value=0,
        bind=alt.binding_range(
            min=0, max=max_age, step=5, name="minimum subject age (years)"
        ),
    )
    max_age_slider = alt.param(
        value=max_age,
        bind=alt.binding_range(
            min=0, max=max_age, step=5, name="maximum subject age (years)"
        ),
    )

    titer_scale = alt.Scale(
        type="log", nice=False, domainMin=TITER_LOWER_LIMIT, padding=4
    )

    base = (
        alt.Chart(titers[["serum", "virus", "titer"]])
        .add_params(
            virus_selection,
            serum_selection,
            cohort_selection,
            min_age_slider,
            max_age_slider,
        )
        .encode(
            **{
                strain_axis: alt.Y(
                    "axis_label:N",
                    sort=strain_sort,
                    axis=alt.Axis(labelLimit=500, title=None),
                ),
            }
        )
        .properties(
            **(
                {"height": alt.Step(11), "width": FACET_SIZE}
                if vertical
                else {"width": alt.Step(11), "height": FACET_SIZE}
            )
        )
    )

    median_points = (
        base.transform_aggregate(
            median_titer="median(titer)",
            groupby=[
                "virus",
                "axis_label",
                "subtype",
                "strain_type",
                "subclade",
                "cohort",
            ],
        )
        .encode(
            **{titer_axis: alt.X("median_titer:Q", title="titer", scale=titer_scale)},
            tooltip=[
                "virus",
                alt.Tooltip("median_titer:Q", format=".1f"),
                "strain_type:N",
                "subclade:N",
            ],
            color=alt.condition(virus_selection, alt.value("red"), alt.value("black")),
            size=alt.condition(virus_selection, alt.value(80), alt.value(40)),
        )
        .mark_circle(opacity=1)
    )

    if chart_type == "iqr":
        layer = (
            base.transform_joinaggregate(
                median_titer="median(titer)",
                titer_q1="q1(titer)",
                titer_q3="q3(titer)",
                groupby=["virus"],
            )
            .encode(
                **{titer_axis: alt.X("titer", scale=titer_scale)},
                tooltip=[
                    "virus",
                    alt.Tooltip("median_titer:Q", format=".1f"),
                    alt.Tooltip("titer_q1:Q", format=".1f"),
                    alt.Tooltip("titer_q3:Q", format=".1f"),
                    "strain_type:N",
                    "subclade:N",
                ],
            )
            .mark_errorband(extent="iqr", opacity=0.5, interpolate="linear")
        )
    else:  # lines
        layer = base.encode(
            **{titer_axis: alt.X("titer", scale=titer_scale)},
            detail=alt.Detail("serum"),
            tooltip=[
                "virus",
                "serum",
                alt.Tooltip("titer", format=".1f"),
                alt.Tooltip("serum_collection_date:N", title="serum date"),
                alt.Tooltip("age:N", title="age"),
                "sex:N",
            ],
            size=alt.condition(serum_selection, alt.value(3), alt.value(1.5)),
            opacity=alt.condition(serum_selection, alt.value(1), alt.value(0.2)),
        ).mark_line()

    body = layer + median_points

    # Facet first, then attach transform_lookups: lookups attached to a faceted
    # chart compile into outer transforms that run before the facet split, which
    # is what makes the cohort_n facet field available.
    faceted = (
        body.facet({facet_dim: alt.Column("cohort_n:N", title=None)})
        .transform_lookup(
            lookup="serum",
            from_=alt.LookupData(
                data=metadata,
                key="serum",
                fields=[
                    "cohorts",
                    "serum_collection_date",
                    "age",
                    "age_numeric",
                    "sex",
                ],
            ),
        )
        .transform_lookup(
            lookup="virus",
            from_=alt.LookupData(
                data=viruses,
                key="virus",
                fields=["subtype", "strain_type", "subclade", "axis_label"],
            ),
        )
        .transform_flatten(["cohorts"], as_=["cohort"])
        .transform_filter(cohort_selection)
        .transform_filter(alt.datum["age_numeric"] >= min_age_slider)
        .transform_filter(alt.datum["age_numeric"] <= max_age_slider)
        .transform_filter(alt.datum["subtype"] == subtype)
        .transform_filter(alt.FieldOneOfPredicate("strain_type", PLOT_STRAIN_TYPES))
        .transform_joinaggregate(n_per_cohort="distinct(serum)", groupby=["cohort"])
        .transform_calculate(
            cohort_n="datum.cohort + ' (n=' + datum.n_per_cohort + ')'"
        )
    )

    dummy_cohort = (
        alt.Chart(pd.DataFrame({"cohort": all_cohorts}))
        .add_params(cohort_selection)
        .mark_point(opacity=0)
        .encode(
            fill=alt.Fill(
                "cohort",
                title="serum cohort (click to select)",
                scale=alt.Scale(domain=all_cohorts, range=["gray"]),
                legend=alt.Legend(
                    symbolStrokeColor="black",
                    symbolOpacity=1,
                    columns=6,
                    titleLimit=400,
                ),
            )
        )
        .properties(width=1, height=1)
    )

    title = (
        f"median (points) and interquartile range titers for {subtype} strains"
        if chart_type == "iqr"
        else f"median (points) and per-serum (lines) titers for {subtype} strains"
    )

    return (
        alt.vconcat(faceted, dummy_cohort, spacing=1)
        .resolve_scale(fill="independent")
        .configure_axis(
            grid=False,
            titleFontWeight="normal",
            titleFontSize=13,
            labelOverlap=True,
        )
        .configure_header(
            title=None,
            labelOrient="top" if vertical else "right",
            labelFontSize=13,
            labelPadding=2,
        )
        .configure_view(stroke="black")
        .configure_facet(spacing=8)
        .configure_legend(
            labelFontSize=12,
            titleFontSize=13,
            symbolStrokeWidth=1,
            symbolOpacity=1,
            symbolStrokeColor="black",
            columns=12,
            orient="bottom",
            titleLimit=400,
        )
        .properties(title=alt.TitleParams(title, anchor="middle", fontSize=13))
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    titers, viruses, sera = load_data()
    metadata = build_metadata(sera)
    all_cohorts = ["All"] + sorted(sera["cohort"].unique())

    plots = [
        ("H3N2", "iqr", "flu-seqneut-2025to2026_H3N2_titers"),
        ("H1N1", "lines", "flu-seqneut-2025to2026_H1N1_titers"),
    ]
    for subtype, chart_type, basename in plots:
        chart = make_chart(
            subtype=subtype,
            chart_type=chart_type,
            titers=titers,
            viruses=viruses,
            metadata=metadata,
            all_cohorts=all_cohorts,
        )
        html_path = OUT_DIR / f"{basename}.html"
        json_path = OUT_DIR / f"{basename}.json"
        chart.save(str(html_path))
        chart.save(str(json_path))
        print(f"wrote {html_path}")
        print(f"wrote {json_path}")


if __name__ == "__main__":
    main()
