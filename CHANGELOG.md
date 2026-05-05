# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `connect_leader_to_label` (default `False`): extends each strain's
  dashed leader line all the way to its text label. When on, the
  chart's strain-axis labels are suppressed and replacement labels
  are rendered alongside the tree on its chart-facing edge.
- `strain_label_font_size` (default `10`), `strain_label_font_weight`
  (default `"normal"`), and `shift_tree_loc` (default `0`) for tuning
  the size, weight, and placement of the connected labels.

## [0.1.0] - 2026-05-04

Initial release.
