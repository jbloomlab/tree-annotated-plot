# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
