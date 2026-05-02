"""tree-annotated-plot: plots with a categorical axis aligned to a phylogenetic tree."""

from ._plot import plot
from ._tree import TreeNode, load_auspice

__version__ = "0.0.1"

__all__ = ["plot", "load_auspice", "TreeNode", "__version__"]
