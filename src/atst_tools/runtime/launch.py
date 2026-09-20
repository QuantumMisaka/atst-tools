"""Runtime request merging, child-environment construction and worker launch."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
import sys

from atst_tools.runtime import devices as _devices
from atst_tools.runtime import counters as _counters
from atst_tools.runtime.errors import RuntimeBindingError

CACHE_ENV_KEYS = (
    "JAX_COMPILATION_CACHE_DIR",
    "NUMBA_CACHE_DIR",
    "MPLCONFIGDIR",
)
THREAD_ENV_KEYS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
LOG_LEVEL_ENV = "ATST_LOG_LEVEL"
ATTEMPT_ENV = "ATST_ATTEMPT"
THREADS_SOURCE_ENV = "ATST_THREADS_SOURCE"
TELEMETRY_ENV = "ATST_TELEMETRY_ENABLED"
TELEMETRY_INTERVAL_ENV = "ATST_TELEMETRY_INTERVAL_S"
WORKER_MODULE = "atst_tools.api.runner"

EMBEDDED_REFUSAL = (
    "embedding API cannot rebind devices; run the workflow through 'atst run' "
    "or 'python -m atst_tools.api.runner' instead"
)


@dataclass(frozen=True)
class RuntimeRequest:
    """The merged runtime request of one entry point."""

    devices: tuple[_devices.DeviceToken, ...] | None
    devices_source: str | None
    binding: str
    threads: int | None
    threads_source: str | None
    telemetry_enabled: bool
    telemetry_interval_s: float
    requested: bool

    @property
    def rebinds(self) -> bool:
        """Return whether the request asks for process-level rebinding."""
        return (
            self.devices is not None
            or self.threads is not None
            or self.binding == "round_robin"
        )


def _devices_from_section(section: Mapping[str, Any] | None) -> Any:
    if not section:
        return None
    return section.get("devices")


def _coerce_int(value: Any) -> Any:
    """Coerce a CLI string to ``int`` for the shared parsers."""
    if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        return int(value.strip())
    return value


def _coerce_float(value: Any) -> Any:
    """Coerce a CLI string to ``float`` for the shared parsers."""
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return value
    return value


def _positive_interval(value: Any) -> float:
    """Return a positive sampling interval or raise the frozen message."""
    try:
        interval = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "runtime.telemetry.interval_s must be a positive number"
        ) from exc
    if interval <= 0:
        raise ValueError("runtime.telemetry.interval_s must be a positive number")
    return interval


def cpu_affinity_count() -> int:
    """Return the CPU budget implied by the process affinity mask."""
    try:
        return max(len(os.sched_getaffinity(0)), 1)
    except AttributeError:  # pragma: no cover - non-Linux platforms
        return max(os.cpu_count() or 1, 1)


def apply_explicit_omp(value: Any, *, environ: Mapping[str, str] | None = None) -> int:
    """Write one explicit ``calculator.*.omp`` and record any runtime override.

    Only the explicit branch is handled here: calculators whose ``omp`` is
    absent keep their historical behaviour (the DP factory never wrote a
    default, the ABACUS factory writes 1 through
    :func:`resolve_calculator_omp`), and none of them clobber a runtime budget.
    """
    env = os.environ if environ is None else environ
    resolved = int(value)
    inherited = env.get("OMP_NUM_THREADS", "").strip()
    if inherited and inherited.lstrip("+-").isdigit() and int(inherited) != resolved:
        _counters.increment("runtime_threads_overridden")
        _counters.set_gauge("runtime_threads_effective", resolved)
        logging.getLogger(__name__).warning(
            "calculator omp=%s overrides the inherited OMP_NUM_THREADS=%s",
            resolved,
            inherited,
        )
    os.environ["OMP_NUM_THREADS"] = str(resolved)
    return resolved


def resolve_calculator_omp(
    explicit: Any, *, environ: Mapping[str, str] | None = None
) -> int:
    """Apply the frozen OMP precedence for one calculator construction.

    An explicit ``calculator.*.omp`` always wins; an inherited budget set by
    ``runtime.threads`` survives implicit defaults; without either the legacy
    default of 1 is written.
    """
    env = os.environ if environ is None else environ
    if explicit is not None:
        return apply_explicit_omp(explicit, environ=env)
    inherited = env.get("OMP_NUM_THREADS", "").strip()
    if inherited and env.get(THREADS_SOURCE_ENV):
        try:
            return int(inherited)
        except ValueError:
            pass
    os.environ["OMP_NUM_THREADS"] = "1"
    return 1


def _resolve_threads(value: Any) -> tuple[int | None, str | None]:
    """Resolve one thread request; ``auto`` follows the CPU affinity mask."""
    if value is None:
        return None, None
    if isinstance(value, str) and value.strip().lower() == "auto":
        return cpu_affinity_count(), "auto"
    return _devices.parse_threads(_coerce_int(value)), "explicit"


def merge_runtime_request(
    *,
    cli_devices: Any = None,
    cli_binding: Any = None,
    cli_threads: Any = None,
    cli_telemetry: bool | None = None,
    cli_interval: Any = None,
    yaml_section: Mapping[str, Any] | None = None,
    environ: Mapping[str, str],
) -> RuntimeRequest:
    """Merge CLI, YAML and environment runtime dimensions (frozen precedence)."""
    section = yaml_section if isinstance(yaml_section, Mapping) else None

    devices_value: Any = None
    source: str | None = None
    if cli_devices is not None:
        devices_value, source = cli_devices, "--devices"
    elif _devices_from_section(section) is not None:
        devices_value, source = _devices_from_section(section), "runtime.devices"
    elif environ.get(_devices.VISIBLE_DEVICES_ENV) is not None:
        devices_value = environ.get(_devices.VISIBLE_DEVICES_ENV)
        source = _devices.VISIBLE_DEVICES_ENV

    devices = (
        None if devices_value is None else _devices.parse_device_tokens(devices_value)
    )

    if cli_binding is not None:
        binding = _devices.parse_binding(cli_binding)
    elif section is not None and section.get("binding") is not None:
        binding = _devices.parse_binding(section.get("binding"))
    else:
        binding = "inherit"

    if cli_threads is not None:
        threads, threads_source = _resolve_threads(cli_threads)
    elif section is not None and section.get("threads") is not None:
        threads, threads_source = _resolve_threads(section.get("threads"))
    else:
        threads, threads_source = None, None

    telemetry_enabled = False
    telemetry_interval = 1.0
    if section is not None and "telemetry" in section:
        raw = section.get("telemetry")
        if isinstance(raw, bool):
            telemetry_enabled = raw
        elif isinstance(raw, Mapping):
            telemetry_enabled = bool(raw.get("enabled", False))
            if raw.get("interval_s") is not None:
                telemetry_interval = _positive_interval(raw["interval_s"])
        elif raw is not None:
            raise ValueError(
                "runtime.telemetry must be a boolean or a mapping with 'enabled'"
            )
    if cli_telemetry is not None:
        telemetry_enabled = cli_telemetry
    if cli_interval is not None:
        telemetry_interval = _positive_interval(_coerce_float(cli_interval))
    if telemetry_interval <= 0:
        raise ValueError("runtime.telemetry.interval_s must be a positive number")

    requested = bool(
        devices is not None
        or sections_request_runtime(section)
        or cli_devices is not None
        or cli_binding is not None
        or cli_threads is not None
        or cli_telemetry is not None
        or cli_interval is not None
        or environ.get(_devices.VISIBLE_DEVICES_ENV) is not None
    )
    return RuntimeRequest(
        devices=devices,
        devices_source=source,
        binding=binding,
        threads=threads,
        threads_source=threads_source,
        telemetry_enabled=telemetry_enabled,
        telemetry_interval_s=telemetry_interval,
        requested=requested,
    )


def sections_request_runtime(section: Mapping[str, Any] | None) -> bool:
    """Return whether a YAML ``runtime`` section is present at all."""
    return section is not None


def attempt_index(environ: Mapping[str, str]) -> int:
    """Return the current attempt index used for per-attempt cache isolation."""
    raw = environ.get(ATTEMPT_ENV, "1").strip()
    if raw.isdigit() and int(raw) >= 1:
        return int(raw)
    return 1


def child_cache_dir(workflow_dir: Path, attempt: int) -> Path:
    """Return the per-attempt writable cache directory for one worker."""
    return Path(workflow_dir) / ".atst_cache" / f"attempt-{attempt}"


def build_child_environment(
    request: RuntimeRequest,
    resolution: _devices.DeviceResolution,
    *,
    base: Mapping[str, str],
    workflow_dir: Path | None = None,
    attempt: int = 1,
    log_level: str | None = None,
) -> dict[str, str]:
    """Build the environment of the isolated worker (frozen contract)."""
    env = dict(base)
    if resolution.child_mask is not None:
        env[_devices.CUDA_VISIBLE_DEVICES] = resolution.child_mask
    if request.threads is not None:
        for key in THREAD_ENV_KEYS:
            env[key] = str(request.threads)
        env[THREADS_SOURCE_ENV] = request.threads_source or "explicit"
    if workflow_dir is not None:
        cache_dir = child_cache_dir(workflow_dir, attempt)
        cache_dir.mkdir(parents=True, exist_ok=True)
        for key in CACHE_ENV_KEYS:
            env[key] = str(cache_dir)
    env[_devices.RUNTIME_BOUND_ENV] = "1"
    env[_devices.INHERITED_DEVICES_ENV] = ",".join(resolution.inherited)
    env[_devices.EFFECTIVE_DEVICES_ENV] = ",".join(resolution.effective)
    if request.devices is not None:
        env[_devices.REQUESTED_DEVICES_ENV] = ",".join(
            token.raw for token in request.devices
        )
        env[_devices.REQUESTED_SOURCE_ENV] = request.devices_source or "runtime.devices"
    env[_devices.BINDING_ENV] = resolution.binding
    if log_level:
        env[LOG_LEVEL_ENV] = str(log_level)
    if request.telemetry_enabled:
        env[TELEMETRY_ENV] = "1"
        env[TELEMETRY_INTERVAL_ENV] = str(request.telemetry_interval_s)
    return env


def build_worker_command(
    config_path: str | Path,
    *,
    python: str | None = None,
    module: str = WORKER_MODULE,
    workdir: str | Path | None = None,
    dry_run: bool = False,
    restart: bool = False,
    abacus_executable: str | None = None,
    extra: Sequence[str] = (),
) -> list[str]:
    """Build the worker command that reuses the stable API runner protocol."""
    command = [python or sys.executable, "-m", module, "--config", str(config_path)]
    if workdir is not None:
        command += ["--workdir", str(workdir)]
    if dry_run:
        command.append("--dry-run")
    if restart:
        command.append("--restart")
    if abacus_executable:
        command += ["--abacus-executable", str(abacus_executable)]
    command += list(extra)
    return command


def exec_worker(command: Sequence[str], environ: Mapping[str, str]) -> None:
    """Replace the current coordinator process with the bound worker."""
    os.execvpe(command[0], list(command), dict(environ))


def ensure_runtime_contract(
    config: Mapping[str, Any],
    *,
    workflow: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Enforce the worker/embedded-API contract for one normalized config.

    Raises:
        RuntimeBindingError: The config requests rebinding while the process is
            not the bound worker, or the bound facts do not match.
    """
    env = os.environ if environ is None else environ
    section = config.get("runtime")
    bound = env.get(_devices.RUNTIME_BOUND_ENV) == "1"
    if not isinstance(section, Mapping):
        if not bound:
            return
        # A bound worker still verifies against the coordinator's recorded
        # request and binding, so CLI-driven launches get the same check.
        requested_fact = env.get(_devices.REQUESTED_DEVICES_ENV)
        tokens = (
            None
            if requested_fact is None or not requested_fact.strip()
            else _devices.parse_device_tokens(requested_fact)
        )
        _devices.verify_bound_devices(
            tokens,
            environ=env,
            binding=_devices.parse_binding(env.get(_devices.BINDING_ENV)),
        )
        return
    # The coordinator records the *merged* request (CLI wins over YAML); the
    # worker must verify against that, not against the raw YAML alone.
    requested_fact = env.get(_devices.REQUESTED_DEVICES_ENV)
    if requested_fact is not None and requested_fact.strip():
        devices_value = requested_fact
    else:
        devices_value = section.get("devices")
    tokens = (
        None
        if devices_value is None
        else _devices.parse_device_tokens(devices_value)
    )
    section_binding = section.get("binding")
    binding = _devices.parse_binding(
        section_binding if section_binding is not None else env.get(_devices.BINDING_ENV)
    )
    threads = _devices.parse_threads(section.get("threads"))
    rebinds = tokens is not None or threads is not None or binding == "round_robin"
    if not rebinds and not bound:
        return
    if not bound:
        raise RuntimeBindingError(EMBEDDED_REFUSAL, workflow=workflow)
    _devices.verify_bound_devices(tokens, environ=env, binding=binding)
