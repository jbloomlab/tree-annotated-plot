"""`tree-annotated-plot` command-line entry point.

The CLI's --tree, --chart, --output options are hand-written (they are
CLI-specific data inputs without a config-object equivalent: their
*types* differ between Python and CLI surfaces, even though their
*descriptions* are single-sourced as `_config.{TREE,CHART,OUTPUT}_DESCRIPTION`).
Every other option is **auto-generated** from `PlotConfig` so its
`--help` text comes from the same `Annotated[T, "<description>"]`
metadata that documents the Python `tree_annotated_plot.plot` function. Adding a new
parameter takes one edit to `_config.py`; both surfaces pick it up.
"""

from __future__ import annotations

import dataclasses
import json
import types
import typing
from pathlib import Path
from typing import Any, Literal, get_args, get_origin, get_type_hints

import click

from ._config import (
    CHART_DESCRIPTION,
    OUTPUT_DESCRIPTION,
    TREE_DESCRIPTION,
    PlotConfig,
)
from ._plot import _build

_SCALAR_CLICK_TYPE = {int: click.INT, float: click.FLOAT, str: click.STRING}


class _ColorScaleParamType(click.ParamType):
    """Parse a `"key1=color1,key2=color2,..."` string into an ordered dict.

    Supports hex colors (e.g. ``"K=#416DCE,J.2=#59A3AA"``) — the user must
    quote the whole argument so the shell doesn't interpret `#` as a
    comment. An empty/blank value yields ``None``.
    """

    name = "color_scale"

    def convert(self, value, param, ctx):  # type: ignore[override]
        if value is None or isinstance(value, dict):
            return value
        text = str(value).strip()
        if not text:
            return None
        result: dict[str, str] = {}
        for piece in text.split(","):
            piece = piece.strip()
            if not piece:
                continue
            if "=" not in piece:
                self.fail(
                    f"expected 'key=color' pairs separated by commas; "
                    f"got {piece!r}.",
                    param,
                    ctx,
                )
            key, color = piece.split("=", 1)
            key = key.strip()
            color = color.strip()
            if not key or not color:
                self.fail(f"empty key or color in {piece!r}.", param, ctx)
            if key in result:
                self.fail(f"duplicate key {key!r} in tree_color_scale.", param, ctx)
            result[key] = color
        return result or None


_COLOR_SCALE_PARAM_TYPE = _ColorScaleParamType()


class _JsonDictParamType(click.ParamType):
    """Parse a JSON-object string into a dict.

    Used for ``--tree-color-legend-format``: any subset of Vega-Lite's
    Legend properties as a JSON object (e.g.
    ``'{"orient":"left","labelFontSize":13}'``). The user must quote the
    whole argument so the shell doesn't interpret braces or quotes.
    """

    name = "json_dict"

    def convert(self, value, param, ctx):  # type: ignore[override]
        if value is None or isinstance(value, dict):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            self.fail(f"invalid JSON: {exc}", param, ctx)
        if not isinstance(parsed, dict):
            self.fail(
                f'expected a JSON object (e.g. \'{{"orient":"left"}}\'); '
                f"got {type(parsed).__name__}.",
                param,
                ctx,
            )
        return parsed


_JSON_DICT_PARAM_TYPE = _JsonDictParamType()


def _is_str_dict(tp: Any) -> bool:
    """Return True for `dict[str, str]` only (not `dict[str, Any]`)."""
    if get_origin(tp) is dict:
        args = get_args(tp)
        return args == (str, str)
    return False


def _is_dict_any(tp: Any) -> bool:
    """Return True for `dict[str, Any]` or a bare `dict`."""
    if tp is dict:
        return True
    if get_origin(tp) is dict:
        args = get_args(tp)
        return args == (str, Any) or args == ()
    return False


