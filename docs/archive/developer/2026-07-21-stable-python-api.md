# Stable Python API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a stable `atst_tools.api` for YAML-driven workflows and embedded CCQN while making the existing `atst run` and `atst config validate` commands thin, behavior-compatible adapters.

**Spec:** `2026-07-21-python-api-design.html` (archived alongside this completed plan)

**Architecture:** Add a focused public API package over an internal application-service module. The service owns config loading/normalization, dispatch, manifest/result collection, and typed API exceptions; CLI code retains parsing, messages, and exit behavior but delegates to that service. Existing workflow and calculator classes stay internal, and the injected CCQN path bypasses `CalculatorFactory` completely.

**Tech Stack:** Python 3.10+, ASE, Pydantic v2, ruamel.yaml, mpi4py optional extra, pytest, existing Markdown documentation governance.

## Global Constraints

- Preserve every existing CLI command, YAML field/default, relative-CWD path rule, output filename, existing import path, MPI rule, and CLI exit/message contract (spec `#summary`, R2–R4, R8).
- The only new stable import namespace is `atst_tools.api`; do not add an `atst` Python alias or public re-exports from workflow/calculator/vendored packages (spec R1, `#decisions`).
- The API never launches Slurm, `mpirun`, `srun`, or nested ABACUS MPI; `world` is an optional existing-communicator hook (spec `#errors`).
- Config-driven ABACUS execution retains external-abacuslite-first then vendored fallback; injected CCQN calculators are never reconstructed or reconfigured (spec R10, `#architecture`).
- `WorkflowResult` is frozen; atom fields are caller-owned snapshots. `final_images` and `ts_atoms` are root-only for image-parallel execution (spec `#architecture`, `#errors`).
- Retain DMF's experimental classification and guards. Do not introduce a documentation generator in this release (spec `#goals`).

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/atst_tools/api/__init__.py` | The complete stable import surface and explicit `__all__`. |
| `src/atst_tools/api/models.py` | Frozen options/result dataclasses and typed API exceptions, available as `atst_tools.api.models` rather than extra root exports. |
| `src/atst_tools/api/services.py` | Public config validation, workflow dispatch, manifest/result conversion, and CCQN embedding service. |
| `src/atst_tools/scripts/main.py` | Compatibility-only adapters around services; existing parser and logging remain. |
| `src/atst_tools/scripts/cli.py` | Makes `config validate` use the same public validation service without changing output. |
| `src/atst_tools/mep/ccqn.py` | Allows an already-built calculator to be used by CCQN without changing the legacy constructor contract. |
| `src/atst_tools/mep/autoneb.py` | Returns its final image chain and accepts the existing `world` supplied by the shared service. |
| `src/atst_tools/utils/artifacts.py` | Reads the existing durable manifest safely for `WorkflowResult`. |
| `tests/unit/test_api.py` | Owns public import, validation, dispatch, result, error, and backend-provenance contracts. |
| `tests/unit/test_ccqn.py` | Extends existing CCQN tests for injected-calculator execution. |
| `tests/unit/test_mpi_parallel.py` | Extends existing image-parallel suite for communicator injection/root result rules. |
| `tests/unit/test_cli.py` | Retains CLI contracts and adds service-delegation parity checks. |
| `tests/unit/test_examples.py` | Validates the new API example and its reference-results registration. |
| `tests/unit/test_docs_api.py` | Executes public documentation snippets and guards public-only imports/links. |
| `examples/12_ccqn_H2-Au/ccqn_api_auto_modes.py` | Executable, ATST-specific embedded CCQN automatic-reactive-mode example. |
| `examples/reference_results.json` and `examples/README.md` | Records and navigates the API example. |
| `docs/user/PYTHON_API_REFERENCE.md` | Maintained stable API contract and backend/MPI boundary. |
| `README.md`, `docs/index.md`, `docs/user/USER_GUIDE_CN.md`, `docs/user/CLI_REFERENCE.md`, `docs/user/CONFIG_REFERENCE.md` | Public discovery, selection guidance, CLI/API relationship, and CWD YAML bridge. |

### Task 1: Define the public contract and schema-only API

**Files:**
- Create: `src/atst_tools/api/__init__.py`
- Create: `src/atst_tools/api/models.py`
- Create: `src/atst_tools/api/services.py`
- Create: `tests/unit/test_api.py`
- Modify: `src/atst_tools/utils/artifacts.py`

**Test strategy:**
- Behavior boundary: callers can import only the six approved root names, normalize an in-memory mapping or YAML path through the existing schema, and receive typed validation failures from the API's `models` submodule.
- Existing suite to extend: `tests/unit/test_config.py` remains schema-owner; `tests/unit/test_api.py` owns the new public boundary.
- New test file justification: no existing test owns a public Python API namespace or import contract.
- Temporary probes: none.

**Interfaces:**
- Consumes: `ConfigLoader.load()`, `ConfigLoader.normalize()`, `get_ase_world()`, and artifact manifest JSON written by current workflows.
- Produces: `RunOptions`, `CCQNOptions`, `WorkflowResult`, `ATSTAPIError`, `ConfigValidationError`, `MPIConfigurationError`, `WorkflowExecutionError`, `validate_config()`, and a private `_read_manifest()` helper.

- [ ] **Step 1: Write the failing public-contract and normalization tests**

```python
# tests/unit/test_api.py
from __future__ import annotations

