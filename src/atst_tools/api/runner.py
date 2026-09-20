"""Process runner for the stable configuration-driven ATST Python API."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import traceback
from typing import Iterator, Sequence

from atst_tools.api.models import ATSTAPIError

_LOG_LEVEL_ENV = "ATST_LOG_LEVEL"


def _api_attr(name: str):
    """Resolve one public API attribute lazily (PEP 562 keeps import light)."""
    value = globals().get(name)
    if value is None:
        import atst_tools.api as api

        value = getattr(api, name)
        globals()[name] = value
    return value


def __getattr__(name: str):
    """Expose the lazily resolved public API names on this module."""
    if name in ("RunOptions", "run_workflow"):
        return _api_attr(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for ``python -m atst_tools.api.runner``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="ATST YAML configuration path")
    parser.add_argument("--workdir", default=".", help="Workflow working directory")
    parser.add_argument(
        "--result-json",
        default="atst_api_result.json",
        help="Root-rank JSON handoff path, relative to workdir by default",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without execution")
    parser.add_argument("--restart", action="store_true", help="Resume a restartable workflow")
    parser.add_argument(
        "--check-input", action="store_true", help="Run configured input preflight checks"
    )
    parser.add_argument(
        "--check-input-timeout",
        type=int,
        default=120,
        help="Input preflight timeout in seconds",
    )
    parser.add_argument(
        "--abacus-executable", help="Override the configured ABACUS executable"
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help=(
            "Emit structured NDJSON progress events on stdout, one per line; "
            "the same event set as the Python API RunOptions(progress=True)"
        ),
    )
    parser.add_argument(
        "--profiles",
        action="store_true",
        help=(
            "Include the per-image/per-step energy and force summary in the "
            "result document (NEB/AutoNEB images; Sella/CCQN steps)"
        ),
    )
    parser.add_argument(
        "--plots",
        action="store_true",
        help=(
            "Render the workflow energy plot PNG and record its relative path "
            "in the result document and artifact manifest"
        ),
    )
    parser.add_argument(
        "--devices",
        default=None,
        help="Request 0-based logical device indices or full GPU UUIDs (runtime.devices).",
    )
    parser.add_argument(
        "--binding",
        default=None,
        choices=("inherit", "round_robin"),
        help="Per-rank device binding mode for MPI launches.",
    )
    parser.add_argument(
        "--threads",
        default=None,
        help="Process thread budget applied before the scientific stack is imported.",
    )
    parser.add_argument(
        "--telemetry",
        dest="telemetry",
        action="store_true",
        default=None,
        help="Enable the runtime evidence sidecar and GPU host sampling.",
    )
    parser.add_argument(
        "--no-telemetry",
        dest="telemetry",
        action="store_false",
        help="Explicitly disable runtime telemetry.",
    )
    parser.add_argument(
        "--telemetry-interval",
        dest="telemetry_interval",
        default=None,
        help="Host sampling interval in seconds (default 1.0).",
    )
    return parser


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    """Enter *path* temporarily and restore the caller directory afterwards."""
    original = Path.cwd()
    path.mkdir(parents=True, exist_ok=True)
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def _process_rank() -> int:
    """Return the externally assigned MPI rank, or zero for serial execution."""
    try:
        from mpi4py import MPI

        return int(MPI.COMM_WORLD.Get_rank())
    except Exception:
        for name in ("OMPI_COMM_WORLD_RANK", "PMI_RANK", "PMIX_RANK", "MPI_LOCALRANKID"):
            value = os.environ.get(name)
            if value is not None:
                try:
                    return int(value)
                except ValueError:
                    continue
    return 0


def _result_path(value: str, workdir: Path) -> Path:
    """Resolve a result handoff path against the workflow directory."""
    path = Path(value)
    return path if path.is_absolute() else workdir / path


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    """Publish one JSON document atomically without leaving partial results."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def _error_document(error: ATSTAPIError) -> dict[str, object]:
    """Wrap a public API error in the versioned runner result schema."""
    return {
        "schema": "atst-api-result-v1",
        "status": "error",
        "workflow": error.workflow,
        "error": error.to_document(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run one configuration workflow and return its stable process exit code."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(arguments)
    workdir = Path(args.workdir).resolve()
    config_path = Path(args.config).resolve()
    result_path = _result_path(args.result_json, workdir)
    is_root = _process_rank() == 0
    level = os.environ.get(_LOG_LEVEL_ENV)
    if level:
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO), format="%(message)s"
        )
    options = _api_attr("RunOptions")(
        dry_run=args.dry_run,
        restart=args.restart,
        check_input=args.check_input,
        check_input_timeout=args.check_input_timeout,
        abacus_executable=args.abacus_executable,
        progress=args.progress,
        profiles=args.profiles,
        plots=args.plots,
    )

    try:
        with _working_directory(workdir):
            from atst_tools.runtime.cli_dispatch import plan_runner_launch

            plan = plan_runner_launch(arguments, workdir=workdir)
            if plan is not None:  # pragma: no cover - replaces the process
                plan.execute()
            result = _api_attr("run_workflow")(config_path, options)
            if is_root:
                _write_json_atomic(result_path, result.to_document(workdir))
    except ATSTAPIError as error:
        if is_root:
            _write_json_atomic(result_path, _error_document(error))
        return 2
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through module execution.
    raise SystemExit(main())
