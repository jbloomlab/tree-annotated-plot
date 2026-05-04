# Next steps

Phase 2 is complete. This file is the to-do list for resuming —
either by Jesse picking up later or by a future Claude session.
Lifecycle: shrink as items get done; delete the file when only
hypothetical Phase 3 work is left.

## Immediate actions (not yet done)

1. **Push to GitHub.** Local commits haven't been pushed yet.
   ```bash
   git push -u origin main
   ```
2. **Enable Pages.** GitHub repo → Settings → Pages → Source:
   "GitHub Actions". This activates the dormant
   `.github/workflows/docs.yml` so the next push to `main` builds
   and deploys the docs site to
   https://jbloomlab.github.io/tree-annotated-plot/.
3. **Verify the deployed site.** Click through Home / Python API /
   Command line / Examples. On the Examples page, each "Open the
   interactive chart →" link should open a working interactive
   Altair chart with tooltips and selection bindings. If any link
   404s or any image is missing, the `Generate chart assets` step
   in the workflow probably failed — check the Actions tab.
4. **Bump the version + cut a tag** when you're ready for v0.1.0.
   `pyproject.toml`'s `version = "0.0.1"` is an alpha placeholder.
   ```bash
   # edit pyproject.toml: version = "0.1.0"
   git commit -am "release v0.1.0" && git tag v0.1.0
   git push && git push --tags
   ```
5. **Add a GitHub action to run the tests**: this should include running any tests, examples, linting, and code formatting

## Phase 3 candidate features (deferred from Phase 2)

The Phase 2 plan's "Out of scope" section listed these explicitly
and the user signed off on deferring them. Pick from this list when
adding the next round of features:

- **Clade coloring / tree decoration.** API shape undecided. Two
  options on the table:
  - Declarative: `clades=[{"node_attr": "subclade", "values_to_colors": {...}}]` and the package paints branches.
  - Lower-level: expose `tree_chart()` returning the tree panel as
    an editable `alt.Chart` so users layer their own decoration.
- **Image-snapshot regression tests.** Render via
  `vl-convert-python` (already a dep) to PNG and compare with a
  structural diff or perceptual-similarity metric. Tool choice
  undecided (`pytest-mpl` is matplotlib-only; would need to find or
  build something for Vega-Lite output).
- **Newick / Nexus tree input.** Auspice JSON v2 is the only tree
  format today.
- **Static (matplotlib) backend.** Only altair-via-Vega-Lite today.
- **HTML chart-spec extraction beyond the default altair template.**
  Today we parse `var spec = {...}` out of altair's standard
  `to_html()` output via stdlib `html.parser` +
  `json.JSONDecoder.raw_decode()`. Custom `chart.save(template=...)`
  outputs would need a real JS-AST parser (e.g. `esprima`).
- **Per-clade collapsing of subtrees** (different from the
  topology-pruning we already do for `prune_tree_to_chart`).
- **Vega-Lite v5 → v6 auto-upgrade** of stale specs. We currently
  detect-and-report; we don't translate.

## Smaller polish items

- **Add `CHANGELOG.md`.** None today; `git log --oneline` is the
  de-facto record. Worth one if multiple releases pile up.
- **Add a PyPI publish workflow.**
  `.github/workflows/release.yml` triggered on tag, building wheel +
  sdist, uploading via trusted publishing. None today; would
  complement the existing docs-deploy workflow.
- **Compress the H1N1 docs PNG** (currently ~1 MB). Options:
  - Pass `optimize=True` to the PIL save (might need post-processing
    after `chart.save()`).
  - Lower PPI in `scripts/generate_docs_assets.py` from 96 to 72.
  - Crop or resize after rendering.
- **Investigate the "Automatically deduplicated selection parameter"
  altair warning** that appears when the Kikawa chart-builder runs.
  Pre-existing and cosmetic, but it'd be cleaner to silence
  (probably needs explicit `name=` on the selection params).
- **Add badges to README** Add badges for GitHub Actions test and PyPI version to the README.
  Is there also a badge I can add for the docs, or other badges to consider?

## State at session close

- 21 commits on `main`, none pushed.
- All 102 tests pass via `scripts/check.sh`.
- `scripts/build_docs.sh` produces a viewable `site/` from a clean
  checkout.
- `plan.md` is gone (disassembled per its own Lifecycle section in
  commit `b9beb66`).
- `docs_plan.md` is gone (transient design note for the docs
  deployment + asset strategy; written, reviewed, and removed in
  commit `f1f551d`).
