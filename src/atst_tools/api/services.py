"""Application services backing the stable Python API."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from atst_tools.api.models import (
    ConfigValidationError,
    MPIConfigurationError,
    RunOptions,
    WorkflowExecutionError,
    WorkflowResult,
)
from atst_tools.calculators.abacuslite_backend import BACKEND_SOURCE
from atst_tools.utils.artifacts import read_artifact_manifest
from atst_tools.utils.config import ConfigLoader
from atst_tools.utils.mpi import get_ase_world


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


def _dispatch_normalized(config: dict[str, Any], options: RunOptions) -> Any:
    """Dispatch one normalized configuration to its existing workflow runner."""
    calculation = config["calculation"]
    if options.restart:
        calculation["restart"] = True
    workflow = calculation["type"]
    calculator_name = config.get("calculator", {}).get("name", "abacus")

    try:
        # Kept local to avoid importing the CLI module while this service is
        # imported. The CLI is refactored to call services in a later task.
        from atst_tools.scripts import main as legacy_run

        if workflow == "neb":
            return legacy_run.run_neb(
                config, calculator_name, calculation, world=options.world
            )
        if workflow == "autoneb":
            return legacy_run.run_autoneb(
                config, calculator_name, calculation, world=options.world
            )
        if workflow in {"dimer", "sella", "ccqn"}:
            return getattr(legacy_run, f"run_{workflow}")(
                config, calculator_name, calculation
            )

        workflow_class = {
            "d2s": legacy_run.D2SWorkflow,
            "dmf": legacy_run.DMFWorkflow,
            "relax": legacy_run.RelaxWorkflow,
            "vibration": legacy_run.VibrationWorkflow,
            "irc": legacy_run.IRCWorkflow,
            "md": legacy_run.MDWorkflow,
        }[workflow]
        return workflow_class(config, calculator_name, calculation).run()
    except ValueError as exc:
        if "MPI ranks" in str(exc):
            raise MPIConfigurationError(str(exc), workflow=workflow) from exc
        raise WorkflowExecutionError(str(exc), workflow=workflow) from exc
    except Exception as exc:
        raise WorkflowExecutionError(str(exc), workflow=workflow) from exc


def _stored_energy(atoms: Any) -> float | None:
    """Return a frozen calculator energy without triggering a new calculation."""
    calculator = getattr(atoms, "calc", None)
    results = getattr(calculator, "results", None)
    energy = results.get("energy") if isinstance(results, dict) else None
    return float(energy) if energy is not None else None


def _result_from_manifest(
    config: dict[str, Any], value: Any, world: Any, status: str
) -> WorkflowResult:
    """Build one root-aware result using the durable manifest as source of truth."""
    calculation = config["calculation"]
    workflow = calculation["type"]
    manifest_path = Path(calculation.get("artifact_manifest", "atst_artifacts.json"))
    manifest = (
        _read_manifest(manifest_path)
        if manifest_path.exists()
        else {"artifacts": [], "metadata": {}}
    )
    is_root = int(world.rank) == 0
    metadata = dict(manifest.get("metadata", {}))
    metadata.setdefault(
        "backend_source",
        BACKEND_SOURCE
        if config.get("calculator", {}).get("name", "abacus") == "abacus"
        else "provided",
    )

    final_images = None
    ts_atoms = None
    if is_root and workflow in {"neb", "autoneb"} and value is not None:
        images = tuple(value)
        final_images = tuple(image.copy() for image in images)
        interior_energies = [
            (energy, image)
            for image in images[1:-1]
            if (energy := _stored_energy(image)) is not None
        ]
        if interior_energies:
            ts_atoms = max(interior_energies, key=lambda item: item[0])[1].copy()

    final_atoms = (
        value.copy()
        if is_root
        and workflow not in {"neb", "autoneb"}
        and hasattr(value, "copy")
        else None
    )
    return WorkflowResult(
        workflow=workflow,
        status=status,
        is_root=is_root,
        artifact_manifest=str(manifest_path),
        artifacts=tuple(manifest.get("artifacts", [])),
        metadata=metadata,
        final_atoms=final_atoms,
        final_images=final_images,
        ts_atoms=ts_atoms,
    )


def run_workflow(
    config_source: str | Path | Mapping[str, Any], options: RunOptions = RunOptions()
) -> WorkflowResult:
    """Run one YAML-equivalent workflow without changing current-directory semantics.

    The supplied communicator is used as-is; this service never launches MPI,
    a scheduler, or a nested calculator process.
    """
    config = validate_config(config_source)
    world = options.world or get_ase_world()
    if options.dry_run:
        return _result_from_manifest(config, None, world, "validated")
    value = _dispatch_normalized(config, options)
    return _result_from_manifest(config, value, world, "complete")


def run_ccqn(*args: Any, **kwargs: Any) -> Any:
    """Placeholder for embedded CCQN execution.

    This implementation is supplied by the subsequent CCQN-service task.
    """
    raise NotImplementedError("run_ccqn() is not implemented yet")
