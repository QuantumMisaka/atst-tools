"""Immutable models and errors for the stable Python API."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


def _json_detached(value: Any) -> Any:
    """Return a JSON-safe detached value for a stable process document."""
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise TypeError("ATST API document values must be JSON serializable") from exc


class ATSTAPIError(RuntimeError):
    """Base error for the stable ATST-Tools Python API.

    Args:
        message: Human-readable failure description.
        workflow: Workflow associated with the failure, when known.
        context: Machine-readable diagnostic details.
    """

    def __init__(
        self,
        message: str,
        *,
        workflow: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.workflow = workflow
        self.context = dict(context or {})

    def to_document(self) -> dict[str, Any]:
        """Return the stable bounded error payload used by process runners."""
        cause = self.__cause__
        return {
            "type": type(self).__name__,
            "message": str(self),
            "workflow": self.workflow,
            "context": _json_detached(self.context),
            "cause": (
                None
                if cause is None
                else {"type": type(cause).__name__, "message": str(cause)}
            ),
        }


class ConfigValidationError(ATSTAPIError):
    """Raised when a YAML path or mapping fails ATST schema validation."""


class UnsupportedDependencyError(ATSTAPIError):
    """Raised when an optional workflow dependency is unavailable at runtime."""


class MPIConfigurationError(ATSTAPIError):
    """Raised when image-parallel communicator topology is invalid."""


class WorkflowExecutionError(ATSTAPIError):
    """Raised when a workflow cannot complete through the public API."""


@dataclass(frozen=True)
class RunOptions:
    """Controls for configuration-driven workflow execution.

    Progress reporting is dual-entry: the CLI ``--progress`` flag and this
    API surface map to the same driver emission. When ``progress`` is true,
    one NDJSON line per event is written to ``progress_stream`` (standard
    output by default) and the same event mapping is forwarded to
    ``progress_callback``, so Python consumers never need to parse stdout.

    ``profiles`` and ``plots`` are result-envelope extensions (atst-api-result-v1):
    they are opt-in so that existing consumers keep byte-identical documents.
    When ``profiles`` is true the driver adds a per-image (NEB/AutoNEB) or
    per-step (Sella/CCQN) energy/force summary; when ``plots`` is true it
    renders the workflow energy plot PNG and records its relative path in the
    result document and artifact manifest.  Both only ever add optional fields
    and never alter the established result fields.
    """

    dry_run: bool = False
    restart: bool = False
    check_input: bool = False
    check_input_timeout: int = 120
    abacus_executable: str | None = None
    world: Any | None = None
    progress: bool = False
    progress_stream: Any | None = None
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None
    profiles: bool = False
    plots: bool = False


@dataclass(frozen=True)
class CCQNOptions:
    """Controls for embedded CCQN execution with a supplied calculator."""

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
    """Structured outcome returned by a stable API workflow call."""

    workflow: str
    status: str
    is_root: bool
    artifact_manifest: str
    artifacts: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]
    final_atoms: Any | None = None
    final_images: tuple[Any, ...] | None = None
    ts_atoms: Any | None = None
    plots: tuple[str, ...] = ()
    profiles: tuple[dict[str, Any], ...] = ()

    def to_document(self, workdir: str | Path) -> dict[str, Any]:
        """Return the stable JSON handoff envelope without ASE objects.

        The ``plots`` and ``profiles`` extensions are optional: they appear in
        the document only when non-empty, so documents produced without those
        options stay byte-identical to the original atst-api-result-v1 schema.
        """
        root = Path(workdir).resolve()
        manifest = Path(self.artifact_manifest)
        if not manifest.is_absolute():
            manifest = root / manifest
        document = {
            "schema": "atst-api-result-v1",
            "status": "success",
            "workflow": self.workflow,
            "is_root": self.is_root,
            "workdir": str(root),
            "artifact_manifest": str(manifest.resolve()),
            "artifacts": _json_detached(list(self.artifacts)),
            "metadata": _json_detached(self.metadata),
        }
        if self.plots:
            document["plots"] = list(self.plots)
        if self.profiles:
            document["profiles"] = _json_detached(list(self.profiles))
        return document
