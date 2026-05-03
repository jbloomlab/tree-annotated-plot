"""Parse Auspice JSON phylogenetic trees and compute a 2-D layout for drawing."""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pandas as pd


@dataclass
class TreeNode:
    """A node in a phylogenetic tree.

    `name` carries the resolved strain identifier for tips (the value at
    `tree_strain_field`). For internal nodes, `name` is the Auspice top-level
    `name` field — internal-node identity isn't used for chart-strain matching.

    `x` is divergence from the root (read from `node_attrs.div`).
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


def load_auspice(
    source: str | Path | dict,
    *,
    tree_strain_field: str,
    branch_length: str = "div",
    strict_version: bool = True,
) -> TreeNode:
    """Load an Auspice JSON tree from a path or dict.

    Parameters
    ----------
    source
        Path to an Auspice JSON file, or an already-parsed dict.
    tree_strain_field
        Where on each tip to find the strain identifier. The literal string
        ``"name"`` selects the tip's top-level ``name`` field; any other value
        ``X`` selects ``node_attrs[X]`` (auto-unwrapping the Auspice
        ``{"value": ...}`` convention). Dotted paths are not accepted.
    branch_length
        Which Auspice node attribute supplies branch lengths. ``"div"``
        (default) reads ``node_attrs.div`` (a scalar absolute divergence
        from the root). ``"num_date"`` reads ``node_attrs.num_date.value``
        (an absolute calendar position in years). In both cases the value
        is stored on each ``TreeNode.x`` and is used as-is by layout,
        segments, and pruning — they're branch-source-agnostic.
    strict_version
        When True (default), raise ``ValueError`` if the Auspice JSON's
        top-level ``version`` field does not start with ``"v2"``. With
        ``False`` the same case becomes a ``warnings.warn``. A missing
        ``version`` field always warns and proceeds.
    """
    _validate_tree_strain_field(tree_strain_field)
    if branch_length not in ("div", "num_date"):
        raise ValueError(
            f"branch_length={branch_length!r} not supported; expected 'div' "
            "or 'num_date'."
        )

    if isinstance(source, (str, Path)):
        with open(source) as f:
            data = json.load(f)
    elif isinstance(source, dict):
        data = source
    else:
        raise ValueError(f"unsupported tree source type: {type(source).__name__}")

    _check_auspice_version(data, strict_version=strict_version)

    if "tree" not in data:
        raise ValueError("Auspice JSON must have a top-level 'tree' field")
    return _parse_node(data["tree"], tree_strain_field, branch_length)


def _check_auspice_version(data: dict, *, strict_version: bool) -> None:
    """Inspect the Auspice top-level `version`; raise / warn on non-v2."""
    version = data.get("version")
    if version is None:
        warnings.warn(
            "Auspice JSON has no top-level 'version' field; proceeding, but "
            "the structure is assumed to be Auspice v2.",
            stacklevel=3,
        )
        return
    if not isinstance(version, str) or not version.startswith("v2"):
        msg = (
            f"Auspice JSON has version={version!r}; this package only "
            "supports v2. Regenerate the tree with a current Augur version."
        )
        if strict_version:
            raise ValueError(msg)
        warnings.warn(msg, stacklevel=3)


def _validate_tree_strain_field(tree_strain_field: str) -> None:
    if not isinstance(tree_strain_field, str) or not tree_strain_field:
        raise ValueError(
            f"tree_strain_field must be a non-empty string, got "
            f"{tree_strain_field!r}"
        )
    if "." in tree_strain_field:
        raise ValueError(
            f"tree_strain_field={tree_strain_field!r} contains a dot. Dotted "
            "paths are not supported. Use 'name' for the top-level Auspice "
            "node `name` field, or a single attribute name (e.g. "
            "'derived_haplotype') to look up under node_attrs (the "
            "{'value': ...} Auspice convention is auto-unwrapped)."
        )


def _resolve_tip_strain(node_dict: dict, tree_strain_field: str) -> str:
    """Look up tree_strain_field on a tip and return its string value."""
    if tree_strain_field == "name":
        v = node_dict.get("name")
    else:
        attrs = node_dict.get("node_attrs", {})
        if tree_strain_field not in attrs:
            raise ValueError(
                f"tree tip {node_dict.get('name', '?')!r} has no "
                f"node_attrs[{tree_strain_field!r}]"
            )
        v = attrs[tree_strain_field]
        if isinstance(v, dict) and "value" in v:
            v = v["value"]

    if not isinstance(v, str) or not v:
        raise ValueError(
            f"tree_strain_field={tree_strain_field!r} on tip "
            f"{node_dict.get('name', '?')!r} resolved to {v!r}; expected a "
            "non-empty string"
        )
    return v


def _parse_node(d: dict, tree_strain_field: str, branch_length: str) -> TreeNode:
    children_dicts = d.get("children", [])
    branch_value = _resolve_branch_length(d, branch_length)
    if children_dicts:
        # Internal node: use the Auspice top-level name (always present).
        name = d.get("name") or "<internal>"
    else:
        # Tip: resolve via tree_strain_field.
        name = _resolve_tip_strain(d, tree_strain_field)
    children = [
        _parse_node(c, tree_strain_field, branch_length) for c in children_dicts
    ]
    return TreeNode(name=name, x=float(branch_value), children=children)


def _resolve_branch_length(node_dict: dict, branch_length: str) -> float:
    """Pull the branch-length value out of a node's node_attrs."""
    attrs = node_dict.get("node_attrs", {})
    if branch_length == "div":
        v = attrs.get("div")
        if v is None:
            raise ValueError(
                f"tree node {node_dict.get('name', '?')!r} has no "
                "node_attrs.div (required by branch_length='div')."
            )
        return v
    # branch_length == "num_date"
    nd = attrs.get("num_date")
    if not isinstance(nd, dict) or "value" not in nd:
        raise ValueError(
            f"tree node {node_dict.get('name', '?')!r} has no "
            "node_attrs.num_date.value (required by branch_length='num_date')."
        )
    return nd["value"]


