"""Path analysis helpers for NEB/D2S candidate and reaction-atom selection.

The helpers are deliberately independent of any optimizer.  They consume a
sequence of ASE ``Atoms`` images and return plain facts that the toolbox can
record as evidence:

* per-atom minimum-image displacement shares around a chosen candidate;
* the reaction progress of each image along the initial -> final direction;
* ranked interior candidates with energy, progress and maximum force.

The previous ``get_displacement_analysis`` selected the global highest-energy
image and used raw Cartesian differences.  Both choices are kept as an
explicit compatibility path, but callers that already know the candidate
should use :func:`get_anchored_displacement_analysis`.  Minimum-image
displacements are the default so periodic paths do not report atoms that
cross a cell boundary as large displacements.
"""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple

import numpy as np
from ase import Atoms
from ase.geometry import find_mic


def _energy(image: Atoms) -> float:
    """Return the stored potential energy without requiring a live calculator."""
    if image.calc is not None:
        try:
            return float(image.get_potential_energy())
        except Exception:
            pass
    return float(image.info.get("energy", 0.0))


def _forces(image: Atoms) -> np.ndarray | None:
    """Return stored forces from a calculator or the ``forces`` array."""
    if image.calc is not None:
        results = getattr(image.calc, "results", {}) or {}
        forces = results.get("forces")
        if forces is not None:
            return np.asarray(forces, dtype=float)
    forces = image.arrays.get("forces")
    return None if forces is None else np.asarray(forces, dtype=float)


def mic_displacement(reference: Atoms, image: Atoms) -> np.ndarray:
    """Return the per-atom minimum-image displacement reference -> image."""
    raw = np.asarray(image.positions, dtype=float) - np.asarray(
        reference.positions, dtype=float
    )
    vectors, _ = find_mic(raw, reference.cell, reference.pbc)
    return np.asarray(vectors, dtype=float)


def displacement_share(
    chain: Sequence[Atoms],
    index: int,
    *,
    use_mic: bool = True,
) -> np.ndarray:
    """Return the per-atom share of the local displacement around ``index``.

    The local displacement is ``image[index + 1] - image[index - 1]`` with
    endpoint clamping.  A share is the per-atom magnitude divided by the sum
    of all per-atom magnitudes, so the vector sums to one when the path moves.
    """
    if not chain:
        raise ValueError("chain must not be empty")
    index = int(index)
    if index < 0 or index >= len(chain):
        raise ValueError(
            f"candidate index {index} is outside chain of length {len(chain)}"
        )
    before = max(0, index - 1)
    after = min(len(chain) - 1, index + 1)
    if before == after:
        # Preserve the historical single-image contract: no displacement
        # vector exists, so the share array is empty rather than all zeros.
        return np.zeros(0, dtype=float)
    if use_mic:
        vectors = mic_displacement(chain[before], chain[after])
    else:
        vectors = np.asarray(chain[after].positions, dtype=float) - np.asarray(
            chain[before].positions, dtype=float
        )
    magnitudes = np.linalg.norm(vectors, axis=1)
    total = float(magnitudes.sum())
    if total < 1e-12:
        return np.zeros(len(magnitudes), dtype=float)
    return magnitudes / total


def get_anchored_displacement_analysis(
    chain: Sequence[Atoms],
    index: int,
    thr: float = 0.10,
    *,
    use_mic: bool = True,
) -> Tuple[int, List[int], np.ndarray]:
    """Select atoms whose local displacement share exceeds ``thr``.

    Args:
        chain: Path images.
        index: Chosen candidate image index.
        thr: Normalized share threshold (default 0.10).
        use_mic: Use minimum-image displacements.

    Returns:
        ``(index, main_indices, share)`` with zero-based atom indices.
    """
    share = displacement_share(chain, index, use_mic=use_mic)
    main = [atom_index for atom_index, value in enumerate(share) if value > float(thr)]
    return int(index), main, share


def get_displacement_analysis(
    neb_chain: Sequence[Atoms],
    thr: float = 0.10,
    *,
    use_mic: bool = True,
) -> Tuple[int, List[int], np.ndarray]:
    """Compatibility wrapper: pick the highest-energy image, then select atoms.

    Prefer :func:`get_anchored_displacement_analysis` when the candidate is
    already known: the global maximum of a drifted path is not necessarily the
    candidate that should be refined.
    """
    if not neb_chain:
        raise ValueError("neb_chain must not be empty")
    energies = [_energy(image) for image in neb_chain]
    ts_index = int(np.argmax(energies))
    return get_anchored_displacement_analysis(
        neb_chain, ts_index, thr=thr, use_mic=use_mic
    )


def path_progress(
    chain: Sequence[Atoms],
    *,
    init_index: int = 0,
    final_index: int = -1,
    use_mic: bool = True,
) -> np.ndarray:
    """Project every image onto the minimum-image initial -> final direction.

    The result is 0 at the initial image and 1 at the final image.  Values
    outside ``[0, 1]`` are retained because a curved or unconverged path may
    overshoot; callers decide how to interpret them.
    """
    if len(chain) < 2:
        return np.zeros(len(chain), dtype=float)
    init = chain[init_index]
    final = chain[final_index]
    if use_mic:
        direction = mic_displacement(init, final).ravel()
    else:
        direction = (
            np.asarray(final.positions, dtype=float)
            - np.asarray(init.positions, dtype=float)
        ).ravel()
    denominator = float(direction @ direction)
    if denominator < 1e-12:
        return np.zeros(len(chain), dtype=float)
    values = []
    for image in chain:
        if use_mic:
            delta = mic_displacement(init, image).ravel()
        else:
            delta = (
                np.asarray(image.positions, dtype=float)
                - np.asarray(init.positions, dtype=float)
            ).ravel()
        values.append(float(delta @ direction) / denominator)
    return np.asarray(values, dtype=float)


