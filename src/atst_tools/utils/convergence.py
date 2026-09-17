"""Shared convergence stage records and English advisories for ATST workflows.

The module is intentionally dependency-light: it records the execution status of
one workflow stage together with the optimizer-owned convergence facts, and it
prints a single neutral English advisory when an optimizer explicitly reported
``converged=False``.  It imports only the standard library, ``numpy`` and
``atst_tools.utils.mpi`` so it never pulls in calculators, ASE ``Atoms``
objects, trajectories, or any code path that could start a calculation.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Any, Mapping

import numpy as np

from atst_tools.utils.mpi import run_rank_zero_section

__all__ = [
    "EXECUTION_STATUSES",
    "StageRecord",
    "as_step_count",
    "emit_unconverged_advisory",
]


#: Allowed execution statuses for one workflow stage.
EXECUTION_STATUSES = ("complete", "skipped", "failed")

#: Dataclass fields that are written to the manifest only when they carry a value.
_OPTIONAL_MANIFEST_KEYS = (
    "role",
    "criterion",
    "direction",
    "iteration",
    "fmax",
    "fmax_unit",
    "steps",
    "actual_steps",
    "measured",
    "measured_unit",
)

_OPTIONAL_TEXT_FIELDS = ("role", "criterion", "direction", "fmax_unit", "measured_unit")


def _normalized_converged(value: Any) -> bool | None:
    """Coerce an optimizer-owned convergence signal into a strict tri-state.

    Only a Python ``bool`` or a ``numpy.bool_`` scalar is trusted.  Every other
    value, including placeholders such as ``0``, ``"false"`` or an optimizer
    object, is reported as unknown (``None``) instead of being truthiness
    converted into a scientific claim.

    Args:
        value: Raw convergence signal returned by an optimizer.

    Returns:
        ``True``, ``False``, or ``None`` when the signal is unusable.
    """
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return None


def _finite_float(field_name: str, value: Any) -> float:
    """Return ``value`` as a finite ``float`` or raise.

    Args:
        field_name: Human-readable field label used in error messages.
        value: Candidate numeric value.

    Returns:
        The value as a plain ``float``, which is always JSON encodable.

    Raises:
        TypeError: The value is not a real number.
        ValueError: The value is not finite (``nan`` or ``inf``).
    """
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a finite number, got {value!r}.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite, got {value!r}.")
    return number


def _optional_finite_float(field_name: str, value: Any) -> float | None:
    """Validate an optional numeric field.

    Args:
        field_name: Human-readable field label used in error messages.
        value: Candidate value, or ``None`` when the field is unset.

    Returns:
        ``None`` for an unset field, otherwise a finite ``float``.

    Raises:
        TypeError: The value is not a real number.
        ValueError: The value is not finite (``nan`` or ``inf``).
    """
    if value is None:
        return None
    return _finite_float(field_name, value)


def _optional_count(field_name: str, value: Any) -> int | None:
    """Return ``None`` or a validated non-negative integer count.

    ``bool`` is rejected even though it is an ``int`` subclass, because a
    flag passed where a step count belongs is a caller bug.

    Args:
        field_name: Human-readable field label used in error messages.
        value: Candidate count, or ``None`` when the field is unset.

    Returns:
        ``None`` for an unset field, otherwise a non-negative ``int``.

    Raises:
        TypeError: The value is not an integer or ``None``.
        ValueError: The value is negative.
    """
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise TypeError(
            f"{field_name} must be a non-negative integer or None, got {value!r}."
        )
    number = int(value)
    if number < 0:
        raise ValueError(f"{field_name} must be non-negative, got {number}.")
    return number


def _normalized_measured(value: Any) -> dict[str, float] | None:
    """Return ``None`` or a validated copy of a measured-quantity mapping.

    The copy keeps the frozen record independent of later mutations by the
    caller and guarantees that the stored mapping is JSON encodable.

    Args:
        value: Candidate mapping of measured quantities, or ``None``.

    Returns:
        ``None`` for an unset field, otherwise a new ``str`` to ``float`` dict.

    Raises:
        TypeError: The value is not a mapping, a key is not a string, or a
            value is not a real number.
        ValueError: A measured value is not finite.
    """
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(
            "StageRecord.measured must be a mapping of finite numbers or None, "
            f"got {value!r}."
        )
    measured: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"StageRecord.measured keys must be strings, got {key!r}.")
        measured[key] = _finite_float(f"StageRecord.measured[{key!r}]", item)
    return measured


def as_step_count(value: Any) -> int | None:
    """Return a non-negative step count for an optimizer-owned value, else ``None``.

    Optimizer objects from third-party packages may expose ``nsteps`` as a
    plain integer, a NumPy integer, or an integral float.  Diagnostics must
    never corrupt a completed workflow, so any unusable value degrades to
    ``None`` (unknown) instead of raising.  Explicit :class:`StageRecord`
    fields keep their strict validation.

    Args:
        value: Candidate step count, typically ``getattr(optimizer, "nsteps", None)``.

    Returns:
        ``None`` when the value is unusable or negative, otherwise the count as
        a plain ``int``.
    """
    if isinstance(value, (bool, np.bool_)) or value is None:
        return None
    if isinstance(value, Integral):
        count = int(value)
        return count if count >= 0 else None
    if isinstance(value, Real):
        number = float(value)
        if math.isfinite(number) and number.is_integer() and number >= 0:
            return int(number)
    return None


@dataclass(frozen=True)
class StageRecord:
    """One workflow stage's execution status and optimizer-owned convergence facts.

    The record separates observation from inference: ``status`` states whether
    the stage ran to completion, while ``converged`` carries only the signal the
    optimizer itself reported.  ``None`` means unknown (a placeholder or a
    signal the optimizer did not provide) and is never treated as either
    converged or unconverged.

    Attributes:
        name: Stage identity; must be a non-empty string.
        status: Execution status, one of :data:`EXECUTION_STATUSES`.
        converged: Optimizer-owned termination signal; ``None`` means unknown.
        role: Stage role, for example ``"warmup"``, ``"final"``,
            ``"refinement"`` or ``"endpoint"``.
        criterion: Optimizer-owned criterion identity.
        direction: IRC direction (``"forward"`` or ``"backward"``).
        iteration: AutoNEB iteration/subset identity.
        fmax: Configured force threshold value.
        fmax_unit: Unit of ``fmax``.
        steps: Configured step budget for this stage.
        actual_steps: Observed steps for this stage.
        measured: Optional measured quantities; every value must be finite.
        measured_unit: Unit shared by the ``measured`` values.

    Raises:
        TypeError: A field received a value of the wrong type.
        ValueError: A field received an unusable value, such as an unknown
            status, an empty name, a non-finite number or a negative count.
    """

    name: str
    status: str = "complete"
    converged: bool | None = None
    role: str | None = None
    criterion: str | None = None
    direction: str | None = None
    iteration: int | None = None
    fmax: float | None = None
    fmax_unit: str | None = "eV/Angstrom"
    steps: int | None = None
    actual_steps: int | None = None
    measured: Mapping[str, float] | None = None
    measured_unit: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalize every field at construction time.

        Raises:
            TypeError: A field received a value of the wrong type.
            ValueError: A field received an unusable value.
        """
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                f"StageRecord.name must be a non-empty string, got {self.name!r}."
            )
        if self.status not in EXECUTION_STATUSES:
            raise ValueError(
                "StageRecord.status must be one of "
                f"{EXECUTION_STATUSES}, got {self.status!r}."
            )
        for field_name in _OPTIONAL_TEXT_FIELDS:
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(
                    f"StageRecord.{field_name} must be a string or None, "
                    f"got {value!r}."
                )
        object.__setattr__(self, "converged", _normalized_converged(self.converged))
        object.__setattr__(
            self, "iteration", _optional_count("StageRecord.iteration", self.iteration)
        )
        object.__setattr__(
            self, "fmax", _optional_finite_float("StageRecord.fmax", self.fmax)
        )
        object.__setattr__(
            self, "steps", _optional_count("StageRecord.steps", self.steps)
        )
        object.__setattr__(
            self,
            "actual_steps",
            _optional_count("StageRecord.actual_steps", self.actual_steps),
        )
        object.__setattr__(self, "measured", _normalized_measured(self.measured))

    def to_manifest(self) -> dict[str, Any]:
        """Return a JSON-safe stage dict for artifact manifests.

        ``name``, ``status`` and ``converged`` are always present; ``converged``
        may be ``None`` and is then encoded as JSON ``null``.  Every other key is
        emitted only when the record carries a value for it.

        Returns:
            A dict that survives a ``json.dumps`` round trip.
        """
        manifest: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "converged": self.converged,
        }
        for key in _OPTIONAL_MANIFEST_KEYS:
            value = getattr(self, key)
            if value is None:
                continue
            if key == "fmax_unit" and self.fmax is None:
                # A unit without a threshold is misleading in durable records.
                continue
            manifest[key] = dict(value) if key == "measured" else value
        return manifest


