"""Device-request parsing, precedence and admissibility resolution.

Semantics follow the frozen P0 interface design
(docs/superpowers/specs/2026-09-21-atst-runtime-interface-design.md, sections
2-4).  The module is import-light: no NumPy, no ASE, no CUDA initialisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import subprocess
from typing import Any, Callable, Mapping, Sequence

from atst_tools.runtime.errors import RuntimeBindingError, RuntimeConfigError

CUDA_VISIBLE_DEVICES = "CUDA_VISIBLE_DEVICES"
VISIBLE_DEVICES_ENV = "ATST_VISIBLE_DEVICES"
ALLOCATION_DEVICES_ENV = "ATST_ALLOCATION_DEVICES"
INHERITED_DEVICES_ENV = "ATST_INHERITED_DEVICES"
EFFECTIVE_DEVICES_ENV = "ATST_EFFECTIVE_DEVICES"
RUNTIME_BOUND_ENV = "ATST_RUNTIME_BOUND"

_UUID_PATTERN = re.compile(
    r"^GPU-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

DEVICES_TYPE_MESSAGE = "runtime.devices must be a device index, GPU UUID or a list of them"
DEVICES_ENTRY_MESSAGE = (
    "runtime.devices entry {token!r} is not a valid 0-based device index "
    "or full GPU UUID"
)
DEVICES_DUPLICATE_MESSAGE = "runtime.devices must not contain duplicate entries ({token})"
DEVICES_EMPTY_MESSAGE = (
    "runtime.devices must not be empty; omit the field to inherit all visible devices"
)
DEVICES_MIG_MESSAGE = (
    "runtime.devices does not support MIG device selection ({token!r}); "
    "pass a full physical GPU UUID instead"
)
THREADS_MESSAGE = "runtime.threads must be a positive integer"
BINDING_MESSAGE = "runtime.binding {mode!r} is not one of: inherit, round_robin"

REFUSED_PREFIX = "explicit device selection is refused"
REASON_NOT_CALLER_BOUND = (
    "the visible device set is not caller-bound and the trusted allocation is unknown"
)
REASON_OVEREXPOSED = (
    "the visible device set exceeds the trusted allocation and device identity "
    "is unverified"
)
REASON_OUTSIDE_INHERITED = "{token!r} is not part of the inherited visible set"
REASON_OUTSIDE_ALLOCATION = "{token!r} is not part of the trusted allocation"


@dataclass(frozen=True)
class DeviceToken:
    """One parsed device request entry."""

    raw: str
    ordinal: int | None = None
    uuid: str | None = None

    @property
    def is_uuid(self) -> bool:
        """Return whether the entry is a full physical GPU UUID."""
        return self.uuid is not None

    @property
    def key(self) -> tuple[str, object]:
        """Return the canonical identity used for duplicate detection."""
        return ("uuid", self.uuid) if self.is_uuid else ("ordinal", self.ordinal)


@dataclass(frozen=True)
class AllocationFacts:
    """Trusted allocation facts supplied by an outer harness or platform."""

    raw: str
    count: int
    tokens: tuple[str, ...] | None = None


@dataclass(frozen=True)
class DeviceResolution:
    """Resolved device facts for one workflow attempt."""

    requested: tuple[str, ...]
    inherited: tuple[str, ...]
    inherited_source: str
    effective: tuple[str, ...]
    child_mask: str | None
    allocation_identity: str
    binding: str
    caller_bound: bool
    notes: tuple[str, ...] = field(default=())


def _token_from_scalar(value: Any) -> DeviceToken:
    """Return one validated :class:`DeviceToken` or raise a frozen error."""
    if isinstance(value, bool):
        raise RuntimeConfigError(DEVICES_ENTRY_MESSAGE.format(token=value))
    if isinstance(value, int):
        if value < 0:
            raise RuntimeConfigError(DEVICES_ENTRY_MESSAGE.format(token=value))
        return DeviceToken(raw=str(value), ordinal=value)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("MIG-"):
            raise RuntimeConfigError(DEVICES_MIG_MESSAGE.format(token=text))
        if _UUID_PATTERN.match(text):
            return DeviceToken(raw=text, uuid=text)
        if text.isdigit():
            return DeviceToken(raw=text, ordinal=int(text))
        raise RuntimeConfigError(DEVICES_ENTRY_MESSAGE.format(token=text or value))
    raise RuntimeConfigError(DEVICES_ENTRY_MESSAGE.format(token=value))


def parse_device_tokens(value: Any) -> tuple[DeviceToken, ...]:
    """Parse a YAML/CLI/env device request value.

    Args:
        value: Scalar or list of 0-based logical indices or full GPU UUIDs.

    Returns:
        The parsed tokens in request order.

    Raises:
        RuntimeConfigError: The request is empty, duplicated or malformed.
    """
    if isinstance(value, (list, tuple)):
        items: list[Any] = list(value)
        if not items:
            raise RuntimeConfigError(DEVICES_EMPTY_MESSAGE)
    elif isinstance(value, str):
        text = value.strip()
        if text == "":
            raise RuntimeConfigError(DEVICES_EMPTY_MESSAGE)
        if "," in text:
            parts = [part.strip() for part in text.split(",")]
            if any(part == "" for part in parts):
                raise RuntimeConfigError(DEVICES_ENTRY_MESSAGE.format(token=text))
            items = list(parts)
        else:
            items = [text]
    elif isinstance(value, (int, float, bool)):
        items = [value]
    else:
        raise RuntimeConfigError(DEVICES_TYPE_MESSAGE)

    tokens: list[DeviceToken] = []
    seen: set[tuple[str, object]] = set()
    for item in items:
        token = _token_from_scalar(item)
        if token.key in seen:
            raise RuntimeConfigError(DEVICES_DUPLICATE_MESSAGE.format(token=token.raw))
        seen.add(token.key)
        tokens.append(token)
    return tuple(tokens)


def parse_visible_devices_env(value: str | None) -> tuple[DeviceToken, ...] | None:
    """Parse ``ATST_VISIBLE_DEVICES``; ``None`` means 'not requested'."""
    if value is None:
        return None
    return parse_device_tokens(value)


def parse_threads(value: Any) -> int | None:
    """Parse ``runtime.threads``; ``None`` means 'not requested'."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RuntimeConfigError(THREADS_MESSAGE)
    return int(value)