def path_quality(
    chain: Sequence[Atoms],
    *,
    init_index: int = 0,
    final_index: int = -1,
    use_mic: bool = True,
    tolerance: float = 0.05,
) -> dict[str, Any]:
    """Report whether the projected path progress is monotonic.

    A non-monotonic band means the frames are not a coherent initial -> final
    path: the candidate ranking may still return the highest image, but the
    progress and bond metrics must not be read as a reaction coordinate.
    """
    progress = path_progress(
        chain,
        init_index=init_index,
        final_index=final_index,
        use_mic=use_mic,
    )
    if len(progress) < 3:
        return {
            "monotonic": None,
            "max_regression": None,
            "tolerance": float(tolerance),
            "progress": [float(value) for value in progress],
        }
    differences = np.diff(progress)
    regressions = differences[differences < -float(tolerance)]
    return {
        "monotonic": bool(len(regressions) == 0),
        "max_regression": float(-regressions.min()) if len(regressions) else 0.0,
        "tolerance": float(tolerance),
        "progress": [float(value) for value in progress],
    }


def candidate_metrics(
    chain: Sequence[Atoms],
    *,
    init_index: int = 0,
    final_index: int = -1,
    use_mic: bool = True,
) -> List[dict[str, Any]]:
    """Return energy, progress and maximum force for every interior image."""
    if len(chain) < 3:
        return []
    progress = path_progress(
        chain,
        init_index=init_index,
        final_index=final_index,
        use_mic=use_mic,
    )
    metrics: List[dict[str, Any]] = []
    for index in range(1, len(chain) - 1):
        forces = _forces(chain[index])
        max_force = None if forces is None else float(np.linalg.norm(forces, axis=1).max())
        metrics.append(
            {
                "index": index,
                "energy_eV": _energy(chain[index]),
                "progress": float(progress[index]),
                "max_force_eV_A": max_force,
            }
        )
    return metrics


def _is_local_max(metrics: Sequence[dict[str, Any]], index: int) -> bool:
    by_index = {item["index"]: item["energy_eV"] for item in metrics}
    current = by_index.get(index)
    if current is None:
        return False
    previous = by_index.get(index - 1)
    following = by_index.get(index + 1)
    return (previous is None or current >= previous) and (
        following is None or current >= following
    )


def _complementary(
    metrics: Sequence[dict[str, Any]],
    *,
    k: int,
    window: Tuple[float, float],
) -> List[dict[str, Any]]:
    """Pick candidates that cover different roles, keeping the energy peak first.

    A true transition state may be early or late along the path, so the
    in-window preference must not displace the global energy maximum.  The
    window is only used for the ``outside_progress_window`` flag in
    :func:`rank_candidates`; here it only informs the complementary picks.
    """
    selected: List[dict[str, Any]] = []

    def add(item: dict[str, Any]) -> None:
        if len(selected) < k and all(
            chosen["index"] != item["index"] for chosen in selected
        ):
            selected.append(item)

    add(max(metrics, key=lambda item: (item["energy_eV"], -item["index"])))
    remaining = [item for item in metrics if item["index"] != selected[0]["index"]]
    if remaining:
        add(
            min(
                remaining,
                key=lambda item: (abs(item["progress"] - 0.5), -item["energy_eV"]),
            )
        )
    local_maxima = [
        item
        for item in remaining
        if _is_local_max(metrics, item["index"])
        and all(chosen["index"] != item["index"] for chosen in selected)
    ]
    if local_maxima:
        add(max(local_maxima, key=lambda item: item["energy_eV"]))
    for item in sorted(metrics, key=lambda item: (-item["energy_eV"], item["index"])):
        add(item)
    return selected


def rank_candidates(
    chain: Sequence[Atoms],
    *,
    k: int = 3,
    window: Tuple[float, float] = (0.15, 0.85),
    strategy: str = "complementary",
    init_index: int = 0,
    final_index: int = -1,
    use_mic: bool = True,
) -> List[dict[str, Any]]:
    """Rank interior candidates for single-ended refinement.

    ``strategy`` is one of ``energy`` (highest first), ``progress`` (closest
    to 0.5 first) or ``complementary`` (highest in-window energy, closest to
    0.5, a different local maximum, then energy order).  Progress is reported
    for every candidate and is never used as a hard filter.
    """
    metrics = candidate_metrics(
        chain,
        init_index=init_index,
        final_index=final_index,
        use_mic=use_mic,
    )
    if not metrics:
        return []
    lo, hi = window
    for item in metrics:
        progress = item["progress"]
        item["flags"] = [] if lo <= progress <= hi else ["outside_progress_window"]
    if strategy == "energy":
        ordered = sorted(
            metrics, key=lambda item: (-item["energy_eV"], item["index"])
        )
    elif strategy == "progress":
        ordered = sorted(
            metrics, key=lambda item: (abs(item["progress"] - 0.5), item["index"])
        )
    elif strategy == "complementary":
        ordered = _complementary(metrics, k=max(int(k), 0), window=window)
    else:
        raise ValueError("strategy must be one of: energy, progress, complementary")
    return ordered[: max(int(k), 0)]
