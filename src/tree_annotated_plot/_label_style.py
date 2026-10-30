"""Per-strain styling of the tree-panel strain labels (`strain_label_styles`).

Public entry points: :func:`resolve_rules` validates and normalizes the
user's rules, and :func:`mark_props` turns them into label mark properties.

Each rule names some strains, a style (a subset of Vega-Lite text-mark
properties) and, optionally, a `when` condition. Every property a rule sets
becomes one `alt.ExprRef` on the existing label mark(s), evaluated per label:
Vega-Lite compiles a mark-level ``{"expr": ...}`` into the Vega encode block,
where ``datum`` is the label's row. That is why a property with no encoding
channel (``fontWeight``, ``fontStyle``) can still vary by strain without
duplicating the label layers. Which rules a label belongs to is carried in
one boolean column per rule (:func:`membership_column`) on the label data.

``fontSize`` is deliberately not a style key: the label strip's width is
estimated from `strain_label_font_size`, so a per-strain size would need a
different layout calculation.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import altair as alt
from altair.expr.core import Expression

# Allowed `style` keys, in the order their expressions are emitted.
STYLE_KEYS = ("fill", "opacity", "fontWeight", "fontStyle")

# Style keys that change the glyph outline. The white halo layer drawn under
# each label has to follow these so it keeps masking the leader exactly where
# the text is; `fill` and `opacity` apply to the visible text only.
_GLYPH_KEYS = frozenset({"fontWeight", "fontStyle"})

_RULE_KEYS = frozenset({"strains", "style", "when"})

_FONT_WEIGHTS = ("normal", "bold")
_NUMERIC_FONT_WEIGHTS = tuple(range(100, 1000, 100))
_FONT_STYLES = ("normal", "italic")

# Hints for style keys a user is likely to reach for that we don't accept.
_STYLE_KEY_HINTS = {
    "color": 'use "fill" to set the label color',
    "fontSize": (
        "per-strain font sizes are not supported because they change the "
        "label-strip layout; use `strain_label_font_size` for all labels"
    ),
}

# A bare Vega expression identifier, i.e. what a param name looks like.
_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


@dataclass(frozen=True)
class LabelStyleRule:
    """One validated `strain_label_styles` rule.

    `strains` holds only the strains drawn in the tree (pruned ones are
    dropped); `when` is a Vega expression string, or None for always-on.
    """

    strains: frozenset[str]
    style: dict[str, Any]
    when: str | None


def membership_column(index: int) -> str:
    """Name of the boolean label-data column marking rule `index`'s strains."""
    return f"_tap_label_style_{index}"


def resolve_rules(
    raw: Any,
    *,
    input_tip_names: Iterable[str],
    drawn_tip_names: Iterable[str],
    chart_spec: dict,
    tree_strain_field: str,
) -> tuple[list[LabelStyleRule], list[alt.Parameter]]:
    """Validate `strain_label_styles` and return ``(rules, params_to_declare)``.

    `input_tip_names` are the tree's tips before `prune_tree_to_chart`; a
    strain outside them is an error. `drawn_tip_names` are the tips left
    after pruning; strains pruned away are silently dropped from their rule.
    `params_to_declare` lists the `alt.Parameter` objects passed as `when`
    that the chart doesn't already declare, deduplicated by name.
    """
    if raw is None:
        return [], []
    if isinstance(raw, (str, bytes, Mapping)) or not isinstance(raw, Iterable):
        raise ValueError(
            "strain_label_styles must be a list of rule dicts, each with "
            f'"strains" and "style" keys; got {type(raw).__name__}.'
        )
    raw_rules = list(raw)
    if not raw_rules:
        return [], []

    input_tips = set(input_tip_names)
    drawn_tips = set(drawn_tip_names)
    declared = _declared_params(chart_spec)
    rule_params: dict[str, alt.Parameter] = {}
    for rule in raw_rules:
        when = rule.get("when") if isinstance(rule, Mapping) else None
        if isinstance(when, alt.Parameter):
            rule_params.setdefault(_param_name(when), when)

    rules: list[LabelStyleRule] = []
    for i, rule in enumerate(raw_rules):
        if not isinstance(rule, Mapping):
            raise ValueError(
                f"strain_label_styles[{i}] must be a dict with "
                f'"strains" and "style" keys; got {type(rule).__name__}.'
            )
        unknown_keys = set(rule) - _RULE_KEYS
        if unknown_keys:
            raise ValueError(
                f"strain_label_styles[{i}] has unknown key(s) "
                f"{sorted(unknown_keys)}; allowed keys are "
                f"{sorted(_RULE_KEYS)}."
            )
        for required in ("strains", "style"):
            if required not in rule:
                raise ValueError(
                    f"strain_label_styles[{i}] is missing the required "
                    f"{required!r} key."
                )
        rules.append(
            LabelStyleRule(
                strains=_resolve_strains(
                    i,
                    rule["strains"],
                    input_tips=input_tips,
                    drawn_tips=drawn_tips,
                    tree_strain_field=tree_strain_field,
                ),
                style=_validate_style(i, rule["style"]),
                when=_resolve_when(
                    i,
                    rule.get("when"),
                    declared=declared,
                    rule_param_names=set(rule_params),
                ),
            )
        )

    to_declare = [p for name, p in rule_params.items() if name not in declared]
    return rules, to_declare