def parse_binding(value: Any) -> str:
    """Parse ``runtime.binding`` and reject unknown modes."""
    mode = "inherit" if value is None else str(value)
    if mode not in ("inherit", "round_robin"):
        raise RuntimeConfigError(BINDING_MESSAGE.format(mode=mode))
    return mode


def parse_allocation_value(value: str | None) -> AllocationFacts | None:
    """Parse ``ATST_ALLOCATION_DEVICES`` (host-namespace tokens or ``count=N``)."""
    if value is None:
        return None
    text = value.strip()
    if text == "":
        raise RuntimeConfigError("ATST_ALLOCATION_DEVICES must not be empty")
    if text.startswith("count="):
        number = text[len("count=") :].strip()
        if not number.isdigit() or int(number) < 1:
            raise RuntimeConfigError(
                "ATST_ALLOCATION_DEVICES count= must be a positive integer"
            )
        return AllocationFacts(raw=text, count=int(number))
    tokens: list[str] = []
    for part in text.split(","):
        item = part.strip()
        if not item:
            continue
        if item.startswith("MIG-") or (
            not item.isdigit() and not _UUID_PATTERN.match(item)
        ):
            raise RuntimeConfigError(
                f"ATST_ALLOCATION_DEVICES entry {item!r} is not a device index or "
                "full GPU UUID"
            )
        tokens.append(item)
    if not tokens:
        raise RuntimeConfigError("ATST_ALLOCATION_DEVICES must not be empty")
    deduplicated = tuple(dict.fromkeys(tokens))
    return AllocationFacts(raw=text, count=len(deduplicated), tokens=deduplicated)


def enumerate_visible_devices(timeout: float = 5.0) -> tuple[str, ...] | None:
    """Return visible GPU UUIDs in index order through a short-lived query.

    The helper never initialises CUDA; it returns ``None`` when the identity of
    the visible devices cannot be established.
    """
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    tokens = tuple(
        line.strip() for line in completed.stdout.splitlines() if line.strip()
    )
    return tokens or None


def mpi_world_facts(environ: Mapping[str, str]) -> tuple[int, int | None]:
    """Return ``(world_size, local_rank)`` from the launcher environment."""
    size = 1
    for key in ("OMPI_COMM_WORLD_SIZE", "PMI_SIZE", "PMIX_SIZE", "SLURM_NTASKS"):
        value = environ.get(key)
        if value is not None and value.strip().isdigit():
            size = int(value.strip())
            break
    local_rank: int | None = None
    for key in (
        "OMPI_COMM_WORLD_LOCAL_RANK",
        "SLURM_LOCALID",
        "PMIX_LOCAL_RANK",
        "MPI_LOCALRANKID",
    ):
        value = environ.get(key)
        if value is not None and value.strip().isdigit():
            local_rank = int(value.strip())
            break
    return size, local_rank


