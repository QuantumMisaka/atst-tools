"""Tests for the stable public Python API boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import FakeWorld, FalseyFakeWorld


def test_run_workflow_preserves_falsey_supplied_world(monkeypatch, tmp_path):
    """A falsey supplied communicator must not trigger a replacement lookup."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    supplied_world = FalseyFakeWorld()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "get_ase_world", lambda: pytest.fail("looked up a new world"))
    monkeypatch.setattr(
        services,
        "_validated_result",
        lambda config, world: world,
    )

    result = run_workflow(
        {
            "calculation": {"type": "relax", "init_structure": "x.traj"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(world=supplied_world, dry_run=True),
    )

    assert result is supplied_world


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


def test_public_dependency_error_is_typed_without_expanding_root_imports():
    """Optional runtime dependencies have a dedicated API error type."""
    from atst_tools.api.models import ATSTAPIError, UnsupportedDependencyError

    assert issubclass(UnsupportedDependencyError, ATSTAPIError)


def test_run_workflow_maps_missing_cyipopt_to_dependency_error(monkeypatch, tmp_path):
    """DMF dependency import failures remain distinguishable to API callers."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services
    from atst_tools.api.models import UnsupportedDependencyError

    dependency_error = ModuleNotFoundError("No module named 'cyipopt'")
    dependency_error.name = "cyipopt"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        services,
        "_dispatch_normalized",
        lambda *args: (_ for _ in ()).throw(dependency_error),
    )

    with pytest.raises(UnsupportedDependencyError) as excinfo:
        run_workflow(
            {
                "calculation": {"type": "relax", "init_structure": "initial.traj"},
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            },
            RunOptions(world=FakeWorld()),
        )

    assert excinfo.value.workflow == "relax"
    assert excinfo.value.context == {"dependency": "cyipopt"}
    assert excinfo.value.__cause__ is dependency_error


def test_validate_config_normalizes_mapping_without_mutating_input():
    from atst_tools.api import validate_config

    raw = {
        "calculation": {"type": "relax", "init_structure": "initial.traj"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    normalized = validate_config(raw)

    assert normalized["calculation"]["restart"] is False
    assert "restart" not in raw["calculation"]


def test_run_workflow_restart_override_precedes_schema_normalization(monkeypatch, tmp_path):
    """CLI-equivalent restart can supersede an invalid YAML restart value."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    seen = {}
    monkeypatch.chdir(tmp_path)

    def dispatch(config, options):
        seen["restart"] = config["calculation"]["restart"]

    monkeypatch.setattr(services, "_dispatch_normalized", dispatch)
    run_workflow(
        {
            "calculation": {
                "type": "relax",
                "init_structure": "initial.traj",
                "restart": "not-a-bool",
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(restart=True, world=FakeWorld()),
    )

    assert seen["restart"] is True


def test_validate_config_reads_yaml_path_with_current_directory_semantics(tmp_path: Path):
    from atst_tools.api import validate_config

    config = tmp_path / "config.yaml"
    config.write_text(
        "calculation:\n  type: relax\n  init_structure: initial.traj\n"
        "calculator:\n  name: abacus\n  abacus:\n    parameters: {}\n",
        encoding="utf-8",
    )

    assert validate_config(config)["calculation"]["init_structure"] == "initial.traj"


def test_validate_config_wraps_directory_path_error_with_public_exception(tmp_path: Path):
    """Filesystem errors from a config path stay within the public API boundary."""
    from atst_tools.api import validate_config
    from atst_tools.api.models import ConfigValidationError

    with pytest.raises(ConfigValidationError) as excinfo:
        validate_config(tmp_path)

    assert isinstance(excinfo.value.__cause__, IsADirectoryError)
    assert excinfo.value.context == {"config_source": str(tmp_path)}


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


def test_run_workflow_dry_run_ignores_stale_malformed_manifest(monkeypatch, tmp_path):
    """Validation results never consume artifacts from an earlier execution."""
    from atst_tools.api import RunOptions, run_workflow

    monkeypatch.chdir(tmp_path)
    (tmp_path / "atst_artifacts.json").write_text("not valid JSON", encoding="utf-8")

    result = run_workflow(
        {
            "calculation": {"type": "relax", "init_structure": "x.traj"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(dry_run=True),
    )

    assert result.status == "validated"
    assert result.artifacts == ()


def test_run_workflow_wraps_check_input_preflight_error(monkeypatch):
    """The public API represents preflight failures with its stable error type."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api.models import WorkflowExecutionError
    from atst_tools.scripts import main as run_cli

    preflight_error = RuntimeError("ABACUS check-input failed")
    monkeypatch.setattr(
        run_cli,
        "run_abacus_check_input_dry_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(preflight_error),
    )

    with pytest.raises(WorkflowExecutionError) as excinfo:
        run_workflow(
            {
                "calculation": {"type": "relax", "init_structure": "x.traj"},
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            },
            RunOptions(dry_run=True, check_input=True),
        )

    assert excinfo.value.workflow == "relax"
    assert excinfo.value.__cause__ is preflight_error


def test_mapping_check_input_preflight_uses_current_working_directory(monkeypatch, tmp_path):
    """Mappings must not be coerced to their repr as a fictitious config path."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.scripts import main as run_cli

    monkeypatch.chdir(tmp_path)
    observed = {}

    def preflight(config, config_path, **kwargs):
        observed["config_path"] = config_path
        return {"checked": 1, "workdirs": []}

    monkeypatch.setattr(run_cli, "run_abacus_check_input_dry_run", preflight)
    run_workflow(
        {
            "calculation": {"type": "relax", "init_structure": "initial.traj"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(dry_run=True, check_input=True, world=FakeWorld()),
    )

    assert observed["config_path"] is None


def test_run_workflow_synthesizes_missing_completed_manifest(monkeypatch, tmp_path):
    """Completed API calls never advertise a manifest the runner did not write."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda *args: None)

    result = run_workflow(
        {
            "calculation": {"type": "relax", "init_structure": "initial.traj"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(world=FakeWorld()),
    )

    manifest_path = tmp_path / result.artifact_manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["workflow"] == "relax"
    assert manifest["artifacts"] == [
        {"role": "trajectory", "path": "relax.traj"},
        {"role": "log", "path": "relax.log"},
        {"role": "final_structure", "path": "final_relaxed.traj"},
    ]


def test_run_workflow_replaces_a_stale_malformed_manifest(monkeypatch, tmp_path):
    """A completed run replaces an unreadable manifest left by an earlier run."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda *args: None)
    (tmp_path / "atst_artifacts.json").write_text("not valid JSON", encoding="utf-8")

    result = run_workflow(
        {
            "calculation": {"type": "relax", "init_structure": "initial.traj"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(world=FakeWorld()),
    )

    manifest = json.loads((tmp_path / result.artifact_manifest).read_text(encoding="utf-8"))
    assert manifest["workflow"] == "relax"
    assert manifest["metadata"]["manifest_source"] == "api_synthesized"


def test_run_workflow_preserves_a_fresh_runner_written_manifest(monkeypatch, tmp_path):
    """A valid manifest produced during this run remains the runner's source of truth."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services
    from atst_tools.utils.artifacts import write_artifact_manifest

    monkeypatch.chdir(tmp_path)

    def complete_relax(*args):
        write_artifact_manifest(
            "atst_artifacts.json",
            workflow="relax",
            artifacts=[{"role": "trajectory", "path": "runner.traj"}],
            metadata={"manifest_source": "runner"},
        )

    monkeypatch.setattr(services, "_dispatch_normalized", complete_relax)
    result = run_workflow(
        {
            "calculation": {"type": "relax", "init_structure": "initial.traj"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(world=FakeWorld()),
    )

    assert result.artifacts == ({"role": "trajectory", "path": "runner.traj"},)
    assert result.metadata["manifest_source"] == "runner"


def test_run_workflow_refreshes_synthesized_manifest_on_repeated_run(monkeypatch, tmp_path):
    """A second same-workflow run must not reuse the first API manifest."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda *args: None)
    base = {
        "calculation": {"type": "relax", "init_structure": "initial.traj"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    first = run_workflow(
        {**base, "calculation": {**base["calculation"], "trajectory": "first.traj"}},
        RunOptions(world=FakeWorld()),
    )
    second = run_workflow(
        {**base, "calculation": {**base["calculation"], "trajectory": "second.traj"}},
        RunOptions(world=FakeWorld()),
    )

    assert first.artifacts[0]["path"] == "first.traj"
    assert second.artifacts[0]["path"] == "second.traj"


def test_completed_manifest_uses_identical_barriers_on_every_rank(tmp_path):
    """A root-created manifest cannot make a later rank skip a collective."""
    from atst_tools.api import services

    config = {
        "calculation": {
            "type": "relax",
            "artifact_manifest": str(tmp_path / "atst_artifacts.json"),
        }
    }
    root = FakeWorld(size=2, rank=0)
    peer = FakeWorld(size=2, rank=1)

    services._ensure_completed_manifest(config, None, root)
    services._ensure_completed_manifest(config, None, peer)

    assert root.barriers == peer.barriers == 1


def test_dispatch_failure_is_collective_before_manifest_barriers(monkeypatch, tmp_path):
    """A peer failure is raised on every rank before manifest finalization."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services
    from atst_tools.api.models import WorkflowExecutionError

    class FailingWorld(FakeWorld):
        def sum_scalar(self, value):
            return 1

        def barrier(self):
            pytest.fail("a dispatch failure must prevent manifest barriers")

    def fail_on_rank_one(config, options):
        if options.world.rank == 1:
            raise WorkflowExecutionError("local failure", workflow="relax")
        return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", fail_on_rank_one)
    config = {
        "calculation": {"type": "relax", "init_structure": "initial.traj"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    for rank in (0, 1):
        with pytest.raises(WorkflowExecutionError):
            run_workflow(config, RunOptions(world=FailingWorld(size=2, rank=rank)))


def test_manifest_finalization_failure_is_collective_before_barriers(monkeypatch, tmp_path):
    """A root manifest-write failure cannot leave peer ranks at a barrier."""
    from atst_tools.api import services
    from atst_tools.api.models import WorkflowExecutionError

    class FailingWorld(FakeWorld):
        def sum_scalar(self, value):
            return 1

        def barrier(self):
            pytest.fail("a manifest-write failure must prevent barriers")

    monkeypatch.setattr(
        services,
        "write_artifact_manifest",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk failure")),
    )
    config = {
        "calculation": {
            "type": "relax",
            "artifact_manifest": str(tmp_path / "atst_artifacts.json"),
        }
    }

    for rank in (0, 1):
        with pytest.raises(WorkflowExecutionError):
            services._ensure_completed_manifest(config, None, FailingWorld(size=2, rank=rank))


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


def test_run_workflow_reads_relax_final_atoms(monkeypatch, tmp_path):
    """A Relax runner that returns ``None`` exposes its established final structure."""
    from ase import Atoms
    from ase.io import write
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    expected = Atoms("H", positions=[[1.2, 0.0, 0.0]])

    def complete_relax(*args):
        write("final_relaxed.traj", expected)
        return None

    monkeypatch.setattr(services, "_dispatch_normalized", complete_relax)
    relax_result = run_workflow(
        {
            "calculation": {"type": "relax", "init_structure": "initial.traj"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(world=FakeWorld()),
    )

    assert relax_result.final_atoms is not expected
    assert relax_result.final_atoms.get_positions() == pytest.approx(expected.get_positions())


def test_run_workflow_does_not_expose_dmf_summary_as_final_atoms(monkeypatch, tmp_path):
    """A DMF summary mapping is not an atomistic final outcome."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda *args: {"workflow": "dmf"})
    result = run_workflow(
        {
            "calculation": {"type": "dmf", "init_file": "a.traj", "final_file": "b.traj"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(world=FakeWorld()),
    )

    assert result.final_atoms is None


def test_public_ccqn_uses_private_atoms_and_marks_supplied_backend(monkeypatch, tmp_path):
    """The embedded API must neither reconstruct the calculator nor mutate inputs."""
    from ase import Atoms
    from helpers import DummyCalc
    from atst_tools.api import CCQNOptions, run_ccqn

    atoms = Atoms("H2", positions=[[0, 0, 0], [0.8, 0, 0]])
    calculator = DummyCalc()
    monkeypatch.setattr(
        "atst_tools.mep.ccqn.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: pytest.fail("factory used"),
    )
    monkeypatch.setattr("atst_tools.mep.ccqn.CCQNOptimizer.run", lambda self, **kwargs: None)

    result = run_ccqn(
        atoms,
        calculator,
        CCQNOptions(
            reactive_bonds="1-2",
            artifact_manifest=str(tmp_path / "manifest.json"),
        ),
    )

    assert atoms.calc is None
    assert result.final_atoms is not atoms
    assert result.metadata["backend_source"] == "provided"


def test_ccqn_options_config_maps_only_supported_ccqn_schema_fields():
    """The embedded API exposes CCQN controls, never backend configuration."""
    from atst_tools.api import CCQNOptions
    from atst_tools.api import services
    from atst_tools.utils.config_schema import CCQNCalculation

    options = CCQNOptions(
        fmax=0.02,
        max_steps=12,
        trajectory="embedded.traj",
        logfile="embedded.log",
        final_structure="embedded.extxyz",
        e_vector_method="ic",
        reactive_bonds=[(0, 1)],
        auto_reactive_bonds={"enabled": True, "max_modes": 3},
        mode_manifest="modes.json",
        diagnostics_file="diagnostics.json",
        ic_mode="sum",
        cos_phi=0.4,
        trust_radius_uphill=0.12,
        trust_radius_saddle_initial=0.08,
        hessian=True,
        accept_initial_converged=True,
        artifact_manifest="artifacts.json",
    )

    config = services._ccqn_options_to_config(options)

    assert set(config) <= set(CCQNCalculation.model_fields)
    assert config == {
        "type": "ccqn",
        "fmax": 0.02,
        "max_steps": 12,
        "trajectory": "embedded.traj",
        "logfile": "embedded.log",
        "final_structure": "embedded.extxyz",
        "e_vector_method": "ic",
        "reactive_bonds": [(0, 1)],
        "auto_reactive_bonds": {"enabled": True, "max_modes": 3},
        "mode_manifest": "modes.json",
        "diagnostics_file": "diagnostics.json",
        "ic_mode": "sum",
        "cos_phi": 0.4,
        "trust_radius_uphill": 0.12,
        "trust_radius_saddle_initial": 0.08,
        "hessian": True,
        "accept_initial_converged": True,
        "artifact_manifest": "artifacts.json",
    }