from pathlib import Path

import pytest


def test_public_api_has_only_the_supported_contract():
    import atst_tools.api as api

    assert api.__all__ == [
        "CCQNOptions", "RunOptions", "WorkflowResult", "validate_config",
        "run_workflow", "run_ccqn",
    ]


def test_validate_config_normalizes_mapping_without_mutating_input():
    from atst_tools.api import validate_config

    raw = {"calculation": {"type": "relax", "init_structure": "initial.traj"},
           "calculator": {"name": "abacus", "abacus": {"parameters": {}}}}

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
```

- [ ] **Step 2: Run the test to verify the missing namespace fails**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'atst_tools.api'`.

- [ ] **Step 3: Add immutable models, exceptions, and schema-only validation**

```python
# src/atst_tools/api/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ATSTAPIError(RuntimeError):
    """Base error for the stable ATST-Tools Python API."""

    def __init__(self, message: str, *, workflow: str | None = None, context: dict[str, Any] | None = None):
        super().__init__(message)
        self.workflow = workflow
        self.context = dict(context or {})


class ConfigValidationError(ATSTAPIError):
    """Raised when a YAML path or mapping fails ATST schema validation."""


class MPIConfigurationError(ATSTAPIError):
    """Raised when image-parallel communicator topology is invalid."""


class WorkflowExecutionError(ATSTAPIError):
    """Raised when a workflow cannot complete through the public API."""


@dataclass(frozen=True)
class RunOptions:
    dry_run: bool = False
    restart: bool = False
    check_input: bool = False
    check_input_timeout: int = 120
    abacus_executable: str | None = None
    world: Any | None = None


@dataclass(frozen=True)
class CCQNOptions:
    fmax: float = 0.05
    max_steps: int | None = 200
    trajectory: str = "ccqn.traj"
    logfile: str = "ccqn.log"
    final_structure: str | None = "ccqn_final.extxyz"
    e_vector_method: str = "ic"
    reactive_bonds: str | list[tuple[int, int]] | None = None
    auto_reactive_bonds: dict[str, Any] = field(default_factory=dict)
    product_atoms: Any | None = None
    mode_manifest: str | None = "ccqn_mode_manifest.json"
    diagnostics_file: str | None = "ccqn_diagnostics.json"
    ic_mode: str = "democratic"
    cos_phi: float = 0.5
    trust_radius_uphill: float = 0.1
    trust_radius_saddle_initial: float = 0.05
    hessian: bool = False
    accept_initial_converged: bool = False
    artifact_manifest: str = "atst_artifacts.json"


@dataclass(frozen=True)
class WorkflowResult:
    workflow: str
    status: str
    is_root: bool
    artifact_manifest: str
    artifacts: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]
    final_atoms: Any | None = None
    final_images: tuple[Any, ...] | None = None
    ts_atoms: Any | None = None
```

```python
# src/atst_tools/api/services.py (initial content)
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from atst_tools.api.models import ConfigValidationError
from atst_tools.utils.config import ConfigLoader


def _load_and_normalize(config_source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    try:
        raw = ConfigLoader.load(str(config_source)) if isinstance(config_source, (str, Path)) else deepcopy(dict(config_source))
        return ConfigLoader.normalize(raw)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        raise ConfigValidationError(str(exc), context={"config_source": str(config_source)}) from exc


def validate_config(config_source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached schema-normalized ATST configuration."""
    return _load_and_normalize(config_source)
```

```python
# src/atst_tools/api/__init__.py
from atst_tools.api.models import CCQNOptions, RunOptions, WorkflowResult
from atst_tools.api.services import run_ccqn, run_workflow, validate_config

__all__ = ["CCQNOptions", "RunOptions", "WorkflowResult", "validate_config", "run_workflow", "run_ccqn"]
```

```python
# src/atst_tools/utils/artifacts.py (append)
def read_artifact_manifest(path: str | Path) -> dict[str, Any]:
    """Read an existing ATST artifact manifest without altering it."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run API and schema regression tests**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api.py tests/unit/test_config.py -q`

Expected: PASS.

- [ ] **Step 5: Refactor the test portfolio**

