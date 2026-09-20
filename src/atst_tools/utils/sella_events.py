"""Durable, low-overhead event records for a Sella run.

The event sidecar deliberately records optimizer checkpoints separately from
trajectory frames.  A numerical Hessian can write several frames while the
optimizer's ``nsteps`` counter is unchanged, so consumers must use the
``optimizer_step`` field for iteration counts.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "sella-events-v1"


def event_path_for_trajectory(trajectory: str | Path) -> Path:
    """Return the fixed sidecar path for a trajectory output."""

    return Path(trajectory).with_suffix(".events.jsonl")


def trajectory_sha256(path: str | Path) -> str | None:
    """Hash an existing trajectory without opening it through ASE."""

    file_path = Path(path)
    if not file_path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    """Convert the small set of scalar types emitted by ASE/Sella."""

    item = getattr(value, "item", None)
    if callable(item):
        return item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class SellaEventRecorder:
    """Best-effort JSONL writer for one Sella run.

    Event I/O is advisory telemetry.  A filesystem failure disables further
    telemetry after one warning and never changes the optimizer result or
    masks an exception raised by the calculation itself.
    """

    def __init__(self, path: str | Path, *, enabled: bool = True):
        self.path = Path(path)
        self.enabled = bool(enabled)
        self._stream = None
        self._warned = False
        self._hessian_cycle = 0
        if self.enabled:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._stream = self.path.open("w", encoding="utf-8")
            except OSError as exc:
                self._disable_io(exc)
        else:
            # A disabled run rewrites the trajectory in the caller.  Removing
            # its derived sidecar prevents an older event stream being paired
            # with the new trajectory.  Failure to remove it is reported but
            # does not block the calculation.
            try:
                self.path.unlink(missing_ok=True)
            except OSError as exc:
                self._disable_io(exc)

    @property
    def available(self) -> bool:
        """Whether events can currently be written."""

        return self._stream is not None

    def _disable_io(self, exc: OSError) -> None:
        if not self._warned:
            warnings.warn(
                f"Sella event telemetry disabled for {self.path}: {exc}",
                RuntimeWarning,
                stacklevel=3,
            )
            self._warned = True
        self.enabled = False
        if self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                pass
        self._stream = None

    def emit(self, event: str, **fields: Any) -> None:
        """Append and flush one schema-versioned event."""

        if self._stream is None:
            return
        record = {"schema_version": SCHEMA, "event": event, **fields}
        try:
            self._stream.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=_json_default,
                )
                + "\n"
            )
            self._stream.flush()
        except (OSError, TypeError, ValueError) as exc:
            self._disable_io(exc if isinstance(exc, OSError) else OSError(str(exc)))

    def run_start(self, *, trajectory: str | Path, capabilities: Mapping[str, bool]) -> None:
        self.emit(
            "run_start",
            trajectory=str(trajectory),
            capabilities=dict(capabilities),
        )

    def state(
        self,
        event: str,
        *,
        optimizer_step: int,
        frame_index: int | None,
        converged: bool | None,
    ) -> None:
        self.emit(
            event,
            optimizer_step=int(optimizer_step),
            frame_index=frame_index,
            converged=converged,
        )

    def hessian(self, event: str, *, optimizer_step: int, evaluations: int, frame_index: int | None = None) -> None:
        if event == "start":
            self._hessian_cycle += 1
            event_name = "hessian_start"
        elif event == "evaluation":
            event_name = "hessian_evaluation"
        elif event == "done":
            event_name = "hessian_done"
        elif event == "failed":
            event_name = "hessian_failed"
        else:
            return
        fields: dict[str, Any] = {
            "cycle": self._hessian_cycle or 1,
            "optimizer_step": int(optimizer_step),
            "evaluations": int(evaluations),
        }
        if event == "evaluation":
            fields["frame_index"] = frame_index
        self.emit(event_name, **fields)

    def run_end(
        self,
        *,
        actual_steps: int,
        converged: bool | None,
        trajectory_digest: str | None,
        trajectory_frames: int | None,
    ) -> None:
        self.emit(
            "run_end",
            actual_steps=int(actual_steps),
            converged=converged,
            trajectory_sha256=trajectory_digest,
            trajectory_frames=trajectory_frames,
        )

    def run_failed(
        self,
        *,
        actual_steps: int,
        converged: bool | None,
        error: BaseException,
    ) -> None:
        self.emit(
            "run_failed",
            actual_steps=int(actual_steps),
            converged=converged,
            error_type=type(error).__name__,
            error=str(error),
        )

    def close(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.flush()
            self._stream.close()
        except OSError as exc:
            self._disable_io(exc)
        finally:
            self._stream = None
