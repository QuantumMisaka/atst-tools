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


@pytest.mark.parametrize(
    ("dependency_error", "expected_dependency"),
    [
        (ModuleNotFoundError("No module named 'deepmd'"), "deepmd"),
    ],
)
def test_run_workflow_maps_missing_deepmd_to_dependency_error(
    monkeypatch, tmp_path, dependency_error, expected_dependency
):
    """Configured DP imports remain distinguishable to public API callers."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services
    from atst_tools.api.models import UnsupportedDependencyError

    if isinstance(dependency_error, ModuleNotFoundError):
        dependency_error.name = "deepmd"
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
                "calculator": {"name": "dp", "dp": {"model": "model.pt"}},
            },
            RunOptions(world=FakeWorld()),
        )

    assert excinfo.value.workflow == "relax"
    assert excinfo.value.context == {"dependency": expected_dependency}
    assert excinfo.value.__cause__ is dependency_error


def test_run_workflow_maps_deepmd_missing_import_cause_to_dependency_error(
    monkeypatch, tmp_path
):
    """A wrapped DeepMD import error retains its missing-module evidence."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services
    from atst_tools.api.models import UnsupportedDependencyError

    missing_module = ModuleNotFoundError("No module named 'deepmd.calculator'")
    missing_module.name = "deepmd.calculator"
    wrapper = ImportError("calculator initialization failed")
    wrapper.__cause__ = missing_module
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        services,
        "_dispatch_normalized",
        lambda *args: (_ for _ in ()).throw(wrapper),
    )

    with pytest.raises(UnsupportedDependencyError) as excinfo:
        run_workflow(
            {
                "calculation": {"type": "relax", "init_structure": "initial.traj"},
                "calculator": {"name": "dp", "dp": {"model": "model.pt"}},
            },
            RunOptions(world=FakeWorld()),
        )

    assert excinfo.value.context == {"dependency": "deepmd"}
    assert excinfo.value.__cause__ is wrapper


def test_run_workflow_keeps_corrupt_deepmd_model_as_execution_error(monkeypatch, tmp_path):
    """A model failure mentioning DeepMD is not evidence of a missing module."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services
    from atst_tools.api.models import WorkflowExecutionError

    corrupt_model_error = RuntimeError("DeepMD model file is corrupt")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        services,
        "_dispatch_normalized",
        lambda *args: (_ for _ in ()).throw(corrupt_model_error),
    )

    with pytest.raises(WorkflowExecutionError) as excinfo:
        run_workflow(
            {
                "calculation": {"type": "relax", "init_structure": "initial.traj"},
                "calculator": {"name": "dp", "dp": {"model": "corrupt.pt"}},
            },
            RunOptions(world=FakeWorld()),
        )

    assert excinfo.value.__cause__ is corrupt_model_error


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


def test_run_workflow_rejects_check_input_without_dry_run_before_dispatch(monkeypatch):
    """The public API enforces the CLI's check-input dry-run prerequisite."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services
    from atst_tools.api.models import ConfigValidationError

    monkeypatch.setattr(
        services,
        "_dispatch_normalized",
        lambda *args: pytest.fail("invalid options reached workflow dispatch"),
    )

    with pytest.raises(ConfigValidationError, match="--check-input requires --dry-run"):
        run_workflow(
            {
                "calculation": {"type": "relax", "init_structure": "x.traj"},
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            },
            RunOptions(check_input=True),
        )