def _option_for_field(field: dataclasses.Field, hints: dict) -> Any:
    """Build a `click.option(...)` decorator from a PlotConfig field.

    Handles every field shape we use:
      - bool (with default) → `--flag/--no-flag` dual form.
      - Literal[...] → `click.Choice([...])`, required if no default.
      - X | None → unwraps to X with default None. Literal | None becomes
        a Choice with default None.
      - int / float / str → click.INT / click.FLOAT / click.STRING.

    Required fields (no default) become `required=True`.
    """
    annotated = hints[field.name]
    real_type = get_args(annotated)[0]
    description = annotated.__metadata__[0]

    cli_name = "--" + field.name.replace("_", "-")
    has_default = field.default is not dataclasses.MISSING

    # Bool → dual flag.
    if real_type is bool:
        return click.option(
            f"{cli_name}/--no-{field.name.replace('_', '-')}",
            default=field.default,
            help=description,
            show_default=True,
        )

    # Literal → Choice.
    if get_origin(real_type) is Literal:
        choices = [str(c) for c in get_args(real_type)]
        kwargs: dict[str, Any] = {
            "type": click.Choice(choices),
            "help": description,
            "show_default": has_default,
        }
        if has_default:
            kwargs["default"] = field.default
        else:
            kwargs["required"] = True
        return click.option(cli_name, **kwargs)

    # dict[str, str] (with or without `| None`) → custom comma-separated parser.
    if _is_str_dict(real_type):
        return click.option(
            cli_name,
            type=_COLOR_SCALE_PARAM_TYPE,
            default=field.default if has_default else None,
            help=description,
            show_default=False,
        )

    # dict[str, Any] (with or without `| None`) → JSON-object parser.
    if _is_dict_any(real_type):
        return click.option(
            cli_name,
            type=_JSON_DICT_PARAM_TYPE,
            default=field.default if has_default else None,
            help=description,
            show_default=False,
        )

    # Optional / Union — unwrap to the non-None branch.
    origin = get_origin(real_type)
    if origin in (typing.Union, types.UnionType):
        non_none = [a for a in get_args(real_type) if a is not type(None)]
        if len(non_none) == 1:
            inner = non_none[0]
            if _is_str_dict(inner):
                return click.option(
                    cli_name,
                    type=_COLOR_SCALE_PARAM_TYPE,
                    default=field.default if has_default else None,
                    help=description,
                    show_default=False,
                )
            if _is_dict_any(inner):
                return click.option(
                    cli_name,
                    type=_JSON_DICT_PARAM_TYPE,
                    default=field.default if has_default else None,
                    help=description,
                    show_default=False,
                )
            if get_origin(inner) is Literal:
                choices = [str(c) for c in get_args(inner)]
                return click.option(
                    cli_name,
                    type=click.Choice(choices),
                    default=field.default if has_default else None,
                    help=description,
                    show_default=True,
                )
            return click.option(
                cli_name,
                type=_SCALAR_CLICK_TYPE.get(inner, click.STRING),
                default=field.default if has_default else None,
                help=description,
                show_default=True,
            )

    # Plain scalar.
    kwargs = {
        "type": _SCALAR_CLICK_TYPE.get(real_type, click.STRING),
        "help": description,
        "show_default": has_default,
    }
    if has_default:
        kwargs["default"] = field.default
    else:
        kwargs["required"] = True
    return click.option(cli_name, **kwargs)


def _stack_config_options(command: Any) -> Any:
    """Apply one `click.option(...)` per PlotConfig field to `command`.

    `click.option(...)` invoked on an already-built `Command` *appends*
    to `command.params`, so iterating fields in declaration order gives
    --help in declaration order (required fields first, since
    `chart_strain_field` and `tree_strain_field` lead PlotConfig).
    """
    hints = get_type_hints(PlotConfig, include_extras=True)
    for field in dataclasses.fields(PlotConfig):
        command = _option_for_field(field, hints)(command)
    return command


@_stack_config_options
@click.command(
    name="tree-annotated-plot",
    help=(
        "Plot a phylogenetic tree alongside a Vega-Lite chart whose "
        "categorical axis is reordered to match the tree's tip order. "
        "Save the result as HTML / JSON / PNG / SVG / PDF "
        "(format is dispatched on --output's extension)."
    ),
)
@click.option(
    "--tree",
    "tree_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=TREE_DESCRIPTION,
)
@click.option(
    "--chart",
    "chart_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=CHART_DESCRIPTION,
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help=OUTPUT_DESCRIPTION,
)
def main(tree_path: Path, chart_path: Path, output_path: Path, **kwargs: Any) -> None:
    """Top-level CLI entry point."""
    config = PlotConfig(**kwargs)
    out = _build(tree_path, chart_path, config)
    out.save(str(output_path))


if __name__ == "__main__":
    main()