Keep Pydantic/YAML field assertions in `tests/unit/test_config.py`; retain only public import, detached-mapping, path, and exception behavior in `tests/unit/test_api.py`. Confirm no test imports `atst_tools.api.models` or `atst_tools.api.services` as an external contract.

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api.py tests/unit/test_config.py -q`

Expected: PASS with no duplicate schema-field assertions.

- [ ] **Step 6: Commit**

```bash
git add src/atst_tools/api src/atst_tools/utils/artifacts.py tests/unit/test_api.py
git commit -m "feat: add stable API configuration contract"
```

### Task 2: Add configuration-driven execution and durable results

**Files:**
- Modify: `src/atst_tools/api/services.py`
- Modify: `src/atst_tools/scripts/main.py`
- Modify: `src/atst_tools/mep/autoneb.py`
- Modify: `tests/unit/test_api.py`
- Modify: `tests/unit/test_mpi_parallel.py`

**Test strategy:**
- Behavior boundary: `run_workflow()` dispatches every current calculation type, preserves dry-run/restart and CWD semantics, returns manifest-based structured outcomes, and returns path objects only on rank zero.
- Existing suite to extend: `tests/unit/test_mpi_parallel.py` owns communicator topology and `tests/unit/test_cli.py` remains CLI owner.
- New test file justification: none; `test_api.py` was created in Task 1 for this public boundary.
- Temporary probes: none.

**Interfaces:**
- Consumes: `validate_config(config_source) -> dict`, `RunOptions`, all existing functions in `scripts/main.py`, and `AutoNEBRunner.run()`.
- Produces: `run_workflow(config_source, options=RunOptions()) -> WorkflowResult`, `_dispatch_normalized(config, options) -> object | None`, and `AutoNEBRunner.run() -> list[Atoms] | None`.

- [ ] **Step 1: Write failing dispatch/result parity tests**

```python
# append to tests/unit/test_api.py
import json
from helpers import FakeWorld


@pytest.mark.parametrize("workflow", ["neb", "autoneb", "dimer", "sella", "ccqn", "d2s", "relax", "vibration", "irc", "md", "dmf"])
def test_run_workflow_dispatches_every_governed_type(monkeypatch, tmp_path, workflow):
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    seen = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda config, options: seen.append(config["calculation"]["type"]) or None)
    (tmp_path / "atst_artifacts.json").write_text(json.dumps({"workflow": workflow, "artifacts": [], "metadata": {}, "stages": []}))
    result = run_workflow({"calculation": {"type": workflow, **({"init_structure": "x.traj"} if workflow in {"dimer", "sella", "ccqn", "relax", "vibration", "irc", "md"} else {"init_file": "a.traj", "final_file": "b.traj"} if workflow in {"d2s", "dmf"} else {"init_chain": "chain.traj"})}, "calculator": {"name": "abacus", "abacus": {"parameters": {}}}}, RunOptions())

    assert seen == [workflow]
    assert result.workflow == workflow
    assert result.status == "complete"


def test_run_workflow_dry_run_returns_no_in_memory_atoms(monkeypatch):
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.setattr(services, "_dispatch_normalized", lambda *args: pytest.fail("dry run dispatched"))
    result = run_workflow({"calculation": {"type": "relax", "init_structure": "x.traj"}, "calculator": {"name": "abacus", "abacus": {"parameters": {}}}}, RunOptions(dry_run=True))

    assert result.status == "validated"
    assert result.final_atoms is None


def test_path_result_is_root_only(monkeypatch, tmp_path):
    from ase import Atoms
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    images = [Atoms("H"), Atoms("H"), Atoms("H")]
    monkeypatch.setattr(services, "_dispatch_normalized", lambda *args: images)
    (tmp_path / "atst_artifacts.json").write_text('{"workflow":"neb","artifacts":[],"metadata":{},"stages":[]}')
    result = run_workflow({"calculation": {"type": "neb", "init_chain": "chain.traj", "parallel": True}, "calculator": {"name": "abacus", "abacus": {"parameters": {}}}}, RunOptions(world=FakeWorld(size=1, rank=0)))

    assert len(result.final_images) == 3
    assert result.ts_atoms is not None
```

- [ ] **Step 2: Run the test to verify execution API is absent**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api.py -q`

Expected: FAIL with `ImportError` for `run_workflow` or an assertion that `_dispatch_normalized` does not exist.

- [ ] **Step 3: Implement one normalized dispatch service and result construction**

