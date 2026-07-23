"""Application services backing the stable Python API."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import os
from pathlib import Path
from typing import Any

from atst_tools.api.models import (
    ATSTAPIError,
    CCQNOptions,
    ConfigValidationError,
    MPIConfigurationError,
    RunOptions,
    UnsupportedDependencyError,
    WorkflowExecutionError,
    WorkflowResult,
)
from atst_tools.calculators.abacuslite_backend import BACKEND_SOURCE
from atst_tools.utils.artifacts import (
    SCHEMA_VERSION,
    read_artifact_manifest,
    write_artifact_manifest,
)
from atst_tools.utils.config import ConfigLoader
from atst_tools.utils.mpi import get_ase_world


def _load_and_normalize(
    config_source: str | Path | Mapping[str, Any], *, restart_override: bool = False
) -> dict[str, Any]:
    """Load and normalize a copied configuration source through the schema."""
    try:
        raw = (
            ConfigLoader.load(str(config_source))
            if isinstance(config_source, (str, Path))
            else deepcopy(dict(config_source))
        )
        if restart_override and isinstance(raw.get("calculation"), Mapping):
            raw["calculation"] = dict(raw["calculation"])
            raw["calculation"]["restart"] = True
        return ConfigLoader.normalize(raw)
    except (OSError, ValueError, TypeError) as exc:
        raise ConfigValidationError(
            str(exc), context={"config_source": str(config_source)}
        ) from exc


def _read_manifest(path: str | Path) -> dict[str, Any]:
    """Read a workflow artifact manifest without changing it."""
    return read_artifact_manifest(path)


def _is_matching_runner_manifest(path: str | Path, workflow: str) -> bool:
    """Return whether a runner just wrote a complete manifest for ``workflow``."""
    try:
        manifest = _read_manifest(path)
    except (OSError, ValueError, TypeError):
        return False
    return (
        isinstance(manifest, Mapping)
        and manifest.get("schema_version") == SCHEMA_VERSION
        and manifest.get("workflow") == workflow
        and isinstance(manifest.get("artifacts"), list)
        and isinstance(manifest.get("metadata"), Mapping)
        and isinstance(manifest.get("stages"), list)
    )


def _manifest_signature(path: str | Path) -> tuple[int, int, int, int] | None:
    """Capture filesystem identity used to detect a runner-written manifest."""
    try:
        stat = Path(path).stat()
    except FileNotFoundError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def validate_config(config_source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached schema-normalized ATST configuration."""
    return _load_and_normalize(config_source)


