"""Parse Auspice JSON phylogenetic trees and compute a 2-D layout for drawing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pandas as pd


@dataclass
class TreeNode:
    """A node in a phylogenetic tree.

    `x` is divergence from the root (read from `node_attrs.div` in Auspice JSON).
    `y` is set by :func:`layout` and is the integer index of the node's tip
    (for tips) or the midpoint of its descendants' tip indices (for internal
    nodes).
    """

    name: str
    x: float
    children: list["TreeNode"] = field(default_factory=list)
    y: float | None = None

    @property
    def is_tip(self) -> bool:
        return not self.children


def load_auspice(source: str | Path | dict) -> TreeNode:
    """Load an Auspice JSON tree from a path, dict, or file-like object."""
    if isinstance(source, (str, Path)):
        with open(source) as f:
            data = json.load(f)
    elif isinstance(source, dict):
        data = source
    else:
        raise ValueError(f"unsupported tree source type: {type(source).__name__}")

    if "tree" not in data:
        raise ValueError("Auspice JSON must have a top-level 'tree' field")
    return _parse_node(data["tree"])


def _parse_node(d: dict) -> TreeNode:
    name = d.get("name")
    if not name:
        raise ValueError(f"tree node missing 'name': {d!r}")
    div = d.get("node_attrs", {}).get("div")
    if div is None:
        raise ValueError(f"tree node {name!r} missing node_attrs.div")
    children = [_parse_node(c) for c in d.get("children", [])]
    return TreeNode(name=name, x=float(div), children=children)


def tips(root: TreeNode) -> Iterator[TreeNode]:
    """Yield tips of the tree in left-to-right (pre-order) traversal."""
    if root.is_tip:
        yield root
    else:
        for c in root.children:
            yield from tips(c)


def layout(root: TreeNode) -> list[TreeNode]:
    """Assign `y` to every node in the tree and return tips in order.

    Tips get integer y indices 0..N-1 in left-to-right order. Internal nodes
    get the midpoint of their immediate children's y values.
    """
    tip_list = list(tips(root))
    if not tip_list:
        raise ValueError("tree has no tips")
    for i, tip in enumerate(tip_list):
        tip.y = float(i)
    _assign_internal_y(root)
    return tip_list


def _assign_internal_y(node: TreeNode) -> float:
    if node.is_tip:
        assert node.y is not None
        return node.y
    ys = [_assign_internal_y(c) for c in node.children]
    node.y = (min(ys) + max(ys)) / 2.0
    return node.y


def segments(root: TreeNode) -> pd.DataFrame:
    """Build a DataFrame of line segments for drawing the tree.

    Returns columns `x`, `x2`, `y`, `y2`. Each row is one segment:

    - For each internal node, one vertical connector from the topmost to the
      bottommost child (x == x2 == node.x).
    - For each non-root node, one horizontal branch from its parent's x to its
      own x at its own y (y == y2).

    Assumes :func:`layout` has already been called on `root`.
    """
    if root.y is None:
        raise ValueError("call layout(root) before segments(root)")

    rows: list[dict] = []

    def walk(node: TreeNode) -> None:
        if node.is_tip:
            return
        child_ys = [c.y for c in node.children]
        rows.append(
            {"x": node.x, "x2": node.x, "y": min(child_ys), "y2": max(child_ys)}
        )
        for c in node.children:
            rows.append({"x": node.x, "x2": c.x, "y": c.y, "y2": c.y})
            walk(c)

    walk(root)
    return pd.DataFrame(rows, columns=["x", "x2", "y", "y2"])