```python
# add to src/atst_tools/api/services.py
from atst_tools.api.models import MPIConfigurationError, RunOptions, WorkflowExecutionError, WorkflowResult
from atst_tools.calculators.abacuslite_backend import BACKEND_SOURCE
from atst_tools.utils.artifacts import read_artifact_manifest
from atst_tools.utils.mpi import get_ase_world


def _dispatch_normalized(config: dict[str, Any], options: RunOptions) -> Any:
    from atst_tools.scripts import main as legacy_run

    calculation = config["calculation"]
    if options.restart:
        calculation["restart"] = True
    workflow = calculation["type"]
    calculator_name = config.get("calculator", {}).get("name", "abacus")
    try:
        if workflow == "neb":
            return legacy_run.run_neb(config, calculator_name, calculation, world=options.world)
        if workflow == "autoneb":
            return legacy_run.run_autoneb(config, calculator_name, calculation, world=options.world)
        if workflow in {"dimer", "sella", "ccqn"}:
            return getattr(legacy_run, f"run_{workflow}")(config, calculator_name, calculation)
        workflow_class = {
            "d2s": legacy_run.D2SWorkflow, "dmf": legacy_run.DMFWorkflow,
            "relax": legacy_run.RelaxWorkflow, "vibration": legacy_run.VibrationWorkflow,
            "irc": legacy_run.IRCWorkflow, "md": legacy_run.MDWorkflow,
        }[workflow]
        return workflow_class(config, calculator_name, calculation).run()
    except ValueError as exc:
        if "MPI ranks" in str(exc):
            raise MPIConfigurationError(str(exc), workflow=workflow) from exc
        raise WorkflowExecutionError(str(exc), workflow=workflow) from exc
    except Exception as exc:
        raise WorkflowExecutionError(str(exc), workflow=workflow) from exc


def _result_from_manifest(config: dict[str, Any], value: Any, world: Any, status: str) -> WorkflowResult:
    calculation = config["calculation"]
    workflow = calculation["type"]
    manifest_path = calculation.get("artifact_manifest", "atst_artifacts.json")
    manifest = read_artifact_manifest(manifest_path) if Path(manifest_path).exists() else {"artifacts": [], "metadata": {}}
    is_root = int(world.rank) == 0
    metadata = dict(manifest.get("metadata", {}))
    metadata.setdefault("backend_source", BACKEND_SOURCE if config.get("calculator", {}).get("name") == "abacus" else "provided")
    final_images = tuple(image.copy() for image in value) if is_root and workflow in {"neb", "autoneb"} and value is not None else None
    ts_atoms = max(final_images[1:-1], key=lambda image: image.get_potential_energy()).copy() if final_images and len(final_images) > 2 else None
    final_atoms = value.copy() if is_root and workflow not in {"neb", "autoneb"} and hasattr(value, "copy") else None
    return WorkflowResult(workflow, status, is_root, str(manifest_path), tuple(manifest.get("artifacts", [])), metadata, final_atoms, final_images, ts_atoms)


def run_workflow(config_source: str | Path | Mapping[str, Any], options: RunOptions = RunOptions()) -> WorkflowResult:
    """Run one existing YAML workflow without changing CLI/YAML semantics."""
    config = validate_config(config_source)
    world = options.world or get_ase_world()
    if options.dry_run:
        return _result_from_manifest(config, None, world, "validated")
    value = _dispatch_normalized(config, options)
    return _result_from_manifest(config, value, world, "complete")
```

Change only the MPI-aware legacy functions to accept `world=None`, using `get_ase_world()` only when it is `None`; preserve their existing three-argument callers. Specifically, change `run_autoneb()` to construct `AutoNEBRunner(..., world=world)`, and change `AutoNEBRunner.__init__` to take keyword-only `world=None`, assign `self.world = world or get_ase_world()`, and end `run()` with `return final_images if self.world.rank == 0 else None`. End `run_neb()` with `return init_chain if world.rank == 0 else None`; end dimer/sella/ccqn functions with their finalized atoms; return each class workflow's existing `.run()` value unchanged.

- [ ] **Step 4: Run dispatch and MPI regression tests**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api.py tests/unit/test_mpi_parallel.py tests/unit/test_workflows.py -q`

Expected: PASS. Existing direct calls to `run_neb(config, name, calculation)` still work; fake-world tests prove no MPI launcher is started.

- [ ] **Step 5: Refactor result ownership and manifest reads**

Make one result builder own all artifact-manifest reading and atom copies. Ensure it does not call `get_potential_energy()` when final images have only frozen single-point calculators; choose TS from their stored energies. Retain only root-side `final_images`/`ts_atoms`; all ranks retain identical `status`, `metadata`, and manifest path.

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api.py tests/unit/test_mpi_parallel.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atst_tools/api/services.py src/atst_tools/scripts/main.py src/atst_tools/mep/autoneb.py tests/unit/test_api.py tests/unit/test_mpi_parallel.py
git commit -m "feat: run YAML workflows through stable API services"
```

### Task 3: Preserve CLI behavior while delegating run and validation

**Files:**
- Modify: `src/atst_tools/scripts/main.py`
- Modify: `src/atst_tools/scripts/cli.py`
- Modify: `tests/unit/test_cli.py`

**Test strategy:**
- Behavior boundary: command-line argument parsing, text, check-input preflight, and exit behavior stay unchanged while both commands consume public service outputs.
- Existing suite to extend: `tests/unit/test_cli.py`.
- New test file justification: none.
- Temporary probes: none.

**Interfaces:**
- Consumes: `validate_config()`, `run_workflow()`, `RunOptions` from Task 1–2.
- Produces: legacy `run_from_args(args)` and `_config_validate_command(args)` behavior with no direct `ConfigLoader.normalize()` orchestration.

- [ ] **Step 1: Write failing CLI delegation/parity tests**

```python
# append to tests/unit/test_cli.py
def test_config_validate_delegates_to_public_validation_service(monkeypatch, capsys):
    from atst_tools.scripts import cli

    normalized = {"calculation": {"type": "relax", "restart": False}, "calculator": {"name": "abacus"}}
    monkeypatch.setattr(cli, "validate_config", lambda source: normalized)

    cli.main(["config", "validate", "config.yaml"])

    assert capsys.readouterr().out.strip() == "Configuration is valid"


def test_run_adapter_builds_cli_equivalent_options(monkeypatch):
    from atst_tools.scripts import main

    seen = {}
    monkeypatch.setattr(main, "run_workflow", lambda source, options: seen.update(source=source, options=options))

    main.run_from_args(type("Args", (), {"config": "config.yaml", "dry_run": True, "restart": True, "check_input": False, "check_input_timeout": 120, "abacus_executable": None, "log_level": "INFO", "list_types": False, "show_template": None})())

    assert seen["source"] == "config.yaml"
    assert seen["options"].dry_run is True
    assert seen["options"].restart is True
```

