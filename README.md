# tree-annotated-plot

Python package for generating plots with a categorical axis aligned to a compact
phylogenetic tree — for example, neutralization-titer line plots whose strain
axis is shown alongside the strains' phylogeny.

Status: early prototype.

## Installation (development)

This is a pure-Python package. Create a virtual environment and install in
editable mode with the development extras:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

See [`pyproject.toml`](pyproject.toml) for the required Python version and
runtime dependencies.

## Use

To be written once the API stabilizes. The intended interface accepts a
phylogenetic tree (Auspice JSON) plus a user-constructed `altair.Chart` whose
y-encoding is the strain field, and returns an `altair.HConcatChart` with the
tree drawn to the left of the user's chart, tip-aligned to the y-axis.
