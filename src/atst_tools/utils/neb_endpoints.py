"""Endpoint result validation and preparation for NEB-family workflows."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from ase.calculators.singlepoint import SinglePointCalculator


ENDPOINT_RESULT_KEY = "atst_endpoint_result"
ENDPOINT_PLACEHOLDER = "placeholder"
ENDPOINT_PROVIDED = "provided"
ENDPOINT_COMPUTED = "computed"
ENDPOINT_OPTIMIZED = "optimized"


def mark_endpoint_result(atoms, status: str) -> None:
    """Mark how endpoint energy/force results were obtained."""
    atoms.info[ENDPOINT_RESULT_KEY] = status


def is_placeholder_endpoint(atoms) -> bool:
    """Return whether an endpoint carries ATST placeholder results."""
    return atoms.info.get(ENDPOINT_RESULT_KEY) == ENDPOINT_PLACEHOLDER


def get_endpoint_results(atoms) -> tuple[float, np.ndarray] | None:
    """Return endpoint energy and forces if both are readable."""
    if is_placeholder_endpoint(atoms):
        return None
    try:
        energy = float(atoms.get_potential_energy())
        forces = np.asarray(atoms.get_forces(), dtype=float)
    except Exception:
        return None
    if forces.shape != (len(atoms), 3):
        return None
    return energy, forces


def has_endpoint_results(atoms) -> bool:
    """Return whether an endpoint has usable non-placeholder results."""
    return get_endpoint_results(atoms) is not None


def freeze_current_results(atoms, status: str = ENDPOINT_COMPUTED):
    """Freeze current calculator results on an endpoint using SinglePointCalculator."""
    energy = float(atoms.get_potential_energy())
    forces = np.asarray(atoms.get_forces(), dtype=float)
    kwargs: dict[str, Any] = {"energy": energy, "forces": forces}
    try:
        kwargs["stress"] = atoms.get_stress()
    except Exception:
        pass
    atoms.calc = SinglePointCalculator(atoms, **kwargs)
    mark_endpoint_result(atoms, status)
    return atoms


def freeze_results(atoms, energy: float, forces, status: str):
    """Freeze explicit endpoint results using SinglePointCalculator."""
    atoms.calc = SinglePointCalculator(atoms, energy=float(energy), forces=np.asarray(forces, dtype=float))
    mark_endpoint_result(atoms, status)
    return atoms


def endpoint_policy(config: dict[str, Any], default: str = "auto") -> str:
    """Return and validate endpoint single-point policy from workflow config."""
    policy = config.get("endpoint_singlepoint", default)
    if policy not in {"auto", "always", "never"}:
        raise ValueError("endpoint_singlepoint must be one of: auto, always, never")
    return policy


def ensure_neb_endpoint_results(
    images: Sequence,
    get_calculator: Callable[[str], Any],
    policy: str = "auto",
    directories: tuple[str, str] = ("endpoint_initial", "endpoint_final"),
    context: str = "NEB",
):
    """Ensure the first and last images carry meaningful endpoint results.

    Args:
        images: NEB chain including endpoints.
        get_calculator: Callable receiving a directory suffix and returning an
            ASE calculator.
        policy: ``auto`` computes missing/placeholder endpoints, ``always``
            recomputes both endpoints, and ``never`` rejects invalid endpoints.
        directories: Directory suffixes for initial and final endpoint
            calculations.
        context: Text used in warning/error messages.

    Returns:
        The input images sequence after in-place endpoint preparation.
    """
    if policy not in {"auto", "always", "never"}:
        raise ValueError("endpoint_singlepoint must be one of: auto, always, never")
    if len(images) < 2:
        raise ValueError("NEB endpoint preparation requires at least two images")

    endpoint_specs = ((0, "initial", directories[0]), (-1, "final", directories[1]))
    for index, label, directory in endpoint_specs:
        atoms = images[index]
        valid = has_endpoint_results(atoms)
        if policy == "never" and not valid:
            raise ValueError(
                f"{context} {label} endpoint lacks meaningful energy/force results. "
                "Run endpoint single-point/optimization first or set endpoint_singlepoint=auto."
            )
        if policy == "auto" and valid:
            continue
        if policy == "auto":
            print(
                f"Warning: {context} {label} endpoint has missing or placeholder "
                "energy/force results; running an endpoint single-point calculation."
            )
        elif policy == "always":
            print(f"Warning: {context} {label} endpoint is being recomputed by endpoint_singlepoint=always.")

        atoms.calc = get_calculator(directory)
        freeze_current_results(atoms, status=ENDPOINT_COMPUTED)
    return images