- [ ] **Step 2: Run the test to confirm adapters still bypass services**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_cli.py -q`

Expected: FAIL because `cli.validate_config` and `main.run_workflow` are not imported adapter dependencies.

- [ ] **Step 3: Replace only CLI orchestration with API service calls**

```python
# src/atst_tools/scripts/main.py imports
from atst_tools.api import RunOptions, run_workflow

# replace the config-load/normalize/dispatch block in run_from_args after list/template handling
options = RunOptions(
    dry_run=getattr(args, "dry_run", False),
    restart=getattr(args, "restart", False),
    check_input=getattr(args, "check_input", False),
    check_input_timeout=getattr(args, "check_input_timeout", 120),
    abacus_executable=getattr(args, "abacus_executable", None),
)
result = run_workflow(args.config, options)
if options.dry_run:
    LOGGER.info(
        "Configuration is valid: calculation.type=%s, calculator.name=%s",
        result.workflow,
        validate_config(args.config).get("calculator", {}).get("name", "abacus"),
    )
return result
```

Keep ABACUS `--check-input` in a private service helper called by `run_workflow()` during dry-run, using the same `run_abacus_check_input_dry_run()` arguments and log text currently in `run_from_args`. In `cli.py`, import `validate_config` from `atst_tools.api` and replace only `_config_validate_command`'s first line with `config = validate_config(args.config)`. Do not change `_write_yaml()`, output messages, or parser definitions.

- [ ] **Step 4: Run exact CLI regressions**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_cli.py tests/unit/test_config.py -q`

Expected: PASS, including existing `--dry-run`, `--restart`, `--check-input`, normalization print/output, and IR C boundary tests.

- [ ] **Step 5: Refactor cyclic imports before committing**

Ensure `atst_tools.api.services` imports legacy runner functions lazily inside `_dispatch_normalized()` rather than importing `scripts.main` at module import time, because `scripts.main` imports `atst_tools.api`. Re-run the import-contract test from a clean interpreter.

Run: `PYTHONPATH=src conda run -n atst-dev python -c 'import atst_tools.api; from atst_tools.scripts import cli; print("imports passed")'`

Expected: `imports passed`.

- [ ] **Step 6: Commit**

```bash
git add src/atst_tools/scripts/main.py src/atst_tools/scripts/cli.py src/atst_tools/api/services.py tests/unit/test_cli.py
git commit -m "refactor: route CLI workflow commands through API services"
```

### Task 4: Add embedded CCQN calculator injection

**Files:**
- Modify: `src/atst_tools/mep/ccqn.py`
- Modify: `src/atst_tools/api/services.py`
- Modify: `tests/unit/test_ccqn.py`
- Modify: `tests/unit/test_api.py`

**Test strategy:**
- Behavior boundary: `run_ccqn()` copies the caller atoms, attaches exactly the supplied calculator, supports current reactive-mode fields, writes current artifacts, and returns `backend_source: provided`.
- Existing suite to extend: `tests/unit/test_ccqn.py`.
- New test file justification: none; public result assertion belongs in `test_api.py`.
- Temporary probes: none.

**Interfaces:**
- Consumes: `CCQNOptions`, `AbacusCCQN`, `DummyCalc` fixture, CCQN mode-manifest behavior.
- Produces: `run_ccqn(atoms, calculator, options=CCQNOptions()) -> WorkflowResult` and `AbacusCCQN(..., calculator=None)` compatibility extension.

- [ ] **Step 1: Write failing injection/no-factory tests**

```python
# append to tests/unit/test_ccqn.py
def test_ccqn_accepts_injected_calculator_without_factory(monkeypatch, tmp_path):
    from ase import Atoms
    from helpers import DummyCalc
    from atst_tools.mep.ccqn import AbacusCCQN

    atoms = Atoms("H2", positions=[[0, 0, 0], [0.8, 0, 0]])
    calculator = DummyCalc()
    monkeypatch.setattr("atst_tools.mep.ccqn.CalculatorFactory.get_calculator", lambda *a, **k: pytest.fail("factory used"))
    monkeypatch.setattr("atst_tools.mep.ccqn.CCQNOptimizer.run", lambda self, **kwargs: None)

    result = AbacusCCQN(atoms, {}, "abacus", {"artifact_manifest": str(tmp_path / "manifest.json")}, calculator=calculator).run()

    assert result.calc is calculator
    assert atoms.calc is None


def test_public_ccqn_result_marks_supplied_backend(monkeypatch, tmp_path):
    from ase import Atoms
    from helpers import DummyCalc
    from atst_tools.api import CCQNOptions, run_ccqn

    monkeypatch.setattr("atst_tools.mep.ccqn.CCQNOptimizer.run", lambda self, **kwargs: None)
    result = run_ccqn(Atoms("H2", positions=[[0, 0, 0], [0.8, 0, 0]]), DummyCalc(), CCQNOptions(artifact_manifest=str(tmp_path / "manifest.json")))

    assert result.metadata["backend_source"] == "provided"
```

