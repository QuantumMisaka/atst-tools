"""Numerical helpers for constant-potential scans and diagnostics.

The helpers in this module deliberately contain no ASE or backend code.  They
operate on the facts produced by the constant-potential calculator so that
scan fitting remains reproducible and can also be used by API consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


E_PER_V_ANGSTROM2_TO_UF_PER_CM2 = 1602.176634


class ElectrochemistryError(ValueError):
    """Raised when a scan cannot support the requested electrochemical fit."""


def _finite(value: Any, name: str) -> float:
    """Return a finite scalar or raise a descriptive error."""
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ElectrochemistryError(f"{name} must be a finite number") from exc
    if not np.isfinite(result):
        raise ElectrochemistryError(f"{name} must be a finite number")
    return result


def chebyshev_derivative(
    electrons: Sequence[float],
    mu_values: Sequence[float],
    electron: float,
    *,
    difference: float = 1.0e-4,
) -> dict[str, float | int]:
    """Fit the reference Newton curve and estimate its local derivative.

    This follows the pinned FCP-v2 fitting rules: a linear Chebyshev fit is
    available after two samples; the degree is raised to two or three only for
    the exact sample-count and residual-sum-of-squares conditions used by the
    reference implementation.  The derivative is the forward finite
    difference on the fitted curve and therefore does not trigger another
    backend evaluation.
    """
    x = np.asarray([_finite(item, "electron sample") for item in electrons], dtype=float)
    y = np.asarray([_finite(item, "chemical-potential sample") for item in mu_values], dtype=float)
    if x.size != y.size or x.size < 2:
        raise ElectrochemistryError("at least two electron/potential samples are required")
    if np.unique(x).size < 2:
        raise ElectrochemistryError("electron samples must contain two distinct values")

    def fit_at_degree(degree: int):
        try:
            fit_curve, diagnostics = np.polynomial.chebyshev.Chebyshev.fit(
                x, y, deg=degree, full=True
            )
        except (TypeError, ValueError, np.linalg.LinAlgError) as exc:
            raise ElectrochemistryError(
                f"Chebyshev degree-{degree} fit failed"
            ) from exc
        try:
            residuals = np.asarray(diagnostics[0], dtype=float)
            rank = int(diagnostics[1])
            coefficients = np.asarray(fit_curve.coef, dtype=float)
        except (IndexError, TypeError, ValueError) as exc:
            raise ElectrochemistryError(
                f"Chebyshev degree-{degree} fit diagnostics are malformed"
            ) from exc
        if rank < degree + 1:
            raise ElectrochemistryError(
                f"Chebyshev degree-{degree} fit is rank deficient ({rank} < {degree + 1})"
            )
        if not np.all(np.isfinite(coefficients)) or not np.all(np.isfinite(residuals)):
            raise ElectrochemistryError(
                f"Chebyshev degree-{degree} fit coefficients or residuals are not finite"
            )
        rss = float(residuals[0]) if residuals.size else 0.0
        if not np.isfinite(rss):
            raise ElectrochemistryError(
                f"Chebyshev degree-{degree} fit residual is not finite"
            )
        return fit_curve, rss, rank

    degree = 1
    fit_curve, rss, rank = fit_at_degree(degree)
    if x.size > 3 and rss > 0.1:
        degree = 2
        fit_curve, rss, rank = fit_at_degree(degree)
    if x.size > 4 and rss > 0.1:
        degree = 3
        fit_curve, rss, rank = fit_at_degree(degree)
    electron = _finite(electron, "electron")
    difference = _finite(difference, "finite-difference step")
    if difference <= 0:
        raise ElectrochemistryError("finite-difference step must be positive")
    derivative = float((fit_curve(electron + difference) - fit_curve(electron)) / difference)
    if not np.isfinite(derivative):
        raise ElectrochemistryError("fitted chemical-potential derivative is not finite")
    return {
        "derivative_eV_per_e": derivative,
        "fit_degree": degree,
        "fit_rss_eV2": rss,
    }


def surface_area(cell: Any, vacuum_axis: int = 2) -> float:
    """Return the lattice surface area perpendicular to ``vacuum_axis``."""
    vectors = np.asarray(cell, dtype=float)
    if vectors.shape != (3, 3):
        raise ElectrochemistryError("cell must be a 3x3 array")
    axis = int(vacuum_axis)
    if axis not in (0, 1, 2):
        raise ElectrochemistryError("vacuum_axis must be 0, 1, or 2")
    in_plane = [index for index in range(3) if index != axis]
    area = float(np.linalg.norm(np.cross(vectors[in_plane[0]], vectors[in_plane[1]])))
    if not np.isfinite(area) or area <= 0:
        raise ElectrochemistryError("cell surface area must be positive")
    return area


@dataclass(frozen=True)
class PotentialScanPoint:
    """Minimal immutable point accepted by :func:`analyze_potential_scan`."""

    potential_v: float
    electrons: float
    converged: bool = True


def analyze_potential_scan(
    points: Iterable[PotentialScanPoint | Mapping[str, Any]],
    *,
    reference_electrons: float,
    area_A2: float,
    interface_count: int = 1,
    coordinate: str = "potential_v",
) -> dict[str, Any]:
    """Fit a fixed-geometry charge response on a declared coordinate.

    The legacy ``potential_v`` coordinate uses ``Q=N0-N`` and therefore
    reports ``dQ/dU``.  The compensated gate boundary uses ``target_mu_ev``
    (or its aliases) and reports the positive response ``dN/dmu``; its
    zero-charge crossing is named ``zero_charge_mu_ev`` because this custom
    chemical-potential coordinate is not an experimentally calibrated PZC.
    A zero-charge crossing is emitted only when it is bracketed or sampled.
    The capacitance is a linear slope in the sampled interval and is withheld
    when the interval is not identifiable. ``interface_count`` documents
    whether the reported area is normalized to one or two interfaces.
    """
    if interface_count not in (1, 2):
        raise ElectrochemistryError("interface_count must be 1 or 2")
    n0 = _finite(reference_electrons, "reference_electrons")
    area = _finite(area_A2, "area_A2")
    if area <= 0:
        raise ElectrochemistryError("area_A2 must be positive")
    coordinate_aliases = {
        "potential_v": "potential_v",
        "target_mu_ev": "target_mu_ev",
        "mu_ev": "target_mu_ev",
        "chemical_potential": "target_mu_ev",
    }
    try:
        coordinate = coordinate_aliases[str(coordinate)]
    except KeyError as exc:
        raise ElectrochemistryError(
            "coordinate must be 'potential_v' or 'target_mu_ev'"
        ) from exc
    is_mu_coordinate = coordinate == "target_mu_ev"
    normalized: list[PotentialScanPoint] = []
    for point in points:
        if isinstance(point, PotentialScanPoint):
            candidate = point
        else:
            coordinate_key = "target_mu_ev" if is_mu_coordinate else "potential_v"
            candidate = PotentialScanPoint(
                potential_v=_finite(
                    point.get(coordinate_key, point.get("potential_v")),
                    coordinate_key,
                ),
                electrons=_finite(point.get("electrons", point.get("nelec")), "electrons"),
                converged=bool(point.get("converged", point.get("cp_converged", True))),
            )
        if candidate.converged:
            normalized.append(
                PotentialScanPoint(
                    _finite(candidate.potential_v, "potential_v"),
                    _finite(candidate.electrons, "electrons"),
                    True,
                )
            )
    normalized.sort(key=lambda item: item.potential_v)
    result: dict[str, Any] = {
        "point_count": len(normalized),
        "reference_electrons": n0,
        "area_A2": area,
        "interface_count": interface_count,
        "coordinate": coordinate,
        "coordinate_unit": "eV" if is_mu_coordinate else "V",
        "identifiable": False,
        "pzc_v": None,
        "zero_charge_mu_ev": None,
        "pzc_status": "insufficient_points",
        "capacitance": None,
        "capacitance_unit": (
            "e^2/(eV Angstrom^2)" if is_mu_coordinate else "e/(V Angstrom^2)"
        ),
        "capacitance_uF_cm2": None,
        "fit": None,
    }
    if len(normalized) < 2:
        return result
    potentials = np.asarray([item.potential_v for item in normalized], dtype=float)
    # For a voltage coordinate, the historical electrode-charge convention is
    # Q=N0-N.  In the compensated gate profile μ is the declared coordinate;
    # use N-N0 so a positive electronic response gives positive capacitance.
    charge = np.asarray(
        [item.electrons - n0 if is_mu_coordinate else n0 - item.electrons for item in normalized],
        dtype=float,
    )
    if np.allclose(charge, charge[0]):
        result["pzc_status"] = "zero-charge-crossing-unidentified"
        return result
    slope, intercept = np.polyfit(potentials, charge, deg=1)
    prediction = slope * potentials + intercept
    rss = float(np.sum((charge - prediction) ** 2))
    if not np.isfinite(slope) or not np.isfinite(intercept):
        result["pzc_status"] = "non-finite-fit"
        return result
    scaled_area = area * interface_count
    capacitance = slope / scaled_area
    result["capacitance"] = float(capacitance)
    result["capacitance_uF_cm2"] = float(capacitance * E_PER_V_ANGSTROM2_TO_UF_PER_CM2)
    result["fit"] = {
        ("slope_e2_per_ev" if is_mu_coordinate else "slope_e_per_v"): float(slope),
        "intercept_e": float(intercept),
        "rss_e2": rss,
        ("mu_min_ev" if is_mu_coordinate else "potential_min_v"): float(np.min(potentials)),
        ("mu_max_ev" if is_mu_coordinate else "potential_max_v"): float(np.max(potentials)),
    }
    signs = np.sign(charge)
    exact = np.flatnonzero(np.isclose(charge, 0.0))
    if exact.size:
        if is_mu_coordinate:
            result["zero_charge_mu_ev"] = float(potentials[exact[0]])
        else:
            result["pzc_v"] = float(potentials[exact[0]])
        result["pzc_status"] = "sampled"
        result["identifiable"] = True
    elif np.any(signs[:-1] * signs[1:] < 0):
        zero = float(-intercept / slope)
        if is_mu_coordinate:
            result["zero_charge_mu_ev"] = zero
        else:
            result["pzc_v"] = zero
        result["pzc_status"] = "interpolated"
        result["identifiable"] = True
    else:
        result["pzc_status"] = "zero-charge-crossing-not-bracketed"
    return result


__all__ = [
    "E_PER_V_ANGSTROM2_TO_UF_PER_CM2",
    "ElectrochemistryError",
    "PotentialScanPoint",
    "analyze_potential_scan",
    "chebyshev_derivative",
    "surface_area",
]
