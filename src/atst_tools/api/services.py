"""Application services backing the stable Python API."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from atst_tools.api.models import ConfigValidationError
from atst_tools.utils.artifacts import read_artifact_manifest
from atst_tools.utils.config import ConfigLoader


def _load_and_normalize(config_source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load and normalize a copied configuration source through the schema."""
    try:
        raw = (
            ConfigLoader.load(str(config_source))
            if isinstance(config_source, (str, Path))
            else deepcopy(dict(config_source))
        )
        return ConfigLoader.normalize(raw)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        raise ConfigValidationError(
            str(exc), context={"config_source": str(config_source)}
        ) from exc


def _read_manifest(path: str | Path) -> dict[str, Any]:
    """Read a workflow artifact manifest without changing it."""
    return read_artifact_manifest(path)


def validate_config(config_source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached schema-normalized ATST configuration."""
    return _load_and_normalize(config_source)


def run_workflow(*args: Any, **kwargs: Any) -> Any:
    """Placeholder for configuration-driven workflow execution.

    This implementation is supplied by the subsequent workflow-service task.
    """
    raise NotImplementedError("run_workflow() is not implemented yet")


def run_ccqn(*args: Any, **kwargs: Any) -> Any:
    """Placeholder for embedded CCQN execution.

    This implementation is supplied by the subsequent CCQN-service task.
    """
    raise NotImplementedError("run_ccqn() is not implemented yet")