def _run_abacus_check_input_preflight(
    config: dict[str, Any],
    config_source: str | Path | Mapping[str, Any],
    options: RunOptions,
    *,
    base_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Run the legacy ABACUS dry-run preflight and return its CLI status."""
    if not options.check_input:
        return None

    calculator_name = config.get("calculator", {}).get("name", "abacus")
    if calculator_name != "abacus":
        return {"status": "skipped", "calculator_name": calculator_name}

    # The import remains local because the legacy helper lives with the CLI
    # implementation, which imports this service for normal command handling.
    from atst_tools.scripts.main import run_abacus_check_input_dry_run

    arguments = {
        "timeout_sec": options.check_input_timeout,
        "abacus_executable": (
            options.abacus_executable
            or os.environ.get("ABACUS_EXECUTABLE", "abacus")
        ),
    }
    if base_dir is not None:
        arguments["base_dir"] = base_dir
    result = run_abacus_check_input_dry_run(
        config,
        str(config_source) if isinstance(config_source, (str, Path)) else None,
        **arguments,
    )
    return {"status": "passed", "checked": result["checked"]}


def _optional_dependency_name(exc: BaseException) -> str | None:
    """Return the known optional dependency missing from an exception chain."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        dependency = str(getattr(current, "name", "") or "").lower()
        if isinstance(current, ModuleNotFoundError) and (
            dependency == "cyipopt"
            or dependency.startswith("cyipopt.")
            or dependency == "deepmd"
            or dependency.startswith("deepmd.")
            or dependency == "mpi4py"
            or dependency.startswith("mpi4py.")
        ):
            return dependency.split(".", maxsplit=1)[0]
        current = current.__cause__ or current.__context__
    return None


def _configured_backend_source(config: Mapping[str, Any]) -> str:
    """Return provenance for a calculator constructed from configuration."""
    calculator_name = str(config.get("calculator", {}).get("name", "abacus")).lower()
    if calculator_name == "abacus":
        return BACKEND_SOURCE
    if calculator_name in {"dp", "deepmd"}:
        return "deepmd"
    return calculator_name


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
        dependency = _optional_dependency_name(exc)
        if dependency is not None:
            raise UnsupportedDependencyError(
                str(exc), workflow=workflow, context={"dependency": dependency}
            ) from exc
        raise WorkflowExecutionError(str(exc), workflow=workflow) from exc


def _stored_energy(atoms: Any) -> float | None:
    """Return a frozen calculator energy without triggering a new calculation."""
    calculator = getattr(atoms, "calc", None)
    results = getattr(calculator, "results", None)
    energy = results.get("energy") if isinstance(results, dict) else None
    return float(energy) if energy is not None else None


def _synthesized_artifacts(
    config: dict[str, Any], value: Any
) -> list[dict[str, str]]:
    """Describe established outputs for runners that did not write a manifest."""
    calculation = config["calculation"]
    workflow = calculation["type"]
    artifact_fields = {
        "neb": (("trajectory", "trajectory"),),
        "dimer": (("trajectory", "trajectory"),),
        "sella": (("trajectory", "trajectory"),),
        "ccqn": (
            ("trajectory", "trajectory"),
            ("ts_structure", "final_structure"),
            ("ccqn_mode_manifest", "mode_manifest"),
            ("ccqn_diagnostics", "diagnostics_file"),
        ),
        "relax": (
            ("trajectory", "trajectory"),
            ("log", "logfile"),
        ),
        "vibration": (
            ("vibration_results", "results_file"),
            ("ts_validation", "validation_file"),
        ),
        "irc": (
            ("irc_trajectory", "trajectory"),
            ("normalized_irc_trajectory", "normalized_trajectory"),
        ),
        "md": (
            ("trajectory", "trajectory"),
            ("log", "logfile"),
            ("summary", "summary_file"),
            ("final_structure", "final_structure"),
        ),
        "dmf": (
            ("evaluation_path", "trajectory"),
            ("tmax_candidate", "tmax_trajectory"),
            ("summary", "summary_file"),
        ),
    }
    if workflow == "autoneb":
        return [
            {
                "role": "image_trajectory",
                "path": f"{calculation['prefix']}{index:03d}.traj",
            }
            for index, _ in enumerate(value or ())
        ]
    if workflow == "d2s":
        method = calculation["method"]
        artifacts = [
            {"role": "rough_neb_trajectory", "path": "neb_rough.traj"},
            {
                "role": "single_ended_trajectory",
                "path": calculation[method]["trajectory"],
            },
        ]
        if calculation["vibration"]["enabled"]:
            artifacts.extend(
                [
                    {
                        "role": "vibration_results",
                        "path": calculation["vibration"]["results_file"],
                    },
                    {
                        "role": "ts_validation",
                        "path": calculation["vibration"]["validation_file"],
                    },
                ]
            )
        return artifacts

    artifacts = [
        {"role": role, "path": calculation[field]}
        for role, field in artifact_fields[workflow]
        if calculation.get(field) is not None
    ]
    if workflow == "relax":
        artifacts.append({"role": "final_structure", "path": "final_relaxed.traj"})
    return artifacts


def _synchronize_rank_failure(
    world: Any, workflow: str, failure: ATSTAPIError | None
) -> None:
    """Raise a peer-visible API error before any following collective operation."""
    if int(world.size) <= 1:
        if failure is not None:
            raise failure
        return

    try:
        if hasattr(world, "sum_scalar"):
            failure_count = world.sum_scalar(int(failure is not None))
        elif hasattr(world, "sum"):
            reduced = world.sum(int(failure is not None))
            failure_count = int(failure is not None) if reduced is None else reduced
        else:
            raise RuntimeError("communicator does not provide a scalar reduction")
    except Exception as exc:
        raise WorkflowExecutionError(
            "Unable to synchronize an MPI workflow failure.",
            workflow=workflow,
        ) from exc

    if int(failure_count):
        if failure is not None:
            raise failure
        raise WorkflowExecutionError(
            "Workflow execution failed on another MPI rank.",
            workflow=workflow,
        )


def _ensure_completed_manifest(
    config: dict[str, Any],
    value: Any,
    world: Any,
    previous_signature: tuple[int, int, int, int] | None = None,
) -> None:
    """Guarantee that a completed API outcome has an accurate durable manifest."""
    calculation = config["calculation"]
    workflow = calculation["type"]
    manifest_path = Path(calculation.get("artifact_manifest", "atst_artifacts.json"))
    failure = None
    if int(world.rank) == 0:
        try:
            current_signature = _manifest_signature(manifest_path)
            runner_wrote_manifest = (
                previous_signature is not None
                and current_signature != previous_signature
            ) or (previous_signature is None and current_signature is not None)
            matching_manifest = current_signature is not None and _is_matching_runner_manifest(
                manifest_path, workflow
            )
            if not (runner_wrote_manifest and matching_manifest):
                write_artifact_manifest(
                    manifest_path,
                    workflow=workflow,
                    artifacts=_synthesized_artifacts(config, value),
                    stages=[{"name": workflow, "status": "complete"}],
                    metadata={"manifest_source": "api_synthesized"},
                )
        except Exception as exc:
            failure = WorkflowExecutionError(
                "Unable to finalize the workflow artifact manifest.",
                workflow=workflow,
            )
            failure.__cause__ = exc

    _synchronize_rank_failure(world, workflow, failure)
    if int(world.size) > 1 and hasattr(world, "barrier"):
        world.barrier()

    failure = None
    try:
        manifest = _read_manifest(manifest_path)
        if manifest.get("workflow") != workflow:
            raise ValueError("artifact manifest workflow does not match completion")
    except Exception as exc:
        failure = WorkflowExecutionError(
            "Unable to read the completed workflow artifact manifest.",
            workflow=workflow,
        )
        failure.__cause__ = exc
    _synchronize_rank_failure(world, workflow, failure)


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
        _configured_backend_source(config),
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

    final_atoms = _normalized_final_atoms(workflow, value) if is_root else None
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


def _normalized_final_atoms(workflow: str, value: Any) -> Any | None:
    """Copy only an ASE final structure, recovering the Relax output when needed."""
    from ase import Atoms

    if workflow == "relax" and value is None:
        final_structure = Path("final_relaxed.traj")
        if final_structure.is_file():
            from atst_tools.utils.io import read_structure

            value = read_structure(final_structure)
    return value.copy() if isinstance(value, Atoms) else None


def _validated_result(config: dict[str, Any], world: Any) -> WorkflowResult:
    """Build a manifest-independent result for a validation-only run."""
    calculation = config["calculation"]
    return WorkflowResult(
        workflow=calculation["type"],
        status="validated",
        is_root=int(world.rank) == 0,
        artifact_manifest=str(
            calculation.get("artifact_manifest", "atst_artifacts.json")
        ),
        artifacts=(),
        metadata={
            "backend_source": _configured_backend_source(config),
            "calculator_name": config.get("calculator", {}).get("name", "abacus"),
        },
    )


def _result_without_manifest(
    config: dict[str, Any], world: Any, status: str
) -> WorkflowResult:
    """Build the legacy CLI result without reading or writing artifact manifests."""
    calculation = config["calculation"]
    return WorkflowResult(
        workflow=calculation["type"],
        status=status,
        is_root=int(world.rank) == 0,
        artifact_manifest=str(calculation.get("artifact_manifest", "atst_artifacts.json")),
        artifacts=(),
        metadata={},
    )


def _resolve_world(
    options: RunOptions, workflow: str, *, translate_errors: bool
) -> Any:
    """Return the caller communicator or bootstrap ASE MPI at the API boundary."""
    if options.world is not None:
        return options.world
    try:
        return get_ase_world()
    except Exception as exc:
        if not translate_errors:
            raise
        dependency = _optional_dependency_name(exc)
        if dependency is not None:
            raise UnsupportedDependencyError(
                str(exc), workflow=workflow, context={"dependency": dependency}
            ) from exc
        raise WorkflowExecutionError(str(exc), workflow=workflow) from exc


def _run_workflow(
    config_source: str | Path | Mapping[str, Any],
    options: RunOptions,
    *,
    ensure_completed_manifest: bool,
    preflight_base_dir: Path | None = None,
    translate_communicator_errors: bool = False,
) -> WorkflowResult:
    """Execute the shared workflow path with an explicit caller compatibility mode."""
    world = _resolve_world(
        options, "configuration", translate_errors=translate_communicator_errors
    )
    config_failure = None
    try:
        config = _load_and_normalize(config_source, restart_override=options.restart)
    except ConfigValidationError as exc:
        config_failure = exc
        config = None
    _synchronize_rank_failure(world, "configuration", config_failure)
    assert config is not None
    workflow = config["calculation"]["type"]
    if options.dry_run:
        preflight = None
        preflight_failure = None
        try:
            preflight = _run_abacus_check_input_preflight(
                config, config_source, options, base_dir=preflight_base_dir
            )
        except WorkflowExecutionError as exc:
            preflight_failure = exc
        except Exception as exc:
            preflight_failure = WorkflowExecutionError(str(exc), workflow=workflow)
            preflight_failure.__cause__ = exc
        _synchronize_rank_failure(world, workflow, preflight_failure)
        result = _validated_result(config, world)
        if preflight is not None:
            result.metadata["check_input_preflight"] = preflight
        return result
    previous_signature = None
    if ensure_completed_manifest:
        manifest_path = config["calculation"].get(
            "artifact_manifest", "atst_artifacts.json"
        )
        manifest_inspection_failure = None
        try:
            previous_signature = _manifest_signature(manifest_path)
        except OSError as exc:
            manifest_inspection_failure = WorkflowExecutionError(
                "Unable to inspect the workflow artifact manifest.", workflow=workflow
            )
            manifest_inspection_failure.__cause__ = exc
        _synchronize_rank_failure(world, workflow, manifest_inspection_failure)
    value = None
    failure = None
    try:
        value = _dispatch_normalized(config, options)
    except ATSTAPIError as exc:
        failure = exc
    except Exception as exc:
        dependency = _optional_dependency_name(exc)
        if dependency is not None:
            failure = UnsupportedDependencyError(
                str(exc), workflow=workflow, context={"dependency": dependency}
            )
        else:
            failure = WorkflowExecutionError(str(exc), workflow=workflow)
        failure.__cause__ = exc
    _synchronize_rank_failure(world, workflow, failure)
    if not ensure_completed_manifest:
        return _result_without_manifest(config, world, "complete")
    _ensure_completed_manifest(config, value, world, previous_signature)
    return _result_from_manifest(config, value, world, "complete")


def run_workflow(
    config_source: str | Path | Mapping[str, Any], options: RunOptions = RunOptions()
) -> WorkflowResult:
    """Run one YAML-equivalent workflow with API-owned durable artifacts.

    The supplied communicator is used as-is; this service never launches MPI,
    a scheduler, or a nested calculator process.
    """
    if options.check_input and not options.dry_run:
        raise ConfigValidationError(
            "--check-input requires --dry-run",
            context={"option": "check_input"},
        )
    return _run_workflow(
        config_source,
        options,
        ensure_completed_manifest=True,
        preflight_base_dir=Path.cwd(),
        translate_communicator_errors=True,
    )


def run_workflow_from_cli(
    config_source: str | Path | Mapping[str, Any], options: RunOptions
) -> WorkflowResult:
    """Run the legacy command adapter without synthesizing API artifact files."""
    return _run_workflow(
        config_source, options, ensure_completed_manifest=False
    )


def _ccqn_options_to_config(options: CCQNOptions) -> dict[str, Any]:
    """Map embedded-API options to the existing CCQN calculation fields."""
    return {
        "type": "ccqn",
        "fmax": options.fmax,
        "max_steps": options.max_steps,
        "trajectory": options.trajectory,
        "logfile": options.logfile,
        "final_structure": options.final_structure,
        "e_vector_method": options.e_vector_method,
        "reactive_bonds": options.reactive_bonds,
        "auto_reactive_bonds": dict(options.auto_reactive_bonds),
        "mode_manifest": options.mode_manifest,
        "diagnostics_file": options.diagnostics_file,
        "ic_mode": options.ic_mode,
        "cos_phi": options.cos_phi,
        "trust_radius_uphill": options.trust_radius_uphill,
        "trust_radius_saddle_initial": options.trust_radius_saddle_initial,
        "hessian": options.hessian,
        "accept_initial_converged": options.accept_initial_converged,
        "artifact_manifest": options.artifact_manifest,
    }


def run_ccqn(
    atoms: Any,
    calculator: Any,
    options: CCQNOptions = CCQNOptions(),
) -> WorkflowResult:
    """Run CCQN with caller-owned ASE atoms and calculator objects.

    The calculator is attached only to a private atoms copy.  This service
    never reconstructs or reconfigures the caller-provided ASE calculator.
    """
    from atst_tools.mep.ccqn import AbacusCCQN

    private_atoms = atoms.copy()
    calc_config = _ccqn_options_to_config(options)
    try:
        final_atoms = AbacusCCQN(
            private_atoms,
            {},
            "provided",
            calc_config,
            traj_file=options.trajectory,
            product_atoms=options.product_atoms,
            calculator=calculator,
        ).run()
    except Exception as exc:
        raise WorkflowExecutionError(str(exc), workflow="ccqn") from exc

    try:
        manifest = _read_manifest(options.artifact_manifest)
    except Exception as exc:
        raise WorkflowExecutionError(
            "Unable to read the completed workflow artifact manifest.",
            workflow="ccqn",
        ) from exc
    metadata = {**manifest.get("metadata", {}), "backend_source": "provided"}
    return WorkflowResult(
        workflow="ccqn",
        status="complete",
        is_root=True,
        artifact_manifest=options.artifact_manifest,
        artifacts=tuple(manifest.get("artifacts", [])),
        metadata=metadata,
        final_atoms=final_atoms.copy(),
    )