- [ ] **Step 2: Run the injection tests to verify the legacy constructor cannot accept it**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_ccqn.py tests/unit/test_api.py -q`

Expected: FAIL with `TypeError: unexpected keyword argument 'calculator'`.

- [ ] **Step 3: Make calculator injection additive and expose `run_ccqn`**

```python
# src/atst_tools/mep/ccqn.py: extend the existing signature
def __init__(self, init_Atoms, config, calc_name, calc_config, traj_file="ccqn.traj", product_atoms=None, calculator=None):
    self.init_Atoms = init_Atoms
    self.config = config
    self.calc_name = calc_name
    self.calc_config = calc_config
    self.traj_file = traj_file
    self.product_atoms = product_atoms
    self.calculator = calculator

def set_calculator(self):
    """Return the supplied calculator or create the legacy workflow-local one."""
    if self.calculator is not None:
        return self.calculator
    directory = self.calc_config.get("directory", "ccqn_run")
    return CalculatorFactory.get_calculator(self.calc_name, self.config, directory=directory)
```

```python
# append to src/atst_tools/api/services.py
from atst_tools.api.models import CCQNOptions

def run_ccqn(atoms: Any, calculator: Any, options: CCQNOptions = CCQNOptions()) -> WorkflowResult:
    """Run CCQN with caller-owned ASE atoms and calculator; no factory is used."""
    from atst_tools.mep.ccqn import AbacusCCQN

    private_atoms = atoms.copy()
    calc_config = {
        "type": "ccqn", "fmax": options.fmax, "max_steps": options.max_steps,
        "trajectory": options.trajectory, "logfile": options.logfile,
        "final_structure": options.final_structure, "e_vector_method": options.e_vector_method,
        "reactive_bonds": options.reactive_bonds, "auto_reactive_bonds": dict(options.auto_reactive_bonds),
        "mode_manifest": options.mode_manifest, "diagnostics_file": options.diagnostics_file,
        "ic_mode": options.ic_mode, "cos_phi": options.cos_phi,
        "trust_radius_uphill": options.trust_radius_uphill,
        "trust_radius_saddle_initial": options.trust_radius_saddle_initial,
        "hessian": options.hessian, "accept_initial_converged": options.accept_initial_converged,
        "artifact_manifest": options.artifact_manifest,
    }
    try:
        final_atoms = AbacusCCQN(private_atoms, {}, "provided", calc_config, traj_file=options.trajectory, product_atoms=options.product_atoms, calculator=calculator).run()
    except Exception as exc:
        raise WorkflowExecutionError(str(exc), workflow="ccqn") from exc
    manifest = read_artifact_manifest(options.artifact_manifest)
    metadata = {**manifest.get("metadata", {}), "backend_source": "provided"}
    return WorkflowResult("ccqn", "complete", True, options.artifact_manifest, tuple(manifest.get("artifacts", [])), metadata, final_atoms.copy())
```

Do not alter the existing positional arguments, calculator factory path, output defaults, or CCQN optimizer behavior. Update `AbacusCCQN.run()` to attach the calculator to `self.init_Atoms` only after `run_ccqn()` has made its private copy.

- [ ] **Step 4: Run CCQN and API regressions**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_ccqn.py tests/unit/test_api.py tests/unit/test_workflows.py -q`

Expected: PASS, including existing YAML CCQN tests and new injection/no-factory assertions.

- [ ] **Step 5: Refactor option-to-config conversion into one private helper**

Create `_ccqn_options_to_config(options: CCQNOptions) -> dict[str, Any]` in `services.py`; test every emitted key against CCQN schema fields and keep `run_ccqn()` free of calculator-name/directory/MPI options.

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_ccqn.py tests/unit/test_api.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atst_tools/mep/ccqn.py src/atst_tools/api/services.py tests/unit/test_ccqn.py tests/unit/test_api.py
git commit -m "feat: add embedded CCQN Python API"
```

### Task 5: Complete compatibility, MPI, and package-release verification

**Files:**
- Modify: `tests/unit/test_api.py`
- Modify: `tests/unit/test_mpi_parallel.py`
- Modify: `tests/unit/test_package_metadata.py`
- Modify: `pyproject.toml` only if the release version is intentionally bumped by maintainers

**Test strategy:**
- Behavior boundary: external/vendored provenance, injected provenance, serial fallback, rank mismatch, root/non-root result shape, wheel public imports, and all current examples retain their configuration contract.
- Existing suite to extend: `test_mpi_parallel.py`, `test_package_metadata.py`, and `test_examples.py`.
- New test file justification: none.
- Temporary probes: create wheel only in `dist/`; move it to `$HOME/scratch` after verification if it is not an intentional release artifact.

**Interfaces:**
- Consumes: all Task 1–4 public APIs and current `BACKEND_SOURCE` resolver.
- Produces: release gate evidence, without changing external behavior.

- [ ] **Step 1: Write failing provenance and wheel-import tests**

```python
# append to tests/unit/test_api.py
def test_config_driven_abacus_result_reports_existing_backend_source(monkeypatch, tmp_path):
    from atst_tools.api import run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda *args: None)
    (tmp_path / "atst_artifacts.json").write_text('{"workflow":"relax","artifacts":[],"metadata":{},"stages":[]}')
    result = run_workflow({"calculation": {"type": "relax", "init_structure": "x.traj"}, "calculator": {"name": "abacus", "abacus": {"parameters": {}}}})

    assert result.metadata["backend_source"] in {"external", "vendored"}