@pytest.mark.parametrize("dry_run", [False, True])
def test_configured_dp_result_records_deepmd_backend_source(
    monkeypatch, tmp_path, dry_run
):
    """Configured DP provenance is distinct from caller-supplied injection."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    if not dry_run:
        monkeypatch.setattr(services, "_dispatch_normalized", lambda *args: None)

    result = run_workflow(
        {
            "calculation": {"type": "relax", "init_structure": "initial.traj"},
            "calculator": {"name": "dp", "dp": {"model": "model.pt"}},
        },
        RunOptions(dry_run=dry_run, world=FakeWorld()),
    )

    assert result.metadata["backend_source"] == "deepmd"


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


def test_yaml_check_input_preflight_uses_api_current_working_directory(
    monkeypatch, tmp_path
):
    """Public YAML paths must not change API preflight path-resolution semantics."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.scripts import main as run_cli

    config_dir = tmp_path / "yaml-parent"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        "calculation:\n  type: relax\n  init_structure: initial.traj\n"
        "calculator:\n  name: abacus\n  abacus:\n    parameters: {}\n",
        encoding="utf-8",
    )
    api_cwd = tmp_path / "api-cwd"
    api_cwd.mkdir()
    monkeypatch.chdir(api_cwd)
    observed = {}

    def preflight(config, config_path, **kwargs):
        observed["config_path"] = config_path
        observed["base_dir"] = kwargs.get("base_dir")
        return {"checked": 1, "workdirs": []}

    monkeypatch.setattr(run_cli, "run_abacus_check_input_dry_run", preflight)
    run_workflow(config_path, RunOptions(dry_run=True, check_input=True, world=FakeWorld()))

    assert observed == {"config_path": str(config_path), "base_dir": api_cwd}


def test_cli_yaml_check_input_preflight_preserves_yaml_parent_base_dir(
    monkeypatch, tmp_path
):
    """The legacy CLI adapter retains its established YAML-parent behavior."""
    from atst_tools.api import RunOptions
    from atst_tools.api import services
    from atst_tools.scripts import main as run_cli

    config_dir = tmp_path / "yaml-parent"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        "calculation:\n  type: relax\n  init_structure: initial.traj\n"
        "calculator:\n  name: abacus\n  abacus:\n    parameters: {}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    observed = {}

    def preflight(config, config_path, **kwargs):
        observed["config_path"] = config_path
        observed["base_dir"] = kwargs.get("base_dir")
        return {"checked": 1, "workdirs": []}

    monkeypatch.setattr(run_cli, "run_abacus_check_input_dry_run", preflight)
    services.run_workflow_from_cli(
        config_path, RunOptions(dry_run=True, check_input=True, world=FakeWorld())
    )

    assert observed == {"config_path": str(config_path), "base_dir": None}


def test_run_workflow_wraps_mpi_bootstrap_dependency_failure(monkeypatch):
    """MPI bootstrap errors are typed at the public API boundary."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services
    from atst_tools.api.models import UnsupportedDependencyError

    missing_mpi4py = ModuleNotFoundError("No module named 'mpi4py'")
    missing_mpi4py.name = "mpi4py"
    bootstrap_error = RuntimeError("MPI launcher requires mpi4py")
    bootstrap_error.__cause__ = missing_mpi4py
    monkeypatch.setattr(
        services,
        "get_ase_world",
        lambda: (_ for _ in ()).throw(bootstrap_error),
    )

    with pytest.raises(UnsupportedDependencyError) as excinfo:
        run_workflow(
            {
                "calculation": {"type": "relax", "init_structure": "x.traj"},
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            },
            RunOptions(dry_run=True),
        )

    assert excinfo.value.context == {"dependency": "mpi4py"}
    assert excinfo.value.__cause__ is bootstrap_error


def test_cli_adapter_preserves_raw_mpi_bootstrap_failure(monkeypatch):
    """Legacy CLI callers retain the original communicator-bootstrap error."""
    from atst_tools.api import RunOptions
    from atst_tools.api import services

    bootstrap_error = RuntimeError("MPI launcher requires mpi4py")
    monkeypatch.setattr(
        services,
        "get_ase_world",
        lambda: (_ for _ in ()).throw(bootstrap_error),
    )

    with pytest.raises(RuntimeError) as excinfo:
        services.run_workflow_from_cli(
            {
                "calculation": {"type": "relax", "init_structure": "x.traj"},
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            },
            RunOptions(dry_run=True),
        )

    assert excinfo.value is bootstrap_error


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