def mark_props(
    rules: list[LabelStyleRule], *, default_font_weight: str
) -> tuple[dict[str, alt.ExprRef], dict[str, alt.ExprRef]]:
    """Return ``(halo_props, text_props)``: mark properties for the label layers.

    Only properties that some rule sets get an expression; the rest keep the
    marks' static settings. Each expression is a chain of ternaries built in
    rule order, so the last rule's test is evaluated first and later rules
    win where strains overlap. The fallback is the label's unstyled value:
    `default_font_weight` for ``fontWeight``, and Vega-Lite's text defaults
    (black, fully opaque, upright) for the others.
    """
    defaults = {
        "fill": "black",
        "opacity": 1,
        "fontWeight": default_font_weight,
        "fontStyle": "normal",
    }
    text_props: dict[str, alt.ExprRef] = {}
    for key in STYLE_KEYS:
        expr = json.dumps(defaults[key])
        styled = False
        for i, rule in enumerate(rules):
            if key not in rule.style:
                continue
            test = f"datum[{json.dumps(membership_column(i))}]"
            if rule.when is not None:
                test = f"({rule.when}) && {test}"
            expr = f"{test} ? {json.dumps(rule.style[key])} : ({expr})"
            styled = True
        if styled:
            text_props[key] = alt.ExprRef(expr)
    halo_props = {k: v for k, v in text_props.items() if k in _GLYPH_KEYS}
    return halo_props, text_props


def _resolve_strains(
    index: int,
    strains: Any,
    *,
    input_tips: set[str],
    drawn_tips: set[str],
    tree_strain_field: str,
) -> frozenset[str]:
    if isinstance(strains, (str, bytes, Mapping)) or not isinstance(strains, Iterable):
        raise ValueError(
            f'strain_label_styles[{index}]["strains"] must be a list of '
            f"strain names; got {type(strains).__name__} {strains!r}."
        )
    strains = list(strains)
    if not strains:
        raise ValueError(
            f'strain_label_styles[{index}]["strains"] is empty; a rule must '
            "name at least one strain."
        )
    non_str = [s for s in strains if not isinstance(s, str)]
    if non_str:
        raise ValueError(
            f'strain_label_styles[{index}]["strains"] must contain strings; '
            f"got {non_str[:5]!r}."
        )
    unknown = sorted(set(strains) - input_tips)
    if unknown:
        raise ValueError(
            f'strain_label_styles[{index}]["strains"] has {len(unknown)} '
            "strain(s) that are not tips of the tree under "
            f"tree_strain_field={tree_strain_field!r}.\n"
            f"Sample unknown strains: {unknown[:5]}\n"
            f"Sample tree tips:       {sorted(input_tips)[:5]}"
        )
    return frozenset(s for s in strains if s in drawn_tips)


