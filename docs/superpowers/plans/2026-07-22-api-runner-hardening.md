# ATST API Runner Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a wheel-installable `python -m atst_tools.api.runner` and stable JSON handoff contract to the ATST-Tools 2.2.0 candidate without changing the six-name Python API root or any existing CLI behavior.

**Spec:** `docs/superpowers/specs/2026-07-22-abacus-agent-api-runner-design.html`

**Architecture:** Keep `run_workflow()` as the sole configuration-driven application service. Add JSON-safe serialization to the existing models and a dedicated process runner that owns temporary CWD changes, exit-code mapping, MPI root detection, and atomic result-file publication. Extend the existing wheel verifier and MPI integration suite rather than creating a second workflow implementation.

**Tech Stack:** Python 3.10+, dataclasses, argparse, pathlib, JSON, ASE communicator semantics, optional mpi4py, pytest, build/venv wheel verification.

## Global Constraints

- Preserve `atst_tools.api.__all__` exactly as `CCQNOptions`, `RunOptions`, `WorkflowResult`, `validate_config`, `run_workflow`, and `run_ccqn` (spec R1–R4 and `#architecture`).
- Preserve all `atst` CLI commands, messages, exit behavior, YAML semantics, output names, backend choice, and current MPI ownership (spec `#goals` and `#decisions`).
- The runner must not launch Slurm, `srun`, `mpirun`, or ABACUS MPI; external launchers own process topology (spec R2).
- Only rank zero may atomically publish the result JSON; the API artifact manifest remains the scientific source of truth (spec R3–R4 and `#errors`).
- Never serialize ASE `Atoms`, calculators, environment variables, tracebacks, credentials, or arbitrary object representations into the result document.
- Complete ATST local, clean-wheel, real-MPI, documentation-governance, and CLI parity gates before an ATST 2.2.0 tag or release is considered.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/atst_tools/api/models.py` | JSON-safe success and error payload conversion without expanding root exports. |
| `src/atst_tools/api/runner.py` | Module entry point, argument parsing, isolated CWD, MPI root selection, stable exit codes, and atomic JSON publication. |
| `tests/unit/test_api.py` | Existing stable model/service contract and serialization regression coverage. |
| `tests/unit/test_api_runner.py` | Independently executable runner boundary: argv, CWD, success/error JSON, root-only writes, and exit codes. |
| `tests/integration/test_mpi_failure_sync.py` | Real two-rank runner success/failure/no-deadlock coverage. |
| `scripts/verify_wheel_api.py` | Clean-wheel runner smoke and external-consumer verification. |
| `docs/user/PYTHON_API_REFERENCE.md` | User-facing runner and JSON protocol reference. |
| `README.md`, `docs/index.md`, `docs/user/USER_GUIDE_CN.md` | Discoverability and API/CLI/runner selection guidance. |
| `docs/releases/RELEASE_NOTES_2.2.0.md` | Release-visible runner contract and compatibility statement. |
| `docs/developer/HANDOVER.md`, `docs/reports/DOCUMENTATION_STATUS_REPORT.md`, `docs/reports/FEATURE_STATUS_MATRIX.md` | Maintainer and documentation-governance state. |

### Task 1: Add stable JSON-safe model documents

**Files:**
- Modify: `src/atst_tools/api/models.py`
- Modify: `tests/unit/test_api.py`

**Test strategy:**
- Behavior boundary: `WorkflowResult.to_document(workdir)` returns one `atst-api-result-v1` success envelope with absolute paths and JSON-safe detached values; `ATSTAPIError.to_document()` returns a bounded error payload with one cause summary.
- Existing suite to extend: `tests/unit/test_api.py` already owns public models and error semantics.
- New test file justification: none.
- Temporary probes: none.

**Interfaces:**
- Consumes: existing `WorkflowResult` fields and `ATSTAPIError.workflow/context/__cause__`.
- Produces: `WorkflowResult.to_document(workdir: str | Path) -> dict[str, Any]` and `ATSTAPIError.to_document() -> dict[str, Any]` for Task 2.

- [ ] **Step 1: Write failing serialization tests**

```python
def test_workflow_result_document_is_json_safe_and_resolves_paths(tmp_path):
    from atst_tools.api.models import WorkflowResult

    result = WorkflowResult(
        workflow="relax",
        status="complete",
        is_root=True,
        artifact_manifest="atst_artifacts.json",
        artifacts=({"path": "relax.traj", "role": "trajectory"},),
        metadata={"backend": "external-abacuslite"},
        final_atoms=object(),
    )

    document = result.to_document(tmp_path)

    assert document == {
        "schema": "atst-api-result-v1",
        "status": "success",
        "workflow": "relax",
        "is_root": True,
        "workdir": str(tmp_path.resolve()),
        "artifact_manifest": str((tmp_path / "atst_artifacts.json").resolve()),
        "artifacts": [{"path": "relax.traj", "role": "trajectory"}],
        "metadata": {"backend": "external-abacuslite"},
    }
    json.dumps(document)


