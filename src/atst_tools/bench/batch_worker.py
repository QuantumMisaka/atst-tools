"""Shared-worker executor for the batch runner's opt-in ``--share-worker`` mode.

Every case of a batch normally runs in its own worker process, so a machine
learned potential pays its fixed per-process cost - model load, first-call warm
up, framework compilation - once per case.  In ``--share-worker`` mode the
batch runner launches exactly one child, this module, and every case of the
batch runs sequentially inside it, so that fixed cost is paid once.

Usage::

    python -m atst_tools.bench.batch_worker --jobs <jobs.json> --out <out_dir>

``jobs.json`` is written by the batch runner: a JSON array of
``{"case_id": ..., "config": ..., "workdir": ...}`` rows holding absolute
paths.  For every row the worker enters ``workdir``, runs the workflow through
the public API (``atst_tools.api.run_workflow`` with ``RunOptions``) and writes
``<out_dir>/<case_id>/atst_api_result.json``.  The document shape and the
atomic writer are imported from ``atst_tools.api.runner`` so this entry point
cannot drift away from ``python -m atst_tools.api.runner``.

Progress contract - one English line per case on stdout::

    [batch_worker] case=<case_id> status=<status> wall_s=<seconds>

``status`` uses the result-document vocabulary: ``success`` for a case whose
workflow returned, ``error`` for a case whose workflow raised.  The batch
runner maps ``success`` onto its ``succeeded`` case status and ``error`` onto
``failed``, and records the reported ``wall_s`` as that case's own duration.
Both the producer and the consumer use the helpers below, so the two sides of
this contract cannot disagree.

A case that raises is recorded as ``error`` - with the same error document the
API runner writes - and the loop continues with the next case.  A case is never
retried.  The exit status is 0 when every job was attempted, whatever its
per-case outcome, and non-zero only for a setup failure (the job list cannot be
read).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

# Private helpers on purpose: the atomic writer and the error document of the
# API runner are the schema this module must reproduce byte for byte, so they
# are reused instead of copied.  They live in the same package and are imported
# from the defining module rather than through a second implementation.
from atst_tools.api import runner as _runner
from atst_tools.api.models import ATSTAPIError, WorkflowExecutionError

PROGRESS_PREFIX = "[batch_worker]"
RESULT_JSON = "atst_api_result.json"

STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

SETUP_FAILURE_EXIT = 2

_LOG_LEVEL_ENV = "ATST_LOG_LEVEL"


@dataclass(frozen=True)
class Job:
    """One row of the shared job list (absolute ``config`` and ``workdir``)."""

    case_id: str
    config: str
    workdir: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], index: int) -> "Job":
        """Build one job from a job-list row, rejecting malformed rows.

        Raises:
            ValueError: The row is not a mapping or a required field is empty.
        """
        if not isinstance(payload, Mapping):
            raise ValueError(f"job {index}: every job row must be a mapping")
        fields: dict[str, str] = {}
        for key in ("case_id", "config", "workdir"):
            value = str(payload.get(key) or "").strip()
            if not value:
                raise ValueError(f"job {index}: '{key}' must be a non-empty string")
            fields[key] = value
        return cls(**fields)


def load_jobs(path: str | Path) -> list[Job]:
    """Read the job list written by the batch runner.

    Raises:
        ValueError: The list is unreadable, is not a non-empty JSON array or
            holds a malformed row.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"the job list cannot be read: {exc}") from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"the job list is not valid JSON: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError("the job list must be a non-empty JSON array")
    return [Job.from_mapping(row, index) for index, row in enumerate(payload)]


def format_progress_line(case_id: str, status: str, wall_s: float) -> str:
    """Return the one-line per-case progress record the batch runner parses."""
    return f"{PROGRESS_PREFIX} case={case_id} status={status} wall_s={wall_s:.3f}"


