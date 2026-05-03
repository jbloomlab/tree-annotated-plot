"""`tree-annotated-plot` command-line entry point.

The CLI's --tree, --chart-spec, --output options are hand-written (they
are CLI-specific data inputs without a config-object equivalent).
Every other option is **auto-generated** from `PlotConfig` so its
`--help` text comes from the same `Annotated[T, "<description>"]`
metadata that documents the Python `tap.plot` function. Adding a new
parameter takes one edit to `_config.py`; both surfaces pick it up.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from pathlib import Path
from typing import Any, Literal, get_args, get_origin, get_type_hints

import click

from ._config import PlotConfig
from ._plot import _build

_SCALAR_CLICK_TYPE = {int: click.INT, float: click.FLOAT, str: click.STRING}


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

    # Optional / Union — unwrap to the non-None branch.
    origin = get_origin(real_type)
    if origin in (typing.Union, types.UnionType):
        non_none = [a for a in get_args(real_type) if a is not type(None)]
        if len(non_none) == 1:
            inner = non_none[0]
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

    Decorators are applied in reverse so the help text lists the fields
    in declaration order (Click's stacked-option behavior).
    """
    hints = get_type_hints(PlotConfig, include_extras=True)
    fields = list(dataclasses.fields(PlotConfig))
    for field in reversed(fields):
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
    help="Path to an Auspice JSON tree (v2).",
)
@click.option(
    "--chart-spec",
    "chart_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=(
        "Path to a saved Vega-Lite chart spec — either *.json (canonical) "
        "or *.html (extracted from altair's default save template)."
    ),
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help=(
        "Where to save the combined plot. Format inferred from extension: "
        ".html, .json, .png, .svg, .pdf."
    ),
)
def main(tree_path: Path, chart_path: Path, output_path: Path, **kwargs: Any) -> None:
    """Top-level CLI entry point."""
    config = PlotConfig(**kwargs)
    out = _build(tree_path, chart_path, config)
    out.save(str(output_path))


if __name__ == "__main__":
    main()