def test_api_error_document_keeps_bounded_cause_summary():
    from atst_tools.api.models import WorkflowExecutionError

    error = WorkflowExecutionError(
        "workflow failed",
        workflow="neb",
        context={"phase": "optimizer"},
    )
    error.__cause__ = ValueError("invalid image chain")

    assert error.to_document() == {
        "type": "WorkflowExecutionError",
        "message": "workflow failed",
        "workflow": "neb",
        "context": {"phase": "optimizer"},
        "cause": {"type": "ValueError", "message": "invalid image chain"},
    }
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api.py -q`

Expected: FAIL because neither model defines `to_document`.

- [ ] **Step 3: Implement bounded JSON conversion**

```python
# src/atst_tools/api/models.py
import json
from pathlib import Path


def _json_detached(value: Any) -> Any:
    """Return a JSON-safe detached value or raise a precise public error."""
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise TypeError("ATST API document values must be JSON serializable") from exc


class ATSTAPIError(RuntimeError):
    # keep the current constructor and docstring
    def to_document(self) -> dict[str, Any]:
        """Return the stable bounded error payload used by process runners."""
        cause = self.__cause__
        return {
            "type": type(self).__name__,
            "message": str(self),
            "workflow": self.workflow,
            "context": _json_detached(self.context),
            "cause": None if cause is None else {
                "type": type(cause).__name__,
                "message": str(cause),
            },
        }


@dataclass(frozen=True)
class WorkflowResult:
    # keep the current fields
    def to_document(self, workdir: str | Path) -> dict[str, Any]:
        """Return the stable JSON handoff envelope without ASE objects."""
        root = Path(workdir).resolve()
        manifest = Path(self.artifact_manifest)
        if not manifest.is_absolute():
            manifest = root / manifest
        return {
            "schema": "atst-api-result-v1",
            "status": "success",
            "workflow": self.workflow,
            "is_root": self.is_root,
            "workdir": str(root),
            "artifact_manifest": str(manifest.resolve()),
            "artifacts": _json_detached(list(self.artifacts)),
            "metadata": _json_detached(self.metadata),
        }
```

- [ ] **Step 4: Run the owning tests and verify GREEN**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api.py -q`

Expected: PASS.

- [ ] **Step 5: Refactor the test portfolio**

Keep one success-envelope test, one cause test, and one rejection test for a non-JSON metadata value. Do not retain assertions on source layout or dataclass internals.

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api.py -q`

Expected: PASS with the focused model contract intact.

- [ ] **Step 6: Commit**

```bash
git add src/atst_tools/api/models.py tests/unit/test_api.py
git commit -m "feat: add API result documents"
```

### Task 2: Implement the isolated process runner

**Files:**
- Create: `src/atst_tools/api/runner.py`
- Create: `tests/unit/test_api_runner.py`

**Test strategy:**
- Behavior boundary: the module accepts the approved arguments, changes CWD only inside its process call, delegates once to `run_workflow`, writes one atomic success/error document on root, and returns stable `0`, `2`, or `1` exit codes.
- Existing suite to extend: none owns an independently executable API runner.
- New test file justification: runner subprocess and filesystem publication are a distinct public boundary from the in-process API.
- Temporary probes: none.

**Interfaces:**
- Consumes: `RunOptions`, `run_workflow`, `WorkflowResult.to_document()`, and `ATSTAPIError.to_document()`.
- Produces: `build_parser()`, `main(argv: Sequence[str] | None = None) -> int`, and module execution through `python -m atst_tools.api.runner`.

- [ ] **Step 1: Write failing runner tests**

```python
def test_runner_writes_success_document_in_requested_workdir(monkeypatch, tmp_path):
    from atst_tools.api import runner
    from atst_tools.api.models import WorkflowResult

    workdir = tmp_path / "run"
    config = tmp_path / "config.yaml"
    config.write_text("calculation: {}\n", encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "run_workflow",
        lambda source, options: WorkflowResult(
            workflow="relax", status="complete", is_root=True,
            artifact_manifest="atst_artifacts.json", artifacts=(), metadata={},
        ),
    )

    code = runner.main([
        "--config", str(config), "--workdir", str(workdir),
        "--result-json", "atst-api-result-v1.json",
    ])

    assert code == 0
    payload = json.loads((workdir / "atst-api-result-v1.json").read_text())
    assert payload["schema"] == "atst-api-result-v1"
    assert payload["status"] == "success"


