"""Workflow artifact manifest helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "atst-artifacts-v1"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return _jsonable(value.item())
    if isinstance(value, dict):
        return {key: _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def write_artifact_manifest(
    path: str | Path,
    *,
    workflow: str,
    artifacts: list[dict[str, Any]],
    stages: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a stable machine-readable manifest for workflow outputs."""
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "workflow": workflow,
        "metadata": metadata or {},
        "stages": stages or [],
        "artifacts": artifacts,
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(_jsonable(manifest), indent=2), encoding="utf-8")
    return manifest


def read_artifact_manifest(path: str | Path) -> dict[str, Any]:
    """Read an existing ATST artifact manifest without altering it."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
