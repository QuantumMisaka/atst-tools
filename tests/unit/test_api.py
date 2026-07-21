"""Tests for the stable public Python API boundary."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_public_api_has_only_the_supported_contract():
    import atst_tools.api as api

    assert api.__all__ == [
        "CCQNOptions",
        "RunOptions",
        "WorkflowResult",
        "validate_config",
        "run_workflow",
        "run_ccqn",
    ]


def test_validate_config_normalizes_mapping_without_mutating_input():
    from atst_tools.api import validate_config

    raw = {
        "calculation": {"type": "relax", "init_structure": "initial.traj"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    normalized = validate_config(raw)

    assert normalized["calculation"]["restart"] is False
    assert "restart" not in raw["calculation"]


def test_validate_config_reads_yaml_path_with_current_directory_semantics(tmp_path: Path):
    from atst_tools.api import validate_config

    config = tmp_path / "config.yaml"
    config.write_text(
        "calculation:\n  type: relax\n  init_structure: initial.traj\n"
        "calculator:\n  name: abacus\n  abacus:\n    parameters: {}\n",
        encoding="utf-8",
    )

    assert validate_config(config)["calculation"]["init_structure"] == "initial.traj"


def test_validate_config_wraps_schema_error_with_public_exception():
    from atst_tools.api import validate_config
    from atst_tools.api.models import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="calculation"):
        validate_config({"calculation": {"type": "not-a-workflow"}})