def test_runner_non_root_does_not_publish_json(monkeypatch, tmp_path):
    from atst_tools.api import runner

    monkeypatch.setattr(runner, "_process_rank", lambda: 1)
    monkeypatch.setattr(runner, "run_workflow", _non_root_workflow_result)

    code = runner.main([
        "--config", str(tmp_path / "config.yaml"),
        "--workdir", str(tmp_path),
        "--result-json", "result.json",
    ])

    assert code == 0
    assert not (tmp_path / "result.json").exists()
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api_runner.py -q`

Expected: FAIL because `atst_tools.api.runner` does not exist.

- [ ] **Step 3: Implement the runner**

```python
# src/atst_tools/api/runner.py
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

from atst_tools.api import RunOptions, run_workflow
from atst_tools.api.models import ATSTAPIError

SUCCESS = 0
API_ERROR = 2
INTERNAL_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one ATST workflow through the stable Python API.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--result-json", default="atst-api-result-v1.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--check-input", action="store_true")
    parser.add_argument("--check-input-timeout", type=int, default=120)
    parser.add_argument("--abacus-executable")
    return parser


def _process_rank() -> int:
    try:
        from mpi4py import MPI
        return int(MPI.COMM_WORLD.Get_rank())
    except ImportError:
        for key in ("OMPI_COMM_WORLD_RANK", "PMI_RANK", "PMIX_RANK", "MPI_LOCALRANKID"):
            if key in os.environ:
                return int(os.environ[key])
        return 0


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    path.mkdir(parents=True, exist_ok=True)
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _write_json_atomic(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workdir = Path(args.workdir).resolve()
    config = Path(args.config).resolve()
    result_path = Path(args.result_json)
    if not result_path.is_absolute():
        result_path = workdir / result_path
    options = RunOptions(
        dry_run=args.dry_run,
        restart=args.restart,
        check_input=args.check_input,
        check_input_timeout=args.check_input_timeout,
        abacus_executable=args.abacus_executable,
    )
    try:
        with _working_directory(workdir):
            result = run_workflow(config, options)
        if _process_rank() == 0:
            _write_json_atomic(result_path, result.to_document(workdir))
        return SUCCESS
    except ATSTAPIError as exc:
        if _process_rank() == 0:
            _write_json_atomic(result_path, {
                "schema": "atst-api-result-v1",
                "status": "error",
                "workdir": str(workdir),
                "error": exc.to_document(),
            })
        print(str(exc), file=sys.stderr)
        return API_ERROR
    except Exception as exc:
        if _process_rank() == 0:
            _write_json_atomic(result_path, {
                "schema": "atst-api-result-v1",
                "status": "error",
                "workdir": str(workdir),
                "error": {"type": type(exc).__name__, "message": str(exc)},
            })
        print(str(exc), file=sys.stderr)
        return INTERNAL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run runner and CLI parity tests and verify GREEN**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api_runner.py tests/unit/test_api.py tests/unit/test_cli.py -q`

Expected: PASS; existing CLI assertions remain unchanged.

- [ ] **Step 5: Refactor the runner tests**

Parameterize RunOptions flag forwarding, retain separate tests for CWD restoration, atomic replacement, API error exit `2`, unexpected error exit `1`, and root-only publication. Remove source-text assertions and use `runner.main()` or an actual module subprocess.

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_api_runner.py tests/unit/test_cli.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atst_tools/api/runner.py tests/unit/test_api_runner.py
git commit -m "feat: add stable API process runner"
```

### Task 3: Prove clean-wheel and real-MPI runner behavior

**Files:**
- Modify: `scripts/verify_wheel_api.py`
- Modify: `tests/integration/test_mpi_failure_sync.py`
- Modify: `tests/unit/test_package_metadata.py`

**Test strategy:**
- Behavior boundary: an installed wheel runs the module without source-tree imports; external two-rank launch produces one root document for success and failure and terminates all ranks.
- Existing suite to extend: the wheel verifier and MPI failure-sync integration suite already own these boundaries.
- New test file justification: none.
- Temporary probes: wheel verifier temporary environments only; they must be removed by its existing cleanup lifecycle.

**Interfaces:**
- Consumes: the Task 2 module entry point and `atst-tools[parallel]` packaging metadata.
- Produces: release evidence that ABACUS Agent can depend on the runner from an installed 2.2.0 artifact.

- [ ] **Step 1: Add failing wheel and MPI cases**

```python
# scripts/verify_wheel_api.py: run in the clean basic venv
runner = subprocess.run(
    [python, "-m", "atst_tools.api.runner", "--config", str(config),
     "--workdir", str(run_dir), "--result-json", "result.json", "--dry-run"],
    cwd=outside_source_tree,
    text=True,
    capture_output=True,
)
assert runner.returncode == 0, runner.stderr
assert json.loads((run_dir / "result.json").read_text())["status"] == "success"
```

Add a two-rank integration case that invokes the real module, checks that only `rank 0` publishes `result.json`, and uses a bounded subprocess timeout to prove peers exit on configuration and optimizer-construction failures.

- [ ] **Step 2: Run the focused checks and verify RED**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/integration/test_mpi_failure_sync.py tests/unit/test_package_metadata.py -q`

Expected: FAIL because the existing integration fixture and wheel script do not yet exercise the runner.

- [ ] **Step 3: Extend existing verifier fixtures without duplicating workflow logic**

Use the verifier's installed interpreter, isolated CWD, and current generated fixtures. Add module subprocess calls only; do not import from the source checkout or set `PYTHONPATH`. Reuse the integration suite's real `mpiexec` launcher and failure fixtures, passing `--result-json` under its temporary run directory.

- [ ] **Step 4: Run focused wheel and MPI verification and verify GREEN**

Run: `conda run -n atst-dev python scripts/verify_wheel_api.py`

Expected: exit `0`, basic runner success, external API consumer success, and parallel runner success/failure evidence.

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/integration/test_mpi_failure_sync.py tests/unit/test_package_metadata.py -q`

Expected: PASS with no timeout.

- [ ] **Step 5: Run the complete ATST regression gate**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests -q`

Expected: all tests PASS with no existing CLI contract regression.

- [ ] **Step 6: Commit**

```bash
git add scripts/verify_wheel_api.py tests/integration/test_mpi_failure_sync.py tests/unit/test_package_metadata.py
git commit -m "test: verify API runner from wheels and MPI"
```

### Task 4: Publish user and maintainer documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/index.md`
- Modify: `docs/user/PYTHON_API_REFERENCE.md`
- Modify: `docs/user/USER_GUIDE_CN.md`
- Modify: `docs/releases/RELEASE_NOTES_2.2.0.md`
- Modify: `docs/developer/HANDOVER.md`
- Modify: `docs/reports/DOCUMENTATION_STATUS_REPORT.md`
- Modify: `docs/reports/FEATURE_STATUS_MATRIX.md`

**Test strategy:**
- Behavior boundary: users can discover and run the installed runner, understand JSON/manifest authority and MPI ownership, and distinguish it from the stable in-process API and legacy CLI.
- Existing suite to extend: `tests/unit/test_docs_api.py` and repository documentation governance.
- New test file justification: none.
- Temporary probes: none.

**Interfaces:**
- Consumes: exact Task 2 flags, schema name, exit codes, and Task 3 evidence.
- Produces: release-ready documentation and governance entries; no new API or CLI behavior.

- [ ] **Step 1: Add failing documentation snippet tests**

Extend `tests/unit/test_docs_api.py` to execute the documented `--help` module invocation and validate the documented success JSON keys against `WorkflowResult.to_document()`.

- [ ] **Step 2: Run documentation tests and verify RED**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_docs_api.py -q`

Expected: FAIL because the runner reference and snippets are absent.

- [ ] **Step 3: Write the runner reference and governance updates**

Document the installed invocation, all eight flags, exit codes `0/2/1`, `atst-api-result-v1`, absolute manifest path, root-only MPI publication, atomic replacement, and the statement that ATST never starts Slurm or MPI launchers. Link it from README, index, Chinese quick-start, handover, release notes, status ledger, and feature matrix.

- [ ] **Step 4: Run documentation and repository checks and verify GREEN**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_docs_api.py tests/unit/test_docs_governance.py -q`

Expected: PASS.

Run: `git diff --check -- README.md docs examples/README.md AGENTS.md`

Expected: exit `0` with no whitespace errors.

Run: `rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md AGENTS.md`

Expected: no output.

- [ ] **Step 5: Run final pre-release evidence gates**

Run: `PYTHONPATH=src conda run -n atst-dev pytest tests -q`

Expected: all tests PASS.

Run: `conda run -n atst-dev python scripts/verify_wheel_api.py`

Expected: exit `0` from a clean installed wheel environment.

- [ ] **Step 6: Commit**

```bash
git add README.md docs tests/unit/test_docs_api.py
git commit -m "docs: publish API runner contract"
```

## Release Checkpoint

After Tasks 1–4 pass and an independent review finds no blocker, merge the feature branch through the repository's normal process, build the exact 2.2.0 artifacts, and verify their hashes and installed metadata. Creating the `2.2.0` tag and GitHub/PyPI release remains a separately confirmed release action; ABACUS Agent must not pin a local-only commit as though it were released.
