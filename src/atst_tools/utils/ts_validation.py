"""Transition-state validation summaries built from vibration results."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "atst-ts-validation-v1"


def build_ts_validation_summary(
    vibration_results: dict[str, Any],
    *,
    fmax: float | None = None,
    fmax_threshold: float = 0.05,
    imaginary_cutoff_cm1: float = 50.0,
    source: str | None = None,
) -> dict[str, Any]:
    """Classify whether vibration data is consistent with a first-order TS."""
    imaginary = vibration_results.get("imaginary_frequencies") or []
    imag_values = [abs(float(value)) for value in imaginary]
    significant = [value for value in imag_values if value >= float(imaginary_cutoff_cm1)]
    n_imag = len(significant)
    imag_ok = n_imag == 1
    if fmax is None:
        fmax_ok = None
    else:
        fmax_ok = float(fmax) <= float(fmax_threshold)
    status = "pass" if imag_ok and (fmax_ok is not False) else "fail"
    return {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "status": status,
        "checks": {
            "n_imaginary_modes": {
                "value": n_imag,
                "expected": 1,
                "imaginary_cutoff_cm1": imaginary_cutoff_cm1,
                "pass": imag_ok,
            },
            "fmax": {
                "value": fmax,
                "threshold": fmax_threshold,
                "pass": fmax_ok,
            },
        },
        "imaginary_frequencies": significant,
    }
