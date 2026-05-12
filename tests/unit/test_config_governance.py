from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin

from pydantic import BaseModel

from atst_tools.utils.config_docs import CALCULATION_MODELS, generate_yaml_variable_markdown
from atst_tools.utils.config_schema import ATSTConfig, json_schema


def _walk_model_fields(model: type[BaseModel]):
    for name, field in model.model_fields.items():
        yield model, name, field
        nested = _nested_model(field.annotation)
        if nested is not None:
            yield from _walk_model_fields(nested)


def _nested_model(annotation):
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    if get_origin(annotation) in (UnionType, Union):
        for arg in get_args(annotation):
            nested = _nested_model(arg)
            if nested is not None:
                return nested
    return None


def test_non_calculator_schema_fields_have_descriptions():
    models = [ATSTConfig, *CALCULATION_MODELS]
    missing = []
    for model in models:
        for _, name, field in _walk_model_fields(model):
            if name == "calculator":
                continue
            if not field.description:
                missing.append(f"{model.__name__}.{name}")

    assert missing == []


def test_generated_yaml_variable_markdown_is_current():
    docs_path = Path("docs/user/YAML_INPUT_VARIABLES.md")

    assert docs_path.read_text(encoding="utf-8") == generate_yaml_variable_markdown()


def test_redundant_public_yaml_paths_are_not_in_schema():
    schema_text = str(json_schema())

    assert "endpoint_fmax" not in schema_text
    assert "endpoint_max_steps" not in schema_text
    assert "'mag'" not in schema_text
    assert "Thermochemistry temperature in Kelvin" not in schema_text
