"""tree-annotated-plot: plots with a categorical axis aligned to a phylogenetic tree."""

from importlib.metadata import version

from ._plot import plot
from ._tree import TreeNode, load_auspice

__version__ = version("tree-annotated-plot")

__all__ = ["plot", "load_auspice", "TreeNode", "__version__"]
