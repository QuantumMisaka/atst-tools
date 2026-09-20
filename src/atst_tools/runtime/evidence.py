"""Opt-in runtime evidence sidecar: environment identity, device facts, sampling.

The sidecar is written next to the workflow artifact manifest and referenced
from its metadata.  Sampling is opt-in (``runtime.telemetry`` or the
``ATST_TELEMETRY_ENABLED`` fact) and owned by one sampler per job: only the
local rank-0 process starts it, every other rank stays passive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
from typing import Any, Mapping, Sequence

from atst_tools.runtime import devices as _devices
from atst_tools.runtime import counters as _counters
from atst_tools.runtime import launch as _launch

EVIDENCE_FILENAME = "runtime_evidence.json"
EVIDENCE_MANIFEST_KEY = "runtime_evidence"
EVIDENCE_SCHEMA = "atst-runtime-evidence-v1"

STATUS_DISABLED = "disabled"
STATUS_UNAVAILABLE = "unavailable"
STATUS_PARTIAL = "partial"
STATUS_OBSERVED = "observed"

_PACKAGE_NAMES = ("numpy", "ase", "pydantic", "mpi4py", "deepmd-kit", "abacuslite")
_MAX_SAMPLES = 20000


def _now() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""
    return datetime.now(timezone.utc).isoformat()


def _dist_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except Exception:
        return None


def _number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def environment_facts(environ: Mapping[str, str]) -> dict[str, Any]:
    """Collect the interpreter, package and thread identity of this worker."""
    try:
        import atst_tools

        package_path = str(Path(atst_tools.__file__).resolve())
    except Exception:  # pragma: no cover - defensive
        package_path = None
    threads = {
        key: environ.get(key)
        for key in _launch.THREAD_ENV_KEYS
        if environ.get(key) is not None
    }
    return {
        "interpreter": sys.executable,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "atst_tools_path": package_path,
        "atst_tools_version": _dist_version("atst-tools"),
        "packages": {name: _dist_version(name) for name in _PACKAGE_NAMES},
        "threads": threads,
        "threads_source": environ.get(_launch.THREADS_SOURCE_ENV),
        "cpu_affinity_count": _launch.cpu_affinity_count(),
        "mpi": {
            "world_size": _devices.mpi_world_facts(environ)[0],
            "local_rank": _devices.mpi_world_facts(environ)[1],
        },
    }


def device_facts(
    config_runtime: Mapping[str, Any] | None, environ: Mapping[str, str]
) -> dict[str, Any]:
    """Describe the device request and the facts recorded by the coordinator."""
    section = config_runtime if isinstance(config_runtime, Mapping) else {}
    requested_fact = environ.get(_devices.REQUESTED_DEVICES_ENV)
    if requested_fact is not None and requested_fact.strip():
        requested_tokens = [
            part.strip() for part in requested_fact.split(",") if part.strip()
        ]
        requested_source = (
            environ.get(_devices.REQUESTED_SOURCE_ENV) or "runtime.devices"
        )
    elif section.get("devices") is not None:
        requested_value = section.get("devices")
        requested_tokens = [
            token.raw for token in _devices.parse_device_tokens(requested_value)
        ]
        requested_source = "runtime.devices"
    else:
        requested_tokens = []
        requested_source = None
    threads = section.get("threads")
    if threads is None:
        raw_threads = environ.get("OMP_NUM_THREADS", "").strip()
        if raw_threads.isdigit():
            threads = int(raw_threads)
    return {
        "bound": environ.get(_devices.RUNTIME_BOUND_ENV) == "1",
        "requested": requested_tokens,
        "requested_source": requested_source,
        "inherited": _split(environ.get(_devices.INHERITED_DEVICES_ENV)),
        "effective": _split(environ.get(_devices.EFFECTIVE_DEVICES_ENV)),
        "caller_bound": environ.get(_devices.CUDA_VISIBLE_DEVICES) is not None,
        "allocation_identity": (
            "verified"
            if environ.get(_devices.ALLOCATION_DEVICES_ENV)
            else "unverified"
        ),
        "binding": section.get("binding", "inherit"),
        "threads": threads,
    }


def _split(value: str | None) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def sample_gpus(timeout: float = 5.0) -> dict[str, Any]:
    """Take one host-scope GPU sample through a short-lived ``nvidia-smi`` query."""
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=uuid,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": f"nvidia-smi could not be executed ({type(exc).__name__})",
            "source": "nvidia-smi",
            "devices": [],
        }
    if completed.returncode != 0:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": f"nvidia-smi exited with status {completed.returncode}",
            "source": "nvidia-smi",
            "devices": [],
        }
    devices: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 4:
            continue
        devices.append(
            {
                "uuid": parts[0],
                "utilization_gpu_pct": _number(parts[1]),
                "memory_used_mib": _number(parts[2]),
                "memory_total_mib": _number(parts[3]),
            }
        )
    if not devices:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "nvidia-smi reported no GPU rows",
            "source": "nvidia-smi",
            "devices": [],
        }
    return {
        "status": STATUS_OBSERVED,
        "reason": None,
        "source": "nvidia-smi",
        "sampled_at": _now(),
        "devices": devices,
    }


def sample_compute_processes(timeout: float = 5.0) -> dict[str, Any]:
    """Take one host-scope compute-process sample (PID, memory, device UUID).

    Attribution stays conservative: the rows are what the host reports now.
    MPS, container PID namespaces and permissions can block or distort this
    view, so consumers must treat the result as reported evidence rather than
    as an authoritative ownership map.
    """
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_memory,gpu_uuid",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": f"nvidia-smi could not be executed ({type(exc).__name__})",
            "source": "nvidia-smi",
            "processes": [],
        }
    if completed.returncode != 0:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": f"nvidia-smi exited with status {completed.returncode}",
            "source": "nvidia-smi",
            "processes": [],
        }
    processes: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        processes.append(
            {
                "pid": int(parts[0]) if parts[0].isdigit() else None,
                "used_memory_mib": _number(parts[1]),
                "gpu_uuid": parts[2],
                "attribution": "reported",
            }
        )
    return {
        "status": STATUS_OBSERVED if processes else STATUS_UNAVAILABLE,
        "reason": None if processes else "no compute process was reported",
        "source": "nvidia-smi",
        "processes": processes,
    }


@dataclass
class EvidenceSession:
    """One workflow attempt's runtime evidence, written at most once."""

    workflow_dir: Path
    workflow: str
    attempt: int
    environ: Mapping[str, str]
    config_runtime: Mapping[str, Any] | None
    telemetry_enabled: bool
    telemetry_interval_s: float
    sampler: "HostSampler | None" = None
    written_path: Path | None = None
    started_at: str = field(default_factory=_now)
    started_monotonic: float = field(default_factory=lambda: __import__("time").monotonic())

    @property
    def path(self) -> Path:
        """Return the sidecar path next to the workflow artifact manifest."""
        return self.workflow_dir / EVIDENCE_FILENAME

    def start(self) -> None:
        """Start the single host sampler when telemetry is enabled."""
        if self.telemetry_enabled and self.sampler is None:
            self.sampler = HostSampler(self.telemetry_interval_s)
            self.sampler.start()

    def finish(self, status: str, reason: str | None = None) -> str | None:
        """Stop sampling, write the sidecar once and return its relative path."""
        if self.written_path is not None:
            return self.written_path.name
        summary = self.sampler.stop() if self.sampler is not None else {
            "status": STATUS_DISABLED,
            "reason": "telemetry is disabled",
            "source": None,
            "sample_count": 0,
            "coverage_s": 0.0,
            "samples": [],
        }
        payload = {
            "schema": EVIDENCE_SCHEMA,
            "status": status,
            "reason": reason,
            "workflow": self.workflow,
            "attempt": self.attempt,
            "started_at": self.started_at,
            "finished_at": _now(),
            "environment": environment_facts(self.environ),
            "devices": device_facts(self.config_runtime, self.environ),
            "counters": _counters.snapshot(),
            "counters_scope": "process",
            "gauges": _counters.gauge_snapshot(),
            "telemetry": {
                "enabled": self.telemetry_enabled,
                "interval_s": self.telemetry_interval_s,
                "sampler": summary,
            },
            "limitations": [
                "GPU samples are host-scope values; they are not exclusive to "
                "this workflow when devices are shared.",
                "Sampled memory peaks may miss short peaks; missing values are "
                "reported as null, never zero.",
            ],
        }
        try:
            _write_json_atomic(self.path, payload)
        except Exception:
            # Measurement must never mask the scientific result.
            return None
        self.written_path = self.path
        return self.path.name