def declared_node_count(environ: Mapping[str, str]) -> int:
    """Return the node count declared by the launcher environment (default 1)."""
    for key in ("SLURM_JOB_NUM_NODES", "SLURM_NNODES", "ATST_NODES"):
        value = environ.get(key)
        if value is not None and value.strip().isdigit():
            return max(int(value.strip()), 1)
    return 1


def _apply_round_robin(
    resolution: DeviceResolution, environ: Mapping[str, str]
) -> DeviceResolution:
    """Fail-closed ``round_robin`` mapping for a verified single-node pool."""
    size, local_rank = mpi_world_facts(environ)
    if size <= 1:
        raise RuntimeBindingError(
            "runtime.binding 'round_robin' requires an MPI world with more than one rank"
        )
    nodes = declared_node_count(environ)
    if nodes > 1:
        raise RuntimeBindingError(
            "runtime.binding 'round_robin' requires a verified single-node device "
            f"pool; the launcher declares {nodes} nodes"
        )
    if local_rank is None:
        raise RuntimeBindingError(
            "runtime.binding 'round_robin' requires a detectable local rank"
        )
    pool = resolution.effective
    if not resolution.caller_bound or not pool:
        raise RuntimeBindingError(
            "runtime.binding 'round_robin' requires a caller-bound single-node device pool"
        )
    chosen = pool[local_rank % len(pool)]
    return DeviceResolution(
        requested=resolution.requested,
        inherited=resolution.inherited,
        inherited_source=resolution.inherited_source,
        effective=(chosen,),
        child_mask=chosen,
        allocation_identity=resolution.allocation_identity,
        binding=resolution.binding,
        caller_bound=resolution.caller_bound,
        notes=resolution.notes + ("round_robin_rank_device",),
    )


def _entry_outside_inherited(
    token: DeviceToken, inherited: Sequence[str]
) -> RuntimeBindingError:
    """Return the frozen refusal for one entry outside the inherited set."""
    if token.is_uuid:
        message = f"{REFUSED_PREFIX}: {REASON_OUTSIDE_INHERITED.format(token=token.raw)}"
    else:
        message = (
            f"device index {token.ordinal} is outside the inherited visible set "
            f"(size {len(inherited)})"
        )
    return RuntimeBindingError(message, context={"requested": token.raw})


def _resolve_against_inherited(
    token: DeviceToken, inherited: Sequence[str]
) -> str | None:
    """Map one request entry to its inherited host token, or ``None``."""
    if token.is_uuid:
        for entry in inherited:
            if entry == token.uuid:
                return entry
        return None
    assert token.ordinal is not None
    if 0 <= token.ordinal < len(inherited):
        return inherited[token.ordinal]
    return None


