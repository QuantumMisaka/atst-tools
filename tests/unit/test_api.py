"""Tests for the stable public Python API boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import FakeWorld


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


@pytest.mark.parametrize(
    "workflow",
    [
        "neb",
        "autoneb",
        "dimer",
        "sella",
        "ccqn",
        "d2s",
        "relax",
        "vibration",
        "irc",
        "md",
        "dmf",
    ],
)
def test_run_workflow_dispatches_every_governed_type(monkeypatch, tmp_path, workflow):
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    seen = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        services,
        "_dispatch_normalized",
        lambda config, options: seen.append(config["calculation"]["type"]) or None,
    )
    (tmp_path / "atst_artifacts.json").write_text(
        json.dumps({"workflow": workflow, "artifacts": [], "metadata": {}, "stages": []})
    )
    calculation = {"type": workflow}
    if workflow in {"dimer", "sella", "ccqn", "relax", "vibration", "irc", "md"}:
        calculation["init_structure"] = "x.traj"
    elif workflow in {"d2s", "dmf"}:
        calculation.update(init_file="a.traj", final_file="b.traj")
    else:
        calculation["init_chain"] = "chain.traj"
    if workflow == "ccqn":
        calculation["reactive_bonds"] = "1-2"

    result = run_workflow(
        {
            "calculation": calculation,
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(),
    )

    assert seen == [workflow]
    assert result.workflow == workflow
    assert result.status == "complete"


def test_run_workflow_dry_run_returns_no_in_memory_atoms(monkeypatch):
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.setattr(
        services,
        "_dispatch_normalized",
        lambda *args: pytest.fail("dry run dispatched"),
    )

    result = run_workflow(
        {
            "calculation": {"type": "relax", "init_structure": "x.traj"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(dry_run=True),
    )

    assert result.status == "validated"
    assert result.final_atoms is None


def test_path_result_is_root_only(monkeypatch, tmp_path):
    from ase import Atoms
    from ase.calculators.singlepoint import SinglePointCalculator
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    images = [Atoms("H"), Atoms("H"), Atoms("H")]
    for energy, image in enumerate(images):
        image.calc = SinglePointCalculator(image, energy=float(energy), forces=[[0, 0, 0]])
    monkeypatch.setattr(services, "_dispatch_normalized", lambda *args: images)
    (tmp_path / "atst_artifacts.json").write_text(
        '{"workflow":"neb","artifacts":[],"metadata":{},"stages":[]}'
    )

    result = run_workflow(
        {
            "calculation": {"type": "neb", "init_chain": "chain.traj", "parallel": True},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(world=FakeWorld(size=1, rank=0)),
    )

    assert len(result.final_images) == 3
    assert result.ts_atoms is not None


def test_path_result_is_not_returned_by_non_root(monkeypatch, tmp_path):
    from ase import Atoms
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda *args: [Atoms("H")] * 3)
    (tmp_path / "atst_artifacts.json").write_text(
        '{"workflow":"neb","artifacts":[],"metadata":{},"stages":[]}'
    )

    result = run_workflow(
        {
            "calculation": {"type": "neb", "init_chain": "chain.traj", "parallel": True},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(world=FakeWorld(size=3, rank=1)),
    )

    assert result.is_root is False
    assert result.final_images is None
    assert result.ts_atoms is None
