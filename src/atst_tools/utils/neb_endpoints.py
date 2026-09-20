"""Endpoint result validation and preparation for NEB-family workflows."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from ase.calculators.singlepoint import SinglePointCalculator

from atst_tools.calculators.constant_potential import (
    CP_FACTS_INFO_KEY,
    CP_IDENTITY_INFO_KEY,
    _mapping_contains,
    clear_constant_potential_facts,
    publish_constant_potential_facts,
    read_constant_potential_facts,
)


ENDPOINT_RESULT_KEY = "atst_endpoint_result"
ENDPOINT_PLACEHOLDER = "placeholder"
ENDPOINT_PROVIDED = "provided"
ENDPOINT_COMPUTED = "computed"
ENDPOINT_OPTIMIZED = "optimized"
CP_ENDPOINT_IDENTITY_KEY = CP_IDENTITY_INFO_KEY


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
    if CP_FACTS_INFO_KEY in atoms.info and read_constant_potential_facts(atoms) is None:
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


def has_trusted_endpoint_results(atoms) -> bool:
    """Return whether an endpoint carries ATST-marked trustworthy results.

    Only endpoints explicitly marked as ``provided``, ``computed``, or
    ``optimized`` by this tool are trusted. Readable results without such a
    marker (e.g. foreign/uploaded-chain values) are not trusted so that the
    ``auto`` policy can recompute them with the current run's calculator.
    """
    return (
        atoms.info.get(ENDPOINT_RESULT_KEY)
        in {ENDPOINT_PROVIDED, ENDPOINT_COMPUTED, ENDPOINT_OPTIMIZED}
        and get_endpoint_results(atoms) is not None
    )


def endpoint_constant_potential_identity(atoms) -> dict[str, Any] | None:
    """Return the CP identity staged with an endpoint, when present."""
    facts = read_constant_potential_facts(atoms)
    if facts is not None and isinstance(facts.get("identity"), dict):
        return dict(facts["identity"])
    value = atoms.info.get(CP_ENDPOINT_IDENTITY_KEY)
    return dict(value) if isinstance(value, dict) else None


def constant_potential_identity_matches(atoms, expected: dict[str, Any] | None) -> bool:
    """Return whether endpoint results carry the requested CP identity."""
    if expected is None:
        return True
    facts = read_constant_potential_facts(atoms)
    if facts is None or not isinstance(facts.get("identity"), dict):
        return False
    return _mapping_contains(facts["identity"], expected)


def freeze_current_results(atoms, status: str = ENDPOINT_COMPUTED):
    """Freeze current calculator results on an endpoint using SinglePointCalculator."""
    source_calculator = atoms.calc
    identity = getattr(source_calculator, "constant_potential_identity", None)
    energy = float(atoms.get_potential_energy())
    forces = np.asarray(atoms.get_forces(), dtype=float)
    kwargs: dict[str, Any] = {"energy": energy, "forces": forces}
    results = getattr(atoms.calc, "results", {}) if atoms.calc is not None else {}
    if "stress" in results:
        kwargs["stress"] = np.asarray(results["stress"], dtype=float)
    if identity is not None:
        # Explicitly copy the CP envelope before replacing the live calculator;
        # SinglePointCalculator does not retain backend-specific facts.
        if not isinstance(results, dict) or results.get("cp_converged") is not True:
            clear_constant_potential_facts(atoms)
        else:
            publish_constant_potential_facts(atoms, results, identity)
    else:
        clear_constant_potential_facts(atoms)
    atoms.calc = SinglePointCalculator(atoms, **kwargs)
    mark_endpoint_result(atoms, status)
    return atoms


def freeze_results(atoms, energy: float, forces, status: str | None):
    """Freeze explicit endpoint results using SinglePointCalculator."""
    clear_constant_potential_facts(atoms)
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
    constant_potential_identity: dict[str, Any] | None = None,
):
    """Ensure the first and last images carry meaningful endpoint results.

    Args:
        images: NEB chain including endpoints.
        get_calculator: Callable receiving a directory suffix and returning an
            ASE calculator.
        policy: ``auto`` only trusts endpoints explicitly marked by ATST as
            ``provided``/``computed``/``optimized`` and recomputes missing,
            placeholder, or unmarked (e.g. uploaded-chain/foreign) results with
            the current run's calculator; ``always`` recomputes both endpoints;
            ``never`` preserves user-provided readable endpoints (and raises only
            when an endpoint lacks meaningful energy/force results).
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
        if policy == "never":
            if not has_endpoint_results(atoms):
                raise ValueError(
                    f"{context} {label} endpoint lacks meaningful energy/force results. "
                    "Run endpoint single-point/optimization first or set endpoint_singlepoint=auto."
                )
            if not constant_potential_identity_matches(atoms, constant_potential_identity):
                raise ValueError(
                    f"{context} {label} endpoint lacks matching constant-potential identity; "
                    "set endpoint_singlepoint=auto to recompute it."
                )
            continue  # never = explicit preserve of user-provided readable endpoints
        if (
            policy == "auto"
            and has_trusted_endpoint_results(atoms)
            and constant_potential_identity_matches(atoms, constant_potential_identity)
        ):
            continue
        if policy == "auto":
            print(
                f"Warning: {context} {label} endpoint has missing, placeholder, or "
                "untrusted (unmarked) energy/force results; running an endpoint "
                "single-point calculation."
            )
        elif policy == "always":
            print(f"Warning: {context} {label} endpoint is being recomputed by endpoint_singlepoint=always.")

        atoms.calc = get_calculator(directory)
        freeze_current_results(atoms, status=ENDPOINT_COMPUTED)
    return images