def _prune_tree_to(root: TreeNode, keep_strains: set[str]) -> TreeNode:
    """Return a new tree pruned to subtrees whose tips are in `keep_strains`.

    Strict-flavor pruning per the Phase 2 plan:
      - Drop every tip whose `name` is not in `keep_strains`.
      - Drop every internal node whose entire subtree was dropped.
      - Collapse single-child internals: when an internal node has only
        one surviving child after pruning, the kept child replaces it.
        Because each `TreeNode.x` is the *absolute* divergence from the
        original root (not a delta from its parent), no branch-length
        summation is needed — the kept node's `x` already reflects the
        correct distance from any further-up ancestor. (For `num_date`
        once Phase 2h adds it, the same holds: dates are absolute
        positions.)
      - Re-root to the LCA of the kept tips: if the original root has
        only one kept-child path, the recursive case collapses upward
        until a node with ≥2 surviving subtrees is reached, which becomes
        the new root.

    Raises ValueError if the resulting tree has no tips (i.e. `keep_strains`
    didn't overlap any tip's name).
    """
    pruned = _prune_recursive(root, keep_strains)
    if pruned is None:
        raise ValueError(
            "after pruning, no tips remain; keep_strains has no overlap "
            "with the tree's tip names"
        )
    return pruned


def _prune_recursive(node: TreeNode, keep_strains: set[str]) -> TreeNode | None:
    """Return a copy of `node` pruned to kept descendants, or None if no
    descendants are kept.

    Single-child internals are collapsed by returning the surviving child
    directly — its absolute `x` is preserved, so root-to-tip distances
    survive unchanged.
    """
    if node.is_tip:
        if node.name in keep_strains:
            return TreeNode(name=node.name, x=node.x, children=[])
        return None

    new_children: list[TreeNode] = []
    for c in node.children:
        kept = _prune_recursive(c, keep_strains)
        if kept is not None:
            new_children.append(kept)

    if not new_children:
        return None
    if len(new_children) == 1:
        # Collapse this single-child internal into its child.
        return new_children[0]
    return TreeNode(name=node.name, x=node.x, children=new_children)


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
