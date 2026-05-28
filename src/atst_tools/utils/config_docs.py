"""Markdown export helpers for governed YAML variables."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from atst_tools.utils.config_schema import (
    CONFIG_VERSION,
    ATSTConfig,
    AutoNEBCalculation,
    CCQNCalculation,
    D2SCalculation,
    DimerCalculation,
    IRCCalculation,
    NEBCalculation,
    RelaxCalculation,
    SellaCalculation,
    VibrationCalculation,
)


CALCULATION_MODELS: tuple[type[BaseModel], ...] = (
    NEBCalculation,
    AutoNEBCalculation,
    DimerCalculation,
    SellaCalculation,
    CCQNCalculation,
    D2SCalculation,
    RelaxCalculation,
    VibrationCalculation,
    IRCCalculation,
)


def _literal_values(annotation: Any) -> tuple[Any, ...] | None:
    origin = get_origin(annotation)
    if origin is None:
        return None
    if getattr(origin, "__name__", "") == "Literal":
        return get_args(annotation)
    return None


def _type_name(annotation: Any) -> str:
    literal = _literal_values(annotation)
    if literal is not None:
        return " | ".join(repr(item) for item in literal)

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (list, tuple):
        inner = ", ".join(_type_name(arg) for arg in args) if args else "any"
        name = "list" if origin is list else "tuple"
        return f"{name}[{inner}]"
    if origin is dict:
        if len(args) == 2:
            return f"dict[{_type_name(args[0])}, {_type_name(args[1])}]"
        return "dict"
    if origin in (UnionType, Union):
        return " | ".join(_type_name(arg) for arg in args)
    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            return "dict"
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _model_from_annotation(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    origin = get_origin(annotation)
    if origin in (UnionType, Union):
        for arg in get_args(annotation):
            model = _model_from_annotation(arg)
            if model is not None:
                return model
    return None


def _default_text(field: FieldInfo) -> str:
    if field.is_required():
        return "required"
    if field.default_factory is not None:
        return "schema defaults"
    if field.default is None:
        return "null"
    return repr(field.default)


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _collect_model_rows(
    model: type[BaseModel],
    prefix: str,
    level: str,
    rows: list[dict[str, str]],
) -> None:
    for name, field in model.model_fields.items():
        path = f"{prefix}.{name}" if prefix else name
        annotation = field.annotation
        nested_model = _model_from_annotation(annotation)
        if nested_model is not None:
            rows.append(
                {
                    "path": path,
                    "level": level,
                    "type": "dict",
                    "default": _default_text(field),
                    "description": field.description or "",
                }
            )
            _collect_model_rows(nested_model, path, path, rows)
            continue

        rows.append(
            {
                "path": path,
                "level": level,
                "type": _type_name(annotation),
                "default": _default_text(field),
                "description": field.description or "",
            }
        )


def generate_yaml_variable_markdown() -> str:
    """Return a markdown table of user-facing non-calculator YAML variables."""
    rows: list[dict[str, str]] = []
    config_version_field = ATSTConfig.model_fields["config_version"]
    rows.append(
        {
            "path": "config_version",
            "level": "top-level",
            "type": "str",
            "default": repr(CONFIG_VERSION),
            "description": config_version_field.description or "",
        }
    )

    for model in CALCULATION_MODELS:
        calc_type = get_args(model.model_fields["type"].annotation)[0]
        _collect_model_rows(model, f"calculation.{calc_type}", f"calculation.type={calc_type}", rows)

    lines = [
        "# YAML Input Variables",
        "",
        "This file is generated from `src/atst_tools/utils/config_schema.py`.",
        "It lists governed non-calculator YAML variables for `atst run`.",
        "Calculator backend variables are documented separately in `CONFIG_REFERENCE.md`.",
        "",
        "| YAML path | Level | Type | Default | Meaning |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {path} | {level} | `{type}` | `{default}` | {description} |".format(
                path=_escape(row["path"]),
                level=_escape(row["level"]),
                type=_escape(row["type"]),
                default=_escape(row["default"]),
                description=_escape(row["description"]),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """Write generated YAML variable documentation to a markdown file."""
    parser = argparse.ArgumentParser(description="Generate ATST-Tools YAML variable markdown.")
    parser.add_argument(
        "--output",
        default="docs/user/YAML_INPUT_VARIABLES.md",
        help="Output markdown path.",
    )
    args = parser.parse_args(argv)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_yaml_variable_markdown(), encoding="utf-8")


if __name__ == "__main__":
    main()