def _advisory_message(record: StageRecord, workflow: str) -> str:
    """Build the stable English advisory text for one unconverged stage.

    Optional tokens are omitted, never printed as ``None``, so the message stays
    truthful when a stage has no configured threshold or step budget.

    Args:
        record: Stage record carrying the tokens' values.
        workflow: Workflow label; upper-cased for the leading sentence.

    Returns:
        The three-line advisory message, without a trailing newline.
    """
    tokens = [f"workflow={workflow}", f"stage={record.name}"]
    if record.fmax is not None:
        threshold = f"threshold_fmax={record.fmax}"
        if record.fmax_unit is not None:
            threshold = f"{threshold} {record.fmax_unit}"
        tokens.append(threshold)
    if record.actual_steps is not None:
        tokens.append(f"nsteps={record.actual_steps}")
    if record.steps is not None:
        tokens.append(f"max_steps={record.steps}")
    if record.direction is not None:
        tokens.append(f"direction={record.direction}")
    if record.iteration is not None:
        tokens.append(f"iteration={record.iteration}")
    return (
        f"Warning: {workflow.upper()} finished without satisfying its "
        "optimizer convergence criteria\n"
        f"({', '.join(tokens)}).\n"
        "Execution completion does not imply optimizer convergence."
    )


def emit_unconverged_advisory(
    record: StageRecord,
    *,
    workflow: str,
    world: Any | None = None,
    stream: Any | None = None,
) -> bool:
    """Print one English advisory when an optimizer reported ``converged=False``.

    The advisory is purely diagnostic: it states observed facts (workflow, stage,
    configured threshold, observed and budgeted steps) and never infers a
    scientific cause or changes a return value, a workflow status or a manifest.
    A ``converged`` of ``True`` or ``None`` stays silent, and no other code path
    ever calls the optimizer to re-derive convergence.

    Args:
        record: Stage record holding the optimizer-owned convergence facts.
        workflow: Workflow label used in the message and in the ``workflow=``
            token; must be a non-empty string.
        world: Existing ASE/MPI communicator.  When it has more than one rank the
            message is printed by rank 0 only, through
            :func:`atst_tools.utils.mpi.run_rank_zero_section`.  ``None`` or a
            single-rank world prints directly on this process.
        stream: Output stream, defaulting to ``sys.stdout``.

    Returns:
        ``True`` when the record carries ``converged is False``, otherwise
        ``False``.  The value is identical on every rank so callers never branch
        on rank-local state; only the printed message is root-only.

    Raises:
        ValueError: ``workflow`` is not a non-empty string.
    """
    if not isinstance(workflow, str) or not workflow.strip():
        raise ValueError(f"workflow must be a non-empty string, got {workflow!r}.")
    if record.converged is not False:
        return False
    output = sys.stdout if stream is None else stream
    message = _advisory_message(record, workflow)

    def emit() -> None:
        print(message, file=output)

    if world is not None and int(world.size) > 1:
        run_rank_zero_section(
            world,
            emit,
            context="convergence advisory warning",
        )
    else:
        emit()
    return True
