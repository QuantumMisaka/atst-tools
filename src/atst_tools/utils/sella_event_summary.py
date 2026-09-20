"""Read the optional Sella observability sidecar.

The Sella trajectory contains every ASE trajectory write, including finite
difference Hessian probes.  The sidecar is the only source used here to
classify a frame as an optimizer state or a Hessian probe.  In particular,
the reader never infers optimizer steps from the number of trajectory frames.

This module intentionally performs a small amount of validation at the
consumer boundary.  It is not a second event schema implementation: the
producer owns event semantics, while this reader protects summaries from
claiming a complete run for a malformed, truncated, or mismatched sidecar.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from string import hexdigits
from typing import Any


EVENT_SCHEMA_VERSION = "sella-events-v1"
EVENT_SUFFIX = ".events.jsonl"

_FRAME_EVENT_NAMES = {"initial_state", "optimizer_step", "hessian_evaluation"}
_KNOWN_EVENTS = {
    "run_start",
    "initial_state",
    "optimizer_step",
    "hessian_start",
    "hessian_evaluation",
    "hessian_done",
    "hessian_failed",
    "run_end",
    "run_failed",
}


def default_events_path(trajectory: str | Path) -> Path:
    """Return the event sidecar path paired with *trajectory*."""

    return Path(trajectory).with_suffix(EVENT_SUFFIX)


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _valid_optional_bool(record: dict[str, Any], field: str) -> bool:
    value = record.get(field)
    return field not in record or value is None or isinstance(value, bool)


def _schema(record: dict[str, Any]) -> str | None:
    value = record.get("schema_version")
    return value if isinstance(value, str) else None


def _event_name(record: dict[str, Any]) -> str | None:
    value = record.get("event")
    return value if isinstance(value, str) else None


def _base_result(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "schema_version": None,
        "status": "missing",
        "complete": False,
        "diagnostics": [],
        "events": [],
        "n_events": 0,
        "frame_map": {},
        "capabilities": {},
        "actual_steps": None,
        "converged": None,
        "trajectory_frames": None,
        "trajectory_sha256": None,
        "step_count_verified": False,
    }


def _add_mapping(
    result: dict[str, Any],
    record: dict[str, Any],
    *,
    n_frames: int | None,
    optimizer_steps: dict[int, int],
) -> bool:
    event_name = _event_name(record)
    frame_index = record.get("frame_index")
    if frame_index is None:
        # A missing frame ID is a capability limitation, not a frame at index
        # zero.  Keep the event available in the raw event list, but do not
        # manufacture a mapping.
        result["diagnostics"].append(
            f"{event_name} event has no frame_index; it was not mapped to the trajectory"
        )
        return False
    frame_index = _nonnegative_int(frame_index)
    if frame_index is None:
        result["diagnostics"].append(
            f"{event_name} event has an invalid frame_index; it was not mapped"
        )
        return True
    if n_frames is not None and frame_index >= n_frames:
        result["diagnostics"].append(
            f"{event_name} frame_index {frame_index} is outside the trajectory ({n_frames} frame(s))"
        )
        return True

    if event_name == "initial_state":
        frame_kind = "optimizer_state"
        payload = {
            "frame_kind": frame_kind,
            "optimizer_step": 0,
            "converged": record.get("converged"),
        }
    elif event_name == "optimizer_step":
        frame_kind = "optimizer_state"
        optimizer_step = _nonnegative_int(record.get("optimizer_step"))
        if optimizer_step is None:
            result["diagnostics"].append(
                "optimizer_step event has an invalid optimizer_step; it was not mapped"
            )
            return True
        prior_frame = optimizer_steps.get(optimizer_step)
        if prior_frame is not None and prior_frame != frame_index:
            result["diagnostics"].append(
                f"optimizer_step {optimizer_step} maps to both frame {prior_frame} and frame {frame_index}"
            )
            return True
        optimizer_steps[optimizer_step] = frame_index
        payload = {
            "frame_kind": frame_kind,
            "optimizer_step": optimizer_step,
            "converged": record.get("converged"),
        }
    else:
        frame_kind = "hessian_probe"
        payload = {
            "frame_kind": frame_kind,
            "optimizer_step": _nonnegative_int(record.get("optimizer_step")),
            "converged": None,
            "cycle": _nonnegative_int(record.get("cycle")),
        }

    existing = result["frame_map"].get(frame_index)
    if existing is not None:
        if existing == payload:
            result["diagnostics"].append(
                f"duplicate frame mapping for frame {frame_index}; kept one copy"
            )
            return True
        else:
            result["diagnostics"].append(
                f"conflicting frame mapping for frame {frame_index}; kept no mapping"
            )
            result["frame_map"].pop(frame_index, None)
            return True
    result["frame_map"][frame_index] = payload
    return False


def read_sella_events(
    trajectory: str | Path,
    *,
    events_file: str | Path | None = None,
    n_frames: int | None = None,
) -> dict[str, Any]:
    """Read and minimally validate a Sella event sidecar.

    A valid prefix is retained when a later JSONL record is malformed, so a
    caller may inspect known local events.  ``complete`` is false in that
    case, and no partial frame mapping is attached to the trajectory.
    A trajectory hash, when present, is checked before any frame mapping is
    exposed; this prevents a sidecar from a previous run being applied to a
    newly written trajectory.
    """

    trajectory_path = Path(trajectory)
    path = Path(events_file) if events_file is not None else default_events_path(trajectory_path)
    result = _base_result(path)
    if not path.exists():
        result["diagnostics"].append("Sella event sidecar is missing")
        return result

    optimizer_steps: dict[int, int] = {}
    run_end: dict[str, Any] | None = None
    run_failed = False
    parse_failed = False
    schema_error = False
    mapping_error = False
    structure_error = False
    hash_missing = False
    run_start_count = 0
    run_end_count = 0
    seen_event_names: list[str] = []
    missing_run_end = False
    optimizer_events: list[dict[str, Any]] = []
    initial_events: list[dict[str, Any]] = []
    checkpoint_field_error = False

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        result["status"] = "invalid"
        result["diagnostics"].append(f"unable to read event sidecar: {exc}")
        return result

    if not lines:
        result["status"] = "invalid"
        result["diagnostics"].append("Sella event sidecar is empty")
        return result

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            result["diagnostics"].append(f"blank event line {line_number}")
            parse_failed = True
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            result["diagnostics"].append(f"invalid JSON on event line {line_number}: {exc.msg}")
            parse_failed = True
            continue
        if not isinstance(record, dict):
            result["diagnostics"].append(f"event line {line_number} is not a JSON object")
            schema_error = True
            continue

        schema_version = _schema(record)
        if schema_version != EVENT_SCHEMA_VERSION:
            result["diagnostics"].append(
                f"unsupported event schema on line {line_number}: {schema_version!r}"
            )
            schema_error = True
        elif result["schema_version"] is None:
            result["schema_version"] = schema_version
        elif result["schema_version"] != schema_version:
            result["diagnostics"].append(
                f"event schema changed on line {line_number}: {schema_version!r}"
            )
            schema_error = True

        event_name = _event_name(record)
        if event_name not in _KNOWN_EVENTS:
            result["diagnostics"].append(
                f"unsupported Sella event on line {line_number}: {event_name!r}"
            )
            schema_error = True
            continue

        if not seen_event_names and event_name != "run_start":
            result["diagnostics"].append("event sidecar must start with run_start")
            structure_error = True
        if event_name == "run_start":
            run_start_count += 1
            if run_start_count > 1:
                result["diagnostics"].append("event sidecar contains multiple run_start records")
                structure_error = True
        if event_name == "run_end":
            run_end_count += 1
            if run_end_count > 1:
                result["diagnostics"].append("event sidecar contains multiple run_end records")
                structure_error = True
        if run_end_count and event_name != "run_end":
            result["diagnostics"].append("event records appear after run_end")
            structure_error = True
        seen_event_names.append(event_name)
        result["events"].append(record)
        if event_name == "run_start":
            capabilities = record.get("capabilities")
            if isinstance(capabilities, dict):
                result["capabilities"] = dict(capabilities)
        elif event_name in _FRAME_EVENT_NAMES:
            if event_name in {"initial_state", "optimizer_step"}:
                if not _valid_optional_bool(record, "converged"):
                    result["diagnostics"].append(
                        f"{event_name} has a non-boolean converged value"
                    )
                    checkpoint_field_error = True
                elif "converged" not in record:
                    result["diagnostics"].append(
                        f"{event_name} is missing its converged field"
                    )
                    checkpoint_field_error = True
            mapping_error = (
                _add_mapping(
                    result,
                    record,
                    n_frames=n_frames,
                    optimizer_steps=optimizer_steps,
                )
                or mapping_error
            )
            if event_name == "optimizer_step":
                optimizer_events.append(record)
            elif event_name == "initial_state":
                initial_events.append(record)
        elif event_name == "run_end":
            run_end = record
        elif event_name == "run_failed":
            run_failed = True

    if run_end is not None:
        actual_steps = _nonnegative_int(run_end.get("actual_steps"))
        trajectory_frames = _nonnegative_int(run_end.get("trajectory_frames"))
        converged = run_end.get("converged")
        if actual_steps is None:
            result["diagnostics"].append("run_end has an invalid actual_steps value")
            schema_error = True
        else:
            result["actual_steps"] = actual_steps
        if trajectory_frames is None:
            result["diagnostics"].append("run_end has an invalid trajectory_frames value")
            schema_error = True
        else:
            result["trajectory_frames"] = trajectory_frames
            if n_frames is not None and trajectory_frames != n_frames:
                result["diagnostics"].append(
                    f"run_end reports {trajectory_frames} frame(s), but trajectory has {n_frames}"
                )
                mapping_error = True
        if not _valid_optional_bool(run_end, "converged"):
            result["diagnostics"].append("run_end has no trusted boolean/null converged value")
            schema_error = True
        else:
            result["converged"] = converged
        trajectory_sha256 = run_end.get("trajectory_sha256")
        if (
            not isinstance(trajectory_sha256, str)
            or len(trajectory_sha256) != 64
            or any(character not in hexdigits for character in trajectory_sha256)
        ):
            result["diagnostics"].append("run_end has no usable trajectory_sha256")
            hash_missing = True
        else:
            result["trajectory_sha256"] = trajectory_sha256
            try:
                observed_hash = hashlib.sha256(trajectory_path.read_bytes()).hexdigest()
            except OSError as exc:
                result["diagnostics"].append(f"unable to hash trajectory: {exc}")
                mapping_error = True
            else:
                if observed_hash.lower() != trajectory_sha256.lower():
                    result["diagnostics"].append(
                        "event sidecar trajectory_sha256 does not match the trajectory"
                    )
                    mapping_error = True
    else:
        result["diagnostics"].append("event sidecar has no run_end record")
        missing_run_end = True

    checkpoints = result["capabilities"].get("optimizer_checkpoints")
    step_count_verified = False
    checkpoint_error = False
    if run_end is not None and isinstance(result["actual_steps"], int):
        if checkpoints is True:
            actual_steps = result["actual_steps"]
            initial = initial_events[0] if len(initial_events) == 1 else None
            if len(initial_events) != 1:
                result["diagnostics"].append(
                    "optimizer checkpoints require exactly one initial_state record"
                )
                checkpoint_error = True
            elif (
                _nonnegative_int(initial.get("optimizer_step")) != 0
                or "converged" not in initial
                or (
                    initial.get("converged") is not None
                    and not isinstance(initial.get("converged"), bool)
                )
            ):
                result["diagnostics"].append(
                    "initial_state is missing optimizer_step=0 or a boolean/null converged value"
                )
                checkpoint_error = True

            observed_steps = [
                _nonnegative_int(record.get("optimizer_step"))
                for record in optimizer_events
            ]
            sequence_ok = len(observed_steps) == actual_steps and all(
                step == expected for expected, step in enumerate(observed_steps, start=1)
            )
            if not sequence_ok:
                result["diagnostics"].append(
                    "optimizer_step checkpoints do not cover the run_end actual_steps sequence"
                )
                checkpoint_error = True
            else:
                terminal_converged = (
                    optimizer_events[-1].get("converged")
                    if optimizer_events
                    else initial.get("converged") if initial is not None else None
                )
                if terminal_converged != result["converged"]:
                    result["diagnostics"].append(
                        "terminal optimizer_step converged disagrees with run_end"
                    )
                    checkpoint_error = True
                step_count_verified = not checkpoint_error
        else:
            result["diagnostics"].append(
                "optimizer checkpoint capability is unavailable; actual_steps is run_end-only"
            )

    if not result["events"]:
        result["status"] = "invalid"
    elif run_failed:
        result["status"] = "failed"
    elif (
        parse_failed
        or schema_error
        or structure_error
        or mapping_error
        or checkpoint_error
        or checkpoint_field_error
    ):
        result["status"] = (
            "partial_unverified"
            if parse_failed and not schema_error and not structure_error and not mapping_error
            else "invalid"
        )
    elif hash_missing:
        result["status"] = "partial_unverified"
    elif missing_run_end:
        result["status"] = "partial_unverified"
    else:
        result["status"] = "complete"

    result["complete"] = result["status"] == "complete"
    result["n_events"] = len(result["events"])
    result["step_count_verified"] = step_count_verified
    if not result["complete"]:
        # A run-end from a mismatched or malformed stream is not a fact about
        # this trajectory.  Raw local events and diagnostics remain available
        # above, but no partial mapping is attached to this trajectory.
        result["actual_steps"] = None
        result["converged"] = None
        # A frame ID is meaningful only after a closed event stream has
        # verified the trajectory hash.  Preserve raw records and diagnostics
        # above, but never attach a partial stream to this trajectory.
        result["frame_map"] = {}
    return result


__all__ = ["EVENT_SCHEMA_VERSION", "EVENT_SUFFIX", "default_events_path", "read_sella_events"]
