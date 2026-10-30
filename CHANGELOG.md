# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-10-30

### Added

- `strain_label_styles` (default `None`): style a subset of the strain labels
  rendered in the tree panel when `connect_leader_to_label` is on, e.g. to draw
  the vaccine strains' labels in bold red. A list of rules, each naming some
  `strains` and a `style` of Vega-Lite text properties (`fill`, `opacity`,
  `fontWeight`, `fontStyle`). Where rules overlap, later rules win property by
  property. An optional `when` condition applies a rule only while it holds:
  - the name of a parameter declared in the chart, such as a checkbox;
  - any Vega expression, e.g. `"emphasis == 'cell'"` for a radio button;
  - in Python, an `alt.Parameter`, which is declared on the returned chart if
    the chart doesn't already declare it.

  Each styled property becomes a per-label expression on the existing label
  layers, so no layers are added and the returned chart keeps its shape. A
  strain that isn't a tree tip raises; strains dropped by `prune_tree_to_chart`
  are skipped. CLI form: `--strain-label-styles` with a JSON array, where
  `when` names a parameter saved in the chart JSON.
  ([#12](https://github.com/jbloomlab/tree-annotated-plot/issues/12))

### Fixed

- A chart with selection parameters on a compound chart (layer, facet, or
  concat) failed to render when passed to `plot()` as a JSON path, HTML path
  or spec dict, which is every CLI use. Vega-Lite reported
  `Duplicate signal name: "<selection>_tuple"`. This affected the flu examples'
  CLI reproductions. The chart loader removed each selection's `views` before
  loading, and altair then emitted empty `views`, which makes Vega-Lite define
  the selection in every view. The loader now leaves the spec's `views` intact.
  Live altair charts were never affected.
- The `plot()` docstring's Returns section described the panel order wrongly
  for a strain on `x`. The default `tree_location="bottom"` puts the chart
  first and the tree second. The section now gives the order for each
  `tree_location`.

## [0.4.0] - 2026-08-20

### Added

- `spacing` (default `0`): pixels of blank space between the tree panel and
  the chart panel. `0` keeps the two butted together, as before. Distinct from
  `shift_tree_loc`, which moves the tree within its own panel by resizing the
  label strip. CLI form: `--spacing`.

### Changed

- Pin `ruff` to `>=0.16,<0.17` and state the lint rules explicitly with
  `[tool.ruff.lint] select`. Ruff's *default* rule set widened in 0.16, which
  turned CI red on unchanged code; the selection is now a project decision
  rather than whatever the installed ruff defaults to. Development-only, no
  effect on the package.

### Fixed

- With `connect_leader_to_label` on, strain labels were anchored exactly on the
  tree panel's chart-facing edge, so the text ran up against the chart's frame
  and the frame line became hard to read. The pad that the label strip already
  reserved is now applied between the text and the chart, and the leader lines
  stop where the text begins rather than continuing to the panel edge. The gap
  is `max(3, strain_label_font_size * 0.2)` px, and the tree panel grows by that
  much, so a hand-tuned `shift_tree_loc` may want the same adjustment.

## [0.3.0] - 2026-05-19

### Added

- `prune_chart_to_tree` (default `False`): when on, chart rows whose
  `chart_strain_field` value isn't a tree tip are filtered out before
  drawing. CLI form:
  `--prune-chart-to-tree / --no-prune-chart-to-tree`.
  ([#6](https://github.com/jbloomlab/tree-annotated-plot/issues/6))
- `-h` is accepted as a short alias for `--help` on the
  `tree-annotated-plot` CLI.

### Changed

- Minimum supported Python lowered from 3.13 to 3.11. CI still
  runs on 3.13.

## [0.2.2] - 2026-05-09

### Fixed

- `mark_line`, `mark_trail`, and `mark_area` now connect points in tree
  tip order regardless of other encodings on the chart. Previously, a
  user chart with an explicit categorical color-scale `domain` rendered
  with crisscrossing line segments because Vega-Lite's default
  connection-order heuristic ignored the strain-axis sort. The package
  now attaches a `calculate` transform that derives a per-row tip rank
  and points the `order` channel at that field on these marks. Any
  user-supplied `order` is left in place.
- When `color_tree_by` is used together with a user chart that has its
  own `color` encoding (e.g. a titer plot colored by `cell_line`), the
  user chart's marks no longer disappear. The concat container now
  resolves the `color` scale as `independent` so the tree's
  `color_value:N` scale (with its tree-specific domain) is not merged
  with the user chart's color scale.

## [0.2.1] - 2026-05-06

### Fixed

- Apply tree-tip ordering to chart axes that use untyped Altair
  shorthand (`alt.Y("strain")` without a `:N` / `:O` type suffix).
  Previously the sort override was silently skipped, so the chart
  rendered in data order instead of tree order.
- An internal consistency check now raises if the spec-level walk
  and the live-object walk over the user's chart ever disagree on
  the number of strain-axis encodings, so silent skips like the
  one above can't recur in another shape.

## [0.2.0] - 2026-05-06

### Added

- `connect_leader_to_label` (default `False`): extends each strain's
  dashed leader line all the way to its text label. When on, the
  chart's strain-axis labels are suppressed and replacement labels
  are rendered alongside the tree on its chart-facing edge.
- `strain_label_font_size` (default `10`), `strain_label_font_weight`
  (default `"normal"`), and `shift_tree_loc` (default `0`) for tuning
  the size, weight, and placement of the connected labels.
- `color_tree_by` (default `None`): color the tree's branches and tip
  circles by an Auspice node attribute (e.g. `"subclade"`) or by the
  inferred genotype state at one or more sites
  (e.g. `"genotype:HA1:158"` or `"genotype:HA1:158,189"`). Colors,
  category ordering, and the bottom-of-plot legend match the
  Nextstrain view of the same tree.
- `tree_color_scale` (default `None`): override the default coloring
  with an explicit `{category: color}` mapping. Keys must match the
  tree's categories one-to-one and the legend order follows the
  user's key order. CLI form: `"value1=#hex1,value2=#hex2,..."`.
- `tree_color_legend_format` (default `None`): pass any subset of
  Vega-Lite's
  [Legend properties](https://vega.github.io/vega-lite/docs/legend.html#properties)
  as a dict to style the tree's color legend (`orient`, `direction`,
  `columns`, `padding`, `labelFontSize`, `titleFontSize`, …). When
  `orient` is `"left"` or `"right"` and the user has not set
  `columns` or `direction`, `columns=1` is forced so entries stack
  vertically. CLI form: a JSON object string.
- `tree_color_legend_show` (default `True`): set to `False` to hide
  the tree's color legend entirely while still coloring the tree.
- `scale_bar_font_size` (default `10`): font size for the tree's
  scale bar label.

### Changed

- Default `tree_line_width` bumped from `1.5` to `2`, default
  `tree_node_size` from `28` to `45`. Tree branch lines and tip
  circles are now drawn at full opacity. The thicker / fuller
  defaults read better when the tree is colored (the prior values
  were tuned for unicolor black trees).

## [0.1.0] - 2026-05-04

Initial release.
