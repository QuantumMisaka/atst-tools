"""Process-scope runtime counters for model builds and force evaluations.

Counters are opt-in (enabled by the runtime evidence session), thread-safe and
import-light.  They count *events in this process*: MPI image-parallel runs
report one set per rank, and ABACUS evaluations launch a subprocess that this
process cannot observe in detail, so ``*.calculate`` counts subprocess
invocations rather than inner SCF iterations.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

_LOCK = threading.Lock()
_ENABLED = False
_COUNTERS: dict[str, int] = {}
_GAUGES: dict[str, float] = {}

# Canonical keys: MPI aggregation sums exactly these counters (and the listed
# gauges) so the rank-0 evidence document can report job-level totals.
COUNTER_KEYS: tuple[str, ...] = (
    "abacus.calculator_built",
    "abacus.force_calls",
    "dp.calculator_built",
    "dp.calculator_reused",
    "dp.force_calls",
    "runtime_threads_overridden",
)
AGGREGATED_GAUGE_KEYS: tuple[str, ...] = ("dp.cached_instances",)


def set_enabled(enabled: bool) -> None:
    """Enable or disable counting for this process."""
    global _ENABLED
    with _LOCK:
        _ENABLED = bool(enabled)


def is_enabled() -> bool:
    """Return whether counting is enabled in this process."""
    with _LOCK:
        return _ENABLED


def increment(key: str, amount: int = 1) -> None:
    """Add ``amount`` to ``key`` (a no-op while counting is disabled)."""
    with _LOCK:
        if not _ENABLED:
            return
        _COUNTERS[key] = _COUNTERS.get(key, 0) + int(amount)


def snapshot() -> dict[str, int]:
    """Return a JSON-safe copy of the current counters."""
    with _LOCK:
        return dict(sorted(_COUNTERS.items()))


def set_gauge(key: str, value: float) -> None:
    """Record the latest value of one observable process quantity."""
    with _LOCK:
        _GAUGES[key] = float(value)


def gauge_snapshot() -> dict[str, float]:
    """Return a JSON-safe copy of the recorded gauges."""
    with _LOCK:
        return dict(sorted(_GAUGES.items()))


def reset() -> None:
    """Clear all counters (used by tests and fresh attempts)."""
    with _LOCK:
        _COUNTERS.clear()
        _GAUGES.clear()


def instrument_calculator(
    calculator: Any,
    *,
    build_key: str | None = None,
    call_key: str | None = None,
) -> Any:
    """Count one construction and later force evaluations of *calculator*.

    The calculator type is preserved: only an instance-level ``calculate``
    wrapper is attached, and any failure to attach it leaves the calculator
    untouched (measurement must never break a workflow).
    """
    if build_key:
        increment(build_key)
    if not is_enabled() or not call_key:
        return calculator
    calculate: Callable[..., Any] | None = getattr(calculator, "calculate", None)
    if calculate is None or not callable(calculate):
        return calculator

    def counted(*args: Any, **kwargs: Any) -> Any:
        increment(call_key)
        return calculate(*args, **kwargs)

    try:
        calculator.calculate = counted
    except Exception:
        return calculator
    return calculator