def _validate_style(index: int, style: Any) -> dict[str, Any]:
    where = f'strain_label_styles[{index}]["style"]'
    if not isinstance(style, Mapping) or not style:
        raise ValueError(
            f"{where} must be a non-empty dict of label properties (any of "
            f"{list(STYLE_KEYS)}); got {style!r}."
        )
    for key, value in style.items():
        if key not in STYLE_KEYS:
            hint = _STYLE_KEY_HINTS.get(key)
            raise ValueError(
                f"{where} has unsupported key {key!r}; allowed keys are "
                f"{list(STYLE_KEYS)}." + (f" Hint: {hint}." if hint else "")
            )
        if key == "fill":
            ok = isinstance(value, str) and bool(value.strip())
            expected = "a non-empty color string"
        elif key == "opacity":
            ok = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and 0 <= value <= 1
            )
            expected = "a number from 0 to 1"
        elif key == "fontWeight":
            ok = value in _FONT_WEIGHTS or (
                isinstance(value, int)
                and not isinstance(value, bool)
                and value in _NUMERIC_FONT_WEIGHTS
            )
            expected = f"one of {list(_FONT_WEIGHTS)} or 100-900 in steps of 100"
        else:  # fontStyle
            ok = value in _FONT_STYLES
            expected = f"one of {list(_FONT_STYLES)}"
        if not ok:
            raise ValueError(f"{where}[{key!r}] must be {expected}; got {value!r}.")
    return dict(style)


def _resolve_when(
    index: int,
    when: Any,
    *,
    declared: dict[str, dict],
    rule_param_names: set[str],
) -> str | None:
    """Return `when` as a Vega expression string (None means always on)."""
    where = f'strain_label_styles[{index}]["when"]'
    if when is None:
        return None
    if isinstance(when, alt.Parameter):
        if when.param_type != "variable":
            raise ValueError(
                f"{where} is a selection parameter ({_param_name(when)!r}); "
                "only variable parameters (alt.param(...), e.g. bound to a "
                "checkbox) are supported, since the label data doesn't carry "
                "the fields a selection tests."
            )
        return _param_name(when)
    if isinstance(when, alt.ParameterExpression):
        expr = when.to_dict().get("expr")
    elif isinstance(when, Expression):
        expr = when.to_dict()
    elif isinstance(when, str):
        expr = when
    else:
        raise ValueError(
            f"{where} must be a param name or Vega expression string, an "
            "alt.Parameter, or an altair parameter expression; got "
            f"{type(when).__name__}."
        )
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError(f"{where} must not be empty; got {when!r}.")
    expr = expr.strip()
    if _IDENTIFIER.fullmatch(expr) and expr not in rule_param_names:
        if expr not in declared:
            raise ValueError(
                f"{where}={expr!r} names no parameter declared in the chart. "
                f"Declared parameters: {sorted(declared) or 'none'}. Declare "
                "it on the chart (e.g. chart.add_params(alt.param(name="
                f"{expr!r}, value=True, bind=alt.binding_checkbox()))) before "
                "saving it, or, in Python, pass the alt.Parameter itself."
            )
        if "select" in declared[expr]:
            raise ValueError(
                f"{where}={expr!r} is a selection parameter; only variable "
                "parameters (e.g. bound to a checkbox) are supported, since "
                "the label data doesn't carry the fields a selection tests."
            )
    return expr


def _declared_params(spec: Any) -> dict[str, dict]:
    """Map every param name declared anywhere in a chart spec to its definition."""
    found: dict[str, dict] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            params = node.get("params")
            if isinstance(params, list):
                for p in params:
                    if isinstance(p, dict) and isinstance(p.get("name"), str):
                        found.setdefault(p["name"], p)
            for k, v in node.items():
                if k in ("data", "datasets"):
                    continue
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return found


def _param_name(param: alt.Parameter) -> str:
    name = param.name
    if hasattr(name, "to_dict"):
        name = name.to_dict()
    return str(name)
