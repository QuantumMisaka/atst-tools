"""Finite-case batch harness for the GPU node tuning work (P3).

The harness runs a bounded case list inside one existing allocation:

* every case runs as an isolated worker process in its own output directory;
* device slots and the CPU thread budget are both respected (a case's rank
  multiplier from its launcher, or its declared ``ranks``, counts towards the
  thread budget);
* failures, timeouts, OOM signals and skips stay in the report instead of
  disappearing from the denominator;
* retries never happen implicitly - a new attempt is a new manifest row;
* one batch-level host sampler covers the whole batch; per-case evidence
  sidecars (and their own samplers) are opt-in through ``case_telemetry``.

Usage::

    python -m atst_tools.bench.harness --manifest cases.json --out runs/batch \\
        --devices 0,1 --slots 1 --cpu-budget 16
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Mapping, Sequence

from atst_tools.runtime import devices as _devices
from atst_tools.runtime import evidence as _evidence
from atst_tools.runtime import launch as _launch

SCHEMA = "atst-bench-harness-v1"
CASE_REPORT = "harness_case.json"
SUMMARY_REPORT = "harness_summary.json"
DEFAULT_RESULT_JSON = "atst_api_result.json"
TERMINATION_GRACE_S = 5.0

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
class HarnessOptions:
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
    worker_factory: Callable[["CaseSpec", Path, tuple[str, ...]], Sequence[str]] | None = None
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


def load_cases(manifest: Mapping[str, Any], options: HarnessOptions) -> list[CaseSpec]:
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
        merged.setdefault("timeout_s", defaults.get("timeout_s", options.default_timeout_s))
        case = CaseSpec.from_mapping(merged)
        if case.case_id in seen:
            raise ValueError(f"duplicate case_id {case.case_id!r}")
        seen.add(case.case_id)
        cases.append(case)
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
    image-parallel cases keep the harness slot, timeout and reporting
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
        return candidate.resolve() if candidate.is_absolute() else (output_dir / candidate)
    return Path(case.config).resolve().parent


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


def _terminate_group(process: subprocess.Popen, grace: float = TERMINATION_GRACE_S) -> None:
    """Terminate one worker group within a bounded grace window."""
    if process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        process.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:  # pragma: no cover - defensive
        pass


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


def run_manifest(
    manifest: Mapping[str, Any], options: HarnessOptions
) -> dict[str, Any]:
    """Run every manifest case with slot/CPU limits and return the summary."""
    cases = load_cases(manifest, options)
    output_dir = Path(options.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pool = _SlotPool(options.devices, options.slots_per_device)
    cpu_limit = options.cpu_limit()
    sampler = (
        _evidence.HostSampler(options.sampler_interval_s)
        if options.telemetry
        else None
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
                        case, devices, base=os.environ, attempt=1, workdir=workdir
                    )
                    stdout_path = report_dir / "harness_worker.out"
                    stderr_path = report_dir / "harness_worker.err"
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
                if timeout is not None and (
                    time.monotonic() - item.started_monotonic
                ) > timeout:
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
    summary = {
        "schema": SCHEMA,
        "status": "cancelled" if cancelled else "complete",
        "revision": _evidence.atst_revision(),
        "started_at": batch_started_at,
        "finished_at": _now(),
        "wall_s": round(time.monotonic() - batch_started, 3),
        "devices": list(options.devices),
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
    parser.add_argument("--slots", type=int, default=1, help="Concurrent cases per device")
    parser.add_argument("--cpu-budget", type=int, default=None, help="Thread budget")
    parser.add_argument("--threads", type=int, default=1, help="Default threads per case")
    parser.add_argument("--timeout", type=float, default=None, help="Default case timeout")
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
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    stop_event = threading.Event()

    def _handle(signum, frame):  # pragma: no cover - signal path
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, _handle)
    summary = run_manifest(
        manifest,
        HarnessOptions(
            devices=tuple(part.strip() for part in args.devices.split(",") if part.strip()),
            output_dir=Path(args.out),
            slots_per_device=max(args.slots, 1),
            cpu_budget=args.cpu_budget,
            default_threads=max(args.threads, 1),
            default_timeout_s=args.timeout,
            continue_on_failure=not args.stop_on_failure,
            telemetry=not args.no_telemetry,
            case_telemetry=not args.no_case_telemetry,
            stop_event=stop_event,
        ),
    )
    print(json.dumps({key: summary[key] for key in (
        "cases_total", "succeeded", "failed", "timed_out", "skipped", "wall_s"
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution entry
    raise SystemExit(main())
