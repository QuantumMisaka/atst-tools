"""Immutable models and errors for the stable Python API."""

from __future__ import annotations

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
    """Controls for configuration-driven workflow execution."""

    dry_run: bool = False
    restart: bool = False
    check_input: bool = False
    check_input_timeout: int = 120
    abacus_executable: str | None = None
    world: Any | None = None


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