def parse_progress_line(line: str) -> tuple[str, str, float] | None:
    """Parse one progress line into ``(case_id, status, wall_s)``.

    Returns:
        The parsed triple, or ``None`` for any line that is not a complete
        progress record (workflow output shares this stream, and a writer may
        still be flushing a partial line).
    """
    text = line.strip()
    if not text.startswith(PROGRESS_PREFIX):
        return None
    fields: dict[str, str] = {}
    for token in text[len(PROGRESS_PREFIX) :].split():
        key, separator, value = token.partition("=")
        if separator and key and value:
            fields[key] = value
    case_id = fields.get("case", "")
    status = fields.get("status", "")
    raw_wall = fields.get("wall_s")
    if not case_id or not status or raw_wall is None:
        return None
    try:
        wall_s = float(raw_wall)
    except ValueError:
        return None
    return case_id, status, wall_s


def _run_workflow(config_path: Path) -> Any:
    """Run one workflow through the public API (lazy import keeps startup light)."""
    import atst_tools.api as api

    return api.run_workflow(config_path, api.RunOptions())


def _unexpected_error(exc: BaseException) -> WorkflowExecutionError:
    """Wrap a non-API exception in the public error document model."""
    error = WorkflowExecutionError(
        f"{type(exc).__name__}: {exc}",
        context={"exception": type(exc).__name__},
    )
    error.__cause__ = exc
    return error


def _publish_error(result_path: Path, error: ATSTAPIError) -> None:
    """Write one error document; a write failure must not end the batch."""
    try:
        _runner._write_json_atomic(result_path, _runner._error_document(error))
    except OSError as exc:
        print(
            f"{PROGRESS_PREFIX} warning: cannot write {result_path}: {exc}",
            file=sys.stderr,
            flush=True,
        )


def run_job(job: Job, output_dir: str | Path) -> str:
    """Run one job in its own working directory and return its case status.

    The workflow always runs in the job work directory, so every artifact of a
    case stays attributable to that case even though the process is shared.
    Failures are recorded as an ``error`` result document instead of being
    raised: a broken case must not take the rest of the batch down.

    Returns:
        :data:`STATUS_SUCCESS` or :data:`STATUS_ERROR`.
    """
    result_path = Path(output_dir) / job.case_id / RESULT_JSON
    workdir = Path(job.workdir)
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        os.chdir(workdir)
        result = _run_workflow(Path(job.config).resolve())
    except ATSTAPIError as error:
        _publish_error(result_path, error)
        return STATUS_ERROR
    except Exception as exc:  # noqa: BLE001 - one case must not end the batch
        traceback.print_exc()
        _publish_error(result_path, _unexpected_error(exc))
        return STATUS_ERROR
    try:
        _runner._write_json_atomic(result_path, result.to_document(workdir))
    except OSError as exc:
        print(
            f"{PROGRESS_PREFIX} warning: cannot write {result_path}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return STATUS_ERROR
    return STATUS_SUCCESS


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for ``python -m atst_tools.bench.batch_worker``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", required=True, help="Job list JSON path")
    parser.add_argument("--out", required=True, help="Batch output directory")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run every job of one shared batch and return the process exit status."""
    args = build_parser().parse_args(argv)
    level = os.environ.get(_LOG_LEVEL_ENV)
    if level:
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO), format="%(message)s"
        )
    output_dir = Path(args.out).resolve()
    try:
        jobs = load_jobs(args.jobs)
        output_dir.mkdir(parents=True, exist_ok=True)
    except (ValueError, OSError) as exc:
        print(f"{PROGRESS_PREFIX} setup failure: {exc}", file=sys.stderr, flush=True)
        return SETUP_FAILURE_EXIT
    for job in jobs:
        started = time.monotonic()
        status = run_job(job, output_dir)
        wall_s = time.monotonic() - started
        print(format_progress_line(job.case_id, status, wall_s), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution entry
    raise SystemExit(main())