def test_non_root_path_result_has_no_atoms(monkeypatch, tmp_path):
    from helpers import FakeWorld
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda *args: [])
    (tmp_path / "atst_artifacts.json").write_text('{"workflow":"neb","artifacts":[],"metadata":{},"stages":[]}')
    result = run_workflow({"calculation": {"type": "neb", "init_chain": "chain.traj"}, "calculator": {"name": "abacus", "abacus": {"parameters": {}}}}, RunOptions(world=FakeWorld(size=2, rank=1)))

    assert result.is_root is False
    assert result.final_images is None
    assert result.ts_atoms is None
```

- [ ] **Step 2: Run the tests to identify remaining result/provenance gaps**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api.py tests/unit/test_mpi_parallel.py tests/unit/test_package_metadata.py -q`

Expected: PASS only after Tasks 1–4 are complete; otherwise fix the uncovered contract before proceeding.

- [ ] **Step 3: Add package and optional real-MPI release checks**

```bash
PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api.py tests/unit/test_cli.py tests/unit/test_ccqn.py tests/unit/test_mpi_parallel.py tests/unit/test_examples.py -q
conda run -n atst-dev python -m build
conda run -n atst-dev python -m venv /tmp/atst-api-wheel-venv
/tmp/atst-api-wheel-venv/bin/pip install dist/atst_tools-*.whl
/tmp/atst-api-wheel-venv/bin/python -c 'from atst_tools.api import CCQNOptions, RunOptions, WorkflowResult, run_ccqn, run_workflow, validate_config; print("wheel API import passed")'
```

Expected: all pytest selections pass, the build succeeds, and the last command prints `wheel API import passed`. If `mpi4py` is installed in `atst-dev`, additionally run the existing opt-in launcher fixture under an allocation; do not add a launcher to the API itself.

- [ ] **Step 4: Run full source regression and governed documentation baseline**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests -q`

Expected: PASS. Record the command/result in the release checklist; investigate any result that imports the installed package rather than `src`.

- [ ] **Step 5: Refactor test overlap and clean build artifact**

Keep manifest/provenance assertions in `test_api.py`, communicator topology in `test_mpi_parallel.py`, and wheel metadata in `test_package_metadata.py`. Move non-release `dist/` to `$HOME/scratch/atst-tools-api-plan-dist` after verification rather than deleting it.

Run: `git status --short`

Expected: only intended source, tests, docs, and example changes remain.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_api.py tests/unit/test_mpi_parallel.py tests/unit/test_package_metadata.py
git commit -m "test: add stable API compatibility gates"
```

### Task 6: Publish governed documentation and an executable CCQN API example

**Files:**
- Create: `docs/user/PYTHON_API_REFERENCE.md`
- Create: `examples/12_ccqn_H2-Au/ccqn_api_auto_modes.py`
- Create: `tests/unit/test_docs_api.py`
- Modify: `README.md`
- Modify: `docs/index.md`
- Modify: `docs/user/USER_GUIDE_CN.md`
- Modify: `docs/user/CLI_REFERENCE.md`
- Modify: `docs/user/CONFIG_REFERENCE.md`
- Modify: `examples/README.md`
- Modify: `examples/reference_results.json`
- Modify: `docs/reports/DOCUMENTATION_STATUS_REPORT.md`

**Test strategy:**
- Behavior boundary: users can discover the stable API, choose API versus CLI correctly, execute only public imports in the lightweight example test, and find explicit ABACUSLite/MPI/dependency boundaries.
- Existing suite to extend: `tests/unit/test_examples.py` and `tests/unit/test_docs_governance.py`.
- New test file justification: existing tests do not execute public Markdown code snippets or prevent internal API imports in new public docs.
- Temporary probes: none.

**Interfaces:**
- Consumes: `from atst_tools.api import CCQNOptions, run_ccqn, run_workflow, validate_config`, finalized `WorkflowResult`, and the current examples/reference-result format.
- Produces: a Markdown-first maintained documentation path and executable ATST-specific CCQN API example; the downstream ABACUS example remains out of this repository/release scope.

- [ ] **Step 1: Write failing documentation and example-contract tests**

```python
# tests/unit/test_docs_api.py
from pathlib import Path


def test_api_reference_is_linked_from_public_navigation():
    assert "docs/user/PYTHON_API_REFERENCE.md" in Path("README.md").read_text(encoding="utf-8")
    assert "user/PYTHON_API_REFERENCE.md" in Path("docs/index.md").read_text(encoding="utf-8")


def test_public_api_docs_never_import_internal_modules():
    text = Path("docs/user/PYTHON_API_REFERENCE.md").read_text(encoding="utf-8")
    assert "from atst_tools.api import" in text
    for forbidden in ("from atst import", "from atst_tools.workflows", "from atst_tools.mep", "from atst_tools.calculators"):
        assert forbidden not in text


def test_ccqn_api_example_declares_required_header_topics():
    text = Path("examples/12_ccqn_H2-Au/ccqn_api_auto_modes.py").read_text(encoding="utf-8")
    for phrase in ("CCQN", "ATST", "https://github.com/QuantumMisaka/atst-tools", "CLI", "from atst_tools.api import"):
        assert phrase in text
```

