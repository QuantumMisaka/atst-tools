"""Batch runner for the GPU node tuning work (P3): finite case lists.

Runs one bounded case manifest inside one existing allocation.  The module
was called ``harness`` until 2026-09-21, and its artifact file names follow
the module name now: ``case_report.json`` per case, ``batch_summary.json`` per
batch, and ``worker.out`` / ``worker.err`` inside the per-case report
directory.

Only two ``harness`` spellings stay frozen, because archived evidence carries
them as values rather than as module names:

* the schema string ``atst-bench-harness-v1``, a versioned document identifier
  that every archived case report and batch summary records;
* the per-case evidence value ``ATST_THREADS_SOURCE=harness``, which the
  archived run sidecars report as ``threads_source``.

Legacy run directories - the archived slices under ``docs/reports/data/**``,
plus any batch staged before this rename - still hold ``harness_case.json``,
``harness_summary.json`` and ``harness_worker.out`` / ``harness_worker.err``.
Those trees stay readable: ``atst_tools.bench.record`` accepts either summary
spelling and falls back to the legacy one.

The batch runner executes a bounded case list inside one existing allocation:

* every case runs as an isolated worker process in its own output directory;
* device slots and the CPU thread budget are both respected (a case's rank
  multiplier from its launcher, or its declared ``ranks``, counts towards the
  thread budget);
* failures, timeouts, OOM signals and skips stay in the report instead of
  disappearing from the denominator;
* retries never happen implicitly - a new attempt is a new manifest row;
* one batch-level host sampler covers the whole batch; per-case evidence
  sidecars (and their own samplers) are opt-in through ``case_telemetry``.

One worker process per case is the default.  ``--share-worker`` is the opt-in
single-process mode: every case of the batch runs sequentially inside one child
(``atst_tools.bench.batch_worker``), so a machine learned potential pays its
fixed model load, first-call warm-up and compilation cost once instead of once
per case.  That mode acquires exactly one device slot for the whole batch and
reports per-case wall time as the case's own segment inside the shared process.
It also publishes the bound-process facts of that slot (see
:func:`shared_bound_environment`), so case configs that declare a ``runtime:``
section run unchanged while a request that contradicts the binding is still
refused per case.

Usage::

    python -m atst_tools.bench.batch_runner --manifest cases.json --out runs/batch \\
        --devices 0,1 --slots 1 --cpu-budget 16
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from atst_tools.bench import batch_worker as _batch_worker
from atst_tools.runtime import devices as _devices
from atst_tools.runtime import evidence as _evidence
from atst_tools.runtime import launch as _launch

# Frozen: a versioned document identifier, not a module name.  Archived case
# reports and batch summaries record this value and ``bench_record`` hashes
# their trees, so renaming it would misread every stored row.
SCHEMA = "atst-bench-harness-v1"
# Artifact names follow the module name (see the module docstring for the
# legacy ``harness_case.json`` / ``harness_summary.json`` spelling that
# archived run trees keep).
CASE_REPORT = "case_report.json"
SUMMARY_REPORT = "batch_summary.json"
DEFAULT_RESULT_JSON = "atst_api_result.json"
TERMINATION_GRACE_S = 5.0

# Shared-worker mode (``--share-worker``): one child runs the whole batch.
SHARED_WORKER_MODULE = "atst_tools.bench.batch_worker"
JOBS_REPORT = "batch_jobs.json"
# Slot-pool key of the single slot the shared batch holds for its whole wall
# clock; it is not a case id and never reaches an artifact.
SHARED_BATCH_SLOT = "__batch__"
# English reason recorded for the case the shared worker was running plus every
# case it never reached when that worker died mid-batch.
SHARED_WORKER_EXIT_REASON = "shared worker exited"
_SHARED_SUCCESS_STATUSES = frozenset({"success", "succeeded"})
_SHARED_ERROR_STATUSES = frozenset({"error", "failed"})

STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"
STATUS_SKIPPED = "skipped"

_OOM_MARKERS = (
    "cuda out of memory",
    "out of memory",
    "out_of_memory",
    "oom-kill",
)


def _now() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CaseSpec:
    """One finite case row: inputs, slot demand, thread budget and timeout."""

    case_id: str
    config: str
    slots: int = 1
    threads: int = 1
    timeout_s: float | None = None
    workdir: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    launcher: tuple[str, ...] = ()
    args: tuple[str, ...] = ()
    ranks: int | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CaseSpec":
        """Build one case from a manifest row, rejecting malformed rows."""
        case_id = str(payload.get("case_id") or "").strip()
        config = str(payload.get("config") or "").strip()
        if not case_id or not config:
            raise ValueError("each case requires a non-empty case_id and config")
        slots = int(payload.get("slots", 1))
        threads = int(payload.get("threads", 1))
        if slots < 1 or threads < 1:
            raise ValueError(f"case {case_id}: slots and threads must be positive")
        timeout = payload.get("timeout_s")
        env = payload.get("env") or {}
        if not isinstance(env, Mapping):
            raise ValueError(f"case {case_id}: env must be a mapping")
        launcher = payload.get("launcher") or ()
        if isinstance(launcher, str):
            launcher = tuple(shlex.split(launcher))
        if isinstance(launcher, (list, tuple)) and not all(
            isinstance(item, str) for item in launcher
        ):
            raise ValueError(f"case {case_id}: launcher entries must be strings")
        args = payload.get("args") or ()
        if isinstance(args, str):
            args = tuple(shlex.split(args))
        if isinstance(args, (list, tuple)) and not all(
            isinstance(item, str) for item in args
        ):
            raise ValueError(f"case {case_id}: args entries must be strings")
        ranks = payload.get("ranks")
        if ranks is not None:
            ranks = int(ranks)
            if ranks < 1:
                raise ValueError(f"case {case_id}: ranks must be positive")
        return cls(
            case_id=case_id,
            config=config,
            slots=slots,
            threads=threads,
            timeout_s=None if timeout is None else float(timeout),
            workdir=payload.get("workdir"),
            env={str(key): str(value) for key, value in env.items()},
            launcher=tuple(launcher),
            args=tuple(args),
            ranks=ranks,
        )


@dataclass
class BatchOptions:
    """Batch-level controls; every default is explicit and conservative."""

    devices: tuple[str, ...]
    output_dir: Path
    slots_per_device: int = 1
    cpu_budget: int | None = None
    default_threads: int = 1
    default_timeout_s: float | None = None
    continue_on_failure: bool = True
    sampler_interval_s: float = 1.0
    telemetry: bool = True
    case_telemetry: bool = True
    share_worker: bool = False
    worker_factory: Callable[
        ["CaseSpec", Path, tuple[str, ...]], Sequence[str]
    ] | None = None
    shared_worker_factory: Callable[[Path, Path], Sequence[str]] | None = None
    stop_event: threading.Event | None = None

    def cpu_limit(self) -> int:
        """Return the CPU thread budget of this batch."""
        if self.cpu_budget is not None:
            return max(int(self.cpu_budget), 1)
        raw = os.environ.get("ATST_BATCH_CPU_BUDGET", "").strip()
        if raw.isdigit() and int(raw) >= 1:
            return int(raw)
        try:
            return max(len(os.sched_getaffinity(0)), 1)
        except AttributeError:  # pragma: no cover - non-Linux
            return max(os.cpu_count() or 1, 1)


def load_cases(manifest: Mapping[str, Any], options: BatchOptions) -> list[CaseSpec]:
    """Load and normalise the manifest case rows."""
    rows = manifest.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ValueError("the manifest requires a non-empty 'cases' list")
    defaults = manifest.get("defaults") or {}
    cases: list[CaseSpec] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("every manifest case must be a mapping")
        merged = dict(row)
        merged.setdefault("threads", defaults.get("threads", options.default_threads))
        merged.setdefault(
            "timeout_s", defaults.get("timeout_s", options.default_timeout_s)
        )
        case = CaseSpec.from_mapping(merged)
        if case.case_id in seen:
            raise ValueError(f"duplicate case_id {case.case_id!r}")
        seen.add(case.case_id)
        cases.append(case)
    shared: dict[str, list[str]] = {}
    for case in cases:
        if case.workdir is not None:
            location = f"workdir:{case.workdir}"
        else:
            # Without an explicit workdir a case runs in its configuration
            # directory, so two cases whose configs share a directory would
            # overwrite each other's trajectories, manifests and caches.
            location = f"config-dir:{Path(case.config).resolve().parent}"
        shared.setdefault(location, []).append(case.case_id)
    clashes = {value: ids for value, ids in shared.items() if len(ids) > 1}
    if clashes:
        detail = "; ".join(
            f"{value} is shared by {', '.join(ids)}" for value, ids in clashes.items()
        )
        raise ValueError(
            f"cases must run in distinct directories so evidence cannot be "
            f"overwritten; give every case its own workdir ({detail})"
        )
    return cases


_RANK_FLAGS = ("-n", "-np", "--n", "--np", "--ntasks")


def resolve_case_ranks(case: CaseSpec) -> tuple[int, str]:
    """Return ``(ranks, source)`` for one case.

    A declared ``ranks`` wins; otherwise the launcher's ``-n``-style flag is
    parsed; a launcher without a recognizable rank flag is recorded as an
    explicit ``assumed-1`` so the CPU budget never silently ignores the rank
    multiplier.
    """
    if case.ranks is not None:
        return int(case.ranks), "declared"
    tokens = list(case.launcher)
    for index, token in enumerate(tokens):
        if token in _RANK_FLAGS and index + 1 < len(tokens):
            value = tokens[index + 1]
            if value.isdigit() and int(value) >= 1:
                return int(value), "parsed"
    return (1, "assumed-1") if tokens else (1, "serial")


def case_thread_cost(case: CaseSpec) -> int:
    """Return the CPU thread cost of one case, including its rank multiplier."""
    ranks, _ = resolve_case_ranks(case)
    return int(case.threads) * ranks


def worker_command(
    case: CaseSpec,
    workdir: Path,
    devices: tuple[str, ...],
    *,
    result_json: Path | None = None,
    factory: Callable[[CaseSpec, Path, tuple[str, ...]], Sequence[str]] | None = None,
) -> list[str]:
    """Return the worker argv for one case (the API runner by default).

    A case-level launcher (for example ``mpiexec -n 3``) is prefixed so
    image-parallel cases keep the batch-runner slot, timeout and reporting
    contracts.
    """
    if factory is not None:
        return list(factory(case, workdir, devices))
    del devices
    command = [
        *case.launcher,
        sys.executable,
        "-m",
        _launch.WORKER_MODULE,
        "--config",
        str(case.config),
        "--workdir",
        str(workdir),
        "--result-json",
        str(result_json) if result_json is not None else DEFAULT_RESULT_JSON,
    ]
    command += list(case.args)
    return command


def case_workdir(case: CaseSpec, output_dir: Path) -> Path:
    """Return where one case runs.

    The worker follows ATST path semantics (relative YAML paths resolve from
    the process working directory), so the default is the configuration file's
    own directory: a case behaves exactly like `atst run` typed there.  An
    explicit `workdir` is resolved against the batch output directory, which
    keeps concurrent cases of one manifest isolated.
    """
    if case.workdir:
        candidate = Path(case.workdir)
        return (
            candidate.resolve() if candidate.is_absolute() else (output_dir / candidate)
        )
    return Path(case.config).resolve().parent


def shared_worker_command(
    jobs_path: Path,
    output_dir: Path,
    *,
    factory: Callable[[Path, Path], Sequence[str]] | None = None,
) -> list[str]:
    """Return the argv of the single worker that runs a whole shared batch.

    The shared batch has exactly one child, so a case-level launcher cannot be
    honoured here; :func:`shared_batch_plan` refuses such a manifest instead of
    dropping the launcher silently.  ``factory`` overrides the argv and
    receives the job-list path and the batch output directory.
    """
    if factory is not None:
        return list(factory(Path(jobs_path), Path(output_dir)))
    return [
        sys.executable,
        "-m",
        SHARED_WORKER_MODULE,
        "--jobs",
        str(jobs_path),
        "--out",
        str(output_dir),
    ]


def write_jobs_file(cases: Sequence[CaseSpec], output_dir: Path) -> Path:
    """Write the shared worker's job list and return its path.

    Paths are absolute: the shared worker enters one case directory at a time,
    so relative paths would resolve against the wrong directory mid-batch.
    """
    rows = [
        {
            "case_id": case.case_id,
            "config": str(Path(case.config).resolve()),
            "workdir": str(case_workdir(case, output_dir)),
        }
        for case in cases
    ]
    path = Path(output_dir) / JOBS_REPORT
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return path


@dataclass(frozen=True)
class SharedBatchPlan:
    """Resolved single-process facts of one ``--share-worker`` batch."""

    devices: tuple[str, ...]
    threads: int
    env: dict[str, str]
    jobs_path: Path


def _shared_runtime_request() -> _launch.RuntimeRequest:
    """Return the binding request that the shared batch publishes.

    The batch runner is the coordinator of this launch: it acquires one device
    slot and hands that binding to the single child, exactly like the isolated
    per-case coordinator does through ``plan_runner_launch``.

    ``devices`` is deliberately ``None`` so that no requested-device record is
    published.  Every case then keeps being verified against the *published*
    binding (``ensure_runtime_contract`` falls back to the case config's own
    ``runtime.devices``), which is what keeps the mode fail-closed: a case that
    asks for a device outside the bound set is still refused instead of being
    silently redirected by a batch-level record.  Threads are left to
    :func:`case_environment`, which owns the ``harness`` thread marker together
    with the per-attempt cache directories of the batch.
    """
    return _launch.RuntimeRequest(
        devices=None,
        devices_source=None,
        binding="inherit",
        threads=None,
        threads_source=None,
        telemetry_enabled=False,
        telemetry_interval_s=0.0,
        requested=True,
    )


def shared_bound_environment(devices: Sequence[str]) -> dict[str, str]:
    """Return the bound-process facts of a shared worker (frozen contract).

    The published variables are the ones ``atst_tools.runtime.launch`` writes
    for an isolated bound worker - ``ATST_RUNTIME_BOUND``,
    ``ATST_INHERITED_DEVICES``, ``ATST_EFFECTIVE_DEVICES`` and ``ATST_BINDING``
    - and they are produced by that same helper so the two binding paths cannot
    drift apart.  Without them a case config carrying a ``runtime:`` section is
    rejected by the embedded-API guard ("embedding API cannot rebind devices")
    because the workflow sees an unbound process.

    The inherited set is the slot the batch actually holds, not every device the
    batch was given: the shared worker may only see its own device, and a case
    that asks for any other one must fail loudly rather than be rebound.
    """
    held = tuple(str(device) for device in devices)
    # The resolver is only asked to describe an already-bound worker: the
    # batch runner hands out host tokens (it never resolves a request against
    # the allocation), so the inherited set is seeded from the held slot.
    resolution = _devices.resolve_devices(
        None,
        binding="inherit",
        environ={_devices.CUDA_VISIBLE_DEVICES: ",".join(held)},
    )
    return _launch.build_child_environment(
        _shared_runtime_request(),
        resolution,
        base=os.environ,
        log_level=os.environ.get(_launch.LOG_LEVEL_ENV),
    )


def shared_batch_plan(
    cases: Sequence[CaseSpec],
    options: BatchOptions,
    *,
    output_dir: Path,
    cpu_limit: int,
) -> SharedBatchPlan:
    """Resolve the one-process facts of a shared batch, or fail explicitly.

    In this mode one process owns the batch for its whole wall clock, so a
    per-case dimension that a single process cannot carry is refused instead of
    being dropped silently: more than one slot per device, a per-case launcher
    and per-case environments that disagree.  The thread budget is the largest
    case cost, because the cases run one after another in the same process.  The
    environment mirrors :func:`case_environment` (caller-bound device, the four
    thread keys, the ``harness`` thread marker, one attempt and a per-attempt
    cache directory), with the batch output directory as the workflow directory.

    The environment additionally carries the bound-process facts published by
    :func:`shared_bound_environment`, so the shared worker is a *bound* worker:
    case configs that declare a ``runtime:`` section - the normal shape of the
    DP, ABACUS, CCQN and joint-acceptance manifests - are validated against the
    published binding instead of being refused by the embedded-API guard, and a
    config that contradicts the binding is still refused per case.

    Returns:
        The plan, including the single device slot, the shared environment and
        the job-list path.

    Raises:
        RuntimeError: The manifest cannot be honoured by one shared process.
    """
    if options.slots_per_device != 1:
        raise RuntimeError(
            "--share-worker runs the whole batch in one process, which holds "
            "exactly one device slot; rerun with --slots 1 (got --slots "
            f"{options.slots_per_device})"
        )
    environments: dict[str, tuple[dict[str, str], list[str]]] = {}
    for case in cases:
        if case.launcher:
            raise RuntimeError(
                f"case {case.case_id}: --share-worker runs every case in one "
                f"process, so the per-case launcher "
                f"'{' '.join(case.launcher)}' cannot be honoured; drop the "
                "launcher or drop --share-worker"
            )
        key = json.dumps(dict(sorted(case.env.items())), sort_keys=True)
        environments.setdefault(key, (dict(case.env), []))[1].append(case.case_id)
    if len(environments) > 1:
        detail = "; ".join(
            f"{', '.join(ids)} declares {values}"
            for values, ids in environments.values()
        )
        raise RuntimeError(
            "--share-worker sets one process environment for the whole batch, "
            f"so every case must declare the same env mapping ({detail})"
        )
    threads = max(case_thread_cost(case) for case in cases)
    if threads > cpu_limit:
        raise RuntimeError(
            "--share-worker runs every case in one process whose thread budget "
            f"is the largest case cost ({threads}); the batch CPU budget is "
            f"{cpu_limit}"
        )
    pool = _SlotPool(options.devices, 1)
    devices = pool.acquire(SHARED_BATCH_SLOT, 1)
    if devices is None:
        raise RuntimeError(
            "--share-worker needs exactly one device slot for the whole batch, "
            "but no device was given (--devices is empty)"
        )
    common_env = next(iter(environments.values()), ({}, []))[0]
    shared_case = CaseSpec(
        case_id=SHARED_BATCH_SLOT,
        config=str(Path(output_dir) / JOBS_REPORT),
        threads=threads,
        env=common_env,
    )
    env = case_environment(
        shared_case,
        devices,
        base=shared_bound_environment(devices),
        attempt=1,
        workdir=Path(output_dir),
        case_telemetry=options.case_telemetry,
    )
    return SharedBatchPlan(
        devices=devices,
        threads=threads,
        env=env,
        jobs_path=write_jobs_file(cases, output_dir),
    )


def case_environment(
    case: CaseSpec,
    devices: tuple[str, ...],
    *,
    base: Mapping[str, str],
    attempt: int,
    workdir: Path,
    case_telemetry: bool = True,
) -> dict[str, str]:
    """Build the isolated environment of one case (caller-bound devices)."""
    env = dict(base)
    env[_devices.CUDA_VISIBLE_DEVICES] = ",".join(devices)
    for key in _launch.THREAD_ENV_KEYS:
        env[key] = str(case.threads)
    # The manifest budget is an explicit caller request, not an implicit
    # default: mark it so the ABACUS factory keeps it instead of falling back to
    # the legacy single thread.  A case config carrying its own
    # ``runtime.threads`` overwrites this marker in the worker environment.
    # Frozen evidence value: archived sidecars record threads_source=harness, so
    # the marker keeps that spelling even though the module is now batch_runner.
    env[_launch.THREADS_SOURCE_ENV] = "harness"
    env[_launch.ATTEMPT_ENV] = str(attempt)
    cache_dir = _launch.child_cache_dir(workdir, attempt)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for key in _launch.CACHE_ENV_KEYS:
        env[key] = str(cache_dir)
    if case_telemetry:
        env.setdefault(_launch.TELEMETRY_ENV, "1")
    env.update(case.env)
    return env


def classify_exit(exit_code: int | None, stderr_text: str) -> tuple[str, str | None]:
    """Classify one finished case without inventing unattributable reasons."""
    lowered = stderr_text.lower()
    if any(marker in lowered for marker in _OOM_MARKERS):
        return STATUS_FAILED, "oom"
    if exit_code is None:
        return STATUS_FAILED, "unknown"
    if exit_code < 0:
        return STATUS_FAILED, f"signal {-exit_code}"
    if exit_code == 0:
        return STATUS_SUCCEEDED, None
    return STATUS_FAILED, f"exit {exit_code}"


class _SlotPool:
    """Atomic device-slot allocation across the visible pool."""

    def __init__(self, devices: Sequence[str], slots_per_device: int) -> None:
        self._free: list[tuple[str, int]] = [
            (device, slot)
            for device in devices
            for slot in range(max(int(slots_per_device), 1))
        ]
        self._held: dict[str, list[tuple[str, int]]] = {}

    def acquire(self, case_id: str, slots: int) -> tuple[str, ...] | None:
        """Reserve ``slots`` device slots atomically, or return ``None``."""
        if slots <= 1:
            if not self._free:
                return None
            taken = [self._free.pop(0)]
        else:
            taken = []
            seen: list[str] = []
            for pair in self._free:
                if pair[0] in seen:
                    continue
                seen.append(pair[0])
                taken.append(pair)
                if len(taken) == slots:
                    break
            if len(taken) < slots:
                return None
            for pair in taken:
                self._free.remove(pair)
        self._held[case_id] = taken
        return tuple(device for device, _ in taken)

    def release(self, case_id: str) -> None:
        """Return every slot held by one case."""
        for item in self._held.pop(case_id, []):
            self._free.append(item)

    @property
    def free_count(self) -> int:
        """Return how many device slots are currently free."""
        return len(self._free)


@dataclass
class _RunningCase:
    case: CaseSpec
    process: subprocess.Popen
    devices: tuple[str, ...]
    workdir: Path
    report_dir: Path
    stdout_path: Path
    stderr_path: Path
    started_monotonic: float
    started_at: str
    attempt: int = 1


def _terminate_group(
    process: subprocess.Popen, grace: float = TERMINATION_GRACE_S
) -> None:
    """Terminate one worker group, including children that ignore SIGTERM.

    The process-group id is captured before any signal because it becomes
    unavailable once the group leader is reaped; after the grace window the
    whole group is SIGKILLed and its emptiness is confirmed, so a surviving
    child cannot keep occupying a GPU after the batch runner moved on.
    """
    try:
        pgid = os.getpgid(process.pid)
    except (ProcessLookupError, PermissionError):
        return

    def signal_group(sig: int) -> None:
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    if process.poll() is None:
        signal_group(signal.SIGTERM)
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    for _ in range(20):
        try:
            os.killpg(pgid, 0)
        except (ProcessLookupError, PermissionError):
            return
        signal_group(signal.SIGKILL)
        time.sleep(0.05)


def _case_report_payload(
    running: _RunningCase,
    *,
    status: str,
    exit_code: int | None,
    classification: str | None,
    wall_s: float,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "case_id": running.case.case_id,
        "attempt": running.attempt,
        "status": status,
        "classification": classification,
        "exit_code": exit_code,
        "devices": list(running.devices),
        "threads": running.case.threads,
        "ranks": resolve_case_ranks(running.case)[0],
        "ranks_source": resolve_case_ranks(running.case)[1],
        "started_at": running.started_at,
        "finished_at": _now(),
        "wall_s": round(wall_s, 3),
        "gpu_seconds": round(wall_s * len(running.devices), 3),
        "config": running.case.config,
        "launcher": list(running.case.launcher),
        "args": list(running.case.args),
        "workdir": str(running.workdir),
        "result_json": (
            str(running.report_dir / DEFAULT_RESULT_JSON)
            if (running.report_dir / DEFAULT_RESULT_JSON).exists()
            else None
        ),
        "stdout": str(running.stdout_path),
        "stderr": str(running.stderr_path),
    }


def _record_skipped(
    case: CaseSpec, output_dir: Path, classification: str
) -> dict[str, Any]:
    """Write and return the record of a case that never started."""
    payload = {
        "schema": SCHEMA,
        "case_id": case.case_id,
        "attempt": 1,
        "status": STATUS_SKIPPED,
        "classification": classification,
        "exit_code": None,
        "devices": [],
        "threads": case.threads,
        "ranks": resolve_case_ranks(case)[0],
        "ranks_source": resolve_case_ranks(case)[1],
        "started_at": None,
        "finished_at": _now(),
        "wall_s": 0.0,
        "gpu_seconds": 0.0,
        "config": case.config,
        "launcher": list(case.launcher),
        "args": list(case.args),
        "workdir": str(case_workdir(case, output_dir)),
        "result_json": None,
        "stdout": None,
        "stderr": None,
    }
    case_dir = output_dir / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / CASE_REPORT).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def _record_spawn_failure(
    case: CaseSpec, output_dir: Path, message: str
) -> dict[str, Any]:
    """Write and return the record of a case whose worker could not start."""
    payload = {
        "schema": SCHEMA,
        "case_id": case.case_id,
        "attempt": 1,
        "status": STATUS_FAILED,
        "classification": f"spawn_error: {message}",
        "exit_code": None,
        "devices": [],
        "threads": case.threads,
        "ranks": resolve_case_ranks(case)[0],
        "ranks_source": resolve_case_ranks(case)[1],
        "started_at": None,
        "finished_at": _now(),
        "wall_s": 0.0,
        "gpu_seconds": 0.0,
        "config": case.config,
        "launcher": list(case.launcher),
        "args": list(case.args),
        "workdir": str(case_workdir(case, output_dir)),
        "result_json": None,
        "stdout": None,
        "stderr": None,
    }
    case_dir = output_dir / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / CASE_REPORT).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def _shared_case_report(
    case: CaseSpec,
    *,
    output_dir: Path,
    status: str,
    classification: str | None,
    wall_s: float,
    devices: tuple[str, ...],
    threads: int,
    exit_code: int | None,
    stdout_path: Path,
    stderr_path: Path,
    started_at: str | None,
) -> dict[str, Any]:
    """Write and return the case report of one case of a shared batch.

    The key set is the per-case report key set plus ``shared_worker``, so a
    consumer of either mode reads the same document.  ``wall_s`` is the
    worker-measured segment of that case inside the shared process: the fixed
    model load is therefore visible in the first case only.  ``exit_code`` is
    the shared worker's exit status when the case never finished on its own,
    and ``None`` for a case the worker completed - one process cannot attribute
    an exit status to a case it carried on past.
    """
    result_path = output_dir / case.case_id / DEFAULT_RESULT_JSON
    payload = {
        "schema": SCHEMA,
        "case_id": case.case_id,
        "attempt": 1,
        "status": status,
        "classification": classification,
        "exit_code": exit_code,
        "devices": list(devices),
        "threads": threads,
        "ranks": 1,
        "ranks_source": "shared-worker",
        "started_at": started_at,
        "finished_at": _now(),
        "wall_s": round(wall_s, 3),
        "gpu_seconds": round(wall_s * len(devices), 3),
        "config": case.config,
        "launcher": list(case.launcher),
        "args": list(case.args),
        "workdir": str(case_workdir(case, output_dir)),
        "result_json": str(result_path) if result_path.exists() else None,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "shared_worker": True,
    }
    case_dir = output_dir / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / CASE_REPORT).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def _shared_error_classification(output_dir: Path, case: CaseSpec) -> str:
    """Return what the parent can attribute to a failed shared case.

    The worker writes the API error document before it reports the case, so the
    recorded classification names the exception instead of leaving a bare
    "failed" with no cause.
    """
    document = output_dir / case.case_id / DEFAULT_RESULT_JSON
    if document.is_file():
        try:
            error = json.loads(document.read_text(encoding="utf-8")).get("error") or {}
        except (OSError, ValueError):
            error = {}
        detail = ": ".join(
            part
            for part in (
                str(error.get("type") or ""),
                str(error.get("message") or ""),
            )
            if part
        )
        if detail:
            return f"case_error: {detail[:200]}"
    return "case_error"


def _next_unrecorded(cases: Sequence[CaseSpec], recorded: set[str]) -> CaseSpec | None:
    """Return the case the shared worker is running, or ``None`` when done.

    Cases run sequentially in manifest order, so the first case without a
    progress record is the one in flight.
    """
    for case in cases:
        if case.case_id not in recorded:
            return case
    return None


class _ProgressReader:
    """Incremental reader of the shared worker's progress stream."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: Any = None
        self._pending = ""

    def lines(self) -> list[str]:
        """Return the complete lines appended since the previous call."""
        if self._handle is None:
            if not self._path.exists():
                return []
            self._handle = self._path.open("r", encoding="utf-8", errors="replace")
        chunk = self._handle.read()
        if not chunk:
            return []
        parts = (self._pending + chunk).split("\n")
        self._pending = parts.pop()
        return parts

    def close(self) -> None:
        """Close the underlying stream when it was opened."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def _run_shared_manifest(
    cases: Sequence[CaseSpec], options: BatchOptions, output_dir: Path
) -> dict[str, Any]:
    """Run every case of one batch inside a single shared worker process.

    One child runs the whole batch, so the parent owns the report layout: it
    writes the same ``case_report.json`` and ``batch_summary.json`` documents
    the per-case mode writes, taking each case's own duration from the worker's
    progress line.  A worker that dies mid-batch is never a silent skip: the
    case it was running and every case it never reached are recorded failed
    with the explicit reason ``shared worker exited``.  Zero cases are retried.

    The child inherits the caller's working directory (it enters each case
    directory itself), so a relative interpreter path such as ``PYTHONPATH=src``
    keeps resolving for the whole batch.
    """
    cpu_limit = options.cpu_limit()
    plan = shared_batch_plan(cases, options, output_dir=output_dir, cpu_limit=cpu_limit)
    stdout_path = output_dir / "worker.out"
    stderr_path = output_dir / "worker.err"
    sampler = (
        _evidence.HostSampler(options.sampler_interval_s) if options.telemetry else None
    )
    if sampler is not None:
        sampler.start()
    stop = options.stop_event or threading.Event()
    case_by_id = {case.case_id: case for case in cases}
    reports: list[dict[str, Any]] = []
    recorded: set[str] = set()
    batch_started = time.monotonic()
    batch_started_at = _now()
    segment_started = batch_started
    segment_started_at = batch_started_at
    cancelled = False
    abandoned: str | None = None
    exit_code: int | None = None
    process: subprocess.Popen | None = None
    sampler_summary: dict[str, Any] | None = None

    def _record(
        case: CaseSpec,
        *,
        status: str,
        classification: str | None,
        wall_s: float,
        case_exit_code: int | None = None,
        started_at: str | None = None,
    ) -> None:
        reports.append(
            _shared_case_report(
                case,
                output_dir=output_dir,
                status=status,
                classification=classification,
                wall_s=wall_s,
                devices=plan.devices,
                threads=plan.threads,
                exit_code=case_exit_code,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                started_at=started_at,
            )
        )
        recorded.add(case.case_id)

    def _read_progress(reader: _ProgressReader) -> None:
        """Record every case the worker has reported since the last read."""
        nonlocal segment_started, segment_started_at
        for line in reader.lines():
            parsed = _batch_worker.parse_progress_line(line)
            if parsed is None:
                continue
            case_id, status, wall_s = parsed
            case = case_by_id.get(case_id)
            if case is None or case.case_id in recorded:
                continue
            if status in _SHARED_SUCCESS_STATUSES:
                classification = None
                case_status = STATUS_SUCCEEDED
            elif status in _SHARED_ERROR_STATUSES:
                classification = _shared_error_classification(output_dir, case)
                case_status = STATUS_FAILED
            else:
                classification = f"shared worker reported status {status!r}"
                case_status = STATUS_FAILED
            _record(
                case,
                status=case_status,
                classification=classification,
                wall_s=wall_s,
                started_at=segment_started_at,
            )
            segment_started = time.monotonic()
            segment_started_at = _now()

    reader = _ProgressReader(stdout_path)
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    try:
        try:
            process = subprocess.Popen(
                shared_worker_command(
                    plan.jobs_path,
                    output_dir,
                    factory=options.shared_worker_factory,
                ),
                env=plan.env,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
        except OSError as exc:
            # No case of this batch can run: record every one instead of
            # letting an unstartable worker shrink the denominator.
            for case in cases:
                _record(
                    case,
                    status=STATUS_FAILED,
                    classification=f"spawn_error: {exc}",
                    wall_s=0.0,
                )
        stdout_handle.close()
        stderr_handle.close()

        while process is not None and len(recorded) < len(cases):
            _read_progress(reader)
            if len(recorded) >= len(cases):
                break
            if stop.is_set():
                cancelled = True
                _terminate_group(process)
                exit_code = process.poll()
                _read_progress(reader)
                break
            if (
                not options.continue_on_failure
                and reports
                and reports[-1]["status"] in {STATUS_FAILED, STATUS_TIMEOUT}
            ):
                abandoned = "stopped_after_failure"
                _terminate_group(process)
                exit_code = process.poll()
                _read_progress(reader)
                break
            finished = process.poll()
            if finished is not None:
                exit_code = finished
                # Take whatever the child flushed before it died.
                _read_progress(reader)
                break
            pending = _next_unrecorded(cases, recorded)
            timeout = None if pending is None else pending.timeout_s
            if timeout is not None and (time.monotonic() - segment_started) > timeout:
                abandoned = "timeout"
                _terminate_group(process)
                exit_code = process.poll()
                _read_progress(reader)
                if pending is not None and pending.case_id not in recorded:
                    _record(
                        pending,
                        status=STATUS_TIMEOUT,
                        classification=None,
                        wall_s=time.monotonic() - segment_started,
                        case_exit_code=exit_code,
                        started_at=segment_started_at,
                    )
                break
            time.sleep(0.05)

        # A fully reported batch leaves the child exiting: its status is the
        # batch-evidence exit code, so wait for it instead of reporting None.
        if process is not None and exit_code is None:
            try:
                exit_code = process.wait(timeout=TERMINATION_GRACE_S)
            except subprocess.TimeoutExpired:  # pragma: no cover - hung child
                exit_code = None

        # Cases the worker never reported: a cancel, a stop-on-failure, a
        # timeout kill or a worker that died mid-batch.  None of them may
        # vanish from the denominator.
        stop_after_failure = bool(
            not options.continue_on_failure
            and reports
            and reports[-1]["status"] in {STATUS_FAILED, STATUS_TIMEOUT}
        )
        in_flight = True
        for case in cases:
            if case.case_id in recorded:
                continue
            if cancelled:
                _record(
                    case,
                    status=STATUS_SKIPPED,
                    classification="cancelled",
                    wall_s=0.0,
                )
            elif stop_after_failure:
                _record(
                    case,
                    status=STATUS_SKIPPED,
                    classification="stopped_after_failure",
                    wall_s=0.0,
                )
            elif abandoned == "timeout":
                _record(
                    case,
                    status=STATUS_FAILED,
                    classification=SHARED_WORKER_EXIT_REASON,
                    wall_s=0.0,
                    case_exit_code=exit_code,
                )
            elif in_flight:
                # The worker died with this case in flight: the parent knows
                # how much of the segment elapsed, and every case after it
                # never started.
                in_flight = False
                _record(
                    case,
                    status=STATUS_FAILED,
                    classification=SHARED_WORKER_EXIT_REASON,
                    wall_s=time.monotonic() - segment_started,
                    case_exit_code=exit_code,
                    started_at=segment_started_at,
                )
            else:
                _record(
                    case,
                    status=STATUS_FAILED,
                    classification=SHARED_WORKER_EXIT_REASON,
                    wall_s=0.0,
                    case_exit_code=exit_code,
                )
    finally:
        reader.close()
        if process is not None and process.poll() is None:
            _terminate_group(process)
        if sampler is not None:
            sampler_summary = sampler.stop()

    succeeded = [row for row in reports if row["status"] == STATUS_SUCCEEDED]
    batch_wall = round(time.monotonic() - batch_started, 3)
    summary = {
        "schema": SCHEMA,
        "status": "cancelled" if cancelled else "complete",
        "revision": _evidence.atst_revision(),
        "started_at": batch_started_at,
        "finished_at": _now(),
        "wall_s": batch_wall,
        "devices": list(options.devices),
        # One shared process holds exactly one device slot for the whole batch,
        # so the cost-accounting view is the batch wall clock on that one
        # device; ``gpu_seconds_total`` below sums the per-case segments.
        "allocation": {
            "devices": list(plan.devices),
            "wall_s": batch_wall,
            "gpu_seconds": round(batch_wall * len(plan.devices), 3),
        },
        "slots_per_device": 1,
        "cpu_budget": cpu_limit,
        "cases_total": len(cases),
        "succeeded": len(succeeded),
        "failed": len([r for r in reports if r["status"] == STATUS_FAILED]),
        "timed_out": len([r for r in reports if r["status"] == STATUS_TIMEOUT]),
        "skipped": len([r for r in reports if r["status"] == STATUS_SKIPPED]),
        "gpu_seconds_total": round(
            sum(float(row["gpu_seconds"]) for row in reports), 3
        ),
        "cases": sorted(reports, key=lambda row: row["case_id"]),
        "telemetry": sampler_summary,
        "shared_worker": {
            "enabled": True,
            "pid": None if process is None else process.pid,
            "devices": list(plan.devices),
            "threads": plan.threads,
            "jobs": str(plan.jobs_path),
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "exit_code": exit_code,
            # Per-case durations come from the worker's own progress records.
            "per_case_wall_source": "batch_worker",
        },
    }
    (output_dir / SUMMARY_REPORT).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if cancelled:
        raise SystemExit("batch cancelled")
    return summary


def run_manifest(manifest: Mapping[str, Any], options: BatchOptions) -> dict[str, Any]:
    """Run every manifest case with slot/CPU limits and return the summary.

    ``options.share_worker`` switches the batch to the single-process mode; the
    default (one worker process per case) is unchanged.
    """
    cases = load_cases(manifest, options)
    output_dir = Path(options.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if options.share_worker:
        return _run_shared_manifest(cases, options, output_dir)
    pool = _SlotPool(options.devices, options.slots_per_device)
    cpu_limit = options.cpu_limit()
    sampler = (
        _evidence.HostSampler(options.sampler_interval_s) if options.telemetry else None
    )
    if sampler is not None:
        sampler.start()

    pending = list(cases)
    running: dict[str, _RunningCase] = {}
    reports: list[dict[str, Any]] = []
    threads_in_use = 0
    stop = options.stop_event or threading.Event()
    cancelled = False
    batch_started = time.monotonic()
    batch_started_at = _now()

    def _record(running_case: _RunningCase, status: str, exit_code: int | None) -> None:
        nonlocal threads_in_use
        stderr_text = ""
        if running_case.stderr_path.exists():
            stderr_text = running_case.stderr_path.read_text(
                encoding="utf-8", errors="replace"
            )[-20000:]
        _, classification = classify_exit(exit_code, stderr_text)
        wall = time.monotonic() - running_case.started_monotonic
        payload = _case_report_payload(
            running_case,
            status=status,
            exit_code=exit_code,
            classification=classification,
            wall_s=wall,
        )
        (output_dir / running_case.case.case_id).mkdir(parents=True, exist_ok=True)
        (output_dir / running_case.case.case_id / CASE_REPORT).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        reports.append(payload)
        pool.release(running_case.case.case_id)
        threads_in_use -= case_thread_cost(running_case.case)

    sampler_summary: dict[str, Any] | None = None
    try:
        while pending or running:
            if not running and pending:
                admissible = any(
                    case.slots <= pool.free_count
                    and case_thread_cost(case) <= cpu_limit
                    for case in pending
                )
                if not admissible and not stop.is_set():
                    blocked = ", ".join(case.case_id for case in pending)
                    raise RuntimeError(
                        f"no case can start with {len(options.devices)} device "
                        f"slot(s) and a CPU budget of {cpu_limit}: {blocked}"
                    )
            if stop.is_set() and not cancelled:
                cancelled = True
                for item in list(running.values()):
                    _terminate_group(item.process)
            if not cancelled:
                for case in list(pending):
                    if stop.is_set():
                        break
                    if threads_in_use + case_thread_cost(case) > cpu_limit:
                        continue
                    devices = pool.acquire(case.case_id, case.slots)
                    if devices is None:
                        continue
                    report_dir = output_dir / case.case_id
                    report_dir.mkdir(parents=True, exist_ok=True)
                    workdir = case_workdir(case, output_dir)
                    workdir.mkdir(parents=True, exist_ok=True)
                    env = case_environment(
                        case,
                        devices,
                        base=os.environ,
                        attempt=1,
                        workdir=workdir,
                        case_telemetry=options.case_telemetry,
                    )
                    # Legacy report directories keep ``harness_worker.out`` and
                    # ``harness_worker.err``; new runs write these names.
                    stdout_path = report_dir / "worker.out"
                    stderr_path = report_dir / "worker.err"
                    stdout_handle = stdout_path.open("w", encoding="utf-8")
                    stderr_handle = stderr_path.open("w", encoding="utf-8")
                    try:
                        process = subprocess.Popen(
                            worker_command(
                                case,
                                workdir,
                                devices,
                                result_json=report_dir / DEFAULT_RESULT_JSON,
                                factory=options.worker_factory,
                            ),
                            env=env,
                            cwd=workdir,
                            stdout=stdout_handle,
                            stderr=stderr_handle,
                            start_new_session=True,
                        )
                    except OSError as exc:
                        stdout_handle.close()
                        stderr_handle.close()
                        pool.release(case.case_id)
                        reports.append(
                            _record_spawn_failure(case, output_dir, str(exc))
                        )
                        pending.remove(case)
                        continue
                    stdout_handle.close()
                    stderr_handle.close()
                    running[case.case_id] = _RunningCase(
                        case=case,
                        process=process,
                        devices=devices,
                        workdir=workdir,
                        report_dir=report_dir,
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                        started_monotonic=time.monotonic(),
                        started_at=_now(),
                    )
                    threads_in_use += case_thread_cost(case)
                    pending.remove(case)
            if not running and not pending:
                break
            time.sleep(0.05)
            for case_id, item in list(running.items()):
                case = item.case
                timeout = case.timeout_s
                rc = item.process.poll()
                if rc is not None:
                    status, _ = classify_exit(
                        rc,
                        ""
                        if not item.stderr_path.exists()
                        else item.stderr_path.read_text(
                            encoding="utf-8", errors="replace"
                        )[-20000:],
                    )
                    _record(item, status, rc)
                    del running[case_id]
                    continue
                if (
                    timeout is not None
                    and (time.monotonic() - item.started_monotonic) > timeout
                ):
                    _terminate_group(item.process)
                    rc = item.process.poll()
                    _record(item, STATUS_TIMEOUT, rc)
                    del running[case_id]
                    continue
                if cancelled:
                    _terminate_group(item.process)
                    _record(item, STATUS_SKIPPED, item.process.poll())
                    del running[case_id]
            if cancelled and not running:
                for case in pending:
                    reports.append(_record_skipped(case, output_dir, "cancelled"))
                pending.clear()
            if (
                not options.continue_on_failure
                and reports
                and reports[-1]["status"] in {STATUS_FAILED, STATUS_TIMEOUT}
                and pending
            ):
                for case in list(pending):
                    reports.append(
                        _record_skipped(case, output_dir, "stopped_after_failure")
                    )
                pending.clear()
            if stop.is_set() and not running and not pending:
                break

    finally:
        # Any exit path (cancel, unexpected exception, KeyboardInterrupt) must
        # not leave worker process groups behind on a GPU node.
        for item in list(running.values()):
            _terminate_group(item.process)
        if sampler is not None:
            sampler_summary = sampler.stop()
    succeeded = [row for row in reports if row["status"] == STATUS_SUCCEEDED]
    batch_wall = round(time.monotonic() - batch_started, 3)
    summary = {
        "schema": SCHEMA,
        "status": "cancelled" if cancelled else "complete",
        "revision": _evidence.atst_revision(),
        "started_at": batch_started_at,
        "finished_at": _now(),
        "wall_s": batch_wall,
        "devices": list(options.devices),
        # ``gpu_seconds_total`` below sums per-case device-seconds (a case on
        # two devices counts two), which over-counts shared cards and ignores
        # allocated-but-idle time; ``allocation`` is the cost-accounting view:
        # every allocated device for the whole batch wall clock.
        "allocation": {
            "devices": list(options.devices),
            "wall_s": batch_wall,
            "gpu_seconds": round(batch_wall * len(options.devices), 3),
        },
        "slots_per_device": options.slots_per_device,
        "cpu_budget": cpu_limit,
        "cases_total": len(cases),
        "succeeded": len(succeeded),
        "failed": len([r for r in reports if r["status"] == STATUS_FAILED]),
        "timed_out": len([r for r in reports if r["status"] == STATUS_TIMEOUT]),
        "skipped": len([r for r in reports if r["status"] == STATUS_SKIPPED]),
        "gpu_seconds_total": round(
            sum(float(row["gpu_seconds"]) for row in reports), 3
        ),
        "cases": sorted(reports, key=lambda row: row["case_id"]),
        "telemetry": sampler_summary,
    }
    (output_dir / SUMMARY_REPORT).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if cancelled:
        raise SystemExit("batch cancelled")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    """Run one batch manifest and return the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Case manifest JSON path")
    parser.add_argument("--out", required=True, help="Batch output directory")
    parser.add_argument(
        "--devices",
        required=True,
        help="Comma-separated device slots available to this batch (host tokens)",
    )
    parser.add_argument(
        "--slots", type=int, default=1, help="Concurrent cases per device"
    )
    parser.add_argument("--cpu-budget", type=int, default=None, help="Thread budget")
    parser.add_argument(
        "--threads", type=int, default=1, help="Default threads per case"
    )
    parser.add_argument(
        "--timeout", type=float, default=None, help="Default case timeout"
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Skip the remaining cases after the first failure",
    )
    parser.add_argument(
        "--no-telemetry", action="store_true", help="Disable the batch host sampler"
    )
    parser.add_argument(
        "--no-case-telemetry",
        action="store_true",
        help="Do not request per-case runtime evidence sidecars",
    )
    parser.add_argument(
        "--share-worker",
        action="store_true",
        help=(
            "Run every case of the batch in one worker process so the fixed "
            "model load and warm-up cost is paid once (requires --slots 1)"
        ),
    )
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    stop_event = threading.Event()

    def _handle(signum, frame):  # pragma: no cover - signal path
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, _handle)
    summary = run_manifest(
        manifest,
        BatchOptions(
            devices=tuple(
                part.strip() for part in args.devices.split(",") if part.strip()
            ),
            output_dir=Path(args.out),
            slots_per_device=max(args.slots, 1),
            cpu_budget=args.cpu_budget,
            default_threads=max(args.threads, 1),
            default_timeout_s=args.timeout,
            continue_on_failure=not args.stop_on_failure,
            telemetry=not args.no_telemetry,
            case_telemetry=not args.no_case_telemetry,
            share_worker=args.share_worker,
            stop_event=stop_event,
        ),
    )
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "cases_total",
                    "succeeded",
                    "failed",
                    "timed_out",
                    "skipped",
                    "wall_s",
                )
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution entry
    raise SystemExit(main())