class HostSampler:
    """One background host sampler with a bounded sample buffer."""

    def __init__(self, interval_s: float) -> None:
        self.interval_s = max(float(interval_s), 0.1)
        self._samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_status = STATUS_DISABLED
        self._reason: str | None = None
        self._source: str | None = None
        self._started = __import__("time").monotonic()

    def start(self) -> None:
        def _loop() -> None:
            while not self._stop.is_set():
                sample = sample_gpus()
                processes = sample_compute_processes()
                sample["processes"] = processes
                self._last_status = sample["status"]
                self._reason = sample.get("reason")
                self._source = sample.get("source")
                if sample["status"] == STATUS_OBSERVED:
                    if len(self._samples) < _MAX_SAMPLES:
                        self._samples.append(sample)
                elif self._samples:
                    # Keep observing after a transient failure without losing
                    # the samples already collected.
                    pass
                self._stop.wait(self.interval_s)

        self._thread = threading.Thread(target=_loop, name="atst-gpu-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.interval_s, 5.0))
        coverage = __import__("time").monotonic() - self._started
        return {
            "status": self._last_status,
            "reason": self._reason,
            "source": self._source,
            "sample_count": len(self._samples),
            "coverage_s": round(coverage, 3),
            "samples": self._samples,
        }


def evidence_requested(
    config_runtime: Mapping[str, Any] | None, environ: Mapping[str, str]
) -> bool:
    """Return whether any runtime dimension asked for an evidence sidecar."""
    return bool(
        isinstance(config_runtime, Mapping)
        or environ.get(_devices.RUNTIME_BOUND_ENV) == "1"
        or environ.get(_devices.VISIBLE_DEVICES_ENV) is not None
        or environ.get(_launch.TELEMETRY_ENV) == "1"
    )


def telemetry_settings(
    config_runtime: Mapping[str, Any] | None, environ: Mapping[str, str]
) -> tuple[bool, float]:
    """Resolve the telemetry switch and interval from config and environment."""
    enabled = environ.get(_launch.TELEMETRY_ENV) == "1"
    interval = 1.0
    if isinstance(config_runtime, Mapping):
        raw = config_runtime.get("telemetry")
        if isinstance(raw, bool):
            enabled = enabled or raw
        elif isinstance(raw, Mapping):
            enabled = enabled or bool(raw.get("enabled", False))
            if raw.get("interval_s") is not None:
                interval = float(raw["interval_s"])
    if environ.get(_launch.TELEMETRY_INTERVAL_ENV):
        interval = float(environ[_launch.TELEMETRY_INTERVAL_ENV])
    return enabled, interval


def start_session(
    *,
    workflow_dir: Path,
    workflow: str,
    config_runtime: Mapping[str, Any] | None,
    environ: Mapping[str, str] | None = None,
    rank: int = 0,
) -> EvidenceSession | None:
    """Return a started evidence session, or ``None`` when it is not requested."""
    env = os.environ if environ is None else environ
    requested = evidence_requested(config_runtime, env)
    _counters.set_enabled(requested)
    if rank != 0 or not requested:
        return None
    enabled, interval = telemetry_settings(config_runtime, env)
    session = EvidenceSession(
        workflow_dir=Path(workflow_dir),
        workflow=workflow,
        attempt=_launch.attempt_index(env),
        environ=env,
        config_runtime=config_runtime,
        telemetry_enabled=enabled,
        telemetry_interval_s=interval,
    )
    session.start()
    return session


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    """Publish one JSON document atomically without leaving partial files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary_path = Path(handle.name)
    temporary_path.replace(path)