- [ ] **Step 2: Run the documentation test to verify required materials are absent**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_docs_api.py -q`

Expected: FAIL because the API reference and embedded API example do not exist.

- [ ] **Step 3: Write the reference and single-file automatic-mode example**

```python
# examples/12_ccqn_H2-Au/ccqn_api_auto_modes.py
"""Run the H2/Au CCQN automatic-reactive-mode example through the stable API.

This is an ATST-specific single-ended transition-state search: it starts from
the supplied H2/Au guess and asks CCQN to enumerate/select reactive modes.
Install ATST-Tools with ``pip install atst-tools`` (plus ``[parallel]`` only
when using an externally launched MPI workflow). Project and installation:
https://github.com/QuantumMisaka/atst-tools . CLI/YAML usage is documented at
https://quantummisaka.github.io/atst-tools/ (or the repository README).

Below, Python creates the ASE calculator and invokes ATST through its stable
``atst_tools.api`` interface; ATST does not rebuild or reconfigure that calculator.
"""
from ase.io import read
from atst_tools.api import CCQNOptions, run_ccqn

# Replace this lightweight example calculator with an already configured
# abacuslite calculator when executing a production ABACUS calculation.
from ase.calculators.emt import EMT

atoms = read("inputs/ccqn_init.stru")
result = run_ccqn(
    atoms,
    EMT(),
    CCQNOptions(
        trajectory="outputs/ccqn_api_auto_modes.traj",
        logfile="outputs/ccqn_api_auto_modes.log",
        final_structure="outputs/ccqn_api_auto_modes_final.extxyz",
        mode_manifest="outputs/ccqn_api_auto_modes_manifest.json",
        diagnostics_file="outputs/ccqn_api_auto_modes_diagnostics.json",
        artifact_manifest="outputs/atst_artifacts_api_auto_modes.json",
        auto_reactive_bonds={"enabled": True, "cutoff_A": 3.0, "max_modes": 20},
    ),
)
print(result.status, result.metadata["backend_source"])
```

Document that the committed example is structurally executable with a lightweight ASE calculator test fixture; a production ABACUS run requires a caller-created, correctly configured abacuslite calculator and normal ABACUS pseudopotential/orbital/runtime setup. In `PYTHON_API_REFERENCE.md`, define every public name, exceptions, artifacts, immutable/result ownership, CWD paths, MPI root-only behavior, DMF experimental boundary, compatibility/deprecation policy, and backend delegation invariants. Use the actual repository documentation URL only after verifying the hosted URL; otherwise link to the stable GitHub Markdown files.

- [ ] **Step 4: Add navigation/reference-result registration and run docs tests**

Update all listed public entry documents with concise links rather than duplicate reference text. Add the new script to `examples/README.md` as the embedded API companion to existing `config_auto_modes.yaml`; add an explicit verification record for `12_ccqn_H2-Au/ccqn_api_auto_modes.py` to `examples/reference_results.json`; update the documentation status report with the new active user-reference document.

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_docs_api.py tests/unit/test_examples.py tests/unit/test_docs_governance.py -q`

Expected: PASS.

- [ ] **Step 5: Execute documentation snippets and governance checks**

Run:

```bash
PYTHONPATH=src conda run -n atst-dev python -c 'from atst_tools.api import validate_config; print(validate_config({"calculation":{"type":"relax","init_structure":"x.traj"},"calculator":{"name":"abacus","abacus":{"parameters":{}}}})["calculation"]["type"])'
conda run -n atst-dev python scripts/check_docs_governance.py
git diff --check -- README.md docs examples/README.md AGENTS.md
rg -n '^<<<<<<<|^=======|^>>>>>>>' README.md docs examples/README.md AGENTS.md
```

Expected: prints `relax`, documentation governance passes, `git diff --check` is silent, and the conflict-marker search has no matches.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/index.md docs/user/PYTHON_API_REFERENCE.md docs/user/USER_GUIDE_CN.md docs/user/CLI_REFERENCE.md docs/user/CONFIG_REFERENCE.md docs/reports/DOCUMENTATION_STATUS_REPORT.md examples/README.md examples/12_ccqn_H2-Au/ccqn_api_auto_modes.py examples/reference_results.json tests/unit/test_docs_api.py tests/unit/test_examples.py
git commit -m "docs: publish stable Python API guide and CCQN example"
```

## Final Release Gate

- [ ] Run `PYTHONPATH=src conda run -n atst-dev pytest tests -q` and record the pass count.
- [ ] Run `conda run -n atst-dev python -m build`; install the built wheel into a clean environment and import every name from `atst_tools.api`.
- [ ] Run `conda run -n atst-dev python scripts/check_docs_governance.py`, `git diff --check -- README.md docs examples/README.md AGENTS.md`, and the conflict-marker scan from Task 6.
- [ ] Confirm `git status --short` contains no unintentional artifacts and that any temporary wheel/build directory was moved to `$HOME/scratch`.
- [ ] Before publishing an ATST release, require an independent review of the public API signatures, CLI parity evidence, MPI evidence, and API documentation. Only after that release may ABACUS PR #7608 add its optional one-file downstream consumer.
