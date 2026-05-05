"""Resolve per-node color categories and the associated `alt.Scale` arrays.

Public entry point: :func:`compute_node_color_values`.

Spec mini-syntax (see `PlotConfig.color_tree_by`):

- ``"<field>"`` — look up ``node_attrs[<field>]`` on each node, auto-unwrapping
  the Auspice ``{"value": ...}`` convention. Missing → ``"unknown"``.
- ``"genotype:<GENE>:<SITE>"`` — single-site genotype state inferred by walking
  ``branch_attrs.mutations[<GENE>]`` from the root. Site with zero mutations
  in the tree → all nodes are labeled ``"<no variation>"``.
- ``"genotype:<GENE>:<SITE1>,<SITE2>,..."`` — haplotype across sites. Per-node
  label is the ``/``-joined letter+site for each *varying* site, in
  user-supplied order. Sites that are invariant in the tree are dropped from
  the label. If all requested sites are invariant, every node gets
  ``"<no variation>"``.

Color resolution prefers ``meta.colorings[<key>].scale`` from the Auspice JSON
when defined (matches Nextstrain views). When unset, partial, or missing for
the requested key, the per-N table in :data:`_AUSPICE_PALETTE` fills in — the
same hand-tuned categorical palette Auspice's frontend uses for trees that
don't ship explicit color scales, so output still matches the Nextstrain
view. Categories are ordered by descending frequency (ties broken
alphabetically) before being mapped positionally onto the palette, again
matching Auspice's behavior. ``"unknown"`` always renders as ``#888888``
(gray) and is reserved — no entry in :data:`_AUSPICE_PALETTE` is gray, so
a category drawn from the palette can never be confused with missing.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterator

from ._tree import TreeNode

# Auspice's frontend categorical palette, indexed by category count.
# `_AUSPICE_PALETTE[N]` is a hand-tuned `N`-color palette, perceptually spaced
# along a viridis-like sweep (purple → blue → green → yellow → orange → red);
# entries 0..36 are reproduced from Auspice's `src/util/globals.js`. We cap at
# 36 (matching Auspice's own `colors[colors.length - 1]` fallback) and reuse
# the largest palette for >36-category trees. Reproducing this table lets
# rendered output match Nextstrain's view of the same tree even when the
# Auspice JSON omits an explicit `meta.colorings[<key>].scale`.
#
# Source: https://github.com/nextstrain/auspice/blob/master/src/util/globals.js
# Auspice is licensed under AGPL-3.0; the per-N color tables are reproduced
# here as factual color data with attribution.
# fmt: off
_AUSPICE_PALETTE: tuple[tuple[str, ...], ...] = (
    (),
    ("#4C90C0",),
    ("#4C90C0", "#CBB742"),
    ("#4988C5", "#7EB876", "#CBB742"),
    ("#4580CA", "#6BB28D", "#AABD52", "#DFA43B"),
    ("#4377CD", "#61AB9D", "#94BD61", "#CDB642", "#E68133"),
    ("#416DCE", "#59A3AA", "#84BA6F", "#BBBC49", "#E29D39", "#E1502A"),
    ("#3F63CF", "#529AB6", "#75B681", "#A6BE55", "#D4B13F", "#E68133", "#DC2F24"),
    ("#3E58CF", "#4B8EC1", "#65AE96", "#8CBB69", "#B8BC4A", "#DCAB3C", "#E67932", "#DC2F24"),
    ("#3F4DCB", "#4681C9", "#5AA4A8", "#78B67E", "#9EBE5A", "#C5B945", "#E0A23A", "#E67231", "#DC2F24"),
    ("#4042C7", "#4274CE", "#5199B7", "#69B091", "#88BB6C", "#ADBD51", "#CEB541", "#E39B39", "#E56C2F", "#DC2F24"),
    ("#4137C2", "#4066CF", "#4B8DC2", "#5DA8A3", "#77B67F", "#96BD60", "#B8BC4B", "#D4B13F", "#E59638", "#E4672F", "#DC2F24"),
    ("#462EB9", "#3E58CF", "#4580CA", "#549DB2", "#69B091", "#83BA70", "#A2BE57", "#C1BA47", "#D9AD3D", "#E69136", "#E4632E", "#DC2F24"),
    ("#4B26B1", "#3F4ACA", "#4272CE", "#4D92BF", "#5DA8A3", "#74B583", "#8EBC66", "#ACBD51", "#C8B944", "#DDA93C", "#E68B35", "#E3602D", "#DC2F24"),
    ("#511EA8", "#403DC5", "#4063CF", "#4785C7", "#559EB1", "#67AF94", "#7EB877", "#98BD5E", "#B4BD4C", "#CDB642", "#DFA53B", "#E68735", "#E35D2D", "#DC2F24"),
    ("#511EA8", "#403AC4", "#3F5ED0", "#457FCB", "#5098B9", "#60AA9F", "#73B583", "#8BBB6A", "#A4BE56", "#BDBB48", "#D3B240", "#E19F3A", "#E68234", "#E25A2C", "#DC2F24"),
    ("#511EA8", "#4138C3", "#3E59CF", "#4379CD", "#4D92BE", "#5AA5A8", "#6BB18E", "#7FB975", "#96BD5F", "#AFBD4F", "#C5B945", "#D8AE3E", "#E39B39", "#E67D33", "#E2572B", "#DC2F24"),
    ("#511EA8", "#4236C1", "#3F55CE", "#4273CE", "#4A8CC2", "#569FAF", "#64AD98", "#76B680", "#8BBB6A", "#A1BE58", "#B7BC4B", "#CCB742", "#DCAB3C", "#E59638", "#E67932", "#E1552B", "#DC2F24"),
    ("#511EA8", "#4335BF", "#3F51CC", "#416ECE", "#4887C6", "#529BB6", "#5FA9A0", "#6EB389", "#81B973", "#95BD61", "#AABD52", "#BFBB48", "#D1B340", "#DEA63B", "#E69237", "#E67531", "#E1522A", "#DC2F24"),
    ("#511EA8", "#4333BE", "#3F4ECB", "#4169CF", "#4682C9", "#4F96BB", "#5AA5A8", "#68AF92", "#78B77D", "#8BBB6A", "#9EBE59", "#B3BD4D", "#C5B945", "#D5B03F", "#E0A23A", "#E68D36", "#E67231", "#E1502A", "#DC2F24"),
    ("#511EA8", "#4432BD", "#3F4BCA", "#4065CF", "#447ECC", "#4C91BF", "#56A0AE", "#63AC9A", "#71B486", "#81BA72", "#94BD62", "#A7BE54", "#BABC4A", "#CBB742", "#D9AE3E", "#E29E39", "#E68935", "#E56E30", "#E14F2A", "#DC2F24"),
    ("#511EA8", "#4531BC", "#3F48C9", "#3F61D0", "#4379CD", "#4A8CC2", "#539CB4", "#5EA9A2", "#6BB18E", "#7AB77B", "#8BBB6A", "#9CBE5B", "#AFBD4F", "#C0BA47", "#CFB541", "#DCAB3C", "#E39B39", "#E68534", "#E56B2F", "#E04D29", "#DC2F24"),
    ("#511EA8", "#4530BB", "#3F46C8", "#3F5ED0", "#4375CD", "#4988C5", "#5098B9", "#5AA5A8", "#66AE95", "#73B583", "#82BA71", "#93BC62", "#A4BE56", "#B5BD4C", "#C5B945", "#D3B240", "#DEA73B", "#E59738", "#E68234", "#E4682F", "#E04C29", "#DC2F24"),
    ("#511EA8", "#462FBA", "#3F44C8", "#3E5BD0", "#4270CE", "#4784C8", "#4E95BD", "#57A1AD", "#61AB9C", "#6DB38A", "#7BB879", "#8BBB6A", "#9BBE5C", "#ABBD51", "#BBBC49", "#CBB843", "#D6AF3E", "#DFA43B", "#E69537", "#E67F33", "#E4662E", "#E04A29", "#DC2F24"),
    ("#511EA8", "#462EB9", "#4042C7", "#3E58CF", "#416DCE", "#4580CA", "#4C90C0", "#549DB2", "#5DA8A3", "#69B091", "#75B681", "#83BA70", "#92BC63", "#A2BE57", "#B2BD4D", "#C1BA47", "#CEB541", "#D9AD3D", "#E1A03A", "#E69136", "#E67C32", "#E4632E", "#E04929", "#DC2F24"),
    ("#511EA8", "#462EB9", "#4040C6", "#3F55CE", "#4169CF", "#447DCC", "#4A8CC2", "#529AB7", "#5AA5A8", "#64AD98", "#70B487", "#7DB878", "#8BBB6A", "#99BD5D", "#A9BD53", "#B7BC4B", "#C5B945", "#D1B340", "#DCAB3C", "#E29D39", "#E68D36", "#E67932", "#E3612D", "#E04828", "#DC2F24"),
    ("#511EA8", "#472DB8", "#403EC6", "#3F53CD", "#4066CF", "#4379CD", "#4989C5", "#4F97BB", "#57A1AD", "#61AA9E", "#6BB18E", "#77B67F", "#84BA70", "#92BC64", "#A0BE58", "#AFBD4F", "#BCBB49", "#CAB843", "#D4B13F", "#DEA83C", "#E39B39", "#E68A35", "#E67732", "#E35F2D", "#DF4728", "#DC2F24"),
    ("#511EA8", "#472CB7", "#403DC5", "#3F50CC", "#4063CF", "#4375CD", "#4785C7", "#4D93BE", "#559EB1", "#5DA8A3", "#67AF94", "#72B485", "#7EB877", "#8BBB6A", "#98BD5E", "#A6BE55", "#B4BD4C", "#C1BA47", "#CDB642", "#D7AF3E", "#DFA53B", "#E49838", "#E68735", "#E67431", "#E35D2D", "#DF4628", "#DC2F24"),
    ("#511EA8", "#482CB7", "#403BC5", "#3F4ECB", "#3F61D0", "#4272CE", "#4682C9", "#4C90C0", "#529BB5", "#5AA5A8", "#63AC9A", "#6DB28B", "#78B77D", "#84BA6F", "#91BC64", "#9EBE59", "#ACBD51", "#B9BC4A", "#C5B945", "#D0B441", "#DAAD3D", "#E0A23A", "#E59637", "#E68434", "#E67231", "#E35C2C", "#DF4528", "#DC2F24"),
    ("#511EA8", "#482BB6", "#403AC4", "#3F4CCB", "#3F5ED0", "#426FCE", "#457FCB", "#4A8CC2", "#5098B9", "#58A2AC", "#60AA9F", "#69B091", "#73B583", "#7FB976", "#8BBB6A", "#97BD5F", "#A4BE56", "#B1BD4E", "#BDBB48", "#C9B843", "#D3B240", "#DCAB3C", "#E19F3A", "#E69337", "#E68234", "#E67030", "#E25A2C", "#DF4428", "#DC2F24"),
    ("#511EA8", "#482BB6", "#4039C3", "#3F4ACA", "#3E5CD0", "#416CCE", "#447CCD", "#4989C4", "#4E96BC", "#559FB0", "#5DA8A4", "#66AE96", "#6FB388", "#7AB77C", "#85BA6F", "#91BC64", "#9DBE5A", "#AABD53", "#B6BD4B", "#C2BA46", "#CDB642", "#D6B03F", "#DDA83C", "#E29D39", "#E69036", "#E67F33", "#E56D30", "#E2592C", "#DF4428", "#DC2F24"),
    ("#511EA8", "#482AB5", "#4138C3", "#3F48C9", "#3E59CF", "#4169CF", "#4379CD", "#4886C6", "#4D92BE", "#539CB4", "#5AA5A8", "#62AB9B", "#6BB18E", "#75B581", "#7FB975", "#8BBB6A", "#96BD5F", "#A2BE57", "#AFBD4F", "#BABC4A", "#C5B945", "#CFB541", "#D8AE3E", "#DFA63B", "#E39B39", "#E68D36", "#E67D33", "#E56B2F", "#E2572B", "#DF4328", "#DC2F24"),
    ("#511EA8", "#492AB5", "#4137C2", "#3F47C9", "#3E57CE", "#4067CF", "#4376CD", "#4783C8", "#4C8FC0", "#519AB7", "#58A2AC", "#5FA9A0", "#68AF93", "#70B486", "#7BB77A", "#85BA6F", "#90BC65", "#9CBE5B", "#A8BE54", "#B3BD4D", "#BEBB48", "#C9B843", "#D2B340", "#DAAD3D", "#E0A33B", "#E49838", "#E68B35", "#E67B32", "#E5692F", "#E2562B", "#DF4227", "#DC2F24"),
    ("#511EA8", "#492AB5", "#4236C1", "#3F45C8", "#3F55CE", "#4064CF", "#4273CE", "#4681CA", "#4A8CC2", "#4F97BA", "#569FAF", "#5CA7A4", "#64AD98", "#6DB28B", "#76B680", "#80B974", "#8BBB6A", "#96BD60", "#A1BE58", "#ACBD51", "#B7BC4B", "#C2BA46", "#CCB742", "#D4B13F", "#DCAB3C", "#E1A13A", "#E59638", "#E68835", "#E67932", "#E4672F", "#E1552B", "#DF4227", "#DC2F24"),
    ("#511EA8", "#4929B4", "#4235C0", "#3F44C8", "#3F53CD", "#3F62CF", "#4270CE", "#457ECB", "#4989C4", "#4E95BD", "#549DB3", "#5AA5A8", "#61AB9C", "#69B090", "#72B485", "#7BB879", "#85BA6E", "#90BC65", "#9BBE5C", "#A6BE55", "#B1BD4E", "#BBBC49", "#C5B945", "#CEB541", "#D6AF3E", "#DDA93C", "#E29F39", "#E69537", "#E68634", "#E67732", "#E4662E", "#E1532B", "#DF4127", "#DC2F24"),
    ("#511EA8", "#4929B4", "#4335BF", "#3F42C7", "#3F51CC", "#3F60D0", "#416ECE", "#447CCD", "#4887C6", "#4D92BF", "#529BB6", "#58A2AB", "#5FA9A0", "#66AE95", "#6EB389", "#77B67E", "#81B973", "#8BBB6A", "#95BD61", "#A0BE59", "#AABD52", "#B5BD4C", "#BFBB48", "#C9B843", "#D1B340", "#D8AE3E", "#DEA63B", "#E29C39", "#E69237", "#E68434", "#E67531", "#E4642E", "#E1522A", "#DF4127", "#DC2F24"),
    ("#511EA8", "#4928B4", "#4334BF", "#4041C7", "#3F50CC", "#3F5ED0", "#416CCE", "#4379CD", "#4784C7", "#4B8FC1", "#5098B9", "#56A0AF", "#5CA7A4", "#63AC99", "#6BB18E", "#73B583", "#7CB878", "#86BB6E", "#90BC65", "#9ABD5C", "#A4BE56", "#AFBD4F", "#B9BC4A", "#C2BA46", "#CCB742", "#D3B240", "#DAAC3D", "#DFA43B", "#E39B39", "#E68F36", "#E68234", "#E67431", "#E4632E", "#E1512A", "#DF4027", "#DC2F24"),
)
# fmt: on

_UNKNOWN = "unknown"
_NO_VARIATION = "<no variation>"
_GRAY = "#888888"

# Auspice mutation strings are like "N158K" / "*123A" / "-456N": one non-digit
# char, then digits, then one non-digit char.
_MUTATION_RE = re.compile(r"^(\D)(\d+)(\D)$")


@dataclass(frozen=True)
class ColorMapping:
    """Resolved color information for a single `color_tree_by` invocation."""

    values_by_node: dict[str, str]
    domain: list[str]
    range_: list[str]
    legend_title: str
    # When None, the legend shows the full domain. When set, it restricts the
    # legend display without altering the scale — used to hide ``"unknown"``
    # when only internal nodes (not tips) lack the attribute, since the gray
    # entry in that case just flags internal-node bookkeeping rather than
    # any missing tip-level data.
    legend_values: list[str] | None = None


def compute_node_color_values(
    root: TreeNode,
    color_spec: str,
    auspice_meta: dict | None = None,
) -> ColorMapping:
    """Walk the tree and resolve per-node color categories + scale arrays.

    Parameters
    ----------
    root
        The root of the tree to color. Internal-node identity is by
        ``TreeNode.name`` (Auspice's ``NODE_xxxx``); tips by their resolved
        strain name.
    color_spec
        The user-supplied spec string (see module docstring).
    auspice_meta
        The Auspice JSON's top-level ``meta`` dict, or ``None`` when no JSON
        is available (caller passed a pre-built `TreeNode`). Used only to
        consult ``meta.colorings[<key>].scale`` and ``.title`` for node-attr
        specs; ignored for genotype specs.

    Returns
    -------
    ColorMapping
        ``values_by_node[node.name]`` is the category string for each node.
        ``domain`` and ``range_`` are parallel lists for ``alt.Scale``.
        ``legend_title`` is the resolved legend header. ``legend_values``,
        when set, restricts which categories appear in the legend (leaving
        the scale untouched).
    """
    parsed = _parse_color_spec(color_spec)
    if parsed[0] == "attr":
        _, key = parsed
        values_by_node = _color_by_node_attr(root, key)
    else:
        _, gene, sites = parsed
        values_by_node = _color_by_genotype(root, gene, sites)

    categories = _ordered_categories(values_by_node.values())
    domain, range_ = _resolve_scale(categories, parsed, auspice_meta)
    legend_title = _resolve_legend_title(color_spec, parsed, auspice_meta)
    legend_values = _resolve_legend_values(domain, values_by_node, root)
    return ColorMapping(
        values_by_node=values_by_node,
        domain=domain,
        range_=range_,
        legend_title=legend_title,
        legend_values=legend_values,
    )


def _resolve_legend_values(
    domain: list[str],
    values_by_node: dict[str, str],
    root: TreeNode,
) -> list[str] | None:
    """Decide whether to hide ``"unknown"`` from the legend.

    Returns ``None`` when the full domain should appear — either because
    ``"unknown"`` isn't a category at all, or because at least one tip
    carries it (in which case the user looking at a gray tip needs the
    legend to explain it). When ``"unknown"`` is present but only on
    internal nodes, returns the domain with ``"unknown"`` filtered out;
    internal segments still render gray via the unchanged scale, but the
    legend doesn't dangle a misleading entry.
    """
    if _UNKNOWN not in domain:
        return None
    for node in _walk_nodes(root):
        if node.is_tip and values_by_node.get(node.name) == _UNKNOWN:
            return None
    return [c for c in domain if c != _UNKNOWN]


def _parse_color_spec(
    spec: str,
) -> tuple[str, str] | tuple[str, str, list[int]]:
    """Parse the spec mini-syntax. See module docstring for the grammar."""
    if not isinstance(spec, str) or not spec or any(c.isspace() for c in spec):
        raise ValueError(
            f"color_tree_by={spec!r}: expected either a node_attrs key, "
            '"genotype:<GENE>:<SITE>", or '
            '"genotype:<GENE>:<SITE1>,<SITE2>,...".'
        )
    if ":" not in spec:
        return ("attr", spec)
    parts = spec.split(":")
    if len(parts) != 3 or parts[0] != "genotype" or not parts[1] or not parts[2]:
        raise ValueError(
            f"color_tree_by={spec!r}: expected either a node_attrs key, "
            '"genotype:<GENE>:<SITE>", or '
            '"genotype:<GENE>:<SITE1>,<SITE2>,...".'
        )
    _, gene, site_str = parts
    site_strs = site_str.split(",")
    sites: list[int] = []
    for s in site_strs:
        try:
            n = int(s)
        except ValueError as e:
            raise ValueError(
                f"color_tree_by={spec!r}: site {s!r} must be a positive integer."
            ) from e
        if n <= 0:
            raise ValueError(
                f"color_tree_by={spec!r}: site {s!r} must be a positive integer."
            )
        sites.append(n)
    seen: set[int] = set()
    dups: set[int] = set()
    for n in sites:
        if n in seen:
            dups.add(n)
        else:
            seen.add(n)
    if dups:
        raise ValueError(
            f"color_tree_by={spec!r}: site list has duplicates ({sorted(dups)}); "
            "each site must appear at most once."
        )
    return ("genotype", gene, sites)


def _walk_nodes(root: TreeNode) -> Iterator[TreeNode]:
    """Yield every node in the tree in pre-order."""
    yield root
    for c in root.children:
        yield from _walk_nodes(c)


def _color_by_node_attr(root: TreeNode, key: str) -> dict[str, str]:
    """Resolve per-node category by reading `node_attrs[key]`."""
    values: dict[str, str] = {}
    found = False
    observed_keys: set[str] = set()
    for node in _walk_nodes(root):
        observed_keys.update(node.node_attrs.keys())
        attr = node.node_attrs.get(key)
        if attr is None:
            values[node.name] = _UNKNOWN
            continue
        if isinstance(attr, dict) and "value" in attr:
            attr = attr["value"]
        if attr is None or attr == "":
            values[node.name] = _UNKNOWN
            continue
        found = True
        values[node.name] = str(attr)
    if not found:
        observed = ", ".join(repr(k) for k in sorted(observed_keys))
        raise ValueError(
            f"color_tree_by={key!r} is not a node_attrs key in this tree. "
            f"Observed keys: [{observed}]"
        )
    return values


def _color_by_genotype(root: TreeNode, gene: str, sites: list[int]) -> dict[str, str]:
    """Resolve per-node category by walking branch_attrs.mutations[gene].

    See :func:`_color_by_genotype_single_site` for the per-site walk.
    Per-node label is the ``/``-joined ``<letter><site>`` for each varying
    site in user-supplied order; if every requested site is invariant, every
    node gets ``"<no variation>"``.
    """
    observed_genes: set[str] = set()
    any_mutation = False
    for node in _walk_nodes(root):
        gene_map = node.branch_attrs.get("mutations", {}) or {}
        if gene_map:
            any_mutation = True
            observed_genes.update(gene_map.keys())
    if not any_mutation:
        raise ValueError(
            f"color_tree_by='genotype:{gene}:{','.join(map(str, sites))}': "
            "the Auspice JSON has no branch_attrs.mutations annotations."
        )
    if gene not in observed_genes:
        observed = ", ".join(repr(g) for g in sorted(observed_genes))
        raise ValueError(
            f"color_tree_by='genotype:{gene}:{','.join(map(str, sites))}': "
            f"gene {gene!r} not in branch_attrs.mutations. "
            f"Observed genes: [{observed}]"
        )

    per_site_states: dict[int, dict[str, str] | None] = {}
    for site in sites:
        per_site_states[site] = _color_by_genotype_single_site(root, gene, site)

    varying_sites = [s for s in sites if per_site_states[s] is not None]
    if not varying_sites:
        # Every requested site is invariant in the tree.
        return {node.name: _NO_VARIATION for node in _walk_nodes(root)}

    values: dict[str, str] = {}
    for node in _walk_nodes(root):
        parts = []
        for site in varying_sites:
            states = per_site_states[site]
            assert states is not None
            parts.append(f"{states[node.name]}{site}")
        values[node.name] = "/".join(parts)
    return values


def _color_by_genotype_single_site(
    root: TreeNode, gene: str, site: int
) -> dict[str, str] | None:
    """Pre-order walk inferring the state at (gene, site) for every node.

    Returns ``None`` when the site has zero mutations in the tree (invariant —
    the caller drops it from the haplotype label, or labels every node
    ``"<no variation>"`` when *all* requested sites are invariant).
    Otherwise returns ``{node.name: letter}``.
    """
    # Pass 1: collect every (gene, site) mutation along with the path-from-root
    # depth at which it was applied. The earliest mutation's "from" letter is
    # the root's state at the site.
    mutations_seen: list[tuple[int, str, str]] = []  # (depth, from_letter, to_letter)

    def collect(node: TreeNode, depth: int) -> None:
        for mut in node.branch_attrs.get("mutations", {}).get(gene, []) or []:
            m = _MUTATION_RE.match(mut)
            if m is None:
                continue
            from_letter, site_str, to_letter = m.group(1), m.group(2), m.group(3)
            if int(site_str) == site:
                mutations_seen.append((depth, from_letter, to_letter))
        for c in node.children:
            collect(c, depth + 1)

    collect(root, 0)
    if not mutations_seen:
        return None

    mutations_seen.sort(key=lambda t: t[0])
    root_letter = mutations_seen[0][1]

    # Pass 2: assign per-node state.
    states: dict[str, str] = {}

    def assign(node: TreeNode, current: str) -> None:
        for mut in node.branch_attrs.get("mutations", {}).get(gene, []) or []:
            m = _MUTATION_RE.match(mut)
            if m is None:
                continue
            site_str, to_letter = m.group(2), m.group(3)
            if int(site_str) == site:
                current = to_letter
        states[node.name] = current
        for c in node.children:
            assign(c, current)

    assign(root, root_letter)
    return states


def _ordered_categories(values: Iterator[str] | list[str]) -> list[str]:
    """Return unique category labels in legend display order.

    Real categories are sorted by descending count (ties broken
    alphabetically), matching Auspice's `sortedDomain` for non-
    clade-membership traits — the most common category lands at index 0
    so it gets the first slot of :data:`_AUSPICE_PALETTE[N]`.
    ``"unknown"`` (if present) is pinned to the end regardless of count.
    ``"<no variation>"`` is only ever the sole category (when every
    requested site is invariant); in that case it stands alone.
    """
    counts = Counter(values)
    if set(counts) == {_NO_VARIATION}:
        return [_NO_VARIATION]
    has_unknown = _UNKNOWN in counts
    real = [c for c in counts if c != _UNKNOWN]
    real.sort(key=lambda c: (-counts[c], c))
    if has_unknown:
        real.append(_UNKNOWN)
    return real


def _resolve_scale(
    categories: list[str],
    parsed_spec: tuple,
    auspice_meta: dict | None,
) -> tuple[list[str], list[str]]:
    """Build (domain, range_) parallel arrays for `alt.Scale`.

    Prefers ``meta.colorings[<key>].scale`` for node-attr specs. Categories
    not covered by the auspice scale (and every category for genotype specs
    or when no `auspice_meta` is supplied) fall back to
    :data:`_AUSPICE_PALETTE[K]`, where K is the number of *unmapped*
    categories — so the fallback hues come from the same per-N palette
    Auspice uses, capped at 36. ``"unknown"`` always maps to
    :data:`_GRAY`.
    """
    auspice_map: dict[str, str] = {}
    if parsed_spec[0] == "attr" and auspice_meta is not None:
        key = parsed_spec[1]
        for c in auspice_meta.get("colorings", []) or []:
            if c.get("key") == key:
                scale = c.get("scale") or []
                for entry in scale:
                    # Each entry is [value, color]; skip malformed rows.
                    if (
                        isinstance(entry, (list, tuple))
                        and len(entry) == 2
                        and isinstance(entry[0], str)
                        and isinstance(entry[1], str)
                    ):
                        auspice_map[entry[0]] = entry[1]
                break

    real_categories = [c for c in categories if c != _UNKNOWN]
    unmapped = [c for c in real_categories if c not in auspice_map]
    palette_idx = min(len(unmapped), len(_AUSPICE_PALETTE) - 1)
    fallback_palette = _AUSPICE_PALETTE[palette_idx]

    domain: list[str] = []
    range_: list[str] = []
    fallback_pos = 0
    for cat in categories:
        if cat == _UNKNOWN:
            domain.append(cat)
            range_.append(_GRAY)
            continue
        domain.append(cat)
        if cat in auspice_map:
            range_.append(auspice_map[cat])
        else:
            if fallback_palette:
                range_.append(fallback_palette[fallback_pos % len(fallback_palette)])
            else:
                range_.append(_GRAY)
            fallback_pos += 1
    return domain, range_


def _resolve_legend_title(
    color_spec: str,
    parsed_spec: tuple,
    auspice_meta: dict | None,
) -> str:
    """Use `meta.colorings[<key>].title` for attr specs when present; else
    the literal spec string."""
    if parsed_spec[0] == "attr" and auspice_meta is not None:
        key = parsed_spec[1]
        for c in auspice_meta.get("colorings", []) or []:
            if c.get("key") == key:
                title = c.get("title")
                if isinstance(title, str) and title:
                    return title
                break
    return color_spec