def resolve_devices(
    requested: Sequence[DeviceToken] | None,
    *,
    binding: str = "inherit",
    environ: Mapping[str, str],
    enumerate_devices: Callable[[], Sequence[str] | None] | None = None,
) -> DeviceResolution:
    """Resolve one runtime request against the inherited and allocation facts.

    Args:
        requested: Parsed request, or ``None`` to inherit the caller's devices.
        binding: ``inherit`` or ``round_robin``.
        environ: Environment mapping holding the CUDA and ATST facts.
        enumerate_devices: Optional identity helper (see
            :func:`enumerate_visible_devices`); only called when the inherited
            set is not caller-bound.

    Returns:
        The resolved facts, including the child mask to apply (``None`` keeps
        the caller's environment untouched).

    Raises:
        RuntimeConfigError: The request or facts are malformed.
        RuntimeBindingError: The request is not admissible (frozen section 4).
    """
    mode = parse_binding(binding)
    cuda_raw = environ.get(CUDA_VISIBLE_DEVICES)
    allocation = parse_allocation_value(environ.get(ALLOCATION_DEVICES_ENV))

    if cuda_raw is None:
        inherited_source = "all"
        caller_bound = False
        enumerated = tuple(enumerate_devices() or ()) if enumerate_devices else ()
        inherited: tuple[str, ...] = enumerated
    else:
        inherited_source = "env"
        text = cuda_raw.strip()
        caller_bound = text != ""
        inherited = tuple(part.strip() for part in text.split(",") if part.strip())

    if requested is None:
        identity = (
            "verified"
            if allocation is not None and allocation.tokens is not None
            else "unknown"
        )
        if inherited_source == "env" and not caller_bound:
            identity = "unverified"
        inherit_resolution = DeviceResolution(
            requested=(),
            inherited=inherited,
            inherited_source=inherited_source,
            effective=inherited,
            child_mask=None,
            allocation_identity=identity,
            binding=mode,
            caller_bound=caller_bound,
        )
        if mode == "round_robin":
            return _apply_round_robin(inherit_resolution, environ)
        return inherit_resolution

    requested_raw = tuple(token.raw for token in requested)
    notes: list[str] = []

    if allocation is not None and allocation.tokens is not None:
        trusted = set(allocation.tokens)
        resolved: list[str] = []
        for token in requested:
            host = _resolve_against_inherited(token, inherited)
            if host is None:
                raise _entry_outside_inherited(token, inherited)
            if host not in trusted:
                raise RuntimeBindingError(
                    f"{REFUSED_PREFIX}: {REASON_OUTSIDE_ALLOCATION.format(token=token.raw)}",
                    context={"requested": token.raw, "allocation": allocation.raw},
                )
            resolved.append(host)
        identity = "verified"
    elif allocation is not None:
        if not caller_bound or allocation.count < len(inherited):
            raise RuntimeBindingError(
                f"{REFUSED_PREFIX}: {REASON_OVEREXPOSED}",
                context={
                    "requested": ",".join(requested_raw),
                    "allocation": allocation.raw,
                },
            )
        resolved = []
        for token in requested:
            host = _resolve_against_inherited(token, inherited)
            if host is None:
                raise _entry_outside_inherited(token, inherited)
            resolved.append(host)
        identity = "unverified"
        notes.append("allocation_count_covers_visible_set")
    else:
        if not caller_bound:
            raise RuntimeBindingError(
                f"{REFUSED_PREFIX}: {REASON_NOT_CALLER_BOUND}",
                context={"requested": ",".join(requested_raw)},
            )
        resolved = []
        for token in requested:
            host = _resolve_against_inherited(token, inherited)
            if host is None:
                raise _entry_outside_inherited(token, inherited)
            resolved.append(host)
        identity = "unverified"

    resolution = DeviceResolution(
        requested=requested_raw,
        inherited=inherited,
        inherited_source=inherited_source,
        effective=tuple(resolved),
        child_mask=",".join(resolved),
        allocation_identity=identity,
        binding=mode,
        caller_bound=caller_bound,
        notes=tuple(notes),
    )
    if mode == "round_robin":
        return _apply_round_robin(resolution, environ)
    return resolution


def verify_bound_devices(
    requested: Sequence[DeviceToken] | None,
    *,
    environ: Mapping[str, str],
) -> None:
    """Verify an already-bound worker against its recorded facts.

    The worker resolves the request against the *pre-binding* inherited set
    (``ATST_INHERITED_DEVICES``) and compares the result with
    ``ATST_EFFECTIVE_DEVICES`` and the actual child mask.  A mismatch raises
    :class:`RuntimeBindingError`; the function never rebinds.
    """
    basis = environ.get(INHERITED_DEVICES_ENV)
    if basis is None:
        raise RuntimeBindingError(
            "the runtime binding facts are missing; run the workflow through "
            "'atst run' or 'python -m atst_tools.api.runner' instead",
            context={"missing": INHERITED_DEVICES_ENV},
        )
    basis_tokens = tuple(part.strip() for part in basis.split(",") if part.strip())
    expected = environ.get(EFFECTIVE_DEVICES_ENV, "")
    expected_tokens = tuple(part.strip() for part in expected.split(",") if part.strip())
    actual = environ.get(CUDA_VISIBLE_DEVICES)
    actual_tokens = (
        None
        if actual is None
        else tuple(part.strip() for part in actual.split(",") if part.strip())
    )

    if requested is None:
        resolved = basis_tokens
    else:
        resolved_list: list[str] = []
        for token in requested:
            host = _resolve_against_inherited(token, basis_tokens)
            if host is None:
                raise _entry_outside_inherited(token, basis_tokens)
            resolved_list.append(host)
        resolved = tuple(resolved_list)

    if resolved != expected_tokens:
        raise RuntimeBindingError(
            "the worker environment does not match the resolved device request",
            context={
                "resolved": ",".join(resolved),
                "recorded_effective": ",".join(expected_tokens),
            },
        )
    if actual_tokens is not None and actual_tokens != expected_tokens:
        raise RuntimeBindingError(
            "the worker CUDA_VISIBLE_DEVICES does not match the recorded effective set",
            context={
                "actual": ",".join(actual_tokens),
                "recorded_effective": ",".join(expected_tokens),
            },
        )
